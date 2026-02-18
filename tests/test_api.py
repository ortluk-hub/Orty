from fastapi.testclient import TestClient

from service.api import app
from service.config import settings


client = TestClient(app)


def test_health_endpoint_returns_ok_and_assistant_name():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "assistant": "Orty"}


def test_chat_requires_shared_secret_header():
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 422


def test_chat_rejects_invalid_shared_secret():
    response = client.post(
        "/chat",
        json={"message": "hello"},
        headers={"x-orty-secret": "invalid-secret"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_chat_returns_configuration_message_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    response = client.post(
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

    first = client.post(
        "/chat",
        json={"message": "one"},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    first_id = first.json()["conversation_id"]

    second = client.post(
        "/chat",
        json={"message": "two", "conversation_id": first_id},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == first_id


def test_ui_home_page_is_available():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Orty Web UI" in response.text
    assert "Simple testing interface for chat + conversation continuity." in response.text
