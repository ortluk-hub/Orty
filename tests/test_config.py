from importlib import reload


def test_llm_provider_defaults_to_ollama_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ORTY_ENV_FILE", raising=False)

    import service.config as config

    reload(config)

    assert config.settings.LLM_PROVIDER == "ollama"


def test_dotenv_overrides_existing_env_value(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_PROVIDER=ollama\n", encoding="utf-8")

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ORTY_ENV_FILE", str(env_path))

    import service.config as config

    reload(config)

    assert config.settings.LLM_PROVIDER == "ollama"
