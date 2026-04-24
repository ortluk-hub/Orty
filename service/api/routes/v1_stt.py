import base64

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from service.api.deps import get_request_auth
from service.api.voice_proxy import voice_proxy_gateway
from service.models.schemas import SpeechRecognizeRequest, SpeechRecognizeResponse

router = APIRouter(prefix="/v1/stt", tags=["v1-stt"])


@router.post("/recognize", response_model=SpeechRecognizeResponse)
async def recognize_speech(
    payload: SpeechRecognizeRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    del request, auth

    api_key = (payload.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Google STT API key is missing.")

    try:
        base64.b64decode(payload.audio_base64, validate=True)
    except Exception as exc:  # pragma: no cover - exact type is not important here
        raise HTTPException(status_code=422, detail="audio_base64 is not valid base64.") from exc

    request_body = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16_000,
            "languageCode": payload.language_code.strip() or "en-US",
            "enableAutomaticPunctuation": True,
            "model": "latest_short",
        },
        "audio": {
            "content": payload.audio_base64,
        },
    }

    try:
        response = await _post_google_speech(api_key=api_key, request_body=request_body)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Google STT request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Google STT failed: {response.status_code} {response.reason_phrase}".strip(),
        )

    parsed = response.json() if response.content else {}
    transcript = None
    for result in parsed.get("results") or []:
        alternatives = result.get("alternatives") or []
        candidate = ((alternatives[0] or {}).get("transcript") if alternatives else None) or ""
        candidate = candidate.strip()
        if candidate:
            transcript = candidate
            break

    return SpeechRecognizeResponse(
        transcript=transcript,
        no_speech=not bool(transcript),
    )


async def _post_google_speech(api_key: str, request_body: dict) -> httpx.Response:
    return await voice_proxy_gateway.post_google_speech(
        api_key=api_key,
        request_body=request_body,
    )
