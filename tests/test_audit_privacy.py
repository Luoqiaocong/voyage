"""验证审计日志不泄露操作者邮箱，只给角色。

需求（用户提出）：审计日志的操作者只显示「超级管理员」这类角色，
否则普通管理员又能看见账号邮箱了 —— 那会绕过「普通管理员看不到更高层级
账号」这条约束（见 repo.list_users 的 viewer_rank 过滤），
而审计日志里几乎都是超级管理员的操作。

本测试同时覆盖函数层与 HTTP 层：
  · 函数层：service 返回的 items 里没有 operator_email
  · HTTP 层：以**普通管理员**身份取审计日志，响应体内不得出现任何邮箱格式串
    （后者是关键 —— 它验证的是「普通管理员实际拿不到」，而不只是「字段名改了」）
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

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


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
    from app.shared.db.models import AdminAuditLog, User

    r = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
    if keys:
        await r.delete(*keys)
    await r.aclose()

    SUPER = "__t_audit_super__@voyage-test.example.com"
    PLAIN = "__t_audit_plain__@voyage-test.example.com"
    PWD = "Voyage#2026test"

    async with AsyncSessionLocal() as db:
        for e in (SUPER, PLAIN):
            old = (await db.execute(select(User).where(User.email == e))).scalar_one_or_none()
            if old:
                await db.execute(delete(User).where(User.id == old.id))
        await db.commit()
        db.add(User(email=SUPER, username="t-super", password=PasswordManager.hash(PWD),
                    role="super_admin", is_active=True))
        db.add(User(email=PLAIN, username="t-plain", password=PasswordManager.hash(PWD),
                    role="admin", is_active=True))
        await db.commit()
        ids = {
            e: (await db.execute(select(User).where(User.email == e))).scalar_one().id
            for e in (SUPER, PLAIN)
        }

    # 造一条审计记录：操作者是超级管理员
    async with AsyncSessionLocal() as db:
        db.add(AdminAuditLog(
            operator_id=ids[SUPER],
            operator_email=SUPER,
            action="user.role.update",
            target_type="user",
            target_id=str(ids[PLAIN]),
            detail='{"before": "user", "after": "admin"}',
            ip="127.0.0.1",
        ))
        await db.commit()
    print(f"  已建临时账号：超管 id={ids[SUPER]}，普通管理员 id={ids[PLAIN]}")
    print("  已插入一条「超管操作」的审计记录")

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # ---- 以普通管理员身份取审计日志 ----
            rr = await c.post(f"{API}/users/login", json={"email": PLAIN, "password": PWD})
            tok = ((rr.json() or {}).get("data") or {}).get("access_token")
            if not tok:
                check("普通管理员可登录", False, rr.text[:140])
                return
            h = {"Authorization": f"Bearer {tok}"}
            rr = await c.get(f"{API}/admin/audit-logs", headers=h, params={"page_size": 50})
            raw = rr.text
            body = rr.json() or {}
            items = ((body.get("data") or {}).get("items")) or []

            print(f"\n=== 普通管理员取到 {len(items)} 条审计记录 ===")
            for it in items[:5]:
                print(f"  {it.get('created_at')}  {it.get('operator_role')!r}  "
                      f"{it.get('action')}  {it.get('target_type')}#{it.get('target_id')}")
            if items:
                print(f"\n  单条字段名: {sorted(items[0].keys())}")

            print("\n=== 判定 ===")
            check("普通管理员能读审计日志（只读权限保留）", rr.status_code == 200,
                  f"HTTP {rr.status_code}")
            if items:
                check("单条记录里没有 operator_email 字段",
                      "operator_email" not in items[0], str(sorted(items[0].keys())))
                check("单条记录里有 operator_role 字段",
                      "operator_role" in items[0], str(sorted(items[0].keys())))
                roles = {it.get("operator_role") for it in items}
                check("超管操作显示为 super_admin", "super_admin" in roles, str(roles))

            # 关键：整个响应体里不得出现任何邮箱串
            leaked = EMAIL_RE.findall(raw)
            check("响应体内无邮箱泄露", not leaked, str(sorted(set(leaked))[:5]))
            check("响应体内不含临时超管的邮箱", SUPER not in raw)
            check("响应体内不含临时管理员的邮箱", PLAIN not in raw)

            # ---- 对照：超管自己取，同样不应看到邮箱 ----
            rr2 = await c.post(f"{API}/users/login", json={"email": SUPER, "password": PWD})
            tok2 = ((rr2.json() or {}).get("data") or {}).get("access_token")
            rr2 = await c.get(f"{API}/admin/audit-logs",
                              headers={"Authorization": f"Bearer {tok2}"},
                              params={"page_size": 50})
            leaked2 = EMAIL_RE.findall(rr2.text)
            check("超管取审计日志同样无邮箱", not leaked2, str(sorted(set(leaked2))[:5]))
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(AdminAuditLog).where(AdminAuditLog.operator_id.in_(list(ids.values())))
            )
            await db.execute(delete(User).where(User.id.in_(list(ids.values()))))
            await db.commit()
        print(f"\n已清理临时账号与测试审计记录")

    print(f"\n{'=' * 56}\n审计日志隐私验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
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
