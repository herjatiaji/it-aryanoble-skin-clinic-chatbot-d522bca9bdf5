"""Query Intent Detection Module for ERHA RAG Chatbot.

Classifies user queries into granular intent categories to determine
strict response length limits and tailored response constraints.
"""

from enum import Enum
from typing import Dict, Any, Tuple, Optional
import re
from datetime import datetime, timezone, timedelta
from loguru import logger


def get_current_time_period() -> str:
    """
    Returns the time period in Indonesian:
    - 'pagi' (04:00 - 10:59)
    - 'siang' (11:00 - 14:59)
    - 'sore' (15:00 - 18:29)
    - 'malam' (18:30 - 03:59)
    Uses WIB (UTC+7) or local system time.
    """
    try:
        tz_wib = timezone(timedelta(hours=7))
        now = datetime.now(tz_wib)
    except Exception:
        now = datetime.now()

    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute

    if 4 * 60 <= total_minutes < 11 * 60:
        return "pagi"
    elif 11 * 60 <= total_minutes < 15 * 60:
        return "siang"
    elif 15 * 60 <= total_minutes < 18 * 60 + 30:
        return "sore"
    else:
        return "malam"


def format_doctor_name(doctor_name: Optional[str] = None) -> str:
    """Formats doctor name cleanly, ensuring polite title like 'dr. Sarah' or 'Dok'."""
    if not doctor_name or not str(doctor_name).strip():
        return "Dok"
    clean = str(doctor_name).strip()
    if clean.lower().startswith("dr.") or clean.lower().startswith("dr ") or clean.lower().startswith("dokter"):
        return clean
    return f"dr. {clean}"


def get_contextual_greeting_response(query: str = "", doctor_name: Optional[str] = None) -> str:
    """
    Generates a natural, warm, and contextual greeting response for Doctors,
    matching the doctor's greeting tone and greeting words (not rigid to server clock).
    """
    doc_title = format_doctor_name(doctor_name)
    q_lower = query.lower().strip()

    # Contextual greeting matching from doctor's prompt
    salutation = "Halo"
    if "selamat pagi" in q_lower or "pagi" in q_lower.split():
        salutation = "Selamat pagi"
    elif "selamat siang" in q_lower or "siang" in q_lower.split():
        salutation = "Selamat siang"
    elif "selamat sore" in q_lower or "sore" in q_lower.split():
        salutation = "Selamat sore"
    elif "selamat malam" in q_lower or "malam" in q_lower.split():
        salutation = "Selamat malam"
    elif "assalamualaikum" in q_lower or "assalamu'alaikum" in q_lower:
        salutation = "Wa'alaikumsalam"
    elif "hai" in q_lower.split() or "hi" in q_lower.split():
        salutation = "Hai"

    if any(k in q_lower for k in ["siapa", "kamu siapa", "anda siapa", "bot apa", "siapakah kamu"]):
        return f"{salutation}, {doc_title}! Saya ERHA Medical Assistant, asisten klinis yang siap membantu Dokter mencari informasi SOP tindakan medis, indikasi, dan panduan produk ERHA."

    return f"{salutation}, {doc_title}! Saya ERHA Medical Assistant. Ada yang bisa saya bantu terkait protokol tindakan medis atau produk ERHA hari ini?"


# Backward compatibility alias
def get_time_greeting_response(query: str = "", doctor_name: Optional[str] = None) -> str:
    return get_contextual_greeting_response(query=query, doctor_name=doctor_name)


def get_closing_response(doctor_name: Optional[str] = None) -> str:
    """Generates a warm, professional closing response without repeating past recommendations."""
    doc_title = format_doctor_name(doctor_name)
    return f"Sama-sama, {doc_title}! Senang bisa membantu."


class QueryIntent(str, Enum):
    GREETING = "GREETING"
    CLOSING = "CLOSING"
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
    EDIT = "EDIT"
    DELETE = "DELETE"
    UNKNOWN = "UNKNOWN"



