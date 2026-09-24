# Changelog

All notable changes and release updates for the Arya Noble AI Chatbot System are documented in this file.

---

## [1.5.1] - 24 September 2026

### Knowledge Re-Ingestion Lifecycle, Soft-Delete Filtering & UI Error Fixes

#### 1. Summary of Changes
This update resolves lifecycle and state synchronization issues when documents that were previously ingested, approved, and deleted are re-uploaded:

1. **Clean Re-Ingestion & Soft-Delete Filtering**: Re-ingesting a previously deleted file now creates a brand new `Knowledge` record with a freshly generated UUID (`_uuid.uuid4()`), preventing the resurrection of soft-deleted records and stale metadata.
2. **Duplicate Lifecycle Active Record Verification**: Enhanced duplicate detection so matches in `data/output/` or `data/pending/` verify active database status (`deleted_at IS NULL`). Orphaned local files from soft-deleted documents are purged on the fly rather than causing false-positive `HTTP 400 (PUBLISHED)` blocks.
3. **TanStack Query Cache Eviction on Deletion**: Purged the deleted document's query cache entry (`queryClient.removeQueries`) on deletion to prevent cached 404 error states from flashing on subsequent navigations.
4. **Knowledge Detail Skeleton Priority**: Ensured the loading skeleton renders ahead of error cards during active data fetching.

---

#### 2. Detailed Component Breakdown

##### 2.1 Backend Subsystem (`backend/app/rag/router.py`)
- **Filtered Soft-Deleted Records on Ingestion**:
  - In `_process_single_upload_file`, added `Knowledge.deleted_at.is_(None)` check when querying existing database documents.
  - Ensured re-ingested files receive a clean UUID, fresh timestamps, and reset metadata.
- **Active Record Verification in `detect_duplicate_lifecycle`**:
  - Implemented `is_knowledge_record_active` helper to query PostgreSQL and check if matched files are active or deleted.
  - Automatically unlinks and removes orphaned local staging/output files belonging to soft-deleted records.

##### 2.2 Frontend Subsystem (`frontend/src/app/dashboard/knowledge/`)
- **Query Cache Eviction (`hooks/use-knowledge.ts`)**:
  - Added `queryClient.removeQueries({ queryKey: knowledgeKeys.detail(id) })` inside `useDeleteKnowledge` on successful deletion.
- **Loading vs Error Guard (`[id]/page.tsx`)**:
  - Reordered rendering logic so `KnowledgeDetailSkeleton` displays while `isLoading && !data` before evaluating `error && !data`.

---

## [1.5.0] - 24 September 2026

### Database Performance, Resource Optimization & RAG Enhancements

#### 1. Summary of Changes
This update delivers enterprise-grade performance optimizations, database connection pool protections, SQL batching, in-memory caching, composite indexing, and RAG metadata filtering enhancements:

1. **Decoupled Database Sessions during Streaming**: Chat sessions pre-fetch context upfront and release the connection before SSE streaming; a dedicated short-lived session persists final messages and token metrics upon completion, preventing database pool starvation.
2. **N+1 Query Elimination & Batch Hydration**: Implemented batch hydration routines across Users, Roles, Branches, Search, and Chat Sessions, reducing round-trip database queries from 400+ down to 2-4 per request.
3. **SQL-Level Pagination & Filter Pushdown**: Pushed search filters and `LIMIT`/`OFFSET` pagination down to PostgreSQL across Knowledge, Chat History, and User directories.
4. **RBAC In-Memory TTL Caching & Dynamic Invalidation**: Added thread-safe 5-minute TTL caching for `RequireAccess` permission evaluations, with instant cache invalidation hooks triggered on user/role mutations and deletions.
5. **Database Composite Indexes**: Added comprehensive multi-column indexes for chat messages, chat sessions, user-branch assignments, feedback issues, and timestamps.
6. **Bounded Chat Title Service History**: Limited initial message fetch to the first 4 messages for LLM conversation titling to prevent unbounded table scans.
7. **RAG Vector Search Null-Safety**: Migrated `DocumentChunk.metadata_` to PostgreSQL `JSONB` and applied `func.coalesce` to safely preserve uncategorized chunks when filtering with `excluded_categories`.

