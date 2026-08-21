from enum import Enum

"""
业务错误码定义规范：
- 20000–20400: 成功
- 10xxx–15xxx: 通用（参数、鉴权、资源、系统）
- 21xxx: 用户错误
- 30xxx: 会话与记忆模块 (Conversation & Memory)
- 40xxx: AI Agent & 大模型模块 (LLM & Agent Execution)
- 50xxx: 知识库与 RAG 模块 (Knowledge & Vector DB)
- 60xxx: 行程规划模块 (Itinerary & Travel Plan)
- 7xxx/8xxx: 暂不开放，等有新业务域再定
"""


class BusinessCode(Enum):
    """
    统一响应码枚举
    格式: (code, message)
    """

    # ========== 通用成功状态 ==========
    SUCCESS = (20000, "success")
    CREATED = (20100, "created")
    UPDATED = (20200, "updated")
    NO_CONTENT = (20400, "no content")
    

    # ========== 通用错误 (1xxxx) ==========
    PARAM_ERROR = (10001, "参数错误")
    PARAM_MISSING = (10002, "缺少必要参数")
    PARAM_INVALID = (10003, "参数格式不正确")
    FILE_TOO_LARGE = (10004, "文件大小超过限制")
    CODE_VERIFY_FAILED = (10005, "验证码验证失败")
    RATE_LIMIT_EXCEEDED = (10006, "请求过于频繁，请稍后再试")

    UNAUTHORIZED = (10101, "未授权，请先登录")
    TOKEN_EXPIRED = (10102, "登录已过期，请重新登录")
    TOKEN_INVALID = (10103, "无效的令牌")
    FORBIDDEN = (10104, "禁止访问")
    PERMISSION_DENIED = (10105, "权限不足")
    TOKEN_DECODE_FAILED = (10106, "令牌解码失败")

    NOT_FOUND = (10201, "资源不存在")
    RESOURCE_EXISTS = (10202, "资源已存在")
    CONFLICT = (10203, "操作冲突")

    INTERNAL_ERROR = (10501, "服务器内部错误")
    SERVICE_UNAVAILABLE = (10502, "服务暂时不可用")
    DATABASE_ERROR = (10503, "数据库操作失败")

    # ========== 用户模块 (21xxx) ==========
    USER_NOT_FOUND = (21001, "用户不存在")
    USER_EXIST = (21002, "用户已存在")
    USER_LOGIN_FAILED = (21003, "用户名或密码错误")
    USER_ACCOUNT_DISABLED = (21004, "账户已停用")
    USER_REGISTER_FAILED = (21005, "注册失败，请稍后重试")
    USER_PWD_AUTH_FAILED = (21007, "密码验证失败")
    USER_PWD_WEAK = (21010, "密码强度不足")
    USER_PWD_SAME = (21011, "新密码不能与当前密码相同")
    USER_AVATAR_INVALID = (21012, "头像暂且不支持")

    # ========== 会话与记忆模块 (3xxxx) ==========
    CONVERSATION_NOT_FOUND = (30001, "会话不存在或已过期")
    CONVERSATION_CREATE_FAILED = (30002, "创建会话失败")
    CONVERSATION_UPDATE_FAILED = (30003, "更新会话状态失败")
    CONVERSATION_DELETE_FAILED = (30004, "删除会话失败")
    CONVERSATION_PERMISSION_DENIED = (30005, "无权访问此会话")
    MEMORY_READ_FAILED = (30006, "读取对话短期记忆失败")
    MEMORY_CLEAR_FAILED = (30007, "清空会话记忆失败")

    # ========== AI Agent & 大模型模块 (4xxxx) ==========
    LLM_CALL_FAILED = (40001, "模型服务响应失败，请稍后再试")
    LLM_STREAM_ERROR = (40002, "流式响应生成中断")
    LLM_CONTEXT_EXCEEDED = (40003, "对话上下文长度超出限制")
    AGENT_EXECUTION_ERROR = (40004, "Agent 任务执行异常")
    AGENT_TOOL_CALL_FAILED = (40005, "Agent 工具调用失败")
    AGENT_TIMEOUT = (40006, "Agent 思考分析超时")
    SEMANTIC_CACHE_ERROR = (40007, "语义缓存检索异常")

    # ========== 知识库与 RAG 模块 (5xxxx) ==========
    KNOWLEDGE_NOT_FOUND = (50001, "知识库文档不存在")
    KNOWLEDGE_INDEX_FAILED = (50002, "构建向量索引失败")
    VECTOR_SEARCH_FAILED = (50003, "语义向量检索失败")
    DOC_PARSING_FAILED = (50004, "文档解析处理失败")

    # ========== 行程规划模块 (6xxxx) ==========
    ITINERARY_NOT_FOUND = (60001, "行程规划记录不存在")
    ITINERARY_GEN_FAILED = (60002, "行程方案生成失败")
    ITINERARY_UPDATE_FAILED = (60003, "行程修改保存失败")
    ITINERARY_SHARE_EXPIRED = (60004, "行程分享链接已失效")

    @property
    def code(self) -> int:
        """获取错误码"""
        return self.value[0]

    @property
    def message(self) -> str:
        """获取错误信息"""
        return self.value[1]


def get_response_info(res_code: BusinessCode):
    """便捷获取码和信息的工具函数"""
    return res_code.code, res_code.message
