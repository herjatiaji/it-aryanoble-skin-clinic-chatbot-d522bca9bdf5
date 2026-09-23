from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    # LLM Settings
    llm_provider: str = "openai"
    openai_api_key: Optional[str] = None
    openai_model_name: str = "gpt-5.4-mini"
    llm_generation_temperature: float = 0.2  # Set to 0.2 for natural & dynamic response generation

    # Vector DB (PGVector) Settings
    pg_host: str = "localhost"
    pg_port: int = 50010
    pg_db: str = "arya_noble"
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_collection_name: str = "arya_noble_kb"
    
    @property
    def pg_conn_str(self) -> str:
        host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST") or self.pg_host
        port = os.getenv("POSTGRES_PORT") or os.getenv("PG_PORT") or self.pg_port
        return f"postgresql+psycopg://{self.pg_user}:{self.pg_password}@{host}:{port}/{self.pg_db}"


    
    # Chunking Settings
    chunk_size: int = 500
    chunk_overlap: int = 50
    
    # Embedding Settings
    embedding_provider: str = "openai"
    embedding_model_name: str = "text-embedding-3-small"
    
    # Reranker Settings
    reranker_model_name: str = "BAAI/bge-reranker-base"
    rerank_confidence_threshold: float = 0.1
    
    # Ingestion Concurrency Settings
    max_ingestion_concurrency: int = 3

    # BM25 Settings
    bm25_index_path: str = "./data/output/bm25_index.pkl"

    # AI Agent Settings (ReAct Agent with Tool Calling)
    rag_agent_enabled: bool = True
    rag_agent_max_iterations: int = 5

    # Guardrails Settings
    guardrails_enabled: bool = True
    guardrails_block_offtopic: bool = True
    guardrails_redact_pii: bool = True
    prompt_injection_confidence_threshold: float = 0.7  # Score threshold for blocking prompt injections

    # Vector Store Provider (factory pattern)
    vector_store_provider: str = "pgvector"  # "pgvector" | "qdrant"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env", "../../.env"),
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
