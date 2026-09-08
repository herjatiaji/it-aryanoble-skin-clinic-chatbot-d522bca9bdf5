import os
import re
import pickle
from typing import List, Dict, Any, Optional
from loguru import logger
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from app.rag.services.interfaces import BaseVectorStoreAdapter
from app.rag.config import settings

# --- Local BM25 Index ---
class BM25Index:
    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []       # Original chunks with text and metadata
        self.corpus: List[List[str]] = []            # Tokenized corpus for BM25
        self.bm25: Optional[BM25Okapi] = None         # rank-bm25 object

    def tokenize(self, text: str) -> List[str]:
        """Simple lowercase alphanumeric word tokenization."""
        if not text:
            return []
        return re.findall(r'\w+', text.lower())

    def add_chunks(self, new_chunks: List[Dict[str, Any]]):
        """Adds new chunks to the BM25 index, removing old chunks of the same source file first."""
        if not new_chunks:
            return

        # Try to extract the source_file name to clear older entries
        source_file = new_chunks[0].get("metadata", {}).get("source_file")
        if source_file:
            logger.debug(f"Clearing old BM25 chunks for source file: {source_file}")
            self.remove_file_chunks(source_file)

        for chunk in new_chunks:
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            self.chunks.append({
                "text": text,
                "metadata": metadata
            })
            self.corpus.append(self.tokenize(text))

        # Re-initialize the BM25 model with the updated corpus
        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus)
            logger.info(f"Re-initialized BM25 index. Total chunks in index: {len(self.chunks)}")
        else:
            self.bm25 = None

    def remove_file_chunks(self, source_file: str):
        """Removes all chunks associated with a given source file name."""
        indices_to_keep = [
            i for i, chunk in enumerate(self.chunks) 
            if chunk.get("metadata", {}).get("source_file") != source_file
        ]
        self.chunks = [self.chunks[i] for i in indices_to_keep]
        self.corpus = [self.corpus[i] for i in indices_to_keep]
        
        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus)
        else:
            self.bm25 = None

    def clear(self):
        """Clears all chunks and corpus, resetting the BM25 index state."""
        self.chunks = []
        self.corpus = []
        self.bm25 = None


    def search(self, query: str, top_k: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Searches the corpus using BM25.
        Applies metadata filtering before scoring if filter_metadata is provided.
        """
        if not self.chunks:
            return []

        # Step 1: Filter chunk candidates by metadata
        filtered_indices = []
        for idx, chunk in enumerate(self.chunks):
            match = True
            if filter_metadata:
                meta = chunk.get("metadata", {})
                for k, v in filter_metadata.items():
                    if meta.get(k) != v:
                        match = False
                        break
            if match:
                filtered_indices.append(idx)

        if not filtered_indices:
            logger.debug(f"No chunks matched metadata filter {filter_metadata} in BM25 index.")
            return []

        tokenized_query = self.tokenize(query)

        # Step 2: Calculate BM25 scores
        # If we have a filter, build a temporary BM25 okapi index of just the filtered candidates
        if filter_metadata and len(filtered_indices) < len(self.chunks):
            filtered_corpus = [self.corpus[i] for i in filtered_indices]
            temp_bm25 = BM25Okapi(filtered_corpus)
            scores = temp_bm25.get_scores(tokenized_query)
            
            top_temp_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            results = []
            for idx in top_temp_indices:
                score = scores[idx]
                if score == 0.0:  # Skip chunks with absolutely zero term matches
                    continue
                orig_idx = filtered_indices[idx]
                results.append({
                    "text": self.chunks[orig_idx]["text"],
                    "score": float(score),
                    "metadata": self.chunks[orig_idx]["metadata"]
                })
            return results
        else:
            # Score against global BM25 model
            if not self.bm25:
                return []
            scores = self.bm25.get_scores(tokenized_query)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            results = []
            for idx in top_indices:
                score = scores[idx]
                if score == 0.0:  # Skip chunks with absolutely zero term matches
                    continue
                results.append({
                    "text": self.chunks[idx]["text"],
                    "score": float(score),
                    "metadata": self.chunks[idx]["metadata"]
                })
            return results

    def save(self, file_path: str):
        """Serializes and saves the index to disk using pickle."""
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(file_path, "wb") as f:
                pickle.dump({
                    "chunks": self.chunks,
                    "corpus": self.corpus
                }, f)
            logger.info(f"Successfully saved BM25 index to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")

    def load(self, file_path: str):
        """Loads and deserializes the index from disk."""
        if not os.path.exists(file_path):
            logger.info(f"No existing BM25 index file found at {file_path}. Creating new.")
            return
            
        try:
            with open(file_path, "rb") as f:
                data = pickle.load(f)
                self.chunks = data.get("chunks", [])
                self.corpus = data.get("corpus", [])
            
            if self.corpus:
                self.bm25 = BM25Okapi(self.corpus)
                logger.info(f"Successfully loaded BM25 index from {file_path}. Loaded {len(self.chunks)} chunks.")
            else:
                self.bm25 = None
        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")


# --- Cross-Encoder Reranker ---
class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model_name = model_name
        self.model = None
        self._initialized = False

    def _ensure_loaded(self):
        if not self._initialized:
            self._initialized = True
            logger.info(f"Lazy loading Cross-Encoder Reranker model: {self.model_name}...")
            try:
                self.model = CrossEncoder(self.model_name)
                logger.info("Cross-Encoder Reranker model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load CrossEncoder model: {e}")
                self.model = None

    def rerank(self, query: str, hits: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        Reranks retrieve search candidates using the Cross-Encoder.
        """
        if not hits:
            return []
            
        self._ensure_loaded()
        if not self.model:
            logger.warning("Reranker model is not loaded. Returning original hits limited to top_n.")
            return hits[:top_n]

        try:
            pairs = []
            for hit in hits:
                meta = hit.get("metadata", {})
                product_name = meta.get("product_name")
                if not product_name:
                    source_file = meta.get("source_file", "unknown")
                    product_name = source_file
                    for ext in [".pdf", ".docx", ".txt", "_parsed.json"]:
                        product_name = product_name.replace(ext, "")
                    pn_lower = product_name.lower()
                    for prefix in ["dummy_", "dumy_", "dummy-", "dumy-", "dummy ", "dumy "]:
                        if pn_lower.startswith(prefix):
                            product_name = product_name[len(prefix):]
                            pn_lower = pn_lower[len(prefix):]
                    if pn_lower.startswith("dummy") or pn_lower.startswith("dumy"):
                        product_name = product_name[5:]
                    product_name = product_name.replace("-", " ").replace("_", " ")
                    product_name = product_name.strip()
                
                section = meta.get("section", "General")
                text = hit.get("text", "")
                
                enriched_text = f"Product: {product_name} | Section: {section} | Content: {text}"
                pairs.append([query, enriched_text])
            
            scores = self.model.predict(pairs, batch_size=32, show_progress_bar=False)
            
            reranked_hits = []
            for hit, score in zip(hits, scores):
                updated_hit = hit.copy()
                updated_hit["rerank_score"] = float(score)
                reranked_hits.append(updated_hit)
                
            sorted_hits = sorted(reranked_hits, key=lambda h: h["rerank_score"], reverse=True)
            
            logger.info(f"Successfully reranked {len(hits)} candidates. Top score: {sorted_hits[0]['rerank_score']:.4f}")
            return sorted_hits[:top_n]
        except Exception as e:
            logger.error(f"Reranking failed: {e}. Falling back to original rankings.")
            return hits[:top_n]


# --- Prompt Context Builder ---
class PromptContextBuilder:
    @staticmethod
    def build_context(hits: List[Dict[str, Any]]) -> str:
        """
        Builds a structured, numbered context string with source file, page, 
        and section headers to pass into the LLM prompt.
        """
        if not hits:
            return "No relevant context found."

        context_parts = []
        for idx, hit in enumerate(hits, start=1):
            metadata = hit.get("metadata", {})
            source_file = metadata.get("source_file", "unknown")
            product_name = metadata.get("product_name")
            if not product_name:
                product_name = source_file
                for ext in [".pdf", ".docx", ".txt", "_parsed.json"]:
                    product_name = product_name.replace(ext, "")
                pn_lower = product_name.lower()
                for prefix in ["dummy_", "dumy_", "dummy-", "dumy-", "dummy ", "dumy "]:
                    if pn_lower.startswith(prefix):
                        product_name = product_name[len(prefix):]
                        pn_lower = pn_lower[len(prefix):]
                if pn_lower.startswith("dummy") or pn_lower.startswith("dumy"):
                    product_name = product_name[5:]
                product_name = product_name.replace("-", " ").replace("_", " ")
                product_name = product_name.strip()
                
            section = metadata.get("section", "General")
            page = metadata.get("page", 1)
            text = hit.get("text", "")

            part = (
                f"[{idx}] Source: {source_file} | Product: {product_name} | Section: {section} | Page: {page}\n"
                f"Content:\n{text.strip()}"
            )
            context_parts.append(part)

        return "\n\n".join(context_parts)


# --- Helper Rank Functions ---
def get_chunk_key(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata", {})
    source_file = meta.get("source_file")
    chunk_index = meta.get("chunk_index")
    if source_file is not None and chunk_index is not None:
        return f"{source_file}_{chunk_index}"
    return str(hash(hit.get("text", "")))

def reciprocal_rank_fusion(
    dense_hits: List[Dict[str, Any]], 
    sparse_hits: List[Dict[str, Any]], 
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    rrf_scores = {}

    for rank, hit in enumerate(dense_hits, start=1):
        key = get_chunk_key(hit)
        if key not in rrf_scores:
            rrf_scores[key] = {"hit": hit, "score": 0.0}
        rrf_scores[key]["score"] += 1.0 / (rrf_k + rank)

    for rank, hit in enumerate(sparse_hits, start=1):
        key = get_chunk_key(hit)
        if key not in rrf_scores:
            rrf_scores[key] = {"hit": hit, "score": 0.0}
        rrf_scores[key]["score"] += 1.0 / (rrf_k + rank)

    sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k]["score"], reverse=True)

    fused_hits = []
    for key in sorted_keys:
        merged_hit = rrf_scores[key]["hit"].copy()
        merged_hit["rrf_score"] = rrf_scores[key]["score"]
        merged_hit["score"] = rrf_scores[key]["score"]
        fused_hits.append(merged_hit)

    return fused_hits


# --- Hybrid Retriever ---
class HybridRetriever:
    def __init__(
        self, 
        vector_store: BaseVectorStoreAdapter, 
        bm25_index: BM25Index,
        reranker: Optional[Reranker] = None
    ):
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.reranker = reranker

    def retrieve(
        self, 
        query: str, 
        top_k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        rerank_top_n: int = 3,
        confidence_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes Advanced Retrieval Pipeline:
        1. Dense Retrieval (Qdrant)
        2. Sparse Retrieval (BM25)
        3. Reciprocal Rank Fusion (RRF)
        4. Cross-Encoder Reranking (optional)
        5. Prompt Context Generation
        """
        logger.info(f"Retrieving for query: '{query}' with top_k={top_k}, metadata_filter={filter_metadata}")

        sub_queries = []
        for separator in [" dan ", " serta ", " and ", " & "]:
            if separator in query:
                parts = query.split(separator)
                parts = [p.strip() for p in parts if len(p.strip()) > 3]
                if len(parts) > 1:
                    sub_queries = parts
                    break

        candidate_k = top_k * 2
        
        if sub_queries:
            logger.info(f"Multi-intent query detected. Splitting query into sub-queries: {sub_queries}")
            sub_fused_hits = []
            
            for sq in sub_queries:
                sq_dense = self.vector_store.search(sq, top_k=candidate_k, filter_metadata=filter_metadata) if self.vector_store else []
                sq_sparse = self.bm25_index.search(sq, top_k=candidate_k, filter_metadata=filter_metadata) if self.bm25_index else []
                sq_fused = reciprocal_rank_fusion(sq_dense, sq_sparse)
                sub_fused_hits.append(sq_fused)
                
            fused_hits = []
            seen_keys = set()
            
            max_len = max(len(lst) for lst in sub_fused_hits) if sub_fused_hits else 0
            for i in range(max_len):
                for lst in sub_fused_hits:
                    if i < len(lst):
                        hit = lst[i]
                        key = get_chunk_key(hit)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            fused_hits.append(hit)
            logger.info(f"Interleaved sub-queries completed. Combined into {len(fused_hits)} candidates.")
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_dense = executor.submit(self.vector_store.search, query, candidate_k, filter_metadata) if self.vector_store else None
                future_sparse = executor.submit(self.bm25_index.search, query, candidate_k, filter_metadata) if self.bm25_index else None
                
                dense_hits = future_dense.result() if future_dense else []
                sparse_hits = future_sparse.result() if future_sparse else []

            if self.vector_store:
                logger.debug(f"Dense retrieval returned {len(dense_hits)} candidates.")
            if self.bm25_index:
                logger.debug(f"Sparse retrieval returned {len(sparse_hits)} candidates.")
            
            fused_hits = reciprocal_rank_fusion(dense_hits, sparse_hits)
            logger.info(f"RRF Fusion completed. Fused {len(fused_hits)} candidates.")

        # Deduplicate
        seen_texts = set()
        deduplicated_hits = []
        for hit in fused_hits:
            text = hit.get("text", "").strip()
            norm_text = " ".join(text.split()).lower()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                deduplicated_hits.append(hit)
        logger.info(f"Deduplicated fused hits from {len(fused_hits)} to {len(deduplicated_hits)} unique candidates.")

        final_hits = deduplicated_hits
        if rerank and self.reranker:
            all_reranked = self.reranker.rerank(query, deduplicated_hits, top_n=len(deduplicated_hits))
            
            query_lower = query.lower()
            usage_keywords = ["how to use", "directions", "cara pakai", "cara penggunaan", "aturan pakai", "dosis", "instruksi"]
            ingredients_keywords = ["kandungan", "ingredients", "bahan aktif", "komposisi", "active ingredients"]
            
            is_usage_intent = any(k in query_lower for k in usage_keywords)
            is_ingredients_intent = any(k in query_lower for k in ingredients_keywords)
            
            boosted_hits = []
            for hit in all_reranked:
                updated_hit = hit.copy()
                section_upper = updated_hit.get("metadata", {}).get("section", "").upper()
                boost = 0.0
                if is_usage_intent and any(s in section_upper for s in ["HOW TO USE", "DIRECTIONS"]):
                    boost += 0.05
                elif is_ingredients_intent and any(s in section_upper for s in ["INGREDIENT", "KANDUNGAN", "KOMPOSISI"]):
                    boost += 0.05
                
                if boost > 0:
                    updated_hit["rerank_score"] = updated_hit.get("rerank_score", 0.0) + boost
                    logger.debug(f"Applied intent boost of +{boost} to section '{section_upper}' (new score: {updated_hit['rerank_score']:.4f})")
                boosted_hits.append(updated_hit)
                
            final_hits = sorted(boosted_hits, key=lambda h: h.get("rerank_score", 0.0), reverse=True)[:rerank_top_n]
            logger.info(f"Reranking and intent boosting completed. Returned top {len(final_hits)} chunks.")
        else:
            final_hits = deduplicated_hits[:top_k]

        threshold = confidence_threshold if confidence_threshold is not None else settings.rerank_confidence_threshold
        if rerank and self.reranker and final_hits:
            max_score = final_hits[0].get("rerank_score", 0.0)
            if max_score < threshold:
                logger.warning(f"Retrieval confidence score {max_score:.4f} is below threshold {threshold:.4f}. Rejecting retrieved context.")
                return {
                    "query": query,
                    "results": [],
                    "context": "Maaf, saya tidak menemukan informasi."
                }

        context_string = PromptContextBuilder.build_context(final_hits)

        return {
            "query": query,
            "results": final_hits,
            "context": context_string
        }
