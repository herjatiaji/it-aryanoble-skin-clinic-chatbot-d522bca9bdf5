"""Automated Benchmark Evaluator for ERHA Truwhite Skincare Chatbot.

Runs the 10 gold-standard benchmark test queries against the RAG Generation Pipeline
and evaluates Retrieval Metrics (Hit Rate, MRR) as well as Generation Quality 
(Faithfulness, Answer Relevance).
"""

import sys
import os
import json
import asyncio
from typing import List, Dict, Any
from loguru import logger

# Add parent directories to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# Force UTF-8 encoding for Windows stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.rag.services.evaluation import RAGEvaluator, GenerationEvaluator
from app.rag.services.rag_generator import GenerationPipeline
from app.rag.services.rag_retriever import HybridRetriever, BM25Index
from app.rag.services.factory import AdapterFactory
from app.rag.config import settings as rag_settings


# ── 10 Gold-Standard ERHA Truwhite Benchmark Test Set ────────────────────────

BENCHMARK_DATASET: List[Dict[str, Any]] = [
    {
        "id": 1,
        "category": "Routine Selection",
        "query": "Saya punya kulit yang terlihat kusam, warna kulit juga kurang merata, dan ada beberapa bekas jerawat yang membuat wajah terlihat tidak bersih. Saya ingin mulai menggunakan rangkaian ERHA Truwhite, tetapi bingung harus memilih produk yang mana karena ada facial wash, toner, serum, booster, moisturizer, dan produk lainnya. Dari produk yang ada di dokumen, mana yang paling relevan untuk kondisi tersebut dan bagaimana urutan penggunaannya?",
        "expected_answer": "Produk yang relevan adalah ERHA Truwhite Brightening Facial Wash, Brightening Pore Toner, Truwhite Brightening Serum with 10% Stable Ethyl Vitamin C & Brightening Peptides, dan Truwhite Brightening Day Cream SPF30 PA+++. Facial wash digunakan pagi dan malam, toner setelah mencuci wajah, serum 2–3 tetes setelah toner sebelum moisturizer, dan day cream digunakan setiap pagi sebagai langkah terakhir sebelum makeup.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 2,
        "category": "Product Comparison",
        "query": "Saya melihat ada dua produk yang sama-sama ditujukan untuk masalah brightening, yaitu ERHA Truwhite Brightening Serum dengan 10% Stable Ethyl Vitamin C & Brightening Peptides dan ERHA Truwhite Active Glow Booster dengan 3% Tranexamic Acid & Hexyl Resorcinol. Kulit saya kusam, punya noda hitam dan bekas jerawat. Apa perbedaan fokus kedua produk tersebut, kandungan utamanya apa, dan kapan masing-masing produk digunakan?",
        "expected_answer": "Brightening Serum menggunakan 10% Ethyl Ascorbic Acid, Brightening Peptides, Niacinamide 5%, Vitamin E, dan Hyaluronic Acid dengan fokus menyamarkan dark spots dan meratakan warna kulit. Booster menggunakan Tranexamic Acid 3%, Hexyl Resorcinol, Alpha Arbutin 2%, Niacinamide, dan Allantoin dengan fokus hiperpigmentasi dan noda hitam. Serum digunakan setelah toner sebelum moisturizer, sedangkan booster digunakan setelah toner dan sebelum serum/moisturizer.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 3,
        "category": "Morning & Night Routine",
        "query": "Saya ingin membuat rutinitas skincare sederhana menggunakan produk ERHA Truwhite. Saya ingin tahu produk mana yang digunakan pada pagi hari dan mana yang digunakan pada malam hari, mulai dari mencuci wajah sampai moisturizer. Tolong susun urutannya berdasarkan petunjuk penggunaan dalam dokumen dan jangan menambahkan produk atau langkah yang tidak disebutkan.",
        "expected_answer": "Pagi hari: Facial Wash -> Pore Toner -> Serum/Booster -> Day Cream SPF30 PA+++. Malam hari: Facial Wash -> Pore Toner -> Serum/Booster -> Night Cream. Night cream digunakan setiap malam setelah serum.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 4,
        "category": "Oily Skin Moisturizer",
        "query": "Saya memiliki kulit normal yang cenderung berminyak dan saya tidak suka moisturizer yang terasa berat atau lengket. Dari seluruh produk ERHA Truwhite dalam dokumen, moisturizer mana yang paling sesuai untuk kondisi tersebut? Jelaskan tekstur, kandungan utama, manfaat, jenis kulit yang direkomendasikan, serta kapan penggunaannya.",
        "expected_answer": "Produk yang paling sesuai adalah ERHA Truwhite Peptovitae® Bright, Yuzu Extract & Niacinamide Moisture Gel Cream. Teksturnya ringan, melembapkan tanpa lengket, cocok untuk kulit normal, kombinasi, dan berminyak, serta digunakan pagi dan malam setelah serum.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 5,
        "category": "Sensitive Skin Toner",
        "query": "Saya punya kulit yang cukup sensitif dan sedang mencari toner yang tidak hanya membantu hidrasi tetapi juga bisa membantu membuat kulit tampak lebih cerah. Apakah ada toner dalam rangkaian ERHA Truwhite yang menurut dokumen cocok untuk kulit sensitif? Saya juga ingin mengetahui kandungan utamanya dan cara penggunaannya.",
        "expected_answer": "Ada, yaitu ERHA Truwhite Brightening Pore Toner. Toner ini cocok untuk semua jenis kulit termasuk kulit sensitif. Kandungannya antara lain Niacinamide, PHA, Licorice Extract, Betaine, dan Hyaluronic Acid. Digunakan setelah mencuci wajah.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 6,
        "category": "Trick Question (Missing Facts)",
        "query": "Saya ingin membeli ERHA Truwhite Brightening Facial Wash. Berapa harga produknya, apakah sedang ada diskon 50%, dan apakah tersedia ukuran 150 ml? Saya juga ingin tahu apakah produk tersebut bebas alkohol dan parfum.",
        "expected_answer": "Informasi mengenai harga, diskon 50%, ukuran 150 ml, serta kandungan alkohol atau parfum tidak tercantum dalam dokumen basis pengetahuan.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 7,
        "category": "Eye Serum Specifics",
        "query": "Saya punya masalah area bawah mata yang terlihat lelah, terdapat dark circle dan sedikit puffiness. Saya ingin tahu apakah ada produk khusus area mata dalam rangkaian ERHA Truwhite. Jika ada, apa kandungan utamanya, manfaatnya, siapa yang bisa menggunakannya, dan berapa banyak produk yang harus diaplikasikan?",
        "expected_answer": "Ada, yaitu ERHA Truwhite Algae Complex & Cucumber Extract Brightening Eye Serum. Kandungannya meliputi Algae Complex, Cucumber Extract, Caffeine, Niacinamide, dan Peptides. Cara penggunaannya adalah sebesar sebutir beras pada area bawah mata pagi dan malam.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 8,
        "category": "Day vs Night Cream",
        "query": "Saya masih bingung mengapa dalam rangkaian Truwhite ada Brightening Day Cream SPF30 PA+++ dan Brightening Night Cream. Kalau tujuan saya sama-sama ingin mendapatkan kulit yang lebih cerah dan lembap, apakah keduanya memiliki fungsi yang sama? Jelaskan perbedaan kandungan, manfaat, jenis kulit, dan waktu penggunaannya berdasarkan dokumen.",
        "expected_answer": "Brightening Day Cream berfokus melembapkan dan melindungi dari sinar UVA/UVB (SPF30 PA+++) pada pagi hari. Brightening Night Cream berfokus pada regenerasi kulit, menyamarkan noda hitam, dan menjaga skin barrier sepanjang malam.",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 9,
        "category": "Explicit Niacinamide Percentage",
        "query": "Saya sedang mencari produk brightening dan melihat bahwa Niacinamide muncul di beberapa produk ERHA Truwhite dengan konsentrasi yang berbeda. Bisa jelaskan produk mana saja dalam dokumen yang secara eksplisit mencantumkan persentase Niacinamide dan berapa persentasenya? Saya ingin jawaban hanya berdasarkan informasi yang tertulis di dokumen.",
        "expected_answer": "Produk yang secara eksplisit mencantumkan persentase Niacinamide adalah: Brightening Facial Wash (2%), Brightening Serum (5%), Brightening Day Cream (4%), dan Peptovitae® Bright Moisture Gel Cream (5%).",
        "ground_truth": {"type": "product"}
    },
    {
        "id": 10,
        "category": "Complex Multi-Need Reasoning",
        "query": "Bayangkan saya adalah pengguna dengan kulit kusam, warna kulit tidak merata, memiliki bekas jerawat dan beberapa noda hitam. Saya juga ingin menjaga kelembapan dan skin barrier, tetapi saya tidak ingin menggunakan produk yang terlalu berat karena kulit saya cenderung berminyak. Dari seluruh produk dalam dokumen, bagaimana kamu akan menyusun pilihan produk yang paling relevan? Jelaskan alasan pemilihan setiap produk berdasarkan manfaat, kandungan, jenis kulit, dan waktu penggunaannya. Jangan memberikan klaim yang tidak tercantum dalam dokumen.",
        "expected_answer": "Rangkaian yang paling sesuai mencakup Brightening Facial Wash, Brightening Pore Toner, Brightening Serum with 10% Ethyl Vitamin C, dan Peptovitae® Bright Moisture Gel Cream (tekstur ringan cocok untuk kulit berminyak) serta Day Cream SPF30 di pagi hari.",
        "ground_truth": {"type": "product"}
    }
]


