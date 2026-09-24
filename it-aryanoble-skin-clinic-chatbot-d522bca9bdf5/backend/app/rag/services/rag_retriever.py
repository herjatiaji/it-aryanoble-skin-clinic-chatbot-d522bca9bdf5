import os
import re
import pickle
import concurrent.futures
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional
from loguru import logger
# pyrefly: ignore [missing-import]
from rank_bm25 import BM25Okapi

from app.rag.services.interfaces import BaseVectorStoreAdapter
from app.rag.config import settings

# Shared persistent worker pool for parallel hybrid dense + sparse retrieval (sized for 1.5 vCPU)
_RETRIEVAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)


# --- Temporal Filtering Helpers ---

def parse_date_safely(date_val: Any) -> Optional[date]:
    """Parses various date string formats safely into a date object."""
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    
    date_str = str(date_val).strip()
    if not date_str or date_str.lower() in ("null", "none", "undefined", ""):
        return None

    # Strip time part if present (e.g. 2026-08-31T00:00:00Z)
    if "t" in date_str.lower():
        date_str = date_str.split("T")[0].split("t")[0]
    if " " in date_str:
        date_str = date_str.split(" ")[0]

    date_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y.%m.%d",
        "%d.%m.%Y"
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def is_chunk_valid_temporal(
    metadata: Dict[str, Any], 
    current_date: Optional[date] = None, 
    include_expired: bool = False
) -> bool:
    """
    Checks if a chunk is currently active and not expired.
    - If include_expired is True: always returns True.
    - If valid_until is present and valid_until < current_date: returns False (expired).
    - If valid_from is present and current_date < valid_from: returns False (future/not yet active).
    """
    if include_expired:
        return True

    if not metadata:
        return True

    today = current_date or datetime.now(timezone.utc).date()

    valid_until_str = metadata.get("valid_until") or metadata.get("expiry_date") or metadata.get("end_date")
    if valid_until_str:
        until_date = parse_date_safely(valid_until_str)
        if until_date and until_date < today:
            return False

    valid_from_str = metadata.get("valid_from") or metadata.get("start_date")
    if valid_from_str:
        from_date = parse_date_safely(valid_from_str)
        if from_date and today < from_date:
            return False

    return True


