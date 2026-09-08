# Dokumentasi Perbaikan - Arya Noble Skin Clinic Chatbot

**Tanggal**: 8 September 2026  
**Auditor**: herjatiaji  
**Sistem**: Arya Noble AI Chatbot (Backend FastAPI + RAG Pipeline)

---

## 1. Ringkasan Masalah

Klien melaporkan bahwa **data tidak bisa di-update di database** setelah proses upload file. Secara spesifik:

1. Upload file multiple **berhasil** — data terbaca dan masuk ke database (PostgreSQL)
2. Namun ketika data **diedit atau dihapus**, perubahan **tidak tersimpan** ke database

---

## 2. Hasil Audit & Analisis Akar Masalah

### 2.1 Endpoint Update Tidak Ada
File `backend/app/api/routers/knowledge.py` sebelumnya **tidak memiliki endpoint PUT maupun PATCH** untuk update data knowledge.
Hanya tersedia:
- `POST /` — Upload (create)
- `GET /` — List
- `GET /{id}` — Detail
- `DELETE /{id}` — Hapus (hanya hard delete sederhana)

**Dampak**: Ketika frontend mengirim request update data (PUT/PATCH), API mengembalikan `405 Method Not Allowed` / `404 Not Found`, sehingga data di DB tidak pernah berubah.

### 2.2 Endpoint Delete Tidak Melakukan Sinkronisasi
Endpoint `DELETE /{knowledge_id}` sebelumnya hanya menjalankan `db.delete(doc)`, tetapi **tidak membersihkan**:
- Data vector & embeddings di **PGVector**
- Data index pada **BM25**
- File JSON staging di `data/pending/` atau `data/output/`

**Dampak**: Meskipun baris di PostgreSQL terhapus, knowledge lama masih tetap bisa ditarik oleh sistem AI/Chatbot (data hantu). Selain itu, tidak ada soft-delete tracking.

### 2.3 UUID Mismatch pada Background Ingestion RAG
Pada proses background ingestion di `backend/app/rag/router.py`, pembuatan chunk embedding menghasilkan ID baru (`uuid.uuid4()`) yang berbeda dari UUID record di tabel `knowledge`.
**Dampak**: Antara record knowledge dan vector chunk terjadi diskoneksi referensi, menyebabkan data orphan.

### 2.4 Regex Intent Detection Kurang Komprehensif
Pattern regex untuk intent `HOW_TO_USE` pada `backend/app/rag/services/intent.py` terlalu sempit, sehingga beberapa variasi pertanyaan customer terkait pemakaian produk tidak terklasifikasikan secara tepat.

---

## 3. Perbaikan yang Dilakukan

### 3.1 Penambahan Endpoint Update Knowledge (`PUT` & `PATCH`)
**File**: `backend/app/api/routers/knowledge.py`
- Menambahkan route `@router.put("/{knowledge_id}")` dan `@router.patch("/{knowledge_id}")`.
- Mengimplementasikan partial update pada field `title`, `content`, `ai_summary`, `ai_confidence`, `status`, dan `type`.
- Menambahkan fungsi sinkronisasi otomatis ke file JSON staging di filesystem jika dokumen masih dalam status staging/pending.

### 3.2 Implementasi Soft-Delete & Full Vector/Staging Cleanup
**File**: `backend/app/api/routers/knowledge.py`
- Mengubah alur delete menjadi **Soft-Delete** (`doc.deleted_at = func.now()`) untuk keamanan data audit.
- Menambahkan pembersihan dokumen terkait di PGVector / BM25 index.
- Menambahkan cleanup file JSON terkait dari staging folder.

### 3.3 Penambahan Model Schema `KnowledgeUpdate`
**File**: `backend/app/schemas/knowledge.py`
- Menambahkan class `KnowledgeUpdate(BaseModel)` dengan dukungan `populate_by_name=True` untuk memvalidasi payload update dari frontend.

### 3.4 Sinkronisasi ID pada RAG Ingestion
**File**: `backend/app/rag/router.py`
- Memastikan ID dokumen pada vector store merujuk ke UUID record `knowledge.id` yang konsisten.

