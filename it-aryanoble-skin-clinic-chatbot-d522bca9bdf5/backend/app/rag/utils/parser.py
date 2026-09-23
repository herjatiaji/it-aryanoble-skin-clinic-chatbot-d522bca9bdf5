import os
import time
import re
from typing import Optional, Tuple
from loguru import logger


class ParseResult:
    """
    Unified parse result that can hold either a DoclingDocument (for OCR path)
    or a list of page-text dicts (for fast path).
    """
    def __init__(self, pages: list = None, docling_doc=None, method: str = "fast"):
        self.pages = pages or []       # [{"page": 1, "text": "..."}, ...]
        self.docling_doc = docling_doc  # DoclingDocument object (only for OCR path)
        self.method = method           # "fast" or "docling"

    @property
    def is_fast(self) -> bool:
        return self.method == "fast"

    @property
    def is_docling(self) -> bool:
        return self.method == "docling"


def _is_valid_image_content(img_bytes: bytes, min_dim: int = 40) -> Tuple[bool, bytes, str]:
    """
    Validates image bytes using Pillow:
    1. Rejects tiny spacer/icon images (< min_dim in width or height).
    2. Rejects solid black, pitch-black (>95% black), or flat unicolor blocks.
    3. Converts WMF/EMF or palette formats to clean PNG.
    4. Sanitizes circular icons with solid black corners → transparent RGBA PNG.
    Returns: (is_valid, cleaned_bytes, cleaned_ext)
    """
    if not img_bytes or len(img_bytes) < 100:
        return False, b"", ""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(img_bytes)) as im:
            w, h = im.size
            if w < min_dim or h < min_dim:
                return False, b"", ""

            # Check format & convert WMF/EMF/TIFF/BMP or palette formats to clean PNG
            ext = (im.format or "png").lower()
            out_bytes = img_bytes
            if ext in ("wmf", "emf", "tiff", "bmp") or im.mode not in ("RGB", "RGBA", "L"):
                buf = io.BytesIO()
                im.convert("RGBA").save(buf, format="PNG")
                out_bytes = buf.getvalue()
                ext = "png"

            # Check for solid pitch black or flat unicolor blocks
            rgb = im.convert("RGB").resize((16, 16))
            colors = rgb.getcolors(maxcolors=256)
            if colors:
                # If single color (flat unicolor rectangle/slide background)
                if len(colors) == 1:
                    return False, b"", ""
                # If solid pitch black (all sampled pixels r, g, b < 18)
                if all(c[1][0] < 18 and c[1][1] < 18 and c[1][2] < 18 for c in colors):
                    return False, b"", ""

            # Sanitize circular/rounded icons or images with solid black borders/corners:
            # If corners are pitch-black, flood fill the outer black areas to transparent RGBA.
            try:
                from PIL import ImageDraw
                rgba_im = im.convert("RGBA")
                w, h = rgba_im.size
                corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
                has_black_corner = False
                for cx, cy in corners:
                    px = rgba_im.getpixel((cx, cy))
                    if px[0] < 20 and px[1] < 20 and px[2] < 20 and px[3] > 200:
                        has_black_corner = True
                        ImageDraw.floodfill(rgba_im, (cx, cy), (0, 0, 0, 0), thresh=25)
                if has_black_corner:
                    buf = io.BytesIO()
                    rgba_im.save(buf, format="PNG")
                    out_bytes = buf.getvalue()
                    ext = "png"
            except Exception:
                pass

            return True, out_bytes, ext
    except Exception:
        # Fallback: if Pillow fails, allow bytes if sufficiently large
        return True, img_bytes, "png"


def _is_ornamental_pdf_image(
    pix_width: int,
    pix_height: int,
    bbox: list,
    page_height: float,
    page_idx: int,
    nearby_text: str,
    prod_label: str
) -> bool:
    """
    Detects and filters out non-substantive ornamental PDF images such as:
    - Publisher/journal logos in headers/footers (e.g. HJKK, Elsevier, Springer, Nature logos)
    - University insignias, academic emblems, hospital/clinic seals
    - DOI badges & icons (e.g. 44x44 DOI icon)
    - Creative Commons / copyright license banners (e.g. 133x46 CC-BY-SA badge)
    - Running headers, page footer banners, separator rules
    - Social media icons / tiny badges (< 55px or banner aspect with tiny height)
    Preserves genuine product photos, clinical figures, histology, charts, diagrams, and patient before/after.
    """
    # 1. Dimension checks
    # Tiny icons/badges (e.g. DOI icon 44x44, favicons, bullets, social media icons)
    if pix_width < 55 or pix_height < 55:
        return True
    
    # License / copyright banner aspect ratio (e.g. CC badge 133x46, 88x31, barcode 200x50)
    if pix_height <= 60 and pix_width <= 250:
        return True

    # 2. Textual pattern checks on label and nearby text
    combined_text = f"{prod_label} {nearby_text}".lower()
    
    # Check if this image has an explicit scientific figure/chart caption (e.g. Figure 1, Gambar 2)
    has_figure_caption = bool(re.search(r'\b(?:figure|fig\.|gambar|diagram|bagan|grafik|chart)\s+[ivx0-9]+', combined_text))

    # Obvious ornamental / metadata badges
    badge_keywords = [
        "doi.org", "http://doi", "https://doi", "doi:", "dx.doi.org",
        "creative commons", "creativecommons", "cc-by", "cc by", "cc_by", "cc-sa", "cc-nc", "cc-nd", "cc0",
        "crossmark", "open access", "openaccess", "open-access",
        "issn", "e-issn", "p-issn", "isbn",
        "scopus", "sinta", "sinta 1", "sinta 2", "sinta 3", "sinta 4", "sinta 5", "sinta 6",
        "pubmed", "pmc", "medline", "doaj", "google scholar", "garuda",
        "dimensions", "clarivate", "web of science", "wos", "scimago", "sjr",
        "copernicus", "index copernicus", "ebsco", "proquest", "cabi",
        "orcid", "orcid.org", "researchgate", "zenodo", "figshare"
    ]
    if any(kw in combined_text for kw in badge_keywords):
        return True

    # Stop words in prod_label (if PyMuPDF extracted nearby words as label)
    label_stop_words = [
        "logo", "banner", "header", "footer", "badge", "crest", "lambang", "kop",
        "cover", "icon", "watermark", "stamp", "stempel", "cap", "emblem", "insignia"
    ]
    if any(sw in prod_label.lower() for sw in label_stop_words) and not has_figure_caption:
        return True

    # 2b. Global journal/publisher metadata keyword filter (position-independent).
    # Catches journal logos like "Borneo Journal of Pharmacy", "HYDROGEN - Jurnal Kependidikan Kimia"
    # regardless of whether they sit in header/footer zone.
    # Only filter if the image does NOT have a genuine scientific figure caption.
    if not has_figure_caption:
        journal_meta_keywords = [
            # Major international academic publishers
            "elsevier", "sciencedirect", "springer", "springer nature", "nature publishing",
            "wiley", "john wiley", "blackwell", "taylor & francis", "taylor and francis",
            "sage pub", "sage publications", "sage journals", "ieee", "acm",
            "mdpi", "frontiers in", "frontiers media", "oxford university press", "oup",
            "cambridge university press", "cup", "wolters kluwer", "lippincott williams", "lww",
            "plos", "plos one", "hindawi", "biomed central", "bmc",
            "emerald publishing", "de gruyter", "bmj", "bmj publishing", "dovepress", "dove medical press",
            "bentham science", "karger", "thieme", "mary ann liebert", "spandidos", "sciendo",
            "academic press", "university press", "ios press", "world scientific",

            # Indonesian & Regional journals / institutions
            "borneo journal", "hydrogen", "jurnal farmasi", "jurnal kedokteran", "jurnal kesehatan",
            "jurnal kependidikan", "jurnal ilmiah", "jurnal penelitian", "media farmasi",
            "majalah farmasi", "acta medica", "folia medica", "berkala kedokteran",
            "perdoski", "ikatan apoteker", "ikatan dokter", "kemenkes", "kemendikbud", "kemenristek",
            "brin", "lipi", "universitas", "university", "fakultas", "faculty", "politeknik", "sekolah tinggi",
            "institut teknologi", "institut pertanian",

            # Journal / Periodical structural terms
            "journal of", "jurnal of", "journal ", "jurnal ", "the journal", "international journal",
            "indonesian journal", "asian journal", "american journal", "european journal",
            "world journal", "global journal", "national journal",
            "bulletin of", "archives of", "annals of", "proceedings of", "review of",
            "advances in", "trends in", "current research in", "periodical",
            "penerbit", "publisher", "published by", "diterbitkan oleh", "diterbitkan", "dipublikasikan",
            "e-journal", "ejournal", "oai:",

            # Medical, Dermatology, Cosmetic & Pharma journal phrases
            "dermatology journal", "clinical dermatology", "pharmaceutical sciences",
            "pharmacy and", "pharmaceutical journal", "pharmacology", "pharmacognosy",
            "biomedical journal", "cosmetic dermatology", "cosmetic science",
            "aesthetic medicine", "aesthetic dermatology", "skin research", "skin pharmacology",
            "experimental dermatology", "investigative dermatology",

            # Submission & Publication tracking metadata
            "manuscript", "how to cite", "how to reference", "cara sitasi", "cara merujuk",
            "suggested citation", "cite this", "homepage:", "homepage :", "available at",
            "available online", "correspondence", "corresponding author", "penulis korespondensi",
            "author for correspondence", "received:", "received :", "accepted:", "accepted :",
            "revised:", "revised :", "published online", "diterima:", "disetujui:", "direvisi:",
            "article info", "informasi artikel", "article history", "riwayat artikel",
            "keywords:", "kata kunci:",
            "volume ", "vol. ", "vol ", "issue ", "no. ", "nomor ", "edisi ", "pp. ",
            "issn ", "e-issn ", "p-issn "
        ]
        if any(jk in combined_text for jk in journal_meta_keywords):
            return True

    # 3. Header & Footer checks
    header_threshold = 0.35 if page_idx == 0 else 0.18
    # bbox[1] is y0 (top edge of image), bbox[3] is y1 (bottom edge of image)
    is_header = (bbox[1] < page_height * header_threshold) if page_height > 0 else False
    is_footer = (bbox[3] > page_height * 0.85 or bbox[1] > page_height * 0.82) if page_height > 0 else False
    
    if not has_figure_caption:
        # On Page 1, any image starting in top 28% of page without a figure caption is a journal logo/header
        if page_idx == 0 and bbox[1] < (page_height * 0.28):
            return True

        # Any horizontal banner aspect ratio (width >= 2.5x height) located in header or footer
        if (is_header or is_footer) and (pix_width >= pix_height * 2.5):
            return True

        # If in header or footer and text contains any academic/header metadata
        if is_header or is_footer:
            header_meta_words = [
                "journal", "jurnal", "volume", "vol.", "vol ", "issue", "no.", "nomor", "edisi", "edition",
                "published", "penerbit", "publisher", "universitas", "university", "fakultas", "faculty",
                "kependidikan", "kimia", "department", "departemen", "hydrogen", "borneo",
                "pharmacy", "farmasi", "sciences", "research", "international", "indonesian",
                "institut", "institute", "politeknik", "polytechnic", "sekolah tinggi", "akademi",
                "jurusan", "program studi", "prodi", "laboratorium", "laboratory",
                "suplemen", "supplement", "halaman", "pages", "pp.", "p-issn", "e-issn", "issn", "isbn",
                "doi:", "doi.org", "copyright", "hak cipta", "all rights reserved", "©", "(c)",
                "license", "lisensi", "annual", "conference", "prosiding", "proceedings",
                "seminar nasional", "symposium", "congress", "symposia"
            ]
            if any(hw in combined_text for hw in header_meta_words):
                return True

    # 4. Signatures, Paraf, Official Stamps, and Approval block images
    sig_keywords = [
        "tanda tangan", "tandatangan", "signature", "signed", "paraf", "ttd",
        "lembar persetujuan", "lembar pengesahan", "approval sheet",
        "dibuat oleh", "diperiksa oleh", "disetujui oleh", "diketahui oleh",
        "disahkan oleh", "diajukan oleh", "mengetahui", "approved by",
        "reviewed by", "prepared by", "checked by"
    ]
    if any(sk in combined_text for sk in sig_keywords):
        sig_indicators = ["tanggal:", "tanggal :", "nama /", "nama terapis", "supervisor", "pic klinik", "(___", "_____", "nama/"]
        if any(si in combined_text for si in sig_indicators) or any(k in combined_text for k in ["tanda tangan", "tandatangan", "signature", "paraf", "disetujui", "diperiksa", "dibuat oleh"]):
            return True

    return False


