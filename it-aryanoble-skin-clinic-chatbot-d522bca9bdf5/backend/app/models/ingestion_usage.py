import uuid
from sqlalchemy import String, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, TimestampMixin

class IngestionTokenUsage(Base, TimestampMixin):
    __tablename__ = "ingestion_token_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year_month: Mapped[str] = mapped_column(String(7), unique=True, nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("tokens_used >= 0", name="chk_ingestion_tokens_used_positive"),
    )
