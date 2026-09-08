import os
import json
from typing import List, Dict, Any, Optional
from loguru import logger

from app.rag.services.interfaces import BaseLLMAdapter
from app.rag.services.rag_retriever import HybridRetriever
from app.rag.services.intent import QueryIntentDetector, QueryIntent
from app.rag.config import settings

# --- LLM Adapter Implementations ---

class OpenAIAdapter(BaseLLMAdapter):
    def __init__(self, api_key: str, model_name: Optional[str] = None, base_url: Optional[str] = None):
        if not api_key:
            raise ValueError("API key is not configured in settings, database, or environment.")
        from langchain_openai import ChatOpenAI
        target_model = model_name or settings.openai_model_name
        logger.info(f"Initializing OpenAI-compatible LLM Adapter: model='{target_model}', base_url='{base_url or 'default'}'")
        
        kwargs = {
            "model": target_model,
            "api_key": api_key,
            "temperature": 0.0  # Grounded & factual response (0.0 temperature)
        }
        if base_url:
            kwargs["base_url"] = base_url
            
        self.llm = ChatOpenAI(**kwargs)

    def generate(self, prompt: str) -> str:
        import time
        max_retries = 3
        backoff_delay = 5.0
        
        for attempt in range(1, max_retries + 1):
            try:
                response = self.llm.invoke(prompt)
                return response.content
            except Exception as e:
                err_msg = str(e)
                if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota exceeded" in err_msg or "rate-limit" in err_msg.lower()) and attempt < max_retries:
                    logger.warning(f"LLM 429 Rate limit hit (attempt {attempt}/{max_retries}). Retrying in {backoff_delay}s... Error: {err_msg}")
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                else:
                    logger.error(f"LLM generation failed on attempt {attempt}/{max_retries}: {e}")
                    raise e


# --- Grounded System Prompt Configuration ---

SYSTEM_PROMPT = """You are ERHA Assistant, a grounded knowledge-base assistant.

Your primary responsibility is to answer the user's question accurately and concisely using ONLY the retrieved knowledge base.

STRICT RULES:
1. Answer ONLY what the user asked.
2. Do not provide unrelated information.
3. Do not expand a simple factual question into a long explanation.
4. Do not provide unsolicited product recommendations.
5. Do not provide unsolicited treatment regimens.
6. Do not provide unsolicited clinical advice.
7. Do not mention other products unless they are necessary to answer the user's question.
8. Do not add greetings such as 'Halo Dok' unless explicitly requested.
9. Do not add unnecessary sections, bullet points, emojis, or disclaimers.
10. Do not end with phrases such as 'Jika Dokter membutuhkan...' unless explicitly requested.
11. Do not repeat the user's question.
12. Do not speculate.
13. Do not use information outside the retrieved context.
14. Never substitute one product name for another.
15. Preserve exact product names, ingredient names, percentages, quantities, and other factual values from the retrieved context.
16. Focus on directly and naturally answering the primary question using the facts provided in the retrieved context. Do not append robotic disclaimer sentences such as "informasi tidak tersedia dalam basis pengetahuan" for minor secondary details if the main clinical query is already answered.
17. If the user asks whether a skincare regimen or product combination is appropriate, prioritize clear safety guidance based on the retrieved treatment aftercare instructions (such as avoiding exfoliating products for 5 days after peeling).

RESPONSE LENGTH RULES:
- Product name question: 1 sentence.
- Ingredient question: 1-2 sentences or a concise list.
- Function/benefit question: maximum 2-3 sentences.
- How-to-use question: maximum 2-4 sentences.
- Comparison question: concise comparison using only relevant information.
- If the user asks for detailed information, then provide more detail.

Do not maximize information.
Maximize relevance."""


# --- Generation Pipeline ---

