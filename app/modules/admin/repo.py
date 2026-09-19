"""管理端数据访问层。"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.constants import ROLE_RANK
from app.shared.db import get_db
from app.shared.db.models import Conversation, Itinerary, TokenUsage, User
from app.shared.utils import to_local_display
from app.shared.utils.datetime_util import LOCAL_TZ

#: 活跃用户排行返回的条数。
#: 用户要求「只显示前十，折叠后面七位」，因此这里多取一些，
#: 由前端负责「先展示前 3、其余折叠」——后端只保证数据够用。
ACTIVE_USER_LIMIT = 10
#: 为两种排序口径（会话数 / 当日消息数）预留的候选倍数。
#: 一次查询取回，在服务层按不同口径排序，避免为每种排序各查一次库。
ACTIVE_USER_POOL = ACTIVE_USER_LIMIT * 3


class AdminRepo:
    """管理端查询（只读为主 + 少量写操作，写操作的审计由 service 负责）。"""

    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        self.db = db

    # -------------------- 用户 --------------------
    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        viewer_rank: int | None = None,
    ) -> tuple[list[User], int]:
        """分页查询用户，支持邮箱/昵称关键词与角色、状态筛选。

        viewer_rank：查看者的角色层级。传入时会**过滤掉层级高于查看者的账号**
        （防止普通管理员看到超级管理员的邮箱，那是可被用于撞库/钓鱼的信息）。
        传 None 表示不做过滤（如 CLI 脚本）。
        """
        conditions = []
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(User.email.ilike(like), User.username.ilike(like)))
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if viewer_rank is not None:
            allowed = [r for r, rank in ROLE_RANK.items() if rank <= viewer_rank]
            conditions.append(User.role.in_(allowed))

        count_stmt = select(func.count(User.id))
        list_stmt = select(User)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        list_stmt = (
            list_stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        rows = list((await self.db.execute(list_stmt)).scalars().all())
        return rows, total

    async def get_user(self, user_id: int) -> User | None:
        return (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    async def user_usage_counts(self, user_id: int) -> tuple[int, int]:
        """返回 (会话数, 行程数)。"""
        conversations = (
            await self.db.execute(
                select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
            )
        ).scalar_one()
        itineraries = (
            await self.db.execute(
                select(func.count(Itinerary.id)).where(Itinerary.user_id == user_id)
            )
        ).scalar_one()
        return int(conversations), int(itineraries)

    async def count_super_admins(self) -> int:
        """当前启用状态的**超级管理员**数量。

        用于「不能停用/降级最后一个超级管理员」的保护。
        刻意不统计普通管理员：后者没有管理能力，即使剩好几个也无法靠它们
        恢复权限，把它们算进来会让保护形同虚设。
        """
        return int(
            (
                await self.db.execute(
                    select(func.count(User.id)).where(
                        User.role == "super_admin", User.is_active.is_(True)
                    )
                )
            ).scalar_one()
        )

    # -------------------- 会话洞察 --------------------
    async def conversation_stats(self) -> dict:
        """会话统计：只做聚合，不触碰任何用户内容。

        刻意不统计「已生成标题的会话数」——那个指标只服务于「查看会话标题」
        这个功能，标题已按隐私要求不再暴露，指标也就没有存在意义。
        """
        total_conversations = (
            await self.db.execute(select(func.count(Conversation.id)))
        ).scalar_one()
        total_messages = (
            await self.db.execute(select(func.coalesce(func.sum(Conversation.message_count), 0)))
        ).scalar_one()

        total_conv = int(total_conversations)
        total_msg = int(total_messages)
        # 排行取前 10：用户要求「只显示前十，折叠后面七位」，
        # 但下面还要展示「当日消息数」与「总体会话数」两个口径，
        # 故这里一并多取一些，由服务层按口径排序后再截断，
        # 避免为两种排序各查一次数据库。
        top_rows = (
            await self.db.execute(
                select(Conversation.user_id, func.count(Conversation.id).label("n"))
                .group_by(Conversation.user_id)
                .order_by(func.count(Conversation.id).desc())
                .limit(ACTIVE_USER_POOL)
            )
        ).all()
        user_ids = [r[0] for r in top_rows]

        emails: dict[int, str] = {}
        today_msg: dict[int, int] = {}
        if user_ids:
            user_rows = (
                await self.db.execute(
                    select(User.id, User.email).where(User.id.in_(user_ids))
                )
            ).all()
            emails = {r[0]: r[1] for r in user_rows}

            # 「今天」的消息数：在 Python 里算出**本地当天起点**，转成 UTC 后
            # 直接比较时间戳。
            #
            # 为什么不在 SQL 里取日期前缀：那样得到的是 UTC 日期，
            # 与用户感知的「今天」最多差 8 小时（UTC 的 16:00 之后已是北京的次日）。
            # 用时间戳区间比较既没有方言差异（PostgreSQL 的 to_char 与
            # SQLite 的 substr 完全不同），口径也与其它统计一致。
            start_local = datetime.now(LOCAL_TZ).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start_utc = start_local.astimezone(timezone.utc)
            day_rows = (
                await self.db.execute(
                    select(Conversation.user_id, func.count(Conversation.id))
                    .where(
                        Conversation.user_id.in_(user_ids),
                        Conversation.created_at >= start_utc,
                    )
                    .group_by(Conversation.user_id)
                )
            ).all()
            today_msg = {r[0]: int(r[1]) for r in day_rows}

        return {
            "total_conversations": total_conv,
            "total_messages": total_msg,
            # 用户要求「平均每会话消息应为**向下取整**的整数」。
            # 原先用 round(...,2) 得到 3.33 这种小数——对「平均每会话几条消息」
            # 这个指标来说，小数既没有意义也不好读。
            "avg_messages_per_conversation": total_msg // total_conv if total_conv else 0,
            "top_active_users": [
                {
                    "user_id": r[0],
                    "email": emails.get(r[0], "未知"),
                    "conversations": int(r[1]),
                    "today_messages": today_msg.get(r[0], 0),
                }
                for r in top_rows
            ],
        }

    async def list_conversations(
        self,
        *,
        page: int,
        page_size: int,
        user_id: int | None = None,
        sort: str = "created_desc",
    ) -> tuple[list[dict], int]:
        """分页查询会话元数据（不返回任何用户内容）。

        隐私约束：这里刻意**不查询也不返回 Conversation.title**。
        会话标题由 LLM 从用户消息生成，等同于用户内容——例如
        「帮我看看妇科检查」「离婚财产分割咨询」这类标题一旦对管理员
        可见，就是内容层面的隐私泄露，超出了运营统计的必要范围。

        同理，原先支持的 `keyword` 按标题模糊搜索也一并移除：
        那不只是「看见标题」，而是可以对全站用户的对话标题做关键词检索，
        属于系统性的内容窥探能力。

        sort 只提供两个与规模统计相关的维度，不做通用排序：
          created_desc  最新创建在前（默认，用于观察近期动态）
          messages_desc 消息数从多到少（用于定位规模最大的会话）
        """
        conditions = []
        if user_id:
            conditions.append(Conversation.user_id == user_id)

        count_stmt = select(func.count(Conversation.id))
        list_stmt = (
            select(
                Conversation.id,
                Conversation.user_id,
                User.email,
                # 不选 Conversation.title —— 见上方隐私说明
                Conversation.message_count,
                Conversation.created_at,
            )
            .join(User, User.id == Conversation.user_id)
        )
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        # 次级排序键统一用 id，保证同值行的顺序稳定（否则翻页会出现重复/遗漏）
        if sort == "messages_desc":
            list_stmt = list_stmt.order_by(
                Conversation.message_count.desc(), Conversation.id.desc()
            )
        else:
            list_stmt = list_stmt.order_by(
                Conversation.created_at.desc(), Conversation.id.desc()
            )
        list_stmt = list_stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(list_stmt)).all()
        items = [
            {
                "id": r[0],
                "user_id": r[1],
                "user_email": r[2],
                "message_count": r[3],
                # repo 直接返回 dict，不经过 Pydantic schema，
                # 故时间必须在此转成本地时区字符串；否则前端拿到的是 UTC，
                # 展示会早 8 小时（与用户详情页同样的问题）。
                "created_at": to_local_display(r[4]) if r[4] else None,
            }
            for r in rows
        ]
        return items, total

    # -------------------- 导出 --------------------
    async def iter_users_for_export(self):
        """流式导出用户（分批 yield，避免一次性载入全部行）。"""
        stmt = select(
            User.id, User.email, User.username, User.role, User.is_active, User.created_at
        ).order_by(User.id)
        result = await self.db.stream(stmt)
        async for row in result:
            yield row

    async def iter_token_usage_for_export(self):
        """流式导出用量明细。"""
        stmt = select(
            TokenUsage.record_date,
            TokenUsage.model,
            TokenUsage.input_tokens,
            TokenUsage.output_tokens,
            TokenUsage.total_tokens,
            TokenUsage.calls,
        ).order_by(TokenUsage.record_date.desc(), TokenUsage.model)
        result = await self.db.stream(stmt)
        async for row in result:
            yield row
