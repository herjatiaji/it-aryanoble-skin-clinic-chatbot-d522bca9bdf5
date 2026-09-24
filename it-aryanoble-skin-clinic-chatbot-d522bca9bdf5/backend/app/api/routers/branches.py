from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User, UserType, UserTokenUsage
from app.models.branch import Branch, UserBranch
from app.models.category import Category, UserCategoryExclusion
from app.schemas.branch import BranchCreate, BranchUpdate, BranchResponse
from datetime import datetime, timezone

router = APIRouter(tags=["Branches"])

from collections import defaultdict
from app.models.config import AppConfig

async def _hydrate_branches_batch(branches: List[Branch], db: AsyncSession) -> List[dict]:
    if not branches:
        return []

    branch_ids = [b.id for b in branches]
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")

    # 1. Batch fetch system configuration flags
    config_keys = [
        "GLOBAL_TOKEN_LIMIT_ACTIVE",
        "GLOBAL_BRANCH_LIMIT_ACTIVE",
        "GLOBAL_TOKEN_LIMIT",
        "GLOBAL_SPKK_LIMIT_ACTIVE",
        "GLOBAL_GP_LIMIT_ACTIVE",
        "TOKEN_LIMIT_SPKK",
        "TOKEN_LIMIT_GP"
    ]
    cfg_stmt = select(AppConfig.key, AppConfig.value).where(AppConfig.key.in_(config_keys))
    cfg_res = await db.execute(cfg_stmt)
    cfg_map = {k: v for k, v in cfg_res.all()}

    is_global_mode = (cfg_map.get("GLOBAL_TOKEN_LIMIT_ACTIVE") or "false").lower() == "true"
    is_branch_global_active = is_global_mode and ((cfg_map.get("GLOBAL_BRANCH_LIMIT_ACTIVE") or "false").lower() == "true")
    is_spkk_global_active = is_global_mode and ((cfg_map.get("GLOBAL_SPKK_LIMIT_ACTIVE") or "false").lower() == "true")
    is_gp_global_active = is_global_mode and ((cfg_map.get("GLOBAL_GP_LIMIT_ACTIVE") or "false").lower() == "true")

    gl_val = cfg_map.get("GLOBAL_TOKEN_LIMIT")
    global_branch_limit_val = int(gl_val) if (gl_val and gl_val.isdigit() and int(gl_val) > 0) else 3000000

    spkk_val = cfg_map.get("TOKEN_LIMIT_SPKK")
    spkk_token_limit = int(spkk_val) if (spkk_val and spkk_val.isdigit()) else 500000

    gp_val = cfg_map.get("TOKEN_LIMIT_GP")
    gp_token_limit = int(gp_val) if (gp_val and gp_val.isdigit()) else 250000

    # 2. Batch fetch branch tokens used
    stmt_branch_used = (
        select(UserTokenUsage.branch_id, func.sum(UserTokenUsage.tokens_used))
        .where(UserTokenUsage.branch_id.in_(branch_ids), UserTokenUsage.year_month == current_ym)
        .group_by(UserTokenUsage.branch_id)
    )
    branch_used_res = await db.execute(stmt_branch_used)
    branch_used_map = {bid: (used or 0) for bid, used in branch_used_res.all()}

    # 3. Batch fetch all assigned doctors across branches
    doc_stmt = (
        select(UserBranch.branch_id, User)
        .join(UserBranch, UserBranch.user_id == User.id)
        .where(
            UserBranch.branch_id.in_(branch_ids),
            UserBranch.status == 1,
            UserBranch.deleted_at.is_(None),
            User.type == UserType.DOCTOR,
            User.deleted_at.is_(None)
        )
    )
    doc_res = await db.execute(doc_stmt)
    branch_docs_map = defaultdict(list)
    all_doctor_ids = set()
    for bid, doc in doc_res.all():
        branch_docs_map[bid].append(doc)
        all_doctor_ids.add(doc.id)

    # 4. Batch fetch doctor token usages per branch
    doc_tokens_map = {}
    if all_doctor_ids:
        dt_stmt = (
            select(UserTokenUsage.user_id, UserTokenUsage.branch_id, func.sum(UserTokenUsage.tokens_used))
            .where(
                UserTokenUsage.user_id.in_(list(all_doctor_ids)),
                UserTokenUsage.branch_id.in_(branch_ids),
                UserTokenUsage.year_month == current_ym
            )
            .group_by(UserTokenUsage.user_id, UserTokenUsage.branch_id)
        )
        dt_res = await db.execute(dt_stmt)
        for uid, bid, used in dt_res.all():
            doc_tokens_map[(uid, bid)] = used or 0

        # Batch fetch doctor exclusions & categories
        excl_stmt = select(UserCategoryExclusion.user_id, UserCategoryExclusion.category_id).where(
            UserCategoryExclusion.user_id.in_(list(all_doctor_ids))
        )
        excl_res = await db.execute(excl_stmt)
        user_excl_map = defaultdict(set)
        for uid, cid in excl_res.all():
            user_excl_map[uid].add(cid)
    else:
        user_excl_map = defaultdict(set)

    all_cats = (await db.execute(select(Category.id, Category.name).where(Category.deleted_at.is_(None)))).all()

    # Hydrate each branch
    hydrated = []
    for branch in branches:
        has_custom_limit = getattr(branch, "has_custom_limit", False) is True

        if has_custom_limit:
            effective_branch_limit = branch.token_limit
        elif is_branch_global_active:
            effective_branch_limit = global_branch_limit_val
        else:
            effective_branch_limit = branch.token_limit or 0

        branch_used = branch_used_map.get(branch.id, 0)
        remaining = max(0, (effective_branch_limit or 0) - branch_used)

        branch_dict = {
            "id": branch.id,
            "external_id": branch.external_id,
            "name": branch.name,
            "code": branch.code,
            "ecosystem": branch.ecosystem,
            "token_limit": effective_branch_limit,
            "tokensMonth": effective_branch_limit,
            "has_custom_limit": has_custom_limit,
            "created_at": branch.created_at,
            "updated_at": branch.updated_at,
            "used": branch_used,
            "remaining": remaining,
            "doctors": []
        }

        doctors = branch_docs_map.get(branch.id, [])
        for doc in doctors:
            doc_tokens_used = doc_tokens_map.get((doc.id, branch.id), 0)

            # Resolve speciality (first non-excluded category)
            excluded_cids = user_excl_map.get(doc.id, set())
            speciality = next((cname for cid, cname in all_cats if cid not in excluded_cids), "")

            status_str = "Active"
            dr_type_clean = (doc.dr_type or "").upper()
            is_spkk_doc = any(k in dr_type_clean for k in ["SPDVE", "SP.DVE", "SPKK", "SP.KK", "SPDV"])
            is_gp_doc = any(k in dr_type_clean for k in ["GP", "GP PLUS", "UMUM"])

            if doc.token_limit and doc.token_limit > 0:
                max_tokens = doc.token_limit
                tokens_left = max(0, max_tokens - doc_tokens_used)
                if doc_tokens_used >= max_tokens * 0.9:
                    status_str = "Warning"
            elif is_spkk_doc and is_spkk_global_active:
                max_tokens = spkk_token_limit
                tokens_left = max(0, max_tokens - doc_tokens_used)
                if doc_tokens_used >= max_tokens * 0.9:
                    status_str = "Warning"
            elif is_gp_doc and is_gp_global_active:
                max_tokens = gp_token_limit
                tokens_left = max(0, max_tokens - doc_tokens_used)
                if doc_tokens_used >= max_tokens * 0.9:
                    status_str = "Warning"
            else:
                max_tokens = effective_branch_limit or 0
                tokens_left = max(0, (effective_branch_limit or 0) - branch_used)
                if doc.token_limit and doc.token_limit > 0 and doc_tokens_used >= doc.token_limit * 0.9:
                    status_str = "Warning"

            if branch_used >= (effective_branch_limit or 1) * 0.9 and (effective_branch_limit or 0) > 0:
                status_str = "Warning"

            branch_dict["doctors"].append({
                "id": doc.id,
                "name": doc.name,
                "speciality": speciality,
                "tokensLeft": tokens_left,
                "tokens_used": doc_tokens_used,
                "status": status_str,
                "maxTokens": max_tokens,
                "employee_id": doc.employee_id,
                "dr_type": doc.dr_type,
                "user_type_code": doc.user_type_code,
                "ecosystem": doc.ecosystem
            })

        hydrated.append(branch_dict)

    return hydrated

