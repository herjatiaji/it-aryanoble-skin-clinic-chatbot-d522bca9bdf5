"""
KB Health Audit (Fase 1).

Mendeteksi inkonsistensi data yang membuat retrieval gagal secara diam-diam:
  - dokumen APPROVED/aktif tanpa chunk aktif
  - versi ingest yang macet (PROCESSING/PENDING terlalu lama)
  - chunk aktif milik dokumen yang sudah di-soft-delete
  - chunk aktif tanpa embedding
Tidak ada nama dokumen/produk yang ditulis di sini; semua berbasis skema.
"""
from typing import Any, Dict, List
from loguru import logger
from sqlalchemy import text

from app.core.database import get_sync_engine

STUCK_MINUTES_DEFAULT = 30


def run_kb_health_audit(stuck_minutes: int = STUCK_MINUTES_DEFAULT) -> Dict[str, Any]:
    engine = get_sync_engine()
    report: Dict[str, Any] = {}

    with engine.connect() as conn:
        report["approved_without_active_chunks"] = [
            dict(r._mapping) for r in conn.execute(text("""
                SELECT k.id::text AS knowledge_id, k.file_name, k.title
                FROM knowledge k
                WHERE k.status = 'APPROVED' AND k.deleted_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM knowledge_version kv
                    JOIN kb_chunk c ON c.version_id = kv.id AND c.is_active = true
                    WHERE kv.knowledge_id = k.id
                  )
                ORDER BY k.file_name
            """))
        ]

        report["stuck_versions"] = [
            dict(r._mapping) for r in conn.execute(text("""
                SELECT kv.id::text AS version_id, kv.knowledge_id::text AS knowledge_id,
                       k.file_name, kv.status, kv.ingestion_job_status,
                       kv.updated_at::text AS updated_at
                FROM knowledge_version kv
                LEFT JOIN knowledge k ON k.id = kv.knowledge_id
                WHERE kv.status IN ('PROCESSING', 'DRAFT')
                  AND kv.ingestion_job_status IN ('PENDING', 'RUNNING', 'PROCESSING')
                  AND kv.updated_at < NOW() - make_interval(mins => :m)
                ORDER BY kv.updated_at
            """), {"m": stuck_minutes})
        ]

        report["active_chunks_of_deleted_docs"] = [
            dict(r._mapping) for r in conn.execute(text("""
                SELECT k.id::text AS knowledge_id, k.file_name, COUNT(c.id) AS active_chunks
                FROM knowledge k
                JOIN knowledge_version kv ON kv.knowledge_id = k.id
                JOIN kb_chunk c ON c.version_id = kv.id AND c.is_active = true
                WHERE k.deleted_at IS NOT NULL
                GROUP BY k.id, k.file_name
            """))
        ]

        report["active_chunks_without_embedding"] = conn.execute(text(
            "SELECT COUNT(*) FROM kb_chunk WHERE is_active = true AND embedding IS NULL"
        )).scalar() or 0

        report["totals"] = dict(conn.execute(text("""
            SELECT COUNT(*) FILTER (WHERE is_active) AS active_chunks,
                   COUNT(*) AS all_chunks
            FROM kb_chunk
        """)).fetchone()._mapping)

    report["issue_count"] = (
        len(report["approved_without_active_chunks"])
        + len(report["stuck_versions"])
        + len(report["active_chunks_of_deleted_docs"])
        + (1 if report["active_chunks_without_embedding"] else 0)
    )
    report["healthy"] = report["issue_count"] == 0
    logger.info(f"[KB Health] issues={report['issue_count']} totals={report['totals']}")
    return report


