"""管理端操作审计日志：记录谁、何时、对谁、做了什么、改前改后是什么。

只记录管理端的**写操作**。目标对象用 (target_type, target_id) 弱关联而非外键——
被操作对象后续可能被删除，但审计记录必须保留下来。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.models import AdminAuditLog, utc_now


async def record(
    session: AsyncSession,
    *,
    operator_id: int,
    operator_email: str,
    action: str,
    target_type: str,
    target_id: str | int,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """写入一条审计记录。

    刻意不 commit：由调用方放在同一事务里，保证「业务变更成功」与
    「审计留痕」要么都生效、要么都不生效，不会出现改了却没记录的缺口。

    这里**不再吞掉写入异常**：原实现用 try/except 记日志后继续，
    但 flush 失败后会话已进入失败状态，事务随后 commit 必然报错——
    所谓「留痕失败但业务继续」根本不会发生，只是把错误推迟、并让
    「改了却没记录」的缺口看起来被兜住了。改为让异常向上抛，
    由 transaction_scope 回滚整笔操作，语义与事务保证一致。
    detail 用 default=str 兜底，非 JSON 原生类型不会成为新的失败点。
    """
    session.add(
        AdminAuditLog(
            operator_id=operator_id,
            operator_email=operator_email,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=(
                json.dumps(detail, ensure_ascii=False, default=str) if detail else None
            ),
            ip=ip,
            created_at=utc_now(),
        )
    )
    await session.flush()


async def list_logs(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    operator_id: int | None = None,
    target_id: str | None = None,
) -> tuple[list[AdminAuditLog], int]:
    """分页查询审计日志（按时间倒序）。"""
    conditions = []
    if action:
        conditions.append(AdminAuditLog.action == action)
    if operator_id:
        conditions.append(AdminAuditLog.operator_id == operator_id)
    if target_id:
        conditions.append(AdminAuditLog.target_id == str(target_id))

    count_stmt = select(func.count(AdminAuditLog.id))
    list_stmt = select(AdminAuditLog)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        list_stmt = list_stmt.where(cond)

    total = int((await session.execute(count_stmt)).scalar_one())
    list_stmt = (
        list_stmt.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = list((await session.execute(list_stmt)).scalars().all())
    return rows, total
