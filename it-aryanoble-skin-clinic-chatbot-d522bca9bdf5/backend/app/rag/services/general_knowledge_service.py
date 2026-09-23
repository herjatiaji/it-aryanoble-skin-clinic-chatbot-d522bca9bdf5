"""
Dedicated CRUD Service for General Knowledge Assistant (Arya Noble).

This service executes deterministic, validated database operations (READ metadata, EDIT, DELETE)
on approved Knowledge Base documents across:
- Local JSON storage (data/output/)
- PostgreSQL (Knowledge table)
- PGVector (arya_noble_kb table)
- MinIO Object Storage (approved & canonical buckets)
- BM25 Index (bm25_index.pkl)

Architectural Principle:
The LLM is NOT the primary decider of CRUD operations.
The AI Orchestrator validates requests against this service, displays a two-step preview,
and upon explicit Admin confirmation, delegates mutation to this Dedicated Service.
"""

import os
import re
import json
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from loguru import logger

from app.rag.config import settings
from app.rag.services.rag_retriever import parse_date_safely


def resolve_approved_file(knowledge_id: str, output_dir: str = "data/output") -> Optional[str]:
    """Resolves the physical JSON file path for an approved document, hydrating from MinIO if needed."""
    if not knowledge_id:
        return None

    k_id = str(knowledge_id).strip()

    # 1. Try exact paths
    direct_paths = [
        k_id,
        os.path.join(output_dir, f"{k_id}.json"),
        os.path.join(output_dir, f"{k_id}_parsed.json"),
        os.path.join("backend", output_dir, f"{k_id}.json"),
        os.path.join("backend", output_dir, f"{k_id}_parsed.json"),
    ]
    for p in direct_paths:
        if os.path.exists(p) and os.path.isfile(p):
            return p

    # 2. Search in directories
    for folder in [output_dir, "data/pending", os.path.join("backend", output_dir), os.path.join("backend", "data/pending")]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith(".json") and f != "bm25_index.pkl":
                    f_path = os.path.join(folder, f)
                    try:
                        with open(f_path, "r", encoding="utf-8") as fp:
                            doc = json.load(fp)
                        if isinstance(doc, dict):
                            doc_id = str(doc.get("knowledge_id") or doc.get("id") or "")
                            doc_title = str(doc.get("title") or "")
                            file_name = str(doc.get("file_name") or "")
                            f_no_ext = f.replace(".json", "").replace("_parsed", "")
                            if k_id.lower() in (doc_id.lower(), doc_title.lower(), file_name.lower(), f_no_ext.lower(), f.lower()):
                                return f_path
                    except Exception as err:
                        logger.debug(f"[DedicatedService] Error scanning file {f}: {err}")

    # 3. MinIO Hydration fallback
    clean_p = os.path.join(output_dir, f"{k_id}.json")
    try:
        from app.services.storage import get_approved_json
        approved_data = get_approved_json(k_id)
        if approved_data:
            os.makedirs(output_dir, exist_ok=True)
            with open(clean_p, "w", encoding="utf-8") as fp:
                json.dump(approved_data, fp, indent=4, ensure_ascii=False)
            return clean_p
    except Exception as e:
        logger.debug(f"[DedicatedService] MinIO approved hydration note: {e}")

    # 4. PostgreSQL Database Hydration fallback
    try:
        import asyncio
        import concurrent.futures
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy import text
        from app.core.config import settings

        async def _fetch_from_db():
            temp_engine = create_async_engine(settings.DATABASE_URL)
            try:
                async with AsyncSession(temp_engine) as session:
                    res = await session.execute(
                        text("SELECT id, title, file_name, ai_summary, metadata FROM knowledge WHERE (id::text = :k_id OR LOWER(title) = LOWER(:k_id) OR LOWER(file_name) = LOWER(:k_id)) AND status = 'APPROVED' AND deleted_at IS NULL LIMIT 1"),
                        {"k_id": k_id}
                    )
                    return res.fetchone()
            finally:
                await temp_engine.dispose()

        def _worker():
            return asyncio.run(_fetch_from_db())

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                row = pool.submit(_worker).result()
        else:
            row = asyncio.run(_fetch_from_db())

        if row:
            row_id, title, fname, summary, meta_val = row[0], row[1], row[2], row[3], row[4]
            m_dict = meta_val if isinstance(meta_val, dict) else (json.loads(meta_val) if isinstance(meta_val, str) else {})
            doc = {
                "knowledge_id": str(row_id),
                "batch_id": m_dict.get("batch_id"),
                "file_name": fname or str(row_id),
                "title": title or fname or str(row_id),
                "status": "Approved",
                "summary": summary or "",
                "chunks": m_dict.get("chunks", []),
                "images": m_dict.get("images", []),
                "image_urls": m_dict.get("image_urls", []),
                "categories": m_dict.get("categories", []),
                "visibility_settings": m_dict.get("visibility_settings", {})
            }
            os.makedirs(output_dir, exist_ok=True)
            clean_p = os.path.join(output_dir, f"{row_id}.json")
            with open(clean_p, "w", encoding="utf-8") as fp:
                json.dump(doc, fp, indent=4, ensure_ascii=False)
            return clean_p
    except Exception as db_e:
        logger.debug(f"[DedicatedService] DB hydration fallback note: {db_e}")

