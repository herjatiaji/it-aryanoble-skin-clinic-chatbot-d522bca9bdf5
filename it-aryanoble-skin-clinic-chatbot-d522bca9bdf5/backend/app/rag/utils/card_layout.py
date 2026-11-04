"""
Deterministic extractor for designed "card grid" PDF pages (cheatsheets, protocol cards, menus).

Typical layout handled:
    - Multiple visual columns separated by whitespace gutters.
    - Each column contains cards: optional eyebrow/category, bold title, optional subtitle,
      optional badge (e.g. "90 menit"), then either bullet items or label/value rows,
      optionally a numbered step strip whose active/inactive state is encoded by text color.

Reading such pages line-by-line across the full page width interleaves neighbouring cards.
This module rebuilds every card independently and renders it as Markdown tables so each
card stays self-contained for chunking & retrieval. Returns None when the page does not
clearly match a card grid, so callers can fall back to the generic pipeline.
"""
from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional

BULLET_CHARS = ("•", "▪", "◦", "‣", "∙", "●", "■", "►", "➤")
CHECK_SYMBOLS = "✓✔✕✖✗✘☑☒"
DURATION_RE = re.compile(r"^(.*?)\s+(\d+(?:\s*/\s*\d+)*)\s*['’′]\s*$")
BADGE_TIME_RE = re.compile(r"^\d+(?:\s*/\s*\d+)*\s*(menit|min|mins|minutes|jam|hours?)$", re.IGNORECASE)
PAGER_RE = re.compile(r"^\d+\s*/\s*\d+$")


def _luminance(color: int) -> float:
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _cell(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "&#124;")
    return t or "-"


