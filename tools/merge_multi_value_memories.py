"""合并存量记忆里的多值键：把「一城一行」折叠成「一行一键」。

背景
----
多值键（preference / dietary / visited_city / companion）原先一个取值一行，
于是「去过的城市」有三座就有三行，记忆面板上呈现为三张几乎相同的卡片。
现在改为一行一个键、多项用「、」连接 —— 这也与注入 prompt 时的按键聚合一致。

本脚本把**改动前已经落库**的数据按新形态折叠。对已经符合新形态的数据
是幂等的（不会重复合并、不会丢值）。

用法
----
    uv run --no-sync python tools/merge_multi_value_memories.py          # 只看结果
    uv run --no-sync python tools/merge_multi_value_memories.py --apply  # 真正写库

安全
----
写真实数据前会调用 tests/guard.py 的 require_non_production()：
连接串指向生产实例时直接拒绝，除非显式设 VOYAGE_ALLOW_PROD_TESTS=1。
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

from app.modules.memory.schemas import (  # noqa: E402
    MULTI_KEYS,
    merge_values,
    pack_values,
    split_values,
)
from app.shared.db import AsyncSessionLocal  # noqa: E402
from app.shared.db.models import UserMemory  # noqa: E402


async def main(*, apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(UserMemory)
                    .where(UserMemory.fact_key.in_(tuple(MULTI_KEYS)))
                    .order_by(UserMemory.user_id, UserMemory.fact_key, UserMemory.id)
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            print("  没有多值键记忆，无需处理")
            return 0

        # 按 (用户, 键) 归拢
        buckets: dict[tuple[int, str], list[UserMemory]] = defaultdict(list)
        for r in rows:
            buckets[(r.user_id, r.fact_key)].append(r)

        print(f"  多值键记忆共 {len(rows)} 行，分布在 {len(buckets)} 个（用户, 键）组合\n")

        changed = 0
        for (uid, key), group in sorted(buckets.items()):
            # 逐行按 id 顺序合并（老项在前），保持用户看惯的顺序
            merged: list[str] = []
            for r in group:
                merged = merge_values(pack_values(merged) or None, *split_values(r.fact_value))
            packed = pack_values(merged)

            # 是否已经收敛？判据是**内容**，而不是「行数」。
            # 只写「len(group) == 1 就跳过」是错的：一行里挤着三项
            # （合并后的正常形态）也会被当成待处理，于是脚本永远报「待合并」，
            # 幂等性不成立（实测踩过）。
            already = len(group) == 1 and group[0].fact_value == packed
            if already:
                continue

            # 保留「命中最多的那一行」作为宿主：它的 hit_count 最能代表
            # 这项偏好被重复确认过几次；并列时取 id 最小的（最老的一行）
            keeper = max(group, key=lambda r: (r.hit_count or 1, -r.id))
            losers = [r for r in group if r is not keeper]

            print(f"  user={uid} {key}")
            print(f"      合并前 {len(group)} 行: {[r.fact_value for r in group]}")
            print(f"      合并后 1 行: {packed!r}")
            print(f"      保留 id={keeper.id}（hits={keeper.hit_count}），删除 "
                  f"{[r.id for r in losers]}")

            # hit_count 取总和：这个数表示「用户说过几次」，合并后仍应保留
            total_hits = sum((r.hit_count or 1) for r in group)
            max_conf = max((r.confidence or 0) for r in group)
            # 只要有一行是生效的，合并后就是生效的（否则用户会莫名少一项）
            any_active = any(r.is_active for r in group)

            if apply:
                keeper.fact_value = packed
                keeper.hit_count = total_hits
                keeper.confidence = max_conf
                keeper.is_active = any_active
                for r in losers:
                    await db.delete(r)
            changed += 1

        if apply:
            await db.commit()
            print(f"\n  已合并 {changed} 组并提交")
        else:
            print(f"\n  待合并 {changed} 组（dry-run，未写库）")
            print("  确认无误后加 --apply 执行")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="合并多值键记忆为一行一个键")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只预览）")
    args = ap.parse_args()

    if args.apply:
        from tests.guard import require_non_production

        require_non_production()

    if sys.platform == "win32":
        code = asyncio.run(
            main(apply=args.apply),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        code = asyncio.run(main(apply=args.apply))
    sys.exit(code)
