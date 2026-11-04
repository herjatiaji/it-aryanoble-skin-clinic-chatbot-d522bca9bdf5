from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=10,
    max_overflow=20,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """FastAPI dependency to get database session"""
    async with AsyncSessionLocal() as session:
        yield session


_SYNC_ENGINE = None

def get_sync_engine():
    """Singleton synchronous SQLAlchemy engine for RAG ingestion/hydration to prevent connection pool leaks."""
    global _SYNC_ENGINE
    if _SYNC_ENGINE is None:
        from sqlalchemy import create_engine
        from app.rag.config import settings as rag_settings
        conn_str = rag_settings.pg_conn_str
        try:
            import psycopg
        except ImportError:
            try:
                import psycopg2
                conn_str = conn_str.replace("+psycopg", "+psycopg2")
            except ImportError:
                conn_str = conn_str.replace("+psycopg", "")
        _SYNC_ENGINE = create_engine(
            conn_str,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5
        )
    return _SYNC_ENGINE

