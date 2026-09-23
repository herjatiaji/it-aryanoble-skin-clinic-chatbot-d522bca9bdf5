# Backend Changelog

All notable changes to the Arya Noble AI Chatbot Backend are documented in this file.

## [1.4.0] - 2026-09-14

### AWS S3 IRSA Authentication, Storage Diagnostics & Clean Relative Image Paths
- **AWS S3 IRSA & IAM Credential Chain (`app/services/storage.py`, `app/core/config.py`)**:
  - Implemented dynamic authentication detection for AWS EKS IRSA (`AWS_ROLE_ARN`, `AWS_WEB_IDENTITY_TOKEN_FILE`) without requiring static keys or secret configs.
  - Made `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, and `S3_SECRET_KEY` optional to auto-detect AWS S3 virtual-hosted addressing vs local MinIO path-style addressing.
  - Added resilient error handling around bucket initialization so IRSA roles without `CreateBucket`/`PutBucketPolicy` permissions initialize seamlessly.
- **FastAPI Storage Diagnostic Endpoints (`app/api/routers/storage.py`)**:
  - Added `GET /api/storage/debug/health` to probe authentication mode, AWS environment variables, and bucket connectivity/permissions (`s3:GetObject`, `s3:ListBucket`).
  - Added `GET /api/storage/debug/diagnose?key=...` for step-by-step resolution tracing of specific image keys across S3 buckets and local disk.
- **Clean Relative Image Paths & Formatting (`app/services/storage.py`, `app/rag/services/rag_generator.py`)**:
  - Reverted forced absolute domain prefixes in markdown, normalizing image tags to clean, portable `/api/storage/images/...` endpoints.
  - Frontend `resolveImageUrl` seamlessly binds `NEXT_PUBLIC_API_URL` to relative storage paths.

---

## [1.3.9] - 2026-09-11

### Revert Category Settings to Unified Per-Knowledge Document Level
- **Unified Knowledge Categories (`app/api/routers/knowledge.py`, `app/rag/router.py`, `app/rag/utils/summary_chunker.py`)**:
  - Reverted category management from chunk-level / section-level selection back to document-level configuration.
  - In `app/rag/router.py` (`approve_document`, `edit_approved_document`, `edit_pending_document`), removed custom per-section category preservation and ensured all chunks uniformly inherit document categories.
  - In `app/rag/utils/summary_chunker.py`, simplified `_build_chunk_meta` so all structural chunks receive the full list of document categories uniformly.
  - In `app/api/routers/knowledge.py`, removed chunk-level category aggregation and directly used `payload.categories` as the source of truth, cascading categories to all database chunk metadata.
- **Frontend Category Settings (`category-settings.tsx`, `chat-preview.tsx`, `types.ts`)**:
  - Replaced `SectionCategoriesEditor` with `CategorySettings` across all Knowledge detail, preview, pending, and approved editing screens.
  - Removed per-chunk category derivation from `extractKnowledgeCategories`.

---

## [1.3.8] - 2026-09-11

### General Chat Confirmation Standardization & English Default Messages
- **Knowledge & RAG Routers (`app/api/routers/knowledge.py`, `app/rag/router.py`)**:
  - Aligned confirmation, success, and cancellation response messages with English default strings (`Changes to '...' were successfully applied to ... Knowledge Base documents.`, `Item '...' was successfully deleted from ...`, `Operation cancelled. No changes were applied to the Knowledge Base.`).
  - Standardized JSON responses for all batch and single-item operations with flat styling and full parity across API responses.
- **Frontend Action Confirmation Card (`action-card.tsx`, `parser.ts`)**:
  - Replaced all raw emojis with contextual Remix Icons (`RiFileEditLine`, `RiDeleteBin7Line`, `RiFileTextLine`, `RiInputField`, `RiArrowRightLine`).
  - Applied flat styling with `shadow-none`, `rounded-lg`, and unified header button sizing (`h-9 px-4`).

---

## [1.3.7] - 2026-09-11

### General Chat Confirmation & Response Text Cleanup
- **Knowledge & RAG Routers (`app/api/routers/knowledge.py`, `app/rag/router.py`)**:
  - Removed all emoji prefixes (`📋`, `✅`, `🗑️`, `❌`) from confirmation preview prompts and post-action assistant messages.
  - Ensured all confirmation messages, success messages, and cancellation responses adhere to clean, professional markdown standards without distracting emoji characters.

---

## [1.3.6] - 2026-09-11

### Storage Proxy S3 UUID Prefix Fallback Resolution
- **Storage Service (`app/services/storage.py`)**:
  - Enhanced `get_s3_object_stream()` and `get_s3_object_data()` with automatic 32-hex UUID prefix matching against MinIO storage.
  - Resolved 404 image load issues when LLMs or Markdown summarizers slightly alter, autocomplete, or truncate human-readable image filename suffixes (e.g. `..._Gentle_Ac.jpeg` vs `..._Gentle_Acne.jpeg`).
  - Guarantees 100% resilient image asset rendering in both Dashboard Knowledge review and Doctor Portal chat streams.

---

## [1.3.5] - 2026-09-10

### Backend Dynamic Image URL Expansion for CIS Floating Chat & Frontend
- **Storage Service URL Expansion (`app/services/storage.py`)**:
  - Enhanced `_format_browser_url()` to intelligently normalize raw S3 keys (`images/...`), relative proxy paths (`/api/storage/images/...`), and already absolute external URLs against the configured `S3_PUBLIC_URL`.
  - Added smart environment-based domain fallback (`dev`, `staging`, `production`) for `S3_PUBLIC_URL` to guarantee absolute URLs in external CIS chats even without explicit environment configuration.
  - Implemented `expand_image_urls_in_markdown()` to scan and expand markdown image tags `![alt](url)` to absolute URLs dynamically.
- **RAG Subsystem Dynamic Normalization (`app/rag/services/rag_generator.py`, `app/rag/router.py`)**:
  - Enhanced `build_prompt()` to dynamically expand relative image URLs inside retrieved context chunks prior to LLM synthesis, enabling the model to stream absolute URLs in real time.
  - Enhanced `_normalize_image_captions_in_text()` and `_sanitize_answer()` to rewrite all output markdown image URLs using `expand_image_urls_in_markdown()`.
  - Enhanced SSE streaming in `generate_answer_stream()` to dynamically normalize `results` context metadata before emitting initial SSE payload.
  - Updated `run_chat_pipeline()` in `app/rag/router.py` to ensure final chat messages always contain absolute URLs.
- **Cross-Origin & Multi-Tenant Compatibility**:
  - Enabled external CIS floating chat (`https://cis.erha.co.id`) to embed images directly from standard Markdown responses without 404 domain collisions or authentication requirements.

