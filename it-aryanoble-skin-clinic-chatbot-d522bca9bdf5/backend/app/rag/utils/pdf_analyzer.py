import os
import re
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from loguru import logger

try:
    import pymupdf as fitz
except ImportError:
    import fitz


class PDFDocumentType(str, Enum):
    DIGITAL_TEXT = "digital_text"          # Scientific papers, Word PDF exports, SOPs with selectable text
    FLATTENED_DESIGN = "flattened_design"  # PowerPoint / Canva Print-to-PDF, product brochures, catalogs
    SCANNED_IMAGE = "scanned_image"        # Physical scanner/camera, 1 full-page raster bitmap
    HYBRID = "hybrid"                      # Mixed pages (some text, some scanned)


class PDFAnalysisResult(BaseModel):
    file_name: str
    page_count: int
    total_pure_chars: int
    text_density: float          # avg pure text chars per page
    pages_with_fonts: int
    font_presence_ratio: float   # ratio of sample pages that contain digital font streams
    total_images: int
    avg_images_per_page: float
    total_drawings: int
    avg_drawings_per_page: float
    avg_aspect_ratio: float = 1.0
    pdf_type: PDFDocumentType
    analysis_details: str


def clean_extracted_text(text: Optional[str]) -> str:
    """
    Removes markdown image tags, URLs, HTML tags, and synthetic slide/page headings
    to calculate pure knowledge text content. Prevents image URL strings and synthetic
    headers from being counted as knowledge text characters.
    """
    if not text:
        return ""
    # 1. Strip markdown image tags ![alt](url)
    cleaned = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 2. Strip standalone URLs
    cleaned = re.sub(r'https?://\S+|/api/storage/\S+', '', cleaned)
    # 3. Strip HTML tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    # 4. Strip synthetic slide headings: "## Slide 1", "## Slide 12: ..."
    cleaned = re.sub(r'(?m)^\s*##\s*Slide\s*\d+.*$', '', cleaned)
    return cleaned.strip()



