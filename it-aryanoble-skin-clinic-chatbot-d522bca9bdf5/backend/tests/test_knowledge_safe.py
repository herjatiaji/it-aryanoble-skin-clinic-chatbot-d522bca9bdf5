import sys
import os
import uuid
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Add backend directory to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.schemas.knowledge import KnowledgeUpdate, KnowledgeResponse, KnowledgeCreate
from app.models.knowledge import Knowledge, KnowledgeStatus, KnowledgeType
from app.models.user import User, UserType
from app.api.routers.knowledge import update_knowledge, delete_knowledge, router as knowledge_router


class TestKnowledgeSafeUnit(unittest.IsolatedAsyncioTestCase):
    """
    Unit tests yang 100% aman (Isolated Unit Tests).
    TIDAK menyentuh database production sama sekali karena menggunakan Mock Session.
    """

    def setUp(self):
        self.dummy_user_id = uuid.uuid4()
        self.dummy_user = User(
            id=self.dummy_user_id,
            email="admin@aryasnow.com",
            name="Admin Test",
            type=UserType.STAFF
        )
        self.dummy_doc_id = uuid.uuid4()
        self.mock_doc = Knowledge(
            id=self.dummy_doc_id,
            title="Old Title.pdf",
            file_name="Old Title.pdf",
            original_path="data/temp/Old Title.pdf",
            mime_type="application/pdf",
            type=KnowledgeType.PRODUCT,
            status=KnowledgeStatus.APPROVED,
            ai_summary="Old summary text",
            uploaded_by=self.dummy_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            deleted_at=None
        )

    def test_schema_knowledge_update_validation(self):
        """Memvalidasi schema KnowledgeUpdate dapat menerima partial field dengan benar."""
        # 1. Update title only
        payload1 = KnowledgeUpdate(title="New Title.pdf")
        self.assertEqual(payload1.title, "New Title.pdf")
        self.assertIsNone(payload1.ai_summary)

        # 2. Update ai_summary only
        payload2 = KnowledgeUpdate(ai_summary="Updated AI Summary")
        self.assertEqual(payload2.ai_summary, "Updated AI Summary")
        self.assertIsNone(payload2.title)

        # 3. Update type & metadata
        payload3 = KnowledgeUpdate(type=KnowledgeType.TREATMENT, metadata_={"category": "Facial"})
        self.assertEqual(payload3.type, KnowledgeType.TREATMENT)
        self.assertEqual(payload3.metadata_, {"category": "Facial"})

    def test_router_routes_registered(self):
        """Memastikan semua route CRUD (GET, PUT, PATCH, DELETE) terdaftar di router."""
        routes = [(route.path, tuple(route.methods)) for route in knowledge_router.routes]
        registered_paths = [r[0] for r in routes]

        self.assertIn("/", registered_paths)
        self.assertIn("/{knowledge_id}", registered_paths)
        self.assertIn("/{knowledge_id}/status", registered_paths)

        # Cek methods untuk /{knowledge_id}
        doc_routes = [r for r in routes if r[0] == "/{knowledge_id}"]
        methods = set()
        for r in doc_routes:
            methods.update(r[1])
        
        self.assertIn("GET", methods)
        self.assertIn("PUT", methods)
        self.assertIn("PATCH", methods)
        self.assertIn("DELETE", methods)

    async def test_update_knowledge_logic_with_mock_db(self):
        """
        Menguji endpoint update_knowledge dengan mock db session.
        Memverifikasi perubahan title dan ai_summary serta pemanggilan commit & refresh.
        """
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_doc
        mock_db.execute.return_value = mock_result

        update_payload = KnowledgeUpdate(
            title="Updated Title Document.pdf",
            ai_summary="This is the new verified summary."
        )

        with patch("os.path.exists", return_value=False):
            updated_doc = await update_knowledge(
                knowledge_id=self.dummy_doc_id,
                update_in=update_payload,
                db=mock_db,
                current_user=self.dummy_user
            )

        # Verifikasi atribut diperbarui
        self.assertEqual(updated_doc.title, "Updated Title Document.pdf")
        self.assertEqual(updated_doc.ai_summary, "This is the new verified summary.")
        # Verifikasi DB commit & refresh dipanggil
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(self.mock_doc)

    async def test_delete_knowledge_soft_delete_with_mock_db(self):
        """
        Menguji endpoint delete_knowledge dengan mock db session.
        Memverifikasi soft-delete (deleted_at diisi) dan DB commit dipanggil.
        """
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_doc
        mock_db.execute.return_value = mock_result

        with patch("os.path.exists", return_value=False):
            res = await delete_knowledge(
                knowledge_id=self.dummy_doc_id,
                db=mock_db,
                current_admin=self.dummy_user
            )

        # Verifikasi deleted_at tidak lagi None (soft-deleted)
        self.assertIsNotNone(self.mock_doc.deleted_at)
        # Verifikasi DB commit dipanggil
        mock_db.commit.assert_awaited_once()
        # Status code 204 No Content
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