---

## [1.3.4] - 2026-09-10


### BM25 Sparse Search Metadata Visibility Filtering Fix
- **BM25 Whitelist Enforcement (`app/rag/services/rag_retriever.py`)**:
  - Corrected `BM25Index.search` metadata filtering logic to ensure user context `['all']` does not bypass chunk-level whitelist restrictions (`doctors`, `clinics`, `doctor_types`).
  - Fixed check to verify specific user attributes against chunk whitelist when `chunk_val` does not contain `'all'`, matching PGVector SQL filtering behavior and eliminating knowledge leakage across doctor profiles.

---

## [1.3.3] - 2026-09-09

### Document Title Synchronization & Chunk Cascade
- **Title Fallback & Resolution (`app/rag/router.py`)**:
  - Updated `edit_approved_document` and `edit_pending_document` to robustly resolve `updated_title` prioritizing non-empty `request.title`, falling back to `existing_doc.get("title")` and then `file_name`.
  - Cascaded `updated_title` to `chunk.metadata["title"]` across all chunks during document edits.
  - Harmonized chunk cascading in `edit_approved_document` with pending revision staging structure (`pending_doc_structure`).
- **Database & Staging Title Consistency (`app/api/routers/knowledge.py`)**:
  - Ensured `k_entry.title` and `k_entry.metadata_["title"]` are both synchronized with updated title.

---

## [1.3.2] - 2026-09-09

### Document-Level Visibility Cascading to Chunk Metadata & Vector Indexing
- **Chunk Metadata Visibility Synchronization (`app/rag/router.py`)**:
  - Updated `edit_approved_document`, `edit_pending_document`, and `approve_document` to cascade top-level document `visibility_settings` (`clinics`, `doctor_types`, `doctors`) to every chunk's `metadata` fields before re-indexing into PGVector and BM25.
  - Ensures doctor role-based filtering in `HybridRetriever` and vector store queries accurately enforces document-level permissions on individual chunks.
