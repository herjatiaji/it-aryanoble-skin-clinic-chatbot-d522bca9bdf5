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

# ── Prompt Injection Patterns with Weights ─────────────────────────────────────

# Stage 1: Weighted patterns. High severity patterns carry 0.5 - 0.6 weight.
# Medium/contextual patterns carry 0.25 - 0.35 weight.
# Stage 2: Compared against settings.prompt_injection_confidence_threshold (default: 0.7).
_INJECTION_PATTERNS: list[Tuple[re.Pattern, float, str]] = [
    # High-severity explicit instructions override & jailbreak (0.5 - 0.6)
    (
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
        0.5,
        "ignore_previous_instructions"
    ),
    (
        re.compile(r"(disregard|forget|override)\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompts?|rules?|guidelines?)", re.IGNORECASE),
        0.5,
        "override_instructions"
    ),
    (
        re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
        0.6,
        "dan_mode"
    ),
    (
        re.compile(r"\bjailbreak\b", re.IGNORECASE),
        0.6,
        "jailbreak"
    ),
    (
        re.compile(r"(bypass|circumvent|disable)\s+(safety|filter|guard|restriction|policy)", re.IGNORECASE),
        0.5,
        "bypass_safety"
    ),
    (
        re.compile(r"(reveal|show|print|display|output)\s+(your|the|my)\s+(system|internal|hidden)\s+(prompt|instructions?|rules?)", re.IGNORECASE),
        0.5,
        "reveal_system_prompt"
    ),
    (
        re.compile(r"\b(developer\s*mode|god\s*mode|unrestricted\s*mode)\b", re.IGNORECASE),
        0.5,
        "unrestricted_mode"
    ),
    # Contextual / Medium patterns (0.25 - 0.35)
    (
        re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
        0.3,
        "persona_override"
    ),
    (
        re.compile(r"(act|behave|pretend|respond)\s+(as|like)\s+(a|an|if)\s+", re.IGNORECASE),
        0.25,
        "roleplay_prompt"
    ),
    (
        re.compile(r"\b(system\s*prompt|system\s*message|internal\s*instructions?)\b", re.IGNORECASE),
        0.3,
        "system_prompt_mention"
    ),
    (
        re.compile(r"\b(base64|rot13|hex)\s+(decode|eval)\b", re.IGNORECASE),
        0.35,
        "obfuscation_decode"
    ),
]

# ── Indonesian Stemming / Root Candidates Helper ─────────────────────────────

_ID_PREFIXES = ("meng", "meny", "mem", "men", "me", "peng", "peny", "pem", "pen", "pe", "per", "ber", "ter", "di", "ke", "se")
_ID_SUFFIXES = ("nya", "kan", "lah", "kah", "pun", "an", "i")


def _stem_indonesian_word(word: str) -> set[str]:
    """Generates candidate root forms for an Indonesian word by stripping common affixes."""
    candidates = {word}
    stem = word
    # Suffix stripping
    for sfx in _ID_SUFFIXES:
        if stem.endswith(sfx) and len(stem) - len(sfx) >= 3:
            stem = stem[:-len(sfx)]
            candidates.add(stem)
            break

    # Prefix stripping on original word and suffix-stripped stem
    for base in list(candidates):
        for pfx in _ID_PREFIXES:
            if base.startswith(pfx) and len(base) - len(pfx) >= 3:
                remainder = base[len(pfx):]
                candidates.add(remainder)
                # handle nasal sound replacements in Indonesian morphology
                if pfx == "meny":
                    candidates.add("s" + remainder)
                elif pfx == "mem":
                    candidates.add("p" + remainder)
                elif pfx == "men":
                    candidates.add("t" + remainder)
                elif pfx == "meng":
                    candidates.add("k" + remainder)
                elif pfx == "peny":
                    candidates.add("s" + remainder)
                elif pfx == "pem":
                    candidates.add("p" + remainder)
                elif pfx == "pen":
                    candidates.add("t" + remainder)
                elif pfx == "peng":
                    candidates.add("k" + remainder)
    return candidates


# ── Whitelist & Blacklist Definitions (Topicality Gate) ───────────────────────

