import os
import json
from typing import List, Dict, Any
from functools import lru_cache
from loguru import logger

from sqlalchemy import create_engine, Column, String, Text, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
# pyrefly: ignore [missing-import]
from pgvector.sqlalchemy import Vector

from app.rag.services.interfaces import BaseVectorStoreAdapter
from app.rag.services.embeddings import EmbeddingFactory
from app.rag.config import settings

Base = declarative_base()

class DocumentChunk(Base):
    __tablename__ = settings.pg_collection_name
    
    id = Column(String, primary_key=True)
    text = Column(Text, nullable=False)
    source_file = Column(String, nullable=False, index=True)
    metadata_ = Column("metadata", JSONB, nullable=False)
    embedding = Column(Vector(768), nullable=False)



class PGVectorAdapter(BaseVectorStoreAdapter):
    def __init__(self):
        conn_str = settings.pg_conn_str
        try:
            import psycopg
        except ImportError:
            conn_str = conn_str.replace("postgresql+psycopg://", "postgresql+psycopg2://")
        self.conn_str = conn_str
        self.collection_name = settings.pg_collection_name
        
        # Instantiate embedding adapter first to get dimension
        self.embeddings = EmbeddingFactory.get_embeddings_adapter()
        dim = self.embeddings.dimension
        
        logger.info(f"Initializing PGVector client (Dimension: {dim})...")
        try:
            self.engine = create_engine(self.conn_str, pool_pre_ping=True, pool_recycle=300)
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()

                # Check if table exists and if vector dimension matches
                check_table_sql = text("""
                    SELECT atttypmod 
                    FROM pg_attribute 
                    WHERE attrelid = to_regclass(:tablename) AND attname = 'embedding';
                """)
                try:
                    result = conn.execute(check_table_sql, {"tablename": self.collection_name}).fetchone()
                    if result and result[0] != dim:
                        logger.warning(f"Vector dimension mismatch (DB: {result[0]}, Model: {dim}). Recreating table...")
                        conn.execute(text(f"DROP TABLE IF EXISTS {self.collection_name} CASCADE;"))
                        conn.commit()
                except Exception:
                    conn.rollback()

                # Create table if not exists with correct dimension
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {self.collection_name} (
                    id VARCHAR PRIMARY KEY,
                    text TEXT NOT NULL,
                    source_file VARCHAR NOT NULL,
                    metadata JSONB NOT NULL,
                    embedding vector({dim}) NOT NULL
                );
                """
                conn.execute(text(create_table_sql))
                conn.commit()
                
                # Create HNSW index if not exists
                index_name = f"idx_{self.collection_name}_embedding_hnsw"
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON {self.collection_name} USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 100);
                """))

                # Create GIN index on metadata JSONB if not exists
                gin_index_name = f"idx_{self.collection_name}_metadata_gin"
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {gin_index_name} 
                    ON {self.collection_name} USING gin (metadata);
                """))

                # Create B-Tree index on source_file if not exists
                source_index_name = f"idx_{self.collection_name}_source_file"
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {source_index_name} 
                    ON {self.collection_name} (source_file);
                """))
                conn.commit()
                
            self.Session = sessionmaker(bind=self.engine)
            logger.info(f"Connected to PostgreSQL. Table '{self.collection_name}' ready with {dim}D vectors.")
        except Exception as e:
            logger.error(f"Failed to initialize PGVector: {e}")
            raise

        logger.info("PGVectorAdapter initialized successfully.")

    def insert_chunks(self, chunks: List[Dict]):
        if not chunks:
            logger.warning("No chunks provided to insert.")
            return

        logger.info(f"Embedding {len(chunks)} chunks with active embedding model...")
        
        texts_to_embed = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            retrieval_text = metadata.get("retrieval_text")
            if not retrieval_text:
                source_file = metadata.get("source_file", "unknown")
                product_name = metadata.get("product_name")
                treatment_name = metadata.get("treatment_name")
                form_factor = metadata.get("form_factor")
                section = metadata.get("section", "General")
                sku = metadata.get("sku") or metadata.get("product_id") or metadata.get("item_code")
                if not sku and isinstance(metadata.get("extracted_information"), dict):
                    ext_info = metadata["extracted_information"]
                    sku = ext_info.get("sku") or ext_info.get("product_id") or ext_info.get("item_code")

                parts = []
                if treatment_name:
                    parts.append(f"Treatment: {treatment_name}")
                if product_name:
                    parts.append(f"Product: {product_name}")
                if form_factor:
                    parts.append(f"Form Factor: {form_factor}")
                if sku:
                    parts.append(f"SKU: {sku}")
                if section and section.lower() not in ("general", "root"):
                    parts.append(f"Section: {section}")
                parts.append(f"Content: {chunk.get('text', '')}")
                retrieval_text = " | ".join(parts)
            texts_to_embed.append(retrieval_text)
            
        embeddings = self.embeddings.embed_documents(texts_to_embed)
        
        logger.info(f"Inserting points to PGVector table: {self.collection_name}")
        with self.Session() as session:
            for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                metadata = chunk.get("metadata", {})
                source_file = metadata.get("source_file", "unknown")
                chunk_id = metadata.get("chunk_id")
                if chunk_id:
                    unique_id = str(chunk_id)
                else:
                    chunk_index = metadata.get("chunk_index", i)
                    unique_id = f"{source_file}_{chunk_index}_{i}"
                
                existing = session.query(DocumentChunk).filter_by(id=unique_id).first()
                if existing:
                    session.delete(existing)
                    
                doc = DocumentChunk(
                    id=unique_id,
                    text=chunk["text"],
                    source_file=source_file,
                    metadata_=metadata,
                    embedding=vector
                )
                session.add(doc)
            
            session.commit()
            logger.info(f"Successfully inserted {len(chunks)} chunks into PGVector.")

    @lru_cache(maxsize=2048)
    def _get_cached_embedding(self, query: str) -> List[float]:
        return self.embeddings.embed_query(query)

    def search(self, query: str, top_k: int = 5, filter_metadata: Any = None) -> List[Dict]:
        try:
            query_vector = self._get_cached_embedding(query)
            
            with self.Session() as session:
                dist_col = DocumentChunk.embedding.cosine_distance(query_vector).label("dist")
                q = session.query(DocumentChunk, dist_col)
                
                if filter_metadata:
                    from sqlalchemy import not_, or_, func
                    for k, v in filter_metadata.items():
                        if k in ("clinic_id", "user_clinic_id") and v:
                            user_clinic = str(v).strip()
                            scope_clause = or_(
                                DocumentChunk.metadata_["knowledge_scope"].astext.ilike("GLOBAL"),
                                DocumentChunk.metadata_["knowledge_scope"].astext.ilike("TENANT"),
                                DocumentChunk.metadata_["clinic_id"].astext.ilike(f"%{user_clinic}%"),
                                DocumentChunk.metadata_["clinics"].astext.ilike(f"%{user_clinic}%"),
                                DocumentChunk.metadata_["clinics"].astext.ilike("%all%"),
                                DocumentChunk.metadata_["clinic_id"].is_(None)
                            )
                            q = q.filter(scope_clause)
                        elif k == "excluded_categories" and isinstance(v, list):
                            for item in v:
                                if item:
                                    # Native JSONB array containment exclusion (coalesce handles missing/null categories key safely)
                                    q = q.filter(not_(func.coalesce(DocumentChunk.metadata_["categories"].astext, "").ilike(f"%{item}%")))
                        elif isinstance(v, list):
                            or_clauses = []
                            for item in v:
                                if item:
                                    or_clauses.append(DocumentChunk.metadata_[k].astext.ilike(f"%{item}%"))
                            if any(str(x).lower() == "all" for x in v):
                                or_clauses.append(DocumentChunk.metadata_[k].astext.ilike("%all%"))
                                or_clauses.append(DocumentChunk.metadata_[k].is_(None))
                            if or_clauses:
                                q = q.filter(or_(*or_clauses))
                        elif v:
                            q = q.filter(DocumentChunk.metadata_[k].astext.ilike(f"%{v}%"))
                        
                results = q.order_by(dist_col).limit(top_k).all()
                
                hits = []
                for hit_chunk, dist in results:
                    dist_val = float(dist) if dist is not None else 1.0
                    similarity = float(max(0.0, 1.0 - dist_val))
                    hits.append({
                        "text": hit_chunk.text,
                        "score": similarity,
                        "metadata": hit_chunk.metadata_
                    })
                return hits
        except Exception as e:
            logger.error(f"Search failed in PGVector store: {e}")
            return []

    def delete_document(self, identifier: str):
        try:
            logger.info(f"Deleting chunks for identifier: {identifier}")
            from sqlalchemy import text
            src_str = str(identifier).strip()
            clean_id = src_str.replace("_parsed.json", "").replace(".json", "").replace(".pdf", "").strip()
            
            with self.Session() as session:
                result = session.execute(text(f"""
                    DELETE FROM {self.collection_name}
                    WHERE source_file = :src
                       OR source_file ILIKE :src_like
                       OR source_file ILIKE :clean_like
                       OR metadata ->> 'knowledge_id' = :src
                       OR metadata ->> 'knowledge_id' = :clean_id
                       OR metadata ->> 'file_name' = :src
                       OR metadata ->> 'file_name' ILIKE :clean_like
                       OR metadata ->> 'title' = :src
                       OR metadata ->> 'title' ILIKE :clean_like
                """), {
                    "src": src_str,
                    "src_like": f"%{src_str}%",
                    "clean_id": clean_id,
                    "clean_like": f"%{clean_id}%"
                })
                session.commit()
                deleted_rows = result.rowcount
            logger.info(f"Successfully deleted {deleted_rows} chunks for '{identifier}' from PGVector.")
        except Exception as e:
            logger.error(f"Failed to delete chunks for {identifier}: {e}")
            raise

    def clear_all(self):
        try:
            logger.info(f"Clearing all data from {self.collection_name}...")
            with self.Session() as session:
                session.query(DocumentChunk).delete()
                session.commit()
            logger.info("Vector store successfully cleared.")
        except Exception as e:
            logger.error(f"Failed to clear vector store: {e}")
            raise
