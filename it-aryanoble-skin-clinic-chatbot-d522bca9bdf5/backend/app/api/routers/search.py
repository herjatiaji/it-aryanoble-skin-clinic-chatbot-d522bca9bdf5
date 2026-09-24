import uuid
import re
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func, or_, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies import get_current_user_flexible
from app.models.user import User, UserType, Access, RoleAccess, UserRole
from app.models.knowledge import Knowledge, KnowledgeChunk, KnowledgeCategory
from app.models.category import Category
from app.models.project import Project
from app.models.chat import ChatSession, ChatMessage, ChatRole
from app.models.branch import Branch
from app.schemas.search import (
    UnifiedSearchResponse,
    KnowledgeSearchResult,
    ProjectSearchResult,
    CategorySearchResult,
    ChatSearchResult
)

router = APIRouter(tags=["search"])

def extract_snippet(text: Optional[str], query: str, max_chars: int = 150) -> Optional[str]:
    if not text:
        return None
    clean_text = " ".join(text.split())
    if not query or not query.strip():
        return clean_text[:max_chars] + ("..." if len(clean_text) > max_chars else "")
    
    q_words = [re.escape(w) for w in query.strip().split() if len(w.strip()) > 1]
    if not q_words:
        q_words = [re.escape(w) for w in query.strip().split() if w.strip()]
    
    if not q_words:
        return clean_text[:max_chars] + ("..." if len(clean_text) > max_chars else "")
    
    pattern = re.compile(r"(" + "|".join(q_words) + r")", re.IGNORECASE)
    match = pattern.search(clean_text)
    if not match:
        return clean_text[:max_chars] + ("..." if len(clean_text) > max_chars else "")
    
    start_pos = match.start()
    half = max_chars // 2
    snip_start = max(0, start_pos - half)
    snip_end = min(len(clean_text), start_pos + half)
    
    if snip_start > 0:
        space_idx = clean_text.find(" ", snip_start)
        if space_idx != -1 and space_idx < start_pos:
            snip_start = space_idx + 1
    if snip_end < len(clean_text):
        space_idx = clean_text.rfind(" ", start_pos, snip_end)
        if space_idx != -1 and space_idx > start_pos:
            snip_end = space_idx
            
    snippet = clean_text[snip_start:snip_end].strip()
    if snip_start > 0:
        snippet = "..." + snippet
    if snip_end < len(clean_text):
        snippet = snippet + "..."
    return snippet


async def has_chats_read_access(user: User, db: AsyncSession) -> bool:
    if user.type != UserType.STAFF:
        return False
    stmt = (
        select(Access.name)
        .join(RoleAccess, RoleAccess.access_id == Access.id)
        .join(UserRole, UserRole.role_id == RoleAccess.role_id)
        .where(UserRole.user_id == user.id)
    )
    result = await db.execute(stmt)
    return "chats:read" in result.scalars().all()


