"""Query Intent Detection Module for ERHA RAG Chatbot.

Classifies user queries into granular intent categories to determine
strict response length limits and tailored response constraints.
"""

from enum import Enum
from typing import Dict, Any, Tuple
import re
from loguru import logger


class QueryIntent(str, Enum):
    PRODUCT_NAME = "PRODUCT_NAME"
    PRODUCT_FUNCTION = "PRODUCT_FUNCTION"
    INGREDIENTS = "INGREDIENTS"
    HOW_TO_USE = "HOW_TO_USE"
    BENEFITS = "BENEFITS"
    SUITABLE_FOR = "SUITABLE_FOR"
    WARNING = "WARNING"
    COMPARISON = "COMPARISON"
    AVAILABILITY = "AVAILABILITY"
    PRICE = "PRICE"
    UNKNOWN = "UNKNOWN"


_INTENT_PATTERNS = [
    # 1. PRICE
    (
        QueryIntent.PRICE,
        [r"\bharga\b", r"\bberapa harga\b", r"\bbiaya\b", r"\bprice\b", r"\bharganya\b"]
    ),
    # 2. PRODUCT_NAME
    (
        QueryIntent.PRODUCT_NAME,
        [
            r"\bapa nama produk\b", r"\bnama produk\b", r"\bapa nama\b",
            r"\bfacial cleanser dari\b", r"\bcleanser dari\b", r"\bfacial wash dari\b",
            r"\bproduk pembersih\b", r"\bserum dari\b", r"\bmoisturizer dari\b",
            r"\bsebutkan nama produk\b"
        ]
    ),
    # 3. INGREDIENTS
    (
        QueryIntent.INGREDIENTS,
        [
            r"\bingredients?\b", r"\bkandungan\b", r"\bbahan aktif\b",
            r"\bkomposisi\b", r"\bformula\b", r"\bactive ingredients?\b",
            r"\bterbuat dari\b", r"\bmengandung apa\b"
        ]
    ),
    # 4. HOW_TO_USE
    (
        QueryIntent.HOW_TO_USE,
        [
            r"\bcara pakai(?:nya)?\b", r"\bcara peng+unaan\b", r"\baturan pakai\b",
            r"\bdosis\b", r"\bhow to use\b", r"\bdipakai kapan\b", r"\burutan pakai\b",
            r"\bcara menggunakannya\b", r"\bcara mengoleskan\b"
        ]
    ),
    # 5. WARNING / CONTRAINDICATION / PREGNANCY
    (
        QueryIntent.WARNING,
        [
            r"\baman untuk\b", r"\bibu hamil\b", r"\bbumil\b", r"\bmenyusui\b",
            r"\befek samping\b", r"\bkontraindikasi\b", r"\bahaya\b",
            r"\biritasi\b", r"\balergi\b", r"\bpantangan\b"
        ]
    ),
    # 6. COMPARISON
    (
        QueryIntent.COMPARISON,
        [
            r"\bperbedaan\b", r"\bbedanya\b", r"\bperbandingan\b",
            r"\bdibandingkan\b", r"\bvs\b", r"\bmana yang lebih\b"
        ]
    ),
    # 7. SUITABLE_FOR
    (
        QueryIntent.SUITABLE_FOR,
        [
            r"\bcocok untuk\b", r"\bdiperuntukkan\b", r"\bunduk kulit apa\b",
            r"\bjenis kulit\b", r"\bindikasi pasien\b", r"\bsuitable for\b"
        ]
    ),
    # 8. BENEFITS
    (
        QueryIntent.BENEFITS,
        [
            r"\bkeunggulan\b", r"\bkelebihan\b", r"\bbenefit\b", r"\badvantages\b"
        ]
    ),
    # 9. PRODUCT_FUNCTION
    (
        QueryIntent.PRODUCT_FUNCTION,
        [
            r"\bdigunakan untuk apa\b", r"\buntuk apa\b", r"\bfungsi\b",
            r"\bmanfaat\b", r"\bkegunaan\b", r"\bkhasiat\b", r"\bguna\b",
            r"\bberfungsi untuk\b"
        ]
    ),
    # 10. AVAILABILITY
    (
        QueryIntent.AVAILABILITY,
        [
            r"\btersedia di mana\b", r"\bada di mana\b", r"\bstok\b", r"\bready\b",
            r"\bbisa dibeli\b", r"\bdapat dibeli\b"
        ]
    ),
]