_INTENT_PATTERNS = [
    # 0. GREETING / SAPAAN & IDENTITY
    (
        QueryIntent.GREETING,
        [
            r"^\s*(halo|hallo|hai|hi|hey|hello)(\s+dok|\s+dokter)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(selamat\s+(pagi|siang|sore|malam)|(pagi|siang|sore|malam))(\s+dok|\s+dokter)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(halo|hallo|hai|hi|hey|hello)\s*[\.\,\!\?]*\s*(selamat\s+(pagi|siang|sore|malam)|(pagi|siang|sore|malam))(\s+dok|\s+dokter)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(selamat\s+(pagi|siang|sore|malam)|(pagi|siang|sore|malam))\s*[\.\,\!\?]*\s*(halo|hallo|hai|hi|hey|hello)(\s+dok|\s+dokter)?\s*[\.\,\!\?]*\s*$",
            r"^\s*assalamu['a]?laikum(\s+wr\s+wb|\s+warahmatullahi\s+wabarakatuh)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(tes|test|ping)\s*[\.\,\!\?]*\s*$",
            r"^\s*(halo|hallo|hai|hi|hello)\s+(ada\s+orang|apakah\s+ada\s+orang|bisa\s+bantu|apa\s+kabar)\s*[\.\,\!\?]*\s*$",
            r"^\s*(halo|hallo|hai|hi|hello)\s+(admin|cs|asisten|bot|erha)\s*[\.\,\!\?]*\s*$",
            r"^\s*(kamu|anda|siapa\s+kamu|siapa\s+anda|kamu\s+siapa|anda\s+siapa|kamu\s+bot\s+apa|siapa\s+kamu\?|kamu\s+siapa\?)\s*[\.\,\!\?]*\s*$",
        ]
    ),
    # 0.1 CLOSING / TERIMA KASIH & ACKNOWLEDGMENT
    (
        QueryIntent.CLOSING,
        [
            r"^\s*(oke|ok|okay|kalo\s+begitu|kalau\s+gitu|kalau\s+begitu|kalo\s+gitu|baik|baiklah|sip|siap)?\s*(terima\s*kasih|terimakasih|terimaksih|makasih|makasi|thanks|thank\s*you|thx|trims|tengkyu)(\s+banyak|\s+infonya|\s+atas\s+rekomendasinya|\s+rekomendasinya|\s+ya|\s+ya\s+dok|\s+ya\s+dokter|\s+dok|\s+dokter|\s+atas\s+infonya|\s+saran\s*nya)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(terima\s*kasih|terimakasih|makasih|thanks|thank\s*you|trims)\s+(banyak|atas\s+bantuannya|atas\s+infonya|infonya|rekomendasinya|sarannya|ya|dok|dokter)(\s+dok|\s+dokter|\s+ya|\s+ya\s+dok|\s+ya\s+dokter)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(oke|ok|okay|sip|siap|baik|baiklah|mantap|noted|clear|paham|mengerti|cukup|sudah\s+cukup|cukup\s+jelas|sudah\s+jelas|sama[- ]sama)(\s+deh|\s+ya|\s+nih|\s+sip|\s+dok|\s+dokter|\s+terima\s*kasih|\s+makasih)?\s*[\.\,\!\?]*\s*$",
            r"^\s*(oke|ok|okay)\s+(dok|dokter|sip|siap|baik|noted)\s*[\.\,\!\?]*\s*$"
        ]
    ),
    # 1. EDIT KNOWLEDGE
    (
        QueryIntent.EDIT,
        [
            r"\b(ganti|ubah|edit|tukar|salin|revisi|pembaruan|perbarui|modifikasi|perbaiki|gantikan|gantiin|update|pasang|set|sesuaikan)\b"
        ]
    ),
    # 2. DELETE KNOWLEDGE
    (
        QueryIntent.DELETE,
        [
            r"\b(hapus|delete|hilangkan|remove|buang|bersihkan|tiadakan|drop|clear|wipe|erase)\b"
        ]
    ),
    # 3. PRICE
    (
        QueryIntent.PRICE,
        [r"\bharga\b", r"\bberapa harga\b", r"\bbiaya\b", r"\bprice\b", r"\bharganya\b"]
    ),
    # 4. PRODUCT_NAME
    (
        QueryIntent.PRODUCT_NAME,
        [
            r"\bapa nama produk\b", r"\bnama produk\b", r"\bapa nama\b",
            r"\bfacial cleanser dari\b", r"\bcleanser dari\b", r"\bfacial wash dari\b",
            r"\bproduk pembersih\b", r"\bserum dari\b", r"\bmoisturizer dari\b",
            r"\bsebutkan nama produk\b"
        ]
    ),
    # 5. INGREDIENTS
    (
        QueryIntent.INGREDIENTS,
        [
            r"\bingredients?\b", r"\bkandungan\b", r"\bbahan aktif\b",
            r"\bkomposisi\b", r"\bformula\b", r"\bactive ingredients?\b",
            r"\bterbuat dari\b", r"\bmengandung apa\b"
        ]
    ),
    # 6. HOW_TO_USE / PROCEDURE / TAHAPAN TREATMENT
    (
        QueryIntent.HOW_TO_USE,
        [
            r"\bcara pakain?ya?\b", r"\bcara pengunaan\b", r"\baturan pakai\b",
            r"\bdosis\b", r"\bhow to use\b", r"\bdipakai kapan\b", r"\burutan pakai\b",
            r"\bcara menggunakannya\b", r"\bcara mengoleskan\b",
            r"\b(tahapan|tahapan treatment|tahapan tindakan|prosedur|prosedur tindakan|prosedur treatment|langkah[- ]langkah|protokol|step[- ]by[- ]step|alur tindakan|alur treatment)\b"
        ]
    ),
    # 7. WARNING / CONTRAINDICATION / PREGNANCY
    (
        QueryIntent.WARNING,
        [
            r"\baman untuk\b", r"\bibu hamil\b", r"\bbumil\b", r"\bmenyusui\b",
            r"\befek samping\b", r"\bkontraindikasi\b", r"\bahaya\b",
            r"\biritasi\b", r"\balergi\b", r"\bpantangan\b"
        ]
    ),
    # 8. COMPARISON
    (
        QueryIntent.COMPARISON,
        [
            r"\bperbedaan\b", r"\bbedanya\b", r"\bperbandingan\b",
            r"\bdibandingkan\b", r"\bvs\b", r"\bmana yang lebih\b"
        ]
    ),
    # 9. SUITABLE_FOR
    (
        QueryIntent.SUITABLE_FOR,
        [
            r"\bcocok untuk\b", r"\bdiperuntukkan\b", r"\bunduk kulit apa\b",
            r"\bjenis kulit\b", r"\bindikasi pasien\b", r"\bsuitable for\b"
        ]
    ),
    # 10. BENEFITS
    (
        QueryIntent.BENEFITS,
        [
            r"\bkeunggulan\b", r"\bkelebihan\b", r"\bbenefit\b", r"\badvantages\b"
        ]
    ),
    # 11. PRODUCT_FUNCTION
    (
        QueryIntent.PRODUCT_FUNCTION,
        [
            r"\bdigunakan untuk apa\b", r"\buntuk apa\b", r"\bfungsi\b",
            r"\bmanfaat\b", r"\bkegunaan\b", r"\bkhasiat\b", r"\bguna\b",
            r"\bberfungsi untuk\b"
        ]
    ),
    # 12. AVAILABILITY
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

        # Check if query is a multi-aspect query (asks for ingredients/function/usage AND price/warnings)
        aspect_indicators = [
            any(k in query_clean for k in ["kandungan", "ingredient", "komposisi", "bahan aktif"]),
            any(k in query_clean for k in ["indikasi", "fungsi", "manfaat", "kegunaan", "keunggulan"]),
            any(k in query_clean for k in ["cara pakai", "dosis", "aturan pakai"]),
            any(k in query_clean for k in ["harga", "biaya", "price"])
        ]
        aspect_count = sum(1 for a in aspect_indicators if a)
        if aspect_count >= 2:
            rules = QueryIntentDetector._get_rules_for_intent(QueryIntent.UNKNOWN)
            logger.debug(f"Multi-aspect query detected ({aspect_count} aspects) -> Using UNKNOWN/General rules to answer all requested aspects.")
            return QueryIntent.UNKNOWN, rules

        for intent, patterns in _INTENT_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, query_clean, re.IGNORECASE):
                    rules = QueryIntentDetector._get_rules_for_intent(intent)
                    logger.debug(f"Query intent detected: '{intent.value}' (matched pattern: '{pattern}')")
                    return intent, rules

        # Default fallback: UNKNOWN
        rules = QueryIntentDetector._get_rules_for_intent(QueryIntent.UNKNOWN)
        logger.debug(f"Query intent detected: '{QueryIntent.UNKNOWN.value}' (default)")
        return QueryIntent.UNKNOWN, rules

    @staticmethod
    def get_recommended_top_k(query: str, intent: QueryIntent, requested_top_k: int = 5) -> int:
        """
        Calculates dynamic top_k:
        - Greeting / Closing -> 1
        - Simple price/single product queries -> min(requested_top_k, 4)
        - All clinical queries, multi-condition, aftercare, cross-doc, or general queries -> max(requested_top_k, 9)
        """
        if intent == QueryIntent.GREETING:
            return 1
        elif intent in (QueryIntent.PRICE, QueryIntent.AVAILABILITY):
            return min(requested_top_k, 4) if requested_top_k > 4 else requested_top_k
        return max(requested_top_k, 9)

    @staticmethod
    def should_use_agent(query: str, intent: QueryIntent) -> bool:
        """
        Evaluates whether a query requires deep ReAct Agent multi-step tool reasoning:
        - Simple factual queries (greeting, closing, single product usage, ingredients, price) -> False (Use fast GenerationPipeline)
        - Complex multi-condition, comparison, multi-topic, or deep reasoning queries -> True (Use MedicalAgent)
        """
        if intent in (QueryIntent.GREETING, QueryIntent.CLOSING, QueryIntent.PRICE, QueryIntent.PRODUCT_NAME):
            return False

        query_lower = query.lower()
        complex_agent_indicators = [
            "bandingkan", "perbandingan", "bedanya", "vs", "kombinasi", 
            "kontraindikasi dan", "aman untuk", "sekaligus", "pisahkan",
            "buat analisis klinis", "urutkan", "tindakan dan produk",
            "treatment + produk", "treatment dan produk", "fase active", "fase post"
        ]

        words = query_lower.split()
        is_long_multi_topic = len(words) >= 12 and any(kw in query_lower for kw in ["dan", "serta", "tetapi", "namun", "untuk"])
        is_explicit_complex = any(ind in query_lower for ind in complex_agent_indicators)

        return is_explicit_complex or is_long_multi_topic

    @staticmethod
    def _get_rules_for_intent(intent: QueryIntent) -> Dict[str, Any]:
        """Returns length constraints and specific rules per intent."""
        if intent == QueryIntent.GREETING:
            return {
                "max_sentences": 2,
                "length_instruction": "Acknowledge the greeting warmly and politely in Indonesian, adjusted to the current time of day (Selamat pagi/siang/sore/malam). Offer assistance with ERHA products or treatments.",
                "missing_fallback": get_time_greeting_response()
            }
        elif intent == QueryIntent.CLOSING:
            return {
                "max_sentences": 1,
                "length_instruction": "Respond with a polite, brief acknowledgment/closing in Indonesian ('Sama-sama, Dok!' or 'Baik, Dok. Siap membantu jika ada pertanyaan lain.').",
                "missing_fallback": "Sama-sama, Dokter! Siap membantu kembali jika ada pertanyaan seputar protokol tindakan atau produk ERHA."
            }
        elif intent == QueryIntent.PRODUCT_NAME:
            return {
                "max_sentences": 1,
                "length_instruction": "Return ONLY the exact product name in 1 sentence. Do not add unsolicited product recommendations, clinical regimens, or usage instructions.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.INGREDIENTS:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY the relevant active ingredients in 1-2 sentences or a concise list. Do not add unsolicited product recommendations or clinical advice.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.PRODUCT_FUNCTION or intent == QueryIntent.BENEFITS:
            return {
                "max_sentences": 3,
                "length_instruction": "Return ONLY the primary product function/benefits in maximum 2-3 sentences. Do not add unsolicited clinical regimens, extra product recommendations, or disclaimers.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.HOW_TO_USE:
            return {
                "max_sentences": 6,
                "length_instruction": "Return ONLY the usage instructions, treatment steps, or clinical procedure in a clear step-by-step manner. Do not add extra product recommendations or clinical disclaimers.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.PRICE:
            return {
                "max_sentences": 3,
                "length_instruction": "Return the product price if found in context. If the query also asks about active ingredients or indications, summarize all requested details found in context.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.WARNING:
            return {
                "max_sentences": 3,
                "length_instruction": "Return ONLY safety warnings, contraindications, or pregnancy notes mentioned in context in maximum 2-3 sentences. Do not provide medical advice outside retrieved context.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.COMPARISON:
            return {
                "max_sentences": 4,
                "length_instruction": "Provide a concise comparison comparing ONLY the requested products using retrieved context. Do not mention any third product.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.SUITABLE_FOR:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY the target skin type / indication in 1-2 sentences.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        elif intent == QueryIntent.AVAILABILITY:
            return {
                "max_sentences": 2,
                "length_instruction": "Return ONLY product availability or branch availability mentioned in context.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
        else:
            return {
                "max_sentences": 3,
                "length_instruction": "Answer the question concisely in maximum 2-3 sentences using ONLY the retrieved context. Do not over-explain or provide unsolicited recommendations.",
                "missing_fallback": "Untuk saat ini informasi tersebut belum tersedia."
            }
