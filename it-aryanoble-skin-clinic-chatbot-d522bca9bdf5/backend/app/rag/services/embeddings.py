import os
from abc import ABC, abstractmethod
from typing import List
from loguru import logger
from app.rag.config import settings

class BaseEmbeddingsAdapter(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        pass


class OpenAIEmbeddingsAdapter(BaseEmbeddingsAdapter):
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str = None, batch_size: int = 200):
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API Key is required for OpenAI Embeddings.")
        from langchain_openai import OpenAIEmbeddings
        self.batch_size = batch_size
        self._embeddings = OpenAIEmbeddings(
            model=self.model_name, 
            openai_api_key=self.api_key,
            chunk_size=self.batch_size
        )
        self._dimension = 1536
        logger.info(f"[embeddings] Loading OpenAI ({self.model_name}), batch_size: {self.batch_size}, dimension: {self._dimension}")

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import time as _time
        if not texts:
            return []
        
        max_retries = 3
        backoff = 3.0
        logger.info(f"⚡ [OpenAI Batch Embedding] Embedding {len(texts)} chunks in batches of up to {self.batch_size}...")
        for attempt in range(1, max_retries + 1):
            try:
                embeddings = self._embeddings.embed_documents(texts)
                logger.info(f"✅ [OpenAI Batch Embedding] Successfully generated {len(embeddings)} vectors.")
                return embeddings
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "rate" in err_str.lower() or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower()) and attempt < max_retries:
                    logger.warning(f"⚠️ [Embedding 429 Rate Limit] Attempt {attempt}/{max_retries}. Backing off {backoff}s... Error: {err_str[:150]}")
                    _time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error(f"❌ [Embedding Error] Failed on attempt {attempt}/{max_retries}: {e}")
                    raise e

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)


class EmbeddingFactory:
    @staticmethod
    def get_embeddings_adapter() -> BaseEmbeddingsAdapter:
        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY") or ""
        model_name = getattr(settings, "embedding_model_name", "text-embedding-3-small")
        if "bge" in model_name.lower() or "models/" in model_name.lower():
            model_name = "text-embedding-3-small"
        return OpenAIEmbeddingsAdapter(model_name=model_name, api_key=api_key)