### 3.5 Perluasan Regex Intent Classifier
**File**: `backend/app/rag/services/intent.py` & `backend/app/rag/services/rag_generator.py`
- Memperluas deteksi intent `HOW_TO_USE` agar mencakup variasi bahasa Indonesia sehari-hari ("cara pakai", "cara pemakaian", "aturan pakai", dll).
- Menambahkan metadata `intent` pada return output `generate_answer`.

---

## 4. Hasil Verifikasi & Testing (19/19 PASSED)

Seluruh pengujian unit test dan integration test berhasil dijalankan dengan status **OK**:

### 4.1 Unit Test CRUD Knowledge (`backend/tests/test_knowledge_safe.py`)
- `test_01_create_knowledge` : PASSED
- `test_02_read_knowledge_by_id` : PASSED
- `test_03_update_knowledge_title_and_summary` : PASSED
- `test_04_soft_delete_knowledge` : PASSED
- `test_05_list_knowledge_excludes_soft_deleted` : PASSED

### 4.2 Chatbot Scenario & Guardrails (`backend/tests/test_chatbot_scenarios.py`)
- `test_01_product_inquiry_detection` : PASSED
- `test_02_treatment_inquiry_detection` : PASSED
- `test_03_how_to_use_inquiry_detection` : PASSED
- `test_04_greeting_detection` : PASSED
- `test_05_guardrails_prompt_injection_blocked` : PASSED
- `test_06_guardrails_offtopic_blocked` : PASSED
- `test_07_rag_pipeline_with_context` : PASSED

### 4.3 Database Integration Test (`backend/tests/test_knowledge_database.py`)
Menguji alur transaksi database aktual menggunakan SQLite in-memory (dengan otomatisasi rollback):
- `test_01_insert_knowledge_to_database` : PASSED
- `test_02_read_list_knowledge_excludes_soft_deleted` : PASSED
- `test_03_update_knowledge_title_and_summary` : PASSED
- `test_04_update_knowledge_status_to_approved` : PASSED
- `test_05_update_knowledge_type` : PASSED
- `test_06_soft_delete_knowledge` : PASSED
- `test_07_full_lifecycle_insert_update_delete` : PASSED

---

## 5. Ringkasan File yang Diubah & Ditambahkan

| File | Tipe | Deskripsi Perubahan |
|---|---|---|
| `backend/app/api/routers/knowledge.py` | MODIFIED | Menambahkan endpoint PUT/PATCH, soft-delete, sinkronisasi file staging & vector |
| `backend/app/schemas/knowledge.py` | MODIFIED | Menambahkan skema data `KnowledgeUpdate` |
| `backend/app/rag/router.py` | MODIFIED | Menyelaraskan UUID dokumen pada background ingestion |
| `backend/app/rag/services/intent.py` | MODIFIED | Perbaikan regex intent detection |
| `backend/app/rag/services/rag_generator.py` | MODIFIED | Penambahan intent label pada response |
| `backend/tests/test_knowledge_safe.py` | NEW | Unit test CRUD aman (mocked) |
| `backend/tests/test_chatbot_scenarios.py` | NEW | Unit test guardrails & intent chatbot |
| `backend/tests/test_knowledge_database.py` | NEW | Integration test database transaksi (SQLite) |

---

## 6. Petunjuk Menjalankan Test & Deployment

### Menjalankan Test
```powershell
# Jalankan seluruh test suite
python -m unittest backend/tests/test_knowledge_safe.py -v
python -m unittest backend/tests/test_chatbot_scenarios.py -v
python -m unittest backend/tests/test_knowledge_database.py -v
```

### Langkah Push ke Repository Baru (GitHub)
Karena repositori lokal sudah memiliki commit terakhir, Anda dapat menghubungkannya ke repositori GitHub baru dengan perintah:
```powershell
# 1. Tambahkan remote url repository baru Anda di GitHub:
git remote add origin https://github.com/<USERNAME>/arya-noble-skin-clinic-chatbot.git

# 2. Rename branch utama ke main (jika belum):
git branch -M main

# 3. Push seluruh branch dan commit ke GitHub:
git push -u origin main
```
