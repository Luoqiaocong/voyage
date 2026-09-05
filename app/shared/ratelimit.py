"""接口限流（固定窗口，Redis 实现）。

设计思想
--------
- 用 Redis 的 INCR 做原子计数，首次计数时用 EXPIRE ... NX 设置过期时间。
  过期即代表窗口复位，无需后台清理任务，也不会因为请求持续进来而不断续期。
- Redis 单线程特性保证 INCR 原子性，并发场景下计数不会丢。
- 键名统一为 "rate:<场景>:<维度>:<值>"，维度可以是 IP、邮箱、用户 ID 等。

分层设计
--------
- 纯计数原语（INCR/EXPIRE/DEL）位于 app/shared/redis/ops.py（基础设施层）；
- 本模块只保留"限流策略"：规则常量、键构造、判定、429 语义。
  将来升级算法（Lua / 令牌桶 / 滑动窗口）只动 redis 层，策略层无需变更。

使用方式
--------
- IP 维度：路由级依赖注入
    ``@router.post("/reg", dependencies=[Depends(rate_limit("register", REG_IP_LIMIT, REG_IP_WINDOW))])``
- 邮箱等请求体维度：在 service 层调用（依赖注入拿不到已解析的请求体）
    ``if await check_rate_limit(email_code_key(email), CODE_EMAIL_LIMIT, CODE_EMAIL_WINDOW): ...``

超出限制统一抛 HTTPException(429)，并带 Retry-After 响应头；
全局异常处理器将 429 映射为 RATE_LIMIT_EXCEEDED 业务码（见 app/core/business/util.py）。
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from starlette import status

from app.shared.redis import incr_counter

# ===================== 1. 业务限流规则（集中管理，便于调整） =====================

# 发送验证码
CODE_EMAIL_LIMIT = 5      # 同一邮箱 1 小时内最多发送 5 次验证码（防邮件轰炸）
CODE_EMAIL_WINDOW = 3600  # 秒
CODE_IP_LIMIT = 10        # 同一 IP 1 小时内最多触发 10 次发码请求
CODE_IP_WINDOW = 3600     # 秒

# 登录
LOGIN_FAIL_LIMIT = 5      # 同一邮箱 15 分钟内最多 5 次登录失败（防暴力破解）
LOGIN_FAIL_WINDOW = 900   # 秒
LOGIN_IP_LIMIT = 20       # 同一 IP 15 分钟内最多 20 次登录请求
LOGIN_IP_WINDOW = 900     # 秒

# 注册
REG_IP_LIMIT = 5          # 同一 IP 1 小时内最多注册 5 个账号（防批量注册）
REG_IP_WINDOW = 3600      # 秒

# 密码重置（验证码换重置令牌 / 凭令牌重置）
RESET_EMAIL_LIMIT = 3     # 同一邮箱 10 分钟内最多 3 次申请重置令牌（防枚举）
RESET_EMAIL_WINDOW = 600  # 秒
RESET_IP_LIMIT = 10       # 同一 IP 10 分钟内最多 10 次重置相关请求
RESET_IP_WINDOW = 600     # 秒

# ===================== 2. 限流判定（计数原语在 redis 层） =====================


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """计数 +1；超过阈值返回 True（调用方应拒绝该请求），否则返回 False。

    底层计数由 app/shared/redis/ops.incr_counter 提供（纯 Redis 原语），
    本层只做"限流决策"。用于 service 内部对邮箱/账号等请求体维度的限流。
    """
    count = await incr_counter(key, window_seconds)
    return count > limit


def _too_many_requests(retry_after: int) -> HTTPException:
    """统一的 429 响应：带 Retry-After 头，语义明确。"""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="请求过于频繁，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


# ===================== 3. IP 维度限流依赖（路由级） =====================


def rate_limit(prefix: str, limit: int, window_seconds: int):
    """IP 维度的限流依赖工厂。

    Args:
        prefix: 场景前缀，最终键为 ``rate:{prefix}:ip:{ip}``
        limit: 窗口内允许的最大请求次数
        window_seconds: 窗口时长（秒）

    用法（路由装饰器）：
        ``dependencies=[Depends(rate_limit("register", REG_IP_LIMIT, REG_IP_WINDOW))]``
    """

    async def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        if await check_rate_limit(f"rate:{prefix}:ip:{ip}", limit, window_seconds):
            raise _too_many_requests(window_seconds)

    return dependency


# ===================== 4. 邮箱维度键构造（service 层使用） =====================


def email_code_key(email: str) -> str:
    """发验证码的邮箱维度键（统一小写，避免大小写绕过限流）。"""
    return f"rate:send_code:email:{email.lower()}"


def reset_token_email_key(email: str) -> str:
    """申请重置令牌的邮箱维度键。"""
    return f"rate:reset_token:email:{email.lower()}"


def login_fail_key(email: str) -> str:
    """登录失败计数的邮箱维度键。"""
    return f"rate:login_fail:email:{email.lower()}"
