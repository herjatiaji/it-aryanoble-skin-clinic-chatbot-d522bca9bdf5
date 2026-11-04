"""
Text Hygiene and Normalization Utilities for RAG Ingestion and Generation.
PT Arya Noble (ERHA / Dermies Skin Clinic).

Handles:
1. Normalization of Private Use Area (PUA) bullet glyphs and broken font boxes (U+F0B7, U+FFFD, etc.)
2. Merging wrapped line breaks (<br>, <br/>) inside table cells while preserving intentional list breaks
3. Normalization of discontinued product phrasing (e.g. 'Per 12 Juni-stok klinik habis' -> 'sampai dengan')
4. Deterministic post-processing alignment for LLM discontinued responses
"""

import re
from typing import Optional

# Specific PUA / Symbol font bullet mappings frequently found in clinical PDFs (Wingdings/Symbol)
PUA_BULLET_MAP = {
    '\uf0b7': '•',  # Wingdings round bullet
    '\uf0a7': '•',  # Wingdings square bullet
    '\uf06c': '•',  # Symbol bullet
    '\uf0a8': '•',  # Symbol square
    '\uf0d8': '•',  # Symbol arrow/bullet
    '\uf076': '•',  # Generic symbol bullet
    '\uf0fc': '✓',  # Wingdings checkmark
    '\uf0e0': '→',  # Wingdings right arrow
}

# Regex to match any PUA characters (U+E000 to U+F8FF), replacement char (U+FFFD), or box glyphs (U+25AF, U+25A1)
_PUA_GENERAL_RE = re.compile(r'[\uE000-\uF8FF\uFFFD\u25AF\u25A1]')


def normalize_pua_glyphs(text: str) -> str:
    """
    Replaces Private Use Area (PUA) bullet glyphs, replacement characters, and empty square boxes
    with standard clean markdown characters (e.g. '•', '✓', '→').
    If a PUA character appears at the start of a line/cell/list item, it becomes a bullet.
    If it is embedded inside normal alphanumeric words (garbled ligature), it is stripped cleanly.
    """
    if not text:
        return ""

    # 1. Map known Wingdings / Symbol bullets
    res = text
    for char, replacement in PUA_BULLET_MAP.items():
        if char in res:
            res = res.replace(char, replacement)

    # 2. Handle remaining unknown PUA / box glyphs
    if _PUA_GENERAL_RE.search(res):
        def _replace_pua(match: re.Match) -> str:
            # Check context: if at start of string or preceded by whitespace/pipe/newline
            start = match.start()
            if start == 0 or res[start - 1] in " \t\n\r|*#-•":
                return "• "
            # Inside a word or trailing
            return ""

        res = _PUA_GENERAL_RE.sub(_replace_pua, res)
        # Clean up double bullets if any
        res = re.sub(r'•\s*•', '•', res)

    return res


def merge_wrapped_br_in_cell(cell_text: str) -> str:
    """
    Cleans up <br> or <br/> tags within a markdown table cell.
    - If a break occurs before a list item (e.g. '1. ', '2. ', '• ', '- ', '✓', '→')
      or between distinctly separated sentences / footnote markers, preserve the break.
    - If a break is an accidental line-wrap from narrow PDF columns (e.g. 'yang<br>ditandai',
      'Pemeriksaan<br>Penunjang', or trailing commas), merge with a clean space.
    """
    if not cell_text or ("<br" not in cell_text and "<BR" not in cell_text):
        return cell_text

    # Split cell on any variant of <br> or <br/>
    parts = re.split(r'<br\s*/?>', cell_text, flags=re.IGNORECASE)
    if len(parts) <= 1:
        return cell_text

    merged_parts = [parts[0].strip()]

    # Pattern for intentional list items or headers following a break
    list_start_re = re.compile(r'^(?:[•◦▪▫●○■□◆✓✔→➢\-\*]|(?:\d{1,2}|[a-zA-Z]|[ivxIVX]{2,4})[\.\)])\s')

    # Items of an enumeration repeat their leading word ('Clear Me Toner<br>Clear Me Serum');
    # a phrase wrapped by a narrow column does not ('Pemeriksaan<br>Penunjang').
    lead_words = [p.strip().split()[0].lower() for p in parts if p.strip()]
    repeated_leads = {w for w in lead_words if lead_words.count(w) >= 2 and len(w) > 1}

    for i in range(1, len(parts)):
        curr = parts[i].strip()
        prev = merged_parts[-1]

        if not curr:
            continue
        if not prev:
            merged_parts[-1] = curr
            continue

        # Condition to KEEP break:
        # 1. Next part starts with an explicit list marker (1. , • , - , a) , etc.)
        # 2. Either side contains markdown image ![...] or <sub>
        # 3. Previous part ends with a terminal punctuation (. ! ? : ;) followed by uppercase next part or digit
        # 4. Previous part ends with footnote reference digits after period (e.g. '.1,4' or '.2,3') and curr starts uppercase
        is_list = bool(list_start_re.match(curr)) or curr.split()[0].lower() in repeated_leads
        has_media = "![" in prev or "![" in curr or "<sub" in prev or "<sub" in curr
        ends_terminal = bool(re.search(r'[\.\!\?\:\;](?:\d+(?:,\d+)*)?$', prev)) and (curr[0].isupper() or curr[0].isdigit())

        should_keep_break = is_list or has_media or (ends_terminal and len(prev) > 15)

        # Accidental line wraps in narrow PDF columns (e.g. 'Pemeriksaan<br>Penunjang', 'Diagnosis<br>Banding')
        # should NEVER be broken into separate lines if they lack terminal punctuation and are not lists!
        if not is_list and not has_media:
            prev_is_item = bool(list_start_re.match(prev))
            if prev.endswith((',', '-', '&', '/')) or curr[0].islower() or curr.startswith(('dan ', 'atau ', 'yang ', 'dengan ', 'untuk ')):
                should_keep_break = False
            elif not ends_terminal and not prev_is_item and len(prev.split()) <= 3 and len(curr.split()) <= 3:
                # A short title wrapped by a narrow column ('Pemeriksaan' + 'Penunjang'). A label followed by its
                # text ('Nonmedikamentosa' / 'Kamuflase (rambut palsu, ...)') or a list item followed by its
                # description ('1. Alopesia areata tipe patchy' / 'Patch kebotakan ...') are separate lines.
                should_keep_break = False
            elif not ends_terminal:
                should_keep_break = True

        if should_keep_break:
            # Keep as a single clean <br/> separator for tables
            merged_parts.append(curr)
        else:
            # Merge with space (accidental word wrapping)
            if prev.endswith('-') and len(prev) >= 2 and prev[-2].isalpha() and curr[0].isalpha():
                # Word hyphenation wrap (e.g. 'pe-<br>meriksaan' -> 'pemeriksaan')
                merged_parts[-1] = prev[:-1] + curr
            else:
                merged_parts[-1] = prev + " " + curr

    return "<br/>".join(merged_parts)


def join_multiline_table_cells(markdown_text: str) -> str:
    """
    Re-joins table rows whose cells were written over several lines ('| Step 2 | • Toner\\n• Serum |').
    Markdown ends a row at the line break, so such a row falls apart into loose text, stray pipes and
    a broken table. A row that starts with '|' but has no closing '|' continues on the following lines
    (those not starting a new row) until the closing '|'; the pieces are joined with <br>.
    """
    if not markdown_text or "|" not in markdown_text:
        return markdown_text
    lines = markdown_text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if stripped.lstrip().startswith("|") and not stripped.endswith("|"):
            parts = [stripped]
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("|") or nxt.startswith("#"):
                    break
                parts.append(nxt)
                j += 1
                if nxt.endswith("|"):
                    break
            if len(parts) > 1 and parts[-1].endswith("|"):
                out.append("<br>".join(p.strip() for p in parts))
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def clean_markdown_table_breaks(markdown_text: str) -> str:
    """
    Processes markdown text line-by-line. For markdown table rows (lines starting with '|'),
    merges wrapped <br> tags within each cell appropriately.
    """
    if not markdown_text or "|" not in markdown_text or ("<br" not in markdown_text and "<BR" not in markdown_text):
        return markdown_text

    lines = markdown_text.split("\n")
    processed_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and not re.match(r'^\|(?:\s*:?-{3,}:?\s*\|)+$', stripped):
            # Table data or header row
            cells = line.split("|")
            # Preserve leading and trailing empty strings from split
            new_cells = []
            for idx, c in enumerate(cells):
                if idx == 0 or idx == len(cells) - 1:
                    new_cells.append(c)
                else:
                    new_cells.append(merge_wrapped_br_in_cell(c))
            processed_lines.append("|".join(new_cells))
        else:
            processed_lines.append(line)

    return "\n".join(processed_lines)


