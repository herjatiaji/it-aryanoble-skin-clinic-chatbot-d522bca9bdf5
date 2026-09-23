import uuid
import enum
from typing import Optional
from sqlalchemy import String, Enum as SQLEnum, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base, TimestampMixin

class ChatStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"

class ChatRole(str, enum.Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"

class ChatRating(str, enum.Enum):
    GOOD = "GOOD"
    BAD = "BAD"

class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_session"
    __table_args__ = (
        Index("ix_chat_session_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    session_type: Mapped[str] = mapped_column(String(50), default="DOCTOR", server_default="DOCTOR", nullable=False)
    status: Mapped[ChatStatus] = mapped_column(SQLEnum(ChatStatus, name="chat_status"), default=ChatStatus.ACTIVE, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rating: Mapped[Optional[ChatRating]] = mapped_column(SQLEnum(ChatRating, name="chat_rating"), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    has_data_issue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    is_feedback_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_id_created_at", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_session.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[ChatRole] = mapped_column(SQLEnum(ChatRole, name="chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
