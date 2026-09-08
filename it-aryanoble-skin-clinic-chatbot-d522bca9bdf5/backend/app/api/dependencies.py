from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
import uuid

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.cis_sync import get_cis_public_key

# Used for Swagger UI only, actual auth happens via cookies
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        # Fallback for swagger UI testing
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "RS256":
            # This is a CIS-signed token
            public_key = get_cis_public_key()
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
            user_cis_id = payload.get("sub")
            if not user_cis_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            stmt = select(User).where(User.cis_id == user_cis_id, User.deleted_at.is_(None))
        else:
            # This is a backend-signed token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id_str: str = payload.get("sub")
            if user_id_str is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            user_id = uuid.UUID(user_id_str)
            stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
            
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    return user

class RequireAccess:
    def __init__(self, required_access: str):
        self.required_access = required_access

    async def __call__(self, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        from app.models.user import UserType, Role, UserRole, RoleAccess, Access, UserAccess
        
        if current_user.type != UserType.STAFF:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
            
        stmt_acc = (
            select(Access.name)
            .join(RoleAccess, RoleAccess.access_id == Access.id)
            .join(UserRole, UserRole.role_id == RoleAccess.role_id)
            .where(UserRole.user_id == current_user.id)
        )
        
        stmt_user_acc = (
            select(Access.name)
            .join(UserAccess, UserAccess.access_id == Access.id)
            .where(UserAccess.user_id == current_user.id)
        )
        
        union_stmt = stmt_acc.union(stmt_user_acc)
        result = await db.execute(union_stmt)
        user_accesses = result.scalars().all()
        
        if self.required_access not in user_accesses:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Required access: {self.required_access}")
            
        return current_user
