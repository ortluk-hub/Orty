import asyncio

import httpx

from service.api.voice_proxy import VoiceProxyGateway


class FakeAsyncClient:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False
        self.active_requests = 0
        self.max_active_requests = 0

    async def post(self, url: str, params: dict, json: dict) -> httpx.Response:
        self.calls.append((url, params, json))
        self.active_requests += 1
        self.max_active_requests = max(self.max_active_requests, self.active_requests)
        try:
            await asyncio.sleep(0.01)
            return httpx.Response(status_code=200, json={"ok": True})
        finally:
            self.active_requests -= 1

    async def aclose(self) -> None:
        self.closed = True


def test_voice_proxy_reuses_clients_and_closes_them() -> None:
    gateway = VoiceProxyGateway()
    stt_client = FakeAsyncClient()
    tts_client = FakeAsyncClient()
    built = [stt_client, tts_client]

    gateway._build_client = lambda: built.pop(0)  # type: ignore[method-assign]

    async def scenario() -> None:
        await gateway.post_google_speech("key-1", {"one": 1})
        await gateway.post_google_speech("key-2", {"two": 2})
        await gateway.post_google_tts("key-3", {"three": 3})
        await gateway.aclose()

    asyncio.run(scenario())

    assert len(stt_client.calls) == 2
    assert len(tts_client.calls) == 1
    assert stt_client.closed is True
    assert tts_client.closed is True


def test_voice_proxy_limits_concurrent_stt_requests() -> None:
    gateway = VoiceProxyGateway()
    stt_client = FakeAsyncClient()
    gateway._stt_client = stt_client
    gateway._stt_semaphore = asyncio.Semaphore(1)

    async def scenario() -> None:
        await asyncio.gather(
            gateway.post_google_speech("key-1", {"request": 1}),
            gateway.post_google_speech("key-2", {"request": 2}),
        )

    asyncio.run(scenario())

    assert len(stt_client.calls) == 2
    assert stt_client.max_active_requests == 1