def _is_upper_label(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and text.upper() == text


def _collect_lines(page) -> List[Dict[str, Any]]:
    lines = []
    d = page.get_text("dict")
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for l in b.get("lines", []):
            spans = [s for s in l.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in l["spans"]).replace("\u200b", "")
            if not text.strip():
                continue
            main = max(spans, key=lambda s: len(s["text"].strip()))
            font = main.get("font", "")
            x0, y0, x1, y1 = l["bbox"]
            lines.append({
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "yc": (y0 + y1) / 2.0,
                "text": text.strip(),
                "size": float(main.get("size", 0.0)),
                "bold": ("bold" in font.lower()) or bool(main.get("flags", 0) & 16),
                "italic": ("italic" in font.lower()) or ("oblique" in font.lower()) or bool(main.get("flags", 0) & 2),
                "color": int(main.get("color", 0)),
            })
    return lines


def _find_columns(body: List[Dict[str, Any]], min_gutter: float = 15.0) -> List[List[float]]:
    min_x = int(min(l["x0"] for l in body))
    max_x = int(max(l["x1"] for l in body)) + 1
    width = max_x - min_x
    if width <= 0:
        return []
    occ = [0] * (width + 1)
    for l in body:
        for x in range(int(l["x0"]) - min_x, min(int(l["x1"]) - min_x + 1, width + 1)):
            occ[x] += 1

    cols: List[List[float]] = []
    start = None
    gap = 0
    for x, v in enumerate(occ):
        if v > 0:
            if start is None:
                start = x
            elif gap >= min_gutter:
                cols.append([start, x - gap - 1])
                start = x
            gap = 0
        elif start is not None:
            gap += 1
    if start is not None:
        cols.append([start, width - gap])

    # Merge slivers (badges, icons labels) into the nearest neighbour column
    min_w = width * 0.15
    merged = True
    while merged and len(cols) > 1:
        merged = False
        for ci, c in enumerate(cols):
            if c[1] - c[0] < min_w:
                if ci == 0:
                    cols[1][0] = c[0]
                elif ci == len(cols) - 1:
                    cols[ci - 1][1] = c[1]
                else:
                    left_gap = c[0] - cols[ci - 1][1]
                    right_gap = cols[ci + 1][0] - c[1]
                    if left_gap <= right_gap:
                        cols[ci - 1][1] = c[1]
                    else:
                        cols[ci + 1][0] = c[0]
                cols.pop(ci)
                merged = True
                break
    return [[c[0] + min_x, c[1] + min_x] for c in cols]


def _group_rows(lines: List[Dict[str, Any]], tol: float = 3.5) -> List[List[Dict[str, Any]]]:
    rows: List[List[Dict[str, Any]]] = []
    for l in sorted(lines, key=lambda l: (l["yc"], l["x0"])):
        if rows and abs(l["yc"] - rows[-1][0]["yc"]) <= tol:
            rows[-1].append(l)
        else:
            rows.append([l])
    return [sorted(r, key=lambda l: l["x0"]) for r in rows]


def _parse_legend(footer_lines: List[Dict[str, Any]]) -> Dict[int, str]:
    legend: Dict[int, str] = {}
    used = set()
    ordered = sorted(footer_lines, key=lambda l: (l["y0"], l["x0"]))
    for i, l in enumerate(ordered):
        m = re.match(r"^(\d{1,2})\s+(.+)$", l["text"])
        if not m:
            continue
        label = m.group(2).strip()
        for j, o in enumerate(ordered):
            if j == i or j in used or re.match(r"^\d", o["text"]):
                continue
            if abs(o["x0"] - l["x0"]) <= 3 and 0 <= o["y0"] - l["y1"] <= 3:
                label = f"{label} {o['text'].strip()}"
                used.add(j)
                break
        legend[int(m.group(1))] = re.sub(r"\s+", " ", label).strip()
    return legend


def _new_card(col: int, y0: float, pending: Dict[str, Any], section: Optional[str]) -> Dict[str, Any]:
    card = {
        "col": col, "y0": y0, "title": "", "title_size": 0.0, "subtitle": "",
        "category": pending.pop("category", None), "badge": list(pending.pop("badge", [])),
        "notes": [], "bullets": [], "kv": [], "steps": None, "section": section,
        "last": None,
    }
    return card


def _has_content(card: Optional[Dict[str, Any]]) -> bool:
    return bool(card and (card["bullets"] or card["kv"] or card["steps"]))


def _parse_column(rows, col_idx: int, body_median: float, stats: Dict[str, int]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    card: Optional[Dict[str, Any]] = None
    pending: Dict[str, Any] = {}
    section: Optional[str] = None

    for row in rows:
        texts = [l["text"] for l in row]
        first = row[0]
        stats["total"] += len(row)

        # Numbered step strip (e.g. 1..11 with active/inactive colors)
        if len(row) >= 4 and all(re.fullmatch(r"\d{1,2}", t) for t in texts):
            if card is None:
                card = _new_card(col_idx, first["y0"], pending, section)
                cards.append(card)
            card["steps"] = [(int(l["text"]), _luminance(l["color"]) < 0.6) for l in row]
            card["last"] = "steps"
            continue

        if len(row) == 1:
            l = first
            t = l["text"]
            is_white = _luminance(l["color"]) > 0.95

            if is_white:
                if _is_upper_label(t):
                    section = t
                    card = None
                    pending = {}
                elif card is not None and not _has_content(card):
                    card["badge"].append(t)
                else:
                    pending.setdefault("badge", []).append(t)
                continue

            if t.startswith(BULLET_CHARS):
                if card is None:
                    card = _new_card(col_idx, l["y0"], pending, section)
                    cards.append(card)
                item = t.lstrip("".join(BULLET_CHARS)).strip()
                card["bullets"].append({"text": item, "x0": l["x0"]})
                card["last"] = "bullet"
                continue

            # Continuation of bullet or kv value (wrapped line)
            if card is not None and not l["bold"]:
                if card["last"] == "bullet" and card["bullets"] and l["x0"] > card["bullets"][-1]["x0"] + 3:
                    card["bullets"][-1]["text"] += " " + t
                    continue
                if card["last"] == "kv" and card["kv"] and abs(l["x0"] - card["kv"][-1]["vx0"]) <= 4:
                    card["kv"][-1]["value"] = (card["kv"][-1]["value"] + " " + t).strip()
                    continue

            if l["bold"] and _is_upper_label(t):
                pending["category"] = t
                continue

            if l["bold"]:
                if card is not None and card["title"] and not _has_content(card) and not card["subtitle"] \
                        and l["size"] < card["title_size"] - 0.5:
                    card["subtitle"] = t
                    continue
                if l["size"] >= body_median * 1.05:
                    card = _new_card(col_idx, l["y0"], pending, section)
                    card["title"] = t
                    card["title_size"] = l["size"]
                    cards.append(card)
                    continue

            if card is not None and card["title"] and not _has_content(card):
                card["notes"].append(t)
            elif card is not None:
                card["notes"].append(t)
                stats["unstructured"] += 1
            else:
                stats["unstructured"] += 1
            continue

        # Multi-line row: label / value pairs
        key_line = first
        key = key_line["text"].strip(CHECK_SYMBOLS + " :")
        if len(row) >= 5:
            # Wide rows of many cells are comparison matrices, not label/value cards
            stats["matrix_rows"] += 1
        if key in BULLET_CHARS or key in ("-", "–", "*"):
            # Bullet glyph rendered as a separate text line: treat as a bullet item
            if card is None:
                card = _new_card(col_idx, key_line["y0"], pending, section)
                cards.append(card)
            card["bullets"].append({"text": " ".join(texts[1:]), "x0": key_line["x0"]})
            card["last"] = "bullet"
            continue
        if len(key) <= 25 and sum(ch.isalpha() for ch in key) >= 2 and not key[0].isdigit():
            if card is None:
                card = _new_card(col_idx, key_line["y0"], pending, section)
                cards.append(card)
            value_lines = row[1:]
            card["kv"].append({"key": key, "value": value_lines[0]["text"], "vx0": value_lines[0]["x0"]})
            for vl in value_lines[1:]:
                vt = vl["text"]
                m = re.match(r"^([A-Za-zÀ-ÿ][\w .+/-]{0,20}?)\s{2,}(.+)$", vt)
                if m:
                    card["kv"].append({"key": m.group(1).strip(), "value": m.group(2).strip(), "vx0": value_lines[0]["x0"]})
                elif vt.rstrip().endswith(":") and len(vt) <= 25:
                    card["kv"].append({"key": vt.strip().rstrip(":"), "value": "", "vx0": value_lines[0]["x0"]})
                else:
                    card["kv"][-1]["value"] = (card["kv"][-1]["value"] + " " + vt).strip()
            card["last"] = "kv"
            continue

        if card is not None:
            card["notes"].append(" ".join(texts))
        stats["unstructured"] += len(row)

    return cards


def _render_list_section(section: Optional[str], cards: List[Dict[str, Any]]) -> str:
    has_sub = any(c["subtitle"] for c in cards)
    items = [b["text"] for c in cards for b in c["bullets"]]
    dur_hits = sum(1 for t in items if DURATION_RE.match(re.sub(r"\s+", " ", t)))
    has_dur = items and dur_hits >= max(1, int(len(items) * 0.5))

    headers = ["Kondisi / Topik"]
    if has_sub:
        headers.append("Fokus / Keterangan")
    headers.append("Item / Rekomendasi")
    if has_dur:
        headers.append("Durasi (menit)")

    rows = []
    for c in cards:
        title = c["title"] or c.get("category") or "-"
        for b in c["bullets"]:
            txt = re.sub(r"\s+", " ", b["text"]).strip()
            dur = "-"
            if has_dur:
                m = DURATION_RE.match(txt)
                if m:
                    txt, dur = m.group(1).strip(), re.sub(r"\s+", "", m.group(2))
            row = [title]
            if has_sub:
                row.append(c["subtitle"] or "-")
            row.append(txt)
            if has_dur:
                row.append(dur)
            rows.append("| " + " | ".join(_cell(v) for v in row) + " |")

    parts = []
    if section:
        parts.append(f"### {section}")
    parts.append("| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _render_kv_card(card: Dict[str, Any], legend: Dict[int, str]) -> str:
    title = card["title"] or card.get("category") or "Detail"
    rows: List[List[str]] = []
    if card.get("category") and card["category"] != title:
        rows.append(["Kategori", card["category"]])
    elif card.get("section"):
        rows.append(["Kategori", card["section"]])
    if card["subtitle"]:
        rows.append(["Keterangan", card["subtitle"]])
    if card["badge"]:
        badge = re.sub(r"\s+", " ", " ".join(card["badge"])).strip()
        rows.append(["Durasi" if BADGE_TIME_RE.match(badge) else "Label", badge])
    for n in card["notes"]:
        rows.append(["Catatan", n])
    if card["steps"]:
        def _name(num: int) -> str:
            return f"{num}. {legend[num]}" if num in legend else str(num)
        done = [_name(n) for n, active in card["steps"] if active]
        skipped = [_name(n) for n, active in card["steps"] if not active]
        rows.append(["Tahapan dilakukan", ", ".join(done) if done else "-"])
        rows.append(["Tahapan tidak dilakukan", ", ".join(skipped) if skipped else "-"])
    for kv in card["kv"]:
        key = kv["key"]
        if key.strip().upper() == "KI":
            key = "KI (Kontraindikasi)"
        rows.append([key, kv["value"]])
    for b in card["bullets"]:
        rows.append(["Poin", b["text"]])

    table = "| Parameter | Detail |\n| --- | --- |\n" + "\n".join(f"| {_cell(k)} | {_cell(v)} |" for k, v in rows)
    return f"### {title}\n\n{table}"


def extract_card_grid_markdown(page, slide_title: str = "") -> Optional[str]:
    """Return Markdown for a card-grid page, or None if the page is not a confident match."""
    try:
        page_w = page.rect.width
        page_h = page.rect.height
        lines = _collect_lines(page)
        if len(lines) < 12:
            return None

        header_cut = page_h * 0.14
        footer_cut = page_h - 45
        header = [l for l in lines if l["y1"] <= header_cut]
        footer = [l for l in lines if l["y0"] > footer_cut]
        body = [l for l in lines if l["y1"] > header_cut and l["y0"] <= footer_cut]
        if len(body) < 10:
            return None

        columns = _find_columns(body)
        if not columns:
            return None

        body_median = statistics.median(l["size"] for l in body)
        legend = _parse_legend(footer)
        stats = {"total": 0, "unstructured": 0, "matrix_rows": 0}
        all_cards: List[Dict[str, Any]] = []
        for ci, (cx0, cx1) in enumerate(columns):
            col_lines = [l for l in body if cx0 - 2 <= (l["x0"] + l["x1"]) / 2.0 <= cx1 + 2]
            if not col_lines:
                continue
            all_cards.extend(_parse_column(_group_rows(col_lines), ci, body_median, stats))

        if stats["matrix_rows"] >= 3:
            return None
        valid = [c for c in all_cards if c["title"] and (len(c["bullets"]) >= 1 or len(c["kv"]) >= 2)]
        if not valid or len(valid) != len([c for c in all_cards if c["bullets"] or c["kv"]]):
            return None
        multi_card = len(valid) >= 2 and len({c["col"] for c in valid}) >= 2
        single = valid[0] if len(valid) == 1 else None
        single_strong = bool(single) and (
            (single["steps"] and len(single["kv"]) >= 2)
            or (len(single["kv"]) >= 4 and not single["bullets"] and not single["notes"])
        )
        if not (multi_card or single_strong):
            return None
        if stats["total"] == 0 or stats["unstructured"] / stats["total"] > 0.2:
            return None

        # Assemble units: list-style cards grouped by section, kv-style cards individually
        units = []
        list_groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for c in valid:
            if c["bullets"] and not c["kv"] and not c["steps"]:
                key = (c["col"], c["section"])
                if key not in list_groups:
                    list_groups[key] = []
                    units.append(("list", key, c["y0"], c["col"]))
                list_groups[key].append(c)
            else:
                units.append(("kv", c, c["y0"], c["col"]))

        if all(u[0] == "kv" for u in units):
            units.sort(key=lambda u: (round(u[2] / 30.0), u[3]))
        else:
            units.sort(key=lambda u: (u[3], u[2]))

        parts = []
        norm_title = re.sub(r"\s+", " ", slide_title or "").strip().lower()
        for l in sorted(header, key=lambda l: (l["y0"], l["x0"])):
            t = l["text"].strip()
            if PAGER_RE.match(t) or re.sub(r"\s+", " ", t).lower() == norm_title:
                continue
            parts.append(t)
        for u in units:
            if u[0] == "list":
                parts.append(_render_list_section(u[1][1], list_groups[u[1]]))
            else:
                parts.append(_render_kv_card(u[1], legend))
        return "\n\n".join(parts) + "\n\n"
    except Exception:
        return None
