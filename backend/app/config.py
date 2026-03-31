from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/pdfcleaner"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/pdfcleaner"
    REDIS_URL: str = "redis://redis:6379/0"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168  # 7 dias
    STORAGE_PATH: str = "/data"
    MAX_FILE_SIZE_MB: int = 200
    MAX_PAGES: int = 1000
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"

    class Config:
        env_file = ".env"


settings = Settings()
