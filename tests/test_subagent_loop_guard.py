"""验证子 Agent 的死循环防护。

背景（真实事故）：一次「珠海 → 澳门」查票，澳门没有铁路站，票务子 Agent
把「珠海周边各站 → 广州/深圳/香港」这组查询重复了 274 次（20 组参数、
前 7 组各重复 36-38 次），单次问答烧掉约 1380 万 token。根因三条：

  1. langchain 的 create_agent 默认 recursion_limit=9999，等于没有上限；
  2. 子 Agent 未清理长工具结果，上下文随轮数线性膨胀（总成本按平方增长）；
  3. 没有「同工具同参数反复调用」的守卫，模型不收敛时无人打断。

本测试覆盖对应的三层修复：

  1. DuplicateToolCallMiddleware 的判定与结束行为；
  2. 三个子 Agent 已挂上 SUBAGENT_MIDDLEWARE；
  3. 子 Agent 调用带 recursion_limit，且超限时优雅降级而非上抛重试。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

import app.core.ai.agents.ticket as ticket_mod
import app.core.ai.agents.travel as travel_mod
import app.core.ai.agents.weather as weather_mod
import app.core.ai.tools.travel_tools as travel_tools_mod
from app.core.ai.middleware import (
    SUBAGENT_MIDDLEWARE,
    DuplicateToolCallMiddleware,
)
from langchain.agents.middleware import ContextEditingMiddleware

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def ai_with(name: str, args: dict, cid: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])


# ===================== 1. 中间件配置 =====================
print("=== 1. SUBAGENT_MIDDLEWARE 组成 ===")
has_ctx = any(isinstance(m, ContextEditingMiddleware) for m in SUBAGENT_MIDDLEWARE)
has_dup = any(isinstance(m, DuplicateToolCallMiddleware) for m in SUBAGENT_MIDDLEWARE)
check("包含上下文清理中间件", has_ctx)
check("包含重复调用守卫", has_dup)


# ===================== 2. DuplicateToolCallMiddleware 判定 =====================
print("=== 2. 重复调用守卫判定 ===")
guard = DuplicateToolCallMiddleware(max_repeats=3)
sig_call = {"name": "get-tickets", "args": {"from": "珠海", "to": "澳门", "date": "2026-09-28"}}

# 2.1 未达阈值：前面的同签名调用只有 2 次，不拦
below = {
    "messages": [
        HumanMessage(content="查票"),
        ai_with("get-tickets", sig_call["args"], "1"),
        ai_with("get-tickets", sig_call["args"], "2"),
        ai_with("get-tickets", sig_call["args"], "3"),
    ]
}
check("未达阈值不拦截", guard.after_model(below, None) is None)

# 2.2 达到阈值且本轮只有这一个调用：拦截并结束
at_limit = {
    "messages": [
        HumanMessage(content="查票"),
        ai_with("get-tickets", sig_call["args"], "1"),
        ai_with("get-tickets", sig_call["args"], "2"),
        ai_with("get-tickets", sig_call["args"], "3"),
        ai_with("get-tickets", sig_call["args"], "4"),
    ]
}
out = guard.after_model(at_limit, None)
check("达阈值有返回", isinstance(out, dict))
check("本轮结束（jump_to=end）", bool(out) and out.get("jump_to") == "end")
check(
    "注入 error ToolMessage + 收尾 AI 消息",
    bool(out) and len(out.get("messages", [])) == 2,
    str(out and len(out.get("messages", []))),
)

# 2.3 交替参数（A,B,A,B...）也能累计判定 —— 这是事故的真实形态
alternating = {
    "messages": [
        HumanMessage(content="查票"),
        ai_with("get-tickets", {"from": "珠海北"}, "1"),
        ai_with("get-tickets", {"from": "珠海"}, "2"),
        ai_with("get-tickets", {"from": "珠海北"}, "3"),
        ai_with("get-tickets", {"from": "珠海"}, "4"),
        ai_with("get-tickets", {"from": "珠海北"}, "5"),
        ai_with("get-tickets", {"from": "珠海"}, "6"),
        ai_with("get-tickets", {"from": "珠海北"}, "7"),
    ]
}
out2 = guard.after_model(alternating, None)
check("交替重复同样被拦", isinstance(out2, dict))
check("交替重复触发结束", bool(out2) and out2.get("jump_to") == "end")

# 2.4 参数不同：不拦（合法的多站查询）
distinct = {
    "messages": [
        HumanMessage(content="查票"),
        ai_with("get-tickets", {"to": "广州南"}, "1"),
        ai_with("get-tickets", {"to": "广州东"}, "2"),
        ai_with("get-tickets", {"to": "深圳北"}, "3"),
        ai_with("get-tickets", {"to": "香港西九龙"}, "4"),
    ]
}
check("不同参数不拦截", guard.after_model(distinct, None) is None)

# 2.5 混合：一个重复 + 一个全新 → 只拦重复的，不结束
mixed = {
    "messages": [
        HumanMessage(content="查票"),
        ai_with("get-tickets", {"to": "广州南"}, "1"),
        ai_with("get-tickets", {"to": "广州南"}, "2"),
        ai_with("get-tickets", {"to": "广州南"}, "3"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get-tickets", "args": {"to": "广州南"}, "id": "4"},
                {"name": "get-weather", "args": {"city": "珠海"}, "id": "5"},
            ],
        ),
    ]
}
out3 = guard.after_model(mixed, None)
check("混合场景有返回", isinstance(out3, dict))
check("混合场景不结束（放行未重复调用）", bool(out3) and "jump_to" not in out3)
check(
    "混合场景只拦重复那一个",
    bool(out3) and len(out3.get("messages", [])) == 1,
    str(out3 and len(out3.get("messages", []))),
)


# ===================== 3. 子 Agent 已挂载中间件 =====================
print("=== 3. 子 Agent 挂载中间件 ===")


class _FakeAgent:
    pass


for name, module, builder, cache_attr in (
    ("ticket", ticket_mod, "get_ticket_agent", "_ticket_agent_cache"),
    ("weather", weather_mod, "get_weather_agent", "_weather_agent_cache"),
    ("travel", travel_mod, "get_travel_agent", "_travel_agent_cache"),
):
    captured: dict = {}

    async def fake_tools(_ns):
        return []

    def fake_create_agent(sink, **kwargs):
        sink.update(kwargs)
        return _FakeAgent()

    module.create_agent = lambda **kw: fake_create_agent(captured, **kw)
    module.get_namespace_tools = fake_tools
    if cache_attr == "_travel_agent_cache":
        module.with_cache = lambda tools: tools
    setattr(module, cache_attr, None)
    run(getattr(module, builder)())
    check(
        f"{name} 子 Agent 传入 SUBAGENT_MIDDLEWARE",
        captured.get("middleware") is SUBAGENT_MIDDLEWARE,
    )


# ===================== 4. recursion_limit 与降级 =====================
print("=== 4. 步数上限与优雅降级 ===")
limits = travel_tools_mod.SUBAGENT_RECURSION_LIMITS
check("ticket 上限为正整数", isinstance(limits.get("ticket"), int) and limits["ticket"] > 0, str(limits.get("ticket")))
check("weather 上限为正整数", isinstance(limits.get("weather"), int) and limits["weather"] > 0, str(limits.get("weather")))
check("travel 上限为正整数", isinstance(limits.get("travel"), int) and limits["travel"] > 0, str(limits.get("travel")))
check(
    "上限远小于 langchain 默认的 9999",
    all(v < 100 for v in limits.values()),
    str(limits),
)

captured_cfg: dict = {}


class _OkAgent:
    async def ainvoke(self, payload, config=None):
        captured_cfg["config"] = config
        return {"messages": [AIMessage(content="查到 3 趟车次")]}


text = run(
    travel_tools_mod._invoke_subagent(
        _OkAgent(), "查票", kind="ticket", fallback="兜底"
    )
)
check("正常返回末条消息内容", text == "查到 3 趟车次", text)
check(
    "按 kind 传对应 recursion_limit",
    captured_cfg.get("config", {}).get("recursion_limit") == limits["ticket"],
    str(captured_cfg.get("config")),
)


class _RunawayAgent:
    async def ainvoke(self, payload, config=None):
        raise GraphRecursionError("recursion limit reached")


degraded = run(
    travel_tools_mod._invoke_subagent(
        _RunawayAgent(), "查票", kind="ticket", fallback="车次信息暂时查询不到"
    )
)
check("超限降级为友好文案（不上抛）", degraded == "车次信息暂时查询不到", degraded)


print(f"\n结果：PASS {ok_n} / FAIL {fail_n}")
sys.exit(1 if fail_n else 0)
