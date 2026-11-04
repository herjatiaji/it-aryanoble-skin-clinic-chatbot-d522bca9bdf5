"""
Lightweight structure-aware summary chunker.
Zero heavy dependencies — only re + loguru.
Import: from app.rag.utils.summary_chunker import chunk_summary_markdown
"""
import re
from loguru import logger

from app.rag.pipeline_versions import CHUNKER_VERSION


def _clean_item_name(val: str) -> str:
    if not val:
        return ""
    v = re.sub(r'[\*\_\[\]]', '', val)
    v = re.sub(r'(?i)\b(Dummy|Documentation|Detail|Dokumentasi|Katalog|Catalog|Spesifikasi|Alat|Mesin|Peralatan|Parameter|Gambar|Foto|Tabel)\b', '', v)
    v = re.sub(r'^\s*[\d\.\)\-\:\•\*\#]+\s*', '', v)
    v = re.sub(r'[\-_/&]+', ' ', v)
    v = re.sub(r'\s+', ' ', v).strip()
    return v


def _is_generic_name(name: str) -> bool:
    if not name or len(name) <= 2:
        return True
    n_lower = name.lower()
    generic_words = [
        "general", "unknown", "cover", "cover page", "sampul", "halaman utama",
        "spesifikasi", "alat", "mesin", "peralatan", "parameter", "overview",
        "before & after", "sebelum & sesudah", "kondisi sebelum", "kondisi sesudah",
        "sebelum dan sesudah", "before after", "hasil perawatan", "tindakan",
        "faq", "pertanyaan umum", "tabel treatment", "daftar treatment", "daftar produk",
        "product overview", "deskripsi produk", "keunggulan", "cara penggunaan", "aftercare",
        "spesifikasi alat", "spesifikasi alat / mesin", "spesifikasi alat / mesin & gambar",
        "treatment", "perawatan", "gambar alat treatment", "alat treatment", "gambar alat",
        "before after perawatan", "before & after perawatan", "sebelum sesudah perawatan"
    ]
    return n_lower in generic_words or any(n_lower == gw for gw in generic_words)



