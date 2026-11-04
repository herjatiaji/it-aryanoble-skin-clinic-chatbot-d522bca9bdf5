"""
Ingest quality check, the same for every document whatever its format or subject:

1. Coverage   - how much of the original file's own text (PDF text layer, DOCX, PPTX, XLSX, TXT) reached the
                index the chatbot retrieves from.
2. Structure  - defects in the indexed chunks: placeholder values, tables whose rows disagree on column
                count, chunks holding only headings, empty, oversized or duplicated chunks.
3. Probes     - questions generated from the original text, each with the passage that answers it, asked
                through the same retrieval and generation the doctors use; an answer counts only when it
                carries the facts of that passage.

The report is stored on the version (knowledge_version.parse_report["quality"]) and shown with the
readiness gate, so a weak document is visible before and after it is published.
"""
import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import text

from app.rag.utils.source_coverage import content_words, missing_lines, text_coverage

QUALITY_CHECK_VERSION = 1
COVERAGE_MIN = 0.85
PROBE_PASS_MIN = 0.8
MAX_PROBES = 12
MAX_CHUNK_CHARS = 6000

_NULL_VALUE_RE = re.compile(r"(?:\*\*[^*\n]+\*\*|^[ \t]*[-*][^:\n]{1,60})\s*:\s*(?:null|undefined|nan)\s*$|\|\s*(?:null|undefined)\s*\|",
                            re.IGNORECASE | re.MULTILINE)
