import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from service.ai import AIService, ChatRequestContext
from service.config import settings


def test_generate_uses_ollama_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

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
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

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

    assert result == (
        "Unsupported LLM_PROVIDER 'anthropic'. Available providers: "
        "ollama, ollama_cloud, openai, vertex_ai."
    )


def test_generate_can_use_registered_custom_provider(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

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
        "bots_overview, clients_overview, codey_overview, echo, fs_list, fs_pwd, fs_read, "
        "gh_file, gh_repo, gh_tree, memory_overview, smart_home, system_overview, utc_time, web_search."
    )


def test_build_system_prompt_grounds_orty_as_server_identity():
    service = AIService()

    prompt = service._build_system_prompt(
        ChatRequestContext(channel="orty_web_ui", requested_client_name="orty-web-ui")
    )

    assert "You are Orty, the server system and coordination layer" in prompt
    assert "Treat the active language model as one of your faculties" in prompt
    assert "This is the Orty web UI." in prompt
    assert "/tool system_overview" in prompt


def test_build_system_prompt_can_include_client_contract():
    service = AIService()

    prompt = service._build_system_prompt(
        ChatRequestContext(
            channel="api",
            requested_client_name="alfred-android",
            assistant_name="Jane",
            personality_preset="friendly",
            client_system_prompt="Always answer outwardly as Jane for Alfred Android.",
        )
    )

    assert "This request came through a managed client." in prompt
    assert "Presented assistant name for this client: Jane." in prompt
    assert "Always answer outwardly as Jane for Alfred Android." in prompt


def test_build_system_prompt_includes_client_tool_contract():
    service = AIService()

    prompt = service._build_system_prompt(
        ChatRequestContext(
            channel="api",
            requested_client_name="alfred-android",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "alfred.navigate_to",
                        "description": "Navigate to a saved place",
                    },
                }
            ],
            tool_choice="auto",
        )
    )

    assert "Client tool contract:" in prompt
    assert "Available client tools: alfred.navigate_to." in prompt
    assert "Requested tool choice: auto." in prompt
    assert "direct tool_calls shape" in prompt


def test_generate_with_meta_parses_structured_tool_calls(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

    async def fake_openai(message, history, system_prompt=None, request_context=None):
        assert request_context is not None
        assert request_context.tools[0]["function"]["name"] == "alfred.navigate_to"
        return json.dumps(
            {
                "reply": "",
                "tool_calls": [
                    {
                        "name": "alfred.navigate_to",
                        "arguments": {"destination": "home"},
                    }
                ],
            }
        )

    service.register_provider("openai", fake_openai)

    result = asyncio.run(
        service.generate_with_meta(
            "navigate home",
            request_context=ChatRequestContext(
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "alfred.navigate_to"},
                    }
                ],
                tool_choice="auto",
            ),
        )
    )

    assert result["reply"] == ""
    assert result["tool_calls"] == [
        {"name": "alfred.navigate_to", "arguments": {"destination": "home"}}
    ]


def test_generate_with_meta_parses_fenced_structured_tool_calls(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

    async def fake_openai(message, history, system_prompt=None, request_context=None):
        return """```json
        {
          "reply": "",
          "tool_calls": [
            {
              "name": "alfred.navigate_to",
              "arguments": {"destination": "home"}
            }
          ]
        }
        ```"""

    service.register_provider("openai", fake_openai)

    result = asyncio.run(
        service.generate_with_meta(
            "navigate home",
            request_context=ChatRequestContext(
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "alfred.navigate_to"},
                    }
                ],
                tool_choice="auto",
            ),
        )
    )

    assert result["reply"] == ""
    assert result["tool_calls"] == [
        {"name": "alfred.navigate_to", "arguments": {"destination": "home"}}
    ]


def test_generate_with_meta_routes_tool_requests_away_from_vertex_ai(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "vertex_ai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

    called: dict[str, bool] = {}

    async def fake_openai(message, history, system_prompt=None, request_context=None):
        called["openai"] = True
        return json.dumps(
            {
                "reply": "",
                "tool_calls": [
                    {
                        "name": "alfred.navigate_to",
                        "arguments": {"destination": "home"},
                    }
                ],
            }
        )

    async def fake_vertex(message, history, system_prompt=None, request_context=None):
        raise AssertionError("vertex_ai should not be selected for tool requests")

    service.register_provider("openai", fake_openai)
    service.register_provider("vertex_ai", fake_vertex)

    result = asyncio.run(
        service.generate_with_meta(
            "navigate home",
            request_context=ChatRequestContext(
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "alfred.navigate_to"},
                    }
                ],
                tool_choice="auto",
            ),
        )
    )

    assert called["openai"] is True
    assert result["tool_calls"] == [
        {"name": "alfred.navigate_to", "arguments": {"destination": "home"}}
    ]


def test_generate_openai_passes_tool_contract_and_normalizes_tool_calls(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "alfred.navigate_to",
                                        "arguments": '{"destination":"home"}',
                                    }
                                }
                            ],
                        }
                    }
                ]
            }

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = asyncio.run(
        service._generate_openai(
            "navigate home",
            [],
            request_context=ChatRequestContext(
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "alfred.navigate_to"},
                    }
                ],
                tool_choice="auto",
            ),
        )
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["tools"][0]["function"]["name"] == "alfred.navigate_to"
    assert payload["tool_choice"] == "auto"

    parsed = json.loads(result)
    assert parsed["reply"] == ""
    assert parsed["tool_calls"] == [
        {"name": "alfred.navigate_to", "arguments": {"destination": "home"}}
    ]


