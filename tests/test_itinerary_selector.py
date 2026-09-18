"""行程选择器测试：用真实出现过的回复形态，确认选得对。

直接运行：uv run python tests/test_itinerary_selector.py

样本全部来自本项目实测（含两个曾让关键词方案翻车的反例），
不是编造的理想数据。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.itinerary.selector import pick_best, score_reply, top_candidates

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


REAL_TRIP = """帮你把成都 3 天安排好了：

**Day 1 市区文化美食**
- 上午：宽窄巷子，门票免费
- 下午：人民公园鹤鸣茶社，约 80 元
- 晚上：蜀大侠火锅春熙路店，人均 150 元

**Day 2 都江堰一日**
- 上午：都江堰景区，门票 80 元
- 下午：青城山前山，门票 90 元
- 晚上：返回市区休息

**Day 3 熊猫与返程**
- 上午：大熊猫繁育研究基地，门票 55 元
- 下午：太古里方所书店
- 晚上：返程

住宿：春熙路亚朵酒店两晚约 1160 元
预算：合计约 3000 元"""

PHILOSOPHY = """哈哈，你又来聊哲学了！😄

上次我说世界像一场没有固定路线的旅行，今天换个角度——
我觉得世界有点像你刚才规划的那趟杭州之旅：看起来是你在规划世界，
其实是世界在给你惊喜。你精心挑了 10:33 的高铁、订了西湖边的亲子酒店、
算好了预算，结果呢——两天都下雨。

好了，哲学家模式关闭 😂 刚才的杭州行程还有什么需要调整的吗？"""

CLOSING = "好的，行程已经给你了，还有什么需要调整的吗？随时告诉我～"

TRAINS = """明天广州南到北京西的高铁，按早班优先：

| 车次 | 时刻 | 二等座 |
|---|---|---|
| G77 | 08:00 → 13:24 | ¥553 |
| G79 | 10:05 → 15:38 | ¥553 |
| D7 | 16:20 → 22:40 | ¥420 |

历时约 5 小时 24 分。"""

HOTELS = """西湖边适合亲子的酒店，按位置和价位理一下：

**🏨 中端之选（约 500–800 元/晚）**
- **全季酒店（湖滨店）**：位置核心，出门就是湖滨步行街
- **柳莺里一带的酒店**：靠近柳浪闻莺，环境安静

**🏨 高端之选（1200 元+/晚）**
- **杭州君悦、杭州四季**：多备有儿童备品，部分带泳池"""

print("=== 1. 单条打分（行程应显著高于各反例）===")
trip_score, trip_sig = score_reply(REAL_TRIP)
print(f"        真实行程   {trip_score:6.1f}  {trip_sig}")
for name, text in [
    ("哲学闲聊", PHILOSOPHY),
    ("收尾寒暄", CLOSING),
    ("车次表", TRAINS),
    ("酒店推荐", HOTELS),
]:
    s, sig = score_reply(text)
    print(f"        {name:<9} {s:6.1f}  {sig}")
    check(f"行程分高于{name}", trip_score > s, f"{trip_score:.1f} vs {s:.1f}")

print("\n=== 2. 核心场景：行程之后跟了一句闲话 ===")
res = pick_best([REAL_TRIP, CLOSING])
print(f"        reason={res.reason}")
check("选中了行程而非末条寒暄", res.decided and res.reply.index == 0,
      f"index={res.reply.index if res.reply else None}")
check("选中的确实是行程",
      res.decided and res.reply.text.startswith("帮你把成都"))

print("\n=== 3. 核心场景：行程之后闲聊了哲学 ===")
res2 = pick_best([REAL_TRIP, PHILOSOPHY, CLOSING])
print(f"        reason={res2.reason}")
check("仍能选中行程", res2.decided and res2.reply.index == 0,
      f"index={res2.reply.index if res2.reply else None}")

print("\n=== 4. 多份行程：应选最新的那份 ===")
trip_old = REAL_TRIP.replace("成都", "西安").replace("3000", "2500")
trip_new = REAL_TRIP.replace("成都", "三亚").replace("3000", "4000")
res3 = pick_best([trip_old, CLOSING, trip_new])
print(f"        reason={res3.reason}  "
      f"得分={[round(x.score, 1) for x in ([res3.reply] if res3.reply else res3.ambiguous)]}")
picked = res3.reply.text if res3.reply else ""
check("同分时选最新的（三亚）", "三亚" in picked,
      f"命中={'三亚' if '三亚' in picked else '西安' if '西安' in picked else '无'}")

print("\n=== 5. 只有闲聊时应判定无行程（不硬选）===")
res4 = pick_best([CLOSING, PHILOSOPHY])
print(f"        reason={res4.reason}")
check("无行程时给出明确原因", not res4.decided and res4.reason == "no_itinerary_like_reply",
      res4.reason)

print("\n=== 6. 单条行程（唯一候选）===")
res5 = pick_best([REAL_TRIP])
check("唯一候选直接定案", res5.decided and res5.reply.index == 0, res5.reason)

print("\n=== 7. 空输入 ===")
check("空列表返回空结果", pick_best([]).reply is None)
check("全空文本返回空结果", pick_best(["", "  "]).reply is None)

print("\n=== 8. 车次表分数应低于行程 ===")
s_train, _ = score_reply(TRAINS)
check("行程 > 车次表", trip_score > s_train, f"{trip_score:.1f} vs {s_train:.1f}")

print("\n=== 9. 打分器能否识破「堆砌关键词但内容是空的」 ===")
# 这条回复逐日标题、时段词、价格词都齐，但每个时段都是空的——
# 是「关键词密度高、语义上却不可提取」的典型。
# 期望：打分器自己就把它压下去，不必动用大模型。
# （若哪天打分器失灵，这条会先失败，起到哨兵作用。）
stuffed_new = """这是更新后的方案，信息更全，含逐日明细与预算：

