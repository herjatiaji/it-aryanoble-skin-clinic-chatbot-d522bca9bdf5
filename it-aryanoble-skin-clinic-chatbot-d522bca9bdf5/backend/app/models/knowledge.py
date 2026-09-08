import uuid
import enum
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Numeric, Enum as SQLEnum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector
from .base import Base, TimestampMixin, SoftDeleteMixin

class KnowledgeType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    TREATMENT = "TREATMENT"
    PROMOTIONAL = "PROMOTIONAL"
    GENERAL = "GENERAL"

class KnowledgeStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class Knowledge(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "knowledge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[KnowledgeType] = mapped_column(SQLEnum(KnowledgeType, name="knowledge_type"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    original_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[KnowledgeStatus] = mapped_column(SQLEnum(KnowledgeStatus, name="knowledge_status"), default=KnowledgeStatus.PENDING, nullable=False)
    ai_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    
    # Note: searchable_content on Knowledge is GENERATED ALWAYS in postgres if needed, but for chunks we define it below.

class KnowledgeCategory(Base, TimestampMixin):
    __tablename__ = "knowledge_category"

    knowledge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)

class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunk"
    
    __table_args__ = (
        Index('ix_knowledge_chunk_embedding', 'embedding', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'}),
        Index('ix_knowledge_chunk_searchable_content', 'searchable_content', postgresql_using='gin'),
    )

    knowledge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), primary_key=True)
    chunk_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    embedding = mapped_column(Vector(1024))
    searchable_content = mapped_column(TSVECTOR)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
