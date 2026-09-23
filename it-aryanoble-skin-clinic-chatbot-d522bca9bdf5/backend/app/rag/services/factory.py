import os
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.rag.config import settings
from app.rag.services.interfaces import BaseLLMAdapter, BaseVectorStoreAdapter

class AdapterFactory:
    _vector_store_instance = None

    # ── Vector Store Registry ────────────────────────────────────────────────
    # Maps provider names to their adapter classes (lazy imports).
    # Add new providers here to support them via VECTOR_STORE_PROVIDER env var.
    VECTOR_STORE_REGISTRY: dict = {
        "pgvector": "app.rag.services.vector_store.PGVectorAdapter",
        # "qdrant": "app.rag.services.qdrant_adapter.QdrantAdapter",  # uncomment when available
    }

    @staticmethod
    def _resolve_provider_base_url(provider: str, base_url: Optional[str] = None) -> Optional[str]:
        """
        Maps known LLM providers to their default OpenAI-compatible base URLs if not custom provided.
        """
        if base_url:
            return base_url

        provider_clean = (provider or "").lower()
        if provider_clean == "deepseek":
            return "https://api.deepseek.com/v1"
        elif provider_clean == "ollama":
            return "http://localhost:11434/v1"
        elif provider_clean == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        
        return os.getenv("OPENAI_BASE_URL")

    @staticmethod
    async def get_dynamic_llm(session: Optional[AsyncSession] = None) -> BaseLLMAdapter:
        """
        Dynamically fetches LLM provider, model name, base_url, and API key from DB AppConfig (with .env fallback).
        All providers use OpenAI-compatible ChatOpenAI adapter.
        """
        from app.rag.services.rag_generator import OpenAIAdapter
        
        provider = settings.llm_provider.lower()
        model_name = None
        api_key = None
        base_url = None
        
        if session:
            try:
                from app.models.config import AppConfig
                from sqlalchemy import select
                
                stmt = select(AppConfig).where(
                    AppConfig.key.in_(["LLM_ACTIVE_PROVIDER", "LLM_ACTIVE_MODEL_NAME", "LLM_API_KEY", "LLM_BASE_URL"])
                )
                res = await session.execute(stmt)
                config_map = {cfg.key: cfg.value for cfg in res.scalars().all() if cfg.value}
                
                if "LLM_ACTIVE_PROVIDER" in config_map:
                    provider = config_map["LLM_ACTIVE_PROVIDER"].lower()
                if "LLM_ACTIVE_MODEL_NAME" in config_map:
                    model_name = config_map["LLM_ACTIVE_MODEL_NAME"]
                if "LLM_API_KEY" in config_map:
                    try:
                        from app.core.security import decrypt_api_key
                        api_key = decrypt_api_key(config_map["LLM_API_KEY"])
                    except Exception:
                        api_key = config_map["LLM_API_KEY"]
                if "LLM_BASE_URL" in config_map:
                    base_url = config_map["LLM_BASE_URL"]
            except Exception as e:
                logger.warning(f"Failed to load dynamic LLM config from DB: {e}")

        # Resolve provider base URL mapping
        base_url = AdapterFactory._resolve_provider_base_url(provider, base_url)
        api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY") or "dummy-key"

        return OpenAIAdapter(api_key=api_key, model_name=model_name, base_url=base_url)

    @staticmethod
    def get_llm() -> BaseLLMAdapter:
        from app.rag.services.rag_generator import OpenAIAdapter
        provider = settings.llm_provider.lower()
        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY") or "dummy-key"
        base_url = AdapterFactory._resolve_provider_base_url(provider)
        model_name = getattr(settings, "openai_model_name", None) or "gpt-5.4-mini"

        return OpenAIAdapter(api_key=api_key, model_name=model_name, base_url=base_url)

    @staticmethod
    def get_llm_adapter() -> BaseLLMAdapter:
        return AdapterFactory.get_llm()

    @staticmethod
    def get_vector_store() -> BaseVectorStoreAdapter:
        """
        Factory method: instantiates the vector store adapter based on
        VECTOR_STORE_PROVIDER env var (default: 'pgvector').
        
        Uses a registry pattern inspired by Open-Brain for easy provider switching.
        """
        if AdapterFactory._vector_store_instance is None:
            provider = settings.vector_store_provider.lower()
            class_path = AdapterFactory.VECTOR_STORE_REGISTRY.get(provider)

            if class_path is None:
                available = ", ".join(AdapterFactory.VECTOR_STORE_REGISTRY.keys())
                raise ValueError(
                    f"Unknown VECTOR_STORE_PROVIDER '{provider}'. "
                    f"Must be one of: {available}"
                )

            # Lazy import the adapter class
            module_path, class_name = class_path.rsplit(".", 1)
            import importlib
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)

            logger.info(f"Initializing vector store: provider='{provider}', class='{class_name}'")
            AdapterFactory._vector_store_instance = adapter_cls()

        return AdapterFactory._vector_store_instance

    _reranker_instance = None
    _bm25_instance = None

    @staticmethod
    def get_reranker():
        """
        Thread-safe singleton for CrossEncoder Reranker.
        Prevents expensive PyTorch model reloading (~400MB) on every incoming chat request.
        """
        if AdapterFactory._reranker_instance is None:
            from app.rag.services.rag_retriever import Reranker
            from app.rag.config import settings as rag_settings
            model_name = getattr(rag_settings, "reranker_model_name", "BAAI/bge-reranker-base")
            AdapterFactory._reranker_instance = Reranker(model_name=model_name)
        return AdapterFactory._reranker_instance

    @staticmethod
    def get_bm25_index():
        """
        In-memory singleton for BM25Index.
        Prevents downloading and rebuilding the BM25 index on every incoming chat request.
        """
        if AdapterFactory._bm25_instance is None:
            from app.rag.services.rag_retriever import BM25Index
            from app.rag.config import settings as rag_settings
            bm25 = BM25Index()
            try:
                bm25.load(rag_settings.bm25_index_path)
            except Exception as e:
                logger.warning(f"Could not load BM25 index on startup: {e}")
            AdapterFactory._bm25_instance = bm25
        return AdapterFactory._bm25_instance

    @staticmethod
    def invalidate_bm25_index():
        """
        Forces a reload of the BM25 index from storage/SSOT when documents are added, updated, or removed.
        """
        from app.rag.config import settings as rag_settings
        if AdapterFactory._bm25_instance is not None:
            try:
                AdapterFactory._bm25_instance.load(rag_settings.bm25_index_path)
                logger.info("Successfully reloaded in-memory BM25 index.")
            except Exception as e:
                logger.warning(f"Failed to reload BM25 index: {e}")


