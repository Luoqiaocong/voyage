import asyncio
from typing import Annotated

from fastapi import BackgroundTasks, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.business import BusinessCode, UserException
from app.core.business.exception import AuthException
from app.modules.user.auth import get_hashed_id
from app.modules.user.repo import UserRepo
from app.shared.db import get_db
from app.shared.ratelimit import (
    CODE_EMAIL_LIMIT,
    CODE_EMAIL_WINDOW,
    RESET_EMAIL_LIMIT,
    RESET_EMAIL_WINDOW,
    check_rate_limit,
    email_code_key,
    reset_token_email_key,
)

from .constants import CODE_FAST_WAIT_SECONDS
from .tokens import (
    consume_code,
    create_access_token,
    deliver_code,
    get_refresh_token_user,
    issue_code,
    issue_reset_token,
    mail_delivery_failed,
)


async def _await_silently(task: asyncio.Task) -> None:
    """等待后台投递任务结束并吞掉异常。

    为什么需要：转入后台的投递仍需有人等待，否则任务被回收时
    可能出现「请求已返回、邮件却没发出去」且无人知晓的情况。
    异常在此吞掉是有意的——deliver_code 已把结果写进 Redis 标记，
    错误详情只用于日志。
    """
    try:
        await task
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[mail] 后台投递失败: {type(exc).__name__}: {exc}")


class AuthService:
    """认证服务（验证码 / 重置令牌签发）。"""

    def __init__(
        self,
        repo: Annotated[UserRepo, Depends()],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        self.repo = repo
        self.db = db

    async def send_code(self, email: str, background: BackgroundTasks) -> dict:
        """签发邮箱验证码（邮箱维度限流：1 小时最多 5 次，防邮件轰炸）。

        为什么要分「快速路径 + 后台」：
        实测 Resend 一次 SMTP 投递约 4 秒（TCP + STARTTLS + 认证 + 投递）。
        原先一路同步等待，用户点完按钮 4 秒内没有任何反馈，
        主观上就是「点了没反应 / 发送失败」。

        现在的顺序与策略：
          1. 先落 Redis —— 验证码立即可用，不再受发信耗时影响
          2. 同步等最多 CODE_FAST_WAIT_SECONDS 秒
             多数情况下这一步就能拿到确定结果，于是仍能如实告诉用户成功与否
          3. 超过则把发信转入后台，请求立即返回
             不直接丢弃任务：若客户端此刻断开，邮件仍会被发出

        返回值里的 pending 用于告知前端「邮件还在路上」，
        前端据此给出「已生成、正在发送」的提示，而不是假装已经完全成功。
        """
        if await check_rate_limit(email_code_key(email), CODE_EMAIL_LIMIT, CODE_EMAIL_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证码发送过于频繁，请稍后再试",
                headers={"Retry-After": str(CODE_EMAIL_WINDOW)},
            )

        # 第一步：生成并落库，此时验证码已经可用
        code = await issue_code(email)

        # 第二步：快速路径等待
        task = asyncio.create_task(deliver_code(email, code))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=CODE_FAST_WAIT_SECONDS)
        except TimeoutError:
            # 邮件还在发：交给后台继续，请求立即返回
            background.add_task(_await_silently, task)
            logger.info(f"[mail] 投递超过 {CODE_FAST_WAIT_SECONDS}s，转入后台继续发送: {email}")
            return {"sent": True, "pending": True}
        except Exception as exc:  # noqa: BLE001
            # deliver_code 自身不抛错，走到这里说明是意料之外的故障
            logger.warning(f"[mail] 投递任务异常: {email} - {type(exc).__name__}: {exc}")
            raise AuthException(code=BusinessCode.MAIL_SEND_FAILED) from exc

        if not task.result():
            raise AuthException(code=BusinessCode.MAIL_SEND_FAILED)
        return {"sent": True, "pending": False}

    async def issue_reset_token(self, email: str, code: str) -> dict:
        """两步重置第一步：校验验证码后签发一次性重置令牌。

        要求邮箱已注册（user_exists=True）。
        """
        # 邮箱维度限流（防枚举与滥用）：先限流再查用户
        if await check_rate_limit(reset_token_email_key(email), RESET_EMAIL_LIMIT, RESET_EMAIL_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="操作过于频繁，请稍后再试",
                headers={"Retry-After": str(RESET_EMAIL_WINDOW)},
            )

        user = await self.repo.get_user_dynamic(email=email)
        if not user:
            raise UserException(code=BusinessCode.USER_NOT_FOUND)

        if not await consume_code(email, code):
            # 区分两种「验不过」：邮件根本没发出去 vs 验证码填错了。
            # 不区分的话用户会反复重填一个本来就正确的码，
            # 而真正的问题是那封邮件从未送达。
            if await mail_delivery_failed(email):
                raise AuthException(code=BusinessCode.MAIL_SEND_FAILED)
            raise UserException(code=BusinessCode.CODE_VERIFY_FAILED)

        token = await issue_reset_token(email)
        return {"token": token}
    
    async def issue_access_token(self, refresh_token: str):
        user_id = await get_refresh_token_user(refresh_token)
        if user_id is None:
            raise AuthException(code=BusinessCode.TOKEN_INVALID)
        access_token = create_access_token({"sub": get_hashed_id(user_id)})
        return {"access_token": access_token, "token_type": "bearer"}