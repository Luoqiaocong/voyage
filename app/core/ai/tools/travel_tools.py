from datetime import datetime

from langchain.messages import HumanMessage
from langchain.tools import ToolRuntime, tool

from app.core.ai.agents.ticket import get_ticket_agent
from app.core.ai.agents.travel import get_travel_agent
from app.core.ai.agents.weather import get_weather_agent


@tool
async def get_today():
    """获取今天的确切日期与当前时间，用于把「相对日期」换算成具体日期。

    触发场景：对话中出现 今天/明天/后天/大后天/本周五/下周 等相对时间表达，
    或需要给行程、车票、天气查询填写具体出发日期时——请先调用本工具确认今天到底是几号，
    再进行推算，禁止凭模型自身的日期记忆猜测今天日期。

    返回：今天是 YYYY-MM-DD（星期X），当前时间 HH:MM:SS
    """
    now = datetime.now()  # noqa: DTZ005 - 面向中国用户的本地时间即可
    weekday = "一二三四五六日"[now.weekday()]
    return f"今天是 {now.strftime('%Y-%m-%d')}（星期{weekday}），当前时间 {now.strftime('%H:%M:%S')}"


@tool
async def ticket_schedule(
    origin: str,
    destination: str,
    date: str,
    requirements: str,
    runtime: ToolRuntime,
) -> str:
    """查询火车票/车次：当用户明确要查出发地与目的地之间的车票、票价、车次、时刻、坐席余票时调用。

    仅在用户明确给出（或能自然推断出）出发地、目的地、日期时使用；缺任一关键信息时请先向用户追问，不要乱猜。

    参数:
        origin: 出发地（如 北京西）
        destination: 目的地（如 西安北）
        date: 出发日期，YYYY-MM-DD
        requirements: 额外约束，如时间段、坐席、排序
    """
    origin, destination, date = origin.strip(), destination.strip(), date.strip()
    if not (origin and destination and date):
        return "ERROR: origin/destination/date 均为必填，请重新调用并补全。"

    agent = await get_ticket_agent()
    msg = f"帮我查一下 {date} 从 {origin} 到 {destination} 的车票。细化要求：{requirements}"
    response = await agent.ainvoke({"messages": [HumanMessage(content=msg)]})
    return response["messages"][-1].content


@tool
async def weather_forecast(
    date_range: str,
    destination: str,
    runtime: ToolRuntime,
) -> str:
    """查询某地某段时间的天气，并给出穿衣与户外建议：当用户明确要查目的地天气、气温、是否适合出行时调用。

    仅在用户明确给出目的地和日期范围时使用；缺信息时先补问。若用户只是闲聊或问常识性天气知识，直接回答即可，不必调用。

    参数:
        date_range: 如 "2026-08-15 到 2026-08-16"
        destination: 如 "西安"
    """
    destination = destination.strip()
    if not destination or not date_range.strip():
        return "ERROR: destination 与 date_range 均为必填。"

    agent = await get_weather_agent()
    msg = f"帮我查一下 {destination} 在 {date_range} 的天气，并给出是否适合户外的建议。"
    response = await agent.ainvoke({"messages": [HumanMessage(content=msg)]})
    return response["messages"][-1].content


@tool
async def travel_recommend(
    destination: str,
    weather_summary: str,
    ticket_summary: str,
    hotel_budget: str,
    hotel_dates: str,
    extra_requirements: str,
    mode: str = "full",
) -> str:
    """综合推荐酒店、景点、美食：当用户要「一整套行程/完整攻略/住在哪吃啥玩啥」时才调用。

    这是在已拿到天气与车次信息之后做的综合推荐。若用户只问单个信息（比如只问景点、只问吃），
    不必硬凑整套，可直接基于已有信息回答。

    参数:
        destination: 目的地
        weather_summary: 天气工具返回摘要（尽量原文）
        ticket_summary: 票务工具返回摘要（含到站时间/车站），没有可填空字符串
        hotel_budget: 如 "500元以内"，没有预算信息传空
        hotel_dates: 如 "2026-08-14 入住 2026-08-16 退房"，没有传空
        extra_requirements: 如 "陕菜、商务型、靠近西安北站"，没有传空
        mode: "full"（完整攻略：酒店+景点+美食）或 "brief"（精简要点，用户只要快速建议时用）
    """
    destination = destination.strip()
    if not destination:
        return "ERROR: destination 必填。"

    agent = await get_travel_agent()

    msg = (
        f"目的地：{destination}\n"
        f"天气情况：{weather_summary or '（未提供）'}\n"
        f"车次信息：{ticket_summary or '（未提供）'}\n"
        f"酒店预算：{hotel_budget or '（未明确）'}\n"
        f"入住日期：{hotel_dates or '（未明确）'}\n"
        f"其他要求：{extra_requirements or '（无）'}\n"
        f"输出模式：{'full' if mode == 'full' else 'brief'}\n"
    )
    if mode == "brief":
        msg += "请只输出精简要点（每个维度 1-2 条，不要长篇幅、不要完整攻略框架），突出最推荐的可执行建议。"
    else:
        msg += "请结合以上信息，推荐景点、美食和酒店。"
    response = await agent.ainvoke({"messages": [HumanMessage(content=msg)]})
    return response["messages"][-1].content