class GenerationPipeline:
    def __init__(self, retriever: HybridRetriever, llm_adapter: BaseLLMAdapter):
        self.retriever = retriever
        self.llm_adapter = llm_adapter

    def build_prompt(
        self, 
        query: str, 
        context: str, 
        history: List[Dict[str, str]], 
        intent: QueryIntent, 
        intent_rules: Dict[str, Any]
    ) -> str:
        """
        Compiles system prompt, retrieved context, intent instructions,
        conversation history, and user query into a grounded prompt.
        """
        history_str = ""
        if history:
            for msg in history:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                history_str += f"{role}: {content}\n"
        else:
            history_str = "No previous conversation.\n"

        length_instruction = intent_rules.get("length_instruction", "Be concise and factual.")

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"--- DETECTED INTENT ---\n"
            f"Intent Category: {intent.value}\n"
            f"Specific Instruction: {length_instruction}\n\n"
            f"--- CONTEXT (RETRIEVED FROM ERHA KNOWLEDGE BASE) ---\n"
            f"{context}\n\n"
            f"--- CONVERSATION HISTORY ---\n"
            f"{history_str}\n"
            f"User: {query}\n"
            f"Assistant:"
        )
        return prompt

    def generate_answer(
        self, 
        query: str, 
        top_k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        confidence_threshold: Optional[float] = None,
        history: List[Dict[str, str]] = []
    ) -> Dict[str, Any]:
        """
        Retrieves relevant context, compiles prompt, and generates grounded response.
        Includes intent classification and debug logging.
        """
        # 1. Query Intent Detection
        intent, intent_rules = QueryIntentDetector.detect(query)

        # 2. Retrieve relevant chunks from Hybrid Retriever
        retrieval_response = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            filter_metadata=filter_metadata,
            rerank=rerank,
            rerank_top_n=top_k,
            confidence_threshold=confidence_threshold
        )

        results = retrieval_response.get("results", [])
        context = retrieval_response.get("context", "")

        # 3. Check for empty context or low confidence
        is_context_empty = (
            not results 
            or context in ("Maaf, saya tidak menemukan informasi.", "No relevant context found.")
            or len(context.strip()) == 0
        )

        if is_context_empty:
            missing_msg = intent_rules.get("missing_fallback", "Informasi tersebut tidak tersedia dalam knowledge base.")
            logger.info(f"Retrieval context empty for query '{query}'. Returning grounded fallback message.")
            
            # --- DEBUG LOGGING ---
            logger.debug(
                f"\n=== [RAG DEBUG LOG] ===\n"
                f"QUERY: {query}\n"
                f"INTENT: {intent.value}\n"
                f"RETRIEVED CONTEXT: [EMPTY]\n"
                f"SIMILARITY SCORE: N/A\n"
                f"LLM RESPONSE (GROUNDED FALLBACK): {missing_msg}\n"
                f"========================\n"
            )
            return {
                "query": query,
                "answer": missing_msg,
                "context": "No relevant context found in knowledge base.",
                "results": []
            }

        # 4. Build Grounded Prompt with Context, Intent & History
        full_prompt = self.build_prompt(query, context, history, intent, intent_rules)

        # 5. Generate Answer via LLM Adapter
        try:
            answer = self.llm_adapter.generate(full_prompt)
            answer = answer.strip()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            answer = "Maaf, terjadi kesalahan teknis pada pemrosesan LLM. Silakan coba beberapa saat lagi."

        # --- DEBUG LOGGING ---
        scores_summary = []
        for i, res in enumerate(results, 1):
            sc = res.get("rerank_score") if "rerank_score" in res else res.get("score", 0.0)
            src = res.get("metadata", {}).get("source_file", "unknown")
            scores_summary.append(f"Chunk {i}: source={src}, score={sc:.4f}")
        
        logger.debug(
            f"\n=== [RAG DEBUG LOG] ===\n"
            f"QUERY: {query}\n"
            f"INTENT: {intent.value}\n"
            f"RETRIEVED CHUNKS COUNT: {len(results)}\n"
            f"RETRIEVED CONTEXT PREVIEW:\n{context[:600]}...\n"
            f"SIMILARITY SCORES:\n" + "\n".join(scores_summary) + "\n"
            f"FINAL LLM PROMPT PREVIEW:\n{full_prompt[:500]}...\n"
            f"LLM RESPONSE:\n{answer}\n"
            f"========================\n"
        )

        return {
            "query": query,
            "intent": intent.value,
            "answer": answer,
            "context": context,
            "results": results
        }
