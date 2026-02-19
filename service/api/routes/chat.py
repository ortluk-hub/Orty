from fastapi import APIRouter, Depends

from service.ai import AIService
from service.memory import MemoryStore
from service.models.schemas import ChatRequest, ChatResponse
from service.security import verify_secret

router = APIRouter()
ai_service = AIService()
memory_store = MemoryStore()


@router.post('/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, _: str = Depends(verify_secret)):
    incoming_conversation_id = None if request.reset_conversation else request.conversation_id
    conversation_id = memory_store.ensure_conversation_id(incoming_conversation_id)

    history = memory_store.get_recent_messages(conversation_id, limit=request.history_limit)
    reply = await ai_service.generate(request.message, history=history)

    if request.persist:
        memory_store.append_message(conversation_id, 'user', request.message)
        memory_store.append_message(conversation_id, 'assistant', reply)

    return ChatResponse(
        reply=reply,
        conversation_id=conversation_id,
        used_history=len(history),
    )