class QueryIntentDetector:
    """Classifies user queries into specific intent categories."""

    @staticmethod
    def detect(query: str) -> Tuple[QueryIntent, Dict[str, Any]]:
        """
        Detects query intent and returns (intent, rules_dict).
        """
        query_clean = query.strip().lower()

        for intent, patterns in _INTENT_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, query_clean, re.IGNORECASE):
                    rules = QueryIntentDetector._get_rules_for_intent(intent)
                    logger.info(f"Query intent detected: '{intent.value}' (matched pattern: '{pattern}')")
                    return intent, rules

        # Default fallback: UNKNOWN
        rules = QueryIntentDetector._get_rules_for_intent(QueryIntent.UNKNOWN)
        logger.info(f"Query intent detected: '{QueryIntent.UNKNOWN.value}' (default)")
        return QueryIntent.UNKNOWN, rules

    @staticmethod
    def _get_rules_for_intent(intent: QueryIntent) -> Dict[str, Any]:
        """Returns length constraints and specific rules per intent."""
        if intent == QueryIntent.PRODUCT_NAME:
            return {
                "max_sentences": 1,
                "length_instruction": "Return ONLY the exact product name in 1 sentence. Do not add unsolicited product recommendations, clinical regimens, or usage instructions.",
                "missing_fallback": "Informasi nama produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.INGREDIENTS:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY the relevant active ingredients in 1-2 sentences or a concise list. Do not add unsolicited product recommendations or clinical advice.",
                "missing_fallback": "Informasi ingredients produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.PRODUCT_FUNCTION or intent == QueryIntent.BENEFITS:
            return {
                "max_sentences": 3,
                "length_instruction": "Return ONLY the primary product function/benefits in maximum 2-3 sentences. Do not add unsolicited clinical regimens, extra product recommendations, or disclaimers.",
                "missing_fallback": "Informasi fungsi produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.HOW_TO_USE:
            return {
                "max_sentences": 4,
                "length_instruction": "Return ONLY the usage instructions in maximum 2-4 sentences. Do not add extra product recommendations or clinical disclaimers.",
                "missing_fallback": "Informasi cara penggunaan produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.PRICE:
            return {
                "max_sentences": 1,
                "length_instruction": "Return ONLY the product price if found in context in 1 sentence.",
                "missing_fallback": "Informasi harga produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.WARNING:
            return {
                "max_sentences": 3,
                "length_instruction": "Return ONLY safety warnings, contraindications, or pregnancy notes mentioned in context in maximum 2-3 sentences. Do not provide medical advice outside retrieved context.",
                "missing_fallback": "Informasi mengenai keamanan/kontraindikasi penggunaan produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.COMPARISON:
            return {
                "max_sentences": 4,
                "length_instruction": "Provide a concise comparison comparing ONLY the requested products using retrieved context. Do not mention any third product.",
                "missing_fallback": "Informasi perbandingan produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.SUITABLE_FOR:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY the target skin type / indication in 1-2 sentences.",
                "missing_fallback": "Informasi indikasi/kesesuaian jenis kulit produk tersebut tidak tersedia dalam knowledge base."
            }
        elif intent == QueryIntent.AVAILABILITY:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY product availability or branch availability mentioned in context.",
                "missing_fallback": "Informasi ketersediaan produk tersebut tidak tersedia dalam knowledge base."
            }
        else:
            return {
                "max_sentences": 3,
                "length_instruction": "Answer the question concisely in maximum 2-3 sentences using ONLY the retrieved context. Do not over-explain or provide unsolicited recommendations.",
                "missing_fallback": "Informasi yang diminta tidak tersedia dalam knowledge base."
            }
