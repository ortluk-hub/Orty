from fastapi import FastAPI, Depends
from service.schemas import ChatRequest, ChatResponse
from service.security import verify_secret
from service.ai import AIService

app = FastAPI(title="Orty AI Assistant")

ai_service = AIService()

@app.get("/health")
async def health():
    return {"status": "ok", "assistant": "Orty"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, _: str = Depends(verify_secret)):
    reply = await ai_service.generate(request.message)
    return ChatResponse(reply=reply)

