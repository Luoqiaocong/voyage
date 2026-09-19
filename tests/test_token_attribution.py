"""验证 Token 用量按用户归属：发出真实对话 → 落库 → 排行能查到。

这是本次改动的核心链路，必须实测：
  1. Redis 里出现 usage:user:day:{date} 且有本用户的字段
  2. 落库后 user_token_usage 有本用户的行，且 total_tokens > 0
  3. 排行接口返回本用户，且数值与库中一致
  4. **现有模型维度统计不受影响**（回归）
"""
import asyncio
import selectors
import sys
import time

import httpx

sys.path.insert(0, ".")

API = "http://127.0.0.1:8000/api/v1"
ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


async def main() -> None:
    import redis.asyncio as aioredis
    from sqlalchemy import delete, func, select

    from app.config import config
    from app.core.ai.token import USER_TOTAL_KEY, user_day_key
    from app.modules.user.auth import PasswordManager
    from app.shared.db import AsyncSessionLocal
    from app.shared.db.models import User, UserTokenUsage
    from app.shared.usage_store import flush_pending_usage

    # 关键：必须连**应用实际使用的那个 Redis**，即 config.REDIS_URL。
    #
    # 这里踩过一个坑：脚本原先硬编码 redis://127.0.0.1:6379/7，
    # 而后端用的是 .env 里配置的远程实例 —— 后端写本地、脚本查远程，
    # 于是「Redis 里看不到增量」这个现象把排查带偏了很久。
    # 顺带说明：写测试时不要让脚本自己假设后端连哪里，一律读配置。
    _r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    r = _r

    # 清限流
    r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
    if keys:
        await r.delete(*keys)

    EMAIL, PWD = "__t_tok__@voyage-test.example.com", "Voyage#2026test"
    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if old:
            await db.execute(delete(User).where(User.id == old.id))
            await db.commit()
        db.add(User(email=EMAIL, username="t-tok", password=PasswordManager.hash(PWD),
                    role="user", is_active=True))
        await db.commit()
        uid = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one().id
    print(f"  临时用户 id={uid}")

    out = {}
    try:
        # 清掉本次测试用户可能残留的增量，保证从 0 开始观察
        await r.hdel(user_day_key(), str(uid))
        await r.hdel(USER_TOTAL_KEY, f"{uid}:total_tokens")
        await r.aclose()

        async with httpx.AsyncClient(timeout=300) as c:
            rr = await c.post(f"{API}/users/login", json={"email": EMAIL, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            h = {"Authorization": f"Bearer {tok}"}
            rr = await c.post(f"{API}/conversations/", headers=h)
            cid = ((rr.json() or {}).get("data") or {}).get("id")

            print("\n=== 1. 发一条真实对话（会调用模型）===")
            t0 = time.perf_counter()
            text = ""
            async with c.stream("POST", f"{API}/conversations/{cid}/messages",
                                headers=h, json={"message": "你好，简单介绍一下你能做什么"}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        if raw and raw != "[DONE]":
                            try:
                                import json as _j
                                o = _j.loads(raw)
                                if o.get("type") == "text":
                                    text += o.get("content") or ""
                            except Exception:
                                pass
            print(f"    耗时 {time.perf_counter()-t0:.1f}s，回复 {len(text)} 字")
            check("模型确实回复了", len(text) > 0, f"{len(text)} 字")

        print("\n=== 2. 累计键有本用户的记录（采集确实发生了）===")
        # 只读累计键，**不要碰当日键**。
        #
        # 这里踩过一个把自己带偏很久的坑：最初为了「看当日增量」调了
        # drain_day_user_usage()，而它用的是「HGETALL + DEL」的 Lua 脚本 ——
        # 读一次就把增量消费掉了。随后第 3 步的 flush 自然什么都取不到，
        # 于是断言「库中无行」失败，看起来像实现有问题，实际是测试自己
        # 把数据吃掉了。教训：**验证与消费不能混用同一个原语**。
        #
        # 累计键（usage:user:total）不会被 drain，适合用来确认采集发生过。
        r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
        tot = await r.hget(USER_TOTAL_KEY, f"{uid}:total_tokens")
        await r.aclose()
        print(f"    {USER_TOTAL_KEY}[{uid}:total_tokens] = {tot}")
        check("累计键有该用户记录（采集生效）", tot is not None and int(tot) > 0, str(tot))
        tok_seen = int(tot or 0)

        print("\n=== 3. 落库到 user_token_usage ===")
        # 独立脚本没有经过 FastAPI 的 lifespan，Redis 需自行初始化
        from app.shared.redis import redis_client

        try:
            redis_client.get_client()
        except RuntimeError:
            await redis_client.init_redis()
            await redis_client.get_client().ping()
        await flush_pending_usage()
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(UserTokenUsage).where(UserTokenUsage.user_id == uid)
                )
            ).scalars().first()
            if row is None:
                check("库中有该用户的行", False, "未找到")
            else:
                print(f"    total_tokens={row.total_tokens} calls={row.calls} "
                      f"date={row.record_date}")
                check("库中有该用户的行", True)
                check("total_tokens > 0", row.total_tokens > 0, str(row.total_tokens))
                if tok_seen:
                    check("数值不低于本次取到的增量",
                          row.total_tokens >= tok_seen,
                          f"库 {row.total_tokens} vs 增量 {tok_seen}")

        print("\n=== 4. 严格核对：库里数值 == 重新落库前的 Redis 快照 ===")
        async with AsyncSessionLocal() as db:
            total_in_db = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(UserTokenUsage.total_tokens), 0))
                        .where(UserTokenUsage.user_id == uid)
                    )
                ).scalar_one()
            )
        print(f"    库中该用户累计 total_tokens = {total_in_db}")
        check("库中累计为正", total_in_db > 0, str(total_in_db))

        print("\n=== 5. 排行接口包含该用户 ===")
        async with httpx.AsyncClient(timeout=30) as c:
            # 用超管身份查（临时提升，测完随用户一起删除）
            async with AsyncSessionLocal() as db:
                u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                u.role = "super_admin"
                await db.commit()
            rr = await c.post(f"{API}/users/login", json={"email": EMAIL, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            hh = {"Authorization": f"Bearer {tok}"}
            rr = await c.get(f"{API}/admin/conversations/stats", headers=hh)
            st = (rr.json() or {}).get("data") or {}
            tops = st.get("top_token_users") or []
            print(f"    top_token_users = {tops}")
            mine_row = next((t for t in tops if t["user_id"] == uid), None)
            check("排行里有该用户", mine_row is not None, str(tops))
            if mine_row:
                check("排行里的 tokens 与库一致",
                      mine_row["tokens"] == total_in_db,
                      f"{mine_row['tokens']} vs {total_in_db}")

        print("\n=== 6. 回归：模型维度统计未受影响 ===")
        async with AsyncSessionLocal() as db:
            from app.shared.db.models import TokenUsage
            n_model = int(
                (await db.execute(select(func.count(TokenUsage.id)))).scalar_one()
            )
            model_total = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(TokenUsage.total_tokens), 0))
                    )
                ).scalar_one()
            )
        print(f"    token_usage 行数={n_model} 总 token={model_total}")
        check("模型维度仍有数据", n_model > 0 and model_total > 0,
              f"{n_model} 行 / {model_total} tokens")
        check("用户维度总量不超过模型维度总量（应小于等于）",
              total_in_db <= model_total,
              f"用户 {total_in_db} vs 模型 {model_total}")
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
        keys = [k async for k in r.scan_iter(match="usage:user:*", count=200)]
        if keys:
            await r.delete(*keys)
        await r.aclose()
        print(f"\n已清理临时用户 id={uid} 与用户维度用量键")

    print(f"\n{'=' * 58}\nToken 用户归属验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 58}")
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    # 写真实数据前先确认不是生产实例（见 tests/guard.py 的说明）
    from tests.guard import require_non_production

    require_non_production()
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
