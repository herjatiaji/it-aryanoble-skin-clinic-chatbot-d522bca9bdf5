"""Guardrails Engine for Skin-Clinic-Chatbot.

Provides input validation (prompt injection, topicality) and output
post-processing (PII redaction, medical disclaimer) for the RAG chat pipeline.

Inspired by Open-Brain's multi-tenancy safety layer, adapted for medical domain.
All guards use lightweight regex + keyword matching — no external dependencies.
"""

import re
from typing import Dict, Any, Optional, Tuple
from loguru import logger

from app.rag.config import settings


# ── Prompt Injection Patterns ────────────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"(disregard|forget|override)\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompts?|rules?|guidelines?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
    re.compile(r"(act|behave|pretend|respond)\s+(as|like)\s+(a|an|if)\s+", re.IGNORECASE),
    re.compile(r"(system\s*prompt|system\s*message|internal\s*instructions?)", re.IGNORECASE),
    re.compile(r"(reveal|show|print|display|output)\s+(your|the|my)\s+(system|internal|hidden)\s+(prompt|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"(bypass|circumvent|disable)\s+(safety|filter|guard|restriction)", re.IGNORECASE),
]

# ── Off-topic keyword lists ──────────────────────────────────────────────────

_MEDICAL_DERMA_KEYWORDS: list[str] = [
    # Indonesian medical/skincare terms
    "kulit", "jerawat", "acne", "krim", "serum", "gel", "lotion", "cleanser",
    "sunscreen", "moisturizer", "pelembab", "tabir surya", "skincare", "skin care",
    "dermatologi", "dermatitis", "eksim", "eczema", "psoriasis", "rosacea",
    "hiperpigmentasi", "flek", "dark spot", "melasma", "brightening", "whitening",
    "anti aging", "antiaging", "kerutan", "wrinkle", "kolagen", "collagen",
    "retinol", "niacinamide", "salicylic", "benzoyl", "hyaluronic", "aha", "bha",
    "laser", "chemical peel", "microneedling", "botox", "filler", "mesotherapy",
    "erha", "arya noble", "klinik", "clinic", "dokter", "doctor", "resep",
    "produk", "product", "treatment", "tindakan", "perawatan", "facial",
    "komedo", "blackhead", "whitehead", "pori", "pore", "berminyak", "oily",
    "kering", "dry", "sensitif", "sensitive", "iritasi", "alergi", "allergy",
    "scar", "bekas", "luka", "wound", "inflamasi", "radang",
    "dosis", "kontraindikasi", "efek samping", "side effect", "indikasi",
    "bahan aktif", "active ingredient", "kandungan", "komposisi", "formula",
    "spf", "uva", "uvb", "vitamin c", "vitamin e", "zinc", "copper peptide",
    "hamil", "menyusui", "pregnant", "lactation", "anak", "bayi",
    "halo", "selamat pagi", "selamat siang", "selamat sore", "selamat malam",
    "hai", "hi", "hello", "terima kasih", "thanks", "thank you",
    "rekomendasi", "recommend", "saran", "suggest", "cara pakai", "how to use",
    "apa", "bagaimana", "kenapa", "kapan", "dimana", "berapa",
    "jadwal", "cabang", "branch", "promo", "diskon", "harga",
]

_OFFTOPIC_KEYWORDS: list[str] = [
    "coding", "programming", "javascript", "python", "react", "database",
    "website", "software", "hardware", "laptop", "komputer", "computer",
    "politik", "political", "election", "pemilu", "presiden", "partai",
    "saham", "stock", "crypto", "bitcoin", "forex", "trading",
    "sepak bola", "football", "basketball", "liga", "pertandingan",
    "resep masakan", "recipe", "cooking", "masak",
    "lirik lagu", "lyrics", "download film", "streaming",
]

# ── PII Patterns ─────────────────────────────────────────────────────────────

_PII_PATTERNS: list[Tuple[re.Pattern, str]] = [
    # Indonesian phone numbers (08xx-xxxx-xxxx variations)
    (re.compile(r"\b0[87]\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"), "[NOMOR_HP_TERSEMBUNYI]"),
    # +62 phone numbers
    (re.compile(r"\+62[-.\s]?\d{2,3}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"), "[NOMOR_HP_TERSEMBUNYI]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL_TERSEMBUNYI]"),
    # NIK (16-digit Indonesian national ID)
    (re.compile(r"\b\d{16}\b"), "[NIK_TERSEMBUNYI]"),
    # "Pasien: Name" or "atas nama Name" patterns
    (re.compile(r"(?:Pasien|Patient|atas nama|a\.n\.)\s*[:]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"), "[NAMA_PASIEN_TERSEMBUNYI]"),
]