---

#### 2. Detailed Component Breakdown

##### 2.1 Database & Migrations
- **Composite Performance Indexes (`backend/alembic/versions/a9b8c7d6e5f4_add_performance_composite_indexes.py`)**:
  - `ix_chat_messages_session_created`: Composite index on `chat_messages(session_id, created_at)`.
  - `ix_chat_session_user_status`: Composite index on `chat_session(user_id, status)`.
  - `ix_chat_session_branch_id`: Index on `chat_session(branch_id)`.
  - `ix_chat_session_feedback_issue`: Composite index on `chat_session(has_data_issue, session_type)`.
  - `ix_chat_session_updated_at`: Index on `chat_session(updated_at)`.
  - `ix_user_branch_branch_status`: Composite index on `user_branch(branch_id, status)`.

##### 2.2 Main Backend Routers & API Optimization
- **Streaming Connection Management (`backend/app/api/routers/chats.py`)**:
  - Isolated database query execution from long-running SSE response generation.
  - Pushed chat search filters (`summary`, `doctor`, `branch`, `content`) directly into PostgreSQL subqueries and applied SQL `LIMIT`/`OFFSET` pagination.
- **Batch Hydration (`backend/app/api/routers/`)**:
  - `users.py`: Batch loads roles, direct accesses, doctor branch assignments, and monthly token usages in `_hydrate_users_batch`.
  - `roles.py`: Batch loads assigned accesses and user counts in `_hydrate_roles_batch`.
  - `branches.py`: Batch loads token usages, configuration overrides, and doctor assignments in `_hydrate_branches_batch`.
  - `search.py`: Batch resolves users, branches, message counts, and first messages.
  - `knowledge.py`: Pushes pagination and status filters to SQL query level.
- **RBAC Caching & Dynamic Invalidation (`backend/app/api/dependencies.py`, `backend/app/api/routers/users.py`, `backend/app/api/routers/roles.py`)**:
  - Cached permission checks for 5 minutes via `_USER_ACCESS_CACHE`.
  - Added cache eviction via `invalidate_user_access_cache` across `update_user`, `update_user_roles`, `update_user_accesses`, `delete_user`, `create_role`, `update_role`, and `delete_role`.

##### 2.3 RAG Subsystem
- **Vector Store JSONB & Coalesce Filtering (`backend/app/rag/services/vector_store.py`)**:
  - Switched `DocumentChunk.metadata_` from generic `JSON` to PostgreSQL `JSONB`.
  - Handled `excluded_categories` using `not_(func.coalesce(DocumentChunk.metadata_["categories"].astext, "").ilike(f"%{item}%"))`.
- **Medical Agent Feature Flag (`backend/app/rag/services/rag_generator.py`)**:
  - Added `settings.rag_agent_enabled` guard check before orchestrating multi-step medical tool agents.

---

## [1.4.1] - 23 September 2026

## 1. Summary of Changes

Today's update comprises 6 commits covering the following functional areas:

1. **Branch & Token Management**: Added `has_custom_limit` migration column, enforced strict 0-token quota blocking, automated global pool resets, and added a "Reset to Global Pool" action.
2. **Global Search & Filter**: Keyboard navigation (Arrow Up/Down, Enter, Esc) with auto-scroll in the search bar, and synced active category filters with URL query parameters.
3. **Knowledge Ingestion & Review**: Integrated skeleton loaders, visual processing pipeline status, responsive batch tab navigation, and preserved original uploader metadata on staging approval.
4. **WYSIWYG Markdown Editor**: Integrated the MdForge editor for manual markdown content editing across review and detail pages.
5. **Markdown Helpers & Image Sanitization**: Introduced `stripMarkdown` utility and removed broken fallback image placeholders on markdown cards.
6. **Backend Logger & Accuracy Fix**: Prevented background logger thread deadlocks and normalized `ai_confidence` percentage scales.

---

## 2. Feature & Component Details

### 2.1 Branch & Token Management

- **Database Migration**:
  - Added `has_custom_limit` (BOOLEAN, default `FALSE`) column to the `branches` table.
  - Migration file: `backend/alembic/versions/*_add_has_custom_limit_to_branches.py`.
