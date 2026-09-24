from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess, invalidate_user_access_cache
from app.models.user import User, Role, Access, RoleAccess, UserRole
from app.schemas.role import RoleResponse, RoleCreate, RoleUpdate, AccessResponse
from app.schemas.pagination import PaginatedResponse
from collections import defaultdict
from typing import List, Optional, Union
from fastapi import Query
import math

router = APIRouter(tags=["Roles"])

async def _hydrate_roles_batch(roles: List[Role], db: AsyncSession) -> List[RoleResponse]:
    if not roles:
        return []

    role_ids = [r.id for r in roles]
    has_admin = any(r.name.upper() == "ADMIN" for r in roles)

    # 1. Fetch all accesses if ADMIN role is present
    all_access_names: List[str] = []
    if has_admin:
        stmt_all = select(Access.name)
        acc_res = await db.execute(stmt_all)
        all_access_names = list(acc_res.scalars().all())

    # 2. Batch fetch role accesses
    role_access_map: dict[uuid.UUID, list[str]] = defaultdict(list)
    stmt_acc = (
        select(RoleAccess.role_id, Access.name)
        .join(Access, RoleAccess.access_id == Access.id)
        .where(RoleAccess.role_id.in_(role_ids))
    )
    for r_id, acc_name in (await db.execute(stmt_acc)).all():
        role_access_map[r_id].append(acc_name)

    # 3. Batch fetch user counts
    user_count_map: dict[uuid.UUID, int] = defaultdict(int)
    stmt_users = (
        select(UserRole.role_id, func.count(UserRole.user_id))
        .where(UserRole.role_id.in_(role_ids))
        .group_by(UserRole.role_id)
    )
    for r_id, count in (await db.execute(stmt_users)).all():
        user_count_map[r_id] = count or 0

    # 4. Construct responses
    responses: List[RoleResponse] = []
    for role in roles:
        if role.name.upper() == "ADMIN":
            accesses = all_access_names
        else:
            accesses = role_access_map.get(role.id, [])

        responses.append(
            RoleResponse(
                id=role.id,
                name=role.name,
                accesses=accesses,
                user_count=user_count_map.get(role.id, 0),
                created_at=role.created_at,
                updated_at=role.updated_at
            )
        )
    return responses

async def _hydrate_role(role: Role, db: AsyncSession) -> RoleResponse:
    hydrated = await _hydrate_roles_batch([role], db)
    return hydrated[0]

@router.get("/accesses", response_model=List[AccessResponse])
async def list_available_accesses(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess(["roles:read", "users:read"]))
):
    stmt = select(Access).order_by(Access.name)
    result = await db.execute(stmt)
    return result.scalars().all()

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
        roles = list(result.scalars().all())
        hydrated = await _hydrate_roles_batch(roles, db)

        return PaginatedResponse[RoleResponse](
            items=hydrated,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    result = await db.execute(stmt)
    roles = list(result.scalars().all())
    return await _hydrate_roles_batch(roles, db)

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
    invalidate_user_access_cache()
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
    invalidate_user_access_cache()
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
    invalidate_user_access_cache()
