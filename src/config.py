from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    PROJECT_NAME: str = "Zero-Trust Enterprise RAG"
    VERSION: str = "1.1.0"
    ENVIRONMENT: str = "development"

    # Required; deliberately has no insecure public fallback.
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "enterprise_rbac_docs"

    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    LLM_TEMPERATURE: float = 0.2

    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    DEFAULT_TOP_K: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
