import uuid
from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from app.models.user import User, UserType, UserTokenUsage
from app.models.branch import Branch
from app.models.config import AppConfig
from app.models.ingestion_usage import IngestionTokenUsage
from app.core.config import settings


async def get_app_config_value(db: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
    stmt = select(AppConfig.value).where(AppConfig.key == key)
    res = await db.execute(stmt)
    val = res.scalar_one_or_none()
    return val if val is not None else default


async def check_chat_token_quota(
    db: AsyncSession,
    user: User,
    branch_id: Optional[uuid.UUID]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check whether a chat request is allowed based on the active token allocation mode:
    - Mode ON (Global Config = ON):
      * Token limit is determined per branch (Shared Branch Pool).
      * No individual doctor limit per branch (doctor can chat as long as their active branch has tokens).
    - Mode OFF (Global Config = OFF):
      * Strict individual limit per doctor.
      * Strict individual limit per branch.
    - Staff / Admin / Functional Dept:
      * Tracked by usage without hard doctor blocking.
    """
    # 1. Staff and Admin accounts are tracked by usage without hard doctor block
    if user.type == UserType.STAFF:
        return True, "OK", {"mode": "staff_by_usage"}

    # 2. Doctor must be assigned to an active clinic branch
    if not branch_id:
        return False, "Doctor is not assigned to an active clinic branch.", {
            "mode": "blocked_no_branch",
            "reason": "no_branch_assigned"
        }

    b_stmt = select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    branch_res = await db.execute(b_stmt)
    branch = branch_res.scalar_one_or_none()

    if not branch:
        return False, "Clinic branch not found or has been deactivated.", {
            "mode": "blocked_branch_not_found",
            "reason": "branch_not_found"
        }

    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    is_global_mode = (await get_app_config_value(db, "GLOBAL_TOKEN_LIMIT_ACTIVE", "false")).lower() == "true"

    if is_global_mode:
        # --- Mode ON: Granular checks per active sub-setting ---
        is_threshold_active = (await get_app_config_value(db, "GLOBAL_THRESHOLD_ACTIVE", "false")).lower() == "true"
        is_branch_global_active = (await get_app_config_value(db, "GLOBAL_BRANCH_LIMIT_ACTIVE", "false")).lower() == "true"
        is_spkk_global_active = (await get_app_config_value(db, "GLOBAL_SPKK_LIMIT_ACTIVE", "false")).lower() == "true"
        is_gp_global_active = (await get_app_config_value(db, "GLOBAL_GP_LIMIT_ACTIVE", "false")).lower() == "true"

        # 1. Global Monthly Threshold Check (if active, cap system-wide total token consumption)
        if is_threshold_active:
            thresh_str = await get_app_config_value(db, "GLOBAL_TOKEN_THRESHOLD", "1000000")
            threshold_limit = int(thresh_str) if (thresh_str and thresh_str.isdigit()) else 1000000

            tot_chat_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(UserTokenUsage.year_month == current_ym)
            tot_chat_used = (await db.execute(tot_chat_stmt)).scalar() or 0

            tot_ingest_stmt = select(func.sum(IngestionTokenUsage.tokens_used)).where(IngestionTokenUsage.year_month == current_ym)
            tot_ingest_used = (await db.execute(tot_ingest_stmt)).scalar() or 0

            total_global_used = tot_chat_used + tot_ingest_used
            if total_global_used >= threshold_limit:
                return False, f"Global monthly token threshold ({threshold_limit:,}) has been reached.", {
                    "mode": "global_threshold",
                    "threshold_limit": threshold_limit,
                    "tokens_used": total_global_used,
                    "reason": "global_threshold_exceeded"
                }

        # 2. Branch limit check (Custom Branch Limit OR Shared Global Pool OR fallback to Global Threshold)
        has_branch_custom = getattr(branch, "has_custom_limit", False) is True
        if has_branch_custom:
            branch_limit = branch.token_limit if branch.token_limit is not None else 0
            if branch_limit <= 0:
                return False, f"Branch '{branch.name}' token limit is set to 0 tokens. Please contact your administrator.", {
                    "mode": "branch_custom",
                    "branch_limit": 0,
                    "reason": "branch_limit_zero"
                }
        elif is_branch_global_active:
            global_branch_limit_str = await get_app_config_value(db, "GLOBAL_TOKEN_LIMIT", None)
            branch_limit = int(global_branch_limit_str) if (global_branch_limit_str and global_branch_limit_str.isdigit()) else 0
        else:
            branch_limit = branch.token_limit or 0

        # If branch limit is unallocated (<= 0), check if Global Threshold is active as a fallback pool
        if branch_limit <= 0:
            if not is_threshold_active:
                return False, f"Branch '{branch.name}' token limit has not been allocated (0 tokens). Please contact your administrator to set a token quota.", {
                    "mode": "branch_custom" if has_branch_custom else ("global_shared" if is_branch_global_active else "branch_individual"),
                    "branch_limit": 0,
                    "reason": "branch_limit_zero"
                }
        else:
            branch_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
                UserTokenUsage.branch_id == branch.id,
                UserTokenUsage.year_month == current_ym
            )
            branch_used = (await db.execute(branch_usage_stmt)).scalar() or 0
            if branch_used >= branch_limit:
                pool_label = "custom monthly token limit" if has_branch_custom else ("global monthly token pool" if is_branch_global_active else "monthly token limit")
                return False, f"Branch '{branch.name}' {pool_label} ({branch_limit:,}) is exhausted for this month.", {
                    "mode": "branch_custom" if has_branch_custom else ("global_shared" if is_branch_global_active else "branch_individual"),
                    "branch_limit": branch_limit,
                    "branch_used": branch_used,
                    "reason": "branch_limit_exceeded"
                }

        # 2. Doctor limit check (Custom override OR Doctor Type Global Quota OR Branch Pool)
        if user.token_limit is not None and user.token_limit > 0:
            doc_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
                UserTokenUsage.user_id == user.id,
                UserTokenUsage.year_month == current_ym
            )
            doc_used = (await db.execute(doc_usage_stmt)).scalar() or 0
            if doc_used >= user.token_limit:
                return False, f"Individual monthly token limit ({user.token_limit:,}) has been exceeded.", {
                    "mode": "global_override",
                    "doc_limit": user.token_limit,
                    "doc_used": doc_used,
                    "reason": "individual_doctor_limit_exceeded"
                }
        else:
            # Evaluate global doctor type quotas if active
            dr_type_clean = (user.dr_type or "").upper()
            is_spkk = any(k in dr_type_clean for k in ["SPDVE", "SP.DVE", "SPKK", "SP.KK", "SPDV"])
            is_gp = any(k in dr_type_clean for k in ["GP", "GP PLUS", "UMUM"])

            effective_doc_quota = None
            if is_spkk and is_spkk_global_active:
                spkk_str = await get_app_config_value(db, "TOKEN_LIMIT_SPKK", "500000")
                effective_doc_quota = int(spkk_str) if (spkk_str and spkk_str.isdigit()) else 500000
            elif is_gp and is_gp_global_active:
                gp_str = await get_app_config_value(db, "TOKEN_LIMIT_GP", "250000")
                effective_doc_quota = int(gp_str) if (gp_str and gp_str.isdigit()) else 250000

            if effective_doc_quota is not None:
                if effective_doc_quota <= 0:
                    type_label = "SpDVE" if is_spkk else "GP Plus"
                    return False, f"{type_label} global token limit is set to 0. Please contact your administrator.", {
                        "mode": "doctor_type_quota",
                        "doc_limit": 0,
                        "reason": "doctor_type_quota_zero"
                    }

                doc_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
                    UserTokenUsage.user_id == user.id,
                    UserTokenUsage.year_month == current_ym
                )
                doc_used = (await db.execute(doc_usage_stmt)).scalar() or 0
                if doc_used >= effective_doc_quota:
                    type_label = "SpDVE" if is_spkk else "GP Plus"
                    return False, f"{type_label} global monthly token limit ({effective_doc_quota:,}) has been exceeded.", {
                        "mode": "doctor_type_quota",
                        "doc_limit": effective_doc_quota,
                        "doc_used": doc_used,
                        "reason": "doctor_type_quota_exceeded"
                    }

        return True, "OK", {"mode": "global_granular"}

    else:
        # --- Mode OFF: Strict individual doctor limit & strict individual branch limit ---
        # 1. Branch limit check (Strict: Must be > 0 and not exceeded)
        branch_limit = branch.token_limit or 0
        if branch_limit <= 0:
            return False, f"Branch '{branch.name}' token limit has not been allocated (0 tokens). Please contact your administrator to set a token quota.", {
                "mode": "individual",
                "branch_limit": 0,
                "reason": "branch_limit_zero"
            }

        branch_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
            UserTokenUsage.branch_id == branch.id,
            UserTokenUsage.year_month == current_ym
        )
        branch_used = (await db.execute(branch_usage_stmt)).scalar() or 0
        if branch_used >= branch_limit:
            return False, f"Branch '{branch.name}' monthly token limit ({branch_limit:,}) has been reached.", {
                "mode": "individual",
                "branch_limit": branch_limit,
                "branch_used": branch_used,
                "reason": "branch_limit_exceeded"
            }

        # 2. Individual doctor limit (applied only if positive custom override is set)
        if user.token_limit is not None and user.token_limit > 0:
            doc_usage_stmt = select(func.sum(UserTokenUsage.tokens_used)).where(
                UserTokenUsage.user_id == user.id,
                UserTokenUsage.year_month == current_ym
            )
            doc_used = (await db.execute(doc_usage_stmt)).scalar() or 0
            if doc_used >= user.token_limit:
                return False, f"Individual monthly token limit ({user.token_limit:,}) has been exceeded.", {
                    "mode": "individual",
                    "doc_limit": user.token_limit,
                    "doc_used": doc_used,
                    "reason": "individual_doctor_limit_exceeded"
                }

        return True, "OK", {"mode": "individual"}


async def record_chat_token_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    branch_id: Optional[uuid.UUID],
    input_tokens: int,
    output_tokens: int
):
    """
    Record prompt (input) and completion (output) tokens for a doctor chat turn.
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return

    total_tokens = input_tokens + output_tokens
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")

    branch_filter = UserTokenUsage.branch_id.is_(None) if branch_id is None else (UserTokenUsage.branch_id == branch_id)
    stmt = select(UserTokenUsage).where(
        UserTokenUsage.user_id == user_id,
        branch_filter,
        UserTokenUsage.year_month == current_ym
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.tokens_used += total_tokens
    else:
        record = UserTokenUsage(
            user_id=user_id,
            branch_id=branch_id,
            year_month=current_ym,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=total_tokens
        )
        db.add(record)

    await db.commit()
    logger.info(f"Recorded chat token usage for user {user_id}, branch {branch_id}: in={input_tokens}, out={output_tokens}, total={total_tokens}")


async def check_ingestion_quota(db: AsyncSession) -> Tuple[bool, Dict[str, Any]]:
    """
    Check monthly ingestion token limit (Global Token Threshold) and calculate warning state (>= 90%) and exceeded state (>= 100%).
    Returns is_allowed=True (soft warning/notice model) to avoid disrupting document knowledge ingestion.
    """
    config_val = await get_app_config_value(db, "GLOBAL_TOKEN_THRESHOLD", None)
    if not config_val or not config_val.isdigit():
        config_val = await get_app_config_value(db, "INGESTION_MONTHLY_TOKEN_LIMIT", None)

    if config_val and config_val.isdigit():
        limit = int(config_val)
    else:
        limit = getattr(settings, "INGESTION_MONTHLY_TOKEN_LIMIT", 1000000)

    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")

    stmt = select(IngestionTokenUsage).where(IngestionTokenUsage.year_month == current_ym)
    result = await db.execute(stmt)
    usage = result.scalar_one_or_none()

    used = usage.tokens_used if usage else 0
    docs_count = usage.documents_count if usage else 0
    percentage = (used / limit * 100) if limit > 0 else 0.0

    is_warning = (percentage >= 90.0 and percentage < 100.0) if limit > 0 else False
    is_exceeded = (percentage >= 100.0) if limit > 0 else False
    is_allowed = True # Soft warning: ingestion proceeds without blocking

    return is_allowed, {
        "year_month": current_ym,
        "tokens_used": used,
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "token_limit": limit,
        "percentage": round(percentage, 1),
        "documents_count": docs_count,
        "warning": is_warning,
        "exceeded": is_exceeded
    }


async def record_ingestion_token_usage(
    db: AsyncSession,
    input_tokens: int,
    output_tokens: int,
    documents_count: int = 1
):
    """
    Record document processing, chunking, and AI summary tokens for ingestion.
    """
    if input_tokens <= 0 and output_tokens <= 0 and documents_count <= 0:
        return

    total_tokens = input_tokens + output_tokens
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")

    stmt = select(IngestionTokenUsage).where(IngestionTokenUsage.year_month == current_ym)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.tokens_used += total_tokens
        record.documents_count += documents_count
    else:
        record = IngestionTokenUsage(
            year_month=current_ym,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=total_tokens,
            documents_count=documents_count
        )
        db.add(record)

    await db.commit()
    logger.info(f"Recorded ingestion token usage: in={input_tokens}, out={output_tokens}, total={total_tokens}, docs={documents_count}")


async def record_knowledge_not_found_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    branch_id: Optional[uuid.UUID],
    user_query: str
):
    """
    Records a KNOWLEDGE_NOT_FOUND alert when a doctor asks a question that yields no matching KB context.
    Publishes real-time notification to Admin SSE channel and logs audit alert.
    """
    logger.warning(
        f"⚠️ [KNOWLEDGE_NOT_FOUND_ALERT] User '{user_id}' (Branch: '{branch_id}') "
        f"asked: '{user_query}' — No matching KB documents found."
    )
    try:
        from app.core.broadcaster import broadcaster
        import json
        event_payload = json.dumps({
            "event_type": "KNOWLEDGE_NOT_FOUND",
            "user_id": str(user_id),
            "branch_id": str(branch_id) if branch_id else None,
            "query": user_query,
            "message": f"Pertanyaan dokter tidak ditemukan di Knowledge Base: '{user_query}'"
        })
        await broadcaster.publish(event_payload)
    except Exception as err:
        logger.debug(f"Broadcasting KNOWLEDGE_NOT_FOUND event failed: {err}")

