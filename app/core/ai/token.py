# app/core/ai/token.py
from langchain_core.callbacks import AsyncCallbackHandler

from app.shared.redis import redis_client
from app.shared.utils import log


class TokenCounter(AsyncCallbackHandler):
    async def on_llm_end(self, response, **kwargs):
        # log.info(f"LLM Response: {response}")
        try:
            for gens in response.generations or []:
                for gen in gens:
                    msg = getattr(gen, "message", None)
                    if not msg:
                        continue
                    usage = getattr(msg, "usage_metadata", None)
                    if not usage:
                        continue

                    meta = getattr(msg, "response_metadata", None) or {}
                    model = meta.get("model_name") or meta.get("model") or "unknown"
                    key = f"usage:{model}"

                    inp = int(usage.get("input_tokens") or 0)
                    out = int(usage.get("output_tokens") or 0)
                    total = int(usage.get("total_tokens") or (inp + out))

                    client = redis_client.get_client()

                    async with client.pipeline() as pipe:
                        pipe.hincrby(key, "input_tokens", inp)
                        pipe.hincrby(key, "output_tokens", out)
                        pipe.hincrby(key, "total_tokens", total)
                        pipe.expire(key, 86400 * 2)
                        await pipe.execute()
        except Exception:
            log.exception("TokenCounter failed")


token_counter = TokenCounter()
