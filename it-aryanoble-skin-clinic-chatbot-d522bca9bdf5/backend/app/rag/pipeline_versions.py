"""
Versions of the processing stages a published document went through. The chunker stamps every chunk it
makes with its version; when a stage changes in a way that changes its output, its version goes up, and
documents processed by an older version are brought up to date (app.rag.services.reprocess) instead of
keeping what the old code produced.
"""
from typing import Any, List

# 1: heading-split chunking. 2: block-based chunking (no heading-only or duplicate chunks, tables by rows).
# 3: a cover-page H1 names the whole document even when later pages have their own H1.
# 4: image-to-item matching ignores words shared by most of the document's image labels (no brand stop words).
# 5: an item is typed treatment or product by the document's type, then by product-form words in its name.
CHUNKER_VERSION = 5

# Vision parser for scanned/flattened PDFs. 1: Markdown per page (current). Typed blocks under a strict schema
# (app.rag.utils.vision_blocks) are prepared for version 2 but not active: they lost descriptive page titles that
# retrieval of catalog pages relies on. A re-parse costs vision tokens per page, so outdated documents are
# listed for the admin (GET /knowledge/maintenance/pipeline-status) rather than re-parsed automatically.
PARSER_VERSION = 1


def chunker_version_of(chunks: List[Any]) -> int:
    """The oldest chunker version among a document's chunks (1 for chunks made before versions were stamped)."""
    versions = [int(((c.get("metadata") or {}).get("chunker_version")) or 1) for c in chunks or [] if isinstance(c, dict)]
    return min(versions) if versions else 1
