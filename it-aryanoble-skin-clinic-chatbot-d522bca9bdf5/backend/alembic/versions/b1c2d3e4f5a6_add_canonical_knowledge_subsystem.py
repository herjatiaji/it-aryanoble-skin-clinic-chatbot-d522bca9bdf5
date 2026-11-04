"""add canonical knowledge subsystem and relations

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-10-09 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. PostgreSQL Extensions
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector;'))

    # 1. knowledge_version
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS knowledge_version (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      knowledge_id UUID NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,
      version_no INT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PROCESSING', 'READY_FOR_REVIEW', 'ACTIVE', 'SUPERSEDED', 'REJECTED')),
      ingestion_job_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (ingestion_job_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
      visual_jobs_summary JSONB NOT NULL DEFAULT '{"total": 0, "completed": 0, "failed": 0, "review_required": 0}'::jsonb,
      file_hash TEXT NOT NULL,
      default_knowledge_type TEXT NOT NULL DEFAULT 'OTHER',
      authority_level SMALLINT NOT NULL CHECK (authority_level BETWEEN 1 AND 5),
      effective_from DATE,
      effective_until DATE,
      visibility JSONB NOT NULL DEFAULT '{"clinics": ["ALL"], "doctor_types": ["ALL"], "doctors": ["ALL"]}'::jsonb,
      summary_md TEXT,
      parse_report JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_by UUID REFERENCES users(id) ON DELETE SET NULL,
      approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
      approved_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_knowledge_version_no UNIQUE (knowledge_id, version_no)
    );
    """))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_version_per_doc ON knowledge_version(knowledge_id) WHERE status = 'ACTIVE';"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_knowledge_version_doc ON knowledge_version(knowledge_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_knowledge_version_status ON knowledge_version(status);"))

    # 2. kb_evidence
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_evidence (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      version_id UUID NOT NULL REFERENCES knowledge_version(id) ON DELETE CASCADE,
      evidence_type TEXT NOT NULL CHECK (evidence_type IN ('TABLE', 'TABLE_ROW', 'KEY_VALUE', 'PROCEDURE_STEP', 'RULE', 'SECTION', 'TEXT', 'VISUAL')),
      knowledge_type TEXT CHECK (knowledge_type IN ('PRODUCT', 'TREATMENT', 'SOP', 'CRITERIA', 'LITERATURE', 'PROMO', 'OTHER')),
      authority_override SMALLINT CHECK (authority_override BETWEEN 1 AND 5),
      section_path TEXT[] NOT NULL DEFAULT '{}',
      title TEXT,
      body TEXT NOT NULL,
      attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
      provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
      evidence_content_hash TEXT NOT NULL,
      derivation TEXT NOT NULL CHECK (derivation IN ('NATIVE', 'OCR', 'VISION', 'ADMIN_EDIT')),
      processor TEXT NOT NULL,
      processor_version TEXT NOT NULL,
      confidence REAL CHECK (confidence BETWEEN 0.0 AND 1.0),
      visual_analysis_status TEXT CHECK (visual_analysis_status IN (
        'NATIVE_COMPLETE', 'OCR_COMPLETE', 'VISION_COMPLETE', 'PARTIAL', 'LOW_CONFIDENCE', 'REVIEW_REQUIRED', 'VISION_FAILED'
      )),
      ordinal INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_evidence_version_ordinal ON kb_evidence(version_id, ordinal);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_evidence_hash ON kb_evidence(evidence_content_hash);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_evidence_vis_status ON kb_evidence(visual_analysis_status);"))

    # 3. kb_entity
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_entity (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      entity_type TEXT NOT NULL CHECK (entity_type IN ('PRODUCT', 'TREATMENT', 'CONDITION', 'INGREDIENT')),
      entity_namespace TEXT NOT NULL DEFAULT 'ERHA',
      canonical_name TEXT NOT NULL,
      normalized_key TEXT NOT NULL,
      form_factor TEXT,
      aliases TEXT[] NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_kb_entity_type_ns_key UNIQUE (entity_type, entity_namespace, normalized_key)
    );
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_entity_lookup ON kb_entity(entity_type, normalized_key);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_entity_aliases ON kb_entity USING GIN (aliases);"))

    # 4. kb_evidence_entity (Mapping)
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_evidence_entity (
      evidence_id UUID NOT NULL REFERENCES kb_evidence(id) ON DELETE CASCADE,
      entity_id UUID NOT NULL REFERENCES kb_entity(id) ON DELETE CASCADE,
      PRIMARY KEY (evidence_id, entity_id)
    );
    """))

    # 5. kb_asset
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_asset (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      version_id UUID NOT NULL REFERENCES knowledge_version(id) ON DELETE CASCADE,
      storage_key TEXT NOT NULL,
      content_hash TEXT NOT NULL,
      asset_kind TEXT NOT NULL DEFAULT 'STANDALONE_IMAGE' CHECK (asset_kind IN ('FULL_PAGE', 'REGION_CROP', 'STANDALONE_IMAGE')),
      parent_asset_id UUID REFERENCES kb_asset(id) ON DELETE CASCADE,
      bbox INT[],
      asset_class TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (asset_class IN ('PRODUCT_PHOTO', 'CLINICAL_PHOTO', 'DIAGRAM', 'CHART', 'LOGO', 'DECORATIVE', 'UNKNOWN')),
      classification_score REAL NOT NULL DEFAULT 0.0,
      classification_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
      label TEXT,
      width INT,
      height INT,
      provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
      status TEXT NOT NULL DEFAULT 'VALID' CHECK (status IN ('VALID', 'MISSING', 'EXCLUDED')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_asset_version_class ON kb_asset(version_id, asset_class);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_asset_hash ON kb_asset(content_hash);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_asset_parent ON kb_asset(parent_asset_id);"))

    # 6. kb_evidence_asset (Mapping)
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_evidence_asset (
      evidence_id UUID NOT NULL REFERENCES kb_evidence(id) ON DELETE CASCADE,
      asset_id UUID NOT NULL REFERENCES kb_asset(id) ON DELETE CASCADE,
      role TEXT NOT NULL DEFAULT 'REFERENCE' CHECK (role IN ('PRIMARY_PRODUCT_IMAGE', 'BEFORE_TREATMENT', 'AFTER_TREATMENT', 'DIAGRAM_ILLUSTRATION', 'REFERENCE')),
      PRIMARY KEY (evidence_id, asset_id)
    );
    """))

    # 7. kb_chunk
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_chunk (
      id TEXT PRIMARY KEY,
      version_id UUID NOT NULL REFERENCES knowledge_version(id) ON DELETE CASCADE,
      evidence_ids UUID[] NOT NULL DEFAULT '{}',
      retrieval_text TEXT NOT NULL,
      knowledge_type TEXT NOT NULL,
      authority_level SMALLINT NOT NULL DEFAULT 2,
      entity_ids UUID[] NOT NULL DEFAULT '{}',
      acl_clinics TEXT[] NOT NULL DEFAULT '{"ALL"}',
      acl_doctor_types TEXT[] NOT NULL DEFAULT '{"ALL"}',
      acl_doctors TEXT[] NOT NULL DEFAULT '{"ALL"}',
      is_active BOOLEAN NOT NULL DEFAULT false,
      embedding vector(1536),
      tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', retrieval_text)) STORED
    );
    """))
    op.execute(sa.text("""
    CREATE INDEX IF NOT EXISTS idx_kb_chunk_embedding_active ON kb_chunk USING hnsw (embedding vector_cosine_ops)
      WITH (m = 16, ef_construction = 64)
      WHERE is_active = true;
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_tsv ON kb_chunk USING GIN (tsv);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_entity_ids ON kb_chunk USING GIN (entity_ids);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_acl_clinics ON kb_chunk USING GIN (acl_clinics);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_acl_doctor_types ON kb_chunk USING GIN (acl_doctor_types);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_acl_doctors ON kb_chunk USING GIN (acl_doctors);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_active_type ON kb_chunk (is_active, knowledge_type);"))

    # 8. kb_relation (Phase 4 Multi-Treatment & Combo Rules)
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS kb_relation (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      source_entity_id UUID NOT NULL REFERENCES kb_entity(id) ON DELETE CASCADE,
      target_entity_id UUID NOT NULL REFERENCES kb_entity(id) ON DELETE CASCADE,
      relation_type TEXT NOT NULL CHECK (relation_type IN ('RECOMMENDED_AFTER', 'CONTRAINDICATED_WITH', 'COMBINED_WITH', 'REQUIRES_PREREQUISITE')),
      evidence_id UUID REFERENCES kb_evidence(id) ON DELETE SET NULL,
      description TEXT,
      attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_kb_relation_triple UNIQUE (source_entity_id, target_entity_id, relation_type)
    );
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_relation_source ON kb_relation(source_entity_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_relation_target ON kb_relation(target_entity_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_relation_type ON kb_relation(relation_type);"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS kb_relation CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_chunk CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_evidence_asset CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_asset CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_evidence_entity CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_entity CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS kb_evidence CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS knowledge_version CASCADE;"))
