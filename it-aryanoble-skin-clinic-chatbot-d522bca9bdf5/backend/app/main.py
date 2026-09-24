import os
import asyncio
from fastapi import FastAPI, Request, HTTPException, status
from contextlib import asynccontextmanager
from loguru import logger
from app.core.config import settings
from app.core.logger import setup_logging
from app.api.routers import auth, users, branches, categories, projects, knowledge, chats, webhooks, config, events, roles, bandwidth, search, system, storage

# Initialize centralized logging and interceptors immediately
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize RAG Pipeline components safely
    try:
        from app.rag.services.factory import AdapterFactory
        from app.rag.services.rag_pipeline import IngestionPipeline
        from app.rag.services.rag_retriever import HybridRetriever, BM25Index, Reranker
        from app.rag.services.rag_generator import GenerationPipeline
        from app.rag.config import settings as rag_settings

        logger.info("Initializing RAG pipeline components...")

        try:
            vector_store = AdapterFactory.get_vector_store()
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            vector_store = None

        ingestion_pipeline = IngestionPipeline(vector_store=vector_store)

        bm25_index = BM25Index()
        try:
            bm25_index.load(rag_settings.bm25_index_path)
        except Exception as e:
            logger.warning(f"BM25 index load failed: {e}")

        # Pure RRF Hybrid Search Architecture (PGVector + BM25) for production
        reranker = None

        try:
            hybrid_retriever = HybridRetriever(
                vector_store=vector_store,
                bm25_index=bm25_index,
                reranker=reranker
            )
        except Exception as e:
            logger.error(f"Failed to initialize hybrid retriever: {e}")
            hybrid_retriever = None

        try:
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                llm_adapter = await AdapterFactory.get_dynamic_llm(session)
        except Exception as e:
            logger.warning(f"LLM adapter unavailable: {e}")
            llm_adapter = None

        generation_pipeline = None
        if hybrid_retriever and llm_adapter:
            try:
                generation_pipeline = GenerationPipeline(
                    retriever=hybrid_retriever, llm_adapter=llm_adapter
                )
            except Exception as e:
                logger.error(f"Failed to initialize generation pipeline: {e}")

        app.state.vector_store = vector_store
        app.state.ingestion_pipeline = ingestion_pipeline
        app.state.bm25_index = bm25_index
        app.state.reranker = reranker
        app.state.hybrid_retriever = hybrid_retriever
        app.state.llm_adapter = llm_adapter
        app.state.generation_pipeline = generation_pipeline

        if reranker:
            try:
                reranker._ensure_loaded()
                logger.info("⚡ Cross-Encoder Reranker model pre-warmed successfully.")
            except Exception as rw_e:
                logger.warning(f"Reranker pre-warm note: {rw_e}")

        logger.info("RAG components initialized successfully!")
    except Exception as e:
        logger.error(f"Failed to initialize RAG lifespan: {e}")

    # Initialize MinIO dual-bucket storage (images + knowledge-documents)
    try:
        from app.services.storage import ensure_all_buckets
        ensure_all_buckets()
    except Exception as e:
        logger.warning(f"MinIO bucket initialization failed (non-fatal): {e}")

    # Start periodic MinIO auto-sync worker to flush any local fallback files once MinIO is online
    async def _minio_background_sync_worker():
        while True:
            try:
                await asyncio.sleep(20)
                if os.path.exists("data/storage") and os.listdir("data/storage"):
                    from app.services.storage import _get_client, sync_existing_local_to_minio
                    client = _get_client()
                    if client:
                        await asyncio.to_thread(sync_existing_local_to_minio, client)
            except asyncio.CancelledError:
                break
            except Exception as w_err:
                logger.debug(f"MinIO background sync worker note: {w_err}")

    sync_worker_task = asyncio.create_task(_minio_background_sync_worker())

    yield

    sync_worker_task.cancel()
    try:
        await sync_worker_task
    except asyncio.CancelledError:
        pass

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Arya Noble AI Chatbot",
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True}
)

# Pure ASGI Middleware to buffer and replay raw request body when X-Signature is present.
# This prevents Starlette's MultipartParser from starving signature verification dependencies.
@app.middleware("http")
async def cache_raw_body_for_signature(request: Request, call_next):
    if request.headers.get("X-Signature") or request.headers.get("x-signature"):
        body_bytes = await request.body()
        request.scope["_raw_body"] = body_bytes
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate Limiting & Observability Middleware ---
import time
import uuid
from collections import defaultdict
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

RATE_LIMIT_STORE = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

@app.middleware("http")
async def observability_and_rate_limit_middleware(request: Request, call_next):
    """
    1. Generates/preserves X-Request-ID for full end-to-end request traceability.
    2. Measures total server execution latency.
    3. Protects AI & Chat endpoints against spam/DDoS via IP rate limiting.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start_time = time.time()

    path = request.url.path
    if path.startswith("/api/chats") or path.startswith("/api/ai"):
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        
        # Keep timestamps within the last 60 seconds
        timestamps = [t for t in RATE_LIMIT_STORE[client_ip] if now - t < 60]
        RATE_LIMIT_STORE[client_ip] = timestamps
        
        if len(timestamps) >= MAX_REQUESTS_PER_MINUTE:
            logger.warning(f"[{request_id}] Rate limit exceeded for IP {client_ip} on path {path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Maximum 30 requests per minute allowed."},
                headers={"X-Request-ID": request_id}
            )
        
        RATE_LIMIT_STORE[client_ip].append(now)

    response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000.0
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{latency_ms:.1f}ms"

    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex[:12]
    logger.error(f"[{request_id}] Unhandled server exception on {request.url.path}: {exc}\n{traceback.format_exc()}")
    
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and (origin in settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS) else (settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "*")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc), "request_id": request_id},
        headers={
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Request-ID": request_id
        }
    )


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(roles.router, prefix="/api/roles")
app.include_router(branches.router, prefix="/api/branches")
app.include_router(categories.router, prefix="/api/categories")
app.include_router(projects.router, prefix="/api/projects")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(chats.router, prefix="/api/chats")
app.include_router(webhooks.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(events.router, prefix="/api/events")
app.include_router(bandwidth.router, prefix="/api")
app.include_router(search.router, prefix="/api/search")
app.include_router(system.router, prefix="/api")
app.include_router(storage.router, prefix="/api")

# --- RAG Integration Router ---
try:
    from app.rag.router import router as rag_router
    app.include_router(rag_router, prefix="/api/ai")
    print("AI Module loaded successfully!")
except Exception as e:
    print(f"AI module skipped due to error: {e}")

@app.on_event("startup")
async def startup_preload_models():
    """Preloads Cross-Encoder Reranker and BM25 index in background on server startup to eliminate first-request latency."""
    import asyncio
    def _preload():
        try:
            from app.rag.services.factory import AdapterFactory
            enable_reranker = os.getenv("ENABLE_RERANKER", "false").lower() in ("true", "1", "yes")
            if enable_reranker:
                reranker = AdapterFactory.get_reranker()
                reranker._ensure_loaded()
                logger.info("Cross-Encoder Reranker model pre-warmed successfully on server startup.")
            AdapterFactory.get_bm25_index()
            logger.info("AI RAG BM25 index pre-warmed successfully on server startup.")
        except Exception as e:
            logger.warning(f"Background model preloading skipped: {e}")

    asyncio.get_event_loop().run_in_executor(None, _preload)

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}