_WHITELIST_PHRASES: list[str] = [
    # Dermatology conditions & anatomy
    "dark spot", "skin care", "skincare", "anti aging", "anti-aging", "chemical peel",
    "stretch mark", "bekas luka", "luka bakar", "kulit sensitif", "kulit berminyak",
    "kulit kering", "kulit kombinasi", "flek hitam", "garis halus", "pori-pori",
    "pori pori", "jerawat aktif", "jerawat batu", "jerawat meradang", "infeksi kulit",
    "rambut rontok", "kebotakan dini", "kulit kusam",
    # Ingredients
    "salicylic acid", "asam salisilat", "glycolic acid", "asam glikolat",
    "lactic acid", "asam laktat", "azelaic acid", "asam azelat", "hyaluronic acid",
    "asam hialuronat", "alpha arbutin", "tranexamic acid", "asam traneksamat",
    "vitamin c", "vitamin e", "vitamin a", "benzoyl peroxide", "copper peptide",
    "zinc oxide", "titanium dioxide", "aloe vera", "centella asiatica",
    # Formulations & procedures
    "facial wash", "face wash", "sun screen", "sun block", "day cream",
    "night cream", "eye cream", "body lotion", "micellar water",
    "thread lift", "tarik benang", "co2 fractional", "dermal filler",
    "platelet rich plasma", "comedo extraction", "ekstraksi komedo",
    "suntik jerawat", "injeksi jerawat", "infus whitening", "uji klinis",
    # ERHA brand, clinic operations & services
    "erha derma center", "erha clinic", "erha skin", "erha apotheke",
    "arya noble", "erha buddy", "erha connect", "jam buka", "jam operasional",
    "hari praktek", "hari praktik", "jadwal praktek", "jadwal praktik",
    "janji temu", "rekam medis", "biaya tindakan", "biaya perawatan",
    "efek samping", "side effect", "bahan aktif", "active ingredient",
    "aturan pakai", "cara pakai", "how to use", "interaksi obat",
    # Clinical consultation & treatment recommendation phrases
    "rekomendasi produk", "rekomendasi treatment", "rekomendasi tindakan",
    "rekomendasi skincare", "rekomendasi dokter", "rekomendasi obat",
    "rekomendasi perawatan", "rekomendasi krim", "resep dokter",
    "ruam merah", "bercak merah",
]

