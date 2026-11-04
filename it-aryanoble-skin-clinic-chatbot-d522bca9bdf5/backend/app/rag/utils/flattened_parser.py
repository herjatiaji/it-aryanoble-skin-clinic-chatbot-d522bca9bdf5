import os
import re
import time
import base64
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from loguru import logger

try:
    import pymupdf as fitz
except ImportError:
    import fitz

try:
    from rapidocr.utils.typings import EngineType
    from rapidocr.main import RapidOCR
except ImportError:
    EngineType = None
    RapidOCR = None

from app.rag.utils.spatial_associator import SpatialImageTextAssociator
from app.rag.canonical import PDFContext, ImageDisplayPolicy, ImageProvenance
from app.services.storage import upload_image


import threading

_GLOBAL_OCR_LOCK = threading.Lock()
_SHARED_RAPID_OCR = None


def get_shared_rapid_ocr() -> Optional[Any]:
    global _SHARED_RAPID_OCR
    if RapidOCR is None:
        logger.warning("RapidOCR package is not installed. OCR extraction will be unavailable.")
        return None
    if _SHARED_RAPID_OCR is None:
        logger.info("Initializing Shared RapidOCR instance (PyTorch CPU)...")
        params = {
            "Det.engine_type": EngineType.TORCH,
            "Cls.engine_type": EngineType.TORCH,
            "Rec.engine_type": EngineType.TORCH,
        }
        _SHARED_RAPID_OCR = RapidOCR(params=params)
    return _SHARED_RAPID_OCR


from app.rag.utils.source_coverage import missing_lines, text_coverage

# Longest side (px) an extracted image asset is kept at: enough for chat display and image analysis,
# while bounding memory per page on a small server.
MAX_ASSET_SIDE_PX = 2048

# A vision transcription covering less of the page's PDF text layer than this is retried once
TEXT_LAYER_MIN_COVERAGE = 0.85


