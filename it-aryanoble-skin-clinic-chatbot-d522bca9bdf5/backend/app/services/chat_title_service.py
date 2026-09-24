import re
import uuid
from typing import Optional
from loguru import logger
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.chat import ChatSession, ChatMessage, ChatRole


def clean_heuristic_title(text: Optional[str], max_words: int = 6, max_len: int = 45) -> str:
    """
    Fast rule-based title extractor (fallback like ChatGPT's instant title preview).
    Extracts key topic, removes conversational filler, and formats as Title Case.
    """
    if not text or not text.strip():
        return "Percakapan Baru"

    s = text.strip()
    # 1. Remove markdown links, images, bold/italics
    s = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)
    s = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', s)
    s = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', s)

    # Key-value pattern (Brand: ... Kategori: ...)
    brand_match = re.search(r'(?:^|\n)\s*[-*•]?\s*Brand\s*:\s*([^\n\r]+)', s, re.IGNORECASE)
    cat_match = re.search(r'(?:^|\n)\s*[-*•]?\s*Kategori\s*:\s*([^\n\r]+)', s, re.IGNORECASE)
    if brand_match:
        b_val = brand_match.group(1).strip()
        c_val = cat_match.group(1).strip() if cat_match else ""
        res = f"{b_val} {c_val}".strip()
        return res[:max_len].title()

    # First meaningful line
    lines = [l.strip() for l in s.splitlines() if l.strip()]
    first_line = lines[0] if lines else s
    first_line = re.sub(r'^[#>\s*\-+•\d\.]+', '', first_line).strip()

    # Remove common conversational filler words
    filler_patterns = [
        r'^(halo|hai|selamat\s+(pagi|siang|sore|malam)|permisi|assalamualaikum)\b[,!\s]*',
        r'^(tolong|mohon|bisa\s+bantu|bisa\s+tolong|saya\s+mau\s+tanya|mau\s+tanya|apakah\s+bisa|apakah\s+ada|bagaimana\s+cara)\b[,!\s]*',
        r'^(dok|dokter|admin|kak|min)\b[,!\s]*',
    ]
    for pat in filler_patterns:
        first_line = re.sub(pat, '', first_line, flags=re.IGNORECASE).strip()

    first_line = re.sub(r'\s+', ' ', first_line).strip()

    # Words limit
    words = first_line.split()
    if len(words) > max_words:
        first_line = " ".join(words[:max_words])

    if len(first_line) > max_len:
        first_line = first_line[:max_len].rsplit(' ', 1)[0]

    return first_line.strip().title() or "Percakapan Baru"


def sanitize_llm_title(raw_title: str, max_len: int = 50) -> str:
    """Sanitizes raw LLM output into a clean, concise title."""
    if not raw_title:
        return "Percakapan Baru"

    t = raw_title.strip()
    # Strip markdown bold/italics
    t = re.sub(r'[*_`]', '', t)
    # Strip quotes
    t = t.strip('"\'“”‘’')
    # Strip prefixes like "Judul:", "Title:", "Judul Singkat:"
    t = re.sub(r'^(Judul\s*(Singkat)?|Title|Topik)\s*:\s*', '', t, flags=re.IGNORECASE)
    # Strip trailing punctuation
    t = t.rstrip('.!?,-:; ')
    # Collapse spaces
    t = re.sub(r'\s+', ' ', t).strip()

    if len(t) > max_len:
        t = t[:max_len].rsplit(' ', 1)[0]

    return t or "Percakapan Baru"


async def generate_and_save_chat_title(
    session_id: uuid.UUID,
    user_query: Optional[str] = None,
    ai_response: Optional[str] = None,
    force: bool = False
) -> str:
    """
    Generates an LLM-powered conversation title (like Gemini & ChatGPT: 3-6 words,
    Title Case, topic-focused, no markdown/quotes) and persists it in ChatSession.summary.
    """
    try:
        from app.rag.services.factory import AdapterFactory
    except ImportError:
        AdapterFactory = None

    async with AsyncSessionLocal() as db:
        stmt = select(ChatSession).where(ChatSession.id == session_id)
        res = await db.execute(stmt)
        session = res.scalar_one_or_none()
        if not session:
            return "Percakapan Baru"

        # If session already has a good summary/title and not forced, return it
        if session.summary and not force:
            return session.summary

        # If user_query or ai_response not provided, fetch from messages
        if not user_query:
            stmt_msgs = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .limit(4)
            )
            msg_res = await db.execute(stmt_msgs)
            all_msgs = msg_res.scalars().all()

            for m in all_msgs:
                if m.role == ChatRole.USER and not user_query:
                    user_query = m.content
                elif m.role == ChatRole.ASSISTANT and not ai_response:
                    ai_response = m.content

        # Fallback to heuristic immediately if no messages at all
        if not user_query and not ai_response:
            title = "Percakapan Baru"
            session.summary = title
            db.add(session)
            await db.commit()
            return title

        # Fast heuristic preview
        fallback_title = clean_heuristic_title(user_query or ai_response)

        # Try LLM title generation
        if AdapterFactory:
            try:
                llm = await AdapterFactory.get_dynamic_llm(db)
                prompt = (
                    "Anda adalah asisten pembuat judul percakapan seperti pada ChatGPT dan Google Gemini.\n"
                    "Buatlah judul percakapan yang padat, ringkas, dan sangat relevan untuk obrolan berikut.\n\n"
                    "Ketentuan format judul:\n"
                    "1. Panjang judul: 3 sampai 6 kata (maksimal 45 karakter).\n"
                    "2. Bahasa: Bahasa Indonesia, gunakan Title Case.\n"
                    "3. DILARANG menggunakan tanda petik/kutip, tanda titik di akhir, awalan 'Judul:', atau format markdown (**).\n"
                    "4. Fokuskan pada subjek topik, nama produk, atau aksi utama.\n\n"
                )
                if user_query:
                    prompt += f"Pesan Pengguna: {user_query[:300]}\n"
                if ai_response:
                    clean_ai = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', ai_response)
                    clean_ai = re.sub(r'[*_#]', '', clean_ai)[:300]
                    prompt += f"Pesan Asisten: {clean_ai}\n"
                prompt += "\nJudul Singkat:"

                raw_llm_title = llm.generate(prompt)
                generated_title = sanitize_llm_title(raw_llm_title)
                if generated_title and len(generated_title) >= 3:
                    session.summary = generated_title
                    db.add(session)
                    await db.commit()
                    return generated_title
            except Exception as ex:
                logger.warning(f"LLM title generation failed for session {session_id}: {ex}")

        # If LLM failed, persist heuristic title
        session.summary = fallback_title
        db.add(session)
        await db.commit()
        return fallback_title