- **Database Chunk Visibility Consistency (`app/api/routers/knowledge.py`)**:
  - Enhanced `edit_knowledge` to synchronize `k_entry.metadata_["chunks"]` with the active document-level `visibility_settings`.

---

## [1.3.1] - 2026-09-09

### Per-Chunk Category Preservation During Approval & Sync
- **Approval Re-Chunking Guard (`app/rag/router.py`)**:
  - Enhanced `approve_document` to inspect existing chunk metadata before re-chunking. If chunks already contain user-customized per-section categories (`metadata.is_custom` or `metadata.categories`), existing chunks are preserved and indexed directly into PGVector and BM25 instead of being wiped out by top-level summary re-chunking.
- **Dual-Sync Chunks Persistence (`app/rag/router.py`, `app/api/routers/knowledge.py`)**:
  - Ensured `approve_document` and `approve_knowledge` persist customized `chunks` directly into PostgreSQL `metadata_["chunks"]` and `data/output/{id}.json`.

---

## [1.3.0] - 2026-09-09

### Section-Aware Category Persistence & Bottom-Up Chunk Integration
- **Per-Section Chunk Metadata Schema (`app/rag/schemas.py`)**:
  - Extended `EditApprovedDocumentRequest` to accept `chunks: Optional[List[Dict[str, Any]]] = None`, allowing section-level category edits to be passed and persisted directly into chunk metadata.
- **Section Chunk Preservation & Re-Indexing (`app/rag/router.py`)**:
  - Enhanced `edit_approved_document` and `edit_pending_document` to prioritize supplied `request.chunks` when updating documents, ensuring user-defined per-section categories are stored in chunk metadata and indexed into PGVector and BM25.
- **Bottom-Up Category Synchronization (`app/api/routers/knowledge.py`)**:
  - Enhanced `edit_knowledge` (`PUT /api/knowledge/{id}`) to derive top-level document categories from modified chunk metadata (`payload.chunks`) and synchronize changes to PostgreSQL `metadata_["chunks"]`, MinIO canonical JSON, and PGVector.

---

## [1.2.9] - 2026-09-08

### 100% Stateless Architecture, BM25 MinIO SSOT & Out-of-Band Sync Isolation
- **BM25Index MinIO Persistence & In-Memory Hydration (`app/rag/services/rag_retriever.py`)**:
  - Enhanced `BM25Index.save()` and `BM25Index.load()` to serialize and persist index pickle bytes directly to MinIO Object Storage (`knowledge-documents/indexes/bm25_index.pkl`).
  - Preserved 100% of the AI Engineer's exact `rank-bm25` Python algorithm, tokenization, ingredient intent boosting (+0.35), and cross-encoder reranking in memory without local disk dependencies.
- **MinIO Presigned 307 Redirection & Storage Offloading (`app/api/routers/storage.py`)**:
  - Implemented `307 Temporary Redirect` to cryptographically signed S3 presigned URLs in `GET /api/storage/{s3_key}`, offloading binary image delivery from FastAPI worker threads directly to MinIO.
- **Approved Document Edit & Refine Promotion Persistence (`app/api/routers/knowledge.py`)**:
  - Fixed `PUT /api/knowledge/{id}` so that when saving an approved document with an active refinement staging draft, the endpoint merges draft modifications, calls `edit_approved_document` to reindex PGVector and BM25, purges the staging draft, and commits updated summary, title, and categories directly to PostgreSQL DB.
- **Prompt Attachment Image Extraction (`app/rag/router.py`)**:
  - Enhanced `refine_approved_document` and `refine_pending_document` to automatically detect and parse embedded image markdown tags (`![...](url)`) within pre-parsed prompt attachments, ensuring newly attached images are embedded and preserved in the top-level summary.

---

## [1.2.8] - 2026-09-07

### Fullstack Risk Analysis & Defect Remediation
- **Database Soft-Deleted Category Sanitation (`app/api/routers/knowledge.py`)**:
  - Implemented `sanitize_knowledge_categories(db, categories)` helper that queries active database records (`Category.deleted_at.is_(None)`) and prunes soft-deleted category names from knowledge metadata.
  - Integrated sanitation into `get_knowledge` and `edit_knowledge` endpoints.