_CONTENT_RE = re.compile(r"\bContent:\s*", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")


# ---------------------------------------------------------------------------------------------------------
# Source text
# ---------------------------------------------------------------------------------------------------------

def extract_source_sections(path: str) -> List[str]:
    """The original file's own text, one entry per page, slide, sheet or document; empty for image files."""
    ext = os.path.splitext(path)[1].lower()
    sections: List[str] = []
    try:
        if ext == ".pdf":
            import fitz
            with fitz.open(path) as doc:
                sections = [page.get_text() or "" for page in doc]
        elif ext == ".docx":
            import docx
            d = docx.Document(path)
            parts = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            sections = ["\n".join(parts)]
        elif ext == ".pptx":
            from pptx import Presentation
            for slide in Presentation(path).slides:
                parts = []
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                        parts.append(shape.text_frame.text)
                    if getattr(shape, "has_table", False) and shape.has_table:
                        for row in shape.table.rows:
                            parts.append(" | ".join(c.text for c in row.cells))
                sections.append("\n".join(parts))
        elif ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                rows = [" | ".join("" if v is None else str(v) for v in row) for row in ws.iter_rows(values_only=True)]
                sections.append("\n".join(r for r in rows if r.strip(" |")))
            wb.close()
        elif ext == ".csv":
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                sections = [fh.read()]
        elif ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                sections = [fh.read()]
    except Exception as e:
        logger.warning(f"[QUALITY] Could not read source text of '{path}': {e}")
    return sections


QUALITY_SRC_DIR = os.path.join(tempfile.gettempdir(), "quality_src")


def _source_file(knowledge_id: str, engine) -> Optional[str]:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT original_path, file_name FROM knowledge WHERE id = :k"), {"k": knowledge_id}).fetchone()
    if row and row[0] and os.path.exists(row[0]):
        return row[0]
    from app.services.storage import download_original_document
    return download_original_document(knowledge_id, QUALITY_SRC_DIR, (row[1] if row else "") or "")


# ---------------------------------------------------------------------------------------------------------
# Indexed chunks
# ---------------------------------------------------------------------------------------------------------

def chunk_content(retrieval_text: str) -> str:
    """The chunk's own text, without the metadata header the index prepends."""
    m = _CONTENT_RE.search(retrieval_text or "")
    return (retrieval_text[m.end():] if m else retrieval_text or "").strip()


def lint_chunks(chunks: List[str]) -> Dict[str, Any]:
    """Structural defects in indexed chunk texts, with a few examples of each."""
    issues: Dict[str, List[str]] = {"placeholder_value": [], "table_column_mismatch": [], "heading_only": [],
                                    "empty": [], "oversized": [], "duplicate": []}
    seen = set()
    for c in chunks:
        body = c.strip()
        if len(re.sub(r"[#*|\-\s]", "", body)) < 3:
            issues["empty"].append(body[:80])
            continue
        if len(body) > MAX_CHUNK_CHARS:
            issues["oversized"].append(f"{len(body)} chars: {body[:80]}")
        key = re.sub(r"\s+", " ", body.lower())
        if key in seen:
            issues["duplicate"].append(body[:80])
        seen.add(key)
        m = _NULL_VALUE_RE.search(body)
        if m:
            issues["placeholder_value"].append(m.group(0).strip()[:80])
        lines = [l for l in body.splitlines() if l.strip()]
        if lines and all(l.lstrip().startswith("#") for l in lines):
            issues["heading_only"].append(body[:80])
        table_rows = [l for l in lines if l.strip().startswith("|") and not re.fullmatch(r"\|[\s:\-|]+\|?", l.strip())]
        if len(table_rows) >= 2:
            counts = {r.strip().strip("|").count("|") for r in table_rows}
            if len(counts) > 1:
                issues["table_column_mismatch"].append(table_rows[0][:80])
    return {k: {"count": len(v), "examples": v[:3]} for k, v in issues.items() if v}


# ---------------------------------------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------------------------------------

def _plain(text: str) -> str:
    """Lower-case words only: a quote is matched regardless of markdown, table pipes or punctuation."""
    return re.sub(r"[^a-z0-9%]+", " ", (text or "").lower()).strip()


def _numbers(text: str) -> set:
    """Numbers regardless of thousands separators ('600.000', '600,000' and '600000' are one value)."""
    return {re.sub(r"[.,]", "", n) for n in _NUMBER_RE.findall(text or "")}


def _pick_sections(sections: List[str], n: int) -> List[str]:
    rich = [s for s in sections if len(content_words(s)) >= 15]
    if len(rich) <= n:
        return rich
    step = len(rich) / n
    return [rich[int(i * step)] for i in range(n)]


def generate_probes(client, model: str, sections: List[str], n: int = MAX_PROBES,
                    original_text: Optional[str] = None) -> List[Dict[str, str]]:
    """
    One factual question per sampled section, with the exact passage that answers it. Sections are the
    published content, where tables keep their columns (a PDF text layer flattens them, pairing values with
    the wrong row); with the original file's text given, the passage must also be printed there, so the
    fact under test comes from the document and not from the parser.
    """
    original_plain = _plain(original_text) if original_text else None
    picked = _pick_sections(sections, n)
    if not picked:
        return []
    numbered = "\n\n".join(f"[SECTION {i + 1}]\n{s[:2500]}" for i, s in enumerate(picked))
    prompt = (
        "You write test questions for a document question-answering system.\n"
        "For EACH section below write ONE question a professional user would ask whose answer is a specific "
        "fact stated in that section (a value, name, ingredient, step, date, indication, condition...).\n"
        "Rules: write the question in Indonesian; 'subject' is the specific named item the fact belongs to "
        "(a product, treatment, device, condition, document section...) copied exactly as printed in the section, "
        "and the question must contain it word for word (never 'this product', 'the therapy', 'the first step'); "
        "'answer_quote' must be copied verbatim from ONE line of the section (the line holding the fact); "
        "skip a section with no stated fact or no named subject.\n"
        'Return JSON: {"probes": [{"section": <number>, "subject": "...", "question": "...", "answer_quote": "..."}]}\n\n'
        + numbered
    )
    resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                          response_format={"type": "json_object"}, temperature=0.0)
    data = json.loads(resp.choices[0].message.content or "{}")
    probes = []
    for p in data.get("probes") or []:
        q, quote = str(p.get("question") or "").strip(), str(p.get("answer_quote") or "").strip()
        subject = str(p.get("subject") or "").strip()
        try:
            idx = int(p.get("section") or 0) - 1
        except (TypeError, ValueError):
            continue
        source = _plain(picked[idx]) if 0 <= idx < len(picked) else ""
        # A quote not found in its section is the model's paraphrase: it cannot be a reference. A question
        # without the printed subject is ambiguous across the knowledge base: its answer proves nothing.
        if (q and quote and _plain(quote) and _plain(quote) in source
                and len(_plain(subject)) >= 4 and _plain(subject) in source and _plain(subject) in _plain(q)
                and (original_plain is None or _plain(quote) in original_plain)):
            probes.append({"question": q, "answer_quote": quote, "subject": subject})
    return probes


