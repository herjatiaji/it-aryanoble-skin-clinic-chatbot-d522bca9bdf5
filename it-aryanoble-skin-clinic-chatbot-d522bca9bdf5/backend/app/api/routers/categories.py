from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_user, RequireAccess
from app.models.user import User, UserType
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from datetime import datetime, timezone

router = APIRouter(tags=["Categories"])

@router.get("/", response_model=List[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("categories:read"))
):
    stmt = select(Category).where(Category.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_in: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("categories:write"))
):
    stmt = select(Category).where(Category.name == category_in.name)
    result = await db.execute(stmt)
    existing_category = result.scalar_one_or_none()
    
    if existing_category:
        if existing_category.deleted_at is None:
            raise HTTPException(status_code=400, detail="Category with this name already exists")
        else:
            # Reactivate soft-deleted category
            existing_category.deleted_at = None
            if category_in.description is not None:
                existing_category.description = category_in.description
            await db.commit()
            await db.refresh(existing_category)
            return existing_category
            
    category = Category(**category_in.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    category_in: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("categories:write"))
):
    stmt = select(Category).where(Category.id == category_id, Category.deleted_at.is_(None))
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    update_data = category_in.model_dump(exclude_unset=True)
    
    if "name" in update_data and update_data["name"] != category.name:
        check_stmt = select(Category).where(Category.name == update_data["name"])
        check_result = await db.execute(check_stmt)
        if check_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category with this name already exists")
            
    for field, value in update_data.items():
        setattr(category, field, value)
        
    await db.commit()
    await db.refresh(category)
    return category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(RequireAccess("categories:write"))
):
    stmt = select(Category).where(Category.id == category_id, Category.deleted_at.is_(None))
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    category.deleted_at = datetime.now(timezone.utc)
    await db.commit()
