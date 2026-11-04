import re
from typing import List, Dict, Any
from loguru import logger
from langchain_experimental.text_splitter import SemanticChunker

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    HuggingFaceEmbeddings = None

try:
    from docling.chunking import HierarchicalChunker
    from docling_core.types.doc import DoclingDocument
except ImportError:
    DoclingDocument = Any
    HierarchicalChunker = None
    logger.warning("docling is not installed. Docling OCR chunking will be unavailable.")

from app.rag.utils.parser import ParseResult

from app.rag.services.embeddings import EmbeddingFactory

def _with_context(meta: dict, context_heading: str) -> dict:
    """
    Records the heading a chunk was prefixed with for standalone retrieval context, so the document's display
    text, assembled from its chunks, can leave out a heading it already shows instead of repeating it.
    """
    if context_heading:
        meta["context_prefix"] = context_heading
    return meta


def join_chunk_texts_for_display(chunks: list) -> str:
    """
    The document text shown to reviewers, rebuilt from chunk dicts: a context heading the chunker prefixed to a
    chunk ('### Indikasi', '## ALOPESIA AREATA') is dropped when that heading is already shown above it.
    """
    out = []
    shown = set()
    for c in chunks:
        if not isinstance(c, dict):
            continue
        t = (c.get("text") or "").strip()
        if not t:
            continue
        ctx = ((c.get("metadata") or {}).get("context_prefix") or "").strip()
        if ctx and t.startswith(ctx) and ctx.lstrip("# ").strip().lower() in shown:
            t = t[len(ctx):].lstrip()
        for line in t.splitlines():
            if line.startswith("#"):
                # Compared by heading text: the same title may be shown at another level
                shown.add(line.lstrip("# ").strip().lower())
        if t:
            out.append(t)
    return "\n\n".join(out)


