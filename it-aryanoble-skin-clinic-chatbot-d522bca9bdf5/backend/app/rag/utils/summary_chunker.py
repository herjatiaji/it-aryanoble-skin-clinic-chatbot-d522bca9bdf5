"""
Lightweight structure-aware summary chunker.
Zero heavy dependencies — only re + loguru.
Import: from app.rag.utils.summary_chunker import chunk_summary_markdown
"""
import re
from loguru import logger


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

    if item_label and not any(k in item_label.lower() for k in ["treatment", "perawatan", "laser", "peeling", "facial", "therapy", "injeksi", "gel", "wash", "cream", "serum", "moisturizer"]):
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
            # Never strip clinical, treatment, or product images if physical asset exists
            is_clinical_or_treatment = any(k in alt_lower or k in u_lower for k in [
                "sebelum", "sesudah", "before", "after", "alat", "device", "treatment",
                "perawatan", "tindakan", "klinis", "clinical", "hasil", "spot", "wash",
                "moisturizer", "truwhite", "acneact", "serum", "s3_img", "s4_img"
            ])
            if is_clinical_or_treatment:
                fn = os.path.basename(u_lower)
                if any(k in alt_lower or k in fn for k in ["sesudah", "after", "setelah", "image3", "img_3"]):
                    img_type = "Foto Sesudah Perawatan"
                elif any(k in alt_lower or k in fn for k in ["before_after", "before-after", "sebelum_sesudah"]) or ("before" in alt_lower and "after" in alt_lower):
                    img_type = "Foto Before & After Perawatan"
                elif any(k in alt_lower or k in fn for k in ["sebelum", "before", "image2", "img_2"]):
                    img_type = "Foto Sebelum Perawatan"
                elif any(k in alt_lower or k in fn for k in ["alat", "device", "mesin", "peralatan", "image1", "img_1"]):
                    img_type = "Foto Treatment"
                elif any(k in alt_lower or k in fn for k in ["produk", "product", "wash", "spot", "moisturizer", "serum"]):
                    img_type = "Foto Produk"
                else:
                    img_type = "Foto Treatment"

                if item_label:
                    new_alt = f"{img_type} - {item_label}"
                else:
                    new_alt = img_type
                return f"![{new_alt}]({url})"

            # Strip generic document cover/header slide images ONLY if explicitly presentation cover slide
            if ("pptx_img_1_" in u_lower or "pptx_img_2_" in u_lower or "cover" in u_lower) and (alt_text == title or "cover" in alt_lower):
                return ""
            return f"![{alt_text}]({url})"
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




def _split_large_markdown_table(table_text: str, section_title: str = "", max_chars: int = 1500) -> list:
    """
    Splits a large Markdown table (> max_chars) safely by rows.
    Preserves the Table Column Headers + Delimiter + Section Title on EVERY sub-chunk
    so LLM and vector embeddings never lose column or section context.
    """
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
    table_lines = [l for l in lines if l.startswith("|")]

    # If it's not a standard markdown table or too small, return as single chunk
    if len(table_lines) < 3:
        return [table_text]

    # Extract header line and delimiter line
    header_line = table_lines[0]
    delimiter_line = table_lines[1]
    data_rows = table_lines[2:]

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

    # Split summary into sections by ## headings
    raw_sections = re.split(r'(?=\n##\s+)', summary)
    ref_sec_pattern = re.compile(
        r'^##\s*(?:REFERENCES?|DAFTAR\s+(?:PUSTAKA|REFERENSI|RUJUKAN)|BIBLIOGRAPHY|LITERATURE\s+CITED|CITED\s+LITERATURE|PUSTAKA\s+ACUAN)\b',
        re.IGNORECASE
    )
    sig_sec_pattern = re.compile(
        r'^##\s*(?:\d+[\.\)]\s*)?(?:.*persetujuan.*tanda\s*tangan|.*lembar\s+(?:persetujuan|pengesahan)|.*halaman\s+pengesahan|.*tanda\s+tangan|.*approval\s+sheet)',
        re.IGNORECASE
    )
    sections = [
        s.strip() for s in raw_sections 
        if s.strip() and len(s.strip()) >= 30 
        and not ref_sec_pattern.match(s.strip())
        and not sig_sec_pattern.match(s.strip())
    ]
    if not sections:
        sections = [summary.strip()]

    logger.debug(f"Structure-aware chunking: split summary into {len(sections)} sections by ## headings.")

    # Lightweight meta builder with clean, non-redundant schema
    def _build_meta(chunk_text, entity_name, chunk_index):
        heading_path = f"{title} > {entity_name}" if title and entity_name and title.lower() != entity_name.lower() else (entity_name or title)
        meta = {
            "source_file": source_file,
            "file_name": source_file or knowledge_id,
            "section": entity_name,
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
                if doc_type == "TREATMENT" or any(k in clean_ent.lower() for k in ["treatment", "perawatan", "laser", "peel", "facial", "therapy", "injeksi"]):
                    detected_treatment = clean_ent
                else:
                    detected_product = clean_ent

        # If still not found, check current_main_entity
        if not detected_treatment and not detected_product and current_main_entity:
            clean_main = _clean_item_name(current_main_entity)
            if clean_main and not _is_generic_name(clean_main):
                if doc_type == "TREATMENT" or any(k in clean_main.lower() for k in ["treatment", "perawatan", "laser", "peel", "facial", "therapy", "injeksi"]):
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
                    target_words = [w for w in clean_target.split() if len(w) > 2 and w not in ["erha", "acneact", "truwhite", "the", "and", "with"]]
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

    chunks = []
    chunk_idx = 0
    current_main_entity = title

    for section_text in sections:
        h2_match = re.match(r'^##\s+(?:\d+[\.\)]\s*)?(.+)', section_text)
        header_title = h2_match.group(1).strip() if h2_match else title

        clean_header = header_title.lower().strip(":-_#\t ")
        is_sub = (
            clean_header in GENERIC_SUBHEADERS or 
            len(clean_header) <= 3 or 
            any(k in clean_header for k in [
                "spesifikasi alat", "kondisi sebelum", "sebelum & sesudah", 
                "before & after", "sebelum dan sesudah", "gambar treatment", 
                "foto treatment", "parameter alat", "parameter treatment",
                "alat / mesin", "alat & mesin"
            ])
        )
        if is_sub:
            entity_name = current_main_entity or title
        else:
            entity_name = header_title
            current_main_entity = header_title

        if len(section_text) <= max_section_chars:
            chunk_idx += 1
            chunks.append({
                "text": section_text,
                "metadata": _build_meta(section_text, entity_name, chunk_idx)
            })
        else:
            # Split long sections safely (handling large tables & paragraphs)
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            running_parts = []
            running_len = 0

            for para in paragraphs:
                # If paragraph itself is a giant Markdown Table (> max_section_chars)
                if para.startswith("|") and len(para) > max_section_chars:
                    # Flush any accumulated running_parts first
                    if running_parts and running_len >= 100:
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

                    # Split giant table safely row-by-row while preserving headers
                    sub_tables = _split_large_markdown_table(
                        table_text=para,
                        section_title=entity_name,
                        max_chars=max_section_chars
                    )
                    for sub_tbl in sub_tables:
                        chunk_idx += 1
                        chunks.append({
                            "text": sub_tbl,
                            "metadata": _build_meta(sub_tbl, entity_name, chunk_idx)
                        })
                    continue

                # Normal paragraph handling
                combined_len = running_len + len(para)
                if combined_len > max_section_chars and running_parts and running_len >= 100:
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
