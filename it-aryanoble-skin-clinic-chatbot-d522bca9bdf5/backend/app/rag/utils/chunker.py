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
            
            is_table = any(type(item).__name__ == "TableItem" for item in sc.meta.doc_items) if hasattr(sc, "meta") and hasattr(sc.meta, "doc_items") and sc.meta.doc_items else False
            is_picture = any(type(item).__name__ == "PictureItem" for item in sc.meta.doc_items) if hasattr(sc, "meta") and hasattr(sc.meta, "doc_items") and sc.meta.doc_items else False
            
            if is_table:
                chunk_type = "TableChunk"
            elif is_picture:
                chunk_type = "PictureChunk"
            else:
                chunk_type = "TextChunk"
            
            if not headings and text_strip.lower() in self.KNOWN_SECTIONS:
                current_section = text_strip.upper()
                continue
                
            if headings:
                section = headings[-1].upper()
            else:
                section = current_section
                
            base_metadata = {
                "headings": headings,
                "section": section,
                "chunk_type": chunk_type,
                "page": page
            }
            
            processed_chunks.append({
                "text": text,
                "metadata": base_metadata
            })

        return self._merge_and_split(processed_chunks, max_length_for_semantic)

    # =========================================================================
    # FAST PATH: Section-aware chunking from plain page text
    # =========================================================================
    def _chunk_fast_pages(self, pages: List[Dict], max_length_for_semantic: int = 500) -> List[Dict]:
        """
        Smart section-aware chunking from fast-extracted page text.
        Detects section headers, splits by sections, and preserves page numbers.
        """
        logger.info(f"⚡ Fast chunking {len(pages)} pages with section detection...")

        # Build a regex pattern for known section headers
        section_pattern = re.compile(
            r"^(?:" + "|".join(re.escape(s) for s in self.KNOWN_SECTIONS) + r")\s*:?\s*$",
            re.IGNORECASE | re.MULTILINE
        )

        processed_chunks = []
        current_section = "Root"

        for page_data in pages:
            page_num = page_data.get("page", 1)
            page_text = page_data.get("text", "").strip()
            if not page_text:
                continue

            # Split page text into lines and group by sections
            lines = page_text.split("\n")
            current_block_lines = []

            for line in lines:
                line_strip = line.strip()
                if not line_strip:
                    continue

                # Check if this line is a section header
                if line_strip.lower() in self.KNOWN_SECTIONS or section_pattern.match(line_strip):
                    # Flush current block before switching sections
                    if current_block_lines:
                        block_text = "\n".join(current_block_lines).strip()
                        if block_text:
                            processed_chunks.append({
                                "text": block_text,
                                "metadata": {
                                    "headings": [current_section],
                                    "section": current_section,
                                    "chunk_type": "TextChunk",
                                    "page": page_num
                                }
                            })
                        current_block_lines = []

                    current_section = line_strip.upper()
                    continue

                current_block_lines.append(line_strip)

            # Flush remaining lines from this page
            if current_block_lines:
                block_text = "\n".join(current_block_lines).strip()
                if block_text:
                    processed_chunks.append({
                        "text": block_text,
                        "metadata": {
                            "headings": [current_section],
                            "section": current_section,
                            "chunk_type": "TextChunk",
                            "page": page_num
                        }
                    })

        logger.info(f"Created {len(processed_chunks)} section-aware chunks from fast extraction.")
        return self._merge_and_split(processed_chunks, max_length_for_semantic)

    # =========================================================================
    # SHARED: Merge consecutive same-section chunks + semantic split long ones
    # =========================================================================
    def _merge_and_split(self, processed_chunks: List[Dict], max_length_for_semantic: int = 500) -> List[Dict]:
        """
        Phase 2: Merge consecutive text chunks belonging to the same section and page.
        Apply semantic splitting to chunks that exceed max_length_for_semantic.
        """
        final_chunks = []
        current_merged = None
        
        def push_chunk(merged_chunk):
            if not merged_chunk:
                return
            txt = merged_chunk["text"]
            meta = merged_chunk["metadata"]
            c_type = meta.get("chunk_type")
            
            if len(txt) > max_length_for_semantic and c_type == "TextChunk":
                # Fast paragraph splitting for long section blocks (> 1500 chars)
                paragraphs = [p.strip() for p in txt.split("\n\n") if p.strip()]
                if len(paragraphs) > 1:
                    for p in paragraphs:
                        final_chunks.append({
                            "text": p,
                            "metadata": meta.copy()
                        })
                else:
                    final_chunks.append({
                        "text": txt,
                        "metadata": meta
                    })
            else:
                final_chunks.append({
                    "text": txt,
                    "metadata": meta
                })

        for pc in processed_chunks:
            text = pc["text"]
            meta = pc["metadata"]
            c_type = meta.get("chunk_type")
            
            if c_type == "TextChunk":
                if current_merged:
                    same_section = current_merged["metadata"]["section"] == meta["section"]
                    same_page = current_merged["metadata"]["page"] == meta["page"]
                    not_too_long = (len(current_merged["text"]) + len(text) + 2) <= max_length_for_semantic
                    
                    if same_section and same_page and not_too_long:
                        current_merged["text"] += "\n" + text
                    else:
                        push_chunk(current_merged)
                        current_merged = {
                            "text": text,
                            "metadata": meta
                        }
                else:
                    current_merged = {
                        "text": text,
                        "metadata": meta
                    }
            else:
                push_chunk(current_merged)
                current_merged = None
                final_chunks.append({
                    "text": text,
                    "metadata": meta
                })
                
        push_chunk(current_merged)
        
        logger.info(f"Final total chunks generated after merging and semantic splitting: {len(final_chunks)}")
        return final_chunks

    # =========================================================================
    # PUBLIC API: Unified entry point
    # =========================================================================
    def chunk_document(self, parse_result, max_length_for_semantic: int = 500) -> List[Dict]:
        """
        Unified chunking entry point. Accepts either:
        - ParseResult (from new smart parser)
        - DoclingDocument (backward compatibility)
        
        Automatically routes to the correct chunking path.
        """
        # Handle new ParseResult objects
        if isinstance(parse_result, ParseResult):
            if parse_result.is_fast:
                return self._chunk_fast_pages(parse_result.pages, max_length_for_semantic)
            elif parse_result.is_docling and parse_result.docling_doc:
                return self._chunk_docling_document(parse_result.docling_doc, max_length_for_semantic)
            else:
                logger.error("ParseResult has no usable data.")
                return []

        # Backward compatibility: accept raw DoclingDocument
        if DoclingDocument and isinstance(parse_result, DoclingDocument):
            return self._chunk_docling_document(parse_result, max_length_for_semantic)

        # Fallback: try treating it as a DoclingDocument anyway
        logger.warning(f"Unknown parse_result type: {type(parse_result)}. Attempting Docling chunking.")
        return self._chunk_docling_document(parse_result, max_length_for_semantic)
