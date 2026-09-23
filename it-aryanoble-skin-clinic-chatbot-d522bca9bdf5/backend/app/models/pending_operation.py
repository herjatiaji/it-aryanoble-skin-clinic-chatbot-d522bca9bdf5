import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base, TimestampMixin

class PendingOperation(Base, TimestampMixin):
    """
    Stores CRUD operations requested by admin via chat prompts awaiting explicit confirmation.
    Decouples LLM from directly executing changes.
    """
    __tablename__ = "pending_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "edit" or "delete"
    knowledge_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_item: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    context_label: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending", nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