def _strip_references_from_pages(pages: list) -> list:
    """
    Strips out 'References', 'Daftar Pustaka', 'Bibliography', and literature citations
    from parsed pages of academic papers and journals.
    Ensures that LLM context window, knowledge summary in FE, and chunk storage
    are dedicated purely to the scientific content (Introduction, Methods, Results, Discussion, Conclusion).
    """
    if not pages:
        return pages

    total_pages = len(pages)
    # References always appear towards the back half of an academic document
    min_page = max(1, total_pages // 2 - 1) if total_pages >= 4 else 0

    ref_heading_pattern = re.compile(
        r'^(?:#{1,3}\s*)?(?:REFERENCES?|DAFTAR\s+(?:PUSTAKA|REFERENSI|RUJUKAN)|BIBLIOGRAPHY|LITERATURE\s+CITED|CITED\s+LITERATURE|PUSTAKA\s+ACUAN|SENARAI\s+PUSTAKA|RUJUKAN)\s*$',
        re.IGNORECASE
    )

    cutoff_page = None
    cutoff_line_idx = None

    for p_idx in range(min_page, total_pages):
        text = pages[p_idx].get("text", "")
        lines = text.splitlines()
        for l_idx, line in enumerate(lines):
            clean = line.strip()
            if ref_heading_pattern.match(clean):
                # Verify that following lines are actual citations, not table contents
                following = [lines[j].strip() for j in range(l_idx + 1, min(l_idx + 25, len(lines))) if lines[j].strip()]
                numbered_hits = sum(1 for f in following if re.match(r'^(?:\[\d+\]|\d+[\.\)])\s*', f))
                doi_hits = sum(1 for f in following if 'doi:' in f.lower() or 'doi.org' in f.lower() or 'http' in f.lower())
                author_hits = sum(1 for f in following if 'et al' in f.lower() or re.search(r'\b(19\d\d|20\d\d)\b', f))
                has_table_words = any(w in " ".join(following).lower() for w in ['cleanser', 'moisturizer', 'sunscreen', 'table ', 'tabel '])

                if (numbered_hits >= 2 or doi_hits >= 1 or author_hits >= 2) and not has_table_words:
                    cutoff_page = p_idx
                    cutoff_line_idx = l_idx
                    break
        if cutoff_page is not None:
            break

    if cutoff_page is None:
        return pages

    logger.info(f"📚 Stripping references/daftar pustaka starting at page {cutoff_page + 1}, line {cutoff_line_idx + 1} (Total pages: {total_pages} -> {cutoff_page + 1})")

    cleaned_pages = []
    for p_idx in range(cutoff_page):
        cleaned_pages.append(pages[p_idx])

    # For the cutoff page, keep lines prior to the references heading
    cutoff_p_text = pages[cutoff_page].get("text", "")
    lines = cutoff_p_text.splitlines()
    kept_lines = lines[:cutoff_line_idx]
    kept_text = "\n".join(kept_lines).strip()
    if kept_text:
        new_page = dict(pages[cutoff_page])
        new_page["text"] = kept_text
        cleaned_pages.append(new_page)

    return cleaned_pages


def _strip_signature_and_approval_blocks(pages: list) -> list:
    """
    Strips out bureaucratic signature blocks, 'Lembar Persetujuan', 'Lembar Pengesahan',
    and approval sheets from SOPs, clinical protocols, and official letters.
    Keeps actionable clinical procedures, monitoring, aftercare, and treatment guidelines.
    """
    if not pages:
        return pages

    approval_heading_pattern = re.compile(
        r'^(?:#{1,4}\s*)?(?:\d+[\.\)]\s*)?(?:PERSETUJUAN\s+DAN\s+TANDA\s+TANGAN|LEMBAR\s+(?:PENGESAHAN|PERSETUJUAN)|HALAMAN\s+PENGESAHAN|TANDA\s+TANGAN\s+(?:DAN\s+)?PENGESAHAN|TANDA\s+TANGAN|SIGNATURES?|APPROVAL\s+SHEET|SIGN-?OFF)\s*$',
        re.IGNORECASE
    )

    sig_table_header_pattern = re.compile(
        r'^(?:Dibuat\s+Oleh|Disiapkan\s+Oleh|Diajukan\s+Oleh)\s+(?:Diperiksa\s+Oleh|Diketahui\s+Oleh)?\s*(?:Disetujui\s+Oleh|Disahkan\s+Oleh)',
        re.IGNORECASE
    )

    letter_closing_pattern = re.compile(
        r'^(?:Hormat\s+kami|Mengetahui|Disetujui\s+oleh|Disahkan\s+oleh)\s*[,:]?\s*$',
        re.IGNORECASE
    )

    cleaned_pages = []

    for p_idx, page in enumerate(pages):
        text = page.get("text", "")
        if not text:
            cleaned_pages.append(page)
            continue

        lines = text.splitlines()

        # Check if the entire page is an approval sheet / lembar pengesahan
        page_first_lines = [l.strip() for l in lines[:6] if l.strip()]
        is_full_approval_page = any(
            re.match(r'^(?:#{1,3}\s*)?(?:LEMBAR\s+(?:PENGESAHAN|PERSETUJUAN)|HALAMAN\s+PENGESAHAN|APPROVAL\s+SHEET)\s*$', l, re.IGNORECASE)
            for l in page_first_lines
        ) and any(w in text.lower() for w in ["disetujui oleh", "diperiksa oleh", "tanda tangan", "mengetahui", "dibuat oleh"])

        if is_full_approval_page:
            logger.info(f"📋 Stripping entire approval sheet page {p_idx + 1}")
            continue

        cutoff_line = None
        for l_idx, line in enumerate(lines):
            clean = line.strip()
            # 1. Heading match
            if approval_heading_pattern.match(clean):
                following = [lines[j].strip() for j in range(l_idx + 1, min(l_idx + 20, len(lines))) if lines[j].strip()]
                following_text = " ".join(following).lower()
                if any(w in following_text for w in ["tanda tangan", "dibuat oleh", "disetujui oleh", "diperiksa oleh", "tanggal:", "terapis", "supervisor", "(___", "_____"]):
                    cutoff_line = l_idx
                    break
            # 2. Signature table header match without explicit section heading
            if sig_table_header_pattern.match(clean):
                cutoff_line = l_idx
                break
            # 3. Official letter closing signature match
            if letter_closing_pattern.match(clean):
                following = [lines[j].strip() for j in range(l_idx + 1, min(l_idx + 8, len(lines))) if lines[j].strip()]
                following_text = " ".join(following).lower()
                if any(w in following_text for w in ["(___", ".....", "direktur", "kepala", "manajer", "pic", "dokter", "terapis"]):
                    cutoff_line = l_idx
                    break

        if cutoff_line is not None:
            logger.info(f"📋 Stripping signature block on page {p_idx + 1} starting at line {cutoff_line + 1}: '{lines[cutoff_line].strip()}'")
            kept_lines = lines[:cutoff_line]
            kept_text = "\n".join(kept_lines).strip()
            if kept_text:
                new_page = dict(page)
                new_page["text"] = kept_text
                # Clean up any image URLs in page metadata that were exclusively in the stripped signature block
                if "image_urls" in new_page and isinstance(new_page["image_urls"], list):
                    valid_urls = [u for u in new_page["image_urls"] if u in kept_text]
                    new_page["image_urls"] = valid_urls
                    new_page["image_url"] = valid_urls[0] if valid_urls else None
                cleaned_pages.append(new_page)
        else:
            cleaned_pages.append(page)

    return cleaned_pages


def _is_valid_grid_table(table, page_height: float) -> bool:
    """
    Validates whether a candidate table from PyMuPDF find_tables is an actual data table
    and not a false grouping of multi-column narrative paragraphs or horizontal decorative rules.
    """
    data = table.extract()
    if not data or len(data) < 2 or len(data[0]) < 2:
        return False
    headers = [str(c or '').strip() for c in data[0]]
    cols = len(headers)
    rows = len(data)

    # 1. Reject if more than 25% of column headers are empty
    empty_headers = sum(1 for h in headers if not h)
    if (empty_headers / cols) > 0.25:
        return False

    # 2. Reject if any header is longer than 12 words (indicates a paragraph in cell)
    for h in headers:
        if len(h.split()) > 12:
            return False

    # 3. Reject if header is a major section title (e.g. METHOD, ABSTRACT, INTRODUCTION)
    section_kws = {'method', 'methods', 'abstract', 'introduction', 'results', 'discussion', 'conclusion', 'references'}
    for h in headers:
        if h.lower().strip() in section_kws:
            return False

    # 4. Sparsity and narrative density check
    total_cells = rows * cols
    empty_cells = sum(1 for r in data for c in r if not str(c or '').strip())
    long_narrative = sum(1 for r in data for c in r if len(str(c or '').strip().split()) > 25)
    if total_cells >= 8 and (empty_cells / total_cells) > 0.65:
        return False

    tbl_height = table.bbox[3] - table.bbox[1]
    if page_height > 0 and (tbl_height / page_height) > 0.40 and long_narrative >= 2:
        return False

    return True


def _extract_in_paragraph_tables(page, non_footers: list, h_lines: list) -> Tuple[list, set]:
    """
    Extracts in-paragraph open / academic three-line tables (e.g. Table 1, Table 2, Table 3)
    embedded within scientific papers and clinical reports.
    Reconstructs them as clean Markdown tables with captions and footnotes,
    and returns (academic_tables, consumed_block_indices).
    """
    import fitz
    academic_tables = []
    consumed = set()

    caption_candidates = []
    for bi, b in enumerate(non_footers):
        text = b[4].strip()
        first_line = text.splitlines()[0] if text else ''
        m = re.match(r'^(?:Table|Tabel)\s+(\d+)[\.:]\s*(.+)', first_line, re.I)
        if m:
            caption_candidates.append((bi, b, m.group(0).strip()))

    for ci, (c_bi, c_block, full_cap) in enumerate(caption_candidates):
        y0 = c_block[1]
        next_cap_y = caption_candidates[ci + 1][1][1] if ci + 1 < len(caption_candidates) else page.rect.height - 45
        candidates = [l for l in h_lines if l.y0 >= c_block[3] - 4 and l.y1 < next_cap_y]
        if not candidates:
            continue

        t_lines = [candidates[0]]
        for l in candidates[1:]:
            if l.y0 - t_lines[-1].y0 < 100:
                t_lines.append(l)
            else:
                break

        y_top = min(l.y0 for l in t_lines)
        y_bottom = max(l.y1 for l in t_lines)
        top_segs = [l for l in t_lines if abs(l.y0 - y_top) < 3]
        top_segs.sort(key=lambda s: s.x0)
        x0 = min(l.x0 for l in t_lines) - 4
        x1 = max(l.x1 for l in t_lines) + 4

        footnote = ''
        fn_b = None
        fn_bi = None
        for bi, b in enumerate(non_footers):
            if bi == c_bi or bi in consumed:
                continue
            if y_bottom - 2 <= b[1] <= y_bottom + 35:
                fl = b[4].strip().splitlines()[0]
                if re.match(r'^(?:\([+-]\)\s*:|\*|\†|Note:|\bKet\b|\bKeterangan\b)', fl, re.I):
                    footnote = fl
                    fn_b = b
                    fn_bi = bi
                    break

        tbl_rect = fitz.Rect(x0, y_top + 1.0, x1, y_bottom - 0.5)
        words = page.get_text('words', clip=tbl_rect)
        if fn_b:
            words = [w for w in words if w[3] <= fn_b[1] + 2]

        rows_dict = {}
        for w in words:
            y_mid = (w[1] + w[3]) / 2.0
            matched = None
            for ry in rows_dict:
                if abs(ry - y_mid) < 4:
                    matched = ry
                    break
            if matched is None:
                rows_dict[y_mid] = [w]
            else:
                rows_dict[matched].append(w)

        sorted_rys = sorted(rows_dict.keys())
        if len(sorted_rys) < 2:
            continue

        col_bounds = []
        if len(top_segs) >= 3:
            for i, seg in enumerate(top_segs):
                c_min = seg.x0 - 5
                c_max = seg.x1 + 5 if i == len(top_segs) - 1 else (seg.x1 + top_segs[i + 1].x0) / 2.0
                col_bounds.append((c_min, c_max))
        else:
            best_row = None
            max_items = 0
            for ry in sorted_rys:
                rw = sorted(rows_dict[ry], key=lambda x: x[0])
                if len(rw) > max_items:
                    max_items = len(rw)
                    best_row = rw
            if best_row and max_items >= 4:
                sym_idxs = [idx for idx, w in enumerate(best_row) if w[4] in ('+', '-', '–')]
                if sym_idxs:
                    first_sym_idx = sym_idxs[0]
                    label_end = best_row[first_sym_idx - 1][2]
                    sym_start = best_row[first_sym_idx][0]
                    col_bounds.append((x0, (label_end + sym_start) / 2.0))
                    for si in range(first_sym_idx, len(best_row)):
                        w = best_row[si]
                        c_min = col_bounds[-1][1]
                        c_max = x1 if si == len(best_row) - 1 else (w[2] + best_row[si + 1][0]) / 2.0
                        col_bounds.append((c_min, c_max))

        if not col_bounds or len(col_bounds) < 2:
            continue

        num_cols = len(col_bounds)
        rows_grid = []
        for ry in sorted_rys:
            rw = sorted(rows_dict[ry], key=lambda x: x[0])
            cells = [''] * num_cols
            for w in rw:
                w_mid = (w[0] + w[2]) / 2.0
                for ci, (cmin, cmax) in enumerate(col_bounds):
                    if cmin <= w_mid < cmax:
                        cells[ci] = (cells[ci] + ' ' + w[4]).strip()
                        break
            if any(cells):
                rows_grid.append(cells)

        if not rows_grid:
            continue

        header_lines = [l for l in t_lines if abs(l.y0 - y_top) > 5 and abs(l.y1 - y_bottom) > 5]
        y_hdr_sep = min(l.y0 for l in header_lines) if header_lines else None

        header_rows = []
        data_rows = []
        if y_hdr_sep is not None:
            for ry, cells in zip(sorted_rys, rows_grid):
                if ry <= y_hdr_sep + 3:
                    header_rows.append(cells)
                else:
                    data_rows.append(cells)
        else:
            header_rows = [rows_grid[0]]
            data_rows = rows_grid[1:]

        merged_headers = [''] * num_cols
        for hr in header_rows:
            for ci, val in enumerate(hr):
                if val:
                    if ci >= 3 and num_cols == 8:
                        nums = re.findall(r'\b\d+(?:\.\d+)?\b', val)
                        if nums:
                            merged_headers[ci] = f'{nums[-1]}%'
                            continue
                    merged_headers[ci] = (merged_headers[ci] + ' ' + val).strip()

        headers = [h if h else f'Kolom {ci+1}' for ci, h in enumerate(merged_headers)]
        aligns = [':---' if ci == 0 else ':---:' for ci in range(num_cols)]

        md_lines = [f'### {full_cap}', '', '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(aligns) + ' |']
        for dr in data_rows:
            md_lines.append('| ' + ' | '.join(dr) + ' |')
        if footnote:
            md_lines.append('')
            md_lines.append(f'*{footnote}*')

        consumed.add(c_bi)
        if fn_bi is not None:
            consumed.add(fn_bi)
        for bi, b in enumerate(non_footers):
            if bi in consumed:
                continue
            b_cx = (b[0] + b[2]) / 2.0
            b_cy = (b[1] + b[3]) / 2.0
            if x0 - 5 <= b_cx <= x1 + 5 and y_top - 2 <= b_cy <= y_bottom + 10:
                consumed.add(bi)

        academic_tables.append({
            'y0': y0,
            'md': '\n'.join(md_lines),
            'bbox': (x0, y0, x1, y_bottom)
        })

    return academic_tables, consumed


class DocumentParser:
    """
    Smart Document Parser with two extraction paths:
    
    1. FAST PATH (python-docx / pypdf / plain read):
       - For .docx, .txt, and PDF files that contain selectable digital text.
       - Extracts text in < 1 second.
       
    2. DOCLING OCR FALLBACK:
       - For scanned/image-based PDFs where no selectable text exists.
       - Uses Docling's deep layout + OCR model pipeline (~60-120s on CPU).
    """

    def __init__(self):
        logger.info("Initializing Smart DocumentParser (Fast + Docling Selective Fallback)...")
        self._docling_converter = None  # Lazy-loaded only when needed

    def _get_docling_converter(self):
        """Lazy-load Docling DocumentConverter only when OCR is actually needed."""
        if self._docling_converter is None:
            logger.info("Loading Docling DocumentConverter for OCR fallback (first use)...")
            from docling.document_converter import DocumentConverter
            self._docling_converter = DocumentConverter()
        return self._docling_converter

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: DOCX
    # -------------------------------------------------------------------------
    def _parse_docx_fast(self, file_path: str) -> ParseResult:
        """Extract text from .docx using python-docx with heading hierarchy, inline images, and table structure."""
        from docx import Document as DocxDocument
        import re
        import os

        doc = DocxDocument(file_path)
        pages = []
        current_page_text = []
        page_num = 1

        # 1. Pre-extract and upload embedded images from docx relationships
        rid_to_url = {}
        extracted_image_urls = []
        try:
            from app.services.storage import upload_image

            for rId, rel in doc.part.rels.items():
                if hasattr(rel, "target_ref") and "image" in str(rel.target_ref).lower() and hasattr(rel, "target_part"):
                    try:
                        img_bytes = rel.target_part.blob
                        is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not img_bytes:
                            continue
                        fname = f"docx_img_{rId}_{os.path.basename(rel.target_ref).split('.')[0]}.{img_ext}"
                        upload_res = upload_image(img_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            rid_to_url[rId] = img_url
                            extracted_image_urls.append(img_url)
                            logger.info(f"🖼️ Extracted and uploaded embedded DOCX image '{rel.target_ref}' (rId: {rId}) -> {img_url}")
                    except Exception as upload_err:
                        logger.debug(f"Failed uploading image for rId {rId}: {upload_err}")
        except Exception as img_init_err:
            logger.debug(f"DOCX rel image extraction error: {img_init_err}")

        # Fallback zip extraction if relationship extraction yielded nothing
        if not extracted_image_urls:
            try:
                import zipfile
                from app.services.storage import upload_image

                with zipfile.ZipFile(file_path, 'r') as z:
                    media_files = [f for f in z.namelist() if f.startswith('word/media/')]
                    for idx, media_name in enumerate(media_files, start=1):
                        img_bytes = z.read(media_name)
                        is_valid, clean_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not clean_bytes:
                            continue
                        fname = f"docx_img_{idx}_{os.path.basename(media_name).split('.')[0]}.{img_ext}"
                        upload_res = upload_image(clean_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            extracted_image_urls.append(img_url)
            except Exception as zip_err:
                logger.debug(f"DOCX zip fallback image extraction skipped: {zip_err}")

        # 2. Extract paragraphs with inline images
        for para in doc.paragraphs:
            text = para.text.strip()
            blips = para._element.xpath('.//a:blip/@r:embed')
            img_tags = [f"![Gambar]({rid_to_url[rId]})" for rId in blips if rId in rid_to_url]
            if img_tags:
                if text:
                    text = f"{text}\n\n" + "\n\n".join(img_tags)
                else:
                    text = "\n\n".join(img_tags)

            if not text:
                continue

            # Check for page break in paragraph runs
            has_page_break = False
            for run in para.runs:
                if run._element.xml and "w:br" in run._element.xml and 'w:type="page"' in run._element.xml:
                    has_page_break = True
                    break

            if has_page_break and current_page_text:
                pages.append({"page": page_num, "text": "\n\n".join(current_page_text)})
                current_page_text = []
                page_num += 1

            # Detect style-based headings or bold title lines
            style_name = para.style.name.lower() if para.style else ""
            is_bold_para = para.runs and all(run.bold for run in para.runs if run.text.strip()) and len(text) < 120

            if "title" in style_name:
                formatted_text = f"# {text}"
            elif "heading 1" in style_name:
                formatted_text = f"# {text}"
            elif "heading 2" in style_name:
                formatted_text = f"## {text}"
            elif "heading 3" in style_name or "heading 4" in style_name:
                formatted_text = f"### {text}"
            elif re.match(r"^\d+\.\d+\s+", text):
                formatted_text = f"### {text}"
            elif re.match(r"^\d+\.\s+[A-Z]", text) and len(text) < 80:
                formatted_text = f"## {text}"
            elif is_bold_para and not text.startswith("#"):
                formatted_text = f"### {text}"
            else:
                formatted_text = text

            current_page_text.append(formatted_text)

        # 3. Extract tables in docx as clean markdown tables (including embedded images in cells)
        for table in doc.tables:
            table_rows = []
            header_cells = [cell.text.strip() for cell in table.rows[0].cells] if table.rows else []
            for row in table.rows:
                row_cells = []
                for c_idx, cell in enumerate(row.cells):
                    c_text = cell.text.strip().replace("\n", " ")
                    blips = cell._element.xpath('.//a:blip/@r:embed')
                    if blips:
                        col_name = header_cells[c_idx] if c_idx < len(header_cells) and header_cells[c_idx] else "Gambar"
                        cell_img_tags = [f"![{col_name}]({rid_to_url[rId]})" for rId in blips if rId in rid_to_url]
                        if cell_img_tags:
                            if c_text:
                                c_text = f"{c_text} " + " ".join(cell_img_tags)
                            else:
                                c_text = " ".join(cell_img_tags)
                    row_cells.append(c_text)
                table_rows.append("| " + " | ".join(row_cells) + " |")
            if table_rows:
                if len(table_rows) >= 1:
                    col_count = len(table.columns)
                    delimiter = "| " + " | ".join(["---"] * col_count) + " |"
                    table_rows.insert(1, delimiter)
                current_page_text.append("\n".join(table_rows))

        # Flush remaining text
        if current_page_text:
            pages.append({"page": page_num, "text": "\n\n".join(current_page_text)})

        if extracted_image_urls and pages:
            pages[0]["image_urls"] = extracted_image_urls
            pages[0]["image_url"] = extracted_image_urls[0]

        pages = _strip_references_from_pages(pages)
        pages = _strip_signature_and_approval_blocks(pages)
        return ParseResult(pages=pages, method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: TXT
    # -------------------------------------------------------------------------
    def _parse_txt_fast(self, file_path: str) -> ParseResult:
        """Extract text from .txt file (instant)."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return ParseResult(pages=[{"page": 1, "text": content}], method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: PDF (with scanned detection)
    # -------------------------------------------------------------------------
    def _parse_pdf_fast(self, file_path: str, max_pages: int = 250) -> Optional[ParseResult]:
        """
        Extract text and embedded images from PDF using PyMuPDF (fitz).
        Features:
        - 2-Column journal layout detection (reads left column first, then right column)
        - Memory safeguard for long PDFs (max_pages cap + per-page text limits)
        - Fault-tolerant per-page extraction (corrupted pages don't abort entire file)
        - Extracts embedded images and links them with nearby product names
        """
        import fitz  # PyMuPDF
        import re
        from app.services.storage import upload_images_parallel

        try:
            doc = fitz.open(file_path)
        except Exception as open_err:
            logger.error(f"Failed to open PDF file {file_path}: {open_err}")
            return None

        total_pages = len(doc)
        if total_pages > max_pages:
            logger.warning(f"PDF exceeds max_pages ({total_pages} > {max_pages}). Processing first {max_pages} pages for memory stability.")
            num_pages = max_pages
        else:
            num_pages = total_pages

        pages = []
        total_chars = 0
        pages_with_text = 0
        upload_batch = []
        page_layouts = []

        for i in range(num_pages):
            try:
                page = doc[i]
                page_width = page.rect.width
                page_height = page.rect.height
                midpoint = page_width / 2.0

                blocks = page.get_text("blocks")
                text_blocks = [b for b in blocks if len(b) >= 5 and b[4].strip() and (len(b) < 7 or b[6] == 0)]
                footers = [b for b in text_blocks if b[1] > page_height - 45]
                non_footers = [b for b in text_blocks if b[1] <= page_height - 45]

                # 1. Grid Tables detection (lines strategy) with validation
                grid_tables = []
                consumed_indices = set()
                try:
                    tabs = page.find_tables(strategy="lines")
                    for t in tabs.tables:
                        if not _is_valid_grid_table(t, page_height):
                            continue
                        data = t.extract()
                        if not data or len(data) < 2 or len(data[0]) < 2:
                            continue
                        headers = [re.sub(r'\s+', ' ', str(c or '')).strip() for c in data[0]]
                        headers = [h if h else f"Kolom {ci+1}" for ci, h in enumerate(headers)]
                        aligns = ['---'] * len(headers)
                        rows = []
                        for r in data[1:]:
                            clean_row = []
                            for c in r:
                                val = re.sub(r'\s+', ' ', str(c or '')).strip()
                                val = re.sub(r'_{4,}', '-', val)
                                clean_row.append(val)
                            if len(clean_row) < len(headers):
                                clean_row.extend([''] * (len(headers) - len(clean_row)))
                            rows.append('| ' + ' | '.join(clean_row[:len(headers)]) + ' |')
                        md_table = '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(aligns) + ' |\n' + '\n'.join(rows)
                        grid_tables.append({
                            "y0": t.bbox[1],
                            "md": md_table,
                            "bbox": t.bbox
                        })
                        for bi, b in enumerate(non_footers):
                            b_cx = (b[0] + b[2]) / 2.0
                            b_cy = (b[1] + b[3]) / 2.0
                            if t.bbox[0] - 5 <= b_cx <= t.bbox[2] + 5 and t.bbox[1] - 5 <= b_cy <= t.bbox[3] + 5:
                                consumed_indices.add(bi)
                except Exception as tab_err:
                    logger.debug(f"Table detection on page {i+1}: {tab_err}")

                # 1b. In-paragraph open academic tables (Table 1, Table 2, Table 3, etc.)
                try:
                    drawings = page.get_drawings()
                    h_lines = [d["rect"] for d in drawings if d.get("rect") and d["rect"].height <= 3 and d["rect"].width > 50]
                    h_lines.sort(key=lambda r: r.y0)
                    acad_tables, acad_consumed = _extract_in_paragraph_tables(page, non_footers, h_lines)
                    consumed_indices.update(acad_consumed)
                    grid_tables.extend(acad_tables)
                except Exception as acad_err:
                    logger.debug(f"Academic table extraction on page {i+1}: {acad_err}")

                # 2. Extract embedded images info on this page
                img_infos = page.get_image_info(xrefs=True)
                if not img_infos:
                    raw_imgs = page.get_images()
                    img_infos = [{"xref": im[0], "bbox": [0, 0, 0, 0]} for im in raw_imgs if len(im) > 0]

                # 3. Detect SOP / Procedural Step Cards with Illustrations
                sop_step_data = None
                step_candidates = []
                for bi, b in enumerate(non_footers):
                    if bi in consumed_indices:
                        continue
                    first_line = b[4].strip().splitlines()[0]
                    m = re.match(r'^(?:Step\s+)?(\d+)[\.\:]\s*(.+)', first_line, re.IGNORECASE)
                    if m:
                        num = int(m.group(1))
                        title = m.group(2).strip()
                        # Exclude major document section titles
                        if any(k in title.lower() for k in [
                            'tujuan', 'ruang lingkup', 'persiapan', 'rangkaian',
                            'monitoring', 'aftercare', 'dokumentasi', 'persetujuan'
                        ]):
                            continue
                        b_lower = b[4].lower()
                        if 'prosedur' in b_lower or 'procedure' in b_lower or 'catatan' in b_lower:
                            step_candidates.append({'num': num, 'title': title, 'block': b, 'bi': bi})

                step_img_xrefs = {}
                if step_candidates and len(img_infos) > 0:
                    step_candidates.sort(key=lambda s: s["block"][1])
                    sorted_imgs = sorted(img_infos, key=lambda im: im.get('bbox', [0, 0, 0, 0])[1])

                    step_rows = []
                    for si, s in enumerate(step_candidates):
                        consumed_indices.add(s["bi"])
                        b = s["block"]
                        lines = [l.strip() for l in b[4].splitlines() if l.strip()]
                        proc_lines = []
                        for l in lines[1:]:
                            if l.lower() in ("prosedur", "procedure", "instruksi"):
                                continue
                            proc_lines.append(l)
                        proc_text = " ".join(proc_lines)

                        y_next = step_candidates[si+1]["block"][1] if si+1 < len(step_candidates) else page_height - 45
                        notes_text = "-"
                        for nbi, nb in enumerate(non_footers):
                            if nbi in consumed_indices:
                                continue
                            if nb[1] >= b[1] and nb[1] < y_next:
                                if "catatan" in nb[4].lower():
                                    consumed_indices.add(nbi)
                                    nb_lines = [l.strip() for l in nb[4].splitlines() if l.strip() and not l.startswith("___")]
                                    sub = [l for l in nb_lines if l.lower() not in ("catatan", "note", "notes", "keterangan")]
                                    if sub:
                                        notes_text = " ".join(sub)

                        # Match image by vertical overlap or index
                        img_item = None
                        s_top = b[1] - 30
                        s_bottom = y_next + 10
                        for im in sorted_imgs:
                            ib = im.get("bbox", [0, 0, 0, 0])
                            im_y_mid = (ib[1] + ib[3]) / 2.0
                            if s_top <= im_y_mid <= s_bottom:
                                img_item = im
                                break
                        if not img_item and si < len(sorted_imgs) and len(sorted_imgs) == len(step_candidates):
                            img_item = sorted_imgs[si]

                        xref = img_item["xref"] if img_item else None
                        step_dict = {
                            "num": s["num"],
                            "title": s["title"],
                            "procedure": proc_text,
                            "notes": notes_text,
                            "xref": xref,
                            "y0": b[1]
                        }
                        if xref:
                            step_img_xrefs[xref] = step_dict
                        step_rows.append(step_dict)

                    if step_rows:
                        sop_step_data = {
                            "y0": step_rows[0]["y0"],
                            "steps": step_rows
                        }

                # 4. Prepare image upload info for this page
                seen_xrefs = set()
                for img_idx, im in enumerate(img_infos):
                    xref = im.get("xref")
                    if not xref or xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)

                    try:
                        base_img = doc.extract_image(xref)
                    except Exception:
                        base_img = {}

                    smask = base_img.get("smask", 0)
                    img_bytes = None
                    img_ext = base_img.get("ext", "png")

                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.width < 40 or pix.height < 40:
                            continue
                        if getattr(pix, "is_unicolor", False):
                            continue
                        if hasattr(pix, "color_topusage"):
                            top_usage, top_color = pix.color_topusage()
                            if top_usage >= 0.95 and isinstance(top_color, (bytes, bytearray)) and len(top_color) >= 3:
                                if all(c < 18 for c in top_color[:3]):
                                    continue
                        if smask and smask > 0:
                            try:
                                mask_pix = fitz.Pixmap(doc, smask)
                                if mask_pix.colorspace != fitz.csGRAY:
                                    mask_pix = fitz.Pixmap(fitz.csGRAY, mask_pix)
                                if mask_pix.alpha:
                                    mask_pix = fitz.Pixmap(mask_pix, 0)
                                if pix.colorspace != fitz.csRGB:
                                    pix = fitz.Pixmap(fitz.csRGB, pix)
                                # Strip existing alpha channel before applying mask
                                # to prevent fitz ValueError: "pixmap must not have an alpha channel"
                                if pix.alpha:
                                    pix = fitz.Pixmap(pix, 0)  # drop alpha
                                if pix.width == mask_pix.width and pix.height == mask_pix.height:
                                    pix = fitz.Pixmap(pix, mask_pix)
                                    img_ext = "png"
                            except Exception:
                                pass
                        if pix.colorspace and pix.colorspace != fitz.csRGB and pix.colorspace != fitz.csGRAY:
                            try:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            except Exception:
                                pass
                        if getattr(pix, "is_unicolor", False):
                            continue
                        if img_ext.lower() in ("jpg", "jpeg") and not pix.alpha:
                            img_bytes = pix.tobytes("jpeg")
                        else:
                            img_bytes = pix.tobytes("png")
                            img_ext = "png"
                    except Exception as pix_err:
                        logger.debug(f"Pixmap processing fallback for xref {xref}: {pix_err}")
                        img_bytes = base_img.get("image")
                        img_ext = base_img.get("ext", "png")

                    is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                    if not is_valid or not img_bytes:
                        continue

                    bbox = im.get("bbox", [0, 0, 0, 0])
                    img_y_mid = (bbox[1] + bbox[3]) / 2.0

                    prod_label = ""
                    matched_step = step_img_xrefs.get(xref)
                    if matched_step:
                        prod_label = matched_step["title"]

                    if not prod_label:
                        best_block = None
                        best_dist = float("inf")
                        for b in non_footers:
                            b_y_mid = (b[1] + b[3]) / 2.0
                            dist = abs(b_y_mid - img_y_mid)
                            if dist < best_dist:
                                best_dist = dist
                                best_block = b

                        if best_block and best_dist <= 100:
                            lines = [l.strip() for l in best_block[4].splitlines() if l.strip()]
                            for l in lines:
                                if re.match(r'^(?:figure|fig\.|gambar|diagram|bagan|grafik)\s+[ivx0-9]+', l, re.IGNORECASE):
                                    prod_label = l
                                    break
                            if not prod_label:
                                skip_labels = {
                                    "foto produk", "nama produk", "brand", "kategori", "ukuran", "deskripsi",
                                    "no", "action", "gambar", "catatan", "note", "notes", "keterangan",
                                    "prosedur", "procedure", "status", "checklist", "field", "isi / catatan"
                                }
                                for l in lines:
                                    clean_l = re.sub(r'^[0-9\.\-\*\•\s]+', '', l).strip()
                                    if clean_l.lower() in skip_labels or clean_l.startswith("___"):
                                        continue
                                    prod_label = l
                                    break

                    if not prod_label:
                        prod_label = f"Image p{i+1}_{img_idx+1}"

                    # Filter out non-substantive ornamental images
                    clip_rect = fitz.Rect(
                        max(0, bbox[0] - 80),
                        max(0, bbox[1] - 100),
                        min(page_width, bbox[2] + 80),
                        min(page_height, bbox[3] + 100)
                    )
                    surrounding_text = page.get_text("text", clip=clip_rect).strip()

                    # If image is in the upper 35% of the page, also grab the full-width header strip
                    # so logos in the top-right corner catch journal titles on the top-left
                    header_zone_y = page_height * (0.35 if i == 0 else 0.18)
                    if bbox[1] < header_zone_y:
                        header_rect = fitz.Rect(0, 0, page_width, min(page_height, max(bbox[3] + 50, header_zone_y)))
                        header_text = page.get_text("text", clip=header_rect).strip()
                        surrounding_text = f"{header_text} {surrounding_text}"

                    # If image is in bottom 18% of the page, also grab full-width footer strip
                    if bbox[3] > page_height * 0.82:
                        footer_rect = fitz.Rect(0, max(0, min(bbox[1] - 50, page_height * 0.82)), page_width, page_height)
                        footer_text = page.get_text("text", clip=footer_rect).strip()
                        surrounding_text = f"{footer_text} {surrounding_text}"

                    nearby_text = f"{prod_label} {surrounding_text}"
                    if _is_ornamental_pdf_image(
                        pix_width=pix.width,
                        pix_height=pix.height,
                        bbox=bbox,
                        page_height=page_height,
                        page_idx=i,
                        nearby_text=nearby_text,
                        prod_label=prod_label
                    ):
                        logger.info(f"Filtered out ornamental/metadata PDF image on page {i+1}: '{prod_label}' ({pix.width}x{pix.height})")
                        continue

                    clean_fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', prod_label)[:40].strip('_')
                    if not clean_fname:
                        clean_fname = f"pdf_img_p{i+1}_{img_idx+1}"
                    else:
                        clean_fname = f"pdf_img_p{i+1}_{img_idx+1}_{clean_fname}"

                    fname = f"{clean_fname}.{img_ext}"
                    upload_batch.append({
                        "content": img_bytes,
                        "filename": fname,
                        "content_type": f"image/{img_ext}",
                        "page_index": i,
                        "img_fname": fname,
                        "product_name": prod_label,
                        "xref": xref,
                        "step_num": matched_step["num"] if matched_step else None
                    })

                # 5. Build non-consumed text blocks
                remaining_blocks = [b for bi, b in enumerate(non_footers) if bi not in consumed_indices and b[1] >= 35]

                # 2-Column layout ordering for remaining blocks
                def _is_spanning_block(b):
                    w = b[2] - b[0]
                    if w > page_width * 0.62:
                        return True
                    if b[0] < (midpoint - 60) and b[2] > (midpoint + 60):
                        return True
                    return False

                sorted_by_y = sorted(remaining_blocks, key=lambda b: b[1])
                slices = []
                current_slice = []
                for b in sorted_by_y:
                    if _is_spanning_block(b):
                        if current_slice:
                            slices.append(('col', current_slice))
                            current_slice = []
                        slices.append(('span', [b]))
                    else:
                        current_slice.append(b)
                if current_slice:
                    slices.append(('col', current_slice))

                ordered_remaining = []
                for stype, sblocks in slices:
                    if stype == 'span':
                        ordered_remaining.extend(sblocks)
                    else:
                        lefts = [b for b in sblocks if (b[0] + b[2]) / 2.0 < midpoint]
                        rights = [b for b in sblocks if (b[0] + b[2]) / 2.0 >= midpoint]
                        if lefts and rights:
                            lefts.sort(key=lambda b: b[1])
                            rights.sort(key=lambda b: b[1])
                            ordered_remaining.extend(lefts)
                            ordered_remaining.extend(rights)
                        else:
                            sblocks.sort(key=lambda b: (round(b[1] / 5) * 5, b[0]))
                            ordered_remaining.extend(sblocks)

                page_layouts.append({
                    "page_idx": i,
                    "grid_tables": grid_tables,
                    "sop_step_data": sop_step_data,
                    "ordered_blocks": ordered_remaining,
                    "footers": footers
                })
                pages.append({"page": i + 1, "text": ""})

            except Exception as page_err:
                logger.warning(f"Error parsing page {i+1} of {file_path}: {page_err}")
                pages.append({"page": i + 1, "text": f"[Halaman {i+1} gagal diekstraksi: {page_err}]"})
                page_layouts.append({"page_idx": i, "grid_tables": [], "sop_step_data": None, "ordered_blocks": [], "footers": []})

        # Upload images and assemble pages
        try:
            url_by_xref = {}
            url_by_step = {}
            if upload_batch:
                results = upload_images_parallel(upload_batch)
                for item, res in zip(upload_batch, results):
                    img_url = res.get("image_url")
                    p_idx = item["page_index"]
                    fname = item["img_fname"]
                    prod_name = item.get("product_name") or fname
                    xref = item.get("xref")
                    step_num = item.get("step_num")

                    if img_url:
                        if xref:
                            url_by_xref[xref] = img_url
                        if step_num is not None:
                            url_by_step[(p_idx, step_num)] = img_url

                        if p_idx < len(pages):
                            if "image_urls" not in pages[p_idx]:
                                pages[p_idx]["image_urls"] = []
                            if "images" not in pages[p_idx]:
                                pages[p_idx]["images"] = []
                            pages[p_idx]["image_urls"].append(img_url)
                            is_fig = bool(re.match(r'^(?:figure|fig\.|gambar|diagram|bagan|grafik)', prod_name, re.IGNORECASE)) or (step_num is not None)
                            pages[p_idx]["images"].append({
                                "id": f"img_p{p_idx+1}_{len(pages[p_idx]['images'])+1}",
                                "url": img_url,
                                "product_name": prod_name,
                                "caption": prod_name,
                                "role": "FIGURE" if is_fig else "PRODUCT_PACKAGING"
                            })

            # Assemble structured text for each page
            for layout in page_layouts:
                p_idx = layout["page_idx"]
                if p_idx >= len(pages):
                    continue

                items_to_render = []

                # Add Grid Tables
                for gt in layout.get("grid_tables", []):
                    items_to_render.append((gt["y0"], gt["md"]))

                # Add SOP Step Table if present
                sop_data = layout.get("sop_step_data")
                if sop_data and sop_data.get("steps"):
                    rows = []
                    for s in sop_data["steps"]:
                        s_num = s["num"]
                        s_title = s["title"]
                        s_xref = s.get("xref")
                        img_url = url_by_step.get((p_idx, s_num)) or (url_by_xref.get(s_xref) if s_xref else None)
                        img_md = f"![{s_title}]({img_url})" if img_url else "-"
                        rows.append(f"| {s_num} | {s_title} | {img_md} | {s['procedure']} | {s['notes']} |")

                    md_sop = (
                        "| No | Tahapan Treatment | Ilustrasi | Prosedur | Catatan |\n"
                        "|:---:|:---|:---:|:---|:---:|\n" +
                        "\n".join(rows)
                    )
                    items_to_render.append((sop_data["y0"], md_sop))

                # Add non-consumed text blocks
                for b in layout.get("ordered_blocks", []):
                    items_to_render.append((b[1], b[4].strip()))

                # Sort all content by vertical position y0
                items_to_render.sort(key=lambda it: it[0])

                # Footers at the end
                for fb in layout.get("footers", []):
                    items_to_render.append((fb[1], fb[4].strip()))

                assembled_text = "\n\n".join(it[1] for it in items_to_render if it[1])

                # For non-step images, embed near their product_name if not already present
                if p_idx < len(pages) and pages[p_idx].get("images"):
                    for img_obj in pages[p_idx]["images"]:
                        p_name = img_obj["product_name"]
                        u = img_obj["url"]
                        if u not in assembled_text:
                            if p_name and p_name in assembled_text:
                                pattern = re.compile(rf'(^.*{re.escape(p_name)}.*$)', re.MULTILINE)
                                if pattern.search(assembled_text):
                                    assembled_text = pattern.sub(rf'\1\n![{p_name}]({u})', assembled_text, count=1)
                                else:
                                    assembled_text += f"\n\n![{p_name}]({u})"
                            else:
                                assembled_text += f"\n\n![{p_name}]({u})"

                # Memory protection
                if len(assembled_text) > 50000:
                    assembled_text = assembled_text[:50000] + "\n... [teks halaman dipadatkan untuk stabilitas]"

                pages[p_idx]["text"] = assembled_text
                char_count = len(assembled_text)
                total_chars += char_count
                if char_count > 30:
                    pages_with_text += 1

            for i in range(len(pages)):
                if pages[i].get("image_urls"):
                    pages[i]["image_url"] = pages[i]["image_urls"][0]

        except Exception as img_err:
            logger.warning(f"PDF embedded image extraction failed: {img_err}", exc_info=True)

        # Apply Structure Reconstruction / Document Normalization on each page's extracted text
        from app.rag.utils.normalizer import normalize_document_text
        for p in pages:
            if p.get("text"):
                p["text"] = normalize_document_text(p["text"])

        # Strip bibliography / references so chunking and frontend knowledge display
        # focus 100% on paper body, findings, and discussions
        pages = _strip_references_from_pages(pages)

        # Strip bureaucratic signature blocks and approval sheets from SOPs, protocols, and letters
        pages = _strip_signature_and_approval_blocks(pages)

        return ParseResult(pages=pages, method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: EXCEL & CSV (.xlsx, .xls, .csv)
    # -------------------------------------------------------------------------
    def _parse_excel_fast(self, file_path: str) -> ParseResult:
        """Extract text and markdown tables from .xlsx, .xls, and .csv files using openpyxl & pandas."""
        import pandas as pd

        ext = os.path.splitext(file_path)[1].lower()
        pages = []

        try:
            def _df_to_markdown_safe(dataframe) -> str:
                try:
                    return dataframe.to_markdown(index=False)
                except Exception:
                    headers = [str(c) for c in dataframe.columns]
                    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                    for _, row in dataframe.iterrows():
                        row_vals = ["" if pd.isna(v) else str(v).replace("\n", " ").strip() for v in row]
                        lines.append("| " + " | ".join(row_vals) + " |")
                    return "\n".join(lines)

            if ext == ".csv":
                df = pd.read_csv(file_path)
                df = df.dropna(how="all")
                md_table = _df_to_markdown_safe(df)
                pages.append({
                    "page": 1,
                    "sheet_name": "CSV",
                    "text": f"### CSV Data Table\n\n{md_table}",
                    "image_urls": [],
                    "image_url": None
                })
            else:
                # Use openpyxl for .xlsx/.xlsm to extract images per sheet with exact cell row anchors
                wb = None
                if ext in [".xlsx", ".xlsm"]:
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(file_path, data_only=True)
                    except Exception as wb_err:
                        logger.debug(f"openpyxl load failed, falling back to standard pandas: {wb_err}")
                        wb = None

                with pd.ExcelFile(file_path) as excel_file:
                    sheet_names = excel_file.sheet_names
                    logger.info(f"Parsing Excel with {len(sheet_names)} sheets: {sheet_names}")

                    from app.services.storage import upload_images_parallel

                    for page_idx, sheet_name in enumerate(sheet_names, start=1):
                        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                        if df.empty:
                            continue

                        from collections import defaultdict
                        sheet_image_urls = []
                        cell_to_images = defaultdict(list)
                        unanchored_images = []

                        # 0. Propagate merged cell values so multi-row headers are preserved across cells
                        if wb and sheet_name in wb.sheetnames:
                            ws = wb[sheet_name]
                            for rng in list(ws.merged_cells.ranges):
                                top_val = ws.cell(rng.min_row, rng.min_col).value
                                for r_m in range(rng.min_row - 1, rng.max_row):
                                    for c_m in range(rng.min_col - 1, rng.max_col):
                                        if r_m < len(df) and c_m < df.shape[1] and (pd.isna(df.iat[r_m, c_m]) or not str(df.iat[r_m, c_m]).strip()):
                                            df.iat[r_m, c_m] = top_val

                        # 1. Extract embedded images for THIS worksheet using 2D cell coordinates
                        if wb and sheet_name in wb.sheetnames:
                            ws = wb[sheet_name]
                            ws_images = getattr(ws, '_images', [])
                            upload_batch = []
                            img_meta = []

                            for idx, img in enumerate(ws_images):
                                try:
                                    raw_bytes = img._data()
                                except Exception:
                                    continue
                                is_valid, clean_bytes, img_ext = _is_valid_image_content(raw_bytes, min_dim=30)
                                if not is_valid or not clean_bytes:
                                    continue

                                anchor = getattr(img, 'anchor', None)
                                r, c = None, None
                                if anchor is not None:
                                    if hasattr(anchor, '_from') and getattr(anchor._from, 'row', None) is not None:
                                        r = anchor._from.row
                                        c = getattr(anchor._from, 'col', 0)
                                    elif hasattr(anchor, 'from') and getattr(getattr(anchor, 'from'), 'row', None) is not None:
                                        r = getattr(anchor, 'from').row
                                        c = getattr(getattr(anchor, 'from'), 'col', 0)
                                    elif isinstance(anchor, str):
                                        try:
                                            from openpyxl.utils import coordinate_to_tuple
                                            coord_r, coord_c = coordinate_to_tuple(anchor)
                                            r = coord_r - 1
                                            c = coord_c - 1
                                        except Exception:
                                            pass
                                    elif hasattr(anchor, 'pos') and hasattr(anchor.pos, 'y') and anchor.pos.y is not None:
                                        # Handle openpyxl AbsoluteAnchor using EMUs (1 pt = 12700 EMUs)
                                        try:
                                            y_emu = anchor.pos.y
                                            accum_emu = 0
                                            found_r = 1
                                            max_r = ws.max_row or 100
                                            for r_i in range(1, max_r + 2):
                                                r_dim = ws.row_dimensions.get(r_i)
                                                h_pt = r_dim.height if (r_dim and r_dim.height) else 15.0
                                                h_emu = int(h_pt * 12700)
                                                if accum_emu + h_emu > y_emu:
                                                    found_r = r_i
                                                    break
                                                accum_emu += h_emu
                                                found_r = r_i
                                            r = found_r - 1
                                            c = 0
                                        except Exception as abs_err:
                                            logger.debug(f"Error calculating AbsoluteAnchor row: {abs_err}")

                                safe_sheet_name = "".join(c_ch if c_ch.isalnum() else "_" for c_ch in sheet_name)
                                filename = f"excel_{safe_sheet_name}_img_{idx+1}.{img_ext}"
                                upload_batch.append({
                                    "content": clean_bytes,
                                    "filename": filename,
                                    "content_type": f"image/{img_ext}"
                                })
                                img_meta.append((r, c))

                            if upload_batch:
                                results = upload_images_parallel(upload_batch)
                                for (cell_r, cell_c), res in zip(img_meta, results):
                                    url = res.get("image_url")
                                    if url:
                                        sheet_image_urls.append(url)
                                        if cell_r is not None and 0 <= cell_r < len(df):
                                            c_val = cell_c if (cell_c is not None and 0 <= cell_c < df.shape[1]) else 0
                                            # Strict header shift: Only shift if the cell text is purely a short header label
                                            curr_cell_txt = str(df.iat[cell_r, c_val]).strip().lower()
                                            header_keywords = [
                                                "shampoo", "serum", "exfoliating", "nama tindakan",
                                                "foto", "gambar", "photo", "image", "foto produk", "gambar produk", "product image",
                                                "produk", "product", "tindakan", "treatment", "kategori", "category",
                                                "langkah", "step", "tahap", "cleanser", "toner", "moisturizer", "sunscreen", "cream", "lotion", "gel"
                                            ]
                                            is_pure_header = curr_cell_txt in header_keywords or (len(curr_cell_txt) <= 25 and any(curr_cell_txt == k for k in header_keywords))
                                            if is_pure_header and cell_r + 1 < len(df):
                                                below_txt = str(df.iat[cell_r + 1, c_val]).strip()
                                                if below_txt and below_txt != "nan":
                                                    cell_r = cell_r + 1
                                            cell_to_images[(cell_r, c_val)].append(url)
                                        else:
                                            unanchored_images.append(url)
                                total_anchored_cells = len(cell_to_images)
                                total_anchored_imgs = sum(len(v) for v in cell_to_images.values())
                                logger.info(f"Sheet '{sheet_name}': uploaded {len(sheet_image_urls)} images ({total_anchored_imgs} images anchored across {total_anchored_cells} cells, {len(unanchored_images)} unanchored).")

                        # 2. Inject anchored images directly into DataFrame cells WITHOUT raw <br> tags
                        for (r_idx, c_idx), img_urls in cell_to_images.items():
                            curr_val = "" if pd.isna(df.iat[r_idx, c_idx]) else str(df.iat[r_idx, c_idx]).strip()
                            curr_val_clean = " ".join(curr_val.split())
                            alt = curr_val_clean if curr_val_clean else f"Produk R{r_idx+1}C{c_idx+1}"
                            img_tags = " ".join(f"![{alt}]({u})" for u in img_urls)
                            # The MarkdownImage component in frontend already renders `alt` as the official card caption.
                            # Using img_tags directly prevents redundant plaintext from spilling outside and floating awkwardly around the card.
                            df.iat[r_idx, c_idx] = img_tags

                        # 3. Structural Block Detection: Separate Title/Metadata rows from Data Tables
                        blocks = []
                        current_table_rows = []

                        for r in range(len(df)):
                            raw_row = [("" if pd.isna(v) else str(v).strip()) for v in df.iloc[r]]
                            non_empty = [(c, v) for c, v in enumerate(raw_row) if v]

                            if not non_empty:
                                if current_table_rows:
                                    blocks.append({"type": "table", "rows": current_table_rows})
                                    current_table_rows = []
                                continue

                            # Single non-empty cell without image tag -> Title/Heading or Meta line
                            if len(non_empty) == 1 and "![" not in non_empty[0][1]:
                                txt = non_empty[0][1]
                                if current_table_rows:
                                    blocks.append({"type": "table", "rows": current_table_rows})
                                    current_table_rows = []

                                txt_lower = txt.lower()
                                if txt_lower in ["nama tindakan"]:
                                    # Redundant merge artifact row directly above table header
                                    continue
                                if any(k in txt_lower for k in ["cheatsheet", "katalog", "daftar", "panduan", "tabel"]):
                                    blocks.append({"type": "heading", "level": 3, "text": txt})
                                elif "updated" in txt_lower or "tanggal" in txt_lower:
                                    blocks.append({"type": "meta", "text": f"*{txt}*"})
                                else:
                                    blocks.append({"type": "text", "text": txt})
                            else:
                                current_table_rows.append(raw_row)

                        if current_table_rows:
                            blocks.append({"type": "table", "rows": current_table_rows})

                        # 4. Render Section Blocks into Clean Markdown
                        output_parts = []
                        for b in blocks:
                            if b["type"] == "heading":
                                output_parts.append(f"### {b['text']}")
                            elif b["type"] == "meta":
                                output_parts.append(b["text"])
                            elif b["type"] == "text":
                                output_parts.append(b["text"])
                            elif b["type"] == "table":
                                t_rows = b["rows"]
                                if not t_rows:
                                    continue

                                # A. Check for Side-by-Side Tables (Split by contiguous active column clusters)
                                num_total_cols = max(len(r) for r in t_rows)
                                col_has_data = [any(r[c].strip() for r in t_rows if c < len(r)) for c in range(num_total_cols)]
                                clusters = []
                                curr_cluster = []
                                for c, has_d in enumerate(col_has_data):
                                    if has_d:
                                        curr_cluster.append(c)
                                    else:
                                        if curr_cluster:
                                            clusters.append(curr_cluster)
                                            curr_cluster = []
                                if curr_cluster:
                                    clusters.append(curr_cluster)

                                # Split into sub-tables if multiple clusters are found separated by empty spacer columns
                                sub_tables = []
                                if len(clusters) > 1:
                                    for cl in clusters:
                                        sub_t = []
                                        for r in t_rows:
                                            sub_t.append([r[c] if c < len(r) else "" for c in cl])
                                        sub_tables.append(sub_t)
                                else:
                                    sub_tables = [t_rows]

                                for sub_rows in sub_tables:
                                    max_active_c = max((max(c for c, v in enumerate(r) if v) + 1 for r in sub_rows if any(r)), default=0)
                                    if max_active_c == 0:
                                        continue
                                    trimmed_rows = [r[:max_active_c] for r in sub_rows if any(r[:max_active_c])]
                                    if not trimmed_rows:
                                        continue

                                    # B. Check for Transposed Table (Row = Attributes, Col = Products)
                                    ATTR_KEYWORDS = {
                                        "nama", "nama produk", "produk", "product", "product name",
                                        "harga", "price", "biaya", "tarif", "sku", "kode", "code",
                                        "komposisi", "kandungan", "ingredients", "active ingredients",
                                        "indikasi", "indications", "manfaat", "benefits",
                                        "kontraindikasi", "contraindications", "cara pakai", "cara penggunaan",
                                        "directions", "how to use", "aturan pakai", "dosis", "dosage",
                                        "efek samping", "side effects", "kategori", "category",
                                        "netto", "ukuran", "kemasan", "packaging"
                                    }
                                    col0_vals = [r[0].strip().lower() for r in trimmed_rows if r and r[0].strip()]
                                    matches = sum(1 for v in col0_vals if any(v == k or v.startswith(k + " ") or v.endswith(" " + k) for k in ATTR_KEYWORDS))
                                    if len(col0_vals) >= 3 and (matches / len(col0_vals) >= 0.5) and len(trimmed_rows[0]) > 1:
                                        num_new_rows = max(len(r) for r in trimmed_rows)
                                        transposed = []
                                        for col_idx in range(num_new_rows):
                                            new_r = [trimmed_rows[r_idx][col_idx] if col_idx < len(trimmed_rows[r_idx]) else "" for r_idx in range(len(trimmed_rows))]
                                            transposed.append(new_r)
                                        trimmed_rows = transposed
                                        max_active_c = len(trimmed_rows[0])

                                    # C. Render trimmed_rows to Markdown table
                                    max_cols = max(len(r) for r in trimmed_rows)
                                    header_candidate = trimmed_rows[0]
                                    non_empty_h = sum(1 for v in header_candidate if v)
                                    is_valid_header = non_empty_h >= 2 and all("![" not in v for v in header_candidate)

                                    lines = []
                                    if is_valid_header and len(trimmed_rows) > 1:
                                        headers = [h if h else f"Kolom {i+1}" for i, h in enumerate(header_candidate)]
                                        lines.append("| " + " | ".join(headers) + " |")
                                        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
                                        body_rows = trimmed_rows[1:]
                                    else:
                                        headers = [f"Kolom {i+1}" for i in range(max_cols)]
                                        lines.append("| " + " | ".join(headers) + " |")
                                        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
                                        body_rows = trimmed_rows

                                    for r_vals in body_rows:
                                        padded = r_vals + [""] * (max_cols - len(r_vals))
                                        lines.append("| " + " | ".join(v.replace("\n", " ").strip() for v in padded) + " |")

                                    output_parts.append("\n".join(lines))

                        rendered_content = "\n\n".join(output_parts)
                        unanchored_md = ""
                        if unanchored_images:
                            unanchored_md = "\n".join(f"![Lampiran Gambar]({u})" for u in unanchored_images) + "\n\n"
                        sheet_text = f"## Sheet: {sheet_name}\n\n{unanchored_md}{rendered_content}"
                        pages.append({
                            "page": page_idx,
                            "sheet_name": sheet_name,
                            "text": sheet_text,
                            "image_urls": sheet_image_urls,
                            "image_url": sheet_image_urls[0] if sheet_image_urls else None
                        })

            if not pages:
                pages = [{"page": 1, "text": "Dokumen spreadsheet kosong.", "image_urls": [], "image_url": None}]

            return ParseResult(pages=pages, method="fast")
        except Exception as e:
            logger.warning(f"Fast Excel parse failed for {file_path}: {e}. Falling back to text extraction...")
            return ParseResult(pages=[{"page": 1, "text": f"Error parsing spreadsheet: {e}", "image_urls": [], "image_url": None}], method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: POWERPOINT (.pptx, .ppt)
    # -------------------------------------------------------------------------
    def _parse_pptx_fast(self, file_path: str) -> ParseResult:
        """Extracts text, slide titles, tables, and notes from PowerPoint (.pptx, .ppt) presentations."""
        try:
            from pptx import Presentation

            prs = Presentation(file_path)
            pages = []
            any_shape_has_image = False

            for slide_idx, slide in enumerate(prs.slides, start=1):
                slide_texts = []
                slide_image_urls = []
                slide_title = f"Slide {slide_idx}"

                # Extract title if present
                if slide.shapes.title and slide.shapes.title.text:
                    slide_title = slide.shapes.title.text.strip()
                    slide_texts.append(f"## {slide_title}")

                # 1. Detect spatial Before / After text labels on this slide
                before_labels = []
                after_labels = []
                for s in slide.shapes:
                    if s.has_text_frame:
                        s_text = s.text_frame.text.strip().upper()
                        if any(w in s_text for w in ["SEBELUM", "BEFORE"]):
                            before_labels.append((s.left, s.top, s_text))
                        elif any(w in s_text for w in ["SESUDAH", "AFTER", "SETELAH"]):
                            after_labels.append((s.left, s.top, s_text))

                # 2. Collect and classify image shapes spatially
                img_shapes_on_slide = [s for s in slide.shapes if hasattr(s, "image")]
                classified_images = []

                if img_shapes_on_slide:
                    any_shape_has_image = True
                    if before_labels and after_labels and len(img_shapes_on_slide) >= 2:
                        # Spatial proximity matching: match each image to closest label on X axis
                        scored_shapes = []
                        for s in img_shapes_on_slide:
                            dist_before = min(abs(s.left - bl[0]) for bl in before_labels)
                            dist_after = min(abs(s.left - al[0]) for al in after_labels)
                            scored_shapes.append((s, dist_before, dist_after))

                        # Shape with smallest distance to Before label is BEFORE
                        # Shape with smallest distance to After label is AFTER
                        # Sort so that BEFORE comes first (0), AFTER comes second (1)
                        scored_shapes.sort(key=lambda item: item[1] - item[2])
                        for idx, (s, d_b, d_a) in enumerate(scored_shapes):
                            role = "CLINICAL_BEFORE" if idx == 0 else "CLINICAL_AFTER"
                            classified_images.append((s, role))
                    else:
                        # Standard reading order: top-to-bottom, left-to-right
                        sorted_shapes = sorted(img_shapes_on_slide, key=lambda s: (round(s.top / 100000), s.left))
                        for s in sorted_shapes:
                            classified_images.append((s, "IMAGE"))

                # 3. Process non-image shapes (text & tables)
                for shape in slide.shapes:
                    if shape == slide.shapes.title or hasattr(shape, "image"):
                        continue
                    # Extract text frames
                    if shape.has_text_frame:
                        for paragraph in shape.text_frame.paragraphs:
                            text = paragraph.text.strip()
                            if text:
                                slide_texts.append(f"- {text}")

                    # Extract tables in slides
                    elif shape.has_table:
                        table_rows = []
                        table = shape.table
                        for row in table.rows:
                            row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                            table_rows.append("| " + " | ".join(row_cells) + " |")
                        if table_rows:
                            if len(table_rows) >= 1:
                                col_count = len(table.columns)
                                delimiter = "| " + " | ".join(["---"] * col_count) + " |"
                                table_rows.insert(1, delimiter)
                            slide_texts.append("\n".join(table_rows))

                # 4. Upload and append classified image shapes in deterministic order (BEFORE first, then AFTER)
                for img_idx, (shape, role) in enumerate(classified_images, start=1):
                    try:
                        from app.services.storage import upload_image
                        img_obj = shape.image
                        img_bytes = img_obj.blob
                        is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not img_bytes:
                            continue
                        role_tag = "before" if role == "CLINICAL_BEFORE" else ("after" if role == "CLINICAL_AFTER" else f"img_{img_idx}")
                        fname = f"pptx_s{slide_idx}_{role_tag}.{img_ext}"
                        upload_res = upload_image(img_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            slide_image_urls.append(img_url)
                            if role == "CLINICAL_BEFORE":
                                slide_texts.append(f"![Foto Sebelum Perawatan - {slide_title}]({img_url})")
                            elif role == "CLINICAL_AFTER":
                                slide_texts.append(f"![Foto Sesudah Perawatan - {slide_title}]({img_url})")
                            else:
                                slide_texts.append(f"![{slide_title} Image]({img_url})")
                    except Exception as shape_img_err:
                        logger.debug(f"PPTX slide image shape extraction skipped: {shape_img_err}")

                # Extract speaker notes if any
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_texts.append(f"**Notes:** {notes}")

                if slide_texts:
                    full_slide_content = f"### Slide {slide_idx}: {slide_title}\n\n" + "\n".join(slide_texts)
                    pages.append({
                        "page": slide_idx,
                        "text": full_slide_content,
                        "image_urls": slide_image_urls,
                        "image_url": slide_image_urls[0] if slide_image_urls else None
                    })

            if not pages:
                pages = [{"page": 1, "text": "Presentasi PowerPoint kosong."}]

            # Extract embedded images from .pptx media parts zip fallback ONLY if NO shapes had images
            if not any_shape_has_image:
                try:
                    import zipfile
                    from app.services.storage import upload_images_parallel

                    with zipfile.ZipFile(file_path, 'r') as z:
                        media_files = [f for f in z.namelist() if f.startswith('ppt/media/')]
                        upload_batch = []
                        for idx, media_name in enumerate(media_files, start=1):
                            img_bytes = z.read(media_name)
                            is_valid, clean_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                            if not is_valid or not clean_bytes:
                                continue
                            fname = f"pptx_img_{idx}_{os.path.basename(media_name).split('.')[0]}.{img_ext}"
                            upload_batch.append({
                                "content": clean_bytes,
                                "filename": fname,
                                "content_type": f"image/{img_ext}"
                            })
                        
                        if upload_batch:
                            results = upload_images_parallel(upload_batch)
                            extracted_image_urls = [r["image_url"] for r in results if r.get("image_url")]
                            if extracted_image_urls and pages:
                                existing_urls = pages[0].get("image_urls", [])
                                combined_urls = list(dict.fromkeys(existing_urls + extracted_image_urls))
                                pages[0]["image_urls"] = combined_urls
                                pages[0]["image_url"] = combined_urls[0]
                            logger.info(f"⚡ [ASYNC BATCH] Uploaded {len(extracted_image_urls)} embedded PPTX images to MinIO in parallel.")
                except Exception as img_err:
                    logger.debug(f"PPTX embedded image extraction skipped: {img_err}")

            return ParseResult(pages=pages, method="fast")
        except Exception as e:
            logger.warning(f"Fast PPTX parse failed for {file_path}: {e}. Falling back to Docling...")
            return self._parse_with_docling(file_path)

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: LEGACY DOC (.doc)
    # -------------------------------------------------------------------------
    def _parse_doc_fast(self, file_path: str) -> ParseResult:
        """Extract text from legacy .doc files using Docling OCR / parser."""
        return self._parse_with_docling(file_path)

    def _parse_standalone_image(self, file_path: str, fast_mode: bool = False) -> ParseResult:
        """
        Uploads standalone image file to MinIO S3 and extracts structured knowledge using 
        Generic Image Knowledge Extraction Vision LLM (with Docling OCR fallback)
        so it can be indexed in PGVector/BM25 and displayed by frontend during chatbot recommendations.
        """
        import base64
        import json
        import uuid
        from app.services.storage import upload_image

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower().replace(".", "")
        content_type = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "webp"] else "image/png"

        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()

            upload_res = upload_image(image_bytes, file_name, content_type=content_type)
            image_url = upload_res.get("image_url", "")
            s3_key = upload_res.get("s3_key", "")

            # If fast_mode or refine attachment: upload directly to MinIO and return instant ParseResult (<0.1s)
            if fast_mode or "refine_" in file_name or "supp_" in file_name or "refine" in file_path.lower():
                clean_title = os.path.splitext(file_name)[0]
                img_id = f"img_{uuid.uuid4().hex[:8]}"
                image_asset = {
                    "id": img_id,
                    "url": image_url,
                    "s3_key": s3_key,
                    "role": "PRODUCT_PACKAGING",
                    "product_name": clean_title,
                    "caption": f"Foto {clean_title}"
                }
                page_data = {
                    "page": 1,
                    "text": f"![{clean_title}]({image_url})",
                    "image_id": img_id,
                    "image_urls": [image_url] if image_url else [],
                    "image_url": image_url,
                    "images": [image_asset],
                    "s3_key": s3_key,
                    "storage_key": s3_key,
                    "image_reference": image_url,
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"],
                    "visibility_settings": {
                        "clinics": ["all"],
                        "doctor_types": ["all"],
                        "doctors": ["all"]
                    }
                }
                logger.info(f"⚡ [FAST IMAGE PARSE] Standalone image '{file_name}' uploaded to MinIO in < 0.1s ({image_url})")
                return ParseResult(pages=[page_data], method="fast")

            extracted_text = ""
            extracted_meta = {
                "s3_key": s3_key,
                "storage_key": s3_key,
                "image_url": image_url,
                "image_reference": image_url,
            }

            # --- Multimodal Vision LLM Extraction ---
            try:
                from app.rag.config import settings
                from openai import OpenAI

                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                data_uri = f"data:{content_type};base64,{b64_img}"

                db_api_key = None
                db_model_name = None
                db_base_url = None

                try:
                    from sqlalchemy import create_engine, text
                    from app.rag.config import settings
                    from app.core.security import decrypt_api_key
                    
                    sync_conn_str = settings.pg_conn_str.replace("+asyncpg", "")
                    engine = create_engine(sync_conn_str)
                    with engine.connect() as conn:
                        res = conn.execute(text("SELECT key, value FROM app_config WHERE key IN ('LLM_API_KEY', 'LLM_ACTIVE_MODEL_NAME', 'LLM_BASE_URL')")).fetchall()
                        config_map = {row[0]: row[1] for row in res if row[1]}
                        
                        if "LLM_API_KEY" in config_map:
                            try:
                                db_api_key = decrypt_api_key(config_map["LLM_API_KEY"])
                            except Exception:
                                db_api_key = config_map["LLM_API_KEY"]
                        db_model_name = config_map.get("LLM_ACTIVE_MODEL_NAME")
                        db_base_url = config_map.get("LLM_BASE_URL")
                except Exception as db_cfg_err:
                    logger.debug(f"Sync DB config fetch failed: {db_cfg_err}")

                api_key = db_api_key or os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
                if api_key and not api_key.startswith("sk-"):
                    env_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
                    if env_key and env_key.startswith("sk-"):
                        api_key = env_key

                base_url = db_base_url or os.getenv("OPENAI_BASE_URL") or getattr(settings, "openai_base_url", None)
                model_name = db_model_name or os.getenv("VISION_MODEL_NAME") or getattr(settings, "openai_model_name", None) or "gpt-5.4-mini"

                # Guard against mismatched OpenAI vs Gemini model name / base_url
                if api_key and api_key.startswith("sk-"):
                    if not model_name or "gemini" in model_name.lower() or not any(model_name.startswith(p) for p in ["gpt-", "o1", "o3", "chatgpt"]):
                        model_name = "gpt-5.4-mini"
                    if base_url and "googleapis.com" in base_url:
                        base_url = None

                if api_key:
                    logger.info(f"🔍 Running Generic Image Knowledge Extraction for '{file_name}' using model '{model_name}'...")
                    client_kwargs = {
                        "api_key": api_key,
                        "timeout": 30.0
                    }
                    if base_url:
                        client_kwargs["base_url"] = base_url

                    client = OpenAI(**client_kwargs)
                    prompt_text = (
                        "You are an expert product recognition system for PT Arya Noble (ERHA) Knowledge Base.\n\n"
                        "Your task is to identify the EXACT PRODUCT NAME shown on the product packaging or image.\n\n"
                        "## STRICT RULES (MANDATORY):\n"
                        "1. **IDENTIFY PRODUCT NAME ONLY**: Recognize and extract ONLY the official Product Name printed on the packaging (e.g., 'Exfoliating Cleansing Scrub', 'Acne Act Acne Spot Gel').\n"
                        "2. **DO NOT EXTRACT PACKAGING DETAILS**: Do NOT generate, OCR, or invent packaging text such as Brand, SKU, Net Weight, instructions, benefits, or 'Informasi Tertera pada Kemasan'. Generating packaging text is strictly forbidden to prevent false detections.\n"
                        "3. **PRESERVE RETRIEVAL CONTEXT**: Provide the clean product name and a clean 1-line Indonesian context so this image has full context and can be retrieved accurately in search and RAG answers.\n"
                        "4. **Clinical / Before-After Photos**: If this is a clinical photo of skin/face (not product packaging), identify the treatment or clinical condition (e.g., 'Acne Vulgaris - Before Treatment') and state whether it is BEFORE or AFTER.\n\n"
                        "## Output Format (Valid JSON ONLY):\n"
                        "{\n"
                        '  "title": "Exact Visible Product Name",\n'
                        '  "product_name": "Exact Visible Product Name",\n'
                        '  "image_role": "PRODUCT_PACKAGING",\n'
                        '  "caption": "Foto produk Exact Visible Product Name",\n'
                        '  "document_type": "PRODUCT",\n'
                        '  "summary_markdown": "# Exact Visible Product Name\\n\\n![Exact Visible Product Name](IMAGE_URL_PLACEHOLDER)\\n\\nDokumen visual produk resmi ERHA: Exact Visible Product Name."\n'
                        "}"
                    )

                    completion_kwargs = {
                        "model": model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_text},
                                    {"type": "image_url", "image_url": {"url": data_uri}}
                                ]
                            }
                        ],
                        "temperature": 0.0
                    }
                    try:
                        response = client.chat.completions.create(
                            **completion_kwargs,
                            max_completion_tokens=2000
                        )
                    except Exception as tok_err:
                        err_str = str(tok_err).lower()
                        if "max_completion_tokens" in err_str or "unsupported" in err_str:
                            response = client.chat.completions.create(
                                **completion_kwargs,
                                max_tokens=2000
                            )
                        else:
                            raise tok_err
                    if response.choices and len(response.choices) > 0:
                        raw_content = (response.choices[0].message.content or "").strip()
                        try:
                            clean_json = raw_content
                            if "```" in clean_json:
                                lines = clean_json.split("\n")
                                if lines[0].startswith("```"):
                                    lines = lines[1:]
                                if lines and lines[-1].startswith("```"):
                                    lines = lines[:-1]
                                clean_json = "\n".join(lines).strip()
                            data = json.loads(clean_json, strict=False)

                            img_title = data.get("title") or data.get("product_name") or os.path.splitext(file_name)[0]
                            p_name = data.get("product_name") or img_title
                            brand = data.get("brand") or "PT Arya Noble"
                            active_ing = []
                            clean_sku = None

                            # Infer or extract image role
                            img_role = data.get("image_role")
                            valid_roles = ["PRODUCT_PACKAGING", "CLINICAL_BEFORE", "CLINICAL_AFTER", "TREATMENT_PROCEDURE", "GENERAL"]
                            if not img_role or img_role not in valid_roles:
                                lower_fname = file_name.lower()
                                lower_text = (data.get("summary_markdown") or "").lower()
                                if any(k in lower_fname or k in lower_text for k in ["before", "sebelum"]):
                                    img_role = "CLINICAL_BEFORE"
                                elif any(k in lower_fname or k in lower_text for k in ["after", "sesudah", "setelah"]):
                                    img_role = "CLINICAL_AFTER"
                                elif any(k in lower_fname or k in lower_text for k in ["kemasan", "packaging", "bottle", "box", "produk"]):
                                    img_role = "PRODUCT_PACKAGING"
                                else:
                                    img_role = "PRODUCT_PACKAGING" if data.get("document_type") == "PRODUCT" else "GENERAL"

                            caption = data.get("caption") or f"Foto produk {p_name}"

                            extracted_meta.update({
                                "title": img_title,
                                "product_name": p_name,
                                "brand": brand,
                                "sku": None,
                                "active_ingredients": [],
                                "image_role": img_role,
                                "caption": caption
                            })

                            # Clean structured markdown with product name and image context only (zero packaging hallucination)
                            clean_markdown = f"# {img_title}\n\n![{img_title}]({image_url})\n\nDokumen visual resmi: {p_name}."
                            extracted_text = clean_markdown

                        except Exception as json_err:
                            logger.warning(f"Could not parse Vision LLM JSON response for '{file_name}': {json_err}. Using raw output.")
                            clean_title = os.path.splitext(file_name)[0]
                            extracted_text = f"![{clean_title}]({image_url})\n\n{raw_content}"

            except Exception as vision_err:
                logger.warning(f"Vision LLM extraction skipped/failed for '{file_name}': {vision_err}. Falling back to OCR.")

            # If Vision LLM was not available or produced empty text, fallback to Docling OCR
            if not extracted_text:
                try:
                    ocr_res = self._parse_with_docling(file_path)
                    if ocr_res and ocr_res.docling_doc:
                        ocr_md = ocr_res.docling_doc.export_to_markdown()
                        clean_title = os.path.splitext(file_name)[0]
                        extracted_text = f"![{clean_title}]({image_url})\n\n{ocr_md}"
                except Exception as ocr_err:
                    logger.warning(f"Docling OCR fallback failed for '{file_name}': {ocr_err}")

            if not extracted_text:
                clean_title = os.path.splitext(file_name)[0]
                extracted_text = f"### Image Asset: {clean_title}\n\n![{clean_title}]({image_url})\n\nStorage Key: `{s3_key}`."

            import uuid
            img_id = f"img_{uuid.uuid4().hex[:8]}"
            clean_title = os.path.splitext(file_name)[0]
            current_role = img_role if 'img_role' in locals() and img_role else ("PRODUCT_PACKAGING" if any(k in file_name.lower() for k in ["produk", "bottle", "box"]) else "GENERAL")
            current_caption = caption if 'caption' in locals() and caption else f"Foto {clean_title}"
            current_pname = p_name if 'p_name' in locals() and p_name else clean_title

            image_asset = {
                "id": img_id,
                "url": image_url,
                "s3_key": s3_key,
                "role": current_role,
                "product_name": current_pname,
                "caption": current_caption
            }

            page_data = {
                "page": 1,
                "text": extracted_text,
                "image_id": img_id,
                "image_urls": [image_url] if image_url else [],
                "image_url": image_url,
                "images": [image_asset],
                "s3_key": s3_key,
                "storage_key": s3_key,
                "image_reference": image_url,
                "clinics": ["all"],
                "doctor_types": ["all"],
                "doctors": ["all"],
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                }
            }
            page_data.update(extracted_meta)

            logger.info(f"🖼️ Standalone image '{file_name}' processed via Generic Image Knowledge Extraction (chars={len(extracted_text)}, s3_key={s3_key}, image_url={image_url})")
            return ParseResult(pages=[page_data], method="fast")
        except Exception as e:
            logger.warning(f"Standalone image processing failed for {file_path}: {e}")
            return self._parse_with_docling(file_path)

    # -------------------------------------------------------------------------
    # DOCLING OCR FALLBACK (Heavy / Scanned PDFs & Standalone Images)
    # -------------------------------------------------------------------------
    def _parse_with_docling(self, file_path: str) -> Optional[ParseResult]:
        """Full Docling OCR parse for scanned/image PDFs and standalone images."""
        import io
        from docling_core.types.io import DocumentStream

        converter = self._get_docling_converter()
        file_name = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        stream = io.BytesIO(file_bytes)
        doc_stream = DocumentStream(name=file_name, stream=stream)

        result = converter.convert(doc_stream)
        doc = result.document
        return ParseResult(docling_doc=doc, method="docling")

    # -------------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -------------------------------------------------------------------------
    def parse_file(self, file_path: str, fast_mode: bool = False) -> Optional[ParseResult]:
        """
        Smart parse: tries fast extraction first for docx, doc, pptx, ppt, txt, pdf, xlsx, xls, csv.
        Falls back to Docling OCR for scanned PDFs & image files.
        Returns a ParseResult object.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        ext = os.path.splitext(file_path)[1].lower()
        start_time = time.time()

        try:
            if ext == ".docx":
                logger.info(f"⚡ Fast DOCX extraction: {file_path}")
                result = self._parse_docx_fast(file_path)

            elif ext == ".doc":
                logger.info(f"📄 Legacy DOC extraction: {file_path}")
                result = self._parse_doc_fast(file_path)

            elif ext in [".pptx", ".ppt"]:
                logger.info(f"📊 Fast PowerPoint extraction: {file_path}")
                result = self._parse_pptx_fast(file_path)

            elif ext == ".txt":
                logger.info(f"⚡ Fast TXT extraction: {file_path}")
                result = self._parse_txt_fast(file_path)

            elif ext in [".xlsx", ".xls", ".csv"]:
                logger.info(f"📊 Fast Excel/CSV extraction: {file_path}")
                result = self._parse_excel_fast(file_path)

            elif ext == ".pdf":
                logger.info(f"⚡ Attempting fast PDF extraction: {file_path}")
                result = self._parse_pdf_fast(file_path)

                if result is None:
                    # Scanned PDF detected → Docling OCR fallback
                    logger.info(f"🔬 Docling OCR fallback for scanned PDF: {file_path}")
                    result = self._parse_with_docling(file_path)
            elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
                logger.info(f"🖼️ Standalone image extraction & MinIO upload: {file_path}")
                result = self._parse_standalone_image(file_path, fast_mode=fast_mode)
            else:
                # Unknown extension → try Docling as universal fallback
                logger.info(f"🔬 Docling universal parse for {ext}: {file_path}")
                result = self._parse_with_docling(file_path)

            elapsed = time.time() - start_time
            if result:
                method_label = "Fast" if result.is_fast else "Docling OCR"
                page_count = len(result.pages) if result.is_fast else "N/A"
                logger.info(
                    f"✅ Parsed {file_path} via {method_label} in {elapsed:.2f}s "
                    f"(pages={page_count})"
                )
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Error parsing {file_path} after {elapsed:.2f}s: {e}")
            return None