- **Backend (`token_service.py`, `branches.py`, `config.py`)**:
  - Differentiated between branches without custom limits (`has_custom_limit=False`, following the global pool) and branches explicitly set to 0 tokens (`has_custom_limit=True` and `custom_token_limit=0`).
  - Chat requests from branches with a limit of 0 tokens are immediately rejected with an out-of-quota error.
  - Updating the global branch token rule in the Configuration page automatically resets all branch overrides (`has_custom_limit=False`, `custom_token_limit=None`) to synchronize with the new global value.
- **Frontend (`branches/`, `configuration/`, `users/`)**:
  - Added a **Reset to Global Pool** button in the branch token edit dialog.
  - Updated branch table rows and detail sheets to reflect custom override vs. global pool status.
  - Replaced text badges with status dot indicators and enabled inline editing on inactive rules in `token-limit-row.tsx`.

### 2.2 Global Search & Category Sync

- **Frontend (`global-search-bar.tsx`)**:
  - Added keyboard event handlers: Arrow Down / Arrow Up to navigate search results, Enter to select, and Escape to dismiss.
  - Implemented auto-scrolling of the active search item into view via `scrollIntoView`.
- **Frontend (`use-categories-state.ts`)**:
  - Synchronized selected category filter state with browser URL query parameters (`?category=...`), supporting bookmarking and back/forward browser navigation.

### 2.3 Knowledge Ingestion & Batch Review

- **Frontend (`knowledge/batch/[id]`, `knowledge/[id]`)**:
  - Added dedicated skeleton loading components (`BatchReviewSkeleton`, `KnowledgeDetailSkeleton`).
  - Upgraded `BatchDocumentTabs` with per-document processing status badges and seamless tab switching.
  - Added `ProcessingPipelineCard` to visualize ingestion stages (Parsing, Chunking, Embedding, Vector Storing).
- **Backend (`knowledge.py`)**:
  - Preserved original uploader metadata during staged document approval/ingestion (`created_by` / `uploader_name`) rather than overwriting with the reviewer's ID.

### 2.4 WYSIWYG Markdown Editor

- **Frontend (`components/shared/wysiwyg-editor/`)**:
  - Integrated MdForge rich-text editor (`editor-toolbar.tsx`, `wysiwyg-editor.tsx`) into batch review and knowledge detail edit forms.
  - Configured global CSS rules in `globals.css` for markdown tables, lists, and toolbar actions.

### 2.5 Markdown Rendering & Fallback Image Cleanup

- **Frontend (`components/shared/markdown/`, `lib/utils.ts`)**:
  - Created `stripMarkdown(text)` helper function to sanitize markdown strings into plain text for summaries and tooltips.
  - Removed broken placeholder fallbacks from `before-after-card.tsx`, `product-card.tsx`, and `treatment-card.tsx`.

### 2.6 Backend Logger & AI Confidence Normalization

- **Backend (`core/logger.py`)**:
  - Resolved potential thread deadlock on loguru background sinks by configuring non-blocking handlers.
- **Backend (`api/routers/knowledge.py`)**:
  - Normalized `ai_confidence` parsing to handle both decimal (0.0 - 1.0) and percentage (0 - 100) representations consistently.

---

## 3. Commit History (Git Log)

| Hash      | Author    | Timestamp (WIB)  | Commit Message                                                                           |
| --------- | --------- | ---------------- | ---------------------------------------------------------------------------------------- |
| `7af6e80` | alterashy | 23-09-2026 07:44 | feat(branches): synchronize global token distribution and support true zero overrides    |
| `3192217` | alterashy | 23-09-2026 06:46 | feat(search): add keyboard list scrolling and category query param sync                  |
| `e7bd217` | alterashy | 23-09-2026 06:44 | feat(knowledge): enhance ingestion pipeline feedback and review workflows                |
| `fa1a542` | alterashy | 23-09-2026 06:44 | refactor(markdown): clean up image error fallbacks and add stripMarkdown helper          |
| `eed9069` | alterashy | 23-09-2026 06:44 | fix(backend): prevent logger thread deadlock and normalize confidence percentage         |
| `2778896` | alterashy | 23-09-2026 04:54 | feat(knowledge): integrate wysiwyg markdown editor and preserve staged uploader metadata |

