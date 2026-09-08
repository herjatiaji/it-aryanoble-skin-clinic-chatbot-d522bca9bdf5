# Arya Noble AI Chatbot - Backend Service

FastAPI Modular Monolith backend powering the Skin Clinic AI Chatbot system. It handles user authentication, clinic branch administration, daily CIS attendance synchronization, knowledge base management, and a dynamic Retrieval-Augmented Generation (RAG) conversational engine.

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Tech Stack & Key Dependencies](#tech-stack--key-dependencies)
3. [Directory & Module Architecture](#directory--module-architecture)
4. [RAG Subsystem (`app/rag`) Detailed Breakdown](#rag-subsystem-apprag-detailed-breakdown)
5. [Environment Variables & Configuration](#environment-variables--configuration)
6. [Database Migrations & Seeding](#database-migrations--seeding)
7. [Document Ingestion & RAG Verification Workflow](#document-ingestion--rag-verification-workflow)
8. [Setup, Run & Test Commands](#setup-run--test-commands)
9. [API Documentation & Endpoint Summary](#api-documentation--endpoint-summary)
10. [Operational Troubleshooting](#operational-troubleshooting)

---

## Overview & Architecture

The backend is structured as a **FastAPI Modular Monolith** designed for scalability, clean domain separation, and dynamic feature loading:

- **Core Module**: Provides core REST API services including user management, JWT authentication, clinic branch administration, category management, and event-driven CIS data synchronization via RSA-signed webhooks (`POST /api/webhooks/cis`).
- **AI/RAG Module (`app/rag`)**: Implements an enterprise RAG pipeline. It handles document parsing (via `Docling`), text chunking, dynamic embedding generation, hybrid vector similarity search (`pgvector`), reranking, and contextual LLM answer generation.
- **Dual-Mode Startup**: If RAG-specific dependencies in `requirements.txt` are absent, `app/main.py` gracefully boots in **Core-Only** mode without breaking core API services.

```
       ┌────────────────┐
       │ Next.js Client │
       └───────┬────────┘
               │ HTTP / REST
               ▼
┌───────────────────────────────┐                  ┌─────────────────┐
│     FastAPI Backend Core      │ <── Webhooks ─── │    Mock CIS     │
│  ┌──────────┬──────────────┐  │  RSA Signed      │ (Automated Sync)│
│  │   Auth   │  Branch/User │  │ (X-Signature)    └─────────────────┘
│  ├──────────┴──────────────┤  │
│  │  RAG Engine (app/rag)   │  │
│  └──────────┬──────────────┘  │
└─────────────┼─────────────────┘
              │ Async ORM (SQLAlchemy)
              ▼
  ┌──────────────────────────┐
  │      PostgreSQL DB       │
  │  (Relational + pgvector) │
  └──────────────────────────┘
```

---

## Tech Stack & Key Dependencies

- **Web Framework**: Python 3.11+, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), Pydantic v2
- **Database & ORM**: PostgreSQL 15+ with [`pgvector`](https://github.com/pgvector/pgvector), [SQLAlchemy 2.0 (AsyncIO)](https://docs.sqlalchemy.org/), [Alembic](https://alembic.sqlalchemy.org/)
- **RAG & AI Framework**: [LangChain](https://www.langchain.com/), HuggingFace Transformers (`BAAI/bge-m3`), OpenAI API, Google Gemini AI, [Docling](https://github.com/DS4SD/docling)
- **Task Scheduler**: [APScheduler](https://apscheduler.readthedocs.io/) (for daily CIS attendance sync)
- **Authentication**: OAuth2 Password Flow, JWT tokens (via `PyJWT`/`python-jose`), Passlib (`bcrypt`)

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
│   │   └── routers/              # Feature domain routers
│   │       ├── auth.py           # Login, JWT token generation & user profile
│   │       ├── branches.py       # Clinic location & branch management
│   │       ├── categories.py     # Product & treatment category management
│   │       ├── chats.py          # Chat session history & user message persistence
│   │       ├── config.py         # Dynamic AppConfig (active LLM keys, embedding models)
│   │       ├── knowledge.py      # Knowledge base admin review & CRUD
│   │       ├── users.py          # User management & granular RBAC access administration
│   │       └── webhooks.py       # External service webhooks & RSA-signed CIS triggers
│   ├── core/                     # Core application infrastructure
│   │   ├── config.py             # Base Pydantic settings & environment validation
│   │   ├── database.py           # Async SQLAlchemy engine & AsyncSessionLocal factory
│   │   └── security.py           # JWT encoding/decoding & bcrypt password hashing
│   ├── models/                   # SQLAlchemy DB ORM Entity Models
│   │   ├── attendance.py         # Daily attendance records
│   │   ├── branch.py             # Clinic branch entities
│   │   ├── chat.py               # Chat session & message history records
│   │   ├── config.py             # AppConfig key-value persistence store
│   │   ├── knowledge.py          # Knowledge document & KnowledgeChunk (pgvector)
│   │   └── user.py               # User accounts & role models
│   ├── schemas/                  # Pydantic DTOs for request/response validation
│   ├── services/                 # Core domain business logic
│   │   └── cis_sync.py           # RSA-signed CIS webhook event processors & key loader
│   │
│   ├── rag/                      # RAG Engine Subsystem
│   │   ├── config.py             # Isolated RAG configuration settings
│   │   ├── deps.py               # FastAPI dependency injection for RAG singletons
│   │   ├── router.py             # RAG Endpoints (/api/ai/* - ingest, chat, search, pending, refine, evaluate)
│   │   ├── schemas.py            # Pydantic schemas for RAG API payloads
│   │   ├── services/             # Core AI Pipeline Services (AI Team Workspace)
│   │   │   ├── evaluation.py     # Retrieval & search quality evaluator (Hit Rate, MRR)
│   │   │   ├── factory.py        # LLM & Vector Store adapter factories (OpenAI primary)
│   │   │   ├── interfaces.py     # BaseVectorStoreAdapter & BaseLLMAdapter base classes
│   │   │   ├── rag_generator.py  # GenerationPipeline & OpenAIAdapter/GeminiAdapter
│   │   │   ├── rag_pipeline.py   # IngestionPipeline (Docling -> CustomChunker -> Vector DB)
│   │   │   ├── rag_retriever.py  # HybridRetriever (BM25 + PGVector + Reranker + Intent Boosting)
│   │   │   └── vector_store.py   # PGVectorAdapter (executes vector similarity search via pgvector)
│   │   └── utils/                # RAG Utilities (AI Team Workspace)
│   │       ├── chunker.py        # Heading-based & Semantic CustomChunker strategies
│   │       ├── logger.py         # Structured logging helpers
│   │       ├── metadata.py       # Document metadata extraction & language detection
│   │       └── parser.py         # Docling document text & table extraction engine
│   └── main.py                   # FastAPI app factory, lifespan events & router mounts
├── .env                          # Local environment variables (git-ignored)
├── .env.example                  # Environment configuration template
├── seed.py                       # DB Seeder (Default admin accounts, branch data, sample configs)
├── start.sh                      # Shell execution script for Docker containers
├── Dockerfile                    # Backend container build specification
└── requirements.txt              # Unified Python dependencies (Core + RAG)
```

---

## RAG Subsystem (`app/rag`) Detailed Breakdown

| Component / File       | File Path                                                                                                                                         | Detailed Description & Implementation                                                                                                                                                                                                                                                                                                                                |
| :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Interfaces**         | [`app/rag/core/interfaces.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/core/interfaces.py)             | Defines abstract blueprints `BaseVectorStoreAdapter` and `BaseLLMAdapter`. Standardizes operations across vector stores and LLM providers.                                                                                                                                                                                                                           |
| **PgVector Adapter**   | [`app/rag/core/vector.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/core/vector.py)                     | Concrete `PgVectorAdapter` implementation. Translates vector insertions and similarity queries directly into PostgreSQL `knowledge_chunk` table operations using `KnowledgeChunk.embedding.cosine_distance()`. Replaces standalone vector DBs (e.g. Chroma/Qdrant).                                                                                                  |
| **Embedding Manager**  | [`app/rag/embeddings/embedder.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/embeddings/embedder.py)     | Manages embedding model loading (`HuggingFace`, `OpenAI`, `Google Gemini`). Contains `ensure_embedding_dimension_synced()`, which automatically checks DB column vector dimensions on startup. If the embedding model changes, it updates the DB schema (`vector(N)`), rebuilds the HNSW index, and kicks off background chunk re-indexing (`reindex_all_chunks()`). |
| **Document Parser**    | [`app/rag/ingestion/parser.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/ingestion/parser.py)           | Extracts text, tables, and section structures from PDF, TXT, and Markdown files using Docling.                                                                                                                                                                                                                                                                       |
| **Chunking Engine**    | [`app/rag/ingestion/chunker.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/ingestion/chunker.py)         | Splits parsed documents into structured chunks with chunk index and character offset tracking.                                                                                                                                                                                                                                                                       |
| **Ingestion Pipeline** | [`app/rag/ingestion/pipeline.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/ingestion/pipeline.py)       | Connects parser, chunker, metadata extractor, and `PgVectorAdapter` into an automated pipeline.                                                                                                                                                                                                                                                                      |
| **Hybrid Retriever**   | [`app/rag/retrieval/retriever.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/retrieval/retriever.py)     | Combines `pgvector` similarity search with metadata filtering (`document_type`, `knowledge_id`) and SQL keyword matching.                                                                                                                                                                                                                                            |
| **Reranker**           | [`app/rag/retrieval/reranker.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/retrieval/reranker.py)       | Re-evaluates top-k vector candidates using Cross-Encoders or LLM scoring to optimize context relevance.                                                                                                                                                                                                                                                              |
| **Generation Engine**  | [`app/rag/generation/generator.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/generation/generator.py)   | Orchestrates `HybridRetriever`, `ExternalReranker`, system prompts ([`builder.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/generation/builder.py)), conversation history, and LLM inference.                                                                                                                              |
| **AI Summarizer**      | [`app/rag/generation/summarizer.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/generation/summarizer.py) | Generates executive summaries for newly uploaded knowledge documents upon ingestion.                                                                                                                                                                                                                                                                                 |
| **Evaluation**         | [`app/rag/evaluation/evaluator.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/evaluation/evaluator.py)   | Evaluates RAG answer quality against Faithfulness and Context Relevance metrics.                                                                                                                                                                                                                                                                                     |
| **RAG Router**         | [`app/rag/router.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/app/rag/router.py)                               | Exposes RAG REST endpoints (`/api/ai/ingest`, `/api/ai/chat`, `/api/ai/search`). Orchestrates background document ingestion tasks and status transitions (`KnowledgeStatus.PENDING`).                                                                                                                                                                                |

---

## Environment Variables & Configuration

Create a `.env` file in the `backend/` root directory by copying `.env.example`:

```bash
cp .env.example .env
```

```env
# --- Core Application Settings ---
PROJECT_NAME="Arya Noble Chatbot API"

# --- Database & PgVector Connection ---
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/arya_noble

# --- Security & JWT Authentication ---
SECRET_KEY=supersecretkey_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# --- File Storage ---
UPLOAD_DIR=data/uploads

# --- External CIS Integration ---
CIS_RSA_PUBLIC_KEY_PATH=keys/cis_public_key.pem
# CIS_RSA_PUBLIC_KEY="-----BEGIN RSA PUBLIC KEY-----\n...\n-----END RSA PUBLIC KEY-----"

# --- RAG & Embedding Model Settings ---
# EMBEDDING_PROVIDER options: huggingface | openai | google
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

Whenever database models in `app/models/` are modified, run Alembic migration commands:

```bash
# Generate a new migration revision based on model changes
alembic revision --autogenerate -m "add_new_feature_column"

# Apply all pending migrations to the database
alembic upgrade head

# Rollback the last migration revision (if needed)
alembic downgrade -1
```

### 2. Database Seeder Script

The [`seed.py`](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/seed.py) script populates initial data into PostgreSQL (admin accounts, default clinic branches, category items, and dynamic AppConfig key-values):

```bash
python seed.py
```

---

## Document Ingestion & RAG Verification Workflow

```
[ Upload PDF ] ──► [ POST /api/ai/ingest ] ──► [ Status: PROCESSING ]
                                                       │
                                                       ▼
[ Status: PENDING ] ◄── [ AI Executive Summary ] ◄── [ Parse & Vectorize ]
        │
        ▼
[ Admin Review ] ──► [ Approve via /api/knowledge ] ──► [ Status: APPROVED ]
                                                               │
                                                               ▼
                                                  [ Available in Chat Queries ]
```

1. **Upload Document**: User or Admin posts document to `POST /api/ai/ingest` or via the Knowledge Admin UI (`/api/knowledge`).
2. **Background Ingestion**: File is saved in `data/` directory. Background task parses contents using Docling, splits text into chunks, generates vector embeddings, and stores chunks in the `knowledge_chunk` table.
3. **AI Summarization**: `generate_document_summary()` generates an executive summary and sets the document status to `KnowledgeStatus.PENDING`.
4. **Admin Approval**: An admin reviews the document summary and approves it via `PATCH /api/knowledge/{id}`. Once set to `APPROVED`, the document chunks participate in vector search for user queries.

---

## Setup, Run & Test Commands

### Option A: Standalone Development Run

1. **Navigate to the backend directory**:

   ```bash
   cd backend
   ```

2. **Set up Virtual Environment**:

   ```bash
   # Create virtual environment
   python -m venv venv

   # Activate on Windows (PowerShell / CMD):
   venv\Scripts\activate

   # Activate on Linux / macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**:

   ```bash
   # Install all backend dependencies
   pip install -r requirements.txt
   ```

4. **Initialize Database & Seed Data**:

   ```bash
   # Execute database migrations
   alembic upgrade head

   # Seed default admin user & initial data
   python seed.py
   ```

5. **Start FastAPI Development Server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   _Server will run at `http://localhost:8000`._

---

### Option B: Running via Root Docker Compose

From the project root workspace directory:

```bash
# Build and run backend container alongside PostgreSQL and Mock CIS
docker compose up --build backend

# Or launch all services using the production compose file
docker compose -f docker-compose.prod.yaml up --build backend
```

---

## API Documentation & Endpoint Summary

- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check Endpoint**: `http://localhost:8000/health`

### Key Endpoint Groups

| Domain                  | Route Prefix      | Key Functionality                                                                                 |
| :---------------------- | :---------------- | :------------------------------------------------------------------------------------------------ |
| **Authentication**      | `/api/auth`       | `/login` (JWT token issue), `/me` (Current user profile).                                         |
| **User Administration** | `/api/users`      | User CRUD operations, RBAC role assignment.                                                       |
| **Knowledge Base**      | `/api/knowledge`  | Knowledge document list, approval workflow (`PENDING` -> `APPROVED`), delete documents.           |
| **RAG AI Engine**       | `/api/ai`         | `/ingest` (Upload document), `/chat` (RAG chat completion), `/search` (Hybrid similarity search). |
| **Clinic Branches**     | `/api/branches`   | Clinic location list, operating hours, branch configuration.                                      |
| **Categories**          | `/api/categories` | Product & service categories catalog.                                                             |
| **Chat Sessions**       | `/api/chats`      | Chat session creation, user message history persistence.                                          |
| **Webhooks**            | `/api/webhooks`   | `/cis` (Receive RSA-signed data pushes from CIS).                                                 |

---

## Operational Troubleshooting

### 1. Vector Embedding Dimension Mismatch

- **Symptom**: Error stating vector dimension mismatch (e.g. `expected 768 dimensions, got 1024`).
- **Resolution**:
  - The backend automatically resolves dimension mismatches on startup via `ensure_embedding_dimension_synced()`.
  - If a manual schema reset is required, run the following SQL statements in PostgreSQL:
    ```sql
    DROP INDEX IF EXISTS ix_knowledge_chunk_embedding;
    ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(1024); -- Set target dim
    CREATE INDEX ix_knowledge_chunk_embedding ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
    ```

### 2. Database Migration Sync Issues

- **Symptom**: `alembic.util.exc.CommandError: Target database is not up to date.`
- **Resolution**:
  ```bash
  alembic upgrade head
  ```
  If the database schema already matches the models manually:
  ```bash
  alembic stamp head
  ```

### 3. Core-Only Mode Log Message

- **Symptom**: Startup log states `Running in Core-Only mode. AI module skipped...`.
- **Resolution**: Ensure all packages from `requirements.txt` are installed in your Python environment.
