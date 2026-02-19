import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ROOT_ENV_FILE = Path(os.getenv("ORTY_ENV_FILE", str(DEFAULT_ROOT_ENV_FILE))).expanduser()
load_dotenv(dotenv_path=ROOT_ENV_FILE, override=True)


class Settings:
    def __init__(self) -> None:
        self.ORTY_SHARED_SECRET: str = os.getenv("ORTY_SHARED_SECRET", "dev-secret")

        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()

        self.OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")

        self.SQLITE_PATH: str = os.getenv("SQLITE_PATH", "data/orty.db")
        self.SQLITE_TIMEOUT_SECONDS: float = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "5"))

        self.FS_READ_ROOT: str = os.getenv("FS_READ_ROOT", ".")

        self.BOT_HEARTBEAT_DEFAULT_SECONDS: int = int(os.getenv("BOT_HEARTBEAT_DEFAULT_SECONDS", "10"))
        self.BOT_RUNNER_MAX_BOTS: int = int(os.getenv("BOT_RUNNER_MAX_BOTS", "25"))


settings = Settings()