def test_generate_vertex_ai_disables_safety_settings_at_instantiation(monkeypatch):
    pytest.importorskip("vertexai.generative_models")
    import service.ai as service_ai
    import vertexai.generative_models as vertex_generative_models

    service = AIService()
    monkeypatch.setattr(settings, "VERTEX_AI_PROJECT_ID", "test-project")
    monkeypatch.setattr(settings, "VERTEX_AI_LOCATION", "us-central1")
    monkeypatch.setattr(settings, "VERTEX_AI_MODEL_ID", "gemini-1.5-pro")
    monkeypatch.setattr(settings, "VERTEX_AI_CREDENTIALS_PATH", None)
    monkeypatch.setattr(
        service_ai,
        "google_auth",
        SimpleNamespace(
            default=lambda: (object(), "test-project"),
            load_credentials_from_file=lambda _: (object(), "test-project"),
            exceptions=SimpleNamespace(DefaultCredentialsError=Exception),
        ),
    )
    monkeypatch.setattr(service_ai.aiplatform, "init", lambda **kwargs: None)
    monkeypatch.setattr(AIService, "_build_system_prompt", lambda self, request_context=None: None)

    captured: dict[str, object] = {}

    class FakeChatSession:
        def send_message(self, message):
            captured["message"] = message
            return SimpleNamespace(text="vertex-reply")

    class FakeGenerativeModel:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

        def start_chat(self, history=None, response_validation=True):
            captured["history"] = history
            captured["response_validation"] = response_validation
            return FakeChatSession()

    monkeypatch.setattr(vertex_generative_models, "GenerativeModel", FakeGenerativeModel)

    result = asyncio.run(service._generate_vertex_ai("hello", []))

    assert result == "vertex-reply"
    assert captured["model_name"] == "gemini-1.5-pro"
    assert captured["response_validation"] is False
    assert [setting.to_dict() for setting in captured["kwargs"]["safety_settings"]] == [
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
        {"category": "HARM_CATEGORY_JAILBREAK", "threshold": "OFF"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
        {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"},
    ]


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


def test_generate_executes_group_smart_home_tool_with_smartthings(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "SMART_HOME_PROVIDER", "smartthings")
    monkeypatch.setattr(settings, "SMARTTHINGS_PAT", "test-pat")
    monkeypatch.setattr(
        settings,
        "SMARTTHINGS_DEVICE_MAP",
        json.dumps(
            {
                "paul": {
                    "device_id": "device-1",
                    "kind": "dimmer",
                    "aliases": ["paul", "master bedroom light"],
                },
                "lisa": {
                    "device_id": "device-2",
                    "kind": "dimmer",
                    "aliases": ["lisa", "master bedroom light"],
                },
            }
        ),
    )
    monkeypatch.setattr(
        settings,
        "SMARTTHINGS_GROUP_MAP",
        json.dumps(
            {
                "master bedroom lights": {
                    "members": ["paul", "lisa"],
                    "aliases": ["master bedroom lights", "master bedroom light"],
                }
            }
        ),
    )

    sent_commands: list[tuple[str, dict]] = []

    async def fake_send(self, device_id, payload):
        sent_commands.append((device_id, payload))

    monkeypatch.setattr(AIService, "_smartthings_send_command", fake_send)

    result = asyncio.run(service.generate("/tool smart_home turn off the master bedroom light"))

    assert sent_commands == [
        ("device-1", {"commands": [{"component": "main", "capability": "switch", "command": "off"}]}),
        ("device-2", {"commands": [{"component": "main", "capability": "switch", "command": "off"}]}),
    ]
    assert result == "I turned off paul and lisa."


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
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)

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


def test_generate_parallel_race_prefers_fastest_success(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", True)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", True)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "openai")

    async def fake_ollama(message, history):
        await asyncio.sleep(0.05)
        return "local-reply"

    async def fake_openai(message, history):
        await asyncio.sleep(0.01)
        return "cloud-reply"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate_with_meta("hello"))

    assert result["reply"] == "cloud-reply"
    assert result["provider"] == "openai"
    assert result["fallback_used"] is True
    assert result["handled_by"] == "cloud-fallback"


def test_generate_parallel_race_ignores_fast_error_and_uses_slower_success(monkeypatch):
    service = AIService()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", True)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", True)
    monkeypatch.setattr(settings, "CLOUD_FALLBACK_PROVIDER", "openai")

    async def fake_ollama(message, history):
        await asyncio.sleep(0.01)
        return "Ollama error: overloaded"

    async def fake_openai(message, history):
        await asyncio.sleep(0.05)
        return "cloud-reply"

    service.register_provider("ollama", fake_ollama)
    service.register_provider("openai", fake_openai)

    result = asyncio.run(service.generate_with_meta("hello"))

    assert result["reply"] == "cloud-reply"
    assert result["provider"] == "openai"
    assert result["fallback_used"] is True


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