- **Image Role & URL Metadata Preservation (`app/api/routers/knowledge.py`)**:
  - In `edit_knowledge`, ensured granular image role metadata (`metadata_["images"]` with roles like `CLINICAL_BEFORE`, `TREATMENT_PROCEDURE`, captions) and `metadata_["image_urls"]` are deeply preserved during title, summary, or category updates.
- **CIS Alphanumeric & Numeric Identifier Parsing Safety (`app/services/cis_sync.py`, `app/api/dependencies.py`)**:
  - Standardized all external CIS ID parsing with `parse_cis_int` across auth dependencies and webhook bulk synchronization payloads.
- **Storage Proxy Streaming & Multi-Folder Fallback (`app/api/routers/storage.py`)**:
  - Verified `StreamingResponse` for S3 object delivery and multi-tier local folder search hierarchy (`data/temp/images`, `data/output/images`, `data/images`, `data/documents`, `data/storage`).

---

## [1.2.7] - 2026-09-04

### DOCX Embedded Table & Inline Image Parser Enhancement
- **Relationship-Aware Image Extraction in DOCX Fast Parser (`app/rag/utils/parser.py`)**:
  - Enhanced `_parse_docx_fast` to pre-extract and upload embedded images directly from `doc.part.rels` (`word/media/*`), mapping relationship IDs (`rId`) to MinIO storage URLs.
  - Added XML drawing traversal (`.//a:blip/@r:embed`) across table cells and paragraphs, preserving inline and table-embedded images as markdown `![ColumnName/Image](url)` tags.
  - Fixed issue where cells containing only drawings (e.g. Before & After images) returned empty strings (`cell.text`), leaving tables blank in parsed document output and AI summaries.
- **Ingestion Cancellation Reset on Upload & Reingest (`app/rag/router.py`)**:
  - Implemented `uncancel_ingestion_job(knowledge_id)` to clear stale cancellation flags from `CANCELLED_INGESTION_IDS` when re-uploading or re-ingesting documents, preventing false-positive background job aborts.

---

## [1.2.6] - 2026-09-02

### CIS Master Data Batch Webhook Synchronization
- **Polymorphic Ingestion & Key Aliases (`app/services/cis_sync.py`, `app/api/routers/webhooks.py`)**:
  - `upsert_branch_payload` and `upsert_doctor_payload` now accept both single JSON objects and list arrays, allowing CIS to push entities in batches without `AttributeError`.
  - Added key aliases in `bulk_sync_payload` for branches (`branches`, `branch`), doctors (`users`, `doctors`, `doctor`), and user branches (`user_branches`, `user_branchs`, `doctor_branches`).
- **Defensive Safeguards & Collision Avoidance (`app/services/cis_sync.py`)**:
  - Added duplicate email collision guard preventing PostgreSQL `users_email_key` unique constraint violations when doctors share placeholder or clinic emails.
  - Added strict integer parsing for IDs and silent filtering for malformed/null entries.
  - Implemented ecosystem-scoped pruning so full sync with `prune_omitted: true` only reconciles branches and doctors within the ecosystems present in the incoming payload.
- **Race Condition Prevention in Webhooks (`app/api/routers/webhooks.py`)**:
  - Moved `broadcaster.publish("sync_completed")` to execute strictly after `await db.commit()`, ensuring frontend listeners read fully committed data.
- **Documentation (`docs/CIS_BATCH_SYNC.md`, `docs/cis-integration-guide.md`)**:
  - Authored comprehensive integration guides and RSA signature examples in Node.js, Python, and PHP/Laravel.

---

## [1.2.5] - 2026-09-02

### Approved Knowledge Refinement Fix
- **Module-Level Datetime Import in RAG Router (`app/rag/router.py`)**:
  - Added module-level `from datetime import datetime, timezone` to resolve `NameError: name 'datetime' is not defined` triggered in `refine_approved_document` during timestamp generation for `edit_history`.

---

## [1.2.4] - 2026-09-01

