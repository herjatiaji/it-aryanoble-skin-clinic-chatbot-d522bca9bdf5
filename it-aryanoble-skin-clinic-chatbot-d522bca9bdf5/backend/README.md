# Arya Noble AI Chatbot - Backend Service

FastAPI Modular Monolith backend powering the Skin Clinic AI Chatbot system. It handles user authentication, clinic branch administration, token quota allocation, MinIO object storage, daily CIS attendance synchronization, multi-stage knowledge base management, and a dynamic Retrieval-Augmented Generation (RAG) conversational engine.

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Tech Stack & Key Dependencies](#tech-stack--key-dependencies)
3. [Directory & Module Architecture](#directory--module-architecture)
4. [RAG Subsystem (`app/rag`) Detailed Breakdown](#rag-subsystem-apprag-detailed-breakdown)
5. [Storage Architecture (MinIO & Local Fallback)](#storage-architecture-minio--local-fallback)
6. [Environment Variables & Configuration](#environment-variables--configuration)
7. [Database Migrations & Seeding](#database-migrations--seeding)
8. [Document Ingestion & RAG Verification Workflow](#document-ingestion--rag-verification-workflow)
9. [Setup, Run & Test Commands](#setup-run--test-commands)
10. [API Documentation & Endpoint Summary](#api-documentation--endpoint-summary)
11. [Operational Troubleshooting](#operational-troubleshooting)

---

## Overview & Architecture

The backend is structured as a **FastAPI Modular Monolith** designed for scalability, clean domain separation, high observability, and dynamic feature loading:

- **Core Module**: Provides REST API services including user management, granular Role-Based Access Control (RBAC), JWT authentication (HttpOnly cookies), clinic branch quota administration, product/treatment categories, and event-driven CIS data synchronization via RSA-signed webhooks (`POST /api/webhooks/cis`).
- **Storage Module (`app/services/storage.py`)**: S3-compatible MinIO object storage management with dual-bucket partitioning (`images` for assets & `knowledge-documents` for parsed files), accompanied by an automated background sync worker that flushes local fallback uploads.
- **AI/RAG Module (`app/rag`)**: Implements an enterprise RAG pipeline. It handles document parsing (via `Docling`), text chunking, dynamic embedding generation (`BAAI/bge-m3`), hybrid vector similarity search (`pgvector` cosine similarity + `rank-bm25`), Cross-Encoder reranking (`BAAI/bge-reranker-base`), and contextual LLM answer generation (OpenAI / Google Gemini).
- **Dual-Mode Startup**: If RAG-specific dependencies in `requirements.txt` are absent, `app/main.py` gracefully boots in **Core-Only** mode without breaking core API services.

```mermaid
graph TD
    subgraph ClientLayer["Frontend Client (Next.js 16)"]
        WebClient["App Router Client<br/>(Dashboard & Doctor Portal)"]
    end

    subgraph CISLayer["External Integration"]
        MockCIS["Mock CIS Service<br/>(RSA-Signed Webhooks)"]
    end

    subgraph BackendApp["FastAPI Backend Core (Port 8000)"]
        AuthService["Auth & RBAC Guards<br/>(HttpOnly JWT)"]
        StorageService["MinIO Storage Service<br/>(Dual-Bucket + Local Sync)"]
        DomainRouters["Domain Routers<br/>(Branches, Users, Quotas, Chats)"]
        
        subgraph RAGSubsystem["RAG Subsystem (app/rag)"]
            DoclingEngine["Docling Parser & Semantic Chunker"]
            HybridRetriever["Hybrid Retriever<br/>(pgvector + BM25)"]
            Reranker["Cross-Encoder Reranker"]
            LLMGenerator["LLM Generation Pipeline<br/>(OpenAI / Gemini)"]
        end
    end

    subgraph Persistence["Storage & Database Layer"]
        PostgresDB[("PostgreSQL 16 + pgvector<br/>Port 50010 : 5432")]
        MinIOBucket[("MinIO Object Storage<br/>API 9000 | Console 9001")]
    end

    WebClient -->|"HTTP / REST / SSE Stream"| BackendApp
    MockCIS -->|"POST /api/webhooks/cis (X-Signature)"| BackendApp
    BackendApp -->|"SQLAlchemy 2.0 AsyncIO"| PostgresDB
    BackendApp -->|"boto3 S3 API"| MinIOBucket
    DoclingEngine --> HybridRetriever
    HybridRetriever --> Reranker
    Reranker --> LLMGenerator
```

---

## Tech Stack & Key Dependencies

- **Web Framework**: Python 3.11+, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), Pydantic v2, Pydantic-Settings
- **Database & ORM**: PostgreSQL 16 with [`pgvector`](https://github.com/pgvector/pgvector), [SQLAlchemy 2.0 (AsyncIO)](https://docs.sqlalchemy.org/), [Alembic](https://alembic.sqlalchemy.org/), `asyncpg`, `psycopg[binary]`
- **Object Storage**: [MinIO](https://min.io/) (S3-compatible dual-bucket), AWS SDK (`boto3` / `aioboto3`)
- **RAG & AI Framework**: [LangChain](https://www.langchain.com/), HuggingFace Transformers (`BAAI/bge-m3`), OpenAI API (`gpt-4o-mini`), Google Gemini AI, [Docling](https://github.com/DS4SD/docling), PyMuPDF, `rank-bm25`, Cross-Encoder Reranker (`BAAI/bge-reranker-base`)
- **Task Scheduler**: [APScheduler](https://apscheduler.readthedocs.io/) (for CIS sync & periodic tasks)
- **Authentication & Security**: OAuth2 Password Flow, JWT tokens (via `PyJWT`/`python-jose`), Passlib (`bcrypt`), RSA-SHA256 signature verification
- **Observability**: [Loguru](https://github.com/Delgan/loguru) (non-blocking thread-safe logging), `speedtest-cli` (bandwidth telemetry)

---

## Directory & Module Architecture

```text
backend/
├── alembic/                      # Database migration scripts & environment
│   ├── env.py                    # Migration script configuration
│   └── versions/                 # Revision scripts tracking schema changes
├── app/
│   ├── api/                      # REST Controllers & middleware guards
│   │   ├── dependencies.py       # Auth guards, DB session injection, RequireAccess RBAC permissions
│   │   └── routers/              # 16 Feature domain routers
│   │       ├── auth.py           # Login, JWT cookies, profile & password management
│   │       ├── bandwidth.py      # Server network bandwidth speed testing
│   │       ├── branches.py       # Clinic locations, custom token limits, & global resets
│   │       ├── categories.py     # Product & treatment category taxonomy
│   │       ├── chats.py          # Chat sessions, SSE stream (/stream), citations, attachments
│   │       ├── config.py         # Dynamic AppConfig (LLM keys, embedding models, token quotas)
│   │       ├── events.py         # Server-Sent Events (SSE) notification stream
│   │       ├── knowledge.py      # Multi-stage document ingestion, MdForge edit, & approvals
│   │       ├── projects.py       # Knowledge batch/project collections
│   │       ├── roles.py          # Granular RBAC role definition & permission assignment
│   │       ├── search.py         # Hybrid search across clinic treatments and products
│   │       ├── storage.py        # MinIO asset upload, presigned URLs, & image streaming
│   │       ├── system.py         # System telemetry, disk, memory, & health metrics
│   │       ├── users.py          # User management & doctor token quota adjustments
│   │       └── webhooks.py       # RSA-signed CIS webhook receiver (POST /api/webhooks/cis)
│   ├── core/                     # Core application infrastructure
│   │   ├── config.py             # Pydantic BaseSettings & environment validation
│   │   ├── database.py           # Async SQLAlchemy engine & AsyncSessionLocal factory
│   │   ├── logger.py             # Thread-safe Loguru logging configuration
│   │   └── security.py           # JWT encoding/decoding & bcrypt password hashing
│   ├── models/                   # SQLAlchemy DB ORM Entity Models
│   │   ├── attendance.py         # Daily attendance records
│   │   ├── branch.py             # Clinic branches (has_custom_limit, token quotas)
│   │   ├── category.py           # Category taxonomy entities
│   │   ├── chat.py               # Chat session & message history records
│   │   ├── config.py             # AppConfig key-value persistence store
│   │   ├── ingestion_usage.py    # Document token & ingestion usage metrics
│   │   ├── knowledge.py          # Knowledge document & KnowledgeChunk (pgvector)
│   │   ├── pending_operation.py  # Pending batch operations & staging state
│   │   ├── project.py            # Knowledge project collections
│   │   └── user.py               # User accounts, doctor metadata, & role models
│   ├── schemas/                  # Pydantic DTOs for request/response validation
│   ├── services/                 # Core domain business logic
│   │   ├── auth_service.py       # Authentication helper utilities
│   │   ├── chat_title_service.py # Dynamic AI chat conversation title generator
│   │   ├── cis_sync.py           # RSA-signed CIS webhook event processors & key loader
│   │   ├── db_seeder.py          # Database seeding logic
│   │   ├── rag_service.py        # Bridge service between core routers and RAG pipeline
│   │   ├── storage.py            # MinIO dual-bucket storage engine & local fallback sync
│   │   └── token_service.py      # Quota calculation, 0-limit blocking, & global pool sync
│   │
│   ├── rag/                      # RAG Engine Subsystem (AI Team Workspace)
│   │   ├── config.py             # Isolated RAG configuration settings
│   │   ├── deps.py               # FastAPI dependency injection for RAG singletons
│   │   ├── router.py             # RAG Endpoints (/api/ai/* - ingest, chat, search, refine, evaluate)
│   │   ├── schemas.py            # Pydantic schemas for RAG API payloads
│   │   ├── services/             # Core AI Pipeline Services
│   │   │   ├── evaluation.py     # Retrieval & search quality evaluator (Hit Rate, MRR)
│   │   │   ├── factory.py        # LLM & Vector Store adapter factories (OpenAI / Gemini)
│   │   │   ├── interfaces.py     # BaseVectorStoreAdapter & BaseLLMAdapter base classes
│   │   │   ├── rag_generator.py  # GenerationPipeline & OpenAIAdapter/GeminiAdapter
│   │   │   ├── rag_pipeline.py   # IngestionPipeline (Docling -> CustomChunker -> Vector DB)
│   │   │   ├── rag_retriever.py  # HybridRetriever (BM25 + PGVector + Reranker + Intent Boosting)
│   │   │   └── vector_store.py   # PGVectorAdapter (executes vector similarity search via pgvector)
│   │   └── utils/                # RAG Utilities
│   │       ├── chunker.py        # Heading-based & Semantic CustomChunker strategies
│   │       ├── logger.py         # Structured logging helpers
│   │       ├── metadata.py       # Document metadata extraction & language detection
│   │       └── parser.py         # Docling document text & table extraction engine
│   └── main.py                   # FastAPI app factory, lifespan singletons & router mounts
├── data/                         # Local storage workspace and upload fallback
├── .env                          # Local environment variables (git-ignored)
├── .env.example                  # Environment configuration template
├── seed.py                       # DB Seeder (Default admin accounts, branch data, sample configs)
├── start.sh                      # Shell execution script for Docker containers
├── Dockerfile                    # Backend container build specification
└── requirements.txt              # Unified Python dependencies (Core + RAG)
```

---

## RAG Subsystem (`app/rag`) Detailed Breakdown

| Component / File | File Path | Detailed Description & Implementation |
| :--- | :--- | :--- |
| **Interfaces** | [`app/rag/services/interfaces.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/interfaces.py) | Defines abstract blueprints `BaseVectorStoreAdapter` and `BaseLLMAdapter`. Standardizes operations across vector stores and LLM providers. |
| **PgVector Adapter** | [`app/rag/services/vector_store.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/vector_store.py) | Translates vector insertions and similarity queries directly into PostgreSQL `knowledge_chunk` table operations using `KnowledgeChunk.embedding.cosine_distance()`. |
| **Adapter Factory** | [`app/rag/services/factory.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/factory.py) | Dynamically instantiates the active LLM (OpenAI / Gemini) and Vector Store from database `AppConfig` runtime settings. |
| **Document Parser** | [`app/rag/utils/parser.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/utils/parser.py) | Extracts structured text, tables, and section structures from PDF, TXT, and Markdown files using Docling. |
| **Chunking Engine** | [`app/rag/utils/chunker.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/utils/chunker.py) | Splits parsed documents into semantic chunks with heading context, chunk index, and character offset tracking. |
| **Ingestion Pipeline** | [`app/rag/services/rag_pipeline.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/rag_pipeline.py) | Connects Docling parser, semantic chunker, metadata extractor, and `PGVectorAdapter` into an automated staged pipeline. |
| **Hybrid Retriever** | [`app/rag/services/rag_retriever.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/rag_retriever.py) | Reciprocal Rank Fusion (RRF) combining `pgvector` cosine similarity search with in-memory `BM25Index` and Cross-Encoder reranking (`BAAI/bge-reranker-base`). |
| **Generation Engine** | [`app/rag/services/rag_generator.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/rag_generator.py) | Orchestrates `HybridRetriever`, system prompts, conversation history, medical source citations, and LLM inference streaming. |
| **Evaluation** | [`app/rag/services/evaluation.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/services/evaluation.py) | Evaluates search and answer quality (Hit Rate, Mean Reciprocal Rank MRR). |
| **RAG Router** | [`app/rag/router.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/router.py) | Exposes internal RAG REST endpoints (`/api/ai/ingest`, `/api/ai/chat`, `/api/ai/search`, `/api/ai/refine`, `/api/ai/evaluate`). |

---

## Storage Architecture (MinIO & Local Fallback)

The backend implements a **Dual-Bucket S3 Object Storage Architecture** via [`app/services/storage.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/services/storage.py):

1. **Dual Buckets**:
   - `images`: Stores clinic product images, before-after photos, and user-uploaded chat attachments.
   - `knowledge-documents`: Stores original raw PDFs, TXT, and Markdown knowledge base files.
2. **Local Fallback**: If MinIO is temporarily unreachable during startup, uploads are saved locally in `data/storage/`.
3. **Background Auto-Sync Worker**: An asynchronous background worker periodically verifies MinIO connectivity and flushes any pending local fallback files to MinIO without data loss.

---

## Environment Variables & Configuration

Create a `.env` file in the `backend/` root directory by copying `.env.example`:

```bash
cp .env.example .env
```

```env
# --- Core Application Settings ---
PROJECT_NAME="Arya Noble Chatbot API"
CORS_ORIGINS=["http://localhost:3000","http://localhost:8001"]

# --- Database & PgVector Connection ---
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:50010/arya_noble

# --- Security & JWT Authentication ---
SECRET_KEY=supersecretkey_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# --- MinIO Object Storage Settings ---
MINIO_ENDPOINT=localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_USE_SSL=false
MINIO_IMAGE_BUCKET=images
MINIO_DOC_BUCKET=knowledge-documents

# --- External CIS Integration ---
CIS_RSA_PUBLIC_KEY_PATH=keys/cis_public_key.pem

# --- RAG & Embedding Model Settings ---
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL_NAME=BAAI/bge-m3

# --- LLM Provider Settings & Credentials ---
LLM_MODEL_NAME=gpt-4o-mini
# OPENAI_API_KEY=sk-proj-...
# GEMINI_API_KEY=AIzaSy...
```

---

## Database Migrations & Seeding

### 1. Alembic Migrations

```bash
# Generate a new migration revision based on model changes
alembic revision --autogenerate -m "add_has_custom_limit_to_branches"

# Apply all pending migrations to the database
alembic upgrade head

# Rollback the last migration revision (if needed)
alembic downgrade -1
```

### 2. Database Seeder Script

The [`seed.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/seed.py) script populates initial data into PostgreSQL (superadmin accounts, default clinic branches, category taxonomies, and dynamic AppConfig values):

```bash
python seed.py
```

---

## Document Ingestion & RAG Verification Workflow

```mermaid
flowchart LR
    UploadDoc["Upload PDF / MD<br/><code>POST /api/knowledge/upload</code>"] --> Processing["Status: PROCESSING<br/>Docling Parser"]
    Processing --> AISummary["Generate AI Summary & Chunks"]
    AISummary --> Staging["Status: PENDING<br/>Staged Admin Review Queue"]
    Staging --> EditWYSIWYG["MdForge Markdown Editor<br/>Category & Metadata Validation"]
    EditWYSIWYG --> Approval["POST /api/knowledge/{id}/approve"]
    Approval --> Active["Status: APPROVED<br/>pgvector HNSW Vector Search"]
```

1. **Upload Document**: User or Admin posts documents to `POST /api/knowledge/upload`. Raw files are persisted in MinIO (`knowledge-documents`).
2. **Background Ingestion**: Docling extracts text, tables, and images. The Custom Chunker creates semantic chunks with character offsets.
3. **AI Summarization**: Generates an executive summary and marks status as `KnowledgeStatus.PENDING`.
4. **Staged Review with MdForge**: Admins review chunk text and edit content directly via the MdForge WYSIWYG editor.
5. **Admin Approval**: Document is approved via `POST /api/knowledge/{id}/approve`. Status transitions to `APPROVED` and chunks are indexed in `pgvector` for live RAG query retrieval.

---

## Setup, Run & Test Commands

### Option A: Standalone Development Run

```bash
cd backend

# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # (Windows: venv\Scripts\activate)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Execute database migrations and seed data
alembic upgrade head
python seed.py

# 4. Start FastAPI server
uvicorn app.main:app --reload --port 8000
```
_Server will run at `http://localhost:8000`._

---

### Option B: Running via Root Docker Compose

From the project root directory:

```bash
# Launch backend alongside PostgreSQL, MinIO, and Mock CIS in development mode
docker compose up --build backend

# Or launch all services in production mode
docker compose -f docker-compose.prod.yaml up --build backend
```

---

## API Documentation & Endpoint Summary

- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check Endpoint**: `http://localhost:8000/health`

### Key Endpoint Groups

| Domain | Route Prefix | Key Functionality |
| :--- | :--- | :--- |
| **Authentication** | `/api` | `/login` (Issue HttpOnly JWT), `/me` (Profile), `/logout`, `/change-password` |
| **User Administration** | `/api/users` | User CRUD, doctor token limit adjustments, role assignments |
| **Roles & Permissions** | `/api/roles` | RBAC role definitions and granular permission matrices |
| **Clinic Branches** | `/api/branches` | Branch locations, custom token overrides, reset to global pool |
| **Categories** | `/api/categories` | Product & treatment category taxonomy |
| **Knowledge Projects** | `/api/projects` | Grouped knowledge document batches and collections |
| **Knowledge Base** | `/api/knowledge` | Multi-stage upload, staged review, MdForge chunk editing, approval, rejection, batch operations |
| **Chat Sessions** | `/api/chats` | Session creation, SSE token streaming (`/stream`), message history, source citations |
| **Hybrid Search** | `/api/search` | Fast hybrid search (pgvector + BM25 + Reranker) for treatments & products |
| **Storage & Assets** | `/api/storage` | MinIO presigned upload URLs, direct uploads, asset streaming |
| **Webhooks** | `/api/webhooks` | `/cis` (Receive RSA-signed data pushes from CIS) |
| **App Configuration** | `/api/config` | Live LLM model toggle, API keys, embedding providers, token rules |
| **Event Stream** | `/api/events` | Server-Sent Events (SSE) notification stream |
| **Bandwidth** | `/api/bandwidth` | Server network bandwidth testing and latency tracking |
| **System Telemetry** | `/api/system` | Server health metrics, CPU, memory, and disk usage |
| **RAG AI Subsystem** | `/api/ai` | Direct AI endpoints (`/chat`, `/search`, `/refine`, `/evaluate`) |

---

## Operational Troubleshooting

### 1. Vector Embedding Dimension Mismatch
- **Symptom**: Error stating vector dimension mismatch (e.g. `expected 768 dimensions, got 1024`).
- **Resolution**: The backend automatically syncs dimensions on startup. To manually reindex:
  ```sql
  DROP INDEX IF EXISTS ix_knowledge_chunk_embedding;
  ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(1024);
  CREATE INDEX ix_knowledge_chunk_embedding ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
  ```

### 2. MinIO Object Storage Connection
- **Symptom**: Warnings stating MinIO client unreachable on startup.
- **Resolution**: Check that the MinIO container is healthy on port `9000`. The backend uses an automatic local fallback in `data/storage/` and will flush pending files once MinIO reconnects.

### 3. Database Migration Sync
- **Symptom**: `alembic.util.exc.CommandError: Target database is not up to date.`
- **Resolution**:
  ```bash
  alembic upgrade head
  ```
