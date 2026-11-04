"""Canonical Retrieval Engine V2 (Phase 3 Specification)
ERHA Skin Clinic RAG Knowledge Architecture.

Engine Architecture:
1. Dense HNSW Partial Retrieval (kb_chunk WHERE is_active = true with hnsw.iterative_scan)
2. PostgreSQL Native Lexical Search (kb_chunk FTS tsvector @@ plainto_tsquery with GIN)
3. Structured Entity Channel (Direct SQL on kb_entity + kb_evidence_entity + kb_evidence for catalog enumeration)
4. Reciprocal Rank Fusion (RRF) with dynamic channel weighting & deterministic tie-breaking
5. Explicit Clinical Conflict Policy Matrix (SOP authority=1 > Catalog authority=2 > Literature authority=4 > Promo authority=5)
6. 3-Level ACL Evaluator (Level 1: Doctor ID -> Level 2: Doctor Type -> Level 3: Clinic ID)
"""

import os
import re
import json
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from loguru import logger
from sqlalchemy import text, Engine

from app.core.database import get_sync_engine
from app.rag.config import settings
from app.rag.services.intent import QueryIntent, QueryIntentDetector
from app.rag.services.embeddings import EmbeddingFactory, BaseEmbeddingsAdapter

# English function words: a translated query keeps the words that name what is asked, not these
_ENGLISH_FUNCTION_WORDS = frozenset("""
about above after again against also among another anything because been before being below between both
could does doing done down during each either else even ever every from further have having here hers herself
himself however including into itself just least less like made make many more most much must myself near
neither never none occur occurs only other others ought ourselves over own same shall should since some
something such than that their theirs them themselves then there these they this those though through thus
under until upon very want what when whence where whether which while whom whose will with within without
would your yours yourself yourselves complete
""".split())


@dataclass
class CanonicalRetrievalHit:
    id: str
    text: str
    score: float
    channel: str  # 'dense', 'fts', 'structured_entity'
    authority_level: int = 2
    knowledge_type: str = "PRODUCT"
    version_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    rrf_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "score": round(self.score, 4),
            "rrf_score": round(self.rrf_score, 4),
            "channel": self.channel,
            "authority_level": self.authority_level,
            "knowledge_type": self.knowledge_type,
            "version_id": self.version_id,
            "metadata": self.metadata
        }


# =============================================================================
# 1. 3-LEVEL ACL EVALUATOR (Section 4.2)
# =============================================================================

def evaluate_acl_3level(
    acl_doctors: List[str],
    acl_doctor_types: List[str],
    acl_clinics: List[str],
    doctor_id: Optional[str] = None,
    doctor_type: Optional[str] = None,
    clinic_id: Optional[str] = None
) -> bool:
    """
    Evaluates 3-Level ACL hierarchy:
    - Level 1: Specific Doctor Override (doctor_id in acl_doctors) -> Granted immediately
    - Level 2: Doctor Type Match (SPKK / GP / CONSULTANT)
      AND
    - Level 3: Clinic Match (CLINIC_A / ALL)
    """
    doc_id_clean = str(doctor_id or "").strip()
    doc_type_clean = str(doctor_type or "ALL").strip().upper()
    clinic_clean = str(clinic_id or "ALL").strip().upper()

    allowed_docs = [str(d).strip() for d in (acl_doctors or ["ALL"])]
    allowed_types = [str(t).strip().upper() for t in (acl_doctor_types or ["ALL"])]
    allowed_clinics = [str(c).strip().upper() for c in (acl_clinics or ["ALL"])]

    # Level 1: Specific Doctor Override
    if doc_id_clean and (doc_id_clean in allowed_docs):
        return True
    # A document restricted to named doctors is visible to those doctors only
    if not any(d.upper() == "ALL" for d in allowed_docs):
        return False

    # Level 2: Doctor Type
    type_matches = ("ALL" in allowed_types or doc_type_clean in allowed_types)

    # Level 3: Clinic
    clinic_matches = ("ALL" in allowed_clinics or clinic_clean in allowed_clinics)

    return type_matches and clinic_matches


# =============================================================================
# 2. CLINICAL CONFLICT POLICY RESOLVER (Section 4.1)
# =============================================================================

