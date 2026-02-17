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
    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "ollama-reply"


def test_generate_uses_openai_provider_by_default(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    async def fake_openai(message, history):
        return "openai-reply"

    monkeypatch.setattr(service, "_generate_openai", fake_openai)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "openai-reply"


def test_generate_returns_clear_message_for_unsupported_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")

    result = asyncio.run(service.generate("hello"))

    assert result == "Unsupported LLM_PROVIDER 'anthropic'. Available providers: ollama, openai."


def test_generate_can_use_registered_custom_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    async def fake_mock(message, history):
        return f"mock:{message}:{len(history)}"

    service.register_provider("mock", fake_mock)

    result = asyncio.run(service.generate("hello", history=[{"role": "user", "content": "x"}]))

    assert result == "mock:hello:1"
