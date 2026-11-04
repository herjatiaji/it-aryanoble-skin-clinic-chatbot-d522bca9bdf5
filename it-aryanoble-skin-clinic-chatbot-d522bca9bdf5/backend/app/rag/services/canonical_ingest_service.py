"""
Canonical Ingestion Service (Phase 1 Frozen Spec).
Provides relational persistence and lifecycle management for:
  - knowledge_version
  - kb_evidence (SSOT)
  - kb_entity (Master Identity)
  - kb_asset (Scored Media)
  - kb_chunk (Derived Materialized Projection)
Enforces:
  1. Knowledge Readiness Gate (D9)
  2. No Orphan Active Projection Invariant
  3. Atomic Publish Transaction
  4. Disposition Contract Observability
"""

import os
import re
import uuid
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_sync_engine
from app.rag.canonical import (
    CanonicalEvidence,
    CanonicalEntity,
    CanonicalAsset,
    ParseReport,
    normalize_entity_key,
    generate_stable_chunk_id,
)


DOMAIN_RULES = [
    ("HAIR_AND_SCALP", ["scalp", "hair", "rambut", "kulit kepala", "shampoo", "sampo", "dandruff", "ketombe", "seboroik", "alopecia", "rontok", "folikel", "kebotakan", "uban"]),
    ("ACNE", ["jerawat", "acne", "komedo", "pustul", "papul", "bha", "salicylic", "bruntusan", "sebum", "acne vulgaris", "inflamasi jerawat"]),
    ("BRIGHTENING", ["flek", "melasma", "brightening", "kusam", "mencerahkan", "hyperpigmentasi", "pigmen", "noda hitam", "whitening", "radiance", "glow", "glowing", "cerah"]),
    ("ANTI_AGING", ["kerutan", "aging", "wrinkle", "garis halus", "penuaan", "tightening", "lifting", "rejuvenation", "firming", "sagging", "kolagen", "collagen", "elastisitas", "skin booster", "monopolar rf", "radio frequency"]),
    ("BODY", ["selulit", "stretch mark", "badan", "body contour", "slimming", "lemak tubuh", "cellulite"]),
    ("GENERAL_FACIAL", ["facial", "cleanser", "toner", "moisturizer", "pelembap", "sunscreen", "tabir surya", "masker"])
]

DISCONTINUED_PATTERNS = [
    r'\bstatus\s*:\s*(?:discontinue[d]?|stok\s+(?:klinik\s+)?habis)',
    r'\bproduk\s+discontinue\b',
    r'\bdiscontinue\s*:\s*(?:per|sejak|mulai)\b',
    r'\bdiscontinue\s+per\b',
    r'\bdiscontinue\s*[-–—]\s*stok',
    r'\(discontinue[d]?\)',
    r'\bstok\s+klinik\s+habis\b',
    r'\bsudah\s+tidak\s+diproduksi\b',
    r'\btidak\s+lagi\s+diproduksi\b',
]


# Field schemas that identify what a chunk describes, regardless of the document it came from
_PRODUCT_FIELD_PATTERNS = [
    r'\b(?:harga|price|idr|rp\.?)\s*[:\|]?\s*[\d.,]+',             # retail price
    r'\b\d+(?:[.,]\d+)?\s?(?:ml|mL|gr?|gram)\b',                    # pack size
    r'\b(?:bahan\s+aktif|kandungan\s+aktif|active\s+ingredients?|komposisi)\b',
    r'\b(?:cara\s+pakai|aturan\s+pakai|how\s+to\s+use|petunjuk\s+pemakaian)\b',
    r'\bnetto\b',
]
_TREATMENT_FIELD_PATTERNS = [
    r'\b\d+\s?menit\b',                                              # session duration
    r'\bkontraindikasi\b',
    r'\b(?:prosedur|protokol)\b',
    r'\b(?:sesi|session|shots?|interval|visit\s+\d)\b',
    r'\barea\s+tindakan\b',
]
_CRITERIA_FIELD_PATTERNS = [
    r'\banamnesis\b', r'\bdiagnosis\b', r'\btatalaksana\b', r'\bpemeriksaan\s+(?:fisik|penunjang)\b',
    r'\betiologi\b', r'\bprognosis\b',
]


def infer_chunk_knowledge_type(text_content: str, default_type: Optional[str]) -> Optional[str]:
    """
    Classifies one evidence chunk by the fields it actually contains (price / pack size / ingredients
    -> PRODUCT; duration / contraindication / procedure / visits -> TREATMENT; anamnesis / diagnosis /
    tatalaksana -> CRITERIA). Returns `default_type` when the chunk carries no dominant schema
    (headers, page numbers, references).
    """
    t = (text_content or "").lower()
    scores = {
        "PRODUCT": sum(1 for p in _PRODUCT_FIELD_PATTERNS if re.search(p, t)),
        "TREATMENT": sum(1 for p in _TREATMENT_FIELD_PATTERNS if re.search(p, t)),
        "CRITERIA": sum(1 for p in _CRITERIA_FIELD_PATTERNS if re.search(p, t)),
    }
    best, best_score = max(scores.items(), key=lambda kv: kv[1])
    runner_up = max(v for k, v in scores.items() if k != best)
    if best_score >= 1 and best_score > runner_up:
        return best
    return default_type


def resolve_document_chunk_types(texts: List[str], document_type: str) -> List[str]:
    """
    Types every chunk of one document version. Chunks with a clear schema keep their own type
    (a document-level guess applied to all chunks mislabels mixed documents, e.g. a facial treatment
    catalog stored as PRODUCT). Chunks without one inherit the type most of the document's classified
    chunks have; the document-level guess is used only when no chunk is classifiable.
    """
    own = [infer_chunk_knowledge_type(t, None) for t in texts]
    classified = [k for k in own if k]
    fallback = max(set(classified), key=classified.count) if classified else document_type
    return [k or fallback for k in own]


