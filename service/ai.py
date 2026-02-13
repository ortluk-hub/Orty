from service.config import Settings

class AIService:
    def __init__(self):
        # Create settings at runtime instead of import time
        settings = Settings()
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL

    async def generate(self, message: str) -> str:
        # Import httpx or other dependencies **only when needed**
        import httpx

        if not self.api_key:
            raise RuntimeError("OpenAI API key not set")

        # Example call — adjust to your actual API integration
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": message}],
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

        response.raise_for_status()
        data = response.json()
        # this assumes the API response is structured in the typical OpenAI way
        return data["choices"][0]["message"]["content"]

