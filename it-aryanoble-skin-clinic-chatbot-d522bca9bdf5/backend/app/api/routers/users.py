from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User, UserType, Role, UserRole, UserTokenUsage
from app.models.branch import Branch, UserBranch
from app.models.category import Category, UserCategoryExclusion
from app.schemas.user import (
    UserResponse, UserCreateStaff, StaffUpdate, DoctorUpdate,
    UserUpdateRoles, UserUpdateCategories, UserUpdateAccesses
)
from datetime import datetime, timezone
from app.core.security import get_password_hash

router = APIRouter(prefix="/users", tags=["users"])

# Helper function to hydrate a user with relationships
async def _hydrate_user(user: User, db: AsyncSession) -> dict:
    user_dict = {
        "id": user.id,
        "type": user.type,
        "email": user.email,
        "name": user.name,
        "cis_id": user.cis_id,
        "token_limit": user.token_limit,
        "employee_id": user.employee_id,
        "dr_type": user.dr_type,
        "ecosystem": user.ecosystem,
        "created_at": user.created_at,
        "status": "Inactive" if user.deleted_at else "Active",
        "roles": [],
        "branches": [],
        "categories": [],
        "tokens_used": 0
    }
    
    if user.type == UserType.STAFF:
        from app.models.user import RoleAccess, Access
        
        stmt = select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
        result = await db.execute(stmt)
        roles = result.scalars().all()
        user_dict["roles"] = [{"id": r.id, "name": r.name} for r in roles]
        
        stmt_acc = (
            select(Access.name)
            .join(RoleAccess, RoleAccess.access_id == Access.id)
            .join(UserRole, UserRole.role_id == RoleAccess.role_id)
            .where(UserRole.user_id == user.id)
        )
        result_acc = await db.execute(stmt_acc)
        user_dict["accesses"] = list(result_acc.scalars().all())
        
    elif user.type == UserType.DOCTOR:
        stmt_branch = select(Branch).join(UserBranch, UserBranch.branch_id == Branch.id).where(UserBranch.user_id == user.id)
        result_branch = await db.execute(stmt_branch)
        branches = result_branch.scalars().all()
        user_dict["branches"] = [{"id": b.id, "name": b.name, "address": b.address, "latitude": b.latitude, "longitude": b.longitude, "image_url": b.image_url, "token_limit": b.token_limit, "created_at": b.created_at, "updated_at": b.updated_at} for b in branches]
        
        stmt_cat = select(Category).where(
            Category.deleted_at.is_(None),
            ~Category.id.in_(
                select(UserCategoryExclusion.category_id).where(UserCategoryExclusion.user_id == user.id)
            )
        )
        result_cat = await db.execute(stmt_cat)
        categories = result_cat.scalars().all()
        user_dict["categories"] = [{"id": c.id, "name": c.name, "description": c.description, "created_at": c.created_at, "updated_at": c.updated_at} for c in categories]
        
        # Calculate tokens used (current month)
        current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
        stmt_token = select(func.sum(UserTokenUsage.tokens_used)).where(UserTokenUsage.user_id == user.id, UserTokenUsage.year_month == current_ym)
        result_token = await db.execute(stmt_token)
        tokens_used = result_token.scalar() or 0
        user_dict["tokens_used"] = tokens_used
        
        # Override status for doctors if tokens are low
        if user_dict["status"] == "Active" and user.token_limit and user.token_limit > 0:
            if tokens_used >= user.token_limit * 0.9:
                user_dict["status"] = "Warning"
                
    return user_dict

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await _hydrate_user(current_user, db)

@router.get("/", response_model=List[UserResponse])
async def list_users(
    type: Optional[UserType] = None,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:read"))
):
    stmt = select(User).where(User.deleted_at.is_(None))
    if type:
        stmt = stmt.where(User.type == type)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return [await _hydrate_user(user, db) for user in users]

@router.post("/staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    user_in: UserCreateStaff,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.email == user_in.email)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    user = User(
        email=user_in.email,
        name=user_in.name,
        type=UserType.STAFF,
        password_hash=get_password_hash(user_in.password)
    )
    db.add(user)
    await db.flush()
    
    if user_in.roles:
        for role_name in user_in.roles:
            stmt = select(Role).where(func.upper(Role.name) == role_name.upper())
            role = (await db.execute(stmt)).scalar_one_or_none()
            if not role:
                role = Role(name=role_name.upper())
                db.add(role)
                await db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            
    await db.commit()
    await db.refresh(user)
    return await _hydrate_user(user, db)



@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:read"))
):
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _hydrate_user(user, db)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    user_in: dict, # We take a dict and parse it manually since it can be either Staff or Doctor
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.type == UserType.DOCTOR:
        update_data = DoctorUpdate(**user_in).model_dump(exclude_unset=True)
    else:
        update_data = StaffUpdate(**user_in).model_dump(exclude_unset=True)

    if "password" in update_data and update_data["password"]:
        user.password_hash = get_password_hash(update_data["password"])
        del update_data["password"]
        
    if "status" in update_data:
        if update_data["status"] == "Inactive":
            if not user.deleted_at:
                user.deleted_at = datetime.now(timezone.utc)
        elif update_data["status"] == "Active":
            user.deleted_at = None
        del update_data["status"]
        
    for field, value in update_data.items():
        setattr(user, field, value)
        
    await db.commit()
    await db.refresh(user)
    return await _hydrate_user(user, db)



@router.put("/{user_id}/categories", response_model=UserResponse)
async def update_user_categories(
    user_id: uuid.UUID,
    categories_in: UserUpdateCategories,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.id == user_id, User.type == UserType.DOCTOR)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    await db.execute(UserCategoryExclusion.__table__.delete().where(UserCategoryExclusion.user_id == user_id))
    
    stmt_all = select(Category.id).where(Category.deleted_at.is_(None))
    all_cat_ids = set((await db.execute(stmt_all)).scalars().all())
    
    excluded_ids = all_cat_ids - set(categories_in.categories)
    for cat_id in excluded_ids:
        db.add(UserCategoryExclusion(user_id=user.id, category_id=cat_id))
        
    await db.commit()
    return await _hydrate_user(user, db)

@router.put("/{user_id}/roles", response_model=UserResponse)
async def update_user_roles(
    user_id: uuid.UUID,
    roles_in: UserUpdateRoles,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.id == user_id, User.type == UserType.STAFF)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
        
    await db.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
    for role_name in roles_in.roles:
        stmt = select(Role).where(func.upper(Role.name) == role_name.upper())
        role = (await db.execute(stmt)).scalar_one_or_none()
        if not role:
            role = Role(name=role_name.upper())
            db.add(role)
            await db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        
    await db.commit()
    return await _hydrate_user(user, db)

@router.put("/{user_id}/accesses", response_model=UserResponse)
async def update_user_accesses(
    user_id: uuid.UUID,
    accesses_in: UserUpdateAccesses,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.id == user_id, User.type == UserType.STAFF)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
        
    from app.models.user import UserAccess, Access
    
    # Delete all existing direct user accesses
    await db.execute(UserAccess.__table__.delete().where(UserAccess.user_id == user_id))
    
    # Insert new direct accesses
    for access_name in accesses_in.accesses:
        stmt = select(Access).where(Access.name == access_name)
        acc = (await db.execute(stmt)).scalar_one_or_none()
        if acc:
            db.add(UserAccess(user_id=user.id, access_id=acc.id))
            
    await db.commit()
    return await _hydrate_user(user, db)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:write"))
):
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.deleted_at = datetime.now(timezone.utc)
    await db.commit()

