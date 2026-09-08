import uuid
import enum
from typing import Optional
from sqlalchemy import String, Integer, Enum as SQLEnum, ForeignKey, CheckConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, TimestampMixin, SoftDeleteMixin

class UserType(str, enum.Enum):
    STAFF = "STAFF"
    DOCTOR = "DOCTOR"

class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[UserType] = mapped_column(SQLEnum(UserType, name="user_type"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cis_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    token_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    employee_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dr_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ecosystem: Mapped[str] = mapped_column(String, default="ERHA", server_default="ERHA", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(type = 'DOCTOR' AND cis_id IS NOT NULL) OR (type = 'STAFF' AND password_hash IS NOT NULL)",
            name="chk_user_integrity"
        ),
        CheckConstraint(
            "email ~* '^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,4}$'",
            name="chk_user_email"
        ),
    )

class Role(Base, TimestampMixin):
    __tablename__ = "role"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

class UserRole(Base, TimestampMixin):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)

class Access(Base, TimestampMixin):
    __tablename__ = "access"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

class RoleAccess(Base, TimestampMixin):
    __tablename__ = "role_access"

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)
    access_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("access.id", ondelete="CASCADE"), primary_key=True)

class UserAccess(Base, TimestampMixin):
    __tablename__ = "user_access"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    access_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("access.id", ondelete="CASCADE"), primary_key=True)

class UserTokenUsage(Base, TimestampMixin):
    __tablename__ = "user_token_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    year_month: Mapped[str] = mapped_column(String(7), primary_key=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("tokens_used >= 0", name="chk_tokens_used_positive"),
    )
