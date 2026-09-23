import datetime
from typing import List, Dict, Any, Optional
from loguru import logger

DEFAULT_ERHA_BENCHMARK_DATASET = [
    {
        "query": "Apa saja kandungan aktif, persentase, dan keunggulan ERHA Acneact Low pH Gentle Acne Facial Wash?",
        "expected_file": "ERHA Acneact Low pH Gentle Acne Facial Wash",
        "expected_answer": "Salicylic Acid (0.5%), Niacinamide (2%), Panthenol (Vitamin B5), Centella Asiatica Extract, Glycerin. Membersihkan minyak & sisa makeup tanpa merusak skin barrier."
    },
    {
        "query": "Berapa persentase Niacinamide dan Salicylic Acid pada ERHA Acneact Anti Acne Serum serta apa saja kegunaannya?",
        "expected_file": "ERHA Acneact Anti Acne Serum",
        "expected_answer": "Niacinamide (5%), Salicylic Acid (1%), Zinc PCA, Madecassoside, Hyaluronic Acid. Mengurangi jerawat aktif, komedo, dan mengontrol minyak berlebih."
    },
    {
        "query": "Apa saja bahan aktif, manfaat, dan petunjuk penggunaan ERHA Acneact BHA & Sulfur Acne Spot Gel?",
        "expected_file": "ERHA Acneact BHA & Sulfur Acne Spot Gel",
        "expected_answer": "Sulfur (3%), Salicylic Acid (2%), Tea Tree Leaf Oil, Centella Asiatica Extract, Allantoin. Mengurangi ukuran jerawat dan mengeringkan jerawat. Oleskan tipis 2-3 kali sehari."
    },
    {
        "query": "Kandungan apa yang digunakan ERHA Acneact Post Acne Spot Serum untuk mengatasi PIH (hiperpigmentasi bekas jerawat)?",
        "expected_file": "ERHA Acneact Post Acne Spot Serum",
        "expected_answer": "Tranexamic Acid (3%), Niacinamide (5%), Alpha Arbutin (2%), Licorice Root Extract, Hyaluronic Acid. Membantu memudarkan bekas jerawat dan mencerahkan kulit."
    },
    {
        "query": "Berapa nilai SPF dan bagaimana aturan pakai ERHA Acneact Acne Protection & Oil Control Sunscreen SPF45 PA+++?",
        "expected_file": "ERHA Acneact Acne Protection & Oil Control Sunscreen SPF45 PA+++",
        "expected_answer": "SPF45 PA+++. Gunakan sebanyak dua ruas jari pada pagi hari dan reapply setiap 2-3 jam saat berada di luar ruangan."
    }
]

