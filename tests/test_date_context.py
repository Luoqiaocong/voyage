"""日期注入的幂等性验证。

这是本次改动最容易出错的地方：中间件在每一轮模型调用前都会执行，
一轮对话里模型可能被调用多次（决定用工具、组织最终回答…）。
若日期段被重复追加，系统提示词会越来越长、且让模型反复确认日期。
"""
import sys

sys.path.insert(0, ".")

from app.core.ai.date_context import _SECTION_TITLE, current_date_line, with_current_date

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


BASE = "你是 Voyage 的旅行顾问。\n\n## 决策原则\n- 能少调就少调"

print("=== 1. 首次注入 ===")
once = with_current_date(BASE)
print(f"  基础 {len(BASE)} 字 -> 注入后 {len(once)} 字")
check("保留了原始提示词", BASE in once)
check("含日期段标题", _SECTION_TITLE in once)
check("含今天的日期", current_date_line() in once)

print("\n=== 2. 连续注入 5 次（模拟多轮模型调用）===")
text = BASE
for i in range(5):
    text = with_current_date(text)
print(f"  5 次后 {len(text)} 字（首次注入后为 {len(once)} 字）")
check("长度不再增长（幂等）", len(text) == len(once), f"{len(text)} vs {len(once)}")
check("日期段只出现一次", text.count(_SECTION_TITLE) == 1,
      f"{text.count(_SECTION_TITLE)} 次")
check("原始提示词只出现一次", text.count("你是 Voyage 的旅行顾问") == 1,
      f"{text.count('你是 Voyage 的旅行顾问')} 次")
check("与首次注入结果完全一致", text == once)

print("\n=== 3. 边界 ===")
check("空基础文本不报错", _SECTION_TITLE in with_current_date(""))
check("None 不报错", _SECTION_TITLE in with_current_date(None))
# 基础文本里恰好含同名字符串时不应被误截断
tricky = f"说明：下面会出现 {_SECTION_TITLE} 这个标题，但它不是日期段"
r = with_current_date(tricky)
check("基础文本含同名字样时仍保留其内容", tricky in r)

print(f"\n{'=' * 52}\n日期注入幂等性: {ok_n} 通过 / {fail_n} 失败\n{'=' * 52}")
sys.exit(1 if fail_n else 0)