class ClinicalConflictResolver:
    """
    Resolves factual and operational conflicts across retrieved candidate evidences
    based on the Clinical Conflict Policy Matrix:
    - Operational / Procedures: SOP (authority=1) wins over Literature / Promo.
    - Product Specs / Indikasi: Catalog (authority=2) wins over sales/marketing.
    - Medical Claims / Efficacy: Scientific Literature (authority=4) attached as evidence.
    - Promotional Prices / Discounts: Promo (authority=5) valid only within active dates.
    """

    PROCEDURE_PATTERNS = [
        r'\b(?:prosedur|tahapan?|protokol|langkah|sop|alur|cara\s+tindakan|sterilisasi|tindakan|treatment)\b'
    ]
    PRODUCT_PATTERNS = [
        r'\b(?:produk|skincare|serum|krim|cream|toner|cleanser|katalog|bahan\s+aktif|kandungan|komposisi|sediaan|indikasi)\b'
    ]
    EFFICACY_PATTERNS = [
        r'\b(?:efikasi|uji\s+klinis|jurnal|studi|penelitian|mekanisme|ilmiah|riset)\b'
    ]
    PROMO_PATTERNS = [
        r'\b(?:promo|diskon|harga|potongan|cashback|voucher|penawaran)\b'
    ]

    @classmethod
    def detect_query_facet(cls, query: str) -> str:
        q_lower = query.lower()
        if any(re.search(p, q_lower) for p in cls.PROCEDURE_PATTERNS):
            return "PROCEDURE"
        if any(re.search(p, q_lower) for p in cls.PROMO_PATTERNS):
            return "PROMO"
        if any(re.search(p, q_lower) for p in cls.EFFICACY_PATTERNS):
            return "EFFICACY"
        if any(re.search(p, q_lower) for p in cls.PRODUCT_PATTERNS):
            return "PRODUCT"
        return "GENERAL"

    @classmethod
    def resolve(
        cls,
        hits: List[Dict[str, Any]],
        query: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not hits:
            return [], None

        facet = cls.detect_query_facet(query)
        conflict_note: Optional[str] = None

        sop_hits = [h for h in hits if h.get("authority_level") == 1 or str(h.get("knowledge_type")).upper() == "SOP"]
        catalog_hits = [h for h in hits if h.get("authority_level") == 2 or str(h.get("knowledge_type")).upper() == "PRODUCT"]
        literature_hits = [h for h in hits if h.get("authority_level") == 4 or str(h.get("knowledge_type")).upper() == "LITERATURE"]
        promo_hits = [h for h in hits if h.get("authority_level") == 5 or str(h.get("knowledge_type")).upper() == "PROMO"]

        # Rule 1: Operational / Clinic Procedure -> SOP Aktif (authority=1) wins
        if facet == "PROCEDURE" and sop_hits:
            resolved_hits = sop_hits.copy()
            # Append non-conflicting catalog/literature hits if relevant
            for h in hits:
                if h not in resolved_hits and h.get("authority_level", 5) < 5:
                    resolved_hits.append(h)
            if promo_hits:
                conflict_note = "Berdasarkan SOP resmi yang berlaku, protokol klinis mengacu pada dokumen operasional resmi. Materi promo dikesampingkan."
            return resolved_hits, conflict_note

        # Rule 2: Product Specs / Indikasi -> Katalog Produk Aktif (authority=2) wins
        if facet == "PRODUCT" and catalog_hits:
            resolved_hits = catalog_hits.copy()
            for h in hits:
                if h not in resolved_hits and h.get("authority_level", 5) != 5:
                    resolved_hits.append(h)
            return resolved_hits, None

        # Rule 3: Promo / Price -> Promo Aktif (authority=5) only if not expired
        if facet == "PROMO":
            today = datetime.now(timezone.utc).date()
            valid_promo_hits = []
            for h in promo_hits:
                meta = h.get("metadata", {})
                v_from = meta.get("effective_from") or meta.get("valid_from")
                v_until = meta.get("effective_until") or meta.get("valid_until")
                is_valid = True
                if v_until:
                    try:
                        u_date = datetime.strptime(str(v_until).split("T")[0], "%Y-%m-%d").date()
                        if u_date < today:
                            is_valid = False
                    except Exception:
                        pass
                if is_valid:
                    valid_promo_hits.append(h)

            resolved_hits = valid_promo_hits + [h for h in hits if h not in promo_hits]
            return resolved_hits, None

        # Default ordering: sort primarily by authority level if scores are tied, or preserve RRF
        return hits, None


# =============================================================================
# 3. RETRIEVAL ENGINE V2 (CANONICAL HYBRID + ENTITY CHANNEL)
# =============================================================================

class CanonicalV2Retriever:
    def __init__(
        self,
        engine: Optional[Engine] = None,
        embeddings_adapter: Optional[BaseEmbeddingsAdapter] = None
    ):
        self.engine = engine or get_sync_engine()
        self.embeddings = embeddings_adapter

    def _get_embeddings_adapter(self) -> Optional[BaseEmbeddingsAdapter]:
        if self.embeddings is None:
            try:
                self.embeddings = EmbeddingFactory.get_embeddings_adapter()
            except Exception as e:
                logger.debug(f"OpenAI Embeddings adapter not initialized: {e}")
                self.embeddings = None
        return self.embeddings

    @staticmethod
    def is_catalog_enumeration_query(query: str) -> bool:
        """
        Detects if query is an enumeration query requiring exhaustive catalog lookup
        (e.g., 'serum brightening ada apa aja', 'daftar produk acne', 'pilihan cleanser').
        """
        if not query:
            return False
        q_lower = query.lower()
        enum_patterns = [
            r"\b(?:ada\s+apa\s+aja|ada\s+apa\s+saja|ada\s+produk\s+apa|ada\s+treatment\s+apa|produk\s+apa\s+saja|produk\s+apa\s+aja)\b",
            r"\b(?:daftar|list|katalog|pilihan|rekomendasi)\s+(?:produk|treatment|tindakan|item)\b",
            r"\b(?:sebutkan\s+semua\s+produk|ada\s+produk\s+apa|produk\s+apa\s+saja|pilihan\s+(?:serum|toner|krim|cleanser|sabun))\b",
            r"\b(?:opsi\s+produk|varian\s+produk|lini\s+produk)\b"
        ]
        return any(re.search(p, q_lower) for p in enum_patterns)

    @staticmethod
    def extract_form_factor(query: str) -> Optional[str]:
        if not query:
            return None
        q_lower = query.lower()
        mapping = {
            "SERUM": ["serum", "ampoule", "essence"],
            "TONER": ["toner", "micellar"],
            "KRIM": ["krim", "cream", "moisturizer", "pelembap", "gel", "lotion"],
            "CLEANSER": ["cleanser", "facial wash", "face wash", "sabun wajah"],
            "SUNSCREEN": ["sunscreen", "tabir surya", "sunblock"],
            "MASKER": ["masker", "sheet mask", "clay mask"],
            "SHAMPOO": ["shampoo", "sampo", "hair tonic", "scalp serum"]
        }
        for ff, keywords in mapping.items():
            if any(re.search(rf'\b{re.escape(k)}\b', q_lower) for k in keywords):
                return ff
        return None

    @staticmethod
    def extract_indication_keyword(query: str) -> Optional[str]:
        if not query:
            return None
        q_lower = query.lower()
        indications = [
            "brightening", "mencerahkan", "glowing", "kusam",
            "acne", "jerawat", "bruntusan", "komedo",
            "anti aging", "penuaan", "kerutan", "garis halus",
            "barrier", "sensitif", "sensitive", "iritasi",
            "flek", "melasma", "noda hitam", "hyperpigmentation"
        ]
        for ind in indications:
            if ind in q_lower:
                return ind
        return None

    # -------------------------------------------------------------------------
    # CHANNEL 1: Dense HNSW Partial Retrieval (Section 4.4)
    # -------------------------------------------------------------------------
    def retrieve_dense(
        self,
        query: str,
        top_k: int = 10,
        doctor_id: Optional[str] = None,
        doctor_type: Optional[str] = None,
        clinic_id: Optional[str] = None
    ) -> List[CanonicalRetrievalHit]:
        """
        Executes Dense HNSW Vector Search on kb_chunk WHERE is_active = true.
        Activates SET LOCAL hnsw.iterative_scan = 'relaxed_order' for full ACL recall.
        """
        emb_adapter = self._get_embeddings_adapter()
        if not emb_adapter:
            logger.debug("Dense retrieval skipped: No embeddings adapter available.")
            return []

        try:
            # One question is retrieved more than once (the access check retrieves it unfiltered as well):
            # the same text has the same embedding, so it is fetched from the model once
            cache = CanonicalV2Retriever._query_embedding_cache
            query_vector = cache.get(query)
            if query_vector is None:
                query_vector = emb_adapter.embed_query(query)
                if len(cache) >= 512:
                    cache.clear()
                cache[query] = query_vector
            vec_str = "[" + ",".join(str(x) for x in query_vector) + "]"
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return []

        doc_id_val = str(doctor_id or "").strip()
        has_doc_id = bool(doc_id_val)
        is_unrestricted = (doctor_id is None and doctor_type is None and clinic_id is None)
        doc_type_val = str(doctor_type or "ALL").strip()
        clinic_val = str(clinic_id or "ALL").strip()

        sql = text("""
            SELECT c.id, c.version_id, c.evidence_ids, c.retrieval_text, c.knowledge_type,
                   c.authority_level, c.acl_clinics, c.acl_doctor_types, c.acl_doctors,
                   1 - (c.embedding <=> CAST(:vec_str AS vector)) AS similarity,
                   c.domain, c.is_discontinued, c.target_indications
            FROM kb_chunk c
            JOIN knowledge_version kv ON kv.id = c.version_id
            JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE c.is_active = true
              AND k.deleted_at IS NULL
              AND k.status = 'APPROVED'
              AND c.embedding IS NOT NULL
              AND (
                :is_unrestricted
                OR (:has_doc_id AND (:doc_id_val = ANY(c.acl_doctors) OR LOWER(:doc_id_val) = ANY(c.acl_doctors)))
                OR (
                  ('ALL' = ANY(c.acl_doctors) OR 'all' = ANY(c.acl_doctors))
                  AND
                  ('ALL' = ANY(c.acl_doctor_types) OR 'all' = ANY(c.acl_doctor_types) OR :doc_type_val = ANY(c.acl_doctor_types) OR LOWER(:doc_type_val) = ANY(c.acl_doctor_types) OR UPPER(:doc_type_val) = ANY(c.acl_doctor_types))
                  AND
                  ('ALL' = ANY(c.acl_clinics) OR 'all' = ANY(c.acl_clinics) OR :clinic_val = ANY(c.acl_clinics) OR LOWER(:clinic_val) = ANY(c.acl_clinics) OR UPPER(:clinic_val) = ANY(c.acl_clinics))
                )
              )
            ORDER BY c.embedding <=> CAST(:vec_str AS vector) ASC
            LIMIT :top_k;
        """)

        hits: List[CanonicalRetrievalHit] = []
        with self.engine.begin() as conn:
            try:
                conn.execute(text("SET LOCAL hnsw.ef_search = 100;"))
                conn.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order';"))
            except Exception:
                try:
                    conn.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed';"))
                except Exception:
                    pass

            rows = conn.execute(sql, {
                "vec_str": vec_str,
                "is_unrestricted": is_unrestricted,
                "has_doc_id": has_doc_id,
                "doc_id_val": doc_id_val,
                "doc_type_val": doc_type_val,
                "clinic_val": clinic_val,
                "top_k": top_k
            }).fetchall()

            for r in rows:
                sim = float(r[9]) if r[9] is not None else 0.0
                hits.append(CanonicalRetrievalHit(
                    id=str(r[0]),
                    text=str(r[3] or ""),
                    score=sim,
                    channel="dense",
                    authority_level=int(r[5] or 2),
                    knowledge_type=str(r[4] or "PRODUCT"),
                    version_id=str(r[1]) if r[1] else None,
                    metadata={
                        "version_id": str(r[1]) if r[1] else None,
                        "evidence_ids": [str(e) for e in (r[2] or [])],
                        "acl_clinics": r[6] or [],
                        "acl_doctor_types": r[7] or [],
                        "acl_doctors": r[8] or [],
                        "domain": r[10] if len(r) > 10 else None,
                        "clinical_domain": r[10] if len(r) > 10 else None,
                        "is_discontinued": bool(r[11]) if len(r) > 11 else False,
                        "target_indications": r[12] if len(r) > 12 else []
                    }
                ))

        logger.debug(f"Dense HNSW Partial returned {len(hits)} active chunks.")
        return hits

    # -------------------------------------------------------------------------
    # CHANNEL 2: PostgreSQL Native FTS Lexical Retrieval (Section 4.4)
    # -------------------------------------------------------------------------
    @staticmethod
    def _build_indonesian_tsquery(query: str) -> Tuple[str, str]:
        """
        Builds robust PostgreSQL full-text search tsquery expressions:
        1. Strips conversational stopwords / question words (apa, bagaimana, adakah, dll).
        2. Normalizes Indonesian suffixes like '-nya' (e.g. indikasinya -> (indikasinya | indikasi)).
        Returns (conjunctive_tsquery, disjunctive_tsquery).
        """
        clauses = CanonicalV2Retriever._build_tsquery_clauses(query)
        return " & ".join(clauses), " | ".join(clauses)

    @staticmethod
    def _build_tsquery_clauses(query: str) -> List[str]:
        """One tsquery clause per meaningful query word (with its suffix-stripped variant)."""
        if not query:
            return []
        STOP_WORDS = {
            'apa', 'apakah', 'siapa', 'kapan', 'dimana', 'di', 'mana', 'ke', 'kenapa', 'mengapa',
            'bagaimana', 'gimana', 'berapa', 'adakah', 'ada', 'adalah', 'ini', 'itu', 'tersebut',
            'yang', 'dan', 'atau', 'pada', 'dari', 'dalam', 'untuk', 'dengan', 'secara', 'bisa',
            'dapat', 'boleh', 'kah', 'lah', 'pun', 'saja', 'aja', 'dong', 'ya', 'nih', 'sih',
            'tolong', 'mohon', 'kepanjangan', 'kepanjangannya', 'singkatan', 'singkatannya',
            'arti', 'artinya', 'maksud', 'maksudnya', 'definisi', 'definisinya', 'jelaskan',
            'tentang', 'mengenai', 'info', 'informasi', 'rekomendasi', 'berikan', 'tahu', 'ketahui'
        }
        clean = re.sub(r'[^\w\s]', ' ', query.lower())
        words = clean.split()
        meaningful = [w for w in words if w not in STOP_WORDS and len(w) > 1]
        if not meaningful:
            meaningful = [w for w in words if len(w) > 1]

        clauses = []
        for w in meaningful:
            if w.endswith('nya') and len(w) > 4:
                base = w[:-3]
                clauses.append(f"({w} | {base})")
            elif w.endswith('an') and len(w) > 5:
                base = w[:-2]
                clauses.append(f"({w} | {base})")
            else:
                clauses.append(w)
        return clauses

    _vocabulary_cache: Dict[str, Any] = {"words": None, "doc_ratio": {}, "loaded_at": 0.0}
    _query_embedding_cache: Dict[str, List[float]] = {}

    def _corpus_vocabulary(self, ttl_seconds: int = 600) -> List[str]:
        import time as _t
        cache = CanonicalV2Retriever._vocabulary_cache
        if cache["words"] is None or _t.time() - cache["loaded_at"] > ttl_seconds:
            with self.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT word, ndoc FROM ts_stat('SELECT tsv FROM kb_chunk WHERE is_active = true') WHERE length(word) >= 4"
                )).fetchall()
                total = conn.execute(text("SELECT count(*) FROM kb_chunk WHERE is_active = true")).scalar() or 1
            cache["words"] = [r[0] for r in rows]
            cache["doc_ratio"] = {r[0]: r[1] / total for r in rows}
            cache["loaded_at"] = _t.time()
        return cache["words"]

    def resolve_spelling_variants(self, query: str, cutoff: float = 0.8) -> List[str]:
        """
        Maps query words that never occur in the knowledge base to the closest word the knowledge base
        does use (e.g. Indonesian 'esensial' -> catalog 'essential'), so spelling/locale variants of a
        product or treatment name still reach it. Returns only the added corpus words.
        """
        import difflib
        terms = sorted({t for t in re.findall(r'[a-z]+', (query or "").lower()) if len(t) >= 5})
        if not terms:
            return []
        vocab = self._corpus_vocabulary()
        vocab_set = set(vocab)
        additions: List[str] = []
        with self.engine.connect() as conn:
            for term in terms:
                if term in vocab_set:
                    continue
                # Only correct towards names the knowledge base uses (product/treatment/tier names);
                # ordinary words are lowercase in the corpus and never become targets.
                for candidate in difflib.get_close_matches(term, vocab, n=3, cutoff=cutoff):
                    if candidate[0] == term[0] and self._is_proper_name_term(conn, candidate):
                        additions.append(candidate)
                        break
        return additions

    # Indonesian loanword endings and their English source endings ('kontraindikasi' <- 'contraindication').
    _COGNATE_SUFFIXES = (
        ("ikasi", "ication"), ("isasi", "ization"), ("asi", "ation"), ("si", "sion"), ("si", "tion"),
        ("tas", "ty"), ("if", "ive"), ("ur", "ure"), ("ik", "ic"), ("is", "ic"), ("al", "al"),
    )

    @classmethod
    def english_cognate_forms(cls, term: str) -> List[str]:
        """Candidate English spellings of an Indonesian loanword (k->c, loanword suffix -> source suffix)."""
        forms = []
        for stem_variant in dict.fromkeys([term, term.replace("k", "c")]):
            for ind_suffix, eng_suffix in cls._COGNATE_SUFFIXES:
                if stem_variant.endswith(ind_suffix) and len(stem_variant) > len(ind_suffix) + 2:
                    base = stem_variant[: -len(ind_suffix)] + eng_suffix
                    forms.extend([base, base + "s"])
        return [f for f in dict.fromkeys(forms) if f != term]

    def resolve_cognates(self, query: str) -> List[str]:
        """
        Adds the English form of Indonesian loanwords in the query when the knowledge base uses it, so an
        Indonesian question ('kontraindikasi') reaches English documents ('Contraindications'). Only words
        present in the corpus vocabulary are added.
        """
        terms = sorted({t for t in re.findall(r'[a-z]+', (query or "").lower()) if len(t) >= 6})
        if not terms:
            return []
        vocab_set = set(self._corpus_vocabulary())
        additions: List[str] = []
        for term in terms:
            additions.extend(f for f in self.english_cognate_forms(term) if f in vocab_set and f not in additions)
        return additions

    _english_query_cache: Dict[str, List[str]] = {}
    _translation_llm: Any = None

    def rerank_with_llm(self, query: str, hits: List[Dict[str, Any]], timeout_seconds: float = 8.0) -> List[Dict[str, Any]]:
        """
        The retrieved chunks ordered by how directly they answer the question, read by a model from each chunk's
        document title, section and opening text. Fusion scores words and vectors; a model reads that 'Burns and
        scabbing' answers 'komplikasi luka bakar' while a facial protocol table that repeats 'protokol' does not.
        Any failure, or an answer that is not an ordering of the candidates, keeps the fused order.
        """
        if len(hits) < 2:
            return hits
        lines = []
        for i, h in enumerate(hits, 1):
            text_value = h.get("text", "") or ""
            title = re.search(r"Title:\s*([^|\n]+)", text_value)
            section = re.search(r"Section:\s*([^|\n]+)", text_value)
            body = re.split(r"\|\s*Content:\s*", text_value, maxsplit=1)[-1]
            body = re.sub(r"\s+", " ", re.sub(r"[#*|`]+", " ", body)).strip()[:350]
            label = " / ".join(x.group(1).strip() for x in (title, section) if x)
            lines.append(f"[{i}] {label}: {body}")
        prompt = (
            "Order these knowledge base passages by how directly they answer the question, most useful first. "
            "Judge by meaning, across Indonesian and English. Output only the passage numbers, comma-separated, "
            "every number once.\n\n"
            f"Question: {query.strip()}\n\nPassages:\n" + "\n".join(lines)
        )
        try:
            from concurrent.futures import ThreadPoolExecutor
            from app.rag.services.factory import AdapterFactory
            if CanonicalV2Retriever._translation_llm is None:
                CanonicalV2Retriever._translation_llm = AdapterFactory.get_llm_adapter()
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                answer = pool.submit(CanonicalV2Retriever._translation_llm.generate, prompt).result(timeout=timeout_seconds)
            finally:
                pool.shutdown(wait=False)
        except Exception as e:
            logger.debug(f"LLM rerank skipped: {e}")
            return hits
        order = []
        for n in re.findall(r"\d+", answer or ""):
            k = int(n)
            if 1 <= k <= len(hits) and k not in order:
                order.append(k)
        if len(order) < len(hits) // 2:
            return hits
        order += [k for k in range(1, len(hits) + 1) if k not in order]
        logger.info(f"🔀 [LLM Rerank] order {order}")
        return [hits[k - 1] for k in order]

    def english_query_terms(self, query: str, timeout_seconds: float = 3.0, max_doc_ratio: float = 0.15) -> List[str]:
        """
        English words of the query that the knowledge base uses, from an LLM translation of the query.
        Source documents are mixed Indonesian/English ('semua jenis kulit' vs 'All Skin Type'); loanword
        cognates cover only part of that gap. Product names and acronyms are kept as typed. Returns []
        when disabled, unavailable or slow, so retrieval never depends on it.
        """
        if not getattr(settings, "cross_lingual_retrieval_enabled", True) or not (query or "").strip():
            return []
        key = query.strip().lower()
        if key not in CanonicalV2Retriever._english_query_cache:
            from concurrent.futures import ThreadPoolExecutor
            from app.rag.services.factory import AdapterFactory
            prompt = (
                "Translate this clinic search query into English. Keep product, brand, device and treatment "
                "names, codes and acronyms exactly as written. Output only the translated query.\n\n"
                f"Query: {query.strip()}"
            )
            # One adapter for every translation: a new one per query also opens a new connection to the model
            if CanonicalV2Retriever._translation_llm is None:
                CanonicalV2Retriever._translation_llm = AdapterFactory.get_llm_adapter()
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                translated = pool.submit(CanonicalV2Retriever._translation_llm.generate, prompt).result(timeout=timeout_seconds)
            except Exception as tr_err:
                logger.debug(f"Query translation skipped: {tr_err}")
                return []
            finally:
                pool.shutdown(wait=False)
            if len(CanonicalV2Retriever._english_query_cache) > 1000:
                CanonicalV2Retriever._english_query_cache.clear()
            CanonicalV2Retriever._english_query_cache[key] = re.findall(r'[a-z0-9]+', (translated or "").lower())
        query_words = set(re.findall(r'[a-z0-9]+', key))
        self._corpus_vocabulary()
        doc_ratio = CanonicalV2Retriever._vocabulary_cache["doc_ratio"]
        # Words in the corpus but not spread across it. English function words ('what', 'from', 'including') are
        # rare in a mostly Indonesian corpus, so the spread test lets them through: they are dropped by name, or
        # they outweigh the words that carry the question ('burns') in every channel
        return [w for w in dict.fromkeys(CanonicalV2Retriever._english_query_cache[key])
                if len(w) >= 4 and w not in _ENGLISH_FUNCTION_WORDS
                and 0 < doc_ratio.get(w, 0) <= max_doc_ratio and w not in query_words]

    @staticmethod
    def _is_proper_name_term(conn: Any, term: str) -> bool:
        """True when the corpus writes the term capitalized in mid-phrase positions (a name, not a word)."""
        rows = conn.execute(
            text("SELECT retrieval_text FROM kb_chunk WHERE is_active = true AND tsv @@ to_tsquery('simple', :t) LIMIT 40"),
            {"t": term},
        ).fetchall()
        capitalized = lowercase = 0
        # Mid-phrase occurrence: preceded by a word character and a space ('by Volnewmer', 'cara pakai')
        for (txt,) in rows:
            for m in re.finditer(rf'(?<=\w )({re.escape(term)})\b', txt or "", re.IGNORECASE):
                if m.group(1)[0].isupper():
                    capitalized += 1
                else:
                    lowercase += 1
        return capitalized >= 2 and capitalized >= 0.8 * (capitalized + lowercase)

    def find_discriminative_phrases(self, query: str, max_doc_ratio: float = 0.05) -> List[str]:
        """
        Adjacent word pairs of the query that the corpus contains as an exact phrase in only a small
        share of chunks ('atrophic skin' vs 'atrophic scar'). Phrases common to whole tables
        ('kombo treatment') do not discriminate and are left out.
        """
        words = [w for w in re.findall(r'[a-z0-9]+', (query or "").lower())]
        clause_words = set(re.findall(r'[a-z0-9]+', " ".join(self._build_tsquery_clauses(query))))
        pairs = []
        for a, b in zip(words, words[1:]):
            if a in clause_words and b in clause_words and len(a) >= 3 and len(b) >= 3 and not (a.isdigit() or b.isdigit()):
                pairs.append(f"{a} {b}")
        if not pairs:
            return []
        phrases = []
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM kb_chunk WHERE is_active = true")).scalar() or 1
            for phrase in dict.fromkeys(pairs):
                df = conn.execute(
                    text("SELECT count(*) FROM kb_chunk WHERE is_active = true AND tsv @@ phraseto_tsquery('simple', :p)"),
                    {"p": phrase},
                ).scalar() or 0
                if 0 < df <= max_doc_ratio * total:
                    phrases.append(phrase)
        return phrases

    # Entity-channel hits summarize an item; beyond a few they crowd out the document text that holds the answer
    MAX_ENTITY_HITS = 3

    @classmethod
    def cap_entity_hits(cls, hits: List[Any]) -> List[Any]:
        """Keeps ranking order but moves entity-channel hits beyond MAX_ENTITY_HITS behind the content hits."""
        def channel(h):
            return (h.get("channel") if isinstance(h, dict) else getattr(h, "channel", None)) or ""
        kept, overflow, n_entity = [], [], 0
        for h in hits or []:
            if channel(h) == "structured_entity":
                n_entity += 1
                if n_entity > cls.MAX_ENTITY_HITS:
                    overflow.append(h)
                    continue
            kept.append(h)
        return kept + overflow

    @staticmethod
    def ensure_subject_coverage(hits: List[Dict[str, Any]], subjects: List[str], top_k: int, quota: int = 2) -> List[Dict[str, Any]]:
        """
        A question about several named subjects ('DPCT dan Volnewmer', 'bandingkan A dan B') must get
        evidence for each of them. Ranking alone lets the subject with the most matching rows (a 27-row
        table) fill every slot. Each subject named in the query is given up to `quota` of its own best
        hits in the final top-k, taken from the lowest-ranked hits of the over-represented subjects.
        """
        final = list(hits[:top_k])
        if len(subjects) < 2 or not final:
            return final
        patterns = {s: re.compile(rf'\b{re.escape(s)}\b', re.IGNORECASE) for s in subjects}

        def subjects_of(hit):
            text = hit.get("text", "") or ""
            return {s for s, p in patterns.items() if p.search(text)}

        for subj, pat in patterns.items():
            present = sum(1 for h in final if subj in subjects_of(h))
            extra = [h for h in hits[top_k:] if pat.search(h.get("text", "") or "") and h not in final]
            while present < quota and extra:
                counts = {s: sum(1 for h in final if s in subjects_of(h)) for s in subjects}
                # Replace the lowest-ranked hit whose removal keeps every subject at or above its quota
                for i in range(len(final) - 1, -1, -1):
                    covered = subjects_of(final[i])
                    if subj in covered:
                        continue
                    if all(counts[s] - 1 >= quota for s in covered):
                        final[i] = extra.pop(0)
                        present += 1
                        break
                else:
                    break
        return final

    def term_idf_weights(self, terms: List[str]) -> Dict[str, float]:
        """IDF (log N/df) of each word or phrase over active chunks; equal weights when the index is unavailable."""
        import math
        try:
            with self.engine.connect() as conn:
                total = conn.execute(text("SELECT count(*) FROM kb_chunk WHERE is_active = true")).scalar() or 1
                weights = {}
                for term in terms:
                    df = conn.execute(
                        text("SELECT count(*) FROM kb_chunk WHERE is_active = true AND tsv @@ phraseto_tsquery('simple', :p)"),
                        {"p": term},
                    ).scalar() or 0
                    weights[term] = math.log((total + 1) / (df + 1))
                return weights
        except Exception as idf_err:
            logger.debug(f"Term IDF lookup skipped: {idf_err}")
            return {t: 1.0 for t in terms}

    def find_anchor_terms(self, query: str, max_doc_ratio: float = 0.15) -> List[str]:
        """
        Returns the query terms the knowledge base itself writes as proper names (product, treatment,
        device or brand names such as 'Volnewmer', 'Scalperfect', 'DPCT'), regardless of how the user
        typed them. A term qualifies when, in the chunks containing it, it is capitalized in mid-phrase
        positions (header/label starts are ignored) and it is not spread across a large share of the
        corpus. Generic words ('cara', 'shot', 'durasi') are written lowercase mid-sentence and never
        qualify, so no word list is needed.
        """
        _, disj = self._build_indonesian_tsquery(re.sub(r'[\'\"]', '', query or ""))
        terms = sorted({t for t in re.findall(r'[a-z0-9]+', disj) if len(t) >= 3 and not t.isdigit()})
        if not terms:
            return []

        anchors: List[str] = []
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM kb_chunk WHERE is_active = true")).scalar() or 0
            for term in terms:
                df = conn.execute(
                    text("SELECT count(*) FROM kb_chunk WHERE is_active = true AND tsv @@ to_tsquery('simple', :t)"),
                    {"t": term},
                ).scalar() or 0
                if df == 0 or (total and df > max_doc_ratio * total):
                    continue
                if self._is_proper_name_term(conn, term):
                    anchors.append(term)
        return anchors

    @staticmethod
    def _idf_ranked_disjunctive_sql(conn: Any, clauses: List[str]) -> Any:
        """
        Any-word lexical match ranked by the summed rarity (IDF) of the distinct query words a chunk
        contains. Plain ts_rank_cd scores by repetition, so a chunk repeating a common word ('produk')
        outranks the one chunk naming the specific subject ('bibir').
        """
        import math
        total = conn.execute(text("SELECT count(*) FROM kb_chunk WHERE is_active = true")).scalar() or 1
        score_terms = []
        params: Dict[str, Any] = {}
        for i, clause in enumerate(clauses):
            try:
                df = conn.execute(
                    text("SELECT count(*) FROM kb_chunk WHERE is_active = true AND tsv @@ to_tsquery('simple', :q)"),
                    {"q": clause},
                ).scalar() or 0
            except Exception:
                continue
            if df == 0:
                continue
            params[f"c{i}"] = clause
            score_terms.append(f"(CASE WHEN c.tsv @@ to_tsquery('simple', :c{i}) THEN {math.log(total / df):.4f} ELSE 0 END)")
        rank_expr = " + ".join(score_terms) if score_terms else "ts_rank_cd(c.tsv, to_tsquery('simple', :query))"
        return text(f"""
            SELECT c.id, c.version_id, c.evidence_ids, c.retrieval_text, c.knowledge_type,
                   c.authority_level, c.acl_clinics, c.acl_doctor_types, c.acl_doctors,
                   ({rank_expr}) AS lexical_rank,
                   c.domain, c.is_discontinued, c.target_indications
            FROM kb_chunk c
            JOIN knowledge_version kv ON kv.id = c.version_id
            JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE c.is_active = true
              AND k.deleted_at IS NULL
              AND k.status = 'APPROVED'
              AND c.tsv @@ to_tsquery('simple', :query)
              AND (
                :is_unrestricted
                OR (:has_doc_id AND (:doc_id_val = ANY(c.acl_doctors) OR LOWER(:doc_id_val) = ANY(c.acl_doctors)))
                OR (
                  ('ALL' = ANY(c.acl_doctors) OR 'all' = ANY(c.acl_doctors))
                  AND
                  ('ALL' = ANY(c.acl_doctor_types) OR 'all' = ANY(c.acl_doctor_types) OR :doc_type_val = ANY(c.acl_doctor_types) OR LOWER(:doc_type_val) = ANY(c.acl_doctor_types) OR UPPER(:doc_type_val) = ANY(c.acl_doctor_types))
                  AND
                  ('ALL' = ANY(c.acl_clinics) OR 'all' = ANY(c.acl_clinics) OR :clinic_val = ANY(c.acl_clinics) OR LOWER(:clinic_val) = ANY(c.acl_clinics) OR UPPER(:clinic_val) = ANY(c.acl_clinics))
                )
              )
            ORDER BY lexical_rank DESC, c.authority_level ASC, c.id ASC
            LIMIT :top_k;
        """).bindparams(**params)

    def retrieve_fts(
        self,
        query: str,
        top_k: int = 10,
        doctor_id: Optional[str] = None,
        doctor_type: Optional[str] = None,
        clinic_id: Optional[str] = None,
        anchors: Optional[List[str]] = None
    ) -> List[CanonicalRetrievalHit]:
        """
        Executes PostgreSQL Native Full-Text Search on kb_chunk using tsv with smart Indonesian query processing.
        Handles conversational question words, suffix stemming (-nya), and case-insensitive ACLs.
        When the query names a product/treatment (anchors), chunks mentioning it are fetched before the
        any-word disjunctive match, which otherwise favours chunks sharing generic words.
        """
        if not query or not query.strip():
            return []

        doc_id_val = str(doctor_id or "").strip()
        has_doc_id = bool(doc_id_val)
        is_unrestricted = (doctor_id is None and doctor_type is None and clinic_id is None)
        doc_type_val = str(doctor_type or "ALL").strip()
        clinic_val = str(clinic_id or "ALL").strip()

        clean_q = re.sub(r'[\'\"]', '', query.strip())
        if not clean_q:
            return []

        conj_tsquery, disj_tsquery = self._build_indonesian_tsquery(clean_q)

        sql_to_tsquery = text("""
            SELECT c.id, c.version_id, c.evidence_ids, c.retrieval_text, c.knowledge_type,
                   c.authority_level, c.acl_clinics, c.acl_doctor_types, c.acl_doctors,
                   ts_rank_cd(c.tsv, to_tsquery('simple', :query)) AS lexical_rank,
                   c.domain, c.is_discontinued, c.target_indications
            FROM kb_chunk c
            JOIN knowledge_version kv ON kv.id = c.version_id
            JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE c.is_active = true
              AND k.deleted_at IS NULL
              AND k.status = 'APPROVED'
              AND c.tsv @@ to_tsquery('simple', :query)
              AND (
                :is_unrestricted
                OR (:has_doc_id AND (:doc_id_val = ANY(c.acl_doctors) OR LOWER(:doc_id_val) = ANY(c.acl_doctors)))
                OR (
                  ('ALL' = ANY(c.acl_doctors) OR 'all' = ANY(c.acl_doctors))
                  AND
                  ('ALL' = ANY(c.acl_doctor_types) OR 'all' = ANY(c.acl_doctor_types) OR :doc_type_val = ANY(c.acl_doctor_types) OR LOWER(:doc_type_val) = ANY(c.acl_doctor_types) OR UPPER(:doc_type_val) = ANY(c.acl_doctor_types))
                  AND
                  ('ALL' = ANY(c.acl_clinics) OR 'all' = ANY(c.acl_clinics) OR :clinic_val = ANY(c.acl_clinics) OR LOWER(:clinic_val) = ANY(c.acl_clinics) OR UPPER(:clinic_val) = ANY(c.acl_clinics))
                )
              )
            ORDER BY lexical_rank DESC, c.authority_level ASC, c.id ASC
            LIMIT :top_k;
        """)

        sql_plain = text("""
            SELECT c.id, c.version_id, c.evidence_ids, c.retrieval_text, c.knowledge_type,
                   c.authority_level, c.acl_clinics, c.acl_doctor_types, c.acl_doctors,
                   ts_rank_cd(c.tsv, plainto_tsquery('simple', :query)) AS lexical_rank,
                   c.domain, c.is_discontinued, c.target_indications
            FROM kb_chunk c
            JOIN knowledge_version kv ON kv.id = c.version_id
            JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE c.is_active = true
              AND k.deleted_at IS NULL
              AND k.status = 'APPROVED'
              AND c.tsv @@ plainto_tsquery('simple', :query)
              AND (
                :is_unrestricted
                OR (:has_doc_id AND (:doc_id_val = ANY(c.acl_doctors) OR LOWER(:doc_id_val) = ANY(c.acl_doctors)))
                OR (
                  ('ALL' = ANY(c.acl_doctors) OR 'all' = ANY(c.acl_doctors))
                  AND
                  ('ALL' = ANY(c.acl_doctor_types) OR 'all' = ANY(c.acl_doctor_types) OR :doc_type_val = ANY(c.acl_doctor_types) OR LOWER(:doc_type_val) = ANY(c.acl_doctor_types) OR UPPER(:doc_type_val) = ANY(c.acl_doctor_types))
                  AND
                  ('ALL' = ANY(c.acl_clinics) OR 'all' = ANY(c.acl_clinics) OR :clinic_val = ANY(c.acl_clinics) OR LOWER(:clinic_val) = ANY(c.acl_clinics) OR UPPER(:clinic_val) = ANY(c.acl_clinics))
                )
              )
            ORDER BY lexical_rank DESC, c.authority_level ASC, c.id ASC
            LIMIT :top_k;
        """)

        hits: List[CanonicalRetrievalHit] = []
        with self.engine.connect() as conn:
            rows = []
            # 1. Try smart conjunctive tsquery (AND)
            if conj_tsquery:
                try:
                    rows = conn.execute(sql_to_tsquery, {
                        "query": conj_tsquery,
                        "is_unrestricted": is_unrestricted,
                        "has_doc_id": has_doc_id,
                        "doc_id_val": doc_id_val,
                        "doc_type_val": doc_type_val,
                        "clinic_val": clinic_val,
                        "top_k": top_k
                    }).fetchall()
                except Exception as conj_err:
                    logger.debug(f"Conjunctive tsquery '{conj_tsquery}' failed: {conj_err}")
                    rows = []

            # 1b. Chunks naming the product/treatment the query is about, ranked by how well they match
            # the rest of the query (an anchor shared by a whole table must not fill the slots arbitrarily)
            if len(rows) < top_k and anchors:
                try:
                    existing_ids = {r[0] for r in rows}
                    anchor_rows = conn.execute(self._idf_ranked_disjunctive_sql(conn, self._build_tsquery_clauses(clean_q)), {
                        "query": " | ".join(anchors),
                        "is_unrestricted": is_unrestricted,
                        "has_doc_id": has_doc_id,
                        "doc_id_val": doc_id_val,
                        "doc_type_val": doc_type_val,
                        "clinic_val": clinic_val,
                        "top_k": top_k
                    }).fetchall()
                    for ar in anchor_rows:
                        if ar[0] not in existing_ids:
                            rows.append(ar)
                            existing_ids.add(ar[0])
                except Exception as anchor_err:
                    logger.debug(f"Anchor tsquery '{anchors}' failed: {anchor_err}")

            # 2. If conjunctive returned fewer results and disjunctive is available, fetch disjunctive
            if len(rows) < top_k and disj_tsquery and disj_tsquery != conj_tsquery:
                try:
                    existing_ids = {r[0] for r in rows}
                    disj_rows = conn.execute(
                        self._idf_ranked_disjunctive_sql(conn, self._build_tsquery_clauses(clean_q)),
                        {
                            "query": disj_tsquery,
                            "is_unrestricted": is_unrestricted,
                            "has_doc_id": has_doc_id,
                            "doc_id_val": doc_id_val,
                            "doc_type_val": doc_type_val,
                            "clinic_val": clinic_val,
                            "top_k": top_k
                        },
                    ).fetchall()
                    for dr in disj_rows:
                        if dr[0] not in existing_ids:
                            rows.append(dr)
                            existing_ids.add(dr[0])
                except Exception as disj_err:
                    logger.debug(f"Disjunctive tsquery '{disj_tsquery}' failed: {disj_err}")

            # 3. Fallback to standard plainto_tsquery if still empty
            if not rows:
                try:
                    rows = conn.execute(sql_plain, {
                        "query": clean_q,
                        "is_unrestricted": is_unrestricted,
                        "has_doc_id": has_doc_id,
                        "doc_id_val": doc_id_val,
                        "doc_type_val": doc_type_val,
                        "clinic_val": clinic_val,
                        "top_k": top_k
                    }).fetchall()
                except Exception as plain_err:
                    logger.debug(f"Plainto_tsquery '{clean_q}' failed: {plain_err}")
                    rows = []

            for r in rows[:top_k]:
                rank_score = float(r[9]) if r[9] is not None else 0.0
                hits.append(CanonicalRetrievalHit(
                    id=str(r[0]),
                    text=str(r[3] or ""),
                    score=rank_score,
                    channel="fts",
                    authority_level=int(r[5] or 2),
                    knowledge_type=str(r[4] or "PRODUCT"),
                    version_id=str(r[1]) if r[1] else None,
                    metadata={
                        "version_id": str(r[1]) if r[1] else None,
                        "evidence_ids": [str(e) for e in (r[2] or [])],
                        "acl_clinics": r[6] or [],
                        "acl_doctor_types": r[7] or [],
                        "acl_doctors": r[8] or [],
                        "domain": r[10] if len(r) > 10 else None,
                        "clinical_domain": r[10] if len(r) > 10 else None,
                        "is_discontinued": bool(r[11]) if len(r) > 11 else False,
                        "target_indications": r[12] if len(r) > 12 else []
                    }
                ))

        logger.debug(f"PostgreSQL FTS returned {len(hits)} active chunks.")
        return hits

    # -------------------------------------------------------------------------
    # CHANNEL 3: Structured Entity Channel (Section 4.3)
    # -------------------------------------------------------------------------
    def retrieve_structured_entities(
        self,
        query: str,
        top_k: int = 25,
        doctor_id: Optional[str] = None,
        doctor_type: Optional[str] = None,
        clinic_id: Optional[str] = None,
        form_factor: Optional[str] = None,
        indication_filter: Optional[str] = None
    ) -> List[CanonicalRetrievalHit]:
        """
        Executes Structured Entity SQL against active knowledge_version + kb_evidence + kb_entity.
        Provides 100% complete product/treatment listings without vector top-k drop.
        """
        doc_id_val = str(doctor_id or "").strip()
        has_doc_id = bool(doc_id_val)
        is_unrestricted = (doctor_id is None and doctor_type is None and clinic_id is None)
        doc_type_val = str(doctor_type or "ALL").strip().upper()
        clinic_val = str(clinic_id or "ALL").strip().upper()

        ff_target = (form_factor or self.extract_form_factor(query))
        ind_target = (indication_filter or self.extract_indication_keyword(query))

        query_conditions = ["kv.status = 'ACTIVE'"]
        query_conditions.append("(kv.effective_from IS NULL OR kv.effective_from <= CURRENT_DATE)")
        query_conditions.append("(kv.effective_until IS NULL OR kv.effective_until >= CURRENT_DATE)")

        # 3-Level ACL SQL
        acl_clause = """
          (
            :is_unrestricted
            OR (:has_doc_id AND kv.visibility->'doctors' @> jsonb_build_array(CAST(:doc_id_val AS text)))
            OR (
              (kv.visibility->'doctor_types' @> '["ALL"]'::jsonb OR kv.visibility->'doctor_types' @> jsonb_build_array(CAST(:doc_type_val AS text)))
              AND
              (kv.visibility->'clinics' @> '["ALL"]'::jsonb OR kv.visibility->'clinics' @> jsonb_build_array(CAST(:clinic_val AS text)))
            )
          )
        """
        query_conditions.append(acl_clause)

        params: Dict[str, Any] = {
            "is_unrestricted": is_unrestricted,
            "has_doc_id": has_doc_id,
            "doc_id_val": doc_id_val,
            "doc_type_val": doc_type_val,
            "clinic_val": clinic_val,
            "top_k": top_k
        }

        if ff_target:
            query_conditions.append("UPPER(COALESCE(e.form_factor, '')) = :ff_target")
            params["ff_target"] = ff_target.upper()

        if ind_target:
            query_conditions.append("""
                (
                  (ev.attributes->'indications')::text ILIKE :ind_pattern
                  OR ev.body ILIKE :ind_pattern
                  OR e.canonical_name ILIKE :ind_pattern
                )
            """)
            params["ind_pattern"] = f"%{ind_target}%"

        # Direct Entity / Acronym Match (Fase 3: Entity Channel precision)
        acronym_match = re.search(r'\b[A-Z0-9]{2,8}\b', query)
        acronym_str = acronym_match.group(0) if acronym_match else None

        clean_ent_q = re.sub(
            r'^(?:apa|apakah|siapa|berapa|bagaimana|jelaskan|tentang|mengenai|arti|definisi|kepanjangan|singkatan|info|produk|treatment|tindakan)\s+',
            '', query.strip(), flags=re.IGNORECASE
        ).strip("?.!, ")

        if acronym_str:
            query_conditions.append("""
                (
                  :acronym_val = ANY(e.aliases)
                  OR LOWER(:acronym_val) = ANY(e.aliases)
                  OR UPPER(:acronym_val) = ANY(e.aliases)
                  OR e.canonical_name ILIKE :acronym_pattern
                  OR e.normalized_key ILIKE :acronym_pattern
                )
            """)
            params["acronym_val"] = acronym_str
            params["acronym_pattern"] = f"%{acronym_str}%"
        elif len(clean_ent_q) >= 3 and not ff_target and not ind_target:
            query_conditions.append("""
                (
                  e.canonical_name ILIKE :direct_ent_pattern
                  OR :direct_ent_val = ANY(e.aliases)
                  OR LOWER(:direct_ent_val) = ANY(e.aliases)
                )
            """)
            params["direct_ent_val"] = clean_ent_q
            params["direct_ent_pattern"] = f"%{clean_ent_q}%"

        where_clause = " AND ".join(query_conditions)

        sql = text(f"""
            SELECT 
              e.id AS entity_id,
              e.canonical_name,
              e.form_factor,
              e.entity_namespace,
              e.entity_type,
              array_agg(DISTINCT ev.id) AS supporting_evidence_ids,
              jsonb_agg(DISTINCT ev.attributes) AS versioned_attributes,
              array_agg(DISTINCT ev.body) AS supporting_bodies,
              MIN(COALESCE(ev.authority_override, kv.authority_level)) AS authority_level,
              MIN(kv.id::text) AS version_id,
              e.aliases
            FROM kb_entity e
            JOIN kb_evidence_entity ee ON ee.entity_id = e.id
            JOIN kb_evidence ev ON ev.id = ee.evidence_id
            JOIN knowledge_version kv ON kv.id = ev.version_id
            JOIN knowledge k ON k.id = kv.knowledge_id
            WHERE k.deleted_at IS NULL
              AND k.status = 'APPROVED'
              AND {where_clause}
            GROUP BY e.id, e.canonical_name, e.form_factor, e.entity_namespace, e.entity_type, e.aliases
            ORDER BY e.canonical_name ASC
            LIMIT :top_k;
        """)

        hits: List[CanonicalRetrievalHit] = []
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                cname = str(r[1])
                ff = str(r[2] or "-")
                ens = str(r[3] or "ERHA")
                etype = str(r[4] or "PRODUCT")
                ev_ids = [str(x) for x in (r[5] or [])]
                attrs = r[6] if r[6] is not None else []
                bodies = [str(b).strip() for b in (r[7] or []) if b]
                auth = int(r[8] or 2)
                vid = str(r[9]) if r[9] else None
                e_aliases = r[10] or []

                aliases_str = ", ".join(e_aliases) if e_aliases else ""
                alias_part = f" (Aliases / Singkatan: {aliases_str})" if aliases_str else ""
                body_summary = " ".join(bodies[:2])
                hit_text = (
                    f"Katalog {etype} ({ens}): {cname}{alias_part} | Sediaan: {ff} | "
                    f"Fakta Terstruktur: {json.dumps(attrs, ensure_ascii=False)} | "
                    f"Konteks: {body_summary}"
                )

                hits.append(CanonicalRetrievalHit(
                    id=f"entity:{r[0]}",
                    text=hit_text,
                    score=1.0,
                    channel="structured_entity",
                    authority_level=auth,
                    knowledge_type=etype,
                    version_id=vid,
                    metadata={
                        "entity_id": str(r[0]),
                        "canonical_name": cname,
                        "form_factor": ff,
                        "entity_namespace": ens,
                        "supporting_evidence_ids": ev_ids,
                        "versioned_attributes": attrs,
                        "is_structured_catalog": True
                    }
                ))

        logger.debug(f"Structured Entity Channel returned {len(hits)} catalog items.")
        return hits

    # -------------------------------------------------------------------------
    # CHANNEL 4: Relational Clinical Graph Channel (Phase 4)
    # -------------------------------------------------------------------------
    def retrieve_relational_graph(
        self,
        entity_name_or_keyword: str,
        relation_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves clinical relationships from kb_relation joined with kb_entity and kb_evidence (Phase 4).
        Handles: RECOMMENDED_AFTER, CONTRAINDICATED_WITH, COMBINED_WITH, REQUIRES_PREREQUISITE.
        """
        if not entity_name_or_keyword or not entity_name_or_keyword.strip():
            return []

        clean_text = entity_name_or_keyword.strip().lower()
        norm_kw = re.sub(r'[^a-zA-Z0-9]', '', clean_text)

        # 1. Generate candidate terms (full sentence, 2-grams, individual words)
        clean_terms = [clean_text]
        raw_words = [w for w in re.findall(r'[a-zA-Z0-9]+', clean_text) if len(w) >= 3]
        stop_words = {"setelah", "sehabis", "sesudah", "pasca", "tindakan", "treatment", "boleh", "bisa", "pakai", "atau", "adalah", "pantangan", "apakah", "dalam"}
        filt_words = [w for w in raw_words if w not in stop_words]
        for i in range(len(filt_words) - 1):
            clean_terms.append(f"{filt_words[i]} {filt_words[i+1]}")
        clean_terms.extend(filt_words)

        token_patterns = [f"%{t}%" for t in clean_terms if len(t) >= 4]
        if not token_patterns:
            token_patterns = [f"%{norm_kw}%"]

        sql = """
            SELECT 
                r.id,
                r.relation_type,
                r.description,
                r.attributes,
                e1.canonical_name AS source_name,
                e1.entity_type AS source_type,
                e2.canonical_name AS target_name,
                e2.entity_type AS target_type,
                ev.title AS evidence_title,
                ev.body AS evidence_body
            FROM kb_relation r
            JOIN kb_entity e1 ON e1.id = r.source_entity_id
            JOIN kb_entity e2 ON e2.id = r.target_entity_id
            LEFT JOIN kb_evidence ev ON ev.id = r.evidence_id
            WHERE (
                LOWER(e1.canonical_name) LIKE ANY(:token_patterns)
                OR LOWER(e2.canonical_name) LIKE ANY(:token_patterns)
                OR e1.normalized_key LIKE ANY(:token_patterns)
                OR e2.normalized_key LIKE ANY(:token_patterns)
                OR :clean_text ILIKE ('%' || LOWER(e1.canonical_name) || '%')
                OR :clean_text ILIKE ('%' || LOWER(e2.canonical_name) || '%')
                OR EXISTS (
                    SELECT 1 FROM unnest(e1.aliases) a WHERE a = ANY(:clean_terms) OR :clean_text ILIKE ('%' || a || '%')
                )
                OR EXISTS (
                    SELECT 1 FROM unnest(e2.aliases) a WHERE a = ANY(:clean_terms) OR :clean_text ILIKE ('%' || a || '%')
                )
            )
        """
        params: Dict[str, Any] = {
            "token_patterns": token_patterns,
            "clean_terms": clean_terms,
            "clean_text": clean_text
        }

        if relation_types:
            sql += " AND r.relation_type = ANY(:r_types)"
            params["r_types"] = [rt.upper() for rt in relation_types]

        sql += " ORDER BY r.created_at ASC LIMIT 10;"

        results = []
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "relation_type": str(row[1]),
                    "description": str(row[2] or ""),
                    "attributes": row[3] or {},
                    "source_name": str(row[4]),
                    "source_type": str(row[5]),
                    "target_name": str(row[6]),
                    "target_type": str(row[7]),
                    "evidence_title": str(row[8] or ""),
                    "evidence_body": str(row[9] or "")
                })
        return results

    @staticmethod
    def requested_knowledge_type(query: str) -> Optional[str]:
        """'PRODUCT' or 'TREATMENT' when the query explicitly asks for one kind (and not both)."""
        q = (query or "").lower()
        wants_product = bool(re.search(r'\b(?:produk|product|skincare|sediaan)\b', q))
        wants_treatment = bool(re.search(r'\b(?:tindakan|treatment|prosedur|terapi)\b', q))
        if wants_product and not wants_treatment:
            return "PRODUCT"
        if wants_treatment and not wants_product:
            return "TREATMENT"
        return None

    @staticmethod
    def is_relational_query(query: str) -> bool:
        if not query:
            return False
        q_lower = query.lower()
        patterns = [
            r'\b(?:setelah|sehabis|sesudah|pasca)\b.*\b(?:boleh|bisa|pakai|tindakan|treatment|laser|peeling)\b',
            r'\b(?:kombo|kombinasi|combo|gabungan)\b',
            r'\b(?:kontraindikasi|pantangan|dilarang|tidak\s+boleh|larangan)\b',
            r'\b(?:urutan|tahapan|sebelum|syarat)\b.*\b(?:tindakan|treatment)\b'
        ]
        return any(re.search(p, q_lower) for p in patterns)

    # -------------------------------------------------------------------------
    # CHANNEL FUSION: Reciprocal Rank Fusion (RRF) V2 (Section 4)
    # -------------------------------------------------------------------------
    def fuse_and_rank(
        self,
        dense_hits: List[CanonicalRetrievalHit],
        fts_hits: List[CanonicalRetrievalHit],
        entity_hits: List[CanonicalRetrievalHit],
        query: str,
        rrf_k: int = 60,
        anchors: Optional[List[str]] = None,
        phrases: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        is_enum = self.is_catalog_enumeration_query(query)
        q_lower = query.lower()
        exact_indicators = ["sku", "harga", "berapa", "kandungan", "komposisi", "kode", "brand", "netto"]
        is_exact = any(i in q_lower for i in exact_indicators)
        has_acronym_or_term = (
            bool(re.search(r'\b[A-Z0-9]{2,8}\b', query))
            or any(k in q_lower for k in [
                "kepanjangan", "singkatan", "apa arti", "arti dari", "apa itu",
                "definisi", "maksud dari", "penjelasan tentang", "adalah"
            ])
        )

        # Dynamic channel weights
        if is_enum:
            w_dense, w_fts, w_entity = 0.8, 1.2, 2.5
            logger.debug("🎯 [RRF V2] Catalog Enumeration detected -> Boosting Entity Channel (2.5)")
        elif has_acronym_or_term or is_exact:
            w_dense, w_fts, w_entity = 0.7, 1.6, 2.2
            logger.debug("🎯 [RRF V2] Acronym/Term/Exact lookup detected -> Boosting Entity (2.2) and FTS (1.6) Channels")
        else:
            w_dense, w_fts, w_entity = 1.2, 1.0, 0.8
            logger.debug("🩺 [RRF V2] Clinical Q&A detected -> Boosting Dense HNSW Channel (1.2)")

        rrf_scores: Dict[str, Dict[str, Any]] = {}

        # 1. Dense Hits
        for rank, hit in enumerate(dense_hits, start=1):
            key = hit.id
            if key not in rrf_scores:
                rrf_scores[key] = {"hit": hit, "score": 0.0}
            rrf_scores[key]["score"] += w_dense * (1.0 / (rrf_k + rank))

        # 2. FTS Hits
        for rank, hit in enumerate(fts_hits, start=1):
            key = hit.id
            if key not in rrf_scores:
                rrf_scores[key] = {"hit": hit, "score": 0.0}
            rrf_scores[key]["score"] += w_fts * (1.0 / (rrf_k + rank))

        # 3. Entity Channel Hits
        for rank, hit in enumerate(entity_hits, start=1):
            key = hit.id
            if key not in rrf_scores:
                rrf_scores[key] = {"hit": hit, "score": 0.0}
            rrf_scores[key]["score"] += w_entity * (1.0 / (rrf_k + rank))

        # Specific-term coverage boost. The query's specific terms are the names it is about (an acronym
        # typed in caps, or a term the knowledge base writes as a proper name) and its rare exact phrases
        # ('atrophic skin' vs 'atrophic scar'). A chunk gains in proportion to the rarity (IDF) of the
        # specific terms it contains, so the chunk naming 'acneact' outranks chunks that only share
        # 'produk' or 'jenis kulit'. The boost is bounded so it reorders close candidates instead of
        # lifting chunks no channel ranked well.
        query_acronyms = [a.lower() for a in re.findall(r'\b[A-Z0-9]{2,8}\b', query) if a not in ("ALL", "SOP", "PPK")]
        specific_terms = list(dict.fromkeys(query_acronyms + [a.lower() for a in (anchors or [])] + [p.lower() for p in (phrases or [])]))
        if specific_terms:
            weights = self.term_idf_weights(specific_terms)
            total_weight = sum(weights.values()) or 1.0
            for key in rrf_scores:
                hit_text = (rrf_scores[key]["hit"].text or "").lower()
                covered = sum(w for t, w in weights.items() if re.search(rf'\b{re.escape(t)}\b', hit_text))
                rrf_scores[key]["score"] += 0.05 * covered / total_weight
                # A table row whose identity cell is exactly the subject ('| EPA |') is the record asked
                # about; rows naming it inside a compound value ('| EPA + PIH |') rank after it.
                if any(re.search(rf'\|\s*{re.escape(t)}\s*\|', hit_text) for t in specific_terms):
                    rrf_scores[key]["score"] += 0.01

        # Requested-kind boost: 'produk untuk bibir' asks for products, so product chunks outrank
        # treatment rows that merely share the body area (and vice versa for 'tindakan').
        requested_kind = self.requested_knowledge_type(query)
        if requested_kind:
            for key in rrf_scores:
                if str(rrf_scores[key]["hit"].knowledge_type).upper() == requested_kind:
                    rrf_scores[key]["score"] += 0.02

        # Deterministic Sorting: (-rrf_score, authority_level ASC, id ASC)
        sorted_keys = sorted(
            rrf_scores.keys(),
            key=lambda k: (
                -rrf_scores[k]["score"],
                rrf_scores[k]["hit"].authority_level,
                str(k)
            )
        )

        fused: List[Dict[str, Any]] = []
        for key in sorted_keys:
            hit_obj = rrf_scores[key]["hit"]
            hit_obj.rrf_score = rrf_scores[key]["score"]
            hit_obj.score = rrf_scores[key]["score"]
            fused.append(hit_obj.to_dict())

        return fused

    # -------------------------------------------------------------------------
    # MAIN RETRIEVAL ENTRY POINT V2
    # -------------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: int = 8,
        doctor_id: Optional[str] = None,
        doctor_type: Optional[str] = None,
        clinic_id: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete Retrieval Engine V2 Pipeline:
        1. Dense HNSW Partial Retrieval (kb_chunk WHERE is_active = true)
        2. PostgreSQL Native Lexical Search (kb_chunk FTS tsvector @@ plainto_tsquery)
        3. Structured Entity Channel (kb_entity + kb_evidence for catalog inquiries)
        4. Reciprocal Rank Fusion (RRF)
        5. Clinical Conflict Policy Resolution
        """
        meta = filter_metadata or {}
        doc_id = doctor_id or meta.get("doctor_id") or meta.get("user_id") or (meta.get("doctors")[0] if isinstance(meta.get("doctors"), list) and meta.get("doctors") and meta.get("doctors")[0] != "all" else None)
        doc_type = doctor_type or meta.get("doctor_type") or meta.get("role") or (meta.get("doctor_types")[0] if isinstance(meta.get("doctor_types"), list) and meta.get("doctor_types") and meta.get("doctor_types")[0] != "all" else None)
        clinic = clinic_id or meta.get("clinic_id") or meta.get("user_clinic_id") or (meta.get("clinics")[0] if isinstance(meta.get("clinics"), list) and meta.get("clinics") and meta.get("clinics")[0] != "all" else None)

        candidate_k = top_k * 2

        try:
            variants = self.resolve_spelling_variants(query)
            if variants:
                logger.info(f"🔤 [Vocabulary] Query spelling variants resolved to corpus terms: {variants}")
                query = f"{query} {' '.join(variants)}"
        except Exception as vocab_err:
            logger.debug(f"Spelling variant resolution skipped: {vocab_err}")

        original_query = query
        try:
            english = self.english_query_terms(original_query)
            if english:
                logger.info(f"🌐 [Vocabulary] English query terms used by the knowledge base: {english}")
                query = f"{query} {' '.join(english)}"
        except Exception as en_err:
            logger.debug(f"English query terms skipped: {en_err}")

        try:
            cognates = [c for c in self.resolve_cognates(original_query) if c not in query.lower().split()]
            if cognates:
                logger.info(f"🌐 [Vocabulary] English cognates used by the knowledge base: {cognates}")
                query = f"{query} {' '.join(cognates)}"
        except Exception as cognate_err:
            logger.debug(f"Cognate resolution skipped: {cognate_err}")

        try:
            # Names come from what the user typed (translation keeps them as written); added English
            # words are search vocabulary, not subjects of the question.
            anchors = self.find_anchor_terms(original_query)
        except Exception as anchor_err:
            logger.debug(f"Anchor term detection skipped: {anchor_err}")
            anchors = []

        # Run channels. The dense channel waits on the embedding model; the lexical, entity and relation
        # channels only on the database, so they run meanwhile (same query, same results, less waiting).
        from concurrent.futures import ThreadPoolExecutor
        dense_pool = ThreadPoolExecutor(max_workers=1)
        dense_future = dense_pool.submit(self.retrieve_dense, query, candidate_k, doc_id, doc_type, clinic)
        fts_hits = self.retrieve_fts(query, candidate_k, doc_id, doc_type, clinic, anchors=anchors)
        
        # Structured Entity Channel (Universal Entity & Acronym Channel)
        is_enum = self.is_catalog_enumeration_query(query)
        has_acr_or_term = (
            bool(re.search(r'\b[A-Z0-9]{2,8}\b', query))
            or any(k in query.lower() for k in [
                "kepanjangan", "singkatan", "apa arti", "arti dari", "apa itu",
                "definisi", "maksud dari", "penjelasan tentang", "adalah", "biaya", "harga"
            ])
        )
        entity_hits: List[CanonicalRetrievalHit] = []
        if is_enum or has_acr_or_term or self.extract_indication_keyword(query) or self.extract_form_factor(query):
            entity_hits = self.retrieve_structured_entities(query, candidate_k, doc_id, doc_type, clinic)

        # Relational Clinical Graph Channel (Phase 4)
        is_relation = self.is_relational_query(query)
        relations: List[Dict[str, Any]] = []
        if is_relation:
            relations = self.retrieve_relational_graph(query)
            if relations:
                logger.info(f"🔗 [Phase 4 Relation Channel] Retrieved {len(relations)} clinical relations for query '{query}'")

        # Fused Hits via RRF
        try:
            phrases = self.find_discriminative_phrases(query)
        except Exception as phrase_err:
            logger.debug(f"Phrase detection skipped: {phrase_err}")
            phrases = []

        try:
            dense_hits = dense_future.result()
        finally:
            dense_pool.shutdown(wait=False)
        fused = self.fuse_and_rank(dense_hits, fts_hits, entity_hits, query, anchors=anchors, phrases=phrases)

        # Apply Clinical Conflict Policy Matrix
        resolved_hits, conflict_note = ClinicalConflictResolver.resolve(fused, query)

        subjects = list(dict.fromkeys(
            [a.lower() for a in anchors]
            + [a.lower() for a in re.findall(r'\b[A-Z0-9]{2,8}\b', original_query) if a not in ("ALL", "SOP", "PPK")]
        ))
        final_hits = self.ensure_subject_coverage(self.cap_entity_hits(resolved_hits), subjects, top_k)
        if getattr(settings, "llm_rerank_enabled", False):
            keep = max(1, int(getattr(settings, "llm_rerank_keep", 6)))
            final_hits = self.ensure_subject_coverage(self.rerank_with_llm(original_query, final_hits), subjects, keep)
        # The search sentence written at ingestion found the chunk; the answer and its checks read only the document
        from app.rag.services.search_context import strip_search_context
        for h in final_hits:
            if isinstance(h.get("text"), str):
                h["text"] = strip_search_context(h["text"])

        # Build Context String
        context_parts = []
        if conflict_note:
            context_parts.append(f"[RESOLUSI KEBIJAKAN OTORITAS: {conflict_note}]\n")

        # Inject Relational Graph Context at highest clinical precedence
        if relations:
            rel_lines = ["[HUBUNGAN RELASIONAL KLINIS & PROTOKOL KOMBO (Phase 4)]"]
            for r in relations:
                rtype_desc = {
                    "RECOMMENDED_AFTER": "Dianjurkan Dilakukan Setelah",
                    "CONTRAINDICATED_WITH": "KONTRAINDIKASI / DILARANG BERSAMA",
                    "COMBINED_WITH": "Dapat Dikombinasikan Dengan",
                    "REQUIRES_PREREQUISITE": "Memerlukan Syarat Awal"
                }.get(r["relation_type"], r["relation_type"])
                rel_lines.append(f"- {r['source_name']} -> {rtype_desc}: {r['target_name']}")
                if r.get("description"):
                    rel_lines.append(f"  Keterangan Protokol: {r['description']}")
            context_parts.append("\n".join(rel_lines) + "\n")

        for idx, h in enumerate(final_hits, 1):
            auth_name = {1: "SOP Resmi", 2: "Katalog Produk", 3: "Kriteria Klinis", 4: "Jurnal Ilmiah", 5: "Promo"}.get(h.get("authority_level", 2), "Dokumen Resmi")
            context_parts.append(f"--- REFERENSI #{idx} [{auth_name} | Channel: {h.get('channel')}] ---")
            context_parts.append(h.get("text", ""))

        context_str = "\n\n".join(context_parts) if context_parts else "Maaf, saya tidak menemukan informasi resmi yang relevan di basis data."

        return {
            "query": query,
            "results": final_hits,
            "context": context_str,
            "conflict_note": conflict_note,
            "is_catalog_enumeration": is_enum,
            "relations": relations
        }
