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
            
            if not headings and text_strip.lower() in self.KNOWN_SECTIONS:
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

        # Extract contextual image_url from markdown image tags in chunk text
        if chunk_text:
            img_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
            if img_matches:
                meta["image_url"] = img_matches[0]

            # Extract SKU
            sku_match = re.search(
                r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)',
                chunk_text, re.IGNORECASE
            )
            if sku_match:
                meta["sku"] = sku_match.group(1).strip()

            # Extract Price/Harga
            price_match = re.search(
                r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r]+)',
                chunk_text, re.IGNORECASE
            )
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
    def _split_large_table(self, table_lines: List[str], max_rows_per_chunk: int = 8) -> List[str]:
        """
        Splits a large markdown table into smaller valid sub-tables,
        ensuring each chunk has the complete table header and delimiter.
        """
        if len(table_lines) <= 3:
            return ["\n".join(table_lines)]

        header = table_lines[0]
        delimiter = table_lines[1]
        data_rows = table_lines[2:]

        sub_tables = []
        for i in range(0, len(data_rows), max_rows_per_chunk):
            chunk_rows = data_rows[i:i + max_rows_per_chunk]
            sub_table = "\n".join([header, delimiter] + chunk_rows)
            sub_tables.append(sub_table)

        return sub_tables

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
        section_h1_h2_pattern = re.compile(r"^(?:#{1,2}\s+|(?:Bab|Section|Bagian|Kategori)\s+\d+)", re.IGNORECASE)
        # Match H3/H4 headers, but NOT bold key-value pairs or numbered list items
        entity_h3_h4_pattern = re.compile(r"^(?:#{3,4}\s+)", re.IGNORECASE)
        bold_entity_pattern = re.compile(r"^\*\*([A-Z0-9][A-Za-z0-9\s\.\-]+)\*\*\s*$", re.IGNORECASE)

        for page_data in pages:
            page_num = page_data.get("page", 1)
            page_image_urls = page_data.get("image_urls") or ([page_data.get("image_url")] if page_data.get("image_url") else [])
            page_image_url = page_image_urls[0] if page_image_urls else page_data.get("image_url")
            page_text = page_data.get("text", "").strip()
            if not page_text:
                continue

            lines = page_text.split("\n")
            current_entity_lines = []
            current_table_lines = []

            def _build_meta(chunk_text: str = "") -> Dict[str, Any]:
                meta = {
                    "section": current_section,
                    "entity": current_entity,
                    "page": page_num
                }
                if current_section and current_section.lower().startswith("sheet:"):
                    meta["sheet_name"] = current_section.split(":", 1)[1].strip()

                extracted_urls = []
                if chunk_text:
                    found_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
                    for u in found_matches:
                        if u not in extracted_urls:
                            extracted_urls.append(u)

                    sku_match = re.search(r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)', chunk_text, re.IGNORECASE)
                    if sku_match:
                        meta["sku"] = sku_match.group(1).strip()

                    # Extract promo validity period (YYYY-MM-DD) per product chunk if present
                    date_matches = re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b', chunk_text)
                    if len(date_matches) >= 2:
                        meta["valid_from"] = date_matches[0]
                        meta["valid_until"] = date_matches[1]
                    elif len(date_matches) == 1:
                        meta["valid_until"] = date_matches[0]

                    # Extract Price / Harga per product chunk if present
                    price_match = re.search(r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r]+)', chunk_text, re.IGNORECASE)
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
                                if current_entity and not sub_text.startswith("#"):
                                    sub_text = f"### {current_entity}\n\n{sub_text}"
                                processed_chunks.append({
                                    "text": sub_text,
                                    "metadata": _build_meta(sub_text)
                                })
                                running_sub = []
                        if running_sub:
                            sub_text = "\n\n".join(running_sub)
                            if current_entity and not sub_text.startswith("#"):
                                sub_text = f"### {current_entity}\n\n{sub_text}"
                            processed_chunks.append({
                                "text": sub_text,
                                "metadata": _build_meta(sub_text)
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

                prefix = f"## {current_section}\n\n" if (current_section and current_section.lower() != "general") else ""

                if len(current_table_lines) > 10:
                    sub_tables = self._split_large_table(current_table_lines, max_rows_per_chunk=6)
                    for tbl in sub_tables:
                        full_tbl = f"{prefix}{tbl}" if prefix and not tbl.startswith("#") else tbl
                        processed_chunks.append({
                            "text": full_tbl,
                            "metadata": _build_meta(full_tbl)
                        })
                else:
                    table_txt = "\n".join(current_table_lines)
                    full_tbl = f"{prefix}{table_txt}" if prefix and not table_txt.startswith("#") else table_txt
                    processed_chunks.append({
                        "text": full_tbl,
                        "metadata": _build_meta(full_tbl)
                    })
                current_table_lines = []

            for line in lines:
                line_strip = line.strip()
                if not line_strip:
                    if current_table_lines:
                        flush_table_block()
                    continue

                # 1. Detect Markdown Table Row
                is_table_row = line_strip.startswith("|") and line_strip.endswith("|")
                if is_table_row:
                    if current_entity_lines:
                        hdr_text = "\n".join(current_entity_lines).strip()
                        if len(hdr_text) <= 250:
                            current_table_lines.extend(current_entity_lines)
                            current_entity_lines = []
                        else:
                            flush_entity_block()
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

    # Split summary into sections by ## headings
    raw_sections = re.split(r'(?=\n##\s+)', summary)
    sections = [s.strip() for s in raw_sections if s.strip() and len(s.strip()) >= 30]
    if not sections:
        sections = [summary.strip()]

    logger.info(f"Structure-aware chunking: split summary into {len(sections)} sections by ## headings.")

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

    chunks = []
    chunk_idx = 0

    for section_text in sections:
        h2_match = re.match(r'^##\s+(?:\d+[\.\)]\s*)?(.+)', section_text)
        entity_name = h2_match.group(1).strip() if h2_match else title

        if len(section_text) <= max_section_chars:
            chunk_idx += 1
            chunks.append({
                "text": section_text,
                "metadata": _build_meta(section_text, entity_name, chunk_idx)
            })
        else:
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            running_parts = []
            running_len = 0
            for para in paragraphs:
                if running_len + len(para) > max_section_chars and running_parts:
                    chunk_idx += 1
                    sub_text = "\n\n".join(running_parts)
                    if entity_name and not sub_text.startswith("##"):
                        sub_text = f"## {entity_name}\n\n{sub_text}"
                    chunks.append({
                        "text": sub_text,
                        "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                    })
                    running_parts = []
                    running_len = 0
                running_parts.append(para)
                running_len += len(para)
            if running_parts:
                chunk_idx += 1
                sub_text = "\n\n".join(running_parts)
                if entity_name and not sub_text.startswith("##"):
                    sub_text = f"## {entity_name}\n\n{sub_text}"
                chunks.append({
                    "text": sub_text,
                    "metadata": _build_meta(sub_text, entity_name, chunk_idx)
                })

    logger.info(f"Structure-aware chunking complete: {len(chunks)} chunks from {len(sections)} sections.")
    return chunks
