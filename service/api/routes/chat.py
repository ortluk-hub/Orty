from fastapi import APIRouter, Depends, Request

from service.api.deps import get_request_auth, get_runtime
from service.models.schemas import ChatRequest, ChatResponse, EscalationContext

router = APIRouter()


@router.post('/chat', response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, auth: dict = Depends(get_request_auth)):
    runtime = get_runtime(request)
    incoming_conversation_id = None if payload.reset_conversation else payload.conversation_id
    conversation_id = runtime.memory_store.ensure_conversation_id(incoming_conversation_id)
    client_id = auth.get("client_id")

    history = runtime.memory_store.get_recent_messages(
        conversation_id,
        limit=payload.history_limit,
        client_id=client_id,
    )
    effective_history = [*history, *_escalation_context_messages(payload.escalation_context)]
    generated = await runtime.ai_service.generate_with_meta(payload.message, history=effective_history)
    reply = generated["reply"]

    if payload.persist:
        runtime.memory_store.append_message(conversation_id, 'user', payload.message, client_id=client_id)
        runtime.memory_store.append_message(conversation_id, 'assistant', reply, client_id=client_id)

    return ChatResponse(
        reply=reply,
        conversation_id=conversation_id,
        used_history=len(history),
        handled_by=generated.get("handled_by"),
        provider=generated.get("provider"),
        fallback_used=bool(generated.get("fallback_used", False)),
        context_version=payload.escalation_context.context_version if payload.escalation_context else None,
        summary_id=payload.escalation_context.summary_id if payload.escalation_context else None,
    )


def _escalation_context_messages(context: EscalationContext | None) -> list[dict[str, str]]:
    if context is None:
        return []

    messages: list[dict[str, str]] = []
    if context.local_summary:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Escalation context from Alfred (local summary):\n"
                    f"{context.local_summary}"
                ),
            }
        )
    for msg in context.recent_messages:
        messages.append({"role": msg.role, "content": msg.content})
    return messages
