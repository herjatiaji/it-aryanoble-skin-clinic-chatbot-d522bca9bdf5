import os
import json
from loguru import logger
from typing import Optional

from app.rag.services.interfaces import BaseVectorStoreAdapter
from app.rag.utils.parser import DocumentParser
from app.rag.utils.chunker import CustomChunker
from app.rag.utils.metadata import MetadataEnricher
from app.rag.config import settings

class IngestionPipeline:
    def __init__(self, vector_store: Optional[BaseVectorStoreAdapter] = None):
        logger.info("Initializing Ingestion Pipeline...")
        self.parser = DocumentParser()
        self.chunker = CustomChunker(embedding_model_name=settings.embedding_model_name)
        self.metadata_enricher = MetadataEnricher()
        self.vector_store = vector_store
        
        # Directory for JSON output
        self.output_dir = "data/output"
        os.makedirs(self.output_dir, exist_ok=True)

    def ingest_file(self, file_path: str) -> str:
        """
        Processes a single file: parse → chunk → enrich metadata → save JSON.
        Uses smart parser with fast extraction for digital docs and Docling OCR fallback for scanned docs.
        """
        logger.info(f"Starting ingestion for {file_path}")
        
        # 1. Smart Parse (Fast or Docling OCR)
        parse_result = self.parser.parse_file(file_path)
        if not parse_result:
            logger.error("Parsing failed. Aborting ingestion for this file.")
            return ""
            
        # 2. Custom Chunking (Section-Aware + Semantic)
        chunks = self.chunker.chunk_document(parse_result)
        if not chunks:
            logger.error("Chunking failed or produced no chunks.")
            return ""
            
        # 3. Metadata Extraction & Formatting
        language = self.metadata_enricher.detect_document_language(parse_result)
        logger.info(f"Detected document language: {language}")
        enriched_data = self.metadata_enricher.enrich_chunks(chunks, file_path, language=language)
        
        # 4. JSON Output
        filename = os.path.basename(file_path)
        output_file = os.path.join(self.output_dir, f"{filename}_parsed.json")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(enriched_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Successfully saved parsed data to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save JSON output: {e}")
            return ""

        # 5. Vector DB Indexing (Optional)
        if self.vector_store:
            logger.info(f"Indexing chunks from {filename} into vector store...")
            try:
                self.vector_store.insert_chunks(enriched_data)
                logger.info(f"Successfully indexed chunks from {filename} into vector store.")
            except Exception as e:
                logger.error(f"Failed to index chunks into vector store: {e}")

        return output_file

    def ingest_directory(self, directory_path: str):
        """Processes a directory and ingests all files."""
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                self.ingest_file(file_path)
