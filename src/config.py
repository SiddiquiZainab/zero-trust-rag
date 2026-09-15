import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration management for Zero-Trust RAG.
    Supports overriding parameters via environment variables or .env files.
    """
    # System Info
    PROJECT_NAME: str = "Zero-Trust Enterprise RAG"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # Security & JWT Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "super-secret-zero-trust-key-change-in-prod")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Qdrant Vector Database
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_COLLECTION_NAME: str = "enterprise_rbac_docs"

    # LLM Service (Ollama)
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    LLM_TEMPERATURE: float = 0.2

    # Embedding Model
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"

    # Retrieval Configuration
    DEFAULT_TOP_K: int = 4

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global settings instance
settings = Settings()


if __name__ == "__main__":
    # --- Quick Sanity Check ---
    print("==================================================")
    print(f" Loaded Configuration: {settings.PROJECT_NAME}")
    print("==================================================")
    print(f"Qdrant Endpoint : http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    print(f"Collection Name : {settings.QDRANT_COLLECTION_NAME}")
    print(f"Ollama Endpoint : {settings.OLLAMA_HOST}")
    print(f"Ollama Model    : {settings.OLLAMA_MODEL}")
    print(f"Embedding Model : {settings.EMBEDDING_MODEL_NAME}")
    print(f"JWT Secret Key  : {'*' * 8}{settings.JWT_SECRET_KEY[-4:]}")
    print("==================================================")