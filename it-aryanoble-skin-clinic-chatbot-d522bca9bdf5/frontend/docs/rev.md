# Frontend Revisions for Backend

This document tracks frontend adjustments and new features that require backend support or awareness.

## 2026-07-28 - Time Limit Per Session

- Added a new configuration component for "Time Limit Per Session" in the Dashboard Configuration page.
- **Key Used:** `TIME_LIMIT_PER_SESSION` (String representing number of minutes, e.g. "5").
- Backend should ensure this configuration key is supported and handle it appropriately in the chat session logic (ending sessions after the specified time).

## 2026-07-30 - AI Prompt File Attachments

- Added a new configuration component for "AI Prompt File Attachments" in the Dashboard Configuration page.
- **Key Used:** `AI_PROMPT_FILE_ATTACHMENTS` (String representing boolean value, "true" or "false").
- Backend should ensure this configuration key is supported and handle it appropriately when receiving chat session prompts (allowing or rejecting file uploads based on this toggle).

## 2026-07-30 - Branch Management CIS Integration

- Migrated Branch Management out of the Configuration page into its own dedicated Branch page.
- Removed branch creation and deletion capabilities from the frontend as branch data is now synced directly from the CIS.
- Removed deprecated branch fields (`address`, `latitude`, `longitude`, `image_url`) from the frontend UI and types.
- The frontend now strictly relies on viewing branch information and updating the `token_limit`.
- Backend should ensure that branch creation/deletion is handled via CIS sync, and frontend branch APIs should align with these removed fields.

## 2026-07-30 - Doctor Feedback Notifications (Staff Dashboard)

- Added a new Notifications page (`/dashboard/notifications`) to the Staff Dashboard.
- This page is intended to display feedback and reports submitted by doctors during their chat sessions.
- **Backend Action Required:** An API endpoint will be needed in the future to fetch and manage (e.g., mark as read) these doctor feedback notifications.

## 2026-07-30 - Shared SearchBar Component

- Consolidated multiple inline search inputs across the Dashboard into a single, reusable `SearchBar` component (`src/components/shared/search-bar.tsx`).

## 2026-07-31 - Doctor AI Access & CIS Sync Updates

- Removed the "AI Chatbot Access" toggle from the Doctor Details sheet.
- All doctors synced from CIS that are "Active" now automatically have AI access.
- Removed the AI access warning banner and restriction logic from the Doctor Chat Interface (`/doctor`).
- Backend `has_ai_access` column was dropped. API endpoints now allow all active doctors to use the AI chat and exclude soft-deleted (inactive) doctors.
