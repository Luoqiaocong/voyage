from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ============================================================
# 层级 1：活动
# ============================================================
class ItineraryActivity(BaseModel):
    """行程中的一个活动安排（一个地点/事件）。"""

    time_slot: Literal["morning", "afternoon", "evening"] = Field(
        description="活动时段。morning=上午（约 8:00-12:00），afternoon=下午（约 13:00-17:00），evening=晚上（约 18:00-22:00）。根据攻略中的时间描述推断。"
    )

    kind: Literal["attraction", "restaurant", "hotel", "transport", "rest"] = Field(
        description="活动类型。attraction=景点/博物馆/公园，restaurant=餐厅/小吃店，hotel=住宿/酒店，transport=交通/换乘，rest=休息/自由活动/未安排。"
    )

    name: str = Field(
        description="地点或场所名称，使用正式全称。示例：「故宫博物院」「全聚德（前门店）」。必须从攻略中提取，不要编造。"
    )

    description: str = Field(
        description="一句话说明为什么安排这里。包含：亮点 + 注意点（如有）。长度控制在 20-40 字。"
    )

    duration_hours: float = Field(
        default=2.0,
        description="预计停留时长（小时）。景点一般 2-4 小时，餐厅 1-2 小时。攻略中没提则使用默认值 2.0。"
    )

    cost: int = Field(
        default=0,
        description="预估单人花费（元）。没提到则填 0（表示未知或免费）。"
    )

    note: Optional[str] = Field(
        default=None,
        description="预订/防坑提示。没有特别提醒的则省略。"
    )


# ============================================================
# 层级 2：一天
# ============================================================
class ItineraryDay(BaseModel):
    """一天的具体安排。"""

    day_no: int = Field(
        description="第几天，从 1 开始编号。"
    )

    date: Optional[str] = Field(
        default=None,
        description="具体日期，格式 YYYY-MM-DD。仅当攻略中明确提到日期时才填写。"
    )

    theme: str = Field(
        description="当天行程主题，用 4-8 个字概括。格式：「区域 + 主题」，如「故宫-王府井文化一日」。"
    )

    activities: list[ItineraryActivity] = Field(
        description="当天的活动列表，按时间先后排序。建议 3-5 项。"
    )

    summary: str = Field(
        description="当天行程一句话总结，用 20-40 字概述。包含：今日核心亮点 + 节奏感。"
    )


# ============================================================
# 层级 3：完整行程（LLM 输出用）
# ============================================================
class ItineraryPlan(BaseModel):
    """一整套旅行行程（结构化输出，供保存/编辑/渲染使用）。"""

    destination: str = Field(
        description="目的地城市或地区，使用正式名称。示例：「北京」「杭州」。从攻略中提取，不要编造。"
    )

    days: int = Field(
        description="行程总天数。必须等于 daily_plans 列表的长度。"
    )

    budget: Optional[int] = Field(
        default=None,
        description="总预算（元）。仅当攻略中明确提到时填写。"
    )

    preferences: list[str] = Field(
        default_factory=list,
        description="旅行偏好标签，如：美食、亲子、穷游、摄影、历史文化、自然风光、购物、休闲、探险。"
    )

    transport: Optional[str] = Field(
        default=None,
        description="往返交通建议。格式：出发地→目的地 交通工具+班次 出发时间-到达时间。"
    )

    accommodation: Optional[ItineraryActivity] = Field(
        default=None,
        description="全程住宿安排，kind 固定为 hotel。入住/退房日期写在 note 中。"
    )

    daily_plans: list[ItineraryDay] = Field(
        description="每天的详细安排，按 day_no 从小到大排列。长度必须等于 days。"
    )

    tips: list[str] = Field(
        default_factory=list,
        description="出行提醒，3-5 条。每条是一句完整的句子，末尾加句号。"
    )

    @model_validator(mode="after")
    def check_days_consistency(self) -> "ItineraryPlan":
        """保证总天数与每日安排数量一致，避免生成/传参时出现结构性脏数据。"""
        if self.days != len(self.daily_plans):
            raise ValueError(
                f"days 必须与 daily_plans 数量一致：days={self.days}，实际安排了 {len(self.daily_plans)} 天"
            )
        return self


# ============================================================
# API 请求/响应
# ============================================================
class UpdateItineraryRequest(ItineraryPlan):
    """创建/更新行程的 API 请求体（结构同 ItineraryPlan，含 days 一致性校验）。"""


class ItineraryPatch(BaseModel):
    """更新行程的局部请求体：仅允许修改独立字段，派生字段不可在此变更。

    - 未传的字段保持不变；显式传 null 视为「不修改该字段」
    - 清空列表请传空数组 []（如 {"tips": []}）
    """

    budget: Optional[int] = Field(default=None, description="总预算（元）")
    preferences: Optional[list[str]] = Field(default=None, description="旅行偏好标签")
    transport: Optional[str] = Field(default=None, description="往返交通建议")
    tips: Optional[list[str]] = Field(default=None, description="出行提醒")
    accommodation: Optional[ItineraryActivity] = Field(default=None, description="住宿安排（整体替换）")
    
    model_config = {"extra": "forbid"}  # 禁用额外字段


class ItineraryDetailResponse(BaseModel):
    """行程详情响应。"""

    id: Annotated[int, Field(description="行程 ID")]
    conversation_id: Annotated[str, Field(description="对话 ID")]
    plan: Annotated[ItineraryPlan, Field(description="行程计划")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]

    model_config = {"from_attributes": True}  # 允许反序列化，即orm转pydantic
    
    
class ItinerariesResponse(BaseModel):
    """行程列表响应。"""
    itineraries: list[ItineraryDetailResponse]