### Remote AI Subsystem Merge & Storage Consolidation
- **Dual-Bucket MinIO Architecture & Canonical JSON Synchronization (`app/services/storage.py`, `app/rag/router.py`)**:
  - Integrated dual-bucket configuration (`images` as public-read, `knowledge-documents` as private) with `_format_browser_url` proxy fallback.
  - Added MinIO synchronization via `upload_canonical_json` on document approval and refinement.
  - Harmonized parallel image uploads (`upload_images_parallel`) with document normalization (`normalize_document_text`) in `app/rag/utils/parser.py`.
  - Preserved active ingestion cancellation guards (`is_ingestion_cancelled`) alongside verbatim parser canonical text handling.

---

## [1.2.3] - 2026-09-01

### Ingestion Failure Resilience, Prompt Processing & Active Cancellation
- **Active Background Ingestion Cancellation & Abort Guards (`app/rag/router.py`, `app/api/routers/knowledge.py`)**:
  - Implemented thread-safe cancellation tracking (`CANCELLED_INGESTION_IDS`, `cancel_ingestion_job`, `is_ingestion_cancelled`).
  - Added cancellation checkpoints throughout `process_ingestion_background` (pre-parsing, post-parsing, pre-LLM review, post-LLM review, pre-DB commit) to immediately halt background processing and discard temporary files when a user cancels an ingestion.
  - Linked `cancel_ingestion_job` directly into `DELETE /api/knowledge/{knowledge_id}`.
- **Parallel PDF Image Uploads (`app/rag/utils/parser.py`)**:
  - Refactored `_parse_pdf_fast` to batch embedded images and upload concurrently via `upload_images_parallel`, eliminating sequential HTTP latency and preventing lingering uploads when parsing is aborted.
- **Ingestion Failure Resilience & Error State Persistence (`app/rag/router.py`)**:
  - Replaced silent return on missing parser output with explicit error handling.
  - In `process_ingestion_background`, unhandled exceptions now write a `"status": "FAILED"` document in `data/pending/{knowledge_id}.json` with error diagnostics and update PostgreSQL `Knowledge.status` to `REJECTED` with `"error"` and `"status": "FAILED"` stored in `metadata_`.
  - Automatic cleanup of temporary files in `data/temp/` on error.
- **Batch Coordinator Fault Tolerance (`app/rag/router.py`)**:
  - `trigger_batch_summary_after_all_done` now counts failed/rejected files as completed states, preventing the coordinator from hanging for 180 seconds when a file in a batch fails.
- **SSE Streaming Client Disconnect Detection (`app/api/routers/chats.py`)**:
  - Added `if await request.is_disconnected(): break` guards in `POST /api/chats/{session_id}/messages` SSE generator loop to halt token generation immediately when a client aborts or closes the session.
- **Prompt Processing Stop Generation & Error Boundaries (`frontend`, `mock-cis`)**:
  - Added `AbortController` signal and Stop button controls to `ChatPreview` (`chat-preview.tsx`) and Doctor CIS floating chat (`FloatingChatbot.jsx`).
  - Added dedicated failed document alert banner in `ChatPreview` and Cancel Ingestion confirmation action in `KnowledgeDetailPage` (`[id]/page.tsx`) and `BatchKnowledgePage` (`batch/[id]/page.tsx`).

---

## [1.2.2] - 2026-08-31

### Knowledge Lifecycle Data Integrity & Bug Fixes
- **Exact UUID Match Soft-Deletion & Complete Index Purge (`app/api/routers/knowledge.py`, `app/rag/router.py`, `app/rag/services/vector_store.py`, `app/rag/services/rag_retriever.py`)**:
  - `list_knowledge` now purges stale staging files strictly by `deleted_ids` (UUIDs), eliminating the bug where files with the same name as previously deleted documents were purged upon upload.
  - `delete_approved_document` and `delete_knowledge` purge matching chunks completely from PostgreSQL `arya_noble_kb` table, `PGVectorAdapter`, and `BM25Index` across `source_file`, `knowledge_id`, and `file_name`, guaranteeing no "zombie knowledge" can be retrieved after deletion.
  - Query filtering strictly uses exact `Knowledge.id == target_uuid`, removing broad substring `ilike("%...%")` matching that caused accidental deletion of unrelated documents.
