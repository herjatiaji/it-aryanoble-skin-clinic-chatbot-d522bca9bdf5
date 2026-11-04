import math
import re
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from app.rag.canonical import (
    ImageType,
    ImageDisplayPolicy,
    ImageRelevance,
    ImageSemanticRole,
    ImageOrigin,
    PDFContext,
    ImageProvenance,
    generate_stable_image_id,
)

# Universal Geometric Title & Content Prominence Thresholds
# No hardcoded domain product dictionaries or brand watermarks

def compute_bbox_center(bbox: List[float]) -> Tuple[float, float]:
    """Computes (cx, cy) center coordinate from bbox [x0, y0, x1, y1]."""
    x0, y0, x1, y1 = bbox[:4]
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def compute_distance(pt1: Tuple[float, float], pt2: Tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)


class SpatialImageTextAssociator:
    """
    Associates embedded images and page regions with extracted OCR text entities
    using a multi-factor scoring formula:
      Score = 0.35 * distance + 0.25 * region + 0.25 * semantic_match + 0.15 * visual_feature
    """

    def __init__(self):
        pass

    def associate_page_elements(
        self,
        document_id: str,
        page_num: int,
        page_width: float,
        page_height: float,
        ocr_blocks: List[Dict[str, Any]],
        embedded_images: List[Dict[str, Any]],
        pdf_context: PDFContext = PDFContext.FLATTENED_DESIGN
    ) -> List[ImageProvenance]:
        """
        Analyzes embedded images on a page, evaluates spatial & semantic correlation
        with OCR text blocks, and generates deterministic ImageProvenance objects.
        """
        if not embedded_images:
            return []

        provenance_list: List[ImageProvenance] = []

        def _is_top_corner_banner(b: Dict[str, Any]) -> bool:
            bbox = b.get("bbox", [0, 0, 0, 0])
            bx0, by0, bx1, by1 = bbox[:4]
            bcx, bcy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
            return (bcy < 0.12 * page_height and (bcx < 0.28 * page_width or bcx > 0.85 * page_width))

        # 1. Detect Primary Title from OCR blocks based on geometric prominence (top 45%, largest font size)
        primary_title = None
        candidate_titles = []
        for b in ocr_blocks:
            txt = (b.get("text") or "").strip()
            bbox = b.get("bbox", [0, 0, 0, 0])
            y_top = bbox[1]
            h_box = abs(bbox[3] - bbox[1])
            if len(txt) > 3 and y_top < (page_height * 0.45) and not _is_top_corner_banner(b):
                lines = [l for l in txt.split("\n") if l.strip()]
                line_count = max(1, len(lines))
                # Skip category matrix navigation strips (e.g. Skin Type, Cleanser, Toner, Serum...)
                if line_count >= 4 and any(k in txt.lower() for k in ["cleanser", "toner", "serum", "skin type"]):
                    continue
                font_size = h_box / line_count
                # Prominence score: large font size + top position - penalty for lengthy body paragraph text
                score = font_size * 3.0 + (1.0 - (y_top / max(1.0, page_height * 0.45))) * 25.0 - (0.25 * max(0, len(txt) - 60))
                candidate_titles.append((score, txt))

        if candidate_titles:
            candidate_titles.sort(key=lambda x: x[0], reverse=True)
            primary_title = candidate_titles[0][1]

        diag_len = math.sqrt(page_width ** 2 + page_height ** 2)

        for img in embedded_images:
            xref = img.get("xref", 0)
            rect = img.get("rect")  # fitz.Rect [x0, y0, x1, y1]
            if not rect:
                continue

            img_bbox = [rect.x0, rect.y0, rect.x1, rect.y1]
            img_cx, img_cy = compute_bbox_center(img_bbox)
            img_w = abs(rect.x1 - rect.x0)
            img_h = abs(rect.y1 - rect.y0)
            native_w = img.get("width", img_w)
            native_h = img.get("height", img_h)

            # Check if this image is a text container card (flat/horizontal box containing text blocks)
            text_blocks_inside = 0
            for b in ocr_blocks:
                b_cx, b_cy = compute_bbox_center(b.get("bbox", [0, 0, 0, 0]))
                if (rect.x0 - 5 <= b_cx <= rect.x1 + 5) and (rect.y0 - 5 <= b_cy <= rect.y1 + 5):
                    text_blocks_inside += 1

            aspect_ratio = native_h / max(1.0, native_w)
            pixel_area = native_w * native_h
            is_background_card = aspect_ratio < 0.75 or aspect_ratio > 4.0
            # Only flat/horizontal images with text inside are background container cards
            is_text_container = (aspect_ratio < 0.85) and (text_blocks_inside >= 1)
            is_margin_decor = img_cx < (page_width * 0.12) or img_cx > (page_width * 0.98)

            # 1. Distance Score: Proximity to primary title
            best_dist_score = 0.5
            if primary_title:
                for b in ocr_blocks:
                    if b.get("text") == primary_title:
                        t_cx, t_cy = compute_bbox_center(b.get("bbox", [0, 0, 0, 0]))
                        d = compute_distance((img_cx, img_cy), (t_cx, t_cy))
                        norm_d = min(1.0, d / max(1.0, diag_len))
                        best_dist_score = max(0.0, 1.0 - norm_d)
                        break

            # 2. Region Score: Symmetric positioning within the primary content display zone
            region_score = 0.75
            if (page_height * 0.12) < img_cy < (page_height * 0.88):
                region_score = min(1.0, region_score + 0.20)
            if (page_width * 0.04) <= img_cx <= (page_width * 0.96):
                region_score = min(1.0, region_score + 0.05)

            # 3. Semantic Match: Nearby substantive text (labels, descriptions, specifications)
            nearby_texts = []
            for b in ocr_blocks:
                b_cx, b_cy = compute_bbox_center(b.get("bbox", [0, 0, 0, 0]))
                d_to_img = compute_distance((img_cx, img_cy), (b_cx, b_cy))
                if d_to_img < (diag_len * 0.35):
                    txt_cand = (b.get("text") or "").strip()
                    if len(txt_cand) > 3:
                        nearby_texts.append(txt_cand)

            substantive_word_count = sum(len(t.split()) for t in nearby_texts)
            semantic_score = min(1.0, substantive_word_count / 15.0)

            # 4. Visual Feature Score: Aspect ratio & pixel area (Universal: supports bottles, jars, devices, landscape photos)
            visual_feature_score = 0.05
            if not is_text_container and not is_background_card and not is_margin_decor:
                # Vertical packaging (bottle, tube, dropper, handpiece applicator)
                if 1.15 <= aspect_ratio <= 3.8 and pixel_area > 35000:
                    visual_feature_score = 1.0
                # Square packaging (jar, cream pot, product box, device console)
                elif 0.75 <= aspect_ratio <= 1.25 and pixel_area > 35000:
                    visual_feature_score = 0.90
                # Wide landscape product / clinical before-after / medical system photo
                elif 0.35 <= aspect_ratio < 0.75 and pixel_area > 40000:
                    visual_feature_score = 0.85
                # General substantive media asset
                elif 0.30 <= aspect_ratio <= 4.0 and pixel_area > 25000:
                    visual_feature_score = 0.70

            # Combined Multi-Factor Association Score
            final_score = (
                0.35 * best_dist_score +
                0.25 * region_score +
                0.25 * semantic_score +
                0.15 * visual_feature_score
            )

            # Classification & Policy Assignment:
            is_genuine_product = visual_feature_score >= 0.70 and final_score >= 0.55

            if is_genuine_product:
                image_type = ImageType.PRODUCT
                display_policy = ImageDisplayPolicy.INCLUDE
                image_relevance = ImageRelevance.RELEVANT
                semantic_role = ImageSemanticRole.PRODUCT_REFERENCE
                linked_product = primary_title
                reason = (
                    f"Product/clinical media linked to '{primary_title}' "
                    f"(score={final_score:.2f}, aspect={aspect_ratio:.2f})"
                )
            else:
                is_logo_or_brand = (img_cy < page_height * 0.12 and (img_cx < page_width * 0.28 or img_cx > page_width * 0.80)) or visual_feature_score < 0.4
                image_type = ImageType.DOCUMENT_LOGO if (is_logo_or_brand and visual_feature_score < 0.5) else ImageType.DECORATIVE
                display_policy = ImageDisplayPolicy.EXCLUDE
                image_relevance = ImageRelevance.IRRELEVANT
                semantic_role = ImageSemanticRole.DOCUMENT_DECORATION
                linked_product = None
                reason = (
                    f"Excluded non-substantive asset (area={pixel_area}, aspect={aspect_ratio:.2f}, "
                    f"is_container={is_text_container}, score={final_score:.2f})"
                )

            target_url = img.get("target_url") or f"/api/storage/images/doc_{document_id}_p{page_num}_{xref}.jpeg"
            stable_id = generate_stable_image_id(
                document_id=document_id,
                page_or_sheet=page_num,
                target_url=target_url,
                image_index=xref
            )

            provenance = ImageProvenance(
                image_id=stable_id,
                document_id=document_id,
                source_document=img.get("source_document", ""),
                page_or_sheet=page_num,
                image_index=xref,
                target_url=target_url,
                alt_text=linked_product or "Product Image",
                image_origin=ImageOrigin.EMBEDDED_ASSET,
                extraction_source="embedded_image",
                pdf_context=pdf_context,
                image_type=image_type,
                image_relevance=image_relevance,
                display_policy=display_policy,
                semantic_role=semantic_role,
                linked_product=linked_product,
                confidence=round(final_score, 3),
                classification_reason=reason
            )

            provenance_list.append(provenance)
            logger.info(
                f"🏷️ [SPATIAL-ASSOCIATOR] Page {page_num} Img xref {xref} ({native_w}x{native_h}) "
                f"-> {provenance.image_type.value.upper()} [{provenance.display_policy.value.upper()}] "
                f"linked='{provenance.linked_product}' (score={final_score:.3f})"
            )

        return provenance_list
