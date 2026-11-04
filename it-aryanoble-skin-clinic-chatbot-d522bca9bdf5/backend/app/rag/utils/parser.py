import os
import time
import re
import hashlib
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, Any, Dict, List
from loguru import logger
from app.core.config import settings


class ParseResult:
    """
    Unified parse result that can hold either a DoclingDocument (for OCR path)
    or a list of page-text dicts (for fast path).
    """
    def __init__(self, pages: list = None, docling_doc=None, method: str = "fast"):
        self.pages = pages or []       # [{"page": 1, "text": "..."}, ...]
        self.docling_doc = docling_doc  # DoclingDocument object (only for OCR path)
        self.method = method           # "fast" or "docling"

    @property
    def is_fast(self) -> bool:
        return self.method == "fast"

    @property
    def is_docling(self) -> bool:
        return self.method == "docling"


def _is_valid_image_content(img_bytes: bytes, min_dim: int = 40) -> Tuple[bool, bytes, str]:
    """
    Validates image bytes using Pillow:
    1. Rejects tiny spacer/icon images (< min_dim in width or height).
    2. Downscales oversized images to max dimension 1200 px to stay safely below 800 KB (1 MB WAF limit).
    3. Rejects solid black, pitch-black (>95% black), or flat unicolor blocks.
    4. Converts WMF/EMF or palette formats to clean PNG / JPEG.
    5. Sanitizes circular icons with solid black corners → transparent RGBA PNG.
    Returns: (is_valid, cleaned_bytes, cleaned_ext)
    """
    if not img_bytes or len(img_bytes) < 100:
        return False, b"", ""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(img_bytes)) as im:
            w, h = im.size
            if w < min_dim or h < min_dim:
                return False, b"", ""

            # Downscale oversized images so they never violate 1 MB stream limits
            MAX_DIM = 1200
            MAX_BYTES = 800 * 1024  # 800 KB limit for 1 MB WAF / stream compliance
            if w > MAX_DIM or h > MAX_DIM:
                scale = min(MAX_DIM / w, MAX_DIM / h)
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                w, h = im.size

            # Check format & convert WMF/EMF/TIFF/BMP or palette formats
            ext = (im.format or "png").lower()
            if ext in ("wmf", "emf", "tiff", "bmp") or im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGBA")
                ext = "png"

            # Check for solid pitch black or flat unicolor blocks
            rgb = im.convert("RGB").resize((16, 16))
            colors = rgb.getcolors(maxcolors=256)
            if colors:
                # If single color (flat unicolor rectangle/slide background)
                if len(colors) == 1:
                    return False, b"", ""
                # If solid pitch black (all sampled pixels r, g, b < 18)
                if all(c[1][0] < 18 and c[1][1] < 18 and c[1][2] < 18 for c in colors):
                    return False, b"", ""

            # Sanitize small circular/rounded icons with solid black borders/corners:
            # Strictly gate to small icons (max dim <= 160 px) to prevent expensive pure-Python floodfill recursion on large photos
            if max(w, h) <= 160:
                try:
                    from PIL import ImageDraw
                    rgba_im = im.convert("RGBA")
                    cw, ch = rgba_im.size
                    corners = [(0, 0), (cw - 1, 0), (0, ch - 1), (cw - 1, ch - 1)]
                    has_black_corner = False
                    for cx, cy in corners:
                        px = rgba_im.getpixel((cx, cy))
                        if px[0] < 20 and px[1] < 20 and px[2] < 20 and px[3] > 200:
                            has_black_corner = True
                            ImageDraw.floodfill(rgba_im, (cx, cy), (0, 0, 0, 0), thresh=25)
                    if has_black_corner:
                        im = rgba_im
                        ext = "png"
                except Exception:
                    pass

            # Optimize bytes output for upload stream limit (< 800 KB)
            buf = io.BytesIO()
            if im.mode == "RGBA":
                im.save(buf, format="PNG")
                out_bytes = buf.getvalue()
                ext = "png"
                if len(out_bytes) > MAX_BYTES:
                    # Fallback to high-quality JPEG on white background if PNG still exceeds 800 KB
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[3])
                    buf = io.BytesIO()
                    bg.save(buf, format="JPEG", quality=85)
                    out_bytes = buf.getvalue()
                    ext = "jpg"
            else:
                rgb_im = im.convert("RGB")
                rgb_im.save(buf, format="JPEG", quality=85)
                out_bytes = buf.getvalue()
                ext = "jpg"

            return True, out_bytes, ext
    except Exception:
        # Fallback: if Pillow fails, allow bytes if sufficiently large
        return True, img_bytes, "png"


_VISION_CLIENT_CACHE = {"client": None, "model_name": None, "ts": 0}

def get_vision_client_and_model() -> Tuple[Any, Optional[str]]:
    """
    Returns (OpenAI client, model_name) configured from app_config DB or environment.
    Caches the client instance to eliminate connection initialization overhead.
    """
    global _VISION_CLIENT_CACHE
    now = time.time()
    if _VISION_CLIENT_CACHE["client"] is not None and (now - _VISION_CLIENT_CACHE["ts"]) < 300:
        return _VISION_CLIENT_CACHE["client"], _VISION_CLIENT_CACHE["model_name"]

    try:
        from app.rag.config import settings
        from openai import OpenAI

        db_api_key = None
        db_model_name = None
        db_base_url = None
        try:
            from sqlalchemy import text
            from app.core.database import get_sync_engine
            from app.core.security import decrypt_api_key

            engine = get_sync_engine()
            with engine.connect() as conn:
                res = conn.execute(text("SELECT key, value FROM app_config WHERE key IN ('LLM_API_KEY', 'LLM_ACTIVE_MODEL_NAME', 'LLM_BASE_URL')")).fetchall()
                config_map = {row[0]: row[1] for row in res if row[1]}
                if "LLM_API_KEY" in config_map:
                    try:
                        db_api_key = decrypt_api_key(config_map["LLM_API_KEY"])
                    except Exception:
                        db_api_key = config_map["LLM_API_KEY"]
                db_model_name = config_map.get("LLM_ACTIVE_MODEL_NAME")
                db_base_url = config_map.get("LLM_BASE_URL")
        except Exception as db_err:
            logger.debug(f"DB config fetch skipped: {db_err}")

        api_key = db_api_key or os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
        if api_key and not api_key.startswith("sk-"):
            env_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
            if env_key and env_key.startswith("sk-"):
                api_key = env_key

        base_url = db_base_url or os.getenv("OPENAI_BASE_URL") or getattr(settings, "openai_base_url", None)
        model_name = db_model_name or os.getenv("VISION_MODEL_NAME") or getattr(settings, "openai_model_name", None) or "gpt-4o-mini"

        if api_key and api_key.startswith("sk-"):
            if not model_name or "gemini" in model_name.lower() or not any(model_name.startswith(p) for p in ["gpt-", "o1", "o3", "chatgpt"]):
                model_name = "gpt-4o-mini"
            if base_url and "googleapis.com" in base_url:
                base_url = None

        if api_key:
            client_kwargs = {"api_key": api_key, "timeout": 20.0}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
            _VISION_CLIENT_CACHE = {"client": client, "model_name": model_name, "ts": now}
            return client, model_name
    except Exception as e:
        logger.warning(f"Could not initialize Vision client: {e}")

    return None, None


_VISION_QUOTA_COOLDOWN_UNTIL = 0.0

# Vision Gate calls of one page in flight at once (network-bound waits, not CPU work)
VISION_GATE_CONCURRENCY = 4

# Longest side of an extracted document image as kept, verified and stored (sharp on any screen)
MAX_IMAGE_SIDE = 1600


def _check_flat_decorative_graphic(img_bytes: bytes) -> Tuple[bool, Dict[str, Any]]:
    """
    Analyzes visual complexity using PIL to eliminate flat decorative vector elements
    (e.g. orange pill banners, wave lines, logos, solid background canvases) without LLM.
    """
    if not img_bytes:
        return True, {"reason": "empty bytes"}
    try:
        import io
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(img_bytes))

        # Composite alpha on white
        has_alpha = False
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            has_alpha = True
            im_rgba = im.convert("RGBA")
            bg = Image.new("RGBA", im_rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im_rgba).convert("RGB")
        else:
            im = im.convert("RGB")

        w, h = im.size
        area = w * h
        if area < 20000 or min(w, h) < 90:
            return True, {"reason": f"too small ({w}x{h})", "dims": (w, h)}

        thumb = im.copy()
        thumb.thumbnail((96, 96), Image.Resampling.LANCZOS)
        tw, th = thumb.size
        total_thumb_px = tw * th

        # Posterize to 4 bits per channel (4096 colors)
        poster = ImageOps.posterize(thumb, 4)
        colors = poster.getcolors(maxcolors=4096) or []

        threshold = total_thumb_px * 0.01
        sig_colors = [c for c in colors if c[0] >= threshold]
        sig_count = len(sig_colors)

        dominant_count = max(c[0] for c in colors) if colors else 0
        dominant_fraction = dominant_count / max(1, total_thumb_px)

        stats = {
            "dims": (w, h),
            "sig_count": sig_count,
            "tot_colors": len(colors),
            "dom_frac": round(dominant_fraction, 3),
            "has_alpha": has_alpha
        }

        # If cutout asset has rich multi-color palette (e.g. 3D studio bottle photo with shading),
        # the high background white percentage is purely from the transparent canvas. It is not a flat shape.
        if has_alpha and len(colors) >= 30:
            return False, stats

        if dominant_fraction >= 0.85:
            return True, {**stats, "reason": "excessive single-color dominance (background canvas)"}
        if sig_count <= 2:
            return True, {**stats, "reason": "nearly solid color (sig_count <= 2)"}
        if sig_count <= 5 and dominant_fraction >= 0.65:
            return True, {**stats, "reason": "flat vector element (pill/swoosh/shape)"}
        if len(colors) <= 25:
            return True, {**stats, "reason": "flat color palette (<25 colors total)"}

        return False, stats
    except Exception as e:
        return False, {"reason": f"analysis error: {e}"}


def _heuristic_visual_classify(
    img_bytes: bytes,
    fallback_title: str,
    reason_prefix: str = "Offline Heuristic Gate"
) -> Dict[str, Any]:
    """
    High-precision offline heuristic image classifier when Vision API is down or on cooldown.
    Eliminates decorative logos, navigation icons, thin banners, and background shapes without LLM.
    """
    clean_title = (fallback_title or "").strip()

    # 1. Reject generic slide markers and non-product labels
    is_generic = any(clean_title.lower().startswith(p) for p in [
        "slide ", "image ", "page ", "#", "http", "www.", "dokumen", "lampiran"
    ])
    is_brand_slogan = clean_title.lower() in [
        "skincare", "skin clinic"
    ]

    # 2. Extract image dimensions using PyMuPDF (fast, memory-safe)
    w, h = 0, 0
    try:
        import fitz
        pm = fitz.Pixmap(img_bytes)
        w, h = pm.width, pm.height
        del pm
    except Exception:
        pass

    area = w * h
    aspect = (w / max(1, h)) if h > 0 else 1.0

    # 2.5 Visual complexity check: reject flat decorative vector shapes or monochromatic canvases
    is_flat, flat_stats = _check_flat_decorative_graphic(img_bytes)
    if is_flat:
        return {
            "is_relevant": False,
            "classification": "DECORATIVE",
            "product_name": None,
            "role": "DECORATIVE",
            "confidence": 0.85,
            "reason": f"{reason_prefix}: rejected flat decorative graphic ({flat_stats.get('reason', 'flat graphic')}, dims={w}x{h})"
        }

    # 3. Geometric constraints: Substantive products have decent area and non-extreme aspect ratios
    # Real physical packaging (bottles, jars, tubes, boxes) have aspect ratios between 0.28 and 2.2.
    # Header logos, typography wordmarks, and banner strips are wide (aspect > 2.2) or thin (aspect < 0.25).
    is_substantive = area >= 40000 and min(w, h) >= 130
    is_balanced_aspect = 0.28 <= aspect <= 2.2

    # Check if title contains specific SKU form factors (e.g. Cleanser, Toner, Serum, Sunscreen, Cream, Wash, Gel, Spray, Mask, etc.)
    sku_keywords = [
        "cleanser", "toner", "serum", "sunscreen", "cream", "wash", "gel", "spray",
        "mask", "scrub", "moisturizer", "powder", "lotion", "balm", "spot",
        "spf", "treatment", "shampoo", "scalp", "soap", "foam", "ampoule", "essence"
    ]
    has_sku_keyword = any(k in clean_title.lower() for k in sku_keywords)

    is_product = (
        is_substantive
        and is_balanced_aspect
        and clean_title
        and not is_generic
        and not is_brand_slogan
        and has_sku_keyword
    )

    if is_product:
        return {
            "is_relevant": True,
            "classification": "PRODUCT",
            "product_name": clean_title,
            "role": "PRODUCT_PACKAGING",
            "confidence": 0.78,
            "reason": f"{reason_prefix}: substantive dimensions ({w}x{h}, area={area}) linked to product '{clean_title}'"
        }
    else:
        return {
            "is_relevant": False,
            "classification": "DECORATIVE",
            "product_name": None,
            "role": "DECORATIVE",
            "confidence": 0.75,
            "reason": f"{reason_prefix}: filtered non-product asset (dims={w}x{h}, area={area}, aspect={aspect:.2f}, title='{clean_title}')"
        }


def verify_and_classify_visual_candidate(
    img_bytes: bytes,
    img_ext: str = "png",
    page_context: str = "",
    fallback_title: str = "",
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
    timeout: float = 15.0
) -> Dict[str, Any]:
    """
    Multimodal Vision Verification Gate (Phase 1 & Phase 3 Unified).
    Inspects candidate images using Vision LLM (gpt-4o-mini) + page/slide document context.
    
    Responsibilities:
    1. Filter out non-substantive ornamental/decorative images (slide background graphics, banners, clipart, floral accents).
    2. Read exact official product names from packaging/labels, cross-referenced with page context.
    3. Categorize image role: PRODUCT_PACKAGING, CLINICAL_PHOTO, FIGURE, or DECORATIVE.
    
    Guarantees:
    - Content-hash caching prevents duplicate calls for repeated template graphics across pages.
    - Graceful fallback if Vision API is offline, timed out, or quota exceeded.
    """
    if not img_bytes:
        return {"is_relevant": False, "classification": "DECORATIVE", "product_name": None, "role": "DECORATIVE", "confidence": 0.0, "reason": "Empty bytes"}

    content_hash = hashlib.sha256(img_bytes).hexdigest()
    if cache is not None and content_hash in cache:
        return cache[content_hash]

    global _VISION_QUOTA_COOLDOWN_UNTIL
    is_quota_cooldown = time.time() < _VISION_QUOTA_COOLDOWN_UNTIL

    client, model_name = (None, None) if is_quota_cooldown else get_vision_client_and_model()
    if not client or is_quota_cooldown:
        # Offline heuristic fallback
        reason_pfx = "Quota cooldown fast-path" if is_quota_cooldown else "Offline fallback without Vision API"
        res = _heuristic_visual_classify(img_bytes, fallback_title, reason_prefix=reason_pfx)
        if cache is not None:
            cache[content_hash] = res
        return res

    clean_ext = img_ext.lower().replace(".", "")
    if clean_ext not in ["png", "jpg", "jpeg", "webp"]:
        clean_ext = "png"
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data_uri = f"data:image/{clean_ext};base64,{b64}"

    prompt = (
        "You are a medical and skincare clinical visual expert for PT Arya Noble (ERHA / Dermies Skin Clinic).\n"
        "Analyze this image extracted from a clinical document, product catalog, training manual, or presentation slide.\n\n"
        f"Context text from this page/slide:\n\"\"\"\n{page_context[:1200]}\n\"\"\"\n\n"
        "Determine:\n"
        "1. classification:\n"
        "   - 'PRODUCT': Physical 3D skincare/dermatology product packaging (real bottle, jar, tube, pump, dropper, box, sachet).\n"
        "   - 'CLINICAL': Clinical photo of skin, face, hair/scalp, dermatological condition, or treatment procedure/before-after.\n"
        "   - 'CHART': Scientific graph, efficacy diagram, mechanism of action flowchart, or anatomical diagram.\n"
        "   - 'INFOGRAPHIC_TABLE': An infographic, designed table, combination guide (e.g. SERUM YES/NO), comparison matrix, regimen checklist, or FAQ/feature table with checkmarks/crosses.\n"
        "   - 'DECORATIVE': Slide background graphic, decorative border/divider, abstract art, generic flower/wave illustration, icon, clipart, 2D BRAND LOGO, CLINIC EMBLEM, TYPOGRAPHY WORDMARK, or header/footer graphic. CRITICAL: A flat 2D brand logo, company emblem, or title wordmark (e.g. 'ERHA', 'ERHA acneact', 'Dermies', 'Arya Noble', clinic emblems, slogans) is DECORATIVE/BRANDING, NOT a product packaging! Even if it mentions a product line or brand name, a 2D logo is DECORATIVE and is_relevant MUST BE FALSE! Only real physical 3D product containers are 'PRODUCT'.\n\n"
        "2. is_relevant:\n"
        "   - true ONLY for physical 3D PRODUCT packaging containers, CLINICAL photos, scientific CHART, or INFOGRAPHIC_TABLE.\n"
        "   - false if DECORATIVE, brand logos, clinic wordmarks, banners, icons, abstract shapes, background graphics.\n\n"
        "3. product_name:\n"
        "   - If PRODUCT: The EXACT official product name printed on the packaging, cross-referenced with the page context text.\n"
        "   - If CLINICAL: The clinical condition or treatment name (state 'Before' or 'After' if applicable).\n"
        "   - If CHART or INFOGRAPHIC_TABLE: The descriptive title of the chart/table/infographic.\n"
        "   - If DECORATIVE: null.\n\n"
        "4. extracted_markdown (CRITICAL FOR TABLES & INFOGRAPHICS):\n"
        "   - If the image contains a table, combination matrix, checklist, or infographic (e.g. SERUM YES/NO, Feature Matrix, Product Grid):\n"
        "     Transcribe it into a complete, clean GFM Markdown table (`| Col 1 | Col 2 |`).\n"
        "     Keep the printed grid: its own column headers, one Markdown row per printed row, every value in the column it is\n"
        "     printed under. A header spanning sub-columns (e.g. 'Ultra Booster Cartridge' over 'MP Mode' and 'Normal Mode')\n"
        "     becomes one column per sub-column; a cell spanning several rows is repeated in each row. Never stack a column's\n"
        "     values as extra rows below the table.\n"
        "     Convert visual icons: green checkmark/tick -> 'YES' / 'Boleh', red cross/X -> 'NO' / 'Tidak Boleh'.\n"
        "     Include all combination rules, morning/night regimens, and text instructions below the table.\n"
        "   - If pure product photo without tabular data: null.\n\n"
        "Output JSON ONLY with keys: classification, is_relevant, product_name, extracted_markdown, confidence, reason."
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=timeout
        )
        parsed = json.loads(response.choices[0].message.content)
        is_rel = bool(parsed.get("is_relevant", False))
        cls_name = str(parsed.get("classification", "DECORATIVE")).upper()
        if cls_name == "DECORATIVE":
            is_rel = False
        prod_n = parsed.get("product_name")
        if not prod_n and is_rel:
            prod_n = fallback_title or "Infografis & Tabel Medis"

        role_map = {
            "PRODUCT": "PRODUCT_PACKAGING",
            "CLINICAL": "CLINICAL_PHOTO",
            "CHART": "FIGURE",
            "INFOGRAPHIC_TABLE": "FIGURE",
            "DECORATIVE": "DECORATIVE"
        }

        def _safe_float(val, default=0.9):
            try:
                return float(val)
            except Exception:
                v = str(val).lower()
                if "high" in v: return 0.95
                if "med" in v: return 0.75
                if "low" in v: return 0.50
                return default

        ext_md = parsed.get("extracted_markdown")
        if ext_md and str(ext_md).strip() and str(ext_md).strip().lower() != "null":
            ext_md = str(ext_md).strip()
            # Strip enclosing markdown code fences that can leak unclosed into document
            ext_md = re.sub(r'^```(?:markdown)?\s*', '', ext_md, flags=re.IGNORECASE)
            ext_md = re.sub(r'\s*```$', '', ext_md)
            from app.rag.utils.text_hygiene import unstack_stacked_columns, flatten_label_only_tables
            ext_md = flatten_label_only_tables(unstack_stacked_columns(ext_md.strip())).strip() or None
        else:
            ext_md = None

        res = {
            "is_relevant": is_rel,
            "classification": cls_name,
            "product_name": prod_n if is_rel else None,
            "role": role_map.get(cls_name, "PRODUCT_PACKAGING"),
            "extracted_markdown": ext_md,
            "confidence": _safe_float(parsed.get("confidence", 0.90)),
            "reason": str(parsed.get("reason", ""))
        }
    except Exception as api_err:
        err_msg = str(api_err).lower()
        if "429" in err_msg or "quota" in err_msg or "spend_limit" in err_msg or "insufficient_quota" in err_msg:
            _VISION_QUOTA_COOLDOWN_UNTIL = time.time() + 600
            logger.warning(f"Vision API quota exceeded ({api_err}), activating 10-minute circuit breaker to fast-path heuristics.")
        else:
            logger.warning(f"Vision API verification failed/timed out, using heuristic: {api_err}")
        res = _heuristic_visual_classify(img_bytes, fallback_title, reason_prefix=f"Fallback error: {api_err}")

    if cache is not None:
        cache[content_hash] = res
    return res


def transcribe_visual_infographic_slide(
    page: Any,
    page_context: str = "",
    cache: Optional[dict] = None,
    timeout: float = 30.0
) -> Optional[str]:
    """
    Multimodal Vision Transcription for designed infographic slides, combination matrices,
    regimen checklists, and visual FAQ tables (e.g. SERUM YES/NO, Feature Matrix with check/cross icons,
    skin type multi-column layout) that cannot be parsed by line-based vector table heuristics.
    """
    client, model_name = get_vision_client_and_model()
    if not client or not model_name:
        return None

    try:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
    except Exception as pix_err:
        logger.debug(f"Failed to render page pixmap for vision transcription: {pix_err}")
        return None

    content_hash = hashlib.sha256(img_bytes).hexdigest()
    if cache is not None and content_hash in cache:
        return cache[content_hash]

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"

    prompt = (
        "Kamu adalah pakar klinis & visual AI PT Arya Noble (ERHA / Dermies Skin Clinic).\n"
        "Analisis slide presentasi / dokumen ini secara teliti. Di slide ini terdapat infografis, matriks kombinasi produk, tabel perbandingan varian, bagan alur konsultasi/decision tree, atau FAQ dengan icon centang/silang.\n\n"
        f"Konteks teks slide:\n\"\"\"\n{page_context[:1000]}\n\"\"\"\n\n"
        "Tugasmu:\n"
        "0. Jika slide sudah memuat tabel tercetak, salin tabel itu apa adanya dan abaikan skema kolom di poin 1:\n"
        "   - Satu baris Markdown untuk setiap baris tabel tercetak; setiap nilai tetap di kolom tempat ia tercetak.\n"
        "   - Header yang membentang di atas beberapa sub-kolom (mis. 'Ultra Booster Cartridge' di atas 'MP Mode' dan 'Normal Mode') menjadi satu kolom per sub-kolom bernama 'Header - Sub-header'.\n"
        "   - Sel yang membentang beberapa baris (mis. satu 'Treatment Interval' untuk semua Skin Type) diulang di setiap baris yang dicakupnya. Jangan menumpuk nilai kolom lain sebagai baris tambahan di bawah.\n"
        "   - Foto (before/after, foto pasien atau alat) walaupun diberi label waktu/keterangan ('Pre', '24 hrs Post', 'Before') BUKAN tabel: jangan dijadikan sel tabel.\n"
        "1. Transkripsikan SELURUH informasi tabular/infografis ke dalam format tabel Markdown (GitHub Flavored Markdown):\n"
        "   - Jika slide berisi matriks kombinasi produk atau FAQ centang/silang: Tuliskan header kolom dan baris presisi. Ubah centang hijau menjadi 'YES' atau 'Boleh', dan silang merah menjadi 'NO' atau 'Tidak Boleh'.\n"
        "   - Jika slide berisi bagan alur rekomendasi / decision tree (misal: 'What is your skin concern?', alur kondisi kulit -> target hasil -> rekomendasi produk): Transkripsikan alur tersebut menjadi tabel rekomendasi Markdown: | Kondisi / Masalah Kulit | Target Hasil | Rekomendasi Produk |\n"
        "   - Jika slide berisi tabel/kolom perbandingan produk (comparison booster/serum/krim): Buat tabel komparasi perbandingan produk dengan kolom: Nama Produk, Manfaat / Fungsi Utama, Cocok Untuk, Waktu Pakai (Pagi/Malam).\n"
        "   - Jika slide berisi matriks regimen berdasarkan tipe kulit (Cleanser, Toner, Serum, Sunscreen, Treatment, dll): Buat tabel langkah perawatan yang lengkap.\n"
        "   - Jika ada simbol matahari/siang atau bulan/malam, beri keterangan (Pagi) atau (Malam).\n"
        "   - ATURAN PAKAI: HANYA JIKA slide SECARA EKSPLISIT memuat instruksi cara pakai / petunjuk penggunaan klinis, buat subjudul '### Cara Pakai:' tepat di bawah tabel. Jika slide TIDAK memiliki petunjuk cara pakai, DILARANG KERAS membuat subjudul 'Cara Pakai' atau menuliskan 'null' / 'none'.\n"
        "   - Bagian 'Catatan:' HANYA untuk peringatan khusus medis, kontraindikasi, atau anjuran penyimpanan. Jika tidak ada peringatan khusus, DILARANG KERAS mencetak bagian Catatan atau 'Catatan: null'.\n"
        "2. Jika slide benar-benar TIDAK memiliki tabel, infografis alur, perbandingan produk, matriks, spesifikasi teknis/alat, atau daftar tabular, kembalikan 'null'.\n"
        "3. Kembalikan HANYA teks Markdown tabel dan subjudulnya (jika ada instruksi), tanpa kalimat pengantar atau penutup."
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]}
            ],
            temperature=0.0,
            timeout=timeout
        )
        content = (response.choices[0].message.content or "").strip()
        if not content or content.lower() in ("null", "none", "tidak ada"):
            res = None
        else:
            if content.startswith("```markdown"):
                content = content[len("```markdown"):].strip()
            elif content.startswith("```"):
                content = content[len("```"):].strip()
            if content.endswith("```"):
                content = content[:-3].strip()

            # Sanitize trailing or isolated null/empty Cara Pakai and Catatan sections
            content = re.sub(r'(?i)(?:^|\n)\s*###\s*(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*(?:```(?:markdown)?\s*)?(?:null|none)?(?:```)?\s*$', '', content).strip()
            content = re.sub(r'(?i)(?:^|\n)\s*(?:###\s*)?(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*(?:null|none)\s*(?=\n|$)', '', content).strip()
            content = re.sub(r'(?i)(?:^|\n)\s*###\s*(?:Cara Pakai|Aturan Pakai|Catatan|Notes?)\s*:\s*$', '', content).strip()
            content = re.sub(r'```(?:markdown)?\s*null\s*```', '', content, flags=re.IGNORECASE).strip()

            from app.rag.utils.text_hygiene import unstack_stacked_columns, flatten_label_only_tables
            res = flatten_label_only_tables(unstack_stacked_columns(content.strip())) if "|" in content else None
            res = res if res and "|" in res else None
    except Exception as e:
        logger.warning(f"Slide vision transcription failed: {e}")
        res = None

    if cache is not None:
        cache[content_hash] = res
    return res


