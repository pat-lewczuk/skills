from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    broker_url: str = "redis://localhost:6379/0"
    upload_dir: str = "/data/uploads"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"


settings = Settings()
