import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, SmallInteger, Float, Boolean, Date, DateTime, 
    Text, ForeignKey, UniqueConstraint, func, text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TSVECTOR
from pgvector.sqlalchemy import Vector

from .base import Base, TimestampMixin


class KnowledgeVersion(Base, TimestampMixin):
    """
    Immutable versioned unit of clinical knowledge after publish (ACTIVE).
    Lifecycle status transitions: DRAFT -> PROCESSING -> READY_FOR_REVIEW -> ACTIVE -> SUPERSEDED.
    SSOT for document active status and ACL visibility.
    """
    __tablename__ = "knowledge_version"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "version_no", name="uq_knowledge_version_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", index=True)
    ingestion_job_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    visual_jobs_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"total": 0, "completed": 0, "failed": 0, "review_required": 0})
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    default_knowledge_type: Mapped[str] = mapped_column(String(30), nullable=False, default="OTHER")
    authority_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    visibility: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"clinics": ["ALL"], "doctor_types": ["ALL"], "doctors": ["ALL"]})
    summary_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parse_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    evidence_items = relationship("KBEvidence", back_populates="version", cascade="all, delete-orphan")
    assets = relationship("KBAsset", back_populates="version", cascade="all, delete-orphan")
    chunks = relationship("KBChunk", back_populates="version", cascade="all, delete-orphan")


class KBEvidence(Base):
    """
    Canonical Clinical Evidence (Factual Source-of-Truth).
    Stores parsed facts, table cells, rules, or semantic visual representations.
    """
    __tablename__ = "kb_evidence"
    __table_args__ = (
        Index("idx_kb_evidence_version_ordinal", "version_id", "ordinal"),
        Index("idx_kb_evidence_hash", "evidence_content_hash"),
        Index("idx_kb_evidence_vis_status", "visual_analysis_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_version.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'TABLE', 'TABLE_ROW', 'KEY_VALUE', 'PROCEDURE_STEP', 'RULE', 'SECTION', 'TEXT', 'VISUAL'
    knowledge_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    authority_override: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    section_path: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    derivation: Mapped[str] = mapped_column(String(20), nullable=False) # 'NATIVE', 'OCR', 'VISION', 'ADMIN_EDIT'
    processor: Mapped[str] = mapped_column(String(60), nullable=False)
    processor_version: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    visual_analysis_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version = relationship("KnowledgeVersion", back_populates="evidence_items")
    entities = relationship("KBEntity", secondary="kb_evidence_entity", back_populates="evidence_refs")
    assets = relationship("KBAsset", secondary="kb_evidence_asset", back_populates="evidence_refs")


class KBEntity(Base):
    """
    Namespaced Clinical Entity Master.
    Stores stable canonical identities, brands, and intrinsic form factors.
    Versioned facts belong strictly to KBEvidence.attributes.
    """
    __tablename__ = "kb_entity"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_namespace", "normalized_key", name="uq_kb_entity_type_ns_key"),
        Index("idx_kb_entity_lookup", "entity_type", "normalized_key"),
        Index("idx_kb_entity_aliases", "aliases", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'PRODUCT', 'TREATMENT', 'CONDITION', 'INGREDIENT'
    entity_namespace: Mapped[str] = mapped_column(String(30), nullable=False, default="ERHA")
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False)
    form_factor: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    aliases: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evidence_refs = relationship("KBEvidence", secondary="kb_evidence_entity", back_populates="entities")


class KBEvidenceEntity(Base):
    """Many-to-Many relationship between Evidence and Entities."""
    __tablename__ = "kb_evidence_entity"

    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_evidence.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_entity.id", ondelete="CASCADE"), primary_key=True)


class KBAsset(Base):
    """
    Scored media asset with full-page and crop support.
    Classified and validated pre-publish.
    """
    __tablename__ = "kb_asset"
    __table_args__ = (
        Index("idx_kb_asset_version_class", "version_id", "asset_class"),
        Index("idx_kb_asset_hash", "content_hash"),
        Index("idx_kb_asset_parent", "parent_asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_version.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="STANDALONE_IMAGE") # 'FULL_PAGE', 'REGION_CROP', 'STANDALONE_IMAGE'
    parent_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_asset.id", ondelete="CASCADE"), nullable=True)
    bbox: Mapped[Optional[List[int]]] = mapped_column(ARRAY(Integer), nullable=True) # [x0, y0, x1, y1]
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    classification_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    classification_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="VALID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version = relationship("KnowledgeVersion", back_populates="assets")
    evidence_refs = relationship("KBEvidence", secondary="kb_evidence_asset", back_populates="assets")


class KBEvidenceAsset(Base):
    """Many-to-Many mapping linking Evidence to Media Assets with a Semantic Role."""
    __tablename__ = "kb_evidence_asset"

    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_evidence.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_asset.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="REFERENCE")


class KBChunk(Base):
    """
    Derived Materialized Chunk Projection (Sole Writer: Index Builder).
    Maintains partial HNSW vector index and PostgreSQL native FTS token vector.
    """
    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index(
            "idx_kb_chunk_embedding_active", 
            "embedding", 
            postgresql_using="hnsw", 
            postgresql_with={"m": 16, "ef_construction": 64}, 
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("is_active = true")
        ),
        Index("idx_kb_chunk_tsv", "tsv", postgresql_using="gin"),
        Index("idx_kb_chunk_entity_ids", "entity_ids", postgresql_using="gin"),
        Index("idx_kb_chunk_acl_clinics", "acl_clinics", postgresql_using="gin"),
        Index("idx_kb_chunk_acl_doctor_types", "acl_doctor_types", postgresql_using="gin"),
        Index("idx_kb_chunk_acl_doctors", "acl_doctors", postgresql_using="gin"),
        Index("idx_kb_chunk_active_type", "is_active", "knowledge_type"),
        Index("idx_kb_chunk_domain", "domain"),
        Index("idx_kb_chunk_discontinued", "is_discontinued"),
        Index("idx_kb_chunk_target_indications", "target_indications", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True) # Deterministic stable chunk_id
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_version.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_ids: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_type: Mapped[str] = mapped_column(String(30), nullable=False)
    authority_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    entity_ids: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    acl_clinics: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=lambda: ["ALL"])
    acl_doctor_types: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=lambda: ["ALL"])
    acl_doctors: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=lambda: ["ALL"])
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    domain: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_discontinued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_indications: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    embedding: Mapped[Optional[Any]] = mapped_column(Vector(1536), nullable=True)
    # Generated stored tsvector column computed by postgres
    tsv: Mapped[Optional[Any]] = mapped_column(
        TSVECTOR, 
        nullable=True
    )

    version = relationship("KnowledgeVersion", back_populates="chunks")


class KBRelation(Base):
    """
    Explicit Clinical and Operational Relationship between Entities (Phase 4).
    Used for multi-treatment combinations, contraindicated items, prerequisites, etc.
    """
    __tablename__ = "kb_relation"
    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relation_type", name="uq_kb_relation_triple"),
        Index("idx_kb_relation_source", "source_entity_id"),
        Index("idx_kb_relation_target", "target_entity_id"),
        Index("idx_kb_relation_type", "relation_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_entity.id", ondelete="CASCADE"), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_entity.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False) # 'RECOMMENDED_AFTER', 'CONTRAINDICATED_WITH', 'COMBINED_WITH', 'REQUIRES_PREREQUISITE'
    evidence_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_evidence.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_entity = relationship("KBEntity", foreign_keys=[source_entity_id])
    target_entity = relationship("KBEntity", foreign_keys=[target_entity_id])
    evidence = relationship("KBEvidence", foreign_keys=[evidence_id])