def deactivate_duplicate_chunks_of_deleted_docs() -> Dict[str, int]:
    """
    Perbaikan aman & reversible: nonaktifkan chunk milik dokumen soft-delete
    HANYA jika ada dokumen hidup dengan file_name yang sama yang punya chunk aktif.
    Dokumen terhapus tanpa kembaran hidup TIDAK disentuh (butuh keputusan manusia).
    """
    engine = get_sync_engine()
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE kb_chunk SET is_active = false
            WHERE is_active = true AND version_id IN (
                SELECT kv.id FROM knowledge_version kv
                JOIN knowledge k ON k.id = kv.knowledge_id
                WHERE k.deleted_at IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM knowledge k2
                    JOIN knowledge_version kv2 ON kv2.knowledge_id = k2.id
                    JOIN kb_chunk c2 ON c2.version_id = kv2.id AND c2.is_active = true
                    WHERE k2.deleted_at IS NULL AND k2.file_name = k.file_name AND k2.id <> k.id
                  )
            )
        """))
        return {"deactivated_chunks": res.rowcount or 0}


def deactivate_all_chunks_of_deleted_or_unapproved_docs() -> Dict[str, int]:
    """
    Deactivates chunks in kb_chunk that belong to documents that are either:
    1. soft-deleted (k.deleted_at IS NOT NULL), or
    2. not APPROVED (e.g. REJECTED, DRAFT, PENDING, ARCHIVED).
    """
    engine = get_sync_engine()
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE kb_chunk SET is_active = false
            WHERE is_active = true AND version_id IN (
                SELECT kv.id FROM knowledge_version kv
                JOIN knowledge k ON k.id = kv.knowledge_id
                WHERE k.deleted_at IS NOT NULL OR k.status != 'APPROVED'
            )
        """))
        return {"deactivated_chunks": res.rowcount or 0}


def cleanup_stuck_versions(stuck_minutes: int = STUCK_MINUTES_DEFAULT) -> Dict[str, int]:
    """
    Marks knowledge_versions that have been stuck in PROCESSING/DRAFT longer than
    stuck_minutes as REJECTED with ingestion_job_status = 'FAILED'.
    """
    engine = get_sync_engine()
    with engine.begin() as conn:
        res = conn.execute(text("""
            UPDATE knowledge_version
            SET status = 'REJECTED',
                ingestion_job_status = 'FAILED',
                updated_at = NOW()
            WHERE status IN ('PROCESSING', 'DRAFT')
              AND ingestion_job_status IN ('PENDING', 'RUNNING', 'PROCESSING')
              AND updated_at < NOW() - make_interval(mins => :m)
        """), {"m": stuck_minutes})
        return {"cleaned_stuck_versions": res.rowcount or 0}


def backfill_missing_embeddings(only_live_docs: bool = True, batch_size: int = 50) -> Dict[str, int]:
    """Hitung embedding dari retrieval_text untuk chunk aktif yang embedding-nya NULL."""
    from app.rag.services.embeddings import EmbeddingFactory

    adapter = EmbeddingFactory.get_embeddings_adapter()
    engine = get_sync_engine()
    live_clause = "AND k.deleted_at IS NULL" if only_live_docs else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT c.id, c.retrieval_text
            FROM kb_chunk c
            JOIN knowledge_version kv ON kv.id = c.version_id
            LEFT JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE c.is_active = true AND c.embedding IS NULL
              AND c.retrieval_text IS NOT NULL AND length(trim(c.retrieval_text)) > 0
              {live_clause}
        """)).fetchall()

    done = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        vectors = adapter.embed_documents([r[1] for r in batch])
        with engine.begin() as conn:
            for (cid, _), vec in zip(batch, vectors):
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
                conn.execute(
                    text("UPDATE kb_chunk SET embedding = CAST(:e AS vector) WHERE id = :id"),
                    {"e": vec_str, "id": cid},
                )
                done += 1
    return {"candidates": len(rows), "embedded": done}


def apply_all_health_fixes(stuck_minutes: int = STUCK_MINUTES_DEFAULT) -> Dict[str, Any]:
    """
    One-click comprehensive KB health remediation:
    1. Deactivates chunks belonging to deleted or unapproved docs.
    2. Backfills any active chunks that lack vector embeddings.
    3. Cleans up orphaned / stuck ingestion jobs.
    Returns audit report before and after fixes.
    """
    before = run_kb_health_audit(stuck_minutes=stuck_minutes)
    deact_res = deactivate_all_chunks_of_deleted_or_unapproved_docs()
    embed_res = backfill_missing_embeddings(only_live_docs=True)
    stuck_res = cleanup_stuck_versions(stuck_minutes=stuck_minutes)
    after = run_kb_health_audit(stuck_minutes=stuck_minutes)

    return {
        "status": "success",
        "healthy_now": after["healthy"],
        "issues_before": before["issue_count"],
        "issues_after": after["issue_count"],
        "actions": {
            "deactivated_unapproved_chunks": deact_res.get("deactivated_chunks", 0),
            "embedded_missing_chunks": embed_res.get("embedded", 0),
            "cleaned_stuck_versions": stuck_res.get("cleaned_stuck_versions", 0),
        },
        "audit": after
    }
