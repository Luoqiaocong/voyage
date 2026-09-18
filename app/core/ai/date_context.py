"""把「今天是几号」注入系统提示词，替掉 get_today 工具。

## 为什么这样做

模型不知道今天是几号（训练数据有截止时间），而且会自信地编一个日期。
所以「不能让模型凭记忆猜日期」这个约束是必要的。

但原先的实现方式是给它一个 `get_today` 工具，这带来三个代价：
  1. 多一次完整的 LLM 往返 —— 实测 3.2 秒。日期本该是**已知常量**，
     却走了「模型决定要查 → 工具返回 → 模型再组织语言」的完整链路
  2. 界面上多一条工具时间线（「获取当前日期」），用户看到会觉得莫名其妙：
     这也要查？
  3. 模型会在回复里把过程念出来 ——「先确认一下今天的日期，好推算后天…
     今天 2026-09-19（周六），那后天就是 2026-09-21」——像在自言自语

日期是服务端**每次调用都确切知道**的信息，直接放进系统提示词即可。
它仍然不是模型的记忆，而是我们给的，因此原有的安全性不受影响。

## 为什么用 dynamic_prompt 而不是直接写进系统提示词

Agent 实例是长驻缓存复用的（见 AgentFactory），若把日期写死在
system_prompt 里，跨天不重启就会一直用昨天的日期——这比不告诉它还糟。

`dynamic_prompt` 在**每次模型调用**时覆盖 system message，
因此日期永远新鲜，也不需要为了换日期而重建 agent。
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import SystemMessage

from app.config import config

_WEEKDAYS = "一二三四五六日"

#: 追加段的标题。用于幂等替换，避免重复追加。
_SECTION_TITLE = "## 当前日期"


def current_date_line() -> str:
    """当前日期与星期的中文描述，供提示词与工具共用。"""
    now = datetime.now(ZoneInfo(config.APP_TIMEZONE))
    return f"{now.strftime('%Y-%m-%d')}（星期{_WEEKDAYS[now.weekday()]}）"


def with_current_date(base_text: str) -> str:
    """把当前日期段追加到系统提示词末尾（幂等）。

    抽成纯函数以便单测：中间件在**每一轮模型调用**前都会执行，
    一轮对话里可能调用多次模型，若每次都无脑追加，系统提示词会带着
    同一段日期重复 N 遍。故先移除已有日期段再追加。
    """
    text = base_text or ""
    marker = f"\n\n{_SECTION_TITLE}\n"
    if marker in text:
        text = text.split(marker, 1)[0]

    return (
        f"{text}\n\n"
        f"{_SECTION_TITLE}\n"
        f"今天是 {current_date_line()}。请据此换算「今天/明天/后天/本周五」等相对日期。\n"
        f"这是系统提供的准确信息，**不要为此调用工具，也不要在回答里复述这一行**。"
    )


@dynamic_prompt
def inject_current_date(request: ModelRequest) -> SystemMessage:
    """在系统提示词末尾追加一行当前日期。

    追加而非替换：原提示词承载角色定位、工具使用原则、输出格式等全部约束，
    这里只补一条事实。幂等性由 with_current_date 保证，理由见其说明。

    提示词里明确要求「不要在回复中提及本行」——否则模型很容易开场就说
    「今天是 X 月 X 日」，那与之前念 get_today 的过程一样啰嗦。
    """
    base = request.system_message
    base_text = ""
    if base is not None:
        content = base.content
        base_text = content if isinstance(content, str) else str(content)

    return SystemMessage(content=with_current_date(base_text))
