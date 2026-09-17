"""管理端请求/响应模型。"""
from typing import Annotated, Any

from pydantic import BaseModel, Field


class AdminUserItem(BaseModel):
    """用户列表项。"""

    id: Annotated[int, Field(description="用户ID（管理端为便于排障直接返回真实 ID）")]
    email: Annotated[str, Field(description="邮箱")]
    username: Annotated[str | None, Field(description="昵称")] = None
    avatar: Annotated[str | None, Field(description="头像文件名")] = None
    role: Annotated[str, Field(description="角色：user / admin")]
    is_active: Annotated[bool, Field(description="账号是否启用")]
    created_at: Annotated[Any, Field(description="注册时间（UTC）")]

    model_config = {"from_attributes": True}


class AdminUserDetail(AdminUserItem):
    """用户详情：附带使用量统计。"""

    conversation_count: Annotated[int, Field(description="会话数")] = 0
    itinerary_count: Annotated[int, Field(description="行程数")] = 0


class AdminUserPage(BaseModel):
    """用户分页结果。"""

    total: Annotated[int, Field(description="符合条件的总数")]
    page: Annotated[int, Field(description="当前页码，从 1 开始")]
    page_size: Annotated[int, Field(description="每页条数")]
    items: Annotated[list[AdminUserItem], Field(description="当前页数据")]


class RoleUpdateRequest(BaseModel):
    """修改用户角色。"""

    role: Annotated[str, Field(description="目标角色：user / admin")]


class StatusUpdateRequest(BaseModel):
    """修改用户启用状态。"""

    is_active: Annotated[bool, Field(description="true=启用，false=禁用")]


class ModelUsageItem(BaseModel):
    """单模型用量。"""

    model: Annotated[str, Field(description="模型 ID")]
    input_tokens: Annotated[int, Field(description="输入 token")]
    output_tokens: Annotated[int, Field(description="输出 token")]
    total_tokens: Annotated[int, Field(description="总 token")]
    calls: Annotated[int, Field(description="调用次数")]


class CostEstimate(BaseModel):
    """成本估算结果。"""

    estimated_usd: Annotated[float, Field(description="估算费用（美元）")]
    currency: Annotated[str, Field(description="币种")] = "USD"
    unpriced_models: Annotated[list[str], Field(description="未配置单价、未计入金额的模型")] = []


class DashboardSummary(BaseModel):
    """看板概览。"""

    today: Annotated[str, Field(description="统计日期（本地时区）")]
    today_tokens: Annotated[int, Field(description="今日消耗 token 总数")]
    today_calls: Annotated[int, Field(description="今日 LLM 调用次数")]
    new_users_today: Annotated[int, Field(description="今日新增用户")]
    active_users_today: Annotated[int, Field(description="今日活跃用户（产生过会话）")]
    total_users: Annotated[int, Field(description="累计用户")]
    total_conversations: Annotated[int, Field(description="累计会话")]
    total_itineraries: Annotated[int, Field(description="累计行程")]
    today_cost: Annotated[CostEstimate, Field(description="今日成本估算")]


class HealthReport(BaseModel):
    """系统健康报告。"""

    redis_ok: Annotated[bool, Field(description="Redis 是否可用")]
    redis_detail: Annotated[str, Field(description="Redis 版本或错误信息")]
    database_ok: Annotated[bool, Field(description="数据库是否可用")]
    database_detail: Annotated[str, Field(description="数据库信息或错误信息")]
    llm_channel_configured: Annotated[bool, Field(description="LLM 通道配置是否完整")]
    llm_model: Annotated[str, Field(description="当前使用的模型")]
    llm_detail: Annotated[str, Field(description="通道说明（不实际发起调用以免消耗额度）")]


class AuditLogItem(BaseModel):
    """审计日志项。"""

    id: Annotated[int, Field(description="主键")]
    operator_id: Annotated[int, Field(description="操作者用户ID")]
    operator_email: Annotated[str, Field(description="操作者邮箱")]
    action: Annotated[str, Field(description="动作标识")]
    target_type: Annotated[str, Field(description="目标类型")]
    target_id: Annotated[str, Field(description="目标标识")]
    detail: Annotated[str | None, Field(description="变更明细（JSON）")] = None
    ip: Annotated[str | None, Field(description="来源 IP")] = None
    created_at: Annotated[Any, Field(description="操作时间（UTC）")]

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    """审计日志分页结果。"""

    total: Annotated[int, Field(description="总数")]
    page: Annotated[int, Field(description="当前页码")]
    page_size: Annotated[int, Field(description="每页条数")]
    items: Annotated[list[AuditLogItem], Field(description="当前页数据")]


class ConversationStats(BaseModel):
    """会话洞察（仅聚合数据，不含任何用户内容）。"""

    total_conversations: Annotated[int, Field(description="会话总数")]
    total_messages: Annotated[int, Field(description="消息总数（会话消息数之和）")]
    avg_messages_per_conversation: Annotated[float, Field(description="平均每会话消息数")]
    top_active_users: Annotated[list[dict], Field(description="会话数最多的用户")]
