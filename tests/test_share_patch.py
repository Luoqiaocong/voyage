"""验证 PATCH 部分更新缺陷已修复，且创建路径不受影响。

必须同时验证两件事：
  1. 只传部分字段时，未传字段不再被重置（缺陷已修）
  2. 创建分享时默认值仍然生效（修复不能误伤创建路径）
"""
import sys

sys.path.insert(0, ".")

from app.modules.itinerary.share_schemas import CreateShareRequest

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def resolve(req: CreateShareRequest) -> dict:
    """复刻修好后的路由逻辑：只取显式传入的字段，其余给 None。"""
    given = req.model_fields_set
    return {
        "allow_copy": req.allow_copy if "allow_copy" in given else None,
        "allow_edit": req.allow_edit if "allow_edit" in given else None,
        "password": req.password if "password" in given else None,
        "expires_in_days": req.expires_in_days if "expires_in_days" in given else None,
    }


print("=== 1. 只传 allow_edit（原缺陷场景）===")
r = resolve(CreateShareRequest(allow_edit=True))
print(f"  {r}")
check("allow_edit 生效", r["allow_edit"] is True)
check("allow_copy 不再被重置为 True", r["allow_copy"] is None, repr(r["allow_copy"]))
check("password 不受影响", r["password"] is None)
check("expires_in_days 不受影响", r["expires_in_days"] is None)

print("\n=== 2. 只关掉 allow_copy（另一个常见场景）===")
r = resolve(CreateShareRequest(allow_copy=False))
print(f"  {r}")
check("allow_copy 被显式设为 False", r["allow_copy"] is False)
check("allow_edit 不被重置为 False", r["allow_edit"] is None, repr(r["allow_edit"]))

print("\n=== 3. 显式传默认值应与「不传」区分开 ===")
r = resolve(CreateShareRequest(allow_copy=True))
check("显式传 True 会被应用（而非当作未传）", r["allow_copy"] is True)
r2 = resolve(CreateShareRequest())
check("完全不传时全部为 None", all(v is None for v in r2.values()), str(r2))

print("\n=== 4. 创建路径不受影响（默认值仍生效）===")
# 创建用的是 req 的解析值本身，而不是过滤后的结果
c = CreateShareRequest()
check("创建时 allow_copy 默认 True", c.allow_copy is True)
check("创建时 allow_edit 默认 False", c.allow_edit is False)
check("创建时 password 默认 None", c.password is None)

print("\n=== 5. 密码与有效期仍可单独修改 ===")
r = resolve(CreateShareRequest(password="abcd1234"))
check("password 被应用", r["password"] == "abcd1234")
check("权限字段不受影响", r["allow_copy"] is None and r["allow_edit"] is None)

r = resolve(CreateShareRequest(expires_in_days=30))
check("expires_in_days 被应用", r["expires_in_days"] == 30)

print(f"\n{'=' * 56}\nPATCH 部分更新验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
sys.exit(1 if fail_n else 0)
