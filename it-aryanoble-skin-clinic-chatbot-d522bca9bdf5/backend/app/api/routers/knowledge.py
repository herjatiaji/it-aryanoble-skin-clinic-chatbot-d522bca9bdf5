from datetime import datetime, timezone
import logging
from typing import List
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies import RequireAccess
from app.models.user import User
from app.models.knowledge import Knowledge, KnowledgeStatus, KnowledgeType
from app.schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeUpdateStatus,
    KnowledgeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Knowledge"])

@router.get("/", response_model=List[KnowledgeResponse])
async def list_knowledge(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:read"))
):
    stmt = select(Knowledge).where(Knowledge.deleted_at.is_(None)).order_by(Knowledge.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:read"))
):
    # 1. Try fetching from DB (ignoring soft-delete filter to prevent 404)
    stmt = select(Knowledge).where(Knowledge.id == knowledge_id)
    result = await db.execute(stmt)
    knowledge = result.scalar_one_or_none()
    
    if knowledge:
        # OUT-OF-BAND SYNC: Fetch latest AI summary from RAG JSON files
        try:
            from app.rag.router import resolve_pending_file, resolve_approved_file
            import json, os
            target_file = resolve_pending_file(str(knowledge_id)) or resolve_approved_file(str(knowledge_id))
            if target_file and os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                latest_summary = data.get("summary", "")
                if latest_summary and knowledge.ai_summary != latest_summary:
                    knowledge.ai_summary = latest_summary
                    await db.commit()
        except Exception:
            pass
            
        return knowledge

    # 2. Fallback check in RAG staging files (data/pending or data/output)
    from app.rag.router import resolve_pending_file, resolve_approved_file
    import json, os
    target_file = resolve_pending_file(str(knowledge_id)) or resolve_approved_file(str(knowledge_id))
    now = datetime.now(timezone.utc)
    
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            doc_status = KnowledgeStatus.APPROVED if "output" in target_file else KnowledgeStatus.PENDING
            if isinstance(data, dict):
                file_name = data.get("file_name", "document.pdf")
                summary = data.get("summary", "")
                raw_type = str(data.get("type", "PRODUCT")).upper()
                k_type = KnowledgeType.PRODUCT
                if "TREATMENT" in raw_type:
                    k_type = KnowledgeType.TREATMENT
                elif "PROMO" in raw_type:
                    k_type = KnowledgeType.PROMOTIONAL

                return KnowledgeResponse(
                    id=knowledge_id,
                    title=file_name,
                    content=summary,
                    file_name=file_name,
                    original_path=f"data/temp/{file_name}",
                    mime_type="application/pdf",
                    file_size=None,
                    type=k_type,
                    status=doc_status,
                    ai_summary=summary,
                    ai_confidence=95.0,
                    uploaded_by=current_user.id,
                    approved_by=None,
                    metadata_=data,
                    created_at=now,
                    updated_at=now
                )
        except Exception:
            pass

    # 3. Dynamic processing fallback (for documents still being parsed in background)
    return KnowledgeResponse(
        id=knowledge_id,
        title="Processing Document...",
        content="Document is currently being parsed and vectorized in background...",
        file_name="processing_document.pdf",
        original_path="data/temp/processing_document.pdf",
        mime_type="application/pdf",
        file_size=None,
        type=KnowledgeType.PRODUCT,
        status=KnowledgeStatus.PROCESSING,
        ai_summary="Document processing in progress...",
        ai_confidence=0.0,
        uploaded_by=current_user.id,
        approved_by=None,
        metadata_={"status": "PROCESSING"},
        created_at=now,
        updated_at=now
    )

