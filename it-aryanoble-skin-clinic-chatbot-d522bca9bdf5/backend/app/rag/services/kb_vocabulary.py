"""
How many documents of the knowledge base use each word. A word few documents use ('ultraformer', 'hgat') can name
an item or a subject; a word many use ('skin', 'treatment', 'kulit') cannot. Copies of one document (same title)
count once. Computed from the active chunks in one pass and kept for a few minutes, so answers only look words up.
"""
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from loguru import logger
from sqlalchemy import text

from app.core.database import get_sync_engine
from app.rag.utils.text_hygiene import _claim_words

# A word is rare when at most this share of the documents use it (at most 2 in a very small knowledge base)
MAX_DOC_SHARE = 0.25
MIN_DOC_LIMIT = 2
_TTL_SECONDS = 600
_lock = threading.Lock()
_state: Dict[str, object] = {"at": 0.0, "df": {}, "docs": 0}


def document_frequency(engine=None) -> Tuple[Dict[str, int], int]:
    """(word -> number of documents using it, number of documents), documents being distinct active titles."""
    with _lock:
        if time.time() - float(_state["at"]) < _TTL_SECONDS and _state["docs"]:
            return _state["df"], int(_state["docs"])
        df: Dict[str, int] = {}
        docs = 0
        try:
            with (engine or get_sync_engine()).connect() as conn:
                rows = conn.execute(text("""
                    SELECT lower(k.title), string_agg(c.retrieval_text, ' ')
                    FROM kb_chunk c
                    JOIN knowledge_version kv ON kv.id = c.version_id AND kv.status = 'ACTIVE'
                    JOIN knowledge k ON k.id = kv.knowledge_id AND k.deleted_at IS NULL
                    WHERE c.is_active GROUP BY lower(k.title)
                """))
                for _, body in rows:
                    docs += 1
                    for w in set(_claim_words(body or "")):
                        df[w] = df.get(w, 0) + 1
        except Exception as e:
            logger.warning(f"[KB Vocabulary] document frequencies unavailable: {e}")
            return {}, 0
        _state.update(at=time.time(), df=df, docs=docs)
        return df, docs


def rare_word_predicate(engine=None, max_share: float = MAX_DOC_SHARE) -> Optional[Callable[[str], bool]]:
    """True for a word some documents, at most `max_share` of them, use; None when the frequencies are unavailable."""
    df, docs = document_frequency(engine)
    if not docs:
        return None
    limit = max(MIN_DOC_LIMIT, max_share * docs)
    return lambda w: 1 <= df.get(w, 0) <= limit
