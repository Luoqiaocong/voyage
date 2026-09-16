"""行程分享业务层。

安全设计
--------
1. 令牌用 secrets.token_urlsafe(32)（约 256 bit 熵），不可枚举、不可猜测；
   对外不暴露行程 ID，拿到链接也推不出其他行程。
2. 密码只存 argon2 哈希（复用用户模块实现），校验用恒定时间比较。
   同时另存明文以便分享者"再次查看"，这是与项目既有 REFRESH_TOKEN 存储一致的
   权衡；属于已知弱点，已在模型注释中标注生产环境应移除。
3. 失效判定统一在 _resolve_share 里完成（不存在/已撤销/已过期），
   调用方拿到的必然是可用分享，避免各处重复判断而遗漏某一分支。
4. 「不存在」与「已撤销」对外返回同一个业务码，避免被用来枚举有效令牌。
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business import BusinessCode, ItineraryException
from app.modules.user.auth import PasswordManager
from app.shared.db import get_db
from app.shared.utils import TransactionMixin

from .repo import ItineraryRepo
from .share_repo import ShareRepo
from .util import generate_share_token


class ShareService(TransactionMixin):
    def __init__(
        self,
        share_repo: Annotated[ShareRepo, Depends()],
        itinerary_repo: Annotated[ItineraryRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        self.share_repo = share_repo
        self.itinerary_repo = itinerary_repo
        self.db = db

    # ==================== 内部：失效判定 ====================
    @staticmethod
    def _status_of(share) -> str:
        """计算分享当前状态：active / expired / revoked。"""
        if share.revoked_at is not None:
            return "revoked"
        if share.expires_at is not None:
            expires = share.expires_at
            # SQLite 存回的 datetime 可能不带 tzinfo，统一按 UTC 处理后再比较
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                return "expired"
        return "active"

    async def _resolve_share(self, token: str):
        """按令牌取出可用分享；不可用时按原因抛异常。

        不存在与已撤销刻意归为同一个错误码：否则攻击者可通过错误码差异
        判断某个令牌是否曾经存在过。
        """
        share = await self.share_repo.get_by_token(token)
        if share is None:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)

        status = self._status_of(share)
        if status == "revoked":
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)
        if status == "expired":
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_EXPIRED)
        return share

    @staticmethod
    def _verify_password(share, password: str | None) -> None:
        """校验访问密码；未设密码则直接通过。"""
        if not share.password_hash:
            return
        if not password:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_PASSWORD_REQUIRED)
        if not PasswordManager.verify(password, share.password_hash):
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_PASSWORD_WRONG)

    # ==================== 分享者侧：管理分享 ====================
    async def check_own_itinerary(self, user_id: int, itinerary_id: int) -> None:
        """确认行程属于该用户（分享管理操作的前置校验）。"""
        itinerary = await self.itinerary_repo.get(itinerary_id)
        if not (itinerary and itinerary.user_id == user_id):
            raise ItineraryException(BusinessCode.ITINERARY_NOT_FOUND)

    async def create_share(
        self,
        *,
        user_id: int,
        itinerary_id: int,
        allow_copy: bool,
        allow_edit: bool,
        password: str | None,
        expires_in_days: int | None,
    ):
        """创建分享链接。"""
        await self.check_own_itinerary(user_id, itinerary_id)

        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days
            else None
        )
        async with self.transaction_scope():
            return await self.share_repo.insert(
                itinerary_id=itinerary_id,
                owner_id=user_id,
                token=generate_share_token(),
                allow_copy=allow_copy,
                allow_edit=allow_edit,
                password_hash=PasswordManager.hash(password) if password else None,
                password_plain=password or None,
                expires_at=expires_at,
            )

    async def list_shares(self, *, user_id: int, itinerary_id: int):
        """列出某行程的全部分享链接。"""
        await self.check_own_itinerary(user_id, itinerary_id)
        return await self.share_repo.list_by_itinerary(itinerary_id)

    async def list_my_shares(self, user_id: int):
        """列出我创建的全部分享链接（跨行程）。"""
        return await self.share_repo.list_by_owner(user_id)

    async def update_share(
        self,
        *,
        user_id: int,
        share_id: int,
        allow_copy: bool | None,
        allow_edit: bool | None,
        password: str | None,
        clear_password: bool,
        expires_in_days: int | None,
        clear_expiry: bool,
    ):
        """修改分享设置（只改传入的字段）。"""
        share = await self._require_own_share(user_id, share_id)

        if allow_copy is not None:
            share.allow_copy = allow_copy
        if allow_edit is not None:
            share.allow_edit = allow_edit

        if clear_password:
            share.password_hash = None
            share.password_plain = None
        elif password:
            share.password_hash = PasswordManager.hash(password)
            share.password_plain = password

        if clear_expiry:
            share.expires_at = None
        elif expires_in_days is not None:
            share.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        async with self.transaction_scope():
            await self.db.flush()
        return share

    async def revoke_share(self, *, user_id: int, share_id: int):
        """撤销分享（保留记录以便追溯，只是置失效）。"""
        share = await self._require_own_share(user_id, share_id)
        if share.revoked_at is None:
            share.revoked_at = datetime.now(timezone.utc)
            async with self.transaction_scope():
                await self.db.flush()
        return share

    async def _require_own_share(self, user_id: int, share_id: int):
        """取分享并确认属于该用户；否则按「不存在」处理避免探测他人分享 ID。"""
        share = await self.share_repo.get_by_id(share_id)
        if share is None or share.owner_id != user_id:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)
        return share

    # ==================== 访问者侧：读取分享 ====================
    async def inspect(self, token: str) -> dict[str, Any]:
        """预检：链接是否可用、是否需要密码。

        刻意不返回行程内容——这样未登录用户也能先看到「需要密码」的提示页，
        而不是先报错再让前端猜。
        """
        share = await self.share_repo.get_by_token(token)
        if share is None or self._status_of(share) != "active":
            # 与 _resolve_share 保持一致：不区分不存在与已撤销
            reason = (
                "expired"
                if share is not None and self._status_of(share) == "expired"
                else "unavailable"
            )
            return {
                "available": False,
                "requires_password": False,
                "reason": reason,
                "destination": None,
                "days": None,
            }

        itinerary = await self.itinerary_repo.get(share.itinerary_id)
        plan = (itinerary.plan or {}) if itinerary else {}
        return {
            "available": True,
            "requires_password": bool(share.password_hash),
            # 目的地与天数属于"轻量预览"，不涉及具体安排，可在密码校验前展示
            "destination": plan.get("destination"),
            "days": plan.get("days"),
            "reason": None,
        }

    async def open_shared(
        self, *, token: str, password: str | None
    ) -> tuple[dict[str, Any], Any]:
        """校验令牌与密码后返回行程内容，并累加访问计数。

        Returns:
            (行程字段字典, 分享者昵称)
        """
        share = await self._resolve_share(token)
        self._verify_password(share, password)

        itinerary = await self.itinerary_repo.get(share.itinerary_id)
        if itinerary is None:
            # 分享级联删除理论上不会留孤儿，这里兜底并给出统一错误码
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)

        owner = await self.share_repo.get_owner(share.owner_id)

        async with self.transaction_scope():
            view_count = await self.share_repo.bump_view_count(share)

        payload = {
            "itinerary_id": itinerary.id,
            "plan": itinerary.plan,
            "allow_copy": share.allow_copy,
            "allow_edit": share.allow_edit,
            "view_count": view_count,
            "owner_name": owner.username if owner else None,
            "created_at": itinerary.created_at,
            "updated_at": itinerary.updated_at,
        }
        return payload, share

    async def copy_to_my_account(
        self, *, token: str, password: str | None, user_id: int
    ) -> Any:
        """把分享的行程复制一份到访问者自己的账号。

        复制的是行程内容快照：之后两边独立演进，互不影响。
        这正是「可复制」与「可编辑」的区别——前者产生副本，后者改原件。
        """
        share = await self._resolve_share(token)
        self._verify_password(share, password)
        if not share.allow_copy:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_ALLOWED)

        source = await self.itinerary_repo.get(share.itinerary_id)
        if source is None:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)

        async with self.transaction_scope():
            return await self.itinerary_repo.insert(
                conversation_id=None,      # 副本不继承来源会话，避免与原对话纠缠
                user_id=user_id,
                plan=dict(source.plan or {}),
            )

    async def extend_shared(
        self,
        *,
        token: str,
        password: str | None,
        user_id: int | None,
        changes: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """在分享链接上编辑行程（需 allow_edit）。

        并发覆盖的处理：多人同时编辑同一份行程时，后写会覆盖先写。
        这里采取保守策略——**只有行程所有者本人**通过分享链接编辑时才写回原件；
        其他人返回合并后的结果但不落库，由前端提示「已生成你的版本，可复制保存」。
        这样不会出现"陌生访问者悄悄改掉你的行程"。

        Returns:
            (是否已写入原件, 合并后的 plan)
        """
        share = await self._resolve_share(token)
        self._verify_password(share, password)
        if not share.allow_edit:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_ALLOWED)

        itinerary = await self.itinerary_repo.get(share.itinerary_id)
        if itinerary is None:
            raise ItineraryException(BusinessCode.ITINERARY_SHARE_NOT_FOUND)

        # 只取非 None 的字段；与行程模块 PATCH 的语义保持一致（显式 null 视为不修改）
        applied = {k: v for k, v in changes.items() if v is not None}
        merged = {**(itinerary.plan or {}), **applied}

        # 合并后仍做一次结构校验，避免写入破坏 days 与 daily_plans 一致性的脏数据
        from .schemas import ItineraryPlan

        validated = ItineraryPlan.model_validate(merged).model_dump()

        is_owner = user_id is not None and user_id == itinerary.user_id
        if is_owner:
            async with self.transaction_scope():
                await self.itinerary_repo.update(itinerary, plan=validated)
            return True, validated
        return False, validated
