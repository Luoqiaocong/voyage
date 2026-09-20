"""用户长期记忆业务层。

三条主线
--------
1. 提炼（extract_from_conversation）：对话结束后异步从文本里提取事实并落库。
2. 注入（build_memory_context）：新会话开始时把记忆渲染成一段提示词文本，
   拼到 system prompt 后面，让模型"记得"用户偏好。
3. 管理（list/update/delete/clear）：用户可查看、停用、删除自己的记忆。

为什么注入用「文本片段」而不是工具（让模型自己查询）：
   - 旅行场景的记忆量很小（通常 5-15 条），全量注入的开销可忽略；
   - 工具方式需要模型主动想起去查，实测容易被忽略；
   - 文本注入对模型更"显眼"，且不占用额外的工具调用轮次与额度。
   代价是记忆条数必须收敛，故设置了 MAX_INJECT 上限并按置信度排序截断。
"""
import re
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.shared.db import get_db
from app.shared.db.models import UserMemory
from app.shared.utils import TransactionMixin, log

from .repo import MemoryRepo
from .schemas import (
    ALLOWED_KEYS,
    CONFIDENCE_EXPLICIT,
    KEY_LABELS,
    MULTI_KEYS,
    VALUE_ENUMS,
    MemoryExtraction,
    canonical_value,
    merge_values,
    pack_values,
    split_values,
)

# 注入 prompt 的最大记忆条数。
# 保守取 12 条：再多会稀释 system prompt 的指令权重，反而降低遵循度。
MAX_INJECT_FACTS = 12

# 低于该置信度的记忆不注入（但仍保留在库里供用户查看）。
# 目的是避免"模型瞎猜的推断"影响正常回答。
MIN_INJECT_CONFIDENCE = 0.5


