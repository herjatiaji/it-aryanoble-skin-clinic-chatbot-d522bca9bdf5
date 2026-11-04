"""
Brings published documents up to date when a processing stage they went through has a newer version
(app.rag.pipeline_versions): a document chunked by an older chunker is re-chunked from its summary and
published again through the normal approval path, which also re-runs its quality check. One document at a
time, so it never competes with ingestion or chat on a small server; vision re-parsing is not done here
(it costs tokens per page and stays an admin action).
"""
import asyncio
import json
import os
from typing import Dict, List

from loguru import logger
from sqlalchemy import text

from app.rag.pipeline_versions import CHUNKER_VERSION, chunker_version_of


def outdated_parser_documents() -> List[Dict[str, object]]:
    """Published documents read by an older vision parser (re-parsing them is an admin decision: it costs tokens)."""
    from app.core.database import get_sync_engine
    from app.rag.pipeline_versions import PARSER_VERSION
    from app.rag.router import resolve_approved_file

    with get_sync_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT id, title FROM knowledge WHERE deleted_at IS NULL AND status = 'APPROVED' ORDER BY created_at"
        )).fetchall()
    outdated = []
    for kid, title in rows:
        path = resolve_approved_file(str(kid))
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        version = int((doc.get("pipeline_versions") or {}).get("parser") or 0)
        vision_parsed = version > 0 or "pdf_flat_" in (doc.get("summary") or "")
        if vision_parsed and version < PARSER_VERSION:
            outdated.append({"knowledge_id": str(kid), "title": title, "parser_version": version or 1})
    return outdated


def outdated_documents() -> List[Dict[str, object]]:
    """Published documents whose chunks were made by an older chunker."""
    from app.core.database import get_sync_engine
    from app.rag.router import resolve_approved_file

    with get_sync_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT id, title FROM knowledge WHERE deleted_at IS NULL AND status = 'APPROVED' ORDER BY created_at"
        )).fetchall()
    outdated = []
    for kid, title in rows:
        path = resolve_approved_file(str(kid))
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        version = chunker_version_of(doc.get("chunks") or [])
        if version < CHUNKER_VERSION and (doc.get("summary") or "").strip():
            outdated.append({"knowledge_id": str(kid), "title": title, "chunker_version": version})
    return outdated


def unindexed_documents() -> List[Dict[str, object]]:
    """
    Published documents the chatbot cannot retrieve: approved, but without one active chunk in the index. Data
    published by an earlier release can be in this state (that release also searched its older index, which hid
    it), as can a document whose publish failed.
    """
    from app.core.database import get_sync_engine

    with get_sync_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT k.id, k.title FROM knowledge k
            WHERE k.deleted_at IS NULL AND k.status = 'APPROVED'
              AND NOT EXISTS (
                  SELECT 1 FROM kb_chunk c JOIN knowledge_version v ON v.id = c.version_id
                  WHERE v.knowledge_id = k.id AND c.is_active
              )
            ORDER BY k.created_at
        """)).fetchall()
    return [{"knowledge_id": str(kid), "title": title} for kid, title in rows]


def _published_document(knowledge_id: str) -> Dict[str, object]:
    """The approved document JSON, or, when that file is gone, the same content as kept on its knowledge row."""
    from app.core.database import get_sync_engine
    from app.rag.router import resolve_approved_file

    path = resolve_approved_file(knowledge_id)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    with get_sync_engine().connect() as conn:
        row = conn.execute(text("SELECT title, file_name, ai_summary, metadata FROM knowledge WHERE id = :k"),
                           {"k": knowledge_id}).fetchone()
    if not row:
        return {}
    doc = dict(row[3]) if isinstance(row[3], dict) else {}
    doc.update({"knowledge_id": knowledge_id, "title": row[0] or doc.get("title"),
                "file_name": row[1] or doc.get("file_name"), "summary": row[2] or doc.get("summary") or ""})
    return doc


async def rechunk_document(knowledge_id: str) -> Dict[str, object]:
    """Re-chunks one published document from its summary and publishes it again."""
    from app.rag.router import approve_document

    doc = _published_document(knowledge_id)
    if not (doc.get("summary") or "").strip():
        return {"knowledge_id": knowledge_id, "ok": False, "result": "no published content to index"}
    doc.pop("chunks", None)
    os.makedirs("data/pending", exist_ok=True)
    with open(os.path.join("data/pending", f"{knowledge_id}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=4, ensure_ascii=False)
    # Generated-question probes cost model calls per document; a knowledge-base-wide re-chunk after a deploy
    # must not turn into hundreds of them, so only the token-free checks run here
    res = await approve_document(knowledge_id=knowledge_id, pipeline=None, bm25=None, quality_probes=False)
    ok = isinstance(res, dict) and knowledge_id in (res.get("approved_ids") or []) and not res.get("publish_failures")
    return {"knowledge_id": knowledge_id, "ok": ok, "result": res if not ok else None}


_RUNNING = False


async def rechunk_outdated() -> List[Dict[str, object]]:
    """Re-chunks every outdated or unindexed published document, one after another."""
    global _RUNNING
    if _RUNNING:
        return []
    _RUNNING = True
    results = []
    try:
        unindexed = await asyncio.to_thread(unindexed_documents)
        if unindexed:
            logger.warning(f"[REPROCESS] {len(unindexed)} approved documents have no active chunk (the chatbot cannot "
                           f"find them): {[d['title'] for d in unindexed]}; indexing them.")
        docs = unindexed + [d for d in await asyncio.to_thread(outdated_documents)
                            if d["knowledge_id"] not in {u["knowledge_id"] for u in unindexed}]
        if len(docs) > len(unindexed):
            logger.info(f"[REPROCESS] {len(docs) - len(unindexed)} published documents were chunked by an older chunker; re-chunking.")
        for d in docs:
            try:
                r = await rechunk_document(d["knowledge_id"])
            except Exception as e:
                r = {"knowledge_id": d["knowledge_id"], "ok": False, "result": str(e)}
            results.append(r)
            logger.info(f"[REPROCESS] {d['title']}: {'done' if r['ok'] else 'FAILED ' + str(r['result'])[:200]}")
            await asyncio.sleep(1)
    finally:
        _RUNNING = False
    return results
