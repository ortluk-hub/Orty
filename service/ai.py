import httpx
from service.config import settings

class AIService:

    async def generate(self, message: str) -> str:
        if not settings.OPENAI_API_KEY:
            return "OPENAI_API_KEY not configured."

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You are Orty, a concise and intelligent on-device assistant."},
                {"role": "user", "content": message}
            ]
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )

        if response.status_code != 200:
            return f"OpenAI error: {response.text}"

        data = response.json()
        return data["choices"][0]["message"]["content"]

