from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.auth_service import authenticate_staff
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings
from jose import jwt, JWTError

from sqlalchemy import select
from app.models.user import User, UserType, Role, UserRole, RoleAccess, Access, UserAccess

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await authenticate_staff(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    roles = []
    accesses = []
    if user.type == UserType.STAFF:
        stmt = select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
        result = await db.execute(stmt)
        roles = list(result.scalars().all())
        
        stmt_acc = (
            select(Access.name)
            .join(RoleAccess, RoleAccess.access_id == Access.id)
            .join(UserRole, UserRole.role_id == RoleAccess.role_id)
            .where(UserRole.user_id == user.id)
        )
        
        stmt_user_acc = (
            select(Access.name)
            .join(UserAccess, UserAccess.access_id == Access.id)
            .where(UserAccess.user_id == user.id)
        )
        
        union_stmt = stmt_acc.union(stmt_user_acc)
        result_acc = await db.execute(union_stmt)
        accesses = list(result_acc.scalars().all())

    access_token = create_access_token(subject=str(user.id), user_type=user.type, roles=roles, accesses=accesses)
    refresh_token = create_refresh_token(subject=str(user.id))
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False, # Should be True in production with HTTPS
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"message": "Login successful"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}

@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token_cookie = request.cookies.get("refresh_token")
    if not refresh_token_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
        
    try:
        payload = jwt.decode(refresh_token_cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        is_refresh = payload.get("refresh")
        
        if not user_id or not is_refresh:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        # Fetch current user to determine type and roles
        import uuid
        stmt_user = select(User).where(User.id == uuid.UUID(user_id), User.deleted_at.is_(None))
        res_user = await db.execute(stmt_user)
        user = res_user.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        roles = []
        accesses = []
        if user.type == UserType.STAFF:
            stmt_roles = select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
            roles = list((await db.execute(stmt_roles)).scalars().all())
            
            stmt_acc = (
                select(Access.name)
                .join(RoleAccess, RoleAccess.access_id == Access.id)
                .join(UserRole, UserRole.role_id == RoleAccess.role_id)
                .where(UserRole.user_id == user.id)
            )
            
            stmt_user_acc = (
                select(Access.name)
                .join(UserAccess, UserAccess.access_id == Access.id)
                .where(UserAccess.user_id == user.id)
            )
            
            union_stmt = stmt_acc.union(stmt_user_acc)
            result_acc = await db.execute(union_stmt)
            accesses = list(result_acc.scalars().all())

        new_access_token = create_access_token(subject=str(user.id), user_type=user.type, roles=roles, accesses=accesses)
        
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        return {"message": "Token refreshed"}
        
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
