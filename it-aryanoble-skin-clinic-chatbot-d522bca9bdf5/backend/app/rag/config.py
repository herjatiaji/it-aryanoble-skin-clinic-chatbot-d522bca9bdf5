from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    # LLM Settings
    llm_provider: str = "openai"
    openai_api_key: Optional[str] = None
    openai_model_name: str = "gpt-5.4-mini"
    llm_generation_temperature: float = 0.0  # Deterministic, evidence-bound clinical answers (0.2 caused run-to-run variation on identical evidence)

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
    enable_reranker: bool = False
    reranker_model_name: str = "BAAI/bge-reranker-base"
    rerank_confidence_threshold: float = 0.1
    
    # Ingestion Concurrency Settings: documents are parsed one at a time. A vision parse of a slide deck
    # takes several hundred MB; parallel ingests would exhaust the 2.9 GB production server. Chat queries
    # are not affected by this limit.
    max_ingestion_concurrency: int = 1
    # The canonical index (kb_chunk) is the one the chatbot reads. The older PGVector/BM25 stores are no longer
    # written; set true only to read them again as a fallback.
    legacy_retrieval_fallback: bool = False
    # Deterministic answer checks (status claims, abbreviation expansions, item attributes) that back up the
    # claim verifier: they hold for any item or abbreviation, and catch what a model-based check misses
    answer_regex_guards: bool = True
    # Rejects an answer whose item type (serum, toner...) differs from the type asked; a fixed form-factor list,
    # superseded by the prompt's item-type principle and the claim verifier
    form_factor_gate: bool = False
    # Re-chunk published documents made by an older chunker version, in the background after startup
    auto_reprocess_outdated: bool = True
    # Measures every ingested/published document (coverage of its own text, structure, generated questions)
    ingest_quality_check_enabled: bool = True

    # BM25 Settings
    bm25_index_path: str = "./data/output/bm25_index.pkl"

    # AI Agent Settings (ReAct Agent with Tool Calling - disabled by default for 3-5x faster responses)
    rag_agent_enabled: bool = False
    rag_agent_max_iterations: int = 3

    # Guardrails Settings
    guardrails_enabled: bool = True
    guardrails_block_offtopic: bool = True
    guardrails_redact_pii: bool = True
    prompt_injection_confidence_threshold: float = 0.7  # Score threshold for blocking prompt injections

    # Answer verification: a second model pass removes answer lines not supported by retrieved evidence.
    # Off by default. UAT-3 measurement (claim-checked v2): no answer was wrongly blanked, but translated
    # content was still removed (Indonesian answer vs English source) and relational errors are not caught.
    answer_verification_enabled: bool = True
    # The verification pass is skipped when code proves every answer line stated in the evidence (each value on
    # the same evidence line or table row as its item); any line it cannot prove still goes to the verifier.
    answer_proof_fast_path: bool = True
    # Order the retrieved chunks with one short LLM call (title + opening of each) and keep only the best ones for
    # the answer prompt. Measured on 19 test questions (Nov 2026): about token-neutral, but one answer lost its
    # chunk and one partial answer was mislabelled, so it stays off.
    llm_rerank_enabled: bool = False
    # Give each chunk an Indonesian search sentence at ingestion (one model call per ten chunks, about 265 tokens a
    # chunk, once); the sentence is indexed but never shown to the answering or checking model. Measured Nov 2026:
    # an Indonesian question found an English side-effects table it missed before, no regressions on 16 questions.
    contextual_retrieval_enabled: bool = True
    llm_rerank_keep: int = 6

    # Cross-lingual retrieval: English words of an LLM translation of the query that the knowledge base
    # uses are added to the search query, so Indonesian questions reach English source documents.
    cross_lingual_retrieval_enabled: bool = True

    # Vector Store Provider (factory pattern)
    vector_store_provider: str = "pgvector"  # "pgvector" | "qdrant"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env", "../../.env"),
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
