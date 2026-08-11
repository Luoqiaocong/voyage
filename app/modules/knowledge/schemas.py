from pydantic import BaseModel


class KnowledgeQueryRequest(BaseModel):
    query: str
    top_k: int = 10


class KnowledgeQueryResponse(BaseModel):
    answer: str
    sources: list[str]