_WHITELIST_KEYWORDS: set[str] = {
    # Skin & anatomy
    "kulit", "skin", "derma", "dermatologi", "dermatologis", "epidermis", "dermis",
    "wajah", "muka", "face", "facial", "badan", "body", "leher", "mata", "bibir",
    "rambut", "hair", "kepala", "scalp", "ketombe", "dandruff", "alis", "bulumata",
    "kuku", "nail", "pori", "pore", "sebum", "minyak", "kering", "sensitif",
    
    # Conditions & lesions
    "jerawat", "acne", "komedo", "blackhead", "whitehead", "bruntus", "bruntusan",
    "flek", "melasma", "hiperpigmentasi", "pigmen", "pigmentasi", "eritema", "kemerahan",
    "radang", "inflamasi", "eksim", "eczema", "dermatitis", "psoriasis",
    "rosacea", "urtikaria", "biduran", "alergi", "allergy", "iritasi", "gatal",
    "pruritus", "keloid", "scar", "bopeng", "luka", "kerut", "kerutan", "wrinkle",
    "aging", "penuaan", "kendur", "sagging", "selulit", "kutil", "wart", "milia",
    "tinea", "jamur", "fungal", "panau", "kadas", "kurap", "herpes", "alopecia",
    "rontok", "botak", "kebotakan", "kusam", "cerah", "putih", "glow", "glowing",

    # Active ingredients & substances
    "retinol", "retinoid", "isotretinoin", "tretinoin", "adapalene", "niacinamide",
    "salicylic", "glycolic", "lactic", "azelaic", "mandelic", "hyaluronic", "aha",
    "bha", "pha", "lha", "ascorbic", "ceramide", "peptide", "peptida", "zinc",
    "hidrokuinon", "hydroquinone", "tranexamic", "arbutin", "kojic", "glutation",
    "glutathione", "cica", "centella", "panthenol", "allantoin", "spf", "uva", "uvb",
    "sunscreen", "sunblock", "tabir", "surya", "antioksidan", "kolagen", "collagen",
    "clindamycin", "erythromycin", "mupirocin", "gentamicin", "ketoconazole",
    "corticosteroid", "kortikosteroid", "hidrokortison", "betamethasone",

    # Products & preparations
    "krim", "cream", "serum", "gel", "lotion", "cleanser", "toner", "essence",
    "ampoule", "moisturizer", "pelembab", "scrub", "masker", "mask", "sabun",
    "soap", "salep", "ointment", "balm", "bedak", "powder", "cushion", "mist",
    "emulsi", "emulsion", "kapsul", "capsule", "tablet", "pil", "suplemen",
    "produk", "product", "sku", "kemasan", "botol", "sachet", "tube", "jar",

    # Treatments & clinical procedures
    "treatment", "tindakan", "perawatan", "terapi", "therapy", "prosedur",
    "laser", "vbeam", "pico", "picoway", "picosure", "ipl", "peel", "peeling",
    "micropeel", "microneedling", "dermapen", "prp", "botox", "botulinum",
    "filler", "mesotherapy", "meso", "cauter", "kauter", "elektrokauter",
    "subsisi", "subcision", "dermabrasi", "microdermabrasion", "hydrafacial",
    "injeksi", "injection", "suntik", "infus", "phototherapy", "fototerapi",
    "rf", "radiofrequency", "hifu", "cauterisasi",

    # Clinic, doctors, administration & services
    "erha", "arya", "noble", "klinik", "clinic", "dokter", "dok", "doctor", "dr",
    "spkk", "spdve", "dermatologist", "resepsionis", "perawat", "nurse", "apoteker",
    "pharmacist", "apotek", "apotheke", "konsultasi", "telekonsultasi", "appointment",
    "janji", "booking", "reservasi", "daftar", "pendaftaran", "registrasi",
    "antre", "antrean", "poli", "cabang", "branch", "outlet", "lokasi", "alamat",
    "jadwal", "praktek", "praktik", "buka", "operasional", "harga", "tarif", "biaya",
    "cost", "price", "bayar", "pembayaran", "asuransi", "klaim", "promo", "promosi",
    "diskon", "discount", "voucher", "paket", "package", "member", "membership",
    "poin", "kebijakan", "policy", "syarat", "ketentuan", "layanan", "service",

    # Clinical pharmacology & safety
    "resep", "preskripsi", "racik", "racikan", "etiket", "sediaan", "dosis",
    "dosage", "frekuensi", "indikasi", "kontraindikasi", "efek", "samping",
    "toksisitas", "alergi", "hipersensitif", "interaksi", "obat", "keamanan",
    "safety", "uji", "klinis", "bpom", "batch", "expired", "kedaluwarsa",
    "simpan", "penyimpanan", "kulkas", "hamil", "bumil", "kehamilan", "pregnancy",
    "menyusui", "busui", "laktasi", "lactation", "anak", "bayi", "pediatrik",
    "dewasa", "lansia", "geriatrik", "formula",

    # General conversational, discussion & interactive terms
    "halo", "hi", "pagi", "siang", "sore", "malam", "terima", "kasih", "thanks", "thank", "you",
    "jelaskan", "bagaimana", "bagaimanakah", "apakah", "mengapa", "kenapa", "rekomendasi", "saran",
    "diskusi", "pendapat", "perbedaan", "beda", "mana", "cocok", "sesuai", "bantu", "bisa", "tolong",
    "mohon", "info", "informasi", "detail", "penjelasan", "opsi", "pilihan", "tanya", "bertanya",
}

# Secondary Check Blacklist (used strictly to generate specific explanatory rejection messages)
_OFFTOPIC_KEYWORDS: list[str] = [
    # Programming & Tech (coding)
    "coding", "koding", "programming", "programing", "javascript", "python", "typescript", "c++", "golang",
    "html", "css", "sql", "react", "database", "software", "hardware", "laptop",
    "komputer", "computer", "source code", "github", "bug fixing", "debug",
    
    # Financial, Crypto & Stocks (saham, crypto)
    "saham", "crypto", "kripto", "bitcoin", "ethereum", "forex", "trading", "investasi saham",
    "reksadana", "pasar modal", "ihsg", "dividend", "investasi", "mata uang kripto",
    
    # Politics & Governance (politik)
    "politik", "political", "election", "pemilu", "pilpres", "pilkada", "presiden",
    "menteri", "partai politik", "partai", "dpr", "kpu", "kampanye", "calon presiden",
    
    # Sports
    "sepak bola", "football", "basketball", "liga inggris", "champions league",
    "piala dunia", "badminton", "skor pertandingan",
    
    # Culinary / Recipes (masak)
    "masak", "memasak", "masakan", "resep masakan", "resep makanan", "cara memasak", "cara masak",
    "bumbu dapur", "bumbu", "kue", "bolu", "kuliner",
    
    # Entertainment
    "lirik lagu", "lyrics", "chord gitar", "download film", "streaming bioskop", "nonton film",
]

