"""
Canonical Knowledge Schema and Data Contracts for Skin Clinic RAG.
Provides standardized metadata representation, stable chunk identity,
adaptive evidence unit construction, and unified retrieval text.
"""

import os
import re
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple


class KnowledgeScope(str, Enum):
    GLOBAL = "GLOBAL"    # Scientific literature, general dermatology textbooks, shared clinical studies
    TENANT = "TENANT"    # Arya Noble / ERHA Group wide policies and formulary
    CLINIC = "CLINIC"    # Branch-specific protocols, local stock/price, unique doctor schedules


class KnowledgeType(str, Enum):
    PRODUCT = "product"                            # Product catalog, formulary, SKU lists
    TREATMENT_SOP = "treatment"                     # Treatment SOP, clinical procedures, device parameters
    SCIENTIFIC_LITERATURE = "scientific_literature"# Research papers, randomized controlled trials, clinical manuscripts
    FAQ = "faq"                                     # Curated clinical Q&A
    OTHER = "other"                                 # General educational materials, guidelines


@dataclass
class CanonicalChunk:
    """
    Standardized, strongly-typed representation of a knowledge chunk.
    Enforces strict separation: Product != Treatment != Form Factor.
    All optional fields are strictly nullable (NO synthetic "N/A" strings allowed).
    """
    document_id: str
    chunk_id: str
    version: str = "1.0"
    knowledge_type: KnowledgeType = KnowledgeType.OTHER
    knowledge_scope: KnowledgeScope = KnowledgeScope.GLOBAL
    clinic_id: Optional[str] = None

    source_file: str = ""
    page: int = 1
    sheet_name: Optional[str] = None
    row_start: Optional[int] = None
    row_end: Optional[int] = None

    section: str = "General"
    treatment_name: Optional[str] = None
    product_name: Optional[str] = None
    form_factor: Optional[str] = None
    product_role: Optional[str] = None
    sku: Optional[str] = None

    dose: Optional[str] = None
    frequency: Optional[str] = None
    indication: Optional[str] = None

    content: str = ""
    retrieval_text: str = ""

    valid_from: Optional[str] = None     # ISO YYYY-MM-DD
    valid_until: Optional[str] = None    # ISO YYYY-MM-DD
    is_temporally_valid: bool = True

    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Converts chunk attributes into a JSON-serializable dictionary for PGVector/BM25 storage."""
        d = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "version": self.version,
            "knowledge_type": self.knowledge_type.value if isinstance(self.knowledge_type, KnowledgeType) else str(self.knowledge_type),
            "knowledge_scope": self.knowledge_scope.value if isinstance(self.knowledge_scope, KnowledgeScope) else str(self.knowledge_scope),
            "clinic_id": self.clinic_id,
            "source_file": self.source_file,
            "page": self.page,
            "sheet_name": self.sheet_name,
            "row_start": self.row_start,
            "row_end": self.row_end,
            "section": self.section,
            "treatment_name": self.treatment_name,
            "product_name": self.product_name,
            "form_factor": self.form_factor,
            "product_role": self.product_role,
            "sku": self.sku,
            "dose": self.dose,
            "frequency": self.frequency,
            "indication": self.indication,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "is_temporally_valid": self.is_temporally_valid,
        }
        # Merge extra metadata if not conflicting
        for k, v in self.extra_metadata.items():
            if k not in d:
                d[k] = v
        return d


def generate_stable_chunk_id(
    doc_identifier: str,
    version: str = "1.0",
    sheet_or_page: Any = 1,
    row_or_entity: Any = 0,
    chunk_index: int = 0
) -> str:
    """
    Generates a deterministic, reproducible chunk_id string.
    Format: '{doc_hash[:8]}:{version}:{sheet_or_page}:{row_or_entity}:{chunk_index}'
    Ensures identical chunks always produce the identical identity for deduplication & tie-breaking.
    """
    raw_id = str(doc_identifier or "doc").strip()
    doc_hash = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:8]
    clean_ver = str(version or "1.0").strip().replace(" ", "_")
    clean_loc = str(sheet_or_page or "1").strip().replace(" ", "_")
    clean_row = str(row_or_entity or "0").strip().replace(" ", "_")
    return f"{doc_hash}:{clean_ver}:{clean_loc}:{clean_row}:{chunk_index}"


def build_canonical_retrieval_text(chunk: CanonicalChunk) -> str:
    """
    Constructs unified retrieval text shared between Dense PGVector embeddings and Sparse BM25 index.
    Guarantees dense and sparse algorithms search against identical canonical tokens.
    Only non-empty attributes are included (avoids synthetic placeholders).
    """
    parts = []

    k_type = chunk.knowledge_type.value if isinstance(chunk.knowledge_type, KnowledgeType) else str(chunk.knowledge_type)
    parts.append(f"Type: {k_type.upper()}")

    if chunk.treatment_name:
        parts.append(f"Treatment: {chunk.treatment_name.strip()}")

    if chunk.product_name:
        parts.append(f"Product: {chunk.product_name.strip()}")

    if chunk.form_factor:
        parts.append(f"Form Factor: {chunk.form_factor.strip().lower()}")

    if chunk.product_role:
        parts.append(f"Role: {chunk.product_role.strip()}")

    if chunk.sku:
        parts.append(f"SKU: {chunk.sku.strip()}")

    if chunk.dose:
        parts.append(f"Dose: {chunk.dose.strip()}")

    if chunk.frequency:
        parts.append(f"Frequency: {chunk.frequency.strip()}")

    if chunk.indication:
        parts.append(f"Indication: {chunk.indication.strip()}")

    if chunk.section and chunk.section.lower() not in ("general", "root"):
        parts.append(f"Section: {chunk.section.strip()}")

    content_clean = (chunk.content or "").strip()
    if content_clean:
        parts.append(f"Content: {content_clean}")

    return " | ".join(parts)


@dataclass
class EvidenceUnit:
    """
    A single factual unit of clinical evidence formatted for compact presentation to the LLM.
    Strictly verifiable and traceable to source document & page/sheet/row coordinates.
    """
    source_file: str
    page: int = 1
    sheet_name: Optional[str] = None
    row: Optional[int] = None

    knowledge_type: str = "other"
    treatment: Optional[str] = None
    product: Optional[str] = None
    form_factor: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    indication: Optional[str] = None
    content: str = ""

    chunk_id: str = ""
    score: float = 0.0

    def format_for_prompt(self, index: int) -> str:
        """Renders evidence unit into a compact, standardized block (~100-200 tokens)."""
        loc_parts = []
        if self.sheet_name:
            loc_parts.append(f"Sheet: {self.sheet_name}")
        if self.page:
            loc_parts.append(f"Page: {self.page}")
        if self.row is not None:
            loc_parts.append(f"Row: {self.row}")
        location_str = f" ({', '.join(loc_parts)})" if loc_parts else ""

        lines = [f"[EVIDENCE {index}]"]
        lines.append(f"Source: {self.source_file}{location_str}")

        if self.treatment:
            lines.append(f"Treatment: {self.treatment}")
        if self.product:
            lines.append(f"Product: {self.product}")
        if self.form_factor:
            lines.append(f"Form Factor: {self.form_factor}")
        if self.dose:
            lines.append(f"Dose: {self.dose}")
        if self.frequency:
            lines.append(f"Frequency: {self.frequency}")
        if self.indication:
            lines.append(f"Indication: {self.indication}")

        clean_content = (self.content or "").strip()
        if clean_content:
            lines.append(f"Content: {clean_content}")

        return "\n".join(lines)


@dataclass
class CompactEvidencePack:
    """
    Container of top-K (typically 3-5) evidence units.
    Acts as the single source of truth (SSOT) passed to the LLM and Factual Safety Gate.
    """
    units: List[EvidenceUnit] = field(default_factory=list)
    confidence: str = "HIGH"  # "HIGH", "PARTIAL", "NONE"

    def to_context_string(self) -> str:
        if not self.units:
            return "No relevant clinical evidence found in knowledge base."
        return "\n\n".join(u.format_for_prompt(idx + 1) for idx, u in enumerate(self.units))


# =============================================================================
# STRUCTURED IMAGE PROVENANCE & CANONICAL TAXONOMY
# =============================================================================

class ImageRelevance(str, Enum):
    RELEVANT = "relevant"      # Relevant to chatbot clinical/product knowledge
    IRRELEVANT = "irrelevant"  # Document artifact (logo, author headshot, decorative icon)
    UNKNOWN = "unknown"        # Insufficient evidence to prove knowledge value


class ImageDisplayPolicy(str, Enum):
    INCLUDE = "include"  # Authorized to display on frontend
    EXCLUDE = "exclude"  # Suppressed from frontend markdown
    REVIEW = "review"    # Flagged for human/admin verification (NOT displayed)


class ImageType(str, Enum):
    PRODUCT = "product"                            # Skincare product, packaging, bottle
    CLINICAL_BEFORE_AFTER = "clinical_before_after"# Clinical before/after comparison photo
    EQUIPMENT = "equipment"                        # Medical device, laser machine, clinical tool
    ILLUSTRATION = "illustration"                  # Anatomical diagram, flowchart, infographic
    SCIENTIFIC_FIGURE = "scientific_figure"        # Clinical study figure, histology, trial outcome
    SCIENTIFIC_GRAPH = "scientific_graph"          # Chart, graph, curve, plot
    DOCUMENT_LOGO = "document_logo"                # Journal/publisher/university/clinic logo, header banner
    AUTHOR_PHOTO = "author_photo"                  # Author headshot, investigator portrait
    DECORATIVE = "decorative"                      # Border, divider, bullet icon, aesthetic graphic
    OTHER = "other"                                # Generic image or unclassified


class ClinicalStage(str, Enum):
    BEFORE = "before"
    AFTER = "after"


# Canonical Form Factor Taxonomy (Single Source of Truth across Parser, Retrieval, and Generator)
FORM_FACTOR_TAXONOMY: Dict[str, str] = {
    "serum": "serum",
    "scalp_serum": "serum",
    "scalp serum": "serum",
    "toner": "toner",
    "krim": "krim",
    "cream": "krim",
    "gel": "gel",
    "lotion": "lotion",
    "cleanser": "cleanser",
    "facial wash": "cleanser",
    "facial cleanser": "cleanser",
    "sabun cuci muka": "cleanser",
    "wash": "cleanser",
    "shampoo": "shampoo",
    "sampo": "shampoo",
    "sunscreen": "sunscreen",
    "tabir surya": "sunscreen",
    "sunblock": "sunscreen",
    "masker": "masker",
    "mask": "masker",
    "foam": "foam",
    "powder": "powder",
    "injeksi": "injeksi",
    "ampoule": "injeksi",
    "vial": "injeksi",
    "peeling_solution": "peeling_solution",
    "peeling solution": "peeling_solution",
    "solution": "solution",
}


def extract_canonical_form_factor(text: str) -> Optional[str]:
    """
    Extracts canonical form factor from text using the unified taxonomy.
    Longer tokens matched first to prevent substring collisions (e.g. 'facial wash' before 'wash').
    """
    if not text:
        return None
    t_lower = text.lower()
    for pattern, canonical_val in sorted(FORM_FACTOR_TAXONOMY.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf'\b{re.escape(pattern)}\b', t_lower):
            return canonical_val
    return None


def generate_stable_image_id(
    document_id: str,
    page_or_sheet: Any = 1,
    row: Any = None,
    column: Any = None,
    target_url: str = "",
    image_index: Optional[int] = None
) -> str:
    """
    Generates deterministic, collision-free image ID anchored to canonical document_id.
    Extraction ordinal (image_index) is used strictly as positional identity disambiguator,
    NEVER as clinical/semantic meaning.
    """
    raw = f"{document_id}:{page_or_sheet}:{row}:{column}:{target_url}:{image_index}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"img_{h}"


@dataclass
class ImageProvenance:
    """
    Structured Image Provenance Data Model.
    Tracks authentic identity, source document, coordinate location,
    extracted alt text, caption, and clinical/scientific classification.
    Adheres strictly to the Three Dimensions:
    1. WHAT IS IT?   -> image_type
    2. IS IT KNOWLEDGE? -> image_relevance (w.r.t chatbot knowledge)
    3. CAN FRONTEND SHOW IT? -> display_policy
    """
    image_id: str
    document_id: str = ""
    source_document: str = ""
    page_or_sheet: Any = 1
    row: Optional[int] = None
    column: Optional[int] = None
    image_index: Optional[int] = None

    target_url: str = ""
    alt_text: str = ""
    caption: Optional[str] = None

    knowledge_type: KnowledgeType = KnowledgeType.OTHER
    image_type: ImageType = ImageType.OTHER
    image_relevance: ImageRelevance = ImageRelevance.UNKNOWN
    display_policy: ImageDisplayPolicy = ImageDisplayPolicy.EXCLUDE

    clinical_stage: Optional[ClinicalStage] = None
    form_factor: Optional[str] = None

    linked_product: Optional[str] = None
    linked_treatment: Optional[str] = None

    figure_number: Optional[str] = None
    section: Optional[str] = None

    table_context: Optional[str] = None
    surrounding_text: Optional[str] = None

    confidence: float = 0.0
    classification_reason: Optional[str] = None

    def should_display(self) -> bool:
        """Only INCLUDE is permitted to display. REVIEW and EXCLUDE are strictly suppressed."""
        return self.display_policy == ImageDisplayPolicy.INCLUDE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "document_id": self.document_id,
            "source_document": self.source_document,
            "page_or_sheet": self.page_or_sheet,
            "row": self.row,
            "column": self.column,
            "image_index": self.image_index,
            "target_url": self.target_url,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "knowledge_type": self.knowledge_type.value if isinstance(self.knowledge_type, KnowledgeType) else str(self.knowledge_type),
            "image_type": self.image_type.value if isinstance(self.image_type, ImageType) else str(self.image_type),
            "image_relevance": self.image_relevance.value if isinstance(self.image_relevance, ImageRelevance) else str(self.image_relevance),
            "display_policy": self.display_policy.value if isinstance(self.display_policy, ImageDisplayPolicy) else str(self.display_policy),
            "clinical_stage": self.clinical_stage.value if isinstance(self.clinical_stage, ClinicalStage) else (str(self.clinical_stage) if self.clinical_stage else None),
            "form_factor": self.form_factor,
            "linked_product": self.linked_product,
            "linked_treatment": self.linked_treatment,
            "figure_number": self.figure_number,
            "section": self.section,
            "table_context": self.table_context,
            "surrounding_text": self.surrounding_text,
            "confidence": self.confidence,
            "classification_reason": self.classification_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ImageProvenance":
        raw_ktype = d.get("knowledge_type", KnowledgeType.OTHER.value)
        k_type = KnowledgeType(raw_ktype) if raw_ktype in KnowledgeType._value2member_map_ else KnowledgeType.OTHER

        raw_type = d.get("image_type", ImageType.OTHER.value)
        img_type = ImageType(raw_type) if raw_type in ImageType._value2member_map_ else ImageType.OTHER

        raw_rel = d.get("image_relevance", ImageRelevance.UNKNOWN.value)
        img_rel = ImageRelevance(raw_rel) if raw_rel in ImageRelevance._value2member_map_ else ImageRelevance.UNKNOWN

        raw_pol = d.get("display_policy", ImageDisplayPolicy.EXCLUDE.value)
        disp_pol = ImageDisplayPolicy(raw_pol) if raw_pol in ImageDisplayPolicy._value2member_map_ else ImageDisplayPolicy.EXCLUDE

        raw_stage = d.get("clinical_stage")
        stage = ClinicalStage(raw_stage) if raw_stage in ClinicalStage._value2member_map_ else None

        return cls(
            image_id=d.get("image_id", ""),
            document_id=d.get("document_id", ""),
            source_document=d.get("source_document", ""),
            page_or_sheet=d.get("page_or_sheet", 1),
            row=d.get("row"),
            column=d.get("column"),
            image_index=d.get("image_index"),
            target_url=d.get("target_url", ""),
            alt_text=d.get("alt_text", ""),
            caption=d.get("caption"),
            knowledge_type=k_type,
            image_type=img_type,
            image_relevance=img_rel,
            display_policy=disp_pol,
            clinical_stage=stage,
            form_factor=d.get("form_factor"),
            linked_product=d.get("linked_product"),
            linked_treatment=d.get("linked_treatment"),
            figure_number=d.get("figure_number"),
            section=d.get("section"),
            table_context=d.get("table_context"),
            surrounding_text=d.get("surrounding_text"),
            confidence=float(d.get("confidence", 0.0)),
            classification_reason=d.get("classification_reason"),
        )

    def format_display_label(self) -> str:
        """
        Renders user-facing markdown label strictly for displayable images.
        Defense-in-depth: Never generates generic 'Foto' fallback.
        """
        if not self.should_display():
            return ""

        if self.image_type == ImageType.PRODUCT:
            return f"Foto Produk - {self.linked_product}" if self.linked_product else "Foto Produk"
        elif self.image_type == ImageType.CLINICAL_BEFORE_AFTER:
            item = self.linked_treatment or self.linked_product or ""
            suffix = f" - {item}" if item else ""
            if self.clinical_stage == ClinicalStage.BEFORE:
                return f"Foto Sebelum Perawatan{suffix}"
            elif self.clinical_stage == ClinicalStage.AFTER:
                return f"Foto Sesudah Perawatan{suffix}"
            else:
                return f"Foto Before & After Perawatan{suffix}"
        elif self.image_type == ImageType.EQUIPMENT:
            item = self.linked_treatment or ""
            return f"Foto Treatment - {item}" if item else "Foto Treatment"
        elif self.image_type == ImageType.SCIENTIFIC_FIGURE:
            desc = self.caption or self.alt_text or self.figure_number or ""
            return f"Gambar Penelitian - {desc}" if desc else "Gambar Penelitian"
        elif self.image_type == ImageType.SCIENTIFIC_GRAPH:
            desc = self.caption or self.alt_text or self.figure_number or ""
            return f"Grafik Penelitian - {desc}" if desc else "Grafik Penelitian"
        elif self.image_type == ImageType.ILLUSTRATION:
            item = self.caption or self.alt_text or ""
            return f"Ilustrasi - {item}" if item else "Ilustrasi"
        else:
            return ""


class ImageProvenanceRegistry:
    """
    Collision-safe registry for image provenance.
    Prevents cross-document metadata pollution:
    - Primary: (document_id, target_url) -> ImageProvenance
    - Secondary: image_id -> ImageProvenance
    - Fallback: (source_document, target_url) -> ImageProvenance
    - Ambiguity-aware URL lookup:
      get_by_url(url, source_document=None):
        0 match -> None
        1 match -> ImageProvenance
        >1 match -> None (ambiguous)
      find_by_url_candidates(url) -> List[ImageProvenance]
    """
    def __init__(self):
        self._by_doc_url: Dict[Tuple[str, str], ImageProvenance] = {}
        self._by_id: Dict[str, ImageProvenance] = {}
        self._by_src_url: Dict[Tuple[str, str], ImageProvenance] = {}
        self._all_by_url: Dict[str, List[ImageProvenance]] = {}

    def register(self, prov: ImageProvenance) -> None:
        if not prov:
            return
        if prov.image_id:
            self._by_id[prov.image_id] = prov
        
        # Only register URL mappings if target_url is not empty (Empty URL Guard)
        if prov.target_url:
            u = prov.target_url
            if prov.document_id:
                self._by_doc_url[(prov.document_id, u)] = prov
                fn = os.path.basename(u)
                if fn:
                    self._by_doc_url[(prov.document_id, fn)] = prov
            if prov.source_document:
                self._by_src_url[(prov.source_document, u)] = prov
                fn = os.path.basename(u)
                if fn:
                    self._by_src_url[(prov.source_document, fn)] = prov
            
            if u not in self._all_by_url:
                self._all_by_url[u] = []
            if prov not in self._all_by_url[u]:
                self._all_by_url[u].append(prov)

    def get(
        self,
        target_url: str,
        document_id: str = "",
        source_document: str = "",
        image_id: str = ""
    ) -> Optional[ImageProvenance]:
        if image_id and image_id in self._by_id:
            return self._by_id[image_id]
        if document_id and target_url and (document_id, target_url) in self._by_doc_url:
            return self._by_doc_url[(document_id, target_url)]
        if document_id and target_url:
            fn = os.path.basename(target_url)
            if (document_id, fn) in self._by_doc_url:
                return self._by_doc_url[(document_id, fn)]
        if source_document and target_url and (source_document, target_url) in self._by_src_url:
            return self._by_src_url[(source_document, target_url)]
        if source_document and target_url:
            fn = os.path.basename(target_url)
            if (source_document, fn) in self._by_src_url:
                return self._by_src_url[(source_document, fn)]
        
        return self.get_by_url(target_url, source_document=source_document)

    def get_by_url(self, target_url: str, source_document: str = "") -> Optional[ImageProvenance]:
        """Returns provenance if unambiguous (exact 1 unique match across all docs), else None."""
        if not target_url:
            return None
        candidates = self.find_by_url_candidates(target_url)
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1 and source_document:
            filtered = [c for c in candidates if c.source_document == source_document]
            if len(filtered) == 1:
                return filtered[0]
        return None

    def find_by_url_candidates(self, target_url: str) -> List[ImageProvenance]:
        """Returns all registered candidates matching this URL or basename for debugging."""
        if not target_url:
            return []
        if target_url in self._all_by_url:
            return list(self._all_by_url[target_url])
        fn = os.path.basename(target_url)
        if fn and fn in self._all_by_url:
            return list(self._all_by_url[fn])
        return []


def classify_image_provenance(
    target_url: str,
    document_id: str = "",
    source_document: str = "",
    knowledge_type: Any = KnowledgeType.OTHER,
    alt_text: str = "",
    caption: str = "",
    table_context: str = "",
    chunk_text: str = "",
    meta: Optional[Dict[str, Any]] = None,
    page_or_sheet: Any = 1,
    row: Optional[int] = None,
    column: Optional[int] = None,
    image_index: Optional[int] = None,
    section: str = ""
) -> ImageProvenance:
    """
    Evidence Precedence Classification for Image Provenance:
    
    1. Explicit metadata (role, knowledge_type, form_factor)
            ↓
    2. Multi-signal Artifact Detection (logo, author portrait, decorative)
            ↓
    3. Knowledge-Type Context Aware Evidence (Product vs SOP vs Scientific Literature)
            ↓
    4. Caption & Alt text & Table context
            ↓
    5. Filename heuristic (LAST RESORT ONLY - and never for generic indices like excel_..._img_3.png)
            ↓
    6. Generic fallback: UNKNOWN + EXCLUDE (Absence of evidence -> DO NOT FABRICATE!)
    """
    m = meta or {}
    
    # Resolve knowledge type
    if isinstance(knowledge_type, KnowledgeType):
        k_type = knowledge_type
    elif isinstance(knowledge_type, str) and knowledge_type in KnowledgeType._value2member_map_:
        k_type = KnowledgeType(knowledge_type)
    else:
        raw_k = str(m.get("knowledge_type", "other")).lower()
        k_type = KnowledgeType(raw_k) if raw_k in KnowledgeType._value2member_map_ else KnowledgeType.OTHER

    # Canonical document identity
    doc_id = document_id or m.get("document_id") or hashlib.sha256((source_document or "doc").encode()).hexdigest()[:12]
    src_doc = source_document or m.get("source_file") or m.get("file_name") or ""
    image_id = generate_stable_image_id(doc_id, page_or_sheet, row, column, target_url, image_index)

    fn_lower = os.path.basename(str(target_url or "")).lower()
    alt_clean = (alt_text or "").strip()
    alt_lower = alt_clean.lower()
    caption_clean = (caption or m.get("caption") or "").strip()
    caption_lower = caption_clean.lower()
    sec_lower = (section or m.get("section") or "").lower()
    tbl_lower = (table_context or "").lower()
    role_upper = str(m.get("role", "")).upper()

    # -------------------------------------------------------------------------
    # 1. EXPLICIT METADATA ROLE (Highest Precedence)
    # -------------------------------------------------------------------------
    if role_upper in ("DOCUMENT_LOGO", "COVER_LOGO", "HEADER_LOGO"):
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.DOCUMENT_LOGO,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=1.0, classification_reason="explicit_role_logo"
        )
    if role_upper in ("AUTHOR_PHOTO", "AUTHOR_PORTRAIT"):
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.AUTHOR_PHOTO,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=1.0, classification_reason="explicit_role_author_photo"
        )
    if role_upper in ("DECORATIVE", "DIVIDER", "ICON"):
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.DECORATIVE,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=1.0, classification_reason="explicit_role_decorative"
        )
    if role_upper == "CLINICAL_BEFORE":
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
            image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
            clinical_stage=ClinicalStage.BEFORE, linked_treatment=m.get("treatment_name") or m.get("treatment"),
            confidence=1.0, classification_reason="explicit_role_clinical_before"
        )
    if role_upper == "CLINICAL_AFTER":
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
            image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
            clinical_stage=ClinicalStage.AFTER, linked_treatment=m.get("treatment_name") or m.get("treatment"),
            confidence=1.0, classification_reason="explicit_role_clinical_after"
        )
    if role_upper == "CLINICAL_BEFORE_AFTER":
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
            image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
            clinical_stage=None, linked_treatment=m.get("treatment_name") or m.get("treatment"),
            confidence=1.0, classification_reason="explicit_role_clinical_ba"
        )
    if role_upper in ("DEVICE_OR_TOOL", "TREATMENT_IMAGE"):
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.EQUIPMENT,
            image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
            linked_treatment=m.get("treatment_name") or m.get("treatment"),
            confidence=1.0, classification_reason="explicit_role_equipment"
        )
    if role_upper in ("PRODUCT_PACKAGING", "PRODUCT"):
        ff = m.get("form_factor") or extract_canonical_form_factor(m.get("product_name", ""))
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
            image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
            form_factor=ff, linked_product=m.get("product_name") or alt_clean,
            confidence=1.0, classification_reason="explicit_role_product"
        )

    # -------------------------------------------------------------------------
    # 2. MULTI-SIGNAL ARTIFACT DETECTION (Non-keyword substring)
    # -------------------------------------------------------------------------
    is_logo_fn = bool(re.search(r'(?:^|[_\-.])(?:logo|publisher_logo|brand_logo|univ_logo|journal_logo)(?:[_\-.]|$)', fn_lower))
    is_logo_text = bool(re.search(r'\b(?:publisher logo|journal logo|springer logo|nature logo|company logo|brand logo|logo erha)\b', alt_lower or caption_lower))
    is_header_footer_logo = any(k in sec_lower for k in ["header", "footer"]) and "logo" in (alt_lower or fn_lower)
    if is_logo_fn or is_logo_text or is_header_footer_logo:
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.DOCUMENT_LOGO,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=0.95, classification_reason="contextual_document_logo"
        )

    is_author_fn = bool(re.search(r'(?:^|[_\-.])(?:headshot|author_photo|portrait|biography_img)(?:[_\-.]|$)', fn_lower))
    is_author_text = bool(re.search(r'\b(?:author portrait|author photo|foto penulis|profile photo|headshot)\b', alt_lower or caption_lower))
    is_author_sec = any(k in sec_lower for k in ["about the author", "author biography", "author information"]) and not re.search(r'\bfig(?:ure)?\b', caption_lower or alt_lower)
    if is_author_fn or is_author_text or is_author_sec:
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.AUTHOR_PHOTO,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=0.95, classification_reason="contextual_author_photo"
        )

    is_decorative_fn = bool(re.search(r'(?:^|[_\-.])(?:divider|separator|bullet|border|spacer)(?:[_\-.]|$)', fn_lower))
    if is_decorative_fn:
        return ImageProvenance(
            image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
            row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
            caption=caption_clean, knowledge_type=k_type, image_type=ImageType.DECORATIVE,
            image_relevance=ImageRelevance.IRRELEVANT, display_policy=ImageDisplayPolicy.EXCLUDE,
            confidence=0.95, classification_reason="contextual_decorative"
        )

    # -------------------------------------------------------------------------
    # 3. KNOWLEDGE-TYPE CONTEXT AWARE CLASSIFICATION
    # -------------------------------------------------------------------------

    # --- A. PRODUCT CATALOG / CHEATSHEET ---
    if k_type == KnowledgeType.PRODUCT:
        active_text = caption_clean or alt_clean
        ff_active = extract_canonical_form_factor(active_text)
        is_product_brand = any(b in (caption_lower or alt_lower) for b in ["erha", "erhair", "acneact", "truwhite", "scalperfect", "produk", "product"])
        if ff_active or is_product_brand:
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                form_factor=ff_active, linked_product=active_text, confidence=0.90,
                classification_reason="explicit_alt_form_factor"
            )

        if tbl_lower:
            ff_tbl = extract_canonical_form_factor(tbl_lower)
            if ff_tbl or any(k in tbl_lower for k in ["exfoliating", "produk", "product"]):
                return ImageProvenance(
                    image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                    row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                    caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
                    image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                    form_factor=ff_tbl, linked_product=active_text or m.get("product_name"),
                    table_context=table_context, confidence=0.85,
                    classification_reason="table_context_form_factor"
                )

        if sec_lower and any(k in sec_lower for k in ["produk", "product", "katalog", "formularium", "daftar produk"]) and active_text:
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                form_factor=extract_canonical_form_factor(sec_lower), linked_product=active_text,
                section=section, confidence=0.75, classification_reason="section_context_product"
            )

    # --- B. TREATMENT SOP ---
    elif k_type == KnowledgeType.TREATMENT_SOP:
        active_text = caption_clean or alt_clean
        comb_text = f"{caption_lower} {alt_lower} {tbl_lower}"
        
        # Clinical Before & After
        if any(k in comb_text for k in ["before & after", "before after", "sebelum & sesudah", "sebelum sesudah", "before-after"]):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                clinical_stage=None, linked_treatment=m.get("treatment_name"), confidence=0.85,
                classification_reason="sop_clinical_ba"
            )
        if any(k in comb_text for k in ["sebelum", "before"]) and not extract_canonical_form_factor(active_text):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                clinical_stage=ClinicalStage.BEFORE, linked_treatment=m.get("treatment_name"), confidence=0.85,
                classification_reason="sop_clinical_before"
            )
        if any(k in comb_text for k in ["sesudah", "after", "setelah"]) and not extract_canonical_form_factor(active_text):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                clinical_stage=ClinicalStage.AFTER, linked_treatment=m.get("treatment_name"), confidence=0.85,
                classification_reason="sop_clinical_after"
            )

        # Equipment / Device
        if any(k in comb_text for k in ["alat", "device", "mesin", "peralatan", "laser", "alat utama", "handpiece"]):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.EQUIPMENT,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                linked_treatment=m.get("treatment_name"), confidence=0.85,
                classification_reason="sop_equipment"
            )

        # Product used in SOP
        ff_sop = extract_canonical_form_factor(active_text)
        if ff_sop:
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                form_factor=ff_sop, linked_product=active_text, confidence=0.85,
                classification_reason="sop_product_used"
            )

    # --- C. SCIENTIFIC LITERATURE ---
    elif k_type == KnowledgeType.SCIENTIFIC_LITERATURE:
        comb_text = f"{caption_clean} {alt_clean}"
        comb_lower = comb_text.lower()

        # Scientific Graph
        if re.search(r'\b(?:chart|graph|curve|plot|histogram|kurva|bar chart|scatter plot)\b', comb_lower):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.SCIENTIFIC_GRAPH,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                confidence=0.85, classification_reason="scientific_graph_caption"
            )

        # Scientific Figure
        if re.search(r'\b(?:figure|fig\.|gambar)\s*\d*\b', comb_lower):
            m_fig = re.search(r'\b(figure\s*\d+|fig\.\s*\d+)\b', comb_lower, re.I)
            fig_num = m_fig.group(1).title() if m_fig else None
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.SCIENTIFIC_FIGURE,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                figure_number=fig_num, confidence=0.85, classification_reason="scientific_figure_caption"
            )

        # Scientific Illustration / Pathway
        if re.search(r'\b(?:illustration|flowchart|pathway|scheme|mekanisme|skema)\b', comb_lower):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.ILLUSTRATION,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                confidence=0.80, classification_reason="scientific_illustration"
            )

    # --- D. FAQ / OTHER (Cross-document fallback detection) ---
    else:
        active_text = caption_clean or alt_clean
        ff_other = extract_canonical_form_factor(active_text)
        is_product_brand = any(b in (caption_lower or alt_lower) for b in ["erha", "erhair", "acneact", "truwhite", "scalperfect", "produk", "product"])
        if ff_other or is_product_brand:
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.PRODUCT,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                form_factor=ff_other, linked_product=active_text, confidence=0.80,
                classification_reason="general_product_detected"
            )
        if any(k in (caption_lower or alt_lower) for k in ["before & after", "before after", "sebelum & sesudah"]):
            return ImageProvenance(
                image_id=image_id, document_id=doc_id, source_document=src_doc, page_or_sheet=page_or_sheet,
                row=row, column=column, image_index=image_index, target_url=target_url, alt_text=alt_clean,
                caption=caption_clean, knowledge_type=k_type, image_type=ImageType.CLINICAL_BEFORE_AFTER,
                image_relevance=ImageRelevance.RELEVANT, display_policy=ImageDisplayPolicy.INCLUDE,
                confidence=0.80, classification_reason="general_clinical_ba_detected"
            )

    # -------------------------------------------------------------------------
    # 4. DEFAULT FALLBACK: UNKNOWN + EXCLUDE (Absence of Evidence -> DO NOT FABRICATE!)
    # -------------------------------------------------------------------------
    return ImageProvenance(
        image_id=image_id,
        document_id=doc_id,
        source_document=src_doc,
        page_or_sheet=page_or_sheet,
        row=row,
        column=column,
        image_index=image_index,
        target_url=target_url,
        alt_text=alt_clean,
        caption=caption_clean,
        knowledge_type=k_type,
        image_type=ImageType.OTHER,
        image_relevance=ImageRelevance.UNKNOWN,
        display_policy=ImageDisplayPolicy.EXCLUDE,
        clinical_stage=None,
        form_factor=None,
        linked_product=None,
        linked_treatment=None,
        confidence=0.0,
        classification_reason="insufficient_evidence"
    )


