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
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, UserException
from app.shared.db import get_db
from app.shared.utils import TransactionMixin, log

from .repo import MemoryRepo
from .schemas import (
    ALLOWED_KEYS,
    CONFIDENCE_EXPLICIT,
    KEY_LABELS,
    VALUE_ENUMS,
    MemoryExtraction,
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
        stats = {"inserted": 0, "deduped": 0, "overwritten": 0, "rejected": 0}

        async with self.transaction_scope():
            for fact in extraction.facts:
                normalized = self._normalize(fact)
                if normalized is None:
                    stats["rejected"] += 1
                    continue
                key, value = normalized

                # 分支一：同一事实已存在 → 命中次数 +1（说明该偏好稳定）
                existing = await self.repo.find_exact(user_id, key, value)
                if existing is not None:
                    existing.hit_count = (existing.hit_count or 1) + 1
                    # 重复出现时若这次是明确表述，提升置信度
                    if fact.confidence > (existing.confidence or 0):
                        existing.confidence = fact.confidence
                    stats["deduped"] += 1
                    continue

                # 分支二：多值键 → 直接新增，与已有取值并存
                if self.repo.is_multi_value_key(key):
                    await self.repo.insert(
                        user_id=user_id,
                        fact_key=key,
                        fact_value=value,
                        confidence=fact.confidence,
                        evidence=(fact.evidence or "")[:500] or None,
                        source_conversation_id=conversation_id,
                        hit_count=1,
                    )
                    stats["inserted"] += 1
                    continue

                # 分支三：标量键换值 → 覆盖当前值并留痕旧值
                current = await self.repo.find_scalar(user_id, key)
                if current is None:
                    await self.repo.insert(
                        user_id=user_id,
                        fact_key=key,
                        fact_value=value,
                        confidence=fact.confidence,
                        evidence=(fact.evidence or "")[:500] or None,
                        source_conversation_id=conversation_id,
                        hit_count=1,
                    )
                    stats["inserted"] += 1
                else:
                    current.previous_value = current.fact_value
                    current.fact_value = value
                    current.confidence = fact.confidence
                    current.evidence = (fact.evidence or "")[:500] or None
                    current.source_conversation_id = conversation_id
                    current.hit_count = 1   # 换值后重新计数
                    current.is_active = True  # 用户改主意了，重新生效
                    stats["overwritten"] += 1

            await self.db.flush()

        return stats

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
