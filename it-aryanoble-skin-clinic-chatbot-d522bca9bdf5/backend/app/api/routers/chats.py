from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
import uuid
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
from app.core.database import AsyncSessionLocal
from app.models.branch import Branch

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserType
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import (
    ChatSessionCreate, ChatSessionUpdate, ChatSessionResponse,
    ChatHistoryResponse, ChatMessageCreate, ChatMessageResponse
)
from app.models.config import AppConfig

router = APIRouter(tags=["Chats"])

async def process_ai_response(session_id: uuid.UUID, user_query: str):
    """
    Background task to generate AI response using app.rag pipeline.
    """
    try:
        from app.rag.services.factory import AdapterFactory
        from app.rag.services.rag_retriever import HybridRetriever, BM25Index, Reranker
        from app.rag.services.rag_generator import GenerationPipeline
        from app.rag.config import settings as rag_settings
    except ImportError as e:
        logger.error(f"AI dependencies missing: {e}")
        return

    async with AsyncSessionLocal() as db:
        try:
            vector_store = AdapterFactory.get_vector_store()
            bm25_index = BM25Index()
            try:
                bm25_index.load(rag_settings.bm25_index_path)
            except Exception:
                pass
            reranker = Reranker(model_name=rag_settings.reranker_model_name)
            retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25_index, reranker=reranker)
            llm_adapter = await AdapterFactory.get_dynamic_llm(db)
            pipeline = GenerationPipeline(retriever=retriever, llm_adapter=llm_adapter)
            
            stmt_msg = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
            result_msg = await db.execute(stmt_msg)
            messages = result_msg.scalars().all()
            
            history = [{"role": msg.role, "content": msg.content} for msg in messages if msg.role in ["user", "assistant"]]
            if history and history[-1]["role"] == "user":
                history.pop()
            
            response_dict = pipeline.generate_answer(
                query=user_query,
                top_k=5,
                rerank=True,
                history=history
            )
            
            ai_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=response_dict["answer"]
            )
            db.add(ai_msg)
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            fallback = ChatMessage(session_id=session_id, role="assistant", content="Maaf, terjadi kesalahan pada pemrosesan AI.")
            db.add(fallback)
            await db.commit()

async def has_chats_read_access(user: User, db: AsyncSession) -> bool:
    if user.type != UserType.STAFF:
        return False
    from app.models.user import Role, UserRole, RoleAccess, Access
    stmt = (
        select(Access.name)
        .join(RoleAccess, RoleAccess.access_id == Access.id)
        .join(UserRole, UserRole.role_id == RoleAccess.role_id)
        .where(UserRole.user_id == user.id)
    )
    result = await db.execute(stmt)
    return "chats:read" in result.scalars().all()

async def _hydrate_chat_session(session: ChatSession, db: AsyncSession) -> dict:
    session_dict = {
        "id": session.id,
        "user_id": session.user_id,
        "branch_id": session.branch_id,
        "status": session.status,
        "summary": session.summary,
        "rating": session.rating,
        "feedback": session.feedback,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "query": "",
        "messages": 0,
        "doctor": "Unknown",
        "branch": "Unknown Branch"
    }
    
    # Get total message count
    stmt_count = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    result_count = await db.execute(stmt_count)
    session_dict["messages"] = result_count.scalar() or 0
    
    # Get the very first message
    stmt_first_msg = select(ChatMessage.content).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc()).limit(1)
    result_msg = await db.execute(stmt_first_msg)
    session_dict["query"] = result_msg.scalar() or ""
    
    # Get the doctor's name
    stmt_user = select(User.name).where(User.id == session.user_id)
    result_user = await db.execute(stmt_user)
    session_dict["doctor"] = result_user.scalar() or "Unknown"
    
    # Get the branch name
    stmt_branch = select(Branch.name).where(Branch.id == session.branch_id)
    result_branch = await db.execute(stmt_branch)
    session_dict["branch"] = result_branch.scalar() or "Unknown Branch"
    
    return session_dict

@router.get("/", response_model=List[ChatHistoryResponse])
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(ChatSession)
    if not await has_chats_read_access(current_user, db):
        stmt = stmt.where(ChatSession.user_id == current_user.id)
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [await _hydrate_chat_session(s, db) for s in sessions]

@router.post("/", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_in: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = ChatSession(
        user_id=current_user.id,
        branch_id=session_in.branch_id
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

@router.put("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: uuid.UUID,
    session_in: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    if not await has_chats_read_access(current_user, db):
        stmt = stmt.where(ChatSession.user_id == current_user.id)
        
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    update_data = session_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)
        
    await db.commit()
    await db.refresh(session)
    return session

@router.get("/{session_id}/messages", response_model=List[ChatMessageResponse])
async def list_chat_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify access to session
    stmt_session = select(ChatSession).where(ChatSession.id == session_id)
    if not await has_chats_read_access(current_user, db):
        stmt_session = stmt_session.where(ChatSession.user_id == current_user.id)
    
    result_session = await db.execute(stmt_session)
    if not result_session.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    # Get messages
    stmt_msg = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    result_msg = await db.execute(stmt_msg)
    return result_msg.scalars().all()

from fastapi import Form, UploadFile, File
import json

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

@router.post("/{session_id}/messages", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_message(
    session_id: uuid.UUID,
    role: str = Form(...),
    content: str = Form(...),
    background_tasks: BackgroundTasks = None,
    files: Optional[List[UploadFile]] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify access to session
    stmt_session = select(ChatSession).where(ChatSession.id == session_id)
    if not await has_chats_read_access(current_user, db):
        stmt_session = stmt_session.where(ChatSession.user_id == current_user.id)
    
    result_session = await db.execute(stmt_session)
    if not result_session.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    attachments = None
    if files:
        attachments = {}
        for file in files:
            if file.content_type not in ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed for file {file.filename}")
            attachments[file.filename] = {"content_type": file.content_type, "status": "processed"}

    # We just save the message. A Langchain service would normally process and reply here.
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        attachments=attachments
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    if role == "user" and background_tasks is not None:
        background_tasks.add_task(process_ai_response, session_id, content)
        
    return message
