import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from service.api.deps import get_request_auth
from service.api.voice_proxy import voice_proxy_gateway
from service.models.schemas import SpeechSynthesizeRequest, SpeechSynthesizeResponse

router = APIRouter(prefix="/v1/tts", tags=["v1-tts"])


@router.post("/synthesize", response_model=SpeechSynthesizeResponse)
async def synthesize_speech(
    payload: SpeechSynthesizeRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    del request, auth

    api_key = (payload.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Google TTS API key is missing.")

    request_body = {
        "input": {
            "text": payload.text.strip(),
        },
        "voice": {
            "languageCode": payload.language_code.strip() or "en-US",
        },
        "audioConfig": {
            "audioEncoding": payload.audio_encoding.strip() or "MP3",
            "speakingRate": payload.speaking_rate,
            "pitch": payload.pitch,
        },
    }
    voice_name = (payload.voice_name or "").strip()
    if voice_name:
        request_body["voice"]["name"] = voice_name

    try:
        response = await _post_google_tts(api_key=api_key, request_body=request_body)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Google TTS request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Google TTS failed: {response.status_code} {response.reason_phrase}".strip(),
        )

    parsed = response.json() if response.content else {}
    audio_base64 = (parsed.get("audioContent") or "").strip()
    if not audio_base64:
        raise HTTPException(status_code=502, detail="Google TTS returned no audio.")

    return SpeechSynthesizeResponse(
        audio_base64=audio_base64,
        audio_encoding=(payload.audio_encoding.strip() or "MP3").upper(),
    )


async def _post_google_tts(api_key: str, request_body: dict) -> httpx.Response:
    return await voice_proxy_gateway.post_google_tts(
        api_key=api_key,
        request_body=request_body,
    )
