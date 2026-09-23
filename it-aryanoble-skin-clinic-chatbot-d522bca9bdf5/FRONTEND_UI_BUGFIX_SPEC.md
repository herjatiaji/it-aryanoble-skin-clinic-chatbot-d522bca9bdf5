# Panduan & Spesifikasi Bugfix Frontend Developer (FE Dev)
## Bug #5, #10, #11, #12 — Modul Knowledge Base

Dokumen ini adalah spesifikasi teknis dan panduan implementasi untuk Frontend Developer dalam menyelesaikan perbaikan UI dan fitur interaktif pada modul **Knowledge Base** (`/dashboard/knowledge`).

---

## 📋 Daftar Isi
1. [Ringkasan Perubahan](#1-ringkasan-perubahan)
2. [Bug #5: Kolom "Uploaded By" (Nama Pengunggah Dokumen)](#2-bug-5-kolom-uploaded-by)
3. [Bug #10: Checkbox Multiple / Bulk Delete](#3-bug-10-checkbox-multiple--bulk-delete)
4. [Bug #11: Editable AI Summary pada Halaman Detail & Review](#4-bug-11-editable-ai-summary)
5. [Bug #12: Approved Timestamp (Tanggal & Jam Disetujui)](#5-bug-12-approved-timestamp)
6. [Update Interface TypeScript (`types.ts`)](#6-update-interface-typescript)
7. [Checklist Verifikasi Frontend Dev](#7-checklist-verifikasi-frontend-dev)

---

## 1. Ringkasan Perubahan

| Bug ID | Fitur / Masalah | File Frontend Utama | Komponen UI yang Terlibat |
|---|---|---|---|
| **Bug #5** | Menampilkan nama pengguna pengunggah asli di tabel Knowledge Base | `frontend/src/app/dashboard/knowledge/components/knowledge-table.tsx` | `TableHead`, `TableCell`, `Avatar`/`Badge` |
| **Bug #10** | Fitur Checkbox selection + Bulk Delete (Multiple Delete) dokumen | `frontend/src/app/dashboard/knowledge/components/knowledge-table.tsx` | `@/components/ui/checkbox`, `Floating Action Bar`, `ConfirmationModal` |
| **Bug #11** | Summary dapat diedit secara langsung (inline / modal edit) pada detail | `frontend/src/app/dashboard/knowledge/[id]/page.tsx`<br/>`frontend/src/app/dashboard/knowledge/batch/[id]/BatchKnowledgeTabContent.tsx` | Textarea markdown editor, tombol Save/Cancel, modal konfirmasi |
| **Bug #12** | Menampilkan timestamp persetujuan (*Approved At*) pada tabel & detail | `frontend/src/app/dashboard/knowledge/components/knowledge-table.tsx`<br/>`frontend/src/app/dashboard/knowledge/[id]/page.tsx` | Date formatter, sub-label/badge pada kolom Status / Date |

---

## 2. Bug #5: Kolom "Uploaded By"

### 🎯 Masalah
Tabel dokumen Knowledge Base saat ini tidak menampilkan informasi siapa admin atau staf yang mengunggah dokumen tersebut, sehingga riwayat kepemilikan dokumen tidak transparan di antarmuka admin.

### 🛠️ Solusi Backend yang Disediakan
Backend API `GET /api/knowledge/` dan `GET /api/knowledge/{id}` kini mengembalikan field:
- `uploaded_by_name: Optional[str]` (contoh: `"Dr. Sarah Jessica"` atau `"admin_arya"`). Jika user tidak memiliki full name, berisi username. Jika user telah dihapus, fallback ke `"Admin"`.

### 💻 Langkah Implementasi Frontend

#### 1. Perbarui Interface `DisplayRowItem` di `knowledge-table.tsx`
Tambahkan properti `uploadedByName?: string | null`:
```typescript
interface DisplayRowItem {
    id: string;
    isBatch: boolean;
    batchId?: string;
    title: string;
    status: string;
    created_at?: string;
    approved_at?: string | null; // Untuk Bug #12
    uploadedByName?: string | null; // <--- TAMBAHKAN INI
    description: string;
    documentCount?: number;
    rawItem: KnowledgeResponse;
    allFileNames: string[];
    categories: string[];
    projectId?: string | null;
    allDocIds?: string[];
}
```

#### 2. Mapping di `displayRows` (`useMemo` di `knowledge-table.tsx`)
- **Untuk Batch Item**:
  ```typescript
  const uploader = docs[0].uploaded_by_name || "Admin";
  rows.push({
      // ...
      uploadedByName: uploader,
      // ...
  });
  ```
- **Untuk Single Item**:
  ```typescript
  rows.push({
      // ...
      uploadedByName: doc.uploaded_by_name || "Admin",
      // ...
  });
  ```

#### 3. Tambahkan Kolom Header & Cell di Tabel
Letakkan kolom **Uploaded By** di antara kolom **Category** dan **Date**:

```tsx
// Di TableHeader:
<TableHead className="w-36 font-medium text-gray-700">Uploaded By</TableHead>

// Di TableBody (dalam map paginatedItems):
<TableCell>
    <div className="flex items-center gap-2">
        <div className="size-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-[11px] font-semibold shrink-0">
            {(row.uploadedByName || "A").charAt(0).toUpperCase()}
        </div>
        <span 
            className="text-xs font-medium text-zinc-700 truncate max-w-28" 
            title={row.uploadedByName || "Admin"}
        >
            {row.uploadedByName || "Admin"}
        </span>
    </div>
</TableCell>
```

---

## 3. Bug #10: Checkbox Multiple / Bulk Delete

### 🎯 Masalah
Admin harus menghapus dokumen satu per satu dengan mengklik tombol menu aksi per baris. Untuk menghapus puluhan dokumen uji coba atau dokumen lama, proses ini sangat memakan waktu. Diperlukan fitur pemilihan massal (checkbox per row + select all) dan tombol hapus massal (*Bulk Delete*).

### 🛠️ Komponen yang Digunakan
- UI Checkbox yang sudah ada: `@/components/ui/checkbox.tsx` (berbasis `@base-ui/react/checkbox`).
- Mutation delete: `useDeleteKnowledge()` dari `use-knowledge.ts`.
- Modal konfirmasi: `ConfirmationModal` dari `@/components/shared/confirmation-modal`.
- Toast: `toast` dari `sonner`.

### 💻 Langkah Implementasi di `knowledge-table.tsx`

#### 1. Tambahkan State Seleksi
```typescript
import { Checkbox } from "@/components/ui/checkbox";

// State seleksi ID
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
const [isBulkDeleteModalOpen, setIsBulkDeleteModalOpen] = useState(false);
const [isBulkDeleting, setIsBulkDeleting] = useState(false);
```

#### 2. Helper Logic untuk Checkbox (Select All & Single Toggle)
```typescript
// Hitung apakah semua item di halaman aktif sedang terpilih
const currentPageDocIds = useMemo(() => {
    return paginatedItems.flatMap((item) => 
        item.allDocIds && item.allDocIds.length > 0 ? item.allDocIds : [item.id]
    );
}, [paginatedItems]);

const isAllCurrentPageSelected = useMemo(() => {
    if (currentPageDocIds.length === 0) return false;
    return currentPageDocIds.every((id) => selectedIds.has(id));
}, [currentPageDocIds, selectedIds]);

const isSomeCurrentPageSelected = useMemo(() => {
    return currentPageDocIds.some((id) => selectedIds.has(id)) && !isAllCurrentPageSelected;
}, [currentPageDocIds, selectedIds, isAllCurrentPageSelected]);

const handleSelectAllCurrentPage = () => {
    setSelectedIds((prev) => {
        const next = new Set(prev);
        if (isAllCurrentPageSelected) {
            // Uncheck all di halaman aktif
            currentPageDocIds.forEach((id) => next.delete(id));
        } else {
            // Check all di halaman aktif
            currentPageDocIds.forEach((id) => next.add(id));
        }
        return next;
    });
};

const handleToggleRow = (row: DisplayRowItem, e: React.MouseEvent) => {
    e.stopPropagation(); // Mencegah navigasi ke halaman detail
    const targetIds = row.allDocIds && row.allDocIds.length > 0 ? row.allDocIds : [row.id];
    
    setSelectedIds((prev) => {
        const next = new Set(prev);
        const hasAll = targetIds.every((id) => next.has(id));
        if (hasAll) {
            targetIds.forEach((id) => next.delete(id));
        } else {
            targetIds.forEach((id) => next.add(id));
        }
        return next;
    });
};
```

#### 3. Tambahkan Checkbox di `TableHeader`
```tsx
<TableHeader className="bg-gray-50/50">
    <TableRow className="bg-gray-50/50 hover:bg-gray-50/50">
        {/* Kolom Checkbox Select All */}
        <TableHead className="w-10 px-3">
            <div className="flex items-center justify-center">
                <Checkbox
                    checked={isAllCurrentPageSelected}
                    onCheckedChange={handleSelectAllCurrentPage}
                    aria-label="Select all rows on current page"
                />
            </div>
        </TableHead>

        {/* Kolom-kolom lainnya */}
        <SortableTableHead sortKey="title" ...>Knowledge Title</SortableTableHead>
        ...
```

#### 4. Tambahkan Checkbox di `TableRow`
```tsx
<TableRow
    key={row.isBatch ? `batch-${row.batchId}` : `doc-${row.id}`}
    className="hover:bg-gray-50/60 cursor-pointer"
    onClick={() => handleRowClick(row)}
>
    {/* Kolom Checkbox Row */}
    <TableCell className="w-10 px-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-center">
            <Checkbox
                checked={
                    row.allDocIds && row.allDocIds.length > 0
                        ? row.allDocIds.every((id) => selectedIds.has(id))
                        : selectedIds.has(row.id)
                }
                onCheckedChange={() => {
                    const targetIds = row.allDocIds && row.allDocIds.length > 0 ? row.allDocIds : [row.id];
                    setSelectedIds((prev) => {
                        const next = new Set(prev);
                        const hasAll = targetIds.every((id) => next.has(id));
                        if (hasAll) {
                            targetIds.forEach((id) => next.delete(id));
                        } else {
                            targetIds.forEach((id) => next.add(id));
                        }
                        return next;
                    });
                }}
                aria-label={`Select row ${row.title}`}
            />
        </div>
    </TableCell>

    <TableCell>...</TableCell>
```

#### 5. Floating / Sticky Bulk Action Bar
Ketika `selectedIds.size > 0`, tampilkan floating bar di bagian atas tabel atau fixed di bawah:

```tsx
{selectedIds.size > 0 && (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 mb-3 bg-blue-50/80 border border-blue-200 rounded-lg animate-in fade-in slide-in-from-top-2 duration-200">
        <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-blue-900 bg-blue-200/80 px-2 py-0.5 rounded-full">
                {selectedIds.size} selected
            </span>
            <span className="text-xs text-blue-800">documents selected across the knowledge base</span>
        </div>
        <div className="flex items-center gap-2">
            <Button
                variant="ghost"
                size="sm"
                className="text-xs text-zinc-600 hover:text-zinc-900 h-8"
                onClick={() => setSelectedIds(new Set())}
            >
                Clear Selection
            </Button>
            <Button
                variant="destructive"
                size="sm"
                className="gap-1.5 text-xs h-8 px-3 bg-red-600 hover:bg-red-700 text-white shadow-none"
                onClick={() => setIsBulkDeleteModalOpen(true)}
            >
                <RiDeleteBinLine className="size-3.5" />
                <span>Delete Selected ({selectedIds.size})</span>
            </Button>
        </div>
    </div>
)}
```

#### 6. Eksekusi Bulk Delete
```typescript
const handleConfirmBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    setIsBulkDeleting(true);
    try {
        // Hapus secara paralel dengan hideToast: true
        await Promise.all(
            ids.map((id) => deleteMutation.mutateAsync({ id, hideToast: true }))
        );
        toast.success(`Successfully deleted ${ids.length} documents!`);
        setSelectedIds(new Set());
    } catch (err) {
        toast.error("An error occurred while deleting selected documents.");
    } finally {
        setIsBulkDeleting(false);
        setIsBulkDeleteModalOpen(false);
    }
};
```

Sertakan `ConfirmationModal`:
```tsx
<ConfirmationModal
    isOpen={isBulkDeleteModalOpen}
    onOpenChange={setIsBulkDeleteModalOpen}
    title={`Delete ${selectedIds.size} Documents?`}
    description={`Are you sure you want to delete ${selectedIds.size} selected document(s)? All vector embeddings, chunks, and uploaded files will be permanently removed.`}
    confirmText={`Delete ${selectedIds.size} Documents`}
    cancelText="Cancel"
    variant="destructive"
    isLoading={isBulkDeleting}
    onConfirm={handleConfirmBulkDelete}
/>
```

---

## 4. Bug #11: Editable AI Summary

### 🎯 Masalah
Admin perlu mengoreksi ringkasan dokumen (*AI Summary*) apabila terdapat dosis medis, klaim manfaat, atau nama produk yang belum akurat. Saat ini, tombol atau form pengeditan summary terkunci atau hanya tersedia terbatas.

### 🛠️ Solusi Backend yang Sudah Aktif
Endpoint `PUT /api/knowledge/{id}` menerima payload:
```json
{
    "summary": "Teks ringkasan baru hasil perbaikan admin...",
    "categories": ["Acne", "Product"],
    "title": "Nama Dokumen",
    "visibility_settings": { ... }
}
```
Backend akan otomatis memperbarui `ai_summary` di PostgreSQL, sinkronisasi file staging/output, dan mengindeks ulang vektor jika diperlukan.

### 💻 Langkah Implementasi Frontend

#### File 1: `frontend/src/app/dashboard/knowledge/[id]/page.tsx`
Pastikan tombol **Edit Knowledge** aktif untuk status `APPROVED` maupun status `PENDING`:

```tsx
// Ganti baris kondisi tombol Edit:
// SEBELUMNYA: {hasWriteAccess && data?.status === "APPROVED" && (
// SESUDAHNYA:
{hasWriteAccess && (data?.status === "APPROVED" || data?.status === "PENDING") && (
    <div className="flex items-center gap-2">
        {isEditMode && (
            <Button
                variant="outline"
                className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg shadow-none h-10 px-4 font-medium text-sm"
                disabled={isLoading || editKnowledge.isPending}
                onClick={handleCancel}
            >
                Cancel
            </Button>
        )}
        <Button
            variant={isEditMode ? "default" : "outline"}
            className={`gap-2 ${
                isEditMode
                    ? "bg-blue-600 hover:bg-blue-700 text-white"
                    : "border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50"
            } rounded-lg shadow-none h-10 px-4 font-medium text-sm`}
            disabled={isLoading || editKnowledge.isPending}
            onClick={() => {
                if (isEditMode) {
                    setIsSaveModalOpen(true);
                } else {
                    setPendingSummary(data?.ai_summary || "");
                    setIsEditMode(true);
                }
            }}
        >
            {isEditMode ? <RiCheckLine className="size-4" /> : <RiEdit2Line className="size-4" />}
            {isEditMode ? "Save Knowledge" : "Edit Knowledge"}
        </Button>
    </div>
)}
```

#### Quick Inline Edit pada Bagian Summary (`ChatPreview.tsx` / `[id]/page.tsx`):
Di samping judul "AI Summary" atau "Individual Summary", tambahkan tombol pensil kecil agar admin dapat langsung masuk ke mode edit tanpa harus scroll ke atas:
```tsx
<div className="flex items-center justify-between mb-2">
    <h4 className="text-xs font-semibold text-zinc-800 uppercase tracking-wider">AI Summary</h4>
    {!isEditMode && hasWriteAccess && (
        <button
            type="button"
            onClick={() => {
                setPendingSummary(data?.ai_summary || "");
                setIsEditMode(true);
            }}
            className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium cursor-pointer"
        >
            <RiEdit2Line className="size-3.5" />
            <span>Edit Summary</span>
        </button>
    )}
</div>
```

---

## 5. Bug #12: Approved Timestamp (*Approved At*)

### 🎯 Masalah
Pada daftar dokumen, tanggal yang tampil selalu merupakan `created_at` (tanggal upload pertama kali). Ketika dokumen disetujui seminggu kemudian, admin tidak dapat melihat kapan dokumen tersebut resmi aktif/disetujui (*Approved At*).

### 🛠️ Solusi Backend yang Disediakan
Backend API `GET /api/knowledge/` dan `GET /api/knowledge/{id}` kini mengembalikan field:
- `approved_at: Optional[datetime]` (ISO 8601 string, misal: `"2026-09-18T08:30:00Z"`). Field ini berisi waktu approval jika dokumen berstatus `APPROVED`, atau `null` jika masih `PENDING`/`PROCESSING`.

### 💻 Langkah Implementasi Frontend

#### 1. Perbarui Format Tanggal di `knowledge-table.tsx`
Pada kolom **Date**, tampilkan indikasi tanggal dibuat dan tanggal disetujui (jika sudah approved):

```tsx
<TableCell className="whitespace-nowrap text-sm text-zinc-600">
    <div className="flex flex-col gap-0.5">
        <span className="text-xs text-zinc-900 font-medium">
            {row.created_at
                ? new Date(row.created_at).toLocaleDateString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                  })
                : "-"}
        </span>
        {row.status === "APPROVED" && row.rawItem.approved_at && (
            <span 
                className="text-[10px] text-emerald-700 flex items-center gap-1"
                title={`Approved on ${new Date(row.rawItem.approved_at).toLocaleString("id-ID")}`}
            >
                <RiCheckLine className="size-3 shrink-0" />
                <span>
                    Appr:{" "}
                    {new Date(row.rawItem.approved_at).toLocaleDateString("en-GB", {
                        day: "2-digit",
                        month: "short",
                    })}
                </span>
            </span>
        )}
    </div>
</TableCell>
```

#### 2. Tampilkan di Halaman Detail Dokumen (`[id]/page.tsx` & Header Detail)
Tampilkan badge info di sebelah status dokumen:
```tsx
{data?.status === "APPROVED" && data?.approved_at && (
    <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-gray-50 border border-gray-200 px-2.5 py-1 rounded-md">
        <span>Approved at:</span>
        <span className="font-medium text-zinc-800">
            {new Date(data.approved_at).toLocaleDateString("id-ID", {
                day: "2-digit",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            })}{" "}
            WIB
        </span>
    </div>
)}
```

---

## 6. Update Interface TypeScript

Buka file [frontend/src/app/dashboard/knowledge/api/types.ts](it-aryanoble-skin-clinic-chatbot-d522bca9bdf5/it-aryanoble-skin-clinic-chatbot-d522bca9bdf5/frontend/src/app/dashboard/knowledge/api/types.ts):

Perbarui interface `KnowledgeResponse` agar sinkron dengan API backend terbaru:

```typescript
export interface KnowledgeResponse {
	id: string; // UUID
	title: string;
	content?: string | null;
	file_name: string;
	original_path: string;
	mime_type?: string | null;
	file_size?: number | null;
	type: KnowledgeType;
	status: KnowledgeStatus;
	ai_summary?: string | null;
	ai_confidence?: number | null;
	uploaded_by: string; // UUID
	uploaded_by_name?: string | null; // <--- TAMBAHKAN UNTUK BUG #5
	approved_by?: string | null; // UUID
	approved_at?: string | null; // ISO Date String <--- TAMBAHKAN UNTUK BUG #12
	project_id?: string | null; // UUID
	metadata?: {
		visibility_settings?: VisibilitySettings;
		categories?: string[];
		suggested_categories?: Array<{ id?: string | null; name: string }>;
		chunks?: KnowledgeChunkItem[];
		batch_id?: string;
		upload_batch_id?: string;
		batch_summary?: string;
		[key: string]: unknown;
	} | null;
	created_at: string;
	updated_at: string;
}
```

---

## 7. Checklist Verifikasi Frontend Dev

Setelah melakukan perubahan, jalankan pengujian manual berikut di browser:

- [ ] **Bug #5 (Uploaded By)**:
  - Buka `/dashboard/knowledge`.
  - Pastikan terdapat kolom **Uploaded By**.
  - Pastikan nama admin / uploader muncul dengan rapi (avatar inisial + teks nama).
  - Pastikan untuk baris batch, nama pengunggah dokumen batch tampil dengan tepat.

- [ ] **Bug #10 (Checkbox & Multiple Delete)**:
  - Buka `/dashboard/knowledge`.
  - Checkbox "Select All" di header tabel mencentang seluruh baris pada halaman aktif.
  - Floating bar muncul dengan info jumlah dokumen yang dipilih (misal: `3 selected`).
  - Klik "Clear Selection", seluruh centang hilang dan floating bar tertutup.
  - Pilih 2 atau 3 dokumen, klik tombol "Delete Selected".
  - Modal konfirmasi muncul dengan peringatan yang jelas.
  - Setelah dikonfirmasi, dokumen terhapus dan tabel otomatis me-refresh tanpa reload halaman.

- [ ] **Bug #11 (Editable Summary)**:
  - Buka detail dokumen (`/dashboard/knowledge/[id]`).
  - Klik tombol "Edit Knowledge" atau tombol pensil di ringkasan.
  - Edit teks ringkasan pada textarea markdown.
  - Klik "Save Knowledge", konfirmasi modal, dan pastikan notifikasi sukses muncul.
  - Refresh halaman, teks ringkasan yang baru tetap tersimpan.

- [ ] **Bug #12 (Approved Timestamp)**:
  - Pada tabel dokumen yang berstatus `APPROVED`, periksa sub-teks tanggal persetujuan (`Appr: DD MMM`).
  - Pada halaman detail dokumen `APPROVED`, periksa label waktu persetujuan (tanggal & jam lengkap).
  - Pada dokumen `PENDING`, pastikan timestamp persetujuan tidak muncul atau bernilai strip (`-`).
