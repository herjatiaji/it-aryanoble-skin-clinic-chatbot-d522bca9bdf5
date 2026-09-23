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
        "user_type_code": user.user_type_code,
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
        
        # Calculate staff tokens used (current month)
        current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
        stmt_token = select(func.sum(UserTokenUsage.tokens_used)).where(
            UserTokenUsage.user_id == user.id,
            UserTokenUsage.year_month == current_ym
        )
        result_token = await db.execute(stmt_token)
        user_dict["tokens_used"] = result_token.scalar() or 0
        
    elif user.type == UserType.DOCTOR:
        stmt_branch = (
            select(Branch)
            .join(UserBranch, UserBranch.branch_id == Branch.id)
            .where(
                UserBranch.user_id == user.id,
                UserBranch.status == 1,
                UserBranch.deleted_at.is_(None),
                Branch.deleted_at.is_(None)
            )
        )
        result_branch = await db.execute(stmt_branch)
        branches = result_branch.scalars().all()
        current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
        user_dict["branches"] = []
        for b in branches:
            b_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
                UserTokenUsage.user_id == user.id,
                UserTokenUsage.branch_id == b.id,
                UserTokenUsage.year_month == current_ym
            )
            b_used_res = await db.execute(b_usage_stmt)
            doc_branch_used = b_used_res.scalar() or 0
            user_dict["branches"].append({
                "id": b.id,
                "external_id": b.external_id,
                "name": b.name,
                "code": b.code,
                "ecosystem": b.ecosystem,
                "token_limit": b.token_limit,
                "tokens_used": doc_branch_used,
                "created_at": b.created_at,
                "updated_at": b.updated_at
            })
        
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
        
        # Check global token mode for status
        from app.models.config import AppConfig
        cfg_stmt = select(AppConfig.value).where(AppConfig.key == "GLOBAL_TOKEN_LIMIT_ACTIVE")
        cfg_res = await db.execute(cfg_stmt)
        cfg_val = cfg_res.scalar_one_or_none()
        is_global_mode = (cfg_val or "false").lower() == "true"

        if is_global_mode:
            # Check Doctor Type limits (SpDVE vs GP Plus) only if sub-flag is active
            dr_type_clean = (user.dr_type or "").upper()
            is_spkk = any(k in dr_type_clean for k in ["SPDVE", "SP.DVE", "SPKK", "SP.KK", "SPDV"])
            is_gp = any(k in dr_type_clean for k in ["GP", "GP PLUS", "UMUM"])
            
            global_doc_limit = 0
            if is_spkk:
                spkk_act = (await db.execute(select(AppConfig.value).where(AppConfig.key == "GLOBAL_SPKK_LIMIT_ACTIVE"))).scalar_one_or_none()
                if (spkk_act or "false").lower() == "true":
                    t_val = (await db.execute(select(AppConfig.value).where(AppConfig.key == "TOKEN_LIMIT_SPKK"))).scalar_one_or_none()
                    global_doc_limit = int(t_val) if (t_val and t_val.isdigit() and int(t_val) > 0) else 0
            elif is_gp:
                gp_act = (await db.execute(select(AppConfig.value).where(AppConfig.key == "GLOBAL_GP_LIMIT_ACTIVE"))).scalar_one_or_none()
                if (gp_act or "false").lower() == "true":
                    t_val = (await db.execute(select(AppConfig.value).where(AppConfig.key == "TOKEN_LIMIT_GP"))).scalar_one_or_none()
                    global_doc_limit = int(t_val) if (t_val and t_val.isdigit() and int(t_val) > 0) else 0

            # If user has custom override (user.token_limit > 0), prioritize it; otherwise use global limit if active
            effective_limit = user.token_limit if (user.token_limit is not None and user.token_limit > 0) else global_doc_limit
            if user_dict["status"] == "Active" and effective_limit > 0 and tokens_used >= effective_limit * 0.9:
                user_dict["status"] = "Warning"
        elif user_dict["status"] == "Active" and user.token_limit and user.token_limit > 0:
            if tokens_used >= user.token_limit * 0.9:
                user_dict["status"] = "Warning"
                
    return user_dict

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await _hydrate_user(current_user, db)