# ── Medical disclaimer keywords ─────────────────────────────────────────────

_PRESCRIPTIVE_KEYWORDS: list[str] = [
    "dosis", "dosage", "resep", "prescription", "diagnosis",
    "pengobatan", "terapi", "therapy", "obat", "medication",
    "injeksi", "injection", "operasi", "surgery", "prosedur medis",
]

_MEDICAL_DISCLAIMER = (
    "\n\n---\n"
    "⚕️ *Catatan: Informasi di atas merupakan panduan umum berdasarkan knowledge base ERHA. "
    "Keputusan klinis akhir tetap berada pada dokter yang menangani pasien secara langsung.*"
)


class InputGuard:
    """Pre-retrieval guard: validates user input before processing."""

    @staticmethod
    def check_prompt_injection(query: str) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_safe, rejection_message).
        is_safe=True means the query is OK to proceed.
        """
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(query):
                logger.warning(f"Prompt injection detected in query: {query[:100]}...")
                return False, (
                    "Maaf, permintaan Anda tidak dapat diproses karena terdeteksi "
                    "sebagai instruksi yang tidak sesuai dengan kebijakan keamanan sistem."
                )
        return True, None

    @staticmethod
    def check_topicality(query: str) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_on_topic, rejection_message).
        Uses keyword matching — medical/skincare keywords indicate on-topic.
        """
        if not settings.guardrails_block_offtopic:
            return True, None

        query_lower = query.lower()

        # Short queries or greetings are always allowed
        if len(query_lower.split()) <= 3:
            return True, None

        # Check if clearly off-topic
        offtopic_score = sum(1 for kw in _OFFTOPIC_KEYWORDS if kw in query_lower)
        medical_score = sum(1 for kw in _MEDICAL_DERMA_KEYWORDS if kw in query_lower)

        if offtopic_score >= 2 and medical_score == 0:
            logger.info(f"Off-topic query blocked: {query[:100]}... (offtopic={offtopic_score}, medical={medical_score})")
            return False, (
                "Maaf, saya adalah CHAT AI ERHA yang dirancang khusus untuk membantu "
                "pertanyaan seputar produk perawatan kulit, tindakan klinis estetika, "
                "dan layanan ERHA Klinik. Silakan ajukan pertanyaan terkait dermatologi "
                "atau produk ERHA."
            )

        return True, None

    @classmethod
    def validate(cls, query: str) -> Tuple[bool, Optional[str]]:
        """
        Runs all input guards. Returns (is_valid, rejection_message).
        """
        # 1. Prompt injection check
        is_safe, msg = cls.check_prompt_injection(query)
        if not is_safe:
            return False, msg

        # 2. Topicality check
        is_on_topic, msg = cls.check_topicality(query)
        if not is_on_topic:
            return False, msg

        return True, None


class OutputGuard:
    """Post-generation guard: sanitizes LLM output before returning to user."""

    @staticmethod
    def redact_pii(text: str) -> str:
        """Masks PII patterns (phone numbers, emails, NIK, patient names)."""
        if not settings.guardrails_redact_pii:
            return text

        redacted = text
        for pattern, replacement in _PII_PATTERNS:
            redacted = pattern.sub(replacement, redacted)

        return redacted

    @staticmethod
    def add_medical_disclaimer(text: str) -> str:
        """Appends a medical disclaimer if the answer contains prescriptive advice."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in _PRESCRIPTIVE_KEYWORDS):
            # Only add if not already present
            if "Keputusan klinis akhir" not in text:
                return text + _MEDICAL_DISCLAIMER
        return text

    @classmethod
    def process(cls, answer: str) -> str:
        """Runs all output guards on the generated answer (PII redaction)."""
        result = cls.redact_pii(answer)
        return result



class GuardrailsPipeline:
    """Orchestrator that wraps input validation and output processing."""

    @staticmethod
    def validate_input(query: str) -> Tuple[bool, Optional[str]]:
        """
        Validates user input. Returns (is_valid, rejection_message).
        If guardrails are disabled globally, always returns True.
        """
        if not settings.guardrails_enabled:
            return True, None
        return InputGuard.validate(query)

    @staticmethod
    def process_output(answer: str) -> str:
        """
        Post-processes LLM output. Returns sanitized answer.
        If guardrails are disabled globally, returns answer unchanged.
        """
        if not settings.guardrails_enabled:
            return answer
        return OutputGuard.process(answer)