def normalize_discontinue_phrases(text: str) -> str:
    """
    Normalizes discontinued badge text where a dash '-' separates a date and stock status.
    In Indonesian clinical catalogs, 'Per 12 Juni - stok klinik habis' means
    'Per 12 Juni sampai dengan stok klinik habis'.
    """
    if not text:
        return ""

    res = text

    # Pattern: 'per/sejak/mulai [DD Month YYYY] - stok klinik habis'
    # e.g. 'Per 12 Juni - stok klinik habis' -> 'Per 12 Juni sampai dengan stok klinik habis'
    pattern_date_stock = re.compile(
        r'\b((?:per|sejak|mulai)\s+\d{1,2}\s+[A-Za-z]{3,}(?:\s+\d{4})?)\s*[-–—]\s*(stok\s+klinik\s+habis|stok\s+habis|stock\s+habis)',
        re.IGNORECASE
    )
    res = pattern_date_stock.sub(r'\1 sampai dengan \2', res)

    # Pattern: 'Discontinue : Per 12 Juni - stok habis'
    pattern_disc_badge = re.compile(
        r'\b(discontinue[a-z]*)\s*[:\-]\s*((?:per|sejak|mulai)\s+\d{1,2}\s+[A-Za-z]{3,}(?:\s+\d{4})?)\s*[-–—]\s*(stok\s+(?:klinik\s+)?habis)',
        re.IGNORECASE
    )
    res = pattern_disc_badge.sub(r'\1: \2 sampai dengan \3', res)

    return res


# Any availability/discontinuation status assertion (badge, bullet, or sentence)
STATUS_CLAIM_RE = re.compile(
    r'\bdiscontinu\w*'
    r'|\bstok\s+(?:klinik\s+)?(?:telah\s+|sudah\s+)?habis\b'
    r'|\b(?:sudah\s+)?tidak\s+(?:lagi\s+)?diproduksi\b',
    re.IGNORECASE
)
_STATUS_NEGATION_RE = re.compile(
    r'\b(?:tidak\s+ada|bukan|belum|tidak\s+(?:termasuk|berstatus|dinyatakan|tercantum))\b',
    re.IGNORECASE
)
# 'Informasi ... discontinue ... belum tersedia': the sentence reports missing information, it asserts nothing
_INFO_ABSENT_RE = re.compile(
    r'\b(?:belum|tidak)\s+(?:tersedia|ditemukan|disebutkan|tercantum|ada\s+(?:informasi|data|keterangan))\b',
    re.IGNORECASE
)
_DATE = r'\d{1,2}\s+[A-Za-z]{3,}(?:\s+\d{4})?'
# A status period as written by the source after normalization: 'Per 12 Juni sampai dengan stok klinik habis'
_CANON_PERIOD_RE = re.compile(
    rf'\b(?:per|sejak|mulai)\s+({_DATE})\s+sampai\s+dengan\s+stok\s+(?:klinik\s+)?habis\b',
    re.IGNORECASE
)
# The same period as re-phrased by an LLM: 'per 12 Juni, dan stok klinik telah habis', 'per 12 Juni hingga stok habis', ...
_PARAPHRASED_PERIOD_RE = re.compile(
    rf'\b(?:per|sejak|mulai)\s+({_DATE})\b[^.\n|]{{0,60}}?\bstok\s+(?:klinik\s+)?(?:telah\s+|sudah\s+)?habis\b',
    re.IGNORECASE
)
_BADGE_RE = re.compile(r'\s*[\(\[][^\)\]\n]*?(?:discontinu|stok\s+(?:klinik\s+)?habis)[^\)\]\n]*[\)\]]\**', re.IGNORECASE)
_LABEL_ONLY_RE = re.compile(r'^(?:status|catatan|keterangan|ketersediaan|availability)?\s*:?$', re.IGNORECASE)


def _date_key(date_str: str) -> str:
    return re.sub(r'\s+', ' ', date_str.strip().lower())


def has_status_notice(text: str) -> bool:
    """True if the text asserts (not negates) a discontinuation/stock-out status."""
    for m in STATUS_CLAIM_RE.finditer(text or ""):
        sentence_start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
        ends = [i for i in (text.find(".", m.end()), text.find("\n", m.end())) if i != -1]
        sentence = text[sentence_start:(min(ends) if ends else len(text))]
        # Negated claim ('tidak ada yang discontinue') or a report of missing information
        if _STATUS_NEGATION_RE.search(text[sentence_start:m.start()]) or _INFO_ABSENT_RE.search(sentence):
            continue
        return True
    return False


def _strip_claim_fragments(fragment: str) -> str:
    cleaned = _BADGE_RE.sub("", fragment)
    if not STATUS_CLAIM_RE.search(cleaned):
        return cleaned
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    kept = [s for s in sentences if not has_status_notice(s)]
    return " ".join(kept)


def strip_status_claims(markdown_text: str) -> str:
    """
    Removes affirmative discontinuation/stock-out claims (badges like '(DISCONTINUED)', status
    bullets, and asserting sentences) while leaving negations ('tidak ada yang discontinue') intact.
    Used when a claim has no supporting evidence in the source.
    """
    if not markdown_text or not STATUS_CLAIM_RE.search(markdown_text):
        return markdown_text

    out_lines = []
    for line in markdown_text.split("\n"):
        if not has_status_notice(line):
            out_lines.append(line)
            continue
        if line.strip().startswith("|"):
            out_lines.append("|".join(_strip_claim_fragments(c) for c in line.split("|")))
            continue
        cleaned = _strip_claim_fragments(line)
        bare = re.sub(r'[\s\-*•#>_|]+', ' ', cleaned).strip()
        if not bare or _LABEL_ONLY_RE.match(bare):
            continue
        out_lines.append(cleaned.rstrip())
    return re.sub(r'\n{3,}', '\n\n', "\n".join(out_lines))


def ground_status_claims(answer: str, evidence_text: str) -> str:
    """
    Grounds availability/discontinuation statements in a generated answer against the evidence
    the answer was generated from:
    - No status notice anywhere in the evidence -> affirmative status claims are removed.
    - Evidence states a period ('per <tanggal> sampai dengan stok klinik habis') -> any paraphrase
      of that period in the answer is replaced verbatim with the evidence wording.
    """
    if not answer or not STATUS_CLAIM_RE.search(answer):
        return answer

    evidence_norm = normalize_discontinue_phrases(evidence_text or "")
    if not has_status_notice(evidence_norm):
        return strip_status_claims(answer)

    canonical_periods = {_date_key(m.group(1)): m.group(0) for m in _CANON_PERIOD_RE.finditer(evidence_norm)}
    if not canonical_periods:
        return answer

    def _restore_period(m: re.Match) -> str:
        canon = canonical_periods.get(_date_key(m.group(1)))
        if not canon:
            return m.group(0)
        return canon[0].lower() + canon[1:] if m.group(0)[0].islower() else canon

    return _PARAPHRASED_PERIOD_RE.sub(_restore_period, answer)


_ACRONYM_FIRST_RE = re.compile(r'\b([A-Z][A-Z0-9]{1,7})\s*\(\s*([A-Za-z][^()\n]{2,80}?)\s*\)')
_EXPANSION_FIRST_RE = re.compile(r'\b([A-Za-z][\w\-]*(?:\s+[\w\-&]+){1,7})\s*\(\s*([A-Z][A-Z0-9]{1,7})\s*\)')
_CONNECTOR_WORDS = {"dan", "and", "of", "the", "&", "untuk", "for", "di", "pada"}