---

## 4. Modified & Added Files Summary

### Backend

| File                                                             | Status   | Description                                                      |
| ---------------------------------------------------------------- | -------- | ---------------------------------------------------------------- |
| `backend/alembic/versions/*_add_has_custom_limit_to_branches.py` | NEW      | Migration adding `has_custom_limit` to `branches` table          |
| `backend/app/models/branch.py`                                   | MODIFIED | Added `has_custom_limit` field to SQLAlchemy ORM model           |
| `backend/app/schemas/branch.py`                                  | MODIFIED | Added `has_custom_limit` to request/response schemas             |
| `backend/app/services/token_service.py`                          | MODIFIED | Quota checking logic and 0-limit blocking                        |
| `backend/app/api/routers/branches.py`                            | MODIFIED | Endpoints for updating custom limit and resetting to global pool |
| `backend/app/api/routers/config.py`                              | MODIFIED | Bulk reset of branch custom overrides upon global limit change   |
| `backend/app/api/routers/knowledge.py`                           | MODIFIED | Confidence normalization and staged uploader preservation        |
| `backend/app/core/logger.py`                                     | MODIFIED | Thread safety and non-blocking handler configuration             |

### Frontend

| File                                                                          | Status       | Description                                              |
| ----------------------------------------------------------------------------- | ------------ | -------------------------------------------------------- |
| `frontend/src/app/globals.css`                                                | MODIFIED     | Markdown styling (tables, lists) and toolbar UI rules    |
| `frontend/src/lib/utils.ts`                                                   | MODIFIED     | Added `stripMarkdown` sanitization helper                |
| `frontend/src/components/shared/wysiwyg-editor/*`                             | NEW          | WYSIWYG editor and toolbar components                    |
| `frontend/src/components/layout/global-search-bar.tsx`                        | MODIFIED     | Keyboard navigation & active item auto-scroll            |
| `frontend/src/app/dashboard/category/hooks/use-categories-state.ts`           | MODIFIED     | Category state synchronization with URL query parameters |
| `frontend/src/app/dashboard/branches/components/edit-branch-token-dialog.tsx` | MODIFIED     | Reset to Global Pool action and custom toggle support    |
| `frontend/src/app/dashboard/branches/components/branches-table-row.tsx`       | MODIFIED     | Branch token limit display updates                       |
| `frontend/src/app/dashboard/branches/components/view-branch-sheet.tsx`        | MODIFIED     | Branch token limit detail presentation                   |
| `frontend/src/app/dashboard/branches/hooks/*`                                 | MODIFIED     | Branch token mutation hooks and local state              |
| `frontend/src/app/dashboard/configuration/components/token-limit-row.tsx`     | MODIFIED     | Status dot indicator and inline edit on inactive rules   |
| `frontend/src/app/dashboard/users/components/doctor-adjust-limit-dialog.tsx`  | MODIFIED     | Alignment with new token management rules                |
| `frontend/src/app/dashboard/knowledge/[id]/*`                                 | MODIFIED/NEW | Knowledge detail skeleton and WYSIWYG editor integration |
| `frontend/src/app/dashboard/knowledge/batch/[id]/*`                           | MODIFIED/NEW | Batch review skeleton and tabs enhancement               |
| `frontend/src/app/dashboard/knowledge/components/preview/*`                   | MODIFIED     | Ingestion pipeline processing card                       |
| `frontend/src/components/shared/markdown/*`                                   | MODIFIED     | Cleaned up fallback images and element rendering         |

---

## 5. Developer Setup & Sync Instructions

After running `git pull origin dev`:

1. **Run Database Migrations**:

   ```bash
   cd backend
   alembic upgrade head
   ```

2. **Update Frontend Dependencies** (required for MdForge and markdown libraries):

   ```bash
   cd frontend
   pnpm install
   ```

3. **Verify Build & Run Servers**:

   ```bash
   # Backend
   uvicorn app.main:app --reload

   # Frontend
   pnpm build
   pnpm dev
   ```
