import asyncio

import httpx

from service.api import app
from service.config import settings


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


def create_client(name: str) -> dict:
    response = request(
        "POST",
        "/v1/clients",
        json={"name": name},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    assert response.status_code == 200
    return response.json()


def issue_access_token(client_data: dict) -> str:
    response = request(
        "POST",
        "/v1/auth/token",
        json={
            "client_id": client_data["client_id"],
            "client_token": client_data["client_token"],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_bug_report_create_and_list_for_authenticated_client():
    created = create_client("Bug Report Client")
    token = issue_access_token(created)

    response = request(
        "POST",
        "/v1/bug-reports",
        json={
            "client": "alfred-android",
            "title": "Wake word only worked once",
            "summary": "Wake word only worked once",
            "details": "The wake word only worked for the first command.",
            "metadata": {"device": "Galaxy S21"},
            "createdAt": 1234,
        },
        headers=bearer_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["report_id"]

    listed = request("GET", "/v1/bug-reports", headers=bearer_headers(token))
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "Wake word only worked once"
    assert rows[0]["client"] == "alfred-android"
    assert rows[0]["metadata"]["device"] == "Galaxy S21"
    assert rows[0]["createdAt"] == 1234


def test_bug_reports_are_scoped_per_authenticated_client():
    client_a = create_client("Bug Report A")
    client_b = create_client("Bug Report B")
    token_a = issue_access_token(client_a)
    token_b = issue_access_token(client_b)

    response_a = request(
        "POST",
        "/v1/bug-reports",
        json={
            "client": "alfred-android",
            "title": "Issue A",
            "summary": "Issue A",
            "details": "Only client A should see this.",
            "metadata": {},
            "createdAt": 1,
        },
        headers=bearer_headers(token_a),
    )
    assert response_a.status_code == 200

    response_b = request(
        "POST",
        "/v1/bug-reports",
        json={
            "client": "alfred-android",
            "title": "Issue B",
            "summary": "Issue B",
            "details": "Only client B should see this.",
            "metadata": {},
            "createdAt": 2,
        },
        headers=bearer_headers(token_b),
    )
    assert response_b.status_code == 200

    listed_a = request("GET", "/v1/bug-reports", headers=bearer_headers(token_a))
    listed_b = request("GET", "/v1/bug-reports", headers=bearer_headers(token_b))

    rows_a = listed_a.json()
    rows_b = listed_b.json()

    assert [row["title"] for row in rows_a] == ["Issue A"]
    assert [row["title"] for row in rows_b] == ["Issue B"]
