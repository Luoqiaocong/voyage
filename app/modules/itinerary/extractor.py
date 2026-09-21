"""行程专属结构化提取：把对话攻略 Markdown → ItineraryPlan。

依赖方向：modules → core（行程域提供 schema 与专属提示词，调用 core 的通用提取器）。
"""
from datetime import date

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
_EXTRACT_SYSTEM_PROMPT = """你是一个旅行行程总结器。下面会给出一段用户与助手的对话记录（每段标注了说话人）。请把对话中关于这次旅行的信息**总结**成一份结构化行程，并按 JSON 格式输出。

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
1. 只总结对话中明确提到的信息，不要编造或补全；对话里没有的字段直接省略（不要填 null 或空字符串）
2. 目的地、天数、预算、出行偏好常出现在**用户**说的话里（如「想去杭州 3 天，预算 3000」），景点、餐厅、住宿、交通常出现在**助手**的回复里，需要综合对话两侧的信息来总结
3. 若对话里先后出现过不同方案，以**最新**的一套为准
4. accommodation 是一个 JSON 对象，必须用大括号 {} 输出，绝不能写成字符串；对话没有明确住宿建议时，省略整个 accommodation 字段
5. 所有嵌套结构（accommodation、daily_plans 中的每个活动）都必须以真正的 JSON 对象/数组形式存在，禁止用字符串包裹
6. time_slot 只能是三个英文值之一：morning / afternoon / evening
7. kind 只能是五个英文值之一：attraction（景点/观光/购物）、restaurant（餐厅/美食）、hotel（住宿）、transport（交通）、rest（休息/自由活动）
8. 每个活动必须包含 name 字段，给一个真实合理的场所名称
9. daily_plans 的数量等于对话里提到的行程天数，day_no 从 1 开始连续编号
10. tips 是字符串数组，每条是一句完整提醒
11. 只输出纯 JSON，不要 Markdown 代码块，不要任何多余文字

【关于 date 字段（重要）】
- 对话里**明确写出**了日期（如「9 月 21 日」「2026-09-21」）才填 date，否则省略。
- 对话里出现「第一天」「第二天」这类相对表述时，**不要**自行推算日期，省略该字段。
- 需要填写时，年份必须与下方给出的「当前日期」一致或在其之后 ——
  行程不会发生在过去。若只给了月日，按当前日期判断应是今年还是明年。
- 绝不要使用你自己记忆中的年份，一律以上方提供的当前日期为准。
"""


async def extract_itinerary_plan(conversation_txt: str) -> ItineraryPlan | None:
    """会话转录 → ItineraryPlan；失败返回 None（不打断对话）。

    输入是「用户/助手」标注的整段会话历史，由模型总结出结构化行程。
    提示词里注入当前日期：对话中的「后天出发」会被模型换算成具体日期，
    若不给今天，模型会拿记忆里的年份去填，产出落后一整年的日期。
    """
    prompt = (
        f"{_EXTRACT_SYSTEM_PROMPT}\n"
        f"【当前日期】今天是 {current_date_line()}。\n"
    )
    plan = await extract_structured(
        conversation_txt,
        ItineraryPlan,
        system_instructions=prompt,
    )
    # 代码层兜底：即便提示词说清了，模型仍可能填错年份
    return _sanitize_plan_dates(plan) if plan is not None else None