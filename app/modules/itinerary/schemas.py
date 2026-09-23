from datetime import datetime
from typing import Annotated, Literal, Optional
import json
import re

from pydantic import BaseModel, BeforeValidator, Field, field_serializer, model_validator

from app.shared.utils import to_local_display


# ---------------------------------------------------------------------------
# 类型容错
#
# 工具调用（function_calling）模式下，模型只是「参考」JSON schema，并不强制类型。
# 实测 glm-4.5-air 会稳定地给出不合 schema 的输出，例如：
#   - cost: 44.5（schema 是 int，Pydantic 默认拒绝带小数的 float）
#   - tips: "一整段话"（schema 是 list[str]）
#   - accommodation: "{\"time_slot\": ...}"（嵌套对象被序列化成字符串）
# 任何一条都会让整份行程校验失败并触发重试，既慢又可能仍失败（用户侧表现为超时）。
# 这里在字段级做「尽力还原」，把模型的小偏差吸收掉，而不是靠重试赌下一次输出。
# ---------------------------------------------------------------------------
def _to_int(value):
    """把 float / 数字字符串 / 带单位文本（如「150元」）还原为 int。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return int(round(float(match.group())))
    return value


def _to_float(value):
    """把数字字符串 / 带单位文本还原为 float。"""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group())
    return value


def _to_str_list(value):
    """把字符串按换行/分号拆成列表；已是列表则逐项转字符串。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parts = [p.strip() for p in re.split(r"[\n；;]+", text) if p.strip()]
        return parts or [text]
    if isinstance(value, (list, tuple)):
        return [v if isinstance(v, str) else str(v) for v in value]
    return [str(value)]


# 复用别名，避免在字段上到处写 Annotated[...]
CoercedInt = Annotated[int, BeforeValidator(_to_int)]
CoercedFloat = Annotated[float, BeforeValidator(_to_float)]
StrList = Annotated[list[str], BeforeValidator(_to_str_list)]


def _maybe_parse_json(value):
    """模型偶尔会把嵌套对象/数组序列化成 JSON 字符串再放进工具参数。

    Pydantic 不会自动把字符串还原成对象，于是整个提取因一条嵌套字段而校验失败、
    转走更慢且更不稳的回退路径。这里只做「能解析成 dict/list 就还原」的兼容处理：
    解析失败或本来就是对象时原样返回，不改变任何合法输入的语义。
    """
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return value
    return parsed if isinstance(parsed, (dict, list)) else value


def _coerce_stringified_nested(data):
    """把 ItineraryPlan 里被字符串化的嵌套字段还原为对象/数组。"""
    if not isinstance(data, dict):
        return data
    data = dict(data)

    if "accommodation" in data:
        data["accommodation"] = _maybe_parse_json(data["accommodation"])

    daily = data.get("daily_plans")
    if isinstance(daily, list):
        for day in daily:
            if not isinstance(day, dict):
                continue
            acts = day.get("activities")
            if isinstance(acts, str):
                day["activities"] = _maybe_parse_json(acts)
            elif isinstance(acts, list):
                day["activities"] = [_maybe_parse_json(a) for a in acts]

    return data


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

    duration_hours: CoercedFloat = Field(
        default=2.0,
        description="预计停留时长（小时）。景点一般 2-4 小时，餐厅 1-2 小时。攻略中没提则使用默认值 2.0。"
    )

    cost: CoercedInt = Field(
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

    day_no: CoercedInt = Field(
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

    @model_validator(mode="before")
    @classmethod
    def _restore_stringified_activities(cls, data):
        """单独校验某一天时，也把被字符串化的 activities 还原为数组。"""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        acts = data.get("activities")
        if isinstance(acts, str):
            data["activities"] = _maybe_parse_json(acts)
        elif isinstance(acts, list):
            data["activities"] = [_maybe_parse_json(a) for a in acts]
        return data


# ============================================================
# 层级 3：完整行程（LLM 输出用）
# ============================================================
class ItineraryPlan(BaseModel):
    """一整套旅行行程（结构化输出，供保存/编辑/渲染使用）。"""

    destination: str = Field(
        description="目的地城市或地区，使用正式名称。示例：「北京」「杭州」。从攻略中提取，不要编造。"
    )

    days: CoercedInt = Field(
        description="行程总天数。必须等于 daily_plans 列表的长度。"
    )

    budget: Optional[CoercedInt] = Field(
        default=None,
        description="总预算（元）。仅当攻略中明确提到时填写。"
    )

    preferences: StrList = Field(
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

    tips: StrList = Field(
        default_factory=list,
        description="出行提醒，3-5 条。每条是一句完整的句子，末尾加句号。"
    )

    @model_validator(mode="before")
    @classmethod
    def _restore_stringified_nested(cls, data):
        """校验前先把被字符串化的 accommodation / activities 还原成对象。

        见 _coerce_stringified_nested 的说明：这是应对模型工具调用输出的兼容层。
        """
        return _coerce_stringified_nested(data)

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


class ExtractItineraryRequest(BaseModel):
    """从会话提取行程。

    overwrite=true 时覆盖该会话最近一份行程；false 则始终另存。
    """

    overwrite: bool = Field(default=False, description="是否覆盖该会话已有行程")


class ItineraryDetailResponse(BaseModel):
    """行程详情响应。"""

    id: Annotated[int, Field(description="行程 ID")]
    conversation_id: Annotated[str | None, Field(description="来源会话ID，会话删除后为空")]
    plan: Annotated[ItineraryPlan, Field(description="行程计划")]
    created_at: Annotated[datetime, Field(description="创建时间（UTC）")]
    updated_at: Annotated[datetime, Field(description="更新时间（UTC）")]

    # 返回时统一转为上海时区展示（与会话模块一致）
    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_local_display(value)

    model_config = {"from_attributes": True}  # 允许反序列化，即orm转pydantic


class ItinerariesResponse(BaseModel):
    """行程列表响应（分页）。"""

    itineraries: list[ItineraryDetailResponse]
    total: Annotated[int, Field(description="符合条件的总条数")] = 0
    page: Annotated[int, Field(description="当前页，从 1 开始")] = 1
    page_size: Annotated[int, Field(description="每页条数")] = 12


class ItineraryMaybeResponse(BaseModel):
    """某会话最近一份行程；没有则为 null。"""

    itinerary: ItineraryDetailResponse | None = None