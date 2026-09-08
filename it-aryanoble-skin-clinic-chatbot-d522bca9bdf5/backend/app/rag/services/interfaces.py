from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseVectorStoreAdapter(ABC):
    """
    Blueprint for Vector Database adapters.
    Whether we use Qdrant, Pinecone, or Chroma, they must implement these methods.
    """
    @abstractmethod
    def insert_chunks(self, chunks: List[Dict]):
        pass

    @abstractmethod
    def search(self, query: str, top_k: int = 5, filter_metadata: Any = None) -> List[Dict]:
        pass

    @abstractmethod
    def delete_document(self, source_file: str):
        """
        Deletes all chunks associated with a given source file.
        """
        pass

    @abstractmethod
    def clear_all(self):
        """
        Clears/deletes all vectors and resets the database.
        """
        pass


class BaseLLMAdapter(ABC):
    """
    Blueprint for LLM adapters.
    Whether we use Gemini, OpenAI, or local LLaMA, they must implement this.
    """
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
