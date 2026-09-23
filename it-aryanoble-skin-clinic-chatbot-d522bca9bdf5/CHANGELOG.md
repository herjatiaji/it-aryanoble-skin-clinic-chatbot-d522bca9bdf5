# Changelog - 23 September 2026

System updates and bug fixes (Backend, Database, and Frontend).

---

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