from app.schemas.pagination import PaginatedResponse
from typing import List, Optional, Union
from fastapi import Query
import math

@router.get("/", response_model=Union[PaginatedResponse[UserResponse], List[UserResponse]])
async def list_users(
    type: Optional[UserType] = None,
    search: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("users:read"))
):
    stmt = select(User).where(User.deleted_at.is_(None))
    if type:
        stmt = stmt.where(User.type == type)
    if search:
        s_clean = f"%{search.strip()}%"
        stmt = stmt.where(
            (User.name.ilike(s_clean)) |
            (User.email.ilike(s_clean)) |
            (User.employee_id.ilike(s_clean))
        )
    stmt = stmt.order_by(User.created_at.desc())

    if page is not None:
        p_size = page_size or 10
        # Calculate total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0
        total_pages = max(1, math.ceil(total / p_size))

        paginated_stmt = stmt.offset((page - 1) * p_size).limit(p_size)
        result = await db.execute(paginated_stmt)
        users = result.scalars().all()
        hydrated_items = [await _hydrate_user(u, db) for u in users]

        return PaginatedResponse[UserResponse](
            items=hydrated_items,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    result = await db.execute(stmt)
    users = result.scalars().all()
    return [await _hydrate_user(u, db) for u in users]

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
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
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
        if "token_limit" in update_data and update_data["token_limit"] is not None:
            stmt_branch = (
                select(Branch)
                .join(UserBranch, UserBranch.branch_id == Branch.id)
                .where(
                    UserBranch.user_id == user.id,
                    UserBranch.status == 1,
                    UserBranch.deleted_at.is_(None),
                    Branch.deleted_at.is_(None)
                )
            )
            result_branch = await db.execute(stmt_branch)
            user_branches = result_branch.scalars().all()
            
            if not user_branches:
                raise HTTPException(status_code=400, detail="Doctor is not assigned to any branch yet.")

            # Check if global branch pool is active to determine max branch limit
            from app.models.config import AppConfig
            cfg_stmt = select(AppConfig.value).where(AppConfig.key == "GLOBAL_TOKEN_LIMIT_ACTIVE")
            cfg_res = await db.execute(cfg_stmt)
            is_global_mode = (cfg_res.scalar_one_or_none() or "false").lower() == "true"

            b_act_stmt = select(AppConfig.value).where(AppConfig.key == "GLOBAL_BRANCH_LIMIT_ACTIVE")
            b_act_res = await db.execute(b_act_stmt)
            is_branch_global_active = is_global_mode and ((b_act_res.scalar_one_or_none() or "false").lower() == "true")

            global_branch_limit = 0
            if is_branch_global_active:
                gl_stmt = select(AppConfig.value).where(AppConfig.key == "GLOBAL_TOKEN_LIMIT")
                gl_res = await db.execute(gl_stmt)
                gl_val = gl_res.scalar_one_or_none()
                global_branch_limit = int(gl_val) if (gl_val and gl_val.isdigit() and int(gl_val) > 0) else 3000000

            branch_limits = []
            for b in user_branches:
                if b.token_limit is not None and b.token_limit > 0:
                    branch_limits.append(b.token_limit)
                elif is_branch_global_active:
                    branch_limits.append(global_branch_limit)
                else:
                    branch_limits.append(b.token_limit or 0)

            max_branch_limit = max(branch_limits) if branch_limits else 0

            if max_branch_limit == 0:
                raise HTTPException(status_code=400, detail="Branch token limit must be set before setting doctor token limit.")
                
            if update_data["token_limit"] > max_branch_limit:
                raise HTTPException(status_code=400, detail=f"Doctor token limit ({update_data['token_limit']:,}) cannot exceed branch token limit ({max_branch_limit:,}).")
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

