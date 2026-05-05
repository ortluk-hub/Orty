import hashlib
import hmac
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from service.config import settings
from service.models.schemas import ModelRegistryItemResponse


logger = logging.getLogger("orty.models")

router = APIRouter(prefix="/v1/models", tags=["v1-models"])
admin_router = APIRouter(prefix="/v1/admin/models", tags=["v1-models"])

MODEL_SUFFIX = ".gguf"
REGISTRY_FILENAME = "registry.json"
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _model_root() -> Path:
    return Path(settings.ORTY_MODEL_STORAGE_ROOT).expanduser()


def _configured_default_model_id() -> str | None:
    candidate = (settings.ORTY_DEFAULT_MODEL_ID or "").strip()
    if candidate and _is_valid_model_id(candidate):
        return candidate
    return None


def _registry_path(root: Path) -> Path:
    return root / REGISTRY_FILENAME


def _is_valid_model_id(model_id: str) -> bool:
    candidate = model_id.strip()
    return bool(
        candidate
        and candidate.endswith(MODEL_SUFFIX)
        and len(candidate) <= 255
        and candidate == Path(candidate).name
        and "/" not in candidate
        and "\\" not in candidate
        and candidate not in {".", ".."}
        and not candidate.startswith(".")
    )


def _validate_model_id(model_id: str) -> str:
    candidate = model_id.strip()
    if not _is_valid_model_id(candidate):
        raise HTTPException(status_code=400, detail="Invalid model_id")
    return candidate


