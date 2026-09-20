"""用户长期记忆接口：查看、修正、停用、删除自己的画像。

全部要求登录，且只能操作自己的记忆（service 层按归属校验，
不属于自己的 ID 统一按「不存在」处理，避免探测他人记忆）。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi_utils.cbv import cbv
from pydantic import BaseModel, Field
from starlette import status

from app.core.route import UnifiedRoute
from app.modules.user.dependencies import get_current_user
from app.shared.db.models import User

from .schemas import KEY_LABELS
from .service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"], route_class=UnifiedRoute)


class MemoryItem(BaseModel):
    """单条记忆。"""

    id: Annotated[int, Field(description="记忆 ID")]
    fact_key: Annotated[str, Field(description="事实键")]
    fact_key_label: Annotated[str, Field(description="事实键的中文标签，便于前端展示")]
    fact_value: Annotated[str, Field(description="当前取值")]
    values: Annotated[
        list[str],
        Field(
            description=(
                "拆开后的取值列表。多值键（偏好/饮食/去过的城市/同行人）"
                "在库里是「一行一个键、多项用「、」连接」，这里拆成数组供前端"
                "逐项展示与删除；标量键则只有一项。前端不必自己解析分隔符 —— "
                "拆分的口径必须与后端一致，放在后端才只有一处实现。"
            )
        ),
    ] = []
    is_multi: Annotated[bool, Field(description="是否多值键（决定前端能否逐项删除）")] = False
    previous_value: Annotated[str | None, Field(description="被覆盖的旧值（偏好变化的痕迹）")] = None
    confidence: Annotated[float, Field(description="置信度 0-1")]
    evidence: Annotated[str | None, Field(description="来源原文片段")] = None
    hit_count: Annotated[int, Field(description="被重复提取到的次数")]
    is_active: Annotated[bool, Field(description="是否生效（停用后不再注入对话）")]
    updated_at: Annotated[str | None, Field(description="最近更新时间")] = None

    @classmethod
    def from_model(cls, m) -> "MemoryItem":
        from app.modules.memory.schemas import MULTI_KEYS, split_values
        from app.shared.utils import to_local_display

        is_multi = m.fact_key in MULTI_KEYS
        return cls(
            id=m.id,
            fact_key=m.fact_key,
            fact_key_label=KEY_LABELS.get(m.fact_key, m.fact_key),
            fact_value=m.fact_value,
            values=split_values(m.fact_value) if is_multi else [m.fact_value],
            is_multi=is_multi,
            previous_value=m.previous_value,
            confidence=round(m.confidence or 0.0, 2),
            evidence=m.evidence,
            hit_count=m.hit_count or 1,
            is_active=m.is_active,
            updated_at=to_local_display(m.updated_at) if m.updated_at else None,
        )


class MemoryListResponse(BaseModel):
    memories: list[MemoryItem]
    stats: dict


class MemoryValueUpdate(BaseModel):
    """手动修正取值。"""

    fact_value: Annotated[str, Field(min_length=1, max_length=40, description="新的取值")]


class ToggleActiveRequest(BaseModel):
    """启停用一条记忆。"""

    is_active: Annotated[bool, Field(description="true=生效，false=停用（停用后不再注入对话）")]


@cbv(router)
class MemoryRouter:
    service: MemoryService = Depends()
    current_user: User = Depends(get_current_user)

    @router.get("/", status_code=status.HTTP_200_OK, summary="查看我的长期记忆")
    async def list_memories(
        self,
        include_inactive: Annotated[
            bool, Query(description="是否包含已停用的记忆")
        ] = False,
    ):
        memories = await self.service.list_memories(
            self.current_user.id, include_inactive=include_inactive
        )
        return MemoryListResponse(
            memories=[MemoryItem.from_model(m) for m in memories],
            stats=await self.service.stats(self.current_user.id),
        )

    @router.patch(
        "/{memory_id}",
        status_code=status.HTTP_200_OK,
        summary="修正某条记忆的取值",
    )
    async def update_memory(
        self,
        memory_id: Annotated[int, Path(ge=1, description="记忆 ID")],
        req: MemoryValueUpdate,
    ):
        memory = await self.service.update_value(
            user_id=self.current_user.id, memory_id=memory_id, fact_value=req.fact_value
        )
        return MemoryItem.from_model(memory)

    @router.patch(
        "/{memory_id}/active",
        status_code=status.HTTP_200_OK,
        summary="启用/停用某条记忆",
    )
    async def toggle_memory(
        self,
        memory_id: Annotated[int, Path(ge=1, description="记忆 ID")],
        req: ToggleActiveRequest,
    ):
        memory = await self.service.set_active(
            user_id=self.current_user.id, memory_id=memory_id, is_active=req.is_active
        )
        return MemoryItem.from_model(memory)

    @router.delete(
        "/{memory_id}/values/{fact_value}",
        status_code=status.HTTP_200_OK,
        summary="删除多值记忆中的某一项",
    )
    async def remove_value(
        self,
        memory_id: Annotated[int, Path(ge=1, description="记忆 ID")],
        fact_value: Annotated[str, Path(min_length=1, max_length=40, description="要删除的那一项")],
    ):
        """只删一项而不是整条。

        合并成一行后，整条删除会把所有城市一起删掉；用户想纠正
        「我没去过桂林」时不该被迫全删重来。删到零项时整行一起删。

        取值放路径而不是请求体：DELETE 带 body 虽然 axios 支持，
        但语义上带 body 的 DELETE 一直是灰色地带（部分代理会丢弃）。
        放路径还能天然享受 URL 解码 —— 前端 encodeURIComponent 即可。
        """
        memory = await self.service.remove_value(
            user_id=self.current_user.id, memory_id=memory_id, fact_value=fact_value
        )
        # 剩最后一项被删掉时整行已不存在，返回 deleted 让前端知道要移除这张卡
        if memory is None:
            return {"deleted": True}
        return MemoryItem.from_model(memory)

    @router.delete(
        "/{memory_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除某条记忆",
    )
    async def delete_memory(
        self,
        memory_id: Annotated[int, Path(ge=1, description="记忆 ID")],
    ):
        await self.service.delete_memory(user_id=self.current_user.id, memory_id=memory_id)

    @router.delete(
        "/",
        status_code=status.HTTP_200_OK,
        summary="清空我的全部长期记忆",
    )
    async def clear_memories(self):
        """隐私诉求：用户有权一键抹掉系统对自己的画像。"""
        deleted = await self.service.clear_all(self.current_user.id)
        return {"deleted": deleted}
