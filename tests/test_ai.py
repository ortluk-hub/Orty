import asyncio

import httpx

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


def test_generate_uses_openai_provider_when_explicitly_selected(monkeypatch):
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


def test_generate_executes_echo_tool_before_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    async def fake_openai(message, history):
        return "openai-reply"

    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("/tool echo hello tools"))

    assert result == "hello tools"


def test_generate_executes_utc_time_tool_before_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    async def fake_openai(message, history):
        return "openai-reply"

    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("/tool utc_time"))

    assert "T" in result
    assert result.endswith("+00:00")


def test_generate_returns_available_tools_for_unknown_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    result = asyncio.run(service.generate("/tool missing"))

    assert result == "Tool 'missing' is not available. Available tools: echo, fs_list, fs_pwd, fs_read, utc_time."


def test_generate_executes_fs_pwd_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    result = asyncio.run(service.generate("/tool fs_pwd"))

    assert result


def test_generate_executes_fs_list_tool(tmp_path, monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    (tmp_path / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "two").mkdir()

    result = asyncio.run(service.generate(f"/tool fs_list {tmp_path}"))

    assert "one.txt" in result
    assert "two/" in result


def test_generate_executes_fs_read_tool(tmp_path, monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "FS_READ_ROOT", str(tmp_path))
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello fs", encoding="utf-8")

    result = asyncio.run(service.generate("/tool fs_read note.txt"))

    assert result == "hello fs"


def test_generate_rejects_fs_read_outside_configured_root(tmp_path, monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "FS_READ_ROOT", str(tmp_path))

    outside_file = tmp_path.parent / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")

    result = asyncio.run(service.generate(f"/tool fs_read {outside_file}"))

    assert "Access denied" in result


def test_generate_rejects_fs_read_path_traversal(tmp_path, monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(settings, "FS_READ_ROOT", str(root))

    escaped_file = tmp_path / "secret.txt"
    escaped_file.write_text("top-secret", encoding="utf-8")

    result = asyncio.run(service.generate("/tool fs_read ../secret.txt"))

    assert "Access denied" in result


def test_generate_returns_recoverable_message_when_ollama_is_unreachable(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    async def fake_post(self, *args, **kwargs):
        raise httpx.ConnectError(
            "connection refused",
            request=httpx.Request("POST", f"{settings.OLLAMA_BASE_URL}/api/chat"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = asyncio.run(service.generate("hello"))

    assert "Ollama is not reachable." in result
    assert settings.OLLAMA_BASE_URL in result
