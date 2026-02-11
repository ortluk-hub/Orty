import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    ORTY_SHARED_SECRET: str = os.getenv("ORTY_SHARED_SECRET", "dev-secret")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

settings = Settings()

