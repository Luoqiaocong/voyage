"""修正 guard 的主机判据。

## 原来的 bug

    if any(m in host for m in LOCAL_MARKERS):   # 含 "redis"
        return False

`condition-curve-eye-30423.db.redis.io` 里含子串 "redis"，于是被当成
「本地」直接放行 —— 判据写反了优先级，而且用裸子串匹配主机名。

## 改法

1. **先判生产**：生产特征（云厂商域名）比本地特征更具体，命中即可确定；
2. **生产特征按域名标签边界匹配**：`redis.io` 应当匹配
   `xxx.db.redis.io`，但不应匹配 `myredis.io`（那是不同域名）；
3. **本地特征只认完整标签**：`redis` / `postgres` 作为主机名的
   **第一个标签**才算（docker compose 的服务名就是这种形式），
   避免再次出现「子串命中」。
"""
from __future__ import annotations

import os
import sys

# 云托管数据库 / Redis 的域名特征（按标签边界匹配）
PROD_HOST_SUFFIXES = (
    "neon.tech",
    "rds.amazonaws.com",
    "redis.io",
    "redislabs.com",
    "upstash.io",
    "aliyuncs.com",
    "tencentcloudapi.com",
    "supabase.co",
)

# docker compose / 本机常见服务名：只认**第一个标签**完全相等
LOCAL_SERVICE_NAMES = {"localhost", "redis", "postgres", "db", "cache", "host.docker.internal"}


def host_of(url: str) -> str:
    """从连接串取主机名（去掉凭据、端口、库名）。"""
    if not url:
        return ""
    body = url.split("@")[-1]
    return body.split("/")[0].split(":")[0].strip().lower()


def _is_private_ipv4(host: str) -> bool:
    """是否 RFC1918 内网地址（10/8、172.16/12、192.168/16）。"""
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    a, b = nums[0], nums[1]
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def looks_like_production(url: str) -> bool:
    """连接串是否指向疑似生产实例。"""
    host = host_of(url)
    if not host:
        return False

    # 1) 回环与内网地址一律视为本地
    #
    # 内网 IP（10./172.16-31./192.168.）按本地处理：它们通常是自建/内网测试
    # 实例，拦住反而妨碍本地验证；真正需要防的是**云托管的生产实例**
    # （数据不可丢、也不该被测试污染），那类都走域名，命中下面的第 2 步。
    if host in {"127.0.0.1", "::1", "0.0.0.0"} or host.startswith("127."):
        return False
    if _is_private_ipv4(host):
        return False

    # 2) 先判生产：命中云厂商域名即确定（按标签边界，不是裸子串）
    if host in PROD_HOST_SUFFIXES or any(
        host.endswith("." + suffix) for suffix in PROD_HOST_SUFFIXES
    ):
        return True

    # 3) 再判本地服务名：只看第一个标签，避免「子串命中」重演
    first_label = host.split(".")[0]
    if first_label in LOCAL_SERVICE_NAMES:
        return False

    # 4) 其余（局域网 IP、自定义域名）视为不确定 —— 保守起见按生产处理，
    #    宁可多拦一次也不要误写真实数据
    return True


def require_non_production(*, allow_env: str = "VOYAGE_ALLOW_PROD_TESTS") -> None:
    """若当前配置指向生产实例则中止；除非显式放行。

    在**建任何数据之前**调用。它只读配置，不连库。
    """
    from app.config import config

    db_prod = looks_like_production(config.DATABASE_URL)
    redis_prod = looks_like_production(config.REDIS_URL)

    if not (db_prod or redis_prod):
        return

    if os.getenv(allow_env) == "1":
        print(
            f"  ⚠ {allow_env}=1：明知指向生产实例仍继续。"
            "请确认脚本会完整清理它创建的数据。"
        )
        return

    print("=" * 72)
    print("已阻止：测试脚本当前会写向**生产实例**")
    print("=" * 72)
    if db_prod:
        print(f"  DATABASE_URL -> {host_of(config.DATABASE_URL)}")
    if redis_prod:
        print(f"  REDIS_URL    -> {host_of(config.REDIS_URL)}")
    print(
        "\n这些连接串来自 .env，而项目没有独立的测试环境配置。\n"
        "可选做法：\n"
        "  1) 在 .env 里换成本地/测试实例后再跑（推荐）\n"
        "  2) 若要明知故犯，设 VOYAGE_ALLOW_PROD_TESTS=1 显式放行\n"
        "  3) docker compose up -d postgres redis 起本地实例，"
        "用它们的地址跑测试"
    )
    print("=" * 72)
    sys.exit(2)


if __name__ == "__main__":
    # 自检：把判据表全跑一遍，避免再出现「子串命中」这类低级错误
    CASES = [
        ("redis://127.0.0.1:6379/7", False, "本机回环"),
        ("redis://localhost:6379/0", False, "localhost"),
        ("redis://redis:6379/7", False, "compose 服务名"),
        ("redis://postgres:6379/0", False, "compose 服务名"),
        ("redis://default:x@condition-curve-eye-30423.db.redis.io:14585", True, "云 Redis（本轮真实用例）"),
        ("redis://x@my-redis.io:6379/0", True, "云 Redis 子域"),
        ("redis://x@myredis.io:6379/0", True, "不同域名（非 *.redis.io）"),
        ("postgresql+asyncpg://u:p@ep-x-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb", True, "Neon"),
        ("postgresql://u:p@db.supabase.co:5432/postgres", True, "Supabase"),
        ("redis://10.0.0.5:6379/0", False, "内网 IP（按本地放行）"),
        ("postgresql://u:p@192.168.1.9:5432/voyage", False, "内网 IP"),
        ("", False, "空串"),
    ]
    ok = bad = 0
    print("=== guard 判据自检 ===")
    for url, expect, note in CASES:
        got = looks_like_production(url)
        good = got == expect
        ok += good
        bad += not good
        print(f"  [{'OK ' if good else 'BUG'}] {note:<26} 期望={expect!s:<5} 实际={got}")
    print(f"\n{ok} 通过 / {bad} 失败")
    sys.exit(1 if bad else 0)
