from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import InMemorySaver
from fastapi import FastAPI
from app.core.ai import AgentFactory
from app.modules.auth.router import router as auth_router
from app.modules.conversation.router import router as conversation_router
from app.modules.itineraries.router import router as itineraries_router
from app.modules.knowledge.router import router as knowledge_router
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pathlib import Path


API_V1_STR = "/api/v1"
SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "exports" / "checkpoints.sqlite"


app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string(str(SQLITE_PATH)) as checkpointer:
        # 若 API 需要：await checkpointer.setup()
        AgentFactory.initialize()
        # AgentFactory.initialize(checkpointer)
        # app.state.checkpointer = checkpointer  # 可选：事后读 state 用
        yield
    AgentFactory.reset()  # 关闭前清掉，避免指着已关连接
    
app = FastAPI(title="VOYAGE AI TRAVEL PLANNER",lifespan=lifespan)

app.include_router(auth_router,prefix=API_V1_STR)
app.include_router(conversation_router,prefix=API_V1_STR)
app.include_router(itineraries_router,prefix=API_V1_STR)
app.include_router(knowledge_router,prefix=API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Hello World"}