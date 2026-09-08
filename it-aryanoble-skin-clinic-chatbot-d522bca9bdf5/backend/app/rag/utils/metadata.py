import os
from typing import List, Dict
from datetime import datetime, timezone
from loguru import logger

try:
    from langdetect import detect
except ImportError:
    logger.warning("langdetect is not installed, language detection will fallback to default.")
    detect = None

class MetadataEnricher:
    def __init__(self):
        pass

    def estimate_token_count(self, text: str) -> int:
        """Estimates the token count based on word count (approx. 1.3 tokens per word)."""
        words = text.split()
        return int(len(words) * 1.3)

    def detect_document_language(self, doc) -> str:
        """Detects the language of the document based on the first few paragraphs.
        Supports both ParseResult and DoclingDocument objects."""
        if not doc:
            return "en"
        
        sample_text = []
        char_count = 0
        
        # Handle ParseResult (fast path)
        from app.rag.utils.parser import ParseResult
        if isinstance(doc, ParseResult):
            for page_data in doc.pages:
                text = page_data.get("text", "").strip()
                if text:
                    sample_text.append(text[:2000])
                    char_count += min(len(text), 2000)
                    if char_count > 2000:
                        break
        # Handle DoclingDocument (docling path)
        elif hasattr(doc, "texts"):
            for element in doc.texts:
                if hasattr(element, "text") and element.text.strip():
                    text = element.text.strip()
                    sample_text.append(text)
                    char_count += len(text)
                    if char_count > 2000:
                        break
                        
        full_sample = " ".join(sample_text)
        if not full_sample.strip():
            return "en"
            
        if detect:
            try:
                return detect(full_sample)
            except Exception as e:
                logger.debug(f"Language detection failed: {e}")
        return "en"

    def infer_document_type(self, file_path: str, section: str) -> str:
        """Infers the document type from the file name, active section, or file path."""
        filename = os.path.basename(file_path).lower()
        section_lower = section.lower()

        # 1. Filename rules
        if "sop" in filename:
            return "sop"
        elif "faq" in filename or "tanya_jawab" in filename or "qna" in filename:
            return "faq"
        elif "promo" in filename or "marketing" in filename or "promotion" in filename:
            return "promotion"
        elif "treatment" in filename or "peeling" in filename or "facial" in filename or "laser" in filename or "micro" in filename:
            return "treatment"
        elif "product" in filename or "brochure" in filename or "brosur" in filename or "gel" in filename or "cream" in filename or "catalog" in filename:
            return "product"

        # 2. Heading rules fallback
        if "sop" in section_lower:
            return "sop"
        elif "faq" in section_lower or "frequently asked" in section_lower or "qna" in section_lower:
            return "faq"
        elif "promo" in section_lower or "promotion" in section_lower:
            return "promotion"
        elif "treatment" in section_lower:
            return "treatment"
        elif "product" in section_lower or "brochure" in section_lower:
            return "product"

        # 3. Path rules
        if "product" in file_path.lower():
            return "product"
        elif "treatment" in file_path.lower():
            return "treatment"

        return "product"

    def enrich_chunks(self, chunks: List[Dict], file_path: str, language: str = "en") -> List[Dict]:
        """
        Enriches the chunks with structured, production-ready metadata:
        - source_file
        - product_name
        - document_type
        - section
        - page
        - chunk_index
        - language
        - token_count
        - processed_at (ISO UTC format)
        """
        enriched_data = []
        filename = os.path.basename(file_path)
        processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Clean and format product_name from filename
        product_name = filename
        for ext in [".pdf", ".docx", ".txt", "_parsed.json"]:
            product_name = product_name.replace(ext, "")
        
        # Case-insensitive prefix cleaning
        pn_lower = product_name.lower()
        for prefix in ["dummy_", "dumy_", "dummy-", "dumy-", "dummy ", "dumy "]:
            if pn_lower.startswith(prefix):
                product_name = product_name[len(prefix):]
                pn_lower = pn_lower[len(prefix):]
        if pn_lower.startswith("dummy") or pn_lower.startswith("dumy"):
            product_name = product_name[5:]
            
        product_name = product_name.replace("-", " ").replace("_", " ")
        product_name = product_name.strip()

        for idx, chunk in enumerate(chunks, start=1):
            text = chunk.get("text", "")
            chunk_meta = chunk.get("metadata", {})

            section = chunk_meta.get("section", "Root")

            document_type = self.infer_document_type(file_path, section)
            page = chunk_meta.get("page", 1)
            token_count = self.estimate_token_count(text)

            enriched_meta = {
                "source_file": filename,
                "product_name": product_name,
                "document_type": document_type,
                "section": section,
                "page": page,
                "chunk_index": idx,
                "language": language,
                "token_count": token_count,
                "processed_at": processed_at
            }

            enriched_data.append({
                "text": text,
                "metadata": enriched_meta
            })

        return enriched_data
