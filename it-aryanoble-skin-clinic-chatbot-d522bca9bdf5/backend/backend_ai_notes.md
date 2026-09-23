# Catatan Teknis & Spesifikasi Bugfix Backend & AI Engineer
## Skin Clinic Chatbot — Knowledge Base & Chat Session

Dokumen ini berisi catatan teknis, akar masalah (*root cause*), dan rekomendasi perbaikan untuk **Backend Developer** dan **AI Engineer** terkait isu-isu yang didelegasikan dari audit sistem.

---

## 📋 Daftar Isi
1. [Ringkasan Masalah & Delegasi](#1-ringkasan-masalah--delegasi)
2. [Isu #1: Gagal Menghapus Dokumen Knowledge (Delete Knowledge)](#2-isu-1-gagal-menghapus-dokumen-knowledge)
3. [Isu #2: Field `uploaded_by_name` dan `approved_at` pada API Knowledge](#3-isu-2-field-uploaded_by_name-dan-approved_at)
4. [Isu #3: Session Chat Tiba-tiba Terminate (Inactivity / Hard Timeout)](#4-isu-3-session-chat-tiba-tiba-terminate)
5. [Isu #4: Glitch "Document Batch Not Found" Saat Upload Batch](#5-isu-4-glitch-document-batch-not-found)
6. [Isu #5: AI / RAG Pipeline — Sinkronisasi Update Summary & Re-indexing](#6-isu-5-ai--rag-pipeline--sinkronisasi-update-summary--re-indexing)

---

## 1. Ringkasan Masalah & Delegasi

| No | Modul | Deskripsi Masalah | File / Komponen Terkait (BE & AI) |
|---|---|---|---|
| **1** | Knowledge Base | Saat delete dari dalam knowledge, dokumen tidak terhapus atau error | `backend/app/services/general_knowledge_service.py`<br/>`backend/app/api/v1/endpoints/knowledge.py` |
| **2** | Knowledge Base | Dukungan data nama pengunggah (`uploaded_by_name`) dan waktu disetujui (`approved_at`) | `backend/app/schemas/knowledge.py`<br/>`backend/app/models/knowledge.py`<br/>SQLAlchemy queries |
| **3** | Chat Engine | Session chat tiba-tiba terminate sendiri setelah beberapa menit | `backend/app/api/v1/endpoints/chats.py`<br/>`TIME_LIMIT_PER_SESSION`<br/>Redis / Session Store |
| **4** | Knowledge Base | Muncul "Not found document batch" sesaat setelah upload massal | `backend/app/api/v1/endpoints/knowledge.py` (upload batch flow)<br/>Background worker / DB commit race condition |
| **5** | AI / RAG Engine | Update summary manual dari admin belum tersinkronisasi ke embedding vektor | Vector store service (Qdrant/Chroma/Milvus)<br/>Chunking & Embedding update pipeline |

---

## 2. Isu #1: Gagal Menghapus Dokumen Knowledge

### 🔍 Root Cause Analysis
1. **Perbedaan Penanganan File `PENDING` vs `APPROVED`:**
   Pada `GeneralKnowledgeService.apply_delete(knowledge_id)`:
   - Kode memanggil `resolve_approved_file(...)`. Jika dokumen masih berstatus `PENDING` (staged di storage sementara) atau belum pernah di-approve, pemanggilan fungsi ini memicu `FileNotFoundError` sehingga eksekusi terhenti sebelum database record dihapus.
2. **Penghapusan File Fisik Tanpa Exception Handling yang Aman:**
   Jika file fisik sudah terhapus secara manual di storage/bucket, fungsi `os.remove` atau S3 `delete_object` melempar error dan membatalkan transaksi database (rollback).
3. **Pembersihan Vector Store Tidak Tuntas / Gagal:**
   Jika point ID di vector store tidak ditemukan saat proses delete dipanggil, exception yang tidak di-handle menyebabkan endpoint me-return HTTP 500 dan membiarkan baris data tetap ada di PostgreSQL.

### 🛠️ Rekomendasi Solusi Backend
1. **Pengecekan Status Dokumen:**
   ```python
   # Rekomendasi penanganan delete di GeneralKnowledgeService:
   async def apply_delete(self, db: AsyncSession, knowledge_id: UUID):
       knowledge = await self.get_by_id(db, knowledge_id)
       if not knowledge:
           raise HTTPException(status_code=404, detail="Knowledge not found")
       
       # 1. Hapus file fisik secara aman (graceful)
       try:
           if knowledge.status == KnowledgeStatus.APPROVED:
               file_path = self.resolve_approved_file(knowledge)
               if file_path and os.path.exists(file_path):
                   os.remove(file_path)
           else:
               staging_path = self.resolve_staged_file(knowledge)
               if staging_path and os.path.exists(staging_path):
                   os.remove(staging_path)
       except Exception as e:
           logger.warning(f"Could not delete physical file for {knowledge_id}: {e}")
       
       # 2. Hapus point dari Vector Database (Qdrant / Chroma)
       try:
           await self.vector_service.delete_by_knowledge_id(knowledge_id)
       except Exception as e:
           logger.warning(f"Failed to delete vector points for {knowledge_id}: {e}")
       
       # 3. Hapus relasi chunks & record database
       await db.delete(knowledge)
       await db.commit()
   ```
2. **Batch Item vs Single Item:**
   Pastikan jika user menghapus single document yang berasal dari suatu batch, relasi batch tidak menyebabkan foreign key constraint violation atau menghapus dokumen lain di batch yang sama secara tidak sengaja.

---

## 3. Isu #2: Field `uploaded_by_name` dan `approved_at`

### 🎯 Kebutuhan Frontend
Frontend telah disiapkan untuk menampilkan kolom **"Uploaded By"** dan **"Approved Timestamp"** di tabel dan halaman detail.

### 🛠️ Rekomendasi Solusi Backend
1. **Update Pydantic Schema (`KnowledgeResponse`):**
   ```python
   class KnowledgeResponse(BaseModel):
       id: UUID
       title: str
       status: KnowledgeStatus
       uploaded_by: UUID
       uploaded_by_name: Optional[str] = None   # <--- Tambahkan field ini
       approved_by: Optional[UUID] = None
       approved_at: Optional[datetime] = None   # <--- Tambahkan field ini
       created_at: datetime
       updated_at: datetime
       # ... field lainnya
   ```
2. **Query SQLAlchemy:**
   Lakukan `outerjoin` dengan tabel `User`:
   ```python
   query = (
       select(Knowledge, User.full_name.label("uploaded_by_name"))
       .outerjoin(User, Knowledge.uploaded_by == User.id)
   )
   ```
   Jika `full_name` bernilai None, fallback ke `username` atau default `"Admin"`.
3. **Pencatatan `approved_at`:**
   Pada endpoint approval (`POST /api/knowledge/{id}/approve`):
   ```python
   knowledge.status = KnowledgeStatus.APPROVED
   knowledge.approved_by = current_user.id
   knowledge.approved_at = datetime.now(timezone.utc)
   ```

---

## 4. Isu #3: Session Chat Tiba-tiba Terminate

### 🔍 Root Cause Analysis
1. **Konfigurasi Timeout Statis:**
   Pada modul chat backend, variabel batas waktu (misalnya `TIME_LIMIT_PER_SESSION`) di-hardcode ke angka rendah (misal: 5 menit / 300 detik).
2. **Absennya Sliding Window / Activity Renewal:**
   Session timeout dihitung sejak pertama kali session dibuat (`created_at`), bukan dari interaksi terakhir (`last_activity_at`). Akibatnya, user yang sedang aktif bertanya di menit ke-6 langsung diputus karena session awal sudah melewati batas 5 menit.
3. **Hard-termination vs Graceful Inactivity:**
   Backend langsung me-reject request dengan error "Session terminated" daripada memperbarui session secara otomatis saat ada pesan baru.

### 🛠️ Rekomendasi Solusi Backend
1. **Ubah ke Pola `last_activity_at` (Sliding Expiry):**
   - Setiap kali user mengirim pesan via `POST /api/chats/{session_id}/message` atau streaming:
     ```python
     session.last_active_at = datetime.now(timezone.utc)
     # Jika menggunakan Redis TTL:
     await redis.expire(f"chat:session:{session_id}", 1800)  # Reset 30 menit
     ```
2. **Tingkatkan Batas Waktu Idle:**
   - Gunakan nilai idle timeout yang wajar untuk percakapan klinik, misalnya **30 menit hingga 60 menit**.
   - Pindahkan nilai ini ke Environment Variable: `CHAT_SESSION_IDLE_TIMEOUT_SECONDS=1800`.
3. **Sediakan Endpoint Keep-Alive / Ping (Opsional):**
   - `POST /api/chats/{session_id}/heartbeat` untuk memperpanjang session jika user tetap berada di tab browser.

---

## 5. Isu #4: Glitch "Document Batch Not Found" Saat Upload Batch

### 🔍 Root Cause Analysis
1. **Race Condition antara Response Upload & Worker Insertion:**
   - Saat admin melakukan upload batch (beberapa file sekaligus), API backend langsung me-return `{ "batch_id": "xxx" }` ke frontend.
   - Frontend langsung melakukan redirect router ke `/dashboard/knowledge/batch/{batch_id}` dan me-request `GET /api/knowledge/batch/{batch_id}`.
   - Namun, proses penyimpanan record dokumen ke PostgreSQL di-dispatch secara asynchronous (BackgroundTasks / Celery worker). Saat request `GET` tiba di backend, baris batch/dokumen belum di-commit ke DB.
   - Endpoint me-return `404 Not Found` atau `[]` (array kosong), memicu pesan glitch "Not found document batch" pada frontend.

### 🛠️ Rekomendasi Solusi Backend
1. **Simpan Baris Dokumen secara Sinkron Sebelum Return Batch ID:**
   - Buat record batch dan stub dokumen (`status: "PENDING"` atau `"PROCESSING"`) di PostgreSQL dalam satu transaksi sinkron sebelum me-return HTTP 200/201 ke frontend.
   - Serahkan proses berat (ekstraksi teks, OCR, chunking, AI embedding) ke worker asynchronous setelah stub tersimpan di database.
2. **Pastikan API Batch Return Status Dokumen:**
   - `GET /api/knowledge/batch/{batch_id}` harus selalu mengembalikan objek batch beserta daftar dokumen meskipun statusnya masih `"UPLOADING"` atau `"PROCESSING"`, jangan mengembalikan 404 jika batch ID valid.

---

## 6. Isu #5: AI / RAG Pipeline — Sinkronisasi Update Summary & Re-indexing

### 🎯 Masalah & Alur RAG
Admin sekarang dapat mengedit `ai_summary` dan kategori dokumen langsung melalui frontend via `PUT /api/knowledge/{id}`.

### 🛠️ Rekomendasi Solusi AI Engineer
1. **Re-embedding Metadata & Summary:**
   - Saat ringkasan (*summary*) diperbarui oleh admin:
     1. Simpan ringkasan baru di database `knowledge.ai_summary`.
     2. Lakukan update pada chunk khusus summary di vector database (biasanya chunk index 0 atau payload metadata dokumen).
     3. Pastikan payload Qdrant / Chroma seperti `categories` dan `summary` di-refresh agar pencarian semantik (RAG retriever) menggunakan teks ringkasan terbaru yang sudah dikoreksi oleh admin.
2. **Evaluasi Confidence Score:**
   - Ketika summary diedit secara manual oleh manusia, AI confidence dapat diset ke `1.0` (manual review verified) atau diberi flag `is_manually_edited: true` pada metadata dokumen.
