from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Arya Noble Chatbot API"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:50010/arya_noble"
    SECRET_KEY: str = "supersecretkey" # Replace in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CIS_RSA_PUBLIC_KEY: Optional[str] = None
    CIS_RSA_PUBLIC_KEY_PATH: Optional[str] = None
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 500 # Maximum allowed file upload size in megabytes
    SECRET_ENCRYPTION_KEY: str = "HD77PDBToZJLKpGJlUKP1HKLH3LcwUe1TUl1ZrTl6MU="
    ENVIRONMENT: str = "development" # "development" | "staging" | "production"

    # RAG & LLM Settings
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    LLM_MODEL_NAME: str = "gpt-5.4-mini"
    OPENAI_API_KEY: Optional[str] = None

    # MinIO / S3 Object Storage Settings
    S3_ENDPOINT_URL: Optional[str] = None # Set only for MinIO (e.g. "http://localhost:9000"); Leave None for AWS S3
    S3_ACCESS_KEY: Optional[str] = None # Leave None for AWS IRSA / IAM role auth, or "minioadmin" for MinIO
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET: str = "skin-clinic-chatbot-dev" # Unified S3 bucket
    S3_DOCUMENTS_BUCKET: Optional[str] = None # Automatically defaults to S3_BUCKET
    S3_STAGING_BUCKET: Optional[str] = None # Automatically defaults to S3_BUCKET
    S3_APPROVED_BUCKET: Optional[str] = None # Automatically defaults to S3_BUCKET
    S3_REGION: str = "ap-southeast-3" # AWS Jakarta Region
    S3_USE_PATH_STYLE: Optional[bool] = None # None = auto-detect (True for MinIO, False for AWS)
    S3_PUBLIC_URL: Optional[str] = None # Optional public CDN / API prefix

    COOKIE_DOMAIN: Optional[str] = None # e.g. ".aryanoble.web.id" or ".aryanoble.co.id"
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: str = "lax"
    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8001",
        "https://dokterpedia-dev.aryanoble.web.id",
        "https://dokterpedia-staging.aryanoble.web.id",
        "https://dokterpedia.aryanoble.co.id",
    ]

    # Token Quotas
    INGESTION_MONTHLY_TOKEN_LIMIT: int = 1000000

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v # type: ignore
        return []

    def validate_security(self):
        """Validates production environment security settings."""
        if self.ENVIRONMENT.lower() in ("production", "prod"):
            if "supersecretkey" in self.SECRET_KEY.lower():
                raise ValueError("SECURITY ALERT: Cannot run in production with default 'supersecretkey'! Set a secure random SECRET_KEY in .env.")
            if not self.OPENAI_API_KEY or "your-key" in self.OPENAI_API_KEY.lower():
                raise ValueError("SECURITY ALERT: Valid OPENAI_API_KEY is required for production deployment!")
        elif "supersecretkey" in self.SECRET_KEY.lower():
            import warnings
            warnings.warn("SECURITY WARNING: Using default 'supersecretkey'. Change SECRET_KEY before deploying to production.")

settings = Settings()
settings.validate_security()