- **Self-Healing DB Fallback (`app/api/routers/knowledge.py`, `app/rag/router.py`)**:
  - Added self-healing fallback to `edit_pending_document` and `edit_approved_document` that loads the document from PostgreSQL `Knowledge` if the disk staging JSON is missing, preventing 404 errors during category edits and approval.
- **Continuous Batch ID Preservation (`app/api/routers/knowledge.py`, `app/rag/router.py`)**:
  - Explicitly preserved `batch_id`, `upload_batch_id`, and all audit metadata fields (`initial_prompt`, `staging_history`, `edit_history`, `timing_metrics`) across all edit, refine, and status transitions, ensuring multi-file batch groups never separate in the dashboard table.

---

## [1.2.1] - 2026-08-31

### Storage Proxy & Structure-Aware Image Support
- **FastAPI Public Storage Proxy (`app/api/routers/storage.py`, `app/services/storage.py`)**:
  - Implemented `GET /api/storage/{s3_key:path}` endpoint to stream MinIO and local assets via FastAPI with HTTP 200 and `Cache-Control: public, max-age=86400`, eliminating the need to expose MinIO port 9000 to external networks or firewalls.
  - Added configurable `S3_PUBLIC_URL` setting and automatic failover in `_get_client()`.
- **Structure-Aware Image Extraction (`app/rag/utils/summary_chunker.py`)**:
  - Enhanced markdown image regex `!\[.*?\]\(([^\s\)]+)\)` to extract both relative proxy URLs (`/api/storage/...`) and absolute URLs into chunk metadata.

---

## [1.2.0] - 2026-08-31

### Ingestion Prompt Lifecycle & Metadata Archival
- **Background Ingestion Metadata Sync (`app/rag/router.py`)**:
  - `process_ingestion_background` now synchronizes `initial_prompt`, `history`, `suggested_categories`, `document_type`, and `timing_metrics` directly into PostgreSQL `Knowledge.metadata_` on document pending transition.
- **Approval History Archival & Clean Thread Lifecycle (`app/rag/router.py`, `app/api/routers/knowledge.py`)**:
  - Staging conversation turns are now archived in `metadata.staging_history` upon approval, while the active `history` array resets cleanly to present canonical approved knowledge in the doctor/admin view.
  - Refinement turns on approved documents during Edit Mode are archived in `metadata.edit_history`.
- **Batch Executive Summary Custom Prompt Injection (`app/rag/router.py`)**:
  - `synthesize_batch_executive_summary` accepts `user_prompt` and applies a high-priority user instruction block to the multi-file reconciliation prompt.

---

## [1.1.0] - 2026-07-22

### Major Milestone: Unification of `arya-noble-rag` into `backend/app/rag/`

The standalone AI team repository (`arya-noble-rag`) has been fully merged and integrated into the main `backend` codebase inside `backend/app/rag/`. This eliminates repository fragmentation and establishes a single shared workspace where AI Engineers and Backend Engineers collaborate directly.

---

### Architecture Overview Post-Merge

```text
backend/app/rag/
├── config.py             # Isolated RAG settings (PGVector connection, OpenAI models, BM25 path)
├── deps.py               # Dependency injection wrappers for app.state singletons
├── router.py             # RAG API endpoints (/api/ai/*)
├── schemas.py            # Pydantic DTOs (ChatRequest, ApproveRequest, RefineRequest, etc.)
├── services/             # Core AI Pipeline Components
│   ├── evaluation.py     # Search quality metric evaluator (Hit Rate & MRR)
│   ├── factory.py        # AdapterFactory (OpenAI / Gemini / PGVector adapters)
│   ├── interfaces.py     # BaseVectorStoreAdapter & BaseLLMAdapter base classes
│   ├── rag_generator.py  # GenerationPipeline & OpenAIAdapter (gpt-4o-mini)
│   ├── rag_pipeline.py   # IngestionPipeline (Docling -> CustomChunker -> Vector DB)
│   ├── rag_retriever.py  # HybridRetriever (BM25 + PGVector + Reranker + Intent Boost)
│   └── vector_store.py   # PGVectorAdapter (PostgreSQL pgvector cosine distance search)
└── utils/                # RAG Utilities
    ├── chunker.py        # Heading-based & Semantic CustomChunker strategies
    ├── logger.py         # Structured logging helpers
    ├── metadata.py       # Document metadata extraction & language detection
    └── parser.py         # Docling document text & table extraction engine
```