def _norm_phrase(text: str) -> str:
    return re.sub(r'[\s\-]+', ' ', (text or "").lower()).strip()


def _initials_match(acronym: str, expansion: str) -> bool:
    words = [w for w in re.split(r'[\s\-]+', expansion) if w and w.lower() not in _CONNECTOR_WORDS]
    initials = "".join(w[0] for w in words).upper()
    return initials == acronym.upper() or (len(words) == len(acronym) - 1 and acronym.upper().startswith(initials))


def _looks_like_expansion(acronym: str, phrase: str) -> bool:
    """
    'ACR (Some Phrase)' is read as an expansion claim when the phrase is a multi-word name starting
    with the acronym's first letter. Generated expansions are not always letter-consistent
    ('EPA (Excessive Post-inflammatory Hyperpigmentation)'), so exact initials are not required.
    """
    words = [w for w in re.split(r'\s+', phrase.strip()) if w]
    return (
        _initials_match(acronym, phrase)
        or (len(words) >= 2 and words[0][0].upper() == acronym[0].upper() and not any(ch.isdigit() for ch in phrase))
    )


def ground_acronym_expansions(answer: str, evidence_text: str) -> str:
    """
    Keeps an acronym expansion ('EPA (Erythema Post Acne)' or 'Erythema Post Acne (EPA)') only when
    that expansion is written in the evidence; otherwise the answer keeps the bare acronym as written
    in the source. Only pairs whose word initials spell the acronym are treated as expansions, so
    descriptive parentheses ('Laser (V-beam, Proyellow)') are untouched.
    """
    if not answer:
        return answer
    evidence_norm = _norm_phrase(evidence_text)
    if "(" not in answer:
        return _ground_prose_expansions(answer, evidence_norm)

    def _acronym_first(m: re.Match) -> str:
        acr, exp = m.group(1), m.group(2)
        if not _looks_like_expansion(acr, exp) or _norm_phrase(exp) in evidence_norm:
            return m.group(0)
        return acr

    def _expansion_first(m: re.Match) -> str:
        exp, acr = m.group(1), m.group(2)
        # The expansion is the trailing words whose initials spell the acronym
        words = exp.split()
        for start in range(len(words)):
            candidate = " ".join(words[start:])
            if _initials_match(acr, candidate):
                if _norm_phrase(candidate) in evidence_norm:
                    return m.group(0)
                prefix = " ".join(words[:start])
                return f"{prefix} {acr}".strip()
        return m.group(0)

    res = _ACRONYM_FIRST_RE.sub(_acronym_first, answer)
    res = _EXPANSION_FIRST_RE.sub(_expansion_first, res)
    return _ground_prose_expansions(res, evidence_norm)


# 'EPA adalah singkatan dari Erythema Post Acne, yang ...' / 'kepanjangan EPA adalah Erythema Post Acne.'
_PROSE_EXPANSION_RE = re.compile(
    r'(?P<b1>\*{0,2})(?P<acr>[A-Z][A-Z0-9]{1,7})(?P<b2>\*{0,2})\s+(?:adalah|merupakan|ialah)\s+'
    r'(?:singkatan|kepanjangan|kependekan|akronim)\s+(?:dari\s+)?\*{0,2}(?P<exp>[^*,.;:\n()]+?)\*{0,2}'
    r'(?P<tail>\s*,\s*(?:yang\s+)?|\s+yang\s+|\s*[.;:]|\s*$)'
)
_PROSE_EXPANSION_REVERSED_RE = re.compile(
    r'[^.\n]*\b(?i:singkatan|kepanjangan|kependekan)\s+(?i:dari\s+)?\*{0,2}(?P<acr>[A-Z][A-Z0-9]{1,7})\*{0,2}\s+'
    r'(?i:adalah|ialah|yaitu|yakni)\s+\*{0,2}(?P<exp>[^*,.;:\n()]+?)\*{0,2}\s*[.;\n]'
)


def _ground_prose_expansions(answer: str, evidence_norm: str) -> str:
    """
    Removes acronym expansions stated in prose when the evidence never writes them. The rest of the
    sentence (what the source does say about the acronym) is kept: 'EPA adalah singkatan dari X, yang
    merujuk pada ...' becomes 'EPA merujuk pada ...'; a sentence that only states the expansion is dropped.
    """
    def _unsupported(acr: str, exp: str) -> bool:
        exp = exp.strip()
        return _initials_match(acr, exp) and _norm_phrase(exp) not in evidence_norm

    def _forward(m: re.Match) -> str:
        if not _unsupported(m.group("acr"), m.group("exp")):
            return m.group(0)
        if re.match(r'\s*([.;:]|$)', m.group("tail")):
            return ""  # the statement was only the expansion
        # The sentence goes on to say something about the acronym: keep that part
        return f"{m.group('b1')}{m.group('acr')}{m.group('b2')} "

    res = _PROSE_EXPANSION_RE.sub(_forward, answer)
    res = _PROSE_EXPANSION_REVERSED_RE.sub(
        lambda m: "" if _unsupported(m.group("acr"), m.group("exp")) else m.group(0), res
    )
    return re.sub(r'[ \t]{2,}', ' ', res)


_TABLE_DELIM_RE = re.compile(r'^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$')


def _split_row(line: str) -> list:
    cells = line.strip()
    if cells.startswith("|"):
        cells = cells[1:]
    if cells.endswith("|"):
        cells = cells[:-1]
    return [c.strip() for c in cells.split("|")]


def wide_tables_to_records(text: str, min_cols: int = 6) -> str:
    """
    Rewrites markdown tables with many columns into one record per row where every value carries
    its column name ('Prosedur - Massage Bahu: -'). In wide matrices (catalogs with 15-25 columns,
    check/cross protocol grids) a model must otherwise count pipes to know which column a cell
    belongs to, and misreads values. Narrow tables are left unchanged.
    """
    if not text or "|" not in text:
        return text

    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        is_header = (
            line.strip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_DELIM_RE.match(lines[i + 1].strip())
        )
        if not is_header:
            out.append(line)
            i += 1
            continue

        headers = _split_row(line)
        j = i + 2
        rows = []
        while j < len(lines) and lines[j].strip().startswith("|"):
            rows.append(_split_row(lines[j]))
            j += 1

        if len(headers) < min_cols:
            out.extend(lines[i:j])
            i = j
            continue

        previous: list = []
        for n, row in enumerate(rows, start=1):
            # Leading cells left blank under a visually merged group cell inherit the group value
            first_filled = next((c for c, v in enumerate(row) if v), len(row))
            row = [previous[c] if (c < first_filled and c < len(previous)) else v for c, v in enumerate(row)]
            previous = row
            pairs = [
                f"{headers[c] or f'Kolom {c + 1}'}: {val}"
                for c, val in enumerate(row)
                if c < len(headers) and val
            ]
            out.append(f"- Baris {n}: " + "; ".join(pairs))
        i = j
    return "\n".join(out)


def remove_answer_lines(answer: str, flagged_line_numbers) -> str:
    """
    Removes the given 1-based line numbers from a markdown answer, together with the lines nested
    under them (deeper-indented continuation/sub-bullets), then drops headings left without content.
    """
    if not answer or not flagged_line_numbers:
        return answer
    flagged = {int(n) for n in flagged_line_numbers}
    lines = answer.split("\n")

    def _indent(s: str) -> int:
        return len(s) - len(s.lstrip(" \t"))

    heading_re = re.compile(r'^\s*(#{1,6})\s+\S')
    # A section title the answer states as a heading or a bold-only line ('### Kontraindikasi', '**Kontraindikasi**')
    title_re = re.compile(r'^\s*(?:(#{1,6})\s+\S.*|\*\*[^*]+\*\*:?)\s*$')

    def _title_level(s: str):
        m = title_re.match(s)
        if not m:
            return None
        return len(m.group(1)) if m.group(1) else 7  # a bold title ranks below every markdown heading

    kept = []
    skip_deeper_than = None
    skip_section_level = None
    for idx, line in enumerate(lines, start=1):
        if skip_section_level is not None:
            level = _title_level(line)
            # A bold title's section ends at a blank line; a heading's at the next heading of its rank or above
            ends = (level is not None and level <= skip_section_level) or (skip_section_level == 7 and not line.strip()) \
                or bool(_DEFERRAL_RE.search(line))  # the closing note leaving the judgment to the doctor stays
            if not ends:
                continue
            skip_section_level = None
            if line.strip() and kept and kept[-1].strip():
                kept.append("")  # keep the next block apart from the list above it
        if skip_deeper_than is not None:
            if line.strip() and _indent(line) > skip_deeper_than:
                continue
            skip_deeper_than = None
        if idx in flagged:
            level = _title_level(line)
            if level is not None:
                # The lines under a removed title go with it: left in place they would read as part of the
                # section above (contraindications listed under 'Indikasi')
                skip_section_level = level
            else:
                skip_deeper_than = _indent(line)
            continue
        kept.append(line)

    # Drop headings whose section became empty (next non-blank line is a same/higher heading or the end)
    result = []
    for i, line in enumerate(kept):
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            nxt = next((l for l in kept[i + 1:] if l.strip()), None)
            nm = heading_re.match(nxt) if nxt is not None else None
            if nxt is None or (nm and len(nm.group(1)) <= level):
                continue
        result.append(line)
    return re.sub(r'\n{3,}', '\n\n', "\n".join(result)).strip()


