"""
Structured page content from the vision parser, and its Markdown rendering.

The vision model returns a page as typed blocks (heading, paragraph, list, table, key_values) under a strict
JSON schema; the Markdown is rendered here, by code. Tables therefore always have one header and rows of the
same width, empty fields are simply absent, and no placeholder or broken row can reach the knowledge base,
whatever the document is about.
"""
import re
from typing import Any, Dict, List

BLOCK_TYPES = ["heading", "paragraph", "list", "table", "key_values"]

# OpenAI structured-outputs schema (strict: every property required, no extra properties). Fields a block
# type does not use are returned empty.
PAGE_BLOCKS_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "description": "The page's printed content in reading order.",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "level", "text", "items", "header", "rows", "pairs"],
        "properties": {
            "type": {"type": "string", "enum": BLOCK_TYPES},
            "level": {"type": "integer", "description": "Heading level 1-4 (headings only; 0 otherwise)."},
            "text": {"type": "string", "description": "Heading or paragraph text; empty for other types."},
            "items": {"type": "array", "items": {"type": "string"}, "description": "List entries, in printed order."},
            "header": {"type": "array", "items": {"type": "string"}, "description": "Table column labels as printed."},
            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                     "description": "Table rows, one cell per column; several items in one cell are separated by '; '."},
            "pairs": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["label", "value"],
                "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
            }, "description": "Printed 'label: value' fields, label exactly as printed."},
        },
    },
}

_PLACEHOLDER_RE = re.compile(r"^\s*(?:null|none|undefined|nan|n/a|-|—|\.\.\.)?\s*$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[•●▪◦·‣⁃*-]\s+")
_INLINE_BULLET_RE = re.compile(r"\s+[•●▪]\s+")


def _clean(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if _PLACEHOLDER_RE.match(text) else text


def _cell(value: Any) -> str:
    # A cell stays on one line; several items in it are kept apart with <br>
    parts = [p for p in (_clean(x) for x in re.split(r"\s*(?:;|\n|<br\s*/?>)\s*", str(value or ""))) if p]
    return "<br>".join(parts).replace("|", "&#124;")


def _render_text(text: Any) -> str:
    """Paragraph text; lines printed as bullets become Markdown list entries."""
    raw = str(text or "")
    # Several bullets run together on one line ('a • b • c') are separate entries
    raw = _INLINE_BULLET_RE.sub("\n• ", raw)
    lines = [l.strip() for l in raw.splitlines() if _clean(l)]
    if not any(_BULLET_RE.match(l) for l in lines):
        return re.sub(r"\s+", " ", " ".join(lines)).strip()
    return "\n".join(_BULLET_RE.sub("- ", l) if _BULLET_RE.match(l) else re.sub(r"\s+", " ", l) for l in lines)


def _render_table(header: List[Any], rows: List[Any]) -> str:
    header = [_cell(h) for h in header or []]
    rows = [[_cell(c) for c in (r if isinstance(r, list) else [r])] for r in rows or []]
    rows = [r for r in rows if any(r)]
    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    if width == 0 or not rows:
        return ""
    header = (header + [""] * width)[:width]
    if not any(header):
        # A table printed without column labels takes its first row as header
        header, rows = (rows[0] + [""] * width)[:width], rows[1:]
        if not rows:
            return " | ".join(c for c in header if c)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join((r + [""] * width)[:width]) + " |" for r in rows]
    return "\n".join(lines)


def _render_pairs(pairs: List[Any]) -> str:
    lines = []
    for pair in pairs or []:
        if isinstance(pair, dict):
            label, value = _clean(pair.get("label")), _clean(pair.get("value"))
        elif isinstance(pair, (list, tuple)) and len(pair) >= 2:
            label, value = _clean(pair[0]), _clean("; ".join(str(x) for x in pair[1:]))
        else:
            continue
        if label and value:
            lines.append(f"- **{label}**: {value}")
        elif value:
            lines.append(f"- {value}")
        # A label with no value is an empty field: nothing to write
    return "\n".join(lines)


def blocks_to_markdown(blocks: List[Dict[str, Any]]) -> str:
    """
    Renders typed page blocks as Markdown. Every filled field is rendered whatever type the block declares
    (a model may put a label/value list in 'rows'): content is never dropped, only empty fields are.
    """
    out: List[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        parts: List[str] = []
        text = block.get("text")
        if kind == "heading" and _clean(text):
            level = min(max(int(block.get("level") or 2), 1), 4)
            parts.append(f"{'#' * level} {_clean(text)}")
        elif _clean(text):
            parts.append(_render_text(text))
        items = [_clean(i) for i in block.get("items") or []]
        if any(items):
            parts.append("\n".join(f"- {i}" for i in items if i))
        if block.get("pairs"):
            parts.append(_render_pairs(block.get("pairs")))
        rows = block.get("rows") or []
        if rows or any(_clean(h) for h in block.get("header") or []):
            two_column = bool(rows) and all(isinstance(r, list) and len(r) == 2 for r in rows)
            if kind == "key_values" and two_column and not any(_clean(h) for h in block.get("header") or []):
                parts.append(_render_pairs(rows))
            else:
                parts.append(_render_table(block.get("header") or [], rows))
        rendered = "\n\n".join(p for p in parts if p)
        if rendered:
            out.append(rendered)
    return "\n\n".join(out).strip()
