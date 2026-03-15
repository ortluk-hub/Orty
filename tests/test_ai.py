import asyncio
import json

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

    assert result == "Unsupported LLM_PROVIDER 'anthropic'. Available providers: ollama, ollama_cloud, openai."


def test_generate_can_use_registered_custom_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    async def fake_mock(message, history):
        return f"mock:{message}:{len(history)}"

    service.register_provider("mock", fake_mock)

    result = asyncio.run(service.generate("hello", history=[{"role": "user", "content": "x"}]))

    assert result == "mock:hello:1"




def test_generate_executes_sync_custom_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    def sync_tool(tool_input):
        return f"sync:{tool_input}"

    service.register_tool("sync", sync_tool)

    result = asyncio.run(service.generate("/tool sync hello"))

    assert result == "sync:hello"


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

    assert result == (
        "Tool 'missing' is not available. Available tools: "
        "echo, fs_list, fs_pwd, fs_read, gh_file, gh_repo, gh_tree, smart_home, utc_time, web_search."
    )


def test_generate_executes_fs_pwd_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    result = asyncio.run(service.generate("/tool fs_pwd"))

    assert result


def test_generate_reports_when_smart_home_not_configured(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "SMART_HOME_PROVIDER", "")
    monkeypatch.setattr(settings, "SMARTTHINGS_PAT", None)
    monkeypatch.setattr(settings, "SMARTTHINGS_DEVICE_MAP", "{}")

    result = asyncio.run(service.generate("/tool smart_home turn off the living room lights"))

    assert "Smart-home control unavailable" in result
    assert "SMART_HOME_PROVIDER=smartthings" in result


def test_generate_executes_smart_home_tool_with_smartthings(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "SMART_HOME_PROVIDER", "smartthings")
    monkeypatch.setattr(settings, "SMARTTHINGS_PAT", "test-pat")
    monkeypatch.setattr(
        settings,
        "SMARTTHINGS_DEVICE_MAP",
        json.dumps(
            {
                "living room lights": {
                    "device_id": "device-123",
                    "kind": "switch",
                    "aliases": ["living room light", "lights"],
                }
            }
        ),
    )

    async def fake_send(self, device_id, payload):
        assert device_id == "device-123"
        assert payload == {
            "commands": [
                {
                    "component": "main",
                    "capability": "switch",
                    "command": "off",
                }
            ]
        }

    monkeypatch.setattr(AIService, "_smartthings_send_command", fake_send)

    result = asyncio.run(service.generate("/tool smart_home turn off the living room lights"))

    assert result == "I turned off living room lights."


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


def test_generate_can_fallback_to_openai_when_ollama_fails(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", True)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "openai")

    async def fake_ollama(message, history):
        return "Ollama is not reachable. Expected server at http://127.0.0.1:11434."

    async def fake_openai(message, history):
        return "cloud-reply"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "cloud-reply"


def test_generate_can_fallback_to_ollama_cloud_when_local_ollama_fails(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", True)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "ollama_cloud")

    async def fake_ollama(message, history):
        return "Ollama error: local model overloaded"

    async def fake_ollama_cloud(message, history):
        return "cloud-reply"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("ollama_cloud", fake_ollama_cloud)

    result = asyncio.run(service.generate("hello"))

    assert result == "cloud-reply"


def test_generate_returns_primary_error_when_cloud_fallback_disabled(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "openai")

    async def fake_ollama(message, history):
        return "Ollama error: model missing"

    async def fake_openai(message, history):
        return "cloud-reply"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert result == "Ollama error: model missing"


def test_generate_reports_when_primary_and_fallback_both_fail(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", True)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "openai")

    async def fake_ollama(message, history):
        return "Ollama error: overloaded"

    async def fake_openai(message, history):
        return "OpenAI error: rate limit"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate("hello"))

    assert "Ollama error: overloaded" in result
    assert "Cloud fallback (openai) also failed: OpenAI error: rate limit" in result


def test_generate_executes_gh_repo_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "full_name": "octocat/Hello-World",
                "description": "test repo",
                "default_branch": "main",
                "stargazers_count": 5,
                "forks_count": 2,
                "open_issues_count": 1,
                "html_url": "https://github.com/octocat/Hello-World",
            }

    
    async def fake_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = asyncio.run(service.generate("/tool gh_repo octocat/Hello-World"))

    assert "name: octocat/Hello-World" in result
    assert "default_branch: main" in result


def test_generate_executes_gh_tree_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return [
                {"name": "service", "type": "dir"},
                {"name": "README.md", "type": "file"},
            ]

    
    async def fake_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = asyncio.run(service.generate("/tool gh_tree octocat/Hello-World"))

    assert "service/" in result
    assert "README.md" in result


def test_generate_executes_gh_file_tool(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "type": "file",
                "encoding": "base64",
                "content": "aGVsbG8gZ2l0aHVi",
            }

    
    async def fake_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = asyncio.run(service.generate("/tool gh_file octocat/Hello-World README.md"))

    assert result == "hello github"


def test_generate_rejects_overly_long_tool_input(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    long_input = "x" * 2001
    result = asyncio.run(service.generate(f"/tool echo {long_input}"))

    assert "Tool input exceeds 2000 characters" in result


def test_generate_validates_gh_repo_contract(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    result = asyncio.run(service.generate("/tool gh_repo invalid/repo/name"))

    assert result == "Usage: /tool gh_repo <owner/repo>"