# Joining words, and currency labels a source often omits around a price ('Rp 600.000' vs '600000')
_CLAIM_STOP_WORDS = {"dan", "atau", "yang", "untuk", "dengan", "pada", "dari", "di", "ke", "the", "and", "of", "for", "with",
                     "rp", "idr"}


_THOUSANDS_RE = re.compile(r'\b\d{1,3}(?:[.,]\d{3})+\b')
# A decimal that PDF/slide extraction split with a space before a unit ('16. 0cm²', '0. 25cm²') is one number;
# the unit right after the digits keeps a numbered list ('1. 2 kali') out of it
_SPLIT_DECIMAL_RE = re.compile(r'(?<![\d.,])(\d+)([.,])[ \t]+(\d+)(?=[a-zµ²³%])')


# A reference number printed against the word it follows ('krim16', 'Crisaborole17', 'Klasifikasi2') is not
# part of the word; applied to claim and evidence alike, so a code such as 'MBTPS2' still matches itself.
_GLUED_FOOTNOTE_RE = re.compile(r'([a-z]{3,})(\d{1,2}(?:[,\-–]\d{1,2})*)(?=[^a-z0-9]|$)')


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = diff = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            diff += 1
            if diff > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return diff + (len(b) - j) + (len(a) - i) <= 1


def _claim_words(text: str) -> list:
    norm = _SPLIT_DECIMAL_RE.sub(r'\1\2\3', (text or "").lower())
    norm = _GLUED_FOOTNOTE_RE.sub(r'\1 \2', norm)
    norm = re.sub(r'[*_`#>|\[\]()]', ' ', norm)
    # A number is the same value with or without thousands separators ('600.000', '600,000', '600000')
    norm = _THOUSANDS_RE.sub(lambda m: re.sub(r'[.,]', '', m.group(0)), norm)
    return [w for w in re.findall(r'[a-z0-9]+(?:[.,][0-9]+)?', norm) if len(w) >= 2 and w not in _CLAIM_STOP_WORDS]


def evidence_units(evidence_text: str) -> list:
    """
    The evidence as units a fact is stated in: each line together with the headings above it, and each
    table row together with its column header, so a value is read with the item it belongs to.
    """
    units, headings, table_header = [], [], None
    for raw in (evidence_text or "").split("\n"):
        line = raw.strip()
        if not line:
            table_header = None
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)', line)
        if heading:
            level = len(heading.group(1))
            headings = [h for h in headings if h[0] < level] + [(level, heading.group(2))]
            table_header = None
            continue
        context = " ".join(h for _, h in headings)
        if line.startswith("|"):
            if re.fullmatch(r'\|[\s:\-|]+\|?', line):
                continue
            if table_header is None:
                table_header = line
                continue
            units.append(f"{context} {table_header} {line}")
        else:
            units.append(f"{context} {line}")
    return units


_CHUNK_HEADER_RE = re.compile(r'^Judul dokumen:\s*(.*?)\s*(?:\|\s*Bagian:\s*(.*?)\s*)?\|\s*Isi:\s*(.*)$')
_DEFERRAL_RE = re.compile(r'\b(?:ada\s+pada|diserahkan\s+kepada)\s+dokter\b', re.IGNORECASE)
_RELATED_CRITERIA_RE = re.compile(r'^[\s*_>-]*kriteria\s+yang\s+berkaitan\b[\s*_:]*', re.IGNORECASE)


def neutral_answer_line(line: str) -> bool:
    """
    A single short sentence that only reports something as not listed ('Dermatitis tidak tercantum secara
    eksplisit pada kriteria DPCT') or leaves the clinical judgment to the doctor. It asserts no fact, so it needs
    no evidence; a number, a table cell or a second clause could carry a claim and makes the line ordinary.
    """
    text = (line or "").strip()
    if "|" in text or any(ch.isdigit() for ch in text) or len(_claim_words(text)) > 20:
        return False
    if re.search(r'\b(?:namun|tetapi|tapi|sedangkan|karena|yaitu|seperti|misalnya)\b|[.;:]\s+\S', text, re.IGNORECASE):
        return False
    return bool(_INFO_ABSENT_RE.search(text) or _DEFERRAL_RE.search(text))


# Words too general to tie an asked condition to a criterion ('kulit' is in nearly every criterion)
_GENERIC_CONDITION_WORDS = {"kulit", "pasien", "wajah", "kondisi", "area", "tindakan", "kriteria", "skin", "patient"}


def drop_unproven_related_criteria(answer: str, evidence_context: str, query: str) -> str:
    """
    In a judgment answer, the 'Kriteria yang berkaitan: ...' line links the asked condition to a criterion. A
    model's sense of what is related cannot be checked (dermatitis read as 'jerawat sedang-berat'), so the line
    stays only when the quoted criterion names the asked condition in the question's own words, and that
    criterion and the item it names are stated together in one evidence line or row, never carried over from
    another item's document. The list a bare label introduces goes with it. When such a criterion stays, the
    condition is listed after all, so a line saying it is not listed is dropped as contradicting it.
    """
    asked = set(_claim_words(query)) - _GENERIC_CONDITION_WORDS
    kept, dropping, related = [], False, False
    for line in (answer or "").split("\n"):
        m = _RELATED_CRITERIA_RE.match(line)
        if m:
            criterion = line[m.end():]
            quoted = (re.findall(r'"([^"]+)"', criterion) or [criterion])[0]
            dropping = not (criterion.strip() and asked & set(_claim_words(quoted))
                            and not unproven_answer_lines(criterion, evidence_context))
            related = related or not dropping
            if dropping:
                continue
        elif dropping and line.strip().startswith(("-", "*")):
            continue
        else:
            dropping = False
        kept.append(line)
    # 'X tidak tercantum secara eksplisit ...' must be about the asked condition, not a criterion standing in for it
    # ('Wanita hamil' when breastfeeding was asked); a related criterion kept above means it is listed after all
    # It is also false when the answer goes on to present that condition itself on another line ('Luka bakar tidak
    # tercantum ...' and then '### Penanganan Luka Bakar'): a judgment answer never describes the asked condition
    def presented_elsewhere(subject: set, own: str) -> bool:
        if not subject:
            return False
        need = 1 if len(subject) == 1 else max(2, (len(subject) + 1) // 2)
        return any(l is not own and not neutral_answer_line(l) and len(subject & set(_claim_words(l))) >= need
                   for l in kept)

    def false_absence(line: str) -> bool:
        m = re.search(r'\btidak\s+tercantum\s+secara\s+eksplisit\b', line, re.IGNORECASE)
        if not m:
            return False
        subject = asked & set(_claim_words(line[:m.start()]))
        return related or not subject or presented_elsewhere(subject, line)
    kept = [l for l in kept if not false_absence(l)]
    # 'The judgment is the doctor's' closes a judgment answer only; on a price or a product list it is a template
    is_judgment = related or any(re.search(r'\btidak\s+tercantum\s+secara\s+eksplisit\b', l, re.IGNORECASE) for l in kept)
    if not is_judgment:
        kept = [l for l in kept if not (neutral_answer_line(l) and _DEFERRAL_RE.search(l))]
    return "\n".join(kept).strip("\n")


def drop_empty_tables(answer: str) -> str:
    """Removes a markdown table left with a header and no rows (its rows removed, or never written)."""
    lines = (answer or "").split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            block = [l for l in lines[i:j] if not re.fullmatch(r'\|?[\s:\-|]+\|?', l.strip())]
            if len(block) > 1:
                out += _drop_empty_columns(lines[i:j])
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# A cell that states nothing: left blank, a dash, or a placeholder saying nothing is listed
_EMPTY_CELL_RE = re.compile(
    r'^(?:|[-–—/]|n/?a|none|tidak\s+ada|tidak\s+tercantum|tidak\s+disebutkan|belum\s+tersedia|'
    r'tidak\s+ada\s+yang\s+(?:tercantum|disebutkan)|tidak\s+tersedia)\.?$', re.IGNORECASE)


def _drop_empty_columns(table_lines: list) -> list:
    """
    Removes a table column whose every body cell states nothing ('-', 'Tidak ada yang tercantum'): such a column
    reads as a finding ('no contraindications') while it only means the source gave none. The first column and a
    table left with a single column are kept as they are.
    """
    def cells(line: str) -> list:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    rows = [cells(l) for l in table_lines]
    is_rule = [bool(re.fullmatch(r'\|?[\s:\-|]+\|?', l.strip())) for l in table_lines]
    body = [r for r, rule in zip(rows[1:], is_rule[1:]) if not rule]
    width = len(rows[0])
    if not body or width < 3 or any(len(r) != width for r in rows):
        return table_lines
    empty = {k for k in range(1, width) if all(_EMPTY_CELL_RE.match(r[k].strip("*_ ")) for r in body)}
    if not empty or len(empty) >= width - 1:
        return table_lines
    return ["| " + " | ".join(c for k, c in enumerate(r) if k not in empty) + " |" for r in rows]


_EMPTY_LABEL_RE = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)\*\*[^*]{1,120}?:?\*\*\s*:?\s*$')


