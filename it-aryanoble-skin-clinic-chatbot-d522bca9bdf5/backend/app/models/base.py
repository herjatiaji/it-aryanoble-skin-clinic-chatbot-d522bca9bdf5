import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass

class TimestampMixin:
    """Provides created_at and updated_at columns."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SoftDeleteMixin:
    """Provides deleted_at column for soft deletes."""
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
