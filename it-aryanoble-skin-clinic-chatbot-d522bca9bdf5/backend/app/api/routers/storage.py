import mimetypes
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from app.services.storage import get_s3_object_stream, diagnose_s3_storage

router = APIRouter(prefix="/storage", tags=["storage"])

MIME_OVERRIDES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _resolve_mime_type(filename: str, default: str = "application/octet-stream") -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or default


import urllib.parse


@router.get("/debug/health", summary="Probe S3 and storage health")
async def get_storage_health():
    """
    Diagnostic probe endpoint for AWS IRSA / MinIO storage.
    Inspects authentication mode, AWS environment variables, and bucket connectivity.
    """
    return diagnose_s3_storage()


@router.get("/debug/diagnose", summary="Diagnose specific storage key lookup")
async def diagnose_storage_key(key: str):
    """
    Deep-dive trace for a specific storage asset key across S3 buckets and local disk fallback.
    """
    if not key or not key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter 'key' is required.")
    return diagnose_s3_storage(key=key)


@router.get("/{s3_key:path}", summary="Stream storage asset or proxy image")
async def get_storage_asset(s3_key: str):
    """
    Public storage proxy endpoint.
    Streams images and documents directly from MinIO or fallback local storage.
    Enables client browsers to access assets in production/CIS with minimal memory footprint.
    """
    raw_key = urllib.parse.unquote(s3_key).strip()
    clean_key = raw_key.lstrip("/")
    if clean_key.startswith("api/storage/"):
        clean_key = clean_key[len("api/storage/"):]
    elif clean_key.startswith("storage/"):
        clean_key = clean_key[len("storage/"):]
    clean_key = clean_key.lstrip("/")

    fname = os.path.basename(clean_key)
    media_type = _resolve_mime_type(fname)


    # 1. Try streaming directly from MinIO Object Storage
    try:
        stream_gen, ctype, content_length = get_s3_object_stream(clean_key)
        if stream_gen:
            headers = {
                "Cache-Control": "public, max-age=86400",
                "Content-Disposition": "inline",
                "Access-Control-Allow-Origin": "*",
            }
            if content_length is not None:
                headers["Content-Length"] = str(content_length)
            return StreamingResponse(
                stream_gen,
                media_type=ctype or media_type,
                headers=headers
            )
    except Exception as err:
        logger.warning(f"Storage proxy S3 stream error for '{clean_key}': {err}")

    # 2. Direct fallback: Check local disk storage folders

    clean_norm = os.path.normpath(clean_key)
    search_folders = [
        "data/temp",
        "data/images",
        "data/uploads",
        "data/documents",
        "data/storage",
        "data/temp/images",
        "data/output/images",
        "data/output"
    ]
    for folder in search_folders:
        for candidate in [clean_key, clean_norm, fname]:
            local_path = os.path.normpath(os.path.join(folder, candidate))
            if os.path.exists(local_path) and os.path.isfile(local_path):
                return FileResponse(
                    path=local_path,
                    media_type=media_type,
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Content-Disposition": "inline",
                        "Access-Control-Allow-Origin": "*",
                    }
                )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storage asset '{clean_key}' not found.")
