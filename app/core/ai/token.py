"""LLM Token 用量统计回调。

写入 Redis 两级哈希（字段格式统一为 "{model}:{指标}"）：
  usage:day:{yyyy-MM-dd}   当日各模型用量，TTL 3 天
  usage:model:total        各模型累计用量，TTL 30 天

为什么引入日期维度：管理端看板要展示「今日消耗」，而原先的 usage:{model}
只存了开天辟地以来的累计值，读不出当日数据。日期取 APP_TIMEZONE 的本地日，
避免 UTC 跨日导致「今日」统计错位。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.callbacks import AsyncCallbackHandler

from app.config import config
from app.shared.redis import redis_client
from app.shared.utils import log

# 当日用量保留 3 天（够跨日对账），累计用量保留 30 天
_DAY_TTL = 86400 * 3
_TOTAL_TTL = 86400 * 30

TOTAL_KEY = "usage:model:total"


def _today() -> str:
    """按配置时区取当前日期（yyyy-MM-dd）。"""
    return datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%Y-%m-%d")


def day_key(date_str: str | None = None) -> str:
    """当日用量键；不传日期则取配置时区的今天。"""
    return f"usage:day:{date_str or _today()}"


def _bump(pipe, key: str, model: str, inp: int, out: int, total: int) -> None:
    """把一次调用的用量累加进指定哈希的四个字段。"""
    pipe.hincrby(key, f"{model}:input_tokens", inp)
    pipe.hincrby(key, f"{model}:output_tokens", out)
    pipe.hincrby(key, f"{model}:total_tokens", total)
    pipe.hincrby(key, f"{model}:calls", 1)


class TokenCounter(AsyncCallbackHandler):
    """在每次 LLM 调用结束时累计 token 用量。"""

    async def on_llm_end(self, response, **kwargs):
        try:
            client = redis_client.get_client()
            day = day_key()

            for gens in response.generations or []:
                for gen in gens:
                    msg = getattr(gen, "message", None)
                    if msg is None:
                        continue
                    usage = getattr(msg, "usage_metadata", None)
                    if not usage:
                        continue

                    meta = getattr(msg, "response_metadata", None) or {}
                    model = meta.get("model_name") or meta.get("model") or "unknown"

                    inp = int(usage.get("input_tokens") or 0)
                    out = int(usage.get("output_tokens") or 0)
                    total = int(usage.get("total_tokens") or (inp + out))
                    if inp <= 0 and out <= 0 and total <= 0:
                        continue

                    async with client.pipeline() as pipe:
                        _bump(pipe, day, model, inp, out, total)
                        pipe.expire(day, _DAY_TTL)
                        _bump(pipe, TOTAL_KEY, model, inp, out, total)
                        pipe.expire(TOTAL_KEY, _TOTAL_TTL)
                        await pipe.execute()
        except Exception:
            # 统计失败绝不能影响主流程，但必须留痕，否则用量会静默丢失
            log.exception("TokenCounter failed")


token_counter = TokenCounter()
