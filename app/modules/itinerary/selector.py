"""在对话历史中挑选「最像行程」的 AI 回复。

背景：原先固定取**最后一条** AI 回复。这在真实使用里很容易选错——
用户拿到行程后常常再追问一句「那酒店呢」「谢谢」，行程就被挤出末位，
提取要么失败、要么把一句寒暄当攻略去结构化（后者更糟：会编造出行程）。

两个信号各有短板，这里**组合**使用：
  - 关键词/结构打分：快、零成本、可解释，但只能识别「像不像」，
    无法理解语义（曾出现「世界像一场旅行」的哲学闲聊命中多个旅行词）
  - 大模型挑选：能理解语义，但要多一次调用，且对明显情况是浪费

故策略为：先用结构打分排序，**多数情况直接定案**；
只在分数接近、靠规则分不出高下时才动用大模型。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- 强信号：这些是行程的「骨架」，出现即基本确定是行程 ----

# 天数标记：Day 1 / 第 2 天 / D3
_DAY_RE = re.compile(r"(?:day\s*(\d+)|第\s*([一二三四五六七八九十\d]+)\s*天|d(\d+))", re.I)
# 时段：行程按时间排布的核心特征
_SLOT_RE = re.compile(r"上午|下午|晚上|傍晚|清晨|中午|早上")
# 价格：行程几乎都会标注花费
_PRICE_RE = re.compile(r"[¥￥]\s*\d|\d+\s*元|人均|门票|免费")

# ---- 弱信号：旅行词汇。单独出现不足以判定，只作为加分 ----
_TRAVEL_WORDS = re.compile(
    r"景点|门票|住宿|酒店|民宿|交通|高铁|动车|航班|机票|预算|行程|路线|"
    r"打卡|游览|地铁|公交|打车|早餐|午餐|晚餐|美食|小吃|餐厅"
)

# ---- 负信号：收尾语、寒暄。这些出现时应降低权重 ----
_CLOSING_RE = re.compile(
    r"^(?:好的|好嘞|没问题|不客气|谢谢|收到|明白|哈哈|嗯|欢迎|祝)[，,。！!～~\s]|"
    r"还需要|要不要我|需要我|随时|可以再|还想了解|有别的|还有什么"
)

# 列表项：行程通常按条目罗列，而不是整段散文
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.、])\s+", re.M)


@dataclass
class ScoredReply:
    """一条候选回复及其得分。"""

    index: int
    text: str
    score: float
    signals: dict[str, int]


def score_reply(text: str) -> tuple[float, dict[str, int]]:
    """给一段文本打「像不像行程」的分，返回 (总分, 各信号计数)。

    权重设计的依据：行程的骨架是「按天 + 按时段排布 + 标价格」，
    这三项出现基本可确认；其余词汇只是旅行话题的常见词，
    谈论旅行的人都会说到，不能作为判据。
    """
    if not text or not text.strip():
        return 0.0, {}

    day = len(_DAY_RE.findall(text))
    slot = len(_SLOT_RE.findall(text))
    price = len(_PRICE_RE.findall(text))
    words = len(_TRAVEL_WORDS.findall(text))
    bullets = len(_BULLET_RE.findall(text))
    closing = len(_CLOSING_RE.findall(text))

    signals = {
        "days": day,
        "slots": slot,
        "prices": price,
        "words": words,
        "bullets": bullets,
        "closing": closing,
    }

    score = 0.0
    # 天数是最强信号：明确提到 Day N / 第 N 天
    score += day * 6.0
    # 时段次之：上午/下午/晚上 是行程排布的特征
    score += slot * 3.0
    # 价格：行程几乎都会标注花费
    score += price * 1.2
    # 列表结构：粗略体现「按条目罗列」
    score += min(bullets, 8) * 0.8
    # 旅行词汇只作弱加分，且设上限——防止「聊旅行」被当成「给行程」
    score += min(words, 10) * 0.35
    # 收尾语/寒暄扣分
    score -= closing * 3.0

    # 篇幅过短基本不可能是完整行程（一句「好的」也可能命中词汇）。
    # 注意阈值不能太高：一份只有 2 天、每餐都省略的简版行程
    # 篇幅也在 100 字上下，罚过头会把真行程误判为闲聊。
    stripped = len(re.sub(r"\s", "", text))
    if stripped < 40:
        score -= 6.0

    return max(score, 0.0), signals


def rank_replies(texts: list[str]) -> list[ScoredReply]:
    """按「更像行程」降序排列；**同分时更新的在前**。

    排序主次很关键，这里踩过一次坑：
      最初写成「先按索引倒序、再按分数倒序」，结果**更新的**成了第一优先级，
      一条只值 15 分的新回复会压过 59 分的完整行程，
      于是「第一名不低于第二名」恒成立，大模型裁决分支沦为死代码。

    正确语义是：
      1. 谁的行程特征更强，谁在前   —— 主
      2. 分数相同时，取更新的那条   —— 次（对应用户「只要最新的相似回复」）

    实现方式：一次排序，key 为 (分数, 索引) 的降序元组。
    """
    scored: list[ScoredReply] = []
    for i, text in enumerate(texts):
        s, sig = score_reply(text)
        scored.append(ScoredReply(index=i, text=text, score=s, signals=sig))

    scored.sort(key=lambda x: (x.score, x.index), reverse=True)
    return scored


@dataclass
class PickResult:
    """挑选结果。

    用显式类型而非「返回 None」表达歧义：None 无法区分
    「没有任何像行程的回复」与「有几条都像、规则分不出高下」，
    而这两种情况的后续处理完全不同（前者应报错，后者应交大模型裁决）。
    """

    reply: ScoredReply | None
    #: 规则无法定案时给出的候选（供大模型裁决），否则为空
    ambiguous: list[ScoredReply]
    #: 便于调用方记录日志/排查
    reason: str

    @property
    def decided(self) -> bool:
        return self.reply is not None


def pick_best(texts: list[str]) -> PickResult:
    """挑出最像行程的一条。

    Args:
        texts: 按时间顺序排列的 AI 回复（旧 → 新）

    判定顺序：
      1. 没有任何候选得分为正 → 无行程（调用方应报错）
      2. 只有一条候选，或最高分**严格高于**第二名 → 语义无争议，直接定案
      3. 最高分与第二名**同分** → 排序已让更新的在前，直接取它（满足「要最新」）
      4. 其余情况（更新但分低）→ 交大模型按语义裁决

    第 3、4 步的分界容易写错：同分不需要大模型（「最新」就是答案），
    真正的冲突是「更新的那条分数更低」——此时「最新」与「最像」指向
    不同条目，才值得多花一次调用。
    """
    if not texts:
        return PickResult(reply=None, ambiguous=[], reason="no_messages")

    ranked = rank_replies(texts)
    best = ranked[0]

    if best.score <= 0:
        return PickResult(reply=None, ambiguous=[], reason="no_itinerary_like_reply")

    # 唯一候选，或严格领先：语义无争议
    if len(ranked) == 1 or best.score > ranked[1].score:
        return PickResult(reply=best, ambiguous=[], reason="clear_winner")

    # 同分：排序保证 best 是其中最新的那条，直接取
    if best.score == ranked[1].score:
        return PickResult(reply=best, ambiguous=[], reason="newest_on_tie")

    # 更新但分低：最新与最像冲突，交大模型
    return PickResult(
        reply=None,
        ambiguous=[r for r in ranked if r.score > 0][:4],
        reason="ambiguous",
    )


def top_candidates(texts: list[str], limit: int = 4) -> list[ScoredReply]:
    """取出得分最高的若干条，供大模型在有歧义时裁决。

    只取 top-N 而不是全部：既控制提示词长度，也避免把长对话里
    几十条无关回复都塞进去干扰判断。
    """
    ranked = rank_replies(texts)
    return [r for r in ranked[:limit] if r.score > 0]