def _default_model_name(model_id: str) -> str:
    base_name = model_id[: -len(MODEL_SUFFIX)]
    friendly = base_name.replace("-", " ").replace("_", " ").strip()
    return friendly.title() if friendly else model_id


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(UPLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_registry_payload(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("model_registry_invalid path=%s", path)
        return {}
    if isinstance(payload, dict):
        return payload
    logger.warning("model_registry_non_object path=%s", path)
    return {}


def _write_registry_payload(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = _registry_path(root)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _build_entry_from_file(
    path: Path,
    *,
    name: str | None = None,
    sha256: str | None = None,
    size_bytes: int | None = None,
    is_default: bool = False,
) -> dict[str, Any]:
    resolved_name = name.strip() if isinstance(name, str) and name.strip() else _default_model_name(path.name)
    resolved_size = size_bytes if size_bytes is not None else path.stat().st_size
    resolved_sha = sha256.strip() if isinstance(sha256, str) and sha256.strip() else _sha256_file(path)
    return {
        "id": path.name,
        "name": resolved_name,
        "size_bytes": resolved_size,
        "sha256": resolved_sha,
        "is_default": is_default,
    }


def _choose_default_model_id(entries: list[dict[str, Any]], registry_default_id: str | None) -> str | None:
    if registry_default_id and any(entry["id"] == registry_default_id for entry in entries):
        return registry_default_id
    explicit_defaults = [entry["id"] for entry in entries if entry.get("is_default")]
    if explicit_defaults:
        return explicit_defaults[0]
    if len(entries) == 1:
        return entries[0]["id"]
    return None


def _sort_model_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: (
            not bool(entry.get("is_default")),
            str(entry.get("name", "")).lower(),
            str(entry.get("id", "")).lower(),
        ),
    )


def _list_model_entries(root: Path) -> list[dict[str, Any]]:
    payload = _load_registry_payload(root)
    registry_default_id = payload.get("default_model_id")
    if isinstance(registry_default_id, str):
        registry_default_id = registry_default_id.strip() or None
        if registry_default_id and not _is_valid_model_id(registry_default_id):
            registry_default_id = None
    else:
        registry_default_id = None
    if registry_default_id is None:
        registry_default_id = _configured_default_model_id()

    entries_by_id: dict[str, dict[str, Any]] = {}
    raw_models = payload.get("models", [])
    if isinstance(raw_models, list):
        for raw_entry in raw_models:
            if not isinstance(raw_entry, dict):
                continue
            raw_model_id = raw_entry.get("id")
            if not isinstance(raw_model_id, str):
                continue
            model_id = raw_model_id.strip()
            if not _is_valid_model_id(model_id):
                continue
            path = root / model_id
            if not path.is_file():
                continue
            entry = _build_entry_from_file(
                path,
                name=raw_entry.get("name") if isinstance(raw_entry.get("name"), str) else None,
                sha256=raw_entry.get("sha256") if isinstance(raw_entry.get("sha256"), str) else None,
                size_bytes=_coerce_int(raw_entry.get("size_bytes")),
                is_default=bool(raw_entry.get("is_default")) or model_id == registry_default_id,
            )
            entries_by_id[model_id] = entry

    if root.is_dir():
        for path in sorted(root.glob(f"*{MODEL_SUFFIX}")):
            model_id = path.name
            if model_id in entries_by_id:
                continue
            entries_by_id[model_id] = _build_entry_from_file(
                path,
                is_default=model_id == registry_default_id,
            )

    entries = _sort_model_entries(list(entries_by_id.values()))
    default_model_id = _choose_default_model_id(entries, registry_default_id)
    if default_model_id:
        for entry in entries:
            entry["is_default"] = entry["id"] == default_model_id
    return entries


def _require_admin_secret(x_orty_admin_secret: str | None) -> None:
    configured_secret = (settings.ORTY_ADMIN_SECRET or "").strip()
    if not configured_secret:
        raise HTTPException(status_code=503, detail="Model upload is not configured")
    if x_orty_admin_secret is None or not hmac.compare_digest(x_orty_admin_secret, configured_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _resolve_download_path(root: Path, model_id: str) -> Path:
    resolved_root = root.resolve(strict=False)
    candidate = (root / model_id).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid model_id") from exc
    return candidate


@router.get("", response_model=list[ModelRegistryItemResponse])
async def list_models() -> list[ModelRegistryItemResponse]:
    root = _model_root()
    return [ModelRegistryItemResponse(**entry) for entry in _list_model_entries(root)]


@router.get("/{model_id}/download")
async def download_model(model_id: str):
    normalized_model_id = _validate_model_id(model_id)
    root = _model_root()
    path = _resolve_download_path(root, normalized_model_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Model not found")
    return FileResponse(path, media_type="application/octet-stream", filename=normalized_model_id)


@admin_router.post("/upload", response_model=ModelRegistryItemResponse)
async def upload_model(
    model_id: str = Query(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    name: str | None = Form(default=None, max_length=200),
    is_default: bool = Form(default=False),
    x_orty_admin_secret: str | None = Header(default=None, alias="x-orty-admin-secret"),
) -> ModelRegistryItemResponse:
    _require_admin_secret(x_orty_admin_secret)
    normalized_model_id = _validate_model_id(model_id)

    root = _model_root()
    root.mkdir(parents=True, exist_ok=True)
    target_path = _resolve_download_path(root, normalized_model_id)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.upload.tmp")

    total_bytes = 0
    digest = hashlib.sha256()
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                total_bytes += len(chunk)
        if total_bytes <= 0:
            raise HTTPException(status_code=400, detail="Uploaded model is empty")
        temp_path.replace(target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    entries = _list_model_entries(root)
    entries_by_id = {entry["id"]: entry for entry in entries}
    existing_entry = entries_by_id.get(normalized_model_id)
    existing_default_id = _choose_default_model_id(entries, _configured_default_model_id())
    resolved_name = (
        name.strip()
        if isinstance(name, str) and name.strip()
        else (existing_entry["name"] if existing_entry else _default_model_name(normalized_model_id))
    )
    entry_is_default = bool(is_default)
    if existing_entry and existing_entry.get("is_default"):
        entry_is_default = True
    if not entries:
        entry_is_default = True
    if existing_default_id == normalized_model_id:
        entry_is_default = True

    entries_by_id[normalized_model_id] = {
        "id": normalized_model_id,
        "name": resolved_name,
        "size_bytes": total_bytes,
        "sha256": digest.hexdigest(),
        "is_default": entry_is_default,
    }
    normalized_entries = _sort_model_entries(list(entries_by_id.values()))
    default_model_id = normalized_model_id if entry_is_default else existing_default_id
    if default_model_id is None and len(normalized_entries) == 1:
        default_model_id = normalized_entries[0]["id"]
    for entry in normalized_entries:
        entry["is_default"] = entry["id"] == default_model_id

    _write_registry_payload(
        root,
        {
            "default_model_id": default_model_id,
            "models": normalized_entries,
        },
    )

    return ModelRegistryItemResponse(**entries_by_id[normalized_model_id])
