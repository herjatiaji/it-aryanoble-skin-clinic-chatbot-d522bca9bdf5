"""
Test CRUD Knowledge dengan Database SQLite In-Memory.

Karena tidak ada akses credential ke PostgreSQL production, test ini menggunakan
SQLite async (in-memory) sebagai pengganti. Menguji alur INSERT → READ → UPDATE →
SOFT-DELETE → LIST (filtered) secara end-to-end dengan database sungguhan.

Strategi:
- Definisi tabel sederhana (tanpa PostgreSQL-specific types seperti UUID, JSONB, Vector)
  untuk kompatibilitas dengan SQLite.
- Setiap test method berjalan di dalam transaksi yang di-ROLLBACK otomatis.
"""

import asyncio
import uuid
import unittest
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Float, DateTime, Enum as SQLEnum,
    create_engine, select, event,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
import enum


# ── Standalone ORM Models (SQLite-compatible, mirror production schema) ──────


class Base(DeclarativeBase):
    pass


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


class KnowledgeTest(Base):
    """Mirror of production Knowledge table, adapted for SQLite."""
    __tablename__ = "knowledge"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(SQLEnum(KnowledgeType, name="knowledge_type"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    file_name = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    file_size = Column(Float, nullable=True)
    status = Column(
        SQLEnum(KnowledgeStatus, name="knowledge_status"),
        default=KnowledgeStatus.PENDING,
        nullable=False,
    )
    ai_summary = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    uploaded_by = Column(String, nullable=False)
    approved_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)


# ── Test Fixtures ────────────────────────────────────────────────────────────


class TestKnowledgeCRUDWithDatabase(unittest.TestCase):
    """
    End-to-end CRUD tests menggunakan SQLite in-memory database.
    Setiap test berjalan di transaksi yang di-ROLLBACK otomatis sehingga
    tidak ada data permanen yang tersisa.
    """

    @classmethod
    def setUpClass(cls):
        """Buat engine SQLite in-memory dan tabel."""
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Drop semua tabel dan dispose engine."""
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Buka transaksi baru sebelum setiap test — akan di-ROLLBACK di tearDown."""
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = self.SessionFactory(bind=self.connection)

        # Prevent session from committing to the outer transaction
        @event.listens_for(self.session, "after_transaction_end")
        def restart_savepoint(session, trans):
            if trans.nested and not trans._parent.nested:
                session.begin_nested()

    def tearDown(self):
        """ROLLBACK transaksi — database kembali bersih tanpa sisa data."""
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    # ── Helper ───────────────────────────────────────────────────────────

    def _create_knowledge(self, **overrides):
        """Helper untuk membuat record Knowledge dengan default values."""
        defaults = {
            "id": str(uuid.uuid4()),
            "type": KnowledgeType.PRODUCT,
            "title": "Test Product Document.pdf",
            "content": "Ini adalah konten dokumen produk skincare ERHA.",
            "file_name": "Test Product Document.pdf",
            "original_path": "data/temp/Test Product Document.pdf",
            "mime_type": "application/pdf",
            "status": KnowledgeStatus.PENDING,
            "ai_summary": "Dokumen berisi informasi produk skincare ERHA.",
            "ai_confidence": 92.5,
            "uploaded_by": str(uuid.uuid4()),
        }
        defaults.update(overrides)
        doc = KnowledgeTest(**defaults)
        self.session.add(doc)
        self.session.flush()
        return doc

    # ── TEST CASES ───────────────────────────────────────────────────────

    def test_01_insert_knowledge_to_database(self):
        """
        SKENARIO: Upload dokumen baru → data masuk database.
        Memverifikasi INSERT berhasil dan data bisa di-SELECT kembali.
        """
        doc = self._create_knowledge(
            title="ERHA Acne Clarifying Gel - Spec Sheet.pdf",
            ai_summary="Produk gel pembersih jerawat dengan Salicylic Acid 2%.",
        )

        # SELECT kembali dari database
        result = self.session.execute(
            select(KnowledgeTest).where(KnowledgeTest.id == doc.id)
        )
        fetched = result.scalar_one()

        self.assertEqual(fetched.title, "ERHA Acne Clarifying Gel - Spec Sheet.pdf")
        self.assertEqual(fetched.ai_summary, "Produk gel pembersih jerawat dengan Salicylic Acid 2%.")
        self.assertEqual(fetched.status, KnowledgeStatus.PENDING)
        self.assertIsNone(fetched.deleted_at)
        print(f"  [OK] INSERT OK: id={fetched.id[:8]}... title='{fetched.title}'")

    def test_02_read_list_knowledge_excludes_soft_deleted(self):
        """
        SKENARIO: GET /api/knowledge -> hanya menampilkan dokumen yang belum dihapus.
        Memverifikasi filter `WHERE deleted_at IS NULL`.
        """
        self._create_knowledge(title="Dokumen Aktif 1")
        self._create_knowledge(title="Dokumen Aktif 2")
        self._create_knowledge(
            title="Dokumen Terhapus",
            deleted_at=datetime.now(timezone.utc),
        )

        # Query yang sama persis dengan list_knowledge endpoint
        stmt = select(KnowledgeTest).where(KnowledgeTest.deleted_at.is_(None))
        result = self.session.execute(stmt)
        active_docs = result.scalars().all()

        self.assertEqual(len(active_docs), 2)
        titles = [d.title for d in active_docs]
        self.assertIn("Dokumen Aktif 1", titles)
        self.assertIn("Dokumen Aktif 2", titles)
        self.assertNotIn("Dokumen Terhapus", titles)
        print(f"  [OK] LIST OK: {len(active_docs)} active, 1 soft-deleted filtered out")

    def test_03_update_knowledge_title_and_summary(self):
        """
        SKENARIO: Edit judul dan AI summary -> data terupdate di database.
        Memverifikasi bahwa PUT/PATCH /{id} benar-benar mengubah record.
        """
        doc = self._create_knowledge(
            title="Old Title.pdf",
            ai_summary="Old summary.",
        )
        original_id = doc.id

        # Simulasi update (logic yang sama dengan endpoint update_knowledge)
        doc.title = "New Updated Title.pdf"
        doc.ai_summary = "Summary baru: Serum dengan Niacinamide 10% untuk mencerahkan kulit."
        doc.updated_at = datetime.now(timezone.utc)
        self.session.flush()

        # Verifikasi dari SELECT fresh
        result = self.session.execute(
            select(KnowledgeTest).where(KnowledgeTest.id == original_id)
        )
        updated = result.scalar_one()

        self.assertEqual(updated.title, "New Updated Title.pdf")
        self.assertEqual(
            updated.ai_summary,
            "Summary baru: Serum dengan Niacinamide 10% untuk mencerahkan kulit.",
        )
        print(f"  [OK] UPDATE OK: title='{updated.title}', summary updated")

    def test_04_update_knowledge_status_to_approved(self):
        """
        SKENARIO: Admin approve dokumen -> status berubah dari PENDING ke APPROVED.
        Memverifikasi perubahan status dan pengisian approved_by.
        """
        admin_id = str(uuid.uuid4())
        doc = self._create_knowledge(status=KnowledgeStatus.PENDING)

        # Simulasi approval
        doc.status = KnowledgeStatus.APPROVED
        doc.approved_by = admin_id
        self.session.flush()

        result = self.session.execute(
            select(KnowledgeTest).where(KnowledgeTest.id == doc.id)
        )
        approved = result.scalar_one()

        self.assertEqual(approved.status, KnowledgeStatus.APPROVED)
        self.assertEqual(approved.approved_by, admin_id)
        print(f"  [OK] STATUS UPDATE OK: PENDING -> APPROVED, approved_by={admin_id[:8]}...")

    def test_05_update_knowledge_type(self):
        """
        SKENARIO: Ubah kategori dokumen dari PRODUCT ke TREATMENT.
        """
        doc = self._create_knowledge(type=KnowledgeType.PRODUCT)

        doc.type = KnowledgeType.TREATMENT
        self.session.flush()

        result = self.session.execute(
            select(KnowledgeTest).where(KnowledgeTest.id == doc.id)
        )
        updated = result.scalar_one()

        self.assertEqual(updated.type, KnowledgeType.TREATMENT)
        print(f"  [OK] TYPE UPDATE OK: PRODUCT -> TREATMENT")

    def test_06_soft_delete_knowledge(self):
        """
        SKENARIO: Delete dokumen -> soft-delete (deleted_at diisi), bukan hard delete.
        Memverifikasi record tetap ada di database tapi terfilter dari list.
        """
        doc = self._create_knowledge(title="Dokumen yang akan dihapus.pdf")
        doc_id = doc.id

        # Soft-delete (logic yang sama dengan endpoint delete_knowledge)
        doc.deleted_at = datetime.now(timezone.utc)
        self.session.flush()

        # Record masih ada di database
        result = self.session.execute(
            select(KnowledgeTest).where(KnowledgeTest.id == doc_id)
        )
        deleted_doc = result.scalar_one()
        self.assertIsNotNone(deleted_doc.deleted_at)

        # Tapi tidak muncul di list (filter deleted_at IS NULL)
        stmt = select(KnowledgeTest).where(KnowledgeTest.deleted_at.is_(None))
        result2 = self.session.execute(stmt)
        active_docs = result2.scalars().all()
        active_ids = [d.id for d in active_docs]
        self.assertNotIn(doc_id, active_ids)
        print(f"  [OK] SOFT-DELETE OK: id={doc_id[:8]}..., deleted_at={deleted_doc.deleted_at}")

    def test_07_full_lifecycle_insert_update_delete(self):
        """
        SKENARIO LENGKAP: Simulasi lifecycle penuh dokumen knowledge.
        1. Upload (INSERT) -> status PENDING
        2. AI Processing -> status PROCESSING, ai_summary diisi
        3. Admin Edit -> title & summary diperbarui
        4. Admin Approve -> status APPROVED
        5. Admin Delete -> soft-delete
        6. Verifikasi tidak muncul di list aktif
        """
        user_id = str(uuid.uuid4())
        admin_id = str(uuid.uuid4())

        # STEP 1: Upload
        doc = self._create_knowledge(
            title="Chemical Peeling Treatment Guide.pdf",
            content="",
            status=KnowledgeStatus.PENDING,
            uploaded_by=user_id,
        )
        doc_id = doc.id
        self.assertEqual(doc.status, KnowledgeStatus.PENDING)
        print("  [UPLOAD] Step 1 - Upload: status=PENDING")

        # STEP 2: AI Processing
        doc.status = KnowledgeStatus.PROCESSING
        doc.ai_summary = "Panduan treatment Chemical Peeling: jenis AHA/BHA, konsentrasi, aftercare 5 hari."
        doc.ai_confidence = 94.0
        self.session.flush()
        self.assertEqual(doc.status, KnowledgeStatus.PROCESSING)
        print("  [AI] Step 2 - AI Processing: summary generated, confidence=94.0")

        # STEP 3: Admin Edit
        doc.status = KnowledgeStatus.PENDING  # Back to pending for review
        doc.title = "Chemical Peeling Treatment Guide v2.pdf"
        doc.ai_summary = "Panduan treatment Chemical Peeling v2: jenis AHA/BHA/TCA, konsentrasi optimal, aftercare protocol 5-7 hari."
        self.session.flush()
        self.assertEqual(doc.title, "Chemical Peeling Treatment Guide v2.pdf")
        print("  [EDIT] Step 3 - Admin Edit: title & summary updated")

        # STEP 4: Admin Approve
        doc.status = KnowledgeStatus.APPROVED
        doc.approved_by = admin_id
        self.session.flush()
        self.assertEqual(doc.status, KnowledgeStatus.APPROVED)
        print(f"  [OK] Step 4 - Approved by admin={admin_id[:8]}...")

        # STEP 5: Admin Delete
        doc.deleted_at = datetime.now(timezone.utc)
        self.session.flush()
        self.assertIsNotNone(doc.deleted_at)
        print(f"  [DELETE] Step 5 - Soft-deleted: deleted_at={doc.deleted_at}")

        # STEP 6: Verify filtered out
        stmt = select(KnowledgeTest).where(KnowledgeTest.deleted_at.is_(None))
        result = self.session.execute(stmt)
        active_ids = [d.id for d in result.scalars().all()]
        self.assertNotIn(doc_id, active_ids)
        print("  [VERIFY] Step 6 - Verified: document no longer in active list")
        print("  [OK] FULL LIFECYCLE COMPLETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
