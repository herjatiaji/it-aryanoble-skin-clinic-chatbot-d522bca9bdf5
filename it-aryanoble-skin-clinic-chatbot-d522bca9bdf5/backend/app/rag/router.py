import os
import re
import time
import json
import asyncio
import contextvars
from typing import List, Optional, Dict, Any, Union
from app.core.logger import logger, ApprovalTrace
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks, Path, Body, Request
from pydantic import BaseModel, Field, model_validator

import uuid
from datetime import datetime, timezone

from app.rag.schemas import (
    ChatResponse, 
    UserContext,
    TextIngestRequest,
    DocumentListItem,
    PendingDocumentResponse,
    RefineRequest,
    EditApprovedDocumentRequest,
    ApprovedDocumentResponse,
    RAGEvaluationItem,
    RAGEvaluationRequest,
    RAGEvaluationResponse,
    QualityGateResponse,
    UpdateEvidenceRequest,
    RegenerateSummaryResponse,
    PublishVersionRequest,
    PublishVersionResponse,
    MediaResolveResponse,
    InvariantCheckResponse,
    ReparseVisionRequest
)
from app.rag.services.rag_pipeline import IngestionPipeline
from app.rag.services.rag_retriever import HybridRetriever, BM25Index
from app.rag.services.rag_generator import GenerationPipeline, _extract_specific_treatment_or_product_name
from app.rag.services.evaluation import RAGEvaluator
from app.rag.services.guardrails import GuardrailsPipeline
from app.rag.config import settings
from app.rag.services.intent import QueryIntentDetector, QueryIntent
from app.rag.deps import (
    get_ingestion_pipeline,
    get_hybrid_retriever,
    get_generation_pipeline,
    get_bm25_index,
    get_llm,
    get_vector_store,
    get_medical_agent
)
from app.rag.services.interfaces import BaseLLMAdapter, BaseVectorStoreAdapter
from app.rag.services.general_knowledge_service import GeneralKnowledgeService
from app.rag.pipeline_versions import chunker_version_of
from app.services.storage import expand_image_urls_in_markdown


def safe_json_loads(json_str: str) -> dict:
    """Parses JSON safely, handling conversational wrapping, unescaped control characters, and markdown code blocks."""
    clean = (json_str or "").strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines).strip()

    # Extract outermost { ... } block if surrounded by conversational text
    import re
    first_brace = clean.find("{")
    last_brace = clean.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        clean = clean[first_brace:last_brace+1]

    try:
        return json.loads(clean, strict=False)
    except Exception:
        # Sanitize unescaped control characters like raw newlines inside JSON strings
        try:
            sanitized = re.sub(r'[\r\n\t]', ' ', clean)
            return json.loads(sanitized, strict=False)
        except Exception:
            return {}


def create_image_asset(
    url: str,
    s3_key: Optional[str] = None,
    role: str = "GENERAL",
    product_name: Optional[str] = None,
    caption: Optional[str] = None,
    img_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a structured MediaAsset object for an image with a unique ID and role.
    Roles: 'PRODUCT_PACKAGING', 'CLINICAL_BEFORE', 'CLINICAL_AFTER', 'TREATMENT_PROCEDURE', 'GENERAL'
    """
    clean_url = str(url or "").strip()
    if not clean_url:
        return {}
    
    unique_id = img_id or f"img_{uuid.uuid4().hex[:8]}"
    return {
        "id": unique_id,
        "url": clean_url,
        "s3_key": s3_key or "",
        "role": role,
        "product_name": product_name,
        "caption": caption or product_name or "Image Asset"
    }


def normalize_image_assets(
    existing_images: Optional[List[Any]] = None,
    image_urls: Optional[List[str]] = None,
    default_product_name: Optional[str] = None,
    default_role: str = "GENERAL"
) -> List[Dict[str, Any]]:
    """
    Ensures images are structured as a list of dicts with unique id, url, role, caption.
    """
    assets = []
    seen_urls = set()
    
    if existing_images and isinstance(existing_images, list):
        for item in existing_images:
            if isinstance(item, dict) and item.get("url"):
                u = str(item["url"]).strip()
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    item_copy = dict(item)
                    if not item_copy.get("id"):
                        item_copy["id"] = f"img_{uuid.uuid4().hex[:8]}"
                    if not item_copy.get("role"):
                        item_copy["role"] = default_role
                    assets.append(item_copy)
            elif isinstance(item, str) and item.strip():
                u = item.strip()
                if u not in seen_urls:
                    seen_urls.add(u)
                    assets.append(create_image_asset(u, role=default_role, product_name=default_product_name))
                    
    if image_urls and isinstance(image_urls, list):
        for u in image_urls:
            if u and isinstance(u, str) and u.strip():
                clean_u = u.strip()
                if clean_u not in seen_urls:
                    seen_urls.add(clean_u)
                    assets.append(create_image_asset(clean_u, role=default_role, product_name=default_product_name))
                
def resolve_matching_categories(raw_cats: Any, db_categories: list, content_text: str = "") -> list:
    """
    Fuzzy and synonym-aware category matcher for Knowledge Base ingestion and refine.
    Maps terms like 'acne', 'jerawat', 'flek', 'brightening' to actual database Category objects.
    Scans content_text as fallback if LLM output is empty or unrecognized.
    """
    if not db_categories:
        return []

    valid_cat_ids = {str(c.get("id")).lower(): c for c in db_categories if isinstance(c, dict) and c.get("id")}
    valid_cat_names = {str(c.get("name")).strip().lower(): c for c in db_categories if isinstance(c, dict) and c.get("name")}
    
    category_alias_map = {
        "acne": "Acne Care", "jerawat": "Acne Care", "acne care": "Acne Care", "komedo": "Acne Care", "jerawat & komedo": "Acne Care",
        "anti aging": "Anti Aging", "aging": "Anti Aging", "penuaan": "Anti Aging", "kerutan": "Anti Aging", "anti-aging": "Anti Aging",
        "dark spot": "Dark Spot", "flek": "Dark Spot", "spot": "Dark Spot", "hiperpigmentasi": "Dark Spot", "flek hitam": "Dark Spot",
        "brightening": "Brightening", "bright": "Brightening", "mencerahkan": "Brightening", "pencerah": "Brightening",
        "scar": "Scar Treatment", "bopeng": "Scar Treatment", "scar treatment": "Scar Treatment", "bekas": "Scar Treatment", "bekas jerawat": "Scar Treatment",
        "wound": "Wound Healing", "luka": "Wound Healing", "wound healing": "Wound Healing",
        "psoriasis": "Psoriasis Care", "psoriasis care": "Psoriasis Care",
        "hair care": "Hair Care", "rambut": "Hair Care", "kerontokan": "Hair Care",
        "body care": "Body Care", "tubuh": "Body Care", "kulit tubuh": "Body Care"
    }

    clean_cats = []
    seen_ids = set()

    for c in (raw_cats or []):
        cname = ""
        cid = ""
        if isinstance(c, dict):
            cid = str(c.get("id", "")).lower()
            cname = str(c.get("name", "")).strip().lower()
        elif isinstance(c, str):
            cname = c.strip().lower()

        if cname in ["category name", "category_name", "category_id", "uuid", "null", "none", ""]:
            continue

        matched_obj = None
        if cid in valid_cat_ids:
            matched_obj = valid_cat_ids[cid]
        elif cname in valid_cat_names:
            matched_obj = valid_cat_names[cname]
        elif cname in category_alias_map and category_alias_map[cname].lower() in valid_cat_names:
            matched_obj = valid_cat_names[category_alias_map[cname].lower()]
        else:
            # Check aliases inside cname
            for alias, canonical in category_alias_map.items():
                if alias in cname and canonical.lower() in valid_cat_names:
                    matched_obj = valid_cat_names[canonical.lower()]
                    break
            if not matched_obj:
                # Dynamic matching against actual DB category names
                for cat_low_name, cat_obj in valid_cat_names.items():
                    if cat_low_name in cname or cname in cat_low_name:
                        matched_obj = cat_obj
                        break

        if matched_obj and matched_obj.get("id") not in seen_ids:
            clean_cats.append(matched_obj)
            seen_ids.add(matched_obj.get("id"))

    # Dynamic Fallback: scan content_text for active DB category names and aliases
    if not clean_cats and content_text:
        text_low = content_text.lower()
        for cat_low_name, cat_obj in valid_cat_names.items():
            if len(cat_low_name) >= 3 and re.search(rf'\b{re.escape(cat_low_name)}\b', text_low):
                if cat_obj.get("id") not in seen_ids:
                    clean_cats.append(cat_obj)
                    seen_ids.add(cat_obj.get("id"))

        if not clean_cats:
            for alias, canonical in category_alias_map.items():
                if len(alias) >= 3 and re.search(rf'\b{re.escape(alias)}\b', text_low):
                    if canonical.lower() in valid_cat_names:
                        cat_obj = valid_cat_names[canonical.lower()]
                        if cat_obj.get("id") not in seen_ids:
                            clean_cats.append(cat_obj)
                            seen_ids.add(cat_obj.get("id"))

    return clean_cats



def auto_embed_images_in_summary(
    summary: str,
    images_or_urls: Union[List[str], List[Dict[str, Any]]],
    title: str = "Knowledge Image"
) -> str:
    """
    Intelligently embeds image assets into the Markdown summary based on their topic, product, or section role.
    Rather than hardcoding images below the main document title, this function:
    1. Detects product name from image metadata and places the image under that specific product's heading.
    2. Detects clinical Before/After images and places them under Clinical Results/Efficacy/Sebelum-Sesudah sections.
    3. Detects procedure/usage images and places them under Cara Pakai/Prosedur sections.
    4. Detects product packaging images and places them in the relevant Product Information section.
    5. Falls back cleanly to the first major topical subsection (##) if no specific heading matches.
    """
    # Check if summary has a | BEFORE | AFTER | table with empty cells: |  |  |
    ba_table_pattern = re.compile(r'(\|\s*BEFORE\s*\|\s*AFTER\s*\|\s*\n\|\s*\-\-\-\s*\|\s*\-\-\-\s*\|\s*\n)\|\s*\|\s*\|\s*\n', re.IGNORECASE)
    
    # Extract asset URLs
    urls = []
    for item in images_or_urls:
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"].strip())
        elif isinstance(item, str) and item.strip():
            urls.append(item.strip())

    updated = summary

    # Case 1: 3 images (device, before, after) + empty Before/After table
    if len(urls) >= 3 and ba_table_pattern.search(updated):
        img_device = urls[0]
        img_before = urls[1]
        img_after = urls[2]

        # Discover specific treatment name from markdown dynamically
        t_match = re.search(r'(?:-\s*)?\*\*(?:Jenis|Nama)\s+Treatment\*\*\s*[:=]\s*([^\n\r\|]+)', updated, re.IGNORECASE)
        if not t_match:
            t_match = re.search(r'\b(?:Jenis|Nama)\s+Treatment\s*[:=]\s*([^\n\r\|]+)', updated, re.IGNORECASE)
        if not t_match:
            t_match = re.search(r'\|\s*(?:Jenis Treatment|Nama Treatment|Treatment)\s*\|\s*([^\|\n]+)\s*\|', updated, re.IGNORECASE)
        
        treatment_name = ""
        if t_match:
            treatment_name = t_match.group(1).strip()
        if not treatment_name:
            treatment_name = re.sub(r'(?i)\b(Dummy|Documentation|Detail|Dokumentasi)\b', '', title).strip()
        
        treatment_name = re.sub(r'[\-_/&]+', ' ', treatment_name).strip()
        treatment_name = re.sub(r'\s+', ' ', treatment_name).strip()
        if treatment_name and not any(k in treatment_name.lower() for k in ["treatment", "perawatan"]):
            treatment_name = f"{treatment_name} Treatment"

        # Replace empty cells in Before/After table with actual image tags
        table_replacement = rf'\1| ![Foto Sebelum Perawatan - {treatment_name}]({img_before}) | ![Foto Sesudah Perawatan - {treatment_name}]({img_after}) |\n'
        updated = ba_table_pattern.sub(table_replacement, updated)

        if img_device not in updated:
            alat_pattern = re.compile(r'(?mi)^(#{2,6}\s*.*?(alat|device|peralatan).*?)$')
            m = alat_pattern.search(updated)
            if m:
                pos = m.end()
                img_md = f"\n\n![Foto Treatment - {treatment_name}]({img_device})\n\n"
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
            else:
                updated += f"\n\n![Foto Treatment - {treatment_name}]({img_device})"

        # Clean up any leftover top-level image dump under ## Gambar Alat Treatment
        for img in [img_before, img_after]:
            count = updated.count(img)
            if count > 1:
                updated = re.sub(rf'!\[[^\]]*\]\({re.escape(img)}\)\s*\n*', '', updated, count=1)

    # Normalize inputs into standard asset dictionary representations
    normalized_assets = []
    for item in images_or_urls:
        if isinstance(item, dict):
            url = item.get("url") or item.get("image_url")
            if url and isinstance(url, str) and url.strip():
                normalized_assets.append({
                    "id": item.get("id", ""),
                    "url": url.strip(),
                    "role": item.get("role", "PRODUCT_PACKAGING"),
                    "product_name": item.get("product_name", ""),
                    "caption": item.get("caption") or title
                })
        elif isinstance(item, str) and item.strip():
            clean_u = item.strip()
            # Infer basic role from URL path keywords if only string URL is provided
            u_lower = clean_u.lower()
            role = "PRODUCT_PACKAGING"
            if any(k in u_lower for k in ["before", "after", "klinis", "clinical"]):
                role = "CLINICAL_AFTER" if "after" in u_lower else "CLINICAL_BEFORE"
            elif any(k in u_lower for k in ["step", "prosedur", "cara", "treatment", "procedure"]):
                role = "TREATMENT_PROCEDURE"
            
            normalized_assets.append({
                "id": "",
                "url": clean_u,
                "role": role,
                "product_name": "",
                "caption": title
            })

    for asset in normalized_assets:
        clean_u = asset["url"]
        # If the image URL is already embedded anywhere in the Markdown summary, respect LLM/table placement!
        if clean_u in updated:
            continue

        role = str(asset.get("role", "PRODUCT_PACKAGING")).upper()
        prod_name = str(asset.get("product_name", "")).strip()
        caption = str(asset.get("caption", "")).strip() or title
        
        # Build descriptive Markdown tag
        alt_label = caption if caption and caption != "Knowledge Image" else (prod_name or title)
        img_md = f"\n\n![{alt_label}]({clean_u})\n\n"

        placed = False

        # --- HEURISTIC 1: Match by Clinical Role (Before / After) ---
        if not placed and role in ("CLINICAL_BEFORE", "CLINICAL_AFTER"):
            clinical_regex = re.compile(
                r'(?mi)^(#{2,6}\s*.*?(hasil\s*(uji|klinis|studi|pemakaian)?|sebelum|sesudah|before|after|efikasi|efektivitas|studi\s*klinis).*?)$'
            )
            match = clinical_regex.search(updated)
            if match:
                pos = match.end()
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                placed = True

        # --- HEURISTIC 2: Match by Treatment Procedure / Usage ---
        if not placed and role == "TREATMENT_PROCEDURE":
            proc_regex = re.compile(
                r'(?mi)^(#{2,6}\s*.*?(cara\s*(pakai|pemakaian|penggunaan)|petunjuk|prosedur|aturan\s*pakai|langkah|aplikasi|sop).*?)$'
            )
            match = proc_regex.search(updated)
            if match:
                pos = match.end()
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                placed = True

        # --- HEURISTIC 3: Match by Specific Sub-Product Heading (## or ###) ---
        if not placed and prod_name and len(prod_name) > 2:
            prod_regex = re.compile(
                r'(?mi)^(#{2,6}\s*.*?' + re.escape(prod_name) + r'.*?)$'
            )
            match = prod_regex.search(updated)
            if match:
                pos = match.end()
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                placed = True
            else:
                words = [w for w in re.split(r'[\s\-_/]+', prod_name) if len(w) > 3 and w.lower() not in ["produk", "product"]]
                if len(words) >= 2:
                    fuzzy_prod_regex = re.compile(
                        r'(?mi)^(#{2,6}\s*.*?' + r'.*?'.join(re.escape(w) for w in words[:3]) + r'.*?)$'
                    )
                    fuzzy_match = fuzzy_prod_regex.search(updated)
                    if fuzzy_match:
                        pos = fuzzy_match.end()
                        updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                        placed = True

        # --- HEURISTIC 3.5: Match by Page/Slide Number in image filename to Slide Heading ---
        if not placed:
            p_match = re.search(r'[_\/]p(?:age)?_?(\d+)[_\.]', clean_u, re.IGNORECASE)
            if p_match:
                p_num = int(p_match.group(1))
                page_head_regex = re.compile(
                    rf'(?mi)^(#{{1,4}}\s*.*?(?:slide|halaman|page)\s*{p_num}\b.*?)$'
                )
                head_match = page_head_regex.search(updated)
                if head_match:
                    pos = head_match.end()
                    updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                    placed = True

        # --- HEURISTIC 4: Match by Product Information / Packaging Section ---
        if not placed and role == "PRODUCT_PACKAGING":
            info_regex = re.compile(
                r'(?mi)^(#{2,6}\s*.*?(informasi\s*produk|detail\s*produk|spesifikasi|kemasan|overview|deskripsi\s*produk|produk).*?)$'
            )
            match = info_regex.search(updated)
            if match:
                pos = match.end()
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                placed = True

        # --- FALLBACK: Only for SINGLE-IMAGE documents (e.g. single product flyer/hero photo) ---
        # Never dump a gallery of unplaced orphan images under # Title or arbitrary ## Headings.
        # If the document has exactly 1 image and NO images are currently placed anywhere in the document:
        if not placed and len(normalized_assets) == 1 and not re.search(r'!\[.*?\]\([^\)]+\)', updated):
            header_match = re.search(r'^(#+\s*[^\n]+)', updated, flags=re.MULTILINE)
            if header_match:
                pos = header_match.end()
                updated = updated[:pos] + img_md + updated[pos:].lstrip("\n")
                placed = True
            else:
                updated = img_md.strip() + "\n\n" + updated
                placed = True

    # Post-processing: Remove any images mistakenly placed under ## Ringkasan / ## Ringkasan Dokumen
    # (Ringkasan should contain executive bullet points, not duplicate photo dumps)
    ringkasan_match = re.search(r'(?mi)(##\s*Ringkasan\s*(?:Dokumen)?\b)([\s\S]*?)(?=\n##|\Z)', updated)
    if ringkasan_match:
        r_header = ringkasan_match.group(1)
        r_body = ringkasan_match.group(2)
        r_cleaned = re.sub(r'!\[[^\]]*\]\([^\)]+\)\s*\n*', '', r_body)
        if r_cleaned != r_body:
            updated = updated[:ringkasan_match.start()] + r_header + r_cleaned + updated[ringkasan_match.end():]

    return updated


router = APIRouter()

def clean_duplicate_headers(text: str) -> str:
    """
    Cleans up accidental duplicated consecutive headers or lines in markdown text.
    For example:
        ERHA Acneact Acne Spot Gel
        
        ERHA Acneact Acne Spot Gel
    becomes:
        ## ERHA Acneact Acne Spot Gel
    """
    if not text:
        return ""
    lines = text.split("\n")
    cleaned_lines = []
    prev_line = None
    for line in lines:
        stripped = line.strip()
        # Avoid repeating identical adjacent title lines (e.g. "Title\n\nTitle")
        if stripped and prev_line and stripped.lower() == prev_line.lower():
            continue
        cleaned_lines.append(line)
        if stripped:
            prev_line = stripped
    return "\n".join(cleaned_lines)


def extract_sku_and_target(user_prompt: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts SKU value and optional product target from user prompt.
    Supports single and multi-product target prompts.
    """
    import re
    # 1. "SKU <target> : <CODE>" e.g. "SKU Acne Spot Gel: PRO-565346"
    m0 = re.search(r'\bsku\b\s+(.+?)\s*[:=]\s*([A-Za-z0-9\-_]+)', user_prompt, re.IGNORECASE)
    if m0:
        middle = m0.group(1).strip(" :_-\t")
        code = m0.group(2).strip()
        if middle and middle.lower() not in ("nomor", "kode", "no", "nya", "dokumen", "produk", "jadi", "menjadi", ""):
            return code, middle

    # 2. "tambahkan SKU PRO-565346 (untuk|pada|di) <target>"
    m1 = re.search(r'\bsku\b\s*(?:nomor|kode|no)?\s*[:=\s]?\s*([A-Za-z0-9\-_]+)\s+(?:pada|untuk|di|buat)\s+(.+)', user_prompt, re.IGNORECASE)
    if m1:
        code = m1.group(1).strip()
        target = m1.group(2).strip(" .")
        if code.lower() not in ("jadi", "menjadi", "none", "null", "tidak", "ada", "kosong", "baru", "untuk", "pada"):
            return code, target

    # 3. "ganti nomor SKU <target> (jadi|menjadi|adalah) <CODE>"
    m2 = re.search(r'\bsku\b\s*(?:nomor|kode|no)?\s+(.+?)\s+(?:jadi|menjadi|adalah)\s*([A-Za-z0-9\-_]+)', user_prompt, re.IGNORECASE)
    if m2:
        middle = m2.group(1).strip(" :_-\t")
        code = m2.group(2).strip()
        if middle and middle.lower() not in ("nomor", "kode", "no", "nya", "dokumen", "produk", "jadi", "menjadi", ""):
            return code, middle
        if code.lower() not in ("jadi", "menjadi", "none", "null", "tidak", "ada", "kosong", "baru"):
            return code, None

    # 4. "ganti SKU (jadi|menjadi|adalah|=|:) <CODE>" or "SKU: <CODE>"
    m3 = re.search(r'\bsku\b\s*(?:nomor|kode|no)?\s*(?:jadi|menjadi|adalah|=|:|\s)\s*([A-Za-z0-9\-_]+)', user_prompt, re.IGNORECASE)
    if m3:
        cand = m3.group(1).strip()
        if cand.lower() not in ("jadi", "menjadi", "none", "null", "tidak", "ada", "kosong", "baru", "untuk", "pada", "di", "nomor", "kode", "no"):
            return cand, None

    # 5. Fallback 'kode sku ...' or 'nomor sku ...'
    m4 = re.search(r'(?:nomor|kode)\s+sku\s*(?:jadi|menjadi|adalah|=|:|\s)?\s*([A-Za-z0-9\-_]+)', user_prompt, re.IGNORECASE)
    if m4:
        cand = m4.group(1).strip()
        if cand.lower() not in ("jadi", "menjadi", "none", "null", "tidak", "ada", "kosong", "baru", "untuk", "pada"):
            return cand, None

    return None, None


def extract_price_and_target(user_prompt: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts Price value and optional product target from user prompt.
    """
    import re
    # 1. "harga <target> (jadi|menjadi|adalah|=|:) Rp 50.000"
    m1 = re.search(r'\b(?:harga|price|tarif|biaya)\b\s+(.+?)\s+(?:jadi|menjadi|adalah|=|:)\s*(?:rp\.?\s*)?([0-9\.\,]+)', user_prompt, re.IGNORECASE)
    if m1:
        middle = m1.group(1).strip(" :_-\t")
        raw_price = m1.group(2).strip()
        target_hint = middle if middle.lower() not in ("nya", "produk", "dokumen", "jadi", "menjadi", "") else None
        return f"Rp {raw_price}" if not raw_price.lower().startswith("rp") else raw_price, target_hint

    # 2. "harga (jadi|menjadi|=|:|\s)* (rp 50.000) (pada|untuk|di|buat) <target>"
    m2 = re.search(r'\b(?:harga|price|tarif|biaya)\b\s*(?:jadi|menjadi|adalah|=|:|\s)?\s*(?:rp\.?\s*)?([0-9\.\,]+)\s+(?:pada|untuk|di|buat)\s+(.+)', user_prompt, re.IGNORECASE)
    if m2:
        raw_price = m2.group(1).strip()
        target = m2.group(2).strip(" .")
        return f"Rp {raw_price}" if not raw_price.lower().startswith("rp") else raw_price, target

    # 3. Simple "harga jadi Rp 50.000" or "harga: 50.000"
    m3 = re.search(r'\b(?:harga|price|tarif|biaya)\b\s*(?:jadi|menjadi|adalah|=|:|\s)?\s*(?:rp\.?\s*)?([0-9\.\,]+)', user_prompt, re.IGNORECASE)
    if m3:
        raw_price = m3.group(1).strip()
        return f"Rp {raw_price}" if not raw_price.lower().startswith("rp") else raw_price, None

    return None, None


def extract_text_replacement(user_prompt: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts text/ingredient replacement targets from user prompt, e.g.:
    Ubah "Hyaluronic Acid" menjadi "Polyglutamic Acid (PGA)"
    Ganti "A" jadi "B"
    """
    import re
    # 1. Quoted replacement: Ubah "X" menjadi "Y" or Ganti 'X' jadi 'Y'
    m = re.search(r'\b(?:ubah|ganti|replace|update)\s+["\']([^"\']+)["\']\s+(?:menjadi|jadi|ke|dengan|with|to)\s+["\']([^"\']+)["\']', user_prompt, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 2. Semi-quoted: Ubah "X" menjadi Y
    m2 = re.search(r'\b(?:ubah|ganti|replace|update)\s+["\']([^"\']+)["\']\s+(?:menjadi|jadi|ke|dengan|with|to)\s+([A-Za-z0-9\s\(\)\.\,\-]+)', user_prompt, re.IGNORECASE)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()

    # 3. Unquoted keyword replacement (excluding sku, harga, gambar, foto)
    m3 = re.search(r'\b(?:ubah|ganti|replace)\s+([A-Za-z0-9\s]{3,30}?)\s+(?:menjadi|jadi|ke|dengan|with|to)\s+([A-Za-z0-9\s\(\)\.\,\-]{3,40})', user_prompt, re.IGNORECASE)
    if m3:
        o = m3.group(1).strip()
        n = m3.group(2).strip()
        forbidden = ("sku", "harga", "price", "gambar", "foto", "image", "status", "judul", "kategori")
        if not any(f in o.lower() for f in forbidden) and not any(f in n.lower() for f in forbidden):
            return o, n
    return None, None


def strip_callout_banners(text: str) -> str:
    """
    Strips audit callout banners (> **Ringkasan Perubahan:** ...) and notes from summary text.
    Ensures saved knowledge documents are clean and never corrupted by audit logs.
    """
    if not text:
        return ""
    cleaned = re.sub(
        r'(?:^|\n)>\s*\*\*(?:Ringkasan Perubahan|Catatan):\*\*[\s\S]*?(?=\n#{1,4}\s+|\n\*\*[^*]+\*\*|\Z)',
        '',
        text,
        flags=re.IGNORECASE
    )
    return cleaned.strip()


def extract_product_deletion(user_prompt: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extracts product deletion instructions from user prompt.
    Returns (target_name, target_ingredient, deletion_type).
    deletion_type can be 'image', 'ingredient' or 'name'.
    """
    import re
    if not user_prompt:
        return None, None, None

    def _clean_target_name(name: str) -> Optional[str]:
        if not name:
            return None
        t = re.split(r'\b(?:pada|dari|di|dokumen|katalog|kb|database)\b', name, flags=re.IGNORECASE)[0]
        t = re.sub(r'^[\s\*_\`"\'“”.,]+|[\s\*_\`"\'“”.,]+$', '', t).strip()
        while True:
            t_sub = re.sub(r'^(?:dari|pada|untuk|buat|bagi|for|from|of|in|at|di)\s+', '', t, flags=re.IGNORECASE).strip()
            t_sub = re.sub(r'^(?:data\s+)?(?:produk|products?|item|barang)\s+', '', t_sub, flags=re.IGNORECASE).strip()
            if t_sub == t:
                break
            t = t_sub
        forbidden = ("yang", "semua", "seluruh", "ini", "itu", "nya", "produk", "product", "products", "item", "barang", "data", "gambar", "foto", "image", "picture")
        if t and t.lower() in forbidden:
            return None
        return t or None

    # 0. By image deletion: e.g. hapus gambar product Spot Gel New Version, hapus foto "ERHA Acneact", hilangkan gambar
    m_img = re.search(
        r'\b(?:hapus|delete|hilangkan|remove|buang|bersihkan|tiadakan)\s+(?:semua\s+|seluruh\s+)?(?:gambar|foto|image|picture|visual|banner)\s*(?:dari|pada|untuk|buat|for|from|of)?\s*(?:(?:data\s+)?(?:produk|products?|item|barang))?\s*(?:["\'“]([^"\'”]+)["\'”]|([A-Za-z0-9\s\-_]{3,60}))?',
        user_prompt,
        re.IGNORECASE
    )
    if m_img:
        raw_target = (m_img.group(1) or m_img.group(2) or "").strip()
        target_name = _clean_target_name(raw_target)
        return target_name or None, None, "image"

    # 1. By ingredient: e.g. hapus seluruh produk yang mengandung "Betaine" or *Betaine*
    m_ingr = re.search(
        r'\b(?:hapus|delete|hilangkan|remove|buang|bersihkan|tiadakan)\s+(?:seluruh\s+|semua\s+)?(?:data\s+)?(?:produk|products?|item|barang)?\s*(?:yang\s+)?(?:mengandung|memuat|berisi|memiliki|ada\s+kandungan|(?:dengan\s+)?kandungan|berbahan|(?:dengan\s+)?ingredients?)\s+([^\n\r]+)',
        user_prompt,
        re.IGNORECASE
    )
    if m_ingr:
        raw_ingr = m_ingr.group(1).strip()
        raw_ingr = re.split(r'\b(?:pada|dari|di|dokumen|katalog|kb|database)\b', raw_ingr, flags=re.IGNORECASE)[0]
        target_ingr = re.sub(r'^[\s\*_\`"\'“”.,]+|[\s\*_\`"\'“”.,]+$', '', raw_ingr).strip()
        if target_ingr and len(target_ingr) >= 2:
            return None, target_ingr, "ingredient"

    # 2. By quoted product name: e.g. delete product "Sakura FW New Version", hapus data "Spot Gel"
    m_name = re.search(
        r'\b(?:hapus|delete|hilangkan|remove|buang)\s+(?:(?:data\s+)?(?:produk|products?|item|barang))?\s*["\'“]([^"\'”]+)["\'”]',
        user_prompt,
        re.IGNORECASE
    )
    if m_name:
        target_name = _clean_target_name(m_name.group(1))
        if target_name and target_name.lower() not in ("gambar", "foto", "image", "picture", "tabel", "section", "bagian", "warning", "warnings"):
            return target_name, None, "name"

    # 3. By unquoted product name: e.g. hapus product Spot Gel New Version di katalog, hapus data produk Spot Gel New Version
    m_unquoted = re.search(
        r'\b(?:hapus|delete|hilangkan|remove|buang)\s+(?:(?:data\s+)?(?:produk|products?|item|barang)\s+)?([A-Za-z0-9\s\-_]{3,60})',
        user_prompt,
        re.IGNORECASE
    )
    if m_unquoted:
        raw_name = m_unquoted.group(1).strip()
        target_name = _clean_target_name(raw_name)
        forbidden_starts = ("gambar", "foto", "image", "picture", "tabel", "section", "bagian", "warning", "warnings", "yang", "semua", "seluruh", "dengan")
        if target_name and not any(target_name.lower().startswith(f) for f in forbidden_starts):
            return target_name, None, "name"

    return None, None, None



def extract_product_cards_from_summary(summary: str, target_product_names: Optional[List[str]] = None) -> str:
    """
    Extracts modular product card markdown blocks from summary markdown.
    If target_product_names is provided, extracts only matching product cards.
    If target_product_names is None or empty, extracts all product cards found in summary.
    """
    import re
    if not summary or not summary.strip():
        return ""

    clean_summary = strip_callout_banners(summary)
    prod_boundary_pattern = r'(?=(?:^|\n)#{1,4}\s+[^\n]+)'
    raw_sections = [s.strip() for s in re.split(prod_boundary_pattern, clean_summary) if s.strip()]

    cards = []
    
    clean_targets = []
    distinctive_targets = []
    generic_words = {
        'produk', 'product', 'erha', 'and', 'the', 'with', 'for',
        'cream', 'serum', 'gel', 'lotion', 'toner', 'wash', 'cleanser',
        'facial', 'sunscreen', 'moisturizer', 'spot', 'care', 'treatment'
    }

    if target_product_names:
        for t in target_product_names:
            if not t:
                continue
            t_clean = t.lower().strip()
            clean_targets.append(t_clean)
            dist_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', t_clean) if w.lower() not in generic_words]
            if dist_words:
                distinctive_targets.append(dist_words)
            else:
                all_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', t_clean) if w.lower() not in ('produk', 'product', 'erha', 'and', 'the')]
                if all_words:
                    distinctive_targets.append(all_words)

    for sec in raw_sections:
        sec_str = sec.strip()
        # Reject non-product sections (Patient profiles, slide intros, procedure metrics, thank you slides, evaluation tables)
        is_patient_or_non_product = bool(re.search(
            r'(?:profil\s+pasien|data\s+pasien|-\s*\*\*Pasien\*\*|-\s*\*\*Keluhan\s+Utama|-\s*\*\*Riwayat\s*&?\s*Catatan|\bpasien\s*:\s*#|\bevaluasi\s+hasil\b|\btahapan\s+prosedur\b|\bprosedur\s*&|\bsesi\s+perawatan\b|\bminggu\s*\/\s*sesi\b|\bbulan\s+program\b|\bterima\s+kasih\b|\blaporan\s+hasil\s+perawatan\b)',
            sec_str,
            re.IGNORECASE
        ))
        if is_patient_or_non_product:
            continue

        has_name = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec_str, re.IGNORECASE)
        has_prod_attr = bool(re.search(r'-\s*\*\*(?:Brand|Kategori|Harga|Ukuran|Kandungan|Manfaat|Deskripsi|Metode Aplikasi|Indikasi|Cara Pakai)\*\*\s*:', sec_str, re.IGNORECASE))
        is_prod_heading = bool(re.match(r'^#{1,4}\s+(?:Detail\s+Produk|Informasi\s+Produk|[A-Za-z0-9\s\-\+\%]+(?:Serum|Cream|Gel|Lotion|Toner|Cleanser|Sunscreen|Moisturizer|Facial|Wash|Mask|Shampoo|Ampoule|Solution))', sec_str, re.IGNORECASE))

        if not (has_prod_attr and (has_name or is_prod_heading or re.match(r'^#{1,4}\s+', sec_str))):
            continue

        prod_name = has_name.group(1).strip() if has_name else ""
        p_lower = prod_name.lower()
        p_full = (prod_name + " " + sec_str).lower()

        if clean_targets:
            matched = False
            # 1. Exact or substring match of full target name or product name
            for t_clean in clean_targets:
                t_norm = re.sub(r'^(?:erha\s+|the\s+)', '', t_clean).strip()
                p_norm = re.sub(r'^(?:erha\s+|the\s+)', '', p_lower).strip()
                if t_norm in p_norm or p_norm in t_norm or t_clean in p_lower:
                    matched = True
                    break

            # 2. Distinctive words match (ALL distinctive words of target must be present in section)
            if not matched and distinctive_targets:
                for dist_words in distinctive_targets:
                    if all(w in p_full for w in dist_words):
                        matched = True
                        break

            if not matched:
                continue

        card_text = sec_str
        if not re.match(r'^#{1,4}\s+', card_text):
            card_text = "### Detail Produk\n" + card_text
        else:
            card_text = re.sub(r'^#{1,4}\s+', '### ', card_text, count=1)
        
        cards.append(card_text)

    return "\n\n".join(cards).strip()


def format_chat_response_with_cards(
    confirmation: str,
    summary: str,
    target_product_names: Optional[List[str]] = None,
    intro_label: str = "Berikut adalah daftar produk yang diperbarui:"
) -> str:
    """
    Formats an assistant chat reply turn to display:
    1. Top: confirmation message (e.g. '✅ Produk X telah berhasil dihapus...')
    2. Bottom: list of updated product cards from the document summary
    """
    confirmation = (confirmation or "").strip()
    if not confirmation:
        return ""

    # Never append product cards or update headers if confirmation indicates
    # an item was not found, operation failed, or nothing was modified.
    negation_keywords = [
        "tidak ditemukan",
        "tidak ada",
        "tidak terdapat",
        "gagal",
        "tidak berhasil",
        "maaf",
        "mohon maaf",
        "not found",
        "cannot be found",
        "tidak dapat",
        "belum terdaftar"
    ]
    conf_lower = confirmation.lower()
    if any(k in conf_lower for k in negation_keywords):
        return confirmation

    if not summary or not summary.strip():
        return confirmation

    cards_md = extract_product_cards_from_summary(summary, target_product_names=target_product_names)
    if not cards_md.strip() and not target_product_names:
        cards_md = extract_product_cards_from_summary(summary)

    if cards_md.strip():
        label = intro_label or "Berikut adalah detail produk yang diperbarui:"
        return f"{confirmation}\n\n{label}\n\n{cards_md}".strip()
    
    # Fallback for general/clinical/table/SOP documents without product cards:
    # Ensure the updated knowledge content is displayed in full
    clean_summary = summary.strip()
    label = "Berikut adalah isi knowledge yang telah diperbarui:"
    return f"{confirmation}\n\n### {label}\n\n{clean_summary}".strip()


def apply_refinements_to_content(
    user_prompt: str,
    summary: str,
    chunks: List[Dict[str, Any]],
    title: Optional[str] = None,
    base_summary: Optional[str] = None
) -> tuple[str, List[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
    """
    Applies deterministic field overrides for SKU, Price, Title, Replacements, and Deletions
    if commanded in user_prompt, with full support for single-product and multi-product documents.
    Ensures modifications targeted at a specific product apply ONLY to that product's section and chunks.
    Never prepends audit log callouts into summary text; returns concise conversational feedback_message.
    """
    import re
    updated_summary = strip_callout_banners(clean_duplicate_headers(summary or ""))
    updated_title = title
    extracted_sku, sku_target = extract_sku_and_target(user_prompt)
    extracted_price, price_target = extract_price_and_target(user_prompt)
    feedback_message = None

    # Split summary into product sections if multi-product
    product_section_pattern = r'(?=(?:^|\n)##\s+[^\n]+|(?:^|\n)Informasi Produk\s+[^\n]+)'
    sections = [s for s in re.split(product_section_pattern, updated_summary) if s]

    if len(sections) > 1 and (extracted_sku or extracted_price):
        new_sections = []
        for sec in sections:
            sec_lower = sec.lower()
            
            # Check if this section is the target for SKU
            is_sku_target = True
            if sku_target:
                sku_target_clean = sku_target.lower()
                target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', sku_target_clean) if w not in ('erha', 'the', 'and', 'for', 'product', 'overview', 'produk')]
                if target_words:
                    is_sku_target = any(tw in sec_lower for tw in target_words)

            # Check if this section is the target for Price
            is_price_target = True
            if price_target:
                price_target_clean = price_target.lower()
                target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', price_target_clean) if w not in ('erha', 'the', 'and', 'for', 'product', 'overview', 'produk')]
                if target_words:
                    is_price_target = any(tw in sec_lower for tw in target_words)

            sec_updated = sec
            if extracted_sku and is_sku_target:
                if re.search(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', r'\1 ' + extracted_sku, sec_updated, count=1, flags=re.IGNORECASE)
                elif re.search(r'((?:-\s*)?\*{0,2}Product Name\*{0,2}\s*:[^\n]+)', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'((?:-\s*)?\*{0,2}Product Name\*{0,2}\s*:[^\n]+)', r'\1\n- **SKU**: ' + extracted_sku, sec_updated, count=1, flags=re.IGNORECASE)
                elif re.search(r'(#{0,3}\s*Product Overview\b[^\n]*)', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'(#{0,3}\s*Product Overview\b[^\n]*)', r'\1\n- **SKU**: ' + extracted_sku, sec_updated, count=1, flags=re.IGNORECASE)

            if extracted_price and is_price_target:
                if re.search(r'((?:-\s*)?\*{0,2}(?:Price|Harga)\*{0,2}\s*:)[^\n]+', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'((?:-\s*)?\*{0,2}(?:Price|Harga)\*{0,2}\s*:)[^\n]+', r'\1 ' + extracted_price, sec_updated, count=1, flags=re.IGNORECASE)
                elif re.search(r'((?:-\s*)?\*{0,2}Net Content\*{0,2}\s*:[^\n]+)', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'((?:-\s*)?\*{0,2}Net Content\*{0,2}\s*:[^\n]+)', r'\1\n- **Harga**: ' + extracted_price, sec_updated, count=1, flags=re.IGNORECASE)
                elif re.search(r'(#{0,3}\s*Product Overview\b[^\n]*)', sec_updated, re.IGNORECASE):
                    sec_updated = re.sub(r'(#{0,3}\s*Product Overview\b[^\n]*)', r'\1\n- **Harga**: ' + extracted_price, sec_updated, count=1, flags=re.IGNORECASE)

            new_sections.append(sec_updated)
        updated_summary = "".join(new_sections)
    else:
        # Single-product document
        if extracted_sku:
            if re.search(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', updated_summary, re.IGNORECASE):
                updated_summary = re.sub(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', r'\1 ' + extracted_sku, updated_summary, count=1, flags=re.IGNORECASE)
            else:
                if re.search(r'((?:-\s*)?\*{0,2}Brand\*{0,2}\s*:[^\n]+)', updated_summary, re.IGNORECASE):
                    updated_summary = re.sub(r'((?:-\s*)?\*{0,2}Brand\*{0,2}\s*:[^\n]+)', r'\1\n- **SKU**: ' + extracted_sku, updated_summary, count=1, flags=re.IGNORECASE)
                elif re.search(r'((?:-\s*)?\*{0,2}Product Name\*{0,2}\s*:[^\n]+)', updated_summary, re.IGNORECASE):
                    updated_summary = re.sub(r'((?:-\s*)?\*{0,2}Product Name\*{0,2}\s*:[^\n]+)', r'\1\n- **SKU**: ' + extracted_sku, updated_summary, count=1, flags=re.IGNORECASE)
                elif re.search(r'(#{0,3}\s*Product Overview\b[^\n]*)', updated_summary, re.IGNORECASE):
                    updated_summary = re.sub(r'(#{0,3}\s*Product Overview\b[^\n]*)', r'\1\n- **SKU**: ' + extracted_sku, updated_summary, count=1, flags=re.IGNORECASE)
                else:
                    updated_summary += f'\n\n- **SKU**: {extracted_sku}'

        if extracted_price:
            if re.search(r'((?:-\s*)?\*{0,2}(?:Price|Harga)\*{0,2}\s*:)[^\n]+', updated_summary, re.IGNORECASE):
                updated_summary = re.sub(r'((?:-\s*)?\*{0,2}(?:Price|Harga)\*{0,2}\s*:)[^\n]+', r'\1 ' + extracted_price, updated_summary, count=1, flags=re.IGNORECASE)
            else:
                if re.search(r'((?:-\s*)?\*{0,2}Net Content\*{0,2}\s*:[^\n]+)', updated_summary, re.IGNORECASE):
                    updated_summary = re.sub(r'((?:-\s*)?\*{0,2}Net Content\*{0,2}\s*:[^\n]+)', r'\1\n- **Harga**: ' + extracted_price, updated_summary, count=1, flags=re.IGNORECASE)
                elif re.search(r'(#{0,3}\s*Product Overview\b[^\n]*)', updated_summary, re.IGNORECASE):
                    updated_summary = re.sub(r'(#{0,3}\s*Product Overview\b[^\n]*)', r'\1\n- **Harga**: ' + extracted_price, updated_summary, count=1, flags=re.IGNORECASE)

    if extracted_sku:
        sku_msg = f"Nomor SKU berhasil diperbarui menjadi {extracted_sku}."
        feedback_message = format_chat_response_with_cards(
            confirmation=sku_msg,
            summary=updated_summary,
            target_product_names=[sku_target] if sku_target else None,
            intro_label="Berikut adalah detail produk yang diperbarui:"
        )
    elif extracted_price:
        price_msg = f"Harga berhasil diperbarui menjadi {extracted_price}."
        feedback_message = format_chat_response_with_cards(
            confirmation=price_msg,
            summary=updated_summary,
            target_product_names=[price_target] if price_target else None,
            intro_label="Berikut adalah detail produk yang diperbarui:"
        )

    # 3. Synchronize chunks with targeted SKU modifications
    for chunk in chunks:
        if isinstance(chunk, dict):
            chunk_text = chunk.get("text", "")
            chunk_meta = chunk.get("metadata", {})
            chunk_prod = chunk_meta.get("product_name") or chunk_meta.get("entity") or ""
            chunk_combined = (chunk_text + " " + chunk_prod).lower()
            
            should_update_sku = True
            if extracted_sku and sku_target:
                target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', sku_target.lower()) if w not in ('erha', 'the', 'and', 'for', 'product', 'overview', 'produk')]
                if target_words:
                    should_update_sku = any(tw in chunk_combined for tw in target_words)

            if should_update_sku and extracted_sku:
                if "metadata" not in chunk or not isinstance(chunk["metadata"], dict):
                    chunk["metadata"] = {}
                chunk["metadata"]["sku"] = extracted_sku
                if re.search(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', chunk_text, re.IGNORECASE):
                    chunk["text"] = re.sub(r'((?:-\s*)?\*{0,2}SKU\*{0,2}\s*:)[^\n]+', r'\1 ' + extracted_sku, chunk_text, count=1, flags=re.IGNORECASE)
                elif re.search(r'((?:-\s*)?\*{0,2}Brand\*{0,2}\s*:[^\n]+)', chunk_text, re.IGNORECASE):
                    chunk["text"] = re.sub(r'((?:-\s*)?\*{0,2}Brand\*{0,2}\s*:[^\n]+)', r'\1\n- **SKU**: ' + extracted_sku, chunk_text, count=1, flags=re.IGNORECASE)

    # 4. Text & Ingredient Replacement
    extracted_replace_old, extracted_replace_new = extract_text_replacement(user_prompt)
    if extracted_replace_old and extracted_replace_new:
        old_pattern = re.compile(re.escape(extracted_replace_old), re.IGNORECASE)
        affected_products = []
        
        clean_base_summary = strip_callout_banners(updated_summary)
        sections = re.split(r'(?=\n#{1,4}\s+)', "\n" + clean_base_summary)
        new_secs = []

        for sec in sections:
            if not sec.strip():
                continue
            name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec)
            p_name = name_m.group(1).strip() if name_m else ""
            if not p_name:
                head_m = re.search(r'^#{1,4}\s+([^\n]+)', sec.strip())
                if head_m:
                    p_name = head_m.group(1).strip()

            # Direct match with old_pattern
            if old_pattern.search(sec):
                sec = old_pattern.sub(extracted_replace_new, sec)
                if p_name and p_name not in affected_products:
                    affected_products.append(p_name)

            new_secs.append(sec)

        updated_summary = "".join(new_secs).strip()

        # Synchronize chunks with text replacements
        for chunk in chunks:
            if isinstance(chunk, dict) and "text" in chunk:
                if old_pattern.search(chunk["text"]):
                    chunk["text"] = old_pattern.sub(extracted_replace_new, chunk["text"])

        if affected_products:
            rep_msg = f"Berhasil mengubah \"{extracted_replace_old}\" menjadi \"{extracted_replace_new}\" pada seluruh produk terkait ({', '.join(affected_products)})."
            feedback_message = format_chat_response_with_cards(
                confirmation=rep_msg,
                summary=updated_summary,
                target_product_names=affected_products,
                intro_label="Berikut adalah daftar produk yang diperbarui:"
            )
        else:
            feedback_message = f"Kandungan \"{extracted_replace_old}\" tidak ditemukan pada produk di dokumen ini."

    # 5. Image or Product Deletion
    del_name, del_ingr, del_type = extract_product_deletion(user_prompt)
    if del_type == "image":
        clean_base = strip_callout_banners(base_summary or "")
        clean_curr = strip_callout_banners(updated_summary or "")
        target_base = clean_curr

        prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'

        target_clean = del_name.lower().strip() if del_name else ""
        generic_words = {
            'produk', 'product', 'products', 'erha', 'the', 'and', 'for', 'with',
            'gambar', 'foto', 'image', 'picture', 'visual', 'banner',
            'new', 'version', 'series', 'edisi', 'baru', 'edition', 'care'
        }
        all_target_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_clean) if w not in ('produk', 'product', 'products', 'erha', 'the', 'and', 'gambar', 'foto', 'image', 'picture')]
        distinctive_target_words = [w for w in all_target_words if w not in generic_words]

        sections = [s for s in re.split(prod_boundary_pattern, target_base) if s.strip()]

        # Check if the target product was dropped in updated_summary but was present in base_summary
        # (e.g. LLM accidentally deleted the entire product instead of just its image)
        target_found_in_curr = False
        for sec in sections:
            name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec)
            p_name = name_m.group(1).strip() if name_m else ""
            if not p_name:
                h_m = re.search(r'^#{1,4}\s+([^\n\r]+)', sec.strip())
                if h_m:
                    p_name = re.sub(r'[\*\_]', '', h_m.group(1)).strip()
            p_low = p_name.lower()
            if target_clean and (target_clean == p_low or (distinctive_target_words and all(tw in p_low for tw in distinctive_target_words))):
                target_found_in_curr = True
                break

        # If target product was dropped by LLM from updated_summary, restore it from base_summary!
        if target_clean and not target_found_in_curr and clean_base:
            base_sections = [s for s in re.split(prod_boundary_pattern, clean_base) if s.strip()]
            for b_sec in base_sections:
                b_name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', b_sec)
                b_pname = b_name_m.group(1).strip() if b_name_m else ""
                if not b_pname:
                    b_hm = re.search(r'^#{1,4}\s+([^\n\r]+)', b_sec.strip())
                    if b_hm:
                        b_pname = re.sub(r'[\*\_]', '', b_hm.group(1)).strip()
                b_plow = b_pname.lower()
                if target_clean == b_plow or (distinctive_target_words and all(tw in b_plow for tw in distinctive_target_words)):
                    b_sec_no_img = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', b_sec).strip()
                    sections.append(b_sec_no_img)
                    break

        new_sections = []
        image_removed = False

        for sec in sections:
            name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec)
            p_name = name_m.group(1).strip() if name_m else ""
            if not p_name:
                h_m = re.search(r'^#{1,4}\s+([^\n\r]+)', sec.strip())
                if h_m:
                    p_name = re.sub(r'[\*\_]', '', h_m.group(1)).strip()

            is_target = False
            if not target_clean:
                is_target = True
            elif p_name:
                p_low = p_name.lower()
                if target_clean == p_low:
                    is_target = True
                elif distinctive_target_words and all(tw in p_low for tw in distinctive_target_words):
                    is_target = True
                elif all_target_words and all(tw in p_low for tw in all_target_words) and len(all_target_words) >= 2:
                    is_target = True
                elif len(target_clean) > 8 and (target_clean in p_low or (len(p_low) > 8 and p_low in target_clean)):
                    is_target = True
            elif distinctive_target_words and all(tw in sec.lower() for tw in distinctive_target_words):
                is_target = True

            if is_target:
                sec_mod = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', sec)
                if sec_mod != sec:
                    image_removed = True
                new_sections.append(sec_mod)
            else:
                new_sections.append(sec)

        updated_summary = "".join(new_sections).strip()

        # SAFE fallback: ONLY strip all images if user EXPLICITLY requested removing all images
        if not image_removed:
            is_explicit_remove_all = (not del_name) and bool(re.search(r'\b(?:semua|seluruh|all)\s+(?:gambar|foto|image|picture)\b', user_prompt, re.IGNORECASE))
            if is_explicit_remove_all or (not del_name and len(sections) <= 1):
                updated_summary = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', updated_summary).strip()

        target_label = f' untuk produk "{del_name}"' if del_name else ''
        del_msg = f"Gambar{target_label} telah berhasil dihapus. Informasi produk tetap tersimpan."
        feedback_message = format_chat_response_with_cards(
            confirmation=del_msg,
            summary=updated_summary,
            target_product_names=[del_name] if del_name else None,
            intro_label="Berikut adalah detail produk yang diperbarui:"
        )

    elif del_type:
        target_base = updated_summary
        if base_summary:
            has_cards_in_base = "Detail Produk" in base_summary
            has_cards_in_curr = "Detail Produk" in updated_summary
            if has_cards_in_base and (not has_cards_in_curr or "### Ingredients" in updated_summary):
                target_base = base_summary

        clean_base_summary = strip_callout_banners(target_base)
        prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'
        sections = [s for s in re.split(prod_boundary_pattern, clean_base_summary) if s.strip()]

        kept_sections = []
        deleted_products = []

        for sec in sections:
            name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec)
            p_name = name_m.group(1).strip() if name_m else ""

            should_delete = False
            if del_type == "ingredient" and del_ingr:
                if re.search(r'\b' + re.escape(del_ingr) + r'\b', sec, re.IGNORECASE):
                    should_delete = True
            elif del_type == "name" and del_name:
                del_name_clean = del_name.lower().strip()
                p_name_clean = p_name.lower().strip() if p_name else sec.lower().strip()

                generic_words = {
                    'produk', 'product', 'products', 'erha', 'the', 'and', 'for', 'with',
                    'new', 'version', 'series', 'edisi', 'baru', 'edition', 'care',
                    'cream', 'serum', 'gel', 'lotion', 'wash', 'cleanser', 'toner', 'facial', 'sunscreen', 'moisturizer'
                }
                distinctive_del_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', del_name_clean) if w not in generic_words]
                all_del_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', del_name_clean) if w not in ('produk', 'product', 'products', 'erha', 'the', 'and')]

                if del_name_clean == p_name_clean:
                    should_delete = True
                elif distinctive_del_words:
                    if all(w in p_name_clean for w in distinctive_del_words):
                        should_delete = True
                elif all_del_words and len(all_del_words) >= 2:
                    if all(w in p_name_clean for w in all_del_words):
                        should_delete = True
                elif len(del_name_clean) > 8 and (del_name_clean in p_name_clean or (p_name and p_name_clean in del_name_clean)):
                    should_delete = True

            if should_delete:
                display_name = p_name or "Produk terkait"
                if display_name not in deleted_products:
                    deleted_products.append(display_name)
            else:
                kept_sections.append(sec)

        updated_summary = "".join(kept_sections).strip()
        target_label = f' yang mengandung "{del_ingr}"' if del_ingr else f' "{del_name}"'
        if deleted_products:
            del_msg = f"Berhasil menghapus produk{target_label} ({', '.join(deleted_products)}) dari dokumen ini."
            feedback_message = format_chat_response_with_cards(
                confirmation=del_msg,
                summary=updated_summary,
                intro_label="Berikut adalah daftar produk yang diperbarui:"
            )
        else:
            feedback_message = f"Produk{target_label} tidak ditemukan pada dokumen ini."

    return updated_summary, chunks, updated_title, extracted_sku, feedback_message


def extract_product_retrieval_query(user_prompt: str) -> Optional[str]:
    """
    Detects if the admin instruction is a product/document retrieval or query request
    (e.g., 'berikan detail produk ERHA Acneact Acne Spot Gel', 'panggil ERHA Acneact Acne Spot Gel',
    'tampilkan produk ERHA Acneact Acne Spot Gel').
    Returns the target product name or None if prompt is a mutation/edit.
    """
    import re
    if not user_prompt:
        return None

    mutation_words = [
        r'\b(?:ubah|ganti|replace|edit|update)\b',
        r'\b(?:hapus|delete|hilangkan|remove)\b',
        r'\b(?:tambahkan|tambahka|tambah|upload|masukkan)\s+(?:gambar|foto|image|file|dokumen)\b',
    ]
    if any(re.search(pat, user_prompt, re.IGNORECASE) for pat in mutation_words):
        return None

    patterns = [
        r'(?:berikan\s+pertanyaan\s+untuk\s+)?(?:memanggil|panggil|panggilkan)\s*(?:produk|item)?\s*[:"\'\s]?\s*([a-zA-Z0-9\s&+\-–\./]{3,80})',
        r'\b(?:berikan|tampilkan|tunjukkan|lihat|cari|tolong\s+tampilkan|mohon\s+tampilkan|minta)\s+(?:detail|informasi|info|data|spesifikasi)?\s*(?:dari|tentang)?\s*(?:produk|item|barang)?\s*[:"\'\s]?\s*([a-zA-Z0-9\s&+\-–\./]{3,80})',
        r'\b(?:detail|informasi|info|spesifikasi)\s+(?:dari|tentang|produk|item|barang)\s*[:"\'\s]?\s*([a-zA-Z0-9\s&+\-–\./]{3,80})',
        r'\b(?:apa|bagaimana)\s+(?:detail|informasi|info|spesifikasi)\s+(?:dari|tentang|produk)?\s*[:"\'\s]?\s*([a-zA-Z0-9\s&+\-–\./]{3,80})'
    ]

    for pat in patterns:
        m = re.search(pat, user_prompt, re.IGNORECASE)
        if m:
            target = m.group(1).strip(' ?."\' :\t\n')
            target = re.sub(r'[\?\.!]+$', '', target).strip()
            while True:
                cleaned = re.sub(r'^(?:produk|item|barang|dari|tentang)\s+', '', target, flags=re.IGNORECASE).strip()
                if cleaned == target:
                    break
                target = cleaned
            if target.lower() not in ('ini', 'itu', 'semua', 'seluruh', 'dokumen', 'katalog', 'produk', 'detail', 'informasi', 'lengkap'):
                return target
    return None


def extract_product_card_from_summary(summary: str, target_product: str) -> Optional[str]:
    """
    Extracts the exact matching product card block (with its image and bullet attributes)
    from summary markdown for a retrieved product.
    """
    import re
    if not summary or not target_product:
        return None
    prod_boundary_pattern = r'(?=(?:^|\n)#{1,3}\s+Detail\s+Produk|(?:^|\n)##\s+(?!Detail\s+Produk)[^\n]+|(?:^|\n)Informasi\s+Produk\s+[^\n]+)'
    sections = [s for s in re.split(prod_boundary_pattern, summary) if s.strip()]
    matched_section = None
    target_clean = target_product.lower()
    target_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_clean) if w.lower() not in ('erha', 'produk', 'product', 'detail', 'item')]
    best_score = 0
    best_name = ''
    for sec in sections:
        name_m = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', sec)
        p_name = name_m.group(1).strip() if name_m else ''
        p_name_lower = p_name.lower()
        score = 0
        if target_clean in p_name_lower:
            score += 10
        elif p_name_lower and p_name_lower in target_clean:
            score += 8
        for tw in target_words:
            if tw in p_name_lower:
                score += 3
            elif tw in sec.lower():
                score += 1
        if score > best_score and score >= 4:
            best_score = score
            matched_section = sec.strip()
            best_name = p_name or target_product
    if matched_section:
        if not matched_section.startswith('#'):
            matched_section = '### Detail Produk\n' + matched_section
        return f'Berikut adalah detail produk **{best_name}**:\n\n{matched_section}'
    return None


def apply_targeted_image_swap(
    user_prompt: str, 
    summary: str, 
    new_image_url: str, 
    default_title: str,
    attachment_name: Optional[str] = None
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Extracts target product/item name from user_prompt or attachment_name and swaps or embeds new_image_url
    specifically inside that target product's section in summary markdown.
    Returns (updated_summary, replaced_old_url, target_product_name).
    """
    import re
    if not summary or not new_image_url:
        return summary, None, None

    # Detect attachment name from user_prompt note if not explicitly provided
    if not attachment_name:
        att_match = re.search(r"\[SUPPLEMENTARY ATTACHED FILE CONTENT:\s*['\"]([^'\"]+)['\"]\]", user_prompt)
        if att_match:
            attachment_name = att_match.group(1).strip()

    target_name = None

    # 1. Target Name Extraction from prompt patterns
    m_target = re.search(
        r'(?:untuk|pada|ke|buat|di|terhadap)\s+(?:produk|item)?\s*[:"\'\s]?\s*([a-zA-Z0-9\s&+\-–\./]{3,80})',
        user_prompt,
        re.IGNORECASE
    )
    if m_target:
        cand = m_target.group(1).strip(" ._-:\"'")
        cand = re.split(r'\b(?:dengan|jadi|ke|menggunakan|pake|pakai|dan|serta)\b', cand, flags=re.IGNORECASE)[0].strip()
        if cand.lower() not in ("ini", "baru", "terlampir", "nya", "dokumen", "katalog", "produk", "foto", "gambar"):
            target_name = cand

    if not target_name:
        m_action = re.search(
            r'\b(?:ganti|ubah|replace|tukar|gantikan|tambahkan|tambahka|tambah|masukkan|upload|pasang|taruh)\s+(?:gambar|foto|image|picture)?(?:\s+(?:produk|item))?\s+([a-zA-Z0-9\s&+\-–\./]{3,80}?)(?:\s+(?:dengan|jadi|ke|menggunakan|pake|pakai)|$)',
            user_prompt,
            re.IGNORECASE
        )
        if m_action:
            cand = m_action.group(1).strip(" ._-:\"'")
            if cand.lower() not in ("ini", "baru", "terlampir", "nya", "dokumen", "katalog", "produk", "foto", "gambar"):
                target_name = cand

    # Scan known products in summary and score against prompt + attachment
    known_products = []
    for h in re.findall(r'#{1,4}\s+([^\n]+)', summary):
        h_clean = h.strip()
        if not re.match(r'^(?:Detail|Overview|Info|Informasi|Spesifikasi)\s+Produk', h_clean, re.IGNORECASE):
            known_products.append(h_clean)
    for np in re.findall(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', summary):
        known_products.append(np.strip())

    # Words most product names share (a brand, a product line) do not tell products apart
    from app.rag.utils.summary_chunker import common_words
    shared_name_words = common_words(known_products)
    best_score = 0
    best_product = None
    for kp in known_products:
        kp_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', kp) if w.lower() not in shared_name_words and w.lower() != "produk"]
        if not kp_words:
            continue
        score = 0
        if attachment_name:
            att_clean = attachment_name.lower().replace("_", " ")
            score += sum(3 for w in kp_words if w in att_clean)
        score += sum(1 for w in kp_words if w in user_prompt.lower())
        if score > best_score:
            best_score = score
            best_product = kp

    if best_score >= 2 and best_product:
        target_name = best_product

    # 2. Section matching (splitting by #{1,4})
    section_pattern = r'(?=\n#{1,4}\s+)'
    sections = re.split(section_pattern, "\n" + summary)
    
    replaced_old_url = None
    target_idx = -1

    if target_name and len(sections) > 1:
        from app.rag.utils.summary_chunker import common_words
        shared_name_words = common_words([h.strip() for h in re.findall(r'#{1,4}\s+([^\n]+)', summary)])
        target_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', target_name)
                        if w.lower() not in shared_name_words and w.lower() not in ("produk", "gambar", "foto", "dengan", "ini", "jadi")]
        best_match_idx = -1
        best_match_score = 0

        for i, sec in enumerate(sections):
            sec_lower = sec.lower()
            if not target_words:
                if target_name.lower() in sec_lower:
                    best_match_idx = i
                    break
            else:
                score = sum(1 for tw in target_words if tw in sec_lower)
                if score > best_match_score:
                    best_match_score = score
                    best_match_idx = i

        if best_match_idx != -1:
            target_idx = best_match_idx

    alt_label = target_name or default_title or "Foto Produk"

    if target_idx != -1:
        sec = sections[target_idx]
        img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', sec)
        if img_match:
            existing_url = img_match.group(2).strip()
            if existing_url != new_image_url:
                replaced_old_url = existing_url
                new_sec = sec.replace(img_match.group(0), f"![{alt_label}]({new_image_url})", 1)
            else:
                replaced_old_url = None
                new_sec = sec
        else:
            hdr_match = re.search(r'^(#{1,4}\s+[^\n]+)', sec.strip())
            if hdr_match:
                hdr = hdr_match.group(1)
                new_sec = sec.replace(hdr, f"{hdr}\n![{alt_label}]({new_image_url})", 1)
            else:
                new_sec = f"![{alt_label}]({new_image_url})\n\n" + sec
        sections[target_idx] = new_sec
        updated_summary = "".join(sections).strip()
        return updated_summary, replaced_old_url, target_name

    # Check if target_name in plain text
    if target_name and target_name.lower() in summary.lower():
        lines = summary.split("\n")
        for idx, line in enumerate(lines):
            if target_name.lower() in line.lower():
                lines.insert(idx + 1, f"![{alt_label}]({new_image_url})")
                return "\n".join(lines), None, target_name

    # Fallback when no target found
    existing_imgs = re.findall(r'!\[([^\]]*)\]\(([^\)]+)\)', summary)
    if len(existing_imgs) == 1:
        if existing_imgs[0][1].strip() != new_image_url:
            replaced_old_url = existing_imgs[0][1].strip()
            updated_summary = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', f"![{alt_label}]({new_image_url})", summary, count=1)
        else:
            replaced_old_url = None
    else:
        if new_image_url not in summary:
            updated_summary = summary + f"\n\n![{alt_label}]({new_image_url})"

    return updated_summary, replaced_old_url, target_name


def preserve_existing_product_images(old_summary: str, new_summary: str, user_prompt: str) -> str:
    """
    Ensures that existing products in a document do not lose their markdown images
    due to LLM omissions during document refinement, unless the user explicitly
    instructed to delete that specific image.
    """
    import re
    if not old_summary or not new_summary:
        return new_summary

    delete_match = re.search(
        r'\b(?:hapus|delete|hilangkan|remove)\s+(?:gambar|foto|image|picture)(?:\s+(?:produk|item|dari)?\s*([^\n\r]+))?',
        user_prompt,
        re.IGNORECASE
    )
    del_target = delete_match.group(1).lower().strip() if (delete_match and delete_match.group(1)) else ""

    old_sections = re.split(r'(?=\n#{1,4}\s+)', "\n" + old_summary)
    # Words most item names share (a brand, a product line) do not tell items apart
    from app.rag.utils.summary_chunker import common_words
    shared_name_words = common_words([h.strip() for h in re.findall(r'#{1,4}\s+([^\n]+)', old_summary)])

    for o_sec in old_sections:
        name_match = re.search(r'-\s*\*\*Nama(?:\s+Produk)?\*\*\s*:\s*([^\n]+)', o_sec)
        if not name_match:
            hdr_m = re.search(r'#{1,4}\s+([^\n]+)', o_sec)
            if hdr_m and not re.match(r'^(?:Detail|Overview|Info|Informasi|Spesifikasi)\s+Produk', hdr_m.group(1).strip(), re.IGNORECASE):
                p_name = hdr_m.group(1).strip()
            else:
                p_name = ""
        else:
            p_name = name_match.group(1).strip()

        img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', o_sec)
        if not img_match or not p_name:
            continue

        old_alt = img_match.group(1)
        old_url = img_match.group(2).strip()

        if del_target and any(w in del_target for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', p_name.lower()) if w not in shared_name_words and w != "produk"):
            continue

        if old_url in new_summary:
            continue

        new_sections = re.split(r'(?=\n#{1,4}\s+)', "\n" + new_summary)
        p_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', p_name.lower()) if w not in shared_name_words and w != "produk"]
        
        target_new_idx = -1
        for idx, n_sec in enumerate(new_sections):
            if p_words and sum(1 for w in p_words if w in n_sec.lower()) >= min(2, len(p_words)):
                if not re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', n_sec):
                    target_new_idx = idx
                    break

        if target_new_idx != -1:
            sec_to_fix = new_sections[target_new_idx]
            hdr_m = re.search(r'^(#{1,4}\s+[^\n]+)', sec_to_fix.strip())
            if hdr_m:
                hdr = hdr_m.group(1)
                new_sec = sec_to_fix.replace(hdr, f"{hdr}\n![{old_alt or p_name}]({old_url})", 1)
            else:
                new_sec = f"![{old_alt or p_name}]({old_url})\n\n" + sec_to_fix
            new_sections[target_new_idx] = new_sec
            new_summary = "".join(new_sections).strip()

    return new_summary


def align_chunks_with_multitreatment(
    summary: str,
    chunks: List[Dict[str, Any]],
    doc_title: str,
    doc_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Scans structured summary for treatment/product entities (e.g. '## 1. Acne Intensive Program', '## Acne Peel Therapy')
    and aligns chunks so each chunk has the correct entity/treatment name in its metadata,
    and prepends the entity header if missing from chunk text for crystal-clear RAG retrieval.
    """
    import re
    if not summary or not chunks:
        return chunks

    # Extract all H2 treatment/product names from summary
    entity_matches = re.findall(r'(?:^|\n)##\s+(?:\d+[\.\)]\s*)?([^\n]+)', summary)
    entities = [e.strip() for e in entity_matches if e.strip() and not e.strip().lower().startswith(('kategori', 'overview', 'ringkasan', 'panduan', 'informasi'))]
    
    if not entities:
        return chunks

    sorted_entities = sorted(entities, key=len, reverse=True)

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_text = chunk.get("text", "")
        if not chunk_text:
            continue
        if "metadata" not in chunk or not isinstance(chunk["metadata"], dict):
            chunk["metadata"] = {}
        chunk_meta = chunk["metadata"]
        chunk_lower = chunk_text.lower()
        
        # 1. Exact substring match (longest entity first)
        matched_entity = None
        for ent in sorted_entities:
            if ent.lower() in chunk_lower:
                matched_entity = ent
                break
        
        # 2. Token overlap score if no exact substring match
        if not matched_entity:
            best_score = 0
            for ent in entities:
                ent_words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', ent.lower()) if w not in ('erha', 'and', 'for', 'the', 'treatment', 'program', 'therapy', 'center')]
                if ent_words:
                    score = sum(1 for w in ent_words if w in chunk_lower) / len(ent_words)
                    if score > best_score and score >= 0.5:
                        best_score = score
                        matched_entity = ent

        if matched_entity:
            chunk_meta["product_name"] = matched_entity
            chunk_meta["entity"] = matched_entity
            chunk_meta["section"] = matched_entity
            # If chunk text doesn't start with the entity header, prepend it for retrieval clarity
            if not re.search(r'^(?:#+\s+|\d+\.\s+)' + re.escape(matched_entity), chunk_text, re.IGNORECASE):
                chunk["text"] = f"## {matched_entity}\n\n{chunk_text}"
        else:
            if not chunk_meta.get("product_name"):
                chunk_meta["product_name"] = doc_title
            # If section contains raw instruction steps, clean it to General / Title
            if str(chunk_meta.get("section", "")).strip().startswith("1."):
                chunk_meta["section"] = doc_title

        chunk_meta["title"] = doc_title
        if doc_type:
            chunk_meta["document_type"] = doc_type

    # Aggregate entity-level metadata (SKU, Price, Promo dates, Image URL) per entity across all chunks
    entity_props = {}
    for chunk in chunks:
        if not isinstance(chunk, dict) or not chunk.get("metadata"):
            continue
        m = chunk["metadata"]
        ent = m.get("entity") or m.get("product_name")
        if not ent or ent == doc_title:
            continue
        if ent not in entity_props:
            entity_props[ent] = {
                "sku": None,
                "price": None,
                "valid_from": None,
                "valid_until": None,
                "image_url": None
            }
        p = entity_props[ent]
        if m.get("sku") and not p["sku"]:
            p["sku"] = m["sku"]
        if m.get("price") and not p["price"]:
            p["price"] = m["price"]
        if m.get("valid_from") and not p["valid_from"]:
            p["valid_from"] = m["valid_from"]
        if m.get("valid_until") and not p["valid_until"]:
            p["valid_until"] = m["valid_until"]
        if m.get("image_url") and not p["image_url"]:
            p["image_url"] = m["image_url"]

    # Propagate aggregated entity metadata across ALL sub-chunks belonging to that product/treatment
    for chunk in chunks:
        if not isinstance(chunk, dict) or not chunk.get("metadata"):
            continue
        m = chunk["metadata"]
        ent = m.get("entity") or m.get("product_name")
        if ent and ent in entity_props:
            p = entity_props[ent]
            m["entity"] = ent
            m["product_name"] = ent
            m["treatment_name"] = ent
            if p["sku"] and not m.get("sku"):
                m["sku"] = p["sku"]
            if p["price"] and not m.get("price"):
                m["price"] = p["price"]
            if p["valid_from"] and not m.get("valid_from"):
                m["valid_from"] = p["valid_from"]
            if p["valid_until"] and not m.get("valid_until"):
                m["valid_until"] = p["valid_until"]
            if p["image_url"] and not m.get("image_url"):
                m["image_url"] = p["image_url"]

    return chunks


def _looks_like_uuid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", (value or "").strip().lower()))


def resolve_pending_file(knowledge_id: str) -> Optional[str]:
    clean_k_id = str(knowledge_id).strip().lower()
    candidate_dirs = ["data/pending", "backend/data/pending"]
    
    # 1. Direct O(1) file path check
    for pending_dir in candidate_dirs:
        if not os.path.exists(pending_dir):
            continue
        for candidate_name in [f"{knowledge_id}.json", f"{knowledge_id}_parsed.json", f"{clean_k_id}.json", f"{clean_k_id}_parsed.json"]:
            clean_p = os.path.join(pending_dir, candidate_name)
            if os.path.exists(clean_p):
                return clean_p

    # 2. MinIO Source of Truth Hydration fallback
    try:
        from app.services.storage import get_staging_json
        staged_data = get_staging_json(knowledge_id)
        if staged_data:
            target_dir = "data/pending" if os.path.exists("data") else "backend/data/pending"
            os.makedirs(target_dir, exist_ok=True)
            clean_p = os.path.join(target_dir, f"{knowledge_id}.json")
            with open(clean_p, "w", encoding="utf-8") as fp:
                json.dump(staged_data, fp, indent=4, ensure_ascii=False)
            return clean_p
    except Exception as e:
        logger.debug(f"MinIO staging hydration note: {e}")

    # 3. PostgreSQL Database Hydration fallback
    try:
        from sqlalchemy import text
        from app.core.database import get_sync_engine
        sync_eng = get_sync_engine()
        with sync_eng.connect() as conn:
            row = conn.execute(
                # A published document has no draft: building one from its row would invent an "On review"
                # copy that later reads and approvals mistake for a real pending edit.
                text("SELECT id, title, file_name, ai_summary, metadata, status FROM knowledge WHERE id::text = :k_id AND deleted_at IS NULL AND status <> 'APPROVED' LIMIT 1"),
                {"k_id": knowledge_id}
            ).fetchone()
            if not row and not clean_k_id.replace("-", "").isalnum():
                row = conn.execute(
                    text("SELECT id, title, file_name, ai_summary, metadata, status FROM knowledge WHERE (LOWER(title) = LOWER(:k_id) OR LOWER(file_name) = LOWER(:k_id)) AND deleted_at IS NULL AND status <> 'APPROVED' LIMIT 1"),
                    {"k_id": knowledge_id}
                ).fetchone()

            if row:
                row_id, title, fname, summary, meta_val, k_status = row[0], row[1], row[2], row[3], row[4], row[5]
                m_dict = meta_val if isinstance(meta_val, dict) else (json.loads(meta_val) if isinstance(meta_val, str) else {})
                doc = {
                    "knowledge_id": str(row_id),
                    "batch_id": m_dict.get("batch_id"),
                    "file_name": fname or str(row_id),
                    "title": title or fname or str(row_id),
                    "status": "Pending",
                    "summary": summary or "",
                    "chunks": m_dict.get("chunks", []),
                    "images": m_dict.get("images", []),
                    "image_urls": m_dict.get("image_urls", []),
                    "categories": m_dict.get("categories", []),
                    "visibility_settings": m_dict.get("visibility_settings", {}),
                    "history": m_dict.get("history", []),
                    "chat_history": m_dict.get("chat_history", []),
                    "initial_prompt": m_dict.get("initial_prompt")
                }
                target_dir = "data/pending" if os.path.exists("data") else "backend/data/pending"
                os.makedirs(target_dir, exist_ok=True)
                clean_p = os.path.join(target_dir, f"{knowledge_id}.json")
                with open(clean_p, "w", encoding="utf-8") as fp:
                    json.dump(doc, fp, indent=4, ensure_ascii=False)
                return clean_p
    except Exception as db_e:
        logger.debug(f"DB pending hydration note: {db_e}")

    # 4. Fast filename-only fallback for legacy name queries (O(1) string check, NO json.load() loop).
    # An id names exactly one document: a fragment match would hand back another document's file.
    if _looks_like_uuid(clean_k_id):
        return None
    for pending_dir in candidate_dirs:
        if not os.path.exists(pending_dir):
            continue
        for f in os.listdir(pending_dir):
            if f.endswith(".json") and (f.lower().startswith(clean_k_id) or clean_k_id in f.lower()):
                return os.path.join(pending_dir, f)

    return None

def resolve_approved_file(knowledge_id: str) -> Optional[str]:
    candidate_dirs = ["data/output", "backend/data/output"]
    clean_k_id = str(knowledge_id).strip().lower()

    # 1. Direct O(1) file path check
    for approved_dir in candidate_dirs:
        if not os.path.exists(approved_dir):
            continue
        for candidate_name in [f"{knowledge_id}.json", f"{knowledge_id}_parsed.json", f"{clean_k_id}.json", f"{clean_k_id}_parsed.json"]:
            clean_p = os.path.join(approved_dir, candidate_name)
            if os.path.exists(clean_p):
                return clean_p

    # 2. MinIO Source of Truth Hydration fallback
    try:
        from app.services.storage import get_approved_json
        approved_data = get_approved_json(knowledge_id)
        if approved_data:
            target_dir = "data/output" if os.path.exists("data") else "backend/data/output"
            os.makedirs(target_dir, exist_ok=True)
            clean_p = os.path.join(target_dir, f"{knowledge_id}.json")
            with open(clean_p, "w", encoding="utf-8") as fp:
                json.dump(approved_data, fp, indent=4, ensure_ascii=False)
            return clean_p
    except Exception as e:
        logger.debug(f"MinIO approved hydration note: {e}")

    # 3. PostgreSQL Database Hydration fallback
    try:
        from sqlalchemy import text
        from app.core.database import get_sync_engine
        sync_eng = get_sync_engine()
        with sync_eng.connect() as conn:
            row = conn.execute(
                text("SELECT id, title, file_name, ai_summary, metadata FROM knowledge WHERE id::text = :k_id AND status = 'APPROVED' AND deleted_at IS NULL LIMIT 1"),
                {"k_id": knowledge_id}
            ).fetchone()
            if not row:
                row = conn.execute(
                    text("SELECT id, title, file_name, ai_summary, metadata FROM knowledge WHERE (LOWER(title) = LOWER(:k_id) OR LOWER(file_name) = LOWER(:k_id)) AND status = 'APPROVED' AND deleted_at IS NULL LIMIT 1"),
                    {"k_id": knowledge_id}
                ).fetchone()

            if row:
                row_id, title, fname, summary, meta_val = row[0], row[1], row[2], row[3], row[4]
                m_dict = meta_val if isinstance(meta_val, dict) else (json.loads(meta_val) if isinstance(meta_val, str) else {})
                doc = {
                    "knowledge_id": str(row_id),
                    "batch_id": m_dict.get("batch_id"),
                    "file_name": fname or str(row_id),
                    "title": title or fname or str(row_id),
                    "status": "Approved",
                    "summary": summary or "",
                    "chunks": m_dict.get("chunks", []),
                    "images": m_dict.get("images", []),
                    "image_urls": m_dict.get("image_urls", []),
                    "categories": m_dict.get("categories", []),
                    "visibility_settings": m_dict.get("visibility_settings", {}),
                    "edit_history": m_dict.get("edit_history", []),
                    "history": m_dict.get("history", [])
                }
                target_dir = "data/output" if os.path.exists("data") else "backend/data/output"
                os.makedirs(target_dir, exist_ok=True)
                clean_p = os.path.join(target_dir, f"{knowledge_id}.json")
                with open(clean_p, "w", encoding="utf-8") as fp:
                    json.dump(doc, fp, indent=4, ensure_ascii=False)
                return clean_p
    except Exception as db_e:
        logger.debug(f"DB approved hydration note: {db_e}")

    # 4. Fast filename-only fallback for legacy name queries (O(1) string check, NO json.load() loop)
    if _looks_like_uuid(clean_k_id):
        return None
    for approved_dir in candidate_dirs:
        if not os.path.exists(approved_dir):
            continue
        for f in os.listdir(approved_dir):
            if f.endswith(".json") and f != "bm25_index.pkl" and (f.lower().startswith(clean_k_id) or clean_k_id in f.lower()):
                return os.path.join(approved_dir, f)

    return None



def is_knowledge_record_active(k_id: Optional[str], file_name: Optional[str]) -> bool:
    """Helper to check whether a document is still actively published/pending in DB (deleted_at IS NULL and not REJECTED)."""
    try:
        from app.core.database import get_sync_engine
        from sqlalchemy import text
        import uuid as _uuid
        sync_engine = get_sync_engine()
        with sync_engine.connect() as conn:
            if k_id:
                try:
                    kuuid = str(_uuid.UUID(k_id))
                    row = conn.execute(
                        text("SELECT id, status, ai_summary FROM knowledge WHERE id = :kid AND deleted_at IS NULL"),
                        {"kid": kuuid}
                    ).first()
                    if row:
                        status_str = str(row.status or "").upper()
                        summary_str = str(row.ai_summary or "")
                        if status_str == "REJECTED" or summary_str.startswith("[Gagal Diproses]"):
                            return False
                        return True
                    if file_name:
                        row_f = conn.execute(
                            text("SELECT id, status, ai_summary FROM knowledge WHERE file_name = :fname AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1"),
                            {"fname": file_name}
                        ).first()
                        if row_f:
                            st_f = str(row_f.status or "").upper()
                            sum_f = str(row_f.ai_summary or "")
                            if st_f == "REJECTED" or sum_f.startswith("[Gagal Diproses]"):
                                return False
                            return True
                        return False
                    return False
                except ValueError:
                    pass
            if file_name:
                row = conn.execute(
                    text("SELECT id, status, ai_summary FROM knowledge WHERE file_name = :fname AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1"),
                    {"fname": file_name}
                ).first()
                if row:
                    st_r = str(row.status or "").upper()
                    sum_r = str(row.ai_summary or "")
                    if st_r == "REJECTED" or sum_r.startswith("[Gagal Diproses]"):
                        return False
                    return True
                return False
    except Exception as e:
        logger.debug(f"DB check in is_knowledge_record_active: {e}")
        return False
    return False


ACTIVE_PROCESSING_HASHES: Dict[str, Dict[str, Any]] = {}


def detect_duplicate_lifecycle(file_hash: str, file_name: str, exclude_knowledge_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluates the duplicate status of an uploaded file across the entire Knowledge Base:
    - State 0: PROCESSING (currently being processed in background pipeline) -> ALREADY IN QUEUE
    - State 1: PUBLISHED (in data/output or KnowledgeStatus.APPROVED) -> BLOCK
    - State 2: PENDING (in data/pending or KnowledgeStatus.PENDING/ON_REVIEW) -> ASK ADMIN (Keep/Replace)
    - State 3: NEW -> Ingest
    """
    import time as _time
    now = _time.time()
    clean_name = file_name.strip().lower()

    # 0. Check IN-FLIGHT PROCESSING (in active background pipeline with stale task eviction > 20m)
    if file_hash and file_hash in ACTIVE_PROCESSING_HASHES:
        active_info = ACTIVE_PROCESSING_HASHES[file_hash]
        started_at = active_info.get("started_at", 0)
        if now - started_at > 1200:
            ACTIVE_PROCESSING_HASHES.pop(file_hash, None)
        else:
            return {
                "status": "PROCESSING",
                "existing_file": active_info.get("file_name", file_name),
                "knowledge_id": active_info.get("knowledge_id"),
                "match_reason": "Active In-Flight Ingestion Task"
            }

    # 0b. The knowledge table is the record of what exists. Approved/staged JSON may live only in object
    # storage (no local file), so a check of the local folders alone lets the same file in twice.
    try:
        from app.core.database import get_sync_engine
        from sqlalchemy import text as _sql
        with get_sync_engine().connect() as conn:
            row = conn.execute(
                _sql(
                    "SELECT id, file_name, status, metadata->>'file_hash' AS fh FROM knowledge "
                    "WHERE deleted_at IS NULL AND status IN ('APPROVED', 'PENDING') "
                    "AND coalesce(ai_summary, '') NOT LIKE '[Gagal Diproses]%' "
                    "AND ((:h <> '' AND metadata->>'file_hash' = :h) OR lower(trim(file_name)) = :n) "
                    "AND id::text <> :ex "
                    "ORDER BY (status = 'APPROVED') DESC, created_at DESC LIMIT 1"
                ),
                {"h": file_hash or "", "n": clean_name, "ex": str(exclude_knowledge_id or "")},
            ).first()
        if row:
            return {
                "status": "PUBLISHED" if str(row.status).upper() == "APPROVED" else "PENDING",
                "existing_file": row.file_name or file_name,
                "knowledge_id": str(row.id),
                "match_reason": "SHA-256 Checksum Match" if (file_hash and row.fh == file_hash) else "Filename Match",
            }
    except Exception as db_err:
        logger.warning(f"Duplicate check against knowledge table skipped: {db_err}")

    # 1. Check PUBLISHED / APPROVED (data/output)
    approved_dir = "data/output"
    if os.path.exists(approved_dir):
        for f in os.listdir(approved_dir):
            if f.endswith(".json") and f != "bm25_index.pkl":
                full_path = os.path.join(approved_dir, f)
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    ex_hash = None
                    ex_name = None
                    k_id = None
                    if isinstance(data, dict):
                        ex_hash = data.get("file_hash")
                        ex_name = data.get("file_name")
                        k_id = data.get("knowledge_id")
                        if not ex_hash and data.get("chunks"):
                            ex_hash = data["chunks"][0].get("metadata", {}).get("file_hash")
                    elif isinstance(data, list) and data:
                        meta = data[0].get("metadata", {})
                        ex_hash = meta.get("file_hash")
                        ex_name = meta.get("source_file")
                        k_id = meta.get("knowledge_id")

                    is_hash_match = bool(file_hash and ex_hash and file_hash == ex_hash)
                    is_name_match = bool(ex_name and ex_name.strip().lower() == clean_name)

                    if is_hash_match or is_name_match:
                        # Verify that this published record is still active in the database
                        doc_kid = k_id or f[:-5]
                        if exclude_knowledge_id and str(doc_kid) == str(exclude_knowledge_id):
                            continue  # the document being replaced is not its own duplicate
                        if not is_knowledge_record_active(doc_kid, ex_name or file_name):
                            # Orphaned file from a soft-deleted knowledge document; remove and ignore
                            try:
                                os.remove(full_path)
                            except Exception:
                                pass
                            continue

                        match_reason = "SHA-256 Checksum Match" if is_hash_match else "Filename Match"
                        return {
                            "status": "PUBLISHED",
                            "existing_file": ex_name or f,
                            "knowledge_id": doc_kid,
                            "match_reason": match_reason
                        }
                except Exception:
                    pass

    # 2. Check PENDING / ON REVIEW (data/pending)
    pending_dir = "data/pending"
    if os.path.exists(pending_dir):
        for f in os.listdir(pending_dir):
            if f.endswith(".json"):
                full_path = os.path.join(pending_dir, f)
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    ex_hash = None
                    ex_name = None
                    k_id = None
                    if isinstance(data, dict):
                        ex_hash = data.get("file_hash")
                        ex_name = data.get("file_name")
                        k_id = data.get("knowledge_id")
                        if not ex_hash and data.get("chunks"):
                            ex_hash = data["chunks"][0].get("metadata", {}).get("file_hash")
                    elif isinstance(data, list) and data:
                        meta = data[0].get("metadata", {})
                        ex_hash = meta.get("file_hash")
                        ex_name = meta.get("source_file")
                        k_id = meta.get("knowledge_id")

                    is_hash_match = bool(file_hash and ex_hash and file_hash == ex_hash)
                    is_name_match = bool(ex_name and ex_name.strip().lower() == clean_name)

                    if is_hash_match or is_name_match:
                        doc_kid = k_id or f[:-5]
                        if exclude_knowledge_id and str(doc_kid) == str(exclude_knowledge_id):
                            continue  # the document being replaced is not its own duplicate
                        if not is_knowledge_record_active(doc_kid, ex_name or file_name):
                            # Orphaned staging file from a soft-deleted knowledge document; remove and ignore
                            try:
                                os.remove(full_path)
                            except Exception:
                                pass
                            continue

                        match_reason = "SHA-256 Checksum Match" if is_hash_match else "Filename Match"
                        return {
                            "status": "PENDING",
                            "existing_file": ex_name or f,
                            "knowledge_id": doc_kid,
                            "match_reason": match_reason
                        }
                except Exception:
                    pass

    return {"status": "NEW"}

def check_sha256_duplicate(file_hash: str, file_name: str) -> Optional[str]:
    """Backward-compatible helper returning duplicate filename if PUBLISHED duplicate is found."""
    res = detect_duplicate_lifecycle(file_hash, file_name)
    if res.get("status") == "PUBLISHED":
        return res.get("existing_file")
    return None

CANCELLED_INGESTION_IDS: set[str] = set()

# The document the current ingestion task is parsing, so long parsing loops can stop when it is cancelled
CURRENT_INGESTION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("current_ingestion_id", default="")


def cancel_ingestion_job(knowledge_id: Union[str, uuid.UUID]):
    """Register a knowledge_id as cancelled so active background workers abort immediately."""
    if knowledge_id:
        k_str = str(knowledge_id).lower()
        CANCELLED_INGESTION_IDS.add(k_str)
        try:
            os.makedirs("data/temp/cancellations", exist_ok=True)
            with open(os.path.join("data/temp/cancellations", k_str), "w") as f:
                f.write("cancelled")
        except Exception:
            pass
        logger.info(f"🛑 [INGESTION CANCELLED] Registered cancellation for knowledge_id: {k_str}")

def uncancel_ingestion_job(knowledge_id: Union[str, uuid.UUID]):
    """Reset the cancellation state for a knowledge_id when a new ingestion job starts."""
    if knowledge_id:
        k_str = str(knowledge_id).lower()
        CANCELLED_INGESTION_IDS.discard(k_str)
        try:
            cancel_marker = os.path.join("data/temp/cancellations", k_str)
            if os.path.exists(cancel_marker):
                os.remove(cancel_marker)
        except Exception:
            pass

clear_cancellation_job = uncancel_ingestion_job

def is_ingestion_cancelled(knowledge_id: Union[str, uuid.UUID]) -> bool:
    """Check whether a knowledge ingestion job was cancelled by user."""
    if not knowledge_id:
        return False
    k_str = str(knowledge_id).lower()
    if k_str in CANCELLED_INGESTION_IDS:
        return True
    try:
        return os.path.exists(os.path.join("data/temp/cancellations", k_str))
    except Exception:
        return False

def _process_extracted_chunks_sync(output_file: str, knowledge_id: str, batch_id: Optional[str], file_hash: Optional[str], file_name: str):
    """Offload CPU-bound JSON load, table repair, and text normalizations from the event loop."""
    with open(output_file, 'r', encoding='utf-8') as f:
        enriched_chunks = json.load(f)

    from app.rag.services.rag_generator import repair_markdown_tables
    from app.rag.utils.normalizer import normalize_document_text

    init_image_url = None
    all_doc_image_urls = []
    doc_s3_key = None

    for chunk in enriched_chunks:
        if isinstance(chunk, dict):
            if "metadata" not in chunk:
                chunk["metadata"] = {}
            chunk["metadata"]["knowledge_id"] = knowledge_id
            chunk["metadata"]["batch_id"] = batch_id
            chunk["metadata"]["file_hash"] = file_hash
            chunk["metadata"]["source_file"] = file_name
            chunk.pop("suggested_categories", None)
            chunk["metadata"].pop("document_type", None)
            if chunk.get("text"):
                chunk["text"] = normalize_document_text(repair_markdown_tables(chunk["text"]))

            m = chunk["metadata"]
            if m.get("image_url") and m["image_url"] not in all_doc_image_urls:
                all_doc_image_urls.append(m["image_url"])
            if m.get("s3_key") and not doc_s3_key:
                doc_s3_key = m["s3_key"]
            elif m.get("storage_key") and not doc_s3_key:
                doc_s3_key = m["storage_key"]

    if all_doc_image_urls:
        init_image_url = all_doc_image_urls[0]

    from app.rag.utils.chunker import join_chunk_texts_for_display
    full_extracted_text = normalize_document_text(
        repair_markdown_tables(join_chunk_texts_for_display(enriched_chunks))
    )
    return enriched_chunks, full_extracted_text, init_image_url, all_doc_image_urls, doc_s3_key

def _write_json_sync(file_path: str, data: dict):
    """Offload blocking file writes of large JSON documents from the event loop."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def _finalize_summary_sync(canonical_text: str, recommended_title: str) -> str:
    """Offload CPU-bound summary text normalization and markdown table repair."""
    import re
    from app.rag.utils.normalizer import normalize_document_text
    from app.rag.services.rag_generator import repair_markdown_tables
    clean_body = normalize_document_text(canonical_text.strip())
    if not clean_body.startswith(f"# {recommended_title}"):
        clean_body = re.sub(r'^#\s+[^\n]+\n*', '', clean_body)
        res_summary = f"# {recommended_title}\n\n{clean_body}"
    else:
        res_summary = clean_body
    if res_summary:
        res_summary = re.sub(r'!\[([^\]]*)\]\s*\n+\s*\(([^)]+)\)', r'![\1](\2)', res_summary)
        res_summary = repair_markdown_tables(res_summary)
    return res_summary

def summary_text_changed(old: Optional[str], new: Optional[str]) -> bool:
    """Whether two summaries differ in content, ignoring table repair and whitespace differences."""
    from app.rag.services.rag_generator import repair_markdown_tables

    def norm(s: Optional[str]) -> str:
        return re.sub(r"\s+", " ", repair_markdown_tables(s or "")).strip()

    return norm(old) != norm(new)


def chunk_texts(chunks: Any) -> List[str]:
    """The text of each chunk, for telling whether two chunk lists hold the same content."""
    if not isinstance(chunks, list):
        return []
    return [str(c.get("text") or "").strip() if isinstance(c, dict) else str(c).strip() for c in chunks]


def _run_canonical_shadow_ingest_sync(
    knowledge_id: str,
    file_name: str,
    file_hash: Optional[str],
    extracted_doc_type: str,
    visibility_settings: dict,
    recommended_title: str,
    enriched_chunks: list,
    summary: str
):
    """Run synchronous canonical clinical evidence ingestion and embeddings in background thread pool."""
    import uuid as _uuid
    from app.rag.services.canonical_ingest_service import CanonicalIngestService
    from app.rag.canonical import (
        CanonicalEvidence,
        CanonicalEntity,
        CanonicalAsset,
        ParseReport,
        extract_canonical_form_factor,
        extract_entity_aliases,
        normalize_entity_key,
    )

    can_service = CanonicalIngestService()
    shadow_ktype = "PRODUCT" if extracted_doc_type == "PRODUCT" else ("TREATMENT" if extracted_doc_type == "TREATMENT" else "OTHER")
    can_ver_info = can_service.get_or_create_version(
        knowledge_id=str(knowledge_id),
        file_hash=file_hash or "shadow_file_hash",
        default_knowledge_type=shadow_ktype,
        authority_level=2,
        visibility=visibility_settings
    )
    can_vid = can_ver_info["version_id"]

    can_evidences = []
    for c_idx, ch in enumerate(enriched_chunks):
        ch_txt = ch.get("text") if isinstance(ch, dict) else str(ch)
        ch_meta = ch.get("metadata", {}) if isinstance(ch, dict) else {}
        c_ev = CanonicalEvidence(
            id=str(_uuid.uuid4()),
            version_id=can_vid,
            evidence_type="TEXT" if not ch_meta.get("is_table") else "TABLE_ROW",
            knowledge_type=shadow_ktype,
            section_path=[ch_meta.get("section", "General")],
            title=ch_meta.get("title") or recommended_title,
            body=ch_txt,
            attributes=ch_meta,
            provenance={"source_file": file_name, "page": ch_meta.get("page", 1)},
            derivation="NATIVE",
            processor="pipeline_ingest_shadow",
            processor_version="2.1.0",
            confidence=1.0,
            visual_analysis_status="NATIVE_COMPLETE",
            ordinal=c_idx
        )
        can_evidences.append(c_ev)

    can_entities = []
    seen_entity_keys = set()
    ent_type = "PRODUCT" if extracted_doc_type == "PRODUCT" else "TREATMENT"

    if recommended_title:
        rec_clean = recommended_title.strip()
        nkey = normalize_entity_key(rec_clean)
        if nkey and nkey not in seen_entity_keys:
            seen_entity_keys.add(nkey)
            can_entities.append(CanonicalEntity(
                entity_type=ent_type,
                canonical_name=rec_clean,
                normalized_key=nkey,
                form_factor=extract_canonical_form_factor(rec_clean),
                aliases=extract_entity_aliases(rec_clean)
            ))

    # Universal Entity Discovery from enriched chunks & markdown table rows
    NAME_COL_PATTERNS = {"nama", "name", "nama tindakan", "nama produk", "treatment", "produk", "product", "item", "layanan", "service", "tindakan", "judul"}
    for ch in enriched_chunks:
        ch_meta = ch.get("metadata", {}) if isinstance(ch, dict) else {}
        for m_key in ("product_name", "treatment_name", "entity_name", "item_name"):
            cand_m = ch_meta.get(m_key)
            if cand_m and isinstance(cand_m, str) and len(cand_m.strip()) >= 3:
                cand_clean = cand_m.strip()
                nkey = normalize_entity_key(cand_clean)
                if nkey and nkey not in seen_entity_keys:
                    seen_entity_keys.add(nkey)
                    can_entities.append(CanonicalEntity(
                        entity_type=ent_type,
                        canonical_name=cand_clean,
                        normalized_key=nkey,
                        form_factor=extract_canonical_form_factor(cand_clean),
                        aliases=extract_entity_aliases(cand_clean)
                    ))

        ch_txt = ch.get("text") if isinstance(ch, dict) else str(ch)
        if "|" in ch_txt:
            lines = ch_txt.splitlines()
            col_name_idx = None
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("|") or not stripped.endswith("|"):
                    continue
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if not cells:
                    continue
                lower_cells = [c.lower() for c in cells]
                if any(lc in NAME_COL_PATTERNS or any(p in lc for p in ("nama", "treatment", "produk")) for lc in lower_cells):
                    for idx, lc in enumerate(lower_cells):
                        if lc in NAME_COL_PATTERNS or any(p in lc for p in ("nama tindakan", "nama produk", "treatment", "nama")):
                            col_name_idx = idx
                            break
                    continue
                if all(set(c).issubset({"-", " ", ":"}) for c in cells if c):
                    continue
                if col_name_idx is not None and col_name_idx < len(cells):
                    raw_cand = cells[col_name_idx].strip()
                    if len(raw_cand) >= 3 and not raw_cand.isdigit() and raw_cand.lower() not in NAME_COL_PATTERNS:
                        nkey = normalize_entity_key(raw_cand)
                        if nkey and nkey not in seen_entity_keys:
                            seen_entity_keys.add(nkey)
                            can_entities.append(CanonicalEntity(
                                entity_type=ent_type,
                                canonical_name=raw_cand,
                                normalized_key=nkey,
                                form_factor=extract_canonical_form_factor(raw_cand),
                                aliases=extract_entity_aliases(raw_cand)
                            ))

    can_rep = ParseReport(
        source_file=file_name,
        total_physical_rows=len(can_evidences),
        disposition_summary={"evidence_count": len(can_evidences), "context_rows": 0, "excluded_rows": 0}
    )

    can_service.ingest_canonical_document(
        version_id=can_vid,
        evidences=can_evidences,
        entities=can_entities,
        assets=[],
        parse_report=can_rep,
        summary_md=summary
    )

_ingestion_semaphore = asyncio.Semaphore(settings.max_ingestion_concurrency)

async def process_ingestion_background(
    knowledge_id: str,
    file_path: str,
    file_name: str,
    pipeline: IngestionPipeline,
    llm: BaseLLMAdapter,
    user_prompt: Optional[str] = None,
    file_hash: Optional[str] = None,
    batch_id: Optional[str] = None
):
    if is_ingestion_cancelled(knowledge_id):
        logger.info(f"🛑 [INGESTION ABORTED] Knowledge ID '{knowledge_id}' ({file_name}) was cancelled before processing started.")
        if file_hash:
            ACTIVE_PROCESSING_HASHES.pop(file_hash, None)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return

    import time as _time
    t0_total = _time.time()
    timing_metrics = {
        "upload_ms": 0,
        "checksum_ms": 0,
        "parsing_ms": 0,
        "ocr_ms": 0,
        "llm_review_ms": 0,
        "embedding_ms": 0,
        "database_insert_ms": 0,
        "bm25_update_ms": 0,
        "total_ingestion_ms": 0
    }

    try:
        async with _ingestion_semaphore:
            if is_ingestion_cancelled(knowledge_id):
                logger.info(f"🛑 [INGESTION ABORTED] Knowledge ID '{knowledge_id}' ({file_name}) was cancelled while waiting for semaphore.")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                return

            # Temporarily configure pipeline to stage file in data/pending without indexing
            original_output_dir = pipeline.output_dir
            original_store = pipeline.vector_store
            
            pipeline.output_dir = "data/pending"
            pipeline.vector_store = None
            os.makedirs(pipeline.output_dir, exist_ok=True)
            
            t0_parse = _time.time()
            # The parsers check this between pages (asyncio.to_thread carries it into the worker thread)
            CURRENT_INGESTION_ID.set(str(knowledge_id))
            try:
                output_file = await asyncio.to_thread(pipeline.ingest_file, file_path)
            finally:
                pipeline.output_dir = original_output_dir
                pipeline.vector_store = original_store
            
            timing_metrics["parsing_ms"] = int((_time.time() - t0_parse) * 1000)
                
            # Cleanup temp file
            try:
                import gc
                gc.collect()
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as cleanup_err:
                logger.warning(f"Could not delete temporary file {file_path}: {cleanup_err}")
                
            if is_ingestion_cancelled(knowledge_id):
                logger.info(f"🛑 [INGESTION ABORTED] Knowledge ID '{knowledge_id}' ({file_name}) was cancelled during parsing. Discarding output.")
                if output_file and os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                    except Exception:
                        pass
                return
                
            if not output_file:
                raise RuntimeError(f"Gagal mengekstrak teks dari dokumen '{file_name}'. Format file mungkin rusak atau tidak didukung.")
                
            # Offload chunk processing, table sanitization, and text normalization from the event loop
            enriched_chunks, full_extracted_text, init_image_url, all_doc_image_urls, doc_s3_key = await asyncio.to_thread(
                _process_extracted_chunks_sync,
                output_file,
                knowledge_id,
                batch_id,
                file_hash,
                file_name
            )

            clean_title_fallback = os.path.splitext(file_name)[0]

            # Write initial pending state asynchronously so GET /pending and GET /documents work instantly without blocking
            os.makedirs("data/pending", exist_ok=True)
            pending_file_path = os.path.join("data/pending", f"{knowledge_id}.json")
            initial_staged_doc = {
                "knowledge_id": knowledge_id,
                "batch_id": batch_id,
                "file_name": file_name,
                "file_hash": file_hash,
                "title": clean_title_fallback,
                "status": "PARSING",
                "text_accuracy": "100%",
                "initial_prompt": user_prompt if user_prompt and str(user_prompt).strip() else None,
                "summary": full_extracted_text,
                "feedback": f"Dokumen {file_name} telah berhasil diekstrak dan tersimpan di area peninjauan.",
                "batch_summary": None,
                "suggested_categories": [],
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                },
                "history": [],
                "chunks": enriched_chunks,
                "timing_metrics": timing_metrics
            }
            if init_image_url:
                initial_staged_doc["image_url"] = init_image_url

            await asyncio.to_thread(_write_json_sync, pending_file_path, initial_staged_doc)
            try:
                from app.services.storage import upload_staging_json
                await asyncio.to_thread(upload_staging_json, knowledge_id, initial_staged_doc)
            except Exception as st_err:
                logger.debug(f"MinIO staging upload note: {st_err}")
                
            if is_ingestion_cancelled(knowledge_id):
                logger.info(f"🛑 [INGESTION ABORTED] Knowledge ID '{knowledge_id}' was cancelled before LLM review.")
                if os.path.exists(pending_file_path):
                    try:
                        os.remove(pending_file_path)
                    except Exception:
                        pass
                try:
                    from app.services.storage import delete_staging_json
                    delete_staging_json(knowledge_id)
                except Exception:
                    pass
                return

            # ─── CANONICAL TEXT: raw parser output, NOT rewritten by LLM ───────────────────
            # The canonical_text is the verbatim content extracted by the document parser.
            # LLM is NOT allowed to rewrite, summarize, or add to this content.
            # Admin sees exactly what the document contains in the Review Dashboard.
            canonical_text = full_extracted_text
            summary = canonical_text
            text_accuracy = "100%"
            feedback = f"Dokumen '{file_name}' telah berhasil diekstrak. Silakan tinjau isi dokumen di bawah sebelum menyetujui."
            suggested_categories = []
            recommended_title = clean_title_fallback
            extracted_doc_type = "GENERAL"
            extracted_valid_from = None
            extracted_valid_until = None

            # ─── AI STRUCTURING & METADATA CLASSIFICATION ─────────────────────────────────
            if llm and enriched_chunks:
                t0_llm = _time.time()
                try:
                    db_categories = []
                    try:
                        from app.core.database import AsyncSessionLocal
                        from app.models.category import Category
                        from sqlalchemy import select
                        async with AsyncSessionLocal() as session:
                            res = await session.execute(select(Category).where(Category.deleted_at.is_(None)))
                            cats = res.scalars().all()
                            db_categories = [{"id": str(c.id), "name": c.name} for c in cats]
                    except Exception as cat_err:
                        logger.warning(f"Failed to fetch categories for metadata detection: {cat_err}")

                    file_name_lower = file_name.lower()
                    canonical_lower = canonical_text.lower()
                    
                    # Identify if the document is an academic paper, scientific journal, manuscript, clinical study, or research publication
                    is_academic_journal = (
                        any(kw in file_name_lower for kw in [
                            "published", "manuscript", "journal", "jurnal", "paper", "article",
                            "penelitian", "skripsi", "tesis", "disertasi", "prosiding"
                        ])
                        or (
                            len(canonical_text) > 8000
                            and sum(1 for kw in [
                                "abstract", "abstrak", "introduction", "pendahuluan",
                                "method", "metode", "materials and methods", "results and discussion",
                                "hasil dan pembahasan", "conclusion", "kesimpulan",
                                "references", "daftar pustaka", "bibliography",
                                "doi:", "issn", "vol."
                            ] if kw in canonical_lower) >= 2
                        )
                    )

                    is_product_catalog = (
                        "detail produk" in canonical_lower
                        or file_name_lower.endswith(('.xlsx', '.xls', '.csv'))
                        or any(kw in canonical_lower for kw in ["harga", "price", "sku", "netto", "katalog", "catalogue", "daftar produk"])
                    )

                    # A spreadsheet, a very long document or a flattened design deck is published as its full parsed
                    # text whatever the model writes (see the coverage guards below), so asking the model to rewrite
                    # it as Markdown only costs time: for a large sheet that rewrite never fits in one request and
                    # times out again and again. Only its metadata is asked for, from the beginning of the document.
                    summary_kept_verbatim = (
                        file_name_lower.endswith(('.xlsx', '.xls', '.csv'))
                        or len(canonical_text) > 30000
                        or "pdf_flat_doc" in canonical_text
                        or any(isinstance(c, dict) and c.get("metadata", {}).get("is_flattened") for c in enriched_chunks)
                    )
                    if is_academic_journal or summary_kept_verbatim or (len(canonical_text) > 12000 and not is_product_catalog):
                        # Title & metadata quickly from the first 8000 chars (title, abstract, authors, first rows)
                        doc_content_excerpt = canonical_text[:8000]
                        doc_kind = (
                            "This document is a scientific research paper, journal article, clinical study, or academic manuscript."
                            if is_academic_journal else
                            "Only the beginning of the document is shown; it is published in full separately."
                        )
                        structuring_prompt = f"""
You are an expert document analysis AI for PT Arya Noble (ERHA).
{doc_kind}

Your tasks:
1. **DETECT METADATA**:
   - title: Extract the EXACT clean document title (without file extensions, authors, or journal metadata).
   - document_type: "GENERAL"
   - valid_from: null
   - valid_until: null
   - suggested_categories: Array of matching category objects strictly from the "Available Categories" list below.
   - feedback: 1 informative sentence in Indonesian describing what the document is about and its scope.

DOCUMENT CONTENT (Beginning excerpt):
{doc_content_excerpt}

Available Categories:
{json.dumps(db_categories, ensure_ascii=False)}

Return ONLY valid JSON (no surrounding markdown code blocks):
{{
    "title": "<clean document title>",
    "document_type": "GENERAL",
    "valid_from": null,
    "valid_until": null,
    "suggested_categories": [],
    "feedback": "<1 kalimat bahasa Indonesia tentang isi dan cakupan dokumen ini>"
}}
The angle-bracket values describe what to write; never copy them literally."""
                    else:
                        # Document content excerpt for structuring (smart head + mid + tail sample if very large)
                        if len(canonical_text) > 30000:
                            head_part = canonical_text[:16000]
                            mid_start = max(16000, len(canonical_text) // 2 - 4000)
                            mid_part = canonical_text[mid_start:mid_start + 8000]
                            tail_part = canonical_text[-6000:]
                            doc_content_excerpt = f"{head_part}\n\n[... CONT'D MIDDLE SECTIONS ...]\n\n{mid_part}\n\n[... CONT'D FINAL SECTIONS ...]\n\n{tail_part}"
                        else:
                            doc_content_excerpt = canonical_text

                        admin_instruction_block = ""
                        if user_prompt and str(user_prompt).strip():
                            admin_instruction_block = f"""
======================================================================
ADMIN INGESTION INSTRUCTION:
"{str(user_prompt).strip()}"
======================================================================
CRITICAL INSTRUCTION:
- The Admin provided specific instructions above for processing this document (e.g. "hanya ambil produk A saja", "ubah harga jadi Rp ...", "tambahkan catatan ...", "abaikan bagian ...").
- You MUST STRICTLY PRIORITIZE and FOLLOW the Admin's instruction!
- Adapt the title and the formatted_summary specifically to what the Admin requested!
"""

                        structuring_prompt = f"""
You are an expert document structuring and knowledge curation AI for PT Arya Noble (ERHA).

{admin_instruction_block}

Your tasks:
1. **FORMAT DOCUMENT CONTENT IN CLEAN, WELL-STRUCTURED MARKDOWN**:
   - Format the document content in clean, consistent, well-structured Markdown hierarchy (`#` for document title, `##` for main sections, `###` for subsections/products).
   - PRODUCT CATALOG & PRODUCT LISTINGS RULE (CRITICAL):
     * For multi-product catalogs, brochures, product lines, or lists of products with photos and attributes:
       Format each product as a dedicated modular `### Detail Produk` block with its associated image and bullet attributes so that the UI can render interactive Product Cards:
       ```markdown
       ### Detail Produk
       ![Nama Produk Lengkap](URL_GAMBAR)
       - **Nama Produk**: Nama Produk Lengkap
       - **Brand**: Brand Produk (hanya jika ada di dokumen)
       - **Kategori**: Kategori Produk (hanya jika ada di dokumen)
       - **Ukuran**: Ukuran/Netto (hanya jika ada di dokumen)
       - **Harga**: Harga Produk (hanya jika ada di dokumen)
       - **Deskripsi**: Penjelasan singkat manfaat dan kegunaan produk (jika ada).
       - **Komposisi**: Komposisi/kandungan aktif (jika ada).
       - **Cara Penggunaan**: Aturan pakai/cara penggunaan (jika ada).
       - **Kontraindikasi**: Kontraindikasi (jika ada).
       - **Efek Samping**: Efek samping (jika ada).
       ```
     * NEVER separate product catalogs into a plain text table with photos dumped at the bottom. Keep each photo directly inside its corresponding `### Detail Produk` block.
     * If a product has no image in the source document, omit the image tag for that product block, but still format it as a `### Detail Produk` block with key-value bullet points.
   - MULTI-SHEET / MULTI-TAB SPREADSHEET CONSISTENCY RULE (CRITICAL):
     * When the document contains multiple sheets/tabs (e.g. `## Sheet: Catalogue1` and `## Sheet: Copy of Produk`), YOU MUST PROCESS AND INCLUDE ALL SHEETS IN THE OUTPUT! DO NOT DROP, SKIP, OR ABBREVIATE ANY SHEET.
     * Create a `## Sheet: [Nama Sheet]` or `## [Nama Sheet]` section for each sheet.
     * Format EVERY product in EVERY sheet consistently into modular `### Detail Produk` blocks, with each product's photo placed directly inside its block.
     * Never dump orphan photos at the top under the main document title (# Title) or between sections.
     * Preserve all specific attributes present in each sheet (e.g. Komposisi, Cara Penggunaan, Kontraindikasi, Efek Samping, Kategori, Ukuran, Deskripsi).
   - STRICT ZERO-HALLUCINATION & FACTUAL ACCURACY RULE FOR PRODUCT ATTRIBUTES (CRITICAL):
     * SKU RULE: ONLY include the `- **SKU**: [Nomor SKU]` line IF AND ONLY IF an explicit SKU code or number is written in the source document. If NO SKU code/number is explicitly written in the source document, YOU MUST COMPLETELY OMIT THE `- **SKU**:` LINE ENTIRELY! DO NOT INVENT, FABRICATE, GENERATE, OR GUESS ANY SKU CODE (e.g. NEVER create ERHA-ACNE-001, ERHA-TRU-001, or any random code).
     * ATTRIBUTE ACCURACY: ONLY include attribute bullet lines (`Brand`, `Kategori`, `Ukuran`, `Harga`, `Deskripsi`, `Komposisi`, `Cara Penggunaan`, `Kontraindikasi`, `Efek Samping`) for values that are EXPLICITLY present in the source document. Do NOT invent missing values or fabricate categories.
     * PRODUCT STATUS & DISCONTINUED RULE (STRICT MANDATE - ZERO TOLERANCE FOR FALSE DISCONTINUED):
       - By default, ALL products are ACTIVE and AVAILABLE.
       - NEVER label, tag, or describe a product as 'Discontinue', 'Discontinued', 'Tidak Aktif', or 'Tidak Tersedia' unless the source document EXPLICITLY and UNAMBIGUOUSLY contains an official discontinuation notice (e.g. "DISCONTINUE", "stok klinik habis") ATTACHED DIRECTLY TO THAT SPECIFIC PRODUCT.
       - If a document contains a list or comparison table where only one specific product is marked discontinued, DO NOT apply or generalize the discontinued status to other products or to the document as a whole!
       - If NO explicit discontinuation notice is physically written for a product, DO NOT include any `- **Status**: Discontinue` line or `(DISCONTINUED)` badge for that product!
   - NON-PRODUCT DOCUMENTS RULE: If the document is a Technical Design Document, SOP, FAQ, operational manual, or general report (NOT a product catalog): DO NOT format content into `### Detail Produk` blocks. Use clean, standard Markdown headings (`##`, `###`) reflecting the actual document sections.
   - EXCEL & SPREADSHEET TABLE PRESERVATION:
     * For non-product SPREADSHEET / CSV files: PRESERVE AND KEEP TABLES AS MARKDOWN (`| Col 1 | Col 2 |`).
     * IMAGE CAPTION & LEGEND PLACEMENT: For images inside or associated with tables/sections, place the markdown image tag `![Alt Text](IMAGE_URL)` cleanly, and place any caption, legend, or description text DIRECTLY BELOW the image tag.
   - SMART TOPIC-BASED IMAGE PLACEMENT:
     * NEVER dump all images together at the top under the main document title (# Title) or at the bottom.
     * Place each image intelligently inside its relevant section or topic:
       - Product packaging / hero photos: Place directly inside the specific product section (under `### Detail Produk` or `## [Product Name]`).
       - Clinical Before & After photos: Place inside the clinical results or efficacy section (`## Hasil Uji Klinis` or `## Sebelum & Sesudah Pemakaian`).
       - Treatment procedure / usage photos: Place inside the directions or application section (`## Cara Pemakaian` or `## Prosedur Tindakan`).
     * Format images cleanly on separate lines with descriptive alt text and blank lines before and after:
       
       ![Deskripsi Gambar](IMAGE_URL)
       
   - GROUNDING RULE: Preserve all factual details from the raw content, but adhere strictly to any modifications, exclusions, or additions requested in the ADMIN INGESTION INSTRUCTION.
2. **DETECT METADATA**:
   - title: Short, clean professional document title inferred from content and admin instruction (without file extension or "Knowledge Base" prefixes).
   - document_type: "PRODUCT" | "TREATMENT" | "PROMOTIONAL" | "SOP" | "GENERAL"
   - valid_from: "YYYY-MM-DD" promo start date if visible, else null
   - valid_until: "YYYY-MM-DD" promo end date if visible, else null
   - suggested_categories: Array of matching category objects strictly from the "Available Categories" list below.
     STRICT CATEGORY RULES:
     * ONLY select categories that exist in "Available Categories".
     * NEVER invent, fabricate, or hallucinate new categories or placeholder text.
     * If NO category from "Available Categories" matches this document, return an empty array: []!
   - feedback: 1 sentence in Indonesian describing the document type and content.

DOCUMENT CONTENT:
{doc_content_excerpt}

Available Categories:
{json.dumps(db_categories, ensure_ascii=False)}

Return ONLY valid JSON (no surrounding markdown code blocks):
{{
    "title": "<short title taken from this document's own content>",
    "document_type": "<PRODUCT | TREATMENT | PROMOTIONAL | SOP | GENERAL>",
    "valid_from": null,
    "valid_until": null,
    "suggested_categories": [],
    "feedback": "<1 kalimat bahasa Indonesia tentang jenis dan isi dokumen ini>",
    "formatted_summary": "# <the same title>\\n\\n<formatted Markdown of this document>"
}}
The angle-bracket values describe what to write; never copy them literally."""

                    llm_response = ""
                    for attempt in range(3):
                        # A large document's review can take minutes per attempt; a cancelled one skips it and
                        # reaches the discard check below instead of running on after the admin deleted it.
                        if is_ingestion_cancelled(knowledge_id):
                            logger.info(f"🛑 [INGESTION ABORTED] '{knowledge_id}' was cancelled; skipping the LLM review.")
                            break
                        try:
                            llm_response = await asyncio.to_thread(llm.generate, structuring_prompt)
                            if llm_response and llm_response.strip():
                                break
                        except Exception as retry_err:
                            logger.warning(f"⚠️ [INGESTION LLM RETRY] Attempt {attempt+1}/3 failed for '{file_name}': {retry_err}")
                            if attempt < 2:
                                await asyncio.sleep(1.5 * (attempt + 1))
                            else:
                                raise retry_err
                    timing_metrics["llm_review_ms"] = int((_time.time() - t0_llm) * 1000)
                    parsed_meta = safe_json_loads(llm_response)

                    raw_title = parsed_meta.get("title") or clean_title_fallback
                    prefixes_to_strip = [
                        "knowledge ingestment", "knowledge ingestion", "knowledge ingest",
                        "ingestment", "ingestion", "knowledge base", "knowledge"
                    ]
                    recommended_title = raw_title.strip()
                    for p in prefixes_to_strip:
                        if recommended_title.lower().startswith(p):
                            recommended_title = recommended_title[len(p):].lstrip(" :-_#\t")
                    for ext in [".pdf", ".docx", ".xlsx", ".csv", ".pptx", ".ppt", ".doc", ".txt"]:
                        if recommended_title.lower().endswith(ext):
                            recommended_title = recommended_title[:-len(ext)].strip()
                    # A title echoed from the prompt's response template is not a title of this document
                    if not recommended_title or recommended_title.startswith("<") or recommended_title.lower() == "clean document title":
                        recommended_title = clean_title_fallback

                    extracted_doc_type = parsed_meta.get("document_type") or "GENERAL"
                    extracted_valid_from = parsed_meta.get("valid_from")
                    extracted_valid_until = parsed_meta.get("valid_until")
                    
                    # Robust Category validation and fuzzy resolution
                    raw_suggested = parsed_meta.get("suggested_categories", [])
                    suggested_categories = resolve_matching_categories(raw_suggested, db_categories, content_text=doc_content_excerpt)
                    feedback = parsed_meta.get("feedback", feedback)

                    # For image files: strictly preserve clean product name + image markdown (zero packaging detail/SKU hallucinations)
                    is_image_file = file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
                    if is_image_file:
                        doc_img = all_doc_image_urls[0] if all_doc_image_urls else init_image_url
                        img_md = f"![{recommended_title}]({doc_img})" if doc_img else ""
                        summary = f"# {recommended_title}\n\n{img_md}\n\nDokumen visual produk resmi ERHA: {recommended_title}."
                        extracted_doc_type = "PRODUCT"
                        logger.info(f"🖼️ [BATCH: {batch_id or 'SINGLE'}] [FILE: {file_name}] Preserved clean product image summary: '{recommended_title}'")
                    else:
                        file_name_lower = file_name.lower()
                        canonical_lower = canonical_text.lower()
                        
                        # Identify if the document is an academic paper, scientific journal, manuscript, clinical study, or research publication
                        # based purely on text density and structural content markers (0% filename heuristics)
                        is_academic_journal = (
                            len(canonical_text) > 6000
                            and sum(1 for kw in [
                                "abstract", "abstrak", "introduction", "pendahuluan",
                                "method", "metode", "materials and methods", "results and discussion",
                                "hasil dan pembahasan", "conclusion", "kesimpulan",
                                "references", "daftar pustaka", "bibliography",
                                "doi:", "issn", "vol."
                            ] if kw in canonical_lower) >= 2
                        )

                        is_product_catalog = (
                            "detail produk" in canonical_lower
                            or file_name_lower.endswith(('.xlsx', '.xls', '.csv'))
                            or any(kw in canonical_lower for kw in ["harga", "price", "sku", "netto", "katalog", "catalogue", "daftar produk"])
                        )

                        ai_formatted_summary = parsed_meta.get("formatted_summary") or parsed_meta.get("summary")

                        # For academic papers, scientific journals, spreadsheets, or long documents:
                        # PRESERVE 100% OF THE COMPLETE CONTENT without truncation!
                        is_spreadsheet = file_name_lower.endswith(('.xlsx', '.xls', '.csv'))
                        is_large_doc = len(canonical_text) > 30000

                        # Check if document was processed by FlattenedDesignParser (has is_flattened in chunks or pdf_flat_doc in canonical text)
                        is_flattened_doc = (
                            "pdf_flat_doc" in canonical_text
                            or any(isinstance(c, dict) and c.get("metadata", {}).get("is_flattened") for c in enriched_chunks)
                        )

                        # Table Guard: check if canonical text contains markdown tables that the AI summary stripped or collapsed
                        canonical_table_count = canonical_text.count("| ---") + canonical_text.count("|:---")
                        ai_table_count = (str(ai_formatted_summary).count("| ---") + str(ai_formatted_summary).count("|:---")) if ai_formatted_summary else 0
                        table_guard_failed = (canonical_table_count > 0 and ai_table_count < canonical_table_count)

                        # Coverage Guard: evaluate if AI summary truncated the source content
                        ai_summary_valid = False
                        if ai_formatted_summary and len(str(ai_formatted_summary).strip()) > 30 and not table_guard_failed and not is_flattened_doc:
                            ai_len = len(str(ai_formatted_summary).strip())
                            # Accept AI formatting only if doc is small/moderate AND preserved at least 70% of canonical text
                            if not is_large_doc and not is_spreadsheet and ai_len >= len(canonical_text) * 0.70:
                                ai_summary_valid = True
                            else:
                                logger.info(f"🛡️ [COVERAGE GUARD] AI summary ({ai_len} chars) truncated canonical ({len(canonical_text)} chars) or large doc/spreadsheet. Preserving 100% canonical parser text.")
                        elif table_guard_failed:
                            logger.info(f"🛡️ [TABLE GUARD] AI summary stripped markdown tables ({ai_table_count} vs {canonical_table_count} in canonical text). Preserving 100% canonical parser tables.")
                        elif is_flattened_doc:
                            logger.info(f"🛡️ [VISION-NATIVE GUARD] Document is a visual flattened presentation deck. Preserving 100% vision-extracted canonical markdown & tables.")

                        if is_academic_journal or is_spreadsheet or is_large_doc or is_flattened_doc or table_guard_failed or not ai_summary_valid:
                            summary = await asyncio.to_thread(_finalize_summary_sync, canonical_text, recommended_title)
                            extracted_doc_type = "PRODUCT" if (is_product_catalog or is_spreadsheet or is_flattened_doc) else (extracted_doc_type or ("GENERAL" if is_academic_journal else "GENERAL"))
                            logger.info(f"📚 [FULL COVERAGE] Preserved 100% canonical detail of '{recommended_title}' ({len(summary)} chars) without truncation.")
                        else:
                            # Use AI structured markdown as summary for short documents if valid
                            summary = str(ai_formatted_summary).strip()
                            if summary:
                                summary = re.sub(r'!\[([^\]]*)\]\s*\n+\s*\(([^)]+)\)', r'![\1](\2)', summary)
                                from app.rag.services.rag_generator import repair_markdown_tables
                                summary = repair_markdown_tables(summary)
                            logger.info(f"AI formatted document into structured Markdown ({len(summary)} chars)")

                    # Apply deterministic refinements if user specified price/SKU/title in user_prompt
                    if user_prompt and str(user_prompt).strip() and summary:
                        refined_summary, _, refined_title, refined_sku, _ = apply_refinements_to_content(
                            user_prompt=str(user_prompt).strip(),
                            summary=summary,
                            chunks=[],
                            title=recommended_title
                        )
                        summary = refined_summary
                        if refined_title:
                            recommended_title = refined_title

                except Exception as llm_err:
                    timing_metrics["llm_review_ms"] = int((_time.time() - t0_llm) * 1000)
                    logger.warning(f"Metadata detection & structuring LLM call failed (non-critical): {llm_err}. Using parser defaults.")
                    recommended_title = clean_title_fallback
                    extracted_doc_type = "GENERAL"
                    extracted_valid_from = None
                    extracted_valid_until = None
                
        # Define document-level visibility settings
        visibility_settings = {
            "clinics": ["all"],
            "doctor_types": ["all"],
            "doctors": ["all"]
        }

        # Collect ALL document-level image URLs from parser chunks AND from AI summary
        all_structured_images = []
        for c in enriched_chunks:
            if isinstance(c, dict) and c.get("metadata"):
                m = c["metadata"]
                if m.get("image_url") and m["image_url"] not in all_doc_image_urls:
                    all_doc_image_urls.append(m["image_url"])
                if m.get("image_urls") and isinstance(m["image_urls"], list):
                    for u in m["image_urls"]:
                        if u and u not in all_doc_image_urls:
                            all_doc_image_urls.append(u)
                if m.get("images") and isinstance(m["images"], list):
                    for img_obj in m["images"]:
                        if isinstance(img_obj, dict) and img_obj.get("url") and img_obj not in all_structured_images:
                            all_structured_images.append(img_obj)
                if m.get("s3_key") and not doc_s3_key:
                    doc_s3_key = m["s3_key"]
                elif m.get("storage_key") and not doc_s3_key:
                    doc_s3_key = m["storage_key"]
            if isinstance(c, dict) and c.get("text"):
                import re as _re
                for url in _re.findall(r'!\[.*?\]\(([^\s\)]+)\)', c["text"]):
                    if url and url not in all_doc_image_urls:
                        all_doc_image_urls.append(url)

        # Extract image URLs embedded in canonical summary markdown (from parser Vision LLM output)
        if summary:
            import re as _re
            for url in _re.findall(r'!\[.*?\]\(([^\s\)]+)\)', summary):
                if url and url not in all_doc_image_urls:
                    all_doc_image_urls.append(url)

        # Structured image assets
        structured_images = normalize_image_assets(
            existing_images=all_structured_images,
            image_urls=all_doc_image_urls,
            default_product_name=recommended_title,
            default_role="PRODUCT_PACKAGING" if extracted_doc_type == "PRODUCT" else "GENERAL"
        )

        # Smart contextual topic-based image embedding if omitted by LLM (only for non-flattened documents, as flattened parser already embeds images in-place)
        is_flattened_doc_context = (
            "pdf_flat_doc" in (summary or "")
            or any(isinstance(c, dict) and c.get("metadata", {}).get("is_flattened") for c in enriched_chunks)
        )
        if all_doc_image_urls and not is_flattened_doc_context:
            summary = auto_embed_images_in_summary(summary, structured_images or all_doc_image_urls, recommended_title)

        if summary:
            from app.rag.services.rag_generator import repair_markdown_tables
            summary = repair_markdown_tables(summary)

        # Category names for chunk metadata
        cat_names = [c["name"] for c in suggested_categories if isinstance(c, dict) and "name" in c] if suggested_categories else []

        # Structure-aware chunking from canonical text (raw parser output — never LLM-rewritten)
        # Preserve high-fidelity page-scoped chunks from pipeline if present.
        # Only fallback to re-chunking summary markdown if enriched_chunks is empty.
        if (not enriched_chunks or len(enriched_chunks) == 0) and summary and summary.strip():
            try:
                from app.rag.utils.summary_chunker import chunk_summary_markdown
                enriched_chunks = chunk_summary_markdown(
                    summary=summary,
                    source_file=file_name,
                    knowledge_id=knowledge_id,
                    batch_id=batch_id,
                    file_hash=file_hash,
                    title=recommended_title,
                    doc_type=extracted_doc_type or "GENERAL",
                    categories=cat_names,
                    valid_from=str(extracted_valid_from).strip() if extracted_valid_from else None,
                    valid_until=str(extracted_valid_until).strip() if extracted_valid_until else None,
                    visibility_settings=visibility_settings,
                )
                logger.info(f"Canonical text chunking produced {len(enriched_chunks)} staging chunks.")
            except Exception as rechunk_err:
                logger.warning(f"Canonical text chunking failed, keeping parser chunks: {rechunk_err}")
        else:
            logger.info(f"Preserving {len(enriched_chunks) if enriched_chunks else 0} granular page-scoped chunks extracted by pipeline parser.")

        if summary:
            from app.rag.services.rag_generator import repair_markdown_tables
            summary = repair_markdown_tables(summary)

        # Populate Turn 0 in history so initial ingestion prompt and summary immediately render in Review Dashboard
        history_list = []
        if user_prompt and str(user_prompt).strip():
            history_list = [
                {"role": "user", "content": str(user_prompt).strip(), "attachmentName": file_name},
                {"role": "assistant", "content": summary}
            ]

        timing_metrics["total_ingestion_ms"] = int((_time.time() - t0_total) * 1000)

        # Structure the final pending document state in exact requested order
        from app.rag.pipeline_versions import PARSER_VERSION
        staged_document = {
            "pipeline_versions": {"parser": PARSER_VERSION} if is_flattened_doc_context else {},
            "knowledge_id": knowledge_id,
            "batch_id": batch_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "title": recommended_title,
            "status": "On review",
            "document_type": extracted_doc_type,
            "summary": summary,
            "image_url": all_doc_image_urls[0] if all_doc_image_urls else None,
            "image_urls": all_doc_image_urls,
            "images": structured_images,
            "text_accuracy": text_accuracy,
            "full_coverage": True,
            "feedback": feedback,
            "batch_summary": None,
            "suggested_categories": suggested_categories,
            "visibility_settings": visibility_settings,
            "initial_prompt": user_prompt if user_prompt and str(user_prompt).strip() else None,
            "initial_summary": summary,
            "history": history_list,
            "chunks": enriched_chunks,
            "timing_metrics": timing_metrics
        }
        if doc_s3_key:
            staged_document["s3_key"] = doc_s3_key
            staged_document["storage_key"] = doc_s3_key
        
        # Save back to pending folder using knowledge_id in filename
        pending_file_path = os.path.join("data/pending", f"{knowledge_id}.json")
        await asyncio.to_thread(_write_json_sync, pending_file_path, staged_document)

        # Upload staging JSON to MinIO staging bucket (Source of Truth)
        try:
            from app.services.storage import upload_staging_json
            await asyncio.to_thread(upload_staging_json, knowledge_id, staged_document)
        except Exception as st_err:
            logger.debug(f"MinIO staging upload note for {knowledge_id}: {st_err}")

        # Remove temporary output_file if named differently (e.g. filename_parsed.json)
        if output_file and os.path.exists(output_file) and os.path.abspath(output_file) != os.path.abspath(pending_file_path):
            try:
                os.remove(output_file)
            except Exception:
                pass

        if is_ingestion_cancelled(knowledge_id):
            logger.info(f"🛑 [INGESTION ABORTED] Knowledge ID '{knowledge_id}' was cancelled before final DB commit. Discarding.")
            if os.path.exists(pending_file_path):
                try:
                    os.remove(pending_file_path)
                except Exception:
                    pass
            try:
                from app.services.storage import delete_staging_json
                delete_staging_json(knowledge_id)
            except Exception:
                pass
            return

        # Update Knowledge DB table status to PENDING
        t0_db = _time.time()
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge, KnowledgeStatus
            from sqlalchemy import select
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                try:
                    k_uuid = _uuid.UUID(str(knowledge_id))
                    stmt_k = select(Knowledge).where(Knowledge.id == k_uuid)
                except ValueError:
                    stmt_k = select(Knowledge).where(Knowledge.file_name == str(knowledge_id))

                result = await session.execute(stmt_k)
                k_entry = result.scalars().first()
                if k_entry:
                    k_entry.deleted_at = None
                    k_entry.status = KnowledgeStatus.PENDING
                    k_entry.title = recommended_title
                    k_entry.ai_summary = summary
                    k_entry.ai_confidence = float(text_accuracy.replace("%", "")) if isinstance(text_accuracy, str) and "%" in text_accuracy else 95.00
                    if k_entry.metadata_ is None:
                        k_entry.metadata_ = {}

                    # Avoid multi-megabyte JSONB column bloat for large documents:
                    # initial_summary and assistant turn history fall back cleanly to ai_summary in UI
                    is_huge = len(summary) > 50000
                    compact_history = history_list
                    if is_huge and history_list:
                        compact_history = [
                            {"role": "user", "content": h.get("content", ""), "attachmentName": h.get("attachmentName")}
                            if h.get("role") == "user" else {"role": "assistant", "content": ""}
                            for h in history_list
                        ]

                    k_entry.metadata_.update({
                        "batch_id": batch_id,
                        "file_hash": file_hash,
                        "document_type": extracted_doc_type,
                        "initial_prompt": user_prompt if user_prompt and str(user_prompt).strip() else None,
                        "initial_summary": "" if is_huge else summary,
                        "history": compact_history,
                        "chat_history": compact_history,
                        "suggested_categories": suggested_categories,
                        "categories": [c["name"] for c in suggested_categories if isinstance(c, dict) and "name" in c] if suggested_categories else [],
                        "visibility_settings": visibility_settings,
                        "image_url": all_doc_image_urls[0] if all_doc_image_urls else None,
                        "image_urls": all_doc_image_urls,
                        "images": structured_images,
                        "feedback": feedback,
                        "timing_metrics": timing_metrics
                    })
                    # Do not store raw chunks in Postgres metadata_ JSONB; data/pending/{id}.json is the canonical staging store
                    k_entry.metadata_.pop("chunks", None)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(k_entry, "metadata_")
                    await session.commit()
        except Exception as db_err:
            logger.warning(f"Could not update status to PENDING in Knowledge DB table: {db_err}")

        timing_metrics["database_insert_ms"] = int((_time.time() - t0_db) * 1000)
        timing_metrics["total_ingestion_ms"] = int((_time.time() - t0_total) * 1000)

        # Update staged document with final timing metrics and save to pending folder
        staged_document["timing_metrics"] = timing_metrics
        await asyncio.to_thread(_write_json_sync, pending_file_path, staged_document)

        # Phase 1 Shadow Ingestion into Canonical Clinical Evidence Schema (Run in thread pool so it never blocks event loop)
        try:
            await asyncio.to_thread(
                _run_canonical_shadow_ingest_sync,
                knowledge_id=str(knowledge_id),
                file_name=file_name,
                file_hash=file_hash,
                extracted_doc_type=extracted_doc_type,
                visibility_settings=visibility_settings,
                recommended_title=recommended_title,
                enriched_chunks=enriched_chunks,
                summary=summary
            )
            logger.info(f"✨ [SHADOW INGEST] Populated Canonical Evidence for {knowledge_id}")
            # Coverage and structure of the draft, ready on the readiness gate before the admin approves
            from app.rag.services.ingest_quality import schedule_quality_check
            schedule_quality_check(str(knowledge_id), probes=False)
        except Exception as can_err:
            logger.warning(f"Shadow Ingest note (non-fatal): {can_err}")

        logger.info(
            f"\n"
            f"[SINGLE FILE INGESTION TIMING] File: '{file_name}' (ID: {knowledge_id})\n"
            f"  - Parsing Stage        : {timing_metrics['parsing_ms']} ms\n"
            f"  - LLM Review Stage     : {timing_metrics['llm_review_ms']} ms\n"
            f"  - DB Staging Stage     : {timing_metrics['database_insert_ms']} ms\n"
            f"  - Total Ingestion Time : {timing_metrics['total_ingestion_ms']} ms\n"
        )

        # Cleanup temporary uploaded raw file on success
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"🧹 Cleaned up temporary ingestion file: {file_path}")
        except Exception:
            pass
        finally:
            if file_hash:
                ACTIVE_PROCESSING_HASHES.pop(file_hash, None)

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Failed background processing for document '{file_name}' (ID: {knowledge_id}): {err_msg}")
        
        # Cleanup temporary file on error
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

        # 1. Update/write FAILED document JSON in data/pending
        try:
            os.makedirs("data/pending", exist_ok=True)
            pending_file_path = os.path.join("data/pending", f"{knowledge_id}.json")
            failed_doc = {
                "knowledge_id": knowledge_id,
                "batch_id": batch_id,
                "file_name": file_name,
                "file_hash": file_hash,
                "title": file_name,
                "status": "FAILED",
                "document_type": "GENERAL",
                "error_message": err_msg,
                "summary": f"[Gagal Diproses] Terjadi kesalahan saat memproses dokumen '{file_name}': {err_msg}",
                "feedback": f"Gagal mengekstrak atau menganalisis dokumen: {err_msg}",
                "suggested_categories": [],
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                },
                "history": [],
                "chunks": [],
                "timing_metrics": timing_metrics
            }
            await asyncio.to_thread(_write_json_sync, pending_file_path, failed_doc)
        except Exception as json_err:
            logger.warning(f"Could not write failed state JSON: {json_err}")

        # 2. Update PostgreSQL Knowledge DB record to REJECTED / FAILED
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge, KnowledgeStatus
            from sqlalchemy import select
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                try:
                    k_uuid = _uuid.UUID(str(knowledge_id))
                    stmt_k = select(Knowledge).where(Knowledge.id == k_uuid)
                except ValueError:
                    stmt_k = select(Knowledge).where(Knowledge.file_name == str(knowledge_id))

                result = await session.execute(stmt_k)
                k_entry = result.scalars().first()
                if k_entry:
                    k_entry.status = KnowledgeStatus.REJECTED
                    k_entry.ai_summary = f"[Gagal Diproses] {err_msg}"
                    if k_entry.metadata_ is None:
                        k_entry.metadata_ = {}
                    k_entry.metadata_["error"] = err_msg
                    k_entry.metadata_["status"] = "FAILED"
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(k_entry, "metadata_")
                    await session.commit()
        except Exception as db_err:
            logger.warning(f"Could not update Knowledge DB record on failure: {db_err}")
    finally:
        CANCELLED_INGESTION_IDS.discard(str(knowledge_id).lower())
        if file_hash:
            ACTIVE_PROCESSING_HASHES.pop(file_hash, None)

async def trigger_batch_summary_after_all_done(batch_id: str, expected_count: int, llm: BaseLLMAdapter, user_prompt: Optional[str] = None, timeout_sec: int = 180):
    """
    Coordinator task that waits until all documents in a multi-file batch finish Parsing & LLM Review,
    then triggers synthesize_batch_executive_summary EXACTLY ONCE for the entire batch.
    """
    import time as _time
    t0 = _time.time()
    logger.info(f"🚀 [BATCH COORDINATOR] Monitoring Batch '{batch_id}' ({expected_count} files)...")

    while _time.time() - t0 < timeout_sec:
        completed_count = 0
        dirs_to_check = ["data/pending", "data/output"]
        for d in dirs_to_check:
            if os.path.exists(d):
                for f in os.listdir(d):
                    if f.endswith(".json") and f != "bm25_index.pkl":
                        try:
                            with open(os.path.join(d, f), "r", encoding="utf-8") as fj:
                                data = json.load(fj)
                            if isinstance(data, dict) and data.get("batch_id") == batch_id:
                                if data.get("status") in ["On review", "PENDING", "APPROVED", "FAILED", "REJECTED"]:
                                    completed_count += 1
                        except Exception:
                            pass
        if completed_count >= expected_count:
            break
        await asyncio.sleep(1.5)

    t0_batch = _time.time()
    try:
        b_summary = await synthesize_batch_executive_summary(batch_id, llm, user_prompt=user_prompt)
        batch_duration_ms = int((_time.time() - t0_batch) * 1000)
        logger.info(
            f"\n"
            f"⏱️ [BATCH EXECUTIVE SUMMARY TIMING] Batch ID: '{batch_id}' ({expected_count} files)\n"
            f"  - Unified Batch Summary Stage : {batch_duration_ms} ms (Executed 1x for full batch)\n"
        )
    except Exception as err:
        logger.warning(f"Could not trigger unified batch summary for {batch_id}: {err}")

async def synthesize_batch_executive_summary(batch_id: str, llm: BaseLLMAdapter, user_prompt: Optional[str] = None) -> Optional[str]:
    """
    Synthesizes multiple uploaded document feedbacks/summaries into a concise, unified Executive Summary paragraph.
    Identifies whether documents are clinically/operationally interrelated or independent.
    Updates all JSON documents in data/pending and data/output for this batch, as well as DB records.
    """
    if not batch_id or not llm:
        return None

    dirs_to_check = ["data/pending", "data/output"]
    batch_docs = []
    batch_file_paths = []

    for d in dirs_to_check:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.endswith(".json") and f != "bm25_index.pkl":
                    fp = os.path.join(d, f)
                    try:
                        with open(fp, "r", encoding="utf-8") as f_json:
                            data = json.load(f_json)
                        if isinstance(data, dict) and data.get("batch_id") == batch_id:
                            batch_docs.append(data)
                            batch_file_paths.append(fp)
                    except Exception:
                        pass

    if len(batch_docs) < 2:
        return None

    docs_text_parts = []
    for i, d in enumerate(batch_docs):
        fname = d.get('file_name', '')
        title = d.get('title', '') or fname
        doctype = d.get('document_type') or d.get('type', 'General')
        ext = os.path.splitext(fname)[1].lower()

        # Use AI-detected feedback (1 sentence) as document description
        # Then supplement with up to 5 chunks of the actual parsed content
        feedback_text = d.get('feedback', '')
        chunks = d.get('chunks', [])
        chunk_samples = []
        for c in chunks[:5]:  # only first 5 chunks to keep context manageable
            c_text = c.get('text', '') if isinstance(c, dict) else str(c)
            if c_text and c_text.strip():
                chunk_samples.append(c_text.strip())

        doc_entry = f"=== DOKUMEN {i+1}: '{fname}' (Tipe: {ext or 'unknown'} | Kategori: {doctype} | Judul: {title}) ===\n"
        if feedback_text:
            doc_entry += f"Ringkasan AI: {feedback_text}\n"
        if chunk_samples:
            doc_entry += f"Sampel Isi Dokumen:\n" + "\n---\n".join(chunk_samples) + "\n"

        docs_text_parts.append(doc_entry)

    docs_text = "\n\n".join(docs_text_parts)

    user_instruction_block = ""
    effective_prompt = user_prompt or next((d.get("initial_prompt") for d in batch_docs if d.get("initial_prompt")), None)
    if effective_prompt and str(effective_prompt).strip():
        user_instruction_block = f"""
INSTRUKSI KHUSUS PENGGUNA (PRIORITAS TINGGI):
"{str(effective_prompt).strip()}"
Harap perhatikan dan penuhi instruksi pengguna di atas saat menyusun ringkasan eksekutif batch ini.
"""

    batch_prompt = f"""
Anda adalah AI Knowledge Specialist & Clinical Data Integrator untuk klinik ERHA (PT Arya Noble).
Pengguna mengunggah {len(batch_docs)} dokumen sekaligus dalam satu batch ingest.

Berikut ringkasan dan sampel isi masing-masing dokumen dalam batch ini:
{docs_text}
{user_instruction_block}
Tugas Anda:
Lakukan rekonsiliasi dan cross-reference antar dokumen di atas secara teliti.
Identifikasi apakah dokumen-dokumen ini saling berkaitan (misalnya: katalog produk + product knowledge detail, atau protokol treatment + bahan aktif).

PENTING — ATURAN AKURASI:
- HANYA gunakan informasi yang BENAR-BENAR ADA di konten dokumen di atas.
- DILARANG mengarang, mengestimasi, atau menambah informasi yang tidak tercantum.
- Jika informasi tidak tersedia di dokumen, nyatakan "tidak ditemukan di dokumen" — JANGAN mengisi dengan asumsi.

ATURAN FORMAT OUTPUT WAJIB:
- JANGAN gunakan heading/judul apapun (DILARANG menulis '### Batch Executive Summary', dsb.)
- JANGAN gunakan penomoran section seperti '1. **Status...**'
- Ikuti PERSIS struktur berikut dalam teks biasa:

[Paragraf 1 - Status Batch & Hubungan Antar Dokumen]:
Sebutkan jumlah dokumen, jenis masing-masing, dan apakah mereka saling terkait atau independen.

[Jika ada cross-reference yang ditemukan — tuliskan sebagai bullet sederhana]:
[Nama Produk/Treatment] → [informasi yang dikaitkan dari dokumen lain]

[Penutup singkat — hal yang tidak dapat dicocokkan karena data tidak ada di dokumen]
"""
    try:
        batch_summary = await asyncio.to_thread(llm.generate, batch_prompt)
        batch_summary = batch_summary.strip().strip('"').strip("'")
        
        # Clean up any accidental leading header if generated
        import re
        batch_summary = re.sub(r"^#+\s*(Batch\s+)?Executive\s+Summary\s*\n+", "", batch_summary, flags=re.IGNORECASE).strip()

        # Save batch_summary to each document's JSON on disk preserving all fields
        for fp in batch_file_paths:
            try:
                if os.path.exists(fp):
                    with open(fp, "r", encoding="utf-8") as in_f:
                        cur_doc = json.load(in_f)
                    if isinstance(cur_doc, dict):
                        cur_doc["batch_summary"] = batch_summary
                        with open(fp, "w", encoding="utf-8") as out_f:
                            json.dump(cur_doc, out_f, indent=4, ensure_ascii=False)
            except Exception as save_err:
                logger.warning(f"Could not save batch_summary to file {fp}: {save_err}")

        # Sync batch_summary to Postgres DB records metadata_
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            from sqlalchemy import select
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                for doc_data in batch_docs:
                    k_id_str = doc_data.get("knowledge_id")
                    if k_id_str:
                        try:
                            try:
                                k_uuid = _uuid.UUID(str(k_id_str))
                                stmt_b = select(Knowledge).where(Knowledge.id == k_uuid)
                            except ValueError:
                                stmt_b = select(Knowledge).where(Knowledge.file_name == str(k_id_str))

                            res = await session.execute(stmt_b)
                            k_obj = res.scalars().first()
                            if k_obj:
                                meta = dict(k_obj.metadata_) if isinstance(k_obj.metadata_, dict) else {}
                                meta["batch_summary"] = batch_summary
                                k_obj.metadata_ = meta
                        except Exception:
                            pass
                await session.commit()
        except Exception as db_sync_err:
            logger.warning(f"Could not sync batch_summary to DB: {db_sync_err}")

        logger.info(f"Synthesized batch executive summary for batch {batch_id}: {batch_summary[:80]}...")
        return batch_summary
    except Exception as e:
        logger.warning(f"Could not synthesize batch executive summary: {e}")
        return None

@router.post(
    "/ingest", 
    tags=["Ingestion"], 
    summary="Upload and Ingest Document",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Document file(s) to upload (PDF, DOCX, XLSX, TXT, JPG, PNG)"
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Optional custom AI processing instruction"
                            },
                            "replace_existing": {
                                "type": "boolean",
                                "default": False,
                                "description": "Set to true to overwrite existing pending draft"
                            }
                        },
                        "required": ["file"]
                    }
                }
            }
        }
    }
)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: List[UploadFile] = File(..., description="Document file(s) to upload (PDF, DOCX, XLSX, TXT, JPG, PNG)"),
    prompt: Optional[str] = Form(None, description="Optional custom AI processing instruction"),
    replace_existing: bool = Form(False, description="Set to true to overwrite existing pending draft"),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    llm: BaseLLMAdapter = Depends(get_llm),
    batch_id: Optional[str] = Form(None, description="Optional shared batch ID for multi-file upload session"),
    replace_knowledge_id: Optional[str] = Form(None, include_in_schema=False)
):
    """
    Uploads and extracts document files (PDF, DOCX, XLSX, TXT, JPG, PNG) into the staging area for review.
    replace_knowledge_id (set by the replace-file flow) re-processes that document in place instead of
    treating its own file as a duplicate or creating a second knowledge record.
    """
    # Called directly as a function (replace-file, chunked upload), omitted arguments are still FastAPI
    # Form(...) markers, not values; they ended up in the job state and broke JSON serialization.
    from pydantic.fields import FieldInfo
    def _plain(value, default):
        return default if isinstance(value, FieldInfo) else value
    prompt = _plain(prompt, None)
    replace_existing = _plain(replace_existing, False)
    batch_id = _plain(batch_id, None)
    replace_knowledge_id = _plain(replace_knowledge_id, None)
    if replace_knowledge_id:
        replace_existing = True

    upload_list = file if isinstance(file, list) else [file]
    upload_list = [f for f in upload_list if f is not None and f.filename]
    if not upload_list:
        raise HTTPException(status_code=400, detail="Please upload at least one document file.")

    try:
        from app.models.knowledge import KnowledgeType
        import uuid as _uuid
        import hashlib
        
        os.makedirs("data/temp", exist_ok=True)
        if not batch_id:
            batch_id = str(_uuid.uuid4()) if len(upload_list) > 1 else None
        total_files = len(upload_list)

        logger.info(
            f"🚀 [BATCH: {batch_id or 'SINGLE'}] Starting bounded parallel ingestion for {total_files} file(s) "
            f"(concurrency limit: {settings.max_ingestion_concurrency})."
        )

        upload_semaphore = asyncio.Semaphore(settings.max_ingestion_concurrency)

        async def _process_single_upload_file(target_file: UploadFile, idx: int, total: int) -> dict:
            file_label = f"[BATCH: {batch_id or 'SINGLE'}] [FILE {idx}/{total}: {target_file.filename}]"
            try:
                async with upload_semaphore:
                    logger.info(f"📥 {file_label} Intake started...")
                    k_type = KnowledgeType.GENERAL

                    os.makedirs("data/temp", exist_ok=True)
                    unique_prefix = _uuid.uuid4().hex[:12]
                    clean_orig_name = os.path.basename(target_file.filename)
                    file_path = f"data/temp/{unique_prefix}_{clean_orig_name}"
                    hasher = hashlib.sha256()

                    # Stream upload chunk-by-chunk directly to disk to prevent RAM spikes (safe for >100MB files)
                    with open(file_path, "wb") as f_out:
                        while chunk := await target_file.read(1024 * 1024):
                            hasher.update(chunk)
                            f_out.write(chunk)

                    file_hash = hasher.hexdigest()
                    file_size = os.path.getsize(file_path)

                    if replace_existing and file_hash:
                        ACTIVE_PROCESSING_HASHES.pop(file_hash, None)

                    # -------------------------------------------------------------
                    # 4-WAY DUPLICATE DETECTION LIFECYCLE (PROCESSING / PUBLISHED / PENDING / NEW)
                    # -------------------------------------------------------------
                    dup_info = detect_duplicate_lifecycle(file_hash, target_file.filename, exclude_knowledge_id=replace_knowledge_id)
                    dup_status = dup_info.get("status", "NEW")
                    if replace_knowledge_id and dup_status in ("NEW", "PROCESSING"):
                        # Replacing a document in place: re-use its record like an overwritten draft
                        dup_info = {"status": "PENDING", "knowledge_id": replace_knowledge_id,
                                    "existing_file": target_file.filename, "match_reason": "Replace File"}
                        dup_status = "PENDING"

                    # 0. STATE: PROCESSING -> PREVENT REDUNDANT CONCURRENT INGESTION
                    if dup_status == "PROCESSING" and not replace_existing:
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        proc_msg = (
                            f"Dokumen '{target_file.filename}' saat ini sedang dianalisis dan diekstrak di antrean server "
                            f"(Knowledge ID: {dup_info.get('knowledge_id')}). Mohon tunggu proses selesai."
                        )
                        logger.warning(f"⏳ {file_label} {proc_msg}")
                        if total == 1:
                            raise HTTPException(
                                status_code=409,
                                detail=proc_msg
                            )
                        return {
                            "file_name": target_file.filename,
                            "existing_knowledge_id": dup_info.get("knowledge_id"),
                            "batch_id": batch_id,
                            "status": "PROCESSING",
                            "action": "QUEUED_ALREADY",
                            "duplicate_status": "PROCESSING",
                            "detail": proc_msg
                        }

                    # 1. STATE: PUBLISHED -> BLOCK
                    if dup_status == "PUBLISHED":
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        block_msg = (
                            f"Dokumen '{target_file.filename}' sudah terpublikasi (PUBLISHED / APPROVED) "
                            f"di knowledge base aktif ({dup_info.get('match_reason')}: '{dup_info.get('existing_file')}'). "
                            f"Upload dibatalkan untuk menjaga keakuratan sistem dokter."
                        )
                        logger.warning(f"🚫 {file_label} {block_msg}")
                        if total == 1:
                            raise HTTPException(
                                status_code=400,
                                detail=block_msg + " Silakan gunakan menu 'Edit Knowledge' di UI jika ingin memperbarui."
                            )
                        return {
                            "file_name": target_file.filename,
                            "batch_id": batch_id,
                            "status": "BLOCKED",
                            "action": "BLOCKED",
                            "duplicate_status": "PUBLISHED",
                            "detail": block_msg
                        }

                    # 2. STATE: PENDING -> REQUIRE ADMIN CONFIRMATION (DO NOT SILENTLY OVERWRITE)
                    # BUT if the existing pending document was REJECTED / FAILED, automatically permit re-ingestion!
                    is_existing_failed = False
                    existing_k_id = dup_info.get("knowledge_id")
                    if existing_k_id:
                        try:
                            from app.core.database import get_sync_engine
                            from sqlalchemy import text
                            with get_sync_engine().connect() as sync_conn:
                                chk = sync_conn.execute(
                                    text("SELECT status, ai_summary FROM knowledge WHERE id = :kid"),
                                    {"kid": str(existing_k_id)}
                                ).first()
                                if chk:
                                    chk_st = str(chk.status or "").upper()
                                    chk_sum = str(chk.ai_summary or "")
                                    if chk_st == "REJECTED" or chk_sum.startswith("[Gagal Diproses]"):
                                        is_existing_failed = True
                        except Exception:
                            pass

                    if dup_status == "PENDING" and not replace_existing and not is_existing_failed:
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        pending_msg = (
                            f"Draft peninjauan untuk '{target_file.filename}' (ID: {existing_k_id}) "
                            f"sudah ada di antrean On Review (Pending) ({dup_info.get('match_reason')}: '{dup_info.get('existing_file')}')."
                        )
                        logger.warning(f"⚠️ {file_label} {pending_msg}")
                        if total == 1:
                            raise HTTPException(
                                status_code=409,
                                detail=pending_msg + " Upload dibatalkan agar draft lama tidak tertimpa. Silakan selesaikan review atau kirim 'replace_existing=true'."
                            )
                        return {
                            "file_name": target_file.filename,
                            "existing_knowledge_id": existing_k_id,
                            "batch_id": batch_id,
                            "status": "REQUIRE_CONFIRMATION",
                            "action": "REQUIRE_ADMIN_CONFIRMATION",
                            "duplicate_status": "PENDING",
                            "detail": pending_msg + " Kirim 'replace_existing=true' jika ingin menimpa draft ini."
                        }

                    # 3. STATE: NEW or PENDING with replace_existing=True (or auto-recovered failed draft) -> PROCEED
                    k_id = existing_k_id if (dup_status == "PENDING" and (replace_existing or is_existing_failed)) else None

                    try:
                        from app.core.database import AsyncSessionLocal
                        from app.models.knowledge import Knowledge, KnowledgeStatus
                        from app.models.user import User
                        from sqlalchemy import select

                        async with AsyncSessionLocal() as session:
                            user_result = await session.execute(select(User).limit(1))
                            user = user_result.scalars().first()
                            user_id = user.id if user else _uuid.uuid4()

                            custom_uuid = None
                            if k_id:
                                try:
                                    custom_uuid = _uuid.UUID(k_id)
                                except ValueError:
                                    pass

                            existing_doc = None
                            if custom_uuid:
                                existing_doc = await session.get(Knowledge, custom_uuid)
                                if existing_doc and existing_doc.deleted_at is not None:
                                    existing_doc = None
                            if not existing_doc and (dup_status == "PENDING" and replace_existing):
                                res = await session.execute(
                                    select(Knowledge).where(
                                        Knowledge.file_name == target_file.filename,
                                        Knowledge.deleted_at.is_(None)
                                    ).order_by(Knowledge.created_at.desc())
                                )
                                existing_doc = res.scalars().first()

                            if existing_doc:
                                knowledge = existing_doc
                                knowledge.status = KnowledgeStatus.PROCESSING
                                knowledge.ai_summary = "Processing..."
                                knowledge.original_path = file_path
                                knowledge.mime_type = target_file.content_type
                                knowledge.file_size = file_size
                                if knowledge.metadata_ is None:
                                    knowledge.metadata_ = {}
                                knowledge.metadata_["batch_id"] = batch_id
                                knowledge.metadata_["file_hash"] = file_hash
                                if dup_status == "PENDING" and replace_existing:
                                    knowledge.metadata_["replaced_at"] = str(asyncio.get_event_loop().time())
                                await session.commit()
                                await session.refresh(knowledge)
                                k_id = str(knowledge.id)
                            else:
                                metadata = {
                                    "batch_id": batch_id,
                                    "file_hash": file_hash
                                }
                                knowledge = Knowledge(
                                    id=_uuid.uuid4(),
                                    type=k_type,
                                    title=target_file.filename,
                                    file_name=target_file.filename,
                                    original_path=file_path,
                                    mime_type=target_file.content_type,
                                    file_size=file_size,
                                    status=KnowledgeStatus.PROCESSING,
                                    uploaded_by=user_id,
                                    ai_summary="Processing...",
                                    ai_confidence=0.0,
                                    metadata_=metadata
                                )
                                session.add(knowledge)
                                await session.commit()
                                await session.refresh(knowledge)
                                k_id = str(knowledge.id)
                    except Exception as db_err:
                        logger.warning(f"{file_label} Could not create/update Knowledge DB record: {db_err}")
                        if not k_id:
                            k_id = str(_uuid.uuid4())

                    # Upload original document to MinIO
                    original_s3_key = None
                    try:
                        from app.services.storage import upload_document
                        doc_upload = upload_document(
                            file_path=file_path,
                            filename=target_file.filename,
                            document_id=k_id,
                            content_type=target_file.content_type or "application/octet-stream"
                        )
                        if doc_upload.get("status") == "success":
                            original_s3_key = doc_upload["s3_key"]
                            logger.info(f"📄 {file_label} [ID: {k_id}] Original document uploaded to MinIO: {original_s3_key}")
                    except Exception as minio_err:
                        logger.warning(f"{file_label} MinIO upload note: {minio_err}")

                    # Register active in-flight processing hash
                    if file_hash:
                        import time as _time
                        ACTIVE_PROCESSING_HASHES[file_hash] = {
                            "knowledge_id": k_id,
                            "file_name": target_file.filename,
                            "started_at": _time.time()
                        }

                    # Spawn concurrent background ingestion task (governed by _ingestion_semaphore)
                    uncancel_ingestion_job(k_id)
                    asyncio.create_task(
                        process_ingestion_background(
                            k_id,
                            file_path,
                            target_file.filename,
                            pipeline,
                            llm,
                            prompt,
                            file_hash,
                            batch_id
                        )
                    )

                    status_display = "On review (Replaced)" if (dup_status == "PENDING" and replace_existing) else "On review"
                    logger.info(f"✅ {file_label} [ID: {k_id}] Staged successfully ({status_display}).")
                    return {
                        "knowledge_id": k_id,
                        "batch_id": batch_id,
                        "file_name": target_file.filename,
                        "original_s3_key": original_s3_key,
                        "duplicate_status": "PENDING_REPLACED" if (dup_status == "PENDING" and replace_existing) else "NEW",
                        "status": status_display,
                        "action": "QUEUED",
                        "detail": f"Berhasil masuk antrean peninjauan ({status_display})."
                    }

            except HTTPException as http_exc:
                if total == 1:
                    raise http_exc
                logger.warning(f"⚠️ {file_label} HTTP rejection: {http_exc.detail}")
                return {
                    "file_name": target_file.filename,
                    "batch_id": batch_id,
                    "status": "FAILED",
                    "action": "FAILED",
                    "detail": str(http_exc.detail)
                }
            except Exception as exc:
                logger.error(f"❌ {file_label} Intake exception: {exc}")
                if total == 1:
                    raise HTTPException(status_code=500, detail=str(exc))
                return {
                    "file_name": target_file.filename,
                    "batch_id": batch_id,
                    "status": "FAILED",
                    "action": "FAILED",
                    "detail": f"Gagal memproses file: {str(exc)}"
                }

        # Process upload files concurrently with safe bounded concurrency
        tasks = [_process_single_upload_file(f, idx + 1, total_files) for idx, f in enumerate(upload_list)]
        response_items = await asyncio.gather(*tasks)

        # Calculate batch statistics
        queued_items = [r for r in response_items if r.get("action") == "QUEUED" or r.get("knowledge_id")]
        failed_items = [r for r in response_items if r.get("action") == "FAILED" or r.get("status") == "FAILED"]
        blocked_items = [r for r in response_items if r.get("action") in ("BLOCKED", "REQUIRE_ADMIN_CONFIRMATION")]

        success_count = len(queued_items)
        fail_count = len(failed_items)
        blocked_count = len(blocked_items)

        logger.info(
            f"🏁 [BATCH: {batch_id or 'SINGLE'}] Batch intake complete: "
            f"{success_count} queued, {fail_count} failed, {blocked_count} blocked (Total: {total_files})."
        )

        # Spawn batch coordinator task if multi-file batch upload and at least one queued
        if batch_id and len(queued_items) > 1 and llm:
            asyncio.create_task(
                trigger_batch_summary_after_all_done(batch_id, len(queued_items), llm, user_prompt=prompt)
            )

        overall_status = "success" if (success_count == total_files) else ("partial_success" if success_count > 0 else "failed")

        return {
            "status": overall_status,
            "batch_id": batch_id,
            "total_files": total_files,
            "processed_files": success_count,
            "failed_files": fail_count,
            "blocked_files": blocked_count,
            "message": (
                f"Processed {total_files} document(s) in Batch '{batch_id}' "
                f"({success_count} queued for review, {fail_count} failed, {blocked_count} blocked/pending confirmation)."
                if batch_id else
                f"Successfully queued {upload_list[0].filename} for ingestion."
            ),
            "documents": response_items
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest document(s): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/text", tags=["Ingestion"], summary="Ingest Knowledge By Text Only")
async def ingest_text_only(
    req: TextIngestRequest,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    llm: BaseLLMAdapter = Depends(get_llm)
):
    """
    ✍️ Ingest Knowledge By Text Saja:
    Memasukkan materi pengetahuan secara langsung via teks tanpa melampirkan file.
    Sistem secara otomatis mengonversi teks menjadi dokumen terstruktur `.md`,
    melakukan rekonstruksi struktur/normalisasi, mengunggah ke MinIO `knowledge-documents`,
    dan menempatkan draft di area peninjauan On Review (Pending).
    """
    if not req.text_content or not req.text_content.strip():
        raise HTTPException(status_code=400, detail="Text content cannot be empty.")

    try:
        from app.models.knowledge import KnowledgeType, Knowledge, KnowledgeStatus
        from app.models.user import User
        from app.rag.utils.normalizer import normalize_document_text
        from app.services.storage import upload_document
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        import uuid as _uuid
        import hashlib
        import re

        raw_text = req.text_content.strip()

        # 1. Determine or infer title
        doc_title = req.title.strip() if req.title and req.title.strip() else None
        if not doc_title:
            first_line = raw_text.split('\n')[0].strip().lstrip('#').strip()
            if first_line and len(first_line) <= 80:
                doc_title = first_line
            else:
                doc_title = f"Pengetahuan Teks {int(asyncio.get_event_loop().time())}"

        # Clean title for filename
        clean_filename_base = re.sub(r'[^\w\s-]', '', doc_title).strip().replace(' ', '_')
        if not clean_filename_base:
            clean_filename_base = "knowledge_text"
        filename = f"{clean_filename_base}.md"

        # 2. Normalize text into structured markdown
        normalized_markdown = normalize_document_text(raw_text)
        if not normalized_markdown.startswith('#'):
            normalized_markdown = f"# {doc_title}\n\n" + normalized_markdown

        file_bytes = normalized_markdown.encode('utf-8')
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # 3. Duplicate detection
        dup_info = detect_duplicate_lifecycle(file_hash, filename)
        dup_status = dup_info.get("status", "NEW")

        if dup_status == "PUBLISHED":
            raise HTTPException(
                status_code=400,
                detail=f"Materi teks '{doc_title}' sudah terpublikasi (APPROVED) di knowledge base. Silakan gunakan menu Edit Knowledge jika ingin memperbarui."
            )

        if dup_status == "PENDING" and not req.replace_existing:
            raise HTTPException(
                status_code=409,
                detail=f"Draft peninjauan untuk '{doc_title}' sudah ada di antrean On Review. Kirim 'replace_existing=true' untuk mengganti draft lama."
            )

        # 4. Save temp .md file
        os.makedirs("data/temp", exist_ok=True)
        file_path = f"data/temp/{filename}"
        with open(file_path, "wb") as f_out:
            f_out.write(file_bytes)

        file_size = len(file_bytes)

        # 5. Create or update Knowledge DB record
        k_id = dup_info.get("knowledge_id") if (dup_status == "PENDING" and req.replace_existing) else None
        async with AsyncSessionLocal() as session:
            user_result = await session.execute(select(User).limit(1))
            user = user_result.scalars().first()
            user_id = user.id if user else _uuid.uuid4()

            custom_uuid = None
            if k_id:
                try:
                    custom_uuid = _uuid.UUID(k_id)
                except ValueError:
                    pass

            existing_doc = None
            if custom_uuid:
                existing_doc = await session.get(Knowledge, custom_uuid)

            if existing_doc:
                knowledge = existing_doc
                knowledge.title = doc_title
                knowledge.status = KnowledgeStatus.PROCESSING
                knowledge.ai_summary = "Processing..."
                knowledge.original_path = file_path
                knowledge.mime_type = "text/markdown"
                knowledge.file_size = file_size
                if knowledge.metadata_ is None:
                    knowledge.metadata_ = {}
                knowledge.metadata_["file_hash"] = file_hash
                await session.commit()
                await session.refresh(knowledge)
                k_id = str(knowledge.id)
            else:
                knowledge = Knowledge(
                    id=custom_uuid if custom_uuid else _uuid.uuid4(),
                    type=KnowledgeType.GENERAL,
                    title=doc_title,
                    file_name=filename,
                    original_path=file_path,
                    mime_type="text/markdown",
                    file_size=file_size,
                    status=KnowledgeStatus.PROCESSING,
                    uploaded_by=user_id,
                    ai_summary="Processing...",
                    ai_confidence=0.0,
                    metadata_={"file_hash": file_hash}
                )
                session.add(knowledge)
                await session.commit()
                await session.refresh(knowledge)
                k_id = str(knowledge.id)

        # 6. Upload .md document to MinIO
        original_s3_key = None
        try:
            doc_upload = upload_document(
                content=file_bytes,
                filename=filename,
                document_id=k_id,
                content_type="text/markdown"
            )
            if doc_upload.get("status") == "success":
                original_s3_key = doc_upload["s3_key"]
        except Exception as minio_err:
            logger.warning(f"Could not upload text .md document to MinIO: {minio_err}")

        # 7. Process background ingestion for staging draft
        uncancel_ingestion_job(k_id)
        asyncio.create_task(
            process_ingestion_background(
                k_id,
                file_path,
                filename,
                pipeline,
                llm,
                req.prompt,
                file_hash,
                None
            )
        )

        return {
            "status": "success",
            "knowledge_id": k_id,
            "file_name": filename,
            "title": doc_title,
            "original_s3_key": original_s3_key,
            "message": f"Berhasil mengonversi teks menjadi dokumen '{filename}' dan menempatkannya di area peninjauan (On Review)."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Text ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/ingest/pending/{knowledge_id}", tags=["Ingestion"], summary="Get Pending Details", response_model=PendingDocumentResponse)
async def get_pending_details(knowledge_id: str = Path(..., description="Pending document identifier (UUID)")):
    """
    Retrieves extracted text, summary, and metadata of a pending staged document.
    """
    target_file = resolve_pending_file(knowledge_id) or resolve_approved_file(knowledge_id)
    if not target_file:
        # Fallback check in PostgreSQL DB for PROCESSING status
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            import uuid as _uuid
            async with AsyncSessionLocal() as session:
                custom_uuid = None
                try:
                    custom_uuid = _uuid.UUID(knowledge_id)
                except ValueError:
                    pass
                
                k_doc = None
                if custom_uuid:
                    k_doc = await session.get(Knowledge, custom_uuid)
                else:
                    from sqlalchemy import select
                    res = await session.execute(
                        select(Knowledge).where(
                            Knowledge.file_name == knowledge_id,
                            Knowledge.deleted_at.is_(None)
                        ).order_by(Knowledge.created_at.desc())
                    )
                    k_doc = res.scalars().first()
                    
                if k_doc and k_doc.deleted_at is None:
                    return {
                        "knowledge_id": str(k_doc.id),
                        "file_name": k_doc.file_name,
                        "title": k_doc.title,
                        "status": "PROCESSING",
                        "summary": "Document processing in progress...",
                        "text_accuracy": "100%",
                        "feedback": "Pemrosesan dokumen sedang berlangsung di background.",
                        "suggested_categories": [],
                        "chunks": []
                    }
        except Exception as db_err:
            logger.warning(f"DB fallback check failed for {knowledge_id}: {db_err}")

        raise HTTPException(status_code=404, detail=f"Document '{knowledge_id}' not found.")
        
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "knowledge_id" not in data:
                data["knowledge_id"] = knowledge_id
            data.pop("type", None)
            if "status" not in data or not data["status"]:
                data["status"] = "Approved" if "output" in target_file else "On review"
            if "title" not in data or not data["title"]:
                data["title"] = data.get("file_name", "document.pdf")
            if not data.get("image_url") and data.get("chunks"):
                for c in data["chunks"]:
                    if isinstance(c, dict) and c.get("metadata", {}).get("image_url"):
                        data["image_url"] = c["metadata"]["image_url"]
                        break

            # Return in exact PendingDocumentResponse schema order
            ordered_data = {
                "knowledge_id": data.get("knowledge_id"),
                "batch_id": data.get("batch_id"),
                "file_name": data.get("file_name", "document.pdf"),
                "file_hash": data.get("file_hash"),
                "title": data.get("title"),
                "status": data.get("status", "On review"),
                "document_type": data.get("document_type"),
                "valid_from": data.get("valid_from"),
                "valid_until": data.get("valid_until"),
                "summary": data.get("summary", ""),
                "image_url": data.get("image_url"),
                "text_accuracy": data.get("text_accuracy", "100%"),
                "feedback": data.get("feedback", ""),
                "batch_summary": data.get("batch_summary"),
                "suggested_categories": data.get("suggested_categories", []),
                "visibility_settings": data.get("visibility_settings", {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                }),
                "initial_prompt": data.get("initial_prompt"),
                "history": data.get("history", []),
                "chunks": data.get("chunks", [])
            }
            if data.get("timing_metrics"):
                ordered_data["timing_metrics"] = data.get("timing_metrics")
            return ordered_data
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read document details: {e}")


# =============================================================================
# PHASE 1.5 QUALITY GATE & STAGING OBSERVABILITY ENDPOINTS (D1-a & D9)
# =============================================================================

@router.get(
    "/ingest/staging/{knowledge_id}/quality-gate",
    tags=["Ingestion"],
    summary="Get Quality Gate Staging Audit & Readiness",
    response_model=QualityGateResponse
)
async def get_staging_quality_gate(
    knowledge_id: str = Path(..., description="Knowledge UUID"),
    summary_only: bool = Query(False, description="If true, return readiness and metrics only without evidences list")
):
    """
    Returns audit details for Staging Knowledge:
    - Knowledge Readiness Gate (D9)
    - Row Disposition Breakdown (Evidence / Context / Excluded)
    - Visual Jobs & Asset Classification Summary
    - List of Canonical Evidences & Scored Media Assets
    """
    try:
        import asyncio as _asyncio
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        audit_data = await _asyncio.to_thread(can_service.get_quality_gate_audit, knowledge_id, summary_only)
        return audit_data
    except Exception as e:
        logger.error(f"Error fetching quality gate audit for {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quality gate audit: {e}")


@router.put(
    "/ingest/staging/{knowledge_id}/evidence/{evidence_id}",
    tags=["Ingestion"],
    summary="Update Canonical Evidence (D1-a Direct Correction)"
)
async def update_staging_evidence(
    knowledge_id: str = Path(..., description="Knowledge UUID"),
    evidence_id: str = Path(..., description="Evidence UUID"),
    request: UpdateEvidenceRequest = Body(...)
):
    """
    D1-a Implementation:
    Admin corrects clinical facts directly on Canonical Evidence SSOT.
    Derivation is marked 'ADMIN_EDIT', SHA-256 hash is recomputed,
    and derived kb_chunk retrieval_text is kept synchronized.
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        with can_service.engine.connect() as conn:
            from sqlalchemy import text as _text
            v_row = conn.execute(
                _text("SELECT id FROM knowledge_version WHERE knowledge_id = :kid ORDER BY version_no DESC LIMIT 1;"),
                {"kid": str(knowledge_id)}
            ).fetchone()
        if not v_row:
            raise HTTPException(status_code=404, detail=f"No knowledge version found for doc '{knowledge_id}'")
        
        version_id = str(v_row[0])
        result = can_service.update_evidence(
            version_id=version_id,
            evidence_id=evidence_id,
            update_data=request.model_dump(exclude_unset=True)
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update evidence: {e}")


@router.post(
    "/ingest/staging/{knowledge_id}/evidence/{evidence_id}/resolve",
    tags=["Ingestion"],
    summary="Resolve Pending Evidence Review (Knowledge Readiness Gate D9)"
)
async def resolve_staging_evidence(
    knowledge_id: str = Path(..., description="Knowledge UUID"),
    evidence_id: str = Path(..., description="Evidence UUID")
):
    """
    Resolves an item in REVIEW_REQUIRED or LOW_CONFIDENCE state to VISION_COMPLETE,
    unblocking the Knowledge Readiness Gate for publication.
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        with can_service.engine.connect() as conn:
            from sqlalchemy import text as _text
            v_row = conn.execute(
                _text("SELECT id FROM knowledge_version WHERE knowledge_id = :kid ORDER BY version_no DESC LIMIT 1;"),
                {"kid": str(knowledge_id)}
            ).fetchone()
        if not v_row:
            raise HTTPException(status_code=404, detail=f"No knowledge version found for doc '{knowledge_id}'")
        
        version_id = str(v_row[0])
        result = can_service.resolve_evidence(version_id=version_id, evidence_id=evidence_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve evidence: {e}")


@router.post(
    "/ingest/staging/{knowledge_id}/regenerate-summary",
    tags=["Ingestion"],
    summary="Regenerate Summary from Canonical Evidence (D1-a)",
    response_model=RegenerateSummaryResponse
)
async def regenerate_summary_from_evidence(
    knowledge_id: str = Path(..., description="Knowledge UUID")
):
    """
    D1-a Implementation:
    Regenerates clean summary markdown from approved/corrected Canonical Evidence SSOT.
    Updates knowledge_version.summary_md and knowledge.ai_summary.
    Also synchronizes any staged pending JSON file.
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        with can_service.engine.connect() as conn:
            from sqlalchemy import text as _text
            v_row = conn.execute(
                _text("SELECT id FROM knowledge_version WHERE knowledge_id = :kid ORDER BY version_no DESC LIMIT 1;"),
                {"kid": str(knowledge_id)}
            ).fetchone()
        if not v_row:
            raise HTTPException(status_code=404, detail=f"No knowledge version found for doc '{knowledge_id}'")
        
        version_id = str(v_row[0])
        new_summary = can_service.regenerate_summary_from_evidences(knowledge_id, version_id)
        
        # Synchronize staged JSON if exists
        pending_file = resolve_pending_file(knowledge_id)
        if pending_file and os.path.exists(pending_file):
            try:
                with open(pending_file, "r", encoding="utf-8") as pf:
                    staged_data = json.load(pf)
                staged_data["summary"] = new_summary
                staged_data["ai_summary"] = new_summary
                with open(pending_file, "w", encoding="utf-8") as pf:
                    json.dump(staged_data, pf, indent=4, ensure_ascii=False)
            except Exception as pf_err:
                logger.warning(f"Could not update staged pending JSON: {pf_err}")
                
        return RegenerateSummaryResponse(
            knowledge_id=knowledge_id,
            version_id=version_id,
            summary_md=new_summary
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate summary for {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to regenerate summary: {e}")


# =============================================================================
# PHASE 2 VERSIONING, ATOMIC PUBLISH & MEDIA SERVING ENDPOINTS
# =============================================================================

@router.post(
    "/ingest/staging/{knowledge_id}/publish",
    tags=["Ingestion"],
    summary="Publish Document Version Atomically (Phase 2 Transaction)",
    response_model=PublishVersionResponse
)
async def publish_staging_version(
    knowledge_id: str = Path(..., description="Knowledge UUID"),
    request: Optional[PublishVersionRequest] = Body(default=None)
):
    """
    Promotes a staging version to ACTIVE atomically:
    - Verifies Knowledge Readiness Gate (D9)
    - Supersedes previous ACTIVE version(s)
    - Deactivates previous chunks
    - Promotes new version to ACTIVE and activates its chunks
    - Invariant: 0 orphan active projections
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()

        # Find version_id if not supplied
        v_id = request.version_id if request and request.version_id else None
        if not v_id:
            with can_service.engine.connect() as conn:
                from sqlalchemy import text as _text
                v_row = conn.execute(
                    _text("SELECT id FROM knowledge_version WHERE knowledge_id = :kid ORDER BY version_no DESC LIMIT 1;"),
                    {"kid": str(knowledge_id)}
                ).fetchone()
            if not v_row:
                raise HTTPException(status_code=404, detail=f"No version found for document '{knowledge_id}'")
            v_id = str(v_row[0])

        approved_by = request.approved_by if request else None
        result = can_service.publish_version_atomic(
            knowledge_id=knowledge_id,
            version_id=v_id,
            approved_by=approved_by
        )
        return PublishVersionResponse(**result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Atomic publish failed for document {knowledge_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Atomic publish failed: {e}")


@router.get(
    "/media/resolve/{asset_id}",
    tags=["Media Serving"],
    summary="Resolve Media Asset Presigned URL from kb_asset",
    response_model=MediaResolveResponse
)
async def resolve_media_asset_endpoint(
    asset_id: str = Path(..., description="Media Asset UUID or Storage Key"),
    preview: bool = Query(False, description="Allow resolution of staging/preview assets")
):
    """
    Phase 2 Media Serving:
    Resolves browser-accessible and presigned MinIO URL validated against kb_asset.
    Production doctor chatbot inquiries only resolve assets of ACTIVE versions.
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        result = can_service.resolve_media_asset(asset_id=asset_id, preview_mode=preview)
        return MediaResolveResponse(**result)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to resolve media asset '{asset_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve media asset: {e}")


@router.get(
    "/ingest/invariants/verify",
    tags=["Ingestion"],
    summary="Verify Canonical Invariants (No Orphan Active Projections)",
    response_model=InvariantCheckResponse
)
async def verify_invariants_endpoint():
    """
    Phase 2 System Invariant Verification:
    Verifies 0 orphan active chunks, exactly 1 active version per document, and chunk alignment.
    """
    try:
        from app.rag.services.canonical_ingest_service import CanonicalIngestService
        can_service = CanonicalIngestService()
        inv_result = can_service.verify_no_orphan_projections()
        return InvariantCheckResponse(**inv_result)
    except Exception as e:
        logger.error(f"Invariant check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Invariant check failed: {e}")


@router.post("/ingest/pending/{knowledge_id}/refine", tags=["Ingestion"], summary="Refine Pending Document", response_model=PendingDocumentResponse)
async def refine_pending_document(
    knowledge_id: str = Path(..., description="Pending document identifier (UUID)"),
    request: str = Form(..., description="Prompt instructions to refine summary"),
    llm: BaseLLMAdapter = Depends(get_llm),
    file_attachment: Optional[UploadFile] = File(None, description="Optional supporting file attachment")
):
    """
    Refines a pending document summary using custom natural language AI instructions.
    """
    # Parse request: accept plain text prompt, JSON {"prompt":"...","history":[...]}, or RefineRequest object
    if isinstance(request, str):
        try:
            parsed = json.loads(request)
            if isinstance(parsed, dict) and "prompt" in parsed:
                request = RefineRequest.model_validate(parsed)
            else:
                request = RefineRequest(prompt=request, history=[])
        except (json.JSONDecodeError, ValueError):
            request = RefineRequest(prompt=request, history=[])

    pending_file = resolve_pending_file(knowledge_id)
    if not pending_file:
        raise HTTPException(status_code=404, detail=f"Pending document '{knowledge_id}' not found.")
            
    try:
        with open(pending_file, "r", encoding="utf-8") as f:
            staged_data = json.load(f)

        # Incorporate current_summary if user provided manual edits from frontend
        req_curr_summary = getattr(request, "current_summary", None)
        if req_curr_summary and str(req_curr_summary).strip():
            staged_data["summary"] = str(req_curr_summary).strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read staged document: {e}")
        
    if not llm:
        raise HTTPException(status_code=500, detail="LLM adapter is not configured. Cannot perform refinement.")
        
    try:
        attached_file_context = ""
        attached_file_name = ""
        all_attached_images = []

        prompt_str = getattr(request, "prompt", "") if hasattr(request, "prompt") else (request if isinstance(request, str) else "")
        for m in re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', prompt_str):
            img_u = m.group(2).strip()
            if img_u and img_u not in all_attached_images:
                all_attached_images.append(img_u)

        if file_attachment and hasattr(file_attachment, "read") and not ("[SUPPLEMENTARY ATTACHED FILE CONTENT:" in getattr(request, "prompt", "")):
            try:
                temp_dir = "data/temp"
                os.makedirs(temp_dir, exist_ok=True)
                attached_file_name = getattr(file_attachment, "filename", "attached_refine_doc")
                temp_file_path = os.path.join(temp_dir, f"refine_{knowledge_id}_{attached_file_name}")
                
                content_bytes = await file_attachment.read()
                with open(temp_file_path, "wb") as f:
                    f.write(content_bytes)
                
                from app.rag.utils.parser import DocumentParser
                parser = DocumentParser()
                parse_res = parser.parse_file(temp_file_path)
                
                extracted_text = ""
                if parse_res and parse_res.pages:
                    extracted_pages = [p.get("text", "") for p in parse_res.pages if p.get("text")]
                    extracted_text = "\n\n".join(extracted_pages)
                    # Collect all embedded / standalone image URLs across all pages/slides/sheets
                    for p in parse_res.pages:
                        if p.get("image_urls") and isinstance(p["image_urls"], list):
                            for u in p["image_urls"]:
                                if u and u not in all_attached_images:
                                    all_attached_images.append(u)
                        if p.get("image_url") and p["image_url"] not in all_attached_images:
                            all_attached_images.append(p["image_url"])
                elif parse_res and parse_res.docling_doc:
                    try:
                        extracted_text = parse_res.docling_doc.export_to_markdown()
                    except Exception as exp_err:
                        logger.warning(f"Docling export to markdown failed: {exp_err}")
                        extracted_text = ""

                # Sync all attached images to staged_data
                if all_attached_images:
                    if "image_urls" not in staged_data or not isinstance(staged_data["image_urls"], list):
                        staged_data["image_urls"] = []
                    for u in all_attached_images:
                        if u not in staged_data["image_urls"]:
                            staged_data["image_urls"].append(u)
                    if not staged_data.get("image_url") and all_attached_images:
                        staged_data["image_url"] = all_attached_images[0]
                
                if extracted_text or all_attached_images:
                    content_snippet = extracted_text
                    if len(content_snippet) > 10000:
                        content_snippet = content_snippet[:10000] + "\n\n... [KONTEN FILE TERLAMPIR DIPOTONG KARENA PANJANG] ..."

                    media_note = ""
                    if all_attached_images:
                        media_lines = [f"- Attached Image {i+1}: {url}" for i, url in enumerate(all_attached_images)]
                        primary_img = all_attached_images[0]
                        media_note = (
                            f"\n\n[ATTACHED MEDIA ASSET URLS FOR THIS TURN:\n"
                            + "\n".join(media_lines)
                            + f"\nCRITICAL INSTRUCTION: If the admin adds a product or section, embed the exact URL '{primary_img}' inside that product's '### Detail Produk' block as ![Product Name]({primary_img}). "
                            f"If updating/replacing an image, swap the old image tag with ![Product Name]({primary_img}). DO NOT output placeholder text like 'URL_GAMBAR' or 'new_image'. "
                            f"NEVER create an 'Asset Media' heading or append raw media asset lists at the end of the summary.]\n"
                        )

                    attached_file_context = (
                        f"\n\n--- NEWLY ATTACHED SUPPLEMENTARY FILE: '{attached_file_name}' ---\n"
                        f"{content_snippet}{media_note}\n"
                        f"--- END OF ATTACHED FILE CONTENT ---\n"
                    )
                    logger.info(f"📄 Successfully parsed attached file '{attached_file_name}' ({len(extracted_text)} chars, {len(all_attached_images)} images) for pending refine (knowledge_id='{knowledge_id}').")
                
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            except Exception as att_err:
                logger.warning(f"Failed to parse attached file in pending refine: {att_err}")

        # Fetch categories from DB for LLM recommendation
        db_categories = []
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.category import Category
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Category).where(Category.deleted_at.is_(None)))
                cats = res.scalars().all()
                db_categories = [{"id": str(c.id), "name": c.name} for c in cats]
        except Exception as cat_err:
            logger.warning(f"Failed to fetch categories for refine prompt: {cat_err}")

        history_str = ""
        if request.history:
            recent_msgs = request.history[-6:] if len(request.history) > 6 else request.history
            for msg in recent_msgs:
                role = "User" if getattr(msg, "role", "") == "user" else "Assistant"
                content = getattr(msg, "content", "")
                history_str += f"{role}: {content}\n"
        else:
            history_str = "No previous refinement history.\n"

        # Check if user instruction is an explicit product retrieval query (e.g. Test 14)
        retrieval_target = extract_product_retrieval_query(request.prompt)
        retrieved_card = extract_product_card_from_summary(staged_data.get("summary", ""), retrieval_target) if retrieval_target else None
        if retrieved_card:
            logger.info(f"🔍 Handled product retrieval query for '{retrieval_target}' without mutating document catalog.")
            existing_hist = staged_data.get("history", [])
            if not isinstance(existing_hist, list):
                existing_hist = []
            new_hist = list(existing_hist)
            new_hist.append({"role": "user", "content": request.prompt})
            new_hist.append({"role": "assistant", "content": retrieved_card})

            staged_data["history"] = new_hist
            staged_data["reply"] = retrieved_card
            staged_data["answer"] = retrieved_card
            staged_data["is_retrieval"] = True
            staged_data["feedback"] = f"Menampilkan detail produk {retrieval_target} beserta gambar."

            with open(pending_file, "w", encoding="utf-8") as f:
                json.dump(staged_data, f, indent=4, ensure_ascii=False)
            try:
                from app.services.storage import upload_staging_json
                upload_staging_json(knowledge_id, staged_data)
            except Exception:
                pass
            return staged_data

        # ─── COLLABORATIVE KNOWLEDGE BASE EDITOR PROMPT ─────────────────────────────
        refine_prompt = f"""
You are an intelligent, helpful knowledge base editor for PT Arya Noble (ERHA).
Your task is to refine, edit, format, or update the document content based on the Admin's instruction.

======================================================================
ADMIN INSTRUCTION:
"{request.prompt}"
======================================================================

Conversation History (for context only):
{history_str}

CURRENT DOCUMENT CONTENT:
{json.dumps(staged_data.get("summary", ""), ensure_ascii=False)}

{attached_file_context if attached_file_context else ""}

Available Categories from Database:
{json.dumps(db_categories, ensure_ascii=False)}

EDITING GUIDELINES:
1. **UNDERSTAND ADMIN BEHAVIOR & INTENT FLEXIBLY**:
   - Admins may write informally, briefly, or colloquially in Indonesian.
   - If admin asks to delete/remove a section or data (e.g. "hapus warnings", "hilangkan efek samping", "hapus tabel ini"), remove that section cleanly while keeping everything else intact.
   - If admin asks to change/update specific data (e.g. "ganti harga jadi 50.000", "ubah nama produk", "sku nya ganti ke ABC-123"), update that specific value accurately.
   - If admin asks to format or tidy up (e.g. "rapikan teks", "buat jadi 2. **MODULAR PRODUCT CARDS & IMAGE PLACEMENT RULE**:
   - For multi-product catalogs or when adding/editing products:
     Format each product as a modular `### Detail Produk` block with its associated image and bullet attributes so the UI renders interactive Product Cards:
     ```markdown
     ### Detail Produk
     ![Nama Produk Lengkap](URL_GAMBAR)
     - **Nama Produk**: Nama Produk Lengkap
     - **Brand**: Brand Produk (hanya jika ada)
     - **Kategori**: Kategori Produk (hanya jika ada)
     - **Ukuran**: Ukuran/Netto (hanya jika ada)
     - **Harga**: Harga Produk (hanya jika ada)
     - **Kandungan Utama**: Bahan aktif utama (format sebagai bullet point, JANGAN buat heading ### terpisah!)
     - **Manfaat**: Manfaat produk (format sebagai bullet point, JANGAN buat heading ### terpisah!)
     - **Cocok Untuk**: Jenis kulit (format sebagai bullet point)
     - **Aturan Pakai**: Cara penggunaan (format sebagai bullet point)
     - **Deskripsi**: Penjelasan manfaat dan kegunaan produk.
     ```
   - STRICT ZERO-HALLUCINATION RULE: ONLY include `- **SKU**:` IF AND ONLY IF an explicit SKU code/number is stated in the source document or explicitly instructed by Admin. NEVER fabricate SKU numbers (e.g. do NOT invent ERHA-ACNE-001).
   - CRITICAL: NEVER break product attributes into raw markdown headings like `### Ingredients` or `### Benefits`! Keep all product attributes as bullet points inside `### Detail Produk` blocks.
   - Intelligently embed each image into its most relevant section or product block.
   - NEVER create any "Asset Media dari File Terlampir" heading or list of raw media assets at the end of the summary. Embed the attached image URL ONLY where it belongs.
3. **DELETION OF SECTIONS & PRODUCTS RULE**:
   - If the admin instructs to delete or remove a specific product, treatment, or ingredient-based group of products (e.g. "hapus produk X", 'hapus seluruh produk yang mengandung "Betaine"', 'delete produk "Sakura FW New Version"'):
     * You MUST completely delete that product/section's headings, text, tables, AND all associated markdown image tags `![...](url)` belonging to that product/section.
     * Do NOT retain, move, or dump that deleted product's images under other remaining sections or titles.
     * Keep all other untouched products in their modular `### Detail Produk` blocks with all bullet attributes intact.
     * Return pure clean Markdown for the updated document summary. NEVER prepend any change summary headers or callout blocks into the summary text.
3b. **IMAGE DELETION ONLY RULE (CRITICAL)**:
   - If the admin instructs to delete or remove ONLY the image or photo of a product (e.g. "hapus gambar product Spot Gel New Version", "hilangkan foto produk X", "delete image for Y"):
     * You MUST ONLY delete the markdown image tag `![...](url)` of that specific target product.
     * You MUST KEEP that product's section, title, and all its bullet attributes (- **Nama Produk**, - **Kategori**, - **Deskripsi**, etc.) 100% INTACT!
     * NEVER delete the product itself when asked to delete only its image!
     * NEVER delete or touch the images of any other products in the document!
4. **STRICT CATEGORIES RULE**:
   - Select suggested_categories ONLY from the "Available Categories from Database" list above.
   - NEVER invent or create new categories. NEVER output placeholder text like "category_name" or "category_id".
   - If NO category from the list genuinely matches this document, you MUST return an empty array: []!
5. **PRESERVE UNCHANGED CONTENT**: Keep all other sections, bullet points, and facts from the existing document that were not requested to be changed.
6. **CLEAN MARKDOWN**: Ensure the output is clean Markdown with headings (`#`, `##`), bullet points, tables, and blank lines before and after images.
7. **FEEDBACK**: Write 1-2 short, polite Indonesian sentences explaining what was changed (e.g. "Bagian Warnings telah dihapus sesuai instruksi.").
8. **IMAGE REPLACEMENT & SWAP RULE**:
   - If the Admin instructs to replace, swap, or update an existing image (e.g. "ubah gambar A diganti dengan ini", "ganti foto produk dengan foto terlampir", "replace image B"), you MUST REPLACE the existing markdown image tag `![Old Alt](OLD_URL)` with the new image tag `![New Alt](NEW_URL)`.
   - Ensure the OLD image URL is completely removed and replaced by the NEW attached image URL in the document text.

Return a valid JSON object ONLY (do NOT wrap in ```json blocks):
{{
    "knowledge_id": "{staged_data.get('knowledge_id', knowledge_id)}",
    "file_name": "{staged_data.get('file_name', knowledge_id)}",
    "title": "{staged_data.get('title', 'Document Title')}",
    "status": "On review",
    "summary": "<FULL_UPDATED_DOCUMENT_MARKDOWN_CONTENT_HERE>",
    "text_accuracy": "100%",
    "feedback": "Deskripsi singkat perubahan yang diterapkan.",
    "suggested_categories": []
}}

CRITICAL REQUIREMENT FOR THE "summary" FIELD:
- The "summary" field MUST contain the ACTUAL, FULL Markdown text of the updated document, including all headings (#, ##), bullet points, and all requested additions, edits, or removals.
- Do NOT output placeholder text like "The updated document in clean Markdown with requested changes applied" or "<FULL_UPDATED_DOCUMENT_MARKDOWN_CONTENT_HERE>". You must output the real text!
"""
        
        llm_res = await asyncio.to_thread(llm.generate, refine_prompt)
        updated_data = safe_json_loads(llm_res)
        candidate_summary = updated_data.get("summary", "")
        if not candidate_summary or any(p in candidate_summary.lower() for p in ["the updated document in clean markdown", "full_updated_document_markdown"]):
            logger.warning("LLM returned placeholder summary during pending refine. Using staged summary as base.")
            updated_data["summary"] = staged_data.get("summary", "")

        k_id = staged_data.get("knowledge_id", knowledge_id)
        updated_data["knowledge_id"] = k_id
        
        # Preserve core physical document properties from initial staging
        for prop in ["file_name", "file_hash", "batch_id", "title", "document_type", "valid_from", "valid_until", "image_url", "s3_key", "storage_key", "batch_summary", "initial_prompt", "visibility_settings"]:
            if prop in staged_data and staged_data.get(prop) is not None:
                if prop not in updated_data or updated_data.get(prop) is None:
                    updated_data[prop] = staged_data.get(prop)

        # Remove legacy type if present
        updated_data.pop("type", None)

        # Apply deterministic refinements for SKU, Price, Replacements, and Deletions
        cur_summary = updated_data.get("summary") or staged_data.get("summary", "")
        cur_title = updated_data.get("title") or staged_data.get("title") or staged_data.get("file_name", k_id)
        
        refined_summary, _, refined_title, refined_sku, refined_feedback = apply_refinements_to_content(
            user_prompt=request.prompt,
            summary=cur_summary,
            chunks=[],
            title=cur_title,
            base_summary=staged_data.get("summary", "")
        )
        updated_data["summary"] = strip_callout_banners(refined_summary)
        if refined_title:
            updated_data["title"] = refined_title
        if refined_sku:
            updated_data["sku"] = refined_sku

        # Cross-document catalog deletion fallback if item not found in current pending document
        del_name, del_ingr, del_type = extract_product_deletion(request.prompt)
        if del_type in ("name", "ingredient") and refined_feedback and "tidak ditemukan pada dokumen ini" in refined_feedback:
            try:
                matched_cat = await GeneralKnowledgeService.find_all_target_documents_and_item(request.prompt)
                if matched_cat:
                    target_item_found, matched_docs = matched_cat
                    other_docs = [d for d in matched_docs if str(d.get("knowledge_id")).lower() != str(k_id).lower()]
                    if other_docs:
                        catalog_doc = other_docs[0]
                        cat_kid = catalog_doc["knowledge_id"]
                        cat_title = catalog_doc.get("title") or catalog_doc.get("file_name") or "Katalog Produk"
                        target_del_item = del_name if del_type == "name" else del_ingr
                        del_res = await GeneralKnowledgeService.apply_delete(
                            knowledge_id=cat_kid,
                            target_item=target_del_item,
                            delete_type=del_type
                        )
                        if del_res.get("success"):
                            del_prods = del_res.get("deleted_products", [])
                            prods_info = f" ({', '.join(del_prods)})" if del_prods else ""
                            refined_feedback = f"Produk \"{target_del_item}\"{prods_info} telah berhasil dihapus dari knowledge base."
            except Exception as cat_del_err:
                logger.debug(f"Catalog delete fallback note: {cat_del_err}")

        reply_message = refined_feedback or updated_data.get("feedback") or "Dokumen berhasil diperbarui."
        updated_data["reply"] = reply_message
        updated_data["feedback"] = reply_message

        # If products were deleted, filter active image_urls to only those still present in updated_summary
        if "> Berhasil menghapus" in updated_data.get("summary", ""):
            rem_imgs = [m.group(2).strip() for m in re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', updated_data.get("summary", "")) if m.group(2).strip() and not m.group(2).strip().startswith("http://example")]
            if rem_imgs:
                updated_data["image_urls"] = rem_imgs
                updated_data["image_url"] = rem_imgs[0]

        # Preserve all untouched product images from previous staged summary
        staged_prev_summary = staged_data.get("summary", "")
        if staged_prev_summary:
            updated_data["summary"] = preserve_existing_product_images(
                old_summary=staged_prev_summary,
                new_summary=updated_data.get("summary", ""),
                user_prompt=request.prompt
            )

        # Embed or Swap newly attached image assets if uploaded in this turn
        if "all_attached_images" in locals() and all_attached_images:
            for new_img in all_attached_images:
                if not new_img:
                    continue
                current_doc_summary = updated_data.get("summary", "")
                new_sum, old_url, t_name = apply_targeted_image_swap(
                    user_prompt=request.prompt,
                    summary=current_doc_summary,
                    new_image_url=new_img,
                    default_title=cur_title or "Foto Produk",
                    attachment_name=getattr(file, "filename", None) if "file" in locals() and file else None
                )
                updated_data["summary"] = new_sum
                t_label = f" untuk {t_name}" if t_name else ""
                action_word = "diganti" if old_url else "ditambahkan"
                img_conf = f"Gambar{t_label} berhasil {action_word} dengan file terlampir yang baru."
                formatted_img_reply = format_chat_response_with_cards(
                    confirmation=img_conf,
                    summary=new_sum,
                    target_product_names=[t_name] if t_name else None,
                    intro_label="Berikut adalah detail produk yang diperbarui:"
                )
                updated_data["feedback"] = formatted_img_reply
                reply_message = formatted_img_reply
                if old_url and old_url != new_img and old_url not in all_attached_images:
                    try:
                        from app.services.storage import delete_image_by_ref
                        delete_image_by_ref(old_url, knowledge_id=knowledge_id)
                        logger.info(f"🗑️ Purged old replaced image '{old_url}' from MinIO on pending refine swap.")
                    except Exception as del_old_err:
                        logger.debug(f"Failed deleting old swapped image: {del_old_err}")

        # Clean up any accidental "Asset Media" headers and duplicate image tags
        clean_sum = updated_data.get("summary", "")
        clean_sum = re.sub(r'(?:###?|\*\*)\s*(?:Asset Media dari File Terlampir|Asset Media|Media Assets|File Terlampir)[^\n]*[\s\S]*?(?=\n#{1,3}\s+|\n\*\*[^*]+\*\*|\Z)', '', clean_sum, flags=re.IGNORECASE)
        seen_img_urls = set()
        def _dedup_img_tag(m):
            u_t = m.group(2).strip()
            if u_t in seen_img_urls:
                return ""
            seen_img_urls.add(u_t)
            return m.group(0)
        clean_sum = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', _dedup_img_tag, clean_sum)
        clean_sum = re.sub(r'\n{3,}', '\n\n', clean_sum).strip()
        updated_data["summary"] = clean_sum

        # Dynamically synchronize image_urls from the updated summary (Single Source of Truth)
        # Any image of a deleted product/section will naturally not be in the summary and thus cleanly excluded.
        actual_summary = updated_data.get("summary", "")
        active_imgs = []
        for img_match in re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', actual_summary):
            u = img_match.group(2).strip()
            if u and u not in active_imgs:
                active_imgs.append(u)

        updated_data["image_urls"] = active_imgs
        updated_data["image_url"] = active_imgs[0] if active_imgs else None

        # Filter structured images metadata to only retain active images
        existing_imgs = staged_data.get("images") or []
        updated_images = []
        for img_obj in existing_imgs:
            if isinstance(img_obj, dict) and img_obj.get("url") in active_imgs:
                updated_images.append(img_obj)
        existing_urls = {img_obj.get("url") for img_obj in updated_images if isinstance(img_obj, dict)}
        for u in active_imgs:
            if u not in existing_urls:
                updated_images.append({
                    "id": f"img_{uuid.uuid4().hex[:8]}",
                    "url": u,
                    "s3_key": "",
                    "role": "PRODUCT_PACKAGING",
                    "product_name": cur_title,
                    "caption": cur_title
                })
        updated_data["images"] = updated_images

        # Robust Category validation against database
        raw_cats = updated_data.get("suggested_categories", staged_data.get("suggested_categories", []))
        raw_cats = resolve_matching_categories(raw_cats, db_categories, content_text=actual_summary)

        # Ensure reply_message contains confirmation + product cards ONLY if actual changes occurred
        # and it's not a negative/not-found result or conversational answer
        is_negative_reply = any(
            p in (reply_message or "").lower()
            for p in ["tidak ditemukan", "tidak ada", "gagal", "tidak berhasil", "tidak terdapat", "maaf", "mohon maaf"]
        )
        prev_summary = staged_data.get("summary", "").strip()
        curr_summary = updated_data.get("summary", "").strip()
        summary_modified = prev_summary != curr_summary

        if reply_message and summary_modified and not is_negative_reply and not ("### Detail Produk" in reply_message or "## Detail Produk" in reply_message):
            reply_message = format_chat_response_with_cards(
                confirmation=reply_message,
                summary=updated_data.get("summary", ""),
                intro_label="Berikut adalah daftar produk yang diperbarui:"
            )
        updated_data["reply"] = reply_message
        updated_data["feedback"] = reply_message

        # Build updated multi-turn conversation history
        existing_hist = staged_data.get("history", [])
        if not isinstance(existing_hist, list):
            existing_hist = []
        new_hist = list(existing_hist)
        new_hist.append({"role": "user", "content": request.prompt})
        new_hist.append({"role": "assistant", "content": reply_message})
        updated_data["history"] = new_hist

        vis_settings = updated_data.get("visibility_settings") or staged_data.get("visibility_settings", {})
        doc_img_url = active_imgs[0] if active_imgs else (updated_data.get("image_url") or staged_data.get("image_url"))
        doc_file_hash = updated_data.get("file_hash") or staged_data.get("file_hash")
        doc_batch_id = updated_data.get("batch_id") or staged_data.get("batch_id")
        doc_file_name = updated_data.get("file_name") or staged_data.get("file_name", k_id)
        doc_title = updated_data.get("title") or staged_data.get("title") or doc_file_name
        doc_type = updated_data.get("document_type") or staged_data.get("document_type")
        doc_valid_from = updated_data.get("valid_from") or staged_data.get("valid_from")
        doc_valid_until = updated_data.get("valid_until") or staged_data.get("valid_until")

        # ─── RE-CHUNK from updated summary (same pipeline as Approve) ─────────────
        cat_names = []
        for c in raw_cats:
            if isinstance(c, dict) and "name" in c:
                cat_names.append(c["name"])
            elif isinstance(c, str):
                cat_names.append(c)

        final_summary = updated_data.get("summary", "")
        updated_chunks = []
        if final_summary and final_summary.strip():
            try:
                from app.rag.utils.summary_chunker import chunk_summary_markdown
                updated_chunks = chunk_summary_markdown(
                    summary=final_summary,
                    source_file=doc_file_name,
                    knowledge_id=k_id,
                    batch_id=doc_batch_id,
                    file_hash=doc_file_hash or "",
                    title=doc_title,
                    doc_type=doc_type or "GENERAL",
                    categories=cat_names,
                    valid_from=str(doc_valid_from).strip() if doc_valid_from else None,
                    valid_until=str(doc_valid_until).strip() if doc_valid_until else None,
                    visibility_settings=vis_settings if isinstance(vis_settings, dict) else {},
                    default_image_url=doc_img_url,
                )
                logger.info(f"Refine Pending: re-chunked summary into {len(updated_chunks)} chunks.")
            except Exception as rechunk_err:
                logger.warning(f"Refine Pending: re-chunking failed, using LLM chunks: {rechunk_err}")
                updated_chunks = updated_data.get("chunks", staged_data.get("chunks", []))
                for chunk in updated_chunks:
                    if isinstance(chunk, dict):
                        if "metadata" not in chunk:
                            chunk["metadata"] = {}
                        chunk["metadata"]["knowledge_id"] = k_id
        
        # Save the updated data back in exact requested schema order
        final_updated_data = {
            "knowledge_id": k_id,
            "batch_id": doc_batch_id,
            "file_name": doc_file_name,
            "file_hash": doc_file_hash,
            "title": doc_title,
            "status": updated_data.get("status") or staged_data.get("status", "On review"),
            "document_type": doc_type,
            "valid_from": doc_valid_from,
            "valid_until": doc_valid_until,
            "summary": final_summary,
            "image_url": doc_img_url,
            "image_urls": active_imgs,
            "images": updated_images,
            "text_accuracy": updated_data.get("text_accuracy") or staged_data.get("text_accuracy", "100%"),
            "feedback": updated_data.get("feedback") or staged_data.get("feedback", ""),
            "batch_summary": updated_data.get("batch_summary") or staged_data.get("batch_summary"),
            "suggested_categories": raw_cats,
            "visibility_settings": vis_settings,
            "initial_prompt": updated_data.get("initial_prompt") or staged_data.get("initial_prompt"),
            "initial_summary": staged_data.get("initial_summary") or staged_data.get("summary"),
            "history": new_hist,
            "chunks": updated_chunks
        }
        if staged_data.get("timing_metrics"):
            final_updated_data["timing_metrics"] = staged_data.get("timing_metrics")

        # If part of a multi-file batch, re-synthesize updated batch executive summary
        batch_id_val = final_updated_data.get("batch_id")
        if batch_id_val and llm:
            try:
                b_summary = await synthesize_batch_executive_summary(batch_id_val, llm)
                if b_summary:
                    final_updated_data["batch_summary"] = b_summary
            except Exception as b_err:
                logger.warning(f"Could not update batch summary after refine: {b_err}")

        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(final_updated_data, f, indent=4, ensure_ascii=False)

        try:
            from app.services.storage import upload_staging_json
            upload_staging_json(k_id, final_updated_data)
        except Exception as st_err:
            logger.debug(f"MinIO staging upload note: {st_err}")

        # Sync refined pending document summary and metadata to PostgreSQL Knowledge record
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            from sqlalchemy import select
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                try:
                    k_uuid = _uuid.UUID(str(k_id))
                    stmt_k = select(Knowledge).where(Knowledge.id == k_uuid, Knowledge.deleted_at.is_(None))
                except ValueError:
                    stmt_k = select(Knowledge).where(Knowledge.file_name.ilike(f"%{doc_file_name}%"), Knowledge.deleted_at.is_(None))
                res_k = await session.execute(stmt_k)
                k_entry = res_k.scalars().first()
                if k_entry:
                    if doc_title:
                        k_entry.title = doc_title
                    k_entry.ai_summary = final_summary
                    k_entry.content = final_summary
                    if k_entry.metadata_ is None:
                        k_entry.metadata_ = {}
                    k_entry.metadata_.update({
                        "summary": final_summary,
                        "batch_id": doc_batch_id,
                        "chunks": updated_chunks,
                        "staging_history": new_hist,
                        "images": updated_images,
                        "image_urls": active_imgs,
                        "categories": cat_names,
                        "visibility_settings": vis_settings,
                    })
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(k_entry, "metadata_")
                    await session.commit()
                    logger.info(f"Updated Knowledge DB record for refined pending document '{k_id}'")
        except Exception as db_err:
            logger.warning(f"Could not sync refined pending summary to Knowledge DB for '{k_id}': {db_err}")

        return final_updated_data
    except Exception as e:
        logger.error(f"Refinement failed for document '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refine document: {e}")


@router.post("/ingest/pending/{knowledge_id}/reparse_vision", tags=["Ingestion"], summary="Reparse Pending Document with Vision", response_model=PendingDocumentResponse)
@router.post("/ingest/staging/{knowledge_id}/reparse_vision", tags=["Ingestion"], summary="Reparse Staging Document with Vision", response_model=PendingDocumentResponse)
async def reparse_pending_with_vision(
    knowledge_id: str = Path(..., description="Pending document identifier (UUID)"),
    request: Optional[ReparseVisionRequest] = None
):
    """
    Re-parses a pending document using Vision-Native VLM extraction.
    Useful when a document was initially parsed with plain text/heuristic mode
    but contains complex visual layouts, infographics, badges, or slide designs.
    """
    pending_file = resolve_pending_file(knowledge_id)
    if not pending_file:
        raise HTTPException(status_code=404, detail=f"Pending document '{knowledge_id}' not found.")

    try:
        with open(pending_file, "r", encoding="utf-8") as f:
            staged_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read staged document: {e}")

    file_name = staged_data.get("file_name", "")
    file_path = staged_data.get("file_path", "")

    # Resolve local file path
    resolved_path = None
    candidate_paths = [
        file_path,
        os.path.join("data", "uploads", file_name) if file_name else None,
        os.path.join("data", "temp", file_name) if file_name else None,
        os.path.join("data", "temp", "assembled", f"{knowledge_id}_{file_name}") if file_name else None,
    ]
    for cp in candidate_paths:
        if cp and os.path.exists(cp):
            resolved_path = cp
            break

    if not resolved_path:
        assembled_dir = os.path.join("data", "temp", "assembled")
        if os.path.exists(assembled_dir) and file_name:
            for fname in os.listdir(assembled_dir):
                if file_name in fname:
                    resolved_path = os.path.join(assembled_dir, fname)
                    break

    downloaded_copy = None
    if not resolved_path:
        # Local upload files are cleaned after ingestion; the durable original lives in MinIO.
        from app.services.storage import download_original_document
        resolved_path = downloaded_copy = download_original_document(
            knowledge_id, os.path.join("data", "temp", "assembled"), file_name
        )

    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(
            status_code=404,
            detail=f"Original document file for '{file_name}' could not be located on disk or in storage for re-parsing."
        )

    try:
        max_p = request.max_pages if (request and request.max_pages) else 1000
        from app.rag.utils.flattened_parser import FlattenedDesignParser
        flat_parser = FlattenedDesignParser()

        logger.info(f"[REPARSE-VISION] Beginning Vision-native re-parse of '{resolved_path}' (knowledge_id={knowledge_id})")
        # Minutes of rendering and vision calls: run off the event loop so chat requests (CIS doctors)
        # keep being served while an admin re-parses a document.
        parsed_pages = await asyncio.to_thread(
            flat_parser.parse_pdf,
            file_path=resolved_path,
            document_id=knowledge_id,
            max_pages=max_p
        )

        if not parsed_pages:
            raise HTTPException(status_code=500, detail="Vision re-parsing produced 0 pages.")

        if request and request.page_numbers:
            target_set = set(request.page_numbers)
            pages_to_assemble = [p for p in parsed_pages if p.get("page") in target_set]
            if not pages_to_assemble:
                pages_to_assemble = parsed_pages
        else:
            pages_to_assemble = parsed_pages

        page_mds = [p.get("text", "") for p in pages_to_assemble if p.get("text")]
        full_summary = "\n\n---\n\n".join(page_mds)

        all_imgs = []
        for p in pages_to_assemble:
            for u in p.get("image_urls", []):
                if u and u not in all_imgs:
                    all_imgs.append(u)

        from app.rag.utils.summary_chunker import chunk_summary_markdown
        updated_chunks = chunk_summary_markdown(
            summary=full_summary,
            source_file=file_name,
            categories=staged_data.get("categories", []),
            title=staged_data.get("title", file_name)
        )

        detected_domains = [p.get("domain") for p in pages_to_assemble if p.get("domain") and p.get("domain") != "general"]
        primary_domain = (detected_domains[0] if detected_domains else staged_data.get("clinical_domain", "GENERAL")).upper()
        any_discontinued = any(bool(p.get("is_discontinued")) for p in pages_to_assemble)

        staged_data["summary"] = full_summary
        staged_data["chunks"] = updated_chunks
        staged_data["image_urls"] = all_imgs
        staged_data["image_url"] = all_imgs[0] if all_imgs else None
        staged_data["clinical_domain"] = primary_domain
        staged_data["is_discontinued"] = any_discontinued
        staged_data["file_path"] = resolved_path

        hist = staged_data.get("history", [])
        if not isinstance(hist, list):
            hist = []
        hist.append({"role": "user", "content": "Re-parse with Vision"})
        feedback_msg = (
            f"Dokumen berhasil di-reparse dengan Vision LLM ({len(pages_to_assemble)} halaman diproses, "
            f"{len(updated_chunks)} chunks dibuat, domain={primary_domain}, discontinued={any_discontinued})."
        )
        hist.append({"role": "assistant", "content": feedback_msg})
        staged_data["history"] = hist
        staged_data["reply"] = feedback_msg
        staged_data["feedback"] = feedback_msg
        from app.rag.pipeline_versions import PARSER_VERSION
        staged_data["pipeline_versions"] = {**(staged_data.get("pipeline_versions") or {}), "parser": PARSER_VERSION}

        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(staged_data, f, indent=4, ensure_ascii=False)

        try:
            from app.services.storage import upload_staging_json
            upload_staging_json(knowledge_id, staged_data)
        except Exception as storage_err:
            logger.debug(f"[REPARSE-VISION] MinIO staging sync note: {storage_err}")

        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            from sqlalchemy import select
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                try:
                    k_uuid = _uuid.UUID(str(knowledge_id))
                    stmt = select(Knowledge).where(Knowledge.id == k_uuid, Knowledge.deleted_at.is_(None))
                except ValueError:
                    stmt = select(Knowledge).where(Knowledge.file_name.ilike(f"%{file_name}%"), Knowledge.deleted_at.is_(None))
                res = await session.execute(stmt)
                k_entry = res.scalars().first()
                if k_entry:
                    k_entry.ai_summary = full_summary
                    k_entry.content = full_summary
                    if k_entry.metadata_ is None:
                        k_entry.metadata_ = {}
                    k_entry.metadata_.update({
                        "summary": full_summary,
                        "chunks": updated_chunks,
                        "staging_history": hist,
                        "image_urls": all_imgs,
                        "clinical_domain": primary_domain,
                        "is_discontinued": any_discontinued,
                        "parsed_with_vision": True
                    })
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(k_entry, "metadata_")
                    await session.commit()
                    logger.info(f"[REPARSE-VISION] Updated Knowledge DB record for '{knowledge_id}'")
        except Exception as db_err:
            logger.warning(f"[REPARSE-VISION] Could not sync to Knowledge DB: {db_err}")

        return staged_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REPARSE-VISION] Failed to re-parse document '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to re-parse document with Vision: {e}")
    finally:
        # A copy fetched from storage only for this re-parse; the original stays in the bucket
        if downloaded_copy and os.path.exists(downloaded_copy):
            try:
                os.remove(downloaded_copy)
            except OSError:
                pass


@router.get("/ingest/documents", tags=["Ingestion"], summary="List All Documents", response_model=List[DocumentListItem])
async def list_all_documents():
    """
    Retrieves all knowledge base documents across Approved, On review, and Processing statuses.
    """
    pending_dir = "data/pending"
    approved_dir = "data/output"
    
    docs = []
    seen_ids = set()
    
    # 1. Scan pending (which are nested object schemas)
    if os.path.exists(pending_dir):
        for f in os.listdir(pending_dir):
            if f.endswith(".json"):
                file_path = os.path.join(pending_dir, f)
                try:
                    with open(file_path, "r", encoding="utf-8") as f_json:
                        data = json.load(f_json)
                    if isinstance(data, dict):
                        chunks = data.get("chunks", [])
                        first_chunk_meta = chunks[0].get("metadata", {}) if chunks and isinstance(chunks[0], dict) else {}
                        fallback_id = f.replace("_parsed.json", "").replace(".json", "")
                        k_id = str(data.get("knowledge_id", first_chunk_meta.get("knowledge_id", fallback_id)))

                        doc_type = data.get("type") or first_chunk_meta.get("type") or first_chunk_meta.get("document_type") or None
                        if doc_type:
                            doc_type = doc_type.capitalize()

                        docs.append(DocumentListItem(
                            knowledge_id=k_id,
                            batch_id=data.get("batch_id") or first_chunk_meta.get("batch_id"),
                            file_name=data.get("file_name", fallback_id),
                            product_name=first_chunk_meta.get("product_name"),
                            status=data.get("status", "On review"),
                            processed_at=first_chunk_meta.get("processed_at"),
                            chunks_count=len(chunks)
                        ))
                        seen_ids.add(k_id)
                except Exception as err:
                    logger.warning(f"Error parsing pending metadata for {f}: {err}")
                    
    # 2. Scan approved
    if os.path.exists(approved_dir):
        for f in os.listdir(approved_dir):
            if f.endswith(".json"):
                file_path = os.path.join(approved_dir, f)
                try:
                    with open(file_path, "r", encoding="utf-8") as f_json:
                        data = json.load(f_json)
                    
                    raw_id = f.replace("_parsed.json", "").replace(".json", "")
                    k_id = raw_id
                    file_name = raw_id
                    product_name = None
                    doc_type = None
                    processed_at = None
                    chunks = []
                    
                    if isinstance(data, dict):
                        k_id = str(data.get("knowledge_id", k_id))
                        file_name = data.get("file_name", file_name)
                        doc_type = data.get("type") or doc_type
                        chunks = data.get("chunks", [])
                        if chunks and isinstance(chunks[0], dict):
                            first_meta = chunks[0].get("metadata", {})
                            product_name = first_meta.get("product_name")
                            doc_type = data.get("type") or first_meta.get("type") or first_meta.get("document_type") or None
                            processed_at = first_meta.get("processed_at")
                    elif isinstance(data, list):
                        chunks = data
                        if chunks and isinstance(chunks[0], dict):
                            first_meta = chunks[0].get("metadata", {})
                            k_id = str(first_meta.get("knowledge_id", k_id))
                            file_name = first_meta.get("source_file", file_name)
                            product_name = first_meta.get("product_name")
                            doc_type = first_meta.get("type") or first_meta.get("document_type") or None
                            processed_at = first_meta.get("processed_at")
                            
                    if doc_type:
                        doc_type = doc_type.capitalize()

                    if k_id not in seen_ids:
                        batch_id_val = None
                        if isinstance(data, dict):
                            batch_id_val = data.get("batch_id")
                            if not batch_id_val and chunks and isinstance(chunks[0], dict):
                                batch_id_val = chunks[0].get("metadata", {}).get("batch_id")
                        elif isinstance(data, list) and chunks and isinstance(chunks[0], dict):
                            batch_id_val = chunks[0].get("metadata", {}).get("batch_id")

                        docs.append(DocumentListItem(
                            knowledge_id=k_id,
                            batch_id=batch_id_val,
                            file_name=file_name,
                            product_name=product_name,
                            status="Approved",
                            processed_at=processed_at,
                            chunks_count=len(chunks)
                        ))
                        seen_ids.add(k_id)
                except Exception as err:
                    logger.warning(f"Error parsing approved metadata for {f}: {err}")

    # 3. Fallback DB sync: Include records from PostgreSQL Knowledge table that aren't in JSON files yet
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.knowledge import Knowledge
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = select(Knowledge).where(Knowledge.deleted_at.is_(None)).order_by(Knowledge.created_at.desc())
            res = await session.execute(stmt)
            k_records = res.scalars().all()
            
            for k in k_records:
                str_id = str(k.id)
                if str_id not in seen_ids:
                    st_val = k.status.value if hasattr(k.status, "value") else str(k.status)
                    status_display = "Approved" if st_val.upper() == "APPROVED" else ("On review" if st_val.upper() in ("PENDING", "PROCESSING") else "On review")
                    
                    docs.append(DocumentListItem(
                        knowledge_id=str_id,
                        file_name=k.file_name or k.title or "Untitled Document",
                        product_name=k.title,
                        status=status_display,
                        processed_at=k.created_at.strftime("%Y-%m-%d %H:%M:%S") if k.created_at else None,
                        chunks_count=0
                    ))
                    seen_ids.add(str_id)
    except Exception as db_err:
        logger.warning(f"DB fallback query in list_all_documents failed: {db_err}")

    return docs


@router.get("/ingest/approved/{knowledge_id}", tags=["Ingestion"], summary="Get Approved Document Details", response_model=ApprovedDocumentResponse)
async def get_approved_document_details(knowledge_id: str = Path(..., description="Approved document identifier (UUID)")):
    """
    Retrieves full summary, metadata, and text chunks of an approved document.
    """
    approved_file = resolve_approved_file(knowledge_id)
    if not approved_file:
        raise HTTPException(
            status_code=404, 
            detail=f"Document '{knowledge_id}' is not approved yet (currently in 'On review' status). Use GET /api/ai/ingest/pending/{knowledge_id} instead."
        )
        
    try:
        with open(approved_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        summary = ""
        categories = []
        chunks = []
        file_name = knowledge_id
        title = knowledge_id

        if isinstance(data, dict):
            summary = data.get("summary", "")
            categories = data.get("categories", [])
            chunks = data.get("chunks", [])
            file_name = data.get("file_name", knowledge_id)
            title = data.get("title", file_name)
        elif isinstance(data, list):
            chunks = data
            if chunks and isinstance(chunks[0], dict):
                first_meta = chunks[0].get("metadata", {})
                file_name = first_meta.get("source_file", knowledge_id)
                title = first_meta.get("title", file_name)
                summary = first_meta.get("summary", "")
                cat = first_meta.get("document_type")
        parsed_categories = []
        for c in categories:
            if isinstance(c, dict) and "name" in c:
                parsed_categories.append(c["name"])
            elif isinstance(c, str):
                parsed_categories.append(c)

        vis_settings = (data.get("visibility_settings") if isinstance(data, dict) else None) or {
            "clinics": ["all"],
            "doctor_types": ["all"],
            "doctors": ["all"]
        }

        return ApprovedDocumentResponse(
            knowledge_id=knowledge_id,
            batch_id=data.get("batch_id") if isinstance(data, dict) else None,
            file_name=file_name,
            file_hash=data.get("file_hash") if isinstance(data, dict) else None,
            title=title,
            status="Approved",
            document_type=data.get("document_type") if isinstance(data, dict) else None,
            valid_from=data.get("valid_from") if isinstance(data, dict) else None,
            valid_until=data.get("valid_until") if isinstance(data, dict) else None,
            summary=summary,
            image_url=data.get("image_url") if isinstance(data, dict) else None,
            batch_summary=data.get("batch_summary") if isinstance(data, dict) else None,
            categories=parsed_categories,
            visibility_settings=vis_settings,
            chunks=chunks
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read approved document '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read approved document: {e}")


@router.put("/ingest/approved/{knowledge_id}", tags=["Ingestion"], summary="Edit Approved Document")
async def edit_approved_document(
    knowledge_id: str = Path(..., description="Approved document identifier"),
    request: EditApprovedDocumentRequest = ...,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    bm25: BM25Index = Depends(get_bm25_index),
    vector_store: BaseVectorStoreAdapter = Depends(get_vector_store)
):
    """
    Updates summary, categories, and metadata of an approved document and re-indexes vector embeddings.
    """
    approved_file = resolve_approved_file(knowledge_id)

    if not approved_file or not os.path.exists(approved_file):
        raise HTTPException(status_code=404, detail=f"Approved document '{knowledge_id}' not found.")

    try:
        with open(approved_file, "r", encoding="utf-8") as f:
            existing_doc = json.load(f)

        updated_summary = request.summary if request.summary is not None else existing_doc.get("summary", "")
        updated_categories = request.categories if (request.categories is not None and len(request.categories) > 0) else existing_doc.get("categories", [])
        updated_title = (request.title.strip() if (request.title and request.title.strip()) else None) or existing_doc.get("title") or existing_doc.get("file_name", knowledge_id)
        updated_doc_type = request.document_type if request.document_type is not None else existing_doc.get("document_type")
        updated_valid_from = request.valid_from if request.valid_from is not None else existing_doc.get("valid_from")
        updated_valid_until = request.valid_until if request.valid_until is not None else existing_doc.get("valid_until")
        updated_chunks = existing_doc.get("chunks", [])

        vis_settings = request.visibility_settings.model_dump() if request.visibility_settings else existing_doc.get("visibility_settings", {
            "clinics": ["all"],
            "doctor_types": ["all"],
            "doctors": ["all"]
        })

        if request.chunks is not None and len(request.chunks) > 0:
            updated_chunks = request.chunks
        elif updated_summary and updated_summary.strip():
            try:
                from app.rag.utils.summary_chunker import chunk_summary_markdown
                updated_chunks = chunk_summary_markdown(
                    summary=updated_summary,
                    source_file=existing_doc.get("file_name", updated_title),
                    knowledge_id=knowledge_id,
                    batch_id=existing_doc.get("batch_id"),
                    file_hash=existing_doc.get("file_hash", ""),
                    title=updated_title,
                    doc_type=updated_doc_type or "GENERAL",
                    categories=updated_categories,
                    visibility_settings=vis_settings,
                )
            except Exception as rechunk_err:
                logger.warning(f"Update approved re-chunking failed: {rechunk_err}")

        # Cascade document-level title, visibility settings, and categories to all chunk metadata
        if isinstance(updated_chunks, list):
            for ch in updated_chunks:
                if isinstance(ch, dict):
                    if "metadata" not in ch or not isinstance(ch["metadata"], dict):
                        ch["metadata"] = {}
                    ch["metadata"]["title"] = updated_title
                    ch["metadata"]["clinics"] = vis_settings.get("clinics", ["all"])
                    ch["metadata"]["doctor_types"] = vis_settings.get("doctor_types", ["all"])
                    ch["metadata"]["doctors"] = vis_settings.get("doctors", ["all"])
                    ch["metadata"]["visibility_settings"] = vis_settings
                    ch["metadata"]["categories"] = updated_categories
                    ch["metadata"]["category"] = updated_categories[0] if updated_categories else ""

        pending_doc_structure = {
            "knowledge_id": knowledge_id,
            "batch_id": existing_doc.get("batch_id") if isinstance(existing_doc, dict) else None,
            "file_name": existing_doc.get("file_name", ""),
            "file_hash": existing_doc.get("file_hash") if isinstance(existing_doc, dict) else None,
            "title": updated_title,
            "status": "On review",
            "document_type": updated_doc_type,
            "valid_from": updated_valid_from,
            "valid_until": updated_valid_until,
            "summary": updated_summary,
            "image_url": existing_doc.get("image_url") if isinstance(existing_doc, dict) else None,
            "image_urls": existing_doc.get("image_urls", []) if isinstance(existing_doc, dict) else [],
            "initial_prompt": existing_doc.get("initial_prompt") if isinstance(existing_doc, dict) else None,
            "staging_history": existing_doc.get("staging_history", []) if isinstance(existing_doc, dict) else [],
            "edit_history": existing_doc.get("edit_history", []) if isinstance(existing_doc, dict) else [],
            "timing_metrics": existing_doc.get("timing_metrics") if isinstance(existing_doc, dict) else None,
            "batch_summary": existing_doc.get("batch_summary") if isinstance(existing_doc, dict) else None,
            "categories": updated_categories,
            "suggested_categories": updated_categories,
            "visibility_settings": vis_settings,
            "chunks": updated_chunks,
            "is_revision": True
        }

        # Save pending draft revision to data/pending/{knowledge_id}.json without overwriting active approved document
        os.makedirs("data/pending", exist_ok=True)
        pending_file = os.path.join("data/pending", f"{knowledge_id}.json")
        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(pending_doc_structure, f, indent=4, ensure_ascii=False)

        try:
            from app.services.storage import upload_staging_json
            upload_staging_json(knowledge_id, pending_doc_structure)
        except Exception as st_err:
            logger.debug(f"MinIO staging upload note: {st_err}")

        logger.info(f"📝 Staged edit revision for approved document '{knowledge_id}' to pending queue (status: 'On review'). Active approved document remains searchable until approved.")
        return pending_doc_structure
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Edit approved document failed for '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update approved document: {e}")



@router.put("/ingest/pending/{knowledge_id}", tags=["Ingestion"], summary="Edit Pending Document")
@router.put("/ingest/staging/{knowledge_id}", tags=["Ingestion"], summary="Edit Staging Document")
async def edit_pending_document(
    knowledge_id: str = Path(..., description="Pending document identifier (UUID)"),
    request: EditApprovedDocumentRequest = ...
):
    """
    Updates summary, categories, and metadata of a pending staged document.
    """
    pending_file = resolve_pending_file(knowledge_id)

    if not pending_file or not os.path.exists(pending_file):
        raise HTTPException(status_code=404, detail=f"Pending document '{knowledge_id}' not found.")

    try:
        with open(pending_file, "r", encoding="utf-8") as f:
            existing_doc = json.load(f)

        updated_summary = request.summary if request.summary is not None else existing_doc.get("summary", "")
        updated_categories = request.categories if (request.categories is not None and len(request.categories) > 0) else existing_doc.get("suggested_categories", [])
        updated_title = request.title if request.title is not None else existing_doc.get("file_name", existing_doc.get("title", knowledge_id))
        updated_doc_type = request.document_type if request.document_type is not None else existing_doc.get("document_type")
        updated_valid_from = request.valid_from if request.valid_from is not None else existing_doc.get("valid_from")
        updated_valid_until = request.valid_until if request.valid_until is not None else existing_doc.get("valid_until")

        # Normalize suggested_categories to list of dicts for pending json
        normalized_categories = []
        if updated_categories:
            if isinstance(updated_categories[0], str):
                normalized_categories = [{"name": c} for c in updated_categories]
            else:
                normalized_categories = updated_categories
                
        existing_doc["summary"] = updated_summary
        existing_doc["title"] = updated_title
        if updated_doc_type is not None:
            existing_doc["document_type"] = updated_doc_type
        if updated_valid_from is not None:
            existing_doc["valid_from"] = updated_valid_from
        if updated_valid_until is not None:
            existing_doc["valid_until"] = updated_valid_until

        if updated_categories is not None and len(updated_categories) > 0:
            existing_doc["suggested_categories"] = normalized_categories
            
        vis_settings = request.visibility_settings.model_dump() if request.visibility_settings else existing_doc.get("visibility_settings", {
            "clinics": ["all"],
            "doctor_types": ["all"],
            "doctors": ["all"]
        })
        existing_doc["visibility_settings"] = vis_settings

        str_categories = [c["name"] if isinstance(c, dict) else c for c in normalized_categories]
        if request.chunks is not None and len(request.chunks) > 0:
            existing_doc["chunks"] = request.chunks
        elif updated_summary and updated_summary.strip():
            try:
                from app.rag.utils.summary_chunker import chunk_summary_markdown
                updated_chunks = chunk_summary_markdown(
                    summary=updated_summary,
                    source_file=existing_doc.get("file_name", updated_title),
                    knowledge_id=knowledge_id,
                    batch_id=existing_doc.get("batch_id"),
                    file_hash=existing_doc.get("file_hash", ""),
                    title=updated_title,
                    doc_type=updated_doc_type or "GENERAL",
                    categories=str_categories,
                    visibility_settings=vis_settings,
                )
                existing_doc["chunks"] = updated_chunks
            except Exception as rechunk_err:
                logger.warning(f"Update pending re-chunking failed: {rechunk_err}")

        # Cascade document-level title, visibility settings, and categories to all chunk metadata
        if isinstance(existing_doc.get("chunks"), list):
            for ch in existing_doc["chunks"]:
                if isinstance(ch, dict):
                    if "metadata" not in ch or not isinstance(ch["metadata"], dict):
                        ch["metadata"] = {}
                    ch["metadata"]["title"] = updated_title
                    ch["metadata"]["clinics"] = vis_settings.get("clinics", ["all"])
                    ch["metadata"]["doctor_types"] = vis_settings.get("doctor_types", ["all"])
                    ch["metadata"]["doctors"] = vis_settings.get("doctors", ["all"])
                    ch["metadata"]["visibility_settings"] = vis_settings
                    ch["metadata"]["categories"] = str_categories
                    ch["metadata"]["category"] = str_categories[0] if str_categories else ""

        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(existing_doc, f, indent=4, ensure_ascii=False)

        try:
            from app.services.storage import upload_staging_json
            upload_staging_json(knowledge_id, existing_doc)
        except Exception as st_err:
            logger.debug(f"MinIO staging upload note: {st_err}")

        # Synchronize manual edits directly to PostgreSQL Knowledge entry
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            import uuid as _uuid
            async with AsyncSessionLocal() as session:
                custom_uuid = None
                try:
                    custom_uuid = _uuid.UUID(str(knowledge_id))
                except ValueError:
                    pass
                if custom_uuid:
                    k_obj = await session.get(Knowledge, custom_uuid)
                    if k_obj:
                        k_obj.ai_summary = updated_summary
                        k_obj.content = updated_summary
                        k_obj.title = updated_title
                        meta = dict(k_obj.metadata_) if isinstance(k_obj.metadata_, dict) else {}
                        meta["summary"] = updated_summary
                        meta["title"] = updated_title
                        meta["suggested_categories"] = normalized_categories
                        meta["visibility_settings"] = vis_settings
                        meta["is_manually_edited"] = True
                        if "chunks" in existing_doc:
                            meta["chunks"] = existing_doc["chunks"]
                        k_obj.metadata_ = meta
                        await session.commit()
                        logger.info(f"💾 Synced pending manual edit for '{knowledge_id}' directly to PostgreSQL.")
        except Exception as db_sync_err:
            logger.debug(f"DB sync in edit_pending_document note: {db_sync_err}")

        return existing_doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Edit pending document failed for '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update pending document: {e}")


@router.post("/ingest/approved/{knowledge_id}/refine", tags=["Ingestion"], summary="Refine Approved Document")
async def refine_approved_document(
    knowledge_id: str = Path(..., description="Approved document identifier (UUID)"),
    request: str = Form(..., description="Prompt instructions to refine summary"),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    bm25: BM25Index = Depends(get_bm25_index),
    vector_store: BaseVectorStoreAdapter = Depends(get_vector_store),
    llm: BaseLLMAdapter = Depends(get_llm),
    file_attachment: Optional[UploadFile] = File(None, description="Optional supporting file attachment")
):
    """
    Refines an approved document summary using AI prompt instructions and updates RAG index.
    """
    # Parse request: accept plain text prompt, JSON {"prompt":"...","history":[...]}, or RefineRequest object
    if isinstance(request, str):
        try:
            parsed = json.loads(request)
            if isinstance(parsed, dict) and "prompt" in parsed:
                request = RefineRequest.model_validate(parsed)
            else:
                request = RefineRequest(prompt=request, history=[])
        except (json.JSONDecodeError, ValueError):
            request = RefineRequest(prompt=request, history=[])

    approved_file = resolve_approved_file(knowledge_id)
    if not approved_file:
        raise HTTPException(status_code=404, detail=f"Approved document '{knowledge_id}' not found.")

    if not llm:
        raise HTTPException(status_code=500, detail="LLM adapter is not configured.")

    try:
        with open(approved_file, "r", encoding="utf-8") as f:
            existing_doc = json.load(f)

        # Incorporate current_summary if user provided manual edits from frontend
        req_curr_summary = getattr(request, "current_summary", None)
        if req_curr_summary and str(req_curr_summary).strip():
            existing_doc["summary"] = str(req_curr_summary).strip()

        # 0. Parse attached file if provided
        attached_file_context = ""
        attached_file_name = ""
        all_attached_images = []

        prompt_str = getattr(request, "prompt", "") if hasattr(request, "prompt") else (request if isinstance(request, str) else "")
        for m in re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', prompt_str):
            img_u = m.group(2).strip()
            if img_u and img_u not in all_attached_images:
                all_attached_images.append(img_u)

        if file_attachment and hasattr(file_attachment, "read") and not ("[SUPPLEMENTARY ATTACHED FILE CONTENT:" in getattr(request, "prompt", "")):
            try:
                temp_dir = "data/temp"
                os.makedirs(temp_dir, exist_ok=True)
                attached_file_name = getattr(file_attachment, "filename", "attached_refine_doc")
                temp_file_path = os.path.join(temp_dir, f"refine_approved_{knowledge_id}_{attached_file_name}")
                
                content_bytes = await file_attachment.read()
                with open(temp_file_path, "wb") as f:
                    f.write(content_bytes)
                
                from app.rag.utils.parser import DocumentParser
                parser = DocumentParser()
                parse_res = parser.parse_file(temp_file_path)
                
                extracted_text = ""
                if parse_res and parse_res.pages:
                    extracted_pages = [p.get("text", "") for p in parse_res.pages if p.get("text")]
                    extracted_text = "\n\n".join(extracted_pages)
                    # Collect all embedded / standalone image URLs across all pages/slides/sheets
                    for p in parse_res.pages:
                        if p.get("image_urls") and isinstance(p["image_urls"], list):
                            for u in p["image_urls"]:
                                if u and u not in all_attached_images:
                                    all_attached_images.append(u)
                        if p.get("image_url") and p["image_url"] not in all_attached_images:
                            all_attached_images.append(p["image_url"])
                elif parse_res and parse_res.docling_doc:
                    try:
                        extracted_text = parse_res.docling_doc.export_to_markdown()
                    except Exception as exp_err:
                        logger.warning(f"Docling export to markdown failed: {exp_err}")
                        extracted_text = ""

                # Sync all attached images to existing_doc
                if all_attached_images:
                    if "image_urls" not in existing_doc or not isinstance(existing_doc["image_urls"], list):
                        existing_doc["image_urls"] = []
                    for u in all_attached_images:
                        if u not in existing_doc["image_urls"]:
                            existing_doc["image_urls"].append(u)
                    if not existing_doc.get("image_url") and all_attached_images:
                        existing_doc["image_url"] = all_attached_images[0]

                if extracted_text or all_attached_images:
                    content_snippet = extracted_text
                    if len(content_snippet) > 10000:
                        content_snippet = content_snippet[:10000] + "\n\n... [KONTEN FILE TERLAMPIR DIPOTONG KARENA PANJANG] ..."

                    media_note = ""
                    if all_attached_images:
                        media_lines = [f"- Attached Image {i+1}: {url}" for i, url in enumerate(all_attached_images)]
                        primary_img = all_attached_images[0]
                        media_note = (
                            f"\n\n[ATTACHED MEDIA ASSET URLS FOR THIS TURN:\n"
                            + "\n".join(media_lines)
                            + f"\nCRITICAL INSTRUCTION: If the admin adds a product or section, embed the exact URL '{primary_img}' inside that product's '### Detail Produk' block as ![Product Name]({primary_img}). "
                            f"If updating/replacing an image, swap the old image tag with ![Product Name]({primary_img}). DO NOT output placeholder text like 'URL_GAMBAR' or 'new_image'. "
                            f"NEVER create an 'Asset Media' heading or append raw media asset lists at the end of the summary.]\n"
                        )

                    attached_file_context = (
                        f"\n\n--- NEWLY ATTACHED SUPPLEMENTARY FILE: '{attached_file_name}' ---\n"
                        f"{content_snippet}{media_note}\n"
                        f"--- END OF ATTACHED FILE CONTENT ---\n"
                    )
                    logger.info(f"📄 Successfully parsed attached file '{attached_file_name}' ({len(extracted_text)} chars, {len(all_attached_images)} images) for approved refine (knowledge_id='{knowledge_id}').")
                
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            except Exception as att_err:
                logger.warning(f"Failed to parse attached file in approved refine: {att_err}")

        db_categories = []
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.category import Category
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Category).where(Category.deleted_at.is_(None)))
                cats = res.scalars().all()
                db_categories = [{"id": str(c.id), "name": c.name} for c in cats]
        except Exception as cat_err:
            logger.warning(f"Failed to fetch categories: {cat_err}")

        history_str = ""
        if request.history:
            recent_msgs = request.history[-6:] if len(request.history) > 6 else request.history
            for msg in recent_msgs:
                role = "User" if getattr(msg, "role", "") == "user" else "Assistant"
                content = getattr(msg, "content", "")
                history_str += f"{role}: {content}\n"
        else:
            history_str = "No previous refinement history.\n"

        # Check if user instruction is an explicit product retrieval query (e.g. Test 14)
        retrieval_target = extract_product_retrieval_query(getattr(request, "prompt", "") if hasattr(request, "prompt") else str(request))
        retrieved_card = extract_product_card_from_summary(existing_doc.get("summary", ""), retrieval_target) if retrieval_target else None
        if retrieved_card:
            logger.info(f"🔍 Handled product retrieval query for approved document '{retrieval_target}'.")
            existing_edit_hist = existing_doc.get("edit_history", []) if isinstance(existing_doc, dict) else []
            new_edit_hist = list(existing_edit_hist) if isinstance(existing_edit_hist, list) else []
            user_prompt_str = getattr(request, "prompt", "") if hasattr(request, "prompt") else str(request)
            new_edit_hist.append({"role": "user", "content": user_prompt_str, "created_at": datetime.now(timezone.utc).isoformat()})
            new_edit_hist.append({"role": "assistant", "content": retrieved_card, "created_at": datetime.now(timezone.utc).isoformat()})

            existing_doc["history"] = new_edit_hist
            existing_doc["edit_history"] = new_edit_hist
            existing_doc["reply"] = retrieved_card
            existing_doc["answer"] = retrieved_card
            existing_doc["is_retrieval"] = True
            existing_doc["feedback"] = f"Menampilkan detail produk {retrieval_target} beserta gambar."
            os.makedirs("data/pending", exist_ok=True)
            pending_file = os.path.join("data/pending", f"{knowledge_id}.json")
            with open(pending_file, "w", encoding="utf-8") as f:
                json.dump(existing_doc, f, indent=4, ensure_ascii=False)
            try:
                from app.services.storage import upload_staging_json
                upload_staging_json(knowledge_id, existing_doc)
            except Exception:
                pass
            return existing_doc

        # ─── COLLABORATIVE KNOWLEDGE BASE EDITOR PROMPT ─────────────────────────────
        refine_prompt = f"""
You are an intelligent, helpful knowledge base editor for PT Arya Noble (ERHA).
Your task is to refine, edit, format, or update the approved document content based on the Admin's instruction.

======================================================================
ADMIN INSTRUCTION:
"{request.prompt}"
======================================================================

Conversation History (for context only):
{history_str}

CURRENT APPROVED DOCUMENT CONTENT:
{json.dumps(existing_doc.get("summary", ""), ensure_ascii=False)}

{attached_file_context if attached_file_context else ""}

EDITING GUIDELINES:
1. **UNDERSTAND ADMIN BEHAVIOR & INTENT FLEXIBLY**:
   - Admins may write informally, briefly, or colloquially in Indonesian.
   - If admin asks to delete/remove a section or data (e.g. "hapus warnings", "hilangkan efek samping", "hapus tabel ini"), remove that section cleanly while keeping everything else intact.
   - If admin asks to change/update specific data (e.g. "ganti harga jadi 50.000", "ubah nama produk", "sku nya ganti ke ABC-123"), update that specific value accurately.
   - If admin asks to format or tidy up (e.g. "rapikan teks", "buat jadi bullet point", "perbaiki tabel"), re-format into clean, well-structured Markdown.
   - If admin attaches a supplementary file or adds new details (e.g. "tambahkan produk ini"), format the new product as a `### Detail Produk` block with its image and attributes.
2. **MODULAR PRODUCT CARDS & IMAGE PLACEMENT RULE**:
   - For multi-product catalogs or when adding/editing products:
     Format each product as a modular `### Detail Produk` block with its associated image and bullet attributes so the UI renders interactive Product Cards:
     ```markdown
     ### Detail Produk
     ![Nama Produk Lengkap](URL_GAMBAR)
     - **Nama Produk**: Nama Produk Lengkap
     - **Brand**: ERHA
     - **Kategori**: Kategori Produk (misal: Sabun Wajah Jerawat)
     - **Ukuran**: 100 g
     - **Harga**: Rp ... (jika ada)
     - **Kandungan Utama**: Bahan aktif utama (format sebagai bullet point, JANGAN buat heading ### terpisah!)
     - **Manfaat**: Manfaat produk (format sebagai bullet point, JANGAN buat heading ### terpisah!)
     - **Cocok Untuk**: Jenis kulit (format sebagai bullet point)
     - **Aturan Pakai**: Cara penggunaan (format sebagai bullet point)
     - **Deskripsi**: Penjelasan manfaat dan kegunaan produk.
     ```
   - CRITICAL: NEVER break product attributes into raw markdown headings like `### Ingredients` or `### Benefits`! Keep all product attributes as bullet points inside `### Detail Produk` blocks.
   - Intelligently embed each image into its most relevant section or product block.
   - NEVER create any "Asset Media dari File Terlampir" heading or list of raw media assets at the end of the summary. Embed the attached image URL ONLY where it belongs.
3. **DELETION OF SECTIONS & PRODUCTS RULE**:
   - If the admin instructs to delete or remove a specific product, treatment, or ingredient-based group of products (e.g. "hapus produk X", 'hapus seluruh produk yang mengandung "Betaine"', 'delete produk "Sakura FW New Version"'):
     * You MUST completely delete that product/section's headings, text, tables, AND all associated markdown image tags `![...](url)` belonging to that product/section.
     * Do NOT retain, move, or dump that deleted product's images under other remaining sections or titles.
     * Keep all other untouched products in their modular `### Detail Produk` blocks with all bullet attributes intact.
     * Return pure clean Markdown for the updated document summary. NEVER prepend any change summary headers or callout blocks into the summary text.
3b. **IMAGE DELETION ONLY RULE (CRITICAL)**:
   - If the admin instructs to delete or remove ONLY the image or photo of a product (e.g. "hapus gambar product Spot Gel New Version", "hilangkan foto produk X", "delete image for Y"):
     * You MUST ONLY delete the markdown image tag `![...](url)` of that specific target product.
     * You MUST KEEP that product's section, title, and all its bullet attributes (- **Nama Produk**, - **Kategori**, - **Deskripsi**, etc.) 100% INTACT!
     * NEVER delete the product itself when asked to delete only its image!
     * NEVER delete or touch the images of any other products in the document!
4. **STRICT CATEGORIES RULE**:
   - Update categories ONLY if the content changes topic and matches the "Available System Categories" list below.
   - NEVER invent or create new categories. NEVER output placeholder text like "category_name".
   - If NO category from the list genuinely matches this document, you MUST return an empty array: []!
5. **PRESERVE UNCHANGED CONTENT**: Keep all other sections, bullet points, and facts from the existing document that were not requested to be changed.
6. **CLEAN MARKDOWN**: Ensure the output is clean Markdown with headings (`#`, `##`), bullet points, tables, and blank lines before and after images.
7. **FEEDBACK**: Write 1-2 short, polite Indonesian sentences explaining what was changed (e.g. "Produk telah berhasil dihapus dari dokumen.").

Available System Categories from Database:
{json.dumps(db_categories, ensure_ascii=False)}

Return a valid JSON object ONLY (do NOT wrap in ```json blocks):
{{
    "summary": "<FULL_UPDATED_DOCUMENT_MARKDOWN_CONTENT_HERE>",
    "categories": []
}}

CRITICAL REQUIREMENT FOR THE "summary" FIELD:
- The "summary" field MUST contain the ACTUAL, FULL Markdown text of the updated document, including all headings (#, ##), bullet points, and all requested additions, edits, or removals.
- Do NOT output placeholder text like "The updated document in clean Markdown with requested changes applied" or "<FULL_UPDATED_DOCUMENT_MARKDOWN_CONTENT_HERE>". You must output the real text!
"""
        
        llm_res = await asyncio.to_thread(llm.generate, refine_prompt)
        parsed_refined = safe_json_loads(llm_res)
        candidate_summary = parsed_refined.get("summary", "")
        if not candidate_summary or any(p in candidate_summary.lower() for p in ["the updated document in clean markdown", "full_updated_document_markdown"]):
            logger.warning("LLM returned placeholder summary during approved refine. Using existing summary as base.")
            updated_summary = existing_doc.get("summary", "")
        else:
            updated_summary = candidate_summary

        # Strict validation of categories against database
        raw_ret_categories = parsed_refined.get("categories", existing_doc.get("categories", []))
        valid_cat_names = {str(c.get("name")).strip().lower(): str(c.get("name")).strip() for c in db_categories if isinstance(c, dict) and c.get("name")}
        clean_approved_cats = []
        if isinstance(raw_ret_categories, list):
            for c in raw_ret_categories:
                cname = str(c.get("name") if isinstance(c, dict) else c).strip().lower()
                if cname in ["category name", "category_name", "category_id", "uuid", "null", "none", ""]:
                    continue
                if cname in valid_cat_names:
                    clean_approved_cats.append(valid_cat_names[cname])
        updated_categories = clean_approved_cats if clean_approved_cats else existing_doc.get("categories", [])

        file_name = existing_doc.get("file_name", knowledge_id)
        doc_type = existing_doc.get("document_type") if isinstance(existing_doc, dict) else None
        doc_title = existing_doc.get("title", file_name) if isinstance(existing_doc, dict) else file_name
        doc_valid_from = existing_doc.get("valid_from") if isinstance(existing_doc, dict) else None
        doc_valid_until = existing_doc.get("valid_until") if isinstance(existing_doc, dict) else None

        # Apply deterministic refinements for SKU, Price, Replacements, and Deletions
        refined_summary, _, refined_title, refined_sku, refined_feedback = apply_refinements_to_content(
            user_prompt=request.prompt,
            summary=updated_summary,
            chunks=[],
            title=doc_title,
            base_summary=existing_doc.get("summary", "")
        )
        updated_summary = strip_callout_banners(refined_summary)
        if refined_title:
            doc_title = refined_title

        # Cross-document catalog deletion fallback if item not found in current approved document
        del_name, del_ingr, del_type = extract_product_deletion(request.prompt)
        if del_type in ("name", "ingredient") and refined_feedback and "tidak ditemukan pada dokumen ini" in refined_feedback:
            try:
                matched_cat = await GeneralKnowledgeService.find_all_target_documents_and_item(request.prompt)
                if matched_cat:
                    target_item_found, matched_docs = matched_cat
                    other_docs = [d for d in matched_docs if str(d.get("knowledge_id")).lower() != str(knowledge_id).lower()]
                    if other_docs:
                        catalog_doc = other_docs[0]
                        cat_kid = catalog_doc["knowledge_id"]
                        cat_title = catalog_doc.get("title") or catalog_doc.get("file_name") or "Katalog Produk"
                        target_del_item = del_name if del_type == "name" else del_ingr
                        del_res = await GeneralKnowledgeService.apply_delete(
                            knowledge_id=cat_kid,
                            target_item=target_del_item,
                            delete_type=del_type,
                            vector_store=vector_store,
                            bm25_index=bm25,
                            db=None
                        )
                        if del_res.get("success"):
                            del_prods = del_res.get("deleted_products", [])
                            prods_info = f" ({', '.join(del_prods)})" if del_prods else ""
                            refined_feedback = f"Produk \"{target_del_item}\"{prods_info} telah berhasil dihapus dari knowledge base."
                            logger.info(f"✅ Surgically deleted '{target_del_item}' from other catalog document '{cat_kid}' ({cat_title}).")
            except Exception as cat_del_err:
                logger.debug(f"Catalog delete fallback note: {cat_del_err}")

        reply_message = refined_feedback or "Dokumen berhasil diperbarui sesuai instruksi."

        # Check if user explicitly requested to delete an image
        delete_img_match = re.search(
            r'\b(?:hapus|delete|hilangkan|remove)\s+(?:gambar|foto|image|picture)(?:\s+(?:produk|item|dari)?\s*([^\n\r]+))?',
            request.prompt,
            re.IGNORECASE
        )
        if delete_img_match:
            del_target = delete_img_match.group(1).strip() if delete_img_match.group(1) else ""
            if del_target:
                img_tags = list(re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', updated_summary))
                from app.rag.utils.summary_chunker import common_words
                shared_label_words = common_words([t.group(1) for t in img_tags])
                target_words = [w for w in re.split(r'[\s\-_/]+', del_target) if len(w) > 2
                                and w.lower() not in shared_label_words and w.lower() not in ["produk", "product", "gambar", "foto", "image"]]
                for itag in img_tags:
                    alt = itag.group(1)
                    url = itag.group(2)
                    if any(tw.lower() in alt.lower() or tw.lower() in url.lower() for tw in target_words):
                        updated_summary = updated_summary.replace(itag.group(0), "")
                        try:
                            from app.services.storage import delete_image_by_ref
                            delete_image_by_ref(url, knowledge_id=knowledge_id)
                            logger.info(f"🗑️ Purged deleted image '{url}' from MinIO on admin request.")
                        except Exception as del_err:
                            logger.debug(f"Failed deleting requested image: {del_err}")
            updated_summary = re.sub(r'\n{3,}', '\n\n', updated_summary)

        # Preserve all untouched product images from previous existing summary
        existing_prev_summary = existing_doc.get("summary") or existing_doc.get("ai_summary", "")
        if existing_prev_summary:
            updated_summary = preserve_existing_product_images(
                old_summary=existing_prev_summary,
                new_summary=updated_summary,
                user_prompt=request.prompt
            )

        # Embed or Swap newly attached image assets if uploaded in this turn
        if "all_attached_images" in locals() and all_attached_images:
            for new_img in all_attached_images:
                if not new_img:
                    continue
                new_sum, old_url, t_name = apply_targeted_image_swap(
                    user_prompt=request.prompt,
                    summary=updated_summary,
                    new_image_url=new_img,
                    default_title=doc_title or "Foto Produk",
                    attachment_name=getattr(file_attachment, "filename", None) if "file_attachment" in locals() and file_attachment else None
                )
                updated_summary = new_sum
                t_label = f" untuk {t_name}" if t_name else ""
                action_word = "diganti" if old_url else "ditambahkan"
                img_conf = f"Gambar{t_label} berhasil {action_word} dengan file terlampir yang baru."
                formatted_img_reply = format_chat_response_with_cards(
                    confirmation=img_conf,
                    summary=new_sum,
                    target_product_names=[t_name] if t_name else None,
                    intro_label="Berikut adalah detail produk yang diperbarui:"
                )
                reply_message = formatted_img_reply
                if old_url and old_url != new_img and old_url not in all_attached_images:
                    try:
                        from app.services.storage import delete_image_by_ref
                        delete_image_by_ref(old_url, knowledge_id=knowledge_id)
                        logger.info(f"🗑️ Purged old replaced image '{old_url}' from MinIO on approved refine swap.")
                    except Exception as del_old_err:
                        logger.debug(f"Failed deleting old swapped image: {del_old_err}")

        # Clean up any accidental "Asset Media" headers and duplicate image tags
        updated_summary = re.sub(r'(?:###?|\*\*)\s*(?:Asset Media dari File Terlampir|Asset Media|Media Assets|File Terlampir)[^\n]*[\s\S]*?(?=\n#{1,3}\s+|\n\*\*[^*]+\*\*|\Z)', '', updated_summary, flags=re.IGNORECASE)
        seen_img_urls_appr = set()
        def _dedup_img_tag_appr(m):
            u_t = m.group(2).strip()
            if u_t in seen_img_urls_appr:
                return ""
            seen_img_urls_appr.add(u_t)
            return m.group(0)
        updated_summary = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', _dedup_img_tag_appr, updated_summary)
        updated_summary = strip_callout_banners(re.sub(r'\n{3,}', '\n\n', updated_summary).strip())

        # Dynamically synchronize image_urls from the updated summary (Single Source of Truth)
        # Any image of a deleted product/section or deleted image will naturally not be in the summary and thus cleanly excluded.
        active_imgs = []
        for img_match in re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', updated_summary):
            u = img_match.group(2).strip()
            if u and u not in active_imgs:
                active_imgs.append(u)

        # Filter structured images metadata to only retain active images
        existing_imgs = existing_doc.get("images") or []
        updated_images = []
        for img_obj in existing_imgs:
            if isinstance(img_obj, dict) and img_obj.get("url") in active_imgs:
                updated_images.append(img_obj)
        existing_urls = {img_obj.get("url") for img_obj in updated_images if isinstance(img_obj, dict)}
        for u in active_imgs:
            if u not in existing_urls:
                updated_images.append({
                    "id": f"img_{uuid.uuid4().hex[:8]}",
                    "url": u,
                    "s3_key": "",
                    "role": "PRODUCT_PACKAGING",
                    "product_name": doc_title,
                    "caption": doc_title
                })

        doc_img_url = active_imgs[0] if active_imgs else None

        # ─── RE-CHUNK from updated summary (same pipeline as Approve) ─────────────
        cat_names = [c for c in updated_categories if isinstance(c, str)]
        vis_settings = existing_doc.get("visibility_settings", {
            "clinics": ["all"],
            "doctor_types": ["all"],
            "doctors": ["all"]
        })
        updated_chunks = []
        if updated_summary and updated_summary.strip():
            try:
                from app.rag.utils.summary_chunker import chunk_summary_markdown
                updated_chunks = chunk_summary_markdown(
                    summary=updated_summary,
                    source_file=file_name,
                    knowledge_id=knowledge_id,
                    batch_id=existing_doc.get("batch_id"),
                    file_hash=existing_doc.get("file_hash", ""),
                    title=doc_title,
                    doc_type=doc_type or "GENERAL",
                    categories=cat_names,
                    valid_from=str(doc_valid_from).strip() if doc_valid_from else None,
                    valid_until=str(doc_valid_until).strip() if doc_valid_until else None,
                    visibility_settings=vis_settings,
                    default_image_url=doc_img_url,
                )
                logger.info(f"Refine Approved: re-chunked summary into {len(updated_chunks)} chunks.")
            except Exception as rechunk_err:
                logger.warning(f"Refine Approved: re-chunking failed, keeping existing chunks: {rechunk_err}")
                updated_chunks = existing_doc.get("chunks", [])
                for chunk in updated_chunks:
                    if isinstance(chunk, dict):
                        if "metadata" not in chunk:
                            chunk["metadata"] = {}
                        chunk["metadata"]["knowledge_id"] = knowledge_id

        existing_edit_hist = existing_doc.get("edit_history", []) if isinstance(existing_doc, dict) else []
        new_edit_hist = list(existing_edit_hist) if isinstance(existing_edit_hist, list) else []

        prompt_text = ""
        if hasattr(request, "prompt"):
            prompt_text = request.prompt
        elif isinstance(request, dict):
            prompt_text = request.get("prompt", "")
        elif isinstance(request, str):
            prompt_text = request

        if prompt_text:
            new_edit_hist.append({
                "role": "user",
                "content": prompt_text,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        is_negative_reply = any(
            p in (reply_message or "").lower()
            for p in ["tidak ditemukan", "tidak ada", "gagal", "tidak berhasil", "tidak terdapat", "maaf", "mohon maaf"]
        )
        prev_summary = (existing_doc.get("summary", "") if isinstance(existing_doc, dict) else "").strip()
        curr_summary = updated_summary.strip()
        summary_modified = prev_summary != curr_summary

        if reply_message and summary_modified and not is_negative_reply and not ("### Detail Produk" in reply_message or "## Detail Produk" in reply_message):
            reply_message = format_chat_response_with_cards(
                confirmation=reply_message,
                summary=updated_summary,
                intro_label="Berikut adalah daftar produk yang diperbarui:"
            )

        if reply_message:
            new_edit_hist.append({
                "role": "assistant",
                "content": reply_message,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

        approved_doc_structure = {
            "knowledge_id": knowledge_id,
            "batch_id": existing_doc.get("batch_id") if isinstance(existing_doc, dict) else None,
            "file_name": file_name,
            "file_hash": existing_doc.get("file_hash") if isinstance(existing_doc, dict) else None,
            "title": doc_title,
            "status": "Approved",
            "document_type": doc_type,
            "valid_from": doc_valid_from,
            "valid_until": doc_valid_until,
            "summary": updated_summary,
            "image_url": doc_img_url,
            "image_urls": active_imgs,
            "images": updated_images,
            "initial_prompt": existing_doc.get("initial_prompt") if isinstance(existing_doc, dict) else None,
            "staging_history": existing_doc.get("staging_history", []) if isinstance(existing_doc, dict) else [],
            "edit_history": new_edit_hist,
            "timing_metrics": existing_doc.get("timing_metrics") if isinstance(existing_doc, dict) else None,
            "batch_summary": existing_doc.get("batch_summary") if isinstance(existing_doc, dict) else None,
            "categories": cat_names,
            "suggested_categories": existing_doc.get("suggested_categories", []) if isinstance(existing_doc, dict) else [],
            "visibility_settings": vis_settings,
            "chunks": updated_chunks
        }

        # If part of a multi-file batch, re-synthesize updated batch executive summary
        batch_id_val = approved_doc_structure.get("batch_id")
        if batch_id_val and llm:
            try:
                b_summary = await synthesize_batch_executive_summary(batch_id_val, llm)
                if b_summary:
                    approved_doc_structure["batch_summary"] = b_summary
            except Exception as b_err:
                logger.warning(f"Could not update batch summary after refine approved: {b_err}")

        # Create Staging Draft Copy for this refinement session (Isolation Pattern)
        pending_file = os.path.join("data/pending", f"{knowledge_id}.json")
        os.makedirs("data/pending", exist_ok=True)

        pending_doc_structure = {
            "knowledge_id": knowledge_id,
            "batch_id": existing_doc.get("batch_id") if isinstance(existing_doc, dict) else None,
            "file_name": file_name,
            "file_hash": existing_doc.get("file_hash") if isinstance(existing_doc, dict) else None,
            "title": doc_title,
            "status": "On review",
            "document_type": doc_type,
            "valid_from": doc_valid_from,
            "valid_until": doc_valid_until,
            "summary": updated_summary,
            "image_url": doc_img_url,
            "image_urls": active_imgs,
            "images": updated_images,
            "initial_prompt": existing_doc.get("initial_prompt") if isinstance(existing_doc, dict) else None,
            "staging_history": existing_doc.get("staging_history", []) if isinstance(existing_doc, dict) else [],
            "history": new_edit_hist,
            "edit_history": new_edit_hist,
            "timing_metrics": existing_doc.get("timing_metrics") if isinstance(existing_doc, dict) else None,
            "batch_summary": approved_doc_structure.get("batch_summary"),
            "categories": cat_names,
            "suggested_categories": cat_names,
            "visibility_settings": vis_settings,
            "chunks": updated_chunks,
            "reply": reply_message,
            "feedback": reply_message
        }

        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(pending_doc_structure, f, indent=4, ensure_ascii=False)

        try:
            from app.services.storage import upload_staging_json
            upload_staging_json(knowledge_id, pending_doc_structure)
        except Exception as canon_err:
            logger.warning(f"Could not sync staging draft JSON to MinIO after refine: {canon_err}")

        logger.info(f"📌 [RefineApproved] Saved staging draft for knowledge_id '{knowledge_id}' (status: On review). PGVector re-indexing deferred until Admin clicks Save Knowledge.")

        return pending_doc_structure
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refine approved document failed for '{knowledge_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refine approved document: {e}")


@router.post("/ingest/approve/{knowledge_id}", tags=["Ingestion"], summary="Approve Document")
async def approve_document(
    knowledge_id: str = Path(..., description="Document ID(s) to approve (supports single ID, comma-separated list, batch/session ID, or 'all')"),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    bm25: BM25Index = Depends(get_bm25_index),
    background_tasks: BackgroundTasks = None,
    quality_probes: bool = True
):
    """
    Approves pending staged document(s) and indexes them into vector and BM25 search databases.
    quality_probes=False keeps the post-publish quality check to its token-free part (coverage and
    structure); automatic re-processing of the whole knowledge base uses it.
    Supports:
    - Single document ID (e.g. '3dc6c820-...')
    - Comma-separated list of document IDs (e.g. 'id1,id2')
    - Batch/Session ID (e.g. 'eda14712-...') -> expands to approve all documents in that session
    - 'all' -> discovers and approves all pending documents across local disk and MinIO
    """
    raw_parts = [k.strip() for k in knowledge_id.split(",") if k and k.strip() and k.strip().lower() != "string"]
    if not raw_parts:
        raise HTTPException(status_code=400, detail="At least one valid knowledge_id must be provided.")

    pending_dir = "data/pending"
    targets = []

    # 1. Handle "all" keyword
    if any(p.lower() == "all" for p in raw_parts):
        all_ids = set()
        # Scan local pending directory
        if os.path.exists(pending_dir):
            for f in os.listdir(pending_dir):
                if f.endswith(".json") and f != "bm25_index.pkl":
                    kid = f.replace("_parsed.json", "").replace(".json", "")
                    if kid:
                        all_ids.add(kid)
        # Scan MinIO staging bucket
        try:
            from app.services.storage import _get_client, _staging_bucket
            s3 = _get_client()
            if s3:
                res = s3.list_objects_v2(Bucket=_staging_bucket())
                for obj in res.get("Contents", []):
                    k = obj["Key"]
                    if k.endswith(".json"):
                        all_ids.add(k.replace(".json", ""))
        except Exception as s3_err:
            logger.debug(f"MinIO staging scan note: {s3_err}")
        # Scan PostgreSQL Knowledge table with status PENDING
        try:
            from app.core.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT id FROM knowledge WHERE status = 'PENDING' AND deleted_at IS NULL")).fetchall()
                for r in rows:
                    all_ids.add(str(r[0]))
        except Exception as db_err:
            logger.debug(f"DB pending scan note: {db_err}")

        targets = list(all_ids)
        if not targets:
            return {"status": "success", "message": "No pending documents to approve.", "approved_ids": []}
    else:
        # 2. Check each part: is it a direct knowledge_id or a batch_id?
        seen_targets = set()
        for p in raw_parts:
            batch_matched_kids = set()
            # Check if p is a batch_id in local data/pending
            if os.path.exists(pending_dir):
                for f in os.listdir(pending_dir):
                    if f.endswith(".json") and f != "bm25_index.pkl":
                        fp = os.path.join(pending_dir, f)
                        try:
                            with open(fp, "r", encoding="utf-8") as jf:
                                p_data = json.load(jf)
                            b_id = p_data.get("batch_id") or p_data.get("upload_batch_id")
                            if not b_id and p_data.get("chunks"):
                                b_id = p_data["chunks"][0].get("metadata", {}).get("batch_id") or p_data["chunks"][0].get("metadata", {}).get("upload_batch_id")
                            if b_id == p:
                                kid = p_data.get("knowledge_id") or f.replace("_parsed.json", "").replace(".json", "")
                                if kid:
                                    batch_matched_kids.add(kid)
                        except Exception:
                            pass

            # Check if p is a batch_id in MinIO staging
            try:
                from app.services.storage import _get_client, _staging_bucket
                s3 = _get_client()
                if s3:
                    res = s3.list_objects_v2(Bucket=_staging_bucket())
                    for obj in res.get("Contents", []):
                        k = obj["Key"]
                        if k.endswith(".json"):
                            try:
                                resp = s3.get_object(Bucket=_staging_bucket(), Key=k)
                                p_data = json.loads(resp["Body"].read().decode("utf-8"))
                                b_id = p_data.get("batch_id") or p_data.get("upload_batch_id")
                                if not b_id and p_data.get("chunks"):
                                    b_id = p_data["chunks"][0].get("metadata", {}).get("batch_id") or p_data["chunks"][0].get("metadata", {}).get("upload_batch_id")
                                if b_id == p:
                                    kid = p_data.get("knowledge_id") or k.replace(".json", "")
                                    if kid:
                                        batch_matched_kids.add(kid)
                            except Exception:
                                pass
            except Exception:
                pass

            # Check if p is a batch_id in PostgreSQL Knowledge table
            try:
                from app.core.database import engine
                from sqlalchemy import text
                with engine.connect() as conn:
                    rows = conn.execute(text(
                        "SELECT id FROM knowledge WHERE deleted_at IS NULL AND "
                        "(metadata ->> 'batch_id' = :b_id OR metadata ->> 'upload_batch_id' = :b_id)"
                    ), {"b_id": p}).fetchall()
                    for r in rows:
                        batch_matched_kids.add(str(r[0]))
            except Exception:
                pass

            if batch_matched_kids:
                for k in batch_matched_kids:
                    if k not in seen_targets:
                        seen_targets.add(k)
                        targets.append(k)
            else:
                if p not in seen_targets:
                    seen_targets.add(p)
                    targets.append(p)

    approved_results = []
    publish_failures = []
    all_chunks_to_index = []
    
    first_target_id = targets[0] if targets else "N/A"
    trace = ApprovalTrace(knowledge_id=first_target_id, batch_id=raw_parts[0] if len(raw_parts) == 1 and raw_parts[0] != first_target_id else None)
    trace.total_documents = len(targets)

    for target_id in targets:
        t0_load = time.time()
        pending_file = resolve_pending_file(target_id)
        data = None
        if pending_file and os.path.exists(pending_file):
            try:
                with open(pending_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        if not data:
            # Try MinIO staging hydration
            try:
                from app.services.storage import get_staging_json
                data = get_staging_json(target_id)
                if data:
                    pending_file = os.path.join("data/pending", f"{target_id}.json")
                    os.makedirs("data/pending", exist_ok=True)
                    with open(pending_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

        if not data:
            # Fallback: check if already approved on disk or in MinIO approved
            try:
                approved_file = resolve_approved_file(target_id)
                if approved_file and os.path.exists(approved_file):
                    with open(approved_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    from app.services.storage import get_approved_json
                    data = get_approved_json(target_id)
            except Exception:
                pass

        if not data:
            logger.warning(f"Pending/Approved document '{target_id}' not found for approval, skipping.")
            trace.log_stage("LOAD_STAGING", int((time.time() - t0_load) * 1000), status="FAILED", detail=f"Document {target_id} not found")
            continue

        trace.log_stage("LOAD_STAGING", int((time.time() - t0_load) * 1000), status="SUCCESS", count=1)

        try:
            t0_chunk = time.time()
            chunks = data.get("chunks", []) if isinstance(data, dict) else data
            k_id = data.get("knowledge_id", target_id) if isinstance(data, dict) else target_id
            file_name = data.get("file_name", target_id) if isinstance(data, dict) else target_id
            doc_title = data.get("title", file_name) if isinstance(data, dict) else file_name
            doc_type = data.get("document_type") if isinstance(data, dict) else None
            doc_valid_from = data.get("valid_from") if isinstance(data, dict) else None
            doc_valid_until = data.get("valid_until") if isinstance(data, dict) else None
            
            # Re-chunk from the LATEST summary (admin may have refined it). Tables are repaired here too, so
            # a summary edited by hand or produced before a table fix is published with intact tables.
            approve_summary = data.get("summary", "") if isinstance(data, dict) else ""
            if approve_summary:
                from app.rag.services.rag_generator import repair_markdown_tables
                from app.rag.utils.text_hygiene import drop_null_placeholders
                approve_summary = drop_null_placeholders(repair_markdown_tables(approve_summary))
                if isinstance(data, dict):
                    data["summary"] = approve_summary
            raw_cats = data.get("categories") or data.get("suggested_categories") or []
            parsed_cats = []
            if isinstance(raw_cats, list):
                for c in raw_cats:
                    if isinstance(c, dict) and "name" in c:
                        parsed_cats.append(c["name"])
                    elif isinstance(c, str):
                        parsed_cats.append(c)

            vis_settings = data.get("visibility_settings") or {
                "clinics": ["all"],
                "doctor_types": ["all"],
                "doctors": ["all"]
            }

            existing_chunks = data.get("chunks")
            from app.rag.pipeline_versions import CHUNKER_VERSION
            # Chunks made by the current chunker (an edit, an AI refine) are kept; parser page chunks and chunks
            # of an older chunker are re-made from the summary, so every published document is chunked alike
            current_chunks = bool(existing_chunks) and isinstance(existing_chunks, list) and chunker_version_of(existing_chunks) >= CHUNKER_VERSION
            chunks_remade = not (current_chunks or (existing_chunks and not (approve_summary and approve_summary.strip())))
            if not chunks_remade:
                chunks = existing_chunks
                logger.info(f"Approve: Preserving {len(chunks)} high-fidelity parser chunks with page-scoped metadata.")
            elif approve_summary and approve_summary.strip():
                try:
                    from app.rag.utils.summary_chunker import chunk_summary_markdown
                    doc_img_url = data.get("image_url") or (data.get("image_urls")[0] if (data.get("image_urls") and isinstance(data.get("image_urls"), list)) else None)
                    chunks = chunk_summary_markdown(
                        summary=approve_summary,
                        source_file=file_name,
                        knowledge_id=k_id,
                        batch_id=data.get("batch_id") if isinstance(data, dict) else None,
                        file_hash=data.get("file_hash", "") if isinstance(data, dict) else "",
                        title=doc_title,
                        doc_type=doc_type or "GENERAL",
                        categories=parsed_cats,
                        valid_from=str(doc_valid_from).strip() if doc_valid_from else None,
                        valid_until=str(doc_valid_until).strip() if doc_valid_until else None,
                        visibility_settings=vis_settings,
                        default_image_url=doc_img_url,
                    )
                except Exception as rechunk_err:
                    logger.warning(f"Approve: re-chunking failed, using existing chunks: {rechunk_err}")

            if isinstance(chunks, list):
                from app.rag.utils.text_hygiene import drop_null_placeholders
                for ch in chunks:
                    if isinstance(ch, dict):
                        if isinstance(ch.get("text"), str):
                            ch["text"] = drop_null_placeholders(ch["text"])
                        if "metadata" not in ch or not isinstance(ch["metadata"], dict):
                            ch["metadata"] = {}
                        ch["metadata"]["clinics"] = vis_settings.get("clinics", ["all"])
                        ch["metadata"]["doctor_types"] = vis_settings.get("doctor_types", ["all"])
                        ch["metadata"]["doctors"] = vis_settings.get("doctors", ["all"])
                        ch["metadata"]["visibility_settings"] = vis_settings
                        ch["metadata"]["categories"] = parsed_cats
                        ch["metadata"]["category"] = parsed_cats[0] if parsed_cats else ""

            trace.log_stage("CHUNK", int((time.time() - t0_chunk) * 1000), status="SUCCESS", count=len(chunks) if isinstance(chunks, list) else 0)

            # Pre-clear existing entries for this doc from vector store and BM25
            v_store = pipeline.vector_store if pipeline else None
            if not v_store:
                try:
                    from app.rag.services.vector_store import PGVectorAdapter
                    v_store = PGVectorAdapter()
                except Exception:
                    pass

            if v_store:
                try:
                    v_store.delete_document(k_id)
                    if file_name and file_name != k_id:
                        v_store.delete_document(file_name)
                except Exception as del_err:
                    logger.debug(f"Pre-approval vector deletion note: {del_err}")

            bm25_inst = bm25
            if not bm25_inst:
                try:
                    from app.rag.services.rag_retriever import BM25Index
                    bm25_inst = BM25Index()
                    if os.path.exists(settings.bm25_index_path):
                        bm25_inst.load(settings.bm25_index_path)
                except Exception:
                    pass

            if bm25_inst:
                try:
                    bm25_inst.remove_file_chunks(k_id)
                    if file_name and file_name != k_id:
                        bm25_inst.remove_file_chunks(file_name)
                except Exception as bm25_del_err:
                    logger.debug(f"Pre-approval BM25 deletion note: {bm25_del_err}")

            if chunks:
                all_chunks_to_index.extend(chunks)

            t0_minio = time.time()
            os.makedirs("data/output", exist_ok=True)
            approved_file = os.path.join("data/output", f"{k_id}.json")
            staging_hist = data.get("history", []) if isinstance(data, dict) else []
            initial_prompt_val = data.get("initial_prompt") if isinstance(data, dict) else None

            approved_doc_structure = {
                "knowledge_id": k_id,
                "batch_id": data.get("batch_id") if isinstance(data, dict) else None,
                "project_id": data.get("project_id") if isinstance(data, dict) else None,
                "file_name": file_name,
                "file_hash": data.get("file_hash") if isinstance(data, dict) else None,
                "title": doc_title,
                "status": "Approved",
                "document_type": doc_type,
                "summary": approve_summary,
                "image_urls": data.get("image_urls", []) if isinstance(data, dict) else [],
                "batch_summary": data.get("batch_summary") if isinstance(data, dict) else None,
                "initial_prompt": initial_prompt_val,
                "staging_history": staging_hist,
                "history": [],
                "edit_history": [],
                "categories": parsed_cats,
                "suggested_categories": raw_cats,
                "visibility_settings": vis_settings,
                "pipeline_versions": {**((data.get("pipeline_versions") if isinstance(data, dict) else None) or {}),
                                      "chunker": chunker_version_of(chunks)},
                "chunks": chunks
            }
            with open(approved_file, "w", encoding="utf-8") as f:
                json.dump(approved_doc_structure, f, indent=4, ensure_ascii=False)
                
            if pending_file and os.path.exists(pending_file):
                try:
                    os.remove(pending_file)
                except Exception:
                    pass

            # Promote staging to approved in MinIO and local disk
            try:
                from app.services.storage import promote_staging_to_approved
                promote_staging_to_approved(k_id, approved_doc_structure)
            except Exception as canon_err:
                logger.warning(f"Could not promote staging to approved in MinIO for '{k_id}': {canon_err}")

            trace.log_stage("MINIO", int((time.time() - t0_minio) * 1000), status="SUCCESS")

            t0_db = time.time()
            # Dual-sync update to Knowledge DB table
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.knowledge import Knowledge, KnowledgeStatus
                from sqlalchemy import select
                import uuid as _uuid
                async with AsyncSessionLocal() as session:
                    try:
                        k_uuid = _uuid.UUID(k_id)
                        stmt_k = select(Knowledge).where(Knowledge.id == k_uuid, Knowledge.deleted_at.is_(None))
                    except ValueError:
                        stmt_k = select(Knowledge).where(Knowledge.file_name.ilike(f"%{file_name}%"), Knowledge.deleted_at.is_(None))
                    res_k = await session.execute(stmt_k)
                    k_entry = res_k.scalars().first()
                    if k_entry:
                        k_entry.status = KnowledgeStatus.APPROVED
                        if isinstance(data, dict) and data.get("project_id"):
                            try:
                                k_entry.project_id = _uuid.UUID(str(data["project_id"]))
                            except Exception:
                                pass
                        if k_entry.metadata_ is None:
                            k_entry.metadata_ = {}
                        if isinstance(data, dict) and data.get("project_id"):
                            k_entry.metadata_["project_id"] = str(data["project_id"])
                        if staging_hist:
                            k_entry.metadata_["staging_history"] = staging_hist
                        k_entry.metadata_["history"] = []
                        k_entry.metadata_["chat_history"] = []
                        k_entry.metadata_["edit_history"] = []
                        k_entry.metadata_["categories"] = parsed_cats
                        k_entry.metadata_["chunks"] = chunks
                        if initial_prompt_val:
                            k_entry.metadata_["initial_prompt"] = initial_prompt_val
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(k_entry, "metadata_")
                        await session.commit()
            except Exception as db_err:
                logger.warning(f"Could not dual-sync approved status to Knowledge DB table for {k_id}: {db_err}")

            trace.log_stage("DB_COMMIT", int((time.time() - t0_db) * 1000), status="SUCCESS")
            approved_results.append(k_id)

            # Phase 1/2: Canonical Schema Atomic Publish
            try:
                from app.rag.services.canonical_ingest_service import CanonicalIngestService
                from sqlalchemy import text as _text
                can_service = CanonicalIngestService()
                def _latest_version():
                    with can_service.engine.connect() as _c_conn:
                        return _c_conn.execute(
                            _text("SELECT id, status FROM knowledge_version WHERE knowledge_id = :kid ORDER BY version_no DESC LIMIT 1;"),
                            {"kid": str(k_id)}
                        ).fetchone()

                def _wait_for_ingest(v_id):
                    # The draft's canonical ingest (embeddings) finishes in the background after the document
                    # already shows as ready for review; an approval arriving first waits for it instead of
                    # having the publish rejected by the readiness gate.
                    wait_deadline = time.time() + 300
                    while time.time() < wait_deadline:
                        with can_service.engine.connect() as _c_conn:
                            job_status = _c_conn.execute(
                                _text("SELECT ingestion_job_status FROM knowledge_version WHERE id = :v_id;"),
                                {"v_id": v_id}
                            ).scalar()
                        if job_status != "PENDING":
                            return
                        time.sleep(2)

                v_row = _latest_version()
                draft_is_stale = False
                if v_row and v_row[1] != "ACTIVE":
                    # A draft holds the content as it was parsed; when the admin edited the summary since,
                    # the draft no longer matches what is being approved.
                    await asyncio.to_thread(_wait_for_ingest, str(v_row[0]))
                    with can_service.engine.connect() as _c_conn:
                        draft_summary, draft_job = _c_conn.execute(
                            _text("SELECT summary_md, ingestion_job_status FROM knowledge_version WHERE id = :v_id;"),
                            {"v_id": str(v_row[0])}
                        ).fetchone()
                    # The draft no longer matches when the summary was edited or the chunks were re-made here.
                    # A draft whose own indexing failed or never finished cannot be published either: without
                    # this, the document would show as approved while the chatbot has none of its content.
                    draft_is_stale = (
                        chunks_remade
                        or draft_job != "COMPLETED"
                        or (bool(approve_summary) and summary_text_changed(draft_summary, approve_summary))
                    )
                    if draft_job != "COMPLETED":
                        logger.warning(f"[CANONICAL] Draft index of '{k_id}' is '{draft_job}' at approval; indexing the approved content again.")
                if (not v_row or v_row[1] == "ACTIVE" or draft_is_stale) and chunks:
                    # The content being approved (an edit or re-parse of an already published document, or a
                    # draft edited by hand) was never ingested into the canonical index the chatbot retrieves
                    # from: ingest it as a new version so the publish below makes it live.
                    await asyncio.to_thread(
                        _run_canonical_shadow_ingest_sync,
                        knowledge_id=str(k_id),
                        file_name=file_name,
                        file_hash=(data.get("file_hash") if isinstance(data, dict) else None) or f"approve:{k_id}:{int(time.time())}",
                        extracted_doc_type=doc_type or "GENERAL",
                        visibility_settings=vis_settings,
                        recommended_title=doc_title,
                        enriched_chunks=chunks,
                        summary=approve_summary
                    )
                    v_row = _latest_version()
                    logger.info(f"[CANONICAL] Ingested approved content of '{k_id}' as new version {v_row[0] if v_row else '?'}")
                if v_row:
                    ver_to_pub = str(v_row[0])
                    await asyncio.to_thread(_wait_for_ingest, ver_to_pub)
                    can_service.publish_version_atomic(
                        knowledge_id=str(k_id),
                        version_id=ver_to_pub
                    )
                    logger.info(f"✨ [CANONICAL ATOMIC PUBLISH] Version {ver_to_pub} is now ACTIVE in Canonical Knowledge Schema for doc {k_id}")
                    # Measure what the doctors now get from this document, generated questions included
                    from app.rag.services.ingest_quality import schedule_quality_check
                    schedule_quality_check(str(k_id), version_id=ver_to_pub, probes=quality_probes)
            except Exception as can_pub_err:
                # The chatbot keeps answering from the previously published version: report it.
                logger.warning(f"Canonical Publish note for {k_id}: {can_pub_err}")
                publish_failures.append({"knowledge_id": str(k_id), "reason": str(can_pub_err)})

        except Exception as e:
            logger.error(f"Approval failed for document '{target_id}': {e}")
            trace.fail("APPROVAL_STEP", str(e))

    # BATCH EMBEDDING & INDEXING: Decoupled to non-blocking background task
    # Canonical knowledge (kb_chunk) was already published synchronously above in <50ms.
    if all_chunks_to_index:
        trace.log_stage("CANONICAL_INDEX", 0, status="SUCCESS", count=len(all_chunks_to_index))
        
        def _sync_legacy_worker(chunks_list=all_chunks_to_index, pl=pipeline, b_inst=bm25):
            try:
                vs = pl.vector_store if pl else None
                if not vs:
                    try:
                        from app.rag.services.vector_store import PGVectorAdapter
                        vs = PGVectorAdapter()
                    except Exception as vs_e:
                        logger.error(f"Failed to instantiate PGVectorAdapter for background sync: {vs_e}")
                if vs:
                    try:
                        vs.insert_chunks(chunks_list)
                    except Exception as pg_e:
                        logger.error(f"PGVector background batch insertion failed: {pg_e}")

                b_obj = b_inst
                if not b_obj:
                    try:
                        from app.rag.services.rag_retriever import BM25Index
                        b_obj = BM25Index()
                        if os.path.exists(settings.bm25_index_path):
                            b_obj.load(settings.bm25_index_path)
                    except Exception as bm_e:
                        logger.error(f"Failed to load BM25Index for background sync: {bm_e}")
                if b_obj:
                    try:
                        b_obj.add_chunks(chunks_list)
                        os.makedirs(os.path.dirname(settings.bm25_index_path), exist_ok=True)
                        b_obj.save(settings.bm25_index_path)
                    except Exception as bms_e:
                        logger.error(f"BM25 background batch indexing failed: {bms_e}")
            except Exception as bg_e:
                logger.warning(f"Background legacy sync note: {bg_e}")

        # The older PGVector/BM25 stores are only kept up to date while they are still read as a fallback
        from app.rag.config import settings as _rag_settings
        if getattr(_rag_settings, "legacy_retrieval_fallback", False):
            if background_tasks is not None:
                background_tasks.add_task(_sync_legacy_worker)
            else:
                asyncio.create_task(asyncio.to_thread(_sync_legacy_worker))

    trace.complete(
        approved_count=len(approved_results),
        failed_count=len(targets) - len(approved_results),
        total_chunks=len(all_chunks_to_index),
        embedding_count=len(all_chunks_to_index),
        bm25_status="BACKGROUND_ASYNC",
        storage_status="SUCCESS"
    )

    if publish_failures:
        return {
            "status": "partial",
            "message": (
                f"Approved {len(approved_results)} document(s), but {len(publish_failures)} could not be published "
                "to the chatbot knowledge index; the chatbot still answers from the previous version."
            ),
            "approved_ids": approved_results,
            "publish_failures": publish_failures,
        }
    return {
        "status": "success",
        "message": f"Successfully approved {len(approved_results)} document(s).",
        "approved_ids": approved_results
    }


@router.delete("/ingest/documents/{knowledge_id}", tags=["Ingestion"], summary="Delete Document Endpoint")
async def delete_document_endpoint(
    knowledge_id: str = Path(..., description="Document ID(s) to delete (supports single ID, comma-separated list, or 'all')"),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    bm25: BM25Index = Depends(get_bm25_index),
    vector_store: BaseVectorStoreAdapter = Depends(get_vector_store)
):
    """
    Deletes document(s) from Knowledge Base and vector search index (supports single ID, comma-separated IDs, or 'all').
    """
    raw_targets = [k.strip() for k in knowledge_id.split(",") if k and k.strip() and k.strip().lower() != "string"]
    if not raw_targets:
        raise HTTPException(status_code=400, detail="At least one valid knowledge_id must be provided.")

    target_store = (pipeline.vector_store if pipeline and pipeline.vector_store else vector_store)
    deleted_ids = []

    # If user passes 'all', delegate to reset
    if any(t.lower() == "all" for t in raw_targets):
        await reset_database(vector_store=target_store, bm25=bm25)
        return {"status": "success", "message": "Successfully deleted all documents.", "deleted_ids": ["all"]}

    target_folders = [
        "data/pending", "backend/data/pending",
        "data/output", "backend/data/output",
        "data/temp", "backend/data/temp"
    ]
    total_images_deleted = 0

    for k_id in raw_targets:
        was_deleted = False

        # 1. Scan JSON files in pending and output by exact knowledge_id OR exact file_name
        for folder in target_folders:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if f.endswith(".json"):
                        f_path = os.path.join(folder, f)
                        try:
                            with open(f_path, "r", encoding="utf-8") as fp:
                                f_data = json.load(fp)
                            doc_id = str(f_data.get("knowledge_id", "")) if isinstance(f_data, dict) else ""
                            doc_name = str(f_data.get("file_name", "")) if isinstance(f_data, dict) else ""
                            f_no_ext = f.replace(".json", "").replace("_parsed", "")

                            if k_id in (doc_id, doc_name, f_no_ext, f):
                                # Purge associated images in MinIO 'images' bucket and documents
                                try:
                                    from app.services.storage import delete_knowledge_images_and_assets
                                    doc_bid = str(f_data.get("batch_id") or (f_data.get("metadata") or {}).get("batch_id") or "")
                                    img_res = delete_knowledge_images_and_assets(doc_id or k_id, doc_data=f_data)
                                    total_images_deleted += img_res.get("deleted_images_count", 0)
                                    logger.info(f"Purged {img_res.get('deleted_images_count', 0)} image(s) from MinIO for doc '{k_id}'")
                                except Exception as img_del_err:
                                    logger.warning(f"Error purging MinIO images for '{k_id}': {img_del_err}")

                                if os.path.exists(f_path):
                                    try:
                                        os.remove(f_path)
                                    except Exception as rm_e:
                                        logger.debug(f"Could not remove {f_path}: {rm_e}")
                                if target_store:
                                    try:
                                        target_store.delete_document(doc_id or f_no_ext)
                                    except Exception as ts_e:
                                        logger.debug(f"Vector store delete note: {ts_e}")
                                if bm25:
                                    try:
                                        bm25.remove_file_chunks(doc_id or f_no_ext)
                                        bm25.save(settings.bm25_index_path)
                                    except Exception as bm_e:
                                        logger.debug(f"BM25 remove note: {bm_e}")
                                was_deleted = True
                                logger.info(f"Deleted JSON file and vectors for '{k_id}' ({f_path})")
                        except Exception as file_err:
                            logger.warning(f"Error checking/deleting file {f}: {file_err}")

        # 2. Soft-delete in PostgreSQL Knowledge DB table (exact ID / exact filename match only)
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            from sqlalchemy import select, func, text
            import uuid as _uuid

            async with AsyncSessionLocal() as session:
                custom_uuid = None
                try:
                    custom_uuid = _uuid.UUID(k_id)
                except ValueError:
                    pass

                if custom_uuid:
                    stmt = select(Knowledge).where(
                        Knowledge.id == custom_uuid,
                        Knowledge.deleted_at.is_(None)
                    )
                else:
                    stmt = select(Knowledge).where(
                        Knowledge.file_name == k_id,
                        Knowledge.deleted_at.is_(None)
                    )

                res = await session.execute(stmt)
                db_docs = res.scalars().all()

                for d_doc in db_docs:
                    # Clean up MinIO images referenced in DB record
                    try:
                        from app.services.storage import delete_knowledge_images_and_assets
                        d_meta = d_doc.metadata_ if isinstance(d_doc.metadata_, dict) else {}
                        d_bid = str(d_meta.get("batch_id") or "").strip()
                        img_res = delete_knowledge_images_and_assets(
                            str(d_doc.id),
                            doc_data={"summary": d_doc.ai_summary, "metadata": d_meta, "batch_id": d_bid, "image_urls": d_meta.get("image_urls", [])}
                        )
                        total_images_deleted += img_res.get("deleted_images_count", 0)
                    except Exception as s3_db_err:
                        logger.debug(f"DB image purge note: {s3_db_err}")

                    d_doc.deleted_at = func.now()
                    await session.execute(text("""
                        UPDATE kb_chunk SET is_active = false
                        WHERE version_id IN (
                            SELECT id FROM knowledge_version WHERE knowledge_id = :kid
                        )
                    """), {"kid": d_doc.id})
                if db_docs:
                    await session.commit()
                    was_deleted = True
                    logger.info(f"Soft-deleted {len(db_docs)} record(s) and deactivated active chunks in PostgreSQL Knowledge DB for '{k_id}'")
        except Exception as db_err:
            logger.warning(f"Could not soft-delete Knowledge DB record for '{k_id}': {db_err}")

        # 3. Final MinIO purge attempt for target ID
        try:
            from app.services.storage import delete_knowledge_images_and_assets
            img_res = delete_knowledge_images_and_assets(k_id)
            total_images_deleted += img_res.get("deleted_images_count", 0)
            if img_res.get("deleted_images_count", 0) > 0:
                was_deleted = True
        except Exception:
            pass

        # 4. Ensure vector store and BM25 remove any lingering chunks for this ID
        if target_store:
            try:
                target_store.delete_document(k_id)
            except Exception:
                pass
        if bm25:
            try:
                bm25.remove_file_chunks(k_id)
                bm25.save(settings.bm25_index_path)
            except Exception:
                pass

        if was_deleted:
            deleted_ids.append(k_id)

    return {
        "status": "success",
        "message": f"Successfully deleted {len(deleted_ids)} document(s) and {total_images_deleted} associated MinIO image(s).",
        "deleted_ids": deleted_ids,
        "deleted_images_count": total_images_deleted
    }




async def run_chat_pipeline(
    query: str,
    file: Optional[UploadFile] = None,
    attachment_text: Optional[str] = None,
    doctor_name: Optional[str] = None,
    history: Optional[List[Any]] = None,
    user_context: Optional[UserContext] = None,
    knowledge_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    categories: Optional[List[str]] = None,
    top_k: int = 8,
    pipeline: GenerationPipeline = None
) -> ChatResponse:
    if not pipeline:
        raise HTTPException(status_code=500, detail="Generation pipeline is not initialized.")

    # 1. Extract text from uploaded file if present
    file_attachment_text = attachment_text
    if file and hasattr(file, "read"):
        try:
            from app.rag.services.attachment_parser import AttachmentParser
            parser = AttachmentParser()
            extracted_text, attach_meta = await parser.extract_from_upload(file)
            if extracted_text and not extracted_text.startswith("[Error") and not extracted_text.startswith("[Dokumen tidak"):
                file_name_str = getattr(file, "filename", "File Terlampir")
                file_attachment_text = f"[Dokumen Pasien Terlampir: {file_name_str}]\n{extracted_text.strip()}"
                logger.info(
                    f"📎 [ChatPipeline] Extracted {attach_meta.get('chars', 0)} chars "
                    f"from '{file_name_str}' via {attach_meta.get('method', '?')} "
                    f"in {attach_meta.get('extraction_ms', 0)}ms"
                )
        except Exception as e:
            logger.error(f"❌ [ChatPipeline] AttachmentParser failed: {e}")

    # 2. Build effective query with attachment text
    effective_query = query
    if file_attachment_text:
        effective_query = (
            f"{query}\n\n"
            f"--- DOKUMEN PASIEN TERLAMPIR ---\n"
            f"{file_attachment_text}"
        )

    # 3. Format history
    raw_history = []
    if history:
        for msg in history:
            if isinstance(msg, dict):
                r = msg.get("role", "")
                c = msg.get("content", "")
            else:
                r = getattr(msg, "role", "")
                c = getattr(msg, "content", "")
            if r and c:
                raw_history.append({"role": r, "content": c})

    # 4. Build metadata filter for RBAC & Scope
    filter_metadata = {}
    if categories:
        valid_cats = [c.strip() for c in categories if c and c.strip().lower() not in ("string", "")]
        if valid_cats:
            filter_metadata["categories"] = valid_cats

    if knowledge_id:
        filter_metadata["knowledge_id"] = str(knowledge_id)
    if batch_id:
        filter_metadata["batch_id"] = str(batch_id)

    if user_context:
        filter_metadata["clinics"] = user_context.branch_ids + ["all"]
        filter_metadata["doctor_types"] = [user_context.dr_type, "all"]
        filter_metadata["doctors"] = [user_context.user_id, "all"]
        if user_context.excluded_categories:
            filter_metadata["excluded_categories"] = user_context.excluded_categories

    parsed_filter = filter_metadata if filter_metadata else None

    # Doctor name for greeting
    doc_name = doctor_name
    if not doc_name and user_context and getattr(user_context, "doctor_name", None):
        doc_name = user_context.doctor_name

    # APPROVAL GATE: Chatbot verifies document exists in KB (approved, staged, or DB).
    # Check if query specifically mentions a document UUID
    import re as _re
    uuid_matches = _re.findall(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', str(effective_query))
    if uuid_matches:
        for requested_uuid in uuid_matches:
            target_f = resolve_approved_file(requested_uuid) or resolve_pending_file(requested_uuid)
            if not target_f:
                from app.core.database import get_sync_engine
                from sqlalchemy import text as _text
                has_doc = False
                try:
                    sync_eng = get_sync_engine()
                    with sync_eng.connect() as conn:
                        row = conn.execute(_text("SELECT id FROM knowledge WHERE id::text = :k_id"), {"k_id": requested_uuid}).fetchone()
                        if row:
                            has_doc = True
                except Exception:
                    pass
                if not has_doc:
                    logger.warning(f"🚫 [ChatPipeline] Document '{requested_uuid}' is not in approved KB.")
                    return ChatResponse(
                        query=query,
                        answer="Untuk saat ini informasi tersebut belum tersedia.",
                        context="",
                        results=[],
                        agent_used=False
                    )

    # If a specific knowledge_id is provided, verify it is accessible in approved, staged, or DB
    if knowledge_id:
        k_id_str = str(knowledge_id).strip()
        app_file = resolve_approved_file(k_id_str) or resolve_pending_file(k_id_str)
        if app_file:
            filter_metadata["knowledge_id"] = k_id_str
        else:
            from app.core.database import get_sync_engine
            from sqlalchemy import text as _text
            has_doc = False
            try:
                sync_eng = get_sync_engine()
                with sync_eng.connect() as conn:
                    row = conn.execute(_text("SELECT id FROM knowledge WHERE id::text = :k_id"), {"k_id": k_id_str}).fetchone()
                    if row:
                        has_doc = True
            except Exception:
                pass
            if has_doc:
                filter_metadata["knowledge_id"] = k_id_str
            else:
                logger.warning(f"🚫 [ChatPipeline] Document '{k_id_str}' is not in approved KB.")
                return ChatResponse(
                    query=query,
                    answer="Untuk saat ini informasi tersebut belum tersedia.",
                    context="",
                    results=[],
                    agent_used=False
                )

    try:
        response = pipeline.generate_answer(
            query=effective_query,
            top_k=top_k,
            filter_metadata=parsed_filter,
            rerank=True,
            history=raw_history,
            doctor_name=doc_name
        )

        ans_text = response.get("answer", "") if isinstance(response, dict) else response.answer
        res_list = response.get("results", []) if isinstance(response, dict) else response.results
        ctx_text = response.get("context", "") if isinstance(response, dict) else response.context
        agent_used_flag = response.get("agent_used", False) if isinstance(response, dict) else response.agent_used

        # Narrow guard: only wipe answer when retrieval genuinely found nothing
        # AND the LLM echoed the default unavailable phrase.
        # DO NOT wipe valid grounded answers that happen to contain negative words
        # like "tidak tercantum", "tidak ditemukan" — these are legitimate factual responses.
        if (
            "untuk saat ini informasi tersebut belum tersedia" in ans_text.lower()
            and (not res_list or not ctx_text or ctx_text in ("Maaf, saya tidak menemukan informasi.", "No relevant context found."))
        ):
            ans_text = "Untuk saat ini informasi tersebut belum tersedia."
            res_list = []

        # Sanitize invisible action HTML comments from answer text for clean UI rendering
        import re as _re_clean
        ans_text = _re_clean.sub(r'<!--\s*action:\s*\{[^>]+?\}\s*-->', '', ans_text).strip()

        return ChatResponse(
            query=query,
            answer=ans_text,
            context=ctx_text,
            results=res_list,
            agent_used=agent_used_flag
        )

    except Exception as e:
        logger.error(f"Unified Chat generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse, tags=["Generation"], summary="Chat Endpoint")
async def chat_endpoint(
    request: Request,
    prompt: Optional[str] = Form(
        None, 
        description="Clinical query or medical instruction from doctor"
    ),
    file: Optional[UploadFile] = File(
        None, 
        description="Optional patient medical record / profile document attachment (PDF, DOCX, XLSX, TXT, JPG, PNG)"
    ),
    doctor_name: Optional[str] = Form(
        None, 
        description="Optional doctor name for personalized greeting"
    ),
    pipeline: GenerationPipeline = Depends(get_generation_pipeline)
):
    """
    Unified RAG Chatbot endpoint for clinical medical queries and optional patient document attachment.
    """
    try:
        content_type = request.headers.get("content-type", "") if hasattr(request, "headers") else ""

        # Mode 1: JSON Body (application/json)
        if "application/json" in content_type:
            try:
                body = await request.json()
                q_str = body.get("prompt") or body.get("query") or ""
                if not q_str:
                    raise HTTPException(status_code=400, detail="Field 'prompt' or 'query' is required in JSON body.")

                return await run_chat_pipeline(
                    query=q_str,
                    attachment_text=body.get("attachment_text"),
                    doctor_name=body.get("doctor_name") or doctor_name,
                    history=body.get("history"),
                    categories=body.get("categories"),
                    top_k=body.get("top_k", 8),
                    knowledge_id=body.get("knowledge_id"),
                    batch_id=body.get("batch_id"),
                    pipeline=pipeline
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")

        # Mode 2: Form Data / Swagger UI / Streamlit
        else:
            form_data = await request.form()
            effective_prompt = prompt or form_data.get("prompt") or form_data.get("query") or ""
            if not effective_prompt:
                raise HTTPException(status_code=400, detail="Field 'prompt' or 'query' is required.")

            raw_hist = form_data.get("history")
            parsed_hist = []
            if raw_hist:
                try:
                    parsed_hist = json.loads(raw_hist) if isinstance(raw_hist, str) else raw_hist
                except Exception:
                    pass

            raw_cats = form_data.get("categories")
            parsed_cats = []
            if raw_cats:
                try:
                    parsed_cats = json.loads(raw_cats) if isinstance(raw_cats, str) else raw_cats
                except Exception:
                    pass

            try:
                form_top_k = int(form_data.get("top_k", 8)) if form_data.get("top_k") else 8
            except (ValueError, TypeError):
                form_top_k = 8

            return await run_chat_pipeline(
                query=effective_prompt,
                file=file,
                doctor_name=form_data.get("doctor_name") or doctor_name,
                history=parsed_hist,
                categories=parsed_cats,
                top_k=form_top_k,
                pipeline=pipeline
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unified Chat generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EVALUATION ENDPOINT (Automated RAGAS Benchmark & Developer Quality Monitoring)
# =============================================================================

@router.post(
    "/evaluation", 
    response_model=RAGEvaluationResponse, 
    tags=["Evaluation"], 
    summary="Run RAG Evaluation Benchmark"
)
async def run_rag_evaluation(
    payload: Optional[Union[RAGEvaluationRequest, List[RAGEvaluationItem], List[Dict[str, Any]], Dict[str, Any]]] = Body(
        default=None,
        description="Benchmark configuration or test dataset list (leave empty {} or null for default benchmark suite)"
    ),
    retriever: HybridRetriever = Depends(get_hybrid_retriever),
    pipeline: GenerationPipeline = Depends(get_generation_pipeline),
    llm: BaseLLMAdapter = Depends(get_llm)
):
    """
    Evaluates retrieval accuracy (Hit Rate@K, MRR@K) and LLM reliability (Faithfulness, Answer Relevance) using RAGAS Framework.
    """
    parsed_dataset = None
    parsed_top_k = 5
    parsed_eval_gen = True

    if payload is not None:
        if isinstance(payload, RAGEvaluationRequest):
            if payload.dataset:
                parsed_dataset = [d.model_dump() for d in payload.dataset]
        elif isinstance(payload, list):
            parsed_dataset = []
            for item in payload:
                if isinstance(item, RAGEvaluationItem):
                    parsed_dataset.append(item.model_dump())
                elif isinstance(item, dict):
                    d_item = dict(item)
                    if "expected_file" in d_item and "expected_document" not in d_item:
                        d_item["expected_document"] = d_item["expected_file"]
                    parsed_dataset.append(d_item)
        elif isinstance(payload, dict):
            if "dataset" in payload and isinstance(payload["dataset"], list):
                parsed_dataset = []
                for item in payload["dataset"]:
                    if isinstance(item, dict):
                        d_item = dict(item)
                        if "expected_file" in d_item and "expected_document" not in d_item:
                            d_item["expected_document"] = d_item["expected_file"]
                        parsed_dataset.append(d_item)
                    else:
                        parsed_dataset.append(item)

    try:
        results = RAGEvaluator.evaluate_full(
            retriever=retriever,
            generation_pipeline=pipeline,
            llm_adapter=llm,
            dataset=parsed_dataset,
            top_k=parsed_top_k,
            rerank=True,
            rerank_top_n=3,
            evaluate_generation=parsed_eval_gen
        )
        return RAGEvaluationResponse(**results)
    except Exception as e:
        logger.error(f"RAG evaluation benchmark failed: {e}")
        raise HTTPException(status_code=500, detail=f"RAG evaluation benchmark failed: {str(e)}")


# =============================================================================
# QUERY GENERAL ENDPOINT (Knowledge Base Explorer, Editor & Deletion via Prompt)
# Akses tergantung RBAC role dari CIS. System prompt dari AppConfig DB.
# =============================================================================

class QueryGeneralRequest(BaseModel):
    """Request schema for Query General endpoint (Simplified: Prompt-only)."""
    prompt: str = Field(
        ..., 
        description="Prompt teks dari user untuk menelusuri (read), mengedit (update), atau menghapus (delete) dokumen KB",
        example="Apakah ada produk ERHA Age Corrector di database?"
    )
    history: List[dict] = Field(
        default=[], 
        description="Riwayat percakapan sebelumnya (opsional)"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_query_alias(cls, values):
        if isinstance(values, dict):
            # Backward-compatibility: if client sent 'query' instead of 'prompt', map it
            if "prompt" not in values and "query" in values:
                values["prompt"] = values["query"]
        return values

class QueryGeneralResponse(BaseModel):
    """Response schema for Query General endpoint (Operation-Based Pipeline)."""
    type: str = Field("answer", description="Tipe respons: 'answer', 'confirmation', 'success', 'cancelled', 'error'")
    message: str = Field("", description="Pesan utama respons")
    operation_id: Optional[str] = Field(None, description="UUID operasi jika respons membutuhkan konfirmasi")
    prompt: str = Field(..., description="Prompt yang dikirimkan user")
    answer: str = Field(..., description="Jawaban dan konfirmasi dari AI")
    action: str = Field("read", description="Aksi yang dijalankan: 'read', 'edit_preview', 'delete_preview', 'edit_executed', 'delete_executed', 'cancelled'")
    target_knowledge_id: Optional[str] = Field(None, description="ID dokumen yang diproses (jika ada update/delete)")
    total_found: int = Field(0, description="Jumlah data relevan yang ditemukan di KB")
    results: List[Dict[str, Any]] = Field(default=[], description="Potongan knowledge base yang ditemukan")

def _extract_kb_action(llm_answer: Union[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Parses the LLM response or conversation history to extract a JSON action block.
    Supports 2-step action lifecycle: edit_preview, edit_execute, delete_preview, delete_execute, edit, delete, cancel.
    Resilient to dict messages, fenced JSON, raw JSON, invisible HTML comment signatures, and structured text fallbacks.
    """
    if not llm_answer:
        return None

    if isinstance(llm_answer, dict):
        if "action" in llm_answer and llm_answer["action"] in ("edit_preview", "edit_execute", "edit", "delete_preview", "delete_execute", "delete", "cancel"):
            return {
                "action": llm_answer["action"],
                "knowledge_id": llm_answer.get("target_knowledge_id") or llm_answer.get("knowledge_id"),
                "field": llm_answer.get("field", "summary"),
                "new_value": llm_answer.get("new_value", ""),
                "target_item": llm_answer.get("target_item")
            }
        att = llm_answer.get("attachments")
        if isinstance(att, dict) and "action" in att:
            return {
                "action": att["action"],
                "knowledge_id": att.get("target_knowledge_id") or att.get("knowledge_id"),
                "field": att.get("field", "summary"),
                "new_value": att.get("new_value", ""),
                "target_item": att.get("target_item")
            }
        llm_answer = str(llm_answer.get("content", ""))

    import re as _re

    # 1. Invisible HTML comment signature: <!-- action:{...} -->
    comment_pattern = r'<!--\s*action:\s*(\{[^>]+?\})\s*-->'
    comment_matches = _re.findall(comment_pattern, llm_answer, _re.DOTALL)
    for cm in comment_matches:
        try:
            parsed = json.loads(cm.strip())
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except Exception:
            continue

    # 2. Fenced JSON blocks ```json ... ``` or ``` ... ```
    pattern = r'```(?:json)?\s*\n?\s*(\{[^`]+?\})\s*\n?\s*```'
    matches = _re.findall(pattern, llm_answer, _re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match.strip())
            if isinstance(parsed, dict):
                action = parsed.get("action")
                if action in ("edit_preview", "edit_execute", "edit", "delete_preview", "delete_execute", "delete", "cancel"):
                    return parsed
        except (json.JSONDecodeError, ValueError):
            continue

    # 3. Raw JSON objects without code fences
    raw_matches = _re.findall(r'(\{\s*"action"\s*:\s*"[^"]+".*?\})', llm_answer, _re.DOTALL)
    for rm in raw_matches:
        try:
            parsed = json.loads(rm.strip())
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except Exception:
            continue

    # 4. Direct cancel string fallback
    if '"action": "cancel"' in llm_answer or '"action":"cancel"' in llm_answer:
        return {"action": "cancel"}

    # 5. Natural Language Text Fallback for Edit Preview
    lower_ans = llm_answer.lower()
    if "pratinjau perubahan" in lower_ans or "apakah anda yakin ingin menerapkan perubahan" in lower_ans:
        kid_match = _re.search(r'(?:id dokumen|id|knowledge_id|dokumen id)\s*[:=]\s*[`"]?([a-zA-Z0-9\-_]+)[`"]?', llm_answer, _re.IGNORECASE)
        field_match = _re.search(r'(?:bagian yang diubah|field|bagian|kolom)\s*[:=]\s*[`"]?([a-zA-Z0-9\-_]+)[`"]?', llm_answer, _re.IGNORECASE)
        val_match = _re.search(r'(?:nilai baru|new value|menjadi)\s*[:=]\s*[`"]?([^\n\r`"]+)[`"]?', llm_answer, _re.IGNORECASE)
        item_match = _re.search(r'(?:produk target|target item|nama produk|item)\s*[:=]\s*[`"]?([^\n\r`"]+)[`"]?', llm_answer, _re.IGNORECASE)
        if kid_match:
            result = {
                "action": "edit_preview",
                "knowledge_id": kid_match.group(1).strip(),
                "field": field_match.group(1).strip() if field_match else "summary",
                "new_value": val_match.group(1).strip() if val_match else ""
            }
            if item_match:
                result["target_item"] = item_match.group(1).strip()
            return result

    # 6. Natural Language Text Fallback for Delete Preview
    if "konfirmasi penghapusan" in lower_ans or "apakah anda yakin ingin menghapus" in lower_ans:
        kid_match = _re.search(r'(?:id dokumen|id|knowledge_id|dokumen id)\s*[:=]\s*[`"]?([a-zA-Z0-9\-_]+)[`"]?', llm_answer, _re.IGNORECASE)
        item_match = _re.search(r'(?:produk target|target item|nama produk|item yang dihapus)\s*[:=]\s*[`"]?([^\n\r`"]+)[`"]?', llm_answer, _re.IGNORECASE)
        if kid_match:
            result = {
                "action": "delete_preview",
                "knowledge_id": kid_match.group(1).strip()
            }
            if item_match:
                result["target_item"] = item_match.group(1).strip()
            return result

    return None


async def _apply_kb_edit(
    knowledge_id: str,
    field: str,
    new_value: str,
    vector_store,
    bm25_index,
    pipeline=None,
    target_item: Optional[str] = None,
    db=None
) -> Dict[str, Any]:
    """Delegates edit to Dedicated CRUD Service."""
    return await GeneralKnowledgeService.apply_edit(
        knowledge_id=knowledge_id,
        field=field,
        new_value=new_value,
        vector_store=vector_store,
        bm25_index=bm25_index,
        pipeline=pipeline,
        target_item=target_item,
        db=db
    )


async def _apply_kb_delete(
    knowledge_id: str,
    vector_store,
    bm25_index,
    target_item: Optional[str] = None,
    db=None
) -> Dict[str, Any]:
    """Delegates delete to Dedicated CRUD Service."""
    return await GeneralKnowledgeService.apply_delete(
        knowledge_id=knowledge_id,
        vector_store=vector_store,
        bm25_index=bm25_index,
        target_item=target_item,
        db=db
    )



async def _resolve_query_general_prompt(db_session) -> str:
    """
    Resolves the system prompt for Query General:
    1. AppConfig DB key: AI_PROMPT_QUERY_GENERAL (admin-configurable via CIS)
    2. DEFAULT_QUERY_GENERAL_PROMPT (hardcoded fallback)
    Auto-synchronizes DB prompt if missing strict anti-duplication rules or product image rules.
    """
    from app.rag.services.rag_generator import DEFAULT_QUERY_GENERAL_PROMPT
    try:
        from app.models.config import AppConfig
        from sqlalchemy import select
        stmt = select(AppConfig.value).where(AppConfig.key == "AI_PROMPT_QUERY_GENERAL")
        result = await db_session.execute(stmt)
        db_prompt = result.scalar_one_or_none()
        if db_prompt and db_prompt.strip():
            needs_sync = (
                "GAMBAR PRODUK & TREATMENT RESMI" not in db_prompt
                or "PENYAJIAN JURNAL ILMIAH & KATALOG TABEL" not in db_prompt
                or "PENYAJIAN PERBANDINGAN PRODUK & TREATMENT" not in db_prompt
                or "BATASAN AKSES ROLE DOKTER" in db_prompt
                or "Currently, we are unable to provide this information." in db_prompt
                or "KONTRAINDIKASI, KONDISI KHUSUS" not in db_prompt
                or "KONSISTENSI PENOMORAN DAFTAR" not in db_prompt
                or "ZERO PROCEDURAL EXTRAPOLATION" not in db_prompt
                or "KOMBO TREATMENT & INDIKASI SPESIFIK" not in db_prompt
            )
            if needs_sync:
                try:
                    stmt_update = select(AppConfig).where(AppConfig.key == "AI_PROMPT_QUERY_GENERAL")
                    res_cfg = await db_session.execute(stmt_update)
                    cfg_obj = res_cfg.scalar_one_or_none()
                    if cfg_obj:
                        cfg_obj.value = DEFAULT_QUERY_GENERAL_PROMPT
                        await db_session.commit()
                        logger.info("[QUERY-GENERAL] Auto-synchronized AI_PROMPT_QUERY_GENERAL in AppConfig DB with natural Q&A persona and clean Admin document guidance.")
                except Exception as sync_err:
                    logger.warning(f"[QUERY-GENERAL] Could not auto-sync DB prompt: {sync_err}")
                return DEFAULT_QUERY_GENERAL_PROMPT
            return db_prompt.strip()
    except Exception as e:
        logger.warning(f"[QUERY-GENERAL] Failed to fetch system prompt from DB: {e}")

    return DEFAULT_QUERY_GENERAL_PROMPT


@router.post("/query-general", response_model=QueryGeneralResponse, tags=["Query General"], summary="Query General Endpoint")
async def query_general_endpoint(
    request: QueryGeneralRequest,
    pipeline: GenerationPipeline = Depends(get_generation_pipeline),
    vector_store: BaseVectorStoreAdapter = Depends(get_vector_store),
    bm25: BM25Index = Depends(get_bm25_index)
):
    """
    Interactively explores, edits, or deletes knowledge base documents using natural language prompt instructions.
    Follows a 4-Phase AI Orchestrator pattern:
    - Phase 1: Confirmation Lifecycle (Executing pending edit/delete operations deterministically)
    - Phase 2: Mutation Intent Classifier (Deterministic operation discovery & preview generation)
    - Phase 3: Dedicated RAG Pipeline (Strictly grounded factual question answering)
    - Phase 4: Output Sanitization & Entity-Isolated MinIO Image Injection
    """
    if not pipeline:
        raise HTTPException(status_code=500, detail="Generation pipeline is not initialized.")

    try:
        user_prompt = request.prompt
        clean_user_prompt = user_prompt.strip().lower()

        has_retriever = hasattr(pipeline, "retriever") and getattr(pipeline, "retriever", None) is not None
        target_vs = (pipeline.retriever.vector_store if has_retriever and hasattr(pipeline.retriever, 'vector_store') else (vector_store if hasattr(vector_store, "delete_document") else None))
        target_bm25 = (pipeline.retriever.bm25_index if has_retriever and hasattr(pipeline.retriever, 'bm25_index') else (bm25 if hasattr(bm25, "remove_file_chunks") else None))

        contextualize_fn = getattr(pipeline, "contextualize_retrieval_query", None) or (lambda p, h: p)
        effective_prompt = contextualize_fn(user_prompt, request.history) if callable(contextualize_fn) else user_prompt

        # -------------------------------------------------------------
        # PHASE 1: Confirmation Lifecycle (Check & Execute Active Pending Operation via Chat Prompt)
        # -------------------------------------------------------------
        from app.models.pending_operation import PendingOperation
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select

        is_confirm_prompt = bool(re.search(r'^\s*(?:ya|ya\s+hapus|ya\s+edit|ya\s+terapkan|konfirmasi|setuju|terapkan|proses|lanjutkan|ok|okay|yep|yes|confirm|execute|lakukan)\b', clean_user_prompt))
        is_cancel_prompt = bool(re.search(r'^\s*(?:batal|batalkan|cancel|tidak|jangan|abort|stop)\b', clean_user_prompt))

        if is_confirm_prompt or is_cancel_prompt:
            async with AsyncSessionLocal() as db_session:
                now_utc = datetime.now(timezone.utc)
                stmt = (
                    select(PendingOperation)
                    .where(PendingOperation.status == "pending")
                    .where(PendingOperation.expires_at > now_utc)
                    .order_by(PendingOperation.created_at.desc())
                )
                res = await db_session.execute(stmt)
                latest_op = res.scalars().first()

                if latest_op:
                    if is_cancel_prompt:
                        latest_op.status = "cancelled"
                        await db_session.commit()
                        cancel_msg = "Operasi telah dibatalkan atas permintaan Anda."
                        return QueryGeneralResponse(
                            type="answer",
                            message=cancel_msg,
                            prompt=user_prompt,
                            answer=cancel_msg,
                            action="cancelled",
                            target_knowledge_id=latest_op.knowledge_id,
                            total_found=0,
                            results=[]
                        )

                    elif is_confirm_prompt:
                        affected_kids = (latest_op.metadata_ or {}).get("affected_knowledge_ids") or [latest_op.knowledge_id]
                        if latest_op.action == "edit":
                            edit_results = []
                            for kid in affected_kids:
                                r_edit = await GeneralKnowledgeService.apply_edit(
                                    knowledge_id=kid,
                                    field=latest_op.field or "summary",
                                    new_value=latest_op.new_value or "",
                                    vector_store=target_vs,
                                    bm25_index=target_bm25,
                                    pipeline=pipeline,
                                    target_item=latest_op.target_item,
                                    db=db_session
                                )
                                edit_results.append(r_edit)

                            any_succ = any(r.get("success") for r in edit_results)
                            if any_succ:
                                latest_op.status = "confirmed"
                                latest_op.confirmed_at = now_utc
                                await db_session.commit()
                                if len(affected_kids) > 1:
                                    succ_msg = f"Changes to '{latest_op.target_item or latest_op.knowledge_id}' were successfully applied to {len(affected_kids)} Knowledge Base documents."
                                else:
                                    succ_msg = edit_results[0].get("message") or f"Changes to '{latest_op.target_item or latest_op.knowledge_id}' were successfully applied to the Knowledge Base."
                                return QueryGeneralResponse(
                                    type="answer",
                                    message=succ_msg,
                                    prompt=user_prompt,
                                    answer=succ_msg,
                                    action="edit_applied",
                                    target_knowledge_id=latest_op.knowledge_id,
                                    total_found=len(affected_kids),
                                    results=[]
                                )
                            else:
                                errs = [r.get("error", "Unknown error") for r in edit_results if not r.get("success")]
                                fail_msg = f"Failed to apply changes: {'; '.join(errs)}"
                                return QueryGeneralResponse(
                                    type="answer",
                                    message=fail_msg,
                                    prompt=user_prompt,
                                    answer=fail_msg,
                                    action="edit_failed",
                                    target_knowledge_id=latest_op.knowledge_id,
                                    total_found=0,
                                    results=[]
                                )

                        elif latest_op.action == "delete":
                            del_results = []
                            meta_dict = latest_op.metadata_ or {}
                            affected_docs_map = {d["knowledge_id"]: d.get("target_item") for d in meta_dict.get("affected_docs", []) if isinstance(d, dict) and "knowledge_id" in d}
                            for kid in affected_kids:
                                doc_target = affected_docs_map.get(kid) or latest_op.target_item
                                r_del = await GeneralKnowledgeService.apply_delete(
                                    knowledge_id=kid,
                                    target_item=doc_target,
                                    vector_store=target_vs,
                                    bm25_index=target_bm25,
                                    db=db_session,
                                    session_id=(latest_op.metadata_ or {}).get("session_id")
                                )
                                del_results.append(r_del)

                            any_succ = any(r.get("success") for r in del_results)
                            if any_succ:
                                latest_op.status = "confirmed"
                                latest_op.confirmed_at = now_utc
                                await db_session.commit()
                                if len(affected_kids) > 1:
                                    succ_msg = f"Item '{latest_op.target_item or latest_op.knowledge_id}' was successfully deleted from {len(affected_kids)} Knowledge Base documents."
                                else:
                                    succ_msg = del_results[0].get("message") or f"Item/document '{latest_op.target_item or latest_op.knowledge_id}' was successfully deleted from the Knowledge Base."
                                return QueryGeneralResponse(
                                    type="answer",
                                    message=succ_msg,
                                    prompt=user_prompt,
                                    answer=succ_msg,
                                    action="delete_applied",
                                    target_knowledge_id=latest_op.knowledge_id,
                                    total_found=len(affected_kids),
                                    results=[]
                                )
                            else:
                                errs = [r.get("error", "Unknown error") for r in del_results if not r.get("success")]
                                fail_msg = f"Gagal menghapus item: {'; '.join(errs)}"
                                return QueryGeneralResponse(
                                    type="answer",
                                    message=fail_msg,
                                    prompt=user_prompt,
                                    answer=fail_msg,
                                    action="delete_failed",
                                    target_knowledge_id=latest_op.knowledge_id,
                                    total_found=0,
                                    results=[]
                                )

        # -------------------------------------------------------------
        # PHASE 1.5: Clarification Follow-Up Interceptor
        # -------------------------------------------------------------
        # If the preceding assistant turn prompted the user to clarify multiple ambiguous documents:
        # e.g.: "Silakan sebutkan ID dokumen/nama file mana yang ingin diubah/dihapus, atau tambahkan frasa 'di seluruh KB'..."
        # and the user now answers with "di seluruh KB", "semua", an option number ("1", "nomor 2"), or a document name/UUID:
        last_asst_msg = None
        prev_user_cmd = None
        if request.history and isinstance(request.history, list):
            for msg in reversed(request.history):
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role") or "").lower()
                content = str(msg.get("content") or "").strip()
                if role == "assistant" and not last_asst_msg:
                    last_asst_msg = content
                elif role in ("user", "admin") and last_asst_msg and not prev_user_cmd:
                    prev_user_cmd = content
                    break

        if last_asst_msg and prev_user_cmd:
            last_asst_low = last_asst_msg.lower()
            is_clarification_response = (
                ("knowledge base dengan target" in last_asst_low or "ditemukan" in last_asst_low)
                and ("di seluruh kb" in last_asst_low or "id dokumen" in last_asst_low or "nama file mana" in last_asst_low)
            )
            if is_clarification_response:
                clean_ans = clean_user_prompt.strip().lower()
                is_all_scope = bool(re.search(r'\b(?:di\s+seluruh|seluruh|semua|all|di\s+semua|semuanya)\b', clean_ans))
                
                # Extract options listed in assistant message:
                # E.g. "1. [d60efdf1-...](url) — *Katalog Produk ERHA Acneact*"
                option_matches = re.findall(r'(?:(\d+)\.\s*)?\[([0-9a-fA-F\-]{36})\]\([^\)]+\)\s*—\s*\*?([^\*\n\r]+)\*?', last_asst_msg)
                
                chosen_doc_id = None
                chosen_doc_title = None

                # Check if user picked by number (e.g. "1", "nomor 2", "opsi 1")
                idx_m = re.search(r'\b(?:nomor|no|opsi|dokumen|pilihan)?\s*(\d+)\b', clean_ans)
                if idx_m and option_matches:
                    opt_idx = int(idx_m.group(1)) - 1
                    if 0 <= opt_idx < len(option_matches):
                        chosen_doc_id = option_matches[opt_idx][1]
                        chosen_doc_title = option_matches[opt_idx][2].strip()
                
                if not chosen_doc_id and option_matches:
                    for num, opt_id, opt_title in option_matches:
                        opt_id_low = opt_id.lower()
                        opt_title_low = opt_title.lower().strip()
                        if opt_id_low in clean_ans or (len(opt_title_low) > 3 and opt_title_low in clean_ans):
                            chosen_doc_id = opt_id
                            chosen_doc_title = opt_title.strip()
                            break

                if is_all_scope:
                    effective_prompt = f"{prev_user_cmd} di seluruh KB"
                    clean_user_prompt = effective_prompt.lower()
                    user_prompt = effective_prompt
                    logger.info(f"🔗 [Clarification Follow-Up] User specified ALL documents -> effective_prompt: '{effective_prompt}'")
                elif chosen_doc_id:
                    effective_prompt = f"{prev_user_cmd} pada dokumen {chosen_doc_id}"
                    clean_user_prompt = effective_prompt.lower()
                    user_prompt = effective_prompt
                    logger.info(f"🔗 [Clarification Follow-Up] User selected doc '{chosen_doc_id}' -> effective_prompt: '{effective_prompt}'")

        # -------------------------------------------------------------
        # PHASE 2: Operation Intent Classifier (EDIT / DELETE Intent Detection)
        # -------------------------------------------------------------
        # Explicit action verbs for DELETE & EDIT
        delete_verbs = r'(?:hapus|delete|hilangkan|buang|bersihkan|tiadakan|wipe|erase|clear\s+data|clear\s+kb|clear\s+database|clear\s+knowledge|clear\s+dokumen|clear\s+item|remove\s+data|remove\s+kb|remove\s+dokumen|remove\s+item|^clear\s+|^remove\s+)'
        edit_verbs = r'(?:ubah|ganti|edit|tukar|salin|update|perbarui|revisi|terapkan|pasang|masukkan|tambahkan|sisipkan|gantikan|gantiin|set\s+data|set\s+harga|set\s+ukuran|modifikasi|perbaiki|^set\s+)'

        has_delete_verb = bool(re.search(rf'\b{delete_verbs}', clean_user_prompt, re.IGNORECASE)) or bool(re.search(rf'\b{delete_verbs}', effective_prompt.lower(), re.IGNORECASE))
        has_edit_verb = bool(re.search(rf'\b{edit_verbs}', clean_user_prompt, re.IGNORECASE)) or bool(re.search(rf'\b{edit_verbs}', effective_prompt.lower(), re.IGNORECASE))

        # Strict READ / Q&A Intent Guard: Active ONLY if prompt contains no explicit action mutation verb (edit/delete)
        read_keywords = r'\b(detail|info|informasi|penjelasan|deskripsi|apa|apakah|bagaimana|mengapa|kenapa|bisa\s*kah|kapan|berapa|siapa|sebutkan|rekomendasi|manfaat|fungsi|cara|prosedur|gambar|foto|lihat|tunjukkan|cari|tampilkan)\b'
        is_read_query = bool(re.search(read_keywords, clean_user_prompt, re.IGNORECASE)) and not (has_delete_verb or has_edit_verb)

        is_delete_cmd = has_delete_verb and not is_read_query
        is_edit_cmd = has_edit_verb and not is_read_query

        if is_edit_cmd:
            matched_res = (
                await GeneralKnowledgeService.find_all_target_documents_and_item(user_prompt)
                or await GeneralKnowledgeService.find_all_target_documents_and_item(effective_prompt)
            )

            if matched_res:
                target_item, matched_docs = matched_res
                top_doc = matched_docs[0]
                target_kid = top_doc["knowledge_id"]
                doc_data = top_doc["doc_data"]
                doc_title = top_doc.get("title") or top_doc.get("file_name") or target_kid
                batch_id = top_doc.get("batch_id")
                context_label = doc_data.get("_matched_context_label") or target_item or doc_title

                # Extract new value
                val_m = re.search(r'(?:\b(?:menjadi|ke|sebagai|jadi|dengan|sebesar|berupa)\b|=)\s*[`"\'“]?([^\n\r`"\'”]+)[`"\'”]?$', user_prompt, re.IGNORECASE)
                if not val_m:
                    val_m = re.search(r'(?:\b(?:menjadi|ke|sebagai|jadi|dengan|sebesar|berupa)\b|=)\s*[`"\'“]?([^\n\r`"\'”]+)[`"\'”]?', user_prompt, re.IGNORECASE)
                new_val = val_m.group(1).strip() if val_m else ""
                if not new_val:
                    unit_m = re.search(r'(?:rp\.?\s*[\d\.,]+|\b\d+\s*(?:k|rb|ribu|gr|gram|ml|l|mg|pcs|sachet|botol|pack)\b)', user_prompt, re.IGNORECASE)
                    if unit_m:
                        new_val = unit_m.group(0).strip()
                if new_val:
                    # Strip trailing scope modifiers: e.g. "pada semua produk", "di semua produk", "di kb", "pada dokumen <uuid>"
                    new_val = re.sub(r'\s+pada\s+dokumen\s+[0-9a-fA-F\-]+$', '', new_val, flags=re.IGNORECASE).strip()
                    new_val = re.sub(r'\s+(?:pada|di|dalam|untuk|bagi)\s+(?:semua|seluruh|setiap)?\s*(?:produk|item|dokumen|kb|knowledge|data|semuanya)?$', '', new_val, flags=re.IGNORECASE).strip()
                    new_val = re.sub(r'[\s,\.]+(?:ya|dong|tolong|mohon|terima\s*kasih|thanks)$', '', new_val, flags=re.IGNORECASE).strip()
                    new_val = re.sub(r'^[`"\'“]+|[`"\'”]+$', '', new_val).strip()
                else:
                    new_val = user_prompt.strip()

                # Extract field name dynamically
                field = None
                field_keywords = [
                    ("ukuran", ["ukuran", "size", "berat", "netto", "volume", "weight"]),
                    ("harga", ["harga", "price", "tarif", "biaya"]),
                    ("sku", ["sku", "kode produk", "kode", "kode sku"]),
                    ("kategori", ["kategori", "category", "jenis"]),
                    ("deskripsi", ["deskripsi", "description", "keterangan", "detail"]),
                    ("nama", ["nama", "nama produk", "judul", "title"]),
                    ("indikasi", ["indikasi", "kegunaan", "manfaat", "fungsi"]),
                    ("cara_pakai", ["cara pakai", "aturan pakai", "cara penggunaan", "aturan penggunaan", "instruksi", "dosis"]),
                    ("periode", ["periode", "masa berlaku", "periode promo", "valid until"]),
                    ("brand", ["brand", "merek", "merk"]),
                    ("kandungan", ["kandungan", "komposisi", "ingredients", "key ingredients", "ingridients", "bahan"])
                ]

                for canonical_name, aliases in field_keywords:
                    for alias in aliases:
                        if re.search(rf'\b{re.escape(alias)}\b', clean_user_prompt):
                            field = canonical_name
                            break
                    if field:
                        break

                clean_target_item = (target_item or "").lower().strip()
                if not field:
                    field_match = re.search(r'\b(?:ubah|ganti|edit|tukar|salin|update|perbarui|revisi)\s+([a-zA-Z_0-9\s]+?)(?:\s+produk|\s+item|\s+ke|\s+menjadi|\s+sebagai|\b)', clean_user_prompt)
                    if field_match:
                        candidate_field = field_match.group(1).lower().strip()
                        if candidate_field not in ("data", "informasi", "dokumen", "item", "produk", "ke", "menjadi", "sebagai") and candidate_field != clean_target_item and clean_target_item not in candidate_field:
                            field = candidate_field

                # Inspect matched docs to detect attribute from bullet points (e.g. Kandungan Utama: ... Hyaluronic Acid)
                # ONLY run this if field was not explicitly extracted from user prompt
                detected_attr = None
                if target_item and (not field or field in ("summary", "text", "konten")):
                    for d in matched_docs:
                        d_sum = (d.get("doc_data") or {}).get("summary") or d.get("summary") or ""
                        bullet_m = re.search(
                            r'-\s*\*\*([^\*\n:]+)\*\*\s*:\s*[^\n]*?\b' + re.escape(target_item.strip()) + r'\b',
                            d_sum,
                            re.IGNORECASE
                        )
                        if not bullet_m:
                            bullet_m = re.search(
                                r'-\s*\*\*([^\*\n:]+)\*\*\s*:\s*[^\n]*?' + re.escape(target_item.strip()),
                                d_sum,
                                re.IGNORECASE
                            )
                        if bullet_m:
                            raw_attr = bullet_m.group(1).strip()
                            raw_attr_lower = raw_attr.lower()
                            if any(k in raw_attr_lower for k in ("kandungan", "bahan", "ingredient", "komposisi")):
                                field = "kandungan"
                                detected_attr = "Kandungan"
                            elif any(k in raw_attr_lower for k in ("kategori", "category")):
                                field = "kategori"
                                detected_attr = "Kategori"
                            elif any(k in raw_attr_lower for k in ("harga", "tarif", "biaya", "price")):
                                field = "harga"
                                detected_attr = "Harga"
                            elif any(k in raw_attr_lower for k in ("ukuran", "size", "netto", "volume", "berat")):
                                field = "ukuran"
                                detected_attr = "Ukuran"
                            elif any(k in raw_attr_lower for k in ("sku", "kode")):
                                field = "sku"
                                detected_attr = "SKU"
                            elif any(k in raw_attr_lower for k in ("nama", "produk")):
                                field = "nama"
                                detected_attr = "Nama Produk"
                            else:
                                detected_attr = raw_attr
                            break

                if not field:
                    field = "summary"

                field_display_names = {
                    "ukuran": "Ukuran",
                    "harga": "Harga",
                    "price": "Harga",
                    "sku": "SKU",
                    "kategori": "Kategori",
                    "deskripsi": "Deskripsi",
                    "nama": "Nama Produk / Judul",
                    "product_name": "Nama Produk",
                    "indikasi": "Indikasi",
                    "cara_pakai": "Cara Pakai / Aturan Pakai",
                    "usage_instruction": "Instruksi Penggunaan",
                    "periode": "Periode Promo / Masa Berlaku",
                    "brand": "Brand",
                    "kandungan": "Kandungan",
                    "summary": "Ringkasan Dokumen"
                }
                field_display = detected_attr or field_display_names.get(field.lower(), field.capitalize())
                scope = GeneralKnowledgeService.detect_mutation_scope(user_prompt) if GeneralKnowledgeService.detect_mutation_scope(user_prompt) == "GLOBAL" else GeneralKnowledgeService.detect_mutation_scope(effective_prompt)

                explicit_doc_ref = False
                uuid_matches = re.findall(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', user_prompt)
                if uuid_matches:
                    explicit_doc_ref = True
                    matched_docs = [d for d in matched_docs if d["knowledge_id"].lower() == uuid_matches[0].lower()]

                if not explicit_doc_ref:
                    for d in list(matched_docs):
                        dt = (d.get("title") or "").lower()
                        fn = (d.get("file_name") or "").lower()
                        if (fn and len(fn) > 3 and fn in clean_user_prompt) or (d["knowledge_id"].lower() in clean_user_prompt):
                            matched_docs = [d]
                            explicit_doc_ref = True
                            break
                        if dt and len(dt) > 3 and dt not in clean_target_item:
                            if re.search(rf'\b{re.escape(dt)}\b', clean_user_prompt):
                                matched_docs = [d]
                                explicit_doc_ref = True
                                break

                if scope == "SINGLE_ITEM" and len(matched_docs) > 1 and not explicit_doc_ref:
                    doc_list_items = []
                    for idx, d in enumerate(matched_docs, 1):
                        kid = d["knowledge_id"]
                        t = d.get("title") or d.get("file_name") or kid
                        b_id = d.get("batch_id")
                        link = f"[{kid}](/dashboard/knowledge/batch/{b_id})" if b_id else f"[{kid}](/dashboard/knowledge/{kid})"
                        doc_list_items.append(f"{idx}. {link} — *{t}*")
                    doc_list_str = "\n".join(doc_list_items)

                    ambiguous_text = (
                        f"**Ditemukan {len(matched_docs)} Knowledge Base dengan target yang sama**\n\n"
                        f"Permintaan Anda merujuk pada **{target_item}** yang ada di beberapa dokumen:\n\n"
                        f"{doc_list_str}\n\n"
                        f"Silakan sebutkan ID dokumen/nama file mana yang ingin diubah, atau tambahkan frasa **\"di seluruh KB\"** jika Anda ingin menerapkan perubahan ke semua dokumen."
                    )
                    return QueryGeneralResponse(
                        type="answer",
                        message=ambiguous_text,
                        prompt=user_prompt,
                        answer=ambiguous_text,
                        action="ambiguous_target_clarification",
                        target_knowledge_id=None,
                        total_found=len(matched_docs),
                        results=[]
                    )

                if scope == "SINGLE_ITEM":
                    matched_docs = [matched_docs[0]]

                top_doc = matched_docs[0]
                target_kid = top_doc["knowledge_id"]
                doc_title = top_doc.get("title") or top_doc.get("file_name") or target_kid
                batch_id = top_doc.get("batch_id")

                if new_val:
                    edit_results = []
                    from app.core.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db_session:
                        for d in matched_docs:
                            d_kid = d["knowledge_id"]
                            d_target = d.get("target_item") or target_item
                            r_edit = await GeneralKnowledgeService.apply_edit(
                                knowledge_id=d_kid,
                                field=field,
                                new_value=new_val,
                                target_item=d_target,
                                auto_approve=True,
                                db=db_session,
                                vector_store=target_vs,
                                bm25_index=target_bm25
                            )
                            edit_results.append(r_edit)

                    any_succ = any(r.get("success") for r in edit_results)
                    if any_succ:
                        attr_label = detected_attr or (field_display if field and field not in ("summary", "text", "konten") else "")
                        if attr_label:
                            succ_msg = f"{attr_label} '{target_item}' berhasil diubah menjadi '{new_val}'. Knowledge base telah diperbarui."
                        else:
                            succ_msg = f"Perubahan '{target_item}' menjadi '{new_val}' berhasil diterapkan. Knowledge base telah diperbarui."

                        updated_doc_summaries = [r.get("summary", "") for r in edit_results if r.get("summary")]
                        combined_summary = "\n\n".join(updated_doc_summaries) if updated_doc_summaries else ""
                        
                        target_names_for_cards = []
                        if target_item:
                            target_names_for_cards.append(target_item)
                        if field in ("nama", "nama_produk", "title") and new_val:
                            target_names_for_cards.append(new_val)

                        formatted_ans = format_chat_response_with_cards(
                            confirmation=succ_msg,
                            summary=combined_summary,
                            target_product_names=target_names_for_cards if target_names_for_cards else None,
                            intro_label="Berikut adalah detail produk yang diperbarui:"
                        )

                        return QueryGeneralResponse(
                            type="answer",
                            message=formatted_ans,
                            prompt=user_prompt,
                            answer=formatted_ans,
                            action="edit_applied",
                            target_knowledge_id=target_kid,
                            total_found=len(matched_docs),
                            results=[]
                        )
                    else:
                        errs = [r.get("error", "Unknown error") for r in edit_results if not r.get("success")]
                        fail_msg = f"Gagal memperbarui data: {'; '.join(errs)}"
                        return QueryGeneralResponse(
                            type="answer",
                            message=fail_msg,
                            prompt=user_prompt,
                            answer=fail_msg,
                            action="edit_failed",
                            target_knowledge_id=target_kid,
                            total_found=0,
                            results=[]
                        )
            else:
                not_found_msg = "Target produk atau bagian yang ingin diubah tidak ditemukan dalam knowledge base."
                return QueryGeneralResponse(
                    type="answer",
                    message=not_found_msg,
                    prompt=user_prompt,
                    answer=not_found_msg,
                    action="read",
                    target_knowledge_id=None,
                    total_found=0,
                    results=[]
                )

        elif is_delete_cmd:
            del_name, del_ingr, del_type = extract_product_deletion(user_prompt)
            if not del_type:
                del_name, del_ingr, del_type = extract_product_deletion(effective_prompt)

            search_query = del_ingr or del_name or user_prompt
            matched_res = (
                await GeneralKnowledgeService.find_all_target_documents_and_item(search_query)
                or await GeneralKnowledgeService.find_all_target_documents_and_item(user_prompt)
                or await GeneralKnowledgeService.find_all_target_documents_and_item(effective_prompt)
            )

            if matched_res:
                target_item, matched_docs = matched_res
                top_doc = matched_docs[0]
                target_kid = top_doc["knowledge_id"]
                doc_data = top_doc["doc_data"]
                doc_title = top_doc.get("title") or top_doc.get("file_name") or target_kid
                batch_id = top_doc.get("batch_id")
                context_label = doc_data.get("_matched_context_label") or target_item or doc_title

                scope = GeneralKnowledgeService.detect_mutation_scope(user_prompt) if GeneralKnowledgeService.detect_mutation_scope(user_prompt) == "GLOBAL" else GeneralKnowledgeService.detect_mutation_scope(effective_prompt)

                explicit_doc_ref = False
                uuid_matches = re.findall(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', user_prompt)
                if uuid_matches:
                    explicit_doc_ref = True
                    matched_docs = [d for d in matched_docs if d["knowledge_id"].lower() == uuid_matches[0].lower()]

                clean_target_item = (target_item or "").lower()
                if not explicit_doc_ref:
                    for d in list(matched_docs):
                        dt = (d.get("title") or "").lower()
                        fn = (d.get("file_name") or "").lower()
                        if (fn and len(fn) > 3 and fn in clean_user_prompt) or (d["knowledge_id"].lower() in clean_user_prompt):
                            matched_docs = [d]
                            explicit_doc_ref = True
                            break
                        if dt and len(dt) > 3 and dt not in clean_target_item:
                            if re.search(rf'\b{re.escape(dt)}\b', clean_user_prompt):
                                matched_docs = [d]
                                explicit_doc_ref = True
                                break

                if scope == "SINGLE_ITEM" and len(matched_docs) > 1 and not explicit_doc_ref:
                    doc_list_items = []
                    for idx, d in enumerate(matched_docs, 1):
                        kid = d["knowledge_id"]
                        t = d.get("title") or d.get("file_name") or kid
                        b_id = d.get("batch_id")
                        link = f"[{kid}](/dashboard/knowledge/batch/{b_id})" if b_id else f"[{kid}](/dashboard/knowledge/{kid})"
                        doc_list_items.append(f"{idx}. {link} — *{t}*")
                    doc_list_str = "\n".join(doc_list_items)

                    ambiguous_text = (
                        f"**Ditemukan {len(matched_docs)} Knowledge Base dengan target penghapusan yang sama**\n\n"
                        f"Permintaan Anda merujuk pada **{target_item}** yang ada di beberapa dokumen:\n\n"
                        f"{doc_list_str}\n\n"
                        f"Silakan sebutkan ID dokumen/nama file mana yang ingin dihapus, atau tambahkan frasa **\"di seluruh KB\"** jika Anda ingin menghapus dari semua dokumen."
                    )
                    return QueryGeneralResponse(
                        type="answer",
                        message=ambiguous_text,
                        prompt=user_prompt,
                        answer=ambiguous_text,
                        action="ambiguous_target_clarification",
                        target_knowledge_id=None,
                        total_found=len(matched_docs),
                        results=[]
                    )

                if scope == "SINGLE_ITEM":
                    matched_docs = [matched_docs[0]]

                top_doc = matched_docs[0]
                target_kid = top_doc["knowledge_id"]
                doc_title = top_doc.get("title") or top_doc.get("file_name") or target_kid
                batch_id = top_doc.get("batch_id")

                # Directly apply deletion: prompt untuk hapus > terhapus > knowledge terupdate
                del_results = []
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db_session:
                    for d in matched_docs:
                        d_kid = d["knowledge_id"]
                        d_target = del_ingr if del_type == "ingredient" else (del_name if del_type in ("name", "image") else (d.get("target_item") or target_item))
                        r_del = await GeneralKnowledgeService.apply_delete(
                            knowledge_id=d_kid,
                            target_item=d_target,
                            delete_type=del_type,
                            vector_store=target_vs,
                            bm25_index=target_bm25,
                            db=db_session
                        )
                        del_results.append(r_del)

                any_succ = any(r.get("success") for r in del_results)
                if any_succ:
                    all_deleted_products = []
                    for r in del_results:
                        for p in r.get("deleted_products", []):
                            if p not in all_deleted_products:
                                all_deleted_products.append(p)

                    prods_str = f" ({', '.join(all_deleted_products)})" if all_deleted_products else ""

                    if del_type == "image":
                        target_prod_disp = target_item or del_name
                        if target_prod_disp:
                            succ_msg = f"Gambar untuk produk \"{target_prod_disp}\" telah berhasil dihapus. Informasi produk tetap tersimpan di knowledge base."
                        else:
                            succ_msg = "Gambar telah berhasil dihapus dari knowledge base. Informasi produk tetap tersimpan."
                    elif del_type == "ingredient":
                        target_disp = del_ingr or target_item
                        succ_msg = f"Seluruh produk yang mengandung \"{target_disp}\"{prods_str} telah berhasil dihapus dari knowledge base. Knowledge base telah diperbarui."
                    elif del_type == "name":
                        target_name_disp = del_name or target_item
                        succ_msg = f"Produk \"{target_name_disp}\"{prods_str} telah berhasil dihapus dari knowledge base. Knowledge base telah diperbarui."
                    else:
                        succ_msg = f"\"{target_item}\"{prods_str} telah berhasil dihapus dari knowledge base. Knowledge base telah diperbarui."

                    updated_doc_summaries = [r.get("summary", "") for r in del_results if r.get("summary")]
                    combined_summary = "\n\n".join(updated_doc_summaries) if updated_doc_summaries else ""
                    formatted_ans = format_chat_response_with_cards(
                        confirmation=succ_msg,
                        summary=combined_summary,
                        target_product_names=[target_prod_disp] if del_type == "image" and target_prod_disp else None,
                        intro_label="Berikut adalah detail produk yang diperbarui:" if del_type == "image" else "Berikut adalah daftar produk yang diperbarui:"
                    )

                    return QueryGeneralResponse(
                        type="answer",
                        message=formatted_ans,
                        prompt=user_prompt,
                        answer=formatted_ans,
                        action="delete_applied",
                        target_knowledge_id=target_kid,
                        total_found=len(matched_docs),
                        results=[]
                    )
                else:
                    errs = [r.get("error", "Unknown error") for r in del_results if not r.get("success")]
                    fail_msg = f"Gagal menghapus item: {'; '.join(errs)}"
                    return QueryGeneralResponse(
                        type="answer",
                        message=fail_msg,
                        prompt=user_prompt,
                        answer=fail_msg,
                        action="delete_failed",
                        target_knowledge_id=target_kid,
                        total_found=0,
                        results=[]
                    )
            else:
                not_found_msg = "Target produk atau kandungan yang ingin dihapus tidak ditemukan dalam knowledge base."
                return QueryGeneralResponse(
                    type="answer",
                    message=not_found_msg,
                    prompt=user_prompt,
                    answer=not_found_msg,
                    action="read",
                    target_knowledge_id=None,
                    total_found=0,
                    results=[]
                )

        # -------------------------------------------------------------
        # PHASE 3: Dedicated RAG Pipeline (READ)
        # -------------------------------------------------------------
        # 3.1 Validate explicit UUIDs in prompt
        uuid_matches = re.findall(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', user_prompt)
        if uuid_matches:
            for requested_uuid in uuid_matches:
                if not resolve_approved_file(requested_uuid):
                    logger.info(f"[QUERY-GENERAL] Requested document '{requested_uuid}' is not in approved KB.")
                    return QueryGeneralResponse(
                        prompt=user_prompt,
                        answer="Untuk saat ini informasi tersebut belum tersedia.",
                        action="read",
                        target_knowledge_id=None,
                        total_found=0,
                        results=[]
                    )

        # 3.2 Dynamic top_k calculation
        broad_keywords = [
            "semua", "lengkap", "runtut", "seluruh", "jurnal", "paper", "katalog", "tabel",
            "daftar", "sebutkan", "jelaskan", "kandungan", "manfaat", "hasil", "penelitian", "metode",
            "perbedaan", "beda", "bandingkan", "perbandingan", "vs", "versus", "komparasi", "list"
        ]
        q_lower = effective_prompt.lower()
        is_broad = any(kw in q_lower for kw in broad_keywords)
        general_top_k = 18 if is_broad else 10

        # 3.3 Execute Unified Generation Pipeline (100% parity with Mock CIS)
        response_dict = pipeline.generate_answer(
            query=effective_prompt,
            top_k=general_top_k,
            rerank=True,
            history=request.history or [],
            doctor_name="Admin"
        )

        clean_answer = response_dict.get("answer", "")
        results = response_dict.get("results", [])

        return QueryGeneralResponse(
            type="answer",
            message=clean_answer,
            prompt=user_prompt,
            answer=clean_answer,
            action="read",
            target_knowledge_id=None,
            total_found=len(results),
            results=results
        )

    except Exception as e:
        logger.error(f"Query General endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/ingest/reset", tags=["Ingestion"], summary="Reset Database")
async def reset_database(
    vector_store: BaseVectorStoreAdapter = Depends(get_vector_store),
    bm25: BM25Index = Depends(get_bm25_index)
):
    """
    Clears all documents, text chunks, and vector embeddings from the Knowledge Base.
    """
    errors = []
    
    try:
        # 1. Clear vector store
        if vector_store:
            logger.info("Clearing PGVector database...")
            vector_store.clear_all()
        else:
            logger.warning("No vector store instance available for clearing.")
            
        # 2. Clear BM25
        if bm25:
            logger.info("Clearing BM25 index...")
            bm25.clear()
            bm25.save(settings.bm25_index_path)
            
        # 3. Clean files in data/pending/, data/output/, data/temp/ (including images)
        cleanup_extensions = (".json", ".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".jpg", ".jpeg", ".png", ".webp")
        for folder in ["data/pending", "data/output", "data/temp"]:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if f.lower().endswith(cleanup_extensions):
                        try:
                            os.remove(os.path.join(folder, f))
                        except Exception as file_err:
                            logger.warning(f"Could not remove file {f}: {file_err}")

        # 3.5. Clear MinIO S3 Object Storage (images & knowledge-documents buckets)
        try:
            from app.services.storage import clear_all_buckets
            minio_res = clear_all_buckets()
            logger.info(f"MinIO bucket reset completed: {minio_res}")
        except Exception as minio_err:
            logger.warning(f"MinIO bucket reset failed: {minio_err}")

        # 4. Soft-delete all records in PostgreSQL Knowledge table (MUST succeed)
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.knowledge import Knowledge
            from sqlalchemy import select, func

            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Knowledge).where(Knowledge.deleted_at.is_(None)))
                k_records = res.scalars().all()
                for k in k_records:
                    k.deleted_at = func.now()
                if k_records:
                    await session.commit()
                    logger.info(f"Soft-deleted {len(k_records)} Knowledge records in PostgreSQL DB.")
        except Exception as db_err:
            error_msg = f"CRITICAL: Failed to soft-delete Knowledge records in PostgreSQL: {db_err}"
            logger.error(error_msg)
            errors.append(error_msg)

        if errors:
            return {
                "status": "partial_success",
                "message": f"Knowledge base partially cleared. {len(errors)} error(s) occurred during reset.",
                "errors": errors
            }
                            
        return {"status": "success", "message": "Knowledge base (PGVector, BM25, staged/approved files, and PostgreSQL Knowledge DB) has been successfully cleared."}
    except Exception as e:
        logger.error(f"Reset database failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))