class FlattenedDesignParser:
    """
    Specialized, lightweight parser for FLATTENED_DESIGN_PDF and SCANNED_IMAGE_PDF.
    Uses PyMuPDF rendering (150 DPI) + RapidOCR (PyTorch CPU backend) + Spatial Image Association.
    Executes in ~10-15s per page with < 250MB RAM footprint (preventing heavy Docling OOM).
    Synchronized with _GLOBAL_OCR_LOCK to prevent CPU starvation on 2 vCPU servers.
    """

    def __init__(self):
        self.ocr = get_shared_rapid_ocr()
        self.associator = SpatialImageTextAssociator()

    @staticmethod
    def _text_layer_coverage(text_layer: str, markdown: str) -> Optional[float]:
        """Share of the text layer's words present in the transcription; None when the page has no text layer."""
        return text_coverage(text_layer, markdown)

    @staticmethod
    def _text_layer_missing_lines(text_layer: str, markdown: str) -> List[str]:
        """Text-layer lines whose words are mostly absent from the transcription."""
        return missing_lines(text_layer, markdown)

    @staticmethod
    def _raw_image_digest(doc, xref) -> Optional[str]:
        """Content identity of an embedded image from its raw PDF stream, without decoding it."""
        if not xref:
            return None
        try:
            raw = doc.xref_stream_raw(xref)
        except Exception:
            return None
        if not raw or len(raw) <= 100:
            return None
        import hashlib
        return hashlib.sha256(raw).hexdigest()

    def parse_pdf(
        self,
        file_path: str,
        document_id: str = "",
        max_pages: int = 1000,
        pdf_context: PDFContext = PDFContext.FLATTENED_DESIGN
    ) -> List[Dict[str, Any]]:
        """
        Parses flattened design PDF pages:
        1. Renders page at 120 DPI for optimal RAM efficiency and sharp text recognition.
        2. Concurrently calls Vision LLM in bounded batches (4 workers) for structured slide extraction.
        3. Identifies embedded images and computes spatial association.
        4. Links product container photos with canonical product headings.
        5. Returns list of page dicts: [{'page': 1, 'text': '...', 'provenance': [...]}]
        """
        if not os.path.exists(file_path):
            logger.error(f"FlattenedDesignParser: file not found: {file_path}")
            return []

        doc = fitz.open(file_path)
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages)

        if total_pages > max_pages:
            logger.warning(
                f"[FLATTENED-PARSER] Document '{os.path.basename(file_path)}' has {total_pages} pages, "
                f"capping at {max_pages} pages for memory & latency stability. Truncation flagged."
            )

        parsed_pages: List[Dict[str, Any]] = []
        seen_hashes: Dict[str, str] = {}   # content-hash -> uploaded url (reuse identical assets)
        vision_cache: Dict[str, Dict[str, Any]] = {}
        batch_size = 4

        # Pre-scan: Identify repeated master template assets (header logos, banners, watermarks, footers)
        # An image appearing repeatedly across multiple pages of a deck is mathematically a slide master graphic, not a single product photo.
        # Images are identified by their raw (still encoded) PDF stream: decoding every image of the document
        # just to hash it cost ~350 MB on a 32-page deck (1,075 images), which a 2.9 GB server cannot afford.
        import hashlib
        image_page_counts: Dict[str, set] = {}
        if pages_to_process >= 3:
            for p_i in range(pages_to_process):
                try:
                    p = doc[p_i]
                    for img_info in p.get_images(full=True):
                        h = self._raw_image_digest(doc, img_info[0])
                        if h:
                            image_page_counts.setdefault(h, set()).add(p_i)
                except Exception:
                    pass

        template_digests = {
            h for h, pages in image_page_counts.items()
            if len(pages) >= 3 or (pages_to_process >= 4 and len(pages) / pages_to_process >= 0.25)
        }
        if template_digests:
            logger.info(f"[FLATTENED-PARSER] Pre-scan identified {len(template_digests)} repeated template assets (logos/headers/footers) across document.")

        try:
            for batch_start in range(0, pages_to_process, batch_size):
                # A cancelled (deleted) document stops here instead of holding the single ingestion slot and
                # spending vision calls on its remaining pages; the caller discards the partial result.
                from app.rag.router import CURRENT_INGESTION_ID, is_ingestion_cancelled
                ingestion_id = document_id or CURRENT_INGESTION_ID.get()
                if ingestion_id and is_ingestion_cancelled(ingestion_id):
                    logger.info(f"[FLATTENED-PARSER] '{ingestion_id}' was cancelled; stopping at page {batch_start + 1}/{pages_to_process}.")
                    break
                batch_end = min(batch_start + batch_size, pages_to_process)
                batch_indices = list(range(batch_start, batch_end))

                # Step 1: Rapid main-thread rendering of page buffers (low RAM footprint: ~120KB JPEG each)
                batch_payloads = []
                for p_idx in batch_indices:
                    page = doc[p_idx]
                    p_num = p_idx + 1
                    try:
                        pix = page.get_pixmap(dpi=120)
                        raw_bytes = pix.tobytes("jpeg")
                        del pix
                        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                        del raw_bytes
                        batch_payloads.append((p_idx, p_num, b64_str, page.get_text()))
                    except Exception as render_err:
                        logger.warning(f"[FLATTENED-PARSER] Page {p_num} render failed: {render_err}")
                        batch_payloads.append((p_idx, p_num, None, ""))

                # Step 2: Concurrently call Vision LLM across the batch (Bounded concurrency: 4 workers)
                vision_results = {}
                with ThreadPoolExecutor(max_workers=min(4, len(batch_payloads))) as executor:
                    future_to_pidx = {}
                    for p_idx, p_num, b64_str, page_text in batch_payloads:
                        if b64_str:
                            f = executor.submit(self.extract_slide_structured_vision, page=None, page_num=p_num, base64_img=b64_str, text_layer=page_text)
                            future_to_pidx[f] = p_idx
                        else:
                            vision_results[p_idx] = None
                    for f in as_completed(future_to_pidx):
                        pidx = future_to_pidx[f]
                        try:
                            vision_results[pidx] = f.result()
                        except Exception as e:
                            logger.warning(f"[FLATTENED-PARSER] Vision batch task error on page {pidx+1}: {e}")
                            vision_results[pidx] = None

                # Completeness against the PDF text layer: a vision transcription occasionally drops whole
                # rows or blocks. When it misses much of the page's own text, ask once more and keep the
                # more complete result.
                page_texts = {p_idx: page_text for p_idx, _, _, page_text in batch_payloads}
                for p_idx, p_num, b64_str, page_text in batch_payloads:
                    data = vision_results.get(p_idx)
                    if not data or not b64_str:
                        continue
                    coverage = self._text_layer_coverage(page_text, data.get("raw_markdown_representation") or "")
                    if coverage is not None and coverage < TEXT_LAYER_MIN_COVERAGE:
                        logger.info(f"[FLATTENED-PARSER] Page {p_num}: vision covers {coverage:.0%} of the text layer; retrying once.")
                        try:
                            retry = self.extract_slide_structured_vision(page=None, page_num=p_num, base64_img=b64_str, text_layer=page_text)
                        except Exception as retry_err:
                            logger.warning(f"[FLATTENED-PARSER] Page {p_num}: retry failed: {retry_err}")
                            retry = None
                        if retry and (self._text_layer_coverage(page_text, retry.get("raw_markdown_representation") or "") or 0) > coverage:
                            vision_results[p_idx] = retry

                del batch_payloads

                # Step 3: Process embedded image assets, fallback OCR if needed, MinIO uploads, and assembly
                for p_idx in batch_indices:
                    page = doc[p_idx]
                    page_num = p_idx + 1
                    pw = page.rect.width
                    ph = page.rect.height
                    vision_data = vision_results.get(p_idx)

                    try:
                        # 1. Embedded image assets from page
                        embedded_imgs: List[Dict[str, Any]] = []
                        for img_info in page.get_images(full=True):
                            xref = img_info[0]
                            smask = img_info[1] if len(img_info) > 1 else 0
                            rects = page.get_image_rects(xref)
                            if not rects:
                                continue
    
                            rect = rects[0]
                            try:
                                base = doc.extract_image(xref)
                                w = base.get("width", int(abs(rect.x1 - rect.x0)))
                                h = base.get("height", int(abs(rect.y1 - rect.y0)))
                                raw_bytes = base.get("image", b"")
                                ext = base.get("ext", "jpeg")
    
                                try:
                                    pm = fitz.Pixmap(doc, xref)
                                    if pm.colorspace and pm.colorspace.n > 3:
                                        pm = fitz.Pixmap(fitz.csRGB, pm)
                                    if smask:
                                        mask_pm = fitz.Pixmap(doc, smask)
                                        if pm.alpha:
                                            pm = fitz.Pixmap(fitz.csRGB, pm)
                                        pm = fitz.Pixmap(pm, mask_pm)
                                        del mask_pm
                                    # Slide backgrounds reach 6000x3000 px; kept at full size every image of a
                                    # page is held as a multi-MB PNG. Halve until the long side fits the
                                    # largest size the chat widget and the image analysis use.
                                    while max(pm.width, pm.height) > MAX_ASSET_SIDE_PX:
                                        pm.shrink(1)
                                    raw_bytes = pm.tobytes("png")
                                    ext = "png"
                                    w, h = pm.width, pm.height
                                    del pm
                                except Exception as pm_err:
                                    logger.debug(f"Pixmap re-render failed for xref {xref}: {pm_err}")
    
                                embedded_imgs.append({
                                    "xref": xref,
                                    "rect": rect,
                                    "width": w,
                                    "height": h,
                                    "target_url": f"pending://{page_num}/{xref}",
                                    "source_document": os.path.basename(file_path),
                                    "bytes": raw_bytes,
                                    "ext": ext
                                })
                            except Exception as img_err:
                                logger.debug(f"Failed extracting image xref {xref} on page {page_num}: {img_err}")
    
                        ocr_blocks: List[Dict[str, Any]] = []
                        provenance_list: List[ImageProvenance] = []
    
                        if not vision_data:
                            # 1. Native Digital Text Extraction (Canva, PowerPoint, Keynote digital exports)
                            # Native digital text has 100% spelling precision and executes in 0ms CPU without OCR latency
                            raw_blocks = page.get_text("blocks") or []
                            digital_blocks = []
                            for b in raw_blocks:
                                if b[6] == 0:  # text block
                                    txt_clean = (b[4] or "").strip()
                                    if len(txt_clean) >= 2:
                                        digital_blocks.append({
                                            "text": txt_clean,
                                            "bbox": [b[0], b[1], b[2], b[3]],
                                            "score": 1.0
                                        })

                            has_digital = len(digital_blocks) >= 2 and sum(len(b["text"]) for b in digital_blocks) >= 25

                            if has_digital:
                                ocr_blocks = digital_blocks
                                logger.info(
                                    f"[FLATTENED-PARSER] Page {page_num}/{pages_to_process}: Using instant native digital "
                                    f"text blocks ({len(ocr_blocks)} blocks, 100% precision, 0ms CPU)"
                                )
                            elif self.ocr:
                                # 2. Fallback to RapidOCR for true rasterized / scanned bitmaps
                                pix = page.get_pixmap(dpi=120)
                                img_bytes = pix.tobytes("png")

                                t0 = time.time()
                                with _GLOBAL_OCR_LOCK:
                                    ocr_out = self.ocr(img_bytes)
                                ocr_ms = int((time.time() - t0) * 1000)
                                time.sleep(0.005)

                                if hasattr(ocr_out, "txts") and ocr_out.txts:
                                    scale_x = pw / max(1.0, pix.width)
                                    scale_y = ph / max(1.0, pix.height)

                                    for b_box, txt, score in zip(ocr_out.boxes, ocr_out.txts, ocr_out.scores):
                                        xs = [pt[0] * scale_x for pt in b_box]
                                        ys = [pt[1] * scale_y for pt in b_box]
                                        rect_box = [min(xs), min(ys), max(xs), max(ys)]
                                        ocr_blocks.append({
                                            "text": txt.strip(),
                                            "bbox": rect_box,
                                            "score": float(score)
                                        })

                                logger.info(
                                    f"[FLATTENED-PARSER] Page {page_num}/{pages_to_process}: OCR fallback extracted {len(ocr_blocks)} "
                                    f"elements in {ocr_ms}ms"
                                )
    
                            provenance_list = self.associator.associate_page_elements(
                                document_id=document_id,
                                page_num=page_num,
                                page_width=pw,
                                page_height=ph,
                                ocr_blocks=ocr_blocks,
                                embedded_images=embedded_imgs,
                                pdf_context=pdf_context
                            )
    
                            provenance_list = self._apply_vision_gate(
                                provenance_list=provenance_list,
                                embedded_imgs=embedded_imgs,
                                ocr_blocks=ocr_blocks,
                                page_num=page_num,
                                document_id=document_id,
                                seen_hashes=seen_hashes,
                                vision_cache=vision_cache,
                            )
    
                            assembled_markdown = self._assemble_catalog_markdown(
                                ocr_blocks=ocr_blocks,
                                provenance_list=provenance_list,
                                page_width=pw,
                                page_height=ph,
                                page=page,
                                page_num=page_num
                            )
                        elif vision_data and embedded_imgs:
                            # Upload valid substantive candidate images to MinIO with strict filtering:
                            # 1. Pixel area >= 35,000 and min_dim >= 110 (supports tall lip serums / toners while rejecting icons)
                            # 2. Aspect ratio between 0.22 and 3.2 (eliminates wide logo strips, banners, dividers)
                            # 3. Flat decorative graphic filter (PIL color analysis eliminates vector logos/bars)
                            # 4. Vision gate verification (distinguishes real physical product packaging from logos)
                            import hashlib
                            from app.rag.utils.parser import _check_flat_decorative_graphic, verify_and_classify_visual_candidate

                            page_ctx = (vision_data.get("slide_title") or "") + " " + (vision_data.get("raw_markdown_representation") or "")[:600]

                            for cand in embedded_imgs:
                                raw = cand.get("bytes") or b""
                                if self._raw_image_digest(doc, cand.get("xref")) in template_digests:
                                    logger.debug(f"[FLATTENED-PARSER] Page {page_num}: Excluded repeated master template graphic/logo (xref {cand.get('xref')}).")
                                    continue

                                w = int(cand.get("width") or 0)
                                h = int(cand.get("height") or 0)
                                area = w * h
                                aspect = (w / max(1, h)) if h > 0 else 1.0

                                if len(raw) < 3000 or area < 25000 or min(w, h) < 90:
                                    continue
                                if aspect > 2.3 or aspect < 0.22:
                                    continue

                                is_flat, desc = _check_flat_decorative_graphic(raw)
                                if is_flat:
                                    reason = desc.get("reason", "")
                                    # Studio product packaging cutouts placed on transparent/white canvas naturally
                                    # have high background dominance. If candidate has substantial area (>= 25000),
                                    # delegate authoritative classification to Vision Gate instead of prematurely dropping.
                                    if not ("dominance" in reason or "pill/swoosh" in reason):
                                        continue

                                v_res = verify_and_classify_visual_candidate(
                                    img_bytes=raw,
                                    img_ext=cand.get("ext", "png"),
                                    page_context=page_ctx,
                                    fallback_title=vision_data.get("slide_title") or f"Slide {page_num}",
                                    cache=vision_cache,
                                    timeout=10.0,
                                )
                                if not v_res.get("is_relevant"):
                                    continue

                                digest = hashlib.sha256(raw).hexdigest()
                                url = seen_hashes.get(digest)
                                if not url:
                                    ext = cand.get("ext", "png")
                                    fname = f"pdf_flat_{document_id or 'doc'}_p{page_num}_{cand.get('xref')}.{ext}"
                                    try:
                                        url = upload_image(raw, fname, content_type=f"image/{ext}").get("image_url") or ""
                                    except Exception as up_err:
                                        logger.debug(f"Image upload note on page {page_num}: {up_err}")
                                        url = ""
                                    if url:
                                        seen_hashes[digest] = url
                                if url:
                                    prod_label = v_res.get("product_name") or vision_data.get("slide_title") or f"Slide {page_num}"
                                    provenance_list.append(ImageProvenance(
                                        image_id=f"{document_id or 'doc'}_p{page_num}_{cand.get('xref')}",
                                        image_index=cand.get("xref", 0),
                                        source_document=os.path.basename(file_path),
                                        page_or_sheet=page_num,
                                        display_policy=ImageDisplayPolicy.INCLUDE,
                                        target_url=url,
                                        linked_product=prod_label
                                    ))
                            assembled_markdown = vision_data.get("raw_markdown_representation") or ""
                        else:
                            assembled_markdown = (vision_data or {}).get("raw_markdown_representation") or ""

                        # Never lose printed text silently: lines of the text layer still absent from the
                        # transcription are kept under the page content.
                        missing_lines = self._text_layer_missing_lines(page_texts.get(p_idx, ""), assembled_markdown)
                        if assembled_markdown and missing_lines:
                            assembled_markdown += "\n\n**Teks lain pada halaman ini:**\n" + "\n".join(f"- {l}" for l in missing_lines)

                        image_urls = [
                            p.target_url for p in provenance_list if p.should_display() and p.target_url
                        ]
    
                        slide_archetype = (vision_data or {}).get("slide_archetype", "GENERAL_CONTENT")
                        # Contextual image placement
                        if image_urls and assembled_markdown and not any(u in assembled_markdown for u in image_urls):
                            if slide_archetype == "PRODUCT_CATALOG":
                                # Primary product slide: place photo(s) directly beneath product heading
                                active_p = [p for p in provenance_list if p.should_display() and p.target_url]
                                if len(active_p) == 1:
                                    first_p = active_p[0]
                                    lbl = first_p.linked_product or (vision_data or {}).get("slide_title") or f"Slide {page_num}"
                                    clean_lbl = re.sub(r'^(?:Foto\s+Produk\s*[-–:]\s*)+', '', lbl, flags=re.IGNORECASE).strip()
                                    img_tag = f"![Foto Produk - {clean_lbl}]({first_p.target_url})"
                                    head_m = re.search(r'^(#{1,3}\s+[^\n]+)', assembled_markdown)
                                    if head_m:
                                        assembled_markdown = re.sub(r'^(#{1,3}\s+[^\n]+)', r'\1\n' + img_tag + '\n', assembled_markdown, count=1)
                                    else:
                                        assembled_markdown = f"{img_tag}\n\n{assembled_markdown}"
                                else:
                                    # Multiple product photos on slide: place each under its respective heading if present
                                    placed_urls = set()
                                    for p in active_p:
                                        p_name = (p.linked_product or "").strip()
                                        clean_p_name = re.sub(r'^(?:Foto\s+Produk\s*[-–:]\s*)+', '', p_name, flags=re.IGNORECASE).strip()
                                        if clean_p_name:
                                            # Match heading containing product name
                                            escaped_p = re.escape(clean_p_name.split('(')[0].strip() if '(' in clean_p_name else clean_p_name)
                                            m = re.search(rf'(#{1,3}\s+.*{escaped_p}.*)', assembled_markdown, re.IGNORECASE)
                                            if m:
                                                tag = f"![Foto Produk - {clean_p_name}]({p.target_url})"
                                                assembled_markdown = assembled_markdown.replace(m.group(1), f"{m.group(1)}\n{tag}\n", 1)
                                                placed_urls.add(p.target_url)
                                    remaining = []
                                    for p in active_p:
                                        if p.target_url not in placed_urls:
                                            p_label = (p.linked_product or "Foto Produk").strip()
                                            clean_label = re.sub(r'^(?:Foto\s+Produk\s*[-–:]\s*)+', '', p_label, flags=re.IGNORECASE).strip() or "Foto Produk"
                                            remaining.append(f"![{clean_label}]({p.target_url})")
                                    if remaining:
                                        assembled_markdown = f"{assembled_markdown}\n\n" + "\n\n".join(remaining)
                            elif slide_archetype == "MATRIX_OR_TABLE":
                                # For overview matrix tables: keep table layout clean and uncorrupted.
                                # Provenance assets are preserved in provenance_list for product entity lookup.
                                pass
                            else:
                                img_md_lines = [f"![{p.linked_product or 'Foto Produk'}]({p.target_url})" for p in provenance_list if p.should_display() and p.target_url]
                                if img_md_lines:
                                    assembled_markdown = f"{assembled_markdown}\n\n" + "\n\n".join(img_md_lines)
    
                        domain_val = (vision_data or {}).get("domain") or "general"
                        is_disc_val = bool((vision_data or {}).get("is_discontinued", False))
                        target_ind_val = (vision_data or {}).get("target_indications") or []
                        routine_steps_val = (vision_data or {}).get("routine_steps") or []
                        product_entities_val = (vision_data or {}).get("product_entities") or []
                        slide_title_val = (vision_data or {}).get("slide_title") or f"Slide {page_num}"
    
                        parsed_pages.append({
                            "page": page_num,
                            "text": assembled_markdown,
                            "slide_title": slide_title_val,
                            "domain": domain_val,
                            "clinical_domain": domain_val,
                            "is_discontinued": is_disc_val,
                            "target_indications": target_ind_val,
                            "routine_steps": routine_steps_val,
                            "product_entities": product_entities_val,
                            "image_urls": image_urls,
                            "image_url": image_urls[0] if image_urls else None,
                            "is_flattened": True,
                            "provenance": [p.to_dict() for p in provenance_list]
                        })
                    except Exception as page_err:
                        logger.warning(f"[FLATTENED-PARSER] Warning: page {page_num} failed to parse, continuing: {page_err}")

                # Periodic garbage collection for memory stability on 2.9GB RAM
                if batch_end % 40 == 0 or batch_end == pages_to_process:
                    gc.collect()

        finally:
            doc.close()

        return parsed_pages

    def extract_slide_structured_vision(
        self,
        page: Any = None,
        page_num: int = 1,
        dpi: int = 120,
        base64_img: Optional[str] = None,
        text_layer: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Vision-Native Ingestion: Extracts structured JSON directly from slide image using Vision LLM.
        Locks in visual entities, layout relationships, badges ('PRODUCT DISCONTINUE'),
        indications, routine steps, product details, and clean markdown representation.
        """
        try:
            from app.rag.utils.parser import get_vision_client_and_model
            client, model_name = get_vision_client_and_model()
            if not client:
                return None

            import json

            if not base64_img:
                if page is None:
                    return None
                if text_layer is None:
                    text_layer = page.get_text()
                pix = page.get_pixmap(dpi=dpi)
                img_bytes = pix.tobytes("jpeg")
                del pix
                base64_img = base64.b64encode(img_bytes).decode("utf-8")
                del img_bytes

            prompt = """You are an expert clinical and aesthetic visual document extraction engine for a dermatology clinic chatbot.
Analyze this slide image with extreme fidelity to visual design, layout, tables, matrices, and product lineups.

TRANSCRIPTION FIDELITY (applies to every archetype and every field, overrides the templates below):
- Write ONLY text that is visibly printed on the slide (headings, labels, table cells, packaging text).
  The output is read by doctors as the clinic's official content: nothing may come from general knowledge.
- NEVER add descriptions, functions, indications, benefits, usage instructions, categories or prices that
  are not printed. If a field or column has no printed text, leave it null/empty or omit that column.
- A slide that only shows product photos is NOT a table: list the products by the names printed on them.
- A table printed on the slide keeps its own printed column headers (e.g. 'Skin Type | Spot Size | Treatment
  Interval'). The example columns below ('Kategori | Nama Produk | Fungsi / Indikasi') are only for a product
  lineup; never put a printed table into them.
- Text you cannot read with certainty (small print on packaging, blurred labels) is left out, never guessed:
  a missing detail is acceptable, a wrong ingredient or name is not.
- On a slide that shows product photos without a printed product description, record ONLY the product
  names in the large print; do not read ingredients, netto or claims from the small print on the packaging.
- Never write the word 'null' into the Markdown: leave the cell empty or drop the line.
- Product names come from the printed name; ingredient lines printed on packaging (e.g. 'PHA, AHA,
  Niacinamide') belong to active ingredients, not to the name. Keep the printed variant words
  (e.g. 'Facial Wash', 'Night Cream').

First, determine the Slide Archetype:
1. 'MATRIX_OR_TABLE': Visual grid, table, or lineup across categories (columns: Cleanser, Toner, Serum, Sunscreen, Moisturizer, Treatment, Body, Mask...) and target row (e.g., 'All Skin Type', 'Dry & Sensitive', 'Oily & Combination').
2. 'PRODUCT_CATALOG': Single or dual product detail slide with bottle/tube photo, active ingredients, netto, price, instructions, description.
3. 'ROUTINE_FLOW': Step-by-step usage flow with timing badges ('Pagi / Siang', 'Malam', 'Step 1, 2, 3...').
4. 'GENERAL_CONTENT': Informational slide or clinical guideline.

RULES FOR 'MATRIX_OR_TABLE':
- DO NOT convert a matrix table into a plain numbered list of steps!
- Identify the target category row/axis: e.g. Skin Type: 'All Skin Type' (or 'Dry & Sensitive', 'Oily & Combination').
- In 'raw_markdown_representation', render a complete, clean GFM Markdown Table with the columns printed on the slide (a 'Fungsi / Indikasi' column only when the slide prints those functions):
  Example (when the slide prints a function per product):
  # Rangkaian Produk - All Skin Type (Semua Jenis Kulit)

  | Kategori | Nama Produk | Fungsi / Indikasi |
  | --- | --- | --- |
  | Cleanser | ACSBP | Pembersih wajah / Cleanses the skin |
  | Toner | Clarifying Toner | Mempersiapkan kulit / Prepares skin |
  ...
- If any product has a visual badge like 'PRODUCT DISCONTINUE' or 'stok klinik habis', note it explicitly in that table row!
- Keep every printed row/column label (e.g. a brand or product-line name heading a row) as its own cell.
- When one cell holds several items, separate them with '<br>' (never run them together, never break the row over lines).
- Keep the printed table's own grid: one Markdown row per printed row, every value in the column it is printed under.
  A header spanning several sub-columns (e.g. 'Ultra Booster Cartridge' over 'MP Mode' and 'Normal Mode') becomes
  one column per sub-column named 'Header - Sub-header'. A cell spanning several rows (e.g. one 'Treatment Interval'
  for every skin type) is repeated in each row it covers. Never stack a second column's values as extra rows below.
- Photos (before/after, patient or device photos), even when labelled with times or captions ('Pre', '24 hrs Post',
  'Before', '8 Weeks Post'), are not a table: describe them in one line with the printed labels, never as table cells.

RULES FOR 'PRODUCT_CATALOG':
- In 'raw_markdown_representation', render a structured clinical product profile, keeping only the lines whose content is printed on the slide:
  ### [Nama Produk]
  [Deskripsi produk / fungsi, if printed]
  - **Kategori**: [Kategori, if printed]
  - **Bahan Aktif**: [every printed ingredient group WITH the function printed next to it, one per sub-bullet,
    e.g. '  - Niacinamide, Camu-Camu Fruit Extract: Brightening agent, moisturizing']
  - **Harga & Ukuran**: [Netto dan harga as printed, e.g. 100 g - Rp. 105.000]
  - **Cara Pakai**: [Petunjuk penggunaan as printed]

RULES FOR 'ROUTINE_FLOW':
- Transcribe BOTH Pagi/Siang and Malam sequences with numbered steps (1., 2., 3....), category names, and product lines.
- Add an explanation to a step only when the slide prints one for that step.

Extract structured JSON strictly conforming to this schema:
{
  "page_number": <int>,
  "slide_title": "<string, clean descriptive title, e.g. 'Rangkaian Produk Acneact - All Skin Type' or 'ACSBP (Acne Cleanser Scrub Beta Plus)'>",
  "slide_archetype": "<string: 'MATRIX_OR_TABLE', 'PRODUCT_CATALOG', 'ROUTINE_FLOW', or 'GENERAL_CONTENT'>",
  "target_skin_type": "<string or null, e.g. 'All Skin Type', 'Dry & Sensitive', 'Oily & Combination'>",
  "domain": "<string strictly one of: 'hair_and_scalp', 'acne', 'brightening', 'anti_aging', 'body_care', 'treatment_procedure', 'general'>",
  "is_discontinued": <boolean, true ONLY IF this specific slide represents a single product that has an explicit visual stamp, banner, or badge visibly stating 'DISCONTINUED' or 'DISCONTINUE' or 'stok klinik habis' directly on that product. If this slide contains multiple products in a table, keep this false>,
  "target_indications": ["<string, e.g. 'acne', 'oily_skin', 'blackheads', 'sensitive_skin'>"],
  "routine_steps": [
    {
      "step": <int>,
      "time_of_day": "<string: 'pagi_siang', 'malam', or 'all'>",
      "category": "<string>",
      "product_name": "<exact product name or category shown>",
      "usage": "<usage/function text printed for this step, or null>"
    }
  ],
  "product_entities": [
    {
      "product_name": "<string>",
      "category": "<string or null>",
      "active_ingredients": "<string or null>",
      "netto": "<string or null>",
      "price": "<string or null>",
      "is_discontinued": <boolean>,
      "description": "<description printed on the slide, or null>"
    }
  ],
  "raw_markdown_representation": "<string, clean human-readable Markdown representing this entire slide faithfully adhering to the archetype rules above>"
}
"""
            if text_layer and text_layer.strip():
                # The PDF's own text is exact; the image is only needed for layout and for text drawn as pixels
                prompt += (
                    "\nPDF TEXT LAYER of this slide (exact characters printed on it, in arbitrary order). Use it for the "
                    "spelling of every name, number, price and ingredient it contains; use the image for layout, grouping "
                    "and any text missing from it:\n<<<\n" + text_layer.strip()[:6000] + "\n>>>\n"
                )

            response = client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_img}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )

            content = response.choices[0].message.content
            if not content:
                return None
            data = json.loads(content)
            data["page_number"] = page_num
            if data.get("raw_markdown_representation"):
                from app.rag.utils.text_hygiene import normalize_markdown_text, unstack_stacked_columns, flatten_label_only_tables
                data["raw_markdown_representation"] = flatten_label_only_tables(unstack_stacked_columns(
                    normalize_markdown_text(data["raw_markdown_representation"])))
            self._ground_status_claims_in_vision_data(data, client, model_name, base64_img, page_num)
            logger.info(
                f"[FLATTENED-PARSER] Page {page_num}: Vision-native extraction succeeded: "
                f"domain={data.get('domain')}, is_discontinued={data.get('is_discontinued')}, "
                f"indications={data.get('target_indications')}, steps={len(data.get('routine_steps', []))}"
            )
            return data
        except Exception as e:
            logger.warning(f"[FLATTENED-PARSER] Page {page_num} vision-native extraction skipped/failed: {e}")
            return None

    def _ground_status_claims_in_vision_data(
        self,
        data: Dict[str, Any],
        client: Any,
        model_name: Optional[str],
        base64_img: str,
        page_num: int
    ) -> None:
        """
        A discontinuation/stock-out status is only kept when an independent, narrowly scoped
        vision check can quote the status text visibly printed on the slide. Claims the slide
        does not show (e.g. a '(DISCONTINUED)' the extractor inferred) are removed from the
        markdown and from every page/product flag, so they never reach summaries or chunks.
        """
        import json
        from app.rag.utils.text_hygiene import has_status_notice, normalize_discontinue_phrases, strip_status_claims

        md = data.get("raw_markdown_representation") or ""
        entities = data.get("product_entities") or []
        claims = (
            bool(data.get("is_discontinued"))
            or has_status_notice(md)
            or any(isinstance(e, dict) and e.get("is_discontinued") for e in entities)
        )
        if not claims:
            return

        quoted = None
        try:
            resp = client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": (
                            "Look only for availability status text physically printed on this slide "
                            "(a stamp, badge, banner, or label such as 'DISCONTINUE', 'DISCONTINUED', "
                            "'stok klinik habis'). Do not infer status from context.\n"
                            "Return JSON: {\"status_texts\": [{\"text\": \"<exact visible text>\", "
                            "\"product\": \"<product the badge is placed on, or null>\"}]}. "
                            "Return an empty list if no such text is visible."
                        )},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}", "detail": "high"}},
                    ],
                }],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            verdict = json.loads(resp.choices[0].message.content or "{}")
            quoted = [
                s for s in (verdict.get("status_texts") or [])
                if isinstance(s, dict) and has_status_notice(normalize_discontinue_phrases(str(s.get("text") or "")))
            ]
        except Exception as verify_err:
            logger.warning(f"[FLATTENED-PARSER] Page {page_num}: status verification unavailable ({verify_err}); keeping extractor output")
            return

        if quoted:
            data["status_evidence"] = quoted
            badge_products = {str(s.get("product") or "").strip().lower() for s in quoted if s.get("product")}
            if badge_products:
                # Only the products the badge is actually placed on carry the status
                for e in entities:
                    if isinstance(e, dict):
                        name = str(e.get("product_name") or "").strip().lower()
                        e["is_discontinued"] = bool(name) and any(b in name or name in b for b in badge_products)
            return

        logger.info(f"[FLATTENED-PARSER] Page {page_num}: status claim not visible on slide -> removed")
        data["is_discontinued"] = False
        for e in entities:
            if isinstance(e, dict):
                e["is_discontinued"] = False
        data["raw_markdown_representation"] = strip_status_claims(md)

    def _apply_vision_gate(
        self,
        provenance_list: List[ImageProvenance],
        embedded_imgs: List[Dict[str, Any]],
        ocr_blocks: List[Dict[str, Any]],
        page_num: int,
        document_id: str,
        seen_hashes: Dict[str, str],
        vision_cache: Dict[str, Dict[str, Any]],
        max_images_per_page: int = 4,
        min_pixel_area: int = 25000,
    ) -> List[ImageProvenance]:
        """
        Understands document context before accepting any image.
        Geometry heuristics only nominate candidates; a Vision LLM decides whether the image is
        genuinely knowledge (PRODUCT packaging / CLINICAL / CHART / INFOGRAPHIC_TABLE).
        Ornaments, icons, circles, backgrounds, logos and stickers are rejected.
        Only accepted images are uploaded to storage (no orphan/broken assets).
        """
        import hashlib
        from concurrent.futures import ThreadPoolExecutor
        from app.rag.utils.parser import verify_and_classify_visual_candidate, _check_flat_decorative_graphic

        by_xref = {img.get("xref"): img for img in embedded_imgs}
        page_context = " ".join(b.get("text", "") for b in ocr_blocks)[:1200]

        # 1. Identify candidates and evaluate geometric pre-filters
        candidates_to_verify = []
        for prov in provenance_list:
            if not prov.should_display():
                continue

            img = by_xref.get(prov.image_index)
            raw = (img or {}).get("bytes") or b""
            w = int((img or {}).get("width", 0))
            h = int((img or {}).get("height", 0))
            area = w * h
            aspect_ratio = (w / max(1, h)) if h > 0 else 1.0

            reject_reason = None
            if not raw:
                reject_reason = "empty image bytes"
            elif len(raw) < 3000 or area < min_pixel_area or min(w, h) < 90:
                reject_reason = f"too small to be a substantive image (area={area}, min_dim={min(w, h)})"
            elif aspect_ratio < 0.22 or aspect_ratio > 3.2:
                reject_reason = f"extreme aspect ratio {aspect_ratio:.2f} (likely line/divider/banner/logo)"
            else:
                is_flat, desc = _check_flat_decorative_graphic(raw)
                if is_flat:
                    reason = desc.get("reason", "")
                    if not ("dominance" in reason or "pill/swoosh" in reason):
                        reject_reason = "flat decorative graphic element"

            candidates_to_verify.append({
                "prov": prov,
                "img": img,
                "raw": raw,
                "reject_reason": reject_reason,
            })

        # 2. Parallelize Vision API calls across valid candidates
        def _call_vision(cand: Dict[str, Any]) -> Dict[str, Any]:
            if cand["reject_reason"]:
                return {"is_relevant": False, "reason": cand["reject_reason"]}
            try:
                return verify_and_classify_visual_candidate(
                    img_bytes=cand["raw"],
                    img_ext=(cand["img"] or {}).get("ext", "png"),
                    page_context=page_context,
                    fallback_title=cand["prov"].linked_product or "",
                    cache=vision_cache,
                )
            except Exception as v_err:
                logger.warning(f"Vision gate error on page {page_num}: {v_err}")
                return {"is_relevant": False, "reason": f"vision error: {v_err}"}

        items_needing_call = [c for c in candidates_to_verify if not c["reject_reason"]]
        results_by_idx = {}
        if items_needing_call:
            with ThreadPoolExecutor(max_workers=min(3, len(items_needing_call))) as executor:
                futures = {executor.submit(_call_vision, c): i for i, c in enumerate(candidates_to_verify) if not c["reject_reason"]}
                for fut in futures:
                    i = futures[fut]
                    try:
                        results_by_idx[i] = fut.result()
                    except Exception as err:
                        results_by_idx[i] = {"is_relevant": False, "reason": f"thread error: {err}"}

        kept = 0
        for i, cand in enumerate(candidates_to_verify):
            prov = cand["prov"]
            img = cand["img"]
            raw = cand["raw"]
            reject_reason = cand["reject_reason"]

            if not reject_reason:
                verdict = results_by_idx.get(i, {})
                if not verdict.get("is_relevant"):
                    reject_reason = f"vision: {verdict.get('classification')} - {verdict.get('reason')}"
                elif kept >= max_images_per_page:
                    reject_reason = "per-page image cap reached"

            if reject_reason:
                prov.display_policy = ImageDisplayPolicy.EXCLUDE
                prov.target_url = ""
                prov.classification_reason = f"Rejected by gate: {reject_reason}"
                logger.info(f"[VISION-GATE] Page {page_num} xref {prov.image_index} rejected ({reject_reason})")
                continue

            # Accepted: name it from what Vision actually read, then upload once
            verdict = results_by_idx.get(i, {})
            name = (verdict.get("product_name") or prov.linked_product or "").strip()
            if name:
                prov.linked_product = name
                prov.alt_text = name

            digest = hashlib.sha256(raw).hexdigest()
            url = seen_hashes.get(digest)
            if not url:
                ext = (img or {}).get("ext", "png")
                fname = f"pdf_flat_{document_id or 'doc'}_p{page_num}_{prov.image_index}.{ext}"
                try:
                    url = upload_image(raw, fname, content_type=f"image/{ext}").get("image_url") or ""
                except Exception as up_err:
                    logger.warning(f"Upload failed for accepted image on page {page_num}: {up_err}")
                    url = ""
                if url:
                    seen_hashes[digest] = url
            if not url:
                prov.display_policy = ImageDisplayPolicy.EXCLUDE
                continue
            prov.target_url = url
            prov.classification_reason = f"Accepted by gate: {verdict.get('classification')} '{name}'"
            kept += 1
            logger.info(f"[VISION-GATE] Page {page_num} xref {prov.image_index} accepted as '{name}'")

        return provenance_list

    def _assemble_catalog_markdown(
        self,
        ocr_blocks: List[Dict[str, Any]],
        provenance_list: List[ImageProvenance],
        page_width: float,
        page_height: float,
        page: Optional[Any] = None,
        page_num: int = 1
    ) -> str:
        """
        Structures OCR blocks into human-readable catalog markdown with headings,
        product info, active ingredients, usage steps, and linked product image.
        Supports:
        1. Product Card Slides (combines multi-line titles, structured cards, prices, and bottle photo).
        2. Infographic / Matrix / Regimen Slides (routes to multimodal vision transcription or clean reading order).
        """
        if not ocr_blocks:
            return ""

        # Add center coordinates if missing
        for b in ocr_blocks:
            if "cx" not in b or "cy" not in b:
                bbox = b.get("bbox", [0, 0, 0, 0])
                b["cx"] = (bbox[0] + bbox[2]) / 2.0
                b["cy"] = (bbox[1] + bbox[3]) / 2.0

        # Helper to group OCR blocks by lines and sort horizontally
        def blocks_to_text(blks: List[Dict[str, Any]], line_thresh: float = 10.0) -> str:
            if not blks:
                return ""
            blks_sorted = sorted(blks, key=lambda b: (b["cy"], b["cx"]))
            lines_grouped: List[List[Dict[str, Any]]] = []
            curr_l: List[Dict[str, Any]] = []
            curr_y: Optional[float] = None
            for b in blks_sorted:
                if curr_y is None or abs(b["cy"] - curr_y) < line_thresh:
                    curr_l.append(b)
                    curr_y = b["cy"]
                else:
                    lines_grouped.append(curr_l)
                    curr_l = [b]
                    curr_y = b["cy"]
            if curr_l:
                lines_grouped.append(curr_l)

            line_strs = []
            for l in lines_grouped:
                l.sort(key=lambda b: b["cx"])
                line_strs.append(" ".join(b["text"] for b in l))
            return " ".join(line_strs)

        # 1. Identify Section Headers
        headers = {}
        for b in ocr_blocks:
            txt_l = b["text"].lower().strip()
            if "product information" in txt_l or "informasi produk" in txt_l:
                headers["info"] = b
            elif "cara pakai" in txt_l or "aturan pakai" in txt_l:
                headers["cara_pakai"] = b
            elif "bahan aktif" in txt_l or "active ingredient" in txt_l:
                headers["bahan_aktif"] = b

        is_product_card = bool(headers)

        # ---------------------------------------------------------------------
        # Non-Product Card Slide Handling (Overview, Range Matrix, Step Guide)
        # ---------------------------------------------------------------------
        if not is_product_card:
            # 1. Check if multimodal vision can transcribe structured table/matrix
            if page is not None:
                try:
                    from app.rag.utils.parser import transcribe_visual_infographic_slide
                    v_table = transcribe_visual_infographic_slide(page, page_context=f"Slide {page_num}")
                    if v_table and "|" in v_table:
                        included_images = [p for p in provenance_list if p.should_display() and p.target_url]
                        img_md = "\n\n".join(f"![{p.linked_product or f'Slide {page_num}'}]({p.target_url})" for p in included_images)
                        if img_md:
                            return f"## Slide {page_num}\n\n{img_md}\n\n{v_table}".strip()
                        return f"## Slide {page_num}\n\n{v_table}".strip()
                except Exception as v_err:
                    logger.debug(f"Vision transcription fallback skipped on page {page_num}: {v_err}")

            # 2. Lossless OCR block reading assembly for non-product slides
            clean_blocks = [
                b for b in ocr_blocks
                if not (b["cy"] < 0.12 * page_height and (b["cx"] < 0.28 * page_width or b["cx"] > 0.85 * page_width))
                and b["text"] not in ["口", "4", "●", "☆", "○", "■"]
            ]
            if not clean_blocks:
                clean_blocks = ocr_blocks

            # Group lines by vertical proximity
            clean_blocks.sort(key=lambda b: (b["cy"], b["cx"]))
            grouped_lines: List[List[Dict[str, Any]]] = []
            curr_l = []
            curr_y = None
            for b in clean_blocks:
                if curr_y is None or abs(b["cy"] - curr_y) < 14.0:
                    curr_l.append(b)
                    curr_y = b["cy"]
                else:
                    grouped_lines.append(curr_l)
                    curr_l = [b]
                    curr_y = b["cy"]
            if curr_l:
                grouped_lines.append(curr_l)

            line_texts = []
            for l in grouped_lines:
                l.sort(key=lambda b: b["cx"])
                line_texts.append(" ".join(b["text"] for b in l))

            included_images = [p for p in provenance_list if p.should_display() and p.target_url]
            img_md = "\n\n".join(f"![{p.linked_product or f'Slide {page_num}'}]({p.target_url})" for p in included_images)

            # Multi-product routine synthesis for Canva / PPT infographic slides
            synthesized_routine_lines = []
            combined_line_text = " ".join(line_texts)
            for p in included_images:
                name_str = p.linked_product or p.alt_text or ""
                if "," in name_str:
                    items = [x.strip() for x in name_str.split(",") if len(x.strip()) > 3]
                    if len(items) >= 2 and not any(it.lower() in combined_line_text.lower() for it in items):
                        synthesized_routine_lines.append("### Rangkaian / Produk dalam Slide:")
                        for idx, it in enumerate(items):
                            synthesized_routine_lines.append(f"{idx+1}. {it}")

            assembled = f"## Slide {page_num}\n\n"
            if img_md:
                assembled += f"{img_md}\n\n"
            if synthesized_routine_lines:
                assembled += "\n".join(synthesized_routine_lines) + "\n\n"
            assembled += "\n\n".join(line_texts)
            return assembled.strip()

        # ---------------------------------------------------------------------
        # Product Card Slide Handling (e.g. Cleansing Gel, Essence Toner, Mist)
        # ---------------------------------------------------------------------
        min_hdr_y = min(h["cy"] for h in headers.values()) if headers else page_height * 0.40

        # Title Candidate: combine vertically stacked lines in top-center region above headers
        title_blocks = [
            b for b in ocr_blocks
            if (0.20 * page_width <= b["cx"] <= 0.80 * page_width)
            and (0.08 * page_height <= b["cy"] < min_hdr_y)
            and len(b["text"]) >= 3
            and not (b["cy"] < 0.12 * page_height and (b["cx"] < 0.28 * page_width or b["cx"] > 0.85 * page_width))
        ]
        title_blocks.sort(key=lambda b: b["cy"])

        if title_blocks:
            title_candidate = " ".join(b["text"] for b in title_blocks).strip()
        else:
            title_candidate = ""
            for b in ocr_blocks:
                txt = b["text"].strip()
                if b["cy"] < (page_height * 0.35) and len(txt) > 4:
                    if not (b["cy"] < 0.12 * page_height and (b["cx"] < 0.28 * page_width or b["cx"] > 0.85 * page_width)):
                        title_candidate = txt
                        break
            if not title_candidate:
                title_candidate = f"Slide {page_num}"

        # Classify Content Blocks
        info_blocks = []
        cara_pakai_blocks = []
        bahan_aktif_blocks = []
        price_blocks = []
        status_blocks = []
        unassigned_blocks = []

        hdr_info_y = headers.get("info", {}).get("cy", 0)
        hdr_cp_y = headers.get("cara_pakai", {}).get("cy", 0)
        hdr_ba_y = headers.get("bahan_aktif", {}).get("cy", 9999)

        # Determine verified product image bounding boxes on page
        prod_boxes = [
            p.bbox for p in provenance_list 
            if p.should_display() and p.bbox and len(p.bbox) >= 4
        ]

        def _is_inside_product_packaging(b_obj):
            for ib in prod_boxes:
                # If block center is well inside product image bounding box
                if (ib[0] + 5 <= b_obj["cx"] <= ib[2] - 5) and (ib[1] + 15 <= b_obj["cy"] <= ib[3] - 15):
                    # Check if text looks like small physical bottle packaging print
                    if len(b_obj["text"].strip()) < 30 or re.search(r'\b(?:ml|gr|netto|batch|exp|distribusi)\b', b_obj["text"].lower()):
                        return True
            return False

        # Determine layout arrangement of detected section headers
        # Check if Info and Cara Pakai are in side-by-side columns:
        is_side_by_side = (
            hdr_info_y > 0 and hdr_cp_y > 0 and abs(hdr_info_y - hdr_cp_y) < 60.0
        )
        if is_side_by_side:
            split_x = (headers["info"]["cx"] + headers["cara_pakai"]["cx"]) / 2.0
        else:
            split_x = page_width * 0.50

        # Right boundary: stop before bottle ONLY if a product bottle actually sits on the right
        bottle_right_x = min([b[0] for b in prod_boxes if (b[0] + b[2]) / 2.0 > page_width * 0.60], default=page_width * 0.98)
        right_max_x = min(page_width * 0.98, bottle_right_x)

        for b in ocr_blocks:
            txt = b["text"].strip()
            txt_l = txt.lower()

            if any(b is tb for tb in title_blocks) or txt == title_candidate:
                continue
            if any(h.get("text") == txt for h in headers.values()):
                continue
            # Ignore top corner banner badges / running watermarks outside title area
            if b["cy"] < min_hdr_y and (b["cx"] < 0.28 * page_width or b["cx"] > 0.85 * page_width):
                continue
            if txt in ["口", "4", "●", "☆", "○", "■"]:
                continue

            # Skip text physically printed on the product bottle packaging label via IoU
            if _is_inside_product_packaging(b):
                continue

            # Price & Status Check
            if re.search(r"\b(?:idr|rp)\b\s*\d+", txt_l):
                price_blocks.append(txt)
                continue
            if "discontinue" in txt_l or "stok klinik habis" in txt_l:
                # Guard against standalone matrix/category headers (e.g. "PRODUCT DISCONTINUE")
                # when multiple products are displayed on a single page
                if txt.strip().upper() in ["PRODUCT DISCONTINUE", "DISCONTINUE", "DISCONTINUED"] and len(ocr_blocks) > 12:
                    pass
                else:
                    status_blocks.append(txt)
                continue

            # Classify into sections adaptively based on header arrangement:
            if is_side_by_side:
                # Layout A: Side-by-side columns (Info on Left, Cara Pakai on Right, Bahan Aktif below)
                if b["cx"] < split_x and min(hdr_info_y, hdr_cp_y) < b["cy"] < hdr_ba_y:
                    info_blocks.append(b)
                    continue
                if split_x <= b["cx"] <= right_max_x and min(hdr_info_y, hdr_cp_y) < b["cy"] < hdr_ba_y:
                    cara_pakai_blocks.append(b)
                    continue
                if hdr_ba_y < 9999 and b["cy"] >= (hdr_ba_y - 10) and b["cy"] < (page_height * 0.92):
                    bahan_aktif_blocks.append(b)
                    continue
            else:
                # Layout B: Stacked sections (or single-column flow)
                if hdr_ba_y < hdr_cp_y:
                    # Bahan Aktif is above Cara Pakai
                    if b["cy"] < hdr_ba_y:
                        info_blocks.append(b)
                        continue
                    elif b["cy"] < hdr_cp_y:
                        bahan_aktif_blocks.append(b)
                        continue
                    elif b["cy"] < (page_height * 0.92):
                        cara_pakai_blocks.append(b)
                        continue
                else:
                    # Cara Pakai (or Info) is above Bahan Aktif
                    target_split_y = hdr_cp_y if hdr_cp_y > 0 else hdr_info_y
                    if target_split_y > 0 and b["cy"] < target_split_y:
                        info_blocks.append(b)
                        continue
                    elif hdr_ba_y < 9999 and b["cy"] < hdr_ba_y:
                        cara_pakai_blocks.append(b)
                        continue
                    elif hdr_ba_y < 9999 and b["cy"] >= (hdr_ba_y - 10) and b["cy"] < (page_height * 0.92):
                        bahan_aktif_blocks.append(b)
                        continue

            if len(txt) > 3:
                unassigned_blocks.append(b)

        # Assemble Structured Markdown
        lines = [f"## {title_candidate}"]

        # Attach linked product image directly below title if authorized
        included_images = [p for p in provenance_list if p.should_display() and p.target_url]
        if included_images:
            for p in included_images:
                label = p.linked_product or title_candidate
                lines.append(f"\n![{label}]({p.target_url})\n")

        if info_blocks:
            lines.append("### Product Information")
            lines.append(blocks_to_text(info_blocks))

        if cara_pakai_blocks:
            lines.append("\n### Cara Pakai")
            lines.append(blocks_to_text(cara_pakai_blocks))

        if bahan_aktif_blocks:
            lines.append("\n### Bahan Aktif")
            bahan_aktif_blocks.sort(key=lambda b: (b["cy"], b["cx"]))
            ba_lines_grouped: List[List[Dict[str, Any]]] = []
            curr_l = []
            curr_y = None
            for b in bahan_aktif_blocks:
                if curr_y is None or abs(b["cy"] - curr_y) < 14:
                    curr_l.append(b)
                    curr_y = b["cy"]
                else:
                    ba_lines_grouped.append(curr_l)
                    curr_l = [b]
                    curr_y = b["cy"]
            if curr_l:
                ba_lines_grouped.append(curr_l)

            raw_ba_items = []
            for bl in ba_lines_grouped:
                bl.sort(key=lambda b: b["cx"])
                joined = " ".join(b["text"] for b in bl)
                joined = re.sub(r"\s+:\s+", " : ", joined).lstrip("-•●◦* ")
                raw_ba_items.append(joined)

            # Stitch wrapped multi-line ingredient names (e.g. Mulberry Extract or Licorice Extract)
            cleaned_ba: List[str] = []
            for item in raw_ba_items:
                t = item.strip()
                if not t:
                    continue
                if ":" not in t and cleaned_ba and (len(t) < 30 or any(kw in t.lower() for kw in ["extract", "root", "fruit", "oil", "acid"])):
                    prev = cleaned_ba[-1]
                    if ":" in prev:
                        parts = prev.split(":", 1)
                        ing = parts[0].strip() + " " + t.strip()
                        cleaned_ba[-1] = f"{ing} : {parts[1].strip()}"
                    else:
                        cleaned_ba[-1] = f"{prev} {t}"
                else:
                    cleaned_ba.append(t)

            for item in cleaned_ba:
                lines.append(f"- {item}")

        if price_blocks or status_blocks:
            lines.append("\n### Detail Produk")
            for pr in price_blocks:
                lines.append(f"- **Harga**: {pr}")
            if status_blocks:
                lines.append(f"- **Status**: {' '.join(status_blocks)}")

        # Append remaining substantive notes/skin types if genuinely present (excluding corner banner watermarks)
        substantive_unassigned = [
            b for b in unassigned_blocks
            if not (b["cy"] < 0.12 * page_height and (b["cx"] < 0.28 * page_width or b["cx"] > 0.85 * page_width))
            and not (b["cy"] > 0.94 * page_height)
        ]
        if substantive_unassigned:
            clean_extra = blocks_to_text(substantive_unassigned).strip()
            if clean_extra and len(clean_extra) > 8:
                clean_l = clean_extra.lower()
                if any(sk in clean_l for sk in ["skin type", "kulit normal", "kulit kering", "kulit berminyak", "kulit sensitif", "all skin"]):
                    lines.append(f"\n### Tipe Kulit / Sasaran\n{clean_extra}")
                elif any(kw in clean_l for kw in ["perhatian", "warning", "catatan", "note", "anjuran", "cara penyimpanan"]):
                    lines.append(f"\n### Catatan\n{clean_extra}")
                elif len(clean_extra) > 25:
                    lines.append(f"\n### Informasi Tambahan\n{clean_extra}")

        return "\n".join(lines).strip()