def drop_empty_labels(answer: str) -> str:
    """
    Removes a list-item label ('2. **PicoSure Focus Lens Array:**') whose content is gone: what follows is the
    next bold label at its own level, a heading, a closing remark that asserts nothing, or the end. A plain bullet
    after it, even unindented, is read as its content.
    """
    lines = (answer or "").split("\n")

    def indent(s: str) -> int:
        return len(s) - len(s.lstrip(" \t"))

    kept = []
    for i, line in enumerate(lines):
        labeled = _LABELED_LINE_RE.match(line)
        if labeled and labeled.group(2).strip() and _EMPTY_CELL_RE.match(labeled.group(2).strip().strip("*_ ")):
            # 'Kontraindikasi: Tidak ada yang tercantum.' reads as a finding while the source only gave none
            continue
        if _EMPTY_LABEL_RE.match(line):
            nxt = next((l for l in lines[i + 1:] if l.strip()), None)
            empty = (nxt is None or nxt.lstrip().startswith("#") or neutral_answer_line(nxt)
                     or (indent(nxt) <= indent(line) and re.match(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)\*\*', nxt)))
            if empty:
                continue
        kept.append(line)
    return re.sub(r'\n{3,}', '\n\n', "\n".join(kept))


def _evidence_word_units(evidence_context: str) -> list:
    """The words of each evidence line or table row, read under its document title, section and headings."""
    # Chunk headers become headings, so each evidence line is read under its document and section
    as_markdown = []
    for raw in (evidence_context or "").split("\n"):
        m = _CHUNK_HEADER_RE.match(raw.strip())
        if m:
            as_markdown += ["", f"# {m.group(1)} {m.group(2) or ''}".rstrip(), m.group(3)]
        else:
            as_markdown.append(raw)
    units = [set(_claim_words(u)) for u in evidence_units("\n".join(as_markdown))]
    return [u for u in units if u]


def _section_end(lines: list, start: int) -> int:
    """The index after the section a heading or bold item line opens (up to the next one of the same or higher rank)."""
    head = lines[start].strip()
    level = len(head) - len(head.lstrip("#")) if head.startswith("#") else 7
    for j in range(start + 1, len(lines)):
        nxt = lines[j].strip()
        if nxt.startswith("#") and len(nxt) - len(nxt.lstrip("#")) <= level:
            return j
        if level == 7 and _ITEM_HEADER_RE.match(nxt):
            return j
    return len(lines)




def asked_item_names(query: str) -> list:
    """
    The item names a question writes as names: runs of two or more capitalised words ('Thread HGAT', 'Ultraformer
    MPT', 'Single Photorejuvenation Laser Neck - Rev'), joined across '-', '&', '+' or '/' between capitalised
    words. The word opening a sentence counts only when the name goes on after it ('Pasien mengalami ...' is none).
    """
    names = []
    for sentence in re.split(r"(?<=[.?!])\s+|\n", query or ""):
        words = [w.strip(",;:?!.()[]\"'") for w in sentence.strip().split()]
        words = [w for w in words if w]
        run = []

        def close():
            while run and not run[-1][:1].isupper():
                run.pop()
            if sum(1 for w in run if w[:1].isupper()) >= 2:
                names.append(" ".join(run))
            run.clear()

        for i, w in enumerate(words):
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if i == 0 and not nxt[:1].isupper():
                continue
            if w[:1].isupper():
                run.append(w)
            elif run and w in ("-", "&", "+", "/") and nxt[:1].isupper():
                run.append(w)
            else:
                close()
        close()
    return names


_LABEL_RE = re.compile(r"^\s*(?:#{1,6}\s+(.+?)\s*$|(?:[-*+]\s+|\d+[.)]\s+)?\*\*([^*]{2,120})\*\*)")


def labels_from_question_only(answer: str, query: str, evidence_text: str) -> list:
    """
    (line number, phrase) for each answer heading or bold label that names its content with a two-word phrase of
    the question the evidence never writes, although it writes some of its words ('Tuning Pulses' over RF pulse data,
    when the source has 'RF pulses' but no tuning pulses): the model has mixed the source's words with the question's
    term and filed evidence under it. A label in another language than the source ('Luka Bakar' for 'Burns') shares
    no word with it and is a translation, not this; the caller still checks a translation of what is returned
    ('kulit tipis' for 'thin skin' shares 'kulit' with other Indonesian evidence).
    """
    from difflib import SequenceMatcher
    q_words = _claim_words(query)
    q_pairs = {p for p in zip(q_words, q_words[1:]) if p[0].isalpha() and p[1].isalpha()}
    ev_words = _claim_words(evidence_text)
    evidence_vocabulary = set(ev_words)
    evidence_pairs = set(zip(ev_words, ev_words[1:]))

    def similar(a, b):
        return a == b or (len(a) >= 4 and len(b) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.8)

    def written(pair):
        # The evidence's own spelling may differ ('MPT Catridge' for 'MPT Cartridge')
        return any(similar(pair[0], e0) and similar(pair[1], e1) for e0, e1 in evidence_pairs)
    found = []
    for n, line in enumerate((answer or "").split("\n"), start=1):
        m = _LABEL_RE.match(line)
        if not m:
            continue
        words = [w for w in _claim_words(m.group(1) or m.group(2)) if w.isalpha()]
        for pair in zip(words, words[1:]):
            phrase = " ".join(pair)
            if pair in q_pairs and any(w in evidence_vocabulary for w in pair) and not written(pair):
                found.append((n, phrase))
                break
    return found


def unknown_named_items(query: str, document_frequency: dict) -> tuple:
    """
    (names the question writes that no document uses, names it writes that documents use). A name is a word typed
    with a capital inside a sentence ('apakah Thermage aman ...'); the word opening a sentence is not one.
    """
    unknown, known = [], []
    for sentence in re.split(r"(?<=[.?!])\s+|\n", query or ""):
        for w in [t.strip(",;:?!.()\"'") for t in sentence.split()[1:]]:
            if len(w) >= 4 and w[:1].isupper() and w.isalpha():
                (known if document_frequency.get(w.lower(), 0) > 0 else unknown).append(w)
    return unknown, known


def drop_unknown_items(answer: str, evidence_context: str, query: str, is_known_word) -> str:
    """
    Removes what the answer says about an item asked for by name that the evidence does not hold. The words of each
    name the question writes (`asked_item_names`) that the evidence uses must be found together in one evidence line
    or row wherever an answer line names two or more of them, so 'Thread HGAT' is not assembled from a 'HGAT' hair
    treatment row and a '10 Thread' lifting row. Words most documents use (`is_known_word` false, e.g. 'facial')
    do not tell items apart and are not checked. A heading or bold item failing this takes its section with it.
    """
    units = _evidence_word_units(evidence_context)
    vocabulary = set().union(*units) if units else set()
    names = []
    for name in asked_item_names(query):
        words = {w for w in _claim_words(name) if w in vocabulary and not any(ch.isdigit() for ch in w) and is_known_word(w)}
        if len(words) >= 2:
            names.append(words)
    lines = (answer or "").split("\n")
    drop = set()
    for i, line in enumerate(lines):
        if i in drop or neutral_answer_line(line):
            continue
        line_words = set(_claim_words(line))
        unknown = [n & line_words for n in names if len(n & line_words) >= 2
                   and not any((n & line_words) <= u for u in units)]
        if not unknown:
            continue
        is_heading = line.strip().startswith("#") or _ITEM_HEADER_RE.match(line.strip())
        drop.update(range(i, _section_end(lines, i)) if is_heading else [i])
    return "\n".join(l for i, l in enumerate(lines) if i not in drop)


def table_only_items(query: str, evidence_context: str) -> list:
    """
    The item names the question writes (`asked_item_names`) that the evidence holds only as table rows, such as a
    catalogue or price list entry: every evidence line naming them is a row, none is text describing them.
    """
    lines = [l.strip() for l in (evidence_context or "").split("\n")
             if l.strip() and not _CHUNK_HEADER_RE.match(l.strip())]
    line_words = [(l, set(_claim_words(l))) for l in lines]
    found = []
    for name in asked_item_names(query):
        words = {w for w in _claim_words(name) if not any(ch.isdigit() for ch in w)}
        naming = [l for l, lw in line_words if words and words <= lw]
        if naming and all(l.startswith("|") for l in naming):
            found.append(name)
    return found


def flatten_label_only_tables(markdown: str) -> str:
    """
    A transcribed 'table' whose body holds no data (every body cell empty, or a single filled cell) is a row of
    labels, such as the captions of a before/after photo series ('Pre | Immediate Post | 24 hrs Post'): it is
    written as one line of those labels instead of an empty table.
    """
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    out, block = [], []
    for line in (markdown or "").split("\n") + [""]:
        if line.strip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 2 and re.fullmatch(r'\|?[\s:\-|]+\|?', block[1].strip()):
            body = [c for row in block[2:] for c in cells(row) if c]
            if len(body) <= 1:
                labels = [c for c in cells(block[0]) if c] + body
                block = [" / ".join(labels)] if labels else []
        out.extend(block)
        block = []
        out.append(line)
    return "\n".join(out[:-1])


def unstack_stacked_columns(markdown: str) -> str:
    """
    Repairs a transcribed table whose second sub-column was written as extra rows below the first: rows with a
    filled first cell followed by as many rows with an empty first cell ('Focal Depth | MP Mode', '1.5 mm | ...'
    then ' | Normal Mode', ' | ...'). The second block is put back beside the first, row by row, as the columns it
    was printed in. When the second block lost its sub-header row (one row fewer), it is aligned with the data rows
    and its sub-header cell stays empty.
    """
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def unstack(table_lines):
        header, sep, body = table_lines[0], table_lines[1], table_lines[2:]
        rows = [cells(l) for l in body]
        split = next((i for i, r in enumerate(rows) if not r[0]), None)
        if split is None or split < 2 or len(rows) - split not in (split, split - 1):
            return table_lines
        top, bottom = rows[:split], rows[split:]
        if any(not r[0] for r in top) or any(r[0] for r in bottom):
            return table_lines
        if len(bottom) == split - 1:
            bottom = [[""] * len(bottom[0])] + bottom
        head = cells(header)
        extra_head = head[1:]
        new_header = "| " + " | ".join(head + extra_head) + " |"
        new_sep = "| " + " | ".join("---" for _ in head + extra_head) + " |"
        new_rows = ["| " + " | ".join(t + b[1:]) + " |" for t, b in zip(top, bottom)]
        return [new_header, new_sep] + new_rows

    out, block = [], []
    for line in (markdown or "").split("\n") + [""]:
        if line.strip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 4 and re.fullmatch(r'\|?[\s:\-|]+\|?', block[1].strip()):
            out.extend(unstack(block))
        else:
            out.extend(block)
        block = []
        out.append(line)
    return "\n".join(out[:-1])


def catalogue_rows_records(names: list, evidence_context: str) -> str:
    """
    The evidence's own table rows for the named items, each row once, written as a record: the item's name in bold,
    then one 'Column: value' line per filled cell, values exactly as the catalogue writes them. A record reads in a
    narrow chat window, where a wide catalogue table would scroll.
    """
    wanted = [{w for w in _claim_words(n) if not any(ch.isdigit() for ch in w)} for n in names]
    header, rows, seen = None, [], set()
    current_header, previous = None, None
    for raw in (evidence_context or "").split("\n"):
        line = raw.strip()
        if not line.startswith("|"):
            previous = None
            continue
        if re.fullmatch(r'\|?[\s:\-|]+\|?', line):
            current_header = previous
            continue
        previous = line
        words = set(_claim_words(line))
        if current_header and any(w and w <= words for w in wanted) and line not in seen:
            seen.add(line)
            header = header or current_header
            if current_header == header:
                rows.append(line)
    if not header or not rows:
        return ""

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    columns = cells(header)
    records = []
    for row in rows:
        values = cells(row)
        # The record is titled by the cell naming the item (the one holding all of a name's words)
        title_idx = next((i for i, v in enumerate(values)
                          if any(w and w <= set(_claim_words(v)) for w in wanted)), None)
        lines = [f"**{values[title_idx]}**" if title_idx is not None else ""]
        for i, (col, val) in enumerate(zip(columns, values)):
            if i != title_idx and val and val not in ("0", "-"):
                lines.append(f"- {col}: {val}")
        records.append("\n".join(l for l in lines if l))
    return "\n\n".join(records)


def keep_stated_lines(answer: str, evidence_context: str, min_coverage: float = 0.7) -> str:
    """
    Keeps only the answer lines the evidence states (`unproven_answer_lines`), and the lines that assert nothing.
    For an item known only from table rows, a value the row gives is stated there; a procedure, technique or dose
    written for it has no source and goes.
    """
    unproven = unproven_answer_lines(answer, evidence_context, min_coverage=min_coverage)
    counts = {}
    for line in unproven:
        counts[line] = counts.get(line, 0) + 1
    kept = []
    for line in (answer or "").split("\n"):
        if counts.get(line) and not neutral_answer_line(line):
            counts[line] -= 1
            continue
        # A line introducing a list ('berikut protokol lengkapnya:') is read as a claim of its own here
        if line.strip().endswith(":") and not neutral_answer_line(line) and unproven_answer_lines(
                line.strip().rstrip(":"), evidence_context, min_coverage=min_coverage):
            continue
        kept.append(line)
    return "\n".join(kept)


def unproven_answer_lines(answer: str, evidence_context: str, min_coverage: float = 0.8) -> list:
    """
    The answer lines the evidence does not state verbatim. A line is proven when one single evidence line or
    table row (read with its document title, section and headings) holds every number of the line and at least
    `min_coverage` of its words together with the words of the item it is written under (the nearest answer
    heading, bold item or introducing line). Values are thus proven for their own item, never from a row about
    another one. Headings and item names must be found the same way, so no invented product passes. Lines that
    only introduce a list (ending in ':', no number) are not claims. An empty result means every line is proven;
    anything paraphrased, translated or combined from several rows is returned, for the full verification.
    """
    units = _evidence_word_units(evidence_context)
    vocabulary = set().union(*units) if units else set()

    def stated(words: list, numbers: list) -> bool:
        # Every word the evidence uses anywhere (names, values, terms) must be in the one line or row: a single
        # differing word ('Pigmentation' vs 'Acne') is what tells two items apart. Only the answer's own
        # wording, absent from the evidence altogether, is tolerated, and only as a small share of the line.
        known = [w for w in words if w in vocabulary]
        if any(n not in vocabulary for n in numbers) or len(words) - len(known) > (1 - min_coverage) * len(words):
            return False
        return any(all(w in u for w in known) for u in units)

    # The item a line is written under and, within it, the line introducing the current list: a value is proven
    # with both, so 'Harga:' under '### Product A' never lets a price be proven from Product B's row
    unproven, item_words, intro_words = [], [], []
    for line in (answer or "").split("\n"):
        text_line = line.strip()
        if not text_line or re.fullmatch(r'\|?[\s:\-|]+\|?', text_line):
            continue
        words = _claim_words(text_line)
        if not words or neutral_answer_line(text_line):
            continue
        numbers = [w for w in words if any(ch.isdigit() for ch in w)]
        is_item = bool(_HEADING_LINE_RE.match(text_line) or _ITEM_HEADER_RE.match(text_line)
                       or re.match(r'^#\s+\S', text_line))
        if is_item:
            if not stated(words, numbers):
                unproven.append(line)
            item_words, intro_words = words, []
            continue
        if text_line.endswith(":") and not numbers:
            intro_words = words
            continue
        target = list(dict.fromkeys(item_words + intro_words + words))
        if not stated(target, numbers):
            unproven.append(line)
    return unproven


def claim_supported_for_subject(claim: str, subject: str, evidence_text: str, min_coverage: float = 0.8,
                                units: list = None) -> bool:
    """
    True unless the evidence shows the claim only apart from the subject. Units are the retrieved chunks
    (each with its heading path) when given, else the evidence's lines and table rows. When no unit names
    the subject at all (a paraphrased or unknown subject), attribution cannot be judged and the claim stands.
    """
    claim_w, subject_w = _claim_words(claim), _claim_words(subject)
    if not claim_w or not subject_w:
        return True
    unit_words = [set(_claim_words(u)) for u in (units or evidence_units(evidence_text)) if u]
    naming_subject = [w for w in unit_words if _word_coverage(subject_w, w) >= min_coverage]
    if not naming_subject:
        return True
    return any(_word_coverage(claim_w, w) >= min_coverage for w in naming_subject)


def blank_claim_cells(row: str, claim: str) -> str:
    """
    A table row with an unsupported claim keeps its other cells: only the cells holding the claim become '-'.
    Returns '' when the line is not a table row, no cell holds the claim, or nothing else would be left.
    """
    stripped = row.strip()
    if not stripped.startswith("|"):
        return ""
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    claim_w = _claim_words(claim)
    if not claim_w or len(cells) < 2:
        return ""
    hit = [i for i, c in enumerate(cells) if _word_coverage(claim_w, set(_claim_words(c))) >= 0.8]
    # The first cell names the row; blanking it would leave values without their item
    if not hit or 0 in hit or len(hit) >= len(cells) - 1:
        return ""
    for i in hit:
        cells[i] = "-"
    return "| " + " | ".join(cells) + " |"


_DANGLING_END_RE = re.compile(
    r"(?:\b(?:adalah|ialah|yaitu|yakni|sebesar|seharga|senilai|sekitar|sebanyak|selama|berupa|untuk|dengan|dan|atau"
    r"|is|are|of)|[:=])\s*[.,;:]?\s*\**\s*$",
    re.IGNORECASE,
)


# A word, a space, then punctuation: the mark of words cut out of the middle of a sentence
_CUT_GAP_RE = re.compile(r"\w\s+[,.;:](?=\s|$)")


def safe_line_rewrite(original: str, rewrite: str, claim: str) -> str:
    """
    A verifier's rewrite of an answer line with an unsupported claim cut out, accepted only when it is a cut
    and nothing else: the claim is gone, almost every word comes from the original line (a couple of joining
    words may change), and enough of the line is left to say something. Returns '' when not acceptable.
    """
    rewrite = (rewrite or "").strip()
    if not rewrite or len(re.sub(r"[\W_]", "", rewrite)) < 20:
        return ""
    # A cut that leaves the sentence waiting for its value ('Harga untuk X adalah .') says nothing: drop the line
    if _DANGLING_END_RE.search(rewrite):
        return ""
    # Nor one that leaves the gap inside the sentence ('direkomendasikan untuk usia , karena ...')
    if len(_CUT_GAP_RE.findall(rewrite)) > len(_CUT_GAP_RE.findall(original)):
        return ""
    if not claim_absent_from_evidence(claim, rewrite):
        return ""
    original_words = set(_claim_words(original))
    new_words = [w for w in _claim_words(rewrite) if w not in original_words]
    if len(new_words) > 2:
        return ""
    # Keep the line's own list/indent prefix
    prefix = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?", original).group(0)
    body = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?", "", rewrite)
    return prefix + body


_ID_PREFIXES = ("meng", "meny", "mem", "men", "me", "peng", "peny", "pem", "pen", "per", "pe", "ber", "be", "ter", "di", "ke", "se")
_ID_SUFFIXES = ("nya", "kan", "an", "i")


def _indonesian_roots(word: str) -> set:
    """
    The possible roots of an Indonesian word with its affixes taken off ('pemberian' and 'berikan' both give
    'beri'). Only roots of four letters or more are kept, so short fragments do not make unrelated words match.
    """
    if not word.isalpha() or len(word) < 5:
        return set()
    stems = {word}
    for suffix in _ID_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stems.add(word[: -len(suffix)])
    roots = set(stems)
    for stem in stems:
        for prefix in _ID_PREFIXES:
            if stem.startswith(prefix):
                if len(stem) - len(prefix) >= 4:
                    roots.add(stem[len(prefix):])
                break  # the longest prefix only ('pem', not also 'pe')
    return {r for r in roots if len(r) >= 4}


def claim_absent_from_evidence(claim: str, evidence_text: str, min_coverage: float = 0.8) -> bool:
    """
    True when a quoted claim (product name, number, short phrase) is not in the evidence: fewer than
    `min_coverage` of its content words occur there. Word-level coverage tolerates word order and light
    rewording, so evidence-backed lines flagged by mistake are kept.
    """
    words = _claim_words(claim)
    if not words:
        return False
    evidence_words = set(_claim_words(evidence_text))
    evidence_roots = set().union(*(_indonesian_roots(w) for w in evidence_words)) if evidence_words else set()
    # A word the evidence writes with another Indonesian affix ('pemberian' for 'berikan') counts as present
    words = [w if w in evidence_words or not (_indonesian_roots(w) & evidence_roots) else next(iter(evidence_words))
             for w in words]
    # A spelling variant one letter apart ('tato' / 'tatto', 'fungsionam' / 'fungctionam') is the same word;
    # numbers and short words must match exactly.
    def _variant(w):
        if w in evidence_words or len(w) < 4 or any(ch.isdigit() for ch in w):
            return w
        for e in evidence_words:
            if e[0] != w[0] or abs(len(e) - len(w)) > 1:
                continue
            # Four-letter words only by a doubled / dropped letter ('tato' / 'tatto'), never a swapped one
            if len(w) == 4 and len(e) == len(w):
                continue
            if _edit_distance_le1(w, e):
                return e
        return w
    words = [_variant(w) for w in words]
    if len(words) > 6:
        # A whole sentence quoted as the claim carries the answer's own wording ('adalah', a paraphrased label):
        # its numbers must be in the evidence exactly, its other words only for the most part
        numbers = [w for w in words if any(ch.isdigit() for ch in w)]
        if any(n not in evidence_words for n in numbers):
            return True
        others = [w for w in words if w not in numbers]
        return bool(others) and sum(1 for w in others if w in evidence_words) / len(others) < 0.6
    present = sum(1 for w in words if w in evidence_words)
    return present / len(words) < min_coverage


_ITEM_HEADER_RE = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+|#{2,6}\s+)?\*\*([^*]{3,120})\*\*\s*$')
_LABELED_LINE_RE = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)?\*\*([^*]{1,60})\*\*\s*:\s*(.*)$')
_HEADING_LINE_RE = re.compile(r'^\s*#{2,6}\s+(.+?)\s*$')


def _word_coverage(words: list, haystack_words: set) -> float:
    return sum(1 for w in words if w in haystack_words) / len(words) if words else 0.0


def ground_item_attributes(answer: str, chunk_texts: list, min_coverage: float = 0.8) -> str:
    """
    Removes answer lines that attach an attribute to an item when the evidence states that attribute
    only for other items (a facial listed with the indications and steps of the facial next to it).

    The answer is read as item blocks: an item header is a bold-only line or heading whose name occurs
    in the evidence. For every labeled line under an item ('**Indikasi**: ...', or a label followed by
    a sub-list), the chunks containing its value are found. The line is kept when one of them also
    names the item, and removed when only chunks about other items contain it. A value found in no
    chunk (paraphrase, translation of an English source) is left alone: this check only acts on values
    copied from the evidence, so a correct translated answer is never cut.
    """
    if not answer or not chunk_texts:
        return answer
    texts = [c for c in chunk_texts if c]
    if not texts:
        return answer
    chunk_words = [set(_claim_words(c)) for c in texts]
    chunk_phrases = [" " + " ".join(_claim_words(c)) + " " for c in texts]

    def _phrase(words: list) -> str:
        return " " + " ".join(words) + " "

    lines = answer.split("\n")
    indent = lambda s: len(s) - len(s.lstrip(" \t"))
    flagged = []
    current_item = None
    i = 0
    while i < len(lines):
        line = lines[i]
        header = _ITEM_HEADER_RE.match(line) or (_HEADING_LINE_RE.match(line) if not _LABELED_LINE_RE.match(line) else None)
        if header:
            name_words = _claim_words(header.group(1))
            # Only names the evidence itself writes (as a phrase) are items; titles the model wrote are not
            current_item = _phrase(name_words) if name_words and any(_phrase(name_words) in p for p in chunk_phrases) else None
            i += 1
            continue

        labeled = _LABELED_LINE_RE.match(line)
        if labeled and current_item:
            value = labeled.group(2).strip()
            j = i + 1
            if not value:
                # Label followed by its values as a nested list
                nested = []
                while j < len(lines) and lines[j].strip() and indent(lines[j]) > indent(line) and not _LABELED_LINE_RE.match(lines[j]):
                    nested.append(lines[j])
                    j += 1
                value = " ".join(nested)
            value_words = _claim_words(value)
            if len(value_words) >= 2:
                holders = [n for n, w in enumerate(chunk_words) if _word_coverage(value_words, w) >= min_coverage]
                if holders and not any(current_item in chunk_phrases[n] for n in holders):
                    flagged.append(i + 1)
        i += 1

    return remove_answer_lines(answer, flagged) if flagged else answer


def substantive_length(markdown_text: str) -> int:
    """Characters of actual content, excluding headings, image tags and markup."""
    body = re.sub(r'^\s*#{1,6}\s+.*$', '', markdown_text or "", flags=re.M)
    body = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', body)
    return len(re.sub(r'[\s*_#>|\-]+', ' ', body).strip())


def align_discontinue_answer(answer: str) -> str:
    """
    Deprecated: superseded by ground_status_claims(), which needs the evidence text.
    """
    return answer


def escape_raw_comparison_operators(text: str) -> str:
    """
    Escapes unescaped comparison operators like '< 4 cm' or 'lesi < 4' or '(> 10 cm)'
    to prevent markdown and HTML parsers from mistaking them for unclosed HTML tags.
    """
    if not text or ("<" not in text and ">" not in text):
        return text

    # Pattern for '<': '<' followed by space or number or comparison value (e.g. '< 4 cm', '<4 cm', '<= 5', '< 10%')
    # but NOT valid html tags like <br>, <br/>, <sub>, <sup>, <b>, <i>, <strong>, etc.
    res = re.sub(
        r'<(?!\/?(?:br|sub|sup|b|i|u|strong|em|p|div|span|table|thead|tbody|tr|th|td)\b)(?=\s*\d|\s*[<>=])',
        '&lt;',
        text,
        flags=re.IGNORECASE
    )
    # Also handle '(< 4' or isolated ' < '
    res = re.sub(r'\(\s*<\s*(?=\d)', '(&lt; ', res)
    res = re.sub(r'(?<=\s)<(?=\s)', '&lt;', res)

    # Pattern for '>': comparison like '> 10 cm' or '(> 10 cm)' or isolated ' > '
    res = re.sub(r'(?<![a-zA-Z0-9/"\'-])>(?=\s*\d|\s*[<>=])', '&gt;', res)
    res = re.sub(r'\(\s*>\s*(?=\d)', '(&gt; ', res)
    res = re.sub(r'(?<=\s)>(?=\s)', '&gt;', res)

    return res


def clean_nontable_br_tags(markdown_text: str) -> str:
    """
    Replaces raw <br> or <br/> tags in general markdown paragraphs (lines NOT in tables)
    with clean markdown line breaks (\\n) so raw HTML does not leak into UI.
    """
    if not markdown_text or ("<br" not in markdown_text and "<BR" not in markdown_text):
        return markdown_text

    lines = markdown_text.split("\n")
    processed = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Table row: preserve table breaks
            processed.append(line)
        else:
            # Non-table line: convert <br> to newline
            clean_l = re.sub(r'<br\s*/?>', '\n', line, flags=re.IGNORECASE)
            processed.append(clean_l)
    return "\n".join(processed)


def unescape_comparison_entities(text: str) -> str:
    """
    Reverses escape_raw_comparison_operators for text a model reads ('lesi &lt; 4 cm' -> 'lesi < 4 cm').
    Stored chunks are escaped for markdown rendering; a model reading '&lt;' tends to drop the threshold.
    Answers are escaped again by normalize_markdown_text before display.
    """
    if not text or "&" not in text:
        return text
    return text.replace("&lt;", "<").replace("&gt;", ">")


# "None" is left alone: in a document it can be a real value ("Side effects: None").
_NULL_TOKEN = r"(?:null|undefined|nan)"
_NULL_FIELD_LINE_RE = re.compile(
    rf"^[ \t]*(?:[-*+][ \t]+)?\*\*[^*\n]+\*\*[ \t]*:?[ \t]*:?[ \t]*[\"'`]?{_NULL_TOKEN}[\"'`]?[ \t]*\.?[ \t]*$\n?",
    re.IGNORECASE | re.MULTILINE,
)
_NULL_ITEM_VALUE_RE = re.compile(
    rf"^([ \t]*(?:[-*+][ \t]+)?[^:\n|]*?\S)[ \t]*:[ \t]*[\"'`]?{_NULL_TOKEN}[\"'`]?[ \t]*\.?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_NULL_TABLE_CELL_RE = re.compile(rf"(?<=\|)[ \t]*{_NULL_TOKEN}[ \t]*(?=\|)", re.IGNORECASE)


def drop_null_placeholders(text: str) -> str:
    """Removes empty-value placeholders ("null") a model writes for fields not printed in the source:
    a labelled field holding only such a value is dropped, an item's ": null" is cut, a table cell is emptied."""
    if not text:
        return text
    t = _NULL_FIELD_LINE_RE.sub("", text)
    t = _NULL_ITEM_VALUE_RE.sub(r"\1", t)
    return _NULL_TABLE_CELL_RE.sub(" ", t)


def normalize_markdown_text(text: str) -> str:
    """
    Master pipeline: applies PUA normalization, table break cleanup,
    non-table break cleanup, comparison operator escaping, and discontinue phrase normalization.
    """
    if not text:
        return ""
    t = normalize_pua_glyphs(text)
    t = clean_markdown_table_breaks(t)
    t = clean_nontable_br_tags(t)
    t = escape_raw_comparison_operators(t)
    t = normalize_discontinue_phrases(t)
    t = drop_null_placeholders(t)
    return t
