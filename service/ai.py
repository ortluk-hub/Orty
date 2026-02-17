import httpx

from service.config import settings


class AIService:
    def __init__(self):
        self.system_prompt = "You are Orty, a concise and intelligent on-device assistant."

    async def generate(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        provider = settings.LLM_PROVIDER
        history = history or []

        if provider == "ollama":
            return await self._generate_ollama(message, history)

        return await self._generate_openai(message, history)

    async def _generate_openai(self, message: str, history: list[dict[str, str]]) -> str:
        if not settings.OPENAI_API_KEY:
            return "OPENAI_API_KEY not configured."

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            return f"OpenAI error: {response.text}"

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _generate_ollama(self, message: str, history: list[dict[str, str]]) -> str:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )

        if response.status_code != 200:
            return f"Ollama error: {response.text}"

        data = response.json()
        return data["message"]["content"]
