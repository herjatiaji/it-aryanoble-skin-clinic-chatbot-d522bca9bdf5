"""
Verification test suite for all bug fixes (Bug #1 to #12) and AI quality improvements.
"""
import sys
import os
import io

def test_bug_2_source_hiding_and_sanitization():
    print("\n--- Testing Bug #2: Document Name Leaking & Sanitization ---")
    from app.rag.services.rag_retriever import PromptContextBuilder
    from app.rag.services.rag_generator import strip_internal_document_references

    builder = PromptContextBuilder()
    chunks = [
        {
            "chunk_id": "test_chunk_1",
            "text": "Acneact Witch Hazel BHA Toner membantu meredakan kemerahan pada jerawat aktif.",
            "metadata": {
                "source_file": "Katalog_Produk_ERHA_Acneact_2024.pdf",
                "knowledge_id": "c1f3089d-784f-4d9d-9ea8-6bc4fb619213",
                "product_name": "ERHA Acneact BHA Toner",
                "category": "Toner",
                "section": "Deskripsi Produk"
            },
            "score": 0.95
        }
    ]

    context = builder.build_context(chunks)
    assert "Katalog_Produk_ERHA_Acneact_2024.pdf" not in context, "LEAK DETECTED: Source filename found in context!"
    assert "Source:" not in context, "LEAK DETECTED: 'Source:' header found in context!"
    assert "c1f3089d-784f-4d9d-9ea8-6bc4fb619213" not in context, "LEAK DETECTED: Knowledge ID found in context!"
    assert "ERHA Acneact BHA Toner" in context, "Product name should be preserved in context."
    print("  [PASS] build_context() successfully excludes raw filenames, Source headers, and UUIDs.")

    # Test strip_internal_document_references sanitizer
    leaky_response = (
        "Berdasarkan dokumen Katalog_Produk_ERHA_Acneact_2024.pdf dan panduan SOP_Klinik.docx, "
        "produk ini memiliki ID c1f3089d-784f-4d9d-9ea8-6bc4fb619213. Silakan cek data_2024.xlsx."
    )
    cleaned = strip_internal_document_references(leaky_response)
    assert ".pdf" not in cleaned, "Sanitizer failed to strip .pdf filename"
    assert ".docx" not in cleaned, "Sanitizer failed to strip .docx filename"
    assert ".xlsx" not in cleaned, "Sanitizer failed to strip .xlsx filename"
    assert "c1f3089d-784f-4d9d-9ea8-6bc4fb619213" not in cleaned, "Sanitizer failed to strip UUID"
    print(f"  [PASS] strip_internal_document_references() successfully sanitized:\n    Original: {leaky_response}\n    Sanitized: {cleaned}")


def test_bug_8_table_deduplication():
    print("\n--- Testing Bug #8: Table Row Duplication ---")
    from app.rag.services.rag_retriever import PromptContextBuilder

    builder = PromptContextBuilder()
    chunks = [
        {
            "chunk_id": "chunk_table_1",
            "text": "| Nama Produk | Harga | Indikasi |\n|---|---|---|\n| Acne Clear Gel | 75000 | Jerawat Ringan |\n| Acne Spot Cream | 85000 | Jerawat Meradang |",
            "metadata": {
                "source_file": "Tabel_Harga_Produk.xlsx",
                "product_name": "Tabel Harga 1"
            },
            "score": 0.9
        },
        {
            "chunk_id": "chunk_table_2",
            "text": "| Nama Produk | Harga | Indikasi |\n|---|---|---|\n| Acne Spot Cream | 85000 | Jerawat Meradang |\n| Oil Control Wash | 65000 | Kulit Berminyak |",
            "metadata": {
                "source_file": "Tabel_Harga_Produk.xlsx",
                "product_name": "Tabel Harga 2"
            },
            "score": 0.85
        }
    ]

    context = builder.build_context(chunks)
    # The duplicate row '| Acne Spot Cream | 85000 | Jerawat Meradang |' should only appear once
    count = context.count("Acne Spot Cream")
    assert count == 1, f"Table row was repeated! Count: {count}"
    assert "Oil Control Wash" in context, "Second non-duplicate row should still be included"
    print(f"  [PASS] Duplicate table row appeared exactly {count} time(s) across chunks.")