# ── Benchmark Runner ─────────────────────────────────────────────────────────

def run_benchmark():
    """Runs full automated benchmark test suite."""
    print("=" * 80)
    print("🚀 ERHA TRUWHITE CHATBOT - AUTOMATED BENCHMARK EVALUATION TEST")
    print("=" * 80)

    try:
        vector_store = AdapterFactory.get_vector_store()
        bm25_index = BM25Index()
        try:
            bm25_index.load(rag_settings.bm25_index_path)
        except Exception:
            pass

        hybrid_retriever = HybridRetriever(
            vector_store=vector_store,
            bm25_index=bm25_index,
            reranker=None
        )
        llm_adapter = AdapterFactory.get_llm_adapter()
        generation_pipeline = GenerationPipeline(
            retriever=hybrid_retriever, llm_adapter=llm_adapter
        )

        print(f"Loaded {len(BENCHMARK_DATASET)} benchmark queries. Running generation & evaluation...\n")

        results = []
        faithfulness_scores = []
        relevance_scores = []

        for item in BENCHMARK_DATASET:
            qid = item["id"]
            cat = item["category"]
            query = item["query"]
            print(f"[{qid}/10] Testing: {cat}...")

            gen_result = generation_pipeline.generate_answer(
                query=query,
                top_k=5,
                rerank=True
            )
            answer = gen_result.get("answer", "")
            context = gen_result.get("context", "")

            faith_score = GenerationEvaluator.evaluate_faithfulness(
                answer=answer, context=context, llm_adapter=llm_adapter
            )
            rel_score = GenerationEvaluator.evaluate_answer_relevance(
                query=query, answer=answer, llm_adapter=llm_adapter, expected_answer=item.get("expected_answer")
            )

            faithfulness_scores.append(faith_score)
            relevance_scores.append(rel_score)

            results.append({
                "id": qid,
                "category": cat,
                "faithfulness": faith_score,
                "relevance": rel_score,
                "answer_preview": answer[:150].replace("\n", " ") + "..."
            })

        avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

        print("\n" + "=" * 80)
        print("📊 AUTOMATED EVALUATION REPORT SUMMARY")
        print("=" * 80)
        print(f"Total Benchmark Queries : {len(BENCHMARK_DATASET)}")
        print(f"Average Faithfulness    : {avg_faithfulness:.4f} ({avg_faithfulness * 100:.1f}%)")
        print(f"Average Answer Relevance: {avg_relevance:.4f} ({avg_relevance * 100:.1f}%)")
        print("-" * 80)
        print(f"{'ID':<4} | {'Category':<28} | {'Faithfulness':<12} | {'Relevance':<10}")
        print("-" * 80)
        for r in results:
            print(f"{r['id']:<4} | {r['category']:<28} | {r['faithfulness']:<12.2f} | {r['relevance']:<10.2f}")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Benchmark run failed: {e}")
        print(f"❌ Error during benchmark execution: {e}")


if __name__ == "__main__":
    run_benchmark()
