"""验证工具明细里不再出现伪工具 total，且总计与明细自洽。

背景：tool.total.calls 是所有工具的合计，供概览卡片与趋势图使用。
它曾被解析成一个名叫 total 的「工具」混进明细表，导致：
  · 明细表里合计与明细并列，容易被误读成「有一个叫 total 的工具」
  · 前端「工具调用」卡片把明细相加时把合计也算了一次，
    数字看着对只是巧合（total 恰好等于工具之和）
"""
import asyncio
import selectors
import sys

sys.path.insert(0, ".")

from app.config import config

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


async def main() -> None:
    from app.shared.observability import get_metrics
    from app.shared.redis import redis_client
    from app.shared.usage_query import local_today

    try:
        redis_client.get_client()
    except RuntimeError:
        await redis_client.init_redis()
        await redis_client.get_client().ping()

    day = local_today()
    snap = await get_metrics(day)

    print(f"=== {day} 的指标快照 ===")
    print(f"  available: {snap.get('available')}")

    tools = snap.get("tools") or {}
    counters = snap.get("counters") or {}

    print("\n=== 明细（tools）===")
    for name, m in sorted(tools.items()):
        print(f"  {name:<30} calls={m.get('calls', 0)}  "
              f"hit_rate={m.get('cache_hit_rate')}  p50={m.get('p50')}")

    total = counters.get("tool.total.calls", 0)
    detail_sum = sum(m.get("calls", 0) for m in tools.values())
    print(f"\n  后端总计 tool.total.calls = {total}")
    print(f"  明细工具之和            = {detail_sum}")

    print("\n=== 判定 ===")
    check("tools 里没有伪工具 total", "total" not in tools,
          f"keys={sorted(tools)}")
    check("总计 > 0（说明统计在工作）", total > 0, str(total))
    # 二者应当相等：每个被统计的调用既计入自己的工具，也计入 total。
    # 若不等，说明 total 与明细的口径不一致（例如某处只写了其中一个）。
    check("总计与明细之和一致", total == detail_sum,
          f"total={total} vs 明细和={detail_sum}")

    print("\n=== 其它工具（不应受影响）===")
    for k in ("cache.hit_rate", "extraction.pass_rate", "chat.total"):
        pass
    check("cache 仍可读", "cache" in snap and isinstance(snap["cache"], dict))
    check("extraction 仍可读", "extraction" in snap and isinstance(snap["extraction"], dict))
    check("chat 仍可读", "chat" in snap and isinstance(snap["chat"], dict))

    print(f"\n{'=' * 56}\n工具明细口径验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            main(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(main())
