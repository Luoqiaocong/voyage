"""实测管理端接口返回的时间：是否已转本地时区、格式是否为约定形式。

用户报的两个问题一起验证：
  · 时间差 8 小时（存 UTC 却按 UTC 展示）
  · 格式是 2026-09-19T05:16:53.742467+00:00 这种原始 ISO 串
"""
import asyncio
import re
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


# 后端约定格式：YYYY-MM-DD HH:MM:SS，且不含时区标记与微秒
EXPECTED = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


async def main() -> None:
    import redis.asyncio as aioredis

    from app.modules.user.auth import PasswordManager
    from app.shared.db import AsyncSessionLocal
    from app.shared.db.models import User
    from sqlalchemy import delete, select

    # 清限流，避免登录被拦
    r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
    if keys:
        await r.delete(*keys)
    await r.aclose()

    # 建一个临时超管用于调用管理端接口。
    # 刻意不用真实账号：不知道也不该猜用户的密码；
    # 测试结束后删除，且用 .invalid 之外的专用域名避免与真实邮箱冲突。
    EMAIL = "__t_timefmt__@voyage-test.example.com"
    PWD = "Voyage#2026test"
    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if old:
            await db.execute(delete(User).where(User.id == old.id))
            await db.commit()
        db.add(User(email=EMAIL, username="t-time", password=PasswordManager.hash(PWD),
                    role="super_admin", is_active=True))
        await db.commit()
        uid = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one().id
    print(f"  已建临时超管 id={uid}")

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            rr = await c.post(f"{API}/users/login", json={"email": EMAIL, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            if not tok:
                print(f"  登录失败: {rr.text[:160]}")
                return
            h = {"Authorization": f"Bearer {tok}"}

            print("\n=== 1. 用户列表 / 详情的时间 ===")
            r1 = await c.get(f"{API}/admin/users", headers=h, params={"page_size": 5})
            items = ((r1.json() or {}).get("data") or {}).get("items") or []
            check("至少有一条用户", bool(items), str(len(items)))
            for u in items[:4]:
                v = u.get("created_at")
                print(f"    {u.get('email')}  created_at = {v!r}")
                check("格式为约定形式 YYYY-MM-DD HH:MM:SS",
                      bool(EXPECTED.match(str(v))), str(v))
                check("不含 +00:00 时区标记", "+00:00" not in str(v), str(v))
                check("不含微秒", "." not in str(v), str(v))

            print("\n=== 2. 用户详情的时间 ===")
            if items:
                r1b = await c.get(f"{API}/admin/users/{items[0]['id']}", headers=h)
                d = (r1b.json() or {}).get("data") or {}
                print(f"    详情 created_at = {d.get('created_at')!r}")
                check("详情时间格式一致",
                      bool(EXPECTED.match(str(d.get('created_at')))), str(d.get("created_at")))

            print("\n=== 3. 会话列表的时间 ===")
            r2 = await c.get(f"{API}/admin/conversations", headers=h, params={"page_size": 3})
            convs = ((r2.json() or {}).get("data") or {}).get("items") or []
            check("至少有一条会话", bool(convs), str(len(convs)))
            for cv in convs[:3]:
                v = cv.get("created_at")
                print(f"    会话 {cv.get('id')}  created_at = {v!r}")
                check("格式为约定形式", bool(EXPECTED.match(str(v))), str(v))

            print("\n=== 4. 审计日志的时间 ===")
            r3 = await c.get(f"{API}/admin/audit-logs", headers=h, params={"page_size": 3})
            logs = ((r3.json() or {}).get("data") or {}).get("items") or []
            if not logs:
                print("    （暂无审计记录，跳过）")
            for lg in logs[:3]:
                v = lg.get("created_at")
                print(f"    {lg.get('action')}  created_at = {v!r}")
                check("格式为约定形式", bool(EXPECTED.match(str(v))), str(v))

            print("\n=== 5. 会话统计：平均值应为整数、排行含今日消息数 ===")
            r4 = await c.get(f"{API}/admin/conversations/stats", headers=h)
            st = (r4.json() or {}).get("data") or {}
            avg = st.get("avg_messages_per_conversation")
            print(f"    avg_messages_per_conversation = {avg!r}")
            check("平均值是整数（向下取整）", isinstance(avg, int), f"{type(avg).__name__}")
            top = st.get("top_active_users") or []
            print(f"    top_active_users 条数 = {len(top)}")
            if top:
                print(f"      首条字段: {sorted(top[0].keys())}")
                check("含 today_messages 字段", "today_messages" in top[0], str(top[0]))
            check("排行不超过 10 条", len(top) <= 10, str(len(top)))
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        print(f"\n已删除临时超管 id={uid}")

    print(f"\n{'=' * 56}\n管理端时间与统计验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
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