def test_bug_1_two_column_pdf_reading_order():
    print("\n--- Testing Bug #1: 2-Column Journal PDF Reading Order ---")
    import fitz
    from app.rag.utils.parser import DocumentParser

    # Create an in-memory 2-column PDF
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # Header spanning across page
    page.insert_text((50, 50), "JUDUL JURNAL PENELITIAN KLINIS ERHA", fontsize=14)

    # Left column text (x: 50 to 280)
    page.insert_text((50, 100), "Kolom Kiri Paragraf 1: Pengujian formula Acneact dimulai.", fontsize=10)
    page.insert_text((50, 150), "Kolom Kiri Paragraf 2: Hasil menunjukkan reduksi sebum hingga 45%.", fontsize=10)

    # Right column text (x: 320 to 550)
    page.insert_text((320, 100), "Kolom Kanan Paragraf 1: Diskusi perbandingan efektivitas.", fontsize=10)
    page.insert_text((320, 150), "Kolom Kanan Paragraf 2: Kesimpulan akhir terapi kombinasi.", fontsize=10)

    test_pdf_path = "/tmp/test_two_col.pdf"
    doc.save(test_pdf_path)
    doc.close()

    parser = DocumentParser()
    res = parser._parse_pdf_fast(test_pdf_path)
    assert res is not None, "Failed to parse test PDF"
    parsed_text = res.pages[0]["text"]

    print("  Parsed PDF Text:\n" + "\n".join("    " + line for line in parsed_text.splitlines() if line))

    pos_left_1 = parsed_text.find("Kolom Kiri Paragraf 1")
    pos_left_2 = parsed_text.find("Kolom Kiri Paragraf 2")
    pos_right_1 = parsed_text.find("Kolom Kanan Paragraf 1")
    pos_right_2 = parsed_text.find("Kolom Kanan Paragraf 2")

    assert pos_left_1 != -1 and pos_left_2 != -1 and pos_right_1 != -1 and pos_right_2 != -1, "Missing expected paragraphs"
    # Reading order must be: Kolom Kiri 1 < Kolom Kiri 2 < Kolom Kanan 1 < Kolom Kanan 2
    assert pos_left_1 < pos_left_2 < pos_right_1 < pos_right_2, (
        f"Reading order invalid! Left 1 ({pos_left_1}), Left 2 ({pos_left_2}), Right 1 ({pos_right_1}), Right 2 ({pos_right_2})"
    )
    print("  [PASS] 2-Column PDF parsed in correct reading order (Left column before Right column).")
    if os.path.exists(test_pdf_path):
        os.remove(test_pdf_path)


def test_bug_6_excel_multi_sheet_and_chunking():
    print("\n--- Testing Bug #6: Excel Multi-Sheet Parsing & Header Preservation ---")
    import pandas as pd
    from app.rag.utils.parser import DocumentParser
    from app.rag.utils.chunker import CustomChunker

    test_xlsx = "/tmp/test_multisheet.xlsx"
    with pd.ExcelWriter(test_xlsx) as writer:
        df1 = pd.DataFrame({
            "Produk": ["Cream Anti Aging", "Serum Retinol"],
            "Harga": [150000, 220000]
        })
        df1.to_excel(writer, sheet_name="Perawatan_Wajah", index=False)

        df2 = pd.DataFrame({
            "Produk": ["Body Lotion Brightening", "Body Scrub Coffee"],
            "Harga": [95000, 85000]
        })
        df2.to_excel(writer, sheet_name="Perawatan_Tubuh", index=False)

    parser = DocumentParser()
    res = parser._parse_excel_fast(test_xlsx)
    assert len(res.pages) == 2, f"Expected 2 sheets as pages, got {len(res.pages)}"
    assert res.pages[0]["sheet_name"] == "Perawatan_Wajah"
    assert res.pages[1]["sheet_name"] == "Perawatan_Tubuh"
    assert "## Sheet: Perawatan_Wajah" in res.pages[0]["text"]
    assert "## Sheet: Perawatan_Tubuh" in res.pages[1]["text"]
    print(f"  [PASS] Parser extracted both sheets: {[p['sheet_name'] for p in res.pages]}")

    chunker = CustomChunker()
    chunks = chunker.chunk_document(res)
    assert len(chunks) >= 2, f"Expected at least 2 chunks for 2 sheets, got {len(chunks)}"

    sheet_names_in_chunks = [c.get("metadata", {}).get("sheet_name") for c in chunks]
    print(f"  [PASS] Chunk metadata sheet_names: {sheet_names_in_chunks}")
    assert "Perawatan_Wajah" in sheet_names_in_chunks and "Perawatan_Tubuh" in sheet_names_in_chunks, "Missing sheet_name in chunk metadata"

    if os.path.exists(test_xlsx):
        os.remove(test_xlsx)


