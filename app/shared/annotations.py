"""共享 FastAPI 类型注解（Annotated 别名）：跨模块复用，避免重复定义。"""
from typing import Annotated

from pydantic import Field

# 对话 ID：12 位字母数字
ConversationId = Annotated[
    str,
    Field(pattern=r"^[a-zA-Z0-9]{12}$", description="对话 ID"),
]

ItineraryId = Annotated[
    int,
    Field(gt=0, description="行程 ID"),
]