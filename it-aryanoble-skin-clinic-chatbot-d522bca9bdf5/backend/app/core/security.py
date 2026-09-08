from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from cryptography.fernet import Fernet
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: str, user_type: str, roles: list[str] | None = None, accesses: list[str] | None = None, expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": user_type, "roles": roles or [], "accesses": accesses or []}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode = {"exp": expire, "sub": str(subject), "refresh": True}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# Symmetric Encryption for API Keys
_fernet = Fernet(settings.SECRET_ENCRYPTION_KEY.encode()) if settings.SECRET_ENCRYPTION_KEY else None

def encrypt_api_key(api_key: str) -> str:
    if not _fernet or not api_key:
        return api_key
    return _fernet.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    if not _fernet or not encrypted_key:
        return encrypted_key
    try:
        return _fernet.decrypt(encrypted_key.encode()).decode()
    except Exception:
        # Fallback in case it's not actually encrypted (legacy plaintext)
        return encrypted_key