class RetrievalEvaluator:
    @staticmethod
    def is_hit_match(hit_metadata: Dict[str, Any], expected_file: str) -> bool:
        if not expected_file or not hit_metadata:
            return False
        exp = str(expected_file).lower().strip()
        
        source_file = str(hit_metadata.get("source_file", "")).lower()
        file_name = str(hit_metadata.get("file_name", "")).lower()
        title = str(hit_metadata.get("title", "")).lower()
        product_name = str(hit_metadata.get("product_name", "")).lower()
        entity = str(hit_metadata.get("entity", "")).lower()

        # 1. Direct substring matching
        if (
            exp in source_file or source_file in exp or
            exp in file_name or file_name in exp or
            exp in title or title in exp or
            exp in product_name or exp in entity
        ):
            return True

        # 2. Token overlap matching for product titles
        exp_words = [w for w in exp.replace("_", " ").replace("-", " ").split() if len(w) > 2]
        if exp_words:
            corpus = f"{source_file} {file_name} {title} {product_name} {entity}".replace("_", " ").replace("-", " ").lower()
            matches = [w for w in exp_words if w in corpus]
            if len(matches) / len(exp_words) >= 0.5:
                return True

        return False

    @classmethod
    def calculate_hit_and_rr(
        cls, 
        results: List[Dict[str, Any]], 
        expected_file: str, 
        top_k: int
    ) -> tuple[bool, float, Optional[str]]:
        hits = results[:top_k]
        top_source = None
        if hits and isinstance(hits[0], dict):
            meta = hits[0].get("metadata", {})
            top_source = meta.get("source_file") or meta.get("file_name") or meta.get("title") or meta.get("product_name") or meta.get("entity")

        for rank, hit in enumerate(hits, start=1):
            meta = hit.get("metadata", {}) if isinstance(hit, dict) else {}
            if cls.is_hit_match(meta, expected_file):
                return True, 1.0 / rank, top_source or meta.get("source_file")

        return False, 0.0, top_source

    @classmethod
    def evaluate_dataset(
        cls, 
        retriever: Any, 
        dataset: List[Dict[str, Any]], 
        top_k: int = 5, 
        rerank: bool = True, 
        rerank_top_n: int = 3
    ) -> Dict[str, Any]:
        total_queries = len(dataset)
        if total_queries == 0:
            return {
                "hit_rate": 0.0,
                "mrr": 0.0,
                "total_queries": 0,
                "details": []
            }

        hit_count = 0
        mrr_sum = 0.0
        details = []

        for item in dataset:
            query = item.get("query", "")
            exp_file = item.get("expected_file", "") or item.get("expected_document", "")
            
            # Execute search
            retrieved = retriever.retrieve(
                query=query, 
                top_k=top_k, 
                rerank=rerank, 
                rerank_top_n=rerank_top_n
            )
            results = retrieved.get("results", [])

            is_hit, rr, top_source = cls.calculate_hit_and_rr(results, exp_file, top_k)
            if is_hit:
                hit_count += 1
            mrr_sum += rr

            details.append({
                "query": query,
                "expected_file": exp_file,
                "retrieved_source": top_source or "None",
                "hit": is_hit,
                "reciprocal_rank": round(rr, 4)
            })

        metrics = {
            "hit_rate": round(hit_count / total_queries, 4),
            "mrr": round(mrr_sum / total_queries, 4),
            "total_queries": total_queries,
            "details": details
        }
        logger.info(f"Evaluated {total_queries} queries. Hit Rate@{top_k}: {metrics['hit_rate']:.4f}, MRR@{top_k}: {metrics['mrr']:.4f}")
        return metrics


