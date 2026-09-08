import os
import json
import httpx
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


class GeminiEmbeddingsAdapter(BaseEmbeddingsAdapter):
    """
    Direct HTTP/REST adapter for Google Gemini Embeddings (models/gemini-embedding-001).
    Uses httpx so no extra external native library dependencies are required.
    """
    def __init__(self, model_name: str = "models/gemini-embedding-001", api_key: str = None):
        self.model_name = "models/gemini-embedding-001"
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API Key is required for Gemini Embeddings.")
        self._dimension = 768
        logger.info(f"[embeddings] Loading Gemini ({self.model_name}), dimension: {self._dimension}")

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:batchEmbedContents?key={self.api_key}"
        embeddings = []
        batch_size = 16
        with httpx.Client(timeout=30.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                requests_payload = [
                    {
                        "model": self.model_name,
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": self._dimension
                    }
                    for t in batch
                ]
                resp = client.post(url, json={"requests": requests_payload})
                if resp.status_code != 200:
                    raise RuntimeError(f"Gemini Embedding API Error: {resp.status_code} - {resp.text}")
                data = resp.json()
                for item in data.get("embeddings", []):
                    embeddings.append(item.get("values", []))
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:embedContent?key={self.api_key}"
        payload = {
            "model": self.model_name,
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": self._dimension
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini Embedding API Error: {resp.status_code} - {resp.text}")
            data = resp.json()
            return data.get("embedding", {}).get("values", [])


class OpenAIEmbeddingsAdapter(BaseEmbeddingsAdapter):
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str = None):
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API Key is required for OpenAI Embeddings.")
        from langchain_openai import OpenAIEmbeddings
        self._embeddings = OpenAIEmbeddings(model=self.model_name, openai_api_key=self.api_key)
        self._dimension = 1536
        logger.info(f"[embeddings] Loading OpenAI ({self.model_name}), dimension: {self._dimension}")

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)


class EmbeddingFactory:
    @staticmethod
    def get_embeddings_adapter() -> BaseEmbeddingsAdapter:
        provider = getattr(settings, "embedding_provider", "openai").lower()
        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY") or ""

        # Auto-detect provider based on API key prefix if not explicitly set
        if api_key.startswith("sk-"):
            provider = "openai"
        elif api_key.startswith("AIza") or provider == "gemini":
            provider = "gemini"

        if provider == "gemini":
            return GeminiEmbeddingsAdapter(model_name="models/gemini-embedding-001", api_key=api_key)
        else:
            model_name = getattr(settings, "embedding_model_name", "text-embedding-3-small")
            if "bge" in model_name.lower() or "models/" in model_name.lower():
                model_name = "text-embedding-3-small"
            return OpenAIEmbeddingsAdapter(model_name=model_name, api_key=api_key)
