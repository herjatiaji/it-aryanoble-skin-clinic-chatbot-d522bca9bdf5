import sys
import os
import logging
import time
import uuid
import re
from collections import deque
from typing import List, Optional, Dict, Any
from loguru import logger

# Thread-safe in-memory ring buffer for recent log lines (last 3,000 entries)
LOG_MEMORY_BUFFER = deque(maxlen=3000)

def _memory_log_sink(message):
    LOG_MEMORY_BUFFER.append(str(message).strip())

def redact_sensitive_data(text: str) -> str:
    """Mask tokens, passwords, authorization headers, or sensitive secrets from log strings."""
    if not isinstance(text, str):
        return text
    # Mask Bearer tokens / authorization headers
    text = re.sub(r'(Authorization:\s*Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    # Mask password fields in JSON / query strings
    text = re.sub(r'("password"\s*:\s*")[^"]+(")', r'\1[REDACTED]\2', text, flags=re.IGNORECASE)
    text = re.sub(r'(&password=)[^&]+', r'\1[REDACTED]', text, flags=re.IGNORECASE)
    return text

class InterceptHandler(logging.Handler):
    """
    Redirect standard logging (Uvicorn, FastAPI, SQLAlchemy, HTTPX) to Loguru.
    Separates HTTP access logs from business workflow logs.
    """
    def emit(self, record):
        # Ignore noisy periodic health check logs, Hugging Face cache checks, and teardown lifecycle logs
        message = record.getMessage()
        if (
            ("GET /health" in message and " 200" in message)
            or any(k in message for k in ["huggingface.co", "resolve-cache", "additional_chat_templates"])
            or message in ("close.started", "close.complete")
            or record.name == "logging"
        ):
            return

        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and getattr(frame, "f_code", None) and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        is_access = record.name == "uvicorn.access"
        clean_msg = redact_sensitive_data(message)

        try:
            if is_access:
                logger.opt(depth=depth, exception=record.exc_info).bind(channel="access").log(level, clean_msg)
            else:
                logger.opt(depth=depth, exception=record.exc_info).bind(channel="app").log(level, clean_msg)
        except Exception:
            # Fallback if frame depth optimization fails or if re-entrant logging occurs during process teardown
            try:
                if is_access:
                    logger.bind(channel="access").log(level, clean_msg)
                else:
                    logger.bind(channel="app").log(level, clean_msg)
            except Exception:
                pass

def _can_write_and_rotate_log(log_dir: str = "logs") -> bool:
    """
    Checks if the application has full POSIX permissions to write and rotate files in log_dir.
    Returns True if log rotation is safe, False if file logging should be skipped to prevent PermissionError.
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
        test_path = os.path.join(log_dir, ".perm_test.tmp")
        renamed_path = os.path.join(log_dir, ".perm_test_renamed.tmp")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("test")
        os.rename(test_path, renamed_path)
        os.remove(renamed_path)
        return True
    except Exception:
        return False

def stdout_filter(record):
    """
    Filters stdout logs:
    - Excludes HTTP access logs (uvicorn.access) at INFO level from terminal stdout to keep business workflow logs clean.
    - Permits access logs if log level is DEBUG.
    """
    channel = record["extra"].get("channel")
    name = record["name"]
    is_access_log = channel == "access" or name == "uvicorn.access"
    if is_access_log:
        return record["level"].name == "DEBUG"
    return True

def setup_logging(log_level: str = "INFO"):
    """
    Configures standard logging across the entire application:
    1. Intercepts standard Python logging (Uvicorn, SQLAlchemy, HTTPX, asyncio).
    2. Outputs formatted business logs to stdout without HTTP access noise.
    3. Persists HTTP access logs separately to logs/access.log.
    4. Persists full debug logs to logs/app.log.
    5. Records last 3,000 entries in in-memory buffer.
    """
    logger.remove() # Remove default handler
    
    # 1. Stdout handler (Clean colorized formatting, filtered for business workflows)
    logger.add(
        sys.stdout, 
        level=log_level,
        filter=stdout_filter,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # 2. Dedicated Access Log File handler (Separate channel for HTTP requests)
    if _can_write_and_rotate_log("logs"):
        try:
            logger.add(
                "logs/access.log",
                level="INFO",
                rotation="10 MB",
                retention="10 days",
                enqueue=True,
                catch=True,
                encoding="utf-8",
                filter=lambda record: record["extra"].get("channel") == "access" or record["name"] == "uvicorn.access",
                format="{time:YYYY-MM-DD HH:mm:ss} | {message}"
            )
            logger.add(
                "logs/app.log", 
                level="DEBUG",
                rotation="10 MB",
                retention="10 days",
                enqueue=True,
                catch=True,
                encoding="utf-8",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
            )
        except Exception as err:
            sys.stderr.write(f"Warning: Could not initialize log files: {err}\n")
    else:
        sys.stderr.write("Notice: Directory 'logs' lacks file rotation permissions. Running via stdout + memory buffer.\n")

    # 3. In-memory buffer sink for web API query (enqueue=False to avoid worker thread lock conflicts during subprocess spawn/exit)
    logger.add(
        _memory_log_sink,
        level="DEBUG",
        enqueue=False,
        catch=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )

    # 4. Intercept standard library loggers
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for noisy in ("botocore", "boto3", "s3transfer", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy.engine", "httpx", "urllib3", "huggingface_hub", "transformers", "sentence_transformers"):
        mod_logger = logging.getLogger(logger_name)
        mod_logger.handlers = [InterceptHandler()]
        mod_logger.propagate = False
    
    logger.info("Universal logging configured successfully (stdout + access.log + app.log + memory buffer).")


class ApprovalTrace:
    """
    Structured Business Logger for Knowledge Approval / Ingestion / Mutation Workflows.
    Correlates operations with operation_id, batch_id, and knowledge_id, tracking individual stage timing & final results.
    """
    def __init__(self, knowledge_id: str, batch_id: Optional[str] = None, operation_id: Optional[str] = None):
        self.operation_id = operation_id or uuid.uuid4().hex[:12]
        self.knowledge_id = str(knowledge_id)
        self.batch_id = str(batch_id) if batch_id else "N/A"
        self.t0_total = time.time()
        self.stages: List[Dict[str, Any]] = []
        self.total_documents = 1
        self.approved = 0
        self.failed = 0
        self.total_chunks = 0
        self.embedding_count = 0
        self.bm25_status = "PENDING"
        self.storage_status = "PENDING"
        self.status = "IN_PROGRESS"

        logger.info(f"[APPROVAL] {self.operation_id} START | knowledge_id={self.knowledge_id} batch_id={self.batch_id}")

    def log_stage(self, stage_name: str, duration_ms: int, status: str = "SUCCESS", count: Optional[int] = None, detail: Optional[str] = None):
        self.stages.append({
            "stage": stage_name,
            "duration_ms": duration_ms,
            "status": status,
            "count": count,
            "detail": detail
        })
        icon = "✓" if status == "SUCCESS" else "❌"
        count_str = f" (count={count})" if count is not None else ""
        logger.info(f"[APPROVAL] {self.operation_id} {stage_name:<14} {duration_ms:>5}ms  {icon}{count_str}")

    def complete(self, approved_count: int = 1, failed_count: int = 0, total_chunks: int = 0, embedding_count: int = 0, bm25_status: str = "SUCCESS", storage_status: str = "SUCCESS") -> int:
        total_duration_ms = int((time.time() - self.t0_total) * 1000)
        self.approved = approved_count
        self.failed = failed_count
        self.total_chunks = total_chunks
        self.embedding_count = embedding_count
        self.bm25_status = bm25_status
        self.storage_status = storage_status
        self.status = "SUCCESS" if failed_count == 0 else "FAILED"

        stages_formatted = ""
        for s in self.stages:
            st_name = s["stage"]
            d_ms = s["duration_ms"]
            st_res = s["status"]
            stages_formatted += f"{st_name:<14} : {d_ms:>5} ms  {st_res}\n"

        summary_box = (
            f"\n============================================================\n"
            f"KNOWLEDGE APPROVAL\n"
            f"============================================================\n"
            f"operation_id : {self.operation_id}\n"
            f"batch_id     : {self.batch_id}\n"
            f"knowledge_id : {self.knowledge_id}\n"
            f"status       : {self.status}\n\n"
            f"STAGES\n"
            f"------------------------------------------------------------\n"
            f"{stages_formatted}"
            f"RESULT\n"
            f"------------------------------------------------------------\n"
            f"documents     : {self.total_documents}\n"
            f"approved      : {self.approved}\n"
            f"chunks        : {self.total_chunks}\n"
            f"embeddings    : {self.embedding_count}\n"
            f"bm25_status   : {self.bm25_status}\n"
            f"storage_status: {self.storage_status}\n"
            f"failed        : {self.failed}\n"
            f"total         : {total_duration_ms} ms\n"
            f"============================================================\n"
        )
        logger.info(summary_box)
        logger.info(f"[APPROVAL] {self.operation_id} COMPLETE {total_duration_ms}ms  ✓")
        return total_duration_ms

    def fail(self, failed_stage: str, error_message: str) -> int:
        total_duration_ms = int((time.time() - self.t0_total) * 1000)
        self.status = "FAILED"
        self.failed = 1
        
        stages_formatted = ""
        for s in self.stages:
            st_name = s["stage"]
            d_ms = s["duration_ms"]
            st_res = s["status"]
            stages_formatted += f"{st_name:<14} : {d_ms:>5} ms  {st_res}\n"

        summary_box = (
            f"\n============================================================\n"
            f"KNOWLEDGE APPROVAL (FAILED)\n"
            f"============================================================\n"
            f"operation_id : {self.operation_id}\n"
            f"batch_id     : {self.batch_id}\n"
            f"knowledge_id : {self.knowledge_id}\n"
            f"status       : FAILED\n"
            f"failed_stage : {failed_stage}\n"
            f"error        : {error_message}\n\n"
            f"STAGES\n"
            f"------------------------------------------------------------\n"
            f"{stages_formatted}"
            f"============================================================\n"
        )
        logger.error(summary_box)
        logger.error(f"[APPROVAL] {self.operation_id} FAILED at {failed_stage} after {total_duration_ms}ms ❌")
        return total_duration_ms


def get_recent_logs(lines: int = 300, level: Optional[str] = None, search: Optional[str] = None) -> List[str]:
    """Retrieve recent log lines from memory buffer or logs/app.log."""
    raw_logs = list(LOG_MEMORY_BUFFER)
    
    # Fallback to reading logs/app.log if buffer is empty
    if not raw_logs and os.path.exists("logs/app.log"):
        try:
            with open("logs/app.log", "r", encoding="utf-8", errors="ignore") as f:
                raw_logs = [line.strip() for line in f.readlines() if line.strip()]
        except Exception:
            pass
            
    filtered = raw_logs
    if level:
        lvl_upper = level.upper()
        filtered = [l for l in filtered if f"| {lvl_upper}" in l or f"[{lvl_upper}]" in l]
        
    if search:
        s_lower = search.lower()
        filtered = [l for l in filtered if s_lower in l.lower()]
        
    return filtered[-lines:]


