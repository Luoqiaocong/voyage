"""验证行程提取的用户维度限流。

提取是同步 LLM 调用（超时 120s），成本远高于普通接口；会话锁只拦
同一会话并发，同一用户换会话仍能并发打模型。这里验证新增的用户配额：

  1. 额度超限时抛 429，并带 Retry-After
  2. 被限流时**会话锁必须释放**，否则该会话 180s 内再也提不了
  3. 额度未超时正常放行（继续走到会话转录）
  4. 键与常量本身稳定（换命名会让线上计数凭空归零）
"""
import asyncio
import sys

sys.path.insert(0, ".")

import app.modules.itinerary.service as svc_mod
from app.core.business import BusinessCode, ItineraryException
from app.modules.itinerary.service import ItineraryService
from app.shared.ratelimit import (
    EXTRACT_USER_LIMIT,
    EXTRACT_USER_WINDOW,
    extract_user_key,
)
from fastapi import HTTPException

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)
        return 1


class FakeRedisManager:
    def __init__(self):
        self.redis = FakeRedis()

    def get_client(self):
        return self.redis


class FakeConvGateway:
    def __init__(self, transcript="用户：帮我规划成都三日游"):
        self.transcript = transcript
        self.called = False

    async def get_conversation_transcript(self, conversation_id):
        self.called = True
        return self.transcript


def make_service(gateway):
    # repo/db 在「拿到锁之后、写库之前」都用不到：
    # 限流与转录发生在写库前，本测试只覆盖这两段。
    return ItineraryService(repo=None, conv_gateway=gateway, db=None)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ===================== 1. 常量与键 =====================
print("=== 1. 常量与键 ===")
check("限额为正整数", EXTRACT_USER_LIMIT > 0, str(EXTRACT_USER_LIMIT))
check("窗口为正整数", EXTRACT_USER_WINDOW > 0, str(EXTRACT_USER_WINDOW))
check("键格式稳定", extract_user_key(42) == "rate:extract:user:42", extract_user_key(42))


# ===================== 2. 超限：429 + 释放锁 =====================
print("=== 2. 额度超限 ===")
fake_mgr = FakeRedisManager()
svc_mod.redis_client = fake_mgr
captured = {}


async def over_limit(key, limit, window):
    captured["key"], captured["limit"], captured["window"] = key, limit, window
    return True


svc_mod.check_rate_limit = over_limit

gateway = FakeConvGateway()
service = make_service(gateway)
raised = None
try:
    run(service.save_from_conversation("conv-1", 42))
except HTTPException as e:
    raised = e

check("抛出 HTTPException", raised is not None)
check("状态码 429", raised is not None and raised.status_code == 429, str(raised and raised.status_code))
check(
    "带 Retry-After",
    raised is not None and raised.headers.get("Retry-After") == str(EXTRACT_USER_WINDOW),
    str(raised and raised.headers),
)
check("按用户维度计次", captured.get("key") == extract_user_key(42), str(captured.get("key")))
check("用统一限额常量", captured.get("limit") == EXTRACT_USER_LIMIT, str(captured.get("limit")))
check("超限时不调用模型", gateway.called is False)
lock_key = "itinerary:extract:42:conv-1"
check("会话锁已释放", lock_key in fake_mgr.redis.deleted, str(fake_mgr.redis.deleted))
check("锁未残留", lock_key not in fake_mgr.redis.store)


# ===================== 3. 未超限：放行到转录 =====================
print("=== 3. 额度未超 ===")
fake_mgr2 = FakeRedisManager()
svc_mod.redis_client = fake_mgr2


async def under_limit(key, limit, window):
    return False


# 把模型调用换成离线桩：返回 None 表示「无可提取内容」，
# 服务应以 ITINERARY_GEN_FAILED 收尾，而**不是**在限流处被拦。
async def fake_extract(transcript):
    return None


svc_mod.check_rate_limit = under_limit
svc_mod.extract_itinerary_plan = fake_extract

gateway2 = FakeConvGateway()
service2 = make_service(gateway2)
raised2 = None
try:
    run(service2.save_from_conversation("conv-2", 7))
except ItineraryException as e:
    raised2 = e
except Exception as e:  # noqa: BLE001
    raised2 = e

check("放行后确实读了转录", gateway2.called is True)
check("未被限流拦截", not isinstance(raised2, HTTPException), type(raised2).__name__)
check(
    "按业务语义失败（无可提取内容）",
    isinstance(raised2, ItineraryException),
    type(raised2).__name__ if raised2 else "no-raise",
)
lock_key2 = "itinerary:extract:7:conv-2"
check("放行路径同样释放锁", lock_key2 in fake_mgr2.redis.deleted, str(fake_mgr2.redis.deleted))
check(
    "忙锁业务码未被改动",
    BusinessCode.ITINERARY_EXTRACT_BUSY.value[0] == 60010,
    str(BusinessCode.ITINERARY_EXTRACT_BUSY.value),
)


print(f"\n结果：PASS {ok_n} / FAIL {fail_n}")
sys.exit(1 if fail_n else 0)
