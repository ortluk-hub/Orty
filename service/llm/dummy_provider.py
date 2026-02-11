from typing import List, Dict
from service.llm.interface import LLMProvider


class DummyProvider(LLMProvider):

    async def generate(self, messages: List[Dict]) -> str:
        # Simple echo logic for testing
        last_user_message = messages[-1]["content"]
        return f"Echo: {last_user_message}"