class CustomChunker:
    def __init__(self, embedding_model_name: str = None):
        logger.info("Initializing Custom Chunker (Structural + Semantic)...")
        
        # 1. Structural Chunker (Docling) — only for OCR path
        if HierarchicalChunker:
            self.structural_chunker = HierarchicalChunker()
        else:
            self.structural_chunker = None
            
        # 2. Semantic Chunker using active EmbeddingFactory
        try:
            logger.info("Loading active EmbeddingAdapter for Semantic Chunking...")
            self.embeddings = EmbeddingFactory.get_embeddings_adapter()
            self.semantic_splitter = SemanticChunker(
                self.embeddings, 
                breakpoint_threshold_type="percentile"
            )
        except Exception as e:
            logger.warning(f"SemanticChunker using fallback: {e}")
            self.semantic_splitter = None

    # =========================================================================
    # KNOWN SECTION HEADERS (shared across both paths)
    # =========================================================================
    KNOWN_SECTIONS = {
        "product name", "brand", "category", "description", "target skin type",
        "active ingredients", "ingredients", "benefits", "indications",
        "contraindications", "how to use", "directions", "warnings", "storage",
        "reference", "references", "product overview", "product information",
        "target patient", "dosage", "composition", "packaging", "shelf life",
        "mechanism of action", "clinical studies", "side effects",
        "precautions", "interactions", "formulation",
        # Indonesian clinical & aesthetic treatment section headers
        "deskripsi", "cocok untuk", "tidak disarankan untuk", "manfaat",
        "persiapan sebelum treatment", "persiapan sebelum tindakan",
        "tahapan treatment", "tahapan prosedur", "informasi prosedur",
        "parameter prosedur", "aftercare", "perawatan setelah tindakan",
        "efek samping", "kandungan peeling", "kandungan", "kategori",
        "kategori treatment", "protokol tindakan", "indikasi"
    }

    # =========================================================================
    # DOCLING PATH: Existing logic for DoclingDocument objects
    # =========================================================================
    def _extract_docling_headings(self, chunk: Any) -> List[str]:
        """Extracts the heading hierarchy from a docling chunk's metadata."""
        headings = []
        if hasattr(chunk, "meta") and hasattr(chunk.meta, "headings"):
            if chunk.meta.headings:
                for h in chunk.meta.headings:
                    headings.append(str(h))
        return headings

    def _extract_docling_page(self, chunk: Any) -> int:
        """Extracts the page number from a docling chunk's metadata."""
        if hasattr(chunk, "meta") and hasattr(chunk.meta, "doc_items") and chunk.meta.doc_items:
            first_item = chunk.meta.doc_items[0]
            if hasattr(first_item, "prov") and first_item.prov:
                prov_item = first_item.prov[0]
                if hasattr(prov_item, "page_no"):
                    return int(prov_item.page_no)
        return 1

    def _chunk_docling_document(self, doc, max_length_for_semantic: int = 500) -> List[Dict]:
        """Original Docling HierarchicalChunker path for OCR-parsed documents."""
        if not self.structural_chunker:
            logger.error("Structural chunker unavailable for Docling document.")
            return []

        logger.info("Applying Docling HierarchicalChunker to Document Tree...")
        try:
            structural_chunks = list(self.structural_chunker.chunk(doc))
        except Exception as e:
            logger.error(f"Failed to chunk document hierarchically: {e}")
            return []
            
        logger.info(f"Created {len(structural_chunks)} structural chunks from Document Tree.")
        
        processed_chunks = []
        current_section = "Root"
        
        for sc in structural_chunks:
            text = sc.text if hasattr(sc, "text") else str(sc)
            text_strip = text.strip()
            if not text_strip:
                continue
                
            headings = self._extract_docling_headings(sc)
            page = self._extract_docling_page(sc)
            
            is_generic_section = (
                text_strip.lower() in self.KNOWN_SECTIONS
                or (
                    len(text_strip) <= 60
                    and not text_strip.endswith('.')
                    and not any(ch in text_strip for ch in ':,;')
                    and not text_strip.isdigit()
                    and (text_strip.isupper() or text_strip.istitle())
                )
            )
            if not headings and is_generic_section:
                current_section = text_strip.upper()
                continue
                
            if headings:
                section = headings[-1].upper()
            else:
                section = current_section
                
            base_metadata = {
                "section": section,
                "page": page
            }
            
            processed_chunks.append({
                "text": text,
                "metadata": base_metadata
            })

        return processed_chunks

    # =========================================================================
    # STRUCTURE-AWARE SUMMARY CHUNKING
    # Splits AI-reviewed Markdown summary by ## headings for precise retrieval.
    # Used at both ingest-time (preview) and approve-time (final indexing).
    # =========================================================================
    def chunk_summary_markdown(
        self,
        summary: str,
        source_file: str = "",
        knowledge_id: str = "",
        batch_id: str = None,
        file_hash: str = "",
        title: str = "",
        doc_type: str = "GENERAL",
        categories: List[str] = None,
        valid_from: str = None,
        valid_until: str = None,
        visibility_settings: Dict = None,
        max_section_chars: int = 1200,
    ) -> List[Dict]:
        """
        Structure-aware chunking of AI-reviewed Markdown summary.

        Strategy:
        1. Split by ## heading boundaries (each product/treatment = 1 logical section)
        2. Tables stay intact within their parent section (never cut mid-row)
        3. If a section exceeds max_section_chars, split at paragraph (\\n\\n)
           boundaries with entity header prepended to each sub-chunk
        4. Extract contextual image_url, sku, price, promo dates per chunk from text
        5. Trivial sections (< 30 chars) are discarded
        """
        if not summary or not summary.strip():
            return []

        categories = categories or []
        visibility_settings = visibility_settings or {
            "clinics": ["all"], "doctor_types": ["all"], "doctors": ["all"]
        }

        # --- Phase 1: Split summary into sections by ## headings ---
        # Use regex to split while preserving the ## header in each section
        raw_sections = re.split(r'(?=\n##\s+)', summary)
        sections = []
        for s in raw_sections:
            s = s.strip()
            if s and len(s) >= 30:
                sections.append(s)

        # If no ## splits found, treat the whole summary as one section
        if not sections:
            sections = [summary.strip()]

        logger.info(f"Structure-aware chunking: split summary into {len(sections)} sections by ## headings.")

        # --- Phase 2: Build chunks from sections ---
        chunks = []
        chunk_idx = 0

        for section_text in sections:
            # Detect entity name from ## header
            h2_match = re.match(r'^##\s+(?:\d+[\.\)]\s*)?(.+)', section_text)
            entity_name = h2_match.group(1).strip() if h2_match else title

            # If section is within target size, keep as 1 self-contained chunk
            if len(section_text) <= max_section_chars:
                chunk_idx += 1
                chunks.append({
                    "text": section_text,
                    "metadata": self._build_chunk_meta(
                        chunk_text=section_text,
                        entity_name=entity_name,
                        chunk_index=chunk_idx,
                        source_file=source_file,
                        knowledge_id=knowledge_id,
                        batch_id=batch_id,
                        file_hash=file_hash,
                        title=title,
                        doc_type=doc_type,
                        categories=categories,
                        valid_from=valid_from,
                        valid_until=valid_until,
                        visibility_settings=visibility_settings,
                    )
                })
            else:
                # --- Phase 3: Recursive paragraph splitting for long sections ---
                paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
                running_parts = []
                running_len = 0

                for para in paragraphs:
                    # Check if adding this paragraph would exceed target
                    if running_len + len(para) > max_section_chars and running_parts:
                        # Flush current accumulator as a chunk
                        chunk_idx += 1
                        sub_text = "\n\n".join(running_parts)
                        # Prepend entity header if not already present
                        if entity_name and not sub_text.startswith("##"):
                            sub_text = f"## {entity_name}\n\n{sub_text}"
                        chunks.append({
                            "text": sub_text,
                            "metadata": self._build_chunk_meta(
                                chunk_text=sub_text,
                                entity_name=entity_name,
                                chunk_index=chunk_idx,
                                source_file=source_file,
                                knowledge_id=knowledge_id,
                                batch_id=batch_id,
                                file_hash=file_hash,
                                title=title,
                                doc_type=doc_type,
                                categories=categories,
                                valid_from=valid_from,
                                valid_until=valid_until,
                                visibility_settings=visibility_settings,
                            )
                        })
                        running_parts = []
                        running_len = 0

                    running_parts.append(para)
                    running_len += len(para)

                # Flush remaining
                if running_parts:
                    chunk_idx += 1
                    sub_text = "\n\n".join(running_parts)
                    if entity_name and not sub_text.startswith("##"):
                        sub_text = f"## {entity_name}\n\n{sub_text}"
                    chunks.append({
                        "text": sub_text,
                        "metadata": self._build_chunk_meta(
                            chunk_text=sub_text,
                            entity_name=entity_name,
                            chunk_index=chunk_idx,
                            source_file=source_file,
                            knowledge_id=knowledge_id,
                            batch_id=batch_id,
                            file_hash=file_hash,
                            title=title,
                            doc_type=doc_type,
                            categories=categories,
                            valid_from=valid_from,
                            valid_until=valid_until,
                            visibility_settings=visibility_settings,
                        )
                    })

        logger.info(f"Structure-aware chunking complete: {len(chunks)} chunks from {len(sections)} sections.")
        return chunks

    def _build_chunk_meta(
        self,
        chunk_text: str,
        entity_name: str,
        chunk_index: int,
        source_file: str = "",
        knowledge_id: str = "",
        batch_id: str = None,
        file_hash: str = "",
        title: str = "",
        doc_type: str = "GENERAL",
        categories: List[str] = None,
        valid_from: str = None,
        valid_until: str = None,
        visibility_settings: Dict = None,
    ) -> Dict[str, Any]:
        """
        Build complete chunk metadata with contextual field extraction from chunk text.
        Extracts: image_url, sku, price, promo dates.
        """
        categories = categories or []
        visibility_settings = visibility_settings or {
            "clinics": ["all"], "doctor_types": ["all"], "doctors": ["all"]
        }

        meta = {
            "source_file": source_file,
            "entity": entity_name,
            "section": entity_name,
            "page": 1,
            "chunk_index": chunk_index,
            "knowledge_id": knowledge_id,
            "batch_id": batch_id,
            "file_hash": file_hash,
            "title": title,
            "document_type": doc_type,
            "clinics": visibility_settings.get("clinics", ["all"]),
            "doctor_types": visibility_settings.get("doctor_types", ["all"]),
            "doctors": visibility_settings.get("doctors", ["all"]),
        }

        # Enforce strict separation: Product != Treatment
        doc_type_upper = (doc_type or "").upper()
        if "TREATMENT" in doc_type_upper or any(w in entity_name.lower() for w in ["treatment", "peeling", "facial", "laser", "tindakan", "sop"]):
            meta["treatment_name"] = entity_name
            meta["product_name"] = None
        else:
            meta["product_name"] = entity_name
            meta["treatment_name"] = None

        # Extract contextual image_url from markdown image tags in chunk text
        if chunk_text:
            img_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
            if img_matches:
                meta["image_url"] = img_matches[0]

            # Extract SKU (colon, equals, or markdown table row)
            sku_match = re.search(
                r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)',
                chunk_text, re.IGNORECASE
            )
            if not sku_match:
                sku_match = re.search(r'\|\s*SKU\s*\|\s*([A-Za-z0-9\-\_]+)\s*\|', chunk_text, re.IGNORECASE)
            if sku_match:
                meta["sku"] = sku_match.group(1).strip()

            # Extract Price/Harga (colon, equals, or markdown table row)
            price_match = re.search(
                r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r]+)',
                chunk_text, re.IGNORECASE
            )
            if not price_match:
                price_match = re.search(r'\|\s*(?:Harga|Price|Harga Normal|Harga Promo)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
            if price_match:
                meta["price"] = price_match.group(1).strip()

            # Extract promo dates (YYYY-MM-DD)
            date_matches = re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b', chunk_text)
            if len(date_matches) >= 2:
                meta["valid_from"] = date_matches[0]
                meta["valid_until"] = date_matches[1]
            elif len(date_matches) == 1:
                meta["valid_until"] = date_matches[0]
            else:
                if valid_from:
                    meta["valid_from"] = valid_from
                if valid_until:
                    meta["valid_until"] = valid_until

        # Categories
        if categories:
            meta["category"] = categories[0]
            meta["categories"] = categories

        return meta

    # =========================================================================
    # FAST PATH: Document -> Section -> Entity/Treatment -> Semantic Chunking
    # =========================================================================
    def _split_large_table(self, table_lines: List[str], max_rows_per_chunk: int = 25) -> List[str]:
        """
        Splits a large markdown table into smaller valid sub-tables,
        ensuring each chunk has the complete table header and delimiter.
        Dynamically adapts chunk row count to table width to prevent oversized chunks.
        """
        actual_lines = [l.strip() for l in table_lines if l.strip().startswith("|")]
        if len(actual_lines) <= 2:
            return ["\n".join(actual_lines)]

        header = actual_lines[0]
        if not header.endswith("|"):
            header = header + " |"

        # Check if line 1 is a valid delimiter
        if len(actual_lines) > 1 and re.match(r'^\|(?:\s*:?-{3,}:?\s*\|)+$', actual_lines[1]):
            delimiter = actual_lines[1]
            data_rows = actual_lines[2:]
        else:
            col_count = max(len(header.split('|')) - 2, 2)
            delimiter = "| " + " | ".join(["---"] * col_count) + " |"
            data_rows = actual_lines[1:]

        # Dynamically scale max_rows_per_chunk based on row character length
        avg_row_len = sum(len(r) for r in data_rows) / max(len(data_rows), 1)
        if avg_row_len > 0:
            target_rows = max(5, int(2200 / max(avg_row_len, 40)))
            eff_max_rows = min(max_rows_per_chunk, target_rows)
        else:
            eff_max_rows = max_rows_per_chunk

        sub_tables = []
        for i in range(0, len(data_rows), eff_max_rows):
            chunk_rows = data_rows[i:i + eff_max_rows]
            sub_table = "\n".join([header, delimiter] + chunk_rows)
            sub_tables.append(sub_table)

        return sub_tables or ["\n".join(actual_lines)]

    def _chunk_fast_pages(self, pages: List[Dict], max_length_for_semantic: int = 600) -> List[Dict]:
        """
        Hierarchical Chunking:
        Document -> Section (H1/H2) -> Entity/Treatment (H3/H4/Numbered) -> Semantic Chunks.
        Ensures 1 chunk = 1 complete informational unit answering 1 doctor intent.
        """
        logger.info(f"⚡ Hierarchical chunking {len(pages)} pages (Document -> Section -> Entity -> Semantic Chunks)...")

        processed_chunks = []
        current_section = "General"
        current_entity = ""

        # Regex patterns for hierarchical boundaries
        section_h1_h2_pattern = re.compile(r"^(?:#{1,2}\s+|(?:Bab|Section|Bagian|Kategori)\s+\d+|Bagan\s+Alur|Alur\s+Diagnosis|Daftar\s+Singkatan)", re.IGNORECASE)
        # Match H3/H4 headers, but NOT bold key-value pairs or numbered list items
        entity_h3_h4_pattern = re.compile(r"^(?:#{3,4}\s+)", re.IGNORECASE)
        bold_entity_pattern = re.compile(r"^\*\*([A-Z0-9][A-Za-z0-9\s\.\-]+)\*\*\s*$", re.IGNORECASE)
        last_sheet_name = None

        for page_data in pages:
            page_num = page_data.get("page", 1)
            page_image_urls = page_data.get("image_urls") or ([page_data.get("image_url")] if page_data.get("image_url") else [])
            page_image_url = page_image_urls[0] if page_image_urls else page_data.get("image_url")
            page_text = page_data.get("text", "").strip()
            if not page_text:
                continue

            # Reset entity context when crossing sheet boundaries to prevent cross-sheet context contamination
            curr_sheet = page_data.get("sheet_name")
            if curr_sheet and curr_sheet != last_sheet_name:
                current_entity = ""
                current_section = f"Sheet: {curr_sheet}"
                last_sheet_name = curr_sheet

            # Reset bibliography/reference section when crossing pages
            if current_section and current_section.lower() in ["daftar pustaka", "references", "bibliography", "pustaka acuan"]:
                current_section = "General"
                current_entity = ""

            lines = page_text.split("\n")
            current_entity_lines = []
            current_table_lines = []
            table_lead = []  # short held-back lines that open the next table
            # Page-level H1 (e.g. the product a catalog page is about); H2 sections below it keep it in
            # their section path so a split-out 'Cara Pakai' chunk still names its product.
            page_h1 = ""

            sheet_name_val = curr_sheet or (current_section.split(":", 1)[1].strip() if current_section and current_section.lower().startswith("sheet:") else None)

            def _build_meta(chunk_text: str = "") -> Dict[str, Any]:
                meta = {
                    "section": current_section,
                    "entity": current_entity,
                    "page": page_num,
                    "sheet_name": sheet_name_val,
                    "is_flattened": page_data.get("is_flattened", False)
                }

                extracted_urls = []
                if chunk_text:
                    found_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
                    for u in found_matches:
                        if u not in extracted_urls:
                            extracted_urls.append(u)

                    # Extract SKU (colon, equals, or markdown table row)
                    sku_match = re.search(r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)', chunk_text, re.IGNORECASE)
                    if not sku_match:
                        sku_match = re.search(r'\|\s*SKU\s*\|\s*([A-Za-z0-9\-\_]+)\s*\|', chunk_text, re.IGNORECASE)
                    if sku_match:
                        meta["sku"] = sku_match.group(1).strip()

                    # Extract Treatment Name vs Product Name (strict separation: Product != Treatment)
                    treat_match = re.search(r'(?:-\s*\*\*(?:Nama Treatment|Treatment|Nama Tindakan|Tindakan)\*\*|\b(?:Nama Treatment|Nama Tindakan)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not treat_match:
                        treat_match = re.search(r'\|\s*(?:Nama Treatment|Treatment|Nama Tindakan|Tindakan)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if treat_match:
                        meta["treatment_name"] = treat_match.group(1).strip()

                    prod_match = re.search(r'(?:-\s*\*\*(?:Nama Produk|Produk|Product Name)\*\*|\b(?:Nama Produk)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not prod_match:
                        prod_match = re.search(r'\|\s*(?:Nama Produk|Produk|Product Name)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if prod_match:
                        meta["product_name"] = prod_match.group(1).strip()
                    elif current_entity and not meta.get("treatment_name"):
                        if any(w in current_section.lower() for w in ["treatment", "tindakan", "prosedur", "sop"]):
                            meta["treatment_name"] = current_entity
                        else:
                            meta["product_name"] = current_entity

                    # Extract Form Factor / Sediaan cleanly without synthetic values
                    t_lower = chunk_text.lower()
                    form_factors = {
                        "serum": ["serum", "ampoule", "essence"],
                        "toner": ["toner", "micellar"],
                        "krim": ["krim", "cream", "lotion", "gel", "moisturizer", "pelembap"],
                        "cleanser": ["cleanser", "facial wash", "face wash", "sabun wajah"],
                        "shampoo": ["shampoo", "sampo", "hair tonic", "scalp serum"],
                        "sunscreen": ["sunscreen", "tabir surya", "sunblock"],
                        "masker": ["masker", "sheet mask", "clay mask"]
                    }
                    for ff_key, aliases in form_factors.items():
                        if any(re.search(rf'\b{re.escape(a)}\b', t_lower) for a in aliases):
                            meta["form_factor"] = ff_key
                            break

                    # Extract Dose / Dosis (colon, equals, or markdown table row)
                    dose_match = re.search(r'(?:-\s*\*\*(?:Dosis|Dose|Aturan Dosis)\*\*|\b(?:Dosis|Dose)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not dose_match:
                        dose_match = re.search(r'\|\s*(?:Dosis|Dose|Aturan Dosis)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if dose_match:
                        meta["dose"] = dose_match.group(1).strip()

                    # Extract Frequency / Frekuensi (colon, equals, or markdown table row)
                    freq_match = re.search(r'(?:-\s*\*\*(?:Frekuensi|Frequency|Cara Pakai)\*\*|\b(?:Frekuensi|Frequency)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not freq_match:
                        freq_match = re.search(r'\|\s*(?:Frekuensi|Frequency|Cara Pakai)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if freq_match:
                        meta["frequency"] = freq_match.group(1).strip()
                    else:
                        daily_freq = re.search(r'\b(\d+\s*x\s*(?:sehari|seminggu|per\s*hari|sehari\s*sekali))\b', chunk_text, re.IGNORECASE)
                        if daily_freq:
                            meta["frequency"] = daily_freq.group(1).strip()

                    # Extract Indication / Indikasi / Manfaat (colon, equals, or markdown table row)
                    ind_match = re.search(r'(?:-\s*\*\*(?:Indikasi|Indication|Manfaat|Benefits)\*\*|\b(?:Indikasi|Indication)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not ind_match:
                        ind_match = re.search(r'\|\s*(?:Indikasi|Indication|Manfaat|Benefits)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if ind_match:
                        meta["indication"] = ind_match.group(1).strip()

                    # Extract Category / Kategori
                    cat_match = re.search(r'(?:-\s*\*\*(?:Kategori|Category)\*\*|\b(?:Kategori|Category)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not cat_match:
                        cat_match = re.search(r'\|\s*(?:Kategori|Category)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if cat_match:
                        meta["category"] = cat_match.group(1).strip()

                    # Extract Case / Kasus
                    case_match = re.search(r'(?:-\s*\*\*(?:Case|Kasus)\*\*|\b(?:Case|Kasus)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not case_match:
                        case_match = re.search(r'\|\s*(?:Case|Kasus)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if case_match:
                        meta["case"] = case_match.group(1).strip()

                    # Extract Grade / Tingkat
                    grade_match = re.search(r'(?:-\s*\*\*(?:Grade|Derajat|Tingkat)\*\*|\b(?:Grade|Derajat)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not grade_match:
                        grade_match = re.search(r'\|\s*(?:Grade|Derajat|Tingkat)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if grade_match:
                        meta["grade"] = grade_match.group(1).strip()

                    # Extract promo validity period (YYYY-MM-DD) per product chunk if present
                    date_matches = re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b', chunk_text)
                    if len(date_matches) >= 2:
                        meta["valid_from"] = date_matches[0]
                        meta["valid_until"] = date_matches[1]
                    elif len(date_matches) == 1:
                        meta["valid_until"] = date_matches[0]

                    # Extract Price / Harga per product chunk if present (colon, equals, or markdown table row)
                    price_match = re.search(r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
                    if not price_match:
                        price_match = re.search(r'\|\s*(?:Harga|Price|Harga Normal|Harga Promo)\s*\|\s*([^|\n\r]+)\s*\|', chunk_text, re.IGNORECASE)
                    if price_match:
                        meta["price"] = price_match.group(1).strip()

                all_urls = list(dict.fromkeys(extracted_urls + page_image_urls))
                if extracted_urls:
                    meta["image_url"] = extracted_urls[0]
                elif all_urls:
                    meta["image_url"] = all_urls[0]
                elif page_image_url:
                    meta["image_url"] = page_image_url
                if all_urls:
                    meta["image_urls"] = all_urls

                # Propagate page-level scoped metadata (context isolation per slide)
                if page_data.get("clinical_domain") or page_data.get("domain"):
                    domain_val = page_data.get("clinical_domain") or page_data.get("domain")
                    meta["clinical_domain"] = domain_val
                    meta["domain"] = domain_val

                if page_data.get("is_discontinued") is not None:
                    # A page-level flag must not leak onto every product chunk of that page (e.g. a
                    # 4-step routine slide where one step is discontinued): the chunk itself must carry the notice.
                    from app.rag.utils.text_hygiene import has_status_notice
                    meta["is_discontinued"] = bool(page_data.get("is_discontinued")) and (
                        not chunk_text or has_status_notice(chunk_text)
                    )

                if page_data.get("target_indications"):
                    meta["target_indications"] = page_data.get("target_indications")
                    if not meta.get("indication"):
                        meta["indication"] = ", ".join(page_data.get("target_indications"))

                if page_data.get("routine_steps"):
                    meta["routine_steps"] = page_data.get("routine_steps")

                if page_data.get("product_entities"):
                    meta["product_entities"] = page_data.get("product_entities")

                if page_data.get("slide_title"):
                    meta["slide_title"] = page_data.get("slide_title")

                return meta

            def flush_entity_block():
                nonlocal current_entity_lines
                if not current_entity_lines:
                    return

                block_text = "\n".join(current_entity_lines).strip()
                if not block_text:
                    current_entity_lines = []
                    return

                # If block is very short (< 80 chars) and has no specific entity, buffer it to combine with next block
                if len(block_text) < 80 and not current_entity:
                    return

                # If entity block is within target size (~600-1200 chars), keep as 1 self-contained unit
                if len(block_text) <= 1200:
                    processed_chunks.append({
                        "text": block_text,
                        "metadata": _build_meta(block_text)
                    })
                else:
                    # Split long entity into logical semantic sub-units (e.g. paragraphs / double newlines)
                    paragraphs = [p.strip() for p in block_text.split("\n\n") if p.strip()]
                    if len(paragraphs) > 1:
                        running_sub = []
                        for p in paragraphs:
                            running_sub.append(p)
                            sub_text = "\n\n".join(running_sub)
                            if len(sub_text) >= 500:
                                # Prepend entity header if not already in sub-text
                                ctx = ""
                                if current_entity and not sub_text.startswith("#"):
                                    ctx = f"### {current_entity}"
                                    sub_text = f"{ctx}\n\n{sub_text}"
                                processed_chunks.append({
                                    "text": sub_text,
                                    "metadata": _with_context(_build_meta(sub_text), ctx)
                                })
                                running_sub = []
                        if running_sub:
                            sub_text = "\n\n".join(running_sub)
                            ctx = ""
                            if current_entity and not sub_text.startswith("#"):
                                ctx = f"### {current_entity}"
                                sub_text = f"{ctx}\n\n{sub_text}"
                            processed_chunks.append({
                                "text": sub_text,
                                "metadata": _with_context(_build_meta(sub_text), ctx)
                            })
                    else:
                        processed_chunks.append({
                            "text": block_text,
                            "metadata": _build_meta(block_text)
                        })

                current_entity_lines = []

            def flush_table_block():
                nonlocal current_table_lines
                if not current_table_lines:
                    return

                is_banned_sec = current_section and current_section.lower() in ["general", "daftar pustaka", "references", "bibliography", "pustaka acuan"]
                prefix = f"## {current_section}\n\n" if (current_section and not is_banned_sec) else ""
                lead = "\n\n".join(table_lead).strip()
                table_lead[:] = []

                if len(current_table_lines) > 10:
                    sub_tables = self._split_large_table(current_table_lines, max_rows_per_chunk=25)
                    for si, tbl in enumerate(sub_tables):
                        if si == 0 and lead:
                            tbl = f"{lead}\n\n{tbl}"
                        added = bool(prefix and not tbl.startswith("#"))
                        full_tbl = f"{prefix}{tbl}" if added else tbl
                        clean_tbl = f"\n\n{full_tbl.strip()}\n\n"
                        processed_chunks.append({
                            "text": clean_tbl.strip(),
                            "metadata": _with_context(_build_meta(clean_tbl.strip()), prefix.strip() if added else "")
                        })
                else:
                    table_txt = "\n".join(current_table_lines)
                    if lead:
                        table_txt = f"{lead}\n\n{table_txt}"
                    added = bool(prefix and not table_txt.startswith("#"))
                    full_tbl = f"{prefix}{table_txt}" if added else table_txt
                    clean_tbl = f"\n\n{full_tbl.strip()}\n\n"
                    processed_chunks.append({
                        "text": clean_tbl.strip(),
                        "metadata": _with_context(_build_meta(clean_tbl.strip()), prefix.strip() if added else "")
                    })
                current_table_lines = []

            for line in lines:
                line_strip = line.strip()
                if not line_strip:
                    if current_table_lines:
                        flush_table_block()
                    elif current_entity_lines and current_entity_lines[-1] != "":
                        # Keep the paragraph boundary: without it the paragraphs and stacked short lines of
                        # a block run together into one paragraph when the chunk text is normalized again.
                        current_entity_lines.append("")
                    continue

                # 1. Detect Markdown Table Row
                is_table_row = line_strip.startswith("|") and line_strip.endswith("|")
                if is_table_row:
                    if current_entity_lines:
                        flush_entity_block()
                    if current_entity_lines and not current_table_lines:
                        # A short block held back to join the next one (a lone heading such as the disease
                        # title) opens the table that follows; held back further it would surface after it.
                        table_lead[:] = [l for l in current_entity_lines if l]
                        current_entity_lines = []
                    current_table_lines.append(line_strip)
                    continue
                else:
                    if current_table_lines:
                        flush_table_block()

                # 2. Detect Major Section (H1 / H2 / 1. Title)
                if section_h1_h2_pattern.match(line_strip) and not is_table_row:
                    flush_entity_block()
                    clean_sec = line_strip.lstrip("#: ").strip()
                    if clean_sec:
                        if re.match(r"^#\s", line_strip):
                            page_h1 = clean_sec
                            current_section = clean_sec
                        elif re.match(r"^##\s", line_strip) and page_h1 and clean_sec != page_h1:
                            current_section = f"{page_h1} / {clean_sec}"
                        else:
                            current_section = clean_sec
                        current_entity = ""
                    current_entity_lines.append(line_strip)
                    continue

                # 3. Detect Entity / Treatment / Product (H3 / H4 / 1.1 Item / **StandaloneBoldTitle**)
                bold_match = bold_entity_pattern.match(line_strip)
                if (entity_h3_h4_pattern.match(line_strip) or bold_match) and not is_table_row:
                    flush_entity_block()
                    if bold_match:
                        clean_ent = bold_match.group(1).strip()
                    else:
                        clean_ent = re.sub(r'^[#\s]+', '', line_strip).strip()
                        clean_ent = re.sub(r'^\d+\.\d+\s*', '', clean_ent).strip()
                    if clean_ent:
                        current_entity = clean_ent
                    current_entity_lines.append(line_strip)
                    continue

                # 4. Regular content line / bullet point
                current_entity_lines.append(line_strip)

            # Flush remaining lines
            flush_entity_block()
            flush_table_block()

        logger.info(f"Hierarchical chunking complete: generated {len(processed_chunks)} granular, entity-aware chunks.")
        return processed_chunks

    # =========================================================================
    # PUBLIC API: Unified entry point
    # =========================================================================
    def chunk_document(self, parse_result, max_length_for_semantic: int = 600) -> List[Dict]:
        """
        Unified chunking entry point. Accepts either:
        - ParseResult (from new smart parser)
        - DoclingDocument (backward compatibility)
        
        Automatically routes to hierarchical chunking.
        """
        if isinstance(parse_result, ParseResult):
            if parse_result.is_fast:
                return self._chunk_fast_pages(parse_result.pages, max_length_for_semantic)
            elif parse_result.is_docling and parse_result.docling_doc:
                return self._chunk_docling_document(parse_result.docling_doc, max_length_for_semantic)
            else:
                logger.error("ParseResult has no usable data.")
                return []

        if DoclingDocument and isinstance(parse_result, DoclingDocument):
            return self._chunk_docling_document(parse_result, max_length_for_semantic)

        logger.warning(f"Unknown parse_result type: {type(parse_result)}. Attempting Docling chunking.")
        return self._chunk_docling_document(parse_result, max_length_for_semantic)


# ===========================================================================
# Standalone function: chunk_summary_markdown
# Does NOT require CustomChunker init (no embedding model needed).
# Can be imported directly: from app.rag.utils.chunker import chunk_summary_markdown
# ===========================================================================
def chunk_summary_markdown(
    summary: str,
    source_file: str = "",
    knowledge_id: str = "",
    batch_id: str = None,
    file_hash: str = "",
    title: str = "",
    doc_type: str = "GENERAL",
    categories: list = None,
    valid_from: str = None,
    valid_until: str = None,
    visibility_settings: dict = None,
    max_section_chars: int = 1200,
) -> list:
    """
    Standalone structure-aware chunking of AI-reviewed Markdown summary.
    Delegates to CustomChunker._build_chunk_meta for metadata extraction.
    No embedding model required.
    """
    if not summary or not summary.strip():
        return []

    categories = categories or []
    visibility_settings = visibility_settings or {
        "clinics": ["all"], "doctor_types": ["all"], "doctors": ["all"]
    }

    # Split summary into sections hierarchically by ## and ### headings (Tahap C)
    raw_sections = re.split(r'(?=\n#{2,3}\s+)', summary)
    sections = [s.strip() for s in raw_sections if s.strip()]
    if not sections:
        sections = [summary.strip()]

    logger.info(f"Structure-aware chunking: split summary into {len(sections)} sections by ## and ### headings.")

    # Lightweight meta builder (no class instance needed)
    def _build_meta(chunk_text, entity_name, chunk_index):
        meta = {
            "source_file": source_file,
            "product_name": entity_name,
            "treatment_name": entity_name,
            "entity": entity_name,
            "section": entity_name,
            "page": 1,
            "chunk_index": chunk_index,
            "knowledge_id": knowledge_id,
            "batch_id": batch_id,
            "file_hash": file_hash,
            "title": title,
            "document_type": doc_type,
            "clinics": visibility_settings.get("clinics", ["all"]),
            "doctor_types": visibility_settings.get("doctor_types", ["all"]),
            "doctors": visibility_settings.get("doctors", ["all"]),
        }
        if chunk_text:
            img_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
            if img_matches:
                meta["image_url"] = img_matches[0]
            sku_match = re.search(
                r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)',
                chunk_text, re.IGNORECASE
            )
            if sku_match:
                meta["sku"] = sku_match.group(1).strip()
            price_match = re.search(
                r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r]+)',
                chunk_text, re.IGNORECASE
            )
            if price_match:
                meta["price"] = price_match.group(1).strip()
            date_matches = re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b', chunk_text)
            if len(date_matches) >= 2:
                meta["valid_from"] = date_matches[0]
                meta["valid_until"] = date_matches[1]
            elif len(date_matches) == 1:
                meta["valid_until"] = date_matches[0]
            else:
                if valid_from:
                    meta["valid_from"] = valid_from
                if valid_until:
                    meta["valid_until"] = valid_until
        if categories:
            meta["category"] = categories[0]
            meta["categories"] = categories
        return meta

    # Helper: split a large Markdown table cleanly while repeating the header row on each sub-table
    def _split_markdown_table(table_text: str, max_chars: int) -> list:
        lines = [l.strip() for l in table_text.splitlines() if l.strip()]
        if len(lines) < 2 or not lines[0].startswith("|"):
            return [table_text]
        header = lines[0]
        if not header.endswith("|"):
            header = header + " |"

        if len(lines) > 1 and re.match(r'^\|(?:\s*:?-{3,}:?\s*\|)+$', lines[1]):
            separator = lines[1]
            body = lines[2:]
        else:
            col_count = max(len(header.split('|')) - 2, 2)
            separator = "| " + " | ".join(["---"] * col_count) + " |"
            body = lines[1:]

        sub_tables = []
        curr_rows = []
        curr_len = len(header) + len(separator) + 2
        for r in body:
            if curr_len + len(r) + 1 > max_chars and curr_rows:
                sub_tables.append("\n\n" + "\n".join([header, separator] + curr_rows) + "\n\n")
                curr_rows = []
                curr_len = len(header) + len(separator) + 2
            curr_rows.append(r)
            curr_len += len(r) + 1
        if curr_rows:
            sub_tables.append("\n\n" + "\n".join([header, separator] + curr_rows) + "\n\n")
        return sub_tables or [table_text]

    chunks = []
    chunk_idx = 0
    current_parent_h2 = ""

    for section_text in sections:
        # Detect heading level and title
        h_match = re.match(r'^(#{2,4})\s+(?:\d+[\.\)]\s*)?(.+)', section_text)
        if h_match:
            h_level, h_title = h_match.group(1), h_match.group(2).strip()
            if h_level == "##":
                current_parent_h2 = h_title
                # If section only has the ## heading line with no body text, record parent and don't emit tiny orphan chunk
                if len(section_text.splitlines()) <= 1:
                    continue
                entity_name = h_title
            else:
                # Sub-heading (### or ####): include parent breadcrumb for standalone semantic clarity
                entity_name = f"{current_parent_h2} > {h_title}" if current_parent_h2 and current_parent_h2 != h_title else h_title
        else:
            entity_name = current_parent_h2 or title

        if len(section_text) <= max_section_chars:
            chunk_idx += 1
            chunks.append({
                "text": section_text,
                "metadata": _build_meta(section_text, entity_name, chunk_idx)
            })
        else:
            # Check if this oversized section is primarily a Markdown table
            first_non_h = [l.strip() for l in section_text.splitlines() if l.strip() and not l.strip().startswith("#")]
            is_table_section = len(first_non_h) >= 2 and first_non_h[0].startswith("|") and first_non_h[1].startswith("|")

            if is_table_section:
                # Extract any heading before table
                leading_h = [l for l in section_text.splitlines() if l.strip().startswith("#")]
                h_prefix = "\n".join(leading_h) + "\n\n" if leading_h else ""
                table_body = "\n".join([l for l in section_text.splitlines() if not l.strip().startswith("#")]).strip()

                table_sub_chunks = _split_markdown_table(table_body, max_section_chars - len(h_prefix))
                for st in table_sub_chunks:
                    chunk_idx += 1
                    full_chunk_text = f"{h_prefix}{st}".strip()
                    chunks.append({
                        "text": full_chunk_text,
                        "metadata": _build_meta(full_chunk_text, entity_name, chunk_idx)
                    })
            else:
                # Standard paragraph / card splitting
                paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
                running_parts = []
                running_len = 0
                for para in paragraphs:
                    # If single paragraph is still huge (> max_section_chars), split by line
                    if len(para) > max_section_chars:
                        if running_parts:
                            chunk_idx += 1
                            sub_text = "\n\n".join(running_parts)
                            chunks.append({
                                "text": sub_text,
                                "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                            })
                            running_parts = []
                            running_len = 0
                        # Line-based slicing for huge paragraph
                        sub_lines = [l.strip() for l in para.splitlines() if l.strip()]
                        line_parts = []
                        line_len = 0
                        for l in sub_lines:
                            if line_len + len(l) > max_section_chars and line_parts:
                                chunk_idx += 1
                                sub_text = "\n".join(line_parts)
                                chunks.append({
                                    "text": sub_text,
                                    "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                                })
                                line_parts = []
                                line_len = 0
                            line_parts.append(l)
                            line_len += len(l) + 1
                        if line_parts:
                            chunk_idx += 1
                            sub_text = "\n".join(line_parts)
                            chunks.append({
                                "text": sub_text,
                                "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                            })
                        continue

                    if running_len + len(para) > max_section_chars and running_parts:
                        chunk_idx += 1
                        sub_text = "\n\n".join(running_parts)
                        if entity_name and not sub_text.startswith("#"):
                            sub_text = f"### {entity_name}\n\n{sub_text}"
                        chunks.append({
                            "text": sub_text,
                            "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                        })
                        running_parts = []
                        running_len = 0
                    running_parts.append(para)
                    running_len += len(para) + 2

                if running_parts:
                    chunk_idx += 1
                    sub_text = "\n\n".join(running_parts)
                    if entity_name and not sub_text.startswith("#"):
                        sub_text = f"### {entity_name}\n\n{sub_text}"
                    chunks.append({
                        "text": sub_text,
                        "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                    })

    # Hard upper bound guard: ensure NO chunk exceeds 2000 chars
    final_chunks = []
    for c in chunks:
        t = c.get("text", "")
        if len(t) <= 2000:
            final_chunks.append(c)
        else:
            # Force slice at 1800 chars
            lines = t.splitlines()
            curr_lines = []
            curr_l = 0
            for l in lines:
                if curr_l + len(l) + 1 > 1800 and curr_lines:
                    chunk_idx += 1
                    sliced_text = "\n".join(curr_lines)
                    final_chunks.append({
                        "text": sliced_text,
                        "metadata": c.get("metadata", {})
                    })
                    curr_lines = []
                    curr_l = 0
                curr_lines.append(l)
                curr_l += len(l) + 1
            if curr_lines:
                chunk_idx += 1
                sliced_text = "\n".join(curr_lines)
                final_chunks.append({
                    "text": sliced_text,
                    "metadata": c.get("metadata", {})
                })

    logger.info(f"Structure-aware chunking complete: {len(final_chunks)} chunks from {len(sections)} sections (max chunk size: {max(len(c['text']) for c in final_chunks) if final_chunks else 0} chars).")
    return final_chunks
