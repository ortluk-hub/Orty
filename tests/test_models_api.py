import asyncio
import hashlib

import httpx

from service.api import app
from service.config import settings


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


def test_model_registry_is_public_and_empty_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ORTY_MODEL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ORTY_ADMIN_SECRET", "model-secret")

    response = request("GET", "/v1/models")

    assert response.status_code == 200
    assert response.json() == []


def test_model_upload_registers_registry_and_streams_download(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ORTY_MODEL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ORTY_ADMIN_SECRET", "model-secret")

    model_id = "llama-3-8b-instruct-q4_k_m.gguf"
    model_bytes = b"gguf-model-bytes"
    expected_sha256 = hashlib.sha256(model_bytes).hexdigest()

    upload = request(
        "POST",
        "/v1/admin/models/upload",
        params={"model_id": model_id},
        files={"file": (model_id, model_bytes, "application/octet-stream")},
        data={"name": "Llama 3 8B (Medium Quant)"},
        headers={"x-orty-admin-secret": "model-secret"},
    )

    assert upload.status_code == 200
    uploaded = upload.json()
    assert uploaded == {
        "id": model_id,
        "name": "Llama 3 8B (Medium Quant)",
        "size_bytes": len(model_bytes),
        "sha256": expected_sha256,
        "is_default": True,
    }

    stored_path = tmp_path / model_id
    assert stored_path.is_file()
    assert stored_path.read_bytes() == model_bytes

    registry = request("GET", "/v1/models")
    assert registry.status_code == 200
    assert registry.json() == [uploaded]

    download = request("GET", f"/v1/models/{model_id}/download")
    assert download.status_code == 200
    assert download.content == model_bytes
    assert download.headers["content-disposition"].startswith("attachment; filename=")
    assert download.headers["content-type"] == "application/octet-stream"


def test_model_upload_requires_admin_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ORTY_MODEL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ORTY_ADMIN_SECRET", "model-secret")

    response = request(
        "POST",
        "/v1/admin/models/upload",
        params={"model_id": "blocked.gguf"},
        files={"file": ("blocked.gguf", b"data", "application/octet-stream")},
        headers={"x-orty-admin-secret": "wrong-secret"},
    )

    assert response.status_code == 401


def test_model_upload_rejects_invalid_model_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ORTY_MODEL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ORTY_ADMIN_SECRET", "model-secret")

    response = request(
        "POST",
        "/v1/admin/models/upload",
        params={"model_id": "../escape.gguf"},
        files={"file": ("escape.gguf", b"data", "application/octet-stream")},
        headers={"x-orty-admin-secret": "model-secret"},
    )

    assert response.status_code == 400