_OFFTOPIC_SPECIFIC_MSG = (
    "Maaf Dok, pertanyaan Anda terdeteksi berada di luar lingkup layanan klinik dan dermatologi medis ERHA "
    "(teridentifikasi topik non-medis seperti teknologi/pemrograman, finansial/investasi, politik, hiburan, atau masakan). "
    "Mohon ajukan pertanyaan terkait produk, kondisi dermatologi, tindakan estetika, atau operasional klinik ERHA."
)

_OFFTOPIC_GENERIC_MSG = (
    "Maaf Dok, saya adalah ERHA Medical Assistant yang dirancang khusus untuk mendukung Dokter "
    "mencari informasi produk perawatan kulit, tindakan klinis estetika, "
    "dan knowledge base ERHA. Silakan ajukan pertanyaan terkait produk atau klinis ERHA."
)

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
        Two-stage prompt injection detection with weighted confidence scoring:
        - Stage 1: Matches patterns and calculates an aggregate suspicion score (0.0 to 1.0).
        - Stage 2: Evaluates against configurable threshold (PROMPT_INJECTION_CONFIDENCE_THRESHOLD, default 0.7).
          - score >= threshold: Blocked (is_safe=False).
          - 0.0 < score < threshold: Allowed (is_safe=True), but logged as 'flagged_low_confidence' for monitoring.
          - score == 0.0: Safe query.
        """
        threshold = float(getattr(settings, "prompt_injection_confidence_threshold", 0.7))
        matched_patterns: list[str] = []
        score = 0.0

        for pattern, weight, label in _INJECTION_PATTERNS:
            if pattern.search(query):
                score += weight
                matched_patterns.append(f"{label}({weight:.2f})")

        total_score = min(1.0, score)

        if total_score >= threshold:
            logger.warning(
                f"🚨 [PROMPT_INJECTION_BLOCKED] Score {total_score:.2f} >= threshold {threshold:.2f} "
                f"in query: {query[:100]}... Matches: {matched_patterns}"
            )
            return False, (
                "Maaf Dok, permintaan Anda tidak dapat diproses karena terdeteksi "
                "sebagai instruksi yang tidak sesuai dengan kebijakan keamanan sistem."
            )
        elif total_score > 0.0:
            # Stage 2 monitoring: Moderate or single contextual pattern matched, but below threshold.
            # Allowed to proceed to prevent false positives, logged for audit & calibration.
            logger.info(
                f"⚠️ [PROMPT_INJECTION_AUDIT: flagged_low_confidence] Score {total_score:.2f} < threshold {threshold:.2f} "
                f"for query: {query[:100]}... Matches: {matched_patterns}. Allowed to proceed."
            )

        return True, None

    @classmethod
    def matches_whitelist(cls, query: str) -> Tuple[bool, list[str]]:
        """
        Evaluates whether the query belongs to the ERHA medical/clinic domain using:
        1. Multi-word phrase matching
        2. Word token and Indonesian stem/root matching
        Returns (is_matched, matched_terms).
        """
        query_lower = query.lower()
        matched: list[str] = []

        # 1. Multi-word phrase matching
        for phrase in _WHITELIST_PHRASES:
            if phrase in query_lower:
                matched.append(phrase)

        # 2. Tokenize words (letters and numbers only)
        tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", query_lower)

        for token in tokens:
            # Disambiguation for Indonesian homonyms: 'resep' in culinary context ('resep masakan', 'resep kue') is not medical
            if token == "resep" and re.search(r"\bresep\s+(?:masak|masakan|kue|makanan|minuman|kuliner|baking)\b", query_lower):
                continue

            if token in _WHITELIST_KEYWORDS:
                matched.append(token)
                continue
            
            # 3. Indonesian stemming candidates
            stems = _stem_indonesian_word(token)
            for stem in stems:
                if stem == "resep" and re.search(r"\bresep\s+(?:masak|masakan|kue|makanan|minuman|kuliner|baking)\b", query_lower):
                    continue
                if stem in _WHITELIST_KEYWORDS:
                    matched.append(f"{token}->{stem}")
                    break

        return (len(matched) > 0), matched

    @classmethod
    def matches_blacklist(cls, query: str) -> Tuple[bool, list[str]]:
        """
        Evaluates whether the query explicitly contains off-topic keywords using word boundaries.
        Returns (is_matched, matched_terms).
        """
        query_lower = query.lower()
        matched: list[str] = []
        for kw in _OFFTOPIC_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", query_lower):
                matched.append(kw)
        return (len(matched) > 0), matched

    @classmethod
    def check_topicality(cls, query: str) -> Tuple[bool, Optional[str]]:
        """
        Whitelist-First Topicality Gate:
        1. Primary Check: Evaluates query against clinical/ERHA Whitelist (semantic & stem-based).
           If query matches Whitelist -> immediately allowed (proceeds to retrieval).
        2. Secondary Check: Evaluates non-whitelisted query against Blacklist for explanatory feedback.
           - If matches Blacklist -> rejected with specific off-topic message.
           - If does NOT match Blacklist -> rejected with generic off-topic message.
        """
        if not settings.guardrails_block_offtopic:
            return True, None

        # Intent detection for greeting & closing shortcut
        try:
            from app.rag.services.intent import QueryIntentDetector, QueryIntent
            intent, _ = QueryIntentDetector.detect(query)
            if intent in (QueryIntent.GREETING, QueryIntent.CLOSING):
                return True, None
        except Exception:
            pass

        # 1. Evaluate Whitelist Match
        is_whitelisted, matched_whitelist = cls.matches_whitelist(query)

        # 2. Evaluate Blacklist Match (explicit non-medical keywords: coding, crypto, saham, politik, masak)
        is_blacklisted, matched_blacklist = cls.matches_blacklist(query)

        if is_blacklisted:
            # If query has strong clinical/medical matches (not just generic transactional words like 'harga'/'biaya'),
            # allow legitimate clinical queries with incidental technical words (e.g. 'rekam medis pasien di database website ERHA')
            _GENERIC_TRANSACTIONAL = {"harga", "tarif", "biaya", "cost", "price", "bayar", "pembayaran"}
            strong_clinical_matches = [
                m for m in matched_whitelist 
                if m.split("->")[-1] not in _GENERIC_TRANSACTIONAL
            ]
            if not strong_clinical_matches:
                logger.info(f"Topicality Gate REJECTED (Specific off-topic blacklist match: {matched_blacklist}) query='{query[:80]}'")
                return False, _OFFTOPIC_SPECIFIC_MSG

        # 3. Whitelist check passed
        if is_whitelisted:
            logger.info(f"Topicality Gate PASSED via Whitelist: matches={matched_whitelist[:5]} query='{query[:80]}'")
            return True, None

        if is_blacklisted:
            logger.info(f"Topicality Gate REJECTED (Specific off-topic blacklist match: {matched_blacklist}) query='{query[:80]}'")
            return False, _OFFTOPIC_SPECIFIC_MSG

        # 4. Query neither whitelisted nor blacklisted -> Generic Rejection
        logger.info(f"Topicality Gate REJECTED (Generic off-topic, no clinical match) query='{query[:80]}'")
        return False, _OFFTOPIC_GENERIC_MSG

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


# ── Patient-facing consultation disclaimer removal patterns ──────────────────
_PATIENT_DISCLAIMER_PATTERNS: list[re.Pattern] = [
    re.compile(r"[\r\n\s]*(?:Sebelum\s+(?:memulai|menggunakan|melakukan)[^\.\n\?!]*,?\s*)?(?:Pastikan|Harap|Mohon|Disarankan|Sebaiknya|Silakan|Jangan lupa)?\s*(?:untuk\s+)?(?:selalu\s+)?(?:melakukan\s+)?(?:ber)?konsultasi(?:\s+lebih\s+lanjut)?(?:\s+terlebih\s+dahulu)?\s*(?:dengan|kepada|ke)?\s*(?:dokter|tenaga medis|ahli dermatologi|profesional medis)?[^\.\n\?!]*(?:sebelum\s+(?:memulai|melakukan|menggunakan)[^\.\n\?!]*)?[\.\!\?]", re.IGNORECASE),
    re.compile(r"[\r\n\s]*(?:Sebelum\s+(?:memulai|menggunakan|melakukan)[^\.\n\?!]*,?\s*(?:pastikan|disarankan|harap|silakan|mohon|sebaiknya)?\s*(?:untuk\s+)?(?:ber)?konsultasi[^\.\n\?!]*[\.\!\?])", re.IGNORECASE),
    re.compile(r"[\r\n\s]*\*?Catatan:\s*Informasi di atas merupakan panduan umum[^\n]*\*?", re.IGNORECASE),
    re.compile(r"[\r\n\s]*(?:Jika\s+(?:ada|terdapat)\s+pertanyaan\s+(?:lebih\s+lanjut|tambahan|lainnya?)|Jika\s+Dokter\s+(?:membutuhkan|memerlukan)\s+(?:informasi|bantuan)\s+(?:lebih\s+lanjut|tambahan))[^\.\n\?!]*,\s*(?:silakan|harap|mohon)?\s*(?:beri\s+tahu|tanyakan|sampaikan|hubungi)[^\.\n\?!]*[\.\!\?]?", re.IGNORECASE),
    re.compile(r"[\r\n\s]*(?:jika\s+[^\.\n\?!]*?(?:pemesanan|order|pembelian)[^\.\n\?!]*[\.\!\?]?)", re.IGNORECASE),
    re.compile(r"[\r\n\s]*(?:(?:jika\s+ingin|untuk)\s+[^\.\n\?!]*?(?:pemesanan|order|pembelian)[^\.\n\?!]*[\.\!\?]?)", re.IGNORECASE),
    re.compile(r"[\r\n\s]*[^\.\n\?!]*?(?:silakan|silahkan)\s+beri\s+tahu\s+saya[^\.\n\?!]*[\.\!\?]?", re.IGNORECASE),
]


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
    def strip_patient_disclaimers(text: str) -> str:
        """
        Removes generic patient-facing disclaimers or warnings (e.g. 'konsultasi lebih lanjut')
        since the user is already a practicing Doctor.
        """
        cleaned = text
        for pattern in _PATIENT_DISCLAIMER_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

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
    def format_clinical_tone(cls, text: str) -> str:
        """Fixes robotic phrasing, strips dummy placeholders, translates raw taxonomy terms, and cleans formatting."""
        if not text:
            return text

        # 1. Translate internal database taxonomy / snake_case terms to humanized Indonesian clinical terms
        taxonomy_map = {
            r'\bacne_vulgaris\b': 'Jerawat (Acne Vulgaris)',
            r'\bcomedones\b': 'Komedo',
            r'\bacne_scar\b': 'Bekas Jerawat (Acne Scar)',
            r'\bsebum_oily\b': 'Kulit Berminyak',
            r'\benlarged_pores\b': 'Pori-Pori Besar',
            r'\bsensitive_barrier\b': 'Kulit Sensitif',
            r'\baging_wrinkles\b': 'Penuaan & Kerutan',
            r'\bdull_skin\b': 'Kulit Kusam',
        }
        for pattern, replacement in taxonomy_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # 2. Strip dummy placeholder lines like "- **Brand**: ...", "- **Harga**: ...", "- **Durasi**: ..."
        text = re.sub(r'^[|\-\*]?\s*\*\*[^\*\n]+\*\*\s*:\s*(?:\.\.\.|\-|null|none|undefined|n/a)\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

        # 3. Replace stiff robotic backend phrases with warm, natural clinical phrasing
        text = re.sub(r'(?i)\bproduk yang tercantum adalah\b', 'rekomendasi produk yang cocok adalah', text)
        text = re.sub(r'(?i)\bperawatan yang tercantum adalah\b', 'rekomendasi perawatan yang cocok adalah', text)
        text = re.sub(r'(?i)\bdokumen yang tercantum adalah\b', 'rekomendasi yang sesuai adalah', text)
        
        # 4. Ensure bullet points '- **' are always on a separate new line
        text = re.sub(r'([^\n])\s+-\s+\*\*', r'\1\n- **', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    @classmethod
    def process(cls, answer: str) -> str:
        """Runs all output guards on the generated answer (PII redaction & disclaimer stripping)."""
        result = cls.redact_pii(answer)
        result = cls.strip_patient_disclaimers(result)
        result = cls.format_clinical_tone(result)
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
