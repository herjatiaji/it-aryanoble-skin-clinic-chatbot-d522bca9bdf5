from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from fastapi.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, update
from typing import List, Optional
import os
import uuid
import re
import asyncio
import json
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
from app.core.database import AsyncSessionLocal
from app.models.branch import Branch, UserBranch
from app.models.category import Category, UserCategoryExclusion

from app.core.database import get_db
from app.api.dependencies import get_current_user, get_current_user_from_proxy, get_current_user_flexible
from app.models.user import User, UserType, UserTokenUsage
from app.models.chat import ChatSession, ChatMessage, ChatRole, ChatStatus, ChatRating
from app.models.config import AppConfig
from app.schemas.chat import (
    ChatSessionCreate, ChatSessionUpdate, ChatSessionResponse,
    ChatHistoryResponse, ChatStatsResponse, ChatMessageCreate, ChatMessageResponse
)
from app.core.token_counter import count_chat_prompt_tokens, count_chat_completion_tokens
from app.services.token_service import check_chat_token_quota, record_chat_token_usage
from datetime import datetime, timezone, timedelta

router = APIRouter(tags=["Chats"])

async def summarize_chat_session(session_id: uuid.UUID):
    """Background task to generate a summary for a closed chat session."""
    try:
        from app.rag.services.factory import AdapterFactory
    except ImportError as e:
        logger.error(f"Cannot summarize, AI dependencies missing: {e}")
        return

    async with AsyncSessionLocal() as db:
        try:
            # Check if session exists and has no summary
            stmt_session = select(ChatSession).where(ChatSession.id == session_id)
            result_session = await db.execute(stmt_session)
            chat_session = result_session.scalar_one_or_none()
            
            if not chat_session or chat_session.summary or chat_session.status != ChatStatus.CLOSED:
                return

            # Fetch messages
            stmt_msg = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
            result_msg = await db.execute(stmt_msg)
            messages = result_msg.scalars().all()
            
            if not messages:
                return
                
            transcript = ""
            for msg in messages:
                role = "Doctor" if msg.role.value == "USER" else "Assistant"
                transcript += f"{role}: {msg.content}\n\n"
                
            prompt = (
                "You are an AI summarizing a medical support chat. "
                "Provide a brief, 1-2 sentence summary of the main topic and resolution of the following conversation.\n\n"
                f"Transcript:\n{transcript}\n\nSummary:"
            )
            
            llm_adapter = await AdapterFactory.get_dynamic_llm(db)
            summary = llm_adapter.generate(prompt)
            
            chat_session.summary = summary.strip()
            db.add(chat_session)
            await db.commit()
            logger.info(f"Successfully generated summary for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to summarize chat session {session_id}: {e}")

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
            
            stmt_sess = select(ChatSession).where(ChatSession.id == session_id)
            sess_res = await db.execute(stmt_sess)
            chat_sess = sess_res.scalar_one_or_none()
            doctor_filter = None
            doctor_name = None
            if chat_sess:
                u_stmt = select(User).where(User.id == chat_sess.user_id)
                u_res = await db.execute(u_stmt)
                u_obj = u_res.scalar_one_or_none()
                if u_obj:
                    doctor_filter = await _build_doctor_filter_metadata(db, u_obj)
                    doctor_name = u_obj.name

            response_dict = pipeline.generate_answer(
                query=user_query,
                top_k=5,
                rerank=True,
                history=history,
                filter_metadata=doctor_filter,
                doctor_name=doctor_name
            )
            
            ai_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=response_dict["answer"]
            )
            db.add(ai_msg)
            await db.commit()

            # Trigger ChatGPT/Gemini-style title generation in background
            import asyncio
            from app.services.chat_title_service import generate_and_save_chat_title
            asyncio.create_task(generate_and_save_chat_title(session_id, user_query, response_dict.get("answer")))
            
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

async def _is_file_attachments_allowed(db: AsyncSession) -> bool:
    stmt = select(AppConfig.value).where(AppConfig.key == "AI_PROMPT_FILE_ATTACHMENTS")
    res = await db.execute(stmt)
    val = res.scalar_one_or_none()
    return val == "true"