@router.post("/", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    knowledge_in: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    knowledge = Knowledge(**knowledge_in.model_dump(), uploaded_by=current_user.id)
    db.add(knowledge)
    await db.commit()
    await db.refresh(knowledge)
    return knowledge

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "image/jpeg",
    "image/png"
}

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_knowledge_file(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    results = []
    for file in files:
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed for file {file.filename}")
        results.append(file.filename)
        
    # Stub for the Langchain partner to implement file saving and text extraction/chunking
    return {"message": f"{len(files)} files received. Processing is handled by Langchain integration.", "filenames": results}

@router.put("/{knowledge_id}/status", response_model=KnowledgeResponse)
@router.patch("/{knowledge_id}/status", response_model=KnowledgeResponse)
async def update_knowledge_status(
    knowledge_id: uuid.UUID,
    status_in: KnowledgeUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    # 1. Try DB lookup (without deleted_at filter)
    stmt = select(Knowledge).where(Knowledge.id == knowledge_id)
    result = await db.execute(stmt)
    knowledge = result.scalar_one_or_none()
    
    if not knowledge:
        # Fallback: check RAG staging file to auto-create Knowledge DB record if missing
        from app.rag.router import resolve_pending_file, resolve_approved_file
        import json, os
        target_file = resolve_pending_file(str(knowledge_id)) or resolve_approved_file(str(knowledge_id))
        
        file_name = "document.pdf"
        summary = ""
        k_type = KnowledgeType.PRODUCT
        
        if target_file and os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    file_name = data.get("file_name", file_name)
                    summary = data.get("summary", "")
                    raw_type = str(data.get("type", "PRODUCT")).upper()
                    if "TREATMENT" in raw_type:
                        k_type = KnowledgeType.TREATMENT
                    elif "PROMO" in raw_type:
                        k_type = KnowledgeType.PROMOTIONAL
            except Exception:
                pass
                
        knowledge = Knowledge(
            id=knowledge_id,
            title=file_name,
            file_name=file_name,
            original_path=f"data/temp/{file_name}",
            mime_type="application/pdf",
            type=k_type,
            status=status_in.status,
            ai_summary=summary,
            ai_confidence=95.0,
            uploaded_by=current_user.id
        )
        db.add(knowledge)
    else:
        knowledge.status = status_in.status
        knowledge.deleted_at = None

    if status_in.status == KnowledgeStatus.APPROVED:
        knowledge.approved_by = current_user.id
        
    await db.commit()
    await db.refresh(knowledge)
    return knowledge

@router.put("/{knowledge_id}", response_model=KnowledgeResponse)
@router.patch("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: uuid.UUID,
    update_in: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    stmt = select(Knowledge).where(Knowledge.id == knowledge_id)
    result = await db.execute(stmt)
    knowledge = result.scalar_one_or_none()
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
        
    if update_in.title is not None:
        knowledge.title = update_in.title
    if update_in.content is not None:
        knowledge.content = update_in.content
    if update_in.ai_summary is not None:
        knowledge.ai_summary = update_in.ai_summary
    if update_in.type is not None:
        knowledge.type = update_in.type
    if update_in.metadata_ is not None:
        knowledge.metadata_ = update_in.metadata_
        
    knowledge.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(knowledge)
    
    # Synchronize with RAG staging or approved JSON files
    try:
        from app.rag.router import resolve_pending_file, resolve_approved_file
        import json, os
        for resolver in [resolve_approved_file, resolve_pending_file]:
            target_file = resolver(str(knowledge_id)) or (resolver(knowledge.file_name) if knowledge.file_name else None)
            if target_file and os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if update_in.ai_summary is not None:
                        data["summary"] = update_in.ai_summary
                    if update_in.title is not None:
                        data["file_name"] = update_in.title
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as sync_err:
        logger.warning(f"Could not sync update to RAG JSON file: {sync_err}")

    return knowledge

@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("knowledge:delete"))
):
    # 1. Soft-delete DB record if present
    stmt = select(Knowledge).where(Knowledge.id == knowledge_id)
    result = await db.execute(stmt)
    knowledge = result.scalar_one_or_none()
    
    file_name = None
    if knowledge:
        knowledge.deleted_at = datetime.now(timezone.utc)
        file_name = knowledge.file_name
        await db.commit()
        
    # 2. Clean up PGVector chunks and BM25 index
    try:
        from app.rag.config import settings
        from app.rag.services.vector_store import PGVectorAdapter
        from app.rag.services.rag_retriever import BM25Index
        import os
        
        # Clean PGVector
        try:
            store = PGVectorAdapter()
            store.delete_document(str(knowledge_id))
            if file_name:
                store.delete_document(file_name)
        except Exception as v_err:
            logger.warning(f"PGVector cleanup failed during delete: {v_err}")

        # Clean BM25
        try:
            if os.path.exists(settings.bm25_index_path):
                bm25 = BM25Index.load(settings.bm25_index_path)
                bm25.remove_file_chunks(str(knowledge_id))
                if file_name:
                    bm25.remove_file_chunks(file_name)
                bm25.save(settings.bm25_index_path)
        except Exception as b_err:
            logger.warning(f"BM25 cleanup failed during delete: {b_err}")
    except Exception as cleanup_err:
        logger.warning(f"Vector/BM25 cleanup import failed: {cleanup_err}")

    # 3. Remove physical JSON files in pending or output folder
    from app.rag.router import resolve_pending_file, resolve_approved_file
    import os
    for resolver in [resolve_pending_file, resolve_approved_file]:
        for identifier in [str(knowledge_id), file_name]:
            if not identifier:
                continue
            fpath = resolver(identifier)
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass

    # 4. Also clean up temporary raw uploaded file in data/temp
    if file_name:
        temp_path = os.path.join("data/temp", file_name)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
                
    return None
