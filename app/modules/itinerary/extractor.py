"""行程专属结构化提取：把对话攻略 Markdown → ItineraryPlan。

依赖方向：modules → core（行程域提供 schema 与专属提示词，调用 core 的通用提取器）。
"""
from datetime import date

from pydantic import BaseModel, Field

from app.core.ai.date_context import current_date_line
from app.core.ai.tasks import extract_structured

from .schemas import ItineraryPlan


def _normalize_year(d: date, today: date) -> date:
    """把明显不合理的年份修正到离今天最近的那一年（月日保持不变）。

    为什么需要：对话里说「后天出发」，攻略文本里就会出现具体日期；
    而模型换算时若不知道今天几号，会拿自己记忆里的年份去填 ——
    实测产出的日期月日正确、年份却落后了整整一年。

    提示词里已注入当前日期，但**模型不可全信**：日期错一年的表现是
    「行程看起来像去年的」，不报错、不显眼，用户要自己发现。故在代码层兜底。

    策略：在当前年、上一年、下一年三个候选里取与今天差得最少的那个。
    因为旅行日期总是近期的（不会有人规划去年的行程，也很少规划两年后的），
    取最近年份是安全的；且月日保持不变，不会把日期改成另一个日子。
    """
    best = d
    best_gap = abs((d - today).days)
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            cand = d.replace(year=year)
        except ValueError:
            continue  # 2 月 29 日在平年会抛错，跳过该候选
        gap = abs((cand - today).days)
        if gap < best_gap:
            best, best_gap = cand, gap
    return best


def _sanitize_plan_dates(plan: ItineraryPlan) -> ItineraryPlan:
    """就地修正 daily_plans 里明显错位的日期年份。"""
    today = date.today()
    fixed = 0
    for day in plan.daily_plans or []:
        raw = (day.date or "").strip()
        if not raw:
            continue
        try:
            y, m, dd = (int(x) for x in raw[:10].split("-"))
            parsed = date(y, m, dd)
        except (ValueError, TypeError):
            # 格式不合规就置空：宁可没有日期（前端会退回「第 N 天」），
            # 也不要展示一个错误日期
            day.date = None
            continue
        norm = _normalize_year(parsed, today)
        if norm != parsed:
            day.date = norm.isoformat()
            fixed += 1
    if fixed:
        from app.shared.utils import log

        log.warning(f"[itinerary] 修正了 {fixed} 处错位年份的日期（模型换算失误）")
    return plan

# 关键：把完整输出结构写死在提示词里，防止模型不遵守 tool schema 绑定而自由发挥字段名
_EXTRACT_SYSTEM_PROMPT = """你是一个旅行攻略结构化提取器。请根据用户提供的 Markdown 攻略，提取关键信息并按 JSON 格式输出。

【输出结构】
{
  "destination": "目的地名称",
  "days": 行程总天数（整数，与 daily_plans 数量一致）,
  "budget": 预算（整数）,
  "preferences": ["偏好1", "偏好2"],
  "transport": "交通建议",
  "accommodation": {
    "time_slot": "morning 或 afternoon 或 evening",
    "kind": "hotel",
    "name": "住宿名称",
    "description": "一句话描述",
    "duration_hours": 12,
    "cost": 400,
    "note": "预订提示"
  },
  "daily_plans": [
    {
      "day_no": 1,
      "date": "日期（可选）",
      "theme": "当天主题",
      "summary": "一句话总结",
      "activities": [
        {
          "time_slot": "morning 或 afternoon 或 evening",
          "kind": "attraction",
          "name": "景点或场所名称",
          "description": "一句话描述",
          "duration_hours": 3,
          "cost": 0,
          "note": "提示（可选）"
        }
      ]
    }
  ],
  "tips": ["提醒1", "提醒2"]
}

【字段要求】
1. 只提取攻略中明确提到的信息，不要编造或补全；攻略里没有的字段直接省略（不要填 null 或空字符串）
2. accommodation 是一个 JSON 对象，必须用大括号 {} 输出，绝不能写成字符串；攻略没有明确住宿建议时，省略整个 accommodation 字段
3. 所有嵌套结构（accommodation、daily_plans 中的每个活动）都必须以真正的 JSON 对象/数组形式存在，禁止用字符串包裹
4. time_slot 只能是三个英文值之一：morning / afternoon / evening
5. kind 只能是五个英文值之一：attraction（景点/观光/购物）、restaurant（餐厅/美食）、hotel（住宿）、transport（交通）、rest（休息/自由活动）
6. 每个活动必须包含 name 字段，给一个真实合理的场所名称
7. daily_plans 的数量等于攻略中实际提到的天数，day_no 从 1 开始连续编号
8. tips 是字符串数组，每条是一句完整提醒
9. 只输出纯 JSON，不要 Markdown 代码块，不要任何多余文字

【关于 date 字段（重要）】
- 攻略里**明确写出**了日期（如「9 月 21 日」「2026-09-21」）才填 date，否则省略。
- 攻略里出现「第一天」「第二天」这类相对表述时，**不要**自行推算日期，省略该字段。
- 需要填写时，年份必须与下方给出的「当前日期」一致或在其之后 ——
  行程不会发生在过去。若攻略只给了月日，按当前日期判断应是今年还是明年。
- 绝不要使用你自己记忆中的年份，一律以上方提供的当前日期为准。
"""


