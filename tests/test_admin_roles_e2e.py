"""管理员分级的端到端验证（真实 HTTP）。

验证用户报告的问题与本次需求的每一条：
  1. 普通管理员（admin）能进入后台、能看数据
  2. 普通管理员**不能**做任何写操作
  3. 普通管理员在用户列表里**看不到超级管理员**（防测密码）
  4. 普通管理员不能把超管降级（用户报的「严重错误」）
  5. 超管之间的保护、自我降级保护
"""
import asyncio
import selectors
import sys

import httpx

sys.path.insert(0, ".")

API = "http://127.0.0.1:8000/api/v1"

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def code_of(resp: httpx.Response) -> int | None:
    try:
        return (resp.json() or {}).get("code")
    except Exception:  # noqa: BLE001
        return None


async def login(c: httpx.AsyncClient, email: str, pwd: str) -> dict | None:
    r = await c.post(f"{API}/users/login", json={"email": email, "password": pwd})
    tok = ((r.json() or {}).get("data") or {}).get("access_token")
    return {"Authorization": f"Bearer {tok}"} if tok else None


async def main() -> None:
    from sqlalchemy import delete, select

    from app.shared.db import AsyncSessionLocal
    from app.shared.db.models import User

    # 准备：三个账号（超管 / 普通管理员 / 普通用户），密码统一
    PWD = "Voyage#2026test"
    from app.modules.user.auth import PasswordManager

    accounts = [
        ("__t_super__@voyage-test.example.com", "t-super", "super_admin"),
        ("__t_admin__@voyage-test.example.com", "t-admin", "admin"),
        ("__t_user__@voyage-test.example.com", "t-user", "user"),
        ("__t_victim__@voyage-test.example.com", "t-victim", "user"),
    ]
    async with AsyncSessionLocal() as db:
        for email, name, role in accounts:
            old = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if old:
                await db.execute(delete(User).where(User.id == old.id))
                await db.commit()
            db.add(
                User(
                    email=email,
                    username=name,
                    password=PasswordManager.hash(PWD),
                    role=role,
                    is_active=True,
                )
            )
        await db.commit()
        rows = list(
            (
                await db.execute(
                    select(User).where(User.email.in_([a[0] for a in accounts]))
                )
            ).scalars().all()
        )
        ids = {u.email: u.id for u in rows}
    print(f"=== 测试账号已建（{len(ids)} 个）===")
    for e, i in sorted(ids.items(), key=lambda x: x[1]):
        print(f"  id={i}  {e}")

    async with httpx.AsyncClient(timeout=30) as c:
        h_super = await login(c, accounts[0][0], PWD)
        h_admin = await login(c, accounts[1][0], PWD)
        h_user = await login(c, accounts[2][0], PWD)
        check("三个账号都能登录", all([h_super, h_admin, h_user]))

        print("\n=== 1. 读权限：两种管理员都能进后台 ===")
        for name, h in (("超管", h_super), ("普通管理员", h_admin)):
            r = await c.get(f"{API}/admin/dashboard/summary", headers=h)
            check(f"{name} 能读看板", code_of(r) == 20000, f"code={code_of(r)}")
        r = await c.get(f"{API}/admin/dashboard/summary", headers=h_user)
        check("普通用户进不了后台", code_of(r) != 20000, f"code={code_of(r)}")

        print("\n=== 2. /admin/me 正确反映权限 ===")
        for name, h, want_write in (("超管", h_super, True), ("普通管理员", h_admin, False)):
            r = await c.get(f"{API}/admin/me", headers=h)
            d = (r.json() or {}).get("data") or {}
            check(f"{name} can_write={want_write}", d.get("can_write") == want_write,
                  f"role={d.get('role')} can_write={d.get('can_write')}")

        print("\n=== 3. 普通管理员看不到超级管理员（防测密码）===")
        r = await c.get(f"{API}/admin/users", headers=h_admin, params={"page_size": 100})
        d = (r.json() or {}).get("data") or {}
        emails = [u["email"] for u in (d.get("items") or [])]
        print(f"        普通管理员看到的账号: {emails}")
        check("看不到超管账号", accounts[0][0] not in emails, "超管出现在列表里了")
        check("看得到普通用户", accounts[2][0] in emails or accounts[3][0] in emails)
        check("can_write=false", d.get("can_write") is False, str(d.get("can_write")))

        r = await c.get(f"{API}/admin/users", headers=h_super, params={"page_size": 100})
        emails_s = [u["email"] for u in (((r.json() or {}).get("data") or {}).get("items") or [])]
        check("超管能看全部（含自己）", accounts[0][0] in emails_s)

        print("\n=== 4. 普通管理员不能做任何写操作 ===")
        victim = ids[accounts[3][0]]
        r = await c.patch(
            f"{API}/admin/users/{victim}/role", headers=h_admin, json={"role": "admin"}
        )
        check("改角色被拒", code_of(r) != 20000, f"code={code_of(r)}")
        r = await c.patch(
            f"{API}/admin/users/{victim}/status", headers=h_admin, json={"is_active": False}
        )
        check("启停用被拒", code_of(r) != 20000, f"code={code_of(r)}")

        print("\n=== 5. 普通管理员不能降级超管（用户报的严重错误）===")
        sup = ids[accounts[0][0]]
        r = await c.patch(
            f"{API}/admin/users/{sup}/role", headers=h_admin, json={"role": "user"}
        )
        check("降级超管被拒", code_of(r) != 20000, f"code={code_of(r)}")
        r = await c.patch(
            f"{API}/admin/users/{sup}/status", headers=h_admin, json={"is_active": False}
        )
        check("停用超管被拒", code_of(r) != 20000, f"code={code_of(r)}")

        print("\n=== 6. 超管可以正常管理 ===")
        r = await c.patch(
            f"{API}/admin/users/{victim}/role", headers=h_super, json={"role": "admin"}
        )
        check("超管能把用户设为普通管理员", code_of(r) == 20000, f"code={code_of(r)}")

        print("\n=== 7. 自我保护 ===")
        r = await c.patch(
            f"{API}/admin/users/{sup}/role", headers=h_super, json={"role": "user"}
        )
        check("超管不能改自己的角色", code_of(r) != 20000, f"code={code_of(r)}")
        r = await c.patch(
            f"{API}/admin/users/{sup}/status", headers=h_super, json={"is_active": False}
        )
        check("超管不能停用自己", code_of(r) != 20000, f"code={code_of(r)}")

        print("\n=== 8. 提升不能超过自己 ===")
        other = ids[accounts[2][0]]
        # 再造一个超管，用它去把别人提升为超管（平级）应被拒
        async with AsyncSessionLocal() as db:
            u = (await db.execute(select(User).where(User.id == sup))).scalar_one()
            u.role = "super_admin"
            await db.commit()
        r = await c.patch(
            f"{API}/admin/users/{other}/role", headers=h_super, json={"role": "super_admin"}
        )
        check("不能把他人提升到与自己同级", code_of(r) != 20000, f"code={code_of(r)}")

    # 清理
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email.in_([a[0] for a in accounts])))
        await db.commit()
    print(f"\n已清理 {len(accounts)} 个测试账号")

    print(f"\n{'=' * 60}\n管理员分级端到端: {ok_n} 通过 / {fail_n} 失败\n{'=' * 60}")
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    for _ in range(30):
        try:
            if httpx.get("http://127.0.0.1:8000/docs", timeout=4).status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        import time

        time.sleep(2)
    if sys.platform == "win32":
        asyncio.run(
            main(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(main())
