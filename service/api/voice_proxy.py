import asyncio

import httpx

from service.config import settings


class VoiceProxyGateway:
    def __init__(self) -> None:
        self._stt_client: httpx.AsyncClient | None = None
        self._tts_client: httpx.AsyncClient | None = None
        self._stt_lock = asyncio.Lock()
        self._tts_lock = asyncio.Lock()
        self._stt_semaphore = asyncio.Semaphore(settings.VOICE_PROXY_MAX_CONCURRENT_STT)
        self._tts_semaphore = asyncio.Semaphore(settings.VOICE_PROXY_MAX_CONCURRENT_TTS)

    async def post_google_speech(self, api_key: str, request_body: dict) -> httpx.Response:
        async with self._stt_semaphore:
            client = await self._get_stt_client()
            return await client.post(
                "https://speech.googleapis.com/v1/speech:recognize",
                params={"key": api_key},
                json=request_body,
            )

    async def post_google_tts(self, api_key: str, request_body: dict) -> httpx.Response:
        async with self._tts_semaphore:
            client = await self._get_tts_client()
            return await client.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                params={"key": api_key},
                json=request_body,
            )

    async def aclose(self) -> None:
        clients = [self._stt_client, self._tts_client]
        self._stt_client = None
        self._tts_client = None
        for client in clients:
            if client is not None:
                await client.aclose()

    async def _get_stt_client(self) -> httpx.AsyncClient:
        if self._stt_client is not None:
            return self._stt_client
        async with self._stt_lock:
            if self._stt_client is None:
                self._stt_client = self._build_client()
        return self._stt_client

    async def _get_tts_client(self) -> httpx.AsyncClient:
        if self._tts_client is not None:
            return self._tts_client
        async with self._tts_lock:
            if self._tts_client is None:
                self._tts_client = self._build_client()
        return self._tts_client

    def _build_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            connect=settings.VOICE_PROXY_CONNECT_TIMEOUT_SECONDS,
            read=settings.VOICE_PROXY_READ_TIMEOUT_SECONDS,
            write=settings.VOICE_PROXY_WRITE_TIMEOUT_SECONDS,
            pool=settings.VOICE_PROXY_POOL_TIMEOUT_SECONDS,
        )
        limits = httpx.Limits(
            max_connections=settings.VOICE_PROXY_MAX_CONNECTIONS,
            max_keepalive_connections=settings.VOICE_PROXY_MAX_KEEPALIVE_CONNECTIONS,
        )
        return httpx.AsyncClient(timeout=timeout, limits=limits)


voice_proxy_gateway = VoiceProxyGateway()
