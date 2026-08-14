from typing import Any, Optional
from .code import BusinessCode

class BaseBusinessException(Exception):
    """业务异常基类"""
    def __init__(
        self, 
        code: BusinessCode = BusinessCode.PARAM_ERROR, 
        msg: Optional[str] = None, 
        data: Any = None
    ):
        self.code = code.code if isinstance(code, BusinessCode) else code
        self.msg = msg or (code.message if isinstance(code, BusinessCode) else "未知错误")
        self.data = data
        super().__init__(self.msg)


class AuthException(BaseBusinessException):
    """认证/鉴权模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.UNAUTHORIZED, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)


class UserException(BaseBusinessException):
    """用户模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.USER_NOT_FOUND, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)


class SessionException(BaseBusinessException):
    """会话与对话记忆模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.SESSION_NOT_FOUND, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)


class AgentException(BaseBusinessException):
    """AI Agent & 大模型调度模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.AGENT_EXECUTION_ERROR, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)


class KnowledgeException(BaseBusinessException):
    """知识库与 RAG 向量检索模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.KNOWLEDGE_NOT_FOUND, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)


class ItineraryException(BaseBusinessException):
    """行程规划与方案生成模块异常"""
    def __init__(self, code: BusinessCode = BusinessCode.ITINERARY_NOT_FOUND, msg: Optional[str] = None, data: Any = None):
        super().__init__(code=code, msg=msg, data=data)