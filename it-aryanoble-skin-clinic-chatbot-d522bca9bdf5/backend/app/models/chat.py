import uuid
import enum
from typing import Optional
from sqlalchemy import String, Enum as SQLEnum, ForeignKey
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    status: Mapped[ChatStatus] = mapped_column(SQLEnum(ChatStatus, name="chat_status"), default=ChatStatus.ACTIVE, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rating: Mapped[Optional[ChatRating]] = mapped_column(SQLEnum(ChatRating, name="chat_rating"), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String, nullable=True)

class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_session.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[ChatRole] = mapped_column(SQLEnum(ChatRole, name="chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
