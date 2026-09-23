from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
import uuid
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.cis_sync import get_cis_public_key, parse_cis_int

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
            cis_int = parse_cis_int(user_cis_id)
            if cis_int is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid doctor ID in token")
            stmt = select(User).where(User.cis_id == cis_int, User.deleted_at.is_(None))
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or session invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

async def verify_cis_proxy_signature(
    request: Request, 
    x_signature: str | None = Header(None, alias="X-Signature"),
    x_user_id: str | None = Header(None, alias="X-User-Id")
) -> str:
    """Dependency verifying RSA signature for the proxy chat stream."""
    if not x_signature or not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Signature or X-User-Id header"
        )
        
    body_bytes = request.scope.get("_raw_body")
    if body_bytes is None:
        try:
            body_bytes = await request.body()
        except RuntimeError:
            body_bytes = getattr(request, "_body", b"")
    payload_to_verify = x_user_id.encode("utf-8") + b":" + body_bytes
    
    try:
        signature_bytes = base64.b64decode(x_signature)
        public_key = get_cis_public_key()
        public_key.verify(
            signature_bytes,
            payload_to_verify,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid proxy RSA signature"
        )
    return x_user_id

async def get_current_user_from_proxy(
    user_id: str = Depends(verify_cis_proxy_signature),
    db: AsyncSession = Depends(get_db)
) -> User:
    cis_int = parse_cis_int(user_id)
    if cis_int is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user ID in header")
    stmt = select(User).where(User.cis_id == cis_int, User.deleted_at.is_(None))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or session invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

async def get_current_user_flexible(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Flexible dependency that uses X-Signature for Server-to-Server calls, 
    or falls back to JWT for internal dashboard users.
    """
    if request.headers.get("x-signature"):
        user_id = await verify_cis_proxy_signature(
            request, 
            request.headers.get("x-signature"), 
            request.headers.get("x-user-id")
        )
        cis_int = parse_cis_int(user_id)
        if cis_int is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user ID in header")
        stmt = select(User).where(User.cis_id == cis_int, User.deleted_at.is_(None))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or session invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
        
    return await get_current_user(request, db)

class RequireAccess:
    def __init__(self, required_access: str | list[str]):
        if isinstance(required_access, str):
            self.required_accesses = [required_access]
        else:
            self.required_accesses = required_access

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
        user_accesses = set(result.scalars().all())
        
        # Check if user has at least one of the required accesses
        if not any(req in user_accesses for req in self.required_accesses):
            req_str = ", ".join(self.required_accesses)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Required access: {req_str}")
            
        return current_user
