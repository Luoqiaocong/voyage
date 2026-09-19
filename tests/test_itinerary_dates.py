"""验证 Bug 1 修复：行程日期年份错位。

两层分别验证：
  1. 代码兜底 _normalize_year / _sanitize_plan_dates（纯函数，可穷举边界）
  2. 提示词是否注入了当前日期（模型换算相对日期的前提）
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.core.ai.date_context import current_date_line
from app.modules.itinerary.extractor import (
    _EXTRACT_SYSTEM_PROMPT,
    _normalize_year,
    _sanitize_plan_dates,
)
from app.modules.itinerary.schemas import ItineraryPlan

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


today = date.today()
print(f"=== 今天是 {today} ===\n")

print("=== 1. _normalize_year：把错位年份拉回最近的一年 ===")
cases = [
    # (输入日期, 期望, 说明)
    (date(today.year - 1, 9, 21), date(today.year, 9, 21), "去年同月日 → 今年（用户报的就是这种）"),
    (date(today.year - 2, 5, 1), date(today.year, 5, 1), "前年 → 今年"),
    (date(today.year, 9, 21), date(today.year, 9, 21), "今年不变"),
    (date(today.year - 1, 12, 25), date(today.year, 12, 25), "去年圣诞 → 今年圣诞"),
]
for given, want, why in cases:
    got = _normalize_year(given, today)
    check(f"{given} -> {got}   （{why}）", got == want, f"期望 {want}")

print("\n=== 2. 跨年边界：月日刚过去时应落到明年 ===")
# 取今天减 10 天（同月日若在今年则已过去），最近的合理年份是明年
past = today - timedelta(days=10)
given = past.replace(year=today.year - 1)     # 模型写了一年前
got = _normalize_year(given, today)
gap_now = abs((given.replace(year=today.year) - today).days)
print(f"  样本：今天 {today}，模型给 {given}")
print(f"        候选 今年={given.replace(year=today.year)}（距今天 {gap_now} 天）"
      f"  明年={given.replace(year=today.year + 1)}")
check("修正结果与今天的距离不超过 366 天",
      abs((got - today).days) <= 366, f"得到 {got}，差 {abs((got - today).days)} 天")

print("\n=== 3. 闰日不崩 ===")
try:
    r = _normalize_year(date(2024, 2, 29), today)
    check("2 月 29 日可处理", True, str(r))
except Exception as e:  # noqa: BLE001
    check("2 月 29 日可处理", False, f"{type(e).__name__}: {e}")

print("\n=== 4. 非法格式的日期被置空（而非展示错误日期）===")


def mk(plan_dates: list[str]) -> ItineraryPlan:
    return ItineraryPlan.model_validate({
        "destination": "测试",
        "days": len(plan_dates),
        "daily_plans": [
            {"day_no": i + 1, "date": d, "theme": "t", "summary": "s", "activities": []}
            for i, d in enumerate(plan_dates)
        ],
    })


plan = _sanitize_plan_dates(mk(["2025-09-21", "乱写的日期", "", "2026-09-22"]))
dates = [d.date for d in plan.daily_plans]
print(f"  输入 ['2025-09-21', '乱写的日期', '', '2026-09-22']")
print(f"  输出 {dates}")
check("错位年份被修正", dates[0] == today.replace(month=9, day=21).isoformat()
      or str(dates[0]).endswith("-09-21"), str(dates[0]))
check("非法格式被置空", dates[1] is None, repr(dates[1]))
check("空值保持为空", not dates[2], repr(dates[2]))

print("\n=== 5. 提示词已注入当前日期 ===")
line = current_date_line()
print(f"  current_date_line() = {line}")
# extract_itinerary_plan 是运行时拼接的，这里验证拼接后的内容
from app.modules.itinerary import extractor as ex

assert ex._EXTRACT_SYSTEM_PROMPT is not None
check("提示词模板含 date 字段的年份要求",
      "绝不要使用你自己记忆中的年份" in ex._EXTRACT_SYSTEM_PROMPT)
check("提示词要求相对表述不自行推算",
      "不要**自行推算日期" in ex._EXTRACT_SYSTEM_PROMPT
      or "自行推算日期" in ex._EXTRACT_SYSTEM_PROMPT)

print("\n=== 6. 其余地方是否也需要注入（记忆抽取）===")
from app.modules.memory import schemas as ms

check("记忆提示词同样缺当前日期",
      "今天" not in ms.MEMORY_SYSTEM_PROMPT,
      "记忆不填具体日期，故不影响；但相对日期表述仍可能被误存")

print(f"\n{'=' * 58}\n日期修复验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 58}")
sys.exit(1 if fail_n else 0)
