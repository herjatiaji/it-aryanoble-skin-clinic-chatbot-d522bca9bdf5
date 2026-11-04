"""
How much of a source text is present in a derived text (a transcription, a summary, an index): the shared
measure behind the parser's completeness retry and the ingest quality check, for any document format.
"""
import re
from typing import List, Optional


def content_words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 3]


def text_coverage(source: str, derived: str, min_words: int = 20) -> Optional[float]:
    """Share of the source's words present in the derived text; None when the source has too little text."""
    words = content_words(source)
    if len(words) < min_words:
        return None
    present = set(content_words(derived))
    return sum(1 for w in words if w in present) / len(words)


def missing_lines(source: str, derived: str, min_words: int = 20) -> List[str]:
    """
    Self-contained source lines (3+ words, not a column fragment starting with punctuation) whose words are
    mostly absent from the derived text. Fragments and short labels say nothing on their own.
    """
    if not source or len(content_words(source)) < min_words:
        return []
    present = set(content_words(derived))
    missing = []
    for line in dict.fromkeys(l.strip() for l in source.splitlines()):
        words = content_words(line)
        if not line or not line[0].isalnum():
            continue
        if len(words) >= 3 and sum(1 for w in words if w in present) / len(words) < 0.5:
            missing.append(line)
    return missing
