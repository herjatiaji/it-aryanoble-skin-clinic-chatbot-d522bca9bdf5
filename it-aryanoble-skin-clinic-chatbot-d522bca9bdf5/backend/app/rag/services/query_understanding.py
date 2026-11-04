import re
import json
import time
import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.rag.services.interfaces import BaseLLMAdapter


@dataclass
class QueryUnderstandingResult:
    standalone_query: str
    intent: str = "CLINICAL_QA"
    entities: List[str] = field(default_factory=list)
    is_followup: bool = False
    is_continuation: bool = False
    raw_response: Optional[str] = None


# Simple in-memory LRU / TTL cache for query understanding
_QUERY_UNDERSTANDING_CACHE: Dict[str, Dict[str, Any]] = {}
_MAX_CACHE_SIZE = 1000
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_cache_key(query: str, history: List[Dict[str, Any]]) -> str:
    recent_history = history[-6:] if history else []
    hist_repr = []
    for m in recent_history:
        role = str(m.get("role", "")).lower()
        content = str(m.get("content", "")).strip()[:150]
        hist_repr.append(f"{role}:{content}")
    key_str = f"{query.strip().lower()}|||{'###'.join(hist_repr)}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


def _get_from_cache(key: str) -> Optional[QueryUnderstandingResult]:
    now = time.time()
    if key in _QUERY_UNDERSTANDING_CACHE:
        entry = _QUERY_UNDERSTANDING_CACHE[key]
        if now - entry["timestamp"] < _CACHE_TTL_SECONDS:
            return entry["result"]
        else:
            del _QUERY_UNDERSTANDING_CACHE[key]
    return None


def _save_to_cache(key: str, result: QueryUnderstandingResult):
    now = time.time()
    if len(_QUERY_UNDERSTANDING_CACHE) >= _MAX_CACHE_SIZE:
        oldest_key = min(_QUERY_UNDERSTANDING_CACHE.keys(), key=lambda k: _QUERY_UNDERSTANDING_CACHE[k]["timestamp"])
        del _QUERY_UNDERSTANDING_CACHE[oldest_key]
    _QUERY_UNDERSTANDING_CACHE[key] = {"result": result, "timestamp": now}


def _fast_fallback_contextualize(query: str, history: List[Dict[str, Any]]) -> QueryUnderstandingResult:
    """Deterministic fast fallback when LLM query understanding is unavailable or times out."""
    clean_q = query.strip()
    q_lower = clean_q.lower()

    if not history:
        return QueryUnderstandingResult(
            standalone_query=clean_q,
            intent="CLINICAL_QA",
            entities=[],
            is_followup=False,
            is_continuation=False
        )

    # Detect continuation markers
    continuation_markers = [
        "ada lagi", "selain itu", "yang lain", "opsi lain", "pilihan lain",
        "ada alternatif", "alternatif lain", "rekomendasi lainnya"
    ]
    is_cont = any(m in q_lower for m in continuation_markers)

    # Find the most recent assistant or user entity from history
    last_entity = ""
    for msg in reversed(history[-6:]):
        content = str(msg.get("content", "")).strip()
        role = str(msg.get("role", "")).lower()

        # Check bold headers or product titles in assistant message: **Product Name**
        bold_items = re.findall(r'\*\*([A-Za-z0-9\s\.\-\/\+]{3,50})\*\*', content)
        if bold_items:
            for b in bold_items:
                b_clean = b.strip()
                if len(b_clean) >= 3 and not b_clean.lower().startswith(("indikasi", "manfaat", "harga", "durasi", "catatan", "peringatan")):
                    last_entity = b_clean
                    break
        if last_entity:
            break

        # Check user message core words
        if role in ("user", "admin"):
            cleaned = re.sub(r'^(?:tolong|bisa|apakah|bagaimana|apa(?:\s+itu|\s+yang|\s+saja)?|mohon|info|tanya|jelaskan\s+tentang|rekomendasi|rekomendasikan)\s+', '', content, flags=re.IGNORECASE).strip()
            clean_words = cleaned.split()[:4]
            if clean_words:
                cand = " ".join(clean_words).strip("?.!,")
                if len(cand) >= 3:
                    last_entity = cand
                    break

    # Check if query is short follow-up (<= 5 words or starts with interrogative)
    words = clean_q.split()
    is_short_followup = len(words) <= 5 or any(q_lower.startswith(w) for w in ["berapa", "bagaimana", "kalau", "apakah", "kenapa", "untuk"])

    if is_cont and last_entity:
        standalone = f"alternatif opsi pilihan selain {last_entity}"
        return QueryUnderstandingResult(
            standalone_query=standalone,
            intent="CLINICAL_QA",
            entities=[last_entity],
            is_followup=True,
            is_continuation=True
        )

    if last_entity and is_short_followup:
        standalone = f"{clean_q} {last_entity}"
        return QueryUnderstandingResult(
            standalone_query=standalone,
            intent="CLINICAL_QA",
            entities=[last_entity],
            is_followup=True,
            is_continuation=False
        )

    return QueryUnderstandingResult(
        standalone_query=clean_q,
        intent="CLINICAL_QA",
        entities=[],
        is_followup=bool(history),
        is_continuation=is_cont
    )


