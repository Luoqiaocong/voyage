class KnowledgeService:
    async def retrieve(self, query: str, top_k: int = 10) -> tuple[str, list[str]]:
        # TODO: implement chunking & vector store logic
        return f"Answer for: {query}", ["source1", "source2"]


knowledge_service = KnowledgeService()