from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    github_token: str = ""
    api_port: int = 8000
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