def analyze_pdf_complexity(doc: fitz.Document, file_path: str = "") -> PDFAnalysisResult:
    """
    Lightweight document-level PDF complexity analyzer (< 20ms).
    Evaluates pure text characters, font existence, embedded image objects,
    and vector drawing paths across document sample pages to classify
    the PDF into DIGITAL_TEXT, FLATTENED_DESIGN, SCANNED_IMAGE, or HYBRID.
    """
    page_count = len(doc)
    if page_count <= 6:
        sample_indices = list(range(page_count))
    else:
        # Strided representative sampling: beginning, middle, and end
        mid = page_count // 2
        sample_indices = sorted(list(set([0, 1, max(0, mid - 1), mid, max(0, page_count - 2), page_count - 1])))

    sample_pages = [doc[idx] for idx in sample_indices if idx < page_count]
    sample_size = len(sample_pages)

    total_pure_chars = 0
    pages_with_fonts = 0
    pages_with_text = 0
    total_images = 0
    total_drawings = 0
    total_aspect_ratio = 0.0

    for page in sample_pages:
        raw_text = page.get_text("text") or ""
        pure = clean_extracted_text(raw_text)
        pure_len = len(pure)
        total_pure_chars += pure_len
        if pure_len > 30:
            pages_with_text += 1

        fonts = page.get_fonts()
        if fonts and len(fonts) > 0:
            pages_with_fonts += 1

        total_images += len(page.get_images(full=True))
        total_drawings += len(page.get_drawings())

        pw = page.rect.width
        ph = page.rect.height
        total_aspect_ratio += (pw / max(1.0, ph))

    avg_chars = total_pure_chars / max(1, sample_size)
    font_ratio = pages_with_fonts / max(1, sample_size)
    avg_images = total_images / max(1, sample_size)
    avg_drawings = total_drawings / max(1, sample_size)
    avg_aspect_ratio = total_aspect_ratio / max(1, sample_size)

    # Document-Level Universal Decision Logic (First Principles)
    # -------------------------------------------------------------------------
    # 1. HIGH-DENSITY DIGITAL DOCUMENT (Scientific journals, SOPs, clinical protocols, dense tables)
    # Even if in landscape orientation (e.g. A4 landscape tables with grid lines) or containing
    # image covers (font_ratio >= 0.65), dense text indicates a structured digital document.
    # PyMuPDF extracts this natively in milliseconds with 100% accuracy.
    if avg_chars >= 800 and font_ratio >= 0.65:
        pdf_type = PDFDocumentType.DIGITAL_TEXT
        details = (
            f"Dense Digital Text PDF: avg_chars={avg_chars:.1f}, font_ratio={font_ratio:.2f}, "
            f"aspect_ratio={avg_aspect_ratio:.2f}, avg_drawings={avg_drawings:.1f}"
        )

    # 2. PRESENTATION SLIDES & VISUAL CANVA CATALOGS
    # Widescreen / landscape orientation with sparse card-like text (< 800 chars/page)
    # alongside embedded product graphics or complex card vectors.
    # Requires FlattenedDesignParser (RapidOCR + multimodal vision) for spatial asset binding.
    elif avg_aspect_ratio >= 1.25 and (avg_chars < 800) and (avg_images >= 0.8 or avg_drawings >= 5):
        pdf_type = PDFDocumentType.FLATTENED_DESIGN
        details = (
            f"Presentation Slide Deck / Visual Catalog: aspect_ratio={avg_aspect_ratio:.2f}, "
            f"avg_images={avg_images:.1f}, avg_drawings={avg_drawings:.1f}, avg_chars={avg_chars:.1f}"
        )

    # 3. STANDARD DIGITAL TEXT (Word exports, papers, books, reports with moderate text density)
    elif font_ratio >= 0.5 and avg_chars >= 80:
        pdf_type = PDFDocumentType.DIGITAL_TEXT
        details = (
            f"Digital Text PDF: avg_chars={avg_chars:.1f}, font_ratio={font_ratio:.2f}, "
            f"aspect_ratio={avg_aspect_ratio:.2f}"
        )

    # 4. FLATTENED DESIGN (Zero or negligible text, or no digital fonts, but vector drawings / multiple graphics)
    elif (font_ratio < 0.2 or avg_chars < 50) and (avg_images >= 2 or avg_drawings > 30):
        pdf_type = PDFDocumentType.FLATTENED_DESIGN
        details = (
            f"Flattened Design PDF: avg_chars={avg_chars:.1f}, font_ratio={font_ratio:.2f}, "
            f"avg_images={avg_images:.1f}, avg_drawings={avg_drawings:.1f}"
        )

    # 5. SCANNED IMAGE (Physical scanner or camera photo: negligible text, single full-page bitmap)
    elif (font_ratio < 0.2 or avg_chars < 50) and avg_drawings <= 10 and avg_images <= 1.5:
        pdf_type = PDFDocumentType.SCANNED_IMAGE
        details = (
            f"Scanned Image PDF: avg_chars={avg_chars:.1f}, font_ratio={font_ratio:.2f}, "
            f"avg_images={avg_images:.1f}"
        )

    # 6. HYBRID (Mixed document: some digital text pages, some scanned/image-only pages)
    elif 0 < pages_with_text < sample_size:
        pdf_type = PDFDocumentType.HYBRID
        details = f"Hybrid PDF: {pages_with_text}/{sample_size} pages have text"

    # 7. FALLBACK
    elif total_pure_chars >= 50:
        pdf_type = PDFDocumentType.DIGITAL_TEXT
        details = f"Fallback Digital Text: total_chars={total_pure_chars}"
    else:
        pdf_type = PDFDocumentType.FLATTENED_DESIGN
        details = "Fallback Flattened Design (no selectable text detected)"

    file_name = os.path.basename(file_path) if file_path else "unknown.pdf"
    logger.info(f"📑 [PDF-ANALYZER] {file_name} -> {pdf_type.value} ({details})")

    return PDFAnalysisResult(
        file_name=file_name,
        page_count=page_count,
        total_pure_chars=total_pure_chars,
        text_density=avg_chars,
        pages_with_fonts=pages_with_fonts,
        font_presence_ratio=font_ratio,
        total_images=total_images,
        avg_images_per_page=avg_images,
        total_drawings=total_drawings,
        avg_drawings_per_page=avg_drawings,
        pdf_type=pdf_type,
        analysis_details=details
    )
