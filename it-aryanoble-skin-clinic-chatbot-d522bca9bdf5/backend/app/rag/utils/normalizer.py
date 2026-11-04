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
    # Indonesian clinical & product subheaders
    "bahan aktif", "kandungan aktif", "komposisi",
    "cara pakai", "cara penggunaan", "aturan pakai", "aturan penggunaan", "petunjuk penggunaan", "petunjuk pemakaian", "tata cara pakai",
    "informasi lain - lain", "informasi lain-lain", "informasi lain", "informasi produk", "informasi tambahan",
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
    "bagan alur", "bagan alur diagnosis", "alur diagnosis", "algoritma", "algoritma diagnosis",
    "daftar singkatan", "singkatan",
}

# KV labels → **Key**: Value
KNOWN_KV_LABELS = {
    "kategori", "durasi", "downtime", "jumlah sesi", "interval",
    "sku", "harga", "price",
    "category",
    "ukuran & harga", "ukuran / harga", "ukuran", "netto", "kemasan",
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
    # Numbered or lettered item (e.g. "1. " or "a. ")
    if re.match(r'^(?:\d+|[a-zA-Z])[\.\\)]\s', line):
        return True
    # Price & size line (e.g. "90 ml - Rp. 70.000", "Rp. 70.000")
    if re.match(r'^(?:\d+\s*(?:ml|gr|gram|g|l|liter|pcs|kapsul|tablet|sachet)?\s*[-–/]\s*Rp\.?\s*[\d\.\,]+|Rp\.?\s*[\d\.\,]+)$', line, re.IGNORECASE):
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


def _numbered_title_like(text: str) -> bool:
    """A numbered line that names a program / treatment, or is a short Title Case phrase."""
    return (
        any(kw in text for kw in ["Program", "Therapy", "Extraction", "Microneedling", "Facial", "Center", "Treatment"])
        or (len(text.split()) <= 5 and text.istitle() and "Analysis" not in text)
    )


def _demote_mixed_numbered_runs(text: str) -> str:
    """
    A run of consecutively numbered items (1., 2., 3., ...) is one list or one set of numbered sections, never
    both: when some items of a run are plain list items, the items of that run promoted to '## N. Title' (judged
    page by page, without seeing their siblings across a page break) become list items again.
    """
    lines = text.split("\n")
    item_re = re.compile(r'^(#{1,6}\s+)?(\d{1,3})[\.\)]\s+\S')
    runs, cur, last = [], [], None
    for idx, line in enumerate(lines):
        m = item_re.match(line)
        if not m:
            if line.startswith("#"):
                # Another heading ('### Cara Pakai') closes the run: steps inside a numbered section are not
                # siblings of the section titles
                if cur:
                    runs.append(cur)
                cur, last = [], None
            continue
        n = int(m.group(2))
        if last is not None and n == last + 1:
            cur.append((idx, bool(m.group(1))))
        else:
            if cur:
                runs.append(cur)
            cur = [(idx, bool(m.group(1)))]
        last = n
    if cur:
        runs.append(cur)
    for run in runs:
        if any(h for _, h in run) and any(not h for _, h in run):
            for idx, is_head in run:
                if is_head:
                    lines[idx] = re.sub(r'^#{1,6}\s+', '', lines[idx])
    return "\n".join(lines)


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
    last_numbered = None  # (number, promoted_to_heading) of the latest numbered item

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

        # --- Generic Key-Value Pairs: "Label : Value" or "Label: Value" across clinical, operational, administrative domains ---
        generic_kv_match = re.match(r'^([A-Za-z0-9\s\(\)\/\.\-]{2,35})\s*:\s*(.+)$', line_clean)
        # A numbered item ('4. Sibbald C. Alopecia Areata: An updated review') is a list item, not a label.
        if (generic_kv_match and not line_clean.startswith("http") and not line_clean.startswith("#") and not line_clean.startswith("!")
                and not re.match(r'^\d{1,3}[\.\)]\s', line_clean)):
            k_cand = generic_kv_match.group(1).strip()
            v_cand = generic_kv_match.group(2).strip()
            if len(k_cand.split()) <= 5 and not k_cand.endswith((".", ",", ";")):
                flush_para()
                blocks.append({"type": "kv", "content": f"**{k_cand.title()}**: {v_cand}"})
                i += 1
                continue

        # --- Price & Size Lines: e.g. "90 ml - Rp. 70.000", "100 ml - Rp. 205.000", "Rp. 70.000" ---
        price_size_match = re.match(r'^(\d+\s*(?:ml|gr|gram|g|l|liter|pcs|kapsul|tablet|sachet)?\s*[-–/]\s*Rp\.?\s*[\d\.\,]+)$', line_clean, re.IGNORECASE)
        if price_size_match:
            flush_para()
            blocks.append({"type": "kv", "content": f"**Ukuran & Harga**: {line_clean}"})
            i += 1
            continue

        pure_price_match = re.match(r'^(Rp\.?\s*[\d\.\,]+)$', line_clean, re.IGNORECASE)
        if pure_price_match:
            flush_para()
            blocks.append({"type": "kv", "content": f"**Harga**: {line_clean}"})
            i += 1
            continue

        # --- Abbreviations / Single-term Definitions (e.g. DAFTAR SINGKATAN: "AD : autosomal dominan") ---
        abbr_match = re.match(r'^([A-Z0-9\.\-\/]{2,15})\s*:\s*(.+)$', line_clean)
        if abbr_match and not line_clean.startswith("http") and len(abbr_match.group(1).split()) == 1:
            flush_para()
            a_key = abbr_match.group(1).strip()
            a_val = abbr_match.group(2).strip()
            blocks.append({"type": "bullet", "content": f"- **{a_key}**: {a_val}"})
            i += 1
            continue

        next_non_empty = i + 1
        while next_non_empty < N and not lines[next_non_empty].strip():
            next_non_empty += 1

        if next_non_empty < N and lines[next_non_empty].strip().startswith(":") and len(line_clean.split()) == 1 and 2 <= len(line_clean) <= 15:
            flush_para()
            a_key = line_clean
            a_val = lines[next_non_empty].strip().lstrip(": ").strip()
            blocks.append({"type": "bullet", "content": f"- **{a_key}**: {a_val}"})
            i = next_non_empty + 1
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
            is_major = not is_citation and _numbered_title_like(full_heading)
            # An item that continues a numbered list whose previous item stayed a list item ('1. Hair pull
            # test (1B)' -> '2. Trikoskopi / Dermoskopi (2A)') is a list item too, however title-like it reads.
            try:
                num_val = int(num_str)
            except ValueError:
                num_val = None
            if is_major and num_val is not None and last_numbered and last_numbered[0] == num_val - 1 and not last_numbered[1]:
                is_major = False
            # Numbered items that follow each other with no content in between ('1. Topikal' / '2. Sistemik')
            # are a list; numbered headings have their own content below them.
            if is_major and num_val is not None:
                j = i
                while j < N and not lines[j]:
                    j += 1
                if j < N and j - i <= 1 and re.match(rf'^{num_val + 1}[\.\)]\s', lines[j]):
                    is_major = False
            # Siblings are one kind: a numbered title is a heading only when its next sibling ('2. Alpha Lipoic
            # Acid (ALA)') reads as a title as well, otherwise the whole run stays a list.
            if is_major and num_val is not None:
                sib_re = re.compile(rf'^{num_val + 1}[\.\)]\s+(.*)')
                for k in range(i, min(N, i + 80)):
                    if lines[k].startswith("#"):
                        break
                    sm = sib_re.match(lines[k])
                    if sm:
                        if not _numbered_title_like(sm.group(1).strip()):
                            is_major = False
                        break
            last_numbered = (num_val, bool(is_major and full_heading))
            flush_para()
            if is_major and full_heading:
                blocks.append({"type": "heading", "content": f"## {num_str}. {full_heading}"})
            elif full_heading:
                blocks.append({"type": "para", "content": f"{num_str}. {full_heading}"})
            continue

        # --- Lettered items: "a. AHA (Glycolic Acid...)" ---
        letter_match = re.match(r'^([a-zA-Z])[\.\\)]\s+(.*)', line)
        if letter_match and len(letter_match.group(1)) == 1:
            flush_para()
            let_str = letter_match.group(1).lower()
            rest = letter_match.group(2).strip()
            title_parts = [rest] if rest else []
            i += 1
            while i < N and lines[i] and not _is_structural_boundary(lines, i, N):
                title_parts.append(lines[i])
                i += 1
            full_item = " ".join(p for p in title_parts if p).strip()
            blocks.append({"type": "bullet", "content": f"- {let_str}. {full_item}"})
            continue

        # --- Horizontal rule / page separator ('---', '***', '___'): a boundary, never a bullet ---
        if re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', line):
            flush_para()
            blocks.append({"type": "rule", "content": "---"})
            i += 1
            continue

        # --- Bullets: ●, -, *, • (ensure ** bold is NOT matched as a bullet) ---
        bullet_match = re.match(r'^(?:[●\-•]|\*(?!\*))\s*(.*)', line)
        if bullet_match or (line in ("●", "-", "•") or line == "*"):
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

    # Post-processing: Repair code fences, deduplicate slide headings, merge split tables, unpack misplaced notes, and auto-heal GFM tables
    out = repair_markdown_code_fences(out)
    out = deduplicate_slide_headings(out)
    out = merge_fragmented_tables(out)
    out = sanitize_catatan_misplacement(out)
    out = sanitize_null_sections(out)
    try:
        from app.rag.services.rag_generator import repair_markdown_tables
        out = repair_markdown_tables(out)
    except Exception as _tbl_err:
        logger.debug(f"repair_markdown_tables note: {_tbl_err}")
    out = _demote_mixed_numbered_runs(out)
    out = re.sub(r'^[●\-*•]\s*\*-', '- **', out, flags=re.MULTILINE)
    out = re.sub(r'([^\n])\s*(##\s*Slide\s*\d+)', r'\1\n\n\2', out)
    out = re.sub(r'\n{3,}', '\n\n', out)

    bullet_count = sum(1 for b in blocks if b["type"] == "bullet")
    heading_count = sum(1 for b in blocks if b["type"] == "heading")
    logger.debug(
        f"Document Normalization: {len(blocks)} blocks, "
        f"{heading_count} headings, {bullet_count} bullets"
    )
    return out.strip()


def sanitize_null_sections(text: str) -> str:
    """
    Strips stray 'Cara Pakai: null', 'Catatan: null', empty '### Cara Pakai:',
    and markdown null code blocks left by LLM or parser outputs.
    """
    if not text:
        return ""
    # Remove code blocks with null
    text = re.sub(r'```(?:markdown)?\s*null\s*```', '', text, flags=re.IGNORECASE)
    # Remove multiline 'Cara Pakai:\nnull'
    text = re.sub(r'(?i)(?:^|\n)\s*(?:###\s*)?(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*\n+\s*(?:null|none)\b', '', text)
    # Remove inline 'Cara Pakai: null' or 'Catatan: null'
    text = re.sub(r'(?i)(?:^|\n)\s*(?:###\s*)?(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*(?:null|none)\b[^\n]*', '', text)
    # Remove empty headers like '### Cara Pakai:\n\n' when immediately followed by another heading or end of string
    text = re.sub(r'(?i)(?:^|\n)\s*###\s*(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*(?=\n\s*(?:##|###|\Z))', '', text)
    return text


def repair_markdown_code_fences(text: str) -> str:
    """Removes rogue unclosed backtick fences from Vision OCR."""
    if not text:
        return ""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Drop standalone unclosed code fences that don't enclose code or contain null
        if stripped in ('```', '```markdown', '```text') or stripped.lower().startswith('```markdown null') or stripped.lower() in ('```null', '```null```'):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def deduplicate_slide_headings(text: str) -> str:
    """Collapses consecutive or nearby duplicate slide headings."""
    if not text:
        return ""
    lines = text.split('\n')
    out = []
    current_slide_num = None

    for line in lines:
        stripped = line.strip()
        m = re.match(r'^##\s*Slide\s*(\d+)[:\s]*(.*)$', stripped, re.IGNORECASE)
        if m:
            s_num = m.group(1)
            if s_num == current_slide_num:
                # Duplicate heading in same slide -> skip
                continue
            current_slide_num = s_num
            out.append(line)
        else:
            if stripped.startswith('# ') and not stripped.startswith('## Slide'):
                current_slide_num = None
            out.append(line)
    return '\n'.join(out)


def merge_fragmented_tables(text: str) -> str:
    """
    Finds fragmented tables where table 2 has synthetic headers like
    '| Kolom 1 | Kolom 2 | ...' and merges its rows into the preceding table.
    """
    if not text:
        return ""
    
    # Split text into slides or sections by ## Slide
    sections = re.split(r'(?m)(?=^##\s*Slide\s*\d+)', text)
    processed_sections = []

    for sec in sections:
        # Check if section contains a table with 'Kolom 1 | Kolom 2'
        generic_table_match = re.search(
            r'(\|\s*Kolom 1\s*\|\s*Kolom 2\s*\|[^\n]*\n\|(?:\s*[-:]+\s*\|)+\n)([\s\S]*?)(?=\n\n\s*[^|\s]|\n\n\s*$|$)',
            sec
        )
        if generic_table_match:
            generic_full = generic_table_match.group(0)
            generic_rows = generic_table_match.group(2).strip()
            
            # Find the preceding valid table in the same section
            prefix = sec[:generic_table_match.start()]
            suffix = sec[generic_table_match.end():]
            
            # Look for previous table in prefix
            prev_table_match = list(re.finditer(
                r'(\|(?!\s*Kolom 1)[^\n]+\|\n\|(?:\s*[-:]+\s*\|)+\n)([\s\S]*?)(?=\n\n|$)',
                prefix
            ))
            if prev_table_match:
                last_tbl = prev_table_match[-1]
                tbl_start = last_tbl.start()
                tbl_end = last_tbl.end()
                
                clean_generic_rows = "\n".join(r for r in generic_rows.split('\n') if r.strip().startswith('|'))
                in_between = prefix[tbl_end:].strip()
                
                merged_table = prefix[tbl_start:tbl_end].rstrip() + "\n" + clean_generic_rows
                new_sec = prefix[:tbl_start] + merged_table + ("\n\n" + in_between if in_between else "") + ("\n\n" + suffix.strip() if suffix.strip() else "")
                processed_sections.append(new_sec)
                continue
                
        processed_sections.append(sec)

    return "".join(processed_sections)


def sanitize_catatan_misplacement(text: str) -> str:
    """
    Unpacks any application/usage instructions accidentally trapped inside 'Catatan:'
    or '**Catatan**:' blocks into their own '### Cara Pakai' section.
    """
    if not text or ('catatan' not in text.lower() and 'note' not in text.lower()):
        return text

    usage_kws = [
        'aplikasikan', 'oleskan', 'pijat', 'ambil secukupnya', 'teteskan',
        'gunakan secara teratur', 'usapkan', 'gunakan pada pagi', 'gunakan sebelum',
        'cara pakai', 'aturan pakai', 'bersihkan wajah', 'gunakan setelah',
        'tunggu serum pertama meresap'
    ]

    # Pattern 1: Inline '**Catatan**: Aplikasikan...' or 'Catatan: Aplikasikan...'
    def _replace_inline(m):
        content = m.group(1).strip()
        if any(kw in content.lower() for kw in usage_kws):
            return f"### Cara Pakai\n\n{content}"
        return m.group(0)

    text = re.sub(r'\*\*(?:Catatan|Notes?)\*\*:\s*([^\n]+)', _replace_inline, text, flags=re.IGNORECASE)

    # Pattern 2: Multiline 'Catatan:\n- item 1\n- item 2'
    sections = re.split(r'(?m)(?=^##|\n\n(?=###))', text)
    cleaned_sections = []

    for sec in sections:
        cat_match = re.search(r'(?m)^(Catatan|Notes?):\s*\n((?:[ \t]*[-*•].*\n?)+)', sec, re.IGNORECASE)
        if cat_match:
            lines = [l.strip() for l in cat_match.group(2).strip().split('\n') if l.strip()]
            usage_lines = []
            genuine_notes = []
            for l in lines:
                clean_l = re.sub(r'^[-*•]\s*', '', l)
                if any(w in clean_l.lower() for w in usage_kws):
                    usage_lines.append(clean_l)
                else:
                    genuine_notes.append(l)
            
            if usage_lines:
                replacement_parts = []
                replacement_parts.append('### Cara Pakai\n\n' + '\n'.join(f'- {u}' for u in usage_lines))
                if genuine_notes:
                    replacement_parts.append('Catatan:\n' + '\n'.join(genuine_notes))
                
                sec = sec[:cat_match.start()] + '\n\n'.join(replacement_parts) + sec[cat_match.end():]
        cleaned_sections.append(sec)

    return ''.join(cleaned_sections)

