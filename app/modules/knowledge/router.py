from fastapi import APIRouter
from app.modules.knowledge.service import knowledge_service
from app.modules.knowledge.schemas import KnowledgeQueryRequest, KnowledgeQueryResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(req: KnowledgeQueryRequest):
    answer, sources = await knowledge_service.retrieve(req.query, req.top_k)
    return KnowledgeQueryResponse(answer=answer, sources=sources)


@router.post("/upload")
async def upload_document():
    # TODO: implement document upload and parsing
    return {"status": "not implemented"}