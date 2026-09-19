"""验证工具明细里不再出现伪工具 total，且总计与明细自洽。

背景：tool.total.calls 是所有工具的合计，供概览卡片与趋势图使用。
它曾被解析成一个名叫 total 的「工具」混进明细表，导致：
  · 明细表里合计与明细并列，容易被误读成「有一个叫 total 的工具」
  · 前端「工具调用」卡片把明细相加时把合计也算了一次，
    数字看着对只是巧合（total 恰好等于工具之和）

## 为什么同时查函数与 HTTP 两层

修完后端代码后我曾忘记重启 uvicorn（--no-reload 模式下进程跑的是旧代码）。
本地测试脚本是新进程、读到新代码，于是**测试全过但页面依旧显示 total**。
只测函数层发现不了这种错位，故这里额外打一次真实 HTTP 接口 ——
它能同时验证「代码正确」与「线上跑的是这份代码」。
"""
import asyncio
import selectors
import sys

import httpx

sys.path.insert(0, ".")

from app.config import config

API = "http://127.0.0.1:8000/api/v1"
ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


async def check_http_layer() -> None:
    """打真实接口 —— 用于发现「代码改了但服务没重启」这类错位。"""
    import redis.asyncio as aioredis
    from sqlalchemy import delete, select

    from app.modules.user.auth import PasswordManager
    from app.shared.db import AsyncSessionLocal
    from app.shared.db.models import User

    r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
    if keys:
        await r.delete(*keys)
    await r.aclose()

    EMAIL, PWD = "__t_shape__@voyage-test.example.com", "Voyage#2026test"
    async with AsyncSessionLocal() as db:
        old = (
            await db.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if old:
            await db.execute(delete(User).where(User.id == old.id))
            await db.commit()
        db.add(
            User(email=EMAIL, username="t-shape", password=PasswordManager.hash(PWD),
                 role="super_admin", is_active=True)
        )
        await db.commit()
        uid = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one().id

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            rr = await c.post(f"{API}/users/login", json={"email": EMAIL, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            if not tok:
                check("HTTP 层可取到 token", False, rr.text[:120])
                return
            h = {"Authorization": f"Bearer {tok}"}
            rr = await c.get(f"{API}/admin/metrics", headers=h)
            data = (rr.json() or {}).get("data") or {}

            tools = data.get("tools") or {}
            print(f"\n=== HTTP 接口返回的 tools ===")
            for name, m in sorted(tools.items()):
                print(f"  {name:<30} calls={m.get('calls', 0)}")

            check("HTTP: tools 里没有伪工具 total", "total" not in tools,
                  f"keys={sorted(tools)}")
            check(
                "HTTP: 概览用的总计仍可读",
                (data.get("counters") or {}).get("tool.total.calls", 0) >= 0,
                str((data.get("counters") or {}).get("tool.total.calls")),
            )
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


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

    print("\n=== 判定（函数层）===")
    check("tools 里没有伪工具 total", "total" not in tools,
          f"keys={sorted(tools)}")
    check("总计 > 0（说明统计在工作）", total > 0, str(total))
    # 二者应当相等：每个被统计的调用既计入自己的工具，也计入 total。
    # 若不等，说明 total 与明细的口径不一致（例如某处只写了其中一个）。
    check("总计与明细之和一致", total == detail_sum,
          f"total={total} vs 明细和={detail_sum}")

    print("\n=== 其它工具（不应受影响）===")
    check("cache 仍可读", "cache" in snap and isinstance(snap["cache"], dict))
    check("extraction 仍可读", "extraction" in snap and isinstance(snap["extraction"], dict))
    check("chat 仍可读", "chat" in snap and isinstance(snap["chat"], dict))

    print("\n=== 判定（HTTP 层，可发现「服务未重启」）===")
    try:
        await check_http_layer()
    except Exception as e:  # noqa: BLE001
        check("HTTP 层检查可执行", False, f"{type(e).__name__}: {e}")

    print(f"\n{'=' * 56}\n工具明细口径验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    import time

    for _ in range(30):
        try:
            if httpx.get("http://127.0.0.1:8000/docs", timeout=4).status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    if sys.platform == "win32":
        asyncio.run(
            main(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(main())

