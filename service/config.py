import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    ORTY_SHARED_SECRET: str = os.getenv("ORTY_SHARED_SECRET", "dev-secret")

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "data/orty.db")
    SQLITE_TIMEOUT_SECONDS: float = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "5"))


settings = Settings()
