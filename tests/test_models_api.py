import asyncio
import hashlib
import json

import httpx

from service.api import app
from service.config import settings


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


def test_model_registry_is_public_and_empty_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'ORTY_ADMIN_SECRET', 'model-secret')

    response = request('GET', '/v1/models')

    assert response.status_code == 200
    assert response.json() == []


def test_model_download_link_is_public(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setattr(
        settings,
        'ORTY_MODEL_PUBLIC_URL_TEMPLATE',
        'https://storage.example/models/{model_id}',
    )

    model_id = 'Qwen2.5-0.5B-Instruct_seq128_q8_ekv1280.tflite'
    response = request(
        'GET',
        '/v1/admin/models/download-link',
        params={'model_id': model_id},
    )

    assert response.status_code == 200
    assert response.json() == {
        'model_id': model_id,
        'download_url': f'https://storage.example/models/{model_id}',
        'filename': model_id,
    }


def test_model_registry_includes_public_entries_without_local_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))

    model_id = 'Qwen2.5-0.5B-Instruct_seq128_q8_ekv1280.tflite'
    download_url = (
        'https://huggingface.co/litert-community/Qwen2.5-0.5B-Instruct/resolve/main/'
        f'{model_id}'
    )
    registry_payload = {
        'default_model_id': model_id,
        'models': [
            {
                'id': model_id,
                'name': 'Qwen2.5 0.5B Instruct Q8',
                'size_bytes': 513219800,
                'sha256': '',
                'download_url': download_url,
                'is_default': True,
            }
        ],
    }
    (tmp_path / 'registry.json').write_text(json.dumps(registry_payload), encoding='utf-8')

    registry = request('GET', '/v1/models')
    assert registry.status_code == 200
    assert registry.json() == [
        {
            'id': model_id,
            'name': 'Qwen2.5 0.5B Instruct Q8',
            'size_bytes': 513219800,
            'sha256': '',
            'is_default': True,
        }
    ]

    download_link = request('GET', '/v1/admin/models/download-link', params={'model_id': model_id})
    assert download_link.status_code == 200
    assert download_link.json() == {
        'model_id': model_id,
        'download_url': download_url,
        'filename': model_id,
    }


def test_model_upload_registers_registry_and_streams_download(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'ORTY_ADMIN_SECRET', 'model-secret')

    model_id = 'demo-model.tflite'
    model_bytes = b'tflite-model-bytes'
    expected_sha256 = hashlib.sha256(model_bytes).hexdigest()

    upload = request(
        'POST',
        '/v1/admin/models/upload',
        params={'model_id': model_id},
        files={'file': (model_id, model_bytes, 'application/octet-stream')},
        data={'name': 'Demo TFLite Model'},
        headers={'x-orty-admin-secret': 'model-secret'},
    )

    assert upload.status_code == 200
    uploaded = upload.json()
    assert uploaded == {
        'id': model_id,
        'name': 'Demo TFLite Model',
        'size_bytes': len(model_bytes),
        'sha256': expected_sha256,
        'is_default': True,
    }

    stored_path = tmp_path / model_id
    assert stored_path.is_file()
    assert stored_path.read_bytes() == model_bytes

    registry = request('GET', '/v1/models')
    assert registry.status_code == 200
    assert registry.json() == [uploaded]

    download = request('GET', f'/v1/models/{model_id}/download')
    assert download.status_code == 200
    assert download.content == model_bytes
    assert download.headers['content-disposition'].startswith('attachment; filename=')
    assert download.headers['content-type'] == 'application/octet-stream'


def test_model_upload_requires_admin_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'ORTY_ADMIN_SECRET', 'model-secret')

    response = request(
        'POST',
        '/v1/admin/models/upload',
        params={'model_id': 'blocked.tflite'},
        files={'file': ('blocked.tflite', b'data', 'application/octet-stream')},
        headers={'x-orty-admin-secret': 'wrong-secret'},
    )

    assert response.status_code == 401


def test_model_upload_rejects_invalid_model_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ORTY_MODEL_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setattr(settings, 'ORTY_ADMIN_SECRET', 'model-secret')

    response = request(
        'POST',
        '/v1/admin/models/upload',
        params={'model_id': '../escape.tflite'},
        files={'file': ('escape.tflite', b'data', 'application/octet-stream')},
        headers={'x-orty-admin-secret': 'model-secret'},
    )

    assert response.status_code == 400
