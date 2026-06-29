from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration.

    The web application deliberately has no mandatory cloud dependency. The
    existing Telegram/Supabase settings remain optional so those integrations
    can still be enabled without preventing local development from starting.
    """

    TELEGRAM_TOKEN: str = ""
    CHAT_ID: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_BUCKET: str = "cv_storage"
    ENCRYPTION_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"

    DATABASE_PATH: str = str(ROOT_DIR / "data" / "jobert.db")
    UPLOAD_DIR: str = str(ROOT_DIR / "data" / "uploads")
    JOBS_FILE: str = str(ROOT_DIR / "jobs.json")
    SESSION_DAYS: int = 30

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


settings = Settings()
