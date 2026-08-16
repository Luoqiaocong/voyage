from datetime import datetime

from langchain.messages import HumanMessage
from langchain.tools import ToolRuntime, tool

from app.core.ai.agents.ticket import get_ticket_agent
from app.core.ai.agents.travel import get_travel_agent
from app.core.ai.agents.weather import get_weather_agent


@tool
async def get_weather(location:str):
    """
    获取某地天气
    args:
        location: 位置
    """
    return f"The weather in {location} is sunny"

@tool
async def get_location():
    """
    获取当前位置
    args:
        None
    """
    return "中国北京"

@tool
async def get_today():
    "获取当前日期与时间，格式为 YYYY-MM-DD"
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
async def ticket_schedule(
    origin: str,
    destination: str,
    date: str,
    requirements: str,
    runtime: ToolRuntime,
) -> str:
    """查询火车票。

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
    """查询目的地天气，并给出穿衣与户外建议。

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
    runtime: ToolRuntime,
) -> str:
    """根据天气与车次信息推荐景点、美食、酒店。

    参数:
        destination: 目的地
        weather_summary: 天气工具返回摘要（尽量原文）
        ticket_summary: 票务工具返回摘要（含到站时间/车站）
        hotel_budget: 如 "500元以内"
        hotel_dates: 如 "2026-08-14 入住 2026-08-16 退房"
        extra_requirements: 如 "陕菜、商务型、靠近西安北站"
    """
    destination = destination.strip()
    if not destination:
        return "ERROR: destination 必填。"

    agent = await get_travel_agent()

    msg = (
        f"目的地：{destination}\n"
        f"天气情况：{weather_summary}\n"
        f"车次信息：{ticket_summary}\n"
        f"酒店预算：{hotel_budget}\n"
        f"入住日期：{hotel_dates}\n"
        f"其他要求：{extra_requirements}\n"
        "请结合以上信息，推荐景点、美食和酒店。"
    )
    response = await agent.ainvoke({"messages": [HumanMessage(content=msg)]})
    return response["messages"][-1].content
