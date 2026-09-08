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

async def _hydrate_branch(branch: Branch, db: AsyncSession) -> dict:
    branch_dict = {
        "id": branch.id,
        "name": branch.name,
        "address": branch.address,
        "latitude": branch.latitude,
        "longitude": branch.longitude,
        "image_url": branch.image_url,
        "token_limit": branch.token_limit,
        "created_at": branch.created_at,
        "updated_at": branch.updated_at,
        "tokensMonth": branch.token_limit,
        "used": 0,
        "remaining": branch.token_limit,
        "doctors": []
    }
    
    # Get doctors assigned to this branch
    stmt = select(User).join(UserBranch, UserBranch.user_id == User.id).where(UserBranch.branch_id == branch.id, User.type == UserType.DOCTOR, User.deleted_at.is_(None))
    result = await db.execute(stmt)
    doctors = result.scalars().all()
    
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    
    branch_used = 0
    
    for doc in doctors:
        # Get tokens used
        stmt_token = select(func.sum(UserTokenUsage.tokens_used)).where(UserTokenUsage.user_id == doc.id, UserTokenUsage.year_month == current_ym)
        result_token = await db.execute(stmt_token)
        tokens_used = result_token.scalar() or 0
        
        branch_used += tokens_used
        
        # Get speciality
        stmt_cat = select(Category).where(
            Category.deleted_at.is_(None),
            ~Category.id.in_(
                select(UserCategoryExclusion.category_id).where(UserCategoryExclusion.user_id == doc.id)
            )
        )
        result_cat = await db.execute(stmt_cat)
        cat = result_cat.scalar() # just get first category
        speciality = cat.name if cat else ""
        
        status = "Active"
        tokens_left = (doc.token_limit or 0) - tokens_used
        if tokens_left < 0: tokens_left = 0
        
        if doc.token_limit and doc.token_limit > 0 and tokens_used >= doc.token_limit * 0.9:
            status = "Warning"
            
        branch_dict["doctors"].append({
            "id": doc.id,
            "name": doc.name,
            "speciality": speciality,
            "tokensLeft": tokens_left,
            "status": status,
            "maxTokens": doc.token_limit or 0
        })
        
    branch_dict["used"] = branch_used
    branch_dict["remaining"] = max(0, branch.token_limit - branch_used)
    
    return branch_dict

@router.get("/", response_model=List[BranchResponse])
async def list_branches(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:read"))
):
    stmt = select(Branch).where(Branch.deleted_at.is_(None))
    result = await db.execute(stmt)
    branches = result.scalars().all()
    return [await _hydrate_branch(b, db) for b in branches]

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

@router.post("/", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    branch_in: BranchCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:write"))
):
    branch = Branch(**branch_in.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
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
        
    update_data = branch_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(branch, field, value)
        
    await db.commit()
    await db.refresh(branch)
    return await _hydrate_branch(branch, db)

@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("branches:write"))
):
    stmt = select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    result = await db.execute(stmt)
    branch = result.scalar_one_or_none()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    branch.deleted_at = datetime.now(timezone.utc)
    await db.commit()
