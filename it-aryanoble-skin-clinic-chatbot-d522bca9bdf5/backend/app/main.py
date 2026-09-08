from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger
from app.core.config import settings
from app.api.routers import auth, users, branches, categories, knowledge, chats, webhooks, config

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

        logger.info("RAG components initialized successfully!")
    except Exception as e:
        logger.error(f"Failed to initialize RAG lifespan: {e}")

    yield

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Arya Noble AI Chatbot",
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(branches.router, prefix="/api/branches")
app.include_router(categories.router, prefix="/api/categories")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(chats.router, prefix="/api/chats")
app.include_router(webhooks.router, prefix="/api")
app.include_router(config.router, prefix="/api")

# --- RAG Integration Router ---
try:
    from app.rag.router import router as rag_router
    app.include_router(rag_router, prefix="/api/ai")
    print("AI Module loaded successfully!")
except Exception as e:
    print(f"AI module skipped due to error: {e}")

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}
