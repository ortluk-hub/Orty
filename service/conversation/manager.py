from typing import Optional, Dict
from service.conversation.repository import ConversationRepository
from service.llm.interface import LLMProvider


class ConversationManager:

    def __init__(self, llm_provider: LLMProvider):
        self.repository = ConversationRepository()
        self.llm_provider = llm_provider

    async def handle_message(
        self,
        content: str,
        conversation_id: Optional[str] = None
    ) -> Dict:

        # Ensure conversation exists
        if conversation_id:
            if not self.repository.conversation_exists(conversation_id):
                raise ValueError("Conversation does not exist.")
        else:
            conversation_id = self.repository.create_conversation()

        # Store user message
        self.repository.add_message(conversation_id, "user", content)

        # Fetch conversation history
        messages = self.repository.get_messages(conversation_id)

        # Generate assistant response
        response_text = await self.llm_provider.generate(messages)

        # Store assistant message
        self.repository.add_message(conversation_id, "assistant", response_text)

        return {
            "conversation_id": conversation_id,
            "response": response_text
        }