def auto_detect_domain_and_status(text_content: str, raw_domain: Optional[str] = None, is_disc: bool = False) -> Tuple[str, bool]:
    """
    Infers clinical domain and discontinued status deterministically from content tokens.
    Guarded against false positives from inactive ingredients (e.g. 'zat tidak aktif')
    and general mentions of discontinue.
    """
    norm_text = text_content.lower()
    
    disc = is_disc
    if not disc:
        for p in DISCONTINUED_PATTERNS:
            if re.search(p, norm_text):
                disc = True
                break

    dom = raw_domain.strip().upper() if (raw_domain and str(raw_domain).strip()) else None
    if not dom:
        for d_name, kws in DOMAIN_RULES:
            if any(kw in norm_text for kw in kws):
                dom = d_name
                break
        if not dom:
            dom = "GENERAL_CLINICAL"
            
    return dom, disc


class CanonicalIngestService:
    """
    Relational SSOT Ingestion & Publishing Service for Clinical Knowledge.
    """

    def __init__(self):
        self.engine = get_sync_engine()

    def get_or_create_version(
        self,
        knowledge_id: str,
        file_hash: str,
        default_knowledge_type: str = "OTHER",
        authority_level: int = 2,
        visibility: Optional[Dict[str, Any]] = None,
        effective_from: Optional[str] = None,
        effective_until: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves an active draft/processing version or creates a new immutable version sequence.
        """
        vis_json = json.dumps(visibility or {"clinics": ["ALL"], "doctor_types": ["ALL"], "doctors": ["ALL"]})
        kid = str(knowledge_id)

        with self.engine.begin() as conn:
            # Check for existing draft or processing version
            check_sql = text("""
                SELECT id, version_no, status, ingestion_job_status
                FROM knowledge_version
                WHERE knowledge_id = :kid AND status IN ('DRAFT', 'PROCESSING')
                ORDER BY version_no DESC
                LIMIT 1;
            """)
            existing = conn.execute(check_sql, {"kid": kid}).fetchone()
            if existing:
                return {
                    "version_id": str(existing[0]),
                    "version_no": existing[1],
                    "status": existing[2],
                    "ingestion_job_status": existing[3],
                    "is_new": False
                }

            # Fetch latest version_no
            max_ver_sql = text("SELECT COALESCE(MAX(version_no), 0) FROM knowledge_version WHERE knowledge_id = :kid;")
            latest_no = conn.execute(max_ver_sql, {"kid": kid}).scalar() or 0
            new_version_no = latest_no + 1
            new_ver_id = str(uuid.uuid4())

            insert_sql = text("""
                INSERT INTO knowledge_version (
                    id, knowledge_id, version_no, status, ingestion_job_status,
                    file_hash, default_knowledge_type, authority_level,
                    effective_from, effective_until, visibility, created_by
                ) VALUES (
                    :id, :kid, :ver_no, 'PROCESSING', 'PENDING',
                    :file_hash, :k_type, :auth_lvl,
                    :eff_from, :eff_until, CAST(:vis AS jsonb), :created_by
                ) RETURNING id, version_no, status, ingestion_job_status;
            """)
            clean_ktype = str(default_knowledge_type or "OTHER").upper().strip()
            if clean_ktype not in {'PRODUCT', 'TREATMENT', 'SOP', 'CRITERIA', 'LITERATURE', 'PROMO', 'OTHER'}:
                clean_ktype = "OTHER"

            row = conn.execute(insert_sql, {
                "id": new_ver_id,
                "kid": kid,
                "ver_no": new_version_no,
                "file_hash": file_hash,
                "k_type": clean_ktype,
                "auth_lvl": authority_level,
                "eff_from": effective_from,
                "eff_until": effective_until,
                "vis": vis_json,
                "created_by": created_by
            }).fetchone()

            logger.info(f"Created new KnowledgeVersion {row[0]} (v{row[1]}) for doc {kid}")
            return {
                "version_id": str(row[0]),
                "version_no": row[1],
                "status": row[2],
                "ingestion_job_status": row[3],
                "is_new": True
            }

    def ingest_canonical_document(self, version_id: str, *args, **kwargs) -> Dict[str, Any]:
        """
        Persists a version's canonical content (see _ingest_canonical_document_tx). The write is one transaction,
        so a failure rolls it back; the version is then marked FAILED, so nothing waits on it as still in progress
        (an approval would otherwise wait out its full timeout on a job that can no longer finish).
        """
        try:
            return self._ingest_canonical_document_tx(version_id, *args, **kwargs)
        except Exception:
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE knowledge_version SET ingestion_job_status = 'FAILED', updated_at = NOW() WHERE id = :v_id;"
                    ), {"v_id": str(version_id)})
            except Exception as mark_err:
                logger.warning(f"Could not mark version {version_id} as FAILED: {mark_err}")
            raise

    def _ingest_canonical_document_tx(
        self,
        version_id: str,
        evidences: List[CanonicalEvidence],
        entities: List[CanonicalEntity],
        assets: List[CanonicalAsset],
        evidence_entities: Optional[List[Tuple[str, str]]] = None,
        evidence_assets: Optional[List[Tuple[str, str, str]]] = None,
        parse_report: Optional[ParseReport] = None,
        summary_md: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Atomically persists canonical evidence, entities, assets, and builds derived kb_chunk projections.
        """
        v_id = str(version_id)
        ev_ents = evidence_entities or []
        ev_asts = evidence_assets or []
        p_rep = parse_report or ParseReport(source_file="unknown")

        with self.engine.begin() as conn:
            # 1. Clean previous staging items for this version (Idempotent replay)
            conn.execute(text("DELETE FROM kb_chunk WHERE version_id = :v_id;"), {"v_id": v_id})
            conn.execute(text("DELETE FROM kb_evidence WHERE version_id = :v_id;"), {"v_id": v_id})
            conn.execute(text("DELETE FROM kb_asset WHERE version_id = :v_id;"), {"v_id": v_id})

            # Fetch version metadata for ACL projection and authority level
            v_meta = conn.execute(
                text("SELECT default_knowledge_type, authority_level, visibility, status FROM knowledge_version WHERE id = :v_id;"),
                {"v_id": v_id}
            ).fetchone()
            if not v_meta:
                raise ValueError(f"KnowledgeVersion {v_id} not found in database.")

            def_ktype, auth_level, vis_dict, ver_status = v_meta
            is_active_projection = (ver_status == "ACTIVE")
            acl_clinics = vis_dict.get("clinics", ["ALL"])
            acl_doctor_types = vis_dict.get("doctor_types", ["ALL"])
            acl_doctors = vis_dict.get("doctors", ["ALL"])

            # 2. Upsert Entities & Build Map
            entity_id_map: Dict[str, str] = {} # normalized_key -> uuid_str
            for ent in entities:
                norm_key = ent.normalized_key or normalize_entity_key(ent.canonical_name)
                ent_sql = text("""
                    INSERT INTO kb_entity (id, entity_type, entity_namespace, canonical_name, normalized_key, form_factor, aliases)
                    VALUES (:id, :etype, :ens, :cname, :nkey, :ff, :aliases)
                    ON CONFLICT (entity_type, entity_namespace, normalized_key)
                    DO UPDATE SET aliases = EXCLUDED.aliases, form_factor = COALESCE(EXCLUDED.form_factor, kb_entity.form_factor)
                    RETURNING id;
                """)
                new_ent_id = ent.id or str(uuid.uuid4())
                res = conn.execute(ent_sql, {
                    "id": new_ent_id,
                    "etype": ent.entity_type,
                    "ens": ent.entity_namespace,
                    "cname": ent.canonical_name,
                    "nkey": norm_key,
                    "ff": ent.form_factor,
                    "aliases": ent.aliases or []
                }).scalar()
                ent.id = str(res)
                entity_id_map[norm_key] = str(res)

            # 3. Insert Media Assets
            for ast in assets:
                ast_id = ast.id or str(uuid.uuid4())
                ast.id = ast_id
                ast_sql = text("""
                    INSERT INTO kb_asset (
                        id, version_id, storage_key, content_hash, asset_kind,
                        parent_asset_id, bbox, asset_class, classification_score,
                        classification_breakdown, label, width, height, provenance, status
                    ) VALUES (
                        :id, :v_id, :s_key, :c_hash, :kind,
                        :parent_id, :bbox, :aclass, :score,
                        CAST(:bdown AS jsonb), :lbl, :w, :h, CAST(:prov AS jsonb), :status
                    );
                """)
                conn.execute(ast_sql, {
                    "id": ast_id,
                    "v_id": v_id,
                    "s_key": ast.storage_key,
                    "c_hash": ast.content_hash,
                    "kind": ast.asset_kind,
                    "parent_id": ast.parent_asset_id,
                    "bbox": ast.bbox,
                    "aclass": ast.asset_class,
                    "score": ast.classification_score,
                    "bdown": json.dumps(ast.classification_breakdown),
                    "lbl": ast.label,
                    "w": ast.width,
                    "h": ast.height,
                    "prov": json.dumps(ast.provenance),
                    "status": ast.status
                })

            # 4. Insert Evidences & Build Materialized Chunks
            chunks_to_insert = []
            ev_params = []
            auto_ee_params = []
            vis_summary = {"total": 0, "completed": 0, "review_required": 0, "failed": 0}

            VALID_KTYPES = {'PRODUCT', 'TREATMENT', 'SOP', 'CRITERIA', 'LITERATURE', 'PROMO', 'OTHER'}
            ev_sql = text("""
                INSERT INTO kb_evidence (
                    id, version_id, evidence_type, knowledge_type, authority_override,
                    section_path, title, body, attributes, provenance,
                    evidence_content_hash, derivation, processor, processor_version,
                    confidence, visual_analysis_status, ordinal
                ) VALUES (
                    :id, :v_id, :etype, :ktype, :auth,
                    :sec, :title, :body, CAST(:attr AS jsonb), CAST(:prov AS jsonb),
                    :hash, :derivation, :proc, :proc_ver,
                    :conf, :vis_status, :ordinal
                );
            """)

            raw_doc_k = str(def_ktype or "OTHER").upper().strip()
            chunk_types = resolve_document_chunk_types(
                [f"{ev.title or ''}\n{ev.body or ''}" for ev in evidences],
                raw_doc_k if raw_doc_k in VALID_KTYPES else "OTHER",
            )

            for idx, ev in enumerate(evidences):
                ev_id = ev.id or str(uuid.uuid4())
                ev.id = ev_id
                ev_hash = ev.ensure_hash()
                ktype = chunk_types[idx]
                ev.knowledge_type = ktype
                ev_auth = ev.authority_override or auth_level

                # Update visual statistics
                if ev.evidence_type == "VISUAL" or ev.visual_analysis_status:
                    vis_summary["total"] += 1
                    st = ev.visual_analysis_status or "VISION_COMPLETE"
                    if st in ("VISION_COMPLETE", "NATIVE_COMPLETE", "OCR_COMPLETE"):
                        vis_summary["completed"] += 1
                    elif st in ("REVIEW_REQUIRED", "LOW_CONFIDENCE", "PARTIAL"):
                        vis_summary["review_required"] += 1
                    else:
                        vis_summary["failed"] += 1

                ev_params.append({
                    "id": ev_id,
                    "v_id": v_id,
                    "etype": ev.evidence_type,
                    "ktype": ktype,
                    "auth": ev_auth,
                    "sec": ev.section_path or [],
                    "title": ev.title,
                    "body": ev.body,
                    "attr": json.dumps(ev.attributes),
                    "prov": json.dumps(ev.provenance),
                    "hash": ev_hash,
                    "derivation": ev.derivation,
                    "proc": ev.processor,
                    "proc_ver": ev.processor_version,
                    "conf": ev.confidence,
                    "vis_status": ev.visual_analysis_status,
                    "ordinal": ev.ordinal or idx
                })

                # Build Derived Materialized Chunk Projection (Section 2.1 #5)
                # Format deterministic retrieval text with canonical tokens
                attr_dict = ev.attributes or {}
                raw_dom = attr_dict.get("domain") or attr_dict.get("clinical_domain")
                raw_disc = bool(attr_dict.get("is_discontinued"))
                tgt_inds = attr_dict.get("target_indications") or attr_dict.get("indications")

                item_probe = f"{ev.title or ''}\n{ev.body or ''}"
                combined_text_probe = f"{item_probe} {' '.join(ev.section_path or [])}"
                eff_domain, is_disc = auto_detect_domain_and_status(
                    text_content=item_probe,
                    raw_domain=raw_dom,
                    is_disc=raw_disc
                )
                if not eff_domain or eff_domain == "GENERAL_CLINICAL":
                    eff_domain, _ = auto_detect_domain_and_status(
                        text_content=combined_text_probe,
                        raw_domain=raw_dom,
                        is_disc=is_disc
                    )

                parts = [f"Type: {ktype.upper()}"]
                if eff_domain:
                    parts.append(f"Domain: {eff_domain}")
                if is_disc:
                    parts.append("Status: DISCONTINUED")
                if tgt_inds and isinstance(tgt_inds, list):
                    parts.append(f"Target Indications: {', '.join(str(x) for x in tgt_inds)}")
                if ev.title:
                    parts.append(f"Title: {ev.title.strip()}")
                if ev.section_path:
                    parts.append(f"Section: {' / '.join(ev.section_path)}")
                parts.append(f"Content: {ev.body.strip()}")
                retrieval_text = " | ".join(parts)

                chunk_deterministic_id = generate_stable_chunk_id(
                    doc_identifier=v_id,
                    version="1.0",
                    sheet_or_page=ev.provenance.get("page", 1),
                    row_or_entity=ev.provenance.get("sheet", idx),
                    chunk_index=idx
                )

                # Resolved entity ids for this evidence
                matched_ent_ids = []
                ev_norm_str = re.sub(r'[^a-zA-Z0-9]', '', f"{ev.title or ''} {ev.body}".lower())
                ev_lower = f"{ev.title or ''} {ev.body}".lower()
                for norm_k, e_uuid in entity_id_map.items():
                    norm_k_alphanumeric = re.sub(r'[^a-zA-Z0-9]', '', norm_k)
                    if (
                        (len(norm_k_alphanumeric) >= 3 and norm_k_alphanumeric in ev_norm_str)
                        or norm_k in ev_lower
                        or (len(norm_k) >= 3 and f" {norm_k} " in f" {ev_lower} ")
                    ):
                        matched_ent_ids.append(e_uuid)

                # Auto-link evidence to entity in kb_evidence_entity
                for m_eid in matched_ent_ids:
                    auto_ee_params.append({"e_id": ev_id, "ent_id": m_eid})

                chunks_to_insert.append({
                    "id": chunk_deterministic_id,
                    "version_id": v_id,
                    "evidence_ids": [ev_id],
                    "retrieval_text": retrieval_text,
                    "knowledge_type": ktype,
                    "authority_level": ev_auth,
                    "entity_ids": matched_ent_ids,
                    "acl_clinics": acl_clinics,
                    "acl_doctor_types": acl_doctor_types,
                    "acl_doctors": acl_doctors,
                    "is_active": is_active_projection,
                    "domain": eff_domain,
                    "is_discontinued": is_disc,
                    "target_indications": [str(x) for x in tgt_inds] if (tgt_inds and isinstance(tgt_inds, list)) else []
                })

            if ev_params:
                conn.execute(ev_sql, ev_params)

            if auto_ee_params:
                conn.execute(text("""
                    INSERT INTO kb_evidence_entity (evidence_id, entity_id)
                    VALUES (:e_id, :ent_id) ON CONFLICT DO NOTHING;
                """), auto_ee_params)

            # 5. Insert Explicit Evidence Entity & Asset Mappings
            for e_id, ent_uuid in ev_ents:
                chk = conn.execute(text("SELECT 1 FROM kb_entity WHERE id = :eid;"), {"eid": ent_uuid}).scalar()
                if chk:
                    conn.execute(text("""
                        INSERT INTO kb_evidence_entity (evidence_id, entity_id)
                        VALUES (:e_id, :ent_id) ON CONFLICT DO NOTHING;
                    """), {"e_id": e_id, "ent_id": ent_uuid})

            for e_id, a_id, role in ev_asts:
                conn.execute(text("""
                    INSERT INTO kb_evidence_asset (evidence_id, asset_id, role)
                    VALUES (:e_id, :a_id, :role) ON CONFLICT DO NOTHING;
                """), {"e_id": e_id, "a_id": a_id, "role": role})

            # 6. Bulk Insert Derived Materialized Chunks with Embeddings
            from app.rag.config import settings as rag_settings
            if getattr(rag_settings, "contextual_retrieval_enabled", False) and chunks_to_insert:
                from app.rag.services.search_context import add_search_context
                add_search_context(chunks_to_insert)
            chunk_embeddings = []
            try:
                from app.rag.services.embeddings import EmbeddingFactory
                emb_adapter = EmbeddingFactory.get_embeddings_adapter()
                if emb_adapter and chunks_to_insert:
                    texts_to_embed = [chk["retrieval_text"] for chk in chunks_to_insert]
                    chunk_embeddings = emb_adapter.embed_documents(texts_to_embed)
            except Exception as emb_err:
                logger.warning(f"Embedding generation during canonical ingestion skipped/failed: {emb_err}")
                chunk_embeddings = []

            chk_sql = text("""
                INSERT INTO kb_chunk (
                    id, version_id, evidence_ids, retrieval_text, knowledge_type,
                    authority_level, entity_ids, acl_clinics, acl_doctor_types,
                    acl_doctors, is_active, domain, is_discontinued, target_indications, embedding
                ) VALUES (
                    :id, :v_id, CAST(:ev_ids AS uuid[]), :rtext, :ktype,
                    :auth, CAST(:ent_ids AS uuid[]), :clinics, :dtypes,
                    :docs, :is_act, :domain, :is_disc, CAST(:tgt_inds AS text[]), CAST(:embedding AS vector)
                )
                ON CONFLICT (id) DO UPDATE SET
                    retrieval_text = EXCLUDED.retrieval_text,
                    is_active = EXCLUDED.is_active,
                    domain = EXCLUDED.domain,
                    is_discontinued = EXCLUDED.is_discontinued,
                    target_indications = EXCLUDED.target_indications,
                    embedding = COALESCE(EXCLUDED.embedding, kb_chunk.embedding);
            """)

            chunk_params = []
            for idx, chk in enumerate(chunks_to_insert):
                vec_str = None
                if chunk_embeddings and idx < len(chunk_embeddings) and chunk_embeddings[idx]:
                    vec_str = "[" + ",".join(str(x) for x in chunk_embeddings[idx]) + "]"

                chunk_params.append({
                    "id": chk["id"],
                    "v_id": chk["version_id"],
                    "ev_ids": chk["evidence_ids"],
                    "rtext": chk["retrieval_text"],
                    "ktype": chk["knowledge_type"],
                    "auth": chk["authority_level"],
                    "ent_ids": chk["entity_ids"],
                    "clinics": chk["acl_clinics"],
                    "dtypes": chk["acl_doctor_types"],
                    "docs": chk["acl_doctors"],
                    "is_act": chk["is_active"],
                    "domain": chk.get("domain"),
                    "is_disc": chk.get("is_discontinued", False),
                    "tgt_inds": chk.get("target_indications", []),
                    "embedding": vec_str
                })

            if chunk_params:
                conn.execute(chk_sql, chunk_params)

            # 7. Update KnowledgeVersion status & reports
            report_dict = p_rep.to_dict()
            report_dict["visual_summary"] = vis_summary
            
            # Determine readiness status
            next_status = "READY_FOR_REVIEW"
            if vis_summary["review_required"] > 0:
                next_status = "READY_FOR_REVIEW" # Has items requiring admin eyes
            
            update_ver_sql = text("""
                UPDATE knowledge_version
                SET ingestion_job_status = 'COMPLETED',
                    status = :st,
                    visual_jobs_summary = CAST(:v_sum AS jsonb),
                    parse_report = CAST(:p_rep AS jsonb),
                    summary_md = COALESCE(:s_md, summary_md),
                    updated_at = NOW()
                WHERE id = :v_id;
            """)
            conn.execute(update_ver_sql, {
                "v_id": v_id,
                "st": next_status,
                "v_sum": json.dumps(vis_summary),
                "p_rep": json.dumps(report_dict),
                "s_md": summary_md
            })

            logger.info(
                f"Ingested KnowledgeVersion {v_id}: {len(evidences)} evidences, "
                f"{len(entities)} entities, {len(assets)} assets, {len(chunks_to_insert)} chunks. Status: {next_status}"
            )

        return {
            "version_id": v_id,
            "evidence_count": len(evidences),
            "entity_count": len(entities),
            "asset_count": len(assets),
            "chunk_count": len(chunks_to_insert),
            "visual_summary": vis_summary,
            "status": next_status
        }

    def check_knowledge_readiness(self, version_id: str) -> Dict[str, Any]:
        """
        Knowledge Readiness Gate (D9).
        Verifies that all mandatory extraction and vision jobs are completed and no unresolved review items remain.
        """
        v_id = str(version_id)
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, status, ingestion_job_status, visual_jobs_summary FROM knowledge_version WHERE id = :v_id;"),
                {"v_id": v_id}
            ).fetchone()
            if not row:
                return {"is_ready": False, "status": "NOT_FOUND", "reasons": ["Version does not exist."]}

            _, status, job_status, vis_summary = row
            reasons = []

            # 1. Job must be COMPLETED
            if job_status != "COMPLETED":
                reasons.append(f"Ingestion job status is '{job_status}' (must be COMPLETED).")

            # 2. Check for unresolved visual / extraction items
            unresolved_sql = text("""
                SELECT COUNT(*) FROM kb_evidence
                WHERE version_id = :v_id
                  AND visual_analysis_status IN ('REVIEW_REQUIRED', 'VISION_FAILED', 'LOW_CONFIDENCE', 'PARTIAL');
            """)
            unresolved_count = conn.execute(unresolved_sql, {"v_id": v_id}).scalar() or 0
            if unresolved_count > 0:
                reasons.append(
                    f"Knowledge Readiness Gate: {unresolved_count} visual/chart evidence items have status "
                    "REVIEW_REQUIRED, LOW_CONFIDENCE, or VISION_FAILED. Admin verification in Staging UI is required."
                )

            is_ready = (len(reasons) == 0)
            return {
                "version_id": v_id,
                "is_ready": is_ready,
                "current_status": status,
                "job_status": job_status,
                "unresolved_items": unresolved_count,
                "reasons": reasons
            }

    def publish_version_atomic(
        self,
        knowledge_id: str,
        version_id: str,
        approved_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Atomically promotes a version to ACTIVE and supersedes prior versions (Phase 2 Transaction).
        Guarantees:
          - Gated by Knowledge Readiness (D9)
          - No orphan active projections
          - Atomic switchover in single DB transaction
        """
        v_id = str(version_id)
        kid = str(knowledge_id)

        # 1. Run Knowledge Readiness Gate
        readiness = self.check_knowledge_readiness(v_id)
        if not readiness["is_ready"]:
            reasons_str = "; ".join(readiness["reasons"])
            raise ValueError(f"Publish Rejected by Knowledge Readiness Gate: {reasons_str}")

        with self.engine.begin() as conn:
            # 2. Supersede old active versions and deactivate their chunks
            conn.execute(text("""
                UPDATE knowledge_version
                SET status = 'SUPERSEDED', updated_at = NOW()
                WHERE knowledge_id = :kid AND status = 'ACTIVE' AND id != :v_id;
            """), {"kid": kid, "v_id": v_id})

            conn.execute(text("""
                UPDATE kb_chunk
                SET is_active = false
                WHERE version_id IN (
                    SELECT id FROM knowledge_version WHERE knowledge_id = :kid AND status = 'SUPERSEDED'
                );
            """), {"kid": kid})

            # 4. Promote target version to ACTIVE and activate its chunks
            conn.execute(text("""
                UPDATE knowledge_version
                SET status = 'ACTIVE',
                    approved_by = :appr,
                    approved_at = NOW(),
                    updated_at = NOW()
                WHERE id = :v_id;
            """), {"v_id": v_id, "appr": approved_by})

            conn.execute(text("""
                UPDATE kb_chunk
                SET is_active = true
                WHERE version_id = :v_id;
            """), {"v_id": v_id})

            # 5. Synchronize main knowledge table to APPROVED
            import uuid as _uuid
            appr_uuid = None
            if approved_by:
                try:
                    appr_uuid = str(_uuid.UUID(str(approved_by)))
                except (ValueError, TypeError):
                    appr_uuid = None

            conn.execute(text("""
                UPDATE knowledge
                SET status = 'APPROVED',
                    approved_by = CAST(:appr_uuid AS uuid),
                    updated_at = NOW()
                WHERE id = CAST(:kid AS uuid);
            """), {"kid": kid, "appr_uuid": appr_uuid})

            logger.info(f"Atomic Publish Successful: Version {v_id} is now ACTIVE for doc {kid}.")

        return {
            "status": "success",
            "knowledge_id": kid,
            "version_id": v_id,
            "is_active": True,
            "message": "Document published atomically with verified readiness."
        }

    def resolve_media_asset(
        self,
        asset_id: str,
        preview_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Phase 2 Media Serving:
        Resolves media URL (presigned MinIO / storage proxy) validated directly against kb_asset.
        In production/chat serving (preview_mode=False), the asset must belong to an ACTIVE knowledge version.
        In staging/preview mode (preview_mode=True), the asset can belong to a version under review.
        """
        from app.services.storage import _generate_presigned_url, _images_bucket, _format_browser_url
        aid = str(asset_id).strip()
        with self.engine.connect() as conn:
            ast_row = conn.execute(text("""
                SELECT 
                    a.id, a.version_id, a.storage_key, a.asset_class,
                    a.classification_score, a.label, a.width, a.height, a.status,
                    v.status AS version_status, v.knowledge_id
                FROM kb_asset a
                JOIN knowledge_version v ON v.id = a.version_id
                WHERE a.id = CAST(:aid AS uuid) OR a.storage_key = :skey;
            """), {"aid": aid if len(aid) == 36 else "00000000-0000-0000-0000-000000000000", "skey": aid}).fetchone()

            if not ast_row:
                raise ValueError(f"Media asset '{asset_id}' not found in Canonical Knowledge Schema.")

            (a_id, v_id, s_key, a_class, c_score, label, w, h, ast_status, ver_status, kid) = ast_row

            if ast_status == "EXCLUDED":
                raise ValueError(f"Media asset '{asset_id}' has been EXCLUDED by Multimodal Asset Guard.")

            if not preview_mode and ver_status != "ACTIVE":
                raise ValueError(
                    f"Media asset '{asset_id}' belongs to version '{v_id}' with status '{ver_status}'. "
                    "Only assets belonging to ACTIVE versions can be served to doctor inquiries."
                )

            presigned_url = _generate_presigned_url(_images_bucket(), s_key)
            browser_url = _format_browser_url(raw_url=presigned_url, s3_key=s_key)

            return {
                "asset_id": str(a_id),
                "version_id": str(v_id),
                "knowledge_id": str(kid),
                "storage_key": s_key,
                "url": browser_url,
                "presigned_url": presigned_url,
                "asset_class": a_class,
                "classification_score": float(c_score) if c_score is not None else 0.0,
                "label": label or s_key.split("/")[-1],
                "width": w,
                "height": h,
                "status": ast_status,
                "is_active": (ver_status == "ACTIVE")
            }

    def verify_no_orphan_projections(self) -> Dict[str, Any]:
        """
        Phase 2 Invariant Verification:
        Guarantees:
          1. 0 active chunks for non-ACTIVE versions.
          2. Exactly 0 or 1 ACTIVE version per document.
          3. Total active chunks strictly equal chunks linked to ACTIVE versions.
        """
        with self.engine.connect() as conn:
            # 1. Orphan active chunks
            orphan_sql = text("""
                SELECT COUNT(*)
                FROM kb_chunk c
                JOIN knowledge_version v ON v.id = c.version_id
                WHERE c.is_active = true AND v.status != 'ACTIVE';
            """)
            orphan_count = conn.execute(orphan_sql).scalar() or 0

            # 2. Inactive chunks of active versions
            inactive_active_ver_sql = text("""
                SELECT COUNT(*)
                FROM kb_chunk c
                JOIN knowledge_version v ON v.id = c.version_id
                WHERE c.is_active = false AND v.status = 'ACTIVE';
            """)
            inactive_count = conn.execute(inactive_active_ver_sql).scalar() or 0

            # 3. Documents with multiple active versions (violates uq_one_active_version_per_doc)
            multi_active_sql = text("""
                SELECT knowledge_id, COUNT(*)
                FROM knowledge_version
                WHERE status = 'ACTIVE'
                GROUP BY knowledge_id
                HAVING COUNT(*) > 1;
            """)
            multi_active_docs = conn.execute(multi_active_sql).fetchall()

            is_valid = (orphan_count == 0) and (inactive_count == 0) and (len(multi_active_docs) == 0)

            return {
                "is_valid": is_valid,
                "orphan_active_chunks": orphan_count,
                "inactive_chunks_of_active_versions": inactive_count,
                "multi_active_documents": [str(r[0]) for r in multi_active_docs],
                "message": "No orphan active projections verified 100%." if is_valid else "Invariant violation detected!"
            }

    def get_quality_gate_audit(self, knowledge_id: str, summary_only: bool = False) -> Dict[str, Any]:
        """
        Phase 1.5 Quality Gate Staging Audit & Admin Observability.
        Returns readiness status, disposition breakdown, visual summary, evidences, and assets.
        If summary_only is True, skips loading heavy evidence/asset body records.
        """
        kid = str(knowledge_id)
        with self.engine.connect() as conn:
            # 1. Get latest version
            ver_row = conn.execute(text("""
                SELECT id, version_no, status, ingestion_job_status, visual_jobs_summary, parse_report, default_knowledge_type, authority_level
                FROM knowledge_version
                WHERE knowledge_id = :kid
                ORDER BY version_no DESC
                LIMIT 1;
            """), {"kid": kid}).fetchone()

            if not ver_row:
                # Return empty/default state if version not yet created
                return {
                    "knowledge_id": kid,
                    "version_id": None,
                    "version_no": 0,
                    "status": "NOT_FOUND",
                    "job_status": "PENDING",
                    "readiness": {"is_ready": False, "can_publish": False, "reasons": ["Version belum dibuat."]},
                    "parse_report": {"total_physical_rows": 0, "disposition_summary": {"evidence_count": 0, "context_rows": 0, "excluded_rows": 0}, "exclusions": []},
                    "visual_summary": {"total": 0, "completed": 0, "review_required": 0, "failed": 0},
                    "total_evidence_count": 0,
                    "total_asset_count": 0,
                    "evidences": [],
                    "assets": []
                }

            v_id, v_no, v_status, job_st, vis_sum, p_rep, def_ktype, auth_lvl = ver_row
            v_id_str = str(v_id)

            # 2. Check Readiness Gate
            readiness = self.check_knowledge_readiness(v_id_str)
            readiness["can_publish"] = readiness["is_ready"] and (v_status != "ACTIVE")

            if summary_only:
                # Lightweight fast path: count evidences & assets without serializing hundreds of bodies
                total_ev = conn.execute(text("SELECT count(*) FROM kb_evidence WHERE version_id = :vid;"), {"vid": v_id_str}).scalar() or 0
                total_ast = conn.execute(text("SELECT count(*) FROM kb_asset WHERE version_id = :vid;"), {"vid": v_id_str}).scalar() or 0
                return {
                    "knowledge_id": kid,
                    "version_id": v_id_str,
                    "version_no": v_no,
                    "status": v_status,
                    "job_status": job_st,
                    "default_knowledge_type": def_ktype,
                    "authority_level": auth_lvl,
                    "readiness": readiness,
                    "parse_report": p_rep or {},
                    "visual_summary": vis_sum or {},
                    "total_evidence_count": total_ev,
                    "total_asset_count": total_ast,
                    "evidences": [],
                    "assets": []
                }

            # 3. Fetch Evidence items
            ev_rows = conn.execute(text("""
                SELECT id, evidence_type, knowledge_type, section_path, title, body, attributes, derivation, confidence, visual_analysis_status, ordinal
                FROM kb_evidence
                WHERE version_id = :vid
                ORDER BY ordinal ASC;
            """), {"vid": v_id_str}).fetchall()

            evidences = []
            for r in ev_rows:
                evidences.append({
                    "id": str(r[0]),
                    "evidence_type": r[1],
                    "knowledge_type": r[2],
                    "section_path": r[3] or [],
                    "title": r[4],
                    "body": r[5],
                    "attributes": r[6] or {},
                    "derivation": r[7],
                    "confidence": r[8],
                    "visual_analysis_status": r[9],
                    "ordinal": r[10]
                })

            # 4. Fetch Media Assets
            ast_rows = conn.execute(text("""
                SELECT id, storage_key, asset_class, classification_score, classification_breakdown, label, width, height, status
                FROM kb_asset
                WHERE version_id = :vid
                ORDER BY created_at ASC;
            """), {"vid": v_id_str}).fetchall()

            assets = []
            for a in ast_rows:
                assets.append({
                    "id": str(a[0]),
                    "storage_key": a[1],
                    "asset_class": a[2],
                    "classification_score": round(a[3], 4) if a[3] is not None else 0.0,
                    "classification_breakdown": a[4] or {},
                    "label": a[5],
                    "width": a[6],
                    "height": a[7],
                    "status": a[8]
                })

            return {
                "knowledge_id": kid,
                "version_id": v_id_str,
                "version_no": v_no,
                "status": v_status,
                "job_status": job_st,
                "readiness": readiness,
                "parse_report": p_rep or {},
                "visual_summary": vis_sum or {},
                "total_evidence_count": len(evidences),
                "total_asset_count": len(assets),
                "evidences": evidences,
                "assets": assets
            }

    def update_evidence(
        self,
        version_id: str,
        evidence_id: str,
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        D1-a Implementation: Admin edits and corrects Evidence in Staging.
        Updates kb_evidence, marks derivation='ADMIN_EDIT', recomputes hash,
        and resynchronizes derived kb_chunk.
        """
        vid = str(version_id)
        eid = str(evidence_id)

        with self.engine.begin() as conn:
            # 1. Fetch existing evidence
            cur = conn.execute(text("""
                SELECT section_path, title, body, attributes, knowledge_type, visual_analysis_status
                FROM kb_evidence
                WHERE id = :eid AND version_id = :vid;
            """), {"eid": eid, "vid": vid}).fetchone()
            if not cur:
                raise ValueError(f"Evidence {eid} not found in version {vid}")

            sec_path, old_title, old_body, old_attrs, ktype, old_vis = cur

            new_title = update_data.get("title", old_title)
            new_body = update_data.get("body", old_body)
            new_attrs = update_data.get("attributes", old_attrs)
            new_vis = update_data.get("visual_analysis_status", old_vis)

            # Recompute content hash
            import json as _json
            sec_str = "/".join(sec_path or [])
            attr_str = _json.dumps(new_attrs or {}, sort_keys=True)
            raw = f"{sec_str}::{new_body}::{attr_str}"
            new_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

            # 2. Update kb_evidence
            conn.execute(text("""
                UPDATE kb_evidence
                SET title = :title,
                    body = :body,
                    attributes = CAST(:attrs AS jsonb),
                    visual_analysis_status = :vis_st,
                    derivation = 'ADMIN_EDIT',
                    evidence_content_hash = :hash
                WHERE id = :eid;
            """), {
                "title": new_title,
                "body": new_body,
                "attrs": _json.dumps(new_attrs),
                "vis_st": new_vis,
                "hash": new_hash,
                "eid": eid
            })

            # 3. Synchronize derived kb_chunk
            new_retrieval_text = f"Type: {str(ktype).upper()} | Section: {' / '.join(sec_path)} | Content: {new_body.strip()}"
            if new_title:
                new_retrieval_text = f"Title: {new_title} | {new_retrieval_text}"

            conn.execute(text("""
                UPDATE kb_chunk
                SET retrieval_text = :rtext
                WHERE version_id = :vid AND :eid = ANY(evidence_ids);
            """), {"rtext": new_retrieval_text, "vid": vid, "eid": eid})

            # 4. Refresh visual_jobs_summary in knowledge_version
            summary_sql = text("""
                SELECT 
                    COUNT(*) FILTER (WHERE evidence_type = 'VISUAL' OR visual_analysis_status IS NOT NULL) AS total,
                    COUNT(*) FILTER (WHERE visual_analysis_status IN ('VISION_COMPLETE', 'NATIVE_COMPLETE', 'OCR_COMPLETE')) AS completed,
                    COUNT(*) FILTER (WHERE visual_analysis_status IN ('REVIEW_REQUIRED', 'LOW_CONFIDENCE', 'PARTIAL')) AS review_required,
                    COUNT(*) FILTER (WHERE visual_analysis_status IN ('VISION_FAILED')) AS failed
                FROM kb_evidence
                WHERE version_id = :vid;
            """)
            s_row = conn.execute(summary_sql, {"vid": vid}).fetchone()
            vis_sum = {
                "total": s_row[0] or 0,
                "completed": s_row[1] or 0,
                "review_required": s_row[2] or 0,
                "failed": s_row[3] or 0
            }

            conn.execute(text("""
                UPDATE knowledge_version
                SET visual_jobs_summary = CAST(:vsum AS jsonb), updated_at = NOW()
                WHERE id = :vid;
            """), {"vsum": _json.dumps(vis_sum), "vid": vid})

            logger.info(f"D1-a: Evidence {eid} updated by Admin in version {vid}. Hash: {new_hash[:8]}")

        readiness = self.check_knowledge_readiness(vid)
        return {
            "status": "success",
            "evidence_id": eid,
            "version_id": vid,
            "derivation": "ADMIN_EDIT",
            "visual_analysis_status": new_vis,
            "readiness": readiness
        }

    def resolve_evidence(self, version_id: str, evidence_id: str) -> Dict[str, Any]:
        """
        Quick resolution action for Admin: marks a REVIEW_REQUIRED or LOW_CONFIDENCE item as resolved.
        """
        return self.update_evidence(
            version_id=version_id,
            evidence_id=evidence_id,
            update_data={"visual_analysis_status": "VISION_COMPLETE"}
        )

    def regenerate_summary_from_evidences(self, knowledge_id: str, version_id: str) -> str:
        """
        D1-a Implementation: "Regenerate Summary" reconstructs summary markdown
        from the currently approved/corrected Canonical Evidence SSOT.
        Summary is a display derivative; Evidence is the Source of Truth.
        """
        vid = str(version_id)
        kid = str(knowledge_id)

        with self.engine.begin() as conn:
            # 1. Fetch document title and all evidences ordered by ordinal
            doc_row = conn.execute(text("SELECT title FROM knowledge WHERE id = :kid;"), {"kid": kid}).fetchone()
            doc_title = doc_row[0] if doc_row else "Knowledge Document"

            ev_rows = conn.execute(text("""
                SELECT section_path, title, body, attributes, evidence_type, ordinal
                FROM kb_evidence
                WHERE version_id = :vid
                ORDER BY ordinal ASC;
            """), {"vid": vid}).fetchall()

            if not ev_rows:
                return f"# {doc_title}\n\n*Tidak ada data evidence klinis yang tersimpan.*"

            # 2. Synthesize clean structured markdown from Evidence items
            lines = [f"# {doc_title}", ""]
            current_section = None

            for sec_path, title, body, attrs, ev_type, ord_val in ev_rows:
                sec_header = " / ".join(sec_path) if sec_path else "Informasi Umum"
                if sec_header != current_section:
                    current_section = sec_header
                    lines.append(f"## {current_section}")
                    lines.append("")

                if title and title != doc_title:
                    lines.append(f"### {title}")

                # Format body text
                lines.append(body.strip())
                lines.append("")

                # Format attributes if present (indications, dosages, flow)
                if attrs and isinstance(attrs, dict):
                    attr_bullets = []
                    if attrs.get("indications"):
                        attr_bullets.append(f"- **Indikasi**: {attrs['indications']}")
                    if attrs.get("form_factor"):
                        attr_bullets.append(f"- **Bentuk Sediaan**: {attrs['form_factor']}")
                    if attrs.get("dose"):
                        attr_bullets.append(f"- **Dosis**: {attrs['dose']}")
                    if attrs.get("extracted_values"):
                        vals = [f"{k}: {v}" for k, v in attrs["extracted_values"].items()]
                        attr_bullets.append(f"- **Data Efikasi Terukur**: {', '.join(vals)}")
                    if attrs.get("flow_steps"):
                        attr_bullets.append(f"- **Alur Prosedur**: {' -> '.join(attrs['flow_steps'])}")

                    if attr_bullets:
                        lines.extend(attr_bullets)
                        lines.append("")

            regenerated_summary = "\n".join(lines).strip()

            # 3. Update knowledge_version and knowledge table
            conn.execute(text("""
                UPDATE knowledge_version
                SET summary_md = :s_md, updated_at = NOW()
                WHERE id = :vid;
            """), {"s_md": regenerated_summary, "vid": vid})

            conn.execute(text("""
                UPDATE knowledge
                SET ai_summary = :s_md, updated_at = NOW()
                WHERE id = :kid;
            """), {"s_md": regenerated_summary, "kid": kid})

            logger.info(f"D1-a: Summary regenerated from {len(ev_rows)} evidences for doc {kid} (v {vid})")

        return regenerated_summary

    def upsert_relations(
        self,
        relations: List[Dict[str, Any]]
    ) -> int:
        """
        Upserts clinical & operational entity relationships into kb_relation (Phase 4).
        Expected relation dict:
        {
            "source_entity_id": UUID/str,
            "target_entity_id": UUID/str,
            "relation_type": 'RECOMMENDED_AFTER' | 'CONTRAINDICATED_WITH' | 'COMBINED_WITH' | 'REQUIRES_PREREQUISITE',
            "evidence_id": Optional[UUID/str],
            "description": Optional[str],
            "attributes": Optional[dict]
        }
        """
        if not relations:
            return 0
        
        upsert_count = 0
        with self.engine.begin() as conn:
            for rel in relations:
                s_id = str(rel["source_entity_id"])
                t_id = str(rel["target_entity_id"])
                rtype = str(rel["relation_type"]).upper()
                ev_id = str(rel.get("evidence_id")) if rel.get("evidence_id") else None
                desc = rel.get("description", "")
                attrs = json.dumps(rel.get("attributes", {}))

                conn.execute(text("""
                    INSERT INTO kb_relation (
                        source_entity_id, target_entity_id, relation_type,
                        evidence_id, description, attributes
                    ) VALUES (
                        CAST(:s_id AS uuid), CAST(:t_id AS uuid), :rtype,
                        CAST(:ev_id AS uuid), :desc, CAST(:attrs AS jsonb)
                    )
                    ON CONFLICT (source_entity_id, target_entity_id, relation_type)
                    DO UPDATE SET
                        evidence_id = EXCLUDED.evidence_id,
                        description = EXCLUDED.description,
                        attributes = EXCLUDED.attributes;
                """), {
                    "s_id": s_id,
                    "t_id": t_id,
                    "rtype": rtype,
                    "ev_id": ev_id,
                    "desc": desc,
                    "attrs": attrs
                })
                upsert_count += 1
        return upsert_count

