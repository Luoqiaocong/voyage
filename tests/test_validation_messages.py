"""验证密码/邮箱等校验错误是否给出可读的中文原因。

覆盖用户报告的两类：
  · 密码不足 8 位 -> 原先只说「Param Error」
  · 密码缺大小写  -> 原先同样只说「Param Error」
以及顺带检查邮箱格式、缺字段等相邻情况。
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


# (端点, 请求体, 期望 message 里包含的关键词, 说明)
#
# 为什么不全用 /users/reg：注册有「同一 IP 每小时最多 5 次」的限制
# （防批量注册，见 shared/ratelimit.py）。用例多于 5 个时，
# 后面的会拿到 429 而不是校验错误 —— 那测的就不是校验逻辑了。
# 校验发生在 schema 层，与端点无关，故把最后一个用例换到 /users/login。
CASES = [
    ("reg", {"email": "a@b.com", "password": "Ab1", "code": "123456", "username": "测试"},
     "至少", "密码 3 位"),
    ("reg", {"email": "a@b.com", "password": "abcdefgh1", "code": "123456", "username": "测试"},
     "大写", "长度够但缺大写"),
    ("reg", {"email": "a@b.com", "password": "ABCDEFG1", "code": "123456", "username": "测试"},
     "小写", "长度够但缺小写"),
    ("login", {"email": "a@b.com", "password": "Abcdefgh"},
     "数字", "长度够但缺数字"),
    ("login", {"email": "not-an-email", "password": "Abcdefg1"},
     "邮箱", "邮箱格式错误"),
    ("login", {"email": "a@b.com"},
     "密码", "完全没给密码"),
]


async def main() -> None:
    import redis.asyncio as aioredis

    # 先清掉限流计数，避免上一次运行的残留影响本次
    r = aioredis.from_url("redis://127.0.0.1:6379/7", decode_responses=True)
    try:
        keys = [k async for k in r.scan_iter(match="rate:*", count=200)]
        if keys:
            await r.delete(*keys)
            print(f"  （已清除 {len(keys)} 个限流计数）")
    finally:
        await r.aclose()

    async with httpx.AsyncClient(timeout=20) as c:
        for endpoint, body, kw, why in CASES:
            url = f"{API}/users/{'reg' if endpoint == 'reg' else 'login'}"
            r = await c.post(url, json=body)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            msg = str(data.get("message", ""))
            print(f"  [{endpoint}] {why}: HTTP {r.status_code}  message={msg!r}")
            if r.status_code == 429:
                check(f"{why}（被限流跳过）", False, "429 说明限流额度不足")
                continue
            check(f"{why} 提示含「{kw}」", kw in msg, msg)
            check(f"{why} 不再是 Param Error", "Param Error" not in msg, msg)


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
    print(f"\n{'=' * 56}\n校验提示验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
    sys.exit(1 if fail_n else 0)