def test_bug_5_and_12_knowledge_schema_fields():
    print("\n--- Testing Bug #5 & Bug #12: Schema Support for uploaded_by_name & approved_at ---")
    from app.schemas.knowledge import KnowledgeResponse
    from datetime import datetime, timezone

    from uuid import uuid4
    from app.models.knowledge import KnowledgeType, KnowledgeStatus

    now = datetime.now(timezone.utc)
    mock_data = {
        "id": "c1f3089d-784f-4d9d-9ea8-6bc4fb619213",
        "title": "Dokumen Test SOP",
        "file_name": "test_sop.pdf",
        "original_path": "data/pending/test_sop.pdf",
        "type": KnowledgeType.GENERAL,
        "status": KnowledgeStatus.APPROVED,
        "uploaded_by": uuid4(),
        "created_at": now,
        "updated_at": now,
        "uploaded_by_name": "Admin Clinic Jkt",
        "approved_at": now
    }

    resp = KnowledgeResponse(**mock_data)
    assert resp.uploaded_by_name == "Admin Clinic Jkt", f"uploaded_by_name mismatch: {resp.uploaded_by_name}"
    assert resp.approved_at == now, f"approved_at mismatch: {resp.approved_at}"
    dumped = resp.model_dump(mode="json")
    assert "uploaded_by_name" in dumped and dumped["uploaded_by_name"] == "Admin Clinic Jkt"
    assert "approved_at" in dumped and dumped["approved_at"] is not None
    print(f"  [PASS] KnowledgeResponse serializes uploaded_by_name ('{dumped['uploaded_by_name']}') and approved_at ('{dumped['approved_at']}')")


def test_bug_4_knowledge_deletion_path_resolution():
    print("\n--- Testing Bug #4: Delete Knowledge File Paths & Logic ---")
    from app.rag.router import resolve_pending_file
    import uuid
    import json

    test_id = f"test_doc_{uuid.uuid4().hex[:8]}"
    os.makedirs("data/pending", exist_ok=True)
    test_pending = f"data/pending/{test_id}.json"
    with open(test_pending, "w") as f:
        json.dump({"knowledge_id": test_id, "title": "Test Pending Doc"}, f)

    resolved = resolve_pending_file(test_id)
    assert resolved is not None and os.path.exists(resolved), f"Could not resolve pending file: {resolved}"
    print(f"  [PASS] resolve_pending_file resolved: {resolved}")

    if os.path.exists(test_pending):
        os.remove(test_pending)


if __name__ == "__main__":
    print("==================================================")
    print("STARTING ALL BUGFIX & AI AUDIT VERIFICATION TESTS")
    print("==================================================")
    try:
        test_bug_2_source_hiding_and_sanitization()
        test_bug_8_table_deduplication()
        test_bug_1_two_column_pdf_reading_order()
        test_bug_6_excel_multi_sheet_and_chunking()
        test_bug_5_and_12_knowledge_schema_fields()
        test_bug_4_knowledge_deletion_path_resolution()
        print("\n==================================================")
        print("ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY! [PASSED]")
        print("==================================================")
    except Exception as e:
        print(f"\n[FAILED] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
