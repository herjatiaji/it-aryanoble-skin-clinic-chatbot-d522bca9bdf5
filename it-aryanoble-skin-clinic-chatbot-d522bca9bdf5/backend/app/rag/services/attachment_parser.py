"""Dedicated Attachment Parser for Chat File Uploads.

Extracts text content from patient documents (PDF, DOCX, TXT, images, etc.)
uploaded during chat sessions. Reuses DocumentParser infrastructure for
robust multi-format support including OCR fallback.

Usage:
    from app.rag.services.attachment_parser import AttachmentParser

    parser = AttachmentParser()
    text, meta = await parser.extract_from_upload(upload_file)
    # text = "Nama: Hamdan Zakirun\nUsia: 28 tahun\n..."
    # meta = {"filename": "...", "content_type": "...", "chars": 1234, "pages": 3}
"""

import os
import tempfile
import time
from typing import Tuple, Dict, Any, Optional

from loguru import logger
from fastapi import UploadFile


class AttachmentParser:
    """
    Extracts text from uploaded chat attachments (patient profiles, documents, images).

    Supports: PDF, DOCX, DOC, XLSX, XLS, CSV, PPTX, PPT, TXT, PNG, JPG, JPEG, WEBP.

    For images (PNG/JPG): Uses a lightweight OCR/description approach suitable for
    chat context (not the full knowledge-base ingestion pipeline with MinIO upload).
    """

    # Map MIME types to file extensions for temp file naming
    MIME_TO_EXT = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "text/csv": ".csv",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "text/plain": ".txt",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    def __init__(self):
        self._doc_parser = None  # Lazy-loaded DocumentParser

    def _get_doc_parser(self):
        """Lazy-load DocumentParser to avoid unnecessary import overhead."""
        if self._doc_parser is None:
            from app.rag.utils.parser import DocumentParser
            self._doc_parser = DocumentParser()
        return self._doc_parser

    async def extract_from_upload(self, upload_file: UploadFile) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from an uploaded file (FastAPI UploadFile).

        Returns:
            Tuple of (extracted_text: str, metadata: dict)
            metadata includes: filename, content_type, chars, pages, method, extraction_ms
        """
        filename = upload_file.filename or "unknown_file"
        content_type = upload_file.content_type or "application/octet-stream"

        logger.info(f"📎 [AttachmentParser] Extracting text from: {filename} ({content_type})")

        file_bytes = await upload_file.read()
        # Reset file position for potential re-reads
        await upload_file.seek(0)

        return self.extract_from_bytes(file_bytes, filename, content_type)

    def extract_from_bytes(
        self, file_bytes: bytes, filename: str, content_type: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from raw bytes with known filename and content type.

        Returns:
            Tuple of (extracted_text: str, metadata: dict)
        """
        t0 = time.time()
        meta = {
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
            "chars": 0,
            "pages": 0,
            "method": "unknown",
        }

        # Determine file extension
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = self.MIME_TO_EXT.get(content_type, "")

        # For plain text files, decode directly without temp file overhead
        if ext == ".txt" or content_type == "text/plain":
            text = self._decode_text(file_bytes)
            meta.update({"chars": len(text), "pages": 1, "method": "direct_decode"})
            meta["extraction_ms"] = int((time.time() - t0) * 1000)
            logger.info(f"✅ [AttachmentParser] Extracted {len(text)} chars from TXT in {meta['extraction_ms']}ms")
            return text, meta

        # For images, use lightweight vision extraction (no MinIO upload)
        if ext in (".png", ".jpg", ".jpeg", ".webp") or content_type.startswith("image/"):
            text = self._extract_image_text(file_bytes, filename, content_type)
            meta.update({"chars": len(text), "pages": 1, "method": "vision_llm"})
            meta["extraction_ms"] = int((time.time() - t0) * 1000)
            logger.info(f"✅ [AttachmentParser] Extracted {len(text)} chars from image in {meta['extraction_ms']}ms")
            return text, meta

        # For all other formats: save to temp file and use DocumentParser
        text = self._extract_via_doc_parser(file_bytes, filename, ext)
        page_count = text.count("\n--- Page") + 1 if text else 0
        meta.update({"chars": len(text), "pages": max(page_count, 1), "method": "doc_parser"})
        meta["extraction_ms"] = int((time.time() - t0) * 1000)
        logger.info(f"✅ [AttachmentParser] Extracted {len(text)} chars from {ext} in {meta['extraction_ms']}ms")
        return text, meta

    def _decode_text(self, file_bytes: bytes) -> str:
        """Decode text bytes with UTF-8 fallback to Latin-1."""
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("latin-1")
            except Exception:
                return file_bytes.decode("utf-8", errors="ignore")

    def _extract_via_doc_parser(self, file_bytes: bytes, filename: str, ext: str) -> str:
        """
        Save bytes to temp file, parse with DocumentParser, return combined text.
        Handles PDF, DOCX, DOC, XLSX, XLS, CSV, PPTX, PPT.
        """
        parser = self._get_doc_parser()
        tmp_path = None

        try:
            # Create temp file with correct extension (required for parser routing)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="chat_attach_") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            parse_result = parser.parse_file(tmp_path)
            if parse_result is None:
                logger.warning(f"⚠️ [AttachmentParser] DocumentParser returned None for {filename}")
                return f"[Dokumen tidak dapat diproses: {filename}]"

            # Extract text from ParseResult
            if parse_result.is_fast and parse_result.pages:
                texts = []
                for page in parse_result.pages:
                    page_text = page.get("text", "").strip()
                    if page_text:
                        page_num = page.get("page", "?")
                        texts.append(page_text)
                return "\n\n".join(texts)

            elif parse_result.is_docling and parse_result.docling_doc:
                try:
                    return parse_result.docling_doc.export_to_markdown()
                except Exception:
                    return str(parse_result.docling_doc)

            return f"[Dokumen tidak dapat diproses: {filename}]"

        except Exception as e:
            logger.error(f"❌ [AttachmentParser] Error parsing {filename}: {e}")
            return f"[Error saat memproses dokumen: {filename} — {type(e).__name__}]"

        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def _extract_image_text(self, image_bytes: bytes, filename: str, content_type: str) -> str:
        """
        Extract text/description from image using Vision LLM.
        Lightweight version for chat context — does NOT upload to MinIO.
        Falls back to basic description if Vision LLM is unavailable.
        """
        import base64

        try:
            from app.rag.config import settings
            from openai import OpenAI

            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            data_uri = f"data:{content_type};base64,{b64_img}"

            # Try to get API key from database first, then fallback to env
            api_key = None
            base_url = None
            model_name = None

            try:
                from sqlalchemy import create_engine, text
                from app.core.security import decrypt_api_key

                sync_conn_str = settings.pg_conn_str.replace("+asyncpg", "")
                engine = create_engine(sync_conn_str)
                with engine.connect() as conn:
                    rows = conn.execute(
                        text("SELECT key, value FROM app_config WHERE key IN ('LLM_API_KEY', 'LLM_MODEL_NAME', 'LLM_BASE_URL')")
                    ).fetchall()
                    config_map = {r[0]: r[1] for r in rows}
                    raw_key = config_map.get("LLM_API_KEY")
                    if raw_key:
                        api_key = decrypt_api_key(raw_key)
                    model_name = config_map.get("LLM_MODEL_NAME")
                    base_url = config_map.get("LLM_BASE_URL")
                engine.dispose()
            except Exception:
                pass

            api_key = api_key or settings.openai_api_key
            model_name = model_name or settings.openai_model_name
            base_url = base_url or getattr(settings, "openai_base_url", None)

            if not api_key:
                logger.warning("⚠️ [AttachmentParser] No Vision LLM API key available for image extraction")
                return f"[Gambar terlampir: {filename} — ekstraksi otomatis tidak tersedia]"

            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url

            client = OpenAI(**client_kwargs)

            vision_prompt = (
                "Kamu adalah asisten medis. Dokter melampirkan gambar ini di dalam chat. "
                "Ekstrak SEMUA informasi yang terlihat dalam gambar ini secara lengkap dan terstruktur:\n"
                "- Jika ini adalah dokumen/formulir pasien: ekstrak semua field (nama, usia, keluhan, diagnosis, riwayat, dll)\n"
                "- Jika ini adalah foto kondisi kulit: deskripsikan kondisi klinis yang terlihat (lokasi, jenis lesi, distribusi, severity)\n"
                "- Jika ini adalah resep/label obat: ekstrak nama obat, dosis, aturan pakai\n"
                "- Jika ini adalah hasil lab/foto klinis: ekstrak data yang relevan\n\n"
                "Format output sebagai teks terstruktur yang rapi. Tulis dalam Bahasa Indonesia."
            )

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": vision_prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=1500,
                temperature=0.0,
            )

            extracted = response.choices[0].message.content.strip()
            if extracted:
                return f"[Informasi dari gambar: {filename}]\n{extracted}"

        except Exception as e:
            logger.warning(f"⚠️ [AttachmentParser] Vision LLM extraction failed for {filename}: {e}")

        return f"[Gambar terlampir: {filename} — konten tidak dapat diekstrak otomatis]"
