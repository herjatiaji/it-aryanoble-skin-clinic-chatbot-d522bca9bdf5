from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User, Role, Access, RoleAccess, UserRole
from app.schemas.role import RoleResponse, RoleCreate, RoleUpdate, AccessResponse

router = APIRouter(tags=["Roles"])

async def _hydrate_role(role: Role, db: AsyncSession) -> RoleResponse:
    # Fetch accesses for this role
    if role.name.upper() == "ADMIN":
        stmt_all = select(Access.name)
        acc_res = await db.execute(stmt_all)
        accesses = list(acc_res.scalars().all())
    else:
        stmt_acc = (
            select(Access.name)
            .join(RoleAccess, RoleAccess.access_id == Access.id)
            .where(RoleAccess.role_id == role.id)
        )
        acc_res = await db.execute(stmt_acc)
        accesses = list(acc_res.scalars().all())

    # Fetch assigned user count
    stmt_users = (
        select(func.count(UserRole.user_id))
        .where(UserRole.role_id == role.id)
    )
    count_res = await db.execute(stmt_users)
    user_count = count_res.scalar() or 0

    return RoleResponse(
        id=role.id,
        name=role.name,
        accesses=accesses,
        user_count=user_count,
        created_at=role.created_at,
        updated_at=role.updated_at
    )

@router.get("/accesses", response_model=List[AccessResponse])
async def list_available_accesses(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:read", "users:read"]))
):
    stmt = select(Access).order_by(Access.name)
    result = await db.execute(stmt)
    return result.scalars().all()

from app.schemas.pagination import PaginatedResponse
from typing import List, Optional, Union
from fastapi import Query
import math

@router.get("/", response_model=Union[PaginatedResponse[RoleResponse], List[RoleResponse]])
async def list_roles(
    search: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:read", "users:read"]))
):
    stmt = select(Role).order_by(Role.name)
    if search:
        s_clean = f"%{search.strip()}%"
        stmt = stmt.where(Role.name.ilike(s_clean))

    if page is not None:
        p_size = page_size or 10
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0
        total_pages = max(1, math.ceil(total / p_size))

        paginated_stmt = stmt.offset((page - 1) * p_size).limit(p_size)
        result = await db.execute(paginated_stmt)
        roles = result.scalars().all()
        hydrated = [await _hydrate_role(role, db) for role in roles]

        return PaginatedResponse[RoleResponse](
            items=hydrated,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    result = await db.execute(stmt)
    roles = result.scalars().all()
    return [await _hydrate_role(role, db) for role in roles]

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:read", "users:read"]))
):
    stmt = select(Role).where(Role.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return await _hydrate_role(role, db)

@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_in: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:write", "users:write"]))
):
    clean_name = role_in.name.strip().upper()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Role name cannot be empty")

    stmt = select(Role).where(func.upper(Role.name) == clean_name)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name already exists")

    role = Role(name=clean_name)
    db.add(role)
    await db.flush()

    if role_in.accesses:
        for acc_name in role_in.accesses:
            stmt_acc = select(Access).where(Access.name == acc_name)
            acc = (await db.execute(stmt_acc)).scalar_one_or_none()
            if not acc:
                acc = Access(name=acc_name)
                db.add(acc)
                await db.flush()
            db.add(RoleAccess(role_id=role.id, access_id=acc.id))

    await db.commit()
    await db.refresh(role)
    return await _hydrate_role(role, db)

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    role_in: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:write", "users:write"]))
):
    stmt = select(Role).where(Role.id == role_id)
    role = (await db.execute(stmt)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role_in.name is not None:
        clean_name = role_in.name.strip().upper()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Role name cannot be empty")
        if clean_name != role.name:
            stmt_dup = select(Role).where(func.upper(Role.name) == clean_name, Role.id != role_id)
            if (await db.execute(stmt_dup)).scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Role with this name already exists")
            role.name = clean_name

    if role_in.accesses is not None:
        # Delete existing role accesses
        await db.execute(delete(RoleAccess).where(RoleAccess.role_id == role_id))
        # Insert new accesses
        for acc_name in role_in.accesses:
            stmt_acc = select(Access).where(Access.name == acc_name)
            acc = (await db.execute(stmt_acc)).scalar_one_or_none()
            if not acc:
                acc = Access(name=acc_name)
                db.add(acc)
                await db.flush()
            db.add(RoleAccess(role_id=role.id, access_id=acc.id))

    await db.commit()
    await db.refresh(role)
    return await _hydrate_role(role, db)

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:write", "users:write"]))
):
    stmt = select(Role).where(Role.id == role_id)
    role = (await db.execute(stmt)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.name.upper() == "ADMIN":
        raise HTTPException(status_code=400, detail="Default ADMIN role cannot be deleted")

    await db.execute(delete(RoleAccess).where(RoleAccess.role_id == role_id))
    await db.execute(delete(UserRole).where(UserRole.role_id == role_id))
    await db.delete(role)
    await db.commit()