async def _build_doctor_filter_metadata(db: AsyncSession, user: User) -> dict:
    """Build filter_metadata dict for doctor-level knowledge restrictions.
    
    Mirrors the logic in knowledge.py to ensure consistent access control
    across both the Knowledge Chat and Live Chat endpoints.
    """
    # Fetch user branches (active connections only)
    stmt_branches = select(UserBranch.branch_id).where(
        UserBranch.user_id == user.id,
        UserBranch.status == 1,
        UserBranch.deleted_at.is_(None)
    )
    result_branches = await db.execute(stmt_branches)
    branch_ids = [str(b_id) for b_id in result_branches.scalars().all()]

    # Fetch excluded category names
    stmt_exclusions = (
        select(Category.name)
        .join(UserCategoryExclusion, UserCategoryExclusion.category_id == Category.id)
        .where(UserCategoryExclusion.user_id == user.id)
    )
    result_exclusions = await db.execute(stmt_exclusions)
    excluded_cats = [name for name in result_exclusions.scalars().all()]

    filter_metadata = {
        "clinics": branch_ids + ["all"],
        "doctor_types": [user.dr_type or "all", "all"],
        "doctors": [str(user.id), "all"],
    }
    if excluded_cats:
        filter_metadata["excluded_categories"] = excluded_cats

    return filter_metadata

from app.services.chat_title_service import (
    clean_heuristic_title,
    sanitize_llm_title,
    generate_and_save_chat_title
)

def clean_and_shorten_session_title(text: Optional[str], max_len: int = 70) -> str:
    """Compatibility wrapper around clean_heuristic_title."""
    return clean_heuristic_title(text, max_len=max_len)

async def _hydrate_chat_session(session: ChatSession, db: AsyncSession) -> dict:
    session_dict = {
        "id": session.id,
        "user_id": session.user_id,
        "branch_id": session.branch_id,
        "session_type": session.session_type,
        "status": session.status,
        "summary": session.summary,
        "rating": session.rating,
        "feedback": session.feedback,
        "has_data_issue": session.has_data_issue,
        "is_feedback_read": session.is_feedback_read,
        "allow_file_attachments": await _is_file_attachments_allowed(db),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "query": "",
        "messages": 0,
        "doctor": "Unknown",
        "user_name": "Unknown",
        "user_type": None,
        "branch": "General Prompt" if not session.branch_id else "Unknown Branch"
    }
    
    # Get total message count
    stmt_count = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    result_count = await db.execute(stmt_count)
    session_dict["messages"] = result_count.scalar() or 0
    
    # 1. If LLM-generated title/summary already exists, use it directly (like Gemini/ChatGPT)
    if session.summary and session.summary.strip():
        session_dict["query"] = sanitize_llm_title(session.summary)
    else:
        # Prioritize the first USER message as the fallback
        stmt_first_user = (
            select(ChatMessage.content)
            .where(ChatMessage.session_id == session.id, ChatMessage.role == ChatRole.USER)
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        res_user_msg = await db.execute(stmt_first_user)
        raw_query = res_user_msg.scalar_one_or_none()

        # Fallback to the very first message if no user message found
        if not raw_query:
            stmt_first_msg = (
                select(ChatMessage.content)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.asc())
                .limit(1)
            )
            res_any_msg = await db.execute(stmt_first_msg)
            raw_query = res_any_msg.scalar_one_or_none()

        if raw_query:
            session_dict["query"] = clean_heuristic_title(raw_query)
            # Asynchronously schedule LLM title generation so future fetches use persistent LLM title
            import asyncio
            asyncio.create_task(generate_and_save_chat_title(session.id, raw_query))
        else:
            session_dict["query"] = "Percakapan Baru"
    
    # Get the user's name, user_type, and doctor type
    stmt_user = select(User.name, User.dr_type, User.type).where(User.id == session.user_id)
    result_user = await db.execute(stmt_user)
    user_row = result_user.first()
    if user_row:
        user_name = user_row[0] or "Unknown"
        session_dict["doctor"] = user_name
        session_dict["user_name"] = user_name
        session_dict["doctor_type"] = user_row[1]
        session_dict["user_type"] = user_row[2].value if hasattr(user_row[2], 'value') else str(user_row[2])
    else:
        session_dict["doctor"] = "Unknown"
        session_dict["user_name"] = "Unknown"
        session_dict["doctor_type"] = None
        session_dict["user_type"] = None
    
    # Get the branch name
    if session.branch_id:
        stmt_branch = select(Branch.name).where(Branch.id == session.branch_id)
        result_branch = await db.execute(stmt_branch)
        session_dict["branch"] = result_branch.scalar() or "Unknown Branch"
    else:
        session_dict["branch"] = "General Assistant"
    
    return session_dict

