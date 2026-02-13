import importlib
import pytest


def test_startup_fails_without_secret(monkeypatch):
    # Disable .env loading so tests are deterministic
    monkeypatch.setenv("ORTY_DISABLE_DOTENV", "1")

    # Remove secret from environment
    monkeypatch.delenv("ORTY_SHARED_SECRET", raising=False)

    # Reload config module so Settings re-evaluates
    import service.config
    importlib.reload(service.config)

    # Reload api module to use new settings / checks
    import service.api
    importlib.reload(service.api)

    with pytest.raises(RuntimeError):
        service.api.startup_check()

