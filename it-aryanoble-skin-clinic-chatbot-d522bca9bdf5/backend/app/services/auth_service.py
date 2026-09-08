from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, UserType
from app.core.security import verify_password
from fastapi import HTTPException, status

async def authenticate_staff(session: AsyncSession, email: str, password: str) -> User | None:
    stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.password_hash:
        return None
        
    if not verify_password(password, user.password_hash):
        return None
        
    return user
