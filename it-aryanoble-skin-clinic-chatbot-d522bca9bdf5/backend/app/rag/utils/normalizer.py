"""
Enhanced Document Normalization & Structure Reconstruction.

Handles:
1. Fragmented word-per-line PDF extraction (rejoins words).
2. Product Name → ## Heading (product boundary for chunking).
3. Clean key-value pairs (Category, Kategori, Durasi, Downtime, Interval).
4. Subheaders (Deskripsi, Key Ingredients, Benefits, Suitable For, etc.).
5. Bullet list formatting: compact, single-newline within list, standard - dashes.
"""
import re
from loguru import logger

# Section subheaders → ### Heading
KNOWN_SECTION_LABELS = {
    # Treatment document subheaders
    "deskripsi", "cocok untuk", "tidak disarankan untuk", "manfaat",
    "persiapan sebelum treatment", "tahapan treatment", "aftercare",
    "efek samping", "kandungan peeling", "active ingredients", "ingredients",
    "peringatan", "indikasi", "kontraindikasi",
    # Product document subheaders
    "key ingredients", "benefits", "suitable for", "how to use",
    "product overview", "product information",
}

# Academic & Scientific Paper Major Headings → ## Heading
ACADEMIC_MAJOR_HEADINGS = {
    "abstract", "abstrak",
    "introduction", "pendahuluan", "background", "latar belakang",
    "method", "methods", "methodology", "metode", "metodologi",
    "materials and methods", "bahan dan metode", "experimental",
    "results and discussion", "hasil dan pembahasan", "results", "hasil",
    "discussion", "pembahasan",
    "conclusion", "conclusions", "kesimpulan", "kesimpulan dan saran",
    "recommendation", "recommendations", "saran",
    "acknowledgments", "acknowledgements", "ucapan terima kasih",
    "references", "bibliography", "daftar pustaka",
    "conflict of interest", "funding",
}

# KV labels → **Key**: Value
KNOWN_KV_LABELS = {
    "kategori", "durasi", "downtime", "jumlah sesi", "interval",
    "sku", "harga", "price",
    "category",
}

# Product Name → ## Heading (used as chunking boundary)
PRODUCT_NAME_LABELS = {"product name"}

# Build lookup sets of first words for fast rejection
_SECTION_FIRST_WORDS = {label.split()[0] for label in KNOWN_SECTION_LABELS}
_KV_FIRST_WORDS = {label.split()[0] for label in KNOWN_KV_LABELS}
_PRODUCT_FIRST_WORDS = {label.split()[0] for label in PRODUCT_NAME_LABELS}
_ALL_FIRST_WORDS = _SECTION_FIRST_WORDS | _KV_FIRST_WORDS | _PRODUCT_FIRST_WORDS


def _match_multi_word_label(lines, idx, N, label_set, first_word_set, max_words=4):
    """Check if lines[idx] starts a known multi-word label.
    Handles:
    - word-per-line: "Product" / "Name" on separate lines
    - pre-joined: "Product Name" on one line
    - label-as-prefix: "Product Name ERHA Truwhite..." on one line
    Returns (matched_label, consumed_line_count, rest_text) or (None, 0, "").
    rest_text contains any text after the label on the same line.
    """
    if idx >= N:
        return None, 0, ""
    line_lower = lines[idx].lower().rstrip(":")
    first_word = line_lower.split()[0] if line_lower else ""
    
    # Quick reject
    if first_word not in first_word_set and line_lower not in label_set:
        return None, 0, ""
    
    # Check if the full current line is exactly a label
    if line_lower in label_set:
        return lines[idx].rstrip(":"), 1, ""
    
    # Check if the line STARTS WITH a known label (label-as-prefix)
    for label in sorted(label_set, key=len, reverse=True):
        if line_lower.startswith(label + " ") or line_lower.startswith(label + ":"):
            rest = lines[idx][len(label):].lstrip(": ")
            return label, 1, rest
    
    # Try multi-word match across consecutive lines (word-per-line scenario)
    for span in range(min(max_words, N - idx), 1, -1):
        candidate = " ".join(lines[idx:idx+span]).strip()
        if candidate.lower().rstrip(":") in label_set:
            return candidate.rstrip(":"), span, ""
    return None, 0, ""