# --- Local BM25 Index ---
class BM25Index:
    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []       # Original chunks with text and metadata
        self.corpus: List[List[str]] = []            # Tokenized corpus for BM25
        self.bm25: Optional[BM25Okapi] = None         # rank-bm25 object

    def tokenize(self, text: str) -> List[str]:
        """Simple lowercase alphanumeric word tokenization."""
        if not text:
            return []
        return re.findall(r'\w+', text.lower())

    def hydrate_from_db(self) -> bool:
        """
        Self-healing fallback: Hydrates BM25 corpus and metadata directly from
        PostgreSQL DocumentChunk table (SSOT) to prevent index loss/desync.
        """
        try:
            from app.rag.services.vector_store import DocumentChunk
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            engine = create_engine(settings.pg_conn_str, pool_pre_ping=True)
            Session = sessionmaker(bind=engine)
            with Session() as session:
                docs = session.query(DocumentChunk).all()
                if not docs:
                    logger.debug("No DocumentChunks found in DB for BM25 self-healing.")
                    return False
                
                self.chunks = []
                self.corpus = []
                for doc in docs:
                    text_val = doc.text or ""
                    meta_val = doc.metadata_ or {}
                    retrieval_text = meta_val.get("retrieval_text") or text_val
                    self.chunks.append({
                        "text": text_val,
                        "metadata": meta_val
                    })
                    self.corpus.append(self.tokenize(retrieval_text))
                
                if self.corpus:
                    self.bm25 = BM25Okapi(self.corpus)
                    logger.info(f"🔄 BM25 self-healed from PostgreSQL DB: loaded {len(self.chunks)} chunks.")
                    self.save(settings.bm25_index_path)
                    return True
        except Exception as e:
            logger.warning(f"BM25 self-healing from DB note: {e}")
        return False

    def add_chunks(self, new_chunks: List[Dict[str, Any]]):
        """Adds new chunks to the BM25 index, removing old chunks of the same source file first."""
        if not new_chunks:
            return

        # Ensure index is loaded before appending to prevent wiping existing index
        if not self.chunks:
            self.load(settings.bm25_index_path)
            if not self.chunks:
                self.hydrate_from_db()

        # Try to extract the source_file name to clear older entries
        meta0 = new_chunks[0].get("metadata", {}) if isinstance(new_chunks[0], dict) else {}
        source_file = meta0.get("source_file") or meta0.get("knowledge_id") or meta0.get("file_name")
        if source_file:
            logger.debug(f"Clearing old BM25 chunks for identifier: {source_file}")
            self.remove_file_chunks(source_file)

        for chunk in new_chunks:
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            retrieval_text = metadata.get("retrieval_text") or text
            self.chunks.append({
                "text": text,
                "metadata": metadata
            })
            self.corpus.append(self.tokenize(retrieval_text))

        # Re-initialize the BM25 model with the updated corpus
        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus)
            logger.info(f"Re-initialized BM25 index. Total chunks in index: {len(self.chunks)}")
            self.save(settings.bm25_index_path)
        else:
            self.bm25 = None

    def remove_file_chunks(self, source_file: str):
        """Removes all chunks associated with a given source file name or knowledge_id."""
        if not self.chunks:
            self.load(settings.bm25_index_path)
            if not self.chunks:
                self.hydrate_from_db()

        s_clean = str(source_file).strip().lower()
        s_base = s_clean.replace("_parsed.json", "").replace(".json", "").replace(".pdf", "").replace(".xlsx", "").strip()

        indices_to_keep = []
        for i, chunk in enumerate(self.chunks):
            meta = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
            chunk_source = str(meta.get("source_file", "")).strip().lower()
            chunk_kid = str(meta.get("knowledge_id", "")).strip().lower()
            chunk_fname = str(meta.get("file_name", "")).strip().lower()
            chunk_title = str(meta.get("title", "")).strip().lower()

            chunk_identifiers = {
                chunk_source, chunk_kid, chunk_fname, chunk_title,
                chunk_source.replace("_parsed.json", "").replace(".json", "").replace(".pdf", "").replace(".xlsx", "").strip(),
                chunk_fname.replace("_parsed.json", "").replace(".json", "").replace(".pdf", "").replace(".xlsx", "").strip()
            }

            if s_clean not in chunk_identifiers and s_base not in chunk_identifiers:
                indices_to_keep.append(i)

        self.chunks = [self.chunks[i] for i in indices_to_keep]
        self.corpus = [self.corpus[i] for i in indices_to_keep]
        
        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus)
        else:
            self.bm25 = None

    def clear(self):
        """Clears all chunks and corpus, resetting the BM25 index state."""
        self.chunks = []
        self.corpus = []
        self.bm25 = None


    def search(
        self, 
        query: str, 
        top_k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Searches the corpus using BM25.
        Applies metadata filtering and temporal validity before scoring if filter_metadata is provided.
        """
        if not self.chunks:
            return []

        today = datetime.now(timezone.utc).date()

        # Step 1: Filter chunk candidates by metadata and temporal validity
        filtered_indices = []
        for idx, chunk in enumerate(self.chunks):
            meta = chunk.get("metadata", {})
            
            # Check temporal validity for promo/dated documents
            if not is_chunk_valid_temporal(meta, current_date=today, include_expired=include_expired):
                continue

            match = True
            if filter_metadata:
                for k, v in filter_metadata.items():
                    if k in ("clinic_id", "user_clinic_id") and v:
                        user_clinic = str(v).strip().lower()
                        chunk_scope = str(meta.get("knowledge_scope") or "").upper()
                        if chunk_scope in ("GLOBAL", "TENANT"):
                            continue
                        chunk_clinic = str(meta.get("clinic_id") or "").strip().lower()
                        chunk_clinics = meta.get("clinics") or []
                        if isinstance(chunk_clinics, list):
                            c_list = [str(c).strip().lower() for c in chunk_clinics]
                        else:
                            c_list = [str(chunk_clinics).strip().lower()]
                        if chunk_clinic and chunk_clinic != user_clinic and user_clinic not in c_list and "all" not in c_list:
                            match = False
                            break
                    elif k == "excluded_categories" and isinstance(v, list):
                        chunk_cats = meta.get("categories", [])
                        if not isinstance(chunk_cats, list):
                            chunk_cats = [chunk_cats] if chunk_cats else []
                        if any(item in chunk_cats for item in v if item):
                            match = False
                            break
                    elif isinstance(v, list):
                        chunk_val = meta.get(k)
                        # If chunk has no restriction, it matches
                        if chunk_val is None or chunk_val == []:
                            continue
                        if not isinstance(chunk_val, list):
                            chunk_val = [chunk_val]
                        # If chunk explicitly allows everyone ('all'), it matches
                        if "all" in chunk_val:
                            continue
                        # If chunk has specific restrictions, check if user's specific attributes match
                        user_specific_items = [item for item in v if item and item != "all"]
                        if not any(
                            any(str(item).lower() in str(c).lower() or str(c).lower() in str(item).lower() for c in chunk_val)
                            for item in user_specific_items
                        ):
                            match = False
                            break
                    elif meta.get(k) != v:
                        match = False
                        break
            if match:
                filtered_indices.append(idx)

        if not filtered_indices:
            logger.debug(f"No chunks matched metadata filter {filter_metadata} in BM25 index.")
            return []

        tokenized_query = self.tokenize(query)

        # Step 2: Calculate BM25 scores
        # If we have a filter, build a temporary BM25 okapi index of just the filtered candidates
        if (filter_metadata or not include_expired) and len(filtered_indices) < len(self.chunks):
            filtered_corpus = [self.corpus[i] for i in filtered_indices]
            temp_bm25 = BM25Okapi(filtered_corpus)
            scores = temp_bm25.get_scores(tokenized_query)
            
            top_temp_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            results = []
            for idx in top_temp_indices:
                score = scores[idx]
                doc_tokens = filtered_corpus[idx]
                matched_count = sum(1 for t in tokenized_query if t in doc_tokens)
                if score <= 0.0 and matched_count == 0:
                    continue
                orig_idx = filtered_indices[idx]
                effective_score = float(score) if score > 0.0 else (0.1 * matched_count)
                results.append({
                    "text": self.chunks[orig_idx]["text"],
                    "score": effective_score,
                    "metadata": self.chunks[orig_idx]["metadata"]
                })
            return results
        else:
            # Score against global BM25 model
            if not self.bm25:
                return []
            scores = self.bm25.get_scores(tokenized_query)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            results = []
            for idx in top_indices:
                score = scores[idx]
                doc_tokens = self.corpus[idx]
                matched_count = sum(1 for t in tokenized_query if t in doc_tokens)
                if score <= 0.0 and matched_count == 0:
                    continue
                effective_score = float(score) if score > 0.0 else (0.1 * matched_count)
                results.append({
                    "text": self.chunks[idx]["text"],
                    "score": effective_score,
                    "metadata": self.chunks[idx]["metadata"]
                })
            return results

    def save(self, file_path: str = None):
        """Serializes and saves the index to MinIO (SSOT) and local disk fallback atomically."""
        try:
            payload = {
                "chunks": self.chunks,
                "corpus": self.corpus
            }
            pickle_bytes = pickle.dumps(payload)

            # 1. Save to MinIO Object Storage (SSOT)
            try:
                from app.services.storage import _get_client, _docs_bucket
                client = _get_client()
                if client:
                    client.put_object(
                        Bucket=_docs_bucket(),
                        Key="indexes/bm25_index.pkl",
                        Body=pickle_bytes,
                        ContentType="application/octet-stream"
                    )
                    logger.info(f"✅ Successfully saved BM25 index to MinIO '{_docs_bucket()}/indexes/bm25_index.pkl' ({len(self.chunks)} chunks)")
            except Exception as s3_err:
                logger.debug(f"MinIO BM25 save note: {s3_err}")

            # 2. Local fallback if path provided
            if file_path:
                parent_dir = os.path.dirname(file_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                tmp_path = f"{file_path}.tmp"
                with open(tmp_path, "wb") as f:
                    f.write(pickle_bytes)
                os.replace(tmp_path, file_path)
                logger.debug(f"Saved BM25 index locally to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")

    def load(self, file_path: str = None):
        """Loads and deserializes the index from MinIO (SSOT) with local disk fallback."""
        data = None

        # 1. Fast MinIO fetch (SSOT)
        try:
            from app.services.storage import _get_client, _docs_bucket
            client = _get_client()
            if client:
                resp = client.get_object(Bucket=_docs_bucket(), Key="indexes/bm25_index.pkl")
                data = pickle.loads(resp["Body"].read())
                logger.info(f"⚡ Successfully loaded BM25 index from MinIO '{_docs_bucket()}/indexes/bm25_index.pkl'")
        except Exception as s3_err:
            logger.debug(f"MinIO BM25 load note: {s3_err}")

        # 2. Local fallback if not found in MinIO
        if not data and file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    data = pickle.load(f)
                logger.info(f"Loaded BM25 index from local file {file_path}")
            except Exception as e:
                logger.error(f"Failed to load local BM25 index: {e}")

        if data:
            self.chunks = data.get("chunks", [])
            self.corpus = data.get("corpus", [])
            if self.corpus:
                self.bm25 = BM25Okapi(self.corpus)
                logger.info(f"Successfully initialized BM25Okapi with {len(self.chunks)} chunks.")
            else:
                self.bm25 = None
        else:
            logger.info("No existing BM25 index found in MinIO or disk. Starting with clean index.")


# --- Lightweight Deterministic Reranker (CPU & RAM Optimized, Zero PyTorch Overhead) ---
class Reranker:
    def __init__(self, model_name: str = "deterministic-rrf"):
        self.model_name = model_name

    def _ensure_loaded(self):
        """No-op: lightweight reranker requires zero external weights/model downloads."""
        pass

    @property
    def model(self):
        return None

    def rerank(self, query: str, hits: List[Dict[str, Any]], top_n: int = 6) -> List[Dict[str, Any]]:
        """
        Deterministic CPU/RAM-friendly ranking.
        Propagates RRF scores without heavy PyTorch forward pass, saving ~800MB RAM and 2-7s CPU.
        """
        if not hits:
            return []
        out = []
        for hit in hits:
            updated_hit = hit.copy()
            updated_hit["rerank_score"] = float(updated_hit.get("rrf_score", updated_hit.get("score", 0.85)))
            out.append(updated_hit)
        return out[:top_n]


# --- Prompt Context Builder ---
class PromptContextBuilder:
    @staticmethod
    def build_context(hits: List[Dict[str, Any]]) -> str:
        """
        Builds a structured, numbered context string with source file, page, 
        section headers, and promotional period (if any) to pass into the LLM prompt.
        """
        if not hits:
            return "No relevant context found."

        context_parts = []
        total_chars = 0
        MAX_CONTEXT_CHARS = 35000  # Generous budget for multi-page scientific journals and comprehensive Excel tables

        seen_table_rows = set()

        for idx, hit in enumerate(hits, start=1):
            metadata = hit.get("metadata", {})
            source_file = metadata.get("source_file", "unknown")
            product_name = metadata.get("product_name") or metadata.get("title") or metadata.get("treatment_name")
            if not product_name:
                product_name = os.path.splitext(source_file)[0].replace("-", " ").replace("_", " ").strip()

            doc_type = metadata.get("document_type", "GENERAL")
            category = metadata.get("category") or (metadata.get("categories")[0] if metadata.get("categories") else "")
            cat_header = f" | Category: {category}" if category else ""

            rel_prods = metadata.get("related_products", [])
            rel_prods_header = f" | Related Products: {', '.join(rel_prods[:4])}" if rel_prods else ""

            rel_treats = metadata.get("related_treatments", [])
            rel_treats_header = f" | Related Treatments: {', '.join(rel_treats[:4])}" if rel_treats else ""

            indications = metadata.get("indications", [])
            ind_header = f" | Indications: {', '.join(indications[:5])}" if indications else ""

            section = metadata.get("section", "General")
            page = metadata.get("page", 1)
            image_url = metadata.get("image_url") or metadata.get("image")
            if not image_url and metadata.get("image_urls") and isinstance(metadata.get("image_urls"), list) and len(metadata["image_urls"]) > 0:
                image_url = metadata["image_urls"][0]
            text = hit.get("text", "")
            if not image_url:
                img_matches = re.findall(r'!\[.*?\]\(([^\)]+)\)', text)
                if img_matches:
                    image_url = img_matches[0]

            # Deduplicate table rows across chunks to prevent duplicate table outputs
            if "|" in text:
                clean_lines = []
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("|") and stripped.endswith("|"):
                        # Table separator line e.g. |---|---|
                        if re.match(r"^\|[\s\-:|]+\|$", stripped):
                            clean_lines.append(line)
                            continue
                        # Normalize cells for fingerprinting
                        row_fingerprint = "|".join(c.strip().lower() for c in stripped.strip("|").split("|"))
                        if row_fingerprint in seen_table_rows:
                            continue
                        seen_table_rows.add(row_fingerprint)
                        clean_lines.append(line)
                    else:
                        clean_lines.append(line)
                text = "\n".join(clean_lines)

            # Smart chunk trimming: limit individual chunk text to 3,500 chars to preserve full tables and detailed clinical sections
            if len(text) > 3500:
                text = text[:3500] + "\n... [bagian detail dipadatkan]"

            valid_from = metadata.get("valid_from")
            valid_until = metadata.get("valid_until")
            promo_header = ""
            if valid_until or valid_from:
                if valid_from and valid_until:
                    promo_header = f" | Periode Promo: {valid_from} s/d {valid_until}"
                elif valid_until:
                    promo_header = f" | Berlaku Hingga: {valid_until}"

            sku = metadata.get("sku")
            sku_header = f" | SKU: {sku}" if sku else ""
            price = metadata.get("price")
            price_header = f" | Price: {price}" if price else ""

            # Exclude raw filename and internal system IDs from context header to prevent LLM leaking them
            img_header = f" | Image: {image_url}" if image_url else ""
            part = (
                f"[{idx}] Type: {doc_type} | Title: {product_name}{cat_header}{sku_header}{price_header}{ind_header}{promo_header}{img_header}{rel_prods_header}{rel_treats_header} | Section: {section}\n"
                f"Content:\n{text.strip()}"
            )

            # Token Budget Check: Stop adding chunks if total context exceeds token budget
            if total_chars + len(part) > MAX_CONTEXT_CHARS and context_parts:
                logger.info(f"Token Budget Reached: Context capped at {idx-1} chunks ({total_chars} chars, ~{total_chars//4} tokens).")
                break

            context_parts.append(part)
            total_chars += len(part)

        return "\n\n".join(context_parts)


# --- Helper Rank Functions ---
def get_chunk_key(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata", {})
    chunk_id = meta.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    source_file = meta.get("source_file")
    chunk_index = meta.get("chunk_index")
    if source_file is not None and chunk_index is not None:
        return f"{source_file}_{chunk_index}"
    return str(hash(hit.get("text", "")))

# --- Clinical Synonym & Slang Dictionary ---
CLINICAL_SYNONYM_DICTIONARY = {
    # ── Acne, Comedones & Scars ──────────────────────────────
    "bruntusan": ["comedonal acne", "closed comedones", "komedo tertutup", "sumbatan pori"],
    "komedoan": ["comedones", "blackhead", "whitehead", "komedo terbuka tertutup"],
    "komedo terbuka": ["open comedones", "blackhead", "ekstraksi komedo"],
    "komedo tertutup": ["closed comedones", "whitehead", "ekstraksi komedo"],
    "ekstraksi komedo": ["deep acne extraction", "ekstraksi komedo terbuka tertutup", "comedone extraction"],
    "deep acne extraction": ["ekstraksi jerawat", "ekstraksi komedo mendalam", "acne extraction", "deep extraction"],
    "bopeng": ["atrophic acne scar", "acne scar", "bopeng bekas jerawat", "microneedling"],
    "scar": ["atrophic acne scar", "acne scar", "bekas jerawat"],
    "ice pick": ["ice pick scar", "tca cross", "atrophic scar"],
    "boxcar": ["boxcar scar", "subcision", "fractional co2"],
    "rolling scar": ["rolling scar", "subcision", "cannula subcision"],
    "mendem": ["cystic acne", "nodular acne", "jerawat meradang kistik"],
    "jerawat batu": ["cystic acne", "nodul kistik", "inflammatory acne berat"],
    "kebal": ["acne resistant", "keratolytic", "peeling"],
    "badak": ["acne resistant", "keratolytic", "peeling kuat"],
    "merah": ["erythema", "post acne erythema", "PAE", "inflamasi kemerahan"],
    "meradang": ["inflammatory acne", "papule", "pustule", "lesi inflamasi"],
    "totol": ["acne spot gel", "spot treatment", "totol jerawat", "penggunaan lokal"],
    "secara lokal": ["spot treatment", "totol jerawat", "acne spot gel", "penggunaan lokal"],
    "spot gel": ["acne spot gel", "spot treatment", "totol jerawat"],
    
    # ── Pigmentation & Center Indication ────────────────────
    "flek": ["hyperpigmentation", "melasma", "PIH", "flek hitam"],
    "flek hitam": ["melasma", "hyperpigmentation", "PIH", "lentigo"],
    "kusam": ["dull skin", "brightening", "kulit kusam", "regenerasi kulit"],
    "melasma": ["melasma", "hyperpigmentation", "flek hormonal", "brightening center"],
    "melasma ringan": ["melasma ringan", "mild melasma", "brightening center", "pih"],
    "pih": ["post-inflammatory hyperpigmentation", "hiperpigmentasi pasca inflamasi", "noda hitam bekas jerawat"],
    "brightening center": ["brightening center", "erha brightening", "produk pencerah melasma"],
    
    # ── Reverse Ingredient & Active Substances ───────────────
    "ethyl ascorbic acid": ["10% ethyl ascorbic acid", "active glow booster", "vitamin c", "brightening peptides"],
    "10% ethyl ascorbic acid": ["erha truwhite active glow booster", "ethyl ascorbic acid", "brightening peptides"],
    "brightening peptides": ["erha truwhite active glow booster", "peptides pencerah", "ethyl ascorbic acid"],
    "active glow booster": ["erha truwhite active glow booster", "glow booster", "brightening serum"],
    "truwhite": ["erha truwhite", "brightening facial wash", "active glow booster"],
    "acneact": ["erha acneact", "gentle acne moisturizer", "acne spot gel"],
    "gentle acne moisturizer": ["erha acneact gentle acne moisturizer", "pelembap jerawat", "acne moisturizer"],
    
    # ── Pores, Sebum & Cleansers ─────────────────────────────
    "pori gede": ["enlarged pores", "pori pori besar", "seborrhea"],
    "pori besar": ["enlarged pores", "pori pori besar", "sebum oily"],
    "minyakan": ["sebum oily", "kulit berminyak", "excess sebum", "oil control"],
    "sabun": ["facial wash", "cleanser", "pembersih wajah"],
    "sabun muka": ["gentle acne facial wash", "cleanser", "pembersih wajah"],
    "facial wash": ["facial wash", "cleanser", "pembersih wajah", "brightening facial wash"],
    
    # ── Product Attributes (Size, Category, Ingredients) ────
    "ukuran": ["netto", "kemasan", "gram", "ml", "size"],
    "kategori": ["category", "lini produk", "center", "klasifikasi produk"],
    "key ingredients": ["kandungan utama", "bahan aktif", "komposisi utama", "active ingredients"],
    "kandungan": ["ingredients", "bahan aktif", "komposisi", "active substances"],
    
    # ── Creams & Protection ──────────────────────────────────
    "krim malam": ["night cream", "retinol", "moisturizer malam"],
    "krim siang": ["day cream", "sunscreen", "moisturizer pagi"],
    "sunscreen": ["tabir surya", "SPF50", "sun protection", "sunblock"],
    
    # ── Procedures, Duration & Downtime ──────────────────────
    "tahapan": ["tahapan treatment", "prosedur tindakan", "protokol perawatan", "langkah treatment"],
    "tahapan treatment": ["prosedur tindakan", "tahapan perawatan", "langkah treatment", "protokol klinis"],
    "prosedur": ["tahapan tindakan", "protokol perawatan", "prosedur medis", "clinical procedure"],
    "durasi": ["durasi tindakan", "waktu pengerjaan", "treatment duration", "lama pengerjaan"],
    "downtime": ["masa pemulihan", "downtime tindakan", "recovery time", "kemerahan bengkak"],
    
    # ── Hair & Scalp (Rambut & Kulit Kepala) ─────────────────
    "akar rambut": ["folikel rambut", "hair follicle", "hair growth therapy", "kerontokan akar"],
    "rambut rontok": ["hair loss", "telogen effluvium", "alopecia", "hair fall", "hair tonic"],
    "kebotakan": ["alopecia androgenetica", "male pattern baldness", "female pattern hair loss"],
    "benang rambut": ["hair thread lift", "tanam benang rambut", "follicle stimulation"],
    "penempatan benang rambut": ["hair thread lift", "protokol benang kulit kepala"],
    "hair growth": ["hair growth therapy", "hgt", "penumbuh rambut", "redensyl"],
    "ketombe": ["seborrheic dermatitis scalp", "pityriasis capitis", "ketombe membandel", "zinc pyrithione"],
    
    # ── Lasers, EBD & Devices ────────────────────────────────
    "laser pico": ["picosecond laser", "pico laser", "melasma pico", "rejuvenation pico"],
    "laser co2": ["fractional co2 laser", "co2 ablatif", "co2 scar bopeng"],
    "nd yag": ["q-switched nd:yag", "laser flek", "laser pigmentasi"],
    "ipl": ["intense pulsed light", "ipl acne", "ipl brightening"],
    "vbeam": ["v-beam", "pulsed dye laser", "laser vaskular kemerahan"],
    "hifu": ["high intensity focused ultrasound", "pengencangan hifu", "skin tightening"],
    "rf": ["radiofrequency", "microneedling rf", "pengencangan kulit rf"],
    "fluence": ["energi laser", "joule per cm2", "parameter alat"],
    "spot size": ["ukuran spot laser", "diameter beam laser"],
    
    # ── Injections & Skin Boosters ───────────────────────────
    "skin booster": ["salmon dna", "pdrn", "profhilo", "skin booster hyaluronic acid"],
    "salmon dna": ["pdrn", "polydeoxyribonucleotide", "rejuvenasi salmon dna"],
    "profhilo": ["hybrid hyaluronic acid", "bioremodeling", "profhilo anti aging"],
    "botox": ["botulinum toxin", "injeksi botox", "kerutan ekspresi", "masseter botox"],
    "filler": ["dermal filler", "hyaluronic acid filler", "filler bibir", "filler dagu"],
    "oklusi": ["vascular occlusion", "komplikasi filler", "hialuronidase darurat"],
    "hialuronidase": ["hyaluronidase", "penawar filler", "protokol darurat filler"],
    
    # ── Thread Lift (Tanam Benang) ───────────────────────────
    "tanam benang": ["thread lift", "benang pdo", "benang pcl", "lifting benang", "benang kolagen"],
    "tarik benang": ["thread lift", "barbed thread", "foxy eyes thread"],
    
    # ── Skin Barrier, Sensitivity & Safety ───────────────────
    "skin barrier": ["barrier kulit", "ceramide", "panthenol", "transepidermal water loss", "tewl"],
    "rosacea": ["eritema fasial", "kulit sensitif kemerahan", "flushing"],
    "dermatitis": ["dermatitis atopik", "dermatitis kontak", "dermatitis seboroik"],
    "perih": ["stinging", "sensasi terbakar", "iritasi", "barrier rusak"],
    "kerutan": ["wrinkles", "fine lines", "garis halus", "penuaan dini", "anti-aging"],
    "kendur": ["skin laxity", "sagging skin", "elastisitas kulit menurun"],
    "ibu hamil": ["pregnancy safe", "kehamilan", "kontraindikasi hamil", "kategori b/c"],
    "ibu menyusui": ["lactation safe", "menyusui", "busui", "keamanan laktasi"],
    "pantangan": ["aftercare", "edukasi pasien", "kontraindikasi pasca tindakan"],
}

def expand_clinical_query(query: str) -> str:
    """Expands doctor slang and informal bilingual terms with standard clinical vocabulary."""
    if not query:
        return query
    q_lower = query.lower()
    expanded_terms = []
    for term, syns in CLINICAL_SYNONYM_DICTIONARY.items():
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, q_lower):
            expanded_terms.extend(syns[:2])

    if expanded_terms:
        unique_syns = list(dict.fromkeys(expanded_terms))
        return f"{query} {' '.join(unique_syns[:8])}"
    return query


def reciprocal_rank_fusion(
    dense_hits: List[Dict[str, Any]], 
    sparse_hits: List[Dict[str, Any]], 
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0
) -> List[Dict[str, Any]]:
    rrf_scores = {}

    for rank, hit in enumerate(dense_hits, start=1):
        key = get_chunk_key(hit)
        if key not in rrf_scores:
            rrf_scores[key] = {"hit": hit, "score": 0.0}
        rrf_scores[key]["score"] += dense_weight * (1.0 / (rrf_k + rank))

    for rank, hit in enumerate(sparse_hits, start=1):
        key = get_chunk_key(hit)
        if key not in rrf_scores:
            rrf_scores[key] = {"hit": hit, "score": 0.0}
        rrf_scores[key]["score"] += sparse_weight * (1.0 / (rrf_k + rank))

    # Deterministic RRF sorting: sort by score DESC, then stable chunk_id ASC for reproducible tie-breaking
    sorted_keys = sorted(rrf_scores.keys(), key=lambda k: (-rrf_scores[k]["score"], str(k)))

    fused_hits = []
    for key in sorted_keys:
        merged_hit = rrf_scores[key]["hit"].copy()
        merged_hit["rrf_score"] = rrf_scores[key]["score"]
        merged_hit["score"] = rrf_scores[key]["score"]
        fused_hits.append(merged_hit)

    return fused_hits


# --- Hybrid Retriever ---
class HybridRetriever:
    def __init__(
        self, 
        vector_store: BaseVectorStoreAdapter, 
        bm25_index: BM25Index,
        reranker: Optional[Reranker] = None
    ):
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.reranker = reranker

    def retrieve(
        self, 
        query: str, 
        top_k: int = 8, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        rerank_top_n: int = 6,
        confidence_threshold: Optional[float] = None,
        include_expired: bool = False
    ) -> Dict[str, Any]:
        """
        Executes Advanced Retrieval Pipeline:
        1. Clinical Synonym & Slang Expansion
        2. Dynamic Hybrid Router (Alpha Weight Tuning)
        3. Parallel Dense (PGVector) & Sparse (BM25)
        4. Reciprocal Rank Fusion (RRF) with weighted alpha
        5. Temporal Validity Filtering
        6. Cross-Encoder Reranking with Clinical Indication Boost
        """
        # 1. Clinical Query Expansion
        expanded_query = expand_clinical_query(query)
        if expanded_query != query:
            logger.info(f"🔍 [Query Expansion] '{query}' -> '{expanded_query}'")
        else:
            logger.debug(f"Retrieving for query: '{query}' with top_k={top_k}")

        # 2. Dynamic Hybrid Router (Alpha Weight Tuning)
        q_lower = query.lower()
        exact_indicators = ["sku", "harga", "berapa", "kandungan", "komposisi", "nama produk", "kode", "brand", "netto", "isi"]
        is_exact_lookup = any(ind in q_lower for ind in exact_indicators)

        if is_exact_lookup:
            dense_weight = 0.7
            sparse_weight = 1.3
            logger.debug("🎯 [Dynamic Router] Exact lookup detected -> Boosting BM25 sparse weight (1.3)")
        else:
            dense_weight = 1.2
            sparse_weight = 0.8
            logger.debug("🩺 [Dynamic Router] Clinical query detected -> Boosting PGVector dense weight (1.2)")

        candidate_k = top_k * 2

        # Use global persistent singleton executor to avoid per-query thread churn
        future_dense = _RETRIEVAL_EXECUTOR.submit(self.vector_store.search, expanded_query, candidate_k, filter_metadata) if self.vector_store else None
        future_sparse = _RETRIEVAL_EXECUTOR.submit(self.bm25_index.search, expanded_query, candidate_k, filter_metadata, include_expired) if self.bm25_index else None
        
        dense_hits = future_dense.result() if future_dense else []
        sparse_hits = future_sparse.result() if future_sparse else []

        if self.vector_store:
            logger.debug(f"Dense retrieval returned {len(dense_hits)} candidates.")
        if self.bm25_index:
            logger.debug(f"Sparse retrieval returned {len(sparse_hits)} candidates.")
        
        fused_hits = reciprocal_rank_fusion(dense_hits, sparse_hits, dense_weight=dense_weight, sparse_weight=sparse_weight)
        logger.debug(f"RRF Fusion completed. Fused {len(fused_hits)} candidates.")

        # Deduplicate
        seen_texts = set()
        deduplicated_hits = []
        for hit in fused_hits:
            text = hit.get("text", "").strip()
            norm_text = " ".join(text.split()).lower()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                deduplicated_hits.append(hit)
        logger.debug(f"Deduplicated fused hits from {len(fused_hits)} to {len(deduplicated_hits)} unique candidates.")

        # Temporal filtering: exclude expired promotional chunks when include_expired=False
        today = datetime.now(timezone.utc).date()
        active_hits = []
        for hit in deduplicated_hits:
            meta = hit.get("metadata", {})
            if is_chunk_valid_temporal(meta, current_date=today, include_expired=include_expired):
                active_hits.append(hit)
            else:
                p_name = meta.get("product_name") or meta.get("source_file", "unknown")
                vu = meta.get("valid_until") or meta.get("expiry_date")
                logger.info(f"Filtered out expired promotional chunk: '{p_name}' (valid_until: {vu})")

    @staticmethod
    def _extract_target_ingredient(query: str) -> Optional[str]:
        """Extracts active ingredient / chemical component name from query for strict precision filtering."""
        if not query:
            return None
        q_lower = query.lower().strip()

        # 1. Explicit ingredient prefix matches
        ing_match = re.search(r'\b(?:kandungan|mengandung|bahan\s+aktif|komposisi|ingredients?|dengan\s+kandungan|dengan\s+komposisi|berbahan|formula)\s+([a-zA-Z0-9\-\s]{3,30})\b', q_lower)
        if ing_match:
            cand = ing_match.group(1).strip()
            cand = re.sub(r'\b(apa\s+saja|adakah|ada|saja|ya|dong|tolong|di\s+erha|ini|itu|tersebut|yang|bisa|untuk)\b', '', cand).strip()
            if re.match(r'^(dan|atau|serta|pada|dari|dalam|tentang|apakah|bagaimana)\b', cand):
                cand = ""
            if len(cand) >= 3 and cand not in ("produk", "skincare", "obat", "cream", "krim", "serum", "cleanser", "wash"):
                return cand

        # 2. General product ingredient queries: "apakah ada produk betaine", "produk centella", "pilihan betaine"
        prod_match = re.search(r'\b(?:produk|pilihan|rekomendasi|katalog|stok)\s+(?:dengan\s+)?([a-zA-Z0-9\-]{4,25})\b', q_lower)
        if prod_match:
            cand = prod_match.group(1).strip()
            known_ingredients = {
                "centella", "retinol", "ceramide", "niacinamide", "betaine", "salicylic",
                "glycolic", "hyaluronic", "allantoin", "panthenol", "azelaic", "benzoyl",
                "clindamycin", "adapalene", "tretinoin", "squalane", "glycerin", "tocopherol"
            }
            if cand in known_ingredients or any(cand.endswith(suf) for suf in ["ine", "ide", "acid", "ol", "ate", "oil"]):
                return cand

        # 3. Direct chemical ingredient mention in query
        known_ingredients = [
            "10% ethyl ascorbic acid", "ethyl ascorbic acid", "ascorbic acid", "vitamin c", "brightening peptides",
            "centella", "retinol", "ceramide", "niacinamide", "betaine", "salicylic acid", "salicylic",
            "glycolic acid", "glycolic", "hyaluronic acid", "hyaluronic", "allantoin", "panthenol",
            "azelaic acid", "azelaic", "benzoyl peroxide", "benzoyl", "clindamycin", "tea tree", "cica"
        ]
        for ing in known_ingredients:
            if re.search(rf'\b{re.escape(ing)}\b', q_lower):
                return ing

        return None

    @staticmethod
    def _extract_target_form_factor(query: str) -> Optional[str]:
        """
        Extracts clinical product form factor / sediaan from query
        to prevent entity drift & forced substitution in smaller models like gpt-4o-mini.
        """
        if not query:
            return None
        q_lower = query.lower()
        form_factors = {
            "serum": ["serum", "ampoule", "essence"],
            "toner": ["toner", "micellar", "micellar water"],
            "krim": ["krim", "cream", "moisturizer", "pelembap", "lotion", "gel"],
            "cleanser": ["cleanser", "facial wash", "face wash", "sabun wajah", "pembersih wajah"],
            "shampoo": ["shampoo", "sampo", "hair tonic", "scalp serum"],
            "sunscreen": ["sunscreen", "tabir surya", "sunblock"],
            "masker": ["masker", "sheet mask", "clay mask", "peeling"]
        }
        for ff_key, aliases in form_factors.items():
            for alias in aliases:
                if re.search(rf'\b{re.escape(alias)}\b', q_lower):
                    return ff_key
        return None

    @staticmethod
    def _detect_form_factor_intent(query: str) -> Dict[str, Any]:
        """
        Analyzes query for explicit form factor constraints.
        Distinguishes:
        - Single-target constraint: e.g. "serum apa untuk acne", "rekomendasi sunscreen oily"
          -> hard_filter = True, target = 'serum'
        - Comparative / Multi-target: e.g. "perbedaan serum dan toner", "beda krim vs gel"
          -> hard_filter = False (comparative intent must retrieve both)
        - No form factor specified: e.g. "obat untuk bruntusan"
          -> hard_filter = False, target = None
        """
        if not query:
            return {"hard_filter": False, "target": None, "all_detected": []}

        q_lower = query.lower()
        form_factors = {
            "serum": ["serum", "ampoule", "essence"],
            "toner": ["toner", "micellar", "micellar water"],
            "krim": ["krim", "cream", "moisturizer", "pelembap", "lotion", "gel"],
            "cleanser": ["cleanser", "facial wash", "face wash", "sabun wajah", "pembersih wajah"],
            "shampoo": ["shampoo", "sampo", "hair tonic", "scalp serum"],
            "sunscreen": ["sunscreen", "tabir surya", "sunblock"],
            "masker": ["masker", "sheet mask", "clay mask", "peeling"]
        }

        detected = []
        for ff_key, aliases in form_factors.items():
            if any(re.search(rf'\b{re.escape(a)}\b', q_lower) for a in aliases):
                detected.append(ff_key)

        if not detected:
            return {"hard_filter": False, "target": None, "all_detected": []}

        comp_patterns = [
            r'\bperbedaan\b', r'\bbeda\b', r'\bbandingkan\b', r'\bdibandingkan\b',
            r'\bvs\b', r'\bversus\b', r'\bmana\s+yang\s+lebih\b', r'\bkelebihan\s+dan\s+kekurangan\b'
        ]
        is_comparative = any(re.search(p, q_lower) for p in comp_patterns) or len(detected) >= 2

        if is_comparative:
            return {"hard_filter": False, "target": None, "all_detected": detected, "is_comparative": True}

        return {"hard_filter": True, "target": detected[0], "all_detected": detected, "is_comparative": False}

    def retrieve(
        self, 
        query: str, 
        top_k: int = 8, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        rerank_top_n: int = 6,
        confidence_threshold: Optional[float] = None,
        include_expired: bool = False
    ) -> Dict[str, Any]:
        """
        Executes Advanced Retrieval Pipeline:
        1. Clinical Synonym & Slang Expansion
        2. Dynamic Hybrid Router (Alpha Weight Tuning)
        3. Parallel Dense (PGVector) & Sparse (BM25)
        4. Reciprocal Rank Fusion (RRF) with weighted alpha
        5. Temporal Validity Filtering
        6. Cross-Encoder Reranking with Clinical Indication Boost
        """
        # 1. Clinical Query Expansion
        expanded_query = expand_clinical_query(query)
        if expanded_query != query:
            logger.info(f"🔍 [Query Expansion] '{query}' -> '{expanded_query}'")
        else:
            logger.debug(f"Retrieving for query: '{query}' with top_k={top_k}")

        # 2. Dynamic Hybrid Router (Alpha Weight Tuning)
        q_lower = query.lower()
        exact_indicators = ["sku", "harga", "berapa", "kandungan", "komposisi", "nama produk", "kode", "brand", "netto", "isi"]
        is_exact_lookup = any(ind in q_lower for ind in exact_indicators)

        if is_exact_lookup:
            dense_weight = 0.7
            sparse_weight = 1.3
            logger.debug("🎯 [Dynamic Router] Exact lookup detected -> Boosting BM25 sparse weight (1.3)")
        else:
            dense_weight = 1.2
            sparse_weight = 0.8
            logger.debug("🩺 [Dynamic Router] Clinical query detected -> Boosting PGVector dense weight (1.2)")

        candidate_k = top_k * 2

        future_dense = _RETRIEVAL_EXECUTOR.submit(self.vector_store.search, expanded_query, candidate_k, filter_metadata) if self.vector_store else None
        future_sparse = _RETRIEVAL_EXECUTOR.submit(self.bm25_index.search, expanded_query, candidate_k, filter_metadata, include_expired) if self.bm25_index else None
        
        dense_hits = future_dense.result() if future_dense else []
        sparse_hits = future_sparse.result() if future_sparse else []

        if self.vector_store:
            logger.debug(f"Dense retrieval returned {len(dense_hits)} candidates.")
        if self.bm25_index:
            logger.debug(f"Sparse retrieval returned {len(sparse_hits)} candidates.")
        
        fused_hits = reciprocal_rank_fusion(dense_hits, sparse_hits, dense_weight=dense_weight, sparse_weight=sparse_weight)
        logger.debug(f"RRF Fusion completed. Fused {len(fused_hits)} candidates.")

        # Deduplicate using stable chunk_id (Task 8.2)
        seen_keys = set()
        deduplicated_hits = []
        for hit in fused_hits:
            key = get_chunk_key(hit)
            if key not in seen_keys:
                seen_keys.add(key)
                deduplicated_hits.append(hit)
        logger.debug(f"Deduplicated fused hits from {len(fused_hits)} to {len(deduplicated_hits)} unique candidates by chunk_id.")

        # Temporal filtering: exclude expired promotional chunks when include_expired=False
        today = datetime.now(timezone.utc).date()
        active_hits = []
        for hit in deduplicated_hits:
            meta = hit.get("metadata", {})
            if is_chunk_valid_temporal(meta, current_date=today, include_expired=include_expired):
                active_hits.append(hit)
            else:
                p_name = meta.get("product_name") or meta.get("source_file", "unknown")
                vu = meta.get("valid_until") or meta.get("expiry_date")
                logger.info(f"Filtered out expired promotional chunk: '{p_name}' (valid_until: {vu})")

        # Explicit Structured Constraint: Intent-Aware Form Factor Policy (Task 7)
        ff_intent = self._detect_form_factor_intent(query)
        if ff_intent.get("hard_filter"):
            target_ff = ff_intent["target"]
            ff_aliases = {
                "serum": ["serum", "ampoule", "essence"],
                "toner": ["toner", "micellar"],
                "krim": ["krim", "cream", "lotion", "gel", "moisturizer", "pelembap"],
                "cleanser": ["cleanser", "facial wash", "face wash", "sabun wajah"],
                "shampoo": ["shampoo", "sampo", "hair tonic", "scalp serum"],
                "sunscreen": ["sunscreen", "tabir surya", "sunblock"],
                "masker": ["masker", "sheet mask", "clay mask"]
            }.get(target_ff, [target_ff])

            matching_ff_hits = []
            for h in active_hits:
                meta = h.get("metadata", {})
                chunk_ff = (meta.get("form_factor") or "").lower()
                chunk_txt = h.get("text", "").lower()
                if chunk_ff == target_ff or any(re.search(rf'\b{re.escape(a)}\b', chunk_ff) for a in ff_aliases) or any(re.search(rf'\b{re.escape(a)}\b', chunk_txt) for a in ff_aliases):
                    h["_matches_form_factor"] = True
                    matching_ff_hits.append(h)

            if matching_ff_hits:
                logger.info(f"🎯 [Constraint Policy] Hard filter applied: retained {len(matching_ff_hits)} strictly matching chunks for form_factor='{target_ff}'.")
                active_hits = matching_ff_hits
            else:
                logger.info(f"🎯 [Constraint Policy] Hard filter applied: 0 chunks matched form_factor='{target_ff}'. Rejecting substitution to prevent entity drift.")
                active_hits = []

        # Target ingredient extraction for precision filtering & anti-contamination
        target_ingredient = self._extract_target_ingredient(query)

        if target_ingredient and active_hits:
            target_ing_lower = target_ingredient.lower()
            matching_active = []
            for h in active_hits:
                txt = h.get("text", "").lower()
                meta_str = str(h.get("metadata", {})).lower()
                if target_ing_lower in txt or target_ing_lower in meta_str:
                    h["_has_target_ingredient"] = True
                    matching_active.append(h)
                else:
                    h["_has_target_ingredient"] = False
            if matching_active:
                logger.info(f"Target ingredient '{target_ingredient}' matched {len(matching_active)} chunks in pre-filtering.")
                active_hits = matching_active

        # Fast-Path / Exact Match Reranker Bypass
        # Fast-Path / Exact Match Reranker Bypass
        # If active_hits <= 2 or dense/sparse agree on top chunk with high confidence (>= 0.70),
        # we can bypass the heavy PyTorch Cross-Encoder, saving 2-7s CPU latency.
        skip_heavy_reranker = False
        if len(active_hits) <= 2:
            skip_heavy_reranker = True
            logger.info(f"⚡ [Fast-Path Bypass] Only {len(active_hits)} chunk(s) matched. Skipping CPU cross-encoder.")
        elif dense_hits and sparse_hits:
            top_dense_src = dense_hits[0].get("metadata", {}).get("source_file") or dense_hits[0].get("metadata", {}).get("knowledge_id")
            top_sparse_src = sparse_hits[0].get("metadata", {}).get("source_file") or sparse_hits[0].get("metadata", {}).get("knowledge_id")
            top_dense_score = float(dense_hits[0].get("score", 0.0))
            if top_dense_src and top_dense_src == top_sparse_src and top_dense_score >= 0.70:
                skip_heavy_reranker = True
                logger.info(f"⚡ [Fast-Path Bypass] Dense & Sparse top match agreed on '{top_dense_src}' (score: {top_dense_score:.3f}). Skipping CPU cross-encoder.")

        final_hits = active_hits
        if active_hits:
            if not self.reranker or not rerank or skip_heavy_reranker:
                all_reranked = []
                default_conf = float(dense_hits[0].get("score", 0.85)) if dense_hits and isinstance(dense_hits[0], dict) else 0.85
                for h in active_hits:
                    hc = h.copy()
                    hc["rerank_score"] = float(hc.get("rrf_score", hc.get("score", default_conf)))
                    all_reranked.append(hc)
            else:
                all_reranked = self.reranker.rerank(query, active_hits, top_n=len(active_hits))
            
            query_lower = query.lower()
            usage_keywords = ["how to use", "directions", "cara pakai", "cara penggunaan", "aturan pakai", "dosis", "instruksi"]
            procedure_keywords = ["tahapan", "tahap", "prosedur", "protokol", "langkah", "step", "alur", "cara tindakan"]
            ingredients_keywords = ["kandungan", "ingredients", "bahan aktif", "komposisi", "active ingredients"]
            treatment_keywords = ["treatment", "tindakan", "prosedur", "perawatan", "peeling", "ekstraksi", "facial", "terapi", "laser"]
            product_keywords = ["produk", "skincare", "serum", "krim", "cream", "facial wash", "cleanser", "sunscreen", "moisturizer", "sku"]

            is_usage_intent = any(k in query_lower for k in usage_keywords)
            is_procedure_intent = any(k in query_lower for k in procedure_keywords)
            is_ingredients_intent = any(k in query_lower for k in ingredients_keywords)
            is_treatment_intent = any(k in query_lower for k in treatment_keywords)
            is_product_intent = any(k in query_lower for k in product_keywords)

            # Target ingredient extraction for precision filtering & anti-contamination
            target_ingredient = self._extract_target_ingredient(query)

            # Target clinical form factor extraction for entity integrity
            target_form_factor = self._extract_target_form_factor(query)


            # Clinical indication keywords for automatic medical cross-referencing
            clinical_indications_query = []
            indication_kw_map = {
                "acne_vulgaris": ["acne", "jerawat", "papul", "pustul", "meradang", "bruntusan", "acne vulgaris"],
                "comedones": ["komedo", "blackhead", "whitehead", "pori tersumbat"],
                "acne_scar": ["bekas jerawat", "scar", "bopeng", "boxcar", "rolling scar"],
                "sebum_oily": ["berminyak", "oily", "minyak", "sebum"],
                "hyperpigmentation": ["flek", "noda hitam", "dark spot", "melasma", "pih", "hiperpigmentasi"],
                "dull_skin": ["kusam", "mencerahkan", "brightening", "glowing", "warna kulit tidak merata"],
                "aging_wrinkles": ["aging", "penuaan", "kerutan", "garis halus", "keriput"],
                "sensitive_barrier": ["sensitif", "kemerahan", "iritasi", "skin barrier", "inflamasi"]
            }
            for ind_key, kws in indication_kw_map.items():
                if any(kw in query_lower for kw in kws):
                    clinical_indications_query.append(ind_key)

            boosted_hits = []
            for hit in all_reranked:
                updated_hit = hit.copy()
                meta = updated_hit.get("metadata", {})
                section_upper = meta.get("section", "").upper()
                doc_type_upper = str(meta.get("document_type", "")).upper()
                boost = 0.0
                
                if is_usage_intent and any(s in section_upper for s in ["HOW TO USE", "DIRECTIONS", "CARA PAKAI"]):
                    boost += 0.05
                elif is_ingredients_intent and any(s in section_upper for s in ["INGREDIENT", "KANDUNGAN", "KOMPOSISI"]):
                    boost += 0.05

                # Strict ingredient match boost (+0.35)
                if target_ingredient:
                    target_ing_lower = target_ingredient.lower()
                    hit_text_lower = updated_hit.get("text", "").lower()
                    meta_lower = str(meta).lower()
                    if target_ing_lower in hit_text_lower or target_ing_lower in meta_lower:
                        boost += 0.35
                        updated_hit["_has_target_ingredient"] = True
                        logger.debug(f"Target ingredient '{target_ingredient}' found in '{meta.get('product_name')}'. Boosted +0.35")
                    else:
                        updated_hit["_has_target_ingredient"] = False

                if is_procedure_intent and any(s in section_upper for s in ["TAHAPAN", "PROSEDUR", "PROTOKOL", "LANGKAH", "INFORMASI PROSEDUR", "CARA TINDAKAN"]):
                    boost += 0.15
                    
                if is_treatment_intent and (doc_type_upper == "TREATMENT" or any(s in section_upper for s in ["TREATMENT", "PERAWATAN", "TINDAKAN", "PROSEDUR", "PROTOKOL"])):
                    boost += 0.10
                elif is_product_intent and (doc_type_upper == "PRODUCT" or any(s in section_upper for s in ["PRODUCT", "PRODUK", "KATALOG", "SKINCARE"])):
                    boost += 0.05

                # Strict Form Factor (Sediaan) Relevance & Anti-Drift Boost (+0.30)
                if target_form_factor:
                    ff_aliases = {
                        "serum": ["serum", "ampoule", "essence"],
                        "toner": ["toner", "micellar"],
                        "krim": ["krim", "cream", "lotion", "gel", "moisturizer", "pelembap"],
                        "cleanser": ["cleanser", "facial wash", "face wash", "sabun wajah"],
                        "shampoo": ["shampoo", "sampo", "hair tonic", "scalp serum"],
                        "sunscreen": ["sunscreen", "tabir surya", "sunblock"],
                        "masker": ["masker", "sheet mask", "clay mask"]
                    }.get(target_form_factor, [target_form_factor])

                    hit_text_lower = updated_hit.get("text", "").lower()
                    meta_lower = str(meta).lower()
                    has_form_factor = any(re.search(rf'\b{re.escape(a)}\b', hit_text_lower) or re.search(rf'\b{re.escape(a)}\b', meta_lower) for a in ff_aliases)
                    if has_form_factor:
                        boost += 0.30
                        updated_hit["_matches_form_factor"] = True
                        logger.debug(f"Form factor '{target_form_factor}' matched in '{meta.get('product_name')}'. Boosted +0.30")
                    else:
                        updated_hit["_matches_form_factor"] = False

                # Auto-Cross-Reference: Clinical Indication Match Boost (+0.12)
                hit_indications = meta.get("indications", [])
                if clinical_indications_query and hit_indications:
                    shared_inds = set(clinical_indications_query).intersection(set(hit_indications))
                    if shared_inds:
                        boost += 0.12
                        logger.debug(f"Applied clinical indication boost +0.12 for {shared_inds} to '{meta.get('product_name')}'")

                if boost > 0:
                    updated_hit["rerank_score"] = updated_hit.get("rerank_score", 0.0) + boost
                    logger.debug(f"Applied total boost of +{boost:.2f} to section '{section_upper}' / doc_type '{doc_type_upper}' (new score: {updated_hit['rerank_score']:.4f})")
                boosted_hits.append(updated_hit)

            # Document Diversity Selection:
            # Prevents a single document from dominating all top-N slots so interrelated documents (e.g. Treatment + Product + Promo) can both be retrieved
            sorted_by_score = sorted(boosted_hits, key=lambda h: h.get("rerank_score", 0.0), reverse=True)

            # Strict ingredient isolation: if target ingredient is requested and we have matching hits,
            # discard non-matching product hits so unrelated products don't leak into the context
            if target_ingredient:
                matching_hits = [h for h in sorted_by_score if h.get("_has_target_ingredient")]
                if matching_hits:
                    logger.info(f"Target ingredient '{target_ingredient}' matched {len(matching_hits)} chunks. Discarding non-matching products to prevent leakage.")
                    sorted_by_score = matching_hits
            diverse_hits = []
            seen_doc_counts = {}
            deferred_hits = []
            max_per_doc = 3 if is_procedure_intent else 2

            for hit in sorted_by_score:
                meta = hit.get("metadata", {})
                doc_key = meta.get("source_file") or meta.get("knowledge_id") or "unknown"
                count = seen_doc_counts.get(doc_key, 0)
                if count < max_per_doc:
                    diverse_hits.append(hit)
                    seen_doc_counts[doc_key] = count + 1
                else:
                    deferred_hits.append(hit)
                if len(diverse_hits) >= rerank_top_n:
                    break

            # If diverse slots are not full, backfill from deferred hits
            if len(diverse_hits) < rerank_top_n:
                for hit in deferred_hits:
                    diverse_hits.append(hit)
                    if len(diverse_hits) >= rerank_top_n:
                        break

            final_hits = diverse_hits
            logger.debug(f"Reranking and Document Diversity Selection completed. Returned {len(final_hits)} chunks across {len(seen_doc_counts)} documents.")
        else:
            final_hits = active_hits[:top_k]

        threshold = confidence_threshold if confidence_threshold is not None else settings.rerank_confidence_threshold
        if rerank and self.reranker and final_hits:
            max_score = final_hits[0].get("rerank_score", 0.0)
            if max_score < threshold:
                logger.warning(f"Retrieval confidence score {max_score:.4f} is below threshold {threshold:.4f}. Rejecting retrieved context.")
                return {
                    "query": query,
                    "results": [],
                    "context": "Maaf, saya tidak menemukan informasi."
                }

        context_string = PromptContextBuilder.build_context(final_hits)
        if target_form_factor:
            context_string = (
                f"[CATATAN INTEGRITAS SEDIAAN: Pengguna menanyakan produk sediaan '{target_form_factor.upper()}'. "
                f"HANYA rekomendasikan produk yang benar-benar sediaan {target_form_factor.upper()}. "
                f"Jika produk pada referensi adalah sediaan lain (misal: Toner), jelaskan sediaan aslinya secara faktual dan dilarang menyamarkannya sebagai {target_form_factor.upper()}!]\n\n"
                + context_string
            )

        return {
            "query": query,
            "results": final_hits,
            "context": context_string
        }