def resolve_pending_file(knowledge_id: str, pending_dir: str = "data/pending") -> Optional[str]:
    """Resolves physical JSON file path for a pending/staging document."""
    if not knowledge_id:
        return None
    k_id = str(knowledge_id).strip()
    candidate_dirs = [pending_dir, os.path.join("backend", pending_dir)]
    for p_dir in candidate_dirs:
        if not os.path.exists(p_dir):
            continue
        clean_p = os.path.join(p_dir, f"{k_id}.json")
        if os.path.exists(clean_p) and os.path.isfile(clean_p):
            return clean_p
        parsed_p = os.path.join(p_dir, f"{k_id}_parsed.json")
        if os.path.exists(parsed_p) and os.path.isfile(parsed_p):
            return parsed_p
        for f in os.listdir(p_dir):
            if f.endswith(".json"):
                full_p = os.path.join(p_dir, f)
                name_no_ext = f[:-5]
                if f.startswith(k_id) or name_no_ext == k_id or name_no_ext.replace("_parsed", "") == k_id:
                    return full_p
                try:
                    with open(full_p, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    if isinstance(data, dict) and (data.get("knowledge_id") == k_id or data.get("file_name") == k_id):
                        return full_p
                except Exception:
                    pass
    return None


class GeneralKnowledgeService:
    """Dedicated service for performing safe, item-level CRUD operations on approved KB data."""

    @staticmethod
    def detect_mutation_scope(user_prompt: str) -> str:
        """
        Detects whether the prompt explicitly requests GLOBAL scope across the entire Knowledge Base/all products.
        Default scope is always SINGLE_ITEM unless explicit global keywords are present.
        """
        if not user_prompt:
            return "SINGLE_ITEM"

        global_keywords = [
            r'\bdi\s+seluruh\s+kb\b',
            r'\bdi\s+seluruh\s+knowledge\b',
            r'\bdi\s+seluruh\s+dokumen\b',
            r'\bdi\s+seluruh\s+database\b',
            r'\bdi\s+semua\s+produk\b',
            r'\bdi\s+semua\s+dokumen\b',
            r'\bpada\s+semua\s+produk\b',
            r'\bpada\s+seluruh\s+produk\b',
            r'\bsemua\s+produk\b',
            r'\bseluruh\s+produk\b',
            r'\ball\s+products\b',
            r'\bacross\s+the\s+knowledge\s+base\b',
            r'\bacross\s+all\s+documents\b',
        ]
        prompt_low = user_prompt.lower()
        for kw in global_keywords:
            if re.search(kw, prompt_low):
                return "GLOBAL"
        return "SINGLE_ITEM"

    @staticmethod
    def log_mutation_summary(
        operation_id: str,
        action: str,  # "UPDATE" or "DELETE"
        scope: str,   # "SINGLE_ITEM" or "GLOBAL"
        knowledge_id: str,
        entity_id: str,
        target_name: str,
        field: str,
        old_value: Any,
        new_value: Any,
        affected_documents: int,
        affected_entities: int,
        chunks_old: int,
        chunks_new: int,
        canonical_status: str = "SUCCESS",
        pgvector_status: str = "SUCCESS",
        bm25_status: str = "SUCCESS",
        retrieval_status: str = "SUCCESS",
        status: str = "APPLIED"
    ):
        log_box = f"""
============================================================
GENERAL KNOWLEDGE MUTATION
============================================================
operation_id : {operation_id}
action       : {action}
scope        : {scope}

TARGET
------------------------------------------------------------
knowledge_id : {knowledge_id}
entity_id    : {entity_id or '-'}
name         : {target_name}

CHANGE
------------------------------------------------------------
field        : {field}
old_value    : {old_value if old_value is not None else '-'}
new_value    : {new_value if new_value is not None else '-'}

AFFECTED
------------------------------------------------------------
documents    : {affected_documents}
entities     : {affected_entities}
chunks_old   : {chunks_old}
chunks_new   : {chunks_new}

RESULT
------------------------------------------------------------
canonical    : {canonical_status}
pgvector     : {pgvector_status}
bm25         : {bm25_status}
retrieval    : {retrieval_status}
status       : {status}
============================================================
"""
        logger.info(log_box)

    @staticmethod
    def clean_markdown_text(text: str, targets: list[str], ing_kw: Optional[str] = None) -> str:
        """
        Surgically cleans markdown sections, cards, bullets, and table rows for target entities.
        Cleans preceding/following image tags, full card blocks, and bullet items.
        """
        if not text or not targets:
            return text or ""
        res = text
        for t in targets:
            if not t or len(t.strip()) < 2:
                continue
            esc = re.escape(t.strip())

            # 1. Full section with heading matching target (including preceding image tag or following image tag)
            res = re.sub(
                r'(?:^|\n)(?:[ \t]*!\[[^\]]*\]\([^\)]+\)\s*\n+)?(?:#{1,4}\s*[^\n]*' + esc + r'[^\n]*\n(?:(?!^#{1,4}\s)[^\n]*\n?)*)',
                '\n',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 2. Product Card block where heading is generic (e.g. ### Detail Produk) but bullets contain target
            card_regex = re.compile(
                r'(?:^|\n)(?:[ \t]*!\[[^\]]*\]\([^\)]+\)\s*\n+)?(?:#{1,4}\s*[^\n]+\n+)(?:[ \t]*!\[[^\]]*\]\([^\)]+\)\s*\n+)?((?:[ \t]*[-*]\s*\*\*[^*]+\*\*\s*[:–-][^\n]+(?:\n|$))+)',
                flags=re.IGNORECASE
            )
            def _filter_card(match):
                card_block = match.group(0)
                bullets = match.group(1)
                if re.search(rf'\b{esc}\b', bullets, re.IGNORECASE):
                    return '\n'
                return card_block

            res = card_regex.sub(_filter_card, res)

            # 3. Numbered list or bullet line matching target (plus any indented sub-bullets)
            res = re.sub(
                rf'^[ \t]*(?:[-*]|\d+\.)\s*[^\n]*\b{esc}\b[^\n]*(?:\n[ \t]{{2,}}[^\n]+)*\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 4. Standalone table rows containing target
            res = re.sub(
                rf'^[ \t]*\|[^\n]*\b{esc}\b[^\n]*\|\s*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 5. Any orphan image tags that have alt text matching target
            res = re.sub(
                rf'^[ \t]*!\[[^\n\]]*{esc}[^\n\]]*\]\([^\)]+\)\s*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 6. Fallback line match
            res = re.sub(
                rf'^[^\n]*\b{esc}\b[^\n]*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

        if ing_kw and len(ing_kw.strip()) > 1:
            esc_ing = re.escape(ing_kw.strip())
            res = re.sub(
                rf'^[^\n]*\b{esc_ing}\b[^\n]*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

        return re.sub(r'\n{3,}', '\n\n', res).strip()

    @staticmethod
    async def prune_chat_messages_for_deleted_targets(
        db,
        delete_targets: list[str],
        session_id: Optional[Any] = None,
        knowledge_id: Optional[str] = None
    ) -> int:
        """
        Prunes or sanitizes ChatMessage records in PostgreSQL that reference deleted targets.
        Removes the deleted item from assistant messages, or deletes the message entirely
        if it only contained information about the deleted item, preventing LLM history contamination.
        """
        if not db or not delete_targets:
            return 0

        from app.models.chat import ChatMessage, ChatRole
        from sqlalchemy import select
        import uuid as _uuid

        pruned_count = 0
        try:
            stmt = select(ChatMessage).where(ChatMessage.role == ChatRole.ASSISTANT)
            if session_id:
                try:
                    s_uuid = _uuid.UUID(str(session_id).strip()) if not isinstance(session_id, _uuid.UUID) else session_id
                    stmt = stmt.where(ChatMessage.session_id == s_uuid)
                except Exception:
                    pass

            res = await db.execute(stmt)
            messages = res.scalars().all()

            for msg in messages:
                content = msg.content or ""
                matches_target = any(t.lower() in content.lower() for t in delete_targets if len(t) > 2)
                
                att = msg.attachments or {}
                is_op_preview = (
                    att.get("action") in ("delete_preview", "delete_applied") or
                    "Pratinjau Penghapusan" in content or
                    "Confirm & Delete" in content
                )
                
                if matches_target or is_op_preview:
                    cleaned_content = GeneralKnowledgeService.clean_markdown_text(content, delete_targets)
                    substantive = re.sub(r'^[#\|\-\*\s\:\d\.]+', '', cleaned_content).strip()
                    substantive = re.sub(r'(?:Pratinjau|Penghapusan|Perubahan|Dokumen Terdampak|Catatan Keamanan|Apakah Anda yakin).*$', '', substantive, flags=re.IGNORECASE | re.DOTALL).strip()

                    if not substantive or len(substantive) < 15 or is_op_preview:
                        await db.delete(msg)
                        pruned_count += 1
                        logger.info(f"[PruneChat] Deleted dedicated assistant message {msg.id} for targets {delete_targets}")
                    else:
                        msg.content = cleaned_content
                        db.add(msg)
                        pruned_count += 1
                        logger.info(f"[PruneChat] Sanitized assistant message {msg.id} removing {delete_targets}")

            await db.commit()
        except Exception as e:
            logger.warning(f"[PruneChat] Error pruning chat messages: {e}")

        return pruned_count

    @staticmethod
    async def find_all_target_documents_and_item(
        query: str, output_dir: str = "data/output", db: Optional[Any] = None
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """
        Scans approved documents to identify the matching target entity/item name and
        ALL documents in the Knowledge Base that contain, define, or are affected by it.
        Returns (target_item_name, list_of_matched_docs) sorted by priority:
        1. Explicit UUID matches
        2. Dedicated documents (where doc_title or file_name matches target entity)
        3. Catalog documents (where target entity is a section heading)
        4. Content mentions
        """
        q_lower = query.lower()

        # Check if an explicit UUID is present in query
        uuid_matches = re.findall(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
            query
        )
        explicit_uuid = uuid_matches[0].lower() if uuid_matches else None

        # 1. Check for ingredient-based delete query:
        # e.g.: "hapus seluruh produk dengan yang mengandung Hyaluronic Acid"
        ingredient_delete_match = re.search(
            r'\b(?:hapus|delete|hilangkan|remove|buang|bersihkan|tiadakan|drop|clear|wipe|erase)\s+(?:seluruh|semua|setiap)?\s*(?:produk|item|barang|treatment)?\s*(?:dengan\s+)?(?:yang\s+)?(?:mengandung|ada\s+kandungan|kandungan|bahan|komposisi|berisi)\s+["\'“]?([^"\'”\n\?\.\(]+)',
            query,
            re.IGNORECASE
        )
        ingredient_filter = None
        if ingredient_delete_match:
            raw_ing = ingredient_delete_match.group(1).strip()
            raw_ing = re.sub(r'\s+(?:dari|pada|di|dalam|ke)\s+.*$', '', raw_ing, flags=re.IGNORECASE).strip()
            raw_ing = re.sub(r'[\s,\.]+(?:ya|dong|tolong|mohon|terima\s*kasih|thanks)$', '', raw_ing, flags=re.IGNORECASE).strip()
            raw_ing = re.sub(r'^[\s\*_\`"\'“”.,]+|[\s\*_\`"\'“”.,]+$', '', raw_ing).strip()
            if len(raw_ing) > 1:
                ingredient_filter = raw_ing

        # 2. Check for edit with transition word:
        # e.g.: "Ubah informasi kandungan Hyaluronic Acid menjadi Polyglutamic Acid (PGA) pada semua produk"
        edit_trans_match = re.search(
            r'\b(?:ubah|ganti|edit|tukar|salin|update|perbarui|revisi)\s+(?:informasi|data|bagian|detail)?\s*(kandungan|komposisi|ingredients|bahan|ukuran|harga|sku|nama|kategori|deskripsi)?\s*["\'“]?([^"\'”\n]+?)["\'”?]?\s+(?:menjadi|jadi|ke|sebagai|=)\s*["\'“]?([^"\'”\n]+?)["\'”?]?\s*(?:pada|di|dalam|untuk)?\s*(?:semua|seluruh|setiap)?\s*(?:produk|item|dokumen|kb|knowledge|data)?$',
            query,
            re.IGNORECASE
        )
        edit_target_candidate = None
        if edit_trans_match:
            edit_target_candidate = edit_trans_match.group(2).strip()
            # Clean leading field or preposition words if captured
            edit_target_candidate = re.sub(r'^(?:informasi|data|bagian|detail|kandungan|komposisi|ingredients|bahan|ukuran|harga|sku|nama|kategori|deskripsi)\s+', '', edit_target_candidate, flags=re.IGNORECASE).strip()

        # 3. Standard command extraction
        container_candidate = None
        explicit_item_candidate = ingredient_filter or edit_target_candidate
        action_verbs_regex = r'\b(?:hapus|delete|hilangkan|remove|buang|bersihkan|tiadakan|drop|clear|wipe|erase|ubah|ganti|edit|tukar|salin|revisi|pembaruan|perbarui|modifikasi|perbaiki|gantikan|gantiin|update|pasang|set|sesuaikan)\b'
        
        if not explicit_item_candidate:
            cmd_match = re.search(
                rf'{action_verbs_regex}\s+(?:bagian|item|produk|tahapan|parameter|indikator|baris|kolom|tabel)?\s*["\'“]?([^"\'”\n]+?)["\'”?]?\s+(?:dari|pada|di|dalam)\s+["\'“]?([^"\'”\n]+)["\'”]?',
                query,
                re.IGNORECASE
            )
            if cmd_match:
                explicit_item_candidate = cmd_match.group(1).strip()
                container_candidate = cmd_match.group(2).strip()
            else:
                quote_match = re.search(r'["\'“]([^"\'”]+)["\'”]', query)
                if quote_match:
                    explicit_item_candidate = quote_match.group(1).strip()
                else:
                    keyword_match = re.search(
                        r'\b(?:bagian|item|produk|tahapan|parameter|indikator|baris|kolom|tabel)\s+([a-zA-Z0-9\s&+\-_/]+?)(?:\s+(?:pada|di|dari|dalam|menjadi|ke|sebagai)\b|$)',
                        query,
                        re.IGNORECASE
                    )
                    if keyword_match:
                        candidate = keyword_match.group(1).strip()
                        if len(candidate) > 2 and candidate.lower() not in ("dokumen", "doc", "kb", "knowledge", "tersebut", "ini", "itu"):
                            explicit_item_candidate = candidate

        # Clean core entity extraction for edit/update patterns:
        if not explicit_item_candidate:
            core = re.sub(
                rf'^\s*(?:tolong\s+|mohon\s+|coba\s+)?{action_verbs_regex}\s+',
                '',
                query,
                flags=re.IGNORECASE
            )
            # Strip trailing target value (ke 40 g / jadi 40 g / dengan 50000 / menjadi 50000)
            val_m = re.search(r'\b(?:menjadi|jadi|ke|sebagai|dengan|sebesar|berupa|=)\s+[`"\'“]?([^\n\r`"\'”]+)[\'"”`]?$', core, re.IGNORECASE)
            if val_m:
                core = core[:val_m.start()].strip()
            else:
                # Also strip raw trailing value without transition word (e.g. "Facial Wash 40 g" -> "Facial Wash")
                raw_val_m = re.search(r'\b(\d+(?:\.\d+)?\s*(?:g|gram|ml|l|kg|oz)\b|(?:Rp\.?\s*)?\d[\d\.\,]+)$', core, re.IGNORECASE)
                if raw_val_m:
                    core = core[:raw_val_m.start()].strip()

            # Strip leading field words
            field_words = [
                'ukuran', 'size', 'berat', 'volume', 'netto',
                'harga', 'price', 'biaya', 'tarif',
                'sku', 'kode_sku', 'kode',
                'nama_produk', 'nama', 'judul',
                'kategori', 'category',
                'deskripsi', 'description', 'keterangan',
                'indikasi', 'cara_pakai', 'dosis',
                'kandungan', 'komposisi', 'ingredients', 'key ingredients', 'bahan'
            ]
            for fw in field_words:
                core = re.sub(rf'\b{fw}\b', '', core, flags=re.IGNORECASE).strip()

            core = re.sub(r'^\s*(?:pada|di|dari|dalam|untuk|bagian|item|produk|treatment|dokumen)\s+', '', core, flags=re.IGNORECASE).strip()
            core = re.sub(r'\s*(?:pada|di|dari|dalam|untuk|bagian|item|produk|treatment|dokumen)\s*$', '', core, flags=re.IGNORECASE).strip()
            if len(core) > 2 and not re.match(r'^[0-9a-fA-F\-]{10,}$', core):
                explicit_item_candidate = core

        # Filter out purely anaphoric terms from explicit_item_candidate
        if explicit_item_candidate:
            explicit_item_candidate = re.sub(r'^[\s\*_\`"\'“”.,]+|[\s\*_\`"\'“”.,]+$', '', explicit_item_candidate).strip()
            anaphoric_clean = explicit_item_candidate.lower().strip()
            if anaphoric_clean in ("tersebut", "produk tersebut", "item tersebut", "dokumen tersebut", "ini", "itu", "nya", "produk ini", "produk itu"):
                explicit_item_candidate = None

        # Fetch soft-deleted and active IDs to avoid matching deleted knowledge documents
        deleted_ids = set()
        active_ids = set()
        try:
            from app.models.knowledge import Knowledge
            from sqlalchemy import select
            
            async def _load_db_ids(sess):
                del_res = await sess.execute(select(Knowledge.id).where(Knowledge.deleted_at.is_not(None)))
                d_ids = {str(r).lower() for r in del_res.scalars().all() if r}
                act_res = await sess.execute(select(Knowledge.id).where(Knowledge.deleted_at.is_(None)))
                a_ids = {str(r).lower() for r in act_res.scalars().all() if r}
                return d_ids, a_ids

            if db:
                deleted_ids, active_ids = await _load_db_ids(db)
            else:
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as sess:
                    deleted_ids, active_ids = await _load_db_ids(sess)
        except Exception as db_err:
            logger.debug(f"[GeneralKnowledgeService] Notice loading knowledge IDs: {db_err}")

        search_folders = [output_dir, os.path.join("backend", output_dir)]
        seen_doc_ids = set()
        matched_docs = []
        resolved_entity_name = explicit_item_candidate

        for folder in search_folders:
            if not os.path.exists(folder):
                continue
            for f in os.listdir(folder):
                if not f.endswith(".json") or f == "bm25_index.pkl":
                    continue
                f_path = os.path.join(folder, f)
                try:
                    with open(f_path, "r", encoding="utf-8") as fp:
                        doc = json.load(fp)
                    if not isinstance(doc, dict):
                        continue

                    doc_id = str(doc.get("knowledge_id") or doc.get("id") or f.replace(".json", "").replace("_parsed", "")).strip()
                    doc_id_low = doc_id.lower()

                    # 1. Skip and purge if document was soft-deleted in DB
                    if doc_id_low in deleted_ids:
                        try:
                            os.remove(f_path)
                            logger.info(f"[GeneralKnowledgeService] Purged stale soft-deleted file during scan: {f_path}")
                        except Exception:
                            pass
                        continue

                    # 2. If active IDs are known, skip any orphan file not belonging to an active document
                    if active_ids and doc_id_low not in active_ids:
                        continue

                    if doc_id in seen_doc_ids:
                        continue

                    doc_title = str(doc.get("title") or doc.get("file_name") or "")
                    file_name = str(doc.get("file_name") or "")
                    summary = str(doc.get("summary") or "")
                    batch_summary = str(doc.get("batch_summary") or "")

                    # Document's own content corpus (summary + chunks)
                    doc_own_corpus = summary
                    for chunk in doc.get("chunks", []):
                        if isinstance(chunk, dict):
                            doc_own_corpus += "\n" + str(chunk.get("text", ""))

                    # Full text corpus including batch and staging
                    full_text_corpus = doc_own_corpus + "\n" + batch_summary
                    if doc.get("staging_history") and isinstance(doc.get("staging_history"), list):
                        for t in doc.get("staging_history"):
                            if isinstance(t, dict) and t.get("role") == "assistant":
                                full_text_corpus += "\n" + str(t.get("content", ""))

                    # Collect candidate items/sections from this document
                    doc_candidates = []
                    for k in ["product_name", "title", "section", "heading", "treatment", "treatment_name", "category"]:
                        v = doc.get(k)
                        if v and isinstance(v, str) and len(v.strip()) > 2 and v.strip().lower() not in ("general", "unknown"):
                            doc_candidates.append(v.strip())

                    # Headings in summary
                    for h in re.findall(r'^#{1,4}\s+([^\n\r]+)', full_text_corpus, re.MULTILINE):
                        h_clean = re.sub(r'[\*\_]', '', h).strip()
                        if len(h_clean) > 2 and h_clean.lower() not in ("ringkasan dokumen", "penutup", "evaluasi hasil", "profil pasien", "detail perawatan"):
                            doc_candidates.append(h_clean)

                    # Product names from modular bullet points in summary / corpus
                    for p_m in re.findall(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', full_text_corpus, re.IGNORECASE):
                        p_clean = re.sub(r'[\*\_`]', '', p_m).strip()
                        if len(p_clean) > 2:
                            doc_candidates.append(p_clean)

                    # Product names from image alt texts
                    for alt_m in re.findall(r'!\[([^\]]+)\]\([^\)]+\)', full_text_corpus):
                        alt_clean = re.sub(r'[\*\_`]', '', alt_m).strip()
                        if len(alt_clean) > 2 and alt_clean.lower() not in ("image", "foto", "product", "foto produk", "dokumen", "document image"):
                            doc_candidates.append(alt_clean)

                    # Chunks metadata
                    for chunk in doc.get("chunks", []):
                        if not isinstance(chunk, dict):
                            continue
                        meta = chunk.get("metadata", {})
                        for k in ["product_name", "title", "section", "heading", "treatment", "treatment_name"]:
                            v = meta.get(k)
                            if v and isinstance(v, str) and len(v.strip()) > 2 and v.strip().lower() not in ("general", "unknown"):
                                doc_candidates.append(v.strip())

                    # Clean candidates
                    unique_candidates = []
                    seen_c = set()
                    for c in doc_candidates:
                        if c.lower() not in seen_c:
                            seen_c.add(c.lower())
                            unique_candidates.append(c)
                    unique_candidates.sort(key=len, reverse=True)

                    # Calculate match score
                    score = 0
                    match_type = "mention"
                    matched_item_for_doc = None
                    target_sub_items = []

                    # 1. Explicit UUID in prompt matches this doc
                    if explicit_uuid and (explicit_uuid == doc_id.lower()):
                        score += 1000
                        match_type = "explicit_uuid"

                    # 2. Ingredient filter match (e.g. "Hyaluronic Acid", "Retinol", "BHA")
                    # Check document's own corpus so cross-document batch summaries don't cause false positives
                    if ingredient_filter:
                        ing_low = ingredient_filter.lower()
                        ing_regex = re.compile(rf'\b{re.escape(ing_low)}\b', re.IGNORECASE)
                        if ing_regex.search(doc_own_corpus):
                            score += 450
                            match_type = "ingredient_match"
                            # Identify specific product sections containing this ingredient
                            sections = re.split(r'(?=^#{1,3}\s+)', full_text_corpus, flags=re.MULTILINE)
                            for s in sections:
                                m_h = re.match(r'^#{1,3}\s+([^\n]+)', s)
                                if m_h:
                                    h_name = re.sub(r'[\*\_]', '', m_h.group(1)).strip()
                                    if ing_regex.search(s) and h_name.lower() not in ("ringkasan dokumen", "penutup", "evaluasi hasil", "profil pasien", "detail perawatan"):
                                        target_sub_items.append(h_name)

                            # Also check markdown table rows for product name
                            for line in full_text_corpus.splitlines():
                                if ing_regex.search(line) and "|" in line:
                                    cols = [c.strip() for c in line.split("|") if c.strip()]
                                    for col in cols:
                                        col_clean = re.sub(r'!\[.*?\]\(.*?\)', '', col).strip()
                                        if len(col_clean) > 3 and not col_clean.startswith("http") and not col_clean.startswith("/api/storage"):
                                            if any(kw in col_clean.lower() for kw in ["erha", "serum", "gel", "cream", "wash", "lotion", "moisturizer", "toner", "sabun"]):
                                                target_sub_items.append(col_clean)
                                                break

                            # Deduplicate preserving order
                            seen_items = set()
                            unique_sub_items = []
                            for it in target_sub_items:
                                if it.lower() not in seen_items:
                                    seen_items.add(it.lower())
                                    unique_sub_items.append(it)

                            if unique_sub_items:
                                matched_item_for_doc = ", ".join(unique_sub_items)
                            else:
                                matched_item_for_doc = f"Produk dengan kandungan {ingredient_filter}"

                            if not resolved_entity_name:
                                resolved_entity_name = matched_item_for_doc

                    # 3. Check explicit item candidate against document title / filename / candidates / summary
                    elif explicit_item_candidate:
                        cand_low = explicit_item_candidate.lower()
                        # Exact or strong title match -> Dedicated document!
                        if cand_low == doc_title.lower() or cand_low in doc_title.lower() or cand_low in file_name.lower().replace("_", " "):
                            score += 500 + len(doc_title)
                            match_type = "dedicated_document"
                            matched_item_for_doc = explicit_item_candidate
                            if not resolved_entity_name or len(doc_title) > len(resolved_entity_name):
                                resolved_entity_name = doc_title

                        # Section match in catalog document
                        for c in unique_candidates:
                            if cand_low == c.lower() or cand_low in c.lower() or c.lower() in cand_low:
                                if match_type != "dedicated_document":
                                    score += 200 + len(c)
                                    match_type = "section"
                                matched_item_for_doc = c
                                if not resolved_entity_name:
                                    resolved_entity_name = c
                                break

                        # Content / ingredient match in summary or batch_summary
                        if score == 0 and (cand_low in full_text_corpus.lower()):
                            score += 150 + len(explicit_item_candidate)
                            match_type = "content_mention"
                            matched_item_for_doc = explicit_item_candidate

                    # 4. Check query text against document title or unique candidates
                    if score == 0:
                        if doc_title and len(doc_title) > 3 and doc_title.lower() in q_lower:
                            score += 300 + len(doc_title)
                            match_type = "title_in_query"
                            matched_item_for_doc = doc_title
                            if not resolved_entity_name:
                                resolved_entity_name = doc_title
                        else:
                            for c in unique_candidates:
                                if len(c) > 3 and c.lower() in q_lower:
                                    score += 150 + len(c)
                                    match_type = "item_in_query"
                                    matched_item_for_doc = c
                                    if not resolved_entity_name or len(c) > len(resolved_entity_name):
                                        resolved_entity_name = c
                                    break

                    if score > 0:
                        seen_doc_ids.add(doc_id)
                        doc_copy = dict(doc)
                        doc_copy["_matched_context_label"] = matched_item_for_doc or resolved_entity_name or doc_title
                        matched_docs.append({
                            "knowledge_id": doc_id,
                            "title": doc_title,
                            "file_name": file_name,
                            "batch_id": doc.get("batch_id") or doc.get("metadata", {}).get("batch_id"),
                            "score": score,
                            "match_type": match_type,
                            "target_item": matched_item_for_doc or resolved_entity_name,
                            "doc_data": doc_copy
                        })

                except Exception as e:
                    logger.debug(f"[DedicatedService] scan error {f}: {e}")

        # DB Hydration fallback: scan active APPROVED PostgreSQL Knowledge records if disk scan yields no matches
        if not matched_docs:
            try:
                from app.models.knowledge import Knowledge, KnowledgeStatus
                from sqlalchemy import select, or_

                async def _scan_db(session):
                    stmt = select(Knowledge).where(
                        or_(Knowledge.status == KnowledgeStatus.APPROVED, Knowledge.status == 'APPROVED'),
                        Knowledge.deleted_at.is_(None)
                    )
                    res = await session.execute(stmt)
                    return res.scalars().all()

                if db:
                    k_rows = await _scan_db(db)
                else:
                    from app.core.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as session:
                        k_rows = await _scan_db(session)

                for k_obj in k_rows:
                    doc_id = str(k_obj.id)
                    if doc_id in seen_doc_ids:
                        continue
                    doc_title = str(k_obj.title or k_obj.file_name or doc_id)
                    file_name = str(k_obj.file_name or "")
                    summary = str(k_obj.ai_summary or "")
                    m_dict = dict(k_obj.metadata_) if isinstance(k_obj.metadata_, dict) else {}
                    doc = {
                        "knowledge_id": doc_id,
                        "batch_id": m_dict.get("batch_id"),
                        "file_name": file_name,
                        "title": doc_title,
                        "summary": summary,
                        "chunks": m_dict.get("chunks", []),
                        "images": m_dict.get("images", []),
                        "image_urls": m_dict.get("image_urls", []),
                        "categories": m_dict.get("categories", []),
                        "visibility_settings": m_dict.get("visibility_settings", {})
                    }

                    doc_candidates = [doc_title]
                    for h in re.findall(r'^#{1,4}\s+([^\n\r]+)', summary, re.MULTILINE):
                        h_clean = re.sub(r'[\*\_]', '', h).strip()
                        if len(h_clean) > 2:
                            doc_candidates.append(h_clean)

                    score = 0
                    match_type = "mention"
                    matched_item_for_doc = None

                    if explicit_uuid and (explicit_uuid == doc_id.lower()):
                        score += 1000
                        match_type = "explicit_uuid"

                    if ingredient_filter:
                        ing_low = ingredient_filter.lower()
                        ing_regex = re.compile(rf'\b{re.escape(ing_low)}\b', re.IGNORECASE)
                        full_txt = summary + " " + doc_title
                        if ing_regex.search(full_txt):
                            score += 450
                            match_type = "ingredient_match"
                            matched_item_for_doc = f"Produk dengan kandungan {ingredient_filter}"
                            if not resolved_entity_name:
                                resolved_entity_name = matched_item_for_doc

                    if explicit_item_candidate:
                        cand_low = explicit_item_candidate.lower()
                        if cand_low == doc_title.lower() or cand_low in doc_title.lower() or cand_low in file_name.lower().replace("_", " "):
                            score += 500 + len(doc_title)
                            match_type = "dedicated_document"
                            matched_item_for_doc = explicit_item_candidate
                            if not resolved_entity_name:
                                resolved_entity_name = doc_title

                        for c in doc_candidates:
                            if cand_low == c.lower() or cand_low in c.lower() or c.lower() in cand_low:
                                if match_type != "dedicated_document":
                                    score += 200 + len(c)
                                    match_type = "section"
                                matched_item_for_doc = c
                                if not resolved_entity_name:
                                    resolved_entity_name = c
                                break

                        if score == 0 and (re.search(r'\b' + re.escape(cand_low) + r'\b', doc_own_corpus, re.IGNORECASE) or cand_low in doc_own_corpus.lower()):
                            score += 350 + len(cand_low)
                            match_type = "section"
                            matched_item_for_doc = explicit_item_candidate
                            if not resolved_entity_name:
                                resolved_entity_name = explicit_item_candidate

                    if score == 0:
                        if doc_title and len(doc_title) > 3 and doc_title.lower() in q_lower:
                            score += 300 + len(doc_title)
                            match_type = "title_in_query"
                            matched_item_for_doc = doc_title
                            if not resolved_entity_name:
                                resolved_entity_name = doc_title
                        else:
                            for c in doc_candidates:
                                if len(c) > 3 and c.lower() in q_lower:
                                    score += 150 + len(c)
                                    match_type = "item_in_query"
                                    matched_item_for_doc = c
                                    if not resolved_entity_name:
                                        resolved_entity_name = c
                                    break

                    if score > 0:
                        seen_doc_ids.add(doc_id)
                        doc_copy = dict(doc)
                        doc_copy["_matched_context_label"] = matched_item_for_doc or resolved_entity_name or doc_title
                        matched_docs.append({
                            "knowledge_id": doc_id,
                            "title": doc_title,
                            "file_name": file_name,
                            "batch_id": doc.get("batch_id"),
                            "score": score,
                            "match_type": match_type,
                            "target_item": matched_item_for_doc or resolved_entity_name,
                            "doc_data": doc_copy
                        })
            except Exception as db_scan_err:
                logger.debug(f"[GeneralKnowledgeService] DB scan fallback note: {db_scan_err}")

        if not matched_docs:
            return None

        # Sort: highest score first (dedicated document first, then catalog sections)
        matched_docs.sort(key=lambda x: x["score"], reverse=True)

        # Filter: if structural matches exist (explicit UUID, dedicated document, section, ingredient match), exclude weak content mentions
        structural_matches = [d for d in matched_docs if d.get("match_type") in ("explicit_uuid", "dedicated_document", "section", "ingredient_match")]
        if structural_matches:
            matched_docs = structural_matches
        elif any(verb in q_lower for verb in ["hapus", "delete", "hilangkan", "remove", "buang", "tiadakan"]):
            return None

        return (resolved_entity_name, matched_docs)

    @staticmethod
    async def find_target_document_and_item(
        query: str, output_dir: str = "data/output", db: Optional[Any] = None
    ) -> Optional[Tuple[str, Optional[str], Dict[str, Any]]]:
        """
        Scans approved documents to identify the matching document ID and target item/entity/section name.
        Returns the highest-priority matching document (knowledge_id, target_item_name, doc_data).
        """
        res = await GeneralKnowledgeService.find_all_target_documents_and_item(query, output_dir, db=db)
        if not res:
            return None
        target_item, matched_docs = res
        if not matched_docs:
            return None
        top_doc = matched_docs[0]
        return (top_doc["knowledge_id"], target_item, top_doc["doc_data"])

    @staticmethod
    def validate_target_entity(knowledge_id: str, target_item: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validates that the target document and (if specified) target item/entity exist in approved KB.
        Returns (is_valid, error_message, doc_data).
        """
        approved_file = resolve_approved_file(knowledge_id)
        if not approved_file:
            return False, f"Dokumen dengan ID/Nama '{knowledge_id}' tidak ditemukan dalam Basis Data Pengetahuan ERHA.", None

        try:
            with open(approved_file, "r", encoding="utf-8") as f:
                doc_data = json.load(f)

            if target_item and target_item.strip():
                item_lower = target_item.strip().lower()
                doc_summary = doc_data.get("summary", "").lower()
                chunks = doc_data.get("chunks", [])
                item_found = item_lower in doc_summary or any(
                    item_lower in str(ch.get("text", "")).lower()
                    or item_lower in str(ch.get("metadata", {}).get("product_name", "")).lower()
                    or item_lower in str(ch.get("metadata", {}).get("section", "")).lower()
                    or item_lower in str(ch.get("metadata", {}).get("heading", "")).lower()
                    or item_lower in str(ch.get("metadata", {}).get("title", "")).lower()
                    for ch in chunks if isinstance(ch, dict)
                )
                if not item_found:
                    return False, f"Item/bagian '{target_item}' tidak ditemukan di dalam dokumen '{knowledge_id}'.", doc_data

            return True, None, doc_data
        except Exception as e:
            return False, f"Gagal membaca data dokumen: {str(e)}", None

    @staticmethod
    def clean_markdown_text(text: str, targets: List[str], ing_kw: Optional[str] = None) -> str:
        """
        Surgically removes target products, sections, images, bullets, and table rows from markdown text.
        Preserves other items and markdown structure intact.
        """
        if not text:
            return ""
        res = text
        for t in targets:
            if not t or len(t.strip()) < 2:
                continue
            esc = re.escape(t.strip())

            # 1. Match preceding image (if any) + section heading + section body (up to next heading of same or higher level)
            res = re.sub(
                r'(?:^|\n)(?:[ \t]*!\[[^\]]*\]\([^\)]*\)[ \t]*\n\s*)?(#{1,4}\s*[^\n]*' + esc + r'[^\n]*\n(?:(?!^#{1,4}\s)[^\n]*\n?)*)',
                '\n',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 2. Match standalone image tags where alt text or url contains the target
            res = re.sub(
                r'(?:^|\n)[ \t]*!\[[^\]]*' + esc + r'[^\]]*\]\([^\)]*\)[ \t]*(?=\n|$)',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 3. Match bullet list items and nested sub-bullets mentioning target
            res = re.sub(
                r'(?:^|\n)[ \t]*[\*\-\+]\s*(?:\*\*)?[^\n]*' + esc + r'[^\n]*(?:\n[ \t]{2,}[^\n]*)*',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 4. Match markdown table rows containing target
            res = re.sub(
                r'(?:^|\n)\|[^\n]*' + esc + r'[^\n]*\|?[ \t]*(?=\n|$)',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

            # 5. Standalone line mentioning target
            res = re.sub(
                rf'^[^\n]*{esc}[^\n]*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

        # 6. If ingredient keyword provided, strip lines containing it
        if ing_kw and len(ing_kw.strip()) > 1:
            esc_ing = re.escape(ing_kw.strip())
            res = re.sub(
                rf'^[^\n]*\b{esc_ing}\b[^\n]*$\n?',
                '',
                res,
                flags=re.MULTILINE | re.IGNORECASE
            )

        # 7. Collapse 3+ consecutive newlines into 2
        return re.sub(r'\n{3,}', '\n\n', res).strip()

    @staticmethod
    async def prune_chat_messages_for_deleted_targets(
        db: Optional[Any],
        delete_targets: List[str],
        session_id: Optional[Any] = None,
        knowledge_id: Optional[str] = None
    ):
        """
        Prunes or sanitizes ChatMessage rows in PostgreSQL so deleted products or documents
        do not persist in conversation history and confuse the user or LLM context.
        """
        from app.models.chat import ChatMessage, ChatRole
        from sqlalchemy import select, or_
        import uuid as _uuid

        if not delete_targets and not knowledge_id:
            return

        async def _prune(session):
            try:
                stmt = select(ChatMessage).where(ChatMessage.role == ChatRole.ASSISTANT)
                conditions = []
                if session_id:
                    try:
                        s_uuid = _uuid.UUID(str(session_id).strip())
                        conditions.append(ChatMessage.session_id == s_uuid)
                    except Exception:
                        pass

                content_filters = []
                for dt in delete_targets:
                    if dt and len(dt.strip()) > 1:
                        content_filters.append(ChatMessage.content.ilike(f"%{dt.strip()}%"))

                if knowledge_id:
                    content_filters.append(ChatMessage.content.ilike(f"%{knowledge_id.strip()}%"))

                if not content_filters:
                    return

                stmt = stmt.where(or_(*content_filters))
                if conditions:
                    for cond in conditions:
                        stmt = stmt.where(cond)

                res = await session.execute(stmt)
                messages = res.scalars().all()

                for msg in messages:
                    cleaned_content = GeneralKnowledgeService.clean_markdown_text(
                        msg.content, delete_targets
                    )
                    stripped = re.sub(r'^[#\|\-\*\s\:\d\.]+', '', cleaned_content).strip()
                    if len(stripped) < 15:
                        await session.delete(msg)
                    else:
                        msg.content = cleaned_content
                        if msg.attachments and isinstance(msg.attachments, dict):
                            att = dict(msg.attachments)
                            if "images" in att and isinstance(att["images"], list):
                                att["images"] = [
                                    img for img in att["images"]
                                    if not any(dt.lower() in str(img).lower() for dt in delete_targets)
                                ]
                            msg.attachments = att

                await session.commit()
                logger.info(f"[GeneralKnowledgeService] Pruned/sanitized {len(messages)} ChatMessage records for targets {delete_targets}")
            except Exception as pe:
                logger.warning(f"[GeneralKnowledgeService] Error pruning chat messages: {pe}")

        try:
            if db:
                await _prune(db)
            else:
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    await _prune(session)
        except Exception as e:
            logger.warning(f"[GeneralKnowledgeService] Failed to run chat message pruning: {e}")

    @staticmethod
    async def sync_knowledge_db(
        knowledge_id: str,
        existing_doc: Optional[Dict[str, Any]] = None,
        deleted: bool = False,
        db: Optional[Any] = None
    ):
        """Synchronously updates the PostgreSQL Knowledge record and commits."""
        from app.models.knowledge import Knowledge
        from sqlalchemy import select
        import uuid as _uuid

        async def _do_sync(session):
            k_obj = None
            try:
                kid_uuid = _uuid.UUID(str(knowledge_id).strip())
                stmt = select(Knowledge).where(Knowledge.id == kid_uuid)
                res = await session.execute(stmt)
                k_obj = res.scalar_one_or_none()
            except Exception:
                pass

            if not k_obj:
                stmt2 = select(Knowledge).where(
                    Knowledge.deleted_at.is_(None),
                    Knowledge.metadata_.op("->>")("document_id") == str(knowledge_id)
                )
                res2 = await session.execute(stmt2)
                k_obj = res2.scalar_one_or_none()

            if not k_obj:
                stmt3 = select(Knowledge).where(
                    Knowledge.deleted_at.is_(None),
                    Knowledge.file_name == str(knowledge_id)
                )
                res3 = await session.execute(stmt3)
                k_obj = res3.scalar_one_or_none()

            if k_obj:
                if deleted:
                    k_obj.deleted_at = datetime.now(timezone.utc)
                    logger.info(f"[DedicatedService] Marked Knowledge '{k_obj.id}' as deleted_at={k_obj.deleted_at}")
                elif existing_doc:
                    k_obj.title = existing_doc.get("title", k_obj.title)
                    k_obj.ai_summary = existing_doc.get("summary", k_obj.ai_summary)
                    meta = dict(k_obj.metadata_) if isinstance(k_obj.metadata_, dict) else {}
                    meta.update(existing_doc.get("metadata", {}))
                    meta["chunks"] = existing_doc.get("chunks", [])
                    meta["summary"] = existing_doc.get("summary")
                    if existing_doc.get("batch_summary"):
                        meta["batch_summary"] = existing_doc.get("batch_summary")
                    if "initial_summary" in meta:
                        meta["initial_summary"] = existing_doc.get("summary")
                    if "staging_history" in existing_doc:
                        meta["staging_history"] = existing_doc["staging_history"]
                    if "edit_history" in existing_doc:
                        meta["edit_history"] = existing_doc["edit_history"]
                    k_obj.metadata_ = meta
                    logger.info(f"[DedicatedService] Updated Knowledge '{k_obj.id}' metadata & summary in DB")
                await session.commit()

        try:
            if db:
                await _do_sync(db)
            else:
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    await _do_sync(session)
        except Exception as e:
            logger.error(f"[DedicatedService] Failed to sync Knowledge DB record '{knowledge_id}': {e}")

    @staticmethod
    async def apply_edit(
        knowledge_id: str,
        field: str,
        new_value: str,
        vector_store=None,
        bm25_index=None,
        pipeline=None,
        target_item: Optional[str] = None,
        db=None,
        auto_approve: bool = True,
        scope: str = "SINGLE_ITEM"
    ) -> Dict[str, Any]:
        """
        Applies a surgical, item-level edit to an approved KB document.
        Updates local JSON, PostgreSQL, PGVector, MinIO, and BM25 index.
        """
        approved_file = resolve_approved_file(knowledge_id)
        if not approved_file:
            return {"success": False, "error": f"Dokumen dengan ID/Nama '{knowledge_id}' tidak ditemukan di approved KB."}

        try:
            with open(approved_file, "r", encoding="utf-8") as f:
                existing_doc = json.load(f)

            backup_doc = json.loads(json.dumps(existing_doc))
            doc_kid = str(existing_doc.get("knowledge_id") or knowledge_id)
            old_value = None
            clean_field = (field or "").strip().lower()
            formatted_val = str(new_value).strip()

            # Prevent chatbot conversational response from polluting summary
            conv_phrases = ["berhasil diubah", "berhasil diperbarui", "telah diubah", "telah diperbarui", "berhasil diterapkan", "berhasil dihapus"]
            if clean_field in ("summary", "deskripsi", "ringkasan") and any(p in formatted_val.lower() for p in conv_phrases):
                logger.warning(f"[DedicatedService] Rejected chatbot conversational response as summary value: {formatted_val}")
                return {"success": False, "error": "Value summary tidak boleh berupa kalimat konfirmasi percakapan chatbot."}

            # Update document root ONLY if no target_item is specified (item-level isolation)
            if not target_item:
                if clean_field in ("price", "harga", "biaya"):
                    old_value = existing_doc.get("price") or existing_doc.get("metadata", {}).get("price")
                    existing_doc["price"] = formatted_val
                    if "metadata" not in existing_doc or not isinstance(existing_doc["metadata"], dict):
                        existing_doc["metadata"] = {}
                    existing_doc["metadata"]["price"] = formatted_val
                elif clean_field in ("title", "nama", "nama_produk"):
                    old_value = existing_doc.get("title", existing_doc.get("file_name", ""))
                    existing_doc["title"] = formatted_val
                elif clean_field in ("valid_until", "expiry_date", "end_date", "periode", "masa_berlaku"):
                    old_value = existing_doc.get("valid_until")
                    existing_doc["valid_until"] = formatted_val
                elif clean_field in ("categories", "kategori"):
                    old_value = existing_doc.get("categories", [])
                    try:
                        parsed_cats = json.loads(new_value) if isinstance(new_value, str) else new_value
                        existing_doc["categories"] = parsed_cats if isinstance(parsed_cats, list) else [str(parsed_cats)]
                    except Exception:
                        existing_doc["categories"] = [formatted_val]
                else:
                    old_value = existing_doc.get(clean_field) or existing_doc.get("metadata", {}).get(clean_field)
                    existing_doc[clean_field] = formatted_val
                    existing_doc["metadata"][clean_field] = formatted_val

            # Surgically update summary and chunks
            chunks = existing_doc.get("chunks", [])
            raw_item_clean = target_item.strip() if target_item else ""
            clean_item_name = re.sub(
                r'^(?:kemasan\s+produk|kemasan\s+item|kemasan|produk|item|detail\s+produk|detail|bagian|treatment)\s+',
                '',
                raw_item_clean,
                flags=re.IGNORECASE
            ).strip()
            clean_item_name = re.sub(
                r'\s+(?:pada|di|dalam|untuk)\s+(?:dokumen|doc|file|kb|knowledge)?\s*[0-9a-fA-F\-]{8,}.*$',
                '',
                clean_item_name,
                flags=re.IGNORECASE
            ).strip()
            clean_item_name = re.sub(
                r'\s+(?:pada|di|dalam|untuk)\s+(?:dokumen|doc|file|kb|knowledge)\s+.*$',
                '',
                clean_item_name,
                flags=re.IGNORECASE
            ).strip()
            clean_item_name = re.sub(r'^\*+|\*+$|^_+|_+$|^#+\s*', '', clean_item_name).strip()
            target_item_lower = clean_item_name.lower() if clean_item_name else None

            # 1. Update summary for target item
            curr_summary = existing_doc.get("summary", "")
            if curr_summary:
                doc_title = str(existing_doc.get("title") or existing_doc.get("file_name") or "")
                is_dedicated = bool(clean_item_name and (clean_item_name.lower() == doc_title.lower() or (len(doc_title) > 5 and doc_title.lower() in clean_item_name.lower())))

                # Field synonym regex helper
                field_synonyms = [re.escape(clean_field)]
                if clean_field in ("ukuran", "size", "netto", "berat", "weight", "volume"):
                    field_synonyms = ["ukuran", "size", "netto", "berat", "weight", "volume"]
                elif clean_field in ("harga", "price", "biaya", "tarif"):
                    field_synonyms = ["harga", "price", "biaya", "tarif"]
                elif clean_field in ("sku", "kode", "kode_sku"):
                    field_synonyms = ["sku", "kode", "kode_sku"]
                elif clean_field in ("kategori", "category"):
                    field_synonyms = ["kategori", "category"]
                elif clean_field in ("deskripsi", "description", "keterangan"):
                    field_synonyms = ["deskripsi", "description", "keterangan"]
                elif clean_field in ("indikasi", "indication"):
                    field_synonyms = ["indikasi", "indication", "indications"]
                elif clean_field in ("cara_pakai", "aturan_pakai", "instruksi", "penggunaan", "dosis"):
                    field_synonyms = ["cara_pakai", "aturan_pakai", "instruksi", "penggunaan", "dosis", "cara pakai", "aturan pakai"]
                elif clean_field in ("kandungan", "komposisi", "ingredients", "key_ingredients", "key ingredients", "ingridients", "bahan"):
                    field_synonyms = ["kandungan", "komposisi", "ingredients", "key ingredients", "key_ingredients", "ingridients", "bahan"]

                syn_regex = "|".join(field_synonyms)
                bullet_attr_pattern = re.compile(
                    r'(^[|\-\*]\s*\*+(?:' + syn_regex + r')[:\*\s]+|^[|\-\*]\s*(?:' + syn_regex + r')[:\s]+)[^\n\r]+',
                    re.MULTILINE | re.IGNORECASE
                )

                is_name_rename = clean_field in (
                    "nama", "nama_produk", "title", "product_name", "treatment", "treatment_name", "judul"
                )
                is_ingredient_rename = not target_item and clean_field in (
                    "kandungan", "komposisi", "ingredients", "key_ingredients", "key ingredients", "ingridients", "bahan"
                )

                if is_dedicated:
                    if is_name_rename:
                        existing_doc["title"] = formatted_val
                        if clean_item_name and clean_item_name.lower() in curr_summary.lower():
                            curr_summary = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, curr_summary, flags=re.IGNORECASE)
                        existing_doc["summary"] = curr_summary
                    elif clean_field in ("harga", "ukuran", "sku", "kategori", "deskripsi") and bullet_attr_pattern.search(curr_summary):
                        curr_summary = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', curr_summary, count=1)
                        existing_doc["summary"] = curr_summary
                    elif clean_item_name and clean_item_name.lower() in curr_summary.lower():
                        curr_summary = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, curr_summary, flags=re.IGNORECASE)
                        existing_doc["summary"] = curr_summary
                    elif bullet_attr_pattern.search(curr_summary):
                        curr_summary = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', curr_summary, count=1)
                        existing_doc["summary"] = curr_summary
                    elif clean_field not in ("summary", "text", "konten"):
                        curr_summary = curr_summary.rstrip() + f"\n- **{field.capitalize()}:** {formatted_val}\n"
                        existing_doc["summary"] = curr_summary

                elif clean_item_name and target_item_lower:
                    # Multi-product document: split into sections and isolate update to matched section
                    sections = re.split(r'(?=\n#{1,4}\s+)', curr_summary)
                    matched_idx = -1
                    for idx, sec in enumerate(sections):
                        if target_item_lower in sec.lower():
                            matched_idx = idx
                            break

                    if matched_idx != -1:
                        target_sec = sections[matched_idx]
                        if is_name_rename:
                            target_sec = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, target_sec, flags=re.IGNORECASE)
                        elif clean_field in ("harga", "ukuran", "sku", "kategori", "deskripsi") and bullet_attr_pattern.search(target_sec):
                            target_sec = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', target_sec, count=1)
                        elif clean_item_name and clean_item_name.lower() in target_sec.lower():
                            target_sec = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, target_sec, flags=re.IGNORECASE)
                        elif bullet_attr_pattern.search(target_sec):
                            target_sec = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', target_sec, count=1)
                        elif clean_field not in ("summary", "text", "konten"):
                            target_sec = target_sec.rstrip() + f"\n- **{field.capitalize()}**: {formatted_val}\n\n"
                        sections[matched_idx] = target_sec
                        curr_summary = "".join(sections)
                        existing_doc["summary"] = curr_summary
                    else:
                        table_row_pattern = re.compile(rf'(^\s*\|\s*[^\n|]*{re.escape(clean_item_name)}[^\n|]*\|)([^\n]+)$', re.MULTILINE | re.IGNORECASE)
                        if table_row_pattern.search(curr_summary):
                            if is_name_rename:
                                curr_summary = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, curr_summary, flags=re.IGNORECASE)
                            else:
                                curr_summary = table_row_pattern.sub(rf'\g<1> {formatted_val} |', curr_summary, count=1)
                            existing_doc["summary"] = curr_summary
                        elif bullet_key_pattern := re.search(rf'(^[|\-\*]\s*\*\*[^\*\n:]*{re.escape(clean_item_name)}[^\*\n:]*\*\*\s*:\s*)[^\n]+', curr_summary, re.MULTILINE | re.IGNORECASE):
                            curr_summary = re.sub(
                                rf'(^[|\-\*]\s*\*\*[^\*\n:]*{re.escape(clean_item_name)}[^\*\n:]*\*\*\s*:\s*)[^\n]+',
                                rf'\g<1>{formatted_val}',
                                curr_summary,
                                flags=re.MULTILINE | re.IGNORECASE,
                                count=1
                            )
                            existing_doc["summary"] = curr_summary
                        elif clean_item_name and clean_item_name.lower() in curr_summary.lower():
                            curr_summary = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, curr_summary, flags=re.IGNORECASE)
                            existing_doc["summary"] = curr_summary

            # 2. Update matching chunks ONLY
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                if "metadata" not in chunk:
                    chunk["metadata"] = {}
                chunk["metadata"]["knowledge_id"] = doc_kid

                chunk_text = chunk.get("text", "")
                chunk_text_lower = chunk_text.lower()
                chunk_prod_name = str(chunk["metadata"].get("product_name", "")).lower()

                chunk_belongs = True
                if target_item_lower:
                    if target_item_lower not in chunk_text_lower and target_item_lower not in chunk_prod_name:
                        chunk_belongs = False

                if not chunk_belongs:
                    continue

                if clean_field in ("harga", "ukuran", "sku", "kategori", "deskripsi") and bullet_attr_pattern.search(chunk_text):
                    chunk["text"] = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', chunk_text, count=1)
                elif clean_item_name and clean_item_name.lower() in chunk_text_lower:
                    chunk["text"] = re.sub(rf'\b{re.escape(clean_item_name)}\b', formatted_val, chunk_text, flags=re.IGNORECASE)
                    chunk_text = chunk["text"]
                    chunk_text_lower = chunk_text.lower()
                    if is_name_rename:
                        chunk["metadata"]["product_name"] = formatted_val
                        chunk["metadata"]["entity"] = formatted_val
                elif bullet_attr_pattern.search(chunk_text):
                    chunk["text"] = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', chunk_text, count=1)
                elif clean_field not in ("summary", "text", "konten"):
                    chunk["text"] = chunk_text.strip() + f"\n- **{field.capitalize()}**: {formatted_val}"

            # Synchronize last assistant turn in staging_history/history if present
            curr_summary = existing_doc.get("summary", "")
            if curr_summary:
                for hist_key in ("staging_history", "history"):
                    if hist_key in existing_doc and isinstance(existing_doc[hist_key], list) and existing_doc[hist_key]:
                        for turn in reversed(existing_doc[hist_key]):
                            if isinstance(turn, dict) and turn.get("role") == "assistant":
                                turn["content"] = curr_summary
                                break

            # Append to edit_history
            edit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "edit",
                "field": clean_field,
                "target_item": target_item,
                "old_value": str(old_value)[:200] if old_value else None,
                "new_value": formatted_val,
                "source": "general_prompt"
            }
            if "edit_history" not in existing_doc or not isinstance(existing_doc["edit_history"], list):
                existing_doc["edit_history"] = []
            existing_doc["edit_history"].append(edit_entry)

            # Update batch_summary if this document belongs to a batch
            batch_id = existing_doc.get("batch_id")
            cur_bs = existing_doc.get("batch_summary") or existing_doc.get("metadata", {}).get("batch_summary")
            if cur_bs and target_item:
                if bullet_attr_pattern.search(cur_bs):
                    cur_bs = bullet_attr_pattern.sub(rf'\g<1>{formatted_val}', cur_bs)
                existing_doc["batch_summary"] = cur_bs
                if "metadata" in existing_doc and isinstance(existing_doc["metadata"], dict):
                    existing_doc["metadata"]["batch_summary"] = cur_bs

                # Propagate updated batch_summary to other output/pending files in this batch
                out_dir = settings.output_dir if hasattr(settings, "output_dir") else "data/output"
                if os.path.exists(out_dir):
                    for fn in os.listdir(out_dir):
                        if fn.endswith(".json") and fn != os.path.basename(approved_file):
                            f_path = os.path.join(out_dir, fn)
                            try:
                                with open(f_path, "r", encoding="utf-8") as bf:
                                    b_data = json.load(bf)
                                if b_data.get("batch_id") == batch_id:
                                    b_data["batch_summary"] = cur_bs
                                    if "metadata" in b_data and isinstance(b_data["metadata"], dict):
                                        b_data["metadata"]["batch_summary"] = cur_bs
                                    with open(f_path, "w", encoding="utf-8") as bf:
                                        json.dump(b_data, bf, indent=4, ensure_ascii=False)
                            except Exception:
                                pass

            if auto_approve:
                # AUTO-APPROVE: General Prompt confirm → overwrite approved file, re-ingest immediately
                existing_doc["status"] = "Approved"
                existing_doc.pop("is_revision", None)

                # 1. Overwrite data/output/{doc_kid}.json
                os.makedirs("data/output", exist_ok=True)
                with open(approved_file, "w", encoding="utf-8") as f:
                    json.dump(existing_doc, f, indent=4, ensure_ascii=False)

                # 2. Re-chunk from updated summary for vector + BM25 indexing
                doc_chunks = existing_doc.get("chunks", [])
                updated_summary = existing_doc.get("summary", "")
                if updated_summary and updated_summary.strip():
                    try:
                        from app.rag.utils.summary_chunker import chunk_summary_markdown
                        doc_img_url = existing_doc.get("image_url") or (
                            existing_doc.get("image_urls", [None])[0]
                            if existing_doc.get("image_urls") else None
                        )
                        raw_cats = existing_doc.get("categories") or existing_doc.get("suggested_categories") or []
                        parsed_cats = []
                        if isinstance(raw_cats, list):
                            for c in raw_cats:
                                if isinstance(c, dict) and "name" in c:
                                    parsed_cats.append(c["name"])
                                elif isinstance(c, str):
                                    parsed_cats.append(c)
                        vis_settings = existing_doc.get("visibility_settings") or {
                            "clinics": ["all"], "doctor_types": ["all"], "doctors": ["all"]
                        }
                        doc_chunks = chunk_summary_markdown(
                            summary=updated_summary,
                            source_file=existing_doc.get("file_name", doc_kid),
                            knowledge_id=doc_kid,
                            batch_id=existing_doc.get("batch_id"),
                            file_hash=existing_doc.get("file_hash", ""),
                            title=existing_doc.get("title", doc_kid),
                            doc_type=existing_doc.get("document_type", "GENERAL"),
                            categories=parsed_cats,
                            valid_from=str(existing_doc.get("valid_from", "")).strip() or None,
                            valid_until=str(existing_doc.get("valid_until", "")).strip() or None,
                            visibility_settings=vis_settings,
                            default_image_url=doc_img_url,
                        )
                        existing_doc["chunks"] = doc_chunks
                        # Re-save with updated chunks
                        with open(approved_file, "w", encoding="utf-8") as f:
                            json.dump(existing_doc, f, indent=4, ensure_ascii=False)
                        logger.info(f"[DedicatedService] Re-chunked summary into {len(doc_chunks)} chunks for '{doc_kid}'")
                    except Exception as rechunk_err:
                        logger.warning(f"[DedicatedService] Re-chunking failed, using existing chunks: {rechunk_err}")

                # 3. Re-ingest into Vector Store (delete old → insert new)
                v_store = vector_store
                if not v_store and pipeline:
                    v_store = pipeline.vector_store
                if not v_store:
                    try:
                        from app.rag.services.vector_store import PGVectorAdapter
                        v_store = PGVectorAdapter()
                    except Exception:
                        pass
                if v_store:
                    try:
                        v_store.delete_document(doc_kid)
                        file_name = existing_doc.get("file_name", "")
                        if file_name and file_name != doc_kid:
                            v_store.delete_document(file_name)
                    except Exception as del_err:
                        logger.debug(f"[DedicatedService] Vector pre-delete note: {del_err}")
                    if doc_chunks:
                        try:
                            v_store.insert_chunks(doc_chunks)
                            logger.info(f"[DedicatedService] Re-indexed {len(doc_chunks)} chunks in vector store for '{doc_kid}'")
                        except Exception as ins_err:
                            logger.error(f"[DedicatedService] Vector insert failed: {ins_err}")
                            # Rollback JSON file & vector store to backup state
                            with open(approved_file, "w", encoding="utf-8") as f:
                                json.dump(backup_doc, f, indent=4, ensure_ascii=False)
                            backup_chunks = backup_doc.get("chunks", [])
                            try:
                                v_store.delete_document(doc_kid)
                                if backup_chunks:
                                    v_store.insert_chunks(backup_chunks)
                            except Exception:
                                pass
                            return {"success": False, "error": f"Vector indexing failed: {ins_err}"}

                # 4. Re-ingest into BM25 Index
                bm25_inst = bm25_index
                if not bm25_inst:
                    try:
                        from app.rag.services.rag_retriever import BM25Index
                        bm25_inst = BM25Index()
                        if os.path.exists(settings.bm25_index_path):
                            bm25_inst.load(settings.bm25_index_path)
                    except Exception:
                        pass
                if bm25_inst:
                    try:
                        bm25_inst.remove_file_chunks(doc_kid)
                        file_name = existing_doc.get("file_name", "")
                        if file_name and file_name != doc_kid:
                            bm25_inst.remove_file_chunks(file_name)
                    except Exception as bm25_del_err:
                        logger.debug(f"[DedicatedService] BM25 pre-delete note: {bm25_del_err}")
                    if doc_chunks:
                        try:
                            bm25_inst.add_chunks(doc_chunks)
                            os.makedirs(os.path.dirname(settings.bm25_index_path), exist_ok=True)
                            bm25_inst.save(settings.bm25_index_path)
                            logger.info(f"[DedicatedService] Re-indexed {len(doc_chunks)} chunks in BM25 for '{doc_kid}'")
                        except Exception as bm25_ins_err:
                            logger.error(f"[DedicatedService] BM25 insert failed: {bm25_ins_err}")
                            # Rollback JSON file, vector store, and BM25 to backup state
                            with open(approved_file, "w", encoding="utf-8") as f:
                                json.dump(backup_doc, f, indent=4, ensure_ascii=False)
                            backup_chunks = backup_doc.get("chunks", [])
                            if v_store:
                                try:
                                    v_store.delete_document(doc_kid)
                                    if backup_chunks:
                                        v_store.insert_chunks(backup_chunks)
                                except Exception:
                                    pass
                            if bm25_inst:
                                try:
                                    bm25_inst.remove_file_chunks(doc_kid)
                                    if backup_chunks:
                                        bm25_inst.add_chunks(backup_chunks)
                                except Exception:
                                    pass
                            return {"success": False, "error": f"BM25 indexing failed: {bm25_ins_err}"}

                # 5. Sync PostgreSQL Knowledge record
                try:
                    await GeneralKnowledgeService.sync_knowledge_db(doc_kid, existing_doc=existing_doc, db=db)
                except Exception as db_err:
                    logger.debug(f"[DedicatedService] DB sync note: {db_err}")

                # 6. Upload approved JSON to MinIO approved bucket
                try:
                    from app.services.storage import promote_staging_to_approved
                    promote_staging_to_approved(doc_kid, existing_doc)
                except Exception as s3_err:
                    logger.debug(f"[DedicatedService] MinIO approved sync note: {s3_err}")

                # 7. Clean up any stale pending file
                pending_cleanup = os.path.join("data/pending", f"{doc_kid}.json")
                if os.path.exists(pending_cleanup):
                    try:
                        os.remove(pending_cleanup)
                    except Exception:
                        pass

                logger.info(f"[DedicatedService] Auto-approved edit for '{doc_kid}'. Data immediately retrievable by RAG.")
                GeneralKnowledgeService.log_mutation_summary(
                    operation_id=f"op_{doc_kid[:8]}",
                    action="UPDATE",
                    scope=scope,
                    knowledge_id=doc_kid,
                    entity_id=clean_item_name or doc_kid,
                    target_name=clean_item_name or existing_doc.get("title", doc_kid),
                    field=clean_field,
                    old_value=str(old_value)[:200] if old_value else None,
                    new_value=formatted_val,
                    affected_documents=1,
                    affected_entities=1,
                    chunks_old=len(backup_doc.get("chunks", [])),
                    chunks_new=len(existing_doc.get("chunks", [])),
                    canonical_status="SUCCESS",
                    pgvector_status="SUCCESS",
                    bm25_status="SUCCESS",
                    retrieval_status="SUCCESS",
                    status="APPLIED"
                )
                return {
                    "success": True,
                    "knowledge_id": doc_kid,
                    "field": field,
                    "target_item": target_item,
                    "old_value": str(old_value)[:200] if old_value else None,
                    "new_value": str(new_value)[:200],
                    "message": f"Perubahan pada '{target_item or doc_kid}' berhasil diterapkan dan langsung aktif di RAG.",
                    "summary": existing_doc.get("summary", "")
                }
            else:
                # PENDING DRAFT: Dashboard Admin edit → Priority 4 versioning rule
                existing_doc["status"] = "On review"
                existing_doc["is_revision"] = True
                os.makedirs("data/pending", exist_ok=True)
                pending_file = os.path.join("data/pending", f"{doc_kid}.json")
                with open(pending_file, "w", encoding="utf-8") as f:
                    json.dump(existing_doc, f, indent=4, ensure_ascii=False)

                try:
                    from app.services.storage import upload_staging_json
                    upload_staging_json(doc_kid, existing_doc)
                except Exception as s3_err:
                    logger.debug(f"[DedicatedService] MinIO staging sync note: {s3_err}")

                logger.info(f"[DedicatedService] Staged edit revision for '{doc_kid}' to pending queue (status: 'On review'). Active approved document remains searchable until approved.")
                return {
                    "success": True,
                    "knowledge_id": doc_kid,
                    "field": field,
                    "target_item": target_item,
                    "old_value": str(old_value)[:200] if old_value else None,
                    "new_value": str(new_value)[:200],
                    "message": f"Perubahan pada '{target_item or doc_kid}' berhasil disimpan sebagai draft peninjauan (PENDING). Dokumen aktif tetap diretrieve RAG sampai diapprove."
                }


        except Exception as e:
            logger.error(f"[DedicatedService] Failed to apply edit for '{knowledge_id}': {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def apply_delete(
        knowledge_id: str,
        vector_store=None,
        bm25_index=None,
        target_item: Optional[str] = None,
        db=None,
        scope: str = "SINGLE_ITEM",
        session_id: Optional[Any] = None,
        delete_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Deletes a KB document or surgically deletes a specific item within a multi-item document.
        Synchronizes local JSON, PostgreSQL, PGVector, MinIO, BM25 index, and ChatMessages.
        """
        clean_target = (knowledge_id or "").strip().lower()

        # 1. Item-Level Surgical Deletion
        if target_item and target_item.strip():
            raw_item_clean = re.sub(r'^\*+|\*+$|^_+|_+$|^#+\s*', '', target_item.strip()).strip()
            target_item_clean = raw_item_clean
            target_item_lower = target_item_clean.lower()
            approved_file = resolve_approved_file(knowledge_id) or resolve_pending_file(knowledge_id)
            if not approved_file:
                return {"success": False, "error": f"Dokumen dengan ID '{knowledge_id}' tidak ditemukan di basis data knowledge."}

            try:
                with open(approved_file, "r", encoding="utf-8") as f:
                    existing_doc = json.load(f)

                doc_kid = str(existing_doc.get("knowledge_id") or knowledge_id)
                summary = existing_doc.get("summary", "")
                deleted_products = []
                delete_targets = []
                filtered_chunks = None
                removed_count = 0

                # Case 0: Delete product image only (Preserve product details 100%)
                if delete_type == "image":
                    deleted_images = []
                    prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'
                    sections = [s for s in re.split(prod_boundary_pattern, summary) if s.strip()]
                    if len(sections) <= 1:
                        sections = [s for s in re.split(r'(?=(?:^|\n)#{1,4}\s+[^\n]+)', summary) if s.strip()]

                    target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_item_lower) if w not in ('produk', 'product', 'erha', 'the', 'and', 'gambar', 'foto', 'image', 'picture')]

                    new_sections = []
                    image_removed_from_section = False

                    for sec in sections:
                        name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec, re.IGNORECASE)
                        p_name = name_m.group(1).strip() if name_m else ""
                        if not p_name:
                            h_m = re.search(r'^#{1,4}\s+([^\n\r]+)', sec.strip())
                            if h_m:
                                cand_h = re.sub(r'[\*\_]', '', h_m.group(1)).strip()
                                if cand_h.lower() not in ("detail produk", "informasi produk", "ringkasan dokumen", "penutup", "evaluasi hasil", "profil pasien", "detail perawatan"):
                                    p_name = cand_h

                        is_match = False
                        if not target_item_clean:
                            is_match = True
                        elif p_name:
                            p_lower = p_name.lower()
                            if target_item_lower == p_lower or target_item_lower in p_lower or p_lower in target_item_lower:
                                is_match = True
                            elif target_words and all(w in p_lower for w in target_words):
                                is_match = True
                        elif target_words and all(w in sec.lower() for w in target_words):
                            is_match = True

                        if is_match:
                            img_tags = list(re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', sec))
                            sec_mod = sec
                            for itag in img_tags:
                                img_url = itag.group(2).strip()
                                if img_url and img_url not in deleted_images:
                                    deleted_images.append(img_url)
                                sec_mod = sec_mod.replace(itag.group(0), "")
                            sec_mod = re.sub(r'\n{3,}', '\n\n', sec_mod)
                            if sec_mod != sec:
                                image_removed_from_section = True
                            new_sections.append(sec_mod)
                        else:
                            new_sections.append(sec)

                    if image_removed_from_section:
                        existing_doc["summary"] = "".join(new_sections).strip()
                    else:
                        # Fallback for single product or unsectioned summary: match image tag by target words or remove image
                        updated_sum = summary
                        img_tags = list(re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', summary))
                        for itag in img_tags:
                            alt = itag.group(1)
                            url = itag.group(2).strip()
                            if not target_words or any(tw in alt.lower() or tw in url.lower() for tw in target_words) or len(img_tags) == 1:
                                if url not in deleted_images:
                                    deleted_images.append(url)
                                updated_sum = updated_sum.replace(itag.group(0), "")
                        existing_doc["summary"] = re.sub(r'\n{3,}', '\n\n', updated_sum).strip()

                    # Purge from MinIO storage
                    for d_url in deleted_images:
                        try:
                            from app.services.storage import delete_image_by_ref
                            delete_image_by_ref(d_url, knowledge_id=doc_kid)
                            logger.info(f"🗑️ [ImageDelete] Purged image '{d_url}' from MinIO for doc '{doc_kid}'")
                        except Exception as s3_err:
                            logger.debug(f"[ImageDelete] MinIO delete note: {s3_err}")

                    # Clean metadata
                    if "image_urls" in existing_doc and isinstance(existing_doc["image_urls"], list):
                        existing_doc["image_urls"] = [u for u in existing_doc["image_urls"] if u not in deleted_images]
                    if existing_doc.get("image_url") in deleted_images:
                        existing_doc["image_url"] = existing_doc["image_urls"][0] if existing_doc.get("image_urls") else None

                    if "metadata" in existing_doc and isinstance(existing_doc["metadata"], dict):
                        meta = existing_doc["metadata"]
                        if "images" in meta and isinstance(meta["images"], list):
                            meta["images"] = [
                                img for img in meta["images"]
                                if (isinstance(img, dict) and img.get("url") not in deleted_images and img.get("s3_key") not in deleted_images)
                                or (isinstance(img, str) and img not in deleted_images)
                            ]
                        if "image_urls" in meta and isinstance(meta["image_urls"], list):
                            meta["image_urls"] = [u for u in meta["image_urls"] if u not in deleted_images]
                        meta["summary"] = existing_doc["summary"]

                    # Clean chunks text & metadata (WITHOUT deleting the product chunk!)
                    original_chunks = existing_doc.get("chunks", [])
                    filtered_chunks = []
                    for chunk in original_chunks:
                        if isinstance(chunk, dict):
                            c_text = chunk.get("text", "")
                            for d_url in deleted_images:
                                c_text = re.sub(rf'!\[[^\]]*\]\({re.escape(d_url)}\)', '', c_text)
                            c_meta = chunk.get("metadata", {})
                            c_prod = str(c_meta.get("product_name", "")).lower()
                            if target_item_lower and target_item_lower in c_prod:
                                c_text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', c_text)
                            chunk["text"] = re.sub(r'\n{3,}', '\n\n', c_text).strip()
                            if "image_url" in c_meta and c_meta["image_url"] in deleted_images:
                                c_meta["image_url"] = None
                            if "image_urls" in c_meta and isinstance(c_meta["image_urls"], list):
                                c_meta["image_urls"] = [u for u in c_meta["image_urls"] if u not in deleted_images]
                            filtered_chunks.append(chunk)

                    existing_doc["chunks"] = filtered_chunks

                    with open(approved_file, "w", encoding="utf-8") as f:
                        json.dump(existing_doc, f, indent=4, ensure_ascii=False)

                    if vector_store:
                        vector_store.delete_document(doc_kid)
                        if filtered_chunks:
                            vector_store.insert_chunks(filtered_chunks)

                    if bm25_index:
                        bm25_index.remove_file_chunks(doc_kid)
                        if filtered_chunks:
                            bm25_index.add_chunks(filtered_chunks)
                        bm25_index.save(settings.bm25_index_path)

                    try:
                        from app.services.storage import upload_approved_json
                        upload_approved_json(doc_kid, existing_doc)
                    except Exception as s3_err:
                        logger.debug(f"[ImageDelete] MinIO update note: {s3_err}")

                    await GeneralKnowledgeService.sync_knowledge_db(doc_kid, existing_doc=existing_doc, db=db)

                    logger.info(f"✅ [DedicatedService] Successfully deleted image(s) {deleted_images} for '{target_item_clean}' in doc '{doc_kid}'. Product info preserved.")
                    return {
                        "success": True,
                        "knowledge_id": doc_kid,
                        "target_item": target_item_clean,
                        "deleted_images": deleted_images,
                        "summary": existing_doc["summary"],
                        "delete_type": "image"
                    }

                # Detect if this is an ingredient-based deletion
                is_ing_delete = (delete_type == "ingredient")
                ing_keyword = None
                if not is_ing_delete:
                    ing_m = re.search(r'(?:produk\s+(?:dengan\s+)?(?:yang\s+)?(?:mengandung|kandungan|bahan)\s+|kandungan\s+|bahan\s+)(.+)', target_item_clean, re.IGNORECASE)
                    if ing_m:
                        is_ing_delete = True
                        ing_keyword = ing_m.group(1).strip().lower()
                else:
                    ing_keyword = target_item_clean.lower()

                # Case A: Delete all products containing specific ingredient
                if is_ing_delete and ing_keyword:
                    prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'
                    sections = [s for s in re.split(prod_boundary_pattern, summary) if s.strip()]
                    if len(sections) <= 1:
                        sections = [s for s in re.split(r'(?=(?:^|\n)#{1,4}\s+[^\n]+)', summary) if s.strip()]

                    kept_sections = []
                    ing_re = re.compile(rf'\b{re.escape(ing_keyword)}\b', re.IGNORECASE)

                    for sec in sections:
                        name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec, re.IGNORECASE)
                        p_name = name_m.group(1).strip() if name_m else ""
                        if not p_name:
                            h_m = re.search(r'^#{1,4}\s+([^\n\r]+)', sec.strip())
                            if h_m:
                                cand_h = re.sub(r'[\*\_]', '', h_m.group(1)).strip()
                                if cand_h.lower() not in ("detail produk", "informasi produk", "ringkasan dokumen", "penutup", "evaluasi hasil", "profil pasien", "detail perawatan"):
                                    p_name = cand_h

                        if ing_re.search(sec):
                            disp_name = p_name or target_item_clean
                            if disp_name not in deleted_products:
                                deleted_products.append(disp_name)
                        else:
                            kept_sections.append(sec)

                    if deleted_products:
                        existing_doc["summary"] = "".join(kept_sections).strip()
                        delete_targets = list(deleted_products)
                        delete_targets.append(ing_keyword)
                        try:
                            from app.rag.utils.summary_chunker import chunk_summary_markdown
                            filtered_chunks = chunk_summary_markdown(
                                summary=existing_doc["summary"],
                                source_file=existing_doc.get("file_name", doc_kid),
                                knowledge_id=doc_kid,
                                batch_id=existing_doc.get("batch_id"),
                                title=existing_doc.get("title", doc_kid),
                                doc_type=existing_doc.get("document_type", "GENERAL")
                            )
                        except Exception as rc_err:
                            logger.debug(f"[DedicatedService] Re-chunk fallback note on delete: {rc_err}")
                            filtered_chunks = []

                # Case B: Delete specific product by name
                elif delete_type == "name" or any(w in target_item_lower for w in ("serum", "cream", "gel", "lotion", "toner", "wash", "cleanser", "facial", "sunscreen", "spot", "moisturizer", "acneact", "truwhite")):
                    prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'
                    sections = [s for s in re.split(prod_boundary_pattern, summary) if s.strip()]
                    if len(sections) <= 1:
                        sections = [s for s in re.split(r'(?=(?:^|\n)#{1,4}\s+[^\n]+)', summary) if s.strip()]

                    kept_sections = []
                    target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_item_lower) if w not in ('produk', 'product', 'erha', 'the', 'and')]

                    for sec in sections:
                        name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec, re.IGNORECASE)
                        p_name = name_m.group(1).strip() if name_m else ""
                        if not p_name:
                            h_m = re.search(r'^#{1,4}\s+([^\n\r]+)', sec.strip())
                            if h_m:
                                cand_h = re.sub(r'[\*\_]', '', h_m.group(1)).strip()
                                if cand_h.lower() not in ("detail produk", "informasi produk", "ringkasan dokumen", "penutup", "evaluasi hasil", "profil pasien", "detail perawatan"):
                                    p_name = cand_h

                        is_match = False
                        if p_name:
                            p_lower = p_name.lower()
                            if target_item_lower == p_lower:
                                is_match = True
                            elif target_item_lower in p_lower or (len(p_lower) > 5 and p_lower in target_item_lower):
                                is_match = True
                            else:
                                generic_words = {
                                    'produk', 'product', 'erha', 'the', 'and', 'for', 'with',
                                    'new', 'version', 'series', 'edisi', 'baru', 'edition', 'care',
                                    'cream', 'serum', 'gel', 'lotion', 'wash', 'cleanser', 'toner', 'facial', 'sunscreen', 'moisturizer'
                                }
                                distinctive_del_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_item_lower) if w not in generic_words]
                                if distinctive_del_words:
                                    if all(w in p_lower for w in distinctive_del_words):
                                        is_match = True
                                elif target_words and sum(1 for w in target_words if w in p_lower) >= len(target_words):
                                    is_match = True
                        elif target_item_lower in sec.lower():
                            is_match = True

                        if is_match:
                            disp_name = p_name or target_item_clean
                            if disp_name not in deleted_products:
                                deleted_products.append(disp_name)
                        else:
                            kept_sections.append(sec)

                    if deleted_products:
                        existing_doc["summary"] = "".join(kept_sections).strip()
                        delete_targets = list(deleted_products)
                        try:
                            from app.rag.utils.summary_chunker import chunk_summary_markdown
                            filtered_chunks = chunk_summary_markdown(
                                summary=existing_doc["summary"],
                                source_file=existing_doc.get("file_name", doc_kid),
                                knowledge_id=doc_kid,
                                batch_id=existing_doc.get("batch_id"),
                                title=existing_doc.get("title", doc_kid),
                                doc_type=existing_doc.get("document_type", "GENERAL")
                            )
                        except Exception as rc_err:
                            logger.debug(f"[DedicatedService] Re-chunk fallback note on delete: {rc_err}")
                            filtered_chunks = []

                # Case C: Fallback to line-by-line / bullet cleanup
                if not deleted_products:
                    if "," in target_item:
                        for s in target_item.split(","):
                            s_clean = s.strip()
                            if s_clean and not s_clean.lower().startswith("produk dengan kandungan"):
                                delete_targets.append(s_clean)

                    if not delete_targets:
                        delete_targets = [target_item_clean]

                    # Deduplicate delete_targets
                    unique_delete_targets = []
                    seen_dt = set()
                    for dt in delete_targets:
                        if dt.lower() not in seen_dt:
                            seen_dt.add(dt.lower())
                            unique_delete_targets.append(dt)
                    delete_targets = unique_delete_targets

                    # Clean summary
                    if summary:
                        existing_doc["summary"] = GeneralKnowledgeService.clean_markdown_text(summary, delete_targets, ing_keyword)

                    original_chunks = existing_doc.get("chunks", [])
                    filtered_chunks = []
                    for chunk in original_chunks:
                        chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else ""
                        chunk_lower = chunk_text.lower()
                        meta = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}

                        is_dedicated_target_chunk = False
                        for dt in delete_targets:
                            dt_low = dt.lower()
                            chunk_prod = str(meta.get("product_name", "")).lower()
                            chunk_sec = str(meta.get("section", "")).lower()
                            chunk_head = str(meta.get("heading", "")).lower()
                            if dt_low and (dt_low in chunk_prod or dt_low in chunk_sec or dt_low in chunk_head or dt_low in chunk_lower):
                                is_dedicated_target_chunk = True
                                break

                        if is_dedicated_target_chunk:
                            removed_count += 1
                            continue

                        cleaned_chunk_text = GeneralKnowledgeService.clean_markdown_text(chunk_text, delete_targets, ing_keyword)
                        stripped_clean = re.sub(r'^[#\|\-\*\s\:\d\.]+', '', cleaned_chunk_text).strip()
                        if not stripped_clean or len(stripped_clean) < 10:
                            removed_count += 1
                            continue

                        chunk["text"] = cleaned_chunk_text
                        filtered_chunks.append(chunk)

                # Clean batch_summary
                if existing_doc.get("batch_summary"):
                    existing_doc["batch_summary"] = GeneralKnowledgeService.clean_markdown_text(existing_doc["batch_summary"], delete_targets, ing_keyword)

                # Clean metadata
                if "metadata" in existing_doc and isinstance(existing_doc["metadata"], dict):
                    meta = existing_doc["metadata"]
                    if existing_doc.get("batch_summary"):
                        meta["batch_summary"] = existing_doc["batch_summary"]
                    if "initial_summary" in meta and meta["initial_summary"]:
                        meta["initial_summary"] = GeneralKnowledgeService.clean_markdown_text(meta["initial_summary"], delete_targets, ing_keyword)
                    if "summary" in meta and meta["summary"]:
                        meta["summary"] = existing_doc["summary"]
                    if "chat_history" in meta and isinstance(meta["chat_history"], list):
                        for turn in meta["chat_history"]:
                            if isinstance(turn, dict) and turn.get("content"):
                                turn["content"] = GeneralKnowledgeService.clean_markdown_text(turn["content"], delete_targets, ing_keyword)

                # Clean staging_history & history
                for hist_key in ("staging_history", "history"):
                    if hist_key in existing_doc and isinstance(existing_doc[hist_key], list):
                        for turn in existing_doc[hist_key]:
                            if isinstance(turn, dict):
                                orig_c = turn.get("content", "")
                                if orig_c:
                                    turn["content"] = GeneralKnowledgeService.clean_markdown_text(orig_c, delete_targets, ing_keyword)

                remaining_summary = (existing_doc.get("summary") or "").strip()
                if filtered_chunks is None:
                    filtered_chunks = []
                if not filtered_chunks and remaining_summary and len(remaining_summary) > 20:
                    try:
                        from app.rag.utils.summary_chunker import chunk_summary_markdown
                        rechunked = chunk_summary_markdown(
                            summary=remaining_summary,
                            source_file=existing_doc.get("file_name", doc_kid),
                            knowledge_id=doc_kid,
                            batch_id=existing_doc.get("batch_id"),
                            title=existing_doc.get("title", doc_kid),
                            doc_type=existing_doc.get("document_type", "GENERAL")
                        )
                        if rechunked:
                            filtered_chunks = rechunked
                    except Exception as rc_err:
                        logger.debug(f"[DedicatedService] Re-chunk fallback note on delete: {rc_err}")

                existing_doc["chunks"] = filtered_chunks

                if not filtered_chunks and not remaining_summary:
                    # Document is completely empty -> Full document deletion
                    if approved_file and os.path.exists(approved_file):
                        try:
                            os.remove(approved_file)
                        except Exception:
                            pass
                    if vector_store:
                        vector_store.delete_document(doc_kid)
                    if bm25_index:
                        bm25_index.remove_file_chunks(doc_kid)
                        bm25_index.save(settings.bm25_index_path)
                    try:
                        from app.services.storage import delete_knowledge_images_and_assets
                        delete_knowledge_images_and_assets(doc_kid, doc_data=existing_doc)
                    except Exception as s3_err:
                        logger.debug(f"[DedicatedService] MinIO delete note: {s3_err}")
                    await GeneralKnowledgeService.prune_chat_messages_for_deleted_targets(
                        db=db,
                        delete_targets=delete_targets,
                        session_id=session_id,
                        knowledge_id=doc_kid
                    )
                    await GeneralKnowledgeService.sync_knowledge_db(doc_kid, deleted=True, db=db)
                    return {
                        "success": True,
                        "knowledge_id": doc_kid,
                        "target_item": target_item_clean,
                        "title": f"Seluruh item ({', '.join(delete_targets)}) dan dokumen '{doc_kid}' berhasil dihapus dari basis pengetahuan."
                    }

                with open(approved_file, "w", encoding="utf-8") as f:
                    json.dump(existing_doc, f, indent=4, ensure_ascii=False)

                if vector_store:
                    vector_store.delete_document(doc_kid)
                    if filtered_chunks:
                        vector_store.insert_chunks(filtered_chunks)

                if bm25_index:
                    bm25_index.remove_file_chunks(doc_kid)
                    if filtered_chunks:
                        bm25_index.add_chunks(filtered_chunks)
                    bm25_index.save(settings.bm25_index_path)

                try:
                    from app.services.storage import upload_approved_json
                    upload_approved_json(doc_kid, existing_doc)
                except Exception as s3_err:
                    logger.debug(f"[DedicatedService] MinIO update note: {s3_err}")

                # Prune chat messages in DB so deleted products don't linger in conversation history
                await GeneralKnowledgeService.prune_chat_messages_for_deleted_targets(
                    db=db,
                    delete_targets=delete_targets,
                    session_id=session_id,
                    knowledge_id=doc_kid
                )

                # Sync PostgreSQL Knowledge DB record directly and commit
                await GeneralKnowledgeService.sync_knowledge_db(doc_kid, existing_doc=existing_doc, db=db)

                logger.info(f"[DedicatedService] Surgically deleted item '{target_item_clean}' from doc '{doc_kid}' ({removed_count} chunks removed)")
                return {
                    "success": True,
                    "knowledge_id": doc_kid,
                    "target_item": target_item_clean,
                    "deleted_products": deleted_products,
                    "title": f"Item '{target_item_clean}' berhasil dihapus dari basis pengetahuan.",
                    "summary": existing_doc.get("summary", "")
                }
            except Exception as e:
                logger.error(f"[DedicatedService] Item-level delete failed: {e}")
                return {"success": False, "error": str(e)}

        # 2. Batch Delete Expired Promos
        if clean_target in ("expired", "expired_promos", "promo_expired", "promo expired", "promo bulan lalu", "semua promo expired", "promo yang sudah expired"):
            today = datetime.now(timezone.utc).date()
            deleted_items = []
            pending_dir = "data/pending"
            approved_dir = "data/output"

            for folder in [pending_dir, approved_dir, os.path.join("backend", pending_dir), os.path.join("backend", approved_dir)]:
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        if f.endswith(".json") and f != "bm25_index.pkl":
                            f_path = os.path.join(folder, f)
                            try:
                                with open(f_path, "r", encoding="utf-8") as fp:
                                    f_data = json.load(fp)
                                is_expired = False
                                vu = f_data.get("valid_until") or f_data.get("expiry_date")
                                if vu:
                                    parsed_vu = parse_date_safely(vu)
                                    if parsed_vu and parsed_vu < today:
                                        is_expired = True

                                if is_expired:
                                    doc_id = str(f_data.get("knowledge_id", f.replace(".json", "")))
                                    doc_title = str(f_data.get("title", f_data.get("file_name", doc_id)))
                                    os.remove(f_path)
                                    if vector_store:
                                        vector_store.delete_document(doc_id)
                                    if bm25_index:
                                        bm25_index.remove_file_chunks(doc_id)
                                    deleted_items.append(f"{doc_title} (expired: {vu})")
                            except Exception as err:
                                logger.debug(f"[DedicatedService] Error checking expired file {f}: {err}")

            if bm25_index and deleted_items:
                bm25_index.save(settings.bm25_index_path)

            return {
                "success": True,
                "knowledge_id": "expired",
                "title": f"Berhasil menghapus {len(deleted_items)} promo kadaluarsa:\n" + "\n".join(f"- {d}" for d in deleted_items[:10])
            }

        # 3. Full Document Deletion (supports both APPROVED and PENDING documents)
        target_file = resolve_approved_file(knowledge_id) or resolve_pending_file(knowledge_id)
        f_data = {}
        target_kid = str(knowledge_id).strip()
        deleted_title = target_kid

        if target_file and os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as fp:
                    f_data = json.load(fp)
                target_kid = str(f_data.get("knowledge_id") or knowledge_id)
                deleted_title = str(f_data.get("title", f_data.get("file_name", target_kid)))
            except Exception as read_err:
                logger.warning(f"[DedicatedService] Note reading file '{target_file}': {read_err}")

        try:
            # Delete local physical file safely
            if target_file and os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except Exception as rm_err:
                    logger.warning(f"[DedicatedService] Could not remove physical file '{target_file}': {rm_err}")

            # Also purge any corresponding pending or output file in data/ and backend/data/
            for p_dir in ["data/pending", "data/output", "backend/data/pending", "backend/data/output"]:
                for fname in [f"{target_kid}.json", f"{target_kid}_parsed.json"]:
                    dup_p = os.path.join(p_dir, fname)
                    if os.path.exists(dup_p):
                        try:
                            os.remove(dup_p)
                        except Exception:
                            pass

            # Clear Vector Store safely
            if vector_store:
                try:
                    vector_store.delete_document(target_kid)
                except Exception as vs_err:
                    logger.warning(f"[DedicatedService] Vector store delete note: {vs_err}")

            # Clear BM25 safely
            if bm25_index:
                try:
                    bm25_index.remove_file_chunks(target_kid)
                    bm25_index.save(settings.bm25_index_path)
                except Exception as bm_err:
                    logger.warning(f"[DedicatedService] BM25 delete note: {bm_err}")

            # Delete from MinIO (including all embedded images and documents)
            try:
                from app.services.storage import delete_knowledge_images_and_assets
                delete_knowledge_images_and_assets(target_kid, doc_data=f_data)
            except Exception as s3_err:
                logger.debug(f"[DedicatedService] MinIO delete note: {s3_err}")

            # Prune chat messages for this document
            try:
                await GeneralKnowledgeService.prune_chat_messages_for_deleted_targets(
                    db=db,
                    delete_targets=[deleted_title, target_kid],
                    session_id=session_id,
                    knowledge_id=target_kid
                )
            except Exception as prune_err:
                logger.debug(f"[DedicatedService] Prune chat note: {prune_err}")

            # Soft-delete in PostgreSQL Knowledge DB record directly and commit
            try:
                await GeneralKnowledgeService.sync_knowledge_db(target_kid, deleted=True, db=db)
            except Exception as db_sync_err:
                logger.warning(f"[DedicatedService] sync_knowledge_db note: {db_sync_err}")

            return {
                "success": True,
                "knowledge_id": target_kid,
                "title": deleted_title
            }

        except Exception as e:
            logger.error(f"[DedicatedService] Failed to delete document '{knowledge_id}': {e}")
            return {"success": False, "error": str(e)}
