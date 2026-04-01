from importlib import reload


def test_llm_provider_defaults_to_ollama_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ORTY_ENV_FILE", raising=False)

    import service.config as config

    reload(config)

    assert config.settings.LLM_PROVIDER == "ollama"


def test_runtime_env_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_PROVIDER=ollama\n", encoding="utf-8")

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ORTY_ENV_FILE", str(env_path))

    import service.config as config

    reload(config)

    assert config.settings.LLM_PROVIDER == "openai"


def test_cloud_fallback_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_CLOUD_FALLBACK", raising=False)
    monkeypatch.delenv("CLOUD_FALLBACK_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_CLOUD_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("ORTY_ENV_FILE", raising=False)

    import service.config as config

    reload(config)

    assert config.settings.ENABLE_CLOUD_FALLBACK is False
    assert config.settings.CLOUD_FALLBACK_PROVIDER == "openai"
    assert config.settings.OLLAMA_CLOUD_FALLBACK_MODEL == "qwen3-coder:480b-cloud"