@router.get("/", response_model=UnifiedSearchResponse)
async def unified_search(
    q: str = Query(..., min_length=1, description="Search query string"),
    category: str = Query("all", description="Search category filter: all, knowledge, projects, categories, chats"),
    limit: int = Query(10, ge=1, le=50, description="Max results per category"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    query_str = q.strip()
    if not query_str:
        return UnifiedSearchResponse(query="", total_results=0, knowledge=[], projects=[], categories=[], chats=[])

    words = [w for w in query_str.split() if w.strip()]
    search_pattern = f"%{query_str}%"
    
    knowledge_results: List[KnowledgeSearchResult] = []
    project_results: List[ProjectSearchResult] = []
    category_results: List[CategorySearchResult] = []
    chat_results: List[ChatSearchResult] = []

    search_all = category == "all"
    search_knowledge = search_all or category == "knowledge"
    search_projects = search_all or category == "projects"
    search_categories = search_all or category == "categories"
    search_chats = search_all or category == "chats"

    # -------------------------------------------------------------
    # 1. Search Projects
    # -------------------------------------------------------------
    if search_projects:
        proj_filters = []
        for w in words:
            proj_filters.append(
                or_(
                    Project.name.ilike(f"%{w}%"),
                    Project.description.ilike(f"%{w}%")
                )
            )

        stmt_proj = (
            select(Project)
            .where(
                Project.deleted_at.is_(None),
                or_(
                    Project.name.ilike(search_pattern),
                    Project.description.ilike(search_pattern),
                    and_(*proj_filters) if proj_filters else False
                )
            )
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        res_proj = await db.execute(stmt_proj)
        projects = res_proj.scalars().all()

        for p in projects:
            count_stmt = select(func.count(Knowledge.id)).where(
                Knowledge.project_id == p.id,
                Knowledge.deleted_at.is_(None)
            )
            count_res = await db.execute(count_stmt)
            doc_count = count_res.scalar() or 0

            project_results.append(
                ProjectSearchResult(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    document_count=doc_count,
                    created_at=p.created_at
                )
            )

    # -------------------------------------------------------------
    # 2. Search Categories
    # -------------------------------------------------------------
    if search_categories:
        cat_filters = []
        for w in words:
            cat_filters.append(
                or_(
                    Category.name.ilike(f"%{w}%"),
                    Category.description.ilike(f"%{w}%")
                )
            )

        stmt_cat = (
            select(Category)
            .where(
                Category.deleted_at.is_(None),
                or_(
                    Category.name.ilike(search_pattern),
                    Category.description.ilike(search_pattern),
                    and_(*cat_filters) if cat_filters else False
                )
            )
            .order_by(Category.updated_at.desc())
            .limit(limit)
        )
        res_cat = await db.execute(stmt_cat)
        categories_found = res_cat.scalars().all()

        for c in categories_found:
            count_stmt = (
                select(func.count(KnowledgeCategory.knowledge_id))
                .join(Knowledge, Knowledge.id == KnowledgeCategory.knowledge_id)
                .where(
                    KnowledgeCategory.category_id == c.id,
                    Knowledge.deleted_at.is_(None)
                )
            )
            count_res = await db.execute(count_stmt)
            k_count = count_res.scalar() or 0

            category_results.append(
                CategorySearchResult(
                    id=c.id,
                    name=c.name,
                    description=c.description,
                    knowledge_count=k_count,
                    created_at=c.created_at
                )
            )

    # -------------------------------------------------------------
    # 3. Search Knowledge Base (Metadata + Chunk Content)
    # -------------------------------------------------------------
    if search_knowledge:
        # Multi-word matching conditions for chunks
        chunk_filters = [KnowledgeChunk.content.ilike(f"%{w}%") for w in words]
        chunk_match_subquery = (
            select(distinct(KnowledgeChunk.knowledge_id))
            .where(and_(*chunk_filters))
        )

        # Multi-word matching conditions across title/summary/filename/chunks
        k_word_clauses = []
        for w in words:
            w_pat = f"%{w}%"
            k_word_clauses.append(
                or_(
                    Knowledge.title.ilike(w_pat),
                    Knowledge.ai_summary.ilike(w_pat),
                    Knowledge.file_name.ilike(w_pat),
                    Knowledge.id.in_(
                        select(distinct(KnowledgeChunk.knowledge_id)).where(KnowledgeChunk.content.ilike(w_pat))
                    ),
                    Knowledge.project_id.in_(
                        select(Project.id).where(Project.name.ilike(w_pat))
                    ),
                    Knowledge.id.in_(
                        select(KnowledgeCategory.knowledge_id).join(Category, Category.id == KnowledgeCategory.category_id).where(Category.name.ilike(w_pat))
                    )
                )
            )

        stmt_k = (
            select(Knowledge)
            .where(
                Knowledge.deleted_at.is_(None),
                or_(
                    Knowledge.title.ilike(search_pattern),
                    Knowledge.ai_summary.ilike(search_pattern),
                    Knowledge.file_name.ilike(search_pattern),
                    Knowledge.id.in_(chunk_match_subquery),
                    and_(*k_word_clauses) if k_word_clauses else False
                )
            )
            .order_by(Knowledge.updated_at.desc())
            .limit(limit)
        )

        res_k = await db.execute(stmt_k)
        knowledge_items = res_k.scalars().all()

        for k in knowledge_items:
            cat_stmt = (
                select(Category.name)
                .join(KnowledgeCategory, KnowledgeCategory.category_id == Category.id)
                .where(KnowledgeCategory.knowledge_id == k.id)
            )
            cat_res = await db.execute(cat_stmt)
            categories = list(cat_res.scalars().all())

            project_name = None
            if k.project_id:
                proj_stmt = select(Project.name).where(Project.id == k.project_id)
                proj_res = await db.execute(proj_stmt)
                project_name = proj_res.scalar_one_or_none()

            match_field = "chunk_content"
            snippet = None

            q_lower = query_str.lower()
            if any(w.lower() in (k.title or "").lower() for w in words):
                match_field = "title"
                snippet = extract_snippet(k.ai_summary or k.title, query_str)
            elif k.ai_summary and any(w.lower() in k.ai_summary.lower() for w in words):
                match_field = "summary"
                snippet = extract_snippet(k.ai_summary, query_str)
            elif any(w.lower() in (k.file_name or "").lower() for w in words):
                match_field = "file_name"
                snippet = extract_snippet(k.file_name, query_str)
            elif project_name and any(w.lower() in project_name.lower() for w in words):
                match_field = "project"
                snippet = f"Part of project: {project_name}"
            elif categories and any(any(w.lower() in c.lower() for w in words) for c in categories):
                match_field = "category"
                snippet = f"Categorized under: {', '.join(categories)}"
            else:
                chunk_stmt = (
                    select(KnowledgeChunk.content)
                    .where(
                        KnowledgeChunk.knowledge_id == k.id,
                        or_(*[KnowledgeChunk.content.ilike(f"%{w}%") for w in words])
                    )
                    .limit(1)
                )
                chunk_res = await db.execute(chunk_stmt)
                matched_chunk_content = chunk_res.scalar_one_or_none()
                if matched_chunk_content:
                    match_field = "chunk_content"
                    snippet = extract_snippet(matched_chunk_content, query_str)
                else:
                    match_field = "title"
                    snippet = extract_snippet(k.ai_summary or k.title, query_str)

            knowledge_results.append(
                KnowledgeSearchResult(
                    id=k.id,
                    title=k.title,
                    type=k.type.value if hasattr(k.type, "value") else str(k.type),
                    categories=categories,
                    project_name=project_name,
                    project_id=k.project_id,
                    file_name=k.file_name,
                    snippet=snippet,
                    match_field=match_field,
                    status=k.status.value if hasattr(k.status, "value") else str(k.status),
                    created_at=k.created_at
                )
            )

    # -------------------------------------------------------------
    # 4. Search Chat History (Sessions + Inside Messages)
    # -------------------------------------------------------------
    if search_chats:
        has_access = await has_chats_read_access(current_user, db)
        
        msg_filters = [ChatMessage.content.ilike(f"%{w}%") for w in words]
        msg_match_subquery = (
            select(distinct(ChatMessage.session_id))
            .where(and_(*msg_filters) if msg_filters else ChatMessage.content.ilike(search_pattern))
        )

        user_match_subquery = (
            select(distinct(User.id))
            .where(or_(*[User.name.ilike(f"%{w}%") for w in words]))
        )

        stmt_chat = (
            select(ChatSession)
            .where(
                or_(
                    ChatSession.summary.ilike(search_pattern),
                    ChatSession.feedback.ilike(search_pattern),
                    ChatSession.id.in_(msg_match_subquery),
                    ChatSession.user_id.in_(user_match_subquery),
                    *[ChatSession.summary.ilike(f"%{w}%") for w in words]
                )
            )
        )

        if not has_access:
            stmt_chat = stmt_chat.where(ChatSession.user_id == current_user.id)

        stmt_chat = stmt_chat.order_by(ChatSession.updated_at.desc()).limit(limit)

        res_chat = await db.execute(stmt_chat)
        chat_sessions = res_chat.scalars().all()

        session_ids = [s.id for s in chat_sessions]
        user_ids = list({s.user_id for s in chat_sessions if s.user_id})
        branch_ids = list({s.branch_id for s in chat_sessions if s.branch_id})

        # Batch fetch users
        user_map = {}
        if user_ids:
            u_stmt = select(User.id, User.name).where(User.id.in_(user_ids))
            for uid, uname in (await db.execute(u_stmt)).all():
                user_map[uid] = uname or "Unknown"

        # Batch fetch branches
        branch_map = {}
        if branch_ids:
            b_stmt = select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids))
            for bid, bname in (await db.execute(b_stmt)).all():
                branch_map[bid] = bname or "Unknown Branch"

        # Batch fetch message counts
        count_map = {}
        if session_ids:
            cnt_stmt = select(ChatMessage.session_id, func.count(ChatMessage.id)).where(ChatMessage.session_id.in_(session_ids)).group_by(ChatMessage.session_id)
            for sid, c in (await db.execute(cnt_stmt)).all():
                count_map[sid] = c

        # Batch fetch first messages
        first_msg_map = {}
        needed_first_msg_sids = [s.id for s in chat_sessions if not (s.summary and s.summary.strip())]
        if needed_first_msg_sids:
            f_stmt = (
                select(ChatMessage.session_id, ChatMessage.content, ChatMessage.role)
                .where(ChatMessage.session_id.in_(needed_first_msg_sids))
                .order_by(ChatMessage.session_id, ChatMessage.created_at.asc())
            )
            for sid, content, role in (await db.execute(f_stmt)).all():
                if sid not in first_msg_map:
                    first_msg_map[sid] = content
                elif role == ChatRole.USER and first_msg_map.get(f"{sid}_role") != ChatRole.USER:
                    first_msg_map[sid] = content
                    first_msg_map[f"{sid}_role"] = ChatRole.USER

        # Batch fetch matched messages
        matched_msg_map = {}
        if session_ids and words:
            m_stmt = (
                select(ChatMessage.session_id, ChatMessage.role, ChatMessage.content)
                .where(
                    ChatMessage.session_id.in_(session_ids),
                    or_(*[ChatMessage.content.ilike(f"%{w}%") for w in words])
                )
                .order_by(ChatMessage.session_id, ChatMessage.created_at.asc())
            )
            for sid, m_role, m_content in (await db.execute(m_stmt)).all():
                if sid not in matched_msg_map:
                    matched_msg_map[sid] = (m_role, m_content)

        from app.services.chat_title_service import sanitize_llm_title, clean_heuristic_title

        for session in chat_sessions:
            msg_count = count_map.get(session.id, 0)
            doctor_name = user_map.get(session.user_id, "Unknown")
            branch_name = branch_map.get(session.branch_id, "General Prompt" if not session.branch_id else "Unknown Branch")

            first_msg_content = first_msg_map.get(session.id)
            if session.summary and session.summary.strip():
                title = sanitize_llm_title(session.summary)
            else:
                title = clean_heuristic_title(first_msg_content) if first_msg_content else "Percakapan Baru"

            match_role = "SUMMARY"
            snippet = None

            matched_msg_row = matched_msg_map.get(session.id)
            if matched_msg_row:
                raw_role, raw_content = matched_msg_row
                match_role = raw_role.value if hasattr(raw_role, "value") else str(raw_role).upper()
                snippet = extract_snippet(raw_content, query_str)
            elif session.summary and any(w.lower() in session.summary.lower() for w in words):
                match_role = "SUMMARY"
                snippet = extract_snippet(session.summary, query_str)
            else:
                snippet = extract_snippet(first_msg_content or session.summary, query_str)


            chat_results.append(
                ChatSearchResult(
                    id=session.id,
                    title=title,
                    doctor_name=doctor_name,
                    branch_name=branch_name,
                    session_type=session.session_type,
                    message_count=msg_count,
                    snippet=snippet,
                    match_role=match_role,
                    created_at=session.created_at,
                    updated_at=session.updated_at
                )
            )

    total_results = len(knowledge_results) + len(project_results) + len(category_results) + len(chat_results)

    return UnifiedSearchResponse(
        query=query_str,
        total_results=total_results,
        knowledge=knowledge_results,
        projects=project_results,
        categories=category_results,
        chats=chat_results
    )
