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

        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()

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
        self.CLOUD_FALLBACK_PROVIDER: str = os.getenv("CLOUD_FALLBACK_PROVIDER", "openai").lower()

        self.SQLITE_PATH: str = os.getenv("SQLITE_PATH", "data/orty.db")
        self.SQLITE_TIMEOUT_SECONDS: float = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "5"))

        self.FS_READ_ROOT: str = os.getenv("FS_READ_ROOT", ".")
        self.SMART_HOME_PROVIDER: str = os.getenv("SMART_HOME_PROVIDER", "").strip().lower()
        self.SMARTTHINGS_PAT: str | None = os.getenv("SMARTTHINGS_PAT")
        self.SMARTTHINGS_DEVICE_MAP: str = os.getenv("SMARTTHINGS_DEVICE_MAP", "{}")

        self.BOT_HEARTBEAT_DEFAULT_SECONDS: int = int(os.getenv("BOT_HEARTBEAT_DEFAULT_SECONDS", "10"))
        self.BOT_RUNNER_MAX_BOTS: int = int(os.getenv("BOT_RUNNER_MAX_BOTS", "25"))
        self.CLIENT_ACCESS_TOKEN_TTL_SECONDS: int = int(os.getenv("CLIENT_ACCESS_TOKEN_TTL_SECONDS", "3600"))
        self.ALLOW_LEGACY_CLIENT_HEADERS: bool = os.getenv(
            "ALLOW_LEGACY_CLIENT_HEADERS", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}


settings = Settings()
