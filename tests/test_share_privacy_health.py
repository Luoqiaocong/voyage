"""分享密码明文移除 + 公开存活探针 /health。

## 背景

ItineraryShare.password_plain 早期用于让分享者「再次查看」自己设的密码，
代价是明文落库：备份、只读副本、运维导出都能直接读到访问密码。现改为
只存 argon2 哈希、明文不落库不回传，忘记密码走「重置」。本测试锁定该行为，
并验证新增的公开 /health 探针已接到 Dockerfile / compose / nginx。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.modules.itinerary.share_schemas import ShareItem
from app.modules.itinerary.share_service import ShareService

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeDB:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.flushes += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeItinerary:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self.plan = {"destination": "成都", "days": 3}


class FakeItineraryRepo:
    def __init__(self, owner_id: int) -> None:
        self.owner_id = owner_id

    async def get(self, _itinerary_id: int):
        return FakeItinerary(self.owner_id)


class FakeShare:
    """足够被 share_service 操作的分享实体。"""

    def __init__(self, **kw) -> None:
        self.id = kw.get("id", 5)
        self.owner_id = kw.get("owner_id", 1)
        self.password_hash = kw.get("password_hash")
        self.password_plain = kw.get("password_plain")
        self.allow_copy = kw.get("allow_copy", True)
        self.allow_edit = kw.get("allow_edit", False)
        self.expires_at = kw.get("expires_at")
        self.revoked_at = None
        self.view_count = 0


class FakeShareRepo:
    def __init__(self) -> None:
        self.inserted: dict | None = None
        self.share: FakeShare | None = None

    async def insert(self, **fields):
        self.inserted = fields
        return FakeShare(**{"id": 99, **fields})

    async def get_by_id(self, _share_id: int):
        return self.share


def make_service(owner_id: int = 1, share: FakeShare | None = None):
    repo = FakeShareRepo()
    repo.share = share
    db = FakeDB()
    svc = ShareService(
        share_repo=repo,
        itinerary_repo=FakeItineraryRepo(owner_id),
        db=db,
    )
    return svc, repo, db


# ===================== 1. schema 不再暴露明文 =====================
print("=== 1. ShareItem schema ===")
check("不再含 password 字段", "password" not in ShareItem.model_fields, str(list(ShareItem.model_fields)))
check("保留 has_password", "has_password" in ShareItem.model_fields)


# ===================== 2. 创建：不写明文 =====================
print("\n=== 2. 创建分享 ===")
svc, repo, db = make_service()
run(svc.create_share(
    user_id=1, itinerary_id=10, allow_copy=True, allow_edit=False,
    password="abcd1234", expires_in_days=7,
))
fields = repo.inserted or {}
check("未写入 password_plain", "password_plain" not in fields, str(sorted(fields)))
check("写入了 password_hash", bool(fields.get("password_hash")))
check("hash 不等于明文", fields.get("password_hash") != "abcd1234")
check("hash 是 argon2 串", str(fields.get("password_hash", "")).startswith("$argon2"), str(fields.get("password_hash"))[:20])

svc2, repo2, _ = make_service()
run(svc2.create_share(
    user_id=1, itinerary_id=10, allow_copy=True, allow_edit=False,
    password=None, expires_in_days=None,
))
check("不设密码时 hash 为 None", repo2.inserted.get("password_hash") is None, str(repo2.inserted))
check("不设密码时同样无 password_plain", "password_plain" not in repo2.inserted)


# ===================== 3. 修改：停写并清除遗留明文 =====================
print("\n=== 3. 修改分享密码 ===")
share = FakeShare(id=5, owner_id=1, password_plain="OLD_PLAINTEXT")
svc3, _, _ = make_service(share=share)
run(svc3.update_share(
    user_id=1, share_id=5, allow_copy=None, allow_edit=None,
    password="newpass1", clear_password=False,
    expires_in_days=None, clear_expiry=False,
))
check("改密码写入新 hash", bool(share.password_hash) and share.password_hash != "newpass1")
check("遗留明文被清为 None", share.password_plain is None, repr(share.password_plain))

share2 = FakeShare(id=6, owner_id=1, password_hash="$argon2$keep", password_plain="OLD2")
svc4, _, _ = make_service(share=share2)
run(svc4.update_share(
    user_id=1, share_id=6, allow_copy=None, allow_edit=None,
    password=None, clear_password=True,
    expires_in_days=None, clear_expiry=False,
))
check("清除密码时 hash 置空", share2.password_hash is None)
check("清除密码时遗留明文也置空", share2.password_plain is None, repr(share2.password_plain))


# ===================== 4. 公开 /health =====================
print("\n=== 4. 公开存活探针 ===")
from app.main import app  # noqa: E402
import httpx  # noqa: E402


async def _get_health():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get("/health")


paths = {getattr(r, "path", None) for r in app.routes}
check("应用注册了 /health 路由", "/health" in paths, str(sorted(p for p in paths if p)))
resp = run(_get_health())
check("GET /health 返回 200", resp.status_code == 200, str(resp.status_code))
check("响应体为 {status: ok}", resp.json() == {"status": "ok"}, resp.text)
check("不进入 OpenAPI schema", "/health" not in app.openapi().get("paths", {}))

docker = Path("Dockerfile").read_text(encoding="utf-8")
compose = Path("docker-compose.yml").read_text(encoding="utf-8")
nginx = Path("web/nginx.conf").read_text(encoding="utf-8")
check("Dockerfile 探针指向 /health", "127.0.0.1:8000/health" in docker)
check("Dockerfile 探针不再打 /docs", "127.0.0.1:8000/docs" not in docker)
check("compose 后端探针指向 /health", "127.0.0.1:8000/health" in compose)
check("nginx 对 /health 精确匹配（不落 SPA 回退）", "location = /health" in nginx)


print(f"\n{'=' * 56}\n分享密码与 /health 验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
sys.exit(1 if fail_n else 0)