class MemoryService(TransactionMixin):
    def __init__(
        self,
        repo: Annotated[MemoryRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        self.repo = repo
        self.db = db

    # ==================== 1. 提炼与落库 ====================
    @staticmethod
    def _normalize(fact) -> tuple[str, str] | None:
        """规整并校验一条事实；不合法返回 None（丢弃而不是写脏数据）。

        校验三件事：
        - 键必须在白名单内（否则冲突消解失效）；
        - 取值不能为空且不过长（避免整句话被当标签存进来）；
        - 取值有限的键必须在枚举内（如 budget_level）。
        """
        key = (fact.fact_key or "").strip()
        value = (fact.fact_value or "").strip()
        if key not in ALLOWED_KEYS:
            log.warning(f"[memory] 丢弃未知键: {key!r}")
            return None
        if not value or len(value) > 40:
            log.warning(f"[memory] 丢弃异常取值: key={key} value={value!r}")
            return None
        allowed_values = VALUE_ENUMS.get(key)
        if allowed_values and value not in allowed_values:
            log.warning(f"[memory] 丢弃非法枚举值: key={key} value={value!r}")
            return None
        return key, value

    @staticmethod
    def _canonical(value: str) -> str:
        """宽松归一：用于「同一事实的不同写法」判定。

        实现已下沉到 schemas._canonical_value —— merge_values 也需要它，
        而 service 依赖 schemas（不能反向导入）。**只能有一份实现**：
        两边口径一旦分叉，就会出现「合并时判为不同、查找时判为相同」
        这类自相矛盾的行为，且很难查。
        """
        return canonical_value(value)

    @classmethod
    def _expand_multi(cls, key: str, value: str) -> list[str]:
        """把一个取值拆成若干「单项」。

        为什么必须拆：实测模型会把多条事实挤进一个值 ——
        「北京、上海、广州」被存成一条，同时又单独存了「北京」「上海」「广州」。
        不拆的话，那条合并值永远无法与单城条目比对，去重必然失效。

        只在**多值键**上拆（visited_city / preference / companion / dietary）：
        标量键（home_city、budget_level）的值本身不该含分隔符，
        真含了说明提炼有问题，交给 _normalize 的长度与枚举校验处理。

        拆分符涵盖中英文顿号、逗号、斜杠，以及「和/与/及」——
        但「和」只在两侧都有内容时才拆（「和风」这类词不应被切断）。
        """
        if key not in MULTI_KEYS:
            return [value]

        # 先用标点拆，再用连接词拆（分开做，避免正则过于复杂而误伤）
        parts = re.split(r"[、,，;；/／|]+", value)
        expanded: list[str] = []
        for p in parts:
            expanded.extend(re.split(r"(?<=.)[和与及](?=.)", p))

        out = [p.strip() for p in expanded if p and p.strip()]
        # 全部拆没了（例如值就是一个分隔符）时退回原值，避免丢数据
        return out or [value]

    async def upsert_facts(
        self,
        *,
        user_id: int,
        extraction: MemoryExtraction,
        conversation_id: str | None,
    ) -> dict[str, int]:
        """把提炼结果合并进库，返回各类处理计数。

        冲突消解的分支见 repo 模块文档；这里负责编排并保证在同一事务内完成。
        """
        stats = {"inserted": 0, "deduped": 0, "overwritten": 0, "rejected": 0, "appended": 0}

        async with self.transaction_scope():
            for fact in extraction.facts:
                normalized = self._normalize(fact)
                if normalized is None:
                    stats["rejected"] += 1
                    continue
                key, raw_value = normalized

                # 一个取值可能含多项（模型偶尔不遵守「一件事一个值」），
                # 逐个处理，使每一项都能与已有记录正确比对
                for value in self._expand_multi(key, raw_value):
                    await self._upsert_one(
                        user_id=user_id,
                        key=key,
                        value=value,
                        confidence=fact.confidence,
                        evidence=fact.evidence,
                        conversation_id=conversation_id,
                        stats=stats,
                    )

            # repo.insert 内部已 flush，但标量覆盖改的是 ORM 对象属性，
            # 需在事务提交前统一 flush 一次
            await self.db.flush()

        return stats

    async def _upsert_one(
        self,
        *,
        user_id: int,
        key: str,
        value: str,
        confidence: float,
        evidence: str | None,
        conversation_id: str | None,
        stats: dict[str, int],
    ) -> None:
        """写入单条事实（已拆分、已归一）。"""
        # 分支一：同一事实已存在 → 命中次数 +1（说明该偏好稳定）
        #
        # 比对用宽松归一而非精确相等：实测重复多来自措辞差异
        # （「美食」/「美食。」，或「北京市」/「北京」），
        # 精确匹配挡不住，会各存一条。
        existing = await self._find_loose(user_id, key, value)
        if existing is not None:
            existing.hit_count = (existing.hit_count or 1) + 1
            # 重复出现时若这次是明确表述，提升置信度
            if confidence > (existing.confidence or 0):
                existing.confidence = confidence
            stats["deduped"] += 1
            return

        # 分支二：多值键 → **并入该键已有的那一行**（而不是新增一行）
        #
        # 原先这里直接 insert，于是「去过的城市」有三座就三行，
        # 用户在记忆面板看到三张几乎相同的卡（实测 6 条记忆里 3 条是城市）。
        # 而注入 prompt 时本来就是按键聚合的 —— 聚合才是这些键的真实语义。
        # 改为一行一个键之后：展示是一张卡、注入是一行、唯一约束也真正生效。
        if self.repo.is_multi_value_key(key):
            row = await self._find_by_key(user_id, key)
            if row is None:
                await self.repo.insert(
                    user_id=user_id,
                    fact_key=key,
                    fact_value=value,
                    confidence=confidence,
                    evidence=(evidence or "")[:500] or None,
                    source_conversation_id=conversation_id,
                    hit_count=1,
                )
                stats["inserted"] += 1
                return
            before = split_values(row.fact_value)
            merged = merge_values(row.fact_value, value)
            if len(merged) == len(before):
                # 归一后已存在（如「北京」与「北京市」）→ 只累加命中次数
                row.hit_count = (row.hit_count or 1) + 1
                stats["deduped"] += 1
                return
            row.fact_value = pack_values(merged)
            # 一次提炼里出现的新项也算一次命中；置信度取高者
            row.hit_count = (row.hit_count or 1) + 1
            if confidence > (row.confidence or 0):
                row.confidence = confidence
            if evidence:
                row.evidence = evidence[:500]
            # 用户之前停用过这一项，说明他不认可；但新项是他这次说的，
            # 重新生效更符合预期（与标量键换值一致）
            row.is_active = True
            stats["appended"] += 1
            return

        # 分支三：标量键换值 → 覆盖当前值并留痕旧值
        # 分支三：标量键换值 → 覆盖当前值并留痕旧值
        current = await self.repo.find_scalar(user_id, key)
        if current is None:
            await self.repo.insert(
                user_id=user_id,
                fact_key=key,
                fact_value=value,
                confidence=confidence,
                evidence=(evidence or "")[:500] or None,
                source_conversation_id=conversation_id,
                hit_count=1,
            )
            stats["inserted"] += 1
        else:
            current.previous_value = current.fact_value
            current.fact_value = value
            current.confidence = confidence
            current.evidence = (evidence or "")[:500] or None
            current.source_conversation_id = conversation_id
            current.hit_count = 1   # 换值后重新计数
            current.is_active = True  # 用户改主意了，重新生效
            stats["overwritten"] += 1

    async def _find_loose(self, user_id: int, key: str, value: str) -> UserMemory | None:
        """按宽松归一比对该键下已有的取值，命中则返回那一行。

        为什么不能直接用唯一约束或精确查询：
        库里的唯一约束是 (user_id, fact_key, fact_value) 精确匹配，
        而实测的重复多来自措辞差异 ——「美食」与「美食。」、「北京」与「北京市」。
        精确匹配挡不住，会各存一条，于是同一个偏好显示两遍。

        多值键现在是「一行一个键、取值用分隔符挤在一起」，所以比对要逐项做
        （见 _find_value_in_multi），不能拿整串比。
        """
        if self.repo.is_multi_value_key(key):
            row = await self._find_by_key(user_id, key)
            if row is None:
                return None
            target = self._canonical(value)
            hit = any(self._canonical(v) == target for v in split_values(row.fact_value))
            return row if hit else None

        rows = list(
            (
                await self.db.execute(
                    select(UserMemory).where(
                        UserMemory.user_id == user_id,
                        UserMemory.fact_key == key,
                    )
                )
            )
            .scalars()
            .all()
        )
        target = self._canonical(value)
        for row in rows:
            if self._canonical(row.fact_value) == target:
                return row
        return None

    async def _find_by_key(self, user_id: int, key: str) -> UserMemory | None:
        """取某键的那一行（多值键与标量键都是「一键一行」）。"""
        return await self.repo.find_scalar(user_id, key)

    async def extract_from_text(
        self, *, user_id: int, text: str, conversation_id: str | None = None
    ) -> dict[str, int]:
        """从对话文本提炼记忆并落库（供后台任务调用）。

        提炼失败不影响主流程：返回全 0 统计并记录日志。
        """
        if not text or not text.strip():
            return {"inserted": 0, "deduped": 0, "overwritten": 0, "rejected": 0}

        from app.core.ai.tasks.structured import extract_structured

        from .schemas import MEMORY_SYSTEM_PROMPT

        try:
            result = await extract_structured(
                text,
                MemoryExtraction,
                temperature=0.1,
                system_instructions=MEMORY_SYSTEM_PROMPT,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(f"[memory] 提炼调用失败: {type(exc).__name__}: {exc}")
            return {"inserted": 0, "deduped": 0, "overwritten": 0, "rejected": 0}

        if result is None or not result.facts:
            return {"inserted": 0, "deduped": 0, "overwritten": 0, "rejected": 0}

        return await self.upsert_facts(
            user_id=user_id, extraction=result, conversation_id=conversation_id
        )

    # ==================== 2. 注入 ====================
    async def build_memory_context(self, user_id: int) -> str:
        """把用户记忆渲染成可拼进 system prompt 的文本；无记忆时返回空串。"""
        memories = await self.repo.list_by_user(user_id, include_inactive=False)
        if not memories:
            return ""

        usable = [
            m for m in memories
            if (m.confidence or 0) >= MIN_INJECT_CONFIDENCE
        ][:MAX_INJECT_FACTS]
        if not usable:
            return ""

        # 按键聚合：多值键的多个取值合并成一行，读起来更像"画像"
        grouped: dict[str, list[str]] = {}
        for m in usable:
            grouped.setdefault(m.fact_key, []).append(m.fact_value)

        lines = [
            f"- {KEY_LABELS.get(key, key)}：{'、'.join(values)}"
            for key, values in grouped.items()
        ]
        return (
            "## 关于这位用户的已知信息（来自以往对话）\n"
            + "\n".join(lines)
            + "\n\n请在规划时自然地参考以上偏好；若与本次需求冲突，以用户本次的说法为准，"
            "不要生硬复述这些信息。"
        )

    # ==================== 3. 用户管理 ====================
    async def list_memories(self, user_id: int, *, include_inactive: bool = False):
        return await self.repo.list_by_user(user_id, include_inactive=include_inactive)

    async def _require_own(self, user_id: int, memory_id: int):
        memory = await self.repo.get(memory_id)
        if memory is None or memory.user_id != user_id:
            # 统一按「不存在」处理，避免通过 ID 探测他人记忆是否存在
            raise UserException(code=BusinessCode.NOT_FOUND, msg="记忆不存在")
        return memory

    async def set_active(self, *, user_id: int, memory_id: int, is_active: bool):
        """启用/停用一条记忆（停用后不再注入，但保留数据）。"""
        memory = await self._require_own(user_id, memory_id)
        memory.is_active = is_active
        async with self.transaction_scope():
            await self.db.flush()
        return memory

    async def update_value(self, *, user_id: int, memory_id: int, fact_value: str):
        """用户手动修正某条记忆的取值。"""
        memory = await self._require_own(user_id, memory_id)
        value = (fact_value or "").strip()
        if not value or len(value) > 40:
            raise UserException(code=BusinessCode.PARAM_INVALID, msg="取值长度需在 1-40 字之间")
        allowed = VALUE_ENUMS.get(memory.fact_key)
        if allowed and value not in allowed:
            raise UserException(
                code=BusinessCode.PARAM_INVALID,
                msg=f"该字段只能取：{'/'.join(sorted(allowed))}",
            )
        # 手动修正视为用户明确表述，置信度提到最高并清除旧值留痕
        memory.previous_value = memory.fact_value
        memory.fact_value = value
        memory.confidence = CONFIDENCE_EXPLICIT
        memory.is_active = True
        async with self.transaction_scope():
            await self.db.flush()
        return memory

    async def delete_memory(self, *, user_id: int, memory_id: int) -> None:
        memory = await self._require_own(user_id, memory_id)
        async with self.transaction_scope():
            await self.db.delete(memory)

    async def remove_value(self, *, user_id: int, memory_id: int, fact_value: str):
        """从多值键里删掉**其中一项**（例如「去过的城市」里去掉一座城）。

        为什么需要它：合并成一行之后，整条删除会把所有城市一起删掉 ——
        用户想纠正「我没去过桂林」时只能全删再等它重新提炼，太粗暴。

        只剩一项时再删就删整行：留一行空值没有意义，也会让面板显示一个空卡片。
        """
        memory = await self._require_own(user_id, memory_id)
        if not self.repo.is_multi_value_key(memory.fact_key):
            raise UserException(
                code=BusinessCode.PARAM_INVALID,
                msg="该记忆只有一个取值，请直接删除整条",
            )
        target = self._canonical(fact_value)
        kept = [v for v in split_values(memory.fact_value) if self._canonical(v) != target]
        if len(kept) == len(split_values(memory.fact_value)):
            raise UserException(code=BusinessCode.NOT_FOUND, msg="该项不存在")

        async with self.transaction_scope():
            if not kept:
                await self.db.delete(memory)
                return None
            memory.fact_value = pack_values(kept)
            await self.db.flush()
        return memory

    async def clear_all(self, user_id: int) -> int:
        """清空该用户的全部记忆（隐私诉求：用户有权抹掉画像）。"""
        memories = await self.repo.list_by_user(user_id, include_inactive=True)
        async with self.transaction_scope():
            for memory in memories:
                await self.db.delete(memory)
        return len(memories)

    async def stats(self, user_id: int) -> dict[str, Any]:
        """记忆概览，供用户端展示「系统记住了什么」。"""
        all_memories = await self.repo.list_by_user(user_id, include_inactive=True)
        active = [m for m in all_memories if m.is_active]
        return {
            "total": len(all_memories),
            "active": len(active),
            "inactive": len(all_memories) - len(active),
            "by_key": {
                key: len([m for m in active if m.fact_key == key])
                for key in sorted({m.fact_key for m in active})
            },
        }
