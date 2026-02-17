import asyncio

from service.ai import AIService
from service.config import settings


def test_generate_uses_ollama_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")

    async def fake_ollama(message, history):
        return "ollama-reply"

    async def fake_openai(message, history):
        return "openai-reply"

    monkeypatch.setattr(service, "_generate_ollama", fake_ollama)
    monkeypatch.setattr(service, "_generate_openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "ollama-reply"


def test_generate_uses_openai_provider_by_default(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    async def fake_openai(message, history):
        return "openai-reply"

    monkeypatch.setattr(service, "_generate_openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "openai-reply"