---

### Sprint-by-Sprint Technical Breakdown

#### Sprint 1: Dependency Cleanup & Directory Unification
- **Python Dependencies (`requirements.txt`)**:
  - Added `rank-bm25` (In-memory BM25 Okapi sparse keyword search engine).
  - Added `psycopg[binary]` (Synchronous PostgreSQL driver for `PGVectorAdapter`).
  - Standardized on `langchain-openai` as the primary LLM provider library (omitted unused Google GenAI packages).
- **Directory Cleanup**:
  - Removed legacy, unneeded RAG subdirectories (`core/`, `embeddings/`, `generation/`, `ingestion/`, `retrieval/`, `evaluation/`).
  - Structure reorganized under clean `app/rag/services/` and `app/rag/utils/` submodules.

#### Sprint 2: Import Refactoring & Lifespan Injection
- **Import Paths Refactored**:
  - Remapped all internal imports in `app/rag/**/*.py` from standalone paths (`from app.services...`) to modular backend paths (`from app.rag.services...`, `from app.rag.utils...`, `from app.rag.config`).
- **OpenAI Model Standardization**:
  - Configured `OpenAIAdapter` using `gpt-4o-mini` as the primary default LLM engine in `app/rag/config.py` and `app/rag/services/factory.py`.
- **FastAPI Lifespan Integration (`app/main.py`)**:
  - Added startup initialization for heavy RAG singletons (`vector_store`, `ingestion_pipeline`, `bm25_index`, `reranker`, `hybrid_retriever`, `llm_adapter`, `generation_pipeline`).
  - Attached singletons to `app.state` to avoid redundant object instantiation during HTTP requests.
  - Mounted the unified RAG router at `/api/ai` (OpenAPI tag: `AI / RAG`).

#### Sprint 3: Database Dual-Sync & Frontend Compatibility Layer
- **Doctor Chat Integration (`app/api/routers/chats.py`)**:
  - Upgraded `process_ai_response()` background task to invoke the unified `GenerationPipeline` with Reranking and intent boosting.
  - Formatted AI responses with grounded citations (`[1]`, `[2]`) and persisted results into the PostgreSQL `ChatMessage` table for seamless Next.js chat rendering.
- **Knowledge Admin Dual-Sync (`app/rag/router.py`)**:
  - Updated `POST /api/ai/ingest` to dual-sync uploads into PostgreSQL `Knowledge` DB table while simultaneously parsing via `Docling` and indexing into `PGVector` + `BM25`.
  - Guarantees the Admin Frontend page (`/admin/knowledge`) displays live document upload status in real-time.
  - Refactored `/api/ai/ingest` to process document chunking and AI summarization asynchronously via `FastAPI BackgroundTasks`, enabling instant API responses and immediate frontend redirection.
- **Human-in-the-Loop (HITL) Staging API**:
  - Introduced endpoints for staged document approval & refinement:
    - `POST /api/ai/ingest`: Stage file in `data/pending/` with AI text accuracy evaluation.
    - `GET /api/ai/ingest/pending/{filename}`: View staged chunks & AI feedback.
    - `POST /api/ai/ingest/pending/{filename}/refine`: Refine chunk content via natural language instructions.
    - `POST /api/ai/ingest/approve`: Index approved chunks to PGVector & BM25.
    - `POST /api/ai/search/evaluate`: Run Hit Rate & MRR benchmark evaluations.

#### Sprint 4: AI Team Collaboration & Guidelines
- **Developer Guidelines (`AGENTS.md`)**:
  - Updated `backend/AGENTS.md` and `frontend/AGENTS.md` to document the unified folder structure, API contracts, and testing procedures.
  - Provided direct Swagger UI testing instructions (`http://localhost:8000/docs#/AI%20%2F%20RAG`).

#### Sprint 5: Security & UI Sync Fixes
- **API Key Decryption**: 
  - Restored API key encryption in `app/api/routers/config.py` for security purposes.
  - Added explicit decryption in `app/rag/services/factory.py` so the `AdapterFactory` can correctly process encrypted `LLM_API_KEY`s before initializing OpenAI adapters (authorized security exception).
