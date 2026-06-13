from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env files by absolute path so settings load regardless of the
# process working directory (uvicorn/celery/scripts may run from anywhere).
# apps/api/app/config.py -> parents[1] == apps/api, parents[3] == repo root.
_API_ENV = Path(__file__).resolve().parents[1] / ".env"
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    github_token: str = ""
    google_api_key: str = ""
    embedding_model: str = "models/gemini-embedding-001"
    brain_llm_model: str = "gemini-2.5-flash"
    clone_base_dir: str = "/tmp/forge_clones"
    api_port: int = 8000
    debug: bool = False

    # Later files take precedence; repo-root .env overrides apps/api/.env.
    model_config = SettingsConfigDict(
        env_file=(str(_API_ENV), str(_ROOT_ENV)),
        extra="ignore",
    )


settings = Settings()