def judge_answers(client, model: str, items: List[Dict[str, str]]) -> List[str]:
    """'correct' when the answer states the fact of the reference passage, 'partial', 'wrong' or 'missing'."""
    if not items:
        return []
    listing = "\n\n".join(
        f"[{i + 1}] QUESTION: {it['question']}\nREFERENCE: {it['answer_quote']}\nANSWER: {it['answer'][:1500]}"
        for i, it in enumerate(items)
    )
    prompt = (
        "Grade each ANSWER against its REFERENCE passage (the source document's own words).\n"
        "correct = the answer states the reference fact (other wording, units written differently, or "
        "additional facts alongside it are all fine); partial = only part of the reference fact; "
        "wrong = it states a different value/fact; missing = it says the information is not available or "
        "does not address it.\n"
        'Return JSON: {"grades": ["correct" | "partial" | "wrong" | "missing", ...]} in the same order.\n\n' + listing
    )
    resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                          response_format={"type": "json_object"}, temperature=0.0)
    grades = json.loads(resp.choices[0].message.content or "{}").get("grades") or []
    grades = [str(g).lower() for g in grades] + ["missing"] * (len(items) - len(grades))
    # A number in the reference that the answer lacks makes it at most partial, whatever the grader said
    for i, it in enumerate(items):
        ref_numbers = _numbers(it["answer_quote"])
        if grades[i] == "correct" and ref_numbers and not ref_numbers <= _numbers(it["answer"]):
            grades[i] = "partial"
    return grades[:len(items)]


def _ask(pipeline, question: str) -> Dict[str, Any]:
    res = pipeline.generate_answer(query=question, top_k=8, rerank=True, history=[], filter_metadata=None)
    return {"answer": str(res.get("answer") or ""),
            "version_ids": [str((r or {}).get("version_id") or "") for r in (res.get("results") or [])]}


def _generation_pipeline(client, model: str):
    """The pipeline the doctors' chat uses, with the model configured for it."""
    from app.rag.services.factory import AdapterFactory
    from app.rag.services.rag_retriever import HybridRetriever, BM25Index
    from app.rag.services.rag_generator import GenerationPipeline, OpenAIAdapter
    from app.rag.config import settings as rag_settings
    bm25 = BM25Index()
    try:
        bm25.load(rag_settings.bm25_index_path)
    except Exception:
        pass
    retriever = HybridRetriever(vector_store=AdapterFactory.get_vector_store(), bm25_index=bm25, reranker=None)
    llm = OpenAIAdapter(api_key=client.api_key, model_name=model, base_url=str(client.base_url))
    return GenerationPipeline(retriever=retriever, llm_adapter=llm)


# ---------------------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------------------