def _is_structural_boundary(lines, idx, N):
    """Check if lines[idx] starts any structural element."""
    if idx >= N or not lines[idx]:
        return True
    line = lines[idx]
    # Bullet
    if re.match(r'^[●\-*•]', line) or line in ("●", "-", "*", "•"):
        return True
    # Numbered item
    if re.match(r'^\d+[\.\\)]', line):
        return True
    # Any known label (check first word AND full line)
    line_lower = line.lower().rstrip(":")
    first_word = line_lower.split()[0] if line_lower else ""
    if first_word in _ALL_FIRST_WORDS or line_lower in (KNOWN_SECTION_LABELS | KNOWN_KV_LABELS | PRODUCT_NAME_LABELS):
        for label_set, fw_set in [
            (KNOWN_SECTION_LABELS, _SECTION_FIRST_WORDS),
            (KNOWN_KV_LABELS, _KV_FIRST_WORDS),
            (PRODUCT_NAME_LABELS, _PRODUCT_FIRST_WORDS),
        ]:
            matched, _, _ = _match_multi_word_label(lines, idx, N, label_set, fw_set)
            if matched:
                return True
    # Colon separator
    if line == ":":
        return True
    # Markdown heading
    if line.startswith("#"):
        return True
    # Academic headings & Table / Figure headers
    if re.match(r'^(?:table|tabel|figure|fig\.|gambar)\s+[ivx0-9]+', line_lower):
        return True
    stripped_num = re.sub(r'^\d+[\.\)]?\s*', '', line_lower)
    if stripped_num in ACADEMIC_MAJOR_HEADINGS:
        return True
    return False


def _consume_value_words(lines, idx, N):
    """Read text words until next structural boundary. Returns (joined_text, new_idx)."""
    parts = []
    while idx < N and lines[idx] and not _is_structural_boundary(lines, idx, N):
        parts.append(lines[idx])
        idx += 1
    return " ".join(parts).strip(), idx


