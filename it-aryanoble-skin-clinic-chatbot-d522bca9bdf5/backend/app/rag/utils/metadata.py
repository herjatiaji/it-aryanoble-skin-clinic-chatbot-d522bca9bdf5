import os
import re
import hashlib
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

        # 0. Scientific literature & research papers
        if any(k in filename for k in ["manuscript", "published", "journal", "paper", "study", "research", "clinical_study"]):
            return "scientific_literature"
        if any(k in section_lower for k in ["abstract", "materials and methods", "methodology", "study design", "clinical results"]):
            return "scientific_literature"

        # 1. Filename rules
        if "sop" in filename:
            return "treatment"
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
            return "treatment"
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

        return "other"

    def enrich_chunks(self, chunks: List[Dict], file_path: str, language: str = "en") -> List[Dict]:
        """
        Enriches chunks with canonical clinical metadata:
        - stable chunk_id
        - proper product_name (never forced from catalog/cheatsheet filename)
        - treatment_name, form_factor, sku, dose, frequency, indication
        - knowledge_scope (GLOBAL, TENANT, CLINIC)
        - canonical retrieval_text for unified Dense & Sparse indexing
        """
        from app.rag.canonical import (
            CanonicalChunk,
            KnowledgeType,
            KnowledgeScope,
            generate_stable_chunk_id,
            build_canonical_retrieval_text,
            extract_canonical_form_factor,
            classify_image_provenance
        )

        enriched_data = []
        filename = os.path.basename(file_path)
        processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Determine if file is a multi-item collection (Catalog, Cheatsheet, SOP, Journal)
        fname_lower = filename.lower()
        is_multi_item_file = any(
            k in fname_lower for k in [
                "catalog", "katalog", "cheatsheet", "daftar", "sop", "treatment",
                "manuscript", "published", "journal", "dummy_test", "matrix"
            ]
        )

        # Clean document title
        doc_title = filename
        for ext in [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".csv", ".pptx", "_parsed.json"]:
            doc_title = doc_title.replace(ext, "")
        for prefix in ["dummy_", "dumy_", "dummy-", "dumy-", "dummy ", "dumy "]:
            if doc_title.lower().startswith(prefix):
                doc_title = doc_title[len(prefix):]
        doc_title = doc_title.replace("-", " ").replace("_", " ").strip()

        # Infer knowledge scope
        if any(k in fname_lower for k in ["manuscript", "published", "journal", "paper", "study"]):
            default_scope = KnowledgeScope.GLOBAL
        else:
            default_scope = KnowledgeScope.TENANT

        for idx, chunk in enumerate(chunks, start=1):
            text = chunk.get("text", "")
            chunk_meta = dict(chunk.get("metadata", {}))

            section = chunk_meta.get("section") or "General"
            doc_type_str = self.infer_document_type(file_path, section)

            # Map to canonical KnowledgeType
            type_mapping = {
                "product": KnowledgeType.PRODUCT,
                "treatment": KnowledgeType.TREATMENT_SOP,
                "scientific_literature": KnowledgeType.SCIENTIFIC_LITERATURE,
                "faq": KnowledgeType.FAQ,
            }
            k_type = type_mapping.get(doc_type_str, KnowledgeType.OTHER)

            page = chunk_meta.get("page", 1)
            sheet_name = chunk_meta.get("sheet_name")
            token_count = self.estimate_token_count(text)

            # Resolve product_name strictly without false fallback
            # Priority:
            # 1. Existing chunk_meta product_name
            # 2. chunk_meta entity (if type is product)
            # 3. Filename ONLY IF single-product document
            product_name = chunk_meta.get("product_name")
            if not product_name and chunk_meta.get("entity") and k_type == KnowledgeType.PRODUCT:
                product_name = chunk_meta.get("entity")
            if not product_name and not is_multi_item_file and k_type == KnowledgeType.PRODUCT:
                product_name = doc_title

            # Resolve treatment_name strictly
            treatment_name = chunk_meta.get("treatment_name")
            if not treatment_name and k_type == KnowledgeType.TREATMENT_SOP:
                treatment_name = chunk_meta.get("entity") or (section if section.lower() not in ("general", "root") else None)

            # Extract form_factor safely if present or discern from canonical taxonomy
            form_factor = chunk_meta.get("form_factor") or extract_canonical_form_factor(text)

            sku = chunk_meta.get("sku")
            dose = chunk_meta.get("dose")
            frequency = chunk_meta.get("frequency")
            indication = chunk_meta.get("indication")
            clinic_id = chunk_meta.get("clinic_id")
            scope_str = chunk_meta.get("knowledge_scope") or default_scope.value

            # Stable Chunk ID
            stable_id = chunk_meta.get("chunk_id") or generate_stable_chunk_id(
                doc_identifier=filename,
                version=chunk_meta.get("version", "1.0"),
                sheet_or_page=sheet_name or page,
                row_or_entity=chunk_meta.get("row_start") or product_name or treatment_name or idx,
                chunk_index=idx
            )

            # Canonical Chunk object
            canon_chunk = CanonicalChunk(
                document_id=filename,
                chunk_id=stable_id,
                version=chunk_meta.get("version", "1.0"),
                knowledge_type=k_type,
                knowledge_scope=KnowledgeScope(scope_str) if scope_str in KnowledgeScope._value2member_map_ else KnowledgeScope.GLOBAL,
                clinic_id=clinic_id,
                source_file=filename,
                page=page,
                sheet_name=sheet_name,
                row_start=chunk_meta.get("row_start"),
                row_end=chunk_meta.get("row_end"),
                section=section,
                treatment_name=treatment_name,
                product_name=product_name,
                form_factor=form_factor,
                product_role=chunk_meta.get("product_role"),
                sku=sku,
                dose=dose,
                frequency=frequency,
                indication=indication,
                content=text,
                valid_from=chunk_meta.get("valid_from"),
                valid_until=chunk_meta.get("valid_until"),
                is_temporally_valid=chunk_meta.get("is_temporally_valid", True)
            )

            retrieval_text = build_canonical_retrieval_text(canon_chunk)
            canon_chunk.retrieval_text = retrieval_text

            # Export dictionary metadata
            enriched_meta = canon_chunk.to_metadata_dict()
            enriched_meta["document_type"] = doc_type_str
            enriched_meta["language"] = language
            enriched_meta["token_count"] = token_count
            enriched_meta["processed_at"] = processed_at
            enriched_meta["retrieval_text"] = retrieval_text

            # Extract and classify structured image provenance for all images in this chunk
            inline_images = re.findall(r'!\[([^\]]*)\]\(([^\s\)]+)\)', text)
            provenance_list = []
            doc_id = chunk_meta.get("document_id") or hashlib.sha256(f"{filename}:{chunk_meta.get('version', '1.0')}".encode()).hexdigest()[:12]
            for img_i, (alt_t, u_str) in enumerate(inline_images, start=1):
                tbl_context = ""
                if "|" in text:
                    for line in text.splitlines():
                        if u_str in line and "|" in line:
                            tbl_context = line
                            break
                prov = classify_image_provenance(
                    target_url=u_str,
                    document_id=doc_id,
                    source_document=filename,
                    knowledge_type=k_type,
                    alt_text=alt_t,
                    caption=chunk_meta.get("caption"),
                    table_context=tbl_context,
                    chunk_text=text,
                    meta=enriched_meta,
                    page_or_sheet=sheet_name or page,
                    row=chunk_meta.get("row_start"),
                    image_index=img_i,
                    section=section
                )
                provenance_list.append(prov.to_dict())

            if provenance_list:
                enriched_meta["image_provenance"] = provenance_list

            # Preserve other non-conflicting metadata keys
            for k, v in chunk_meta.items():
                if k not in enriched_meta and v is not None:
                    enriched_meta[k] = v

            enriched_data.append({
                "text": text,
                "metadata": enriched_meta
            })

        return enriched_data
