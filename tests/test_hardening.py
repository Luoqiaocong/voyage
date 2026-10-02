"""加固项回归：跨用户记忆隔离、统一密码校验、模型「始终思考」匹配、时区口径。

这些点各自的失效都不会报错、只会静默出错（记忆串用户、时间侧信道、
模型名一变就 400、改时区后两处口径不一致），因此逐条断言而不是抽样。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.config import config
from app.core.ai.llm import _matches_model_pattern, _zhipu_always_thinking
from app.core.ai.memory_context import get_memory_context, use_memory_context
from app.modules.user.auth import PasswordManager
from app.shared.utils.datetime_util import LOCAL_TZ

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


print("=== 1. 密码校验统一（时间侧信道）===")
hashed = PasswordManager.hash("Correct#1")
check("存在的用户 + 正确密码 → True", PasswordManager.verify_uniform("Correct#1", hashed) is True)
check("存在的用户 + 错误密码 → False", PasswordManager.verify_uniform("Wrong#1", hashed) is False)
check("不存在的用户（哈希为 None）→ False", PasswordManager.verify_uniform("anything", None) is False)

# 时间侧信道：不存在用户的分支也必须发生一次真实哈希校验，不能秒回
import time

t0 = time.perf_counter()
for _ in range(3):
    PasswordManager.verify_uniform("probe", None)
missing_ms = (time.perf_counter() - t0) / 3 * 1000
check("不存在的用户仍付出 Argon2 校验开销（>5ms/次）", missing_ms > 5.0, f"{missing_ms:.1f}ms/次")

print("\n=== 2. 模型「始终思考」匹配（配置驱动）===")
check("glm-5 命中（精确）", _zhipu_always_thinking("glm-5") is True)
check("glm-5.3-flash 命中（前缀通配 glm-5.*）", _zhipu_always_thinking("glm-5.3-flash") is True)
check("大小写不敏感 GLM-5.3-Flash 命中", _zhipu_always_thinking("GLM-5.3-Flash") is True)
check("glm-4.5-air 不命中（可关闭思考）", _zhipu_always_thinking("glm-4.5-air") is False)
check("glm-5-air 不命中（glm-5.* 需要点号）", _zhipu_always_thinking("glm-5-air") is False)
check("空名安全", _zhipu_always_thinking("") is False)
check("通配匹配函数：glm-5* 命中 glm-5.3-flash", _matches_model_pattern("glm-5.3-flash", "glm-5*") is True)

print("\n=== 3. 跨用户记忆隔离（contextvar）===")


async def _probe(tag: str, delay: float) -> str:
    with use_memory_context(f"memory-of-{tag}"):
        await asyncio.sleep(delay)  # 模拟并发交错
        return get_memory_context()


async def _run_probes() -> list[str]:
    return await asyncio.gather(_probe("alice", 0.05), _probe("bob", 0.01))


results = asyncio.run(_run_probes())
check("并发任务各自读到自己的记忆", results == ["memory-of-alice", "memory-of-bob"], str(results))
check("退出上下文后复原为空", get_memory_context() == "")

print("\n=== 4. 时区口径统一 ===")
check("展示时区来自 config.APP_TIMEZONE", str(LOCAL_TZ) == config.APP_TIMEZONE, str(LOCAL_TZ))

print("\n=== 5. 全局单例不再持有可变记忆状态 ===")
from app.core.ai import AgentFactory

check("AgentFactory 无 apply_memory（旧全局写法）", not hasattr(AgentFactory, "apply_memory"))
check("AgentFactory 无 _memory_context 全局字段", not hasattr(AgentFactory, "_memory_context"))

print("\n" + "=" * 56)
print(f"加固项回归: {ok_n} 通过 / {fail_n} 失败")
print("=" * 56)
sys.exit(1 if fail_n else 0)