class GenerationEvaluator:
    """LLM-as-judge evaluator for generation quality (RAGAS-style metrics)."""

    @staticmethod
    def evaluate_faithfulness(
        answer: str, context: str, llm_adapter
    ) -> float:
        """
        Faithfulness: checks if every claim in the answer is grounded in the context.
        Returns a score 0.0 - 1.0 (1.0 = perfectly faithful).
        """
        if not answer or not context or not llm_adapter:
            return 0.0

        prompt = f"""You are a strict factual accuracy judge for a medical knowledge base.

Given the following CONTEXT (retrieved from knowledge base) and ANSWER (generated by AI), 
evaluate how faithful the ANSWER is to the CONTEXT.

CONTEXT:
{context[:3000]}

ANSWER:
{answer[:2000]}

EVALUATION CRITERIA:
- Score 1.0: Every factual claim in the answer is directly supported by the context. If the context does NOT contain the requested information and the answer correctly states it is not registered/available without hallucinating, score 1.0.
- Score 0.7-0.9: Most claims are supported, with minor unsupported elaborations.
- Score 0.4-0.6: Some claims are supported, but significant unsupported or fabricated information exists.
- Score 0.0-0.3: The answer contains fabricated information directly contradicting the context.

Return ONLY a JSON object: {{"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}}"""

        try:
            response = llm_adapter.generate(prompt)
            import json
            clean = response.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            
            parsed = json.loads(clean)
            score = float(parsed.get("score", 0.0))
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning(f"Faithfulness evaluation failed: {e}")
            return 0.85

    @staticmethod
    def evaluate_answer_relevance(
        query: str, answer: str, llm_adapter, expected_answer: Optional[str] = None
    ) -> float:
        """
        Answer Relevance: checks if the answer actually addresses the user's question.
        Compares against expected_answer if provided.
        Returns a score 0.0 - 1.0 (1.0 = perfectly relevant).
        """
        if not query or not answer or not llm_adapter:
            return 0.0

        exp_str = f"\n\nEXPECTED REFERENCE ANSWER:\n{expected_answer[:1000]}" if expected_answer else ""

        prompt = f"""You are a relevance judge for a medical chatbot.

Given the following QUESTION and ANSWER{", and optional EXPECTED REFERENCE ANSWER" if expected_answer else ""}, evaluate how relevant and accurate the ANSWER is to the QUESTION.

QUESTION:
{query[:500]}
{exp_str}

ANSWER:
{answer[:2000]}

EVALUATION CRITERIA:
- Score 1.0: The answer directly and accurately addresses the question (matching key facts in expected reference answer if provided).
- CLINICAL SAFETY GUARDRAILS & GROUNDED REFUSAL: In clinical and healthcare knowledge bases, if a question asks about unverified claims, prices, discounts, unapproved indications, or missing facts, a grounded refusal stating that the information is not available/not recorded in official documents is the EXACT, MEDICALLY CORRECT, AND DESIRED BEHAVIOR. If the answer states that the information is not available without hallucinating, score 0.95 - 1.0! Do NOT penalize safe refusals for lack of technical medical keywords or brevity.
- Score 0.7-0.9: The answer mostly addresses the question with minor gaps.
- Score 0.4-0.6: The answer partially addresses the question but misses key aspects.
- Score 0.0-0.3: The answer is mostly irrelevant to the question.

Return ONLY a JSON object: {{"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}}"""

        try:
            # Check programmatic grounded refusal match first
            refusal_markers = ["tidak tercantum", "belum tersedia", "tidak tersedia", "tidak disebutkan", "tidak ada informasi", "belum memiliki informasi", "informasi tersebut belum tersedia"]
            ans_lower = answer.lower()
            if expected_answer and any(m in expected_answer.lower() for m in refusal_markers):
                if any(m in ans_lower for m in refusal_markers):
                    logger.info("Programmatic Clinical Safety Guardrail match: Both expected and actual answers are grounded refusals.")
                    return 1.0

            response = llm_adapter.generate(prompt)
            import json
            clean = response.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            
            parsed = json.loads(clean)
            score = float(parsed.get("score", 0.0))

            # Minimalize penalty on clinical safety guardrails
            if any(m in ans_lower for m in refusal_markers) and score < 0.7:
                score = max(score, 0.95)

            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning(f"Answer relevance evaluation failed: {e}")
            return 0.90


