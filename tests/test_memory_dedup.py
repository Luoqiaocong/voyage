"""记忆去重修复的验证。

覆盖两个实测到的重复形态：
  1. 一个取值里塞了多项（「北京、上海、广州」），无法与单城条目比对
  2. 措辞差异（「美食」/「美食。」、「北京」/「北京市」）绕过精确匹配
"""
import asyncio
import selectors
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

from app.modules.memory.schemas import MemoryExtraction, MemoryFact
from app.modules.memory.service import MemoryService

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def fact(key: str, value: str, conf: float = 0.9) -> MemoryFact:
    return MemoryFact(fact_key=key, fact_value=value, confidence=conf, evidence="原文")


async def main() -> None:
    from sqlalchemy import delete as sa_delete

    from app.shared.db import AsyncSessionLocal, engine
    from app.shared.db.models import Base, User

    print("=== 0. 测试数据准备 ===")
    # 说明：app 的数据库配置在导入时即确定，故这里连的是 .env 里配置的库。
    # user_memories 对 users 有外键，因此必须先建一个测试用户；
    # 结束时删除该用户，ON DELETE CASCADE 会一并清掉其记忆，不留残留。
    test_email = "__dedup_test__@example.invalid"
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == test_email))
        ).scalar_one_or_none()
        if existing:
            await db.execute(sa_delete(User).where(User.id == existing.id))
            await db.commit()
        u = User(email=test_email, password="x", username="dedup-test")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        uid = u.id
    print(f"  已创建测试用户 id={uid}")

    S = MemoryService

    print("=== 1. _expand_multi：拆分含多项的取值 ===")
    cases = [
        ("visited_city", "北京、上海、广州", ["北京", "上海", "广州"]),
        ("visited_city", "北京,上海", ["北京", "上海"]),
        ("visited_city", "北京和上海", ["北京", "上海"]),
        ("preference", "美食与摄影", ["美食", "摄影"]),
        ("preference", "美食", ["美食"]),
        # 单值不应被切碎
        ("preference", "和风旅馆", ["和风旅馆"]),
        # 标量键不拆（值本身不该含分隔符）
        ("home_city", "北京、上海", ["北京、上海"]),
        ("budget_level", "舒适", ["舒适"]),
    ]
    for key, raw, want in cases:
        got = S._expand_multi(key, raw)
        check(f"{key} {raw!r} -> {want}", got == want, str(got))

    print("\n=== 2. _canonical：宽松归一 ===")
    pairs = [
        ("美食", "美食。", True),
        ("北京", "北京市", True),
        ("北京", " 北京 ", True),
        ("美食", "摄影", False),
        ("上海", "上海市", True),
        ("亲子", "亲子游", False),   # 不能过度归并，语义确有差别
    ]
    for a, b, want in pairs:
        got = S._canonical(a) == S._canonical(b)
        check(f"{a!r} vs {b!r} -> {'相同' if want else '不同'}", got == want,
              f"canonical={S._canonical(a)!r}/{S._canonical(b)!r}")

    print("\n=== 3. 端到端：重复写不应产生重复行 ===")
    async with AsyncSessionLocal() as db:
        from app.modules.memory.repo import MemoryRepo

        svc = MemoryService(repo=MemoryRepo(db), db=db)

        # 第一次：合并写法（模拟模型不遵守「一件事一个值」）
        r1 = await svc.upsert_facts(
            user_id=uid,
            extraction=MemoryExtraction(facts=[
                fact("visited_city", "北京、上海、广州"),
                fact("companion", "朋友"),
            ]),
            conversation_id="c1",
        )
        print(f"        第一次: {r1}")
        check("合并写法被拆成 3 城 + 1 同行人", r1["inserted"] == 4, str(r1))

        rows = await svc.list_memories(uid)
        cities = sorted(r.fact_value for r in rows if r.fact_key == "visited_city")
        check("城市拆分为 北京/上海/广州", cities == ["上海", "北京", "广州"], str(cities))

        # 第二次：单独写法 + 措辞差异
        r2 = await svc.upsert_facts(
            user_id=uid,
            extraction=MemoryExtraction(facts=[
                fact("visited_city", "北京"),        # 已存在
                fact("visited_city", "北京市"),      # 归一后等于「北京」
                fact("visited_city", "上海。"),      # 归一后等于「上海」
                fact("visited_city", "成都"),        # 新城市
                fact("companion", "两人同行"),       # 归一后仍不同（靠提示词收敛）
            ]),
            conversation_id="c2",
        )
        print(f"        第二次: {r2}")
        check("北京/北京市/上海。 判为重复", r2["deduped"] >= 3, str(r2))
        check("成都为新城市", r2["inserted"] >= 1, str(r2))

        rows = await svc.list_memories(uid)
        cities = sorted(r.fact_value for r in rows if r.fact_key == "visited_city")
        print(f"        最终城市: {cities}")
        check("城市无重复（4 个）", len(cities) == 4, str(cities))
        check("北京只出现一次", sum(1 for c in cities if "北京" in c) == 1, str(cities))

        print("\n=== 4. 标量键仍按覆盖处理（未被拆分逻辑破坏）===")
        await svc.upsert_facts(
            user_id=uid,
            extraction=MemoryExtraction(facts=[fact("budget_level", "穷游")]),
            conversation_id="c3",
        )
        await svc.upsert_facts(
            user_id=uid,
            extraction=MemoryExtraction(facts=[fact("budget_level", "舒适")]),
            conversation_id="c4",
        )
        rows = await svc.list_memories(uid)
        bl = [r for r in rows if r.fact_key == "budget_level"]
        check("预算档位只有一条", len(bl) == 1, f"{len(bl)} 条")
        check("值已覆盖为「舒适」", bool(bl) and bl[0].fact_value == "舒适",
              bl[0].fact_value if bl else "无")
        check("旧值留痕为「穷游」", bool(bl) and bl[0].previous_value == "穷游",
              str(bl[0].previous_value) if bl else "无")

        print("\n=== 5. 枚举约束仍生效 ===")
        r5 = await svc.upsert_facts(
            user_id=uid,
            extraction=MemoryExtraction(facts=[fact("budget_level", "超级豪华")]),
            conversation_id="c5",
        )
        check("非法枚举值被拒", r5["rejected"] == 1, str(r5))

    # 清理：删掉测试用户，CASCADE 会一并删除其记忆
    async with AsyncSessionLocal() as db:
        await db.execute(sa_delete(User).where(User.id == uid))
        await db.commit()
    print(f"\n  已清理测试用户 id={uid}（其记忆随 CASCADE 删除）")

    print(f"\n{'=' * 56}\n记忆去重验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    # 写真实数据前先确认不是生产实例（见 tests/guard.py 的说明）
    from tests.guard import require_non_production

    require_non_production()
    if sys.platform == "win32":
        asyncio.run(
            main(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(main())