async def extract_itinerary_plan(recommend_txt: str) -> ItineraryPlan | None:
    """攻略 Markdown → ItineraryPlan；失败返回 None（不打断对话）。

    提示词里注入当前日期：对话中的「后天出发」会被模型换算成具体日期，
    若不给今天，模型会拿记忆里的年份去填，产出落后一整年的日期。
    """
    prompt = (
        f"{_EXTRACT_SYSTEM_PROMPT}\n"
        f"【当前日期】今天是 {current_date_line()}。\n"
    )
    plan = await extract_structured(
        recommend_txt,
        ItineraryPlan,
        system_instructions=prompt,
    )
    # 代码层兜底：即便提示词说清了，模型仍可能填错年份
    return _sanitize_plan_dates(plan) if plan is not None else None


# 候选编号的选择结果：只让模型回一个序号，避免它复述整篇文本
class _PickChoice(BaseModel):
    """大模型在候选回复中挑选的结果。"""

    index: int = Field(description="最像旅行行程的那条候选的编号；都不像时填 -1")


_PICK_SYSTEM_PROMPT = """你是一个旅行对话的内容筛选器。

下面会给你同一段对话里的若干条 AI 回复，每条带编号。请判断**哪一条包含了一份可以
落成行程表的旅行安排**——即按天或按时段列出了要去哪、做什么的那种回复。

【判断要点】
1. 要的是「行程安排」，不是泛泛聊旅行、不是只给车次表、不是只推荐酒店
2. 若多条都像行程，选**编号最大**的那条（编号越大越新，用户要的是最新那份）
3. 若都不像行程，index 填 -1

只输出 JSON，不要解释。"""


async def pick_itinerary_reply(candidates: list[str]) -> int | None:
    """让大模型在候选回复中挑出最像行程的一条。

    何时需要它：本地打分器（selector.py）完全没有找到行程特征的回复时。
    典型场景是用户让 AI 用**散文**写行程——没有 Day 标记、没有列表，
    关键词规则看不见，但语义上确实是一份行程。

    这条路径是**兜底**，不是主路径：多数情况打分器已能定案，
    多调一次大模型只是徒增延迟与成本。

    Args:
        candidates: 候选回复文本（按时间顺序，旧 → 新）

    Returns:
        选中候选在 candidates 中的下标；判不出或失败时返回 None。
    """
    if not candidates:
        return None

    # 带上编号，并只保留末尾若干条：越新的越可能是用户想要的那份
    numbered = "\n\n".join(
        f"【候选 {i}】\n{text[:1200]}" for i, text in enumerate(candidates)
    )
    result = await extract_structured(
        numbered,
        _PickChoice,
        temperature=0.0,
        system_instructions=_PICK_SYSTEM_PROMPT,
    )
    if result is None:
        return None

    idx = result.index
    if 0 <= idx < len(candidates):
        return idx
    return None