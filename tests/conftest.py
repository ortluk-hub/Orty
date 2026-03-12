import asyncio
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path):
    from service.api import app
    from service.api.deps import reset_runtime

    runtime = reset_runtime(str(tmp_path / "orty-test.db"))
    app.state.runtime = runtime
    yield
    try:
        asyncio.run(runtime.bot_runner.shutdown())
    except RuntimeError:
        # Async tests already have an active loop, so cancel any leftover bot
        # tasks directly instead of skipping teardown.
        for task in list(runtime.bot_runner.tasks.values()):
            if not task.done():
                task.cancel()
        runtime.bot_runner._prune_finished_tasks()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    from service.api import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
