from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import InMemorySaver
from fastapi import FastAPI
from app.core.ai import AgentFactory
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.itineraries.router import router as itineraries_router
from app.modules.knowledge.router import router as knowledge_router

API_V1_STR = "/api/v1"

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpointer = InMemorySaver()  # 全局一个即可
    AgentFactory.initialize(checkpointer)
    yield
    # InMemory 无需关闭连接
    
app = FastAPI(title="VOYAGE AI TRAVEL PLANNER",lifespan=lifespan)

app.include_router(auth_router,prefix=API_V1_STR)
app.include_router(chat_router,prefix=API_V1_STR)
app.include_router(itineraries_router,prefix=API_V1_STR)
app.include_router(knowledge_router,prefix=API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Hello World"}