import sys
import os
import logging

# --- Suppress HuggingFace progress bars & warnings at module-level ---
# Must be set BEFORE any HuggingFace/tqdm libraries are imported.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

from loguru import logger


def setup_logging(log_level: str = "INFO"):
    """
    Configures application-wide logging using Loguru.
    - Terminal (stdout): Clean output, only app-level logs at INFO+
    - File (logs/rag_system.log): Full DEBUG logs including all libraries

    Also suppresses noisy third-party libraries from polluting the terminal.
    """
    # --- Silence noisy third-party libraries in terminal ---
    _SILENT_LIBS = [
        "transformers",
        "huggingface_hub",
        "sentence_transformers",
        "tqdm",
        "httpx",
        "httpcore",
        "filelock",
        "tokenizers",
        "torch",
        "PIL",
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_google_genai",
        "langchain_huggingface",
        "docling",
        "docling_core",
        "pypdfium2",
    ]
    for lib in _SILENT_LIBS:
        logging.getLogger(lib).setLevel(logging.ERROR)

    # --- Remove default Loguru handler ---
    logger.remove()

    # --- Ensure logs directory exists ---
    os.makedirs("logs", exist_ok=True)

    # --- Terminal handler: clean, INFO+ only, app logs only ---
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        filter=lambda record: record["name"].startswith("backend.")
        or record["name"].startswith("evaluation."),
        colorize=True,
    )

    # --- File handler: full DEBUG, all logs including libraries ---
    logger.add(
        "logs/rag_system.log",
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
    )

    logger.info("Logging configured. Terminal: app logs only | File: full debug.")
