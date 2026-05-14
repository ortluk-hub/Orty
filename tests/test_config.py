from importlib import reload


def test_llm_provider_defaults_to_ollama_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ORTY_ENV_FILE", str(env_path))

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


def test_cloud_fallback_defaults_to_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_CLOUD_FALLBACK", raising=False)
    monkeypatch.delenv("ENABLE_PARALLEL_PROVIDER_RACE", raising=False)
    monkeypatch.delenv("CLOUD_FALLBACK_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_CLOUD_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ORTY_DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.delenv("ENABLE_BOT_CONTROL_SURFACE", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ORTY_ENV_FILE", str(env_path))

    import service.config as config

    reload(config)

    assert config.settings.ENABLE_CLOUD_FALLBACK is False
    assert config.settings.ENABLE_PARALLEL_PROVIDER_RACE is False
    assert config.settings.CLOUD_FALLBACK_PROVIDER == "openai"
    assert config.settings.OLLAMA_CLOUD_FALLBACK_MODEL == "qwen3-coder:480b-cloud"
    assert config.settings.DATABASE_URL is None
    assert config.settings.ORTY_DEPLOYMENT_PROFILE == "default"
    assert config.settings.ENABLE_BOT_CONTROL_SURFACE is True


def test_cloud_run_interactive_profile_disables_bot_control_surface(monkeypatch):
    monkeypatch.setenv("ORTY_DEPLOYMENT_PROFILE", "cloud_run_interactive")
    monkeypatch.delenv("ENABLE_BOT_CONTROL_SURFACE", raising=False)
    monkeypatch.delenv("ORTY_ENV_FILE", raising=False)

    import service.config as config

    reload(config)

    assert config.settings.ORTY_DEPLOYMENT_PROFILE == "cloud_run_interactive"
    assert config.settings.ENABLE_BOT_CONTROL_SURFACE is False



def test_cloud_run_interactive_profile_defaults_to_vertex_ai_and_disables_legacy_client_headers(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ALLOW_LEGACY_CLIENT_HEADERS", raising=False)
    monkeypatch.setenv("ORTY_DEPLOYMENT_PROFILE", "cloud_run_interactive")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ORTY_ENV_FILE", str(env_path))

    import service.config as config

    reload(config)

    assert config.settings.LLM_PROVIDER == "vertex_ai"
    assert config.settings.ALLOW_LEGACY_CLIENT_HEADERS is False