**Day 1**
- 上午：
- 下午：
- 晚上：

**Day 2**
- 上午：
- 下午：
- 晚上：

门票、人均、酒店、交通、路线、打卡、游览、景点、住宿、预算
都还在核对中，稍后补齐具体内容与价格。"""
s_stuffed, sig_stuffed = score_reply(stuffed_new)
print(f"        堆砌文本={s_stuffed:.1f} {sig_stuffed}")
print(f"        真实行程={trip_score:.1f} {trip_sig}")
check("空壳行程分数低于真行程", trip_score > s_stuffed,
      f"{trip_score:.1f} vs {s_stuffed:.1f}")
res6 = pick_best([REAL_TRIP, stuffed_new])
check("因此直接选中真行程，无需大模型",
      res6.decided and res6.reply.index == 0, res6.reason)

print("\n=== 9b. 同分时不需要大模型（排序已按最新定案）===")
same_a = REAL_TRIP.replace("成都", "西安")
same_b = REAL_TRIP.replace("成都", "三亚")
res6b = pick_best([same_a, same_b])
print(f"        reason={res6b.reason}")
check("同分直接定案且取最新（三亚）",
      res6b.decided and "三亚" in res6b.reply.text, res6b.reason)

print("\n=== 9c. 打分器找不到行程时应给出明确原因，交由大模型兜底 ===")
# 全部是闲聊 → 规则无从下手，service 会走「送大模型做语义检索」的兜底路径。
# 这里只验证信号正确，大模型那一步在 tests/../service 层由 e2e 覆盖。
res6c = pick_best([PHILOSOPHY, CLOSING])
print(f"        reason={res6c.reason}  候选={len(res6c.ambiguous)} 条")
check("判为「没有像行程的回复」", res6c.reason == "no_itinerary_like_reply",
      res6c.reason)
check("不自行硬选", not res6c.decided)

print("\n=== 10. top_candidates 供大模型裁决 ===")
cands = top_candidates([REAL_TRIP, CLOSING, HOTELS, TRAINS], limit=3)
print(f"        返回 {len(cands)} 条，得分: {[round(c.score, 1) for c in cands]}")
check("返回不超过 limit", len(cands) <= 3)
check("按分数降序", all(cands[i].score >= cands[i + 1].score for i in range(len(cands) - 1)))
check("不含零分候选", all(c.score > 0 for c in cands))

print(f"\n{'=' * 56}\n选择器验证: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
if __name__ == "__main__":
    sys.exit(1 if fail_n else 0)