QUERY_UNDERSTANDING_SYSTEM_PROMPT = """You are a precision clinical query understanding component for a medical & aesthetic skincare RAG chatbot.
Given a conversation history between a user (doctor/patient) and an AI assistant, and the user's latest follow-up question:
Your task is to rephrase the latest question into a single self-contained standalone search query in Indonesian that resolves all pronouns, elliptical references, and missing context from previous turns.

Rules:
1. Return strictly a JSON object with the following schema:
{
  "standalone_query": "Rephrased standalone search query in Indonesian",
  "intent": "CLINICAL_QA" | "PRICE_INQUIRY" | "TREATMENT_SEARCH" | "PRODUCT_SEARCH" | "COMPARISON" | "GREETING" | "CLOSING" | "OTHER",
  "entities": ["list", "of", "extracted", "entities"],
  "is_followup": true or false,
  "is_continuation": true or false
}
2. Never invent or hallucinate entities not mentioned in the history or current question.
3. Preserve acronyms and specific codes exactly as written: If the conversation mentions an acronym, abbreviation, or product code, ALWAYS retain that exact acronym/code in the standalone_query (e.g. 'Berapa biaya untuk perawatan XYZ?'). NEVER expand an acronym into words unless that exact expansion appears in the conversation history.
4. If the user's query is already self-contained (or introduces a completely new topic), keep standalone_query identical or close to the user's input.
4b. A follow-up that does not name its subject (a product, treatment, device, condition or document) is about the subject of the MOST RECENT turn that named one (the latest user question or the answer to it), not an older topic of the conversation: the standalone_query MUST name that subject exactly as it was written in the conversation. Never replace it with a generic word such as 'prosedur', 'perawatan', 'produk' or 'treatment'.
5. Output raw JSON only. Do NOT enclose in markdown code blocks like ```json ... ```.
"""


def understand_query(
    query: str,
    history: List[Dict[str, Any]],
    llm_adapter: Optional[BaseLLMAdapter] = None,
    timeout_seconds: float = 2.0
) -> QueryUnderstandingResult:
    """
    Analyzes query and conversation history using LLM with deterministic fast path and caching:
    1. Returns immediately for 1-turn self-contained queries (0ms overhead).
    2. Checks LRU cache for identical query + history turns.
    3. Calls LLM with bounded timeout to resolve pronouns, ellipsis, and entity references.
    4. Falls back gracefully to deterministic rule if LLM times out or fails.
    """
    clean_q = query.strip()
    if not clean_q:
        return QueryUnderstandingResult(standalone_query="")

    # Fast path: 1-Turn queries without conversation history need no rewrite
    if not history:
        return QueryUnderstandingResult(
            standalone_query=clean_q,
            intent="CLINICAL_QA",
            entities=[],
            is_followup=False,
            is_continuation=False
        )

    cache_key = _get_cache_key(clean_q, history)
    cached = _get_from_cache(cache_key)
    if cached:
        logger.debug(f"🎯 [Query Understanding] Cache hit: '{clean_q}' -> '{cached.standalone_query}'")
        return cached

    if not llm_adapter:
        fallback = _fast_fallback_contextualize(clean_q, history)
        _save_to_cache(cache_key, fallback)
        return fallback

    # Format history turns for LLM (max 6 turns)
    formatted_history = []
    for msg in history[-6:]:
        r = str(msg.get("role", "user")).capitalize()
        c = str(msg.get("content", "")).strip()
        # Truncate long assistant responses to keep prompt light and fast
        if len(c) > 300:
            c = c[:300] + "..."
        formatted_history.append(f"{r}: {c}")

    hist_str = "\n".join(formatted_history)
    user_prompt = f"""Conversation History:
{hist_str}

User's Latest Query: "{clean_q}"

Produce the JSON object:"""

    full_prompt = f"{QUERY_UNDERSTANDING_SYSTEM_PROMPT}\n\n{user_prompt}"

    t0 = time.time()
    try:
        raw_res = llm_adapter.generate(full_prompt)
        elapsed_ms = int((time.time() - t0) * 1000)

        # Parse JSON
        clean_json_str = raw_res.strip()
        if clean_json_str.startswith("```"):
            clean_json_str = re.sub(r'^```(?:json)?\s*', '', clean_json_str)
            clean_json_str = re.sub(r'\s*```$', '', clean_json_str)

        data = json.loads(clean_json_str.strip())
        standalone = str(data.get("standalone_query") or clean_q).strip()
        intent = str(data.get("intent") or "CLINICAL_QA").strip().upper()
        entities = data.get("entities") if isinstance(data.get("entities"), list) else []
        is_followup = bool(data.get("is_followup", True))
        is_continuation = bool(data.get("is_continuation", False))

        result = QueryUnderstandingResult(
            standalone_query=standalone,
            intent=intent,
            entities=entities,
            is_followup=is_followup,
            is_continuation=is_continuation,
            raw_response=raw_res
        )
        logger.info(f"🧠 [Query Understanding] ({elapsed_ms}ms) '{clean_q}' -> '{standalone}' (intent: {intent}, entities: {entities})")
        _save_to_cache(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"⚠️ [Query Understanding] LLM call failed or invalid JSON ({e}). Falling back to fast contextualizer.")
        fallback = _fast_fallback_contextualize(clean_q, history)
        _save_to_cache(cache_key, fallback)
        return fallback