def _find_best_product_title_for_image(
    page: Any,
    bbox: list,
    non_footers: list,
    page_width: float,
    page_height: float,
    is_slide_deck: bool = False
) -> str:
    """
    Spatially and semantically associates an image with its most accurate product title.
    Supports widescreen multi-column slides (e.g. left and right product columns)
    and standard document layouts.
    Rejects prices, quantities, sub-bullets, disclaimers, and category headers.
    """
    if not bbox or len(bbox) < 4:
        return ""

    midpoint = page_width / 2.0 if page_width > 0 else 0.0
    img_x_mid = (bbox[0] + bbox[2]) / 2.0
    img_y_mid = (bbox[1] + bbox[3]) / 2.0
    is_left = img_x_mid < midpoint if midpoint > 0 else True

    SKIP_PHRASES = {
        "foto produk", "nama produk", "brand", "kategori", "ukuran", "deskripsi",
        "no", "action", "gambar", "catatan", "note", "notes", "keterangan",
        "prosedur", "procedure", "status", "checklist", "field", "isi / catatan",
        "bahan aktif", "informasi lain - lain", "informasi lain-lain", "cara pakai",
        "cara penggunaan", "peringatan", "kontraindikasi", "aturan pakai", "komposisi",
        "detail produk", "katalog produk erha", "katalog produk dermies", "katalog produk",
        "booster", "produk", "slide"
    }
    PRICE_SIZE_RE = re.compile(r'(?:rp\.?|\d+\s*(?:ml|gr|gram|mg|l)\b)', re.I)
    SUB_BULLET_RE = re.compile(r'^[a-z0-9][\.\)]\s+', re.I)
    DISCLAIMER_RE = re.compile(r'^(?:tidak\s+diperbolehkan|hindari|perhatian|warning|catatan|khusus)\b', re.I)
    FIG_CAPTION_RE = re.compile(r'^(?:figure|fig\.|gambar|diagram|bagan|grafik)\s+[ivx0-9]+', re.I)

    candidates = []

    # Check whether the same column as the image actually contains candidate titles
    has_same_col_candidates = False
    if is_slide_deck and midpoint > 0:
        for cb in non_footers:
            cb_x_mid = (cb[0] + cb[2]) / 2.0
            cb_is_left = cb_x_mid < midpoint
            if cb_is_left == is_left:
                for cl in cb[4].splitlines():
                    clean_cl = re.sub(r'^[0-9\.\-\*\•\s]+', '', cl).strip().lower()
                    if len(clean_cl) >= 4 and clean_cl not in SKIP_PHRASES and not PRICE_SIZE_RE.search(clean_cl):
                        has_same_col_candidates = True
                        break
            if has_same_col_candidates:
                break

    for b in non_footers:
        txt = b[4].strip()
        if not txt:
            continue

        # Skip blocks that are multi-category table/regimen headers (e.g. Skin Type, Cleanser, Toner, Serum...)
        CATEGORY_HEADER_TERMS = [
            "skin type", "cleanser", "toner", "serum", "moisturizer", "sunscreen",
            "treatment", "others", "other", "body", "mask", "day cream", "night cream", "eye cream"
        ]
        cat_matches = sum(1 for term in CATEGORY_HEADER_TERMS if re.search(r'\b' + re.escape(term) + r'\b', txt.lower()))
        if cat_matches >= 2:
            continue

        bx_mid = (b[0] + b[2]) / 2.0
        by_mid = (b[1] + b[3]) / 2.0

        # In widescreen slide decks, only restrict to same column if that column actually has candidates!
        if is_slide_deck and midpoint > 0 and has_same_col_candidates:
            b_is_left = bx_mid < midpoint
            if is_left != b_is_left and abs(bx_mid - img_x_mid) > 180:
                continue  # Skip opposite column!

        # Horizontal overlap between text block and image
        h_overlap = max(0.0, min(bbox[2], b[2]) - max(bbox[0], b[0]))
        h_overlap_ratio = h_overlap / max(1.0, min(bbox[2] - bbox[0], b[2] - b[0]))

        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        for l in lines:
            clean_l = re.sub(r'^[0-9\.\-\*\•\s]+', '', l).strip()
            l_lower = clean_l.lower()

            # Scientific figure caption takes priority in scientific/general documents
            if FIG_CAPTION_RE.match(clean_l):
                candidates.append((200.0, clean_l, b))
                continue

            # Skip non-title content
            if l_lower in SKIP_PHRASES:
                continue
            if PRICE_SIZE_RE.search(clean_l):
                continue
            if SUB_BULLET_RE.match(l):
                continue
            if DISCLAIMER_RE.match(clean_l):
                continue
            if len(clean_l) < 4:
                continue

            score = 0.0
            gap_above = bbox[1] - b[3]  # Distance from bottom of text block to top of image
            gap_below = b[1] - bbox[3]  # Distance from bottom of image to top of text block

            # Spatial scoring: Title directly above image (allowing sub-pixel/border touching down to -25px)
            if -25 <= gap_above <= 240:
                score += 100.0 - (max(0.0, gap_above) * 0.3)
                if h_overlap > 20:
                    score += 40.0 * min(1.0, h_overlap_ratio + 0.3)
            elif 0 <= gap_below <= 150:
                score += 70.0 - (gap_below * 0.3)
                if h_overlap > 20:
                    score += 30.0 * min(1.0, h_overlap_ratio + 0.3)
            else:
                y_dist = abs(by_mid - img_y_mid)
                score += max(0.0, 40.0 - (y_dist * 0.1))
                if h_overlap > 20:
                    score += 25.0

            # Horizontal proximity bonus
            x_dist = abs(bx_mid - img_x_mid)
            score += max(0.0, 50.0 - (x_dist * 0.15))

            # Universal product, medical, clinical, and procedural terminology cues
            title_keywords = [
                "serum", "cream", "creme", "krim",
                "facial", "wash", "night", "day",
                "toner", "lotion", "sunscreen", "cleanser", "moisturizer",
                "barrier", "glow", "essence", "booster",
                "treatment", "terapi", "peeling", "laser", "hifu", "mpt",
                "ultraformer", "device", "handpiece", "cartridge", "applicator",
                "gel", "solution", "shampoo", "mask", "masker", "ampoule",
                "protocol", "protokol", "sop", "guideline", "panduan"
            ]
            if any(k in l_lower for k in title_keywords):
                score += 50.0
            if clean_l.isupper() and 6 <= len(clean_l) <= 60:
                score += 35.0
            elif clean_l.istitle() and 6 <= len(clean_l) <= 60:
                score += 20.0
            if 8 <= len(clean_l) <= 50:
                score += 15.0
            elif len(clean_l) > 90:
                score -= 30.0  # Paragraph penalty

            candidates.append((score, clean_l, b))

    if not candidates:
        return ""

    candidates.sort(key=lambda c: c[0], reverse=True)
    best_score, best_title, best_b = candidates[0]

    # If the winning block contains multiple lines of title (e.g. "ERHA AGE CORRECTOR\nNIGHT CHARGE")
    lines_in_b = [l.strip() for l in best_b[4].splitlines() if l.strip()]
    if 2 <= len(lines_in_b) <= 3 and all(3 <= len(l) <= 45 for l in lines_in_b):
        joined = " ".join(lines_in_b)
        joined_lower = joined.lower()
        letters = [c for c in joined if c.isalpha()]
        is_capitals_block = bool(letters) and sum(1 for c in letters if c.isupper()) / len(letters) >= 0.8
        if len(joined) <= 70 and (is_capitals_block or any(k in joined_lower for k in ["serum", "cream", "toner", "wash", "cleanser"])):
            return joined

    return best_title


def _is_ornamental_pdf_image(
    pix_width: int,
    pix_height: int,
    bbox: list,
    page_height: float,
    page_idx: int,
    nearby_text: str,
    prod_label: str,
    page_width: float = 0.0,
    is_slide_deck: bool = False
) -> bool:
    """
    Detects and filters out non-substantive ornamental PDF images such as:
    - Publisher/journal logos in headers/footers (e.g. HJKK, Elsevier, Springer, Nature logos)
    - University insignias, academic emblems, hospital/clinic seals
    - DOI badges & icons (e.g. 44x44 DOI icon)
    - Creative Commons / copyright license banners (e.g. 133x46 CC-BY-SA badge)
    - Running headers, page footer banners, separator rules
    - Slide deck icons, prohibition/warning signs, bottom clipart illustrations, slide wallpapers
    - Social media icons / tiny badges (< 55px or banner aspect with tiny height)
    Preserves genuine product photos, clinical figures, histology, charts, diagrams, and patient before/after.
    """
    rendered_w = abs(bbox[2] - bbox[0]) if (bbox and len(bbox) >= 4) else float(pix_width)
    rendered_h = abs(bbox[3] - bbox[1]) if (bbox and len(bbox) >= 4) else float(pix_height)
    is_wide_slide = is_slide_deck or (page_width >= 800 and page_width > page_height * 1.15)

    # 1. Slide Deck specific layout filters
    if is_wide_slide and bbox and len(bbox) >= 4:
        # Small icons/symbols (warning signs, prohibition circles, checkmarks, bullets)
        if (rendered_w < 85 and rendered_h < 85) or rendered_w < 55 or rendered_h < 55:
            return True
        # Full-page / slide background images or template wallpapers
        if (rendered_w > page_width * 0.85 and rendered_h > page_height * 0.85) or (rendered_h >= page_height * 0.92 and (bbox[0] <= 10 or bbox[2] >= page_width - 10)):
            return True
        # Header logo in upper corner (e.g. clinic logo top-right)
        # Genuine products or medical equipment consoles on the right are tall (rendered_h >= 100)
        if (
            bbox[1] < page_height * 0.20
            and bbox[0] > page_width * 0.70
            and rendered_h < 85
            and rendered_w < 180
        ):
            return True
        # Bottom decorative clipart / illustrations (e.g. woman mirror clipart at bottom)
        if bbox[1] > page_height * 0.72 and rendered_h < 260 and not (0.35 <= (rendered_w / max(1.0, rendered_h)) <= 0.65):
            return True

    # Standard dimension checks for all document types
    # Tiny raster icons or tiny rendered sizes (e.g. DOI icon 44x44, favicons, bullets, social media icons)
    if pix_width < 55 or pix_height < 55 or rendered_w < 50 or rendered_h < 50:
        return True
    
    # License / copyright banner aspect ratio (e.g. CC badge 133x46, 88x31, barcode 200x50)
    if pix_height <= 60 and pix_width <= 250:
        return True

    # 2. Textual pattern checks on label and nearby text
    combined_text = f"{prod_label} {nearby_text}".lower()
    
    # Check if this image has an explicit scientific figure/chart/flowchart caption (e.g. Figure 1, Gambar 2, Bagan Alur)
    has_figure_caption = bool(re.search(r'\b(?:figure|fig\.|gambar|diagram|bagan|alur|grafik|chart)\b', combined_text, re.IGNORECASE))

    # Obvious ornamental / metadata badges
    badge_keywords = [
        "doi.org", "http://doi", "https://doi", "doi:", "dx.doi.org",
        "creative commons", "creativecommons", "cc-by", "cc by", "cc_by", "cc-sa", "cc-nc", "cc-nd", "cc0",
        "crossmark", "open access", "openaccess", "open-access",
        "issn", "e-issn", "p-issn", "isbn",
        "scopus", "sinta", "sinta 1", "sinta 2", "sinta 3", "sinta 4", "sinta 5", "sinta 6",
        "pubmed", "pmc", "medline", "doaj", "google scholar", "garuda",
        "dimensions", "clarivate", "web of science", "wos", "scimago", "sjr",
        "copernicus", "index copernicus", "ebsco", "proquest", "cabi",
        "orcid", "orcid.org", "researchgate", "zenodo", "figshare"
    ]
    if any(kw in combined_text for kw in badge_keywords):
        return True

    # Stop words in prod_label (if PyMuPDF extracted nearby words as label)
    label_stop_words = [
        "logo", "banner", "header", "footer", "badge", "crest", "lambang", "kop",
        "cover", "icon", "watermark", "stamp", "stempel", "cap", "emblem", "insignia"
    ]
    if any(sw in prod_label.lower() for sw in label_stop_words) and not has_figure_caption:
        return True

    # 2b. Global journal/publisher metadata keyword filter (position-independent).
    # Catches journal logos like "Borneo Journal of Pharmacy", "HYDROGEN - Jurnal Kependidikan Kimia"
    # regardless of whether they sit in header/footer zone.
    # Only filter if the image does NOT have a genuine scientific figure caption.
    # CRITICAL: Substantive clinical diagrams, flowcharts, and figures (e.g. >= 300x200)
    # MUST NOT be discarded by journal/publisher metadata filters!
    is_substantive_diagram = pix_width >= 300 and pix_height >= 200 and 0.3 <= (pix_width / max(1, pix_height)) <= 3.2
    if not has_figure_caption and not is_substantive_diagram:
        journal_meta_keywords = [
            # Major international academic publishers
            "elsevier", "sciencedirect", "springer", "springer nature", "nature publishing",
            "wiley", "john wiley", "blackwell", "taylor & francis", "taylor and francis",
            "sage pub", "sage publications", "sage journals", "ieee", "acm",
            "mdpi", "frontiers in", "frontiers media", "oxford university press", "oup",
            "cambridge university press", "cup", "wolters kluwer", "lippincott williams", "lww",
            "plos", "plos one", "hindawi", "biomed central", "bmc",
            "emerald publishing", "de gruyter", "bmj", "bmj publishing", "dovepress", "dove medical press",
            "bentham science", "karger", "thieme", "mary ann liebert", "spandidos", "sciendo",
            "academic press", "university press", "ios press", "world scientific",

            # Indonesian & Regional journals / institutions
            "borneo journal", "hydrogen", "jurnal farmasi", "jurnal kedokteran", "jurnal kesehatan",
            "jurnal kependidikan", "jurnal ilmiah", "jurnal penelitian", "media farmasi",
            "majalah farmasi", "acta medica", "folia medica", "berkala kedokteran",
            "perdoski", "ikatan apoteker", "ikatan dokter", "kemenkes", "kemendikbud", "kemenristek",
            "brin", "lipi", "universitas", "university", "fakultas", "faculty", "politeknik", "sekolah tinggi",
            "institut teknologi", "institut pertanian",

            # Journal / Periodical structural terms
            "journal of", "jurnal of", "journal ", "jurnal ", "the journal", "international journal",
            "indonesian journal", "asian journal", "american journal", "european journal",
            "world journal", "global journal", "national journal",
            "bulletin of", "archives of", "annals of", "proceedings of", "review of",
            "advances in", "trends in", "current research in", "periodical",
            "penerbit", "publisher", "published by", "diterbitkan oleh", "diterbitkan", "dipublikasikan",
            "e-journal", "ejournal", "oai:",

            # Medical, Dermatology, Cosmetic & Pharma journal phrases
            "dermatology journal", "clinical dermatology", "pharmaceutical sciences",
            "pharmacy and", "pharmaceutical journal", "pharmacology", "pharmacognosy",
            "biomedical journal", "cosmetic dermatology", "cosmetic science",
            "aesthetic medicine", "aesthetic dermatology", "skin research", "skin pharmacology",
            "experimental dermatology", "investigative dermatology",

            # Submission & Publication tracking metadata
            "manuscript", "how to cite", "how to reference", "cara sitasi", "cara merujuk",
            "suggested citation", "cite this", "homepage:", "homepage :", "available at",
            "available online", "correspondence", "corresponding author", "penulis korespondensi",
            "author for correspondence", "received:", "received :", "accepted:", "accepted :",
            "revised:", "revised :", "published online", "diterima:", "disetujui:", "direvisi:",
            "article info", "informasi artikel", "article history", "riwayat artikel",
            "keywords:", "kata kunci:",
            "volume ", "vol. ", "vol ", "issue ", "no. ", "nomor ", "edisi ", "pp. ",
            "issn ", "e-issn ", "p-issn "
        ]
        if any(jk in combined_text for jk in journal_meta_keywords):
            return True

    # 2c. Substantive clinical product image protection
    # Ensures genuine product packaging, titles, bottles, tubes, and clinical cards are NEVER discarded
    product_protect_keywords = [
        "wash", "facial", "creme", "cream", "serum", "gel", "barrier",
        "toner", "lotion", "mask", "sunscreen", "cleanser",
        "moisturizer", "moist", "booster", "peeling", "essence", "scrub", "spray", "mist",
        "shampoo", "scalp", "treatment", "acne", "aging", "brightening", "glowing", "oil",
        "radiance", "calming", "soothing", "hydration", "hydrating", "rejuvenation", "vit c",
        "vitamin", "niacinamide", "salicylic", "aha", "bha", "pha", "peptide", "retinol"
    ]
    prod_label_clean = prod_label.lower().strip()
    is_invalid_label = (
        any(prod_label_clean.startswith(x) for x in ["tidak ", "hindari ", "perhatian", "warning", "catatan", "15 ml", "30 gr", "b.", "a.", "c.", "rp"]) or
        bool(re.search(r'(?:rp\.?|\d+\s*(?:ml|gr|gram|mg|l)\b)', prod_label_clean))
    )
    is_protected_product = (not is_invalid_label) and any(pw in prod_label_clean for pw in product_protect_keywords)

    # 3. Header & Footer checks
    if not is_protected_product and not has_figure_caption:
        header_threshold = 0.35 if page_idx == 0 else 0.18
        # bbox[1] is y0 (top edge of image), bbox[3] is y1 (bottom edge of image)
        is_header = (bbox[1] < page_height * header_threshold) if page_height > 0 else False
        is_footer = (bbox[3] > page_height * 0.85 or bbox[1] > page_height * 0.82) if page_height > 0 else False

        # On Page 1, any image starting in top 28% of page without a figure caption is a journal logo/header
        if page_idx == 0 and bbox[1] < (page_height * 0.28):
            return True

        # Any thin horizontal divider line / separator rule (height <= 80 and width >= 2.5x height) located in header or footer
        if (is_header or is_footer) and (pix_height <= 80) and (pix_width >= pix_height * 2.5):
            return True

        # If in header or footer and text contains any academic/header metadata
        if is_header or is_footer:
            header_meta_words = [
                "journal", "jurnal", "volume", "vol.", "vol ", "issue", "no.", "nomor", "edisi", "edition",
                "published", "penerbit", "publisher", "universitas", "university", "fakultas", "faculty",
                "kependidikan", "kimia", "department", "departemen", "hydrogen", "borneo",
                "pharmacy", "farmasi", "sciences", "research", "international", "indonesian",
                "institut", "institute", "politeknik", "polytechnic", "sekolah tinggi", "akademi",
                "jurusan", "program studi", "prodi", "laboratorium", "laboratory",
                "suplemen", "supplement", "halaman", "pages", "pp.", "p-issn", "e-issn", "issn", "isbn",
                "doi:", "doi.org", "copyright", "hak cipta", "all rights reserved", "©", "(c)",
                "license", "lisensi", "annual", "conference", "prosiding", "proceedings",
                "seminar nasional", "symposium", "congress", "symposia"
            ]
            if any(hw in combined_text for hw in header_meta_words):
                return True

    # 4. Signatures, Paraf, Official Stamps, and Approval block images
    sig_keywords = [
        "tanda tangan", "tandatangan", "signature", "signed", "paraf", "ttd",
        "lembar persetujuan", "lembar pengesahan", "approval sheet",
        "dibuat oleh", "diperiksa oleh", "disetujui oleh", "diketahui oleh",
        "disahkan oleh", "diajukan oleh", "mengetahui", "approved by",
        "reviewed by", "prepared by", "checked by"
    ]
    if any(sk in combined_text for sk in sig_keywords):
        sig_indicators = ["tanggal:", "tanggal :", "nama /", "nama terapis", "supervisor", "pic klinik", "(___", "_____", "nama/"]
        if any(si in combined_text for si in sig_indicators) or any(k in combined_text for k in ["tanda tangan", "tandatangan", "signature", "paraf", "disetujui", "diperiksa", "dibuat oleh"]):
            return True

    return False


_INLINE_REF_HEADING_RE = re.compile(
    r'^(?:Referensi|References?|Daftar\s+Pustaka|Kepustakaan|Pustaka|Rujukan|Sumber\s+Pustaka)\s*:\s*(.*)$',
    re.IGNORECASE,
)
_CITATION_KEYWORDS = (
    "doi:", "doi.org", "et al", "dkk", "vol.", "pp.", "springer", "elsevier", "wiley", "http", "pmid",
    "penyunting", "editor", "edisi ke", "dalam:", "in:", "statpearls", "publishing", "publishers",
    "isbn", "issn", "[internet]",
)
_CITATION_AUTHOR_RE = re.compile(r"^[A-Z][A-Za-z'’\-]+(?:\s[A-Z][a-z][A-Za-z'’\-]*)?,?\s[A-Z]{1,3}\b[,\.]?")
_CITATION_SOURCE_RE = re.compile(r'\d+\s*\(\s*[\w\s\-]+\)\s*[:;,]|;\s*\d+\s*[:(;]|\bh\.\s*\d+|:\s*\d+\s*[-–]\s*\d+|\bp+\.\s*\d+')
_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')


def _looks_like_citation(text: str) -> bool:
    """A bibliography entry or a wrapped piece of one: authors with initials, a year, a source with volume/pages."""
    s = re.sub(r'^(?:\[\d+\]|\d{1,3}[\.\)])\s*', '', (text or "").strip())
    if not s:
        return False
    low = s.lower()
    has_year = bool(_YEAR_RE.search(s))
    has_source = bool(_CITATION_SOURCE_RE.search(s))
    if any(k in low for k in _CITATION_KEYWORDS) and (has_year or has_source or len(s) < 160):
        return True
    if _CITATION_AUTHOR_RE.match(s) and (has_year or has_source):
        return True
    return has_year and has_source


def _strip_references_from_pages(pages: list) -> list:
    """
    Strips out 'References', 'Daftar Pustaka', 'Bibliography', and literature citations
    from parsed pages of academic papers and journals.

    In multi-chapter documents, clinical guidelines, or book compendiums (> 20 pages or where
    subsequent pages have clinical sections/flowcharts), strips references ONLY within the
    specific citation sections, without truncating the rest of the document.
    """
    if not pages:
        return pages

    total_pages = len(pages)
    ref_heading_pattern = re.compile(
        r'^(?:#{1,3}\s*)?(?:REFERENCES?|DAFTAR\s+(?:PUSTAKA|REFERENSI|RUJUKAN)|BIBLIOGRAPHY|LITERATURE\s+CITED|CITED\s+LITERATURE|PUSTAKA\s+ACUAN|SENARAI\s+PUSTAKA|RUJUKAN)\s*$',
        re.IGNORECASE
    )

    logger.info(f"📚 Stripping references/citations per-section non-destructively across {total_pages} pages.")
    cleaned_pages = []
    in_ref = False

    for p_idx, page in enumerate(pages):
        txt = page.get("text", "")
        if not txt:
            cleaned_pages.append(page)
            continue

        lines = txt.splitlines()
        new_lines = []
        for l in lines:
            clean = l.strip()
            plain = re.sub(r'[*_`]', '', clean).strip()
            if ref_heading_pattern.match(clean) or ref_heading_pattern.match(plain):
                in_ref = True
                continue
            # 'Referensi: Lintzeri DA, ...' — a reference list introduced inline under a figure or flowchart
            inline_ref = _INLINE_REF_HEADING_RE.match(plain)
            if inline_ref:
                in_ref = True
                rest = inline_ref.group(1).strip()
                if rest and not _looks_like_citation(rest):
                    in_ref = False
                    new_lines.append(rest)
                continue
            if in_ref:
                # The reference section ends at a heading, a table, a structural section, or at the first line
                # that is not a citation; it may run on over the next page, which has no heading of its own.
                if (clean.startswith("#")
                    or any(plain.lower().startswith(x) for x in [
                        "bagan alur", "alur diagnosis", "definisi", "anamnesis", "tabel ",
                        "lampiran", "appendix", "persetujuan", "informed consent", "formulir",
                        "jadwal", "instruksi", "monitoring", "aftercare", "evaluasi"
                    ])
                    or (clean.startswith("|") and clean.endswith("|"))):
                    in_ref = False
                    new_lines.append(l)
                elif not plain or re.fullmatch(r'\d{1,4}', plain) or _looks_like_citation(plain):
                    # Citation (in any formatting, also bolded by the normalizer) or a bare page number
                    continue
                else:
                    in_ref = False
                    new_lines.append(l)
            else:
                new_lines.append(l)

        new_page = dict(page)
        new_page["text"] = "\n".join(new_lines).strip()
        cleaned_pages.append(new_page)

    return cleaned_pages


# Clinical key-value tables (practice guidelines, SOPs): a 2-column table whose labels are these aspects has no
# header row of its own, its first row is already data.
_CLINICAL_KEY_LABELS = (
    'definisi', 'anamnesis', 'pemeriksaan', 'diagnosis', 'terapi', 'edukasi', 'prognosis', 'komplikasi',
    'faktor risiko', 'faktor resiko', 'indikasi', 'kontraindikasi', 'parameter', 'fitur', 'karakteristik',
    'tipe', 'kriteria', 'klasifikasi', 'tata laksana', 'tatalaksana', 'penatalaksanaan', 'etiologi',
    'epidemiologi', 'patogenesis', 'gejala', 'manifestasi',
)