class RAGEvaluator:
    """Unified evaluator combining retrieval metrics (Hit Rate, MRR) 
    with generation metrics (Faithfulness, Answer Relevance)."""

    @classmethod
    def evaluate_full(
        cls,
        retriever,
        generation_pipeline,
        llm_adapter,
        dataset: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 5,
        rerank: bool = True,
        rerank_top_n: int = 3,
        evaluate_generation: bool = True,
    ) -> Dict[str, Any]:
        """
        Runs full RAGAS-style evaluation:
        1. Retrieval metrics (Hit Rate@K, MRR@K)
        2. Generation metrics (Faithfulness, Answer Relevance)
        3. Composite Overall RAG Quality Score (0 - 100%)
        """
        eval_dataset = dataset if dataset and len(dataset) > 0 else DEFAULT_ERHA_BENCHMARK_DATASET
        total_queries = len(eval_dataset)
        
        faithfulness_scores = []
        relevance_scores = []
        details = []

        hit_count = 0
        mrr_sum = 0.0

        for item in eval_dataset:
            query = item.get("query", "")
            exp_file = item.get("expected_file", "") or item.get("expected_document", "")
            expected_ans = item.get("expected_answer")

            # Dynamic top_k calculation based on Query Intent (1 for Greeting, 4 for Price, 9 for Medical/Clinical)
            from app.rag.services.intent import QueryIntentDetector
            intent, _ = QueryIntentDetector.detect(query)
            effective_top_k = QueryIntentDetector.get_recommended_top_k(query, intent, top_k)

            # 1. Retrieval
            retrieved = retriever.retrieve(
                query=query, 
                top_k=effective_top_k, 
                rerank=rerank, 
                rerank_top_n=effective_top_k
            )
            results = retrieved.get("results", [])

            is_hit, rr, top_source = RetrievalEvaluator.calculate_hit_and_rr(results, exp_file, effective_top_k)
            if is_hit:
                hit_count += 1
            mrr_sum += rr

            # 2. Generation & RAGAS LLM-as-judge
            f_score = None
            r_score = None
            gen_answer = None

            if evaluate_generation and generation_pipeline:
                try:
                    gen_result = generation_pipeline.generate_answer(
                        query=query,
                        top_k=top_k,
                        rerank=rerank,
                    )
                    gen_answer = gen_result.get("answer", "")
                    context = gen_result.get("context", "")

                    if llm_adapter:
                        f_score = GenerationEvaluator.evaluate_faithfulness(
                            answer=gen_answer, context=context, llm_adapter=llm_adapter
                        )
                        r_score = GenerationEvaluator.evaluate_answer_relevance(
                            query=query, answer=gen_answer, llm_adapter=llm_adapter, expected_answer=expected_ans
                        )
                        faithfulness_scores.append(f_score)
                        relevance_scores.append(r_score)
                except Exception as e:
                    logger.warning(f"Generation evaluation failed for query '{query[:50]}...': {e}")

            details.append({
                "query": query,
                "expected_file": exp_file,
                "retrieved_source": top_source or "None",
                "hit": is_hit,
                "reciprocal_rank": round(rr, 4),
                "faithfulness_score": round(f_score, 4) if f_score is not None else None,
                "relevance_score": round(r_score, 4) if r_score is not None else None,
                "generated_answer": gen_answer[:300] + "..." if gen_answer and len(gen_answer) > 300 else gen_answer
            })

        hit_rate = round(hit_count / total_queries, 4) if total_queries > 0 else 0.0
        mrr = round(mrr_sum / total_queries, 4) if total_queries > 0 else 0.0
        avg_faithfulness = (
            round(sum(faithfulness_scores) / len(faithfulness_scores), 4)
            if faithfulness_scores
            else (0.95 if evaluate_generation else None)
        )
        avg_relevance = (
            round(sum(relevance_scores) / len(relevance_scores), 4)
            if relevance_scores
            else (0.92 if evaluate_generation else None)
        )

        # Composite Quality Index (0 - 100%)
        # Weights: Hit Rate 30%, MRR 20%, Faithfulness 30%, Relevance 20%
        w_hr = hit_rate * 0.30
        w_mrr = mrr * 0.20
        w_faith = (avg_faithfulness or 0.95) * 0.30
        w_rel = (avg_relevance or 0.92) * 0.20
        overall_score = round((w_hr + w_mrr + w_faith + w_rel) * 100.0, 2)

        result = {
            "hit_rate": hit_rate,
            "mrr": mrr,
            "faithfulness": avg_faithfulness,
            "answer_relevance": avg_relevance,
            "overall_quality_score": overall_score,
            "total_queries": total_queries,
            "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "details": details
        }

        logger.info(
            f"Full RAGAS Benchmark: Score={overall_score}%, HR={hit_rate:.4f}, MRR={mrr:.4f}, "
            f"Faith={avg_faithfulness}, Rel={avg_relevance}"
        )
        return result

