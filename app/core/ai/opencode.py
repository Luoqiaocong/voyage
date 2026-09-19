"""OpenCode Go 会话标识管理（基础设施层）。

OpenCode Go 网关强制要求每个请求携带 `x-opencode-session` 头，缺失会直接返回
400 MissingSessionID，请求无法被路由。头值需要在**每次请求时**决定，而 Agent
是进程内单例（启动时创建一次），无法在装配阶段写死对话 ID。

解法：asyncio 上下文变量 + httpx.Auth 动态注入。
- 业务侧在发起流式对话前用 `use_session(conversation_id)` 声明本轮会话；
- 注入通过 `httpx.Auth` 在**每个请求发出前**执行，对同步/异步客户端同时生效；
- 不同对话的请求各自运行在独立 asyncio Task 中，上下文天然隔离，互不串号。
"""
from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.config import config

# 当前请求所属会话；未显式声明时用配置的默认值兜底
_current_session: ContextVar[str] = ContextVar("opencode_session", default="")

# 当前请求的用户 ID；不在请求上下文内时为 0（表示「无法归属」）。
#
# 用途与 _current_session 类似，但方向相反：会话 ID 是**发出去**的（写进
# x-opencode-session 头），用户 ID 是**读回来**的 —— LLM 用量回调
# （core/ai/token.py）需要知道这次调用属于谁，才能做「按用户的 token 排行」。
#
# 为什么用 ContextVar 而不是给回调传参：回调由 LangChain 在链路内部触发，
# 调用点拿不到它，也无法逐个回传。上下文变量是这条链路上唯一可用的通道，
# 且不同对话各自运行在独立 asyncio Task 中，上下文天然隔离，不会串号。
_current_user_id: ContextVar[int] = ContextVar("current_user_id", default=0)


def get_current_user_id() -> int:
    """取当前请求的用户 ID；不在请求上下文内时返回 0。"""
    return _current_user_id.get()


@contextmanager
def use_user(user_id: int) -> Iterator[None]:
    """在 with 块内把当前 asyncio 上下文标记为指定用户。"""
    token = _current_user_id.set(int(user_id or 0))
    try:
        yield
    finally:
        _current_user_id.reset(token)


def get_session_id() -> str:
    """取当前会话标识；未在会话上下文中时返回配置的默认值。"""
    return _current_session.get() or config.OPENCODE_DEFAULT_SESSION


@contextmanager
def use_session(session_id: str) -> Iterator[None]:
    """在 with 块内把当前 asyncio 上下文标记为指定会话。

    Args:
        session_id: 会话标识（用会话 ID 即可，需在单次对话内保持稳定）
    """
    token = _current_session.set(session_id or config.OPENCODE_DEFAULT_SESSION)
    try:
        yield
    finally:
        _current_session.reset(token)


class OpenCodeAuth(httpx.Auth):
    """在每次请求前动态写入身份与会话头。

    用 Auth 而非 default_headers：头值随时间变化，且 Auth 对同步/异步客户端
    同时生效——ChatOpenAI 初始化时不论是否会用到，都会构造同步客户端。
    """

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["x-opencode-session"] = get_session_id()
        # 自报客户端身份，避免被网关按通用 SDK 流量限流
        request.headers["User-Agent"] = config.CLIENT_USER_AGENT
        yield request


def build_http_client() -> httpx.AsyncClient:
    """构造异步 httpx 客户端，供 ChatOpenAI 复用连接池（本平台只走异步调用）。"""
    return httpx.AsyncClient(
        auth=OpenCodeAuth(),
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def build_sync_http_client() -> httpx.Client:
    """构造同步 httpx 客户端。

    ChatOpenAI 初始化时会无条件构造同步 OpenAI 客户端，若不同步提供则会因
    类型校验失败；项目内不存在同步调用路径，该客户端仅用于满足初始化。
    """
    return httpx.Client(
        auth=OpenCodeAuth(),
        timeout=httpx.Timeout(60.0, connect=10.0),
    )
