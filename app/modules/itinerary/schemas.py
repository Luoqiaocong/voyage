from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---------- 层级 1：单个活动项 ----------
class ItineraryActivity(BaseModel):
    """行程中的一个活动安排（一个地点/事件）。"""
    time_slot: Literal["morning", "afternoon", "evening"] = Field(
        description="活动时段：morning=上午, afternoon=下午, evening=晚上"
    )
    kind: Literal["attraction", "restaurant", "hotel", "transport", "rest"] = Field(
        description="活动类型：attraction=景点, restaurant=餐厅, hotel=住宿, transport=交通, rest=休息/自由活动"
    )
    name: str = Field(description="地点或场所名称，如「故宫博物院」「全聚德前门店」")
    description: str = Field(description="为什么安排这里：一句话亮点或注意点（30字内）")
    duration_hours: float = Field(default=2, description="预计停留时长（小时）")
    cost: int = Field(default=0, description="预估单人花费（元），0 表示免费或未知")
    note: str | None = Field(default=None, description="预订/防坑提示，如「提前7天预约」；没有则省略")


# ---------- 层级 2：一天 ----------
class ItineraryDay(BaseModel):
    """一天的具体安排。"""
    day_no: int = Field(description="第几天，从 1 开始")
    date: str | None = Field(default=None, description="日期 YYYY-MM-DD；用户未给具体日期时省略")
    theme: str = Field(description="当天主题，如「故宫-王府井文化一日」")
    activities: list[ItineraryActivity] = Field(
        description="当天活动，按时间先后排序，3-5 项为宜"
    )
    summary: str = Field(description="当天行程一句话总结（给用户快速浏览）")


# ---------- 层级 3：完整行程 ----------
class ItineraryPlan(BaseModel):
    """一整套旅行行程（结构化输出，供保存/编辑/渲染使用）。"""
    destination: str = Field(description="目的地城市，如「北京」")
    days: int = Field(description="行程总天数，与 daily_plans 长度一致")
    budget: int | None = Field(default=None, description="总预算（元），用户未明确时省略")
    preferences: list[str] = Field(default_factory=list, description="旅行偏好标签，如「美食」「亲子」「穷游」")
    transport: str | None = Field(default=None, description="往返交通建议，如「北京西→西安北 G659 08:30-12:05」")
    accommodation: ItineraryActivity | None = Field(
        default=None, description="全程住宿安排（kind 为 hotel），入住/退房日期写进 note"
    )
    daily_plans: list[ItineraryDay] = Field(description="每天的安排，长度必须等于 days")
    tips: list[str] = Field(default_factory=list, description="出行提醒（3-5条），如「热门景点务必提前7天预约」")


    