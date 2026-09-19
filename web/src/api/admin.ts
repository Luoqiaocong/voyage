/**
 * 管理端接口。
 *
 * 全部需要管理员身份：后端在 /admin 路由上统一挂了 get_current_admin，
 * 非管理员会返回业务码 10105（权限不足）。
 */
import http, { downloadFile } from './http'

// ==================== 看板 ====================
export interface CostEstimate {
  estimated_usd: number
  currency: string
  unpriced_models: string[]
}

export interface DashboardSummary {
  today: string
  today_tokens: number
  today_calls: number
  new_users_today: number
  active_users_today: number
  total_users: number
  total_conversations: number
  total_itineraries: number
  today_cost: CostEstimate
}

export interface TrendPoint {
  date: string
  total_tokens: number
  calls: number
}

export interface UserGrowthPoint {
  date: string
  new_users: number
}

export interface DashboardTrend {
  days: number
  users: UserGrowthPoint[]
  tokens: TrendPoint[]
}

export interface ModelUsageItem {
  model: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  calls: number
  /** 占比，由后端计算（0-1） */
  share?: number
}

export interface ModelBreakdown {
  scope: string
  breakdown: ModelUsageItem[]
  cost: CostEstimate
}

export interface HealthReport {
  redis_ok: boolean
  redis_detail: string
  database_ok: boolean
  database_detail: string
  llm_channel_configured: boolean
  llm_model: string
  llm_detail: string
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return (await http.get('/admin/dashboard/summary')) as unknown as DashboardSummary
}

export async function getDashboardTrend(days = 7): Promise<DashboardTrend> {
  return (await http.get('/admin/dashboard/trend', {
    params: { days }
  })) as unknown as DashboardTrend
}

export async function getDashboardModels(day?: string): Promise<ModelBreakdown> {
  return (await http.get('/admin/dashboard/models', {
    params: day ? { day } : {}
  })) as unknown as ModelBreakdown
}

export async function getDashboardHealth(): Promise<HealthReport> {
  return (await http.get('/admin/dashboard/health')) as unknown as HealthReport
}

// ==================== 指标（可观测性）====================
export interface ToolMetric {
  calls?: number
  cache_hit?: number
  cache_miss?: number
  errors?: number
  cache_hit_rate?: number
  error_rate?: number
  p50?: string | null
  p95?: string | null
  avg_ms?: number
}

export interface MetricsSnapshot {
  date: string
  available: boolean
  tools: Record<string, ToolMetric>
  extraction: {
    total: number
    ok: number
    fail: number
    pass_rate: number
    via_tool_call: number
    via_fallback: number
    tool_call_ratio: number
  }
  chat: {
    total: number
    errors: number
    error_rate: number
    p50?: string | null
    p95?: string | null
    avg_ms?: number
  }
  cache: { total: number; hit: number; hit_rate: number }
  counters: Record<string, number>
}

export interface MetricsTrendPoint {
  date: string
  tool_calls: number
  cache_hit_rate: number
  extract_pass_rate: number
  chat_total: number
  chat_error_rate: number
}

export async function getMetrics(day?: string): Promise<MetricsSnapshot> {
  return (await http.get('/admin/metrics', {
    params: day ? { day } : {}
  })) as unknown as MetricsSnapshot
}

export async function getMetricsTrend(days = 7): Promise<{ days: number; trend: MetricsTrendPoint[] }> {
  return (await http.get('/admin/metrics/trend', { params: { days } })) as unknown as {
    days: number
    trend: MetricsTrendPoint[]
  }
}

// ==================== 用户管理 ====================
/** 三档角色。super_admin 可读写；admin 只读；user 无后台权限。 */
export type AdminRole = 'user' | 'admin' | 'super_admin'

export interface AdminUserItem {
  id: number
  email: string
  username: string | null
  avatar: string | null
  role: AdminRole
  is_active: boolean
  created_at: string
}

export interface AdminUserDetail extends AdminUserItem {
  conversation_count: number
  itinerary_count: number
}

export interface AdminUserPage {
  total: number
  page: number
  page_size: number
  /** 当前查看者是否有写权限（后端下发的权威判断，前端不自行推断） */
  can_write?: boolean
  items: AdminUserItem[]
}

/** 当前管理员自身的身份与权限（GET /admin/me） */
export interface AdminMe {
  id: number
  email: string
  username: string | null
  role: AdminRole
  can_write: boolean
}

export async function getAdminMe(): Promise<AdminMe> {
  return (await http.get('/admin/me')) as unknown as AdminMe
}

export interface ListUsersParams {
  page?: number
  page_size?: number
  keyword?: string
  role?: AdminRole | ''
  is_active?: boolean | null
}

