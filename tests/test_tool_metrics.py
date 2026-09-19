"""端到端验证：发一条真实对话，确认 MCP 工具调用被统计到。

这是本次修复的核心验收：改动前 metrics 里没有任何 tool.* 字段。
"""
import asyncio
import json
import selectors
import sys

import httpx

sys.path.insert(0, ".")

from app.config import config

API = "http://127.0.0.1:8000/api/v1"
ok_n = fail_n = 0
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s)


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


async def main() -> None:
    import redis.asyncio as aioredis
    from sqlalchemy import delete, select

    from app.modules.user.auth import PasswordManager
    from app.shared.db import AsyncSessionLocal
    from app.shared.db.models import User
    from app.shared.usage_query import local_today

    r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
    if keys:
        await r.delete(*keys)

    key = f"metrics:{local_today()}"
    before = await r.hgetall(key)
    say("=== 调用前的 tool.* 字段 ===")
    tool_before = {k: v for k, v in before.items() if k.startswith("tool.")}
    say(f"  {tool_before or '（无）'}")

    EMAIL, PWD = "__t_toolmetric__@voyage-test.example.com", "Voyage#2026test"
    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if old:
            await db.execute(delete(User).where(User.id == old.id))
            await db.commit()
        db.add(User(email=EMAIL, username="t-tm", password=PasswordManager.hash(PWD),
                    role="user", is_active=True))
        await db.commit()
        uid = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one().id
    say(f"\n临时用户 id={uid}")

    try:
        async with httpx.AsyncClient(timeout=400) as c:
            rr = await c.post(f"{API}/users/login", json={"email": EMAIL, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            h = {"Authorization": f"Bearer {tok}"}
            rr = await c.post(f"{API}/conversations/", headers=h)
            cid = ((rr.json() or {}).get("data") or {}).get("id")

            # 用一个新城市+新日期，尽量避开缓存，走完整链路
            q = "查一下 2026-11-11 广州南到哈尔滨西的高铁车次"
            say(f"\n=== 发起对话：{q} ===")
            text = ""
            async with c.stream("POST", f"{API}/conversations/{cid}/messages",
                                headers=h, json={"message": q}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        if raw and raw != "[DONE]":
                            try:
                                o = json.loads(raw)
                                if o.get("type") == "text":
                                    text += o.get("content") or ""
                            except Exception:  # noqa: BLE001
                                pass
            say(f"  回复 {len(text)} 字")

        # 等埋点落 Redis（回调是异步的）
        await asyncio.sleep(2)
        after = await r.hgetall(key)
        tool_after = {k: v for k, v in after.items() if k.startswith("tool.")}

        say("\n=== 调用后的 tool.* 字段 ===")
        for k, v in sorted(tool_after.items()):
            say(f"  {k:<36} {v}")

        say("\n=== 判定 ===")
        check("产生了工具调用统计", bool(tool_after), f"{len(tool_after)} 个字段")
        check("tool.total.calls 存在且 > 0",
              int(tool_after.get("tool.total.calls", 0)) > 0,
              tool_after.get("tool.total.calls", "缺"))
        # 关键：MCP 工具名应出现（这是原先完全统计不到的部分）
        mcp_like = [k for k in tool_after if "get-tickets" in k or "get_weather" in k
                    or "search" in k.lower() and "tool.total" not in k]
        say(f"  捕获到的工具名: {sorted({k.split('.')[1] for k in tool_after if k.count('.') >= 2})}")
        check("覆盖到非 supervisor 的工具（原缺失部分）", bool(mcp_like),
              str(mcp_like[:5]))

        lat = await r.hgetall(f"metrics:lat:{local_today()}")
        tool_lat = {k: v for k, v in lat.items() if k.startswith("tool.")}
        say(f"\n  延迟字段: {sorted(tool_lat)[:8]}")
        check("工具延迟也被记录", bool(tool_lat), f"{len(tool_lat)} 个")
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        await r.aclose()
        say(f"\n已清理临时用户 id={uid}")


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
    say(f"\n{'=' * 58}\n工具调用统计验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 58}")
    sys.exit(1 if fail_n else 0)