def run_quality_check(knowledge_id: str, version_id: Optional[str] = None, probes: bool = True) -> Dict[str, Any]:
    """Measures one document version (the active one by default) and stores the report on it."""
    from app.rag.services.canonical_ingest_service import CanonicalIngestService
    from app.rag.utils.parser import get_vision_client_and_model

    t0 = time.time()
    engine = CanonicalIngestService().engine
    with engine.connect() as conn:
        if version_id:
            v = conn.execute(text("SELECT id, status FROM knowledge_version WHERE id = :v"), {"v": version_id}).fetchone()
        else:
            v = conn.execute(text("""SELECT id, status FROM knowledge_version WHERE knowledge_id = :k
                                     ORDER BY (status = 'ACTIVE') DESC, version_no DESC LIMIT 1"""), {"k": knowledge_id}).fetchone()
        if not v:
            return {"status": "NO_VERSION"}
        version_id, v_status = str(v[0]), v[1]
        chunks = [chunk_content(r[0]) for r in conn.execute(
            text("SELECT retrieval_text FROM kb_chunk WHERE version_id = :v ORDER BY id"), {"v": version_id}).fetchall()]

    report: Dict[str, Any] = {"check_version": QUALITY_CHECK_VERSION, "version_id": version_id, "chunk_count": len(chunks)}
    index_text = "\n".join(chunks)

    src_path = _source_file(knowledge_id, engine)
    sections = extract_source_sections(src_path) if src_path else []
    if src_path and os.path.dirname(os.path.abspath(src_path)) == os.path.abspath(QUALITY_SRC_DIR):
        # A copy downloaded only for this check; the original stays in object storage
        try:
            os.remove(src_path)
        except OSError:
            pass
    source_text = "\n".join(sections)
    report["source"] = {"file": os.path.basename(src_path) if src_path else None, "sections": len(sections),
                        "words": len(content_words(source_text))}
    cov = text_coverage(source_text, index_text)
    report["coverage"] = round(cov, 3) if cov is not None else None
    if cov is not None:
        report["missing_examples"] = missing_lines(source_text, index_text)[:10]
    report["structure"] = lint_chunks(chunks)

    if probes and v_status == "ACTIVE":
        try:
            client, model = get_vision_client_and_model()
            plist = generate_probes(client, model, chunks,
                                    original_text=source_text if report["coverage"] is not None else None)
            pipeline = _generation_pipeline(client, model)
            items = []
            for p in plist:
                out = _ask(pipeline, p["question"])
                items.append({**p, "answer": out["answer"], "retrieved": version_id in out["version_ids"]})
            for it, g in zip(items, judge_answers(client, model, items)):
                it["grade"] = g
            correct = sum(1 for it in items if it["grade"] == "correct")
            report["probes"] = {
                "source": "published_content_checked_against_original" if report["coverage"] is not None else "published_content",
                "total": len(items), "correct": correct,
                "retrieved": sum(1 for it in items if it["retrieved"]),
                "score": round(correct / len(items), 3) if items else None,
                "failures": [{k: it[k] for k in ("question", "answer_quote", "answer", "grade", "retrieved")}
                             for it in items if it["grade"] != "correct"][:8],
            }
        except Exception as e:
            logger.warning(f"[QUALITY] Probes failed for {knowledge_id}: {e}")
            report["probes"] = {"error": str(e)}

    severe = {k for k in report["structure"] if k in ("placeholder_value", "table_column_mismatch", "empty")}
    probe_score = (report.get("probes") or {}).get("score")
    weak = [
        *(["coverage"] if report["coverage"] is not None and report["coverage"] < COVERAGE_MIN else []),
        *(["probes"] if probe_score is not None and probe_score < PROBE_PASS_MIN else []),
        *sorted(severe),
    ]
    report["status"] = "PASS" if not weak else "NEEDS_REVIEW"
    report["weak_points"] = weak
    report["seconds"] = round(time.time() - t0, 1)
    report["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    with engine.begin() as conn:
        conn.execute(text("""UPDATE knowledge_version
                             SET parse_report = COALESCE(parse_report, '{}'::jsonb) || jsonb_build_object('quality', CAST(:q AS jsonb))
                             WHERE id = :v"""), {"q": json.dumps(report, ensure_ascii=False), "v": version_id})
    logger.info(f"[QUALITY] {knowledge_id} v={version_id}: {report['status']} coverage={report['coverage']} "
                f"probes={probe_score} structure={list(report['structure'])} ({report['seconds']}s)")
    return report


# One check at a time in the background: it never competes with ingestion or chat for the small server.
_EXECUTOR = None


def schedule_quality_check(knowledge_id: str, version_id: Optional[str] = None, probes: bool = True) -> None:
    from app.rag.config import settings
    if not getattr(settings, "ingest_quality_check_enabled", True):
        return
    global _EXECUTOR
    if _EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor
        _EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest-quality")

    def _run():
        try:
            run_quality_check(knowledge_id, version_id=version_id, probes=probes)
        except Exception as e:
            logger.warning(f"[QUALITY] Check failed for {knowledge_id}: {e}")

    _EXECUTOR.submit(_run)
