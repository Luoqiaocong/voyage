from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.core.agent import build_agent
from app.core.memory import close_checkpointer, init_checkpointer
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.itineraries.router import router as itineraries_router
from app.modules.knowledge.router import router as knowledge_router

API_V1_STR = "/api/v1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpointer = await init_checkpointer()
    build_agent(checkpointer)
    yield
    await close_checkpointer()

app = FastAPI(title="VOYAGE AI TRAVEL PLANNER",lifespan=lifespan)

app.include_router(auth_router,prefix=API_V1_STR)
app.include_router(chat_router,prefix=API_V1_STR)
app.include_router(itineraries_router,prefix=API_V1_STR)
app.include_router(knowledge_router,prefix=API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Hello World"}