def _tag_before_after_images_in_summary(text: str, title: str = "") -> str:
    """
    Enriches generic markdown image tags in Before & After report sections
    with explicit captions ('Foto Sebelum Perawatan' / 'Foto Sesudah Perawatan' or combined 'Foto Before & After Perawatan').
    Dynamically identifies the specific treatment or product name from the text instead of blindly taking title.
    """
    if not text:
        return text

    # Discover specific treatment or product name from text dynamically
    t_match = re.search(r'(?:-\s*)?\*\*(?:Jenis|Nama)\s+Treatment\*\*\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
    if not t_match:
        t_match = re.search(r'\b(?:Jenis|Nama)\s+Treatment\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
    if not t_match:
        t_match = re.search(r'\|\s*(?:Jenis Treatment|Nama Treatment|Treatment)\s*\|\s*([^\|\n]+)\s*\|', text, re.IGNORECASE)
    
    item_label = ""
    if t_match:
        c_name = _clean_item_name(t_match.group(1))
        if c_name and not _is_generic_name(c_name):
            item_label = c_name

    if not item_label:
        p_match = re.search(r'(?:-\s*)?\*\*(?:Nama\s+Produk|Produk)\*\*\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
        if not p_match:
            p_match = re.search(r'\b(?:Nama\s+Produk|Produk)\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
        if not p_match:
            p_match = re.search(r'\|\s*(?:Nama Produk|Produk)\s*\|\s*([^\|\n]+)\s*\|', text, re.IGNORECASE)
        if p_match:
            c_name = _clean_item_name(p_match.group(1))
            if c_name and not _is_generic_name(c_name):
                item_label = c_name

    if not item_label and title:
        c_name = _clean_item_name(title)
        if c_name and not _is_generic_name(c_name):
            item_label = c_name

    if item_label and not any(k in item_label.lower() for k in ["treatment", "perawatan", "laser", "peeling", "facial", "therapy", "injeksi", "gel", "wash", "cream", "serum", "moisturizer"]):
        item_label = f"{item_label} Treatment"

    lines = text.split("\n")
    new_lines = []
    state_queue = []
    in_before_after_section = False
    
    for line in lines:
        l_str = line.strip()
        l_upper = l_str.upper()

        if re.search(r'BEFORE\s*&\s*AFTER|SEBELUM\s*&\s*SESUDAH|HASIL\s*PERAWATAN', l_upper):
            in_before_after_section = True
            
        # Detect standalone Before / After markers (ignoring section titles like 'Before & After')
        if re.match(r'^(?:\*\*|#+|\-\s*\*+)?\s*(SEBELUM|BEFORE)\s*(?:\*+|\:)?$', l_upper):
            state_queue.append("BEFORE")
        elif re.match(r'^(?:\*\*|#+|\-\s*\*+)?\s*(SESUDAH|AFTER)\s*(?:\*+|\:)?$', l_upper):
            state_queue.append("AFTER")
        
        img_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', l_str)
        if img_match:
            alt, url = img_match.group(1), img_match.group(2)
            u_lower = url.lower()
            alt_lower = alt.lower()

            # Single combined image containing both Before & After (side-by-side inside 1 image file)
            is_combined = any(k in u_lower for k in ["before_after", "before-after", "sebelum_sesudah", "sebelum-sesudah"]) or "before & after" in alt_lower or "sebelum & sesudah" in alt_lower

            if is_combined:
                alt_text = f"Foto Before & After Perawatan - {item_label}" if item_label else "Foto Before & After Perawatan"
                line = f"![{alt_text}]({url})"
            elif state_queue:
                st = state_queue.pop(0)
                if st == "BEFORE":
                    alt_text = f"Foto Sebelum Perawatan - {item_label}" if item_label else "Foto Sebelum Perawatan"
                else:
                    alt_text = f"Foto Sesudah Perawatan - {item_label}" if item_label else "Foto Sesudah Perawatan"
                line = f"![{alt_text}]({url})"
            elif in_before_after_section and not any(k in alt_lower for k in ["sebelum", "sesudah", "before", "after"]):
                alt_text = f"Foto Hasil Perawatan (Before & After) - {item_label}" if item_label else "Foto Hasil Perawatan"
                line = f"![{alt_text}]({url})"

        new_lines.append(line)
    return "\n".join(new_lines)


def _clean_invalid_image_markdown(text: str, title: str = "") -> str:
    """
    Strips invalid/placeholder markdown image tags like ![Name](image_url), ![Name](), etc.
    Strips redundant cover slide images (e.g. pptx_img_1 / pptx_img_2 cover slides).
    Deduplicates contiguous image walls on adjacent lines, keeping at most 2 per block.
    Tags Before & After images with explicit captions.
    """
    import os

    # Discover specific treatment or product name from text dynamically
    t_match = re.search(r'(?:-\s*)?\*\*(?:Jenis|Nama)\s+Treatment\*\*\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
    if not t_match:
        t_match = re.search(r'\b(?:Jenis|Nama)\s+Treatment\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
    if not t_match:
        t_match = re.search(r'\|\s*(?:Jenis Treatment|Nama Treatment|Treatment)\s*\|\s*([^\|\n]+)\s*\|', text, re.IGNORECASE)
    
    item_label = ""
    is_product_label = False
    if t_match:
        c_name = _clean_item_name(t_match.group(1))
        if c_name and not _is_generic_name(c_name):
            item_label = c_name

    if not item_label:
        p_match = re.search(r'(?:-\s*)?\*\*(?:Nama\s+Produk|Produk)\*\*\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
        if not p_match:
            p_match = re.search(r'\b(?:Nama\s+Produk|Produk)\s*[:=]\s*([^\n\r\|]+)', text, re.IGNORECASE)
        if not p_match:
            p_match = re.search(r'\|\s*(?:Nama Produk|Produk)\s*\|\s*([^\|\n]+)\s*\|', text, re.IGNORECASE)
        if p_match:
            c_name = _clean_item_name(p_match.group(1))
            if c_name and not _is_generic_name(c_name):
                item_label = c_name
                is_product_label = True

    # A product name stays a product name; only a treatment name gets the "Treatment" suffix
    if item_label and not is_product_label and not any(k in item_label.lower() for k in ["treatment", "perawatan", "laser", "peeling", "facial", "therapy", "injeksi", "gel", "wash", "cream", "serum", "moisturizer"]):
        item_label = f"{item_label} Treatment"

    def _replace_img(match):
        alt_text = match.group(1).strip()
        url = match.group(2).strip()
        u_lower = url.lower()
        alt_lower = alt_text.lower()

        if not url or u_lower in ("none", "null", "undefined", "#", "url_gambar", "url"):
            return ""

        from app.services.storage import is_valid_storage_asset
        if not is_valid_storage_asset(url):
            return ""

        if url.startswith("http://") or url.startswith("https://") or url.startswith("/api/storage/") or url.startswith("/storage/"):
            from app.rag.canonical import classify_image_provenance, ImageType

            # Extract table context if within table
            tbl_context = ""
            if "|" in text:
                for line in text.splitlines():
                    if url in line and "|" in line:
                        tbl_context = line
                        break

            # The heading the image sits under is its section; the document title only when there is none
            heading_re = re.compile(r'(?m)^#{1,6}\s+(.+?)\s*#*\s*$')
            prev_heads = list(heading_re.finditer(text, 0, match.start()))
            img_section = prev_heads[-1].group(1).strip(" *") if prev_heads else title
            # The product this image shows: an explicit "Nama Produk: X" line in the image's own section
            sec_start = prev_heads[-1].end() if prev_heads else 0
            next_head = heading_re.search(text, match.end())
            sec_body = text[sec_start: next_head.start() if next_head else len(text)]
            n_match = re.search(r'\bNama\s+Produk\**\s*[:=]\s*\**\s*([^\n\r\|*]+)', sec_body, re.IGNORECASE)
            product_label = ""
            if n_match:
                n_name = _clean_item_name(n_match.group(1))
                if n_name and not _is_generic_name(n_name):
                    product_label = n_name

            prov = classify_image_provenance(
                target_url=url,
                alt_text=alt_text,
                table_context=tbl_context,
                chunk_text=text,
                section=img_section,
                meta={"product_name": product_label} if product_label else None
            )

            # Suppress document artifacts or images that should not be displayed
            if not prov.should_display():
                return ""

            if item_label and not prov.linked_product and not prov.linked_treatment:
                if prov.image_type == ImageType.PRODUCT:
                    prov.linked_product = item_label
                elif prov.image_type in (ImageType.CLINICAL_BEFORE_AFTER, ImageType.EQUIPMENT):
                    prov.linked_treatment = item_label

            new_alt = prov.format_display_label()
            if not new_alt:
                return ""
            return f"![{new_alt}]({url})"
        # Strip invalid/placeholder image tag
        return ""

    cleaned = re.sub(r'!\[([^\]]*)\]\(([^)]*)\)', _replace_img, text)

    # Collapse ONLY contiguous image blocks on adjacent lines without dotall across paragraphs
    cleaned = re.sub(
        r'(?:!\[.*?\]\([^\s\)]+\)[\t ]*\n?){3,}', 
        lambda m: '\n'.join(re.findall(r'!\[.*?\]\([^\s\)]+\)', m.group(0))[:2]), 
        cleaned
    )

    # Strip redundant images placed under Ringkasan Dokumen (images belong in Hasil Perawatan)
    cleaned = re.sub(
        r'(?mi)(##\s*Ringkasan\s*(?:Dokumen)?\b)([\s\S]*?)(?=\n##|\Z)',
        lambda m: m.group(1) + re.sub(r'!\[[^\]]*\]\([^\)]+\)\s*\n*', '', m.group(2)),
        cleaned
    )

    # Clean up double blank lines caused by removed tags
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    # Tag Before & After images with explicit captions
    cleaned = _tag_before_after_images_in_summary(cleaned, title=title)
    return cleaned.strip()




# Catalog item markers produced by the summary format ('### Detail Produk' + '- **Nama Produk**: X')
ITEM_BLOCK_HEADING_RE = re.compile(r'^#{3,4}\s+(?:Detail\s+(?:Produk|Tindakan|Treatment)|Product\s+Details?|Treatment\s+Details?)\s*$', re.IGNORECASE)
ITEM_NAME_FIELD_RE = re.compile(r'\*\*(?:Nama\s+Produk|Nama\s+Tindakan|Nama\s+Treatment|Product\s+Name|Treatment\s+Name)\*\*\s*:\s*([^\n]+)', re.IGNORECASE)


def _split_large_markdown_table(table_text: str, section_title: str = "", max_chars: int = 1500) -> list:
    """
    Splits a large Markdown table (> max_chars) safely by rows.
    Preserves the Table Column Headers + Delimiter + Section Title on EVERY sub-chunk
    so LLM and vector embeddings never lose column or section context.
    """
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
    table_lines = [l for l in lines if l.startswith("|")]

    # If it's not a standard markdown table or too small, return as single chunk
    if len(table_lines) < 2:
        return [table_text]

    header_line = table_lines[0]
    if not header_line.endswith("|"):
        header_line = header_line + " |"

    if len(table_lines) > 1 and re.match(r'^\|(?:\s*:?-{3,}:?\s*\|)+$', table_lines[1]):
        delimiter_line = table_lines[1]
        data_rows = table_lines[2:]
    else:
        col_count = max(len(header_line.split('|')) - 2, 2)
        delimiter_line = "| " + " | ".join(["---"] * col_count) + " |"
        data_rows = table_lines[1:]

    # Header block string to prepend
    table_header_prefix = f"{header_line}\n{delimiter_line}"

    sub_chunks = []
    current_rows = []
    current_len = len(table_header_prefix)

    for row in data_rows:
        if current_len + len(row) + 1 > max_chars and current_rows:
            # Reconstruct table sub-chunk
            rows_str = "\n".join(current_rows)
            full_sub_table = f"{table_header_prefix}\n{rows_str}"
            if section_title:
                full_sub_table = f"## {section_title}\n\n{full_sub_table}"
            sub_chunks.append(full_sub_table)

            current_rows = []
            current_len = len(table_header_prefix)

        current_rows.append(row)
        current_len += len(row) + 1

    if current_rows:
        rows_str = "\n".join(current_rows)
        full_sub_table = f"{table_header_prefix}\n{rows_str}"
        if section_title:
            full_sub_table = f"## {section_title}\n\n{full_sub_table}"
        sub_chunks.append(full_sub_table)

    return sub_chunks


def common_words(names: list, min_share: float = 0.5, min_names: int = 3) -> set:
    """Words that occur in at least `min_share` of the given names (e.g. a shared brand): not distinctive."""
    if len(names) < min_names:
        return set()
    counts = {}
    for name in names:
        for w in set(re.findall(r"[a-z0-9]+", (name or "").lower())):
            counts[w] = counts.get(w, 0) + 1
    return {w for w, n in counts.items() if n / len(names) >= min_share}


# Words naming a product's form: in an item name they mark a product, whatever treatment word is also there
PRODUCT_FORM_WORDS = ["cleanser", "wash", "serum", "toner", "cream", "creme", "krim", "gel", "lotion", "sunscreen",
                      "moisturizer", "mask", "masker", "essence", "ampoule", "shampoo", "sabun", "soap", "spray", "mist",
                      "balm", "oil", "pad", "booster", "foam", "scrub"]


# Rows per table chunk: small enough that one row's facts (a size, a price, a duration) are found by search
TABLE_ROWS_PER_CHUNK = 10
# A first page with fewer words than this under its opening H1 is a cover: that H1 titles the document
COVER_PAGE_MAX_WORDS = 60


def parse_markdown_blocks(markdown: str) -> list:
    """
    Markdown as a list of blocks: {"kind": "heading" | "text" | "table", "level", "text", "page"}.
    A thematic break ('---') starts a new page; blank lines separate text blocks.
    """
    blocks = []
    page = 0
    para = []

    def _flush_para():
        if para:
            txt = "\n".join(para).strip()
            if txt:
                blocks.append({"kind": "text", "level": 0, "text": txt, "page": page})
            para.clear()

    lines = (markdown or "").split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if re.fullmatch(r"(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,}", stripped):
            _flush_para()
            page += 1
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            _flush_para()
            blocks.append({"kind": "heading", "level": len(heading.group(1)), "text": heading.group(2).strip(), "page": page})
            i += 1
            continue
        if stripped.startswith("|"):
            _flush_para()
            table = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i].strip())
                i += 1
            blocks.append({"kind": "table", "level": 0, "text": "\n".join(table), "page": page})
            continue
        if not stripped:
            _flush_para()
        else:
            para.append(raw.rstrip())
        i += 1
    _flush_para()
    return blocks


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
    default_image_url: str = None,
) -> list:
    """
    Structure-aware chunking of AI-reviewed Markdown summary.
    Splits by ## headings, extracts contextual image_url/sku/price per chunk.
    No embedding model required — instant execution.
    """
    if not summary or not summary.strip():
        return []

    # Clean invalid/placeholder image tags (e.g. ![Name](image_url)) before chunking
    summary = _clean_invalid_image_markdown(summary, title=title)
    if not summary or not summary.strip():
        return []

    # Apply Document Normalization / Structure Reconstruction to fix line-break fragmentation
    from app.rag.utils.normalizer import normalize_document_text
    summary = normalize_document_text(summary)
    if not summary or not summary.strip():
        return []

    # Ensure markdown tables are fully sanitized before chunking
    from app.rag.services.rag_generator import repair_markdown_tables
    summary = repair_markdown_tables(summary)
    if not summary or not summary.strip():
        return []

    # Discover document-level images and classify their roles
    all_doc_imgs_with_alt = re.findall(r'!\[(.*?)\]\(([^\s\)]+)\)', summary)
    all_doc_imgs = [u for _, u in all_doc_imgs_with_alt]

    treatment_img = None
    before_img = None
    after_img = None
    combined_ba_img = None

    for alt, u in all_doc_imgs_with_alt:
        alt_l = alt.lower()
        u_l = u.lower()
        if any(k in alt_l or k in u_l for k in ["before_after", "before-after", "sebelum_sesudah", "sebelum-sesudah", "before & after", "sebelum & sesudah"]):
            if not combined_ba_img:
                combined_ba_img = u
        elif any(k in alt_l or k in u_l for k in ["sebelum", "before", "_bef_"]):
            if not before_img:
                before_img = u
        elif any(k in alt_l or k in u_l for k in ["sesudah", "after", "_aft_"]):
            if not after_img:
                after_img = u
        elif any(k in alt_l or k in u_l for k in ["alat", "device", "treatment", "peralatan", "mesin"]):
            if not treatment_img:
                treatment_img = u

    # If ordered triplet (device/treatment, before, after) exists without explicit keywords:
    if len(all_doc_imgs) >= 3 and not (before_img and after_img):
        if not treatment_img:
            treatment_img = all_doc_imgs[0]
        if not before_img:
            before_img = all_doc_imgs[1]
        if not after_img:
            after_img = all_doc_imgs[2]

    if not default_image_url:
        default_image_url = treatment_img or (all_doc_imgs[0] if all_doc_imgs else None)

    # Words on most of this document's image labels (its brand, its product line) do not tell items apart
    common_label_words = common_words([alt for alt, _ in all_doc_imgs_with_alt])

    # Discover document-level related products / treatments for knowledge interconnection
    doc_related_products = []
    rel_prod_match = re.search(r'(?:Related Products|Produk Terkait|Produk Pendukung|Kombinasi Produk)\s*[:\n](.+?)(?=\n##|\Z)', summary, re.IGNORECASE | re.DOTALL)
    if rel_prod_match:
        raw_items = rel_prod_match.group(1).split("\n")
        for item in raw_items:
            sub_items = re.split(r'[•\*\-\|]', item)
            for sub in sub_items:
                clean_sub = sub.strip()
                if clean_sub and len(clean_sub) > 3 and clean_sub.lower() not in ["none", "null", "-", "n/a", "related products", "produk terkait"]:
                    if clean_sub not in doc_related_products:
                        doc_related_products.append(clean_sub)

    doc_related_treatments = []
    rel_treat_match = re.search(r'(?:Related Treatments|Treatment Terkait|Tindakan Terkait|Kombinasi Treatment)\s*[:\n](.+?)(?=\n##|\Z)', summary, re.IGNORECASE | re.DOTALL)
    if rel_treat_match:
        raw_items = rel_treat_match.group(1).split("\n")
        for item in raw_items:
            sub_items = re.split(r'[•\*\-\|]', item)
            for sub in sub_items:
                clean_sub = sub.strip()
                if clean_sub and len(clean_sub) > 3 and clean_sub.lower() not in ["none", "null", "-", "n/a", "related treatments", "treatment terkait"]:
                    if clean_sub not in doc_related_treatments:
                        doc_related_treatments.append(clean_sub)

    # Standardized clinical indications taxonomy for automatic medical cross-referencing
    clinical_taxonomy = {
        "acne_vulgaris": ["acne vulgaris", "jerawat", "papul", "pustul", "comedonal acne", "acne-prone", "jerawat aktif", "radang jerawat"],
        "comedones": ["komedo", "blackhead", "whitehead", "closed comedones", "open comedones", "penyumbatan pori"],
        "acne_scar": ["acne scar", "bekas jerawat", "boxcar scar", "rolling scar", "atrophic scar", "bopeng", "scar treatment"],
        "sebum_oily": ["kulit berminyak", "oily skin", "produksi minyak", "sebum control", "sebum"],
        "enlarged_pores": ["pori besar", "pori-pori", "enlarged pores", "tampilan pori"],
        "hyperpigmentation": ["hiperpigmentasi", "dark spots", "noda hitam", "flek hitam", "melasma", "pih", "post inflammatory hyperpigmentation"],
        "dull_skin": ["kulit kusam", "mencerahkan", "brightening", "glowing", "warna kulit tidak merata", "uneven skin tone", "skin radiance"],
        "aging_wrinkles": ["aging", "penuaan", "kerutan", "garis halus", "wrinkle", "fine lines", "kulit kendur", "anti-aging"],
        "sensitive_barrier": ["kulit sensitif", "skin barrier", "kemerahan", "iritasi", "inflamasi", "soothing", "calming"]
    }

    doc_summary_lower = summary.lower()
    doc_indications = [k for k, kws in clinical_taxonomy.items() if any(kw in doc_summary_lower for kw in kws)]

    categories = categories or []
    visibility_settings = visibility_settings or {
        "clinics": ["all"], "doctor_types": ["all"], "doctors": ["all"]
    }

    ref_sec_pattern = re.compile(
        r'^##\s*(?:REFERENCES?|DAFTAR\s+(?:PUSTAKA|REFERENSI|RUJUKAN)|BIBLIOGRAPHY|LITERATURE\s+CITED|CITED\s+LITERATURE|PUSTAKA\s+ACUAN)\b',
        re.IGNORECASE
    )
    sig_sec_pattern = re.compile(
        r'^##\s*(?:\d+[\.\)]\s*)?(?:.*persetujuan.*tanda\s*tangan|.*lembar\s+(?:persetujuan|pengesahan)|.*halaman\s+pengesahan|.*tanda\s+tangan|.*approval\s+sheet)',
        re.IGNORECASE
    )

    # The summary as blocks (headings, text, tables, page breaks): chunks are built from content blocks,
    # each carrying the headings above it, so a heading never becomes a chunk of its own.
    blocks = parse_markdown_blocks(summary)
    sections = [b for b in blocks if b["kind"] == "heading"] or [summary]
    logger.debug(f"Structure-aware chunking: {len(blocks)} blocks, {len(sections)} headings.")

    # The summary's opening H1 names the document's subject ('VOLNEWMER Training Book'). When it differs
    # from the stored title, later pages would otherwise never mention the subject, so every chunk
    # carries it as the root of its section path.
    # The opening H1 names the whole document when it is the only H1 (repeats of the same text count once),
    # or when it is a cover title: the document's first block, on a first page with little else on it. When
    # every page opens with its own H1 (a catalog), the first one is just the first page's subject.
    h1_texts = {b["text"].strip().lower() for b in blocks if b["kind"] == "heading" and b["level"] == 1}
    first_block = blocks[0] if blocks else None
    first_page_words = sum(
        len(re.findall(r"\w+", b["text"])) for b in blocks
        if first_block and b["page"] == first_block["page"] and b["kind"] != "heading"
    )
    opens_with_h1 = bool(first_block) and first_block["kind"] == "heading" and first_block["level"] == 1
    is_cover = opens_with_h1 and first_page_words < COVER_PAGE_MAX_WORDS
    doc_heading = first_block["text"] if opens_with_h1 and (len(h1_texts) == 1 or is_cover) else None
    if doc_heading and doc_heading.lower() in (title or "").lower():
        doc_heading = None

    def _entity_kind(name: str) -> str:
        """Treatment or product: the document's type decides; in a mixed document, a product-form word in the
        name ('Facial Cleanser', 'Peeling Gel') makes it a product before any treatment word does."""
        if doc_type == "TREATMENT":
            return "treatment"
        if doc_type == "PRODUCT":
            return "product"
        name_l = (name or "").lower()
        if re.search(r"\b(?:" + "|".join(PRODUCT_FORM_WORDS) + r")\b", name_l):
            return "product"
        if any(k in name_l for k in ["treatment", "perawatan", "laser", "peel", "facial", "therapy", "injeksi"]):
            return "treatment"
        return "product"

    # Lightweight meta builder with clean, non-redundant schema
    def _build_meta(chunk_text, entity_name, chunk_index, section_label=None):
        heading_path = f"{title} > {entity_name}" if title and entity_name and title.lower() != entity_name.lower() else (entity_name or title)
        section = section_label or entity_name
        if doc_heading and doc_heading.lower() not in (section or "").lower():
            section = f"{doc_heading} / {section}" if section else doc_heading
            heading_path = " > ".join(dict.fromkeys(p for p in (title, doc_heading, entity_name) if p))
        meta = {
            "source_file": source_file,
            "file_name": source_file or knowledge_id,
            "section": section,
            "heading_path": heading_path,
            "page": 1,
            "chunk_index": chunk_index,
            "knowledge_id": knowledge_id,
            "batch_id": batch_id,
            "file_hash": file_hash,
            "title": title,
            "document_type": doc_type,
            "related_products": doc_related_products,
            "related_treatments": doc_related_treatments,
            "clinics": visibility_settings.get("clinics", ["all"]),
            "doctor_types": visibility_settings.get("doctor_types", ["all"]),
            "doctors": visibility_settings.get("doctors", ["all"]),
            "chunker_version": CHUNKER_VERSION,
        }

        chunk_txt_lower = (chunk_text or "").lower()
        chunk_inds = [k for k, kws in clinical_taxonomy.items() if any(kw in chunk_txt_lower for kw in kws)]
        meta["indications"] = list(dict.fromkeys(doc_indications + chunk_inds))

        # Dynamically discover specific treatment or product name for this chunk
        detected_treatment = None
        detected_product = None

        if chunk_text:
            t_match = re.search(r'(?:-\s*)?\*\*(?:Jenis|Nama)\s+Treatment\*\*\s*[:=]\s*([^\n\r\|]+)', chunk_text, re.IGNORECASE)
            if not t_match:
                t_match = re.search(r'\b(?:Jenis|Nama)\s+Treatment\s*[:=]\s*([^\n\r\|]+)', chunk_text, re.IGNORECASE)
            if not t_match:
                t_match = re.search(r'\|\s*(?:Jenis Treatment|Nama Treatment|Treatment)\s*\|\s*([^\|\n]+)\s*\|', chunk_text, re.IGNORECASE)
            if t_match:
                candidate_t = _clean_item_name(t_match.group(1))
                if candidate_t and not _is_generic_name(candidate_t):
                    detected_treatment = candidate_t

            p_match = re.search(r'(?:-\s*)?\*\*(?:Nama\s+Produk|Produk)\*\*\s*[:=]\s*([^\n\r\|]+)', chunk_text, re.IGNORECASE)
            if not p_match:
                p_match = re.search(r'\b(?:Nama\s+Produk|Produk)\s*[:=]\s*([^\n\r\|]+)', chunk_text, re.IGNORECASE)
            if not p_match:
                p_match = re.search(r'\|\s*(?:Nama Produk|Produk)\s*\|\s*([^\|\n]+)\s*\|', chunk_text, re.IGNORECASE)
            if p_match:
                candidate_p = _clean_item_name(p_match.group(1))
                if candidate_p and not _is_generic_name(candidate_p):
                    detected_product = candidate_p

        # If not found in text, check entity_name (current section header) if non-generic
        if not detected_treatment and not detected_product:
            clean_ent = _clean_item_name(entity_name)
            if clean_ent and not _is_generic_name(clean_ent):
                if _entity_kind(clean_ent) == "treatment":
                    detected_treatment = clean_ent
                else:
                    detected_product = clean_ent

        # If still not found, check current_main_entity
        if not detected_treatment and not detected_product and current_main_entity:
            clean_main = _clean_item_name(current_main_entity)
            if clean_main and not _is_generic_name(clean_main):
                if _entity_kind(clean_main) == "treatment":
                    detected_treatment = clean_main
                else:
                    detected_product = clean_main

        # Format and save to metadata
        if detected_treatment:
            if not any(k in detected_treatment.lower() for k in ["treatment", "perawatan", "laser", "peeling", "facial", "therapy", "injeksi"]):
                detected_treatment = f"{detected_treatment} Treatment"
            meta["treatment_name"] = detected_treatment
        elif doc_type == "TREATMENT":
            clean_t = _clean_item_name(title)
            if clean_t and not _is_generic_name(clean_t):
                if not any(k in clean_t.lower() for k in ["treatment", "perawatan"]):
                    clean_t = f"{clean_t} Treatment"
                meta["treatment_name"] = clean_t

        if detected_product:
            meta["product_name"] = detected_product
        elif doc_type != "TREATMENT":
            clean_p = _clean_item_name(title)
            if clean_p and not _is_generic_name(clean_p):
                meta["product_name"] = clean_p
        if chunk_text:
            chunk_txt_l = chunk_text.lower()
            entity_l = (entity_name or "").lower()

            is_before_topic = any(k in chunk_txt_l or k in entity_l for k in [
                "kondisi before", "sebelum perawatan", "sebelum treatment", "sebelum tindakan",
                "keluhan", "jerawat aktif", "kondisi kulit sebelum", "sebelum:"
            ])
            is_after_topic = any(k in chunk_txt_l or k in entity_l for k in [
                "kondisi after", "sesudah perawatan", "setelah perawatan", "sesudah treatment",
                "setelah treatment", "hasil treatment", "evaluasi", "sesudah:"
            ])
            is_treatment_device_topic = any(k in chunk_txt_l or k in entity_l for k in [
                "alat", "device", "parameter", "energy", "frequency", "durasi treatment", "prosedur"
            ])

            # 1. Extract inline image markdown tags in this chunk
            img_matches = re.findall(r'!\[.*?\]\(([^\s\)]+)\)', chunk_text)
            if img_matches:
                if is_before_topic and before_img and before_img in img_matches:
                    meta["image_url"] = before_img
                    meta["role"] = "CLINICAL_BEFORE"
                elif is_after_topic and after_img and after_img in img_matches:
                    meta["image_url"] = after_img
                    meta["role"] = "CLINICAL_AFTER"
                else:
                    meta["image_url"] = img_matches[0]
                meta["image_urls"] = [meta["image_url"]]
            else:
                # 2. Strict 1-to-1 Product Image Matching
                product_img_match = None
                target_entity = detected_product or detected_treatment
                if target_entity and all_doc_imgs_with_alt:
                    clean_target = re.sub(r'[^a-zA-Z0-9\s]', '', target_entity.lower()).strip()
                    target_words = [w for w in clean_target.split() if len(w) > 2 and w not in common_label_words
                                    and w not in ["the", "and", "with", "for", "produk", "product", "series", "range"]]
                    for alt, u in all_doc_imgs_with_alt:
                        alt_l = alt.lower()
                        u_l = u.lower()
                        if clean_target in alt_l or (target_words and sum(1 for w in target_words if w in alt_l or w in u_l) >= max(1, len(target_words) - 1)):
                            product_img_match = u
                            break

                if product_img_match:
                    meta["image_url"] = product_img_match
                    meta["image_urls"] = [product_img_match]
                elif is_before_topic and before_img:
                    meta["image_url"] = before_img
                    meta["role"] = "CLINICAL_BEFORE"
                elif is_after_topic and after_img:
                    meta["image_url"] = after_img
                    meta["role"] = "CLINICAL_AFTER"
                elif is_before_topic and combined_ba_img:
                    meta["image_url"] = combined_ba_img
                    meta["role"] = "CLINICAL_BEFORE"
                elif is_after_topic and combined_ba_img:
                    meta["image_url"] = combined_ba_img
                    meta["role"] = "CLINICAL_AFTER"
                elif is_treatment_device_topic and treatment_img:
                    meta["image_url"] = treatment_img
                    meta["role"] = "DEVICE_OR_TOOL"
                elif doc_type == "TREATMENT" and (before_img or after_img) and ("before" in entity_l or "after" in entity_l):
                    meta["image_url"] = before_img or after_img
                    meta["role"] = "CLINICAL_BEFORE" if before_img else "CLINICAL_AFTER"
                elif default_image_url and doc_type != "PRODUCT" and len(sections) == 1:
                    meta["image_url"] = default_image_url

            # Extract SKU
            sku_match = re.search(
                r'(?:-\s*\*\*SKU\*\*|\bSKU\b)\s*[:=]\s*([A-Za-z0-9\-\_]+)',
                chunk_text, re.IGNORECASE
            )
            if sku_match:
                meta["sku"] = sku_match.group(1).strip()

            # Extract price (clean numeric string stopping at comma/semicolon/newline)
            price_match = re.search(
                r'(?:-\s*\*\*(?:Harga|Price|Harga Normal|Harga Promo)\*\*|\b(?:Harga|Price)\b)\s*[:=]\s*([^\n\r,;]+)',
                chunk_text, re.IGNORECASE
            )
            if price_match:
                meta["price"] = price_match.group(1).strip()

            # Extract promo dates from chunk text itself (always used if found)
            date_matches = re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b', chunk_text)
            if len(date_matches) >= 2:
                meta["valid_from"] = date_matches[0]
                meta["valid_until"] = date_matches[1]
            elif len(date_matches) == 1:
                meta["valid_until"] = date_matches[0]
            else:
                # Doc-level promo dates are ONLY inherited by chunks that mention promo content
                # Non-promo chunks (regular product info) must NOT get promo dates
                _PROMO_KEYWORDS = {
                    "promo", "diskon", "discount", "flash sale", "voucher", "cashback",
                    "special price", "harga promo", "berlaku", "valid until", "periode",
                    "penawaran", "potongan harga", "buy 1 get", "gratis", "free gift",
                }
                is_promo_chunk = any(kw in chunk_text.lower() for kw in _PROMO_KEYWORDS)
                if is_promo_chunk:
                    if valid_from:
                        meta["valid_from"] = valid_from
                    if valid_until:
                        meta["valid_until"] = valid_until

        if categories:
            str_cats = [c["name"] if isinstance(c, dict) else str(c) for c in categories if c]
            if str_cats:
                meta["category"] = str_cats[0]
                meta["categories"] = str_cats
        return meta

    GENERIC_SUBHEADERS = {
        "warnings", "warning", "warnings & storage", "warnings and storage", "overview", "product overview", 
        "deskripsi & fungsi produk", "deskripsi produk", "fungsi produk", "active ingredients", "ingredients", 
        "bahan aktif", "kandungan & bahan aktif", "kandungan", "komposisi", "how to use", "cara penggunaan", 
        "cara pakai", "benefits", "benefit", "manfaat", "manfaat produk", "manfaat & penggunaan",
        "manfaat dan penggunaan", "manfaat & hasil yang diharapkan", "penggunaan", "keunggulan", "keunggulan produk", 
        "side effects", "efek samping", "setelah tindakan", "perawatan setelah tindakan", "aftercare", "pre-care", 
        "persiapan sebelum tindakan", "indikasi & target kondisi kulit", "indikasi", "kontraindikasi", 
        "informasi & parameter prosedur", "source mapping", "catatan", "informasi tambahan", "references", "referensi",
        "lampiran", "appendix", "faq", "pertanyaan umum", "syarat & ketentuan", "terms & conditions",
        "spesifikasi alat", "spesifikasi alat / mesin", "spesifikasi alat / mesin & gambar", "spesifikasi alat/mesin",
        "alat & mesin", "alat / mesin", "parameter alat", "parameter treatment", "kondisi sebelum & sesudah",
        "kondisi sebelum & sesudah perawatan", "sebelum & sesudah perawatan", "before & after", "sebelum dan sesudah",
        "foto klinis", "gambar treatment", "dokumentasi klinis", "tabel before after", "before and after",
        "tabel treatment", "spesifikasi & parameter", "informasi treatment", "detail treatment", "gambar & foto"
    }

    def _is_subheader(heading: str) -> bool:
        clean_header = heading.lower().strip(":-_#\t ")
        return (
            clean_header in GENERIC_SUBHEADERS or
            len(clean_header) <= 3 or
            any(k in clean_header for k in [
                "spesifikasi alat", "kondisi sebelum", "sebelum & sesudah",
                "before & after", "sebelum dan sesudah", "gambar treatment",
                "foto treatment", "parameter alat", "parameter treatment",
                "alat / mesin", "alat & mesin"
            ])
        )

    chunks = []
    chunk_idx = 0
    current_main_entity = title
    seen_texts = set()
    stack = []          # headings above the current block: [(level, text)]
    body = []           # content blocks of the chunk being built
    body_len = 0
    current_item = None
    skipping = None     # level of a references/signature heading whose section is left out
    last_page = None

    def _names():
        return [t for _, t in stack if t.strip().lower() != (title or "").strip().lower()]

    def _entity_and_label():
        nonlocal current_main_entity
        names = _names()
        if not names:
            return current_main_entity or title, None
        top = names[0]
        if _is_subheader(top):
            entity = current_main_entity or title
        else:
            entity = top
            current_main_entity = top
        label = " / ".join(names) if len(names) > 1 else None
        return entity, label

    def _emit(parts):
        nonlocal chunk_idx
        content = "\n\n".join(p for p in parts if p).strip()
        if len(re.sub(r"[#*|\-\s]", "", content)) < 3:
            return
        head = "\n".join(f"{'#' * lvl} {txt}" for lvl, txt in stack)
        text = f"{head}\n\n{content}" if head else content
        key = re.sub(r"\s+", " ", text.lower())
        if key in seen_texts:
            return
        seen_texts.add(key)
        entity, label = _entity_and_label()
        if current_item:
            label = f"{label or entity} / {current_item}"
        chunk_idx += 1
        chunks.append({"text": text, "metadata": _build_meta(text, entity, chunk_idx, label)})

    def _flush():
        nonlocal body, body_len
        if body:
            _emit(body)
        body, body_len = [], 0

    for block in blocks:
        if block["page"] != last_page:
            # A page starts its own subject (each catalog page names its product)
            _flush()
            stack, current_item, skipping, last_page = [], None, None, block["page"]

        if block["kind"] == "heading":
            _flush()
            lvl, txt = block["level"], block["text"]
            if skipping is not None and lvl > skipping:
                continue
            skipping = None
            if ref_sec_pattern.match(f"## {txt}") or sig_sec_pattern.match(f"## {txt}"):
                skipping = lvl
                continue
            stack = [(l, t) for l, t in stack if l < lvl] + [(lvl, txt)]
            if ITEM_BLOCK_HEADING_RE.match(f"{'#' * lvl} {txt}"):
                current_item = None
            continue

        if skipping is not None:
            continue

        text = block["text"]
        if block["kind"] == "table":
            rows = [l for l in text.split("\n") if l.strip()]
            has_delim = len(rows) > 1 and re.match(r'^\|(?:\s*:?-{3,}:?\s*\|)+\s*$', rows[1])
            header = rows[:2] if has_delim else rows[:1]
            data = rows[len(header):]
            if body_len + len(text) <= max_section_chars and len(data) <= TABLE_ROWS_PER_CHUNK:
                body.append(text)
                body_len += len(text)
                continue
            # A long table is split by rows, every part keeping the column header; a short lead-in
            # paragraph stays with the first part.
            lead = body if body_len < 300 else []
            if not lead:
                _flush()
            group, group_len = [], 0
            header_len = sum(len(h) for h in header)
            for row in data:
                if group and (len(group) >= TABLE_ROWS_PER_CHUNK or header_len + group_len + len(row) > max_section_chars):
                    _emit(lead + ["\n".join(header + group)])
                    lead, group, group_len = [], [], 0
                group.append(row)
                group_len += len(row)
            if group:
                _emit(lead + ["\n".join(header + group)])
            body, body_len = [], 0
            continue

        # Catalog item boundary: a new item name closes the previous item's chunk
        name_match = ITEM_NAME_FIELD_RE.search(text)
        if name_match:
            new_item = name_match.group(1).strip().strip("*").strip()
            if body and new_item != current_item:
                _flush()
            current_item = new_item

        if body and body_len + len(text) > max_section_chars and body_len >= 100:
            _flush()
        body.append(text)
        body_len += len(text)

    _flush()

    # Integrity Check / Safety Guard: ensure chunking preserved text content (>50% ratio)
    total_chunk_len = sum(len(c.get("text", "")) for c in chunks)
    if summary and len(summary) > 300 and total_chunk_len < (len(summary) * 0.5):
        logger.warning(
            f"⚠️ Summary chunking integrity alert! "
            f"Summary len={len(summary)}, total chunk text len={total_chunk_len}. "
            f"Falling back to single full summary chunk to prevent data loss."
        )
        return [{
            "text": summary,
            "metadata": _build_meta(summary, title, 1)
        }]

    logger.debug(f"Structure-aware chunking complete: {len(chunks)} chunks from {len(sections)} sections.")
    return chunks