export async function listUsers(params: ListUsersParams = {}): Promise<AdminUserPage> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20
  }
  if (params.keyword) query.keyword = params.keyword
  if (params.role) query.role = params.role
  // 注意：false 也要发出去，不能用真值判断，否则「筛选已禁用」会失效
  if (params.is_active !== undefined && params.is_active !== null) {
    query.is_active = params.is_active
  }
  return (await http.get('/admin/users', { params: query })) as unknown as AdminUserPage
}

export async function getUserDetail(userId: number): Promise<AdminUserDetail> {
  return (await http.get(`/admin/users/${userId}`)) as unknown as AdminUserDetail
}

export interface ChangeResult {
  id: number
  changed: boolean
  role?: string
  is_active?: boolean
}

export async function updateUserRole(userId: number, role: AdminRole): Promise<ChangeResult> {
  return (await http.patch(`/admin/users/${userId}/role`, { role })) as unknown as ChangeResult
}

export async function updateUserStatus(userId: number, isActive: boolean): Promise<ChangeResult> {
  return (await http.patch(`/admin/users/${userId}/status`, {
    is_active: isActive
  })) as unknown as ChangeResult
}

// ==================== 会话洞察 ====================
export interface ConversationStats {
  total_conversations: number
  total_messages: number
  /** 平均每会话消息数，后端已**向下取整**（不显示小数） */
  avg_messages_per_conversation: number
  /**
   * 活跃用户排行。
   *
   * 后端多返回一些候选（见 repo.ACTIVE_USER_POOL），前端按不同口径
   * 本地重排后取前 10 —— 切换排序时不需要重新请求。
   */
  top_active_users: {
    user_id: number
    email: string
    conversations: number
    /** 当日（本地时区）产生的消息数 */
    today_messages: number
  }[]
  /**
   * Token 用量排行（按用户，累计）。
   *
   * 数据来自 user_token_usage 表 —— 它从引入时开始累积。
   * 更早的用量没有用户维度（原先只按「模型 × 日期」聚合），
   * 无法拆分到用户，故不出现在这里。
   */
  top_token_users: {
    user_id: number
    email: string
    tokens: number
    calls: number
  }[]
}

/**
 * 会话元数据项。
 *
 * 刻意**不含 title**：会话标题由 LLM 从用户消息生成，属于用户内容。
 * 管理端只做规模统计，不需要、也不应该看到它。
 */
export interface AdminConversationItem {
  id: string
  user_id: number
  user_email: string
  message_count: number
  created_at: string
}

export interface AdminConversationPage {
  total: number
  page: number
  page_size: number
  items: AdminConversationItem[]
}

export async function getConversationStats(): Promise<ConversationStats> {
  return (await http.get('/admin/conversations/stats')) as unknown as ConversationStats
}

/**
 * 拉取会话元数据列表。
 *
 * 没有 keyword 参数：后端已移除「按标题模糊搜索」——
 * 那等于允许对全站用户的对话标题做关键词检索，属隐私越界。
 *
 * sort 只有两个与规模统计相关的维度（后端用 pattern 限制取值）：
 *   created_desc  最新创建在前
 *   messages_desc 消息数从多到少
 */
export async function listConversations(params: {
  page?: number
  page_size?: number
  user_id?: number
  sort?: 'created_desc' | 'messages_desc'
} = {}): Promise<AdminConversationPage> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20
  }
  if (params.user_id) query.user_id = params.user_id
  if (params.sort) query.sort = params.sort
  return (await http.get('/admin/conversations', { params: query })) as unknown as AdminConversationPage
}

// ==================== 审计日志 ====================
export interface AuditLogItem {
  id: number
  operator_id: number
  operator_email: string
  action: string
  target_type: string
  target_id: string
  detail: string | null
  ip: string | null
  created_at: string
}

export interface AuditLogPage {
  total: number
  page: number
  page_size: number
  items: AuditLogItem[]
}

export async function listAuditLogs(params: {
  page?: number
  page_size?: number
  action?: string
  operator_id?: number
  target_id?: string
} = {}): Promise<AuditLogPage> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20
  }
  if (params.action) query.action = params.action
  if (params.operator_id) query.operator_id = params.operator_id
  if (params.target_id) query.target_id = params.target_id
  return (await http.get('/admin/audit-logs', { params: query })) as unknown as AuditLogPage
}

// ==================== 导出 ====================
export async function exportUsersCsv(): Promise<void> {
  await downloadFile('/admin/export/users.csv', 'users.csv')
}

export async function exportTokenUsageCsv(): Promise<void> {
  await downloadFile('/admin/export/token-usage.csv', 'token-usage.csv')
}

/** 审计动作标识 → 中文说明（后端写入的是固定字符串，前端统一翻译） */
export const AUDIT_ACTION_LABEL: Record<string, string> = {
  'user.role.update': '修改用户角色',
  'user.status.update': '启用/禁用用户'
}