- **Out-of-Band Summary Sync**:
  - Intercepted `GET /api/knowledge/{id}` in `app/api/routers/knowledge.py` to seamlessly auto-sync the latest AI-generated summary from the `rag` staging JSON files to the PostgreSQL database, ensuring UI freshness after HITL refinement/approval without modifying internal `rag` router logic.
- **Chunk Metadata Synchronization**:
  - Fixed a bug in `app/rag/router.py` (`edit_approved_document`, `edit_pending_document`, `approve_document`) where only the primary category was assigned to chunk metadata. Now, the complete array of categories (e.g., `["Acne", "Anti-Aging"]`) is correctly injected into every chunk's metadata prior to PGVector indexing, ensuring accurate dense vector filtering.

#### Sprint 6: Real-time SSE Chat Streaming
- **LLM Streaming (`app/rag/services/interfaces.py`, `app/rag/services/rag_generator.py`)**:
  - Added an asynchronous generator method `generate_stream()` to `BaseLLMAdapter` and implemented it in `OpenAIAdapter` using LangChain's native `astream` to yield tokens immediately.
  - Implemented `generate_answer_stream()` inside `GenerationPipeline` to yield initial context metadata (JSON) followed by real-time LLM text tokens, replacing the slow blocking generation for chat interfaces.
- **SSE Chat Endpoint (`app/api/routers/chats.py`)**:
  - Completely refactored `POST /api/chats/{session_id}/messages` to return a `StreamingResponse` using the Server-Sent Events (SSE) `text/event-stream` standard.
  - Removed the background task dependency; user messages now instantly trigger the real-time stream, persisting the final AI message directly to the PostgreSQL database exactly when generation finishes.
- **Frontend Sync Strategy (`frontend`)**:
  - Eliminated the 3-second React Query polling mechanism inside `useChatMessages`.
  - Rewrote the `useSendMessage` mutation to execute a native `fetch` POST, utilizing a custom stream reader and text decoder to instantly parse SSE chunks and feed an optimistic "streaming bubble" UI on the doctor chat page.

---

### Summary of Key Improvements

| Feature | Before (Legacy Backend RAG) | After (Unified `arya-noble-rag`) |
| :--- | :--- | :--- |
| **Document Parsing** | Basic text splitter | **Docling Engine** (Extracts headers, tables, & layout context) |
| **Search Strategy** | Dense PgVector only | **Hybrid Search**: Dense (`PGVector`) + Sparse (`BM25Okapi`) + Reciprocal Rank Fusion (RRF) |
| **Query Understanding** | Single query search | **Multi-Intent Query Splitting** (Splits complex queries containing `"dan"`, `"serta"`, `"and"`) |
| **Reranking** | Basic external reranker | **Cross-Encoder (`bge-reranker-base`)** with **Section & Intent Boosting** (+0.05 score boost) |
| **LLM Adapter** | Generic ChatOpenAI | **OpenAIAdapter** (`gpt-4o-mini`) with ground-rule prompt & citation mapping `[1]`, `[2]` |
| **Document Review** | Direct DB insert | **HITL Staging Workflow**: AI auto-review, accuracy grading, & interactive prompt refinement |
| **Chat Generation** | REST POST + 3-sec polling | **Real-time SSE Streaming**: Async native fetch & instant token rendering |
| **Access Control (ABAC)** | Static/Unfiltered vector search | **Dynamic Visibility Filtering**: Branch/Role-based exclusions built into PGVector search |
| **Ingestion Pipeline** | Single file tracking | **Multi-File Batch Sync**: Returns `batch_id` & explicit parsed `title`s (not just filename) |
| **Prompt Engineering** | Unstructured prompts | **XML Structured Prompts**: With native tool calling & strict LLM adherence |
| **Table Existence Check** | `:tablename::regclass` (Emits SQL `UndefinedObjectError`) | **`to_regclass(:tablename)`**: Evaluates to `NULL` without PostgreSQL error logs |
| **Ingestion Prompt & History** | Staging turns mixed or lost on approve | **Prompt Lifecycle & Archival**: Synchronizes prompt metadata in background; archives to `staging_history` on approval & `edit_history` on edit; keeps published view clean |
| **Batch Executive Summary** | Hardcoded static prompt | **Custom Prompt Guided Synthesis**: Incorporates user prompt instructions into multi-file batch reconciliation |