def normalize_document_text(text: str) -> str:
    """Normalize fragmented PDF text into clean structured Markdown.
    
    - Joins word-per-line fragments into sentences/paragraphs
    - Product Name → ## Heading (product boundary)
    - Category, Durasi, etc. → **Key**: Value
    - Key Ingredients, Benefits, etc. → ### Subheading
    - Bullets → compact - dash list (single newline between items)
    """
    if not text or not text.strip():
        return text

    # Normalize common PDF ligatures
    text = text.replace("\ufb01", "fi")  # ﬁ → fi
    text = text.replace("\ufb02", "fl")  # ﬂ → fl
    text = text.replace("\ufb00", "ff")  # ﬀ → ff
    text = text.replace("\ufb03", "ffi") # ﬃ → ffi
    text = text.replace("\ufb04", "ffl") # ﬄ → ffl

    lines = [l.strip() for l in text.split("\n")]
    N = len(lines)

    blocks = []  # {"type": "heading"|"subheading"|"kv"|"bullet"|"para"|"table"|"image", "content": str}
    current_para = []

    def flush_para():
        nonlocal current_para
        if current_para:
            p = " ".join(current_para).strip()
            if p:
                blocks.append({"type": "para", "content": p})
            current_para = []

    i = 0
    while i < N:
        line = lines[i]

        # Empty line → flush paragraph
        if not line:
            flush_para()
            i += 1
            continue

        # Markdown tables
        if line.startswith("|"):
            flush_para()
            tbl = []
            while i < N and lines[i].startswith("|"):
                tbl.append(lines[i])
                i += 1
            blocks.append({"type": "table", "content": "\n".join(tbl)})
            continue

        # Markdown images
        if line.startswith("![") and "](" in line:
            flush_para()
            blocks.append({"type": "image", "content": line})
            i += 1
            continue

        # Existing markdown headings
        if line.startswith("#"):
            flush_para()
            blocks.append({"type": "heading", "content": line})
            i += 1
            continue

        # --- Academic Major Headings: "1. INTRODUCTION", "METHODS", "RESULTS AND DISCUSSION" ---
        line_clean = line.strip()
        line_lower_clean = line_clean.lower().rstrip(":")
        stripped_acad = re.sub(r'^\d+[\.\)]?\s*', '', line_lower_clean)
        if stripped_acad in ACADEMIC_MAJOR_HEADINGS:
            flush_para()
            heading_title = line_clean.rstrip(":")
            blocks.append({"type": "heading", "content": f"## {heading_title}"})
            i += 1
            continue

        # --- Table and Figure captions: "Table 1. ...", "Figure 1. ..." ---
        tbl_fig_match = re.match(r'^(Table|Tabel|Figure|Fig\.|Gambar)\s+([IVX0-9]+[\.\:]?.*)', line_clean, re.IGNORECASE)
        if tbl_fig_match:
            flush_para()
            prefix = tbl_fig_match.group(1).title()
            rest = tbl_fig_match.group(2).strip()
            blocks.append({"type": "subheading", "content": f"### {prefix} {rest}"})
            i += 1
            continue

        # --- Product Name → ## Heading ---
        pn_label, pn_span, pn_rest = _match_multi_word_label(lines, i, N, PRODUCT_NAME_LABELS, _PRODUCT_FIRST_WORDS)
        if pn_label:
            flush_para()
            i += pn_span
            if i < N and lines[i] == ":":
                i += 1
            # If rest_text already has the product name (label-as-prefix), use it
            if pn_rest:
                name_text = pn_rest
            else:
                name_text, i = _consume_value_words(lines, i, N)
            if name_text:
                blocks.append({"type": "heading", "content": f"## {name_text}"})
            continue

        # --- Section subheaders → ### Heading ---
        sec_label, sec_span, _ = _match_multi_word_label(lines, i, N, KNOWN_SECTION_LABELS, _SECTION_FIRST_WORDS)
        if sec_label:
            flush_para()
            i += sec_span
            if i < N and lines[i] == ":":
                i += 1
            blocks.append({"type": "subheading", "content": f"### {sec_label.title()}"})
            continue

        # --- KV labels → **Key**: Value ---
        kv_label, kv_span, kv_rest = _match_multi_word_label(lines, i, N, KNOWN_KV_LABELS, _KV_FIRST_WORDS)
        if kv_label:
            i += kv_span
            if i < N and lines[i] == ":":
                i += 1
            if kv_rest:
                val_text = kv_rest
            else:
                val_text, i = _consume_value_words(lines, i, N)
            flush_para()
            blocks.append({"type": "kv", "content": f"**{kv_label.strip().title()}**: {val_text}"})
            continue

        # --- Major numbered headings: "1. Acne Intensive Program" ---
        num_match = re.match(r'^(\d+)[\.\\)]\s*(.*)', line)
        if num_match:
            num_str = num_match.group(1)
            rest = num_match.group(2).strip()
            title_parts = [rest] if rest else []
            i += 1
            while i < N and lines[i] and not _is_structural_boundary(lines, i, N):
                title_parts.append(lines[i])
                i += 1
            full_heading = " ".join(p for p in title_parts if p).strip()
            is_citation = (
                "doi:" in full_heading.lower()
                or "et al" in full_heading.lower()
                or bool(re.search(r'\b(vol\.|no\.|pp\.|jurnal|journal)\b', full_heading, re.IGNORECASE))
                or bool(re.search(r'\b(19\d\d|20\d\d)[a-z]?[\.;:]', full_heading))
                or len(full_heading.split()) > 10
            )
            is_major = not is_citation and (
                any(kw in full_heading for kw in [
                    "Program", "Therapy", "Extraction", "Microneedling",
                    "Facial", "Center", "Treatment"
                ])
                or (len(full_heading.split()) <= 5 and full_heading.istitle()
                    and "Analysis" not in full_heading)
            )
            flush_para()
            if is_major and full_heading:
                blocks.append({"type": "heading", "content": f"## {num_str}. {full_heading}"})
            elif full_heading:
                blocks.append({"type": "para", "content": f"{num_str}. {full_heading}"})
            continue

        # --- Bullets: ●, -, *, • ---
        bullet_match = re.match(r'^[●\-*•]\s*(.*)', line)
        if bullet_match or line in ("●", "-", "*", "•"):
            flush_para()
            b_body = bullet_match.group(1).strip() if bullet_match else ""
            i += 1
            b_parts = [b_body] if b_body else []
            while i < N and lines[i] and not _is_structural_boundary(lines, i, N):
                b_parts.append(lines[i])
                i += 1
            b_text = " ".join(p for p in b_parts if p).strip()
            blocks.append({"type": "bullet", "content": f"- {b_text}"})
            continue

        # --- Normal text → accumulate into paragraph ---
        current_para.append(line)
        i += 1

    flush_para()

    # Phase 2: Render blocks into final output
    # Consecutive bullets joined with single \n (compact list)
    output_lines = []
    prev_type = None

    for block in blocks:
        btype = block["type"]
        content = block["content"]

        if btype == "bullet":
            if prev_type == "bullet":
                output_lines.append(content)
            else:
                if output_lines:
                    output_lines.append("")
                output_lines.append(content)
        elif btype in ("heading", "subheading"):
            if output_lines:
                output_lines.append("")
            output_lines.append(content)
        else:
            if output_lines:
                output_lines.append("")
            output_lines.append(content)

        prev_type = btype

    out = "\n".join(output_lines)
    out = re.sub(r'\n{3,}', '\n\n', out)
    out = re.sub(r' +', ' ', out)

    bullet_count = sum(1 for b in blocks if b["type"] == "bullet")
    heading_count = sum(1 for b in blocks if b["type"] == "heading")
    logger.debug(
        f"Document Normalization: {len(blocks)} blocks, "
        f"{heading_count} headings, {bullet_count} bullets"
    )
    return out.strip()
