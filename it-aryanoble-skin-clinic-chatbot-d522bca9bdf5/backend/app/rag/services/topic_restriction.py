"""
Topic-level access restriction.

A document restricted to some doctors (or doctor types, or clinics) restricts its subject, not only its own
chunks: the treatment it is about is also named in price lists, mappings and combo tables that everyone may read.
The subject is taken from the words of the restricted document's title that are distinctive across the knowledge
base (few documents use them, e.g. 'ultraformer', 'mpt'), never from generic ones ('skin', 'therapy'). For a doctor
without access, a question naming such a word is refused, and lines naming it are removed from the evidence of
every other document, so the restricted subject is neither answered nor quoted.
"""
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger
from sqlalchemy import text

from app.core.database import get_sync_engine
from app.rag.services.canonical_retriever import evaluate_acl_3level
from app.rag.services.kb_vocabulary import rare_word_predicate
from app.rag.utils.text_hygiene import _claim_words

RESTRICTED_INFO_MESSAGE = "Mohon maaf, AI tidak dapat memberikan informasi yang diminta."
# A rare title word is the document's subject when at least this share of its chunks use it in their own text
SUBJECT_CHUNK_SHARE = 0.5

_CACHE_TTL_SECONDS = 60
_cache: Dict[Tuple, Tuple[float, Set[str]]] = {}


def _doctor_identity(filter_metadata: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """The doctor, doctor type and clinic a chat filter is for, read as the canonical retriever reads them."""
    meta = filter_metadata or {}

    def first(key):
        values = meta.get(key)
        return values[0] if isinstance(values, list) and values and values[0] != "all" else None

    doctor = meta.get("doctor_id") or meta.get("user_id") or first("doctors")
    doctor_type = meta.get("doctor_type") or meta.get("role") or first("doctor_types")
    clinic = meta.get("clinic_id") or meta.get("user_clinic_id") or first("clinics")
    return doctor, doctor_type, clinic


def _title_words(title: str) -> List[str]:
    return [w for w in _claim_words(title) if not any(ch.isdigit() for ch in w)]


def _body(retrieval_text: str) -> str:
    """A chunk's own text, without the metadata header that repeats the document title in every chunk."""
    parts = re.split(r"\|\s*Content:\s*", retrieval_text or "", maxsplit=1)
    return parts[1] if len(parts) == 2 else (retrieval_text or "")


def restricted_topic_terms(filter_metadata: Optional[Dict[str, Any]], engine=None) -> Set[str]:
    """The distinctive title words of the active documents this doctor may not read (empty for unrestricted users)."""
    doctor, doctor_type, clinic = _doctor_identity(filter_metadata)
    if doctor is None and doctor_type is None and clinic is None:
        return set()
    key = (doctor, doctor_type, clinic)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL_SECONDS:
        return hit[1]

    terms: Set[str] = set()
    try:
        is_rare = rare_word_predicate(engine)
        with (engine or get_sync_engine()).connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (kv.id) kv.id, k.title, c.acl_doctors, c.acl_doctor_types, c.acl_clinics
                FROM knowledge_version kv
                JOIN knowledge k ON k.id = kv.knowledge_id AND k.deleted_at IS NULL
                JOIN kb_chunk c ON c.version_id = kv.id AND c.is_active
                WHERE kv.status = 'ACTIVE' AND (
                    NOT ('ALL' = ANY(c.acl_doctors) OR 'all' = ANY(c.acl_doctors))
                    OR NOT ('ALL' = ANY(c.acl_doctor_types) OR 'all' = ANY(c.acl_doctor_types))
                    OR NOT ('ALL' = ANY(c.acl_clinics) OR 'all' = ANY(c.acl_clinics)))
            """)).fetchall()
            for version_id, title, docs_acl, types_acl, clinics_acl in rows:
                if evaluate_acl_3level(list(docs_acl or []), list(types_acl or []), list(clinics_acl or []),
                                       doctor_id=doctor, doctor_type=doctor_type, clinic_id=clinic):
                    continue
                candidates = {w for w in _title_words(title) if is_rare and is_rare(w)}
                if not candidates:
                    continue
                # The subject is what the document's own text is about: a title word most of its chunks use
                bodies = [set(_claim_words(_body(r[0]))) for r in conn.execute(text(
                    "SELECT retrieval_text FROM kb_chunk WHERE version_id = :v AND is_active"), {"v": version_id})]
                for w in candidates:
                    if bodies and sum(w in b for b in bodies) >= SUBJECT_CHUNK_SHARE * len(bodies):
                        terms.add(w)
    except Exception as e:
        logger.warning(f"[Topic Restriction] could not read restricted documents: {e}")
        return set()
    if terms:
        logger.info(f"[Topic Restriction] restricted subjects for doctor {doctor}: {sorted(terms)}")
    _cache[key] = (time.time(), terms)
    return terms


def _names_term(text_value: str, terms: Set[str]) -> bool:
    lowered = (text_value or "").lower()
    return any(re.search(rf"\b{re.escape(t)}\b", lowered) for t in terms)


def mentions_restricted_topic(queries: List[Optional[str]], terms: Set[str]) -> bool:
    return bool(terms) and any(q and _names_term(q, terms) for q in queries)


def redact_restricted_topic(results: List[Dict[str, Any]], context: str, terms: Set[str]):
    """Removes the evidence lines and table rows naming a restricted subject; results left empty are dropped."""
    if not terms:
        return results, context

    def keep_lines(value: str) -> str:
        return "\n".join(l for l in (value or "").split("\n") if not _names_term(l, terms))

    kept = []
    for r in results or []:
        r_copy = dict(r)
        for field in ("text", "content"):
            if isinstance(r_copy.get(field), str):
                r_copy[field] = keep_lines(r_copy[field])
        if (r_copy.get("text") or r_copy.get("content") or "").strip():
            kept.append(r_copy)
    return kept, keep_lines(context)
