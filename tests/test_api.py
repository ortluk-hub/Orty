import asyncio
import json

import httpx

from service.api import app
from service.api.routes import v1_stt
from service.api.routes import v1_tts
from service.ai import WebSearchResult
from service.config import settings

async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


def _ui_admin_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    login = request(
        "POST",
        "/ui/login",
        data={"shared_secret": "ui-admin-secret"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    cookie = login.headers["set-cookie"].split(";", 1)[0]
    return {"cookie": cookie}


def _force_serial_openai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "ENABLE_CLOUD_FALLBACK", False)
    monkeypatch.setattr(settings, "ENABLE_PARALLEL_PROVIDER_RACE", False)


def test_health_endpoint_returns_ok_and_assistant_name():
    response = request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "assistant": "Orty"}


def test_chat_requires_registered_client_or_shared_secret():
    response = request("POST", "/chat", json={"message": "hello"})

    assert response.status_code == 401


def test_chat_rejects_invalid_shared_secret():
    response = request(
        "POST",
        "/chat",
        json={"message": "hello"},
        headers={"x-orty-secret": "invalid-secret"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_stt_proxy_requires_auth():
    response = request(
        "POST",
        "/v1/stt/recognize",
        json={"audio_base64": "AQID", "language_code": "en-US", "api_key": "test-key"},
    )

    assert response.status_code == 401


def test_stt_proxy_returns_transcript(monkeypatch):
    class FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        content = b'{"results":[{"alternatives":[{"transcript":"hello from orty"}]}]}'

        def json(self):
            return json.loads(self.content.decode("utf-8"))

    async def fake_post_google_speech(api_key: str, request_body: dict):
        assert api_key == "test-key"
        assert request_body["audio"]["content"] == "AQID"
        return FakeResponse()

    monkeypatch.setattr(v1_stt, "_post_google_speech", fake_post_google_speech)

    response = request(
        "POST",
        "/v1/stt/recognize",
        json={"audio_base64": "AQID", "language_code": "en-US", "api_key": "test-key"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    assert response.json() == {
        "transcript": "hello from orty",
        "no_speech": False,
        "provider": "google_speech_v1",
    }


def test_stt_proxy_returns_no_speech(monkeypatch):
    class FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        content = b'{"results":[]}'

        def json(self):
            return {"results": []}

    async def fake_post_google_speech(api_key: str, request_body: dict):
        return FakeResponse()

    monkeypatch.setattr(v1_stt, "_post_google_speech", fake_post_google_speech)

    response = request(
        "POST",
        "/v1/stt/recognize",
        json={"audio_base64": "AQID", "language_code": "en-US", "api_key": "test-key"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    assert response.json()["no_speech"] is True


def test_tts_proxy_requires_auth():
    response = request(
        "POST",
        "/v1/tts/synthesize",
        json={"text": "hello", "language_code": "en-US", "api_key": "test-key"},
    )

    assert response.status_code == 401


def test_tts_proxy_returns_audio(monkeypatch):
    class FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        content = b'{"audioContent":"QUJDRA=="}'

        def json(self):
            return json.loads(self.content.decode("utf-8"))

    async def fake_post_google_tts(api_key: str, request_body: dict):
        assert api_key == "test-key"
        assert request_body["input"]["text"] == "hello from orty"
        assert request_body["voice"]["languageCode"] == "en-US"
        assert request_body["voice"]["name"] == "en-US-Neural2-F"
        assert request_body["audioConfig"]["audioEncoding"] == "MP3"
        return FakeResponse()

    monkeypatch.setattr(v1_tts, "_post_google_tts", fake_post_google_tts)

    response = request(
        "POST",
        "/v1/tts/synthesize",
        json={
            "text": "hello from orty",
            "language_code": "en-US",
            "api_key": "test-key",
            "voice_name": "en-US-Neural2-F",
            "audio_encoding": "MP3",
        },
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    assert response.json() == {
        "audio_base64": "QUJDRA==",
        "audio_encoding": "MP3",
        "provider": "google_tts_v1",
    }


def test_chat_returns_configuration_message_when_api_key_missing(monkeypatch):
    _force_serial_openai(monkeypatch)

    response = request(
        "POST",
        "/chat",
        json={"message": "hello"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "OPENAI_API_KEY not configured."
    assert body["conversation_id"]


def test_chat_reuses_conversation_id(monkeypatch):
    _force_serial_openai(monkeypatch)

    first = request(
        "POST",
        "/chat",
        json={"message": "one"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    first_id = first.json()["conversation_id"]

    second = request(
        "POST",
        "/chat",
        json={"message": "two", "conversation_id": first_id},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == first_id


def test_chat_can_disable_persistence(monkeypatch):
    _force_serial_openai(monkeypatch)

    first = request(
        "POST",
        "/chat",
        json={"message": "ephemeral", "persist": False},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert first.status_code == 200
    conv_id = first.json()["conversation_id"]

    second = request(
        "POST",
        "/chat",
        json={"message": "follow-up", "conversation_id": conv_id},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert second.status_code == 200
    assert second.json()["used_history"] == 0


def test_chat_can_reset_conversation(monkeypatch):
    _force_serial_openai(monkeypatch)

    first = request(
        "POST",
        "/chat",
        json={"message": "one"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    first_id = first.json()["conversation_id"]

    second = request(
        "POST",
        "/chat",
        json={"message": "two", "conversation_id": first_id, "reset_conversation": True},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] != first_id
    assert second.json()["used_history"] == 0


def test_chat_applies_history_limit(monkeypatch):
    _force_serial_openai(monkeypatch)

    seed = request(
        "POST",
        "/chat",
        json={"message": "seed"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    conv_id = seed.json()["conversation_id"]

    limited = request(
        "POST",
        "/chat",
        json={"message": "limited", "conversation_id": conv_id, "history_limit": 1},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert limited.status_code == 200
    assert limited.json()["used_history"] == 1


def test_ui_home_redirects_to_login_when_not_authenticated(monkeypatch):
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    response = request("GET", "/ui", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


def test_root_redirects_to_ui():
    response = request("GET", "/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_ui_home_page_trailing_slash_redirects_to_login_when_not_authenticated(monkeypatch):
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    response = request("GET", "/ui/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


def test_ui_login_page_is_available(monkeypatch):
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    response = request("GET", "/ui/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Admin Login" in response.text
    assert "Sign in as an admin" in response.text


def test_ui_login_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    response = request("POST", "/ui/login", data={"shared_secret": "wrong"})

    assert response.status_code == 401
    assert "Invalid admin secret." in response.text


def test_ui_login_sets_cookie_and_allows_ui(monkeypatch):
    headers = _ui_admin_headers(monkeypatch)
    response = request("GET", "/ui", headers=headers)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Orty Web UI" in response.text
    assert "Admin-authenticated Orty chat interface with conversation continuity." in response.text


def test_homepage_is_available():
    response = request("GET", "/homepage")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Alfred + Orty" in response.text
    assert "/privacy-policy" in response.text
    assert "/jane-charter" in response.text
    assert "/voice-and-identity-contract" in response.text
    assert "/monetization-guardrails" in response.text


def test_privacy_policy_is_available():
    response = request("GET", "/privacy-policy")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Privacy Policy" in response.text
    assert "Effective date: March 20, 2026" in response.text


def test_jane_charter_page_is_available():
    response = request("GET", "/jane-charter")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Jane Charter" in response.text
    assert "persistent across sessions" in response.text


def test_voice_and_identity_contract_page_is_available():
    response = request("GET", "/voice-and-identity-contract")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Voice And Identity Contract" in response.text
    assert "Voice is part of identity" in response.text


def test_monetization_guardrails_page_is_available():
    response = request("GET", "/monetization-guardrails")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Monetization Guardrails" in response.text
    assert "free tier should remain a real assistant" in response.text.lower()

def test_ui_chat_messages_are_rendered_as_text_nodes(monkeypatch):
    response = request("GET", "/ui", headers=_ui_admin_headers(monkeypatch))

    assert response.status_code == 200
    assert "createTextNode" in response.text
    assert "div.innerHTML" not in response.text


def test_ui_chat_requires_admin_login_cookie(monkeypatch):
    monkeypatch.setattr(settings, "ORTY_UI_ADMIN_SECRET", "ui-admin-secret")
    response = request("POST", "/ui/chat", json={"message": "hello root"})

    assert response.status_code == 401


def test_ui_chat_uses_admin_authenticated_session(monkeypatch):
    runtime = app.state.runtime
    captured: dict = {}

    async def fake_generate(message, history=None, request_context=None):
        captured["message"] = message
        captured["request_context"] = request_context
        return "admin-ok"

    monkeypatch.setattr(runtime.ai_service, "generate", fake_generate)
    headers = _ui_admin_headers(monkeypatch)

    response = request("POST", "/ui/chat", json={"message": "hello root"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["conversation_id"]
    assert response.json()["reply"] == "admin-ok"
    assert captured["message"] == "hello root"
    assert captured["request_context"].auth_method == "admin-ui"
    assert captured["request_context"].current_client["is_admin"] is True


def test_chat_returns_generation_metadata(monkeypatch):
    _force_serial_openai(monkeypatch)

    response = request(
        "POST",
        "/chat",
        json={"message": "hello"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["fallback_used"] is False
    assert body["handled_by"] == "cloud-primary"


def test_chat_accepts_escalation_context_and_echoes_context_metadata(monkeypatch):
    _force_serial_openai(monkeypatch)

    response = request(
        "POST",
        "/chat",
        json={
            "message": "handle this",
            "escalation_context": {
                "context_version": "v1",
                "summary_id": "sum-123",
                "local_summary": "Alfred local context summary.",
                "recent_messages": [
                    {"role": "user", "content": "previous user turn"},
                    {"role": "assistant", "content": "previous assistant turn"},
                ],
            },
        },
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["context_version"] == "v1"
    assert body["summary_id"] == "sum-123"


def test_chat_web_search_tool_returns_top_result(monkeypatch):
    async def fake_search(self, query: str):
        assert query == "when does walmart close"
        return [
            WebSearchResult(
                title="Walmart in Lehi, UT - Hours & Locations",
                url="https://example.com/walmart-hours",
                snippet="Open today until 11 PM. Updated this week."
            )
        ]

    monkeypatch.setattr("service.ai.AIService._search_web", fake_search)

    response = request(
        "POST",
        "/chat",
        json={"message": "/tool web_search when does walmart close", "persist": False},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool"
    assert body["handled_by"] == "tool"
    assert body["fallback_used"] is False
    assert "Walmart in Lehi, UT - Hours & Locations" in body["reply"]
    assert "Open today until 11 PM." in body["reply"]
    assert "https://example.com/walmart-hours" in body["reply"]


def test_chat_smart_home_tool_returns_success(monkeypatch):
    monkeypatch.setattr(settings, "SMART_HOME_PROVIDER", "smartthings")
    monkeypatch.setattr(settings, "SMARTTHINGS_PAT", "test-pat")
    monkeypatch.setattr(
        settings,
        "SMARTTHINGS_DEVICE_MAP",
        json.dumps(
            {
                "front door": {
                    "device_id": "lock-123",
                    "kind": "lock",
                }
            }
        ),
    )

    async def fake_send(self, device_id: str, payload: dict) -> None:
        assert device_id == "lock-123"
        assert payload == {
            "commands": [
                {
                    "component": "main",
                    "capability": "lock",
                    "command": "lock",
                }
            ]
        }

    monkeypatch.setattr("service.ai.AIService._smartthings_send_command", fake_send)

    response = request(
        "POST",
        "/chat",
        json={"message": "/tool smart_home lock the front door", "persist": False},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool"
    assert body["handled_by"] == "tool"
    assert body["fallback_used"] is False
    assert body["reply"] == "I updated front door."
