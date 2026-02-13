from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from service.config import Settings
from service.security import verify_secret as require_secret


def startup_check() -> None:
    """
    Validates required configuration at app startup.
    Kept as a plain function so tests can call it directly.
    """
    s = Settings()
    if not s.ORTY_SHARED_SECRET:
        raise RuntimeError("ORTY_SHARED_SECRET is required to start Orty.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    startup_check()
    yield
    # Shutdown (optional cleanup goes here)


app = FastAPI(lifespan=lifespan)


class TextRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/text", dependencies=[Depends(require_secret)])
def text_endpoint(payload: TextRequest):
    """
    Primary text endpoint.
    Uses your AI module if available; otherwise just echoes.
    """
    try:
        from service.ai import generate_text  # type: ignore
        reply = generate_text(payload.text)
    except Exception:
        reply = f"Orty heard you: {payload.text}"

    return {"reply": reply}

