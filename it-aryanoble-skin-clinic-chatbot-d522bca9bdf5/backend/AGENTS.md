# AGENTS.md — Arya Noble Backend Agent Configuration

> **Core Directive:** This file serves as the source of truth for the FastAPI backend architecture, tech stack, conventions, and AI team collaboration workflow. Always refer back to this document when generating new APIs, models, or RAG pipeline features.

## Project Context

We are building the backend for the **Arya Noble AI Chatbot (Clinic Information System)**.

- **Goal**: Serve as a robust standard API for user authentication, CRUD operations, syncing data from the CIS, and driving an enterprise-grade Retrieval-Augmented Generation (RAG) engine.
- **Unified Team Workspace**: Both Backend Engineers and AI Engineers work directly in this repository (`backend/`). The AI subsystem lives entirely inside `backend/app/rag/`.

## Technology Stack

| Layer            | Technology                                                                                                                              |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Framework        | FastAPI (Python 3.11+)                                                                                                                  |
| Database         | PostgreSQL 15+ with `pgvector` extension                                                                                                |
| ORM & Driver     | SQLAlchemy 2.0 (AsyncIO) + `asyncpg` (Core DB), `psycopg[binary]` (PGVectorAdapter)                                                     |
| Auth             | JWT stored in `HttpOnly` cookies                                                                                                        |
| RAG Engine       | LangChain, HuggingFace (`BAAI/bge-m3`), OpenAI (`gpt-4o-mini`), Docling, `rank-bm25`, Cross-Encoder Reranker (`BAAI/bge-reranker-base`) |
| Background Tasks | FastAPI `BackgroundTasks`, `APScheduler` (for CIS syncing)                                                                              |

## Project Structure & AI Subsystem

```text
backend/
├── alembic/                  # Database migration scripts
├── app/
│   ├── api/                  # REST Controllers & middleware guards
│   │   ├── dependencies.py   # Auth guards, DB session injection, RequireAccess granular RBAC permissions
│   │   └── routers/          # Feature domain routers (auth, branches, chats, knowledge, etc.)
│   ├── core/                 # Core infrastructure (config, database, security)
│   ├── models/               # SQLAlchemy ORM models (User, ChatSession, Knowledge, etc.)
│   ├── schemas/              # Core Pydantic request/response DTOs
│   ├── services/             # Business logic (auth_service, cis_sync)
│   │
│   ├── rag/                  # 🤖 UNIFIED AI & RAG SUBSYSTEM (AI Team Workspace)
│   │   ├── config.py         # Isolated RAG configuration settings (settings.py)
│   │   ├── deps.py           # FastAPI dependency injection for RAG singletons
│   │   ├── router.py         # RAG endpoints (/api/ai/* - ingest, chat, search, pending, refine, evaluate)
│   │   ├── schemas.py        # Pydantic schemas for RAG API payloads
│   │   ├── services/         # Core AI Pipeline Services
│   │   │   ├── evaluation.py     # Search quality evaluator (Hit Rate, MRR)
│   │   │   ├── factory.py        # AdapterFactory (OpenAI / Gemini / PGVector adapters)
│   │   │   ├── interfaces.py     # BaseVectorStoreAdapter & BaseLLMAdapter base classes
│   │   │   ├── rag_generator.py  # GenerationPipeline & OpenAIAdapter
│   │   │   ├── rag_pipeline.py   # IngestionPipeline (Docling -> CustomChunker -> Vector DB)
│   │   │   ├── rag_retriever.py  # HybridRetriever (BM25 + PGVector + Reranker + Intent Boosting)
│   │   │   └── vector_store.py   # PGVectorAdapter (vector similarity search via pgvector)
│   │   └── utils/            # RAG Utilities
│   │       ├── chunker.py        # Heading-based & Semantic CustomChunker strategies
│   │       ├── logger.py         # Structured logging helpers
│   │       ├── metadata.py       # Document metadata extraction & language detection
│   │       └── parser.py         # Docling document text & table extraction engine
│   └── main.py               # FastAPI app factory, lifespan singletons & router mounts
```

## Commands

| Action            | Command (from `backend/` directory)          |
| ----------------- | -------------------------------------------- |
| Install Deps      | `pip install -r requirements.txt`            |
| Run Server        | `uvicorn app.main:app --reload`              |
| Run Migrations    | `alembic upgrade head`                       |
| Test Swagger Docs | Open `http://localhost:8000/docs` in browser |
