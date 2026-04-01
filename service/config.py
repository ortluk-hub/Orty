import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ROOT_ENV_FILE = Path(os.getenv("ORTY_ENV_FILE", str(DEFAULT_ROOT_ENV_FILE))).expanduser()
# Keep runtime/exported environment variables authoritative and only use
# values from the env file for missing keys.
load_dotenv(dotenv_path=ROOT_ENV_FILE, override=False)


class Settings:
    def __init__(self) -> None:
        self.ORTY_SHARED_SECRET: str = os.getenv("ORTY_SHARED_SECRET", "dev-secret")
        self.ORTY_DEPLOYMENT_PROFILE: str = os.getenv("ORTY_DEPLOYMENT_PROFILE", "default").strip().lower()

        default_llm_provider = "vertex_ai" if self.ORTY_DEPLOYMENT_PROFILE == "cloud_run_interactive" else "ollama"
        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", default_llm_provider).lower()

        self.OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
        self.OLLAMA_CLOUD_FALLBACK_MODEL: str = os.getenv(
            "OLLAMA_CLOUD_FALLBACK_MODEL", "qwen3-coder:480b-cloud"
        )
        self.ENABLE_CLOUD_FALLBACK: bool = os.getenv(
            "ENABLE_CLOUD_FALLBACK", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        default_cloud_fallback_provider = "vertex_ai" if self.ORTY_DEPLOYMENT_PROFILE == "cloud_run_interactive" else "openai"
        self.CLOUD_FALLBACK_PROVIDER: str = os.getenv("CLOUD_FALLBACK_PROVIDER", default_cloud_fallback_provider).lower()
        self.ENABLE_PARALLEL_PROVIDER_RACE: bool = os.getenv(
            "ENABLE_PARALLEL_PROVIDER_RACE", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

        self.DATABASE_URL: str | None = (os.getenv("DATABASE_URL") or "").strip() or None
        self.DATABASE_CONNECT_TIMEOUT_SECONDS: float = float(
            os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", os.getenv("SQLITE_TIMEOUT_SECONDS", "5"))
        )
        self.SQLITE_PATH: str = os.getenv("SQLITE_PATH", "data/orty.db")
        self.SQLITE_TIMEOUT_SECONDS: float = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "5"))

        self.FS_READ_ROOT: str = os.getenv("FS_READ_ROOT", ".")
        self.SMART_HOME_PROVIDER: str = os.getenv("SMART_HOME_PROVIDER", "").strip().lower()
        self.SMARTTHINGS_PAT: str | None = os.getenv("SMARTTHINGS_PAT")
        self.SMARTTHINGS_DEVICE_MAP: str = os.getenv("SMARTTHINGS_DEVICE_MAP", "{}")
        self.SMARTTHINGS_GROUP_MAP: str = os.getenv("SMARTTHINGS_GROUP_MAP", "{}")

        self.BOT_HEARTBEAT_DEFAULT_SECONDS: int = int(os.getenv("BOT_HEARTBEAT_DEFAULT_SECONDS", "10"))
        self.BOT_RUNNER_MAX_BOTS: int = int(os.getenv("BOT_RUNNER_MAX_BOTS", "25"))
        raw_enable_bot_control = os.getenv("ENABLE_BOT_CONTROL_SURFACE")
        if raw_enable_bot_control is None:
            self.ENABLE_BOT_CONTROL_SURFACE: bool = self.ORTY_DEPLOYMENT_PROFILE != "cloud_run_interactive"
        else:
            self.ENABLE_BOT_CONTROL_SURFACE = raw_enable_bot_control.strip().lower() in {"1", "true", "yes", "on"}
        self.CLIENT_ACCESS_TOKEN_TTL_SECONDS: int = int(os.getenv("CLIENT_ACCESS_TOKEN_TTL_SECONDS", "3600"))
        default_allow_legacy_headers = "false" if self.ORTY_DEPLOYMENT_PROFILE == "cloud_run_interactive" else "true"
        self.ALLOW_LEGACY_CLIENT_HEADERS: bool = os.getenv(
            "ALLOW_LEGACY_CLIENT_HEADERS", default_allow_legacy_headers
        ).strip().lower() in {"1", "true", "yes", "on"}

        # Codey integration settings
        self.CODEY_URL: str | None = os.getenv("CODEY_URL")
        self.CODEY_API_KEY: str | None = os.getenv("CODEY_API_KEY")
        self.CODEY_ALFRED_WORKSPACE: str = os.getenv("CODEY_ALFRED_WORKSPACE", "")
        self.ALFRED_DOCS_ROOT: str | None = (os.getenv("ALFRED_DOCS_ROOT") or "").strip() or None

        # Vertex AI configuration
        self.VERTEX_AI_PROJECT_ID: str | None = os.getenv("VERTEX_AI_PROJECT_ID")
        self.VERTEX_AI_LOCATION: str | None = os.getenv("VERTEX_AI_LOCATION")
        self.VERTEX_AI_MODEL_ID: str | None = os.getenv("VERTEX_AI_MODEL_ID")
        self.VERTEX_AI_CREDENTIALS_PATH: str | None = os.getenv("VERTEX_AI_CREDENTIALS_PATH")

        self.VOICE_PROXY_MAX_CONCURRENT_STT: int = int(
            os.getenv("VOICE_PROXY_MAX_CONCURRENT_STT", "6")
        )
        self.VOICE_PROXY_MAX_CONCURRENT_TTS: int = int(
            os.getenv("VOICE_PROXY_MAX_CONCURRENT_TTS", "4")
        )
        self.VOICE_PROXY_MAX_CONNECTIONS: int = int(
            os.getenv("VOICE_PROXY_MAX_CONNECTIONS", "12")
        )
        self.VOICE_PROXY_MAX_KEEPALIVE_CONNECTIONS: int = int(
            os.getenv("VOICE_PROXY_MAX_KEEPALIVE_CONNECTIONS", "6")
        )
        self.VOICE_PROXY_CONNECT_TIMEOUT_SECONDS: float = float(
            os.getenv("VOICE_PROXY_CONNECT_TIMEOUT_SECONDS", "10")
        )
        self.VOICE_PROXY_READ_TIMEOUT_SECONDS: float = float(
            os.getenv("VOICE_PROXY_READ_TIMEOUT_SECONDS", "30")
        )
        self.VOICE_PROXY_WRITE_TIMEOUT_SECONDS: float = float(
            os.getenv("VOICE_PROXY_WRITE_TIMEOUT_SECONDS", "30")
        )
        self.VOICE_PROXY_POOL_TIMEOUT_SECONDS: float = float(
            os.getenv("VOICE_PROXY_POOL_TIMEOUT_SECONDS", "10")
        )


settings = Settings()
