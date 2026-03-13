import asyncio

import httpx

from service.api import app
from service.ai import WebSearchResult
from service.config import settings

async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


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


def test_chat_returns_configuration_message_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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


def test_ui_home_page_is_available():
    response = request("GET", "/ui")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Orty Web UI" in response.text
    assert "Primary root-user chat interface with conversation continuity." in response.text


def test_root_redirects_to_ui():
    response = request("GET", "/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_ui_home_page_trailing_slash_is_also_available_without_redirect():
    response = request("GET", "/ui/", follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_ui_chat_messages_are_rendered_as_text_nodes():
    response = request("GET", "/ui")

    assert response.status_code == 200
    assert "createTextNode" in response.text
    assert "div.innerHTML" not in response.text


def test_ui_chat_uses_primary_client_auth_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    response = request("POST", "/ui/chat", json={"message": "hello root"})
    assert response.status_code == 200
    assert response.json()["conversation_id"]


def test_chat_returns_generation_metadata(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

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
