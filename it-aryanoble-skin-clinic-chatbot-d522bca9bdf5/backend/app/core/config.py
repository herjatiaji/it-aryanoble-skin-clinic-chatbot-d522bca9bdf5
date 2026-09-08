from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Arya Noble Chatbot API"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/arya_noble"
    SECRET_KEY: str = "supersecretkey" # Replace in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CIS_RSA_PUBLIC_KEY: Optional[str] = None
    CIS_RSA_PUBLIC_KEY_PATH: Optional[str] = None
    UPLOAD_DIR: str = "data/uploads"
    SECRET_ENCRYPTION_KEY: str = "HD77PDBToZJLKpGJlUKP1HKLH3LcwUe1TUl1ZrTl6MU="

    # RAG & LLM Settings
    EMBEDDING_PROVIDER: str = "huggingface"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    OPENAI_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
