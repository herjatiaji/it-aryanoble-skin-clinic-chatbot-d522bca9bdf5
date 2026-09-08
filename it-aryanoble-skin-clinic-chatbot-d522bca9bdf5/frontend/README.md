# Arya Noble AI Chatbot - Frontend Service

Next.js 16 (App Router) user interface powering the Skin Clinic AI Chatbot system. It provides role-based portals for System Administrators, Doctors, and Functional Staff, alongside an embeddable customer chatbot widget.

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Tech Stack & Key Dependencies](#tech-stack--key-dependencies)
3. [Directory & Module Architecture](#directory--module-architecture)
4. [Role-Based Portals & Application Flow](#role-based-portals--application-flow)
5. [Environment Variables & Configuration](#environment-variables--configuration)
6. [Setup, Run & Build Commands](#setup-run--build-commands)
7. [Component Architecture & UI System](#component-architecture--ui-system)
8. [Operational Troubleshooting](#operational-troubleshooting)

---

## Overview & Architecture

The frontend is built using **Next.js (App Router)** and **React 19**, featuring a unified dashboard interface and role-scoped portal layouts (`/dashboard`, `/doctor`):

- **Role-Based Access Control (RBAC)**: Granular access control based on user roles and specific permissions, rendering navigation elements and routes dynamically within the unified `/dashboard`.
- **API Client Layer (`src/lib/axios.ts`)**: Pre-configured Axios instance using `withCredentials: true` to handle HTTP-only JWT authentication cookies issued by the FastAPI backend.
- **State Management & Data Fetching**: [TanStack Query (React Query v5)](https://tanstack.com/query/latest) for server state caching, optimistic updates, and background refetching.
- **Form Management**: [TanStack Form](https://tanstack.com/form/latest) with [Zod](https://zod.dev/) schema validation.

```
                      ┌────────────────────────┐
                      │    Next.js Client      │
                      │  (Port 3000 / React 19)│
                      └───────────┬────────────┘
                                  │
             ┌────────────────────┴────────────────────┐
             ▼                                         ▼
┌─────────────────────────┐               ┌─────────────────────────┐
│     Unified Portal      │               │      Doctor Portal      │
│      (/dashboard)       │               │        (/doctor)        │
└────────────┬────────────┘               └────────────┬────────────┘
             │                                         │
             └────────────────────┬────────────────────┘
                                  │ Axios (withCredentials: true)
                                  ▼
                      ┌────────────────────────┐
                      │   FastAPI Backend API  │
                      │  (Port 8000 / /api/*)  │
                      └────────────────────────┘
```

---

## Tech Stack & Key Dependencies

- **Framework**: [Next.js 16](https://nextjs.org/) (App Router), [React 19](https://react.dev/), TypeScript 5
- **Styling & UI**: [Tailwind CSS v4](https://tailwindcss.com/), `@base-ui/react`, `@shadcn/react`, Remixicon, Lucide icons, `next-themes` (Light/Dark mode)
- **Data Fetching & State**: [TanStack React Query v5](https://tanstack.com/query/latest), [Axios](https://axios-http.com/)
- **Forms & Validation**: TanStack Form, Zod v4
- **Data Visualization & Formatting**: Recharts, Date-fns, React Markdown (RAG answer rendering)
- **Notifications**: Sonner (Toast notifications)
- **Package Manager**: `pnpm` v11+

---

## Directory & Module Architecture

```text
frontend/
├── public/                       # Static public assets, icons, & images
├── src/
│   ├── app/                      # Next.js App Router pages & layouts
│   │   ├── dashboard/            # Unified Portal Routes (Admin & Functional)
│   │   │   ├── category/         # Treatment & product category management
│   │   │   ├── chat-history/     # Session logs & RAG chat history analytics
│   │   │   ├── configuration/    # Global AI model & provider configuration
│   │   │   ├── ingest/           # Document uploader interface
│   │   │   ├── knowledge/        # Knowledge base document review & status workflow
│   │   │   ├── users/            # User account management & RBAC role assignment
│   │   │   └── layout.tsx        # Unified dashboard shell with dynamic RBAC sidebars
│   │   ├── doctor/               # Doctor Clinical Assistant Routes
│   │   │   ├── chat/             # Doctor-facing RAG clinical assistant interface
│   │   │   ├── search/           # Hybrid vector & keyword search interface
│   │   │   └── layout.tsx        # Doctor portal navigation shell
│   │   ├── login/                # Authentication login page
│   │   ├── widget-demo/          # Embeddable AI chatbot widget preview
│   │   ├── globals.css           # Tailwind CSS directives & custom design tokens
│   │   └── layout.tsx            # Root application layout & global context providers
│   ├── components/               # UI & Shared Component Library
│   │   ├── layout/               # Header, Sidebar, and App Shell layout components
│   │   ├── providers/            # React Query & Theme Provider wrappers
│   │   ├── shared/               # Reusable business components (DataTable, Modals, Uploaders)
│   │   └── ui/                   # Base Radix/Shadcn primitives (Buttons, Inputs, Dialogs, Cards)
│   ├── hooks/                    # Custom React Hooks
│   │   ├── use-current-user.ts   # Active user profile query hook
│   │   ├── use-mobile.ts         # Responsive viewport detection hook
│   │   └── use-session.tsx       # Auth session lifecycle hook
│   └── lib/                      # Utilities & API Configuration
│       ├── axios.ts              # Pre-configured Axios client (NEXT_PUBLIC_API_URL + credentials)
│       ├── types.ts              # TypeScript DTO interfaces & enum types
│       └── utils.ts              # Tailwind merge & utility helper functions
├── .env                          # Local environment variables (git-ignored)
├── .env.example                  # Environment configuration template
├── components.json               # Shadcn UI configuration manifest
├── next.config.ts                # Next.js build & runtime configuration
├── package.json                  # Dependencies & script definitions
├── pnpm-lock.yaml                # Lockfile for reproducible builds
└── tsconfig.json                 # TypeScript compiler configuration
```

---

## Role-Based Portals & Application Flow

| Portal / Route | Accessible Roles | Key Capabilities & Features |
| :--- | :--- | :--- |
| **`/login`** | Public | User authentication endpoint issuing HTTP-only JWT cookies. |
| **`/dashboard`** | Admin / Staff | Unified dashboard landing page based on RBAC. |
| **`/dashboard/configuration`** | Admin | Dynamic AI model selector and API key manager. |
| **`/dashboard/knowledge`** | Admin / Staff | Admin review queue and status view for uploaded knowledge docs. |
| **`/dashboard/users`** | Admin | Create, edit, and assign roles to system users. |
| **`/dashboard/ingest`** | Admin / Staff | Upload clinic documents for RAG ingestion. |
| **`/doctor/chat`** | Doctor | Clinical AI assistant interface for medical knowledge & treatment guidelines. |
| **`/doctor/search`** | Doctor | Direct hybrid vector & keyword search engine across clinic knowledge base. |
| **`/widget-demo`** | Public / Demo | Preview of the embeddable customer-facing chat widget. |

---

## Environment Variables & Configuration

Create a `.env` file in the `frontend/` directory by copying `.env.example`:

```bash
cp .env.example .env
```

```env
# --- FastAPI Backend Base URL ---
# URL of the FastAPI backend API endpoint
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

---

## Setup, Run & Build Commands

### 1. Install Dependencies
```bash
# Install packages using pnpm
pnpm install
```

### 2. Launch Development Server
```bash
# Starts Next.js dev server on http://localhost:3000
pnpm dev
```

### 3. Production Build & Execution
```bash
# Build optimized production bundle
pnpm build

# Start production server
pnpm start
```

### 4. Running via Root Docker Compose
```bash
# From project root directory:
# Launch frontend container in development mode
docker compose up --build frontend

# Or run all project services in production mode
docker compose -f docker-compose.prod.yaml up --build frontend
```

### 5. Code Quality & Linting
```bash
# Run ESLint checks across the codebase
pnpm lint
```

---

## Component Architecture & UI System

- **Shadcn / Base UI Primitives**: Located in `src/components/ui/`, styled with Tailwind CSS utility classes and `clsx` / `tailwind-merge`.
- **API Interceptor & Credentials**: [`src/lib/axios.ts`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/frontend/src/lib/axios.ts) automatically attaches `withCredentials: true` so all requests seamlessly pass HTTP-only authentication cookies.
- **RAG Answer Formatting**: Chat messages render rich markdown including code blocks and bullet points using `react-markdown`.

---

## Operational Troubleshooting

### 1. CORS or 401 Unauthorized Errors
- **Symptom**: API requests fail with CORS origin error or instant 401 redirect.
- **Resolution**:
  - Ensure `NEXT_PUBLIC_API_URL` in `frontend/.env` points to the correct backend URL (e.g. `http://localhost:8000/api`).
  - Verify `allow_origins` in backend [`app/main.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/main.py) includes `http://localhost:3000`.

### 2. Stale React Query Cache
- **Symptom**: Updated user or document status does not reflect immediately on the screen.
- **Resolution**: TanStack Query automatically invalidates query keys on mutations. If needed, refresh the page or clear browser local cache.
