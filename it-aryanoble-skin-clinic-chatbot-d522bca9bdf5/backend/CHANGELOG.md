# Backend Changelog

All notable changes to the Arya Noble AI Chatbot Backend are documented in this file.

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
