from fastapi import FastAPI
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.itineraries.router import router as itineraries_router
from app.modules.knowledge.router import router as knowledge_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(itineraries_router)
app.include_router(knowledge_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}