"""
Search context for indexed chunks (contextual retrieval).

A chunk is often a bare table or slide fragment, in English, while doctors ask in Indonesian: 'Burns and
scabbing | ... metcor 8 mg' never meets 'komplikasi luka bakar ... obat oral' by words, and only weakly by meaning.
At ingestion each chunk gets one Indonesian sentence saying what it is about, written into its retrieval text
under 'Konteks:' so that both the word index and the embedding carry it. The sentence is for finding the chunk
only: it is removed again before any answering or checking model reads the chunk, so a generated sentence is
never evidence.
"""
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

_CONTEXT_FIELD_RE = re.compile(r"\| Konteks: [^|]*")
_BATCH = 10
_BODY_CHARS = 700


def strip_search_context(retrieval_text: str) -> str:
    """The chunk as its document writes it, without the search sentence added at ingestion."""
    return _CONTEXT_FIELD_RE.sub("", retrieval_text or "")


def _passage(retrieval_text: str) -> str:
    title = re.search(r"Title:\s*([^|\n]+)", retrieval_text)
    section = re.search(r"Section:\s*([^|\n]+)", retrieval_text)
    body = re.split(r"\|\s*Content:\s*", retrieval_text, maxsplit=1)[-1]
    body = re.sub(r"\s+", " ", body).strip()[:_BODY_CHARS]
    head = " / ".join(m.group(1).strip() for m in (title, section) if m)
    return f"{head}: {body}" if head else body


def _with_context(retrieval_text: str, sentence: str) -> str:
    sentence = re.sub(r"[|\n\r]+", " ", sentence or "").strip()
    if not sentence:
        return retrieval_text
    field = f"| Konteks: {sentence} "
    for anchor in ("| Title:", "| Section:", "| Content:"):
        if anchor in retrieval_text:
            return retrieval_text.replace(anchor, field + anchor, 1)
    return f"{retrieval_text} {field}"


def add_search_context(chunks: List[Dict[str, Any]], llm: Optional[Any] = None) -> int:
    """
    Writes a search sentence into each chunk's retrieval_text, ten chunks per model call. Returns how many chunks
    got one; any failure leaves the affected chunks as they were.
    """
    if not chunks:
        return 0
    if llm is None:
        from app.rag.services.factory import AdapterFactory
        llm = AdapterFactory.get_llm_adapter()
    done = 0
    for start in range(0, len(chunks), _BATCH):
        batch = chunks[start:start + _BATCH]
        listing = "\n".join(f"[{i}] {_passage(c['retrieval_text'])}" for i, c in enumerate(batch, 1))
        prompt = (
            "Untuk setiap potongan dokumen klinik berikut, tulis SATU kalimat bahasa Indonesia (paling banyak 35 kata) "
            "yang menjelaskan isi potongan itu untuk keperluan pencarian: sebutkan item (tindakan, alat, produk) dan "
            "topiknya, dan sertakan padanan bahasa Indonesia untuk istilah bahasa Inggris yang penting (misalnya "
            "'burns' = luka bakar, 'side effects' = efek samping). Jangan menulis angka, dosis, harga, atau fakta yang "
            "tidak tertulis di potongan.\n"
            f"Keluarkan hanya JSON array berisi {len(batch)} string, sesuai urutan nomor.\n\n{listing}"
        )
        try:
            raw = llm.generate(prompt) or ""
            match = re.search(r"\[[\s\S]*\]", raw)
            sentences = json.loads(match.group(0)) if match else []
        except Exception as e:
            logger.warning(f"[Search Context] batch {start // _BATCH + 1} skipped: {e}")
            continue
        if not isinstance(sentences, list) or len(sentences) != len(batch):
            logger.warning(f"[Search Context] batch {start // _BATCH + 1}: {len(sentences) if isinstance(sentences, list) else 0} sentences for {len(batch)} chunks; skipped")
            continue
        for chunk, sentence in zip(batch, sentences):
            if isinstance(sentence, str) and sentence.strip():
                chunk["retrieval_text"] = _with_context(chunk["retrieval_text"], sentence)
                done += 1
    logger.info(f"[Search Context] {done}/{len(chunks)} chunks given a search sentence")
    return done
