import os


# Allow tests / CI to disable .env loading for deterministic behavior.
# If this is NOT set, local dev can still use a .env file.
if os.getenv("ORTY_DISABLE_DOTENV") != "1":
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except ImportError:
        pass


class Settings:
    def __init__(self) -> None:
        # Secret used by x-orty-secret header auth
        self.ORTY_SHARED_SECRET: str | None = os.getenv("ORTY_SHARED_SECRET")

        # Optional OpenAI settings (if you use them)
        self.OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Optional DB path (if you use it)
        self.ORTY_DATABASE_PATH: str = os.getenv("ORTY_DATABASE_PATH", "orty.db")


# Convenience instance (fine for app runtime; tests can reload module)
settings = Settings()