from app.schemas.pagination import PaginatedResponse
from typing import List, Optional, Union
from fastapi import Query
import math

@router.get("/feedback", response_model=Union[PaginatedResponse[ChatHistoryResponse], List[ChatHistoryResponse]])
async def list_chat_feedbacks(
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    # Enforce access - usually only staff/admin should see this
    if not await has_chats_read_access(current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized to view feedbacks")
        
    stmt = (
        select(ChatSession)
        .where(ChatSession.has_data_issue == True, ChatSession.session_type == "DOCTOR")
        .order_by(ChatSession.updated_at.desc())
    )

    if page is not None:
        p_size = page_size or 10
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0
        total_pages = max(1, math.ceil(total / p_size))

        paginated_stmt = stmt.offset((page - 1) * p_size).limit(p_size)
        result = await db.execute(paginated_stmt)
        sessions = result.scalars().all()
        hydrated = [await _hydrate_chat_session(s, db) for s in sessions]

        return PaginatedResponse[ChatHistoryResponse](
            items=hydrated,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )
    
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [await _hydrate_chat_session(s, db) for s in sessions]

from pydantic import BaseModel
class MarkFeedbackReadRequest(BaseModel):
    session_ids: List[uuid.UUID]

@router.put("/feedback/read", status_code=status.HTTP_200_OK)
async def mark_feedback_read(
    req: MarkFeedbackReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    if not await has_chats_read_access(current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if not req.session_ids:
        return {"status": "ok", "marked": 0}
        
    stmt = (
        update(ChatSession)
        .where(ChatSession.id.in_(req.session_ids))
        .values(is_feedback_read=True)
    )
    result = await db.execute(stmt)
    await db.commit()
    return {"status": "ok", "marked": result.rowcount}

@router.get("/stats", response_model=ChatStatsResponse)
async def get_chat_stats(
    doctor_id: Optional[uuid.UUID] = None,
    session_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    """Return overview counts of users reached, sessions, ratings, and missing knowledge."""
    has_messages = select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists()
    base_where = [has_messages, User.type == UserType.DOCTOR]
    if session_type:
        base_where.append(ChatSession.session_type == session_type)
    else:
        base_where.append(ChatSession.session_type == "DOCTOR")

    if not await has_chats_read_access(current_user, db):
        base_where.append(ChatSession.user_id == current_user.id)
    elif doctor_id:
        base_where.append(ChatSession.user_id == doctor_id)

    stmt = (
        select(
            func.count(func.distinct(ChatSession.user_id)).label("doctors_reached"),
            func.count(ChatSession.id).label("total_sessions"),
            func.count(ChatSession.id).filter(ChatSession.rating == ChatRating.GOOD).label("positive_ratings"),
            func.count(ChatSession.id).filter(ChatSession.rating == ChatRating.BAD).label("negative_ratings"),
            func.count(ChatSession.id).filter(ChatSession.has_data_issue.is_(True)).label("missing_knowledge"),
        )
        .join(User, ChatSession.user_id == User.id)
    )
    if base_where:
        stmt = stmt.where(*base_where)

    result = (await db.execute(stmt)).one()

    return ChatStatsResponse(
        doctors_reached=result.doctors_reached or 0,
        total_sessions=result.total_sessions or 0,
        positive_ratings=result.positive_ratings or 0,
        negative_ratings=result.negative_ratings or 0,
        missing_knowledge=result.missing_knowledge or 0,
    )

@router.get("/", response_model=Union[PaginatedResponse[ChatHistoryResponse], List[ChatHistoryResponse]])
async def list_chat_sessions(
    search: Optional[str] = None,
    doctor_id: Optional[uuid.UUID] = None,
    session_type: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    has_messages = select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists()
    stmt = (
        select(ChatSession)
        .where(has_messages)
        .order_by(ChatSession.updated_at.desc())
    )
    if session_type:
        stmt = stmt.where(ChatSession.session_type == session_type)
    if not await has_chats_read_access(current_user, db):
        stmt = stmt.where(ChatSession.user_id == current_user.id)
    elif doctor_id:
        stmt = stmt.where(ChatSession.user_id == doctor_id)

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    hydrated = [await _hydrate_chat_session(s, db) for s in sessions]

    if search:
        s_clean = search.lower().strip()
        hydrated = [
            h for h in hydrated
            if s_clean in (h.get("query") or "").lower()
            or s_clean in (h.get("summary") or "").lower()
            or s_clean in (h.get("doctor") or "").lower()
            or s_clean in (h.get("user_name") or "").lower()
            or s_clean in (h.get("branch") or "").lower()
            or s_clean in (h.get("session_type") or "").lower()
        ]

    if page is not None:
        p_size = page_size or 10
        total = len(hydrated)
        total_pages = max(1, math.ceil(total / p_size))
        start_idx = (page - 1) * p_size
        items = hydrated[start_idx : start_idx + p_size]

        return PaginatedResponse[ChatHistoryResponse](
            items=items,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    return hydrated

@router.post("/", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_in: ChatSessionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    branch_id = session_in.branch_id
    
    if session_in.branch_code:
        stmt = select(Branch.id).where(
            Branch.code == session_in.branch_code,
            Branch.deleted_at.is_(None)
        )
        if current_user.ecosystem:
            stmt = stmt.where(func.lower(Branch.ecosystem) == current_user.ecosystem.lower())
        result = await db.execute(stmt)
        resolved_id = result.scalar_one_or_none()
        if not resolved_id:
            raise HTTPException(
                status_code=404, 
                detail=f"Branch with code '{session_in.branch_code}' not found in ecosystem '{current_user.ecosystem or 'default'}'"
            )
        branch_id = resolved_id
    elif session_in.cis_branch_id is not None:
        try:
            ext_id = int(session_in.cis_branch_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid CIS branch ID format")
        stmt = select(Branch.id).where(
            Branch.external_id == ext_id,
            Branch.deleted_at.is_(None)
        )
        if current_user.ecosystem:
            stmt = stmt.where(func.lower(Branch.ecosystem) == current_user.ecosystem.lower())
        result = await db.execute(stmt)
        resolved_id = result.scalar_one_or_none()
        if not resolved_id:
            raise HTTPException(
                status_code=404, 
                detail=f"Branch with external CIS ID '{session_in.cis_branch_id}' not found in ecosystem '{current_user.ecosystem or 'default'}'"
            )
        branch_id = resolved_id
        
    if not branch_id:
        raise HTTPException(status_code=400, detail="Either branch_code, cis_branch_id, or branch_id must be provided")

    # Fetch configured time limit
    stmt_config = select(AppConfig.value).where(AppConfig.key == "TIME_LIMIT_PER_SESSION")
    result_config = await db.execute(stmt_config)
    time_limit_str = result_config.scalar_one_or_none()
    default_idle_timeout = int(os.environ.get("CHAT_SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    try:
        time_limit_minutes = int(time_limit_str) if time_limit_str else default_idle_timeout
    except ValueError:
        time_limit_minutes = default_idle_timeout

    # Look for existing active session
    stmt_active = select(ChatSession).where(
        ChatSession.user_id == current_user.id,
        ChatSession.branch_id == branch_id,
        ChatSession.status == ChatStatus.ACTIVE
    ).order_by(ChatSession.updated_at.desc())
    result_active = await db.execute(stmt_active)
    active_sessions = result_active.scalars().all()

    valid_session = None
    now = datetime.now(timezone.utc)

    for sess in active_sessions:
        session_updated_at = sess.updated_at.replace(tzinfo=timezone.utc) if sess.updated_at.tzinfo is None else sess.updated_at
        
        # If we haven't found a valid session yet, and this one is not expired, keep it
        if not valid_session and (now - session_updated_at <= timedelta(minutes=time_limit_minutes)):
            valid_session = sess
        else:
            # Otherwise, close it (it's either expired, or a duplicate older active session)
            sess.status = ChatStatus.CLOSED
            db.add(sess)
            background_tasks.add_task(summarize_chat_session, sess.id)

    allow_attachments = await _is_file_attachments_allowed(db)
    if valid_session:
        await db.commit()
        setattr(valid_session, "allow_file_attachments", allow_attachments)
        return valid_session

    session = ChatSession(
        user_id=current_user.id,
        branch_id=branch_id
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    setattr(session, "allow_file_attachments", allow_attachments)
    return session

@router.put("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: uuid.UUID,
    session_in: ChatSessionUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    )
        
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    update_data = session_in.model_dump(exclude_unset=True)
    status_changed_to_closed = False
    
    for field, value in update_data.items():
        if field == "status" and value == ChatStatus.CLOSED and session.status != ChatStatus.CLOSED:
            status_changed_to_closed = True
        setattr(session, field, value)
        
    await db.commit()
    await db.refresh(session)
    
    if status_changed_to_closed:
        background_tasks.add_task(summarize_chat_session, session.id)
        
    # Broadcast event if any feedback, rating, or issue is provided
    if session_in.feedback or session_in.rating or session_in.has_data_issue:
        from app.core.broadcaster import broadcaster
        await broadcaster.publish("feedback_submitted")
        
    setattr(session, "allow_file_attachments", await _is_file_attachments_allowed(db))
    return session

@router.get("/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    if not await has_chats_read_access(current_user, db):
        stmt = stmt.where(ChatSession.user_id == current_user.id)
    
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    return await _hydrate_chat_session(session, db)

@router.get("/{session_id}/messages", response_model=List[ChatMessageResponse])
async def list_chat_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
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
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "image/jpeg",
    "image/png",
    "image/webp"
}

@router.post("/{session_id}/messages", status_code=status.HTTP_201_CREATED)
async def create_chat_message(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    db: AsyncSession = Depends(get_db),
    role: str = Form(...),
    content: str = Form(...),
    files: Optional[List[UploadFile]] = File(None)
):
    # Verify access to session - message creation is only allowed for the session owner
    stmt_session = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    )
    
    result_session = await db.execute(stmt_session)
    chat_session = result_session.scalar_one_or_none()
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    if chat_session.status == ChatStatus.CLOSED:
        raise HTTPException(status_code=403, detail="Chat session is closed")

    # Enforce time limit
    stmt_config = select(AppConfig.value).where(AppConfig.key == "TIME_LIMIT_PER_SESSION")
    result_config = await db.execute(stmt_config)
    time_limit_str = result_config.scalar_one_or_none()
    default_idle_timeout = int(os.environ.get("CHAT_SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    time_limit_minutes = int(time_limit_str) if time_limit_str and str(time_limit_str).isdigit() else default_idle_timeout

    now = datetime.now(timezone.utc)
    session_updated_at = chat_session.updated_at.replace(tzinfo=timezone.utc) if chat_session.updated_at.tzinfo is None else chat_session.updated_at
    
    if now - session_updated_at > timedelta(minutes=time_limit_minutes):
        chat_session.status = ChatStatus.CLOSED
        db.add(chat_session)
        await db.commit()
        background_tasks.add_task(summarize_chat_session, chat_session.id)
        raise HTTPException(status_code=403, detail="Session expired")

    # Update session activity
    chat_session.updated_at = now
    db.add(chat_session)
        
    attachments = None
    extracted_attachment_texts = []
    if files:
        if not await _is_file_attachments_allowed(db):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File attachments are disabled by system configuration"
            )
        attachments = {}
        from app.rag.services.attachment_parser import AttachmentParser
        parser = AttachmentParser()
        for file in files:
            if file.content_type not in ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed for file {file.filename}")
            try:
                extracted_text, meta = await parser.extract_from_upload(file)
                attachments[file.filename] = {
                    "content_type": file.content_type,
                    "status": "processed",
                    "chars": meta.get("chars", len(extracted_text)),
                    "pages": meta.get("pages", 1),
                    "method": meta.get("method", "fast")
                }
                if extracted_text and not extracted_text.startswith("[Error") and not extracted_text.startswith("[Dokumen tidak"):
                    extracted_attachment_texts.append(
                        f"[Dokumen Pasien Terlampir: {file.filename}]\n{extracted_text.strip()}"
                    )
            except Exception as e:
                logger.error(f"Failed to extract attachment {file.filename}: {e}")
                attachments[file.filename] = {"content_type": file.content_type, "status": "error", "error": str(e)}

    message = ChatMessage(
        session_id=session_id,
        role=role.upper(),
        content=content,
        attachments=attachments
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    if role.lower() != "user":
        # If it's not a user message (e.g. system message), just return the saved message.
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(message))

    # Token pre-check
    allowed, reason, _ = await check_chat_token_quota(db, current_user, chat_session.branch_id)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    # Build doctor-level knowledge filter (branch, dr_type, excluded categories)
    doctor_filter = await _build_doctor_filter_metadata(db, current_user)

    # Effective query enriched with attachment text
    effective_query = content
    if extracted_attachment_texts:
        effective_query = f"{content}\n\n" + "\n\n".join(extracted_attachment_texts)

    # For user message, we stream the AI response back via SSE
    async def sse_generator():
        try:
            from app.rag.services.factory import AdapterFactory
            from app.rag.services.rag_retriever import HybridRetriever, BM25Index, Reranker
            from app.rag.services.rag_generator import GenerationPipeline
            from app.rag.config import settings as rag_settings
        except ImportError as e:
            logger.error(f"AI dependencies missing: {e}")
            yield f"data: {json.dumps({'error': 'AI configuration error'})}\n\n"
            return

        async with AsyncSessionLocal() as session:
            try:
                vector_store = AdapterFactory.get_vector_store()
                bm25_index = AdapterFactory.get_bm25_index()
                reranker = AdapterFactory.get_reranker()
                retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25_index, reranker=reranker)
                llm_adapter = await AdapterFactory.get_dynamic_llm(session)
                pipeline = GenerationPipeline(retriever=retriever, llm_adapter=llm_adapter)
                
                stmt_msg = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
                result_msg = await session.execute(stmt_msg)
                messages = result_msg.scalars().all()
                
                history = [{"role": msg.role.value.lower(), "content": msg.content} for msg in messages if msg.role.value in ["USER", "ASSISTANT"]]
                if history and history[-1]["role"] == "user":
                    history.pop()

                ai_response_text = ""
                context_chunks = []
                
                # Immediately yield keep-alive comment so reverse proxy/client connection never times out
                yield ": keep-alive\n\n"

                token_queue = asyncio.Queue()
                generator_done = asyncio.Event()

                async def keep_alive_task():
                    while not generator_done.is_set():
                        try:
                            await asyncio.wait_for(generator_done.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            if not generator_done.is_set():
                                await token_queue.put(("keep_alive", None))

                async def stream_producer():
                    try:
                        async for chunk in pipeline.generate_answer_stream(
                            query=effective_query,
                            top_k=8,
                            rerank=True,
                            history=history,
                            filter_metadata=doctor_filter or None,
                            doctor_name=current_user.name
                        ):
                            await token_queue.put(("chunk", chunk))
                    except Exception as prod_err:
                        await token_queue.put(("error", prod_err))
                    finally:
                        generator_done.set()
                        await token_queue.put(("done", None))

                producer_task = asyncio.create_task(stream_producer())
                pinger_task = asyncio.create_task(keep_alive_task())

                try:
                    while True:
                        msg_type, data = await token_queue.get()
                        if msg_type == "keep_alive":
                            if await request.is_disconnected():
                                logger.info(f"Client disconnected during keep-alive for session {session_id}")
                                break
                            yield ": keep-alive\n\n"
                        elif msg_type == "chunk":
                            if await request.is_disconnected():
                                logger.info(f"Client disconnected from chat session {session_id}")
                                break
                            chunk = data
                            if chunk.startswith('{"type": "context"'):
                                yield f"data: {chunk}\n\n"
                                try:
                                    ctx_json = json.loads(chunk)
                                    context_chunks = [c.get("content", "") for c in ctx_json.get("chunks", [])]
                                except Exception:
                                    pass
                            else:
                                ai_response_text += chunk
                                payload = json.dumps({"type": "token", "content": chunk})
                                yield f"data: {payload}\n\n"
                        elif msg_type == "error":
                            raise data
                        elif msg_type == "done":
                            break
                finally:
                    generator_done.set()
                    producer_task.cancel()
                    pinger_task.cancel()
                
                # Signal end of stream
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save the final AI message to the DB and update session activity
                ai_msg = ChatMessage(
                    session_id=session_id,
                    role="ASSISTANT",
                    content=ai_response_text
                )
                session.add(ai_msg)
                stmt_upd = update(ChatSession).where(ChatSession.id == session_id).values(updated_at=datetime.now(timezone.utc))
                await session.execute(stmt_upd)
                
                # Accurately calculate Input & Output tokens and record usage
                in_tokens = count_chat_prompt_tokens(
                    user_query=content,
                    context_chunks=context_chunks,
                    history=history
                )
                out_tokens = count_chat_completion_tokens(ai_response_text)
                
                from app.services.token_service import record_knowledge_not_found_event
                await record_chat_token_usage(
                    db=session,
                    user_id=current_user.id,
                    branch_id=chat_session.branch_id,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens
                )

                # Check if knowledge was not found for admin notification
                is_no_context = not context_chunks or len(context_chunks) == 0
                is_missing_kw = any(phrase in ai_response_text.lower() for phrase in [
                    "tidak ditemukan", "tidak tersedia", "mohon maaf", "belum ada data"
                ])
                if is_no_context or is_missing_kw:
                    await record_knowledge_not_found_event(
                        db=session,
                        user_id=current_user.id,
                        branch_id=chat_session.branch_id,
                        user_query=content
                    )

                
            except Exception as e:
                logger.error(f"Error streaming AI response: {e}")
                fallback = "Maaf, terjadi kesalahan pada pemrosesan AI."
                yield f"data: {json.dumps({'type': 'token', 'content': fallback})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                ai_msg = ChatMessage(session_id=session_id, role="ASSISTANT", content=fallback)
                session.add(ai_msg)
                await session.commit()
                
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@router.post("/{session_id}/messages/stream")
async def stream_chat_message(
    session_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    import json
    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes)
        role = data.get("role")
        content = data.get("content")
        files = None
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid JSON body")
        
    if not role or not content:
        raise HTTPException(status_code=422, detail="Missing role or content")
    
    role = role.lower()

    # Verify access to session - stream chat is only allowed for the session owner
    stmt_session = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    )
    
    result_session = await db.execute(stmt_session)
    chat_session = result_session.scalar_one_or_none()
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    if chat_session.status == ChatStatus.CLOSED:
        raise HTTPException(status_code=403, detail="Chat session is closed")

    # Enforce time limit
    stmt_config = select(AppConfig.value).where(AppConfig.key == "TIME_LIMIT_PER_SESSION")
    result_config = await db.execute(stmt_config)
    time_limit_str = result_config.scalar_one_or_none()
    default_idle_timeout = int(os.environ.get("CHAT_SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    time_limit_minutes = int(time_limit_str) if time_limit_str and str(time_limit_str).isdigit() else default_idle_timeout

    now = datetime.now(timezone.utc)
    session_updated_at = chat_session.updated_at.replace(tzinfo=timezone.utc) if chat_session.updated_at.tzinfo is None else chat_session.updated_at
    
    if now - session_updated_at > timedelta(minutes=time_limit_minutes):
        chat_session.status = ChatStatus.CLOSED
        db.add(chat_session)
        await db.commit()
        background_tasks.add_task(summarize_chat_session, chat_session.id)
        raise HTTPException(status_code=403, detail="Session expired")

    # Update session activity
    chat_session.updated_at = now
    db.add(chat_session)
        
    attachments = None
    extracted_attachment_texts = []
    if files:
        attachments = {}
        from app.rag.services.attachment_parser import AttachmentParser
        parser = AttachmentParser()
        for file in files:
            if file.content_type not in ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed for file {file.filename}")
            try:
                extracted_text, meta = await parser.extract_from_upload(file)
                attachments[file.filename] = {
                    "content_type": file.content_type,
                    "status": "processed",
                    "chars": meta.get("chars", len(extracted_text)),
                    "pages": meta.get("pages", 1),
                    "method": meta.get("method", "fast")
                }
                if extracted_text and not extracted_text.startswith("[Error") and not extracted_text.startswith("[Dokumen tidak"):
                    extracted_attachment_texts.append(
                        f"[Dokumen Pasien Terlampir: {file.filename}]\n{extracted_text.strip()}"
                    )
            except Exception as e:
                logger.error(f"Failed to extract attachment {file.filename}: {e}")
                attachments[file.filename] = {"content_type": file.content_type, "status": "error", "error": str(e)}

    message = ChatMessage(
        session_id=session_id,
        role=role.upper(),
        content=content,
        attachments=attachments
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    if role.lower() != "user":
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(message))

    # Token pre-check
    allowed, reason, _ = await check_chat_token_quota(db, current_user, chat_session.branch_id)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    # Build doctor-level knowledge filter (branch, dr_type, excluded categories)
    doctor_filter = await _build_doctor_filter_metadata(db, current_user)

    # Effective query enriched with attachment text
    effective_query = content
    if extracted_attachment_texts:
        effective_query = f"{content}\n\n" + "\n\n".join(extracted_attachment_texts)

    async def sse_generator():
        try:
            from app.rag.services.factory import AdapterFactory
            from app.rag.services.rag_retriever import HybridRetriever, BM25Index, Reranker
            from app.rag.services.rag_generator import GenerationPipeline
            from app.rag.config import settings as rag_settings
        except ImportError as e:
            logger.error(f"AI dependencies missing: {e}")
            yield f"data: {json.dumps({'error': 'AI configuration error'})}\n\n"
            return

        async with AsyncSessionLocal() as session:
            try:
                vector_store = AdapterFactory.get_vector_store()
                bm25_index = AdapterFactory.get_bm25_index()
                reranker = AdapterFactory.get_reranker()
                retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25_index, reranker=reranker)
                llm_adapter = await AdapterFactory.get_dynamic_llm(session)
                pipeline = GenerationPipeline(retriever=retriever, llm_adapter=llm_adapter)
                
                stmt_msg = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
                result_msg = await session.execute(stmt_msg)
                messages = result_msg.scalars().all()
                
                history = [{"role": msg.role.value.lower(), "content": msg.content} for msg in messages if msg.role.value in ["USER", "ASSISTANT"]]
                if history and history[-1]["role"] == "user":
                    history.pop()

                ai_response_text = ""
                context_chunks = []
                
                # Immediately yield keep-alive comment so reverse proxy/client connection never times out
                yield ": keep-alive\n\n"

                token_queue = asyncio.Queue()
                generator_done = asyncio.Event()

                async def keep_alive_task():
                    while not generator_done.is_set():
                        try:
                            await asyncio.wait_for(generator_done.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            if not generator_done.is_set():
                                await token_queue.put(("keep_alive", None))

                async def stream_producer():
                    try:
                        async for chunk in pipeline.generate_answer_stream(
                            query=effective_query,
                            top_k=5,
                            rerank=True,
                            history=history,
                            filter_metadata=doctor_filter or None,
                            doctor_name=current_user.name
                        ):
                            await token_queue.put(("chunk", chunk))
                    except Exception as prod_err:
                        await token_queue.put(("error", prod_err))
                    finally:
                        generator_done.set()
                        await token_queue.put(("done", None))

                producer_task = asyncio.create_task(stream_producer())
                pinger_task = asyncio.create_task(keep_alive_task())

                try:
                    while True:
                        msg_type, data = await token_queue.get()
                        if msg_type == "keep_alive":
                            if await request.is_disconnected():
                                logger.info(f"Client disconnected during keep-alive for session {session_id}")
                                break
                            yield ": keep-alive\n\n"
                        elif msg_type == "chunk":
                            if await request.is_disconnected():
                                logger.info(f"Client disconnected from chat session {session_id}")
                                break
                            chunk = data
                            if chunk.startswith('{"type": "context"'):
                                yield f"data: {chunk}\n\n"
                                try:
                                    ctx_json = json.loads(chunk)
                                    context_chunks = [c.get("content", "") for c in ctx_json.get("chunks", [])]
                                except Exception:
                                    pass
                            else:
                                ai_response_text += chunk
                                payload = json.dumps({"type": "token", "content": chunk})
                                yield f"data: {payload}\n\n"
                        elif msg_type == "error":
                            raise data
                        elif msg_type == "done":
                            break
                finally:
                    generator_done.set()
                    producer_task.cancel()
                    pinger_task.cancel()
                
                # Signal end of stream
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Save the final AI message to the DB and update session activity
                ai_msg = ChatMessage(
                    session_id=session_id,
                    role="ASSISTANT",
                    content=ai_response_text
                )
                session.add(ai_msg)
                stmt_upd = update(ChatSession).where(ChatSession.id == session_id).values(updated_at=datetime.now(timezone.utc))
                await session.execute(stmt_upd)
                
                # Accurately calculate Input & Output tokens and record usage
                in_tokens = count_chat_prompt_tokens(
                    user_query=content,
                    context_chunks=context_chunks,
                    history=history
                )
                out_tokens = count_chat_completion_tokens(ai_response_text)
                
                await record_chat_token_usage(
                    db=session,
                    user_id=current_user.id,
                    branch_id=chat_session.branch_id,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens
                )

                # Trigger ChatGPT/Gemini-style title generation in background if title not yet generated
                if not chat_session.summary or chat_session.summary == "Percakapan Baru":
                    from app.services.chat_title_service import generate_and_save_chat_title
                    asyncio.create_task(generate_and_save_chat_title(session_id, content, ai_response_text))
                
            except Exception as e:
                logger.error(f"Error streaming AI response: {e}")
                fallback = "Maaf, terjadi kesalahan pada pemrosesan AI."
                yield f"data: {json.dumps({'type': 'token', 'content': fallback})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                ai_msg = ChatMessage(session_id=session_id, role="ASSISTANT", content=fallback)
                session.add(ai_msg)
                await session.commit()
                
    return EventSourceResponse(sse_generator())