async def _hydrate_branch(branch: Branch, db: AsyncSession) -> dict:
    hydrated = await _hydrate_branches_batch([branch], db)
    return hydrated[0] if hydrated else {}

from app.schemas.pagination import PaginatedResponse
from typing import List, Optional, Union
from fastapi import Query
import math

@router.get("/", response_model=Union[PaginatedResponse[BranchResponse], List[BranchResponse]])
async def list_branches(
    search: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:read"))
):
    stmt = select(Branch).where(Branch.deleted_at.is_(None))
    if search:
        s_clean = f"%{search.strip()}%"
        stmt = stmt.where(
            (Branch.name.ilike(s_clean)) |
            (Branch.code.ilike(s_clean)) |
            (Branch.ecosystem.ilike(s_clean))
        )
    stmt = stmt.order_by(Branch.name.asc())

    if page is not None:
        p_size = page_size or 10
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0
        total_pages = max(1, math.ceil(total / p_size))

        paginated_stmt = stmt.offset((page - 1) * p_size).limit(p_size)
        result = await db.execute(paginated_stmt)
        branches = result.scalars().all()
        hydrated = await _hydrate_branches_batch(list(branches), db)

        return PaginatedResponse[BranchResponse](
            items=hydrated,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    result = await db.execute(stmt)
    branches = result.scalars().all()
    return await _hydrate_branches_batch(list(branches), db)


@router.get("/{branch_id}", response_model=BranchResponse)
async def get_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:read"))
):
    stmt = select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    result = await db.execute(stmt)
    branch = result.scalar_one_or_none()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    return await _hydrate_branch(branch, db)



@router.put("/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: uuid.UUID,
    branch_in: BranchUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:write"))
):
    stmt = select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    result = await db.execute(stmt)
    branch = result.scalar_one_or_none()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    if branch_in.reset_to_global:
        branch.has_custom_limit = False
        branch.token_limit = 0
    elif branch_in.has_custom_limit is not None:
        branch.has_custom_limit = branch_in.has_custom_limit
        if branch_in.token_limit is not None:
            branch.token_limit = branch_in.token_limit
    elif branch_in.token_limit is not None:
        branch.token_limit = branch_in.token_limit
        branch.has_custom_limit = True

    if branch_in.name is not None:
        branch.name = branch_in.name
        
    await db.commit()
    await db.refresh(branch)
    return await _hydrate_branch(branch, db)


