"""LLM Token 用量统计回调。

写入 Redis 两级哈希（字段格式统一为 "{model}:{指标}"）：
  usage:day:{yyyy-MM-dd}   当日各模型用量，TTL 3 天
  usage:model:total        各模型累计用量，TTL 30 天

为什么引入日期维度：管理端看板要展示「今日消耗」，而原先的 usage:{model}
只存了开天辟地以来的累计值，读不出当日数据。日期取 APP_TIMEZONE 的本地日，
避免 UTC 跨日导致「今日」统计错位。

另有**按用户**的两级哈希，字段格式为 "{user_id}:{指标}"：
  usage:user:day:{yyyy-MM-dd}   当日各用户用量，TTL 3 天
  usage:user:total              各用户累计用量，TTL 30 天
用户 ID 由上下文变量提供（见 opencode.use_user），供管理端的「Token 用量排行」。

为什么用户维度单独用一组键，而不是塞进现有哈希：
  两者是**不同的聚合维度**，字段前缀的类型都不一样（模型名 vs 数字 ID），
  混在一个哈希里一旦某个模型名恰好是纯数字就会互相覆盖。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.callbacks import AsyncCallbackHandler

from app.config import config
from app.shared.redis import redis_client
from app.shared.utils import log

from .opencode import get_current_user_id

# 当日用量保留 3 天（够跨日对账），累计用量保留 30 天
_DAY_TTL = 86400 * 3
_TOTAL_TTL = 86400 * 30

TOTAL_KEY = "usage:model:total"
USER_TOTAL_KEY = "usage:user:total"


def _today() -> str:
    """按配置时区取当前日期（yyyy-MM-dd）。"""
    return datetime.now(ZoneInfo(config.APP_TIMEZONE)).strftime("%Y-%m-%d")


def day_key(date_str: str | None = None) -> str:
    """当日用量键；不传日期则取配置时区的今天。"""
    return f"usage:day:{date_str or _today()}"


def user_day_key(date_str: str | None = None) -> str:
    """当日**按用户**用量键。"""
    return f"usage:user:day:{date_str or _today()}"


def _bump(pipe, key: str, name: str, inp: int, out: int, total: int) -> None:
    """把一次调用的用量累加进指定哈希的四个字段。

    name 是字段前缀：模型维度传模型名，用户维度传 user_id。
    """
    pipe.hincrby(key, f"{name}:input_tokens", inp)
    pipe.hincrby(key, f"{name}:output_tokens", out)
    pipe.hincrby(key, f"{name}:total_tokens", total)
    pipe.hincrby(key, f"{name}:calls", 1)


class TokenCounter(AsyncCallbackHandler):
    """在每次 LLM 调用结束时累计 token 用量。"""

    async def on_llm_end(self, response, **kwargs):
        try:
            client = redis_client.get_client()
            day = day_key()
            user_day = user_day_key()
            # 用户 ID 为 0 表示「不在请求上下文内」（启动预热、CLI 调用等）。
            # 这类调用只计模型维度，不写用户维度 —— 归到某个用户头上会是
            # 错误数据，宁可少记也不能记错。
            uid = get_current_user_id()

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
                        if uid:
                            _bump(pipe, user_day, str(uid), inp, out, total)
                            pipe.expire(user_day, _DAY_TTL)
                            _bump(pipe, USER_TOTAL_KEY, str(uid), inp, out, total)
                            pipe.expire(USER_TOTAL_KEY, _TOTAL_TTL)
                        await pipe.execute()
        except Exception:
            # 统计失败绝不能影响主流程，但必须留痕，否则用量会静默丢失
            log.exception("TokenCounter failed")


token_counter = TokenCounter()
