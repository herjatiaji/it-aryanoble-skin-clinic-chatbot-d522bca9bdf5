import os
import sys
import time
from loguru import logger
from sqlalchemy import text

from app.core.database import get_sync_engine
from app.rag.services.embeddings import EmbeddingFactory


def backfill_missing_embeddings(batch_size: int = 100):
    """
    Backfills vector embeddings for all active kb_chunk entries where embedding IS NULL.
    Uses EmbeddingFactory (OpenAI text-embedding-3-small, 1536D).
    """
    engine = get_sync_engine()
    emb_adapter = EmbeddingFactory.get_embeddings_adapter()
    if not emb_adapter:
        logger.error("Failed to obtain embeddings adapter. Aborting backfill.")
        return 0

    with engine.connect() as conn:
        count_missing = conn.execute(
            text("SELECT COUNT(*) FROM kb_chunk WHERE embedding IS NULL AND is_active = true;")
        ).scalar()
        logger.info(f"🔍 Found {count_missing} active kb_chunks with missing embeddings.")

    if not count_missing:
        logger.info("✅ All active chunks already have embeddings.")
        return 0

    total_updated = 0
    while True:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, retrieval_text 
                FROM kb_chunk 
                WHERE embedding IS NULL AND is_active = true 
                LIMIT :limit;
            """), {"limit": batch_size}).fetchall()

        if not rows:
            break

        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]

        logger.info(f"Generating embeddings for batch of {len(texts)} chunks...")
        vectors = emb_adapter.embed_documents(texts)

        with engine.begin() as conn:
            for c_id, vec in zip(ids, vectors):
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
                conn.execute(text("""
                    UPDATE kb_chunk 
                    SET embedding = CAST(:vec AS vector)
                    WHERE id = :cid;
                """), {"vec": vec_str, "cid": c_id})

        total_updated += len(rows)
        logger.info(f"✅ Successfully updated {total_updated}/{count_missing} chunks with embeddings.")

    logger.info(f"🎉 Backfill complete! Total updated: {total_updated}")
    return total_updated


if __name__ == "__main__":
    backfill_missing_embeddings()