_W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class _DocxListRenderer:
    """
    Word stores list bullets and numbers as numbering properties, not as text, so a paragraph's text alone loses
    them and a list reads as plain paragraphs. This resolves a paragraph's numbering (direct or through its
    style) to the marker Word shows: a bullet, or the running number / letter / roman numeral of its level.
    """
    _ROMAN = [(1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'),
              (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')]

    def __init__(self, doc):
        self.fmt = {}
        self.start = {}
        self.counters = {}
        try:
            root = doc.part.numbering_part.element
            abstract = {}
            for an in root.findall(_W_NS + 'abstractNum'):
                aid = an.get(_W_NS + 'abstractNumId')
                for lvl in an.findall(_W_NS + 'lvl'):
                    il = int(lvl.get(_W_NS + 'ilvl') or 0)
                    nf = lvl.find(_W_NS + 'numFmt')
                    st = lvl.find(_W_NS + 'start')
                    st_val = st.get(_W_NS + 'val') if st is not None else None
                    abstract[(aid, il)] = (
                        nf.get(_W_NS + 'val') if nf is not None else 'decimal',
                        int(st_val) if st_val and st_val.isdigit() else 1,
                    )
            for num in root.findall(_W_NS + 'num'):
                nid = num.get(_W_NS + 'numId')
                an = num.find(_W_NS + 'abstractNumId')
                if an is None:
                    continue
                aid = an.get(_W_NS + 'val')
                for (a, il), (f, st) in abstract.items():
                    if a == aid:
                        self.fmt[(nid, il)] = f
                        self.start[(nid, il)] = st
        except Exception:
            pass

    @staticmethod
    def _num_pr(para):
        p_pr = para._element.find(_W_NS + 'pPr')
        num_pr = p_pr.find(_W_NS + 'numPr') if p_pr is not None else None
        style = para.style
        depth = 0
        while num_pr is None and style is not None and depth < 6:
            s_pr = style.element.find(_W_NS + 'pPr')
            num_pr = s_pr.find(_W_NS + 'numPr') if s_pr is not None else None
            style = style.base_style
            depth += 1
        if num_pr is None:
            return None, 0
        nid_el = num_pr.find(_W_NS + 'numId')
        il_el = num_pr.find(_W_NS + 'ilvl')
        nid = nid_el.get(_W_NS + 'val') if nid_el is not None else None
        il_val = il_el.get(_W_NS + 'val') if il_el is not None else None
        il = int(il_val) if il_val and il_val.isdigit() else 0
        if not nid or nid == '0':
            return None, 0
        return nid, il

    def _roman(self, n):
        out = ''
        for v, r in self._ROMAN:
            while n >= v:
                out += r
                n -= v
        return out

    def marker(self, para):
        """(marker, level) for a list paragraph, or ('', 0) for any other paragraph."""
        try:
            nid, il = self._num_pr(para)
        except Exception:
            return '', 0
        if nid is None or not para.text.strip():
            return '', 0
        fmt = self.fmt.get((nid, il), 'decimal')
        if fmt in ('bullet', 'none'):
            return ('•' if il == 0 else '◦'), il
        key = (nid, il)
        n = self.counters.get(key, self.start.get(key, 1) - 1) + 1
        self.counters[key] = n
        for k in list(self.counters):
            if k[0] == nid and k[1] > il:
                del self.counters[k]
        if fmt == 'lowerLetter':
            return f"{chr(97 + (n - 1) % 26)}.", il
        if fmt == 'upperLetter':
            return f"{chr(65 + (n - 1) % 26)}.", il
        if fmt == 'lowerRoman':
            return f"{self._roman(n)}.", il
        if fmt == 'upperRoman':
            return f"{self._roman(n).upper()}.", il
        return f"{n}.", il


def _docx_cell_text(cell, lister, rid_to_url, col_name="Gambar") -> str:
    """
    One table cell as a single markdown cell: each paragraph (with its Word list marker) on its own line,
    line breaks inside a paragraph kept as spaces, a nested table flattened row by row, images inline.
    """
    from docx.text.paragraph import Paragraph as _P
    from docx.table import Table as _T
    parts = []
    for child in cell._tc.iterchildren():
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            para = _P(child, cell)
            text = re.sub(r'\s+', ' ', para.text).strip()
            marker, _level = lister.marker(para)
            if text:
                parts.append(f"{marker} {text}" if marker else text)
            for r in child.xpath('.//a:blip/@r:embed'):
                if r in rid_to_url:
                    parts.append(f"![{col_name}]({rid_to_url[r]})")
        elif tag == 'tbl':
            for row in _T(child, cell).rows:
                vals = []
                prev = None
                for c in row.cells:
                    if c._tc is prev:
                        continue
                    prev = c._tc
                    v = _docx_cell_text(c, lister, rid_to_url, col_name).replace('<br/>', '; ')
                    if v:
                        vals.append(v)
                if vals:
                    parts.append(" — ".join(vals))
    return "<br/>".join(p.replace("|", "&#124;") for p in parts)


def _docx_table_grid(table, lister, rid_to_url) -> Optional[dict]:
    """
    A Word table read into rows of cell texts. A merged cell is written once (Word reports it under every grid
    column and row it spans) and full-width first rows are the table's titles. Returns {'text': ...} for a
    one-column table (a framed text box), {'titles', 'grid', 'n_cols'} for a real table, None when empty.
    """
    grid = []
    for row in table.rows:
        vals = []
        prev_tc = None
        tr = row._tr
        for c in row.cells:
            tc = c._tc
            # Repeated for each grid column of a horizontal merge, or handed down from the row above for a
            # vertical merge (the cell element then belongs to another row): its text is already written.
            if tc is prev_tc or tc.getparent() is not tr:
                vals.append("")
                prev_tc = tc
                continue
            prev_tc = tc
            vals.append(_docx_cell_text(c, lister, rid_to_url))
        grid.append(vals)
    grid = [r for r in grid if any(v.strip() for v in r)]
    if not grid:
        return None
    n_cols = max(len(r) for r in grid)
    grid = [r + [""] * (n_cols - len(r)) for r in grid]
    active = [ci for ci in range(n_cols) if any(r[ci].strip() for r in grid)]
    grid = [[r[ci] for ci in active] for r in grid]
    n_cols = len(active)
    if n_cols == 1:
        # A one-column table is a framed text box: its content is text, not a table
        return {"text": "\n\n".join(r[0].replace("<br/>", "\n") for r in grid)}
    titles = []
    while len(grid) >= 2 and sum(1 for v in grid[0] if v.strip()) == 1 and grid[0][0].strip():
        titles.append(grid[0][0].replace("<br/>", " "))
        grid = grid[1:]
    return {"titles": titles, "grid": grid, "n_cols": n_cols}


def _docx_continue_table(prev: dict, nxt: dict) -> bool:
    """
    A table Word split over a page break comes as a second table right after the first: same columns, no
    title of its own. Its rows are appended to the first; a first row with an empty label is the rest of the
    first table's last cell and is joined to it.
    """
    if not prev or not nxt or "grid" not in prev or "grid" not in nxt:
        return False
    if nxt["titles"] or nxt["n_cols"] != prev["n_cols"] or not nxt["grid"]:
        return False
    rows = list(nxt["grid"])
    if not rows[0][0].strip() and prev["grid"]:
        last = prev["grid"][-1]
        for ci in range(1, prev["n_cols"]):
            if rows[0][ci].strip():
                last[ci] = f"{last[ci]}<br/>{rows[0][ci]}" if last[ci].strip() else rows[0][ci]
        rows = rows[1:]
    prev["grid"].extend(rows)
    return True


def _docx_render_table(t: dict) -> str:
    """
    Markdown for a table read by _docx_table_grid. A clinical key-value table gets a neutral header instead of
    losing its first data row to it, and its titles (the topic it is about: the disease of a practice guideline)
    are top-level headings, so the heading of a previous chapter ('PENDAHULUAN') does not frame its rows.
    """
    if not t:
        return ""
    if "text" in t:
        return t["text"]
    grid, n_cols, titles = t["grid"], t["n_cols"], t["titles"]
    if not grid:
        return "".join(f"### {x}\n\n" for x in titles).strip()
    first_labelled = next((r for r in grid if r[0].strip()), grid[0])
    c0 = re.sub(r'<br/>|\s+', ' ', first_labelled[0]).strip().lower()
    is_key_value = n_cols == 2 and any(c0.startswith(k) for k in _CLINICAL_KEY_LABELS)
    if is_key_value:
        headers, body = ['Parameter / Aspek Klinis', 'Deskripsi / Rekomendasi'], grid
    else:
        headers = [h.replace("<br/>", " ") or f"Kolom {i + 1}" for i, h in enumerate(grid[0])]
        body = grid[1:]
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * n_cols) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in body]
    level = '#' if is_key_value else '###'
    prefix = "".join(f"{level} {x}\n\n" for x in titles)
    return prefix + "\n".join(out)


def _strip_signature_and_approval_blocks(pages: list) -> list:
    """
    Strips out bureaucratic signature blocks, 'Lembar Persetujuan', 'Lembar Pengesahan',
    and approval sheets from SOPs, clinical protocols, and official letters.
    Keeps actionable clinical procedures, monitoring, aftercare, and treatment guidelines.
    """
    if not pages:
        return pages

    approval_heading_pattern = re.compile(
        r'^(?:#{1,4}\s*)?(?:\d+[\.\)]\s*)?(?:PERSETUJUAN\s+DAN\s+TANDA\s+TANGAN|LEMBAR\s+(?:PENGESAHAN|PERSETUJUAN)|HALAMAN\s+PENGESAHAN|TANDA\s+TANGAN\s+(?:DAN\s+)?PENGESAHAN|TANDA\s+TANGAN|SIGNATURES?|APPROVAL\s+SHEET|SIGN-?OFF)\s*$',
        re.IGNORECASE
    )

    sig_table_header_pattern = re.compile(
        r'^(?:Dibuat\s+Oleh|Disiapkan\s+Oleh|Diajukan\s+Oleh)\s+(?:Diperiksa\s+Oleh|Diketahui\s+Oleh)?\s*(?:Disetujui\s+Oleh|Disahkan\s+Oleh)',
        re.IGNORECASE
    )

    letter_closing_pattern = re.compile(
        r'^(?:Hormat\s+kami|Mengetahui|Disetujui\s+oleh|Disahkan\s+oleh)\s*[,:]?\s*$',
        re.IGNORECASE
    )

    cleaned_pages = []

    for p_idx, page in enumerate(pages):
        text = page.get("text", "")
        if not text:
            cleaned_pages.append(page)
            continue

        lines = text.splitlines()

        # Check if the entire page is an approval sheet / lembar pengesahan
        page_first_lines = [l.strip() for l in lines[:6] if l.strip()]
        is_full_approval_page = any(
            re.match(r'^(?:#{1,3}\s*)?(?:LEMBAR\s+(?:PENGESAHAN|PERSETUJUAN)|HALAMAN\s+PENGESAHAN|APPROVAL\s+SHEET)\s*$', l, re.IGNORECASE)
            for l in page_first_lines
        ) and any(w in text.lower() for w in ["disetujui oleh", "diperiksa oleh", "tanda tangan", "mengetahui", "dibuat oleh"])

        if is_full_approval_page:
            logger.info(f"📋 Stripping entire approval sheet page {p_idx + 1}")
            continue

        cutoff_line = None
        for l_idx, line in enumerate(lines):
            clean = line.strip()
            # 1. Heading match
            if approval_heading_pattern.match(clean):
                following = [lines[j].strip() for j in range(l_idx + 1, min(l_idx + 20, len(lines))) if lines[j].strip()]
                following_text = " ".join(following).lower()
                if any(w in following_text for w in ["tanda tangan", "dibuat oleh", "disetujui oleh", "diperiksa oleh", "tanggal:", "terapis", "supervisor", "(___", "_____"]):
                    cutoff_line = l_idx
                    break
            # 2. Signature table header match without explicit section heading
            if sig_table_header_pattern.match(clean):
                cutoff_line = l_idx
                break
            # 3. Official letter closing signature match
            if letter_closing_pattern.match(clean):
                following = [lines[j].strip() for j in range(l_idx + 1, min(l_idx + 8, len(lines))) if lines[j].strip()]
                following_text = " ".join(following).lower()
                if any(w in following_text for w in ["(___", ".....", "direktur", "kepala", "manajer", "pic", "dokter", "terapis"]):
                    cutoff_line = l_idx
                    break

        if cutoff_line is not None:
            logger.info(f"📋 Stripping signature block on page {p_idx + 1} starting at line {cutoff_line + 1}: '{lines[cutoff_line].strip()}'")
            kept_lines = lines[:cutoff_line]
            kept_text = "\n".join(kept_lines).strip()
            if kept_text:
                new_page = dict(page)
                new_page["text"] = kept_text
                # Clean up any image URLs in page metadata that were exclusively in the stripped signature block
                if "image_urls" in new_page and isinstance(new_page["image_urls"], list):
                    valid_urls = [u for u in new_page["image_urls"] if u in kept_text]
                    new_page["image_urls"] = valid_urls
                    new_page["image_url"] = valid_urls[0] if valid_urls else None
                cleaned_pages.append(new_page)
        else:
            cleaned_pages.append(page)

    return cleaned_pages


def _is_valid_grid_table(table, page_height: float, page_width: float = 0.0) -> bool:
    """
    Validates whether a candidate table from PyMuPDF find_tables is an actual data table
    and not a false grouping of multi-column narrative paragraphs, full-slide canvas rectangles,
    or horizontal decorative rules.
    Supports clinical 2-column key-value tables and tables with spanning titles.
    """
    raw_data = table.extract()
    if not raw_data:
        return False

    # 1. Strip all-empty rows
    clean_rows = [r for r in raw_data if any(c and str(c).strip() for c in r)]
    if not clean_rows or len(clean_rows) < 2:
        return False

    # 2. Strip all-empty columns (e.g. padding/margin sub-columns from double borders)
    num_cols = len(clean_rows[0])
    active_cols = [ci for ci in range(num_cols) if any(r[ci] and str(r[ci]).strip() for r in clean_rows)]
    if len(active_cols) < 2:
        return False
    data = [[r[ci] for ci in active_cols] for r in clean_rows]

    # 2b. Check for full canvas / slide background rectangles detected as tables
    tbl_w = table.bbox[2] - table.bbox[0]
    tbl_h = table.bbox[3] - table.bbox[1]
    if page_width > 0 and page_height > 0:
        if table.bbox[0] <= 30 and table.bbox[1] <= 30 and (tbl_w >= page_width * 0.85 and tbl_h >= page_height * 0.85):
            return False

    # 2c. Check for letter-spaced kerning artifacts (e.g. C o m f o r t Y o u) caused by line projection
    for r in data:
        for c in r:
            c_str = str(c or '').strip()
            if re.search(r'\b[A-Za-z](?:\s+[A-Za-z]){4,}\b', c_str):
                return False

    # 2d. Check for staggered / isolated single-cell pseudo tables
    single_cell_rows = sum(1 for r in data if sum(1 for c in r if str(c or '').strip()) <= 1)
    if len(data) >= 2 and (single_cell_rows / len(data)) >= 0.70:
        return False

    # 2e. Check for diagonal 2-cell false tables
    if len(data) == 2 and len(data[0]) == 2:
        if (not str(data[0][0] or '').strip() and not str(data[1][1] or '').strip()) or \
           (not str(data[0][1] or '').strip() and not str(data[1][0] or '').strip()):
            return False

    # 3. Strip spanning title rows from header candidate (e.g. ['PANDUAN PRAKTIK KLINIS...', None])
    while len(data) >= 2:
        first_row_non_empty = [c for c in data[0] if c and str(c).strip()]
        if len(first_row_non_empty) == 1 and (len(data[0]) > 1 and not (data[0][1] and str(data[0][1]).strip())):
            data = data[1:]
        else:
            break

    if not data or len(data) < 2:
        return False

    # 4. Check if 2-column key-value / clinical / property table
    if len(data[0]) == 2 and len(data) >= 2:
        c0 = str(data[0][0] or '').strip().lower()
        clinical_keys = [
            'definisi', 'anamnesis', 'pemeriksaan', 'diagnosis', 'terapi',
            'edukasi', 'prognosis', 'komplikasi', 'faktor risiko', 'faktor resiko',
            'indikasi', 'kontraindikasi', 'parameter', 'fitur', 'karakteristik', 'tipe',
            'spesifikasi', 'nama', 'komposisi', 'kategori', 'harga', 'price', 'dosis',
            'instruksi', 'tahapan', 'langkah', 'persyaratan', 'kriteria'
        ]
        if any(c0.startswith(ck) for ck in clinical_keys):
            return True
        # Universal 2-column key-value check:
        # If column 0 consists of relatively concise labels/keys (<= 80 chars)
        # and has at least 2 non-empty rows, it is a valid 2-column specification table!
        c0_vals = [str(r[0] or '').strip() for r in data if r and len(r) >= 2]
        if c0_vals and all(len(v) < 80 for v in c0_vals) and sum(1 for v in c0_vals if v) >= 2:
            return True

    # 4b. Check for collapsed / deformed multi-row cells where PyMuPDF failed to detect inner row borders
    # (e.g. an entire multi-row table collapsed into 1 giant body row containing 3+ newlines and multiple colons)
    for r in data[1:]:
        for c in r:
            c_str = str(c or '').strip()
            if c_str.count('\n') >= 3 and (len(c_str.split()) > 15 or c_str.count(':') >= 2):
                return False
            if len(data) <= 2 and c_str.count('\n') >= 3:
                return False

    # 5. Multi-column table header check
    headers = [str(c or '').strip() for c in data[0]]
    cols = len(headers)
    rows = len(data)

    # If row 0 has multiple empty cells while row 1 has headers (e.g. Slide 40 or offset table)
    if len(data) > 1 and sum(1 for h in headers if not h) >= cols // 2:
        row1_headers = [str(c or '').strip() for c in data[1]]
        if sum(1 for h in row1_headers if h) > sum(1 for h in headers if h):
            headers = row1_headers
            data = data[1:]
            rows = len(data)

    empty_headers = sum(1 for h in headers if not h)
    # Allow empty first header in comparison tables (e.g. Slide 78 where col 0 is parameters)
    if not headers[0] and empty_headers == 1:
        empty_headers = 0

    if (empty_headers / cols) > 0.40:
        return False

    # Check header length: only reject if more than half of the headers are long narrative sentences (> 20 words)
    if cols > 2:
        long_headers = sum(1 for h in headers if len(h.split()) > 20)
        if long_headers >= (cols // 2 + 1):
            return False

    # Reject if header is a major section title
    section_kws = {'method', 'methods', 'abstract', 'introduction', 'results', 'discussion', 'conclusion', 'references'}
    for h in headers:
        if h.lower().strip() in section_kws:
            return False

    # Sparsity and narrative density check
    total_cells = rows * cols
    empty_cells = sum(1 for r in data for c in r if not str(c or '').strip())
    long_narrative = sum(1 for r in data for c in r if len(str(c or '').strip().split()) > 25)
    if total_cells >= 8 and (empty_cells / total_cells) > 0.70:
        return False

    tbl_height = table.bbox[3] - table.bbox[1]
    if page_height > 0 and (tbl_height / page_height) > 0.40 and long_narrative >= 2 and cols > 2:
        return False

    return True


def merge_sparse_split_rows(rows: list) -> list:
    """
    Merges adjacent rows in vector-extracted tables (PyMuPDF find_tables) where
    vertical bounding box offsets or product packaging images split a single logical row
    across multiple rows, leaving one row with non-empty cells on the left and empty on the right,
    and subsequent rows with empty cells on the left and non-empty on the right.
    """
    if not rows or len(rows) <= 1:
        return rows
    merged = []
    i = 0
    while i < len(rows):
        current = list(rows[i])
        while i + 1 < len(rows):
            next_row = rows[i + 1]
            overlap = False
            for c_curr, c_next in zip(current, next_row):
                val_c = str(c_curr or "").strip()
                val_n = str(c_next or "").strip()
                if val_c and val_n:
                    overlap = True
                    break
            curr_non_empty = sum(1 for c in current if str(c or "").strip())
            next_non_empty = sum(1 for c in next_row if str(c or "").strip())
            if not overlap and curr_non_empty > 0 and next_non_empty > 0:
                for ci in range(min(len(current), len(next_row))):
                    if not str(current[ci] or "").strip():
                        current[ci] = next_row[ci]
                i += 1
            else:
                break
        merged.append(current)
        i += 1
    return merged


_PUA_BULLET_RE = re.compile(r'\s*[\uE000-\uF8FF\u25AF\u25A1\uFFFD]+\s*')


def _format_slide_block_text(txt: str) -> str:
    """
    Restores list structure lost in slide PDFs: private-use bullet/checkmark glyphs
    (rendered as boxes) become '- ' items, and blocks made of several short, capitalised
    lines (checklists, 'Type I..VI' style rows) become bullet lists instead of one glued paragraph.
    """
    if not txt or txt.lstrip().startswith(('|', '#', '![')):
        return txt
    t = txt
    if _PUA_BULLET_RE.search(t):
        parts = [p.strip() for p in _PUA_BULLET_RE.split(t) if p.strip()]
        if len(parts) >= 2:
            lead = parts[0] if not _PUA_BULLET_RE.match(t) else None
            items = parts[1:] if lead else parts
            out = ([lead] if lead else []) + ["- " + re.sub(r'\s+', ' ', i) for i in items]
            return "\n".join(out)
        t = _PUA_BULLET_RE.sub(' ', t)
    lines = [l.strip() for l in t.split('\n') if l.strip()]
    if len(lines) >= 3 and all(len(l) < 100 for l in lines) and not any(re.match(r'^(?:[-*\u2022\u25CF]|\d+[\.\)])\s', l) for l in lines):
        items = _join_wrapped_lines(lines)
        upper_start = sum(1 for l in items if l[0].isupper() or l[0].isdigit())
        sentence_end = sum(1 for l in items if l.endswith(('.', ',', ';')))
        if len(items) >= 2 and upper_start / len(items) >= 0.7 and sentence_end / len(items) < 0.5:
            return "\n".join(f"- {l}" for l in items)
    return t


# A line ending in a word that needs what follows ('Oleskan anastesi topikal estesia dengan') wraps onto the next
_CONTINUES_RE = re.compile(
    r'(?:\b(?:dengan|dan|atau|yang|untuk|pada|di|ke|dari|sesuai|serta|seperti|sampai|hingga|agar|bila|jika|'
    r'the|and|or|of|with|to|for|in)|[,/&+\-])$',
    re.IGNORECASE,
)


def _merge_wrapped_blocks(blocks: list) -> list:
    """
    A slide text box whose lines the file stores as separate blocks ('Oleskan anastesi topikal estesia' /
    'dengan jumlah sesuai dengan indikasi') is one item: a block lying in the same column right below another one
    (their horizontal spans overlap, the vertical gap is under one line height, boxes of a slide may even overlap)
    that continues its sentence is joined to it. Both signs are needed, so a tight list of short items is not glued
    together; the column test keeps the boxes of a two-column flowchart apart, whatever order they come in.
    """
    def line_height(b):
        return max(b[3] - b[1], 1.0)

    merged = []
    for b in blocks:
        text = str(b[4] or "").replace('​', '').strip()
        target = None
        if text:
            for j in range(len(merged) - 1, -1, -1):
                prev = merged[j]
                prev_text = str(prev[4]).strip()
                overlap = min(prev[2], b[2]) - max(prev[0], b[0])
                narrower = max(min(prev[2] - prev[0], b[2] - b[0]), 1.0)
                gap = b[1] - prev[3]
                h = min(line_height(prev), line_height(b), 14)
                if (prev_text and overlap >= 0.5 * narrower and -h <= gap <= h
                        and (text[0].islower() or _CONTINUES_RE.search(prev_text))):
                    target = j
                    break
        if target is not None:
            prev = merged[target]
            merged[target] = (min(prev[0], b[0]), prev[1], max(prev[2], b[2]), max(prev[3], b[3]),
                              f"{str(prev[4]).strip()} {text}") + tuple(prev[5:])
        else:
            merged.append(tuple(b))
    return merged


def _join_wrapped_lines(lines: list) -> list:
    """
    The visual lines of one slide text box are one item: a line that continues the previous one (it starts in
    lower case, or the previous line ends in a joining word or a comma) is joined to it before items are listed.
    """
    joined = []
    for line in lines:
        if joined and (line[0].islower() or _CONTINUES_RE.search(joined[-1])):
            joined[-1] = f"{joined[-1]} {line}"
        else:
            joined.append(line)
    return joined


# A visual line that opens a new list item: a bullet glyph (also the private-use glyphs Symbol/Wingdings fonts
# use), a dash, an 'o' sub-bullet, or an enumerator such as '1.', 'a)', 'iv.', '(2)'.
_LIST_MARKER_RE = re.compile(
    r'^(?:[•●▪▫◦‣⁃∙■□◆➢✓✔-*\-–—]\s*'
    r'|o\s+(?=\S)'
    r'|(?:\d{1,2}|[a-zA-Z]|[ivxIVX]{2,4})[\.\)]\s+'
    r'|\(\s*(?:\d{1,2}|[a-zA-Z])\s*\)\s+)'
)
_GLYPH_BULLET_RE = re.compile(r'^[•●∙-]\s*')
_SUB_BULLET_RE = re.compile(r'^(?:o\s+|[◦▪▫]\s*)(?=\S)')


def _layout_lines(page_dict_blocks: list, rotation_matrix=None) -> list:
    """
    The visual lines of a text region as (x0, x1, text), top to bottom. Fragments the file stores as separate
    lines on one baseline (a bullet glyph and its text, punctuation drawn on its own) are one visual line,
    ordered left to right, so words keep their spaces and punctuation stays where it is printed.
    Coordinates are taken as the page is displayed (a rotated page's lines are turned upright first). Returns
    [] when the region holds text that does not run left to right, so the caller keeps the file's own order.
    """
    raw = []
    for b in page_dict_blocks:
        if b.get("type", 0) != 0:
            continue
        for l in b.get("lines", []):
            txt = "".join(s.get("text", "") for s in l.get("spans", []))
            if not txt.strip():
                continue
            x0, y0, x1, y1 = l["bbox"]
            dx, dy = l.get("dir", (1.0, 0.0))
            if rotation_matrix is not None:
                try:
                    import fitz
                    r = fitz.Rect(x0, y0, x1, y1) * rotation_matrix
                    x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
                    v = fitz.Point(dx, dy) * rotation_matrix - fitz.Point(0, 0) * rotation_matrix
                    dx, dy = v.x, v.y
                except Exception:
                    return []
            if dx < 0.9 or abs(dy) > 0.2:
                return []
            raw.append([x0, y0, x1, y1, txt, len(raw)])
    raw.sort(key=lambda r: ((r[1] + r[3]) / 2.0, r[0]))
    groups = []
    for r in raw:
        if groups:
            g = groups[-1]
            overlap = min(g["y1"], r[3]) - max(g["y0"], r[1])
            if overlap >= 0.5 * max(min(g["y1"] - g["y0"], r[3] - r[1]), 1.0):
                g["parts"].append(r)
                g["y0"], g["y1"] = min(g["y0"], r[1]), max(g["y1"], r[3])
                continue
        groups.append({"y0": r[1], "y1": r[3], "parts": [r]})
    # A single flowing column reads top to bottom in the file's own order too. When the file orders the lines
    # differently (several columns or callouts of a designed page in one block), its order is the reading
    # order and the region is left as the file has it.
    prev_max = -1
    for g in groups:
        idxs = [p[5] for p in g["parts"]]
        if min(idxs) < prev_max:
            return []
        prev_max = max(idxs)
    lines = []
    for g in groups:
        parts = sorted(g["parts"], key=lambda r: r[0])
        text = re.sub(r'\s+', ' ', " ".join(p[4].strip() for p in parts)).strip()
        text = text.replace('​', '')
        if text:
            lines.append((min(p[0] for p in parts), max(p[2] for p in parts), text))
    return lines


def _reflow_layout_items(lines: list) -> list:
    """
    Rebuilds the logical lines (paragraphs, list items) of a region from its visual lines, as (x0, text): a line
    continues the previous one when that line was wrapped (it runs to the right edge of the region), or when it
    starts in lower case / follows a joining word; a line that opens a list item, or follows a line that ended
    short of the edge, starts a new logical line. So a wrapped sentence is one item and a stack of short lines
    stays a stack.
    """
    if not lines:
        return []
    left = min(l[0] for l in lines)
    right = max(l[1] for l in lines)
    tol = max(0.12 * (right - left), 18.0)
    items = []
    prev_x1 = None
    for x0, x1, text in lines:
        if items and not _LIST_MARKER_RE.match(text):
            prev = items[-1][1]
            if prev_x1 >= right - tol or text[0].islower() or _CONTINUES_RE.search(prev):
                if prev.endswith('-') and len(prev) > 1 and prev[-2].isalpha() and text[0].isalpha():
                    items[-1][1] = prev + text
                else:
                    items[-1][1] = f"{prev} {text}"
                prev_x1 = x1
                continue
        items.append([x0, text])
        prev_x1 = x1
    out = []
    for x0, it in items:
        it = _GLYPH_BULLET_RE.sub('• ', it)
        it = _SUB_BULLET_RE.sub('◦ ', it).strip()
        if it:
            out.append((x0, it))
    return out


def _reflow_layout_lines(lines: list) -> list:
    return [t for _, t in _reflow_layout_items(lines)]


def _region_text_lines(page, rect) -> list:
    """Logical lines of the text inside `rect` (a table cell), rebuilt from the page layout."""
    try:
        import fitz
        d = page.get_text("dict", clip=fitz.Rect(rect))
        return _reflow_layout_lines(_layout_lines(d.get("blocks", [])))
    except Exception as e:
        logger.debug(f"Region text reflow failed: {e}")
        return []


def _table_cells_from_layout(page, table, raw_rows: Optional[list] = None) -> Optional[list]:
    """
    The rows of a detected grid table with each cell's text taken from the page layout instead of the table's
    character stream: that stream drops the spaces of justified text and moves punctuation onto lines of its own
    ('Kelainan rambut , , , . merupakan'). A list item keeps its wrapped lines on one line; a short label cell
    ('Anamnesis &' / 'Pemeriksaan Fisik') is one phrase. A cell whose layout cannot be read keeps the table's
    own text; a rotated page keeps it for the whole table. Returns None when the layout is not used.
    """
    try:
        if getattr(page, "rotation", 0):
            return None
        rows = []
        for ri, row in enumerate(table.rows):
            vals = []
            for ci, cell in enumerate(row.cells):
                if cell is None:
                    vals.append(None)
                    continue
                cl = _region_text_lines(page, cell)
                if cl and len(cl) > 1 and sum(len(x) for x in cl) <= 60 and not any(_LIST_MARKER_RE.match(x) for x in cl):
                    cl = [" ".join(cl)]
                if not cl:
                    raw_val = None
                    if raw_rows and ri < len(raw_rows) and ci < len(raw_rows[ri]):
                        raw_val = raw_rows[ri][ci]
                    vals.append(raw_val if raw_val is not None else "")
                    continue
                vals.append("\n".join(cl))
            rows.append(vals)
        return rows if rows else None
    except Exception as e:
        logger.debug(f"Layout table cell extraction failed: {e}")
        return None


def _block_display_text(b) -> str:
    """
    The text a page block contributes to the page: its reflowed text when one was built, else the file's.
    The file's own text (b[4]) stays what image titling, table de-duplication and SOP detection read.
    """
    return b[7] if len(b) > 7 and b[7] else b[4]


def _reflow_text_block(block_lines: list) -> str:
    """
    Text of one free-text block of a document page, one logical line per paragraph or list item. Paragraphs are
    separated by a blank line so they are never glued together downstream. A line printed indented under a list
    item ('4. Alopesia barbae' / its description) stays on the next line so it remains part of that item.
    """
    items = _reflow_layout_items(block_lines)
    if not items:
        return ""
    parts = [items[0][1]]
    item_x0 = items[0][0] if _LIST_MARKER_RE.match(items[0][1]) else None
    for x0, it in items[1:]:
        if _LIST_MARKER_RE.match(it):
            parts.append("\n" + it)
            item_x0 = x0
        elif item_x0 is not None and x0 > item_x0 + 4:
            parts.append("\n" + it)
        else:
            parts.append("\n\n" + it)
            item_x0 = None
    return "".join(parts)


def _format_slide_items_clean(items_to_render: list, slide_title: str = "") -> list:
    """
    Cleans up and formats slide items:
    1. Isolates price/size tags (IDR/Rp) from paragraph blocks into clean '**Harga / Ukuran:** ...'.
    2. Removes redundant slide title from text blocks if already present in slide header.
    3. Detects active ingredients and colon description blocks (: Function) under Bahan Aktif
       and pairs them into a neat Markdown table (| Bahan Aktif | Keterangan / Fungsi |).
    """
    if not items_to_render:
        return []

    norm_title = re.sub(r'\s+', ' ', slide_title or "").strip().lower()

    # 1. Isolate price/size tags that got bundled into paragraph blocks
    split_items = []
    price_tags = []
    for y, txt in items_to_render:
        clean_txt = str(txt or "").strip()
        lines = clean_txt.splitlines()
        filtered_lines = []
        for l in lines:
            l_str = l.strip()
            if re.match(r'^(?:IDR|Rp\.?)\s*[\d\.\,]+(?:\s*/\s*[\d\w\s]+)?$', l_str, re.IGNORECASE) or \
               re.match(r'^\d+\s*(?:gr|g|ml)\s*[-/]\s*(?:IDR|Rp\.?)?\s*[\d\.\,]+', l_str, re.IGNORECASE):
                if l_str not in price_tags:
                    price_tags.append(l_str)
            else:
                filtered_lines.append(l)

        new_txt = "\n".join(filtered_lines).strip()
        if new_txt:
            split_items.append((y, new_txt))

    # 2. Remove redundant title
    deduped_items = []
    for y, txt in split_items:
        clean_txt = txt.strip()
        norm_txt = re.sub(r'\s+', ' ', clean_txt).lower()
        if norm_title and norm_txt == norm_title and not clean_txt.startswith(('#', '|', '![')):
            continue
        deduped_items.append((y, clean_txt))

    # 3. Detect Bahan Aktif + active ingredients + colon function blocks
    final_items = []
    idx = 0
    while idx < len(deduped_items):
        y, txt = deduped_items[idx]
        norm_t = txt.lower().replace('#', '').strip()

        if norm_t in ("bahan aktif", "active ingredients"):
            final_items.append((y, "### Bahan Aktif"))
            curr = idx + 1
            ingred_lines = []
            while curr < len(deduped_items):
                _, next_txt = deduped_items[curr]
                lines = [l.strip() for l in next_txt.splitlines() if l.strip()]
                if any(l.startswith(':') for l in lines):
                    break
                norm_next = next_txt.lower().replace('#', '').strip()
                if norm_next in ("product information", "informasi produk", "cara pakai", "aturan pakai", "petunjuk penggunaan"):
                    break
                ingred_lines.extend(lines)
                curr += 1

            desc_lines = []
            while curr < len(deduped_items):
                _, next_txt = deduped_items[curr]
                lines = [l.strip() for l in next_txt.splitlines() if l.strip()]
                if not any(l.startswith(':') for l in lines):
                    break
                for l in lines:
                    if l.startswith(':'):
                        desc_lines.append(l.lstrip(':').strip())
                    elif desc_lines:
                        desc_lines[-1] += " " + l
                curr += 1

            if ingred_lines and desc_lines:
                # Merge wrapped ingredient lines (e.g. trailing comma or trailing &)
                merged_ingreds = []
                curr_ing = ""
                for ing in ingred_lines:
                    if curr_ing:
                        if curr_ing.endswith((',', '&')) or ing.startswith(('&', 'and', 'dan')) or ing.lower().startswith(('extract', 'ekstrak')):
                            curr_ing += " " + ing
                        else:
                            merged_ingreds.append(curr_ing)
                            curr_ing = ing
                    else:
                        curr_ing = ing
                if curr_ing:
                    merged_ingreds.append(curr_ing)

                rows = ["| Bahan Aktif | Keterangan / Fungsi |", "| --- | --- |"]
                if len(merged_ingreds) == len(desc_lines):
                    for ing, d in zip(merged_ingreds, desc_lines):
                        rows.append(f"| {ing.replace('|', '&#124;')} | {d.replace('|', '&#124;')} |")
                else:
                    max_len = max(len(merged_ingreds), len(desc_lines))
                    for k in range(max_len):
                        ing = merged_ingreds[k] if k < len(merged_ingreds) else "-"
                        d = desc_lines[k] if k < len(desc_lines) else "-"
                        rows.append(f"| {ing.replace('|', '&#124;')} | {d.replace('|', '&#124;')} |")

                final_items.append((y, "\n".join(rows)))
                idx = curr
                continue
            else:
                idx += 1
                continue

        final_items.append((y, txt))
        idx += 1

    if price_tags:
        final_items.append((9999.0, f"**Harga / Ukuran:** {', '.join(price_tags)}"))

    return final_items


def _looks_like_borderless_table(page) -> bool:
    """
    True when text lines on the page split into >=3 horizontally separated cells and
    >=3 lines share the same cell count (a table drawn without ruling lines).
    """
    try:
        words = page.get_text("words")
    except Exception:
        return False
    from collections import Counter
    rows = {}
    for w in words:
        rows.setdefault(round(w[1] / 4), []).append(w)
    counts = Counter()
    for ws in rows.values():
        ws.sort(key=lambda w: w[0])
        cells = 1
        for a, c in zip(ws, ws[1:]):
            if c[0] - a[2] > 18:
                cells += 1
        if cells >= 3:
            counts[cells] += 1
    return any(n >= 3 for n in counts.values())


def _extract_in_paragraph_tables(page, non_footers: list, h_lines: list) -> Tuple[list, set]:
    """
    Extracts in-paragraph open / academic three-line tables (e.g. Table 1, Table 2, Table 3)
    embedded within scientific papers and clinical reports.
    Reconstructs them as clean Markdown tables with captions and footnotes,
    and returns (academic_tables, consumed_block_indices).
    """
    import fitz
    academic_tables = []
    consumed = set()

    caption_candidates = []
    for bi, b in enumerate(non_footers):
        text = b[4].strip()
        first_line = text.splitlines()[0] if text else ''
        m = re.match(r'^(?:Table|Tabel)\s+(\d+)[\.:]\s*(.+)', first_line, re.I)
        if m:
            caption_candidates.append((bi, b, m.group(0).strip()))

    for ci, (c_bi, c_block, full_cap) in enumerate(caption_candidates):
        y0 = c_block[1]
        next_cap_y = caption_candidates[ci + 1][1][1] if ci + 1 < len(caption_candidates) else page.rect.height - 45
        candidates = [l for l in h_lines if l.y0 >= c_block[3] - 4 and l.y1 < next_cap_y]
        if not candidates:
            continue

        t_lines = [candidates[0]]
        for l in candidates[1:]:
            if l.y0 - t_lines[-1].y0 < 100:
                t_lines.append(l)
            else:
                break

        y_top = min(l.y0 for l in t_lines)
        y_bottom = max(l.y1 for l in t_lines)
        top_segs = [l for l in t_lines if abs(l.y0 - y_top) < 3]
        top_segs.sort(key=lambda s: s.x0)
        x0 = min(l.x0 for l in t_lines) - 4
        x1 = max(l.x1 for l in t_lines) + 4

        footnote = ''
        fn_b = None
        fn_bi = None
        for bi, b in enumerate(non_footers):
            if bi == c_bi or bi in consumed:
                continue
            if y_bottom - 2 <= b[1] <= y_bottom + 35:
                fl = b[4].strip().splitlines()[0]
                if re.match(r'^(?:\([+-]\)\s*:|\*|\†|Note:|\bKet\b|\bKeterangan\b)', fl, re.I):
                    footnote = fl
                    fn_b = b
                    fn_bi = bi
                    break

        tbl_rect = fitz.Rect(x0, y_top + 1.0, x1, y_bottom - 0.5)
        words = page.get_text('words', clip=tbl_rect)
        if fn_b:
            words = [w for w in words if w[3] <= fn_b[1] + 2]

        rows_dict = {}
        for w in words:
            y_mid = (w[1] + w[3]) / 2.0
            matched = None
            for ry in rows_dict:
                if abs(ry - y_mid) < 4:
                    matched = ry
                    break
            if matched is None:
                rows_dict[y_mid] = [w]
            else:
                rows_dict[matched].append(w)

        sorted_rys = sorted(rows_dict.keys())
        if len(sorted_rys) < 2:
            continue

        col_bounds = []
        if len(top_segs) >= 3:
            for i, seg in enumerate(top_segs):
                c_min = seg.x0 - 5
                c_max = seg.x1 + 5 if i == len(top_segs) - 1 else (seg.x1 + top_segs[i + 1].x0) / 2.0
                col_bounds.append((c_min, c_max))
        else:
            best_row = None
            max_items = 0
            for ry in sorted_rys:
                rw = sorted(rows_dict[ry], key=lambda x: x[0])
                if len(rw) > max_items:
                    max_items = len(rw)
                    best_row = rw
            if best_row and max_items >= 4:
                sym_idxs = [idx for idx, w in enumerate(best_row) if w[4] in ('+', '-', '–')]
                if sym_idxs:
                    first_sym_idx = sym_idxs[0]
                    label_end = best_row[first_sym_idx - 1][2]
                    sym_start = best_row[first_sym_idx][0]
                    col_bounds.append((x0, (label_end + sym_start) / 2.0))
                    for si in range(first_sym_idx, len(best_row)):
                        w = best_row[si]
                        c_min = col_bounds[-1][1]
                        c_max = x1 if si == len(best_row) - 1 else (w[2] + best_row[si + 1][0]) / 2.0
                        col_bounds.append((c_min, c_max))

        if not col_bounds or len(col_bounds) < 2:
            continue

        num_cols = len(col_bounds)
        rows_grid = []
        for ry in sorted_rys:
            rw = sorted(rows_dict[ry], key=lambda x: x[0])
            cells = [''] * num_cols
            for w in rw:
                w_mid = (w[0] + w[2]) / 2.0
                for ci, (cmin, cmax) in enumerate(col_bounds):
                    if cmin <= w_mid < cmax:
                        cells[ci] = (cells[ci] + ' ' + w[4]).strip()
                        break
            if any(cells):
                rows_grid.append(cells)

        if not rows_grid:
            continue

        header_lines = [l for l in t_lines if abs(l.y0 - y_top) > 5 and abs(l.y1 - y_bottom) > 5]
        y_hdr_sep = min(l.y0 for l in header_lines) if header_lines else None

        header_rows = []
        data_rows = []
        if y_hdr_sep is not None:
            for ry, cells in zip(sorted_rys, rows_grid):
                if ry <= y_hdr_sep + 3:
                    header_rows.append(cells)
                else:
                    data_rows.append(cells)
        else:
            header_rows = [rows_grid[0]]
            data_rows = rows_grid[1:]

        merged_headers = [''] * num_cols
        for hr in header_rows:
            for ci, val in enumerate(hr):
                if val:
                    if ci >= 3 and num_cols == 8:
                        nums = re.findall(r'\b\d+(?:\.\d+)?\b', val)
                        if nums:
                            merged_headers[ci] = f'{nums[-1]}%'
                            continue
                    merged_headers[ci] = (merged_headers[ci] + ' ' + val).strip()

        headers = [h.replace('|', '&#124;') if h else f'Kolom {ci+1}' for ci, h in enumerate(merged_headers)]
        aligns = [':---' if ci == 0 else ':---:' for ci in range(num_cols)]

        md_lines = [f'### {full_cap}', '', '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(aligns) + ' |']
        for dr in data_rows:
            clean_dr = [c.replace('|', '&#124;').replace('\n', '<br/>') for c in dr]
            md_lines.append('| ' + ' | '.join(clean_dr) + ' |')
        if footnote:
            md_lines.append('')
            md_lines.append(f'*{footnote}*')

        consumed.add(c_bi)
        if fn_bi is not None:
            consumed.add(fn_bi)
        for bi, b in enumerate(non_footers):
            if bi in consumed:
                continue
            b_cx = (b[0] + b[2]) / 2.0
            b_cy = (b[1] + b[3]) / 2.0
            if x0 - 5 <= b_cx <= x1 + 5 and y_top - 2 <= b_cy <= y_bottom + 10:
                consumed.add(bi)

        academic_tables.append({
            'y0': y0,
            'md': '\n\n' + '\n'.join(md_lines) + '\n\n',
            'bbox': (x0, y0, x1, y_bottom)
        })

    return academic_tables, consumed



# =========================================================================
# EXCEL DYNAMIC TOPOLOGY & CARD RENDERING HELPERS
# =========================================================================

def clean_cell_str(v: Any) -> str:
    """Cleans a cell value into a normalized string representation."""
    if v is None:
        return ""
    try:
        import datetime
        if isinstance(v, (datetime.datetime, datetime.date)):
            return v.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        import pandas as pd
        if pd.isna(v):
            return ""
        if isinstance(v, (pd.Timestamp,)):
            return v.strftime("%Y-%m-%d")
    except Exception:
        pass

    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if "![" in s:
        return s
    if s.lower() in ["nan", "none", "null"]:
        return ""
    if s.upper() in ["#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?", "#NUM!", "#NULL!"]:
        return ""
    # Strip trailing .0 from whole numbers formatted as float strings (e.g. '1.0' -> '1')
    if re.match(r'^\d+\.0+$', s):
        s = s.split('.')[0]
    return " ".join(s.split())


def is_likely_data_row(row: List[str]) -> bool:
    """Checks if a row contains data-like values (numbers, currencies, dates, booleans, images, dosages) rather than header labels."""
    non_empty = [c for c in row if c]
    if not non_empty:
        return False
    for val in non_empty:
        if "![" in val:
            return True
        v_low = val.lower().strip()
        if re.search(r'^(?:rp|\$|€|¥|\d+[\.,]\d+|\d+$)', v_low):
            return True
        if v_low in ["true", "false", "ya", "tidak"]:
            return True
        if re.search(r'^\d{4}-\d{2}-\d{2}$', v_low):
            return True
        if re.search(r'\b(?:\d+\s*(?:ml|gr|gram|mg|kg|cm|mm|%|jam|menit|mins?|kapsul|tablet|sachet|pcs|botol|ampul))\b', v_low):
            return True
        if len(val) > 80:
            return True
    return False


def infer_generic_headers(rows: List[List[str]], num_cols: int) -> List[str]:
    """Infers meaningful column headers when a table has no explicit header row."""
    inferred = []
    for c in range(num_cols):
        col_vals = [r[c].strip() for r in rows if c < len(r) and r[c].strip()]
        if not col_vals:
            inferred.append(f"Kolom {c+1}")
            continue
        text_vals = [v for v in col_vals if "![" not in v]
        # Check if numbering
        if text_vals and all(re.match(r'^\d+(?:\.0+)?$', v) for v in text_vals):
            inferred.append("No.")
        # Check if date
        elif text_vals and all(re.match(r'^\d{4}-\d{2}-\d{2}$', v) for v in text_vals):
            inferred.append("Tanggal")
        # Check if currency
        elif text_vals and all(re.match(r'^(?:rp|\$|€|¥|\d+[\.,]\d+)', v.lower()) for v in text_vals):
            inferred.append("Nilai/Harga")
        elif c == 1 and inferred and inferred[0] == "No.":
            inferred.append("Keterangan/Deskripsi")
        elif not text_vals and any("![" in v for v in col_vals):
            inferred.append("Lampiran/Gambar")
        else:
            inferred.append(f"Kolom {c+1}")
    return inferred


def detect_and_fuse_headers(trimmed_rows: List[List[str]]) -> Tuple[List[str], List[List[str]], int]:
    """
    Detects 1-tier, 2-tier, or 3-tier headers.
    Horizontally forward-fills category spans across blank columns.
    Fuses headers into clear, unambiguous column names.
    Returns (headers, body_rows, tier_count).
    """
    max_cols = max((len(r) for r in trimmed_rows), default=0)
    if not trimmed_rows or max_cols == 0:
        return [], [], 0

    max_header_candidates = min(3, len(trimmed_rows))
    header_rows: List[List[str]] = []

    for r_idx in range(max_header_candidates):
        row = [clean_cell_str(trimmed_rows[r_idx][c] if c < len(trimmed_rows[r_idx]) else "") for c in range(max_cols)]
        if is_likely_data_row(row):
            break
        if r_idx == 0:
            if sum(1 for v in row if v) < 1 or any("![" in v for v in row):
                break
        header_rows.append(row)

    if not header_rows:
        return [], trimmed_rows, 0

    num_tiers = len(header_rows)

    # Horizontal forward-fill for spanning headers across columns
    for tier in range(num_tiers - 1):
        curr_row = header_rows[tier]
        next_row = header_rows[tier + 1]

        active_label = ""
        for c in range(max_cols):
            if curr_row[c]:
                active_label = curr_row[c]
            elif active_label and next_row[c]:
                curr_row[c] = active_label
            elif not next_row[c]:
                active_label = ""

    # Check if multiple tiers actually contain distinct information
    r0 = header_rows[0]
    r0_non_empty = [v for v in r0 if v]
    # If row 0 is already a complete, unique column header covering all active columns, it's 1-tier
    if len(r0_non_empty) == max_cols and len(set(v.lower() for v in r0_non_empty)) == max_cols:
        num_tiers = 1
    elif num_tiers == 2:
        r1 = header_rows[1]
        r0_has_repeats = any(r0.count(v) > 1 and len(v) > 0 for v in set(r0))
        r1_has_labels = any(len(v) > 0 and v.lower() != r0[idx].lower() for idx, v in enumerate(r1))
        if not (r0_has_repeats or r1_has_labels):
            num_tiers = 1
    elif num_tiers == 3:
        r1 = header_rows[1]
        r2 = header_rows[2]
        r1_labels = any(len(v) > 0 and v.lower() != r0[idx].lower() for idx, v in enumerate(r1))
        r2_labels = any(len(v) > 0 and v.lower() != r1[idx].lower() for idx, v in enumerate(r2))
        if not r2_labels:
            num_tiers = 2 if r1_labels else 1
        elif not r1_labels:
            num_tiers = 1

    # Fuse header tiers
    fused_headers = []
    for c in range(max_cols):
        parts = []
        for t in range(num_tiers):
            val = header_rows[t][c]
            if val and (not parts or val.lower() != parts[-1].lower()):
                parts.append(val)
        if parts:
            fused_headers.append(" - ".join(parts))
        else:
            # If the column has image attachments in the body, label as Lampiran/Gambar
            has_body_images = any(c < len(r) and "![" in str(r[c]) for r in trimmed_rows[num_tiers:])
            if has_body_images:
                fused_headers.append("Lampiran/Gambar")
            else:
                fused_headers.append(f"Kolom {c+1}")

    body_rows = [[clean_cell_str(cell) for cell in row] for row in trimmed_rows[num_tiers:]]
    return fused_headers, body_rows, num_tiers


def propagate_visual_sparse_hierarchy(headers: List[str], body_rows: List[List[str]]) -> List[List[str]]:
    """
    Forward-fills leading categorical columns (Kategori, Case, Divisi, etc.)
    when authors leave visual blanks instead of using openpyxl merged cells.
    """
    if not body_rows or not headers:
        return body_rows

    HIERARCHY_KEYWORDS = [
        "kategori", "category", "case", "kasus", "divisi", "departemen",
        "jenis", "tipe", "kelompok", "group", "klasifikasi", "kondisi",
        "diagnosa", "indikasi", "grade", "derajat", "tingkat", "level",
        "concern", "kebutuhan", "target", "masalah", "tujuan"
    ]

    hierarchy_cols = []
    for c in range(min(4, len(headers))):
        h_low = headers[c].lower()
        if any(k in h_low for k in HIERARCHY_KEYWORDS):
            hierarchy_cols.append(c)
        elif c == 0:
            col0_vals = [r[0] for r in body_rows if len(r) > 0]
            non_empty_count = sum(1 for v in col0_vals if v)
            if 0 < non_empty_count < len(body_rows):
                hierarchy_cols.append(0)

    if not hierarchy_cols:
        return body_rows

    active_hierarchy: Dict[int, str] = {}
    filled_rows = []

    for r_vals in body_rows:
        row_copy = list(r_vals)
        has_other_data = any(row_copy[c] for c in range(len(row_copy)) if c not in hierarchy_cols)

        for c in hierarchy_cols:
            if c < len(row_copy) and row_copy[c]:
                active_hierarchy[c] = row_copy[c]
                for child_c in hierarchy_cols:
                    if child_c > c:
                        active_hierarchy.pop(child_c, None)
            elif c in active_hierarchy and has_other_data:
                row_copy[c] = active_hierarchy[c]

        filled_rows.append(row_copy)

    return filled_rows


def build_smart_card_title(headers: List[str], r_vals: List[str], row_idx: int) -> str:
    """
    Builds a human-readable, clinically and commercially accurate card title
    for ANY Excel table layout.
    """
    max_c = min(len(headers), len(r_vals))

    # 1. Identify Index Columns (No, No., #, ID)
    is_index_col0 = False
    if max_c > 0:
        h0_low = headers[0].lower().strip()
        v0 = r_vals[0].strip()
        if (h0_low in ["no", "no.", "nomor", "#", "id", "idx", "index", "kode"] or h0_low.startswith("no.")) and v0.isdigit():
            is_index_col0 = True

    # 2. Look for explicit Entity Name columns
    NAME_KEYWORDS = [
        "nama", "nama produk", "nama tindakan", "nama treatment", "nama obat",
        "treatment", "produk", "product", "layanan", "paket", "obat",
        "dokter", "cabang", "item", "prosedur", "protokol"
    ]
    name_col_idx = None
    for c in range(min(5, max_c)):
        if c == 0 and is_index_col0:
            continue
        h_low = headers[c].lower()
        if any(h_low == k or h_low.startswith(k + " ") or h_low.endswith(" " + k) for k in NAME_KEYWORDS):
            if r_vals[c].strip() and "![" not in r_vals[c]:
                name_col_idx = c
                break

    # 3. Look for Hierarchy columns
    HIERARCHY_KEYWORDS = [
        "kategori", "category", "case", "kasus", "divisi", "departemen",
        "jenis", "tipe", "diagnosa", "kondisi", "grade", "derajat", "tingkat"
    ]
    hierarchy_parts = []
    for c in range(min(4, max_c)):
        if c == 0 and is_index_col0:
            continue
        if c == name_col_idx:
            continue
        h_low = headers[c].lower()
        if any(k in h_low for k in HIERARCHY_KEYWORDS):
            val = r_vals[c].strip()
            if val and val != "-" and "![" not in val and val not in hierarchy_parts:
                hierarchy_parts.append(val)

    # 4. Assemble title components
    title_parts = []
    if hierarchy_parts:
        title_parts.extend(hierarchy_parts)
    if name_col_idx is not None:
        name_val = r_vals[name_col_idx].strip()
        if name_val and name_val not in title_parts:
            title_parts.append(name_val)

    # 5. Fallback: if no keywords matched, take first 1-2 non-empty text columns
    if not title_parts:
        start_c = 1 if is_index_col0 else 0
        for c in range(start_c, min(start_c + 2, max_c)):
            val = r_vals[c].strip()
            if val and val != "-" and not val.isdigit() and "![" not in val and len(val) <= 60:
                title_parts.append(val)

    # 6. Secondary Discriminator (Patient, Varian, Status, etc. - NOT instructions or notes!)
    DISCRIMINATOR_KEYWORDS = ["patient", "pasien", "tipe pasien", "status", "varian", "variant", "grade", "tingkat"]
    EXCLUDE_DISCRIMINATOR = ["instruksi", "catatan", "note", "keterangan", "deskripsi", "syarat", "tata cara", "panduan"]

    disc_val = ""
    for c in range(max_c):
        h_low = headers[c].lower()
        if any(k in h_low for k in DISCRIMINATOR_KEYWORDS) and not any(k in h_low for k in EXCLUDE_DISCRIMINATOR):
            val = r_vals[c].strip()
            if val and val != "-" and "![" not in val and len(val) <= 35 and val not in " > ".join(title_parts):
                disc_val = val
                break

    card_title = " > ".join(title_parts) if title_parts else f"Baris {row_idx+1}"
    if disc_val and disc_val not in card_title:
        card_title += f" ({disc_val})"

    return card_title


class DocumentParser:
    """
    Smart Document Parser with high-performance Fast Path:
    - Digital PDF: PyMuPDF / fitz (< 1s)
    - Flattened / Scanned PDF: FlattenedDesignParser (RapidOCR)
    - Word (.docx): python-docx
    - Spreadsheets (.xlsx, .xls, .csv): openpyxl & pandas with multi-tier fusion & sparse hierarchy propagation
    - Presentations (.pptx): python-pptx
    - Standalone images: Vision API (OpenAI / Gemini)
    - Legacy Docling fallback (optional / lazy-loaded if installed)
    """

    def __init__(self):
        logger.info("Initializing Smart DocumentParser (Fast Path & Adaptive Extraction)...")
        self._docling_converter = None  # Lazy-loaded only if needed and installed
        self.vision_cache = {}

    def _get_docling_converter(self):
        """Docling is deprecated and disabled. Returns None."""
        return None

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: DOCX
    # -------------------------------------------------------------------------
    def _parse_docx_fast(self, file_path: str) -> ParseResult:
        """Extract text from .docx using python-docx with heading hierarchy, inline images, and table structure."""
        from docx import Document as DocxDocument
        import re
        import os

        doc = DocxDocument(file_path)
        pages = []
        current_page_text = []
        page_num = 1

        # 1. Pre-extract and upload embedded images from docx relationships
        rid_to_url = {}
        rid_to_title = {}
        extracted_image_urls = []
        vision_cache = {}
        try:
            from app.services.storage import upload_image

            for rId, rel in doc.part.rels.items():
                if hasattr(rel, "target_ref") and "image" in str(rel.target_ref).lower() and hasattr(rel, "target_part"):
                    try:
                        img_bytes = rel.target_part.blob
                        is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not img_bytes:
                            continue

                        # Multimodal Vision Verification Gate
                        v_res = verify_and_classify_visual_candidate(
                            img_bytes=img_bytes,
                            img_ext=img_ext,
                            page_context=f"DOCX embedded image {rel.target_ref}",
                            fallback_title="",
                            cache=vision_cache
                        )
                        if not v_res.get("is_relevant", True) or v_res.get("classification") == "DECORATIVE":
                            logger.info(f"Vision Gate dropped decorative DOCX image: {rel.target_ref}")
                            continue

                        prod_title = v_res.get("product_name") or "Gambar"
                        clean_fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', prod_title)[:30].strip('_') if prod_title != "Gambar" else rId
                        fname = f"docx_img_{rId}_{clean_fname}.{img_ext}"
                        upload_res = upload_image(img_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            rid_to_url[rId] = img_url
                            rid_to_title[rId] = prod_title
                            extracted_image_urls.append(img_url)
                            logger.info(f"🖼️ Extracted and uploaded verified DOCX image '{rel.target_ref}' ({prod_title}) -> {img_url}")
                    except Exception as upload_err:
                        logger.debug(f"Failed uploading image for rId {rId}: {upload_err}")
        except Exception as img_init_err:
            logger.debug(f"DOCX rel image extraction error: {img_init_err}")

        # Fallback zip extraction if relationship extraction yielded nothing
        if not extracted_image_urls:
            try:
                import zipfile
                from app.services.storage import upload_image

                with zipfile.ZipFile(file_path, 'r') as z:
                    media_files = [f for f in z.namelist() if f.startswith('word/media/')]
                    for idx, media_name in enumerate(media_files, start=1):
                        img_bytes = z.read(media_name)
                        is_valid, clean_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not clean_bytes:
                            continue
                        v_res = verify_and_classify_visual_candidate(
                            img_bytes=clean_bytes,
                            img_ext=img_ext,
                            page_context=f"DOCX embedded media {media_name}",
                            fallback_title="",
                            cache=vision_cache
                        )
                        if not v_res.get("is_relevant", True) or v_res.get("classification") == "DECORATIVE":
                            continue
                        prod_title = v_res.get("product_name") or f"Gambar {idx}"
                        clean_fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', prod_title)[:30].strip('_')
                        fname = f"docx_img_{idx}_{clean_fname}.{img_ext}"
                        upload_res = upload_image(clean_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            extracted_image_urls.append(img_url)
            except Exception as zip_err:
                logger.debug(f"DOCX zip fallback image extraction skipped: {zip_err}")

        # 2. Walk the body in document order: paragraphs and tables interleaved, so each table stays under
        # the heading it belongs to (a practice guideline keeps its clinical tables under the disease title,
        # not after the bibliography). Word list numbering is rendered as list markers.
        lister = _DocxListRenderer(doc)

        def _para_images(p_el):
            blips = p_el.xpath('.//a:blip/@r:embed')
            return [f"![{rid_to_title.get(r, 'Gambar')}]({rid_to_url[r]})" for r in blips if r in rid_to_url]

        # The last table read is held back until real content follows it, so a table Word continued on the
        # next page (a second table right after it) is joined back into it.
        pending_table = [None]

        def _flush_table():
            if pending_table[0] is not None:
                md = _docx_render_table(pending_table[0])
                if md:
                    current_page_text.append("\n\n" + md + "\n\n")
                pending_table[0] = None

        def _emit_paragraph(para):
            nonlocal current_page_text, page_num
            text = para.text.strip()
            img_tags = _para_images(para._element)
            if text or img_tags:
                _flush_table()
            has_page_break = any(
                run._element.xml and "w:br" in run._element.xml and 'w:type="page"' in run._element.xml
                for run in para.runs
            )
            if has_page_break and current_page_text and pending_table[0] is None:
                pages.append({"page": page_num, "text": "\n\n".join(current_page_text)})
                current_page_text = []
                page_num += 1
            marker, _level = lister.marker(para)
            if text and marker:
                # A Word list item: numbered items keep their number, bullets become '- ' items
                current_page_text.append(f"{marker} {text}" if marker[0].isalnum() else f"- {text}")
            elif text:
                style_name = para.style.name.lower() if para.style else ""
                is_bold_para = para.runs and all(run.bold for run in para.runs if run.text.strip()) and len(text) < 120
                if "title" in style_name or "heading 1" in style_name:
                    current_page_text.append(f"# {text}")
                elif "heading 2" in style_name:
                    current_page_text.append(f"## {text}")
                elif "heading 3" in style_name or "heading 4" in style_name:
                    current_page_text.append(f"### {text}")
                elif re.match(r"^\d+\.\d+\s+", text):
                    current_page_text.append(f"### {text}")
                elif is_bold_para and not text.startswith("#") and not _LIST_MARKER_RE.match(text):
                    current_page_text.append(f"### {text}")
                else:
                    current_page_text.append(text)
            if img_tags:
                current_page_text.append("\n\n".join(img_tags))

        def _emit_table(table):
            t = _docx_table_grid(table, lister, rid_to_url)
            if t is None:
                return
            if _docx_continue_table(pending_table[0], t):
                return
            _flush_table()
            pending_table[0] = t

        from docx.text.paragraph import Paragraph as _DocxParagraph
        from docx.table import Table as _DocxTable

        def _walk(container_el, parent):
            for child in container_el.iterchildren():
                tag = child.tag.split('}')[-1]
                if tag == 'p':
                    _emit_paragraph(_DocxParagraph(child, parent))
                elif tag == 'tbl':
                    _emit_table(_DocxTable(child, parent))
                elif tag in ('sdt', 'customXml'):
                    content = child.find(_W_NS + 'sdtContent')
                    _walk(content if content is not None else child, parent)

        _walk(doc.element.body, doc._body)
        _flush_table()

        # Flush remaining text
        if current_page_text:
            pages.append({"page": page_num, "text": "\n\n".join(current_page_text)})

        if extracted_image_urls and pages:
            pages[0]["image_urls"] = extracted_image_urls
            pages[0]["image_url"] = extracted_image_urls[0]

        pages = _strip_references_from_pages(pages)
        pages = _strip_signature_and_approval_blocks(pages)
        return ParseResult(pages=pages, method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: TXT
    # -------------------------------------------------------------------------
    def _parse_txt_fast(self, file_path: str) -> ParseResult:
        """Extract text from .txt file (instant)."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return ParseResult(pages=[{"page": 1, "text": content}], method="fast")

    # -------------------------------------------------------------------------
    # NAIVE EXTRACTION: PDF (Scenario A: No OCR, No Vision, No Layout Heuristics)
    # -------------------------------------------------------------------------
    def _parse_pdf_naive(self, file_path: str) -> Optional[ParseResult]:
        """
        Skenario A: Naive raw text extraction without OCR, without Vision LLM,
        without 2-column or slide deck reconstruction, and without product image binding.
        """
        import fitz
        try:
            doc = fitz.open(file_path)
            pages = []
            for i, page in enumerate(doc):
                raw_text = page.get_text("text") or ""
                pages.append({
                    "page": i + 1,
                    "text": raw_text.strip(),
                    "images": []
                })
            doc.close()
            return ParseResult(pages=pages, method="fast")
        except Exception as e:
            logger.error(f"Naive PDF extraction failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: PDF (with scanned detection)
    # -------------------------------------------------------------------------
    def _parse_pdf_fast(self, file_path: str, max_pages: int = 1000) -> Optional[ParseResult]:
        """
        Extract text and embedded images from PDF using PyMuPDF (fitz).
        Features:
        - 2-Column journal layout detection (reads left column first, then right column)
        - Memory safeguard for long PDFs (max_pages cap + per-page text limits)
        - Fault-tolerant per-page extraction (corrupted pages don't abort entire file)
        - Extracts embedded images and links them with nearby product names
        """
        import fitz  # PyMuPDF
        import re
        from app.services.storage import upload_images_parallel

        try:
            doc = fitz.open(file_path)
        except Exception as open_err:
            logger.error(f"Failed to open PDF file {file_path}: {open_err}")
            return None

        total_pages = len(doc)
        if total_pages > max_pages:
            logger.warning(f"PDF exceeds max_pages ({total_pages} > {max_pages}). Processing first {max_pages} pages for memory stability.")
            num_pages = max_pages
        else:
            num_pages = total_pages

        pages = []
        total_chars = 0
        pages_with_text = 0
        upload_batch = []
        page_layouts = []

        # Slide-Deck presentation format detection (16:9 / 4:3 landscape)
        sample_pages = min(10, num_pages)
        landscape_count = sum(1 for pi in range(sample_pages) if doc[pi].rect.width > doc[pi].rect.height * 1.2)
        is_slide_deck = (landscape_count / sample_pages) >= 0.7 if sample_pages > 0 else False
        if is_slide_deck:
            logger.info(f"📊 Detected Slide-Deck presentation format ({num_pages} slides). Applying slide card layout & template header filtering.")

        def _extract_slide_title(p) -> str:
            try:
                d = p.get_text("dict")
                spans = []
                for b in d.get("blocks", []):
                    if "lines" in b:
                        for l in b["lines"]:
                            for s in l["spans"]:
                                t = s["text"].strip()
                                if not t or len(t) < 3 or t.isdigit():
                                    continue
                                if any(t.lower().startswith(x) for x in ["idr ", "rp", "halaman", "page", "product info", "bahan aktif", "cara pakai"]):
                                    continue
                                spans.append((s["size"], t, s["bbox"]))
                if not spans:
                    return ""
                max_size = max(s[0] for s in spans)
                top_spans = [s for s in spans if s[0] >= max_size * 0.9]
                top_spans.sort(key=lambda s: (s[2][1], s[2][0]))
                title_parts = []
                for s in top_spans:
                    if s[1] not in title_parts:
                        title_parts.append(s[1])
                return " ".join(title_parts[:3]).strip()
            except Exception:
                return ""

        url_by_xref = {}
        url_by_step = {}
        vision_cache = self.vision_cache

        def _flush_upload_batch():
            nonlocal upload_batch
            if not upload_batch:
                return
            try:
                results = upload_images_parallel(upload_batch)
                for item, res in zip(upload_batch, results):
                    img_url = res.get("image_url")
                    p_idx = item["page_index"]
                    fname = item["img_fname"]
                    prod_name = item.get("product_name") or fname
                    xref = item.get("xref")
                    step_num = item.get("step_num")

                    if img_url:
                        if xref:
                            url_by_xref[xref] = img_url
                        if step_num is not None:
                            url_by_step[(p_idx, step_num)] = img_url

                        if p_idx < len(pages):
                            if "image_urls" not in pages[p_idx]:
                                pages[p_idx]["image_urls"] = []
                            if "images" not in pages[p_idx]:
                                pages[p_idx]["images"] = []
                            pages[p_idx]["image_urls"].append(img_url)
                            is_fig = bool(re.match(r'^(?:figure|fig\.|gambar|diagram|bagan|grafik)', prod_name, re.IGNORECASE)) or (step_num is not None)
                            pages[p_idx]["images"].append({
                                "id": f"img_p{p_idx+1}_{len(pages[p_idx]['images'])+1}",
                                "url": img_url,
                                "product_name": prod_name,
                                "caption": prod_name,
                                "role": item.get("role") or ("FIGURE" if is_fig else "PRODUCT_PACKAGING"),
                                "x_mid": item.get("x_mid", 0.0),
                                "y_mid": item.get("y_mid", 0.0),
                                "xref": xref
                            })
            except Exception as flush_err:
                logger.warning(f"Error flushing image batch to MinIO: {flush_err}")
            finally:
                upload_batch = []
                import gc
                gc.collect()

        from app.rag.router import CURRENT_INGESTION_ID, is_ingestion_cancelled
        ingestion_id = CURRENT_INGESTION_ID.get()
        for i in range(num_pages):
            # A cancelled (deleted) document stops here instead of spending vision calls on its remaining pages;
            # the ingestion task discards the partial result.
            if ingestion_id and is_ingestion_cancelled(ingestion_id):
                logger.info(f"🛑 [PDF-FAST] '{ingestion_id}' was cancelled; stopping at page {i + 1}/{num_pages}.")
                break
            try:
                page = doc[i]
                page_width = page.rect.width
                page_height = page.rect.height
                midpoint = page_width / 2.0
                slide_title = _extract_slide_title(page) if is_slide_deck else ""

                blocks = page.get_text("blocks")
                if not is_slide_deck:
                    # A document page's text blocks are rebuilt from their line layout: wrapped lines of a
                    # paragraph or list item are one line, short stacked lines (a score scale, a list printed
                    # without glyphs) stay separate, so neither gets turned into the other downstream.
                    try:
                        # Matched by position: the two listings number blocks differently (image blocks count
                        # in one of them only).
                        dict_by_box = {
                            tuple(round(v) for v in db["bbox"]): db
                            for db in page.get_text("dict").get("blocks", []) if db.get("type", 0) == 0
                        }
                        rebuilt = []
                        for b in blocks:
                            db = dict_by_box.get(tuple(round(v) for v in b[:4])) if len(b) >= 7 and b[6] == 0 else None
                            if db is not None:
                                new_txt = _reflow_text_block(_layout_lines([db], page.rotation_matrix if page.rotation else None))
                                if new_txt:
                                    b = tuple(b[:7]) + (new_txt,)
                            rebuilt.append(b)
                        blocks = rebuilt
                    except Exception as reflow_err:
                        logger.debug(f"Text block reflow on page {i+1}: {reflow_err}")
                text_blocks = [b for b in blocks if len(b) >= 5 and b[4].strip() and (len(b) < 7 or b[6] == 0)]
                footers = [b for b in text_blocks if b[1] > page_height - 45]
                non_footers = [b for b in text_blocks if b[1] <= page_height - 45]

                # 1. Grid Tables detection (lines strategy) with validation
                grid_tables = []
                consumed_indices = set()
                try:
                    tabs = page.find_tables(strategy="lines", snap_x_tolerance=8, join_x_tolerance=8)
                    for t in tabs.tables:
                        if not _is_valid_grid_table(t, page_height, page_width):
                            continue
                        raw_data = t.extract()
                        if not raw_data:
                            continue
                        layout_data = _table_cells_from_layout(page, t, raw_data)
                        if layout_data and len(layout_data) == len(raw_data) and all(len(a) == len(b) for a, b in zip(layout_data, raw_data)):
                            raw_data = layout_data

                        # 1. Clean all-empty rows
                        clean_rows = [r for r in raw_data if any(c and str(c).strip() for c in r)]
                        if not clean_rows or len(clean_rows) < 2:
                            continue

                        # 2. Clean all-empty columns (e.g. padding sub-columns from double borders)
                        num_cols = len(clean_rows[0])
                        active_cols = [ci for ci in range(num_cols) if any(r[ci] and str(r[ci]).strip() for r in clean_rows)]
                        if len(active_cols) < 2:
                            continue
                        data = [[r[ci] for ci in active_cols] for r in clean_rows]

                        # 3. Detect spanning title rows
                        spanning_titles = []
                        spanning_lead_text = []
                        while len(data) >= 2:
                            first_row_non_empty = [c for c in data[0] if c and str(c).strip()]
                            if len(first_row_non_empty) == 1 and (len(data[0]) > 1 and not (data[0][1] and str(data[0][1]).strip())):
                                spanning_titles.append(first_row_non_empty[0].strip().replace('\n', ' '))
                                data = data[1:]
                            else:
                                break

                        if not data:
                            continue

                        # 4. Check if remaining data is a 2-column key-value clinical table
                        is_key_value = False
                        if len(data[0]) == 2 and len(data) >= 2:
                            clinical_keys = [
                                'definisi', 'anamnesis', 'pemeriksaan', 'diagnosis', 'terapi',
                                'edukasi', 'prognosis', 'komplikasi', 'faktor risiko', 'faktor resiko',
                                'indikasi', 'kontraindikasi', 'parameter', 'fitur', 'karakteristik', 'tipe',
                                'kriteria', 'klasifikasi', 'tata laksana', 'tatalaksana', 'penatalaksanaan'
                            ]
                            # A table continued from the previous page opens with the rest of that page's last
                            # cell (empty label); its first labelled row decides the table's kind.
                            first_labelled = next((r for r in data if str(r[0] or '').strip()), data[0])
                            c0 = re.sub(r'\s+', ' ', str(first_labelled[0] or '')).strip().lower()
                            if any(c0.startswith(ck) for ck in clinical_keys):
                                is_key_value = True

                        if is_key_value:
                            headers = ['Parameter / Aspek Klinis', 'Deskripsi / Rekomendasi']
                            body_data = data
                        else:
                            raw_headers = [re.sub(r'\s+', ' ', str(c or '')).strip().replace('|', '&#124;') for c in data[0]]
                            if len(data) > 1 and sum(1 for h in raw_headers if not h) >= len(raw_headers) // 2:
                                row1_headers = [re.sub(r'\s+', ' ', str(c or '')).strip().replace('|', '&#124;') for c in data[1]]
                                if sum(1 for h in row1_headers if h) > sum(1 for h in raw_headers if h):
                                    # The sparse first row is not thrown away: it is the end of a cell
                                    # continued from the previous page, kept as text right above the table.
                                    lead_text = "\n".join(str(c).strip() for c in data[0] if c and str(c).strip())
                                    if lead_text:
                                        spanning_lead_text.append(lead_text)
                                    raw_headers = row1_headers
                                    data = data[1:]
                            headers = []
                            for ci, h in enumerate(raw_headers):
                                if not h:
                                    headers.append('Parameter' if ci == 0 else f'Kolom {ci+1}')
                                else:
                                    headers.append(h)
                            body_data = data[1:]

                        aligns = ['---'] * len(headers)
                        merged_raw_rows = merge_sparse_split_rows(body_data)
                        rows = []
                        for r in merged_raw_rows:
                            clean_row = []
                            for c in r:
                                val = str(c or '').strip().replace('|', '&#124;')
                                val = re.sub(r'_{4,}', '-', val)
                                val_lines = [vl.strip() for vl in val.splitlines() if vl.strip()]
                                val_formatted = '<br>'.join(val_lines)
                                clean_row.append(val_formatted)
                            if len(clean_row) < len(headers):
                                clean_row.extend([''] * (len(headers) - len(clean_row)))
                            rows.append('| ' + ' | '.join(clean_row[:len(headers)]) + ' |')

                        title_prefix = ''
                        if spanning_titles:
                            # Titles spanning a clinical key-value table name the topic the table is about
                            # (the disease of a practice guideline): they open a section, so a heading left
                            # over from the previous topic ('Bagan Alur') no longer frames these rows.
                            t_level = '#' if is_key_value else '###'
                            title_prefix = '\n\n' + '\n\n'.join(f'{t_level} {st}' for st in spanning_titles) + '\n\n'
                        if spanning_lead_text:
                            title_prefix = '\n\n' + '\n\n'.join(spanning_lead_text) + '\n\n' + title_prefix

                        md_table = title_prefix + '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(aligns) + ' |\n' + '\n'.join(rows) + '\n\n'
                        grid_tables.append({
                            "y0": t.bbox[1],
                            "md": md_table,
                            "bbox": t.bbox
                        })
                        for bi, b in enumerate(non_footers):
                            b_cx = (b[0] + b[2]) / 2.0
                            b_cy = (b[1] + b[3]) / 2.0
                            if t.bbox[0] - 5 <= b_cx <= t.bbox[2] + 5 and t.bbox[1] - 5 <= b_cy <= t.bbox[3] + 5:
                                consumed_indices.add(bi)
                except Exception as tab_err:
                    logger.debug(f"Table detection on page {i+1}: {tab_err}")

                # 1a. Designed card-grid pages (cheatsheets / protocol cards laid out in visual columns).
                # Rebuild each card independently so neighbouring columns are never interleaved.
                card_grid_detected = False
                if not grid_tables:
                    try:
                        from app.rag.utils.card_layout import extract_card_grid_markdown
                        card_md = extract_card_grid_markdown(page, slide_title=slide_title)
                        if card_md:
                            grid_tables.append({
                                "y0": 0.0,
                                "md": card_md,
                                "bbox": [0, 0, page_width, page_height]
                            })
                            consumed_indices.update(range(len(non_footers)))
                            card_grid_detected = True
                            logger.info(f"🗂️ Page {i+1}: card-grid layout reconstructed deterministically.")
                    except Exception as card_err:
                        logger.debug(f"Card-grid extraction on page {i+1}: {card_err}")

                # 1b. In-paragraph open academic tables (Table 1, Table 2, Table 3, etc.)
                if not card_grid_detected:
                    try:
                        drawings = page.get_drawings()
                        h_lines = [d["rect"] for d in drawings if d.get("rect") and d["rect"].height <= 3 and d["rect"].width > 50]
                        h_lines.sort(key=lambda r: r.y0)
                        acad_tables, acad_consumed = _extract_in_paragraph_tables(page, non_footers, h_lines)
                        consumed_indices.update(acad_consumed)
                        grid_tables.extend(acad_tables)
                    except Exception as acad_err:
                        logger.debug(f"Academic table extraction on page {i+1}: {acad_err}")

                # 1c. Multimodal Vision Transcription for Visual Infographic Slides & Tables
                # Handles designed slides where tables/matrices are drawn with shapes, icons (check/cross),
                # multi-column product grids, combination guides (SERUM YES/NO), decision trees, or FAQ matrices.
                is_sparse_or_split = False
                is_deformed_or_collapsed = False
                if grid_tables:
                    for gt in grid_tables:
                        md = gt.get("md", "")
                        # Check for empty cell runs like | | | | | | or fragmented pipe runs
                        if re.search(r'(?:\|\s*){4,}\|', md) or re.search(r'\|\s*\|\s*\|\s*\|\s*\|', md):
                            is_sparse_or_split = True
                            break
                        # Check for collapsed cells with multiple <br> breaks combining separate rows/parameters
                        if md.count("<br>") >= 4 and any(k in md.lower() for k in [":", "mm", "hz", "nm"]):
                            is_deformed_or_collapsed = True
                            break

                nearby_context = " ".join(b[4].strip() for b in non_footers[:8])
                has_infographic_kw = any(kw in nearby_context.lower() for kw in [
                    "yes/no", "faq", "skin type matrix", "kombinasi", "combination",
                    "hypoallergenic", "ph balance", "fragrance free",
                    "alcohol free", "non comedogenic", "regimen",
                    "ultraformer", "mpt", "new services", "perbedaan", "concern", "what's your",
                    "panduan pencampuran", "pilihan", "comparison", "komparasi",
                    "karakteristik", "characteristics", "spesifikasi", "specifications", "specification",
                    "parameter", "wavelength", "spot size", "pulse rate", "beam delivery",
                    "handpiece", "fitur", "feature", "matrix", "matriks"
                ])
                drawings_count = len(page.get_drawings())
                has_images = len(page.get_images()) > 0
                has_generic_header = any("| Kolom 1 |" in gt.get("md", "") for gt in grid_tables)
                is_borderless_tabular = is_slide_deck and (not grid_tables or has_generic_header) and _looks_like_borderless_table(page)

                is_product_spec_slide = is_slide_deck and any(k in nearby_context.lower() for k in [
                    "bahan aktif", "active ingredients", "cara pakai", "aturan pakai", "informasi lain"
                ]) and not any(k in nearby_context.lower() for k in [
                    "perbedaan", "comparison", "komparasi", "kombinasi", "yes/no", "regimen", "tahapan treatment", "prosedur"
                ])

                should_try_vision_table = is_slide_deck and not is_product_spec_slide and (
                    (not grid_tables and (has_infographic_kw or (drawings_count >= 15 and any(k in nearby_context.lower() for k in ["perbedaan", "concern", "comparison", "kombinasi", "yes/no"])) or (has_images and any(k in nearby_context.lower() for k in ["perbedaan", "concern", "comparison", "kombinasi", "yes/no", "karakteristik", "characteristics", "spesifikasi"]))))
                    or is_sparse_or_split
                    or is_deformed_or_collapsed
                    or is_borderless_tabular
                )

                if should_try_vision_table:
                    v_table_md = transcribe_visual_infographic_slide(
                        page=page,
                        page_context=f"Slide {i+1}: {slide_title}. {nearby_context}",
                        cache=vision_cache
                    )
                    if v_table_md and "|" in v_table_md:
                        # If replacing a sparse/split/deformed table, replace it in grid_tables
                        if (is_sparse_or_split or is_deformed_or_collapsed or has_generic_header) and grid_tables:
                            grid_tables[0]["md"] = f"\n\n{v_table_md}\n\n"
                        else:
                            grid_tables.append({
                                "y0": 120.0,
                                "md": f"\n\n{v_table_md}\n\n",
                                "bbox": [0, 0, page_width, page_height]
                            })
                        # Consume non-footer text blocks that appear inside or match table content
                        # to prevent duplicate fragmented dumping of table text
                        for bi, b in enumerate(non_footers):
                            b_text = b[4].strip()
                            if b_text and (
                                b_text in v_table_md
                                or any(w.strip() in v_table_md for w in b_text.splitlines() if len(w.strip()) > 3)
                            ):
                                consumed_indices.add(bi)

                # 2. Extract embedded images info on this page
                img_infos = page.get_image_info(xrefs=True)
                if not img_infos:
                    raw_imgs = page.get_images()
                    img_infos = [{"xref": im[0], "bbox": [0, 0, 0, 0]} for im in raw_imgs if len(im) > 0]

                # 3. Detect SOP / Procedural Step Cards with Illustrations
                sop_step_data = None
                step_candidates = []
                for bi, b in enumerate(non_footers):
                    if bi in consumed_indices:
                        continue
                    first_line = b[4].strip().splitlines()[0]
                    m = re.match(r'^(?:Step\s+)?(\d+)[\.\:]\s*(.+)', first_line, re.IGNORECASE)
                    if m:
                        num = int(m.group(1))
                        title = m.group(2).strip()
                        # Exclude major document section titles
                        if any(k in title.lower() for k in [
                            'tujuan', 'ruang lingkup', 'persiapan', 'rangkaian',
                            'monitoring', 'aftercare', 'dokumentasi', 'persetujuan'
                        ]):
                            continue
                        b_lower = b[4].lower()
                        if 'prosedur' in b_lower or 'procedure' in b_lower or 'catatan' in b_lower:
                            step_candidates.append({'num': num, 'title': title, 'block': b, 'bi': bi})

                step_img_xrefs = {}
                if step_candidates and len(img_infos) > 0:
                    step_candidates.sort(key=lambda s: s["block"][1])
                    sorted_imgs = sorted(img_infos, key=lambda im: im.get('bbox', [0, 0, 0, 0])[1])

                    step_rows = []
                    for si, s in enumerate(step_candidates):
                        consumed_indices.add(s["bi"])
                        b = s["block"]
                        lines = [l.strip() for l in b[4].splitlines() if l.strip()]
                        proc_lines = []
                        for l in lines[1:]:
                            if l.lower() in ("prosedur", "procedure", "instruksi"):
                                continue
                            proc_lines.append(l)
                        proc_text = " ".join(proc_lines)

                        y_next = step_candidates[si+1]["block"][1] if si+1 < len(step_candidates) else page_height - 45
                        notes_text = "-"
                        for nbi, nb in enumerate(non_footers):
                            if nbi in consumed_indices:
                                continue
                            if nb[1] >= b[1] and nb[1] < y_next:
                                if "catatan" in nb[4].lower():
                                    consumed_indices.add(nbi)
                                    nb_lines = [l.strip() for l in nb[4].splitlines() if l.strip() and not l.startswith("___")]
                                    sub = [l for l in nb_lines if l.lower() not in ("catatan", "note", "notes", "keterangan")]
                                    if sub:
                                        notes_text = " ".join(sub)

                        # Match image by vertical overlap or index
                        img_item = None
                        s_top = b[1] - 30
                        s_bottom = y_next + 10
                        for im in sorted_imgs:
                            ib = im.get("bbox", [0, 0, 0, 0])
                            im_y_mid = (ib[1] + ib[3]) / 2.0
                            if s_top <= im_y_mid <= s_bottom:
                                img_item = im
                                break
                        if not img_item and si < len(sorted_imgs) and len(sorted_imgs) == len(step_candidates):
                            img_item = sorted_imgs[si]

                        xref = img_item["xref"] if img_item else None
                        step_dict = {
                            "num": s["num"],
                            "title": s["title"],
                            "procedure": proc_text,
                            "notes": notes_text,
                            "xref": xref,
                            "y0": b[1]
                        }
                        if xref:
                            step_img_xrefs[xref] = step_dict
                        step_rows.append(step_dict)

                    if step_rows:
                        sop_step_data = {
                            "y0": step_rows[0]["y0"],
                            "steps": step_rows
                        }

                # 4. Prepare image upload info for this page
                seen_xrefs = set()
                gate_candidates = []
                for img_idx, im in enumerate(img_infos):
                    xref = im.get("xref")
                    if not xref or xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)

                    bbox = im.get("bbox", [0, 0, 0, 0])
                    # In slide deck mode, filter repeated template header logos and footer banners
                    # EARLY before expensive Pixmap rendering / decompression
                    if is_slide_deck:
                        if bbox[3] < page_height * 0.18:
                            continue
                        if bbox[1] > page_height * 0.88:
                            continue

                    try:
                        base_img = doc.extract_image(xref)
                    except Exception:
                        base_img = {}

                    smask = base_img.get("smask", 0)
                    img_bytes = None
                    img_ext = base_img.get("ext", "png")

                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.width < 40 or pix.height < 40:
                            continue
                        if getattr(pix, "is_unicolor", False):
                            continue
                        if hasattr(pix, "color_topusage"):
                            top_usage, top_color = pix.color_topusage()
                            if top_usage >= 0.95 and isinstance(top_color, (bytes, bytearray)) and len(top_color) >= 3:
                                if all(c < 18 for c in top_color[:3]):
                                    continue
                        if smask and smask > 0:
                            try:
                                mask_pix = fitz.Pixmap(doc, smask)
                                if mask_pix.colorspace != fitz.csGRAY:
                                    mask_pix = fitz.Pixmap(fitz.csGRAY, mask_pix)
                                if mask_pix.alpha:
                                    mask_pix = fitz.Pixmap(mask_pix, 0)
                                if pix.colorspace != fitz.csRGB:
                                    pix = fitz.Pixmap(fitz.csRGB, pix)
                                # Strip existing alpha channel before applying mask
                                # to prevent fitz ValueError: "pixmap must not have an alpha channel"
                                if pix.alpha:
                                    pix = fitz.Pixmap(pix, 0)  # drop alpha
                                if pix.width == mask_pix.width and pix.height == mask_pix.height:
                                    pix = fitz.Pixmap(pix, mask_pix)
                                    img_ext = "png"
                            except Exception:
                                pass
                        if pix.colorspace and pix.colorspace != fitz.csRGB and pix.colorspace != fitz.csGRAY:
                            try:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            except Exception:
                                pass
                        if getattr(pix, "is_unicolor", False):
                            continue
                        # Print-resolution sources (6000x3000 and up) are held per page, sent to the vision model
                        # and stored for display: a copy no larger than MAX_IMAGE_SIDE serves all three at a
                        # fraction of the memory, time and tokens. The size filters below keep using `pix`.
                        out_pix = pix
                        if max(pix.width, pix.height) > MAX_IMAGE_SIDE:
                            out_pix = fitz.Pixmap(pix)
                            while max(out_pix.width, out_pix.height) > MAX_IMAGE_SIDE:
                                out_pix.shrink(1)
                        if img_ext.lower() in ("jpg", "jpeg") and not out_pix.alpha:
                            img_bytes = out_pix.tobytes("jpeg")
                        else:
                            img_bytes = out_pix.tobytes("png")
                            img_ext = "png"
                        del out_pix
                    except Exception as pix_err:
                        logger.debug(f"Pixmap processing fallback for xref {xref}: {pix_err}")
                        img_bytes = base_img.get("image")
                        img_ext = base_img.get("ext", "png")

                    is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                    if not is_valid or not img_bytes:
                        continue

                    # Fast-path check: Global document-level content hash cache
                    # Instantly skip decorative headers, logos, and repeated ornamental graphics across 800+ pages
                    img_hash = hashlib.sha256(img_bytes).hexdigest()
                    if img_hash in vision_cache:
                        cached_v_res = vision_cache[img_hash]
                        if not cached_v_res.get("is_relevant", True) or cached_v_res.get("classification") == "DECORATIVE":
                            continue

                    img_y_mid = (bbox[1] + bbox[3]) / 2.0

                    prod_label = ""
                    matched_step = step_img_xrefs.get(xref)
                    if matched_step:
                        prod_label = matched_step["title"]

                    if not prod_label:
                        prod_label = _find_best_product_title_for_image(
                            page=page,
                            bbox=bbox,
                            non_footers=non_footers,
                            page_width=page_width,
                            page_height=page_height,
                            is_slide_deck=is_slide_deck
                        )

                    if not prod_label and is_slide_deck and slide_title:
                        prod_label = slide_title

                    if not prod_label:
                        prod_label = f"Slide {i+1} Product Image" if is_slide_deck else f"Image p{i+1}_{img_idx+1}"

                    # Filter out non-substantive ornamental images
                    clip_rect = fitz.Rect(
                        max(0, bbox[0] - 80),
                        max(0, bbox[1] - 100),
                        min(page_width, bbox[2] + 80),
                        min(page_height, bbox[3] + 100)
                    )
                    surrounding_text = page.get_text("text", clip=clip_rect).strip()

                    # If image is in the upper 35% of the page, also grab the full-width header strip
                    # so logos in the top-right corner catch journal titles on the top-left
                    header_zone_y = page_height * (0.35 if i == 0 else 0.18)
                    if bbox[1] < header_zone_y:
                        header_rect = fitz.Rect(0, 0, page_width, min(page_height, max(bbox[3] + 50, header_zone_y)))
                        header_text = page.get_text("text", clip=header_rect).strip()
                        surrounding_text = f"{header_text} {surrounding_text}"

                    # If image is in bottom 18% of the page, also grab full-width footer strip
                    if bbox[3] > page_height * 0.82:
                        footer_rect = fitz.Rect(0, max(0, min(bbox[1] - 50, page_height * 0.82)), page_width, page_height)
                        footer_text = page.get_text("text", clip=footer_rect).strip()
                        surrounding_text = f"{footer_text} {surrounding_text}"

                    nearby_text = f"{prod_label} {surrounding_text}"

                    # Filter out container cards, background card shapes, or empty table grid frameworks
                    # that have multiple substantive text blocks rendered over them
                    text_blocks_inside = sum(
                        1 for b in non_footers
                        if (bbox[0] - 8 <= (b[0] + b[2]) / 2.0 <= bbox[2] + 8)
                        and (bbox[1] - 8 <= (b[1] + b[3]) / 2.0 <= bbox[3] + 8)
                        and len(b[4].strip()) > 3
                    )
                    is_substantive_chart = (
                        pix.width >= 350 and pix.height >= 250 and
                        0.35 <= (pix.width / max(1, pix.height)) <= 2.8
                    )
                    max_text_blocks = 8 if is_substantive_chart else 2
                    if text_blocks_inside >= max_text_blocks:
                        logger.info(
                            f"Filtered out background card/table grid container image on page {i+1} "
                            f"({text_blocks_inside} text blocks inside): '{prod_label}' ({pix.width}x{pix.height})"
                        )
                        continue

                    if _is_ornamental_pdf_image(
                        pix_width=pix.width,
                        pix_height=pix.height,
                        bbox=bbox,
                        page_height=page_height,
                        page_idx=i,
                        nearby_text=nearby_text,
                        prod_label=prod_label,
                        page_width=page_width,
                        is_slide_deck=is_slide_deck
                    ):
                        logger.info(f"Filtered out ornamental/metadata PDF image on page {i+1}: '{prod_label}' ({pix.width}x{pix.height})")
                        continue

                    # Tier 2 (Multimodal Vision Verification Gate) runs for all of the page's candidates at once below
                    gate_candidates.append({
                        "img_bytes": img_bytes, "img_ext": img_ext, "nearby_text": nearby_text, "prod_label": prod_label,
                        "img_idx": img_idx, "xref": xref, "matched_step": matched_step, "bbox": bbox,
                    })

                # Tier 2: Multimodal Vision Verification Gate. Each call waits on the vision model for seconds, and an
                # image-heavy document has hundreds of candidates: they are verified concurrently (bounded, like the
                # flattened parser) and then handled in their original order, so the result is the same as one by one.
                if gate_candidates:
                    with ThreadPoolExecutor(max_workers=min(VISION_GATE_CONCURRENCY, len(gate_candidates))) as gate_pool:
                        gate_results = list(gate_pool.map(
                            lambda c: verify_and_classify_visual_candidate(
                                img_bytes=c["img_bytes"],
                                img_ext=c["img_ext"],
                                page_context=c["nearby_text"],
                                fallback_title=c["prod_label"],
                                cache=vision_cache
                            ),
                            gate_candidates
                        ))
                else:
                    gate_results = []
                for cand, v_res in zip(gate_candidates, gate_results):
                    img_bytes, img_ext, prod_label = cand["img_bytes"], cand["img_ext"], cand["prod_label"]
                    img_idx, xref, matched_step, bbox = cand["img_idx"], cand["xref"], cand["matched_step"], cand["bbox"]
                    if not v_res.get("is_relevant", True) or v_res.get("classification") == "DECORATIVE":
                        logger.info(f"Vision Gate dropped decorative/irrelevant image on page {i+1}: {v_res.get('reason')}")
                        continue

                    # If Vision recognizes official product or chart name, adopt it!
                    if v_res.get("product_name") and v_res.get("classification") in ("PRODUCT", "CHART", "DIAGRAM"):
                        prod_label = v_res["product_name"]

                    clean_fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', prod_label)[:40].strip('_')
                    if not clean_fname:
                        clean_fname = f"pdf_img_p{i+1}_{img_idx+1}"
                    else:
                        clean_fname = f"pdf_img_p{i+1}_{img_idx+1}_{clean_fname}"

                    fname = f"{clean_fname}.{img_ext}"
                    upload_batch.append({
                        "content": img_bytes,
                        "filename": fname,
                        "content_type": f"image/{img_ext}",
                        "page_index": i,
                        "img_fname": fname,
                        "product_name": prod_label,
                        "role": v_res.get("role", "PRODUCT_PACKAGING"),
                        "extracted_markdown": v_res.get("extracted_markdown"),
                        "xref": xref,
                        "step_num": matched_step["num"] if matched_step else None,
                        "bbox": bbox,
                        "x_mid": (bbox[0] + bbox[2]) / 2.0 if (bbox and len(bbox) >= 4) else 0.0,
                        "y_mid": (bbox[1] + bbox[3]) / 2.0 if (bbox and len(bbox) >= 4) else 0.0
                    })

                # 4b. Universal Vector Flowchart & Diagram Detection for pages without raster images
                # Detects flowcharts/diagrams drawn natively via vector paths/rectangles
                page_uploaded_count = len([u for u in upload_batch if u.get("page_index") == i])
                if page_uploaded_count == 0 and not grid_tables and not is_slide_deck:
                    try:
                        drawings = page.get_drawings()
                        page_text_raw = page.get_text()
                        has_flowchart_kw = bool(re.search(
                            r'\b(?:bagan\s+alur|flow\s*chart|algoritma)\b',
                            page_text_raw,
                            re.IGNORECASE
                        ))
                        if len(drawings) >= 8 and has_flowchart_kw and len(page_text_raw.strip()) < 1500:
                            union_rect = fitz.Rect()
                            for d in drawings:
                                union_rect |= d["rect"]

                            if union_rect.width >= 200 and union_rect.height >= 120:
                                clip_rect = fitz.Rect(
                                    max(0, union_rect.x0 - 20),
                                    max(0, union_rect.y0 - 35),
                                    min(page_width, union_rect.x1 + 20),
                                    min(page_height, union_rect.y1 + 20)
                                )
                                pix = page.get_pixmap(clip=clip_rect, dpi=150)
                                if pix.width >= 300 and pix.height >= 200:
                                    img_bytes = pix.tobytes("png")
                                    flowchart_label = "Bagan Alur"
                                    for line in page_text_raw.splitlines():
                                        ls = line.strip()
                                        if ls and any(kw in ls.lower() for kw in ["bagan", "alur", "alopesia", "dermatitis", "algoritma"]):
                                            flowchart_label = ls
                                            break

                                    v_res = verify_and_classify_visual_candidate(
                                        img_bytes=img_bytes,
                                        img_ext="png",
                                        page_context=page_text_raw[:500],
                                        fallback_title=flowchart_label,
                                        cache=vision_cache
                                    )
                                    if v_res.get("is_relevant", True) and v_res.get("classification") != "DECORATIVE":
                                        if v_res.get("product_name"):
                                            flowchart_label = v_res["product_name"]
                                        clean_fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', flowchart_label)[:40].strip('_')
                                        if not clean_fname:
                                            clean_fname = f"pdf_img_p{i+1}_flowchart"
                                        else:
                                            clean_fname = f"pdf_img_p{i+1}_{clean_fname}"
                                        fname = f"{clean_fname}.png"
                                        upload_batch.append({
                                            "content": img_bytes,
                                            "filename": fname,
                                            "content_type": "image/png",
                                            "page_index": i,
                                            "img_fname": fname,
                                            "product_name": flowchart_label,
                                            "role": "CHART",
                                            "extracted_markdown": v_res.get("extracted_markdown"),
                                            "xref": None,
                                            "step_num": None,
                                            "bbox": [clip_rect.x0, clip_rect.y0, clip_rect.x1, clip_rect.y1],
                                            "x_mid": (clip_rect.x0 + clip_rect.x1) / 2.0,
                                            "y_mid": (clip_rect.y0 + clip_rect.y1) / 2.0
                                        })
                                        logger.info(f"📊 Extracted vector flowchart on page {i+1}: '{flowchart_label}' ({pix.width}x{pix.height})")
                    except Exception as vf_err:
                        logger.debug(f"Vector flowchart detection on page {i+1}: {vf_err}")

                # 5. Build non-consumed text blocks
                remaining_blocks = [b for bi, b in enumerate(non_footers) if bi not in consumed_indices and b[1] >= 25]

                # 2-Column layout ordering for remaining blocks
                def _is_spanning_block(b):
                    w = b[2] - b[0]
                    if w > page_width * 0.62:
                        return True
                    if b[0] < midpoint * 0.65 and b[2] > midpoint * 1.35:
                        return True
                    return False

                sorted_by_y = sorted(remaining_blocks, key=lambda b: b[1])
                slices = []
                current_slice = []
                for b in sorted_by_y:
                    if _is_spanning_block(b):
                        if current_slice:
                            slices.append(('col', current_slice))
                            current_slice = []
                        slices.append(('span', [b]))
                    else:
                        current_slice.append(b)
                if current_slice:
                    slices.append(('col', current_slice))

                ordered_remaining = []
                for stype, sblocks in slices:
                    if stype == 'span':
                        ordered_remaining.extend(sblocks)
                    elif is_slide_deck:
                        # Slide decks: single cards or slides should follow natural vertical reading order
                        sblocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
                        ordered_remaining.extend(sblocks)
                    else:
                        lefts = [b for b in sblocks if (b[0] + b[2]) / 2.0 < midpoint]
                        rights = [b for b in sblocks if (b[0] + b[2]) / 2.0 >= midpoint]
                        # Genuine 2-column requires a clear separation or gutter between column start margins
                        is_genuine_two_col = (
                            bool(lefts and rights)
                            and (
                                max(b[2] for b in lefts) <= min(b[0] for b in rights) + 60
                                or (min(b[0] for b in rights) - min(b[0] for b in lefts) >= page_width * 0.3)
                            )
                        )
                        if is_genuine_two_col:
                            lefts.sort(key=lambda b: b[1])
                            rights.sort(key=lambda b: b[1])
                            ordered_remaining.extend(lefts)
                            ordered_remaining.extend(rights)
                        else:
                            sblocks.sort(key=lambda b: (round(b[1] / 5) * 5, b[0]))
                            ordered_remaining.extend(sblocks)

                page_layouts.append({
                    "page_idx": i,
                    "grid_tables": grid_tables,
                    "sop_step_data": sop_step_data,
                    "ordered_blocks": ordered_remaining,
                    "footers": footers,
                    "slide_title": slide_title,
                    "is_slide_deck": is_slide_deck,
                    "page_width": page_width,
                    "page_height": page_height
                })
                pages.append({"page": i + 1, "text": ""})

                # Micro-batch flush every 10 pages for flat RAM profile
                if (i + 1) % 10 == 0:
                    _flush_upload_batch()

                # Periodic memory safeguard for massive documents (800+ pages)
                if (i + 1) % 40 == 0:
                    import gc
                    gc.collect()

            except Exception as page_err:
                logger.warning(f"Error parsing page {i+1} of {file_path}: {page_err}")
                pages.append({"page": i + 1, "text": f"[Halaman {i+1} gagal diekstraksi: {page_err}]"})
                page_layouts.append({
                    "page_idx": i,
                    "grid_tables": [],
                    "sop_step_data": None,
                    "ordered_blocks": [],
                    "footers": [],
                    "slide_title": "",
                    "is_slide_deck": is_slide_deck,
                    "page_width": page_width,
                    "page_height": page_height
                })

        # Final flush and assemble pages
        try:
            _flush_upload_batch()

            # Assemble structured text for each page
            for layout in page_layouts:
                p_idx = layout["page_idx"]
                if p_idx >= len(pages):
                    continue

                is_slide = layout.get("is_slide_deck", False)
                slide_title = layout.get("slide_title", "")
                title_heading = f"## Slide {p_idx + 1}: {slide_title}" if slide_title else f"## Slide {p_idx + 1}"
                pw = layout.get("page_width", 0.0)
                midpoint = pw / 2.0 if pw > 0 else 0.0
                ordered_b = layout.get("ordered_blocks", [])

                # Check if this page is a multi-column slide deck (only if NOT a table slide or SOP procedure)
                left_blocks = [b for b in ordered_b if (b[0] + b[2]) / 2.0 < midpoint] if midpoint > 0 else []
                right_blocks = [b for b in ordered_b if (b[0] + b[2]) / 2.0 >= midpoint] if midpoint > 0 else []

                # CRITICAL UNIVERSAL CHECK: A slide is genuinely 2-column ONLY IF:
                # 1. Both left and right have substantive blocks (>= 2 each)
                # 2. There is an actual horizontal gap (whitespace gutter) separating left and right blocks,
                #    meaning left blocks do not overlap in x with right blocks, and no substantive block spans across the middle!
                has_spanning_middle_blocks = any(
                    (b[0] < midpoint - 40 and b[2] > midpoint + 40)
                    for b in ordered_b if b[1] > 80  # exclude top banners
                )
                is_genuine_gutter = (
                    bool(left_blocks and right_blocks)
                    and not has_spanning_middle_blocks
                    and max(b[2] for b in left_blocks) <= min(b[0] for b in right_blocks) + 40
                )
                is_two_col_slide = (
                    is_slide and midpoint > 0 
                    and len(left_blocks) >= 2 and len(right_blocks) >= 2 
                    and is_genuine_gutter
                    and not layout.get("grid_tables") and not layout.get("sop_step_data")
                )

                if is_two_col_slide:
                    # Multi-column Slide Assembly (isolate products into discrete sections without interleaving)
                    top_banner = ""
                    clean_left = []
                    norm_slide_title = re.sub(r'\s+', ' ', slide_title).strip().lower() if slide_title else ""

                    for b in left_blocks:
                        b_text = b[4].replace('\u200b', '').strip()
                        norm_b = re.sub(r'\s+', ' ', b_text).strip().lower()
                        if b[1] < 75 and len(b_text) < 35:
                            top_banner = b_text
                        elif norm_slide_title and norm_b == norm_slide_title:
                            continue
                        else:
                            clean_left.append(b)

                    clean_right = []
                    for b in right_blocks:
                        b_text = b[4].replace('\u200b', '').strip()
                        norm_b = re.sub(r'\s+', ' ', b_text).strip().lower()
                        if b[1] < 75 and len(b_text) < 35 and not top_banner:
                            top_banner = b_text
                        elif norm_slide_title and norm_b == norm_slide_title:
                            continue
                        else:
                            clean_right.append(b)

                    clean_left.sort(key=lambda b: b[1])
                    clean_right.sort(key=lambda b: b[1])

                    slide_imgs = pages[p_idx].get("images", [])
                    left_imgs = [im for im in slide_imgs if im.get("x_mid", 0.0) < midpoint]
                    right_imgs = [im for im in slide_imgs if im.get("x_mid", 0.0) >= midpoint]

                    output_parts = [title_heading]
                    if top_banner:
                        output_parts.append(f"**Kategori:** {top_banner}")

                    # Determine layout: 2 distinct products vs single product with side-by-side details
                    def _is_genuine_product_img(im):
                        pname = im.get("product_name", "").strip()
                        if not pname or len(pname) > 40:
                            return False
                        if any(pname.lower().startswith(x) for x in ["kulit ", "benar ", "untuk ", "sehingga ", "dengan "]):
                            return False
                        return True

                    has_both_product_images = (
                        any(_is_genuine_product_img(im) for im in left_imgs)
                        and any(_is_genuine_product_img(im) for im in right_imgs)
                    )

                    if has_both_product_images:
                        # 2 distinct products (e.g. Night Charge on Left, Skin Renew on Right)
                        left_title = left_imgs[0]["product_name"]
                        left_text = "\n\n".join(b[4].replace('\u200b', '').strip() for b in clean_left if b[4].strip())
                        if left_title and re.sub(r'\s+', ' ', left_title).strip().lower() != norm_slide_title:
                            output_parts.append(f"### {left_title}")
                        for limg in left_imgs:
                            output_parts.append(f"![{limg['product_name']}]({limg['url']})")
                        if left_text:
                            output_parts.append(left_text)

                        right_title = right_imgs[0]["product_name"]
                        right_text = "\n\n".join(b[4].replace('\u200b', '').strip() for b in clean_right if b[4].strip())
                        if right_title and re.sub(r'\s+', ' ', right_title).strip().lower() != norm_slide_title:
                            output_parts.append(f"### {right_title}")
                        for rimg in right_imgs:
                            output_parts.append(f"![{rimg['product_name']}]({rimg['url']})")
                        if right_text:
                            output_parts.append(right_text)
                    else:
                        # Single product layout: preserve natural reading order of ordered_b!
                        single_items = []
                        for b in ordered_b:
                            txt_clean = _block_display_text(b).replace('\u200b', '').strip()
                            if is_slide:
                                txt_clean = _format_slide_block_text(txt_clean)
                            if txt_clean:
                                single_items.append((b[1], txt_clean))
                        if is_slide:
                            single_items = _format_slide_items_clean(single_items, slide_title)

                        for img in slide_imgs:
                            pname = img.get("product_name") or slide_title or f"Slide {p_idx + 1}"
                            output_parts.append(f"![{pname}]({img['url']})")

                        for it in single_items:
                            output_parts.append(it[1])

                    assembled_text = "\n\n".join(output_parts)

                else:
                    items_to_render = []
                    if is_slide:
                        ordered_b = _merge_wrapped_blocks(ordered_b)

                    # Add Grid Tables
                    for gt in layout.get("grid_tables", []):
                        items_to_render.append((gt["y0"], gt["md"]))

                    # Add SOP Step Table if present
                    sop_data = layout.get("sop_step_data")
                    if sop_data and sop_data.get("steps"):
                        rows = []
                        for s in sop_data["steps"]:
                            s_num = s["num"]
                            s_title = s["title"]
                            s_xref = s.get("xref")
                            img_url = url_by_step.get((p_idx, s_num)) or (url_by_xref.get(s_xref) if s_xref else None)
                            img_md = f"![{s_title}]({img_url})" if img_url else "-"
                            rows.append(f"| {s_num} | {s_title} | {img_md} | {s['procedure']} | {s['notes']} |")

                        md_sop = (
                            "| No | Aktivitas / Langkah | Ilustrasi | Prosedur | Catatan |\n"
                            "|:---:|:---|:---:|:---|:---:|\n" +
                            "\n".join(rows)
                        )
                        items_to_render.append((sop_data["y0"], md_sop))

                    # If no tables/SOP data, preserve the reading order of ordered_blocks directly!
                    if not items_to_render:
                        for b in ordered_b:
                            txt_clean = _block_display_text(b).replace('\u200b', '').strip()
                            if is_slide:
                                txt_clean = _format_slide_block_text(txt_clean)
                            if txt_clean:
                                items_to_render.append((b[1], txt_clean))
                    else:
                        all_table_text = " ".join(gt.get("md", "") for gt in layout.get("grid_tables", []))
                        for b in ordered_b:
                            txt_clean = _block_display_text(b).replace('\u200b', '').strip()
                            if txt_clean:
                                if all_table_text and (txt_clean in all_table_text or (len(txt_clean) > 3 and txt_clean.lower() in all_table_text.lower())):
                                    continue
                                if is_slide:
                                    txt_clean = _format_slide_block_text(txt_clean)
                                items_to_render.append((b[1], txt_clean))
                        items_to_render.sort(key=lambda it: it[0])

                    # Footers at the end
                    for fb in layout.get("footers", []):
                        fb_clean = fb[4].replace('\u200b', '').strip()
                        if fb_clean:
                            items_to_render.append((fb[1], fb_clean))

                    if is_slide:
                        items_to_render = _format_slide_items_clean(items_to_render, slide_title)

                    assembled_text = "\n\n".join(it[1] for it in items_to_render if it[1])

                    # For slide decks, add a clear slide header
                    if is_slide:
                        if assembled_text:
                            assembled_text = f"{title_heading}\n\n{assembled_text}"
                        elif pages[p_idx].get("images"):
                            assembled_text = title_heading

                    # For non-step images, embed near their product_name if not already present
                    if p_idx < len(pages) and pages[p_idx].get("images"):
                        for img_obj in pages[p_idx]["images"]:
                            p_name = img_obj["product_name"]
                            u = img_obj["url"]
                            if u not in assembled_text:
                                if p_name and p_name in assembled_text:
                                    pattern = re.compile(rf'(^.*{re.escape(p_name)}.*$)', re.MULTILINE)
                                    if pattern.search(assembled_text):
                                        assembled_text = pattern.sub(rf'\1\n![{p_name}]({u})', assembled_text, count=1)
                                    else:
                                        assembled_text += f"\n\n![{p_name}]({u})"
                                elif is_slide and title_heading in assembled_text:
                                    pattern = re.compile(rf'(^{re.escape(title_heading)})', re.MULTILINE)
                                    if pattern.search(assembled_text):
                                        assembled_text = pattern.sub(rf'\1\n\n![{p_name}]({u})', assembled_text, count=1)
                                    else:
                                        assembled_text += f"\n\n![{p_name}]({u})"
                                else:
                                    assembled_text += f"\n\n![{p_name}]({u})"
                                if img_obj.get("extracted_markdown"):
                                    clean_em = re.sub(r'^```(?:markdown)?\s*', '', img_obj['extracted_markdown'], flags=re.IGNORECASE)
                                    clean_em = re.sub(r'\s*```$', '', clean_em).strip()
                                    if clean_em and clean_em not in assembled_text:
                                        assembled_text += f"\n\n{clean_em}\n\n"

                # Memory protection
                if len(assembled_text) > 50000:
                    assembled_text = assembled_text[:50000] + "\n... [teks halaman dipadatkan untuk stabilitas]"

                pages[p_idx]["text"] = assembled_text
                char_count = len(assembled_text)
                total_chars += char_count
                if char_count > 30:
                    pages_with_text += 1

            for i in range(len(pages)):
                if pages[i].get("image_urls"):
                    pages[i]["image_url"] = pages[i]["image_urls"][0]

        except Exception as img_err:
            logger.warning(f"PDF embedded image extraction failed: {img_err}", exc_info=True)

        # Apply Structure Reconstruction / Document Normalization on each page's extracted text
        from app.rag.utils.normalizer import normalize_document_text
        for p in pages:
            if p.get("text"):
                p["text"] = normalize_document_text(p["text"])

        # Strip bibliography / references so chunking and frontend knowledge display
        # focus 100% on paper body, findings, and discussions
        pages = _strip_references_from_pages(pages)

        # Strip bureaucratic signature blocks and approval sheets from SOPs, protocols, and letters
        pages = _strip_signature_and_approval_blocks(pages)

        # Validate that genuine knowledge text was extracted (strip markdown image tags, URLs, HTML tags, synthetic slide headers)
        from app.rag.utils.pdf_analyzer import clean_extracted_text
        total_pure_chars = sum(len(clean_extracted_text(p.get("text", ""))) for p in pages)
        pages_with_substantive_text = sum(1 for p in pages if len(clean_extracted_text(p.get("text", ""))) > 30)
        if total_pure_chars < 50 or (len(pages) > 3 and pages_with_substantive_text / len(pages) < 0.15):
            logger.info(
                f"⚠️ [PDF-ROUTER] Fast path extracted only {total_pure_chars} pure characters "
                f"({pages_with_substantive_text}/{len(pages)} pages with substantive text) from {file_path}. "
                f"Document requires deep PDF classification & specialized extraction."
            )
            return None

        return ParseResult(pages=pages, method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: EXCEL & CSV (.xlsx, .xls, .csv)
    # -------------------------------------------------------------------------
    def _parse_excel_fast(self, file_path: str) -> ParseResult:
        """Extract text and markdown tables from .xlsx, .xls, and .csv files using openpyxl & pandas."""
        import pandas as pd

        ext = os.path.splitext(file_path)[1].lower()
        pages = []

        try:
            def _df_to_markdown_safe(dataframe) -> str:
                # Cells are written as the sheet shows them: a price stored as 2046000.0000000002 (a float
                # artefact of a formula) is 2046000, as on the main block path
                headers = [clean_cell_str(c).replace("|", "&#124;").replace("\n", " ") for c in dataframe.columns]
                lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                for _, row in dataframe.iterrows():
                    row_vals = [clean_cell_str(v).replace("|", "&#124;").replace("\n", " ").strip() for v in row]
                    lines.append("| " + " | ".join(row_vals) + " |")
                return "\n".join(lines)

            if ext == ".csv":
                df = pd.read_csv(file_path)
                df = df.dropna(how="all")
                md_table = _df_to_markdown_safe(df)
                pages.append({
                    "page": 1,
                    "sheet_name": "CSV",
                    "text": f"### CSV Data Table\n\n{md_table}",
                    "image_urls": [],
                    "image_url": None
                })
            else:
                # Use openpyxl for .xlsx/.xlsm to extract images per sheet with exact cell row anchors
                wb = None
                wb_sheet_map = {}
                if ext in [".xlsx", ".xlsm"]:
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(file_path, data_only=True)
                        wb_sheet_map = {str(s).strip().lower(): s for s in wb.sheetnames}
                    except Exception as wb_err:
                        logger.debug(f"openpyxl load failed, falling back to standard pandas: {wb_err}")
                        wb = None

                with pd.ExcelFile(file_path) as excel_file:
                    sheet_names = excel_file.sheet_names
                    logger.info(f"Parsing Excel with {len(sheet_names)} sheets: {sheet_names}")

                    from app.services.storage import upload_images_parallel

                    for page_idx, sheet_name in enumerate(sheet_names, start=1):
                        try:
                            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                            if df.empty or df.dropna(how="all").empty:
                                continue
                            df = df.astype(object)

                            from collections import defaultdict
                            sheet_image_urls = []
                            cell_to_images = defaultdict(list)
                            unanchored_images = []

                            # Find matching worksheet in openpyxl with whitespace and case tolerance
                            matched_ws_name = wb_sheet_map.get(str(sheet_name).strip().lower()) if wb else None
                            ws = wb[matched_ws_name] if (wb and matched_ws_name and matched_ws_name in wb.sheetnames) else None

                            # 0. Propagate merged cell values so multi-row headers are preserved across cells
                            if ws:
                                for rng in list(ws.merged_cells.ranges):
                                    top_val = ws.cell(rng.min_row, rng.min_col).value
                                    for r_m in range(rng.min_row - 1, rng.max_row):
                                        for c_m in range(rng.min_col - 1, rng.max_col):
                                            if r_m < len(df) and c_m < df.shape[1] and (pd.isna(df.iat[r_m, c_m]) or not str(df.iat[r_m, c_m]).strip()):
                                                df.iat[r_m, c_m] = top_val

                            # 1. Extract embedded images for THIS worksheet using 2D cell coordinates
                            if ws:
                                ws_images = getattr(ws, '_images', [])
                                upload_batch = []
                                img_meta = []

                                for idx, img in enumerate(ws_images):
                                    try:
                                        raw_bytes = img._data()
                                    except Exception:
                                        continue
                                    is_valid, clean_bytes, img_ext = _is_valid_image_content(raw_bytes, min_dim=30)
                                    if not is_valid or not clean_bytes:
                                        continue

                                    anchor = getattr(img, 'anchor', None)
                                    r, c = None, None
                                    if anchor is not None:
                                        if hasattr(anchor, '_from') and getattr(anchor._from, 'row', None) is not None:
                                            r = anchor._from.row
                                            c = getattr(anchor._from, 'col', 0)
                                        elif hasattr(anchor, 'from') and getattr(getattr(anchor, 'from'), 'row', None) is not None:
                                            r = getattr(anchor, 'from').row
                                            c = getattr(getattr(anchor, 'from'), 'col', 0)
                                        elif isinstance(anchor, str):
                                            try:
                                                from openpyxl.utils import coordinate_to_tuple
                                                coord_r, coord_c = coordinate_to_tuple(anchor)
                                                r = coord_r - 1
                                                c = coord_c - 1
                                            except Exception:
                                                pass
                                        elif hasattr(anchor, 'pos') and hasattr(anchor.pos, 'y') and anchor.pos.y is not None:
                                            # Handle openpyxl AbsoluteAnchor using EMUs (1 pt = 12700 EMUs)
                                            try:
                                                y_emu = anchor.pos.y
                                                accum_emu = 0
                                                found_r = 1
                                                max_r = ws.max_row or 100
                                                for r_i in range(1, max_r + 2):
                                                    r_dim = ws.row_dimensions.get(r_i)
                                                    h_pt = r_dim.height if (r_dim and r_dim.height) else 15.0
                                                    h_emu = int(h_pt * 12700)
                                                    if accum_emu + h_emu > y_emu:
                                                        found_r = r_i
                                                        break
                                                    accum_emu += h_emu
                                                r = found_r - 1
                                                c = 0
                                            except Exception as abs_err:
                                                logger.debug(f"Error calculating AbsoluteAnchor row: {abs_err}")

                                    safe_sheet_name = "".join(c_ch if c_ch.isalnum() else "_" for c_ch in sheet_name)
                                    filename = f"excel_{safe_sheet_name}_img_{idx+1}.{img_ext}"
                                    upload_batch.append({
                                        "content": clean_bytes,
                                        "filename": filename,
                                        "content_type": f"image/{img_ext}"
                                    })
                                    img_meta.append((r, c))

                                if upload_batch:
                                    # Ensure df can accommodate anchored images placed beyond initial text boundaries
                                    max_needed_r = max((cell_r for cell_r, _ in img_meta if cell_r is not None), default=-1)
                                    max_needed_c = max((cell_c for _, cell_c in img_meta if cell_c is not None), default=-1)
                                    if max_needed_c >= df.shape[1]:
                                        for new_c in range(df.shape[1], max_needed_c + 1):
                                            df[new_c] = None
                                    if max_needed_r >= len(df):
                                        add_r = max_needed_r - len(df) + 1
                                        new_rows_df = pd.DataFrame([[None] * df.shape[1] for _ in range(add_r)], columns=df.columns)
                                        df = pd.concat([df, new_rows_df], ignore_index=True)

                                    results = upload_images_parallel(upload_batch)
                                    for (cell_r, cell_c), res in zip(img_meta, results):
                                        url = res.get("image_url")
                                        if url:
                                            sheet_image_urls.append(url)
                                            if cell_r is not None and 0 <= cell_r < len(df):
                                                c_val = cell_c if (cell_c is not None and 0 <= cell_c < df.shape[1]) else 0
                                                # Universal header shift: Shift if the cell is at row 0 or is a visual/image column header
                                                curr_cell_txt = str(df.iat[cell_r, c_val]).strip().lower()
                                                is_pure_header = (
                                                    cell_r == 0
                                                    or any(k in curr_cell_txt for k in ["foto", "gambar", "photo", "image", "pic", "visual", "lampiran"])
                                                    or (len(curr_cell_txt) <= 25 and not any(ch.isdigit() for ch in curr_cell_txt) and cell_r <= 1)
                                                )
                                                if is_pure_header and cell_r + 1 < len(df):
                                                    below_txt = str(df.iat[cell_r + 1, c_val]).strip()
                                                    if below_txt and below_txt.lower() != "nan":
                                                        cell_r = cell_r + 1
                                                cell_to_images[(cell_r, c_val)].append(url)
                                            else:
                                                unanchored_images.append(url)
                                    total_anchored_cells = len(cell_to_images)
                                    total_anchored_imgs = sum(len(v) for v in cell_to_images.values())
                                    logger.info(f"Sheet '{sheet_name}': uploaded {len(sheet_image_urls)} images ({total_anchored_imgs} images anchored across {total_anchored_cells} cells, {len(unanchored_images)} unanchored).")

                            # 2. Inject anchored images directly into DataFrame cells WITHOUT raw <br> tags
                            for (r_idx, c_idx), img_urls in cell_to_images.items():
                                curr_val = "" if pd.isna(df.iat[r_idx, c_idx]) else str(df.iat[r_idx, c_idx]).strip()
                                curr_val_clean = " ".join(curr_val.split())
                                alt = curr_val_clean if curr_val_clean else f"Produk R{r_idx+1}C{c_idx+1}"
                                img_tags = " ".join(f"![{alt}]({u})" for u in img_urls)
                                df.iat[r_idx, c_idx] = img_tags

                            # 3. Structural Block Detection: Separate Title/Metadata rows from Data Tables
                            blocks = []
                            current_table_rows = []

                            for r in range(len(df)):
                                # Read as the sheet shows it: a formula's float artefact (2046000.0000000002) is 2046000
                                raw_row = [clean_cell_str(v) for v in df.iloc[r]]
                                non_empty = [(c, v) for c, v in enumerate(raw_row) if v and v.strip().lower() not in ("nan", "none", "null")]

                                if not non_empty:
                                    # Blank spacer row inside a spreadsheet: skip without breaking ongoing data table schema
                                    continue

                                # Single non-empty cell without image tag: Distinguish true structural heading vs note/continuation vs data
                                if len(non_empty) == 1 and "![" not in non_empty[0][1]:
                                    col_idx, txt = non_empty[0]
                                    txt_lower = txt.lower().strip()

                                    is_explicit_heading = any(k in txt_lower for k in [
                                        "cheatsheet", "katalog", "daftar", "panduan", "tabel", "bab", "section",
                                        "kategori", "protokol", "sop", "overview"
                                    ])
                                    is_note_or_meta = (
                                        txt.startswith("*") or txt.endswith("*") or
                                        any(txt_lower.startswith(k) for k in ["catatan", "note", "nb:", "perhatian", "peringatan", "disclaimer", "updated", "tanggal"])
                                    )
                                    is_short_title = (
                                        len(txt) <= 60 and 
                                        not txt.endswith((".", ",", ";", ":")) and 
                                        col_idx == 0 and 
                                        (txt.isupper() or txt.istitle())
                                    )

                                    # If inside an ongoing table and this is a note/continuation, keep it with the table rows instead of breaking table
                                    if current_table_rows and not (is_explicit_heading or (is_short_title and len(current_table_rows) > 3 and not is_note_or_meta)):
                                        current_table_rows.append(raw_row)
                                        continue

                                    if current_table_rows:
                                        blocks.append({"type": "table", "rows": current_table_rows})
                                        current_table_rows = []

                                    if txt_lower in ["nama tindakan"]:
                                        # Redundant merge artifact row directly above table header
                                        continue

                                    if is_explicit_heading or is_short_title:
                                        blocks.append({"type": "heading", "level": 3, "text": txt})
                                    elif is_note_or_meta:
                                        blocks.append({"type": "meta", "text": f"*{txt.strip('*')}*"})
                                    else:
                                        blocks.append({"type": "text", "text": txt})
                                else:
                                    # A header row repeated AFTER data rows (same leading column label, no image cells)
                                    # starts a new table stacked in the same sheet with its own column schema
                                    # (e.g. a 4-column 'Women' table followed by a 3-column 'Men' table).
                                    # Multi-tier header rows share the label via vertical merges but precede any data row.
                                    def _lead_label(cells):
                                        first = next((v for v in cells if v.strip()), "")
                                        return " ".join(first.split()).lower()
                                    header_label = _lead_label(current_table_rows[0]) if current_table_rows else ""
                                    is_repeated_header = (
                                        bool(header_label)
                                        and "![" not in " ".join(raw_row)
                                        and _lead_label(raw_row) == header_label
                                        and any(_lead_label(r) != header_label for r in current_table_rows)
                                    )
                                    if is_repeated_header:
                                        blocks.append({"type": "table", "rows": current_table_rows})
                                        current_table_rows = []
                                    current_table_rows.append(raw_row)

                            if current_table_rows:
                                blocks.append({"type": "table", "rows": current_table_rows})

                            # 4. Render Section Blocks into Clean Markdown
                            output_parts = []
                            active_sheet_headers: Optional[List[str]] = None
                            for b in blocks:
                                if b["type"] == "heading":
                                    output_parts.append(f"### {b['text']}")
                                elif b["type"] == "meta":
                                    output_parts.append(b["text"])
                                elif b["type"] == "text":
                                    output_parts.append(b["text"])
                                elif b["type"] == "table":
                                    t_rows = b["rows"]
                                    if not t_rows:
                                        continue

                                    # A. Check for Side-by-Side Tables (Split by contiguous active column clusters)
                                    num_total_cols = max(len(r) for r in t_rows)
                                    total_r = len(t_rows)
                                    r0 = t_rows[0] if t_rows else []
                                    col_has_data = []
                                    for c in range(num_total_cols):
                                        non_empty_count = sum(1 for r in t_rows if c < len(r) and r[c].strip())
                                        if non_empty_count == 0:
                                            col_has_data.append(False)
                                            continue
                                        c_header = r0[c].strip() if c < len(r0) else ""
                                        # Prune stray outlier cells typed into empty trailing columns outside table
                                        if not c_header and (non_empty_count <= 2 and (total_r > 50 and non_empty_count / total_r < 0.005)):
                                            col_has_data.append(False)
                                        else:
                                            col_has_data.append(True)
                                    clusters = []
                                    curr_cluster = []
                                    for c, has_d in enumerate(col_has_data):
                                        if has_d:
                                            curr_cluster.append(c)
                                        else:
                                            if curr_cluster:
                                                clusters.append(curr_cluster)
                                                curr_cluster = []
                                    if curr_cluster:
                                        clusters.append(curr_cluster)

                                    # Split into sub-tables if multiple clusters are found separated by empty spacer columns
                                    sub_tables = []
                                    if len(clusters) > 1 and all(len(cl) >= 2 for cl in clusters):
                                        for cl in clusters:
                                            sub_t = []
                                            for r in t_rows:
                                                sub_t.append([r[c] if c < len(r) else "" for c in cl])
                                            sub_tables.append(sub_t)
                                    else:
                                        # Unified table: select only active columns with data (prunes blank ghost/spacer columns)
                                        active_cols = [c for cl in clusters for c in cl]
                                        if active_cols:
                                            sub_tables = [[[r[c] if c < len(r) else "" for c in active_cols] for r in t_rows]]
                                        else:
                                            sub_tables = [t_rows]

                                    for sub_rows in sub_tables:
                                        max_active_c = max((max(c for c, v in enumerate(r) if v) + 1 for r in sub_rows if any(r)), default=0)
                                        if max_active_c == 0:
                                            continue
                                        trimmed_rows = [
                                            r[:max_active_c] for r in sub_rows 
                                            if any(v and v.strip().lower() not in ("nan", "none", "null") for v in r[:max_active_c])
                                        ]
                                        if not trimmed_rows:
                                            continue

                                        # B. Check for Transposed Table (Row = Attributes, Col = Records)
                                        col0_vals = [r[0].strip().lower() for r in trimmed_rows if r and r[0].strip() and "![" not in r[0]]
                                        
                                        # Broad universal attribute markers across medical, operational, commercial, technical domains
                                        GENERIC_ATTR_MARKERS = {
                                            "nama", "name", "judul", "title", "kode", "code", "id", "sku", "no", "nomor",
                                            "harga", "price", "tarif", "biaya", "fee", "cost", "total", "jumlah",
                                            "kategori", "category", "tipe", "type", "jenis", "status", "level", "grade",
                                            "deskripsi", "description", "keterangan", "spesifikasi", "parameter", "fitur",
                                            "indikasi", "indications", "kontraindikasi", "contraindications", "efek samping",
                                            "komposisi", "kandungan", "ingredients", "dosis", "aturan", "cara", "petunjuk",
                                            "tanggal", "date", "jadwal", "schedule", "waktu", "durasi", "downtime", "interval",
                                            "lokasi", "cabang", "ruangan", "dokter", "staf", "pic", "kontak", "vendor",
                                            "ukuran", "netto", "satuan", "kemasan", "packaging", "garansi", "catatan"
                                        }
                                        ATTR_REGEX = re.compile(r'\b(?:' + '|'.join(re.escape(m) for m in GENERIC_ATTR_MARKERS) + r')\b', re.IGNORECASE)
                                        
                                        matches = sum(1 for v in col0_vals if ATTR_REGEX.search(v))
                                        row0_vals = [c.strip().lower() for c in trimmed_rows[0] if c and c.strip() and "![" not in c]
                                        row0_matches = sum(1 for v in row0_vals if ATTR_REGEX.search(v))
                                        col0_ratio = (matches / len(col0_vals)) if col0_vals else 0.0
                                        row0_ratio = (row0_matches / len(row0_vals)) if row0_vals else 0.0

                                        is_transposed = (
                                            len(col0_vals) >= 3
                                            and len(trimmed_rows[0]) > 1
                                            and col0_ratio >= 0.50
                                            and col0_ratio > row0_ratio
                                            and row0_ratio < 0.40
                                        )
                                        if is_transposed:
                                            num_new_rows = max(len(r) for r in trimmed_rows)
                                            transposed = []
                                            for col_idx in range(num_new_rows):
                                                new_r = [trimmed_rows[r_idx][col_idx] if col_idx < len(trimmed_rows[r_idx]) else "" for r_idx in range(len(trimmed_rows))]
                                                transposed.append(new_r)
                                            trimmed_rows = transposed
                                            max_active_c = len(trimmed_rows[0])

                                        # C. Universal Dynamic Header Fusion & Hierarchy Propagation
                                        cleaned_sub_rows = [[clean_cell_str(c) for c in row] for row in trimmed_rows]

                                        # Universal leading single-cell row extractor for tables with >= 2 columns
                                        table_captions = []
                                        if max_active_c >= 2:
                                            while cleaned_sub_rows:
                                                r0 = cleaned_sub_rows[0]
                                                non_empty = [c for c in r0 if c]
                                                if len(non_empty) == 1 and not any("![" in c for c in non_empty):
                                                    val = non_empty[0].strip()
                                                    alnum_count = len(re.sub(r'[^a-zA-Z0-9]', '', val))
                                                    if alnum_count >= 3:
                                                        table_captions.append(f"**{val}**")
                                                    cleaned_sub_rows.pop(0)
                                                else:
                                                    break
                                        if not cleaned_sub_rows:
                                            continue

                                        headers, body_rows, tier_count = detect_and_fuse_headers(cleaned_sub_rows)
                                        if not headers and active_sheet_headers and len(cleaned_sub_rows[0]) == len(active_sheet_headers):
                                            headers = active_sheet_headers
                                            body_rows = cleaned_sub_rows
                                        elif headers:
                                            active_sheet_headers = headers
                                        elif not headers and not active_sheet_headers:
                                            headers = infer_generic_headers(cleaned_sub_rows, max_active_c)
                                            body_rows = cleaned_sub_rows

                                        body_rows = propagate_visual_sparse_hierarchy(headers, body_rows)

                                        max_cols = len(headers)
                                        # Always preserve and render detected spreadsheet tables as clean Markdown tables
                                        clean_headers = [h.replace("|", "&#124;").replace("\n", " ").strip() for h in headers]
                                        lines = []
                                        if table_captions:
                                            lines.append("\n".join(table_captions))
                                            lines.append("")
                                        lines.append("| " + " | ".join(clean_headers) + " |")
                                        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
                                        for r_vals in body_rows:
                                            if not any(v and v.strip().lower() not in ("nan", "none", "null") for v in r_vals):
                                                continue
                                            padded = r_vals + [""] * (max_cols - len(r_vals))
                                            lines.append("| " + " | ".join(v.replace("\n", " ").replace("|", "&#124;").strip() for v in padded[:max_cols]) + " |")
                                        output_parts.append("\n\n" + "\n".join(lines) + "\n\n")

                            # Fallback if block detection produced no parts but sheet has content
                            if not output_parts:
                                clean_df = df.dropna(how="all").dropna(axis=1, how="all")
                                if not clean_df.empty:
                                    output_parts.append(_df_to_markdown_safe(clean_df))

                            rendered_content = "\n\n".join(output_parts)
                            unanchored_md = ""
                            if unanchored_images:
                                unanchored_md = "\n".join(f"![Lampiran Gambar]({u})" for u in unanchored_images) + "\n\n"
                            sheet_text = f"## Sheet: {sheet_name}\n\n{unanchored_md}{rendered_content}"
                            pages.append({
                                "page": page_idx,
                                "sheet_name": str(sheet_name).strip(),
                                "text": sheet_text,
                                "image_urls": sheet_image_urls,
                                "image_url": sheet_image_urls[0] if sheet_image_urls else None
                            })
                        except Exception as sheet_err:
                            logger.warning(f"Error parsing sheet '{sheet_name}': {sheet_err}, attempting fallback markdown table...")
                            try:
                                df_fallback = pd.read_excel(excel_file, sheet_name=sheet_name)
                                df_fallback = df_fallback.dropna(how="all").dropna(axis=1, how="all")
                                if not df_fallback.empty:
                                    pages.append({
                                        "page": page_idx,
                                        "sheet_name": str(sheet_name).strip(),
                                        "text": f"## Sheet: {sheet_name}\n\n" + _df_to_markdown_safe(df_fallback),
                                        "image_urls": [],
                                        "image_url": None
                                    })
                            except Exception as fb_err:
                                logger.error(f"Fallback extraction failed for sheet '{sheet_name}': {fb_err}")

            if not pages:
                pages = [{"page": 1, "text": "Dokumen spreadsheet kosong.", "image_urls": [], "image_url": None}]

            return ParseResult(pages=pages, method="fast")
        except Exception as e:
            logger.warning(f"Fast Excel parse failed for {file_path}: {e}. Falling back to text extraction...")
            return ParseResult(pages=[{"page": 1, "text": f"Error parsing spreadsheet: {e}", "image_urls": [], "image_url": None}], method="fast")

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: POWERPOINT (.pptx, .ppt)
    # -------------------------------------------------------------------------
    def _parse_pptx_fast(self, file_path: str) -> ParseResult:
        """Extracts text, slide titles, tables, and notes from PowerPoint (.pptx, .ppt) presentations."""
        try:
            from pptx import Presentation

            prs = Presentation(file_path)
            pages = []
            any_shape_has_image = False
            vision_cache = {}

            def _collect_slide_shapes(shapes_seq):
                collected = []
                for s in shapes_seq:
                    if hasattr(s, "shapes"):  # Recursive unpacking of Group shapes
                        collected.extend(_collect_slide_shapes(s.shapes))
                    else:
                        collected.append(s)
                return collected

            def _split_crammed_cell(text: str, target_count: int) -> list[str]:
                text = text.strip()
                if not text or target_count <= 1:
                    return [text]
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) == target_count:
                    return lines
                bullets = [b.strip() for b in re.split(r'(?:^|\s+)[•●◦\-\*]\s+', text) if b.strip()]
                if len(bullets) == target_count:
                    return bullets
                words = text.split()
                for n in range(6, 1, -1):
                    if len(words) < n * target_count:
                        continue
                    phrases = [' '.join(words[i:i+n]) for i in range(len(words) - n + 1)]
                    from collections import Counter
                    counts = Counter(phrases)
                    candidates = [phrase for phrase, c in counts.items() if c == target_count]
                    if candidates:
                        best_phrase = candidates[0]
                        parts = [p.strip() for p in re.split(r'(?=' + re.escape(best_phrase) + r')', text) if p.strip()]
                        if len(parts) == target_count:
                            return parts
                grade_parts = [p.strip() for p in re.split(r'(?=\b(?:Grade|Step|No\.?|Tindakan)\s+[A-Za-z0-9])', text, flags=re.I) if p.strip()]
                if len(grade_parts) == target_count:
                    return grade_parts
                return [text]

            last_slide_header = None
            last_slide_delimiter = None
            covered_row_numbers = 0

            def _extract_pptx_table(table) -> str:
                nonlocal last_slide_header, last_slide_delimiter, covered_row_numbers
                n_rows = len(table.rows)
                n_cols = len(table.columns)
                matrix = [["" for _ in range(n_cols)] for _ in range(n_rows)]
                
                for r_i, row in enumerate(table.rows):
                    for c_i, cell in enumerate(row.cells):
                        if matrix[r_i][c_i]:
                            continue
                        tc = cell._tc
                        row_span = int(tc.attrib.get('rowSpan', '1'))
                        text = cell.text.strip().replace("\r", "\n").replace("\x0b", "\n")
                        if not text:
                            continue
                            
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        if len(lines) == 1 and row_span > 1:
                            lines = _split_crammed_cell(text, row_span)
                        
                        if len(lines) == row_span:
                            for offset, line_val in enumerate(lines):
                                if r_i + offset < n_rows:
                                    matrix[r_i + offset][c_i] = line_val
                        else:
                            for offset in range(row_span):
                                if r_i + offset < n_rows:
                                    matrix[r_i + offset][c_i] = text
                                    
                # Expand rows when one body cell holds more line-items than the table has rows
                # (author typed all items in a single cell and left the remaining rows empty)
                if n_rows >= 2:
                    max_items = 0
                    for c_i in range(1, n_cols):
                        v = matrix[1][c_i]
                        its = [l for l in v.split("\n") if l.strip()]
                        if len(its) > max_items and all(matrix[r][c_i] == '' for r in range(2, n_rows)):
                            max_items = len(its)
                    if max_items > n_rows - 1:
                        first_num = matrix[1][0].strip()
                        start_no = int(first_num) if first_num.isdigit() else None
                        new_matrix = [matrix[0]]
                        for k in range(max_items):
                            row = [""] * n_cols
                            if start_no is not None:
                                row[0] = str(start_no + k)
                            for c_i in range(1, n_cols):
                                v = matrix[1][c_i]
                                its = [l.strip() for l in v.split("\n") if l.strip()]
                                if len(its) == max_items:
                                    row[c_i] = its[k]
                                elif len(its) == 1:
                                    row[c_i] = its[0]
                                elif k == 0:
                                    row[c_i] = v
                            new_matrix.append(row)
                        matrix = new_matrix
                        n_rows = len(matrix)
                        if start_no is not None:
                            covered_row_numbers = start_no + max_items - 1

                # Skip continuation tables whose numbered rows were already emitted by the expansion above
                if covered_row_numbers and n_rows >= 2:
                    nums = [int(r[0]) for r in matrix[1:] if r[0].strip().isdigit()]
                    body_empty = all(all(not c.strip() for c in r[1:]) for r in matrix[1:])
                    if nums and body_empty and max(nums) <= covered_row_numbers:
                        return ""

                # Unpack unmerged sparse tables where author typed all items in row 1 and left rows 2..N empty
                if n_rows > 2:
                    for c_i in range(n_cols):
                        val_r1 = matrix[1][c_i]
                        if val_r1 and all(matrix[r][c_i] == '' for r in range(2, n_rows)):
                            target_count = n_rows - 1
                            parts = _split_crammed_cell(val_r1, target_count)
                            if len(parts) == target_count:
                                for offset, p in enumerate(parts):
                                    matrix[1 + offset][c_i] = p
                            elif len(parts) == 1 and c_i > 0:
                                # Forward fill single category or device name (e.g. Ultraformer MPT)
                                for r in range(2, n_rows):
                                    matrix[r][c_i] = val_r1

                out_lines = []
                first_cell = matrix[0][0].strip() if matrix and matrix[0] else ""
                is_continuation = False
                if last_slide_header and re.match(r'^\d+$', first_cell) and int(first_cell) > 1:
                    last_hdr_cols = len(last_slide_header.split('|')) - 2
                    if last_hdr_cols == n_cols:
                        is_continuation = True

                if is_continuation:
                    out_lines.append(last_slide_header)
                    out_lines.append(last_slide_delimiter)
                    for row in matrix:
                        clean_row = [c.replace("\n", "<br/>").replace("|", "&#124;") for c in row]
                        out_lines.append("| " + " | ".join(clean_row) + " |")
                else:
                    for r_idx, row in enumerate(matrix):
                        clean_row = [c.replace("\n", "<br/>").replace("|", "&#124;") for c in row]
                        out_lines.append("| " + " | ".join(clean_row) + " |")
                        if r_idx == 0:
                            delimiter = "| " + " | ".join(["---"] * n_cols) + " |"
                            out_lines.append(delimiter)
                    if len(out_lines) >= 2:
                        last_slide_header = out_lines[0]
                        last_slide_delimiter = out_lines[1]

                return "\n".join(out_lines)

            def _cluster_1d_coords(vals: list, tol: int = 15000) -> list:
                if not vals:
                    return []
                sorted_v = sorted(list(set(vals)))
                clusters = [[sorted_v[0]]]
                for v in sorted_v[1:]:
                    if v - clusters[-1][-1] <= tol:
                        clusters[-1].append(v)
                    else:
                        clusters.append([v])
                return [sum(c) / len(c) for c in clusters]

            def _detect_and_reconstruct_pptx_vector_table(slide_obj) -> Tuple[Optional[str], list]:
                """
                Detects and reconstructs vector/geometric tables drawn with PowerPoint lines,
                freeforms, or grouped rectangle borders and text boxes into Markdown tables
                using pure coordinate interval geometry (0% domain-specific regex).
                """
                if any(s.has_table for s in slide_obj.shapes):
                    return None, []

                v_lines = []
                h_lines = []

                def _collect_lines(shapes_seq):
                    for s in shapes_seq:
                        if hasattr(s, "shapes"):
                            _collect_lines(s.shapes)
                        else:
                            w, h = s.width, s.height
                            if w < 20000 and h > 300000:
                                v_lines.append(s.left)
                            elif h < 20000 and w > 300000:
                                h_lines.append(s.top)

                _collect_lines(slide_obj.shapes)
                col_borders = _cluster_1d_coords(v_lines, tol=15000)
                row_borders = _cluster_1d_coords(h_lines, tol=15000)

                # Must have at least 3 column borders (>= 2 columns) and >= 3 row borders (>= 2 rows)
                if len(col_borders) < 3 or len(row_borders) < 3:
                    return None, []

                table_left = col_borders[0] - 25000
                table_right = col_borders[-1] + 25000
                table_top = row_borders[0] - 25000
                table_bottom = row_borders[-1] + 25000

                n_cols = len(col_borders) - 1
                n_rows = len(row_borders) - 1
                grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]

                all_shapes = _collect_slide_shapes(slide_obj.shapes)
                outside_texts = []
                table_text_shapes = []

                for s in all_shapes:
                    if not s.has_text_frame or not s.text_frame.text.strip():
                        continue
                    cx = s.left + s.width / 2
                    cy = s.top + s.height / 2
                    if table_left <= cx <= table_right and table_top <= cy <= table_bottom:
                        table_text_shapes.append(s)
                    else:
                        txt = s.text_frame.text.strip()
                        if s.left < table_left and s.width > 500000:
                            outside_texts.append(f"## {txt.replace(chr(10), ' ')}")
                        else:
                            outside_texts.append(txt)

                if len(table_text_shapes) < 5:
                    return None, []

                # Row 0 Headers: Extract dynamically from shapes lying inside the header row interval
                for s in table_text_shapes:
                    cy = s.top + s.height / 2
                    if row_borders[0] - 25000 <= cy <= row_borders[1] + 15000:
                        cx = s.left + s.width / 2
                        for c_i in range(n_cols):
                            if col_borders[c_i] - 15000 <= cx <= col_borders[c_i+1] + 15000:
                                txt_val = s.text_frame.text.strip().replace("\n", " ")
                                if txt_val and not grid[0][c_i]:
                                    grid[0][c_i] = txt_val
                                break

                # Fill any remaining unassigned header columns with clean defaults
                for c_i in range(n_cols):
                    if not grid[0][c_i]:
                        grid[0][c_i] = f"Kolom {c_i+1}"

                def _find_col_span(s_left: float, s_right: float) -> Tuple[int, int]:
                    c_start = 0
                    for i in range(n_cols):
                        if col_borders[i] - 15000 <= s_left <= col_borders[i+1] + 15000:
                            c_start = i
                            break
                        elif s_left < col_borders[i]:
                            c_start = max(0, i - 1)
                            break
                    c_end = c_start
                    for j in range(c_start, n_cols):
                        if col_borders[j] - 15000 <= s_right <= col_borders[j+1] + 15000:
                            c_end = j
                            break
                        elif s_right > col_borders[j+1]:
                            c_end = j
                    return c_start, min(c_end, n_cols - 1)

                def _find_row_span(s_top: float, s_bottom: float) -> Tuple[int, int]:
                    r_start = 1
                    for i in range(n_rows):
                        if row_borders[i] - 15000 <= s_top <= row_borders[i+1] + 15000:
                            r_start = i
                            break
                    r_end = r_start
                    for j in range(r_start, n_rows):
                        if row_borders[j] - 15000 <= s_bottom <= row_borders[j+1] + 15000:
                            r_end = j
                            break
                        elif s_bottom > row_borders[j+1]:
                            r_end = j
                    return r_start, min(r_end, n_rows - 1)

                avg_row_h = (row_borders[-1] - row_borders[0]) / max(1, n_rows)

                for s in table_text_shapes:
                    cy = s.top + s.height / 2
                    if cy <= row_borders[1] - 15000:
                        continue  # Row 0 header already extracted

                    c_start, c_end = _find_col_span(s.left, s.left + s.width)
                    r_start, r_end = _find_row_span(s.top, s.top + s.height)
                    r_start = max(1, r_start)

                    paragraphs = [p.text.strip() for p in s.text_frame.paragraphs if p.text.strip()]
                    if not paragraphs:
                        continue

                    # Multi-row compound box: height spans multiple rows or multiple paragraphs in tall box
                    is_multi_row = (r_end > r_start) or (s.height > avg_row_h * 1.5 and len(paragraphs) > 1)

                    if is_multi_row:
                        for p_idx, p_text in enumerate(paragraphs):
                            target_r = r_start + p_idx
                            if target_r >= n_rows:
                                break
                            tokens = [t.strip() for t in re.split(r'\t+|\s{2,}', p_text) if t.strip()]
                            if len(tokens) > 1 and c_end > c_start:
                                for t_i, tok in enumerate(tokens):
                                    target_c = c_start + t_i
                                    if target_c < n_cols:
                                        if grid[target_r][target_c]:
                                            grid[target_r][target_c] += "<br/>" + tok
                                        else:
                                            grid[target_r][target_c] = tok
                            else:
                                target_c = min(c_start, n_cols - 1)
                                if grid[target_r][target_c]:
                                    grid[target_r][target_c] += "<br/>" + p_text
                                else:
                                    grid[target_r][target_c] = p_text
                    else:
                        target_r = max(1, min(r_start, n_rows - 1))
                        full_text = "\n".join(paragraphs)
                        tokens = [t.strip() for t in re.split(r'\t+|\s{2,}', full_text) if t.strip()]
                        if len(tokens) > 1 and c_end > c_start:
                            for t_i, tok in enumerate(tokens):
                                target_c = c_start + t_i
                                if target_c < n_cols:
                                    if grid[target_r][target_c]:
                                        grid[target_r][target_c] += "<br/>" + tok
                                    else:
                                        grid[target_r][target_c] = tok
                        else:
                            val = "<br/>".join(paragraphs)
                            target_c = min(c_start, n_cols - 1)
                            if grid[target_r][target_c]:
                                grid[target_r][target_c] += "<br/>" + val
                            else:
                                grid[target_r][target_c] = val

                # Universal sparse hierarchy forward-fill for category columns (e.g. column 0)
                for r_i in range(1, n_rows):
                    if not grid[r_i][0] and grid[r_i-1][0] and any(grid[r_i][1:]):
                        grid[r_i][0] = grid[r_i-1][0]

                out_lines = []
                clean_header = [c.replace("|", "&#124;").strip() or f"Kolom {ci+1}" for ci, c in enumerate(grid[0])]
                out_lines.append("| " + " | ".join(clean_header) + " |")
                out_lines.append("| " + " | ".join(["---"] * n_cols) + " |")

                for r in grid[1:]:
                    clean_row = [c.replace("|", "&#124;").strip() for c in r]
                    if any(clean_row):
                        out_lines.append("| " + " | ".join(clean_row) + " |")

                return "\n".join(out_lines), outside_texts

            for slide_idx, slide in enumerate(prs.slides, start=1):
                last_slide_header = None
                last_slide_delimiter = None
                covered_row_numbers = 0
                slide_texts = []
                slide_image_urls = []
                slide_title = f"Slide {slide_idx}"

                all_slide_shapes = _collect_slide_shapes(slide.shapes)

                # Extract title if present
                if slide.shapes.title and slide.shapes.title.text:
                    slide_title = slide.shapes.title.text.strip()
                    slide_texts.append(f"## {slide_title}")

                # 1. Detect spatial Before / After text labels on this slide
                before_labels = []
                after_labels = []
                for s in all_slide_shapes:
                    if s.has_text_frame:
                        s_text = s.text_frame.text.strip().upper()
                        if any(w in s_text for w in ["SEBELUM", "BEFORE"]):
                            before_labels.append((s.left, s.top, s_text))
                        elif any(w in s_text for w in ["SESUDAH", "AFTER", "SETELAH"]):
                            after_labels.append((s.left, s.top, s_text))

                # 2. Collect and classify image shapes spatially
                img_shapes_on_slide = [s for s in all_slide_shapes if hasattr(s, "image")]
                classified_images = []

                if img_shapes_on_slide:
                    any_shape_has_image = True
                    if before_labels and after_labels and len(img_shapes_on_slide) >= 2:
                        # Spatial proximity matching: match each image to closest label on X axis
                        scored_shapes = []
                        for s in img_shapes_on_slide:
                            dist_before = min(abs(s.left - bl[0]) for bl in before_labels)
                            dist_after = min(abs(s.left - al[0]) for al in after_labels)
                            scored_shapes.append((s, dist_before, dist_after))

                        # Shape with smallest distance to Before label is BEFORE
                        # Shape with smallest distance to After label is AFTER
                        # Sort so that BEFORE comes first (0), AFTER comes second (1)
                        scored_shapes.sort(key=lambda item: item[1] - item[2])
                        for idx, (s, d_b, d_a) in enumerate(scored_shapes):
                            role = "CLINICAL_BEFORE" if idx == 0 else "CLINICAL_AFTER"
                            classified_images.append((s, role))
                    else:
                        # Standard reading order: top-to-bottom, left-to-right
                        sorted_shapes = sorted(img_shapes_on_slide, key=lambda s: (round(s.top / 100000), s.left))
                        for s in sorted_shapes:
                            classified_images.append((s, "IMAGE"))

                # 3. Process non-image shapes (vector tables, native tables, and text frames)
                vector_tbl_md, outside_texts = _detect_and_reconstruct_pptx_vector_table(slide)
                if vector_tbl_md:
                    for ot in outside_texts:
                        if ot.startswith("## "):
                            slide_title = ot[3:].strip()
                            slide_texts.append(ot)
                        else:
                            slide_texts.append(f"- {ot}")
                    slide_texts.append(f"\n\n{vector_tbl_md}\n\n")
                else:
                    # Text boxes are collected as positioned blocks (in points) so that one sentence a slide wraps
                    # over several boxes ('Oleskan anastesi topikal estesia dengan' / 'jumlah sesuai ...') is one item
                    text_blocks = []

                    def flush_text_blocks():
                        for b in _merge_wrapped_blocks(text_blocks):
                            slide_texts.append(f"- {b[4]}")
                        text_blocks.clear()

                    for shape in all_slide_shapes:
                        if shape == slide.shapes.title or hasattr(shape, "image"):
                            continue
                        # Extract text frames
                        if shape.has_text_frame:
                            paragraphs = [p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip()]
                            left, top = (shape.left or 0) / 12700.0, (shape.top or 0) / 12700.0
                            right, bottom = left + (shape.width or 0) / 12700.0, top + (shape.height or 0) / 12700.0
                            for text in _join_wrapped_lines(paragraphs):
                                text_blocks.append((left, top, right, bottom, text))

                        # Extract tables in slides
                        elif shape.has_table:
                            flush_text_blocks()
                            md_table = _extract_pptx_table(shape.table)
                            if md_table:
                                slide_texts.append(f"\n\n{md_table}\n\n")
                    flush_text_blocks()

                # 4. Upload and append classified image shapes in deterministic order (BEFORE first, then AFTER)
                for img_idx, (shape, role) in enumerate(classified_images, start=1):
                    try:
                        from app.services.storage import upload_image
                        img_obj = shape.image
                        img_bytes = img_obj.blob
                        is_valid, img_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                        if not is_valid or not img_bytes:
                            continue

                        # Multimodal Vision Verification Gate
                        ctx_text = f"Slide {slide_idx}: {slide_title}. Role tag: {role}. " + " ".join(slide_texts[:3])
                        v_res = verify_and_classify_visual_candidate(
                            img_bytes=img_bytes,
                            img_ext=img_ext,
                            page_context=ctx_text,
                            fallback_title=slide_title,
                            cache=vision_cache
                        )
                        if not v_res.get("is_relevant", True) or v_res.get("classification") == "DECORATIVE":
                            logger.info(f"Vision Gate dropped decorative PPTX shape on slide {slide_idx}: {v_res.get('reason')}")
                            continue

                        prod_label = v_res.get("product_name") or slide_title
                        clean_tag = re.sub(r'[^a-zA-Z0-9_\-]', '_', prod_label)[:30].strip('_')
                        role_tag = "before" if role == "CLINICAL_BEFORE" else ("after" if role == "CLINICAL_AFTER" else clean_tag)
                        fname = f"pptx_s{slide_idx}_{role_tag}.{img_ext}"
                        upload_res = upload_image(img_bytes, fname, content_type=f"image/{img_ext}")
                        img_url = upload_res.get("image_url")
                        if img_url:
                            slide_image_urls.append(img_url)
                            if role == "CLINICAL_BEFORE":
                                slide_texts.append(f"![Foto Sebelum Perawatan - {prod_label}]({img_url})")
                            elif role == "CLINICAL_AFTER":
                                slide_texts.append(f"![Foto Sesudah Perawatan - {prod_label}]({img_url})")
                            else:
                                slide_texts.append(f"![{prod_label}]({img_url})")
                            if v_res.get("extracted_markdown"):
                                slide_texts.append(f"\n\n{v_res['extracted_markdown']}\n\n")
                    except Exception as shape_img_err:
                        logger.debug(f"PPTX slide image shape extraction skipped: {shape_img_err}")

                # Extract speaker notes if any
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_texts.append(f"**Notes:** {notes}")

                if slide_texts:
                    full_slide_content = f"### Slide {slide_idx}: {slide_title}\n\n" + "\n".join(slide_texts)
                    pages.append({
                        "page": slide_idx,
                        "text": full_slide_content,
                        "image_urls": slide_image_urls,
                        "image_url": slide_image_urls[0] if slide_image_urls else None
                    })

            if not pages:
                pages = [{"page": 1, "text": "Presentasi PowerPoint kosong."}]

            # Extract embedded images from .pptx media parts zip fallback ONLY if NO shapes had images
            if not any_shape_has_image:
                try:
                    import zipfile
                    from app.services.storage import upload_images_parallel

                    with zipfile.ZipFile(file_path, 'r') as z:
                        media_files = [f for f in z.namelist() if f.startswith('ppt/media/')]
                        upload_batch = []
                        for idx, media_name in enumerate(media_files, start=1):
                            img_bytes = z.read(media_name)
                            is_valid, clean_bytes, img_ext = _is_valid_image_content(img_bytes, min_dim=40)
                            if not is_valid or not clean_bytes:
                                continue
                            v_res = verify_and_classify_visual_candidate(
                                img_bytes=clean_bytes,
                                img_ext=img_ext,
                                page_context=f"PPTX embedded media {media_name}",
                                fallback_title="",
                                cache=vision_cache
                            )
                            if not v_res.get("is_relevant", True) or v_res.get("classification") == "DECORATIVE":
                                continue
                            fname = f"pptx_img_{idx}_{os.path.basename(media_name).split('.')[0]}.{img_ext}"
                            upload_batch.append({
                                "content": clean_bytes,
                                "filename": fname,
                                "content_type": f"image/{img_ext}"
                            })
                        
                        if upload_batch:
                            results = upload_images_parallel(upload_batch)
                            extracted_image_urls = [r["image_url"] for r in results if r.get("image_url")]
                            if extracted_image_urls and pages:
                                existing_urls = pages[0].get("image_urls", [])
                                combined_urls = list(dict.fromkeys(existing_urls + extracted_image_urls))
                                pages[0]["image_urls"] = combined_urls
                                pages[0]["image_url"] = combined_urls[0]
                            logger.info(f"⚡ [ASYNC BATCH] Uploaded {len(extracted_image_urls)} embedded PPTX images to MinIO in parallel.")
                except Exception as img_err:
                    logger.debug(f"PPTX embedded image extraction skipped: {img_err}")

            return ParseResult(pages=pages, method="fast")
        except Exception as e:
            logger.warning(f"Fast PPTX parse failed for {file_path}: {e}")
            return None

    # -------------------------------------------------------------------------
    # FAST EXTRACTION: LEGACY DOC (.doc)
    # -------------------------------------------------------------------------
    def _parse_doc_fast(self, file_path: str) -> Optional[ParseResult]:
        """Extract text from legacy .doc files."""
        logger.warning(f"Legacy .doc format requires conversion to .docx for {file_path}")
        return None

    def _parse_standalone_image(self, file_path: str, fast_mode: bool = False) -> ParseResult:
        """
        Uploads standalone image file to MinIO S3 and extracts structured knowledge using 
        Generic Image Knowledge Extraction Vision LLM (with Docling OCR fallback)
        so it can be indexed in PGVector/BM25 and displayed by frontend during chatbot recommendations.
        """
        import base64
        import json
        import uuid
        from app.services.storage import upload_image

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower().replace(".", "")
        content_type = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "webp"] else "image/png"

        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()

            upload_res = upload_image(image_bytes, file_name, content_type=content_type)
            image_url = upload_res.get("image_url", "")
            s3_key = upload_res.get("s3_key", "")

            # If fast_mode or refine attachment: upload directly to MinIO and return instant ParseResult (<0.1s)
            if fast_mode or "refine_" in file_name or "supp_" in file_name or "refine" in file_path.lower():
                clean_title = os.path.splitext(file_name)[0]
                img_id = f"img_{uuid.uuid4().hex[:8]}"
                image_asset = {
                    "id": img_id,
                    "url": image_url,
                    "s3_key": s3_key,
                    "role": "PRODUCT_PACKAGING",
                    "product_name": clean_title,
                    "caption": f"Foto {clean_title}"
                }
                page_data = {
                    "page": 1,
                    "text": f"![{clean_title}]({image_url})",
                    "image_id": img_id,
                    "image_urls": [image_url] if image_url else [],
                    "image_url": image_url,
                    "images": [image_asset],
                    "s3_key": s3_key,
                    "storage_key": s3_key,
                    "image_reference": image_url,
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"],
                    "visibility_settings": {
                        "clinics": ["all"],
                        "doctor_types": ["all"],
                        "doctors": ["all"]
                    }
                }
                logger.info(f"⚡ [FAST IMAGE PARSE] Standalone image '{file_name}' uploaded to MinIO in < 0.1s ({image_url})")
                return ParseResult(pages=[page_data], method="fast")

            extracted_text = ""
            extracted_meta = {
                "s3_key": s3_key,
                "storage_key": s3_key,
                "image_url": image_url,
                "image_reference": image_url,
            }

            # --- Multimodal Vision LLM Extraction ---
            try:
                from app.rag.config import settings
                from openai import OpenAI

                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                data_uri = f"data:{content_type};base64,{b64_img}"

                db_api_key = None
                db_model_name = None
                db_base_url = None

                try:
                    from sqlalchemy import text
                    from app.core.database import get_sync_engine
                    from app.core.security import decrypt_api_key
                    
                    engine = get_sync_engine()
                    with engine.connect() as conn:
                        res = conn.execute(text("SELECT key, value FROM app_config WHERE key IN ('LLM_API_KEY', 'LLM_ACTIVE_MODEL_NAME', 'LLM_BASE_URL')")).fetchall()
                        config_map = {row[0]: row[1] for row in res if row[1]}
                        
                        if "LLM_API_KEY" in config_map:
                            try:
                                db_api_key = decrypt_api_key(config_map["LLM_API_KEY"])
                            except Exception:
                                db_api_key = config_map["LLM_API_KEY"]
                        db_model_name = config_map.get("LLM_ACTIVE_MODEL_NAME")
                        db_base_url = config_map.get("LLM_BASE_URL")
                except Exception as db_cfg_err:
                    logger.debug(f"Sync DB config fetch failed: {db_cfg_err}")

                api_key = db_api_key or os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
                if api_key and not api_key.startswith("sk-"):
                    env_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
                    if env_key and env_key.startswith("sk-"):
                        api_key = env_key

                base_url = db_base_url or os.getenv("OPENAI_BASE_URL") or getattr(settings, "openai_base_url", None)
                model_name = db_model_name or os.getenv("VISION_MODEL_NAME") or getattr(settings, "openai_model_name", None) or "gpt-5.4-mini"

                # Guard against mismatched OpenAI vs Gemini model name / base_url
                if api_key and api_key.startswith("sk-"):
                    if not model_name or "gemini" in model_name.lower() or not any(model_name.startswith(p) for p in ["gpt-", "o1", "o3", "chatgpt"]):
                        model_name = "gpt-5.4-mini"
                    if base_url and "googleapis.com" in base_url:
                        base_url = None

                if api_key:
                    logger.info(f"🔍 Running Generic Image Knowledge Extraction for '{file_name}' using model '{model_name}'...")
                    client_kwargs = {
                        "api_key": api_key,
                        "timeout": 30.0
                    }
                    if base_url:
                        client_kwargs["base_url"] = base_url

                    client = OpenAI(**client_kwargs)
                    prompt_text = (
                        "You are an expert product recognition system for PT Arya Noble (ERHA) Knowledge Base.\n\n"
                        "Your task is to identify the EXACT PRODUCT NAME shown on the product packaging or image.\n\n"
                        "## STRICT RULES (MANDATORY):\n"
                        "1. **IDENTIFY PRODUCT NAME ONLY**: Recognize and extract ONLY the official Product Name printed on the packaging (e.g., 'Exfoliating Cleansing Scrub', 'Acne Act Acne Spot Gel').\n"
                        "2. **DO NOT EXTRACT PACKAGING DETAILS**: Do NOT generate, OCR, or invent packaging text such as Brand, SKU, Net Weight, instructions, benefits, or 'Informasi Tertera pada Kemasan'. Generating packaging text is strictly forbidden to prevent false detections.\n"
                        "3. **PRESERVE RETRIEVAL CONTEXT**: Provide the clean product name and a clean 1-line Indonesian context so this image has full context and can be retrieved accurately in search and RAG answers.\n"
                        "4. **Clinical / Before-After Photos**: If this is a clinical photo of skin/face (not product packaging), identify the treatment or clinical condition (e.g., 'Acne Vulgaris - Before Treatment') and state whether it is BEFORE or AFTER.\n\n"
                        "## Output Format (Valid JSON ONLY):\n"
                        "{\n"
                        '  "title": "Exact Visible Product Name",\n'
                        '  "product_name": "Exact Visible Product Name",\n'
                        '  "image_role": "PRODUCT_PACKAGING",\n'
                        '  "caption": "Foto produk Exact Visible Product Name",\n'
                        '  "document_type": "PRODUCT",\n'
                        '  "summary_markdown": "# Exact Visible Product Name\\n\\n![Exact Visible Product Name](IMAGE_URL_PLACEHOLDER)\\n\\nDokumen visual produk resmi ERHA: Exact Visible Product Name."\n'
                        "}"
                    )

                    completion_kwargs = {
                        "model": model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_text},
                                    {"type": "image_url", "image_url": {"url": data_uri}}
                                ]
                            }
                        ],
                        "temperature": 0.0
                    }
                    try:
                        response = client.chat.completions.create(
                            **completion_kwargs,
                            max_completion_tokens=2000
                        )
                    except Exception as tok_err:
                        err_str = str(tok_err).lower()
                        if "max_completion_tokens" in err_str or "unsupported" in err_str:
                            response = client.chat.completions.create(
                                **completion_kwargs,
                                max_tokens=2000
                            )
                        else:
                            raise tok_err
                    if response.choices and len(response.choices) > 0:
                        raw_content = (response.choices[0].message.content or "").strip()
                        try:
                            clean_json = raw_content
                            if "```" in clean_json:
                                lines = clean_json.split("\n")
                                if lines[0].startswith("```"):
                                    lines = lines[1:]
                                if lines and lines[-1].startswith("```"):
                                    lines = lines[:-1]
                                clean_json = "\n".join(lines).strip()
                            data = json.loads(clean_json, strict=False)

                            img_title = data.get("title") or data.get("product_name") or os.path.splitext(file_name)[0]
                            p_name = data.get("product_name") or img_title
                            brand = data.get("brand") or "PT Arya Noble"
                            active_ing = []
                            clean_sku = None

                            # Infer or extract image role
                            img_role = data.get("image_role")
                            valid_roles = ["PRODUCT_PACKAGING", "CLINICAL_BEFORE", "CLINICAL_AFTER", "TREATMENT_PROCEDURE", "GENERAL"]
                            if not img_role or img_role not in valid_roles:
                                lower_fname = file_name.lower()
                                lower_text = (data.get("summary_markdown") or "").lower()
                                if any(k in lower_fname or k in lower_text for k in ["before", "sebelum"]):
                                    img_role = "CLINICAL_BEFORE"
                                elif any(k in lower_fname or k in lower_text for k in ["after", "sesudah", "setelah"]):
                                    img_role = "CLINICAL_AFTER"
                                elif any(k in lower_fname or k in lower_text for k in ["kemasan", "packaging", "bottle", "box", "produk"]):
                                    img_role = "PRODUCT_PACKAGING"
                                else:
                                    img_role = "PRODUCT_PACKAGING" if data.get("document_type") == "PRODUCT" else "GENERAL"

                            caption = data.get("caption") or f"Foto produk {p_name}"

                            extracted_meta.update({
                                "title": img_title,
                                "product_name": p_name,
                                "brand": brand,
                                "sku": None,
                                "active_ingredients": [],
                                "image_role": img_role,
                                "caption": caption
                            })

                            # Clean structured markdown with product name and image context only (zero packaging hallucination)
                            clean_markdown = f"# {img_title}\n\n![{img_title}]({image_url})\n\nDokumen visual resmi: {p_name}."
                            extracted_text = clean_markdown

                        except Exception as json_err:
                            logger.warning(f"Could not parse Vision LLM JSON response for '{file_name}': {json_err}. Using raw output.")
                            clean_title = os.path.splitext(file_name)[0]
                            extracted_text = f"![{clean_title}]({image_url})\n\n{raw_content}"

            except Exception as vision_err:
                logger.warning(f"Vision LLM extraction skipped/failed for '{file_name}': {vision_err}. Falling back to OCR.")

            if not extracted_text:
                clean_title = os.path.splitext(file_name)[0]
                extracted_text = f"### Image Asset: {clean_title}\n\n![{clean_title}]({image_url})\n\nStorage Key: `{s3_key}`."

            import uuid
            img_id = f"img_{uuid.uuid4().hex[:8]}"
            clean_title = os.path.splitext(file_name)[0]
            current_role = img_role if 'img_role' in locals() and img_role else ("PRODUCT_PACKAGING" if any(k in file_name.lower() for k in ["produk", "bottle", "box"]) else "GENERAL")
            current_caption = caption if 'caption' in locals() and caption else f"Foto {clean_title}"
            current_pname = p_name if 'p_name' in locals() and p_name else clean_title

            image_asset = {
                "id": img_id,
                "url": image_url,
                "s3_key": s3_key,
                "role": current_role,
                "product_name": current_pname,
                "caption": current_caption
            }

            page_data = {
                "page": 1,
                "text": extracted_text,
                "image_id": img_id,
                "image_urls": [image_url] if image_url else [],
                "image_url": image_url,
                "images": [image_asset],
                "s3_key": s3_key,
                "storage_key": s3_key,
                "image_reference": image_url,
                "clinics": ["all"],
                "doctor_types": ["all"],
                "doctors": ["all"],
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                }
            }
            page_data.update(extracted_meta)

            logger.info(f"🖼️ Standalone image '{file_name}' processed via Generic Image Knowledge Extraction (chars={len(extracted_text)}, s3_key={s3_key}, image_url={image_url})")
            return ParseResult(pages=[page_data], method="fast")
        except Exception as e:
            logger.warning(f"Standalone image processing failed for {file_path}: {e}")
            fname = os.path.basename(file_path)
            clean_t = os.path.splitext(fname)[0]
            fallback_page = {
                "page": 1,
                "text": f"### Image Asset: {clean_t}\n\n*Berkas gambar: {fname}*",
                "image_id": f"img_fallback_{clean_t[:12]}",
                "image_urls": [],
                "image_url": None,
                "images": [],
                "clinics": ["all"],
                "doctor_types": ["all"],
                "doctors": ["all"],
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                }
            }
            return ParseResult(pages=[fallback_page], method="fast")

    # -------------------------------------------------------------------------
    # DOCLING OCR FALLBACK (Legacy Optional Fallback)
    # -------------------------------------------------------------------------
    def _parse_with_docling(self, file_path: str) -> Optional[ParseResult]:
        """Legacy Docling OCR fallback stub. Docling is deprecated and superseded by Fast Path & RapidOCR."""
        logger.debug(f"Docling is deprecated and disabled. Skipping parse for {file_path}")
        return None

    # -------------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -------------------------------------------------------------------------
    def parse_file(self, file_path: str, fast_mode: bool = False) -> Optional[ParseResult]:
        """
        Smart parse: tries fast extraction first for docx, doc, pptx, ppt, txt, pdf, xlsx, xls, csv.
        Falls back to Docling OCR for scanned PDFs & image files.
        Returns a ParseResult object.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        ext = os.path.splitext(file_path)[1].lower()
        start_time = time.time()

        try:
            if ext == ".docx":
                logger.info(f"⚡ Fast DOCX extraction: {file_path}")
                result = self._parse_docx_fast(file_path)

            elif ext == ".doc":
                logger.info(f"📄 Legacy DOC extraction: {file_path}")
                result = self._parse_doc_fast(file_path)

            elif ext in [".pptx", ".ppt"]:
                logger.info(f"📊 Fast PowerPoint extraction: {file_path}")
                result = self._parse_pptx_fast(file_path)

            elif ext == ".txt":
                logger.info(f"⚡ Fast TXT extraction: {file_path}")
                result = self._parse_txt_fast(file_path)

            elif ext in [".xlsx", ".xls", ".csv"]:
                logger.info(f"📊 Fast Excel/CSV extraction: {file_path}")
                result = self._parse_excel_fast(file_path)

            elif ext == ".pdf":
                if not getattr(settings, "ENABLE_OCR_VISION", True):
                    logger.info(f"🚫 [SCENARIO A] Running naive PDF extraction without OCR/Vision (ENABLE_OCR_VISION=False): {file_path}")
                    result = self._parse_pdf_naive(file_path)
                else:
                    # 1. Quick Complexity Pre-Check (< 15ms) to avoid wasting minutes in fast path on 0-text PDFs
                    analysis = None
                    try:
                        import fitz
                        from app.rag.utils.pdf_analyzer import analyze_pdf_complexity, PDFDocumentType
                        pdf_doc = fitz.open(file_path)
                        analysis = analyze_pdf_complexity(pdf_doc, file_path)
                        pdf_doc.close()
                    except Exception as an_err:
                        logger.warning(f"PDF pre-analysis skipped: {an_err}")

                    # If PDF is definitively a flattened design or scanned document (no digital text fonts/chars),
                    # immediately route to FlattenedDesignParser (RapidOCR) instead of running digital fast path
                    if analysis and analysis.pdf_type in (PDFDocumentType.FLATTENED_DESIGN, PDFDocumentType.SCANNED_IMAGE):
                        logger.info(f"🎨 Routing {analysis.pdf_type.value} directly to FlattenedDesignParser (RapidOCR)...")
                        from app.rag.utils.flattened_parser import FlattenedDesignParser
                        from app.rag.canonical import PDFContext
                        flat_parser = FlattenedDesignParser()
                        ctx = PDFContext.FLATTENED_DESIGN if analysis.pdf_type == PDFDocumentType.FLATTENED_DESIGN else PDFContext.SCANNED
                        parsed_pages = flat_parser.parse_pdf(file_path, pdf_context=ctx)
                        if parsed_pages and any(p.get("text") for p in parsed_pages):
                            result = ParseResult(pages=parsed_pages, method="fast")
                        else:
                            result = None
                    else:
                        logger.info(f"⚡ Attempting fast PDF extraction: {file_path}")
                        result = self._parse_pdf_fast(file_path)

                        if result is None:
                            # PDF has insufficient selectable digital text -> analyze complexity / fallback
                            logger.info(f"🔍 Analyzing PDF complexity for non-digital PDF: {file_path}")
                            try:
                                import fitz
                                from app.rag.utils.pdf_analyzer import analyze_pdf_complexity, PDFDocumentType
                                from app.rag.utils.flattened_parser import FlattenedDesignParser
                                from app.rag.canonical import PDFContext

                                if not analysis:
                                    pdf_doc = fitz.open(file_path)
                                    analysis = analyze_pdf_complexity(pdf_doc, file_path)
                                    pdf_doc.close()

                                # Catalogs, brochures, PowerPoint/Canva prints, or scanned images -> RapidOCR
                                if analysis.pdf_type in (PDFDocumentType.FLATTENED_DESIGN, PDFDocumentType.SCANNED_IMAGE, PDFDocumentType.HYBRID):
                                    logger.info(f"🎨 Routing {analysis.pdf_type.value} to FlattenedDesignParser (RapidOCR)...")
                                    flat_parser = FlattenedDesignParser()
                                    ctx = PDFContext.FLATTENED_DESIGN if analysis.pdf_type == PDFDocumentType.FLATTENED_DESIGN else PDFContext.SCANNED
                                    parsed_pages = flat_parser.parse_pdf(file_path, pdf_context=ctx)
                                    if parsed_pages and any(p.get("text") for p in parsed_pages):
                                        result = ParseResult(pages=parsed_pages, method="fast")
                                    else:
                                        logger.warning(f"FlattenedDesignParser returned empty text for {file_path}")
                                        result = None
                                else:
                                    logger.info(f"Non-digital PDF type {analysis.pdf_type.value} has insufficient text: {file_path}")
                                    result = None
                            except Exception as route_err:
                                logger.warning(f"Specialized PDF routing failed: {route_err}")
                                result = None
            elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
                logger.info(f"🖼️ Standalone image extraction & MinIO upload: {file_path}")
                result = self._parse_standalone_image(file_path, fast_mode=fast_mode)
            else:
                logger.warning(f"Unsupported document format: {ext} for {file_path}")
                result = None

            elapsed = time.time() - start_time
            if result:
                # Apply text hygiene across all parsed pages (PUA glyphs, wrapped <br> in tables, discontinue phrasing)
                try:
                    from app.rag.utils.text_hygiene import normalize_markdown_text
                    for p in getattr(result, "pages", []):
                        if isinstance(p, dict) and "text" in p and p["text"]:
                            p["text"] = normalize_markdown_text(p["text"])
                except Exception as norm_err:
                    logger.warning(f"Text hygiene normalization error: {norm_err}")

                method_label = "Fast" if result.is_fast else "OCR"
                page_count = len(result.pages) if result.is_fast else "N/A"
                logger.info(
                    f"✅ Parsed {file_path} via {method_label} in {elapsed:.2f}s "
                    f"(pages={page_count})"
                )
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Error parsing {file_path} after {elapsed:.2f}s: {e}")
            return None
