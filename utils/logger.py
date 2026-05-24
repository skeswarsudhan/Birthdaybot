"""
utils/logger.py — Centralised logging for Birthday Bot.

Configures loguru to write to:
  - Console (stdout) with colours
  - logs/birthday_bot.log with daily rotation and 7-day retention

Usage:
    from utils.logger import logger, log_event

    logger.info("Plain loguru message")
    log_event("INFO", "birthday_scanned", detail="Test Employee")
"""

import sys
from pathlib import Path
from loguru import logger as _loguru_logger

# We import lazily inside log_event() to avoid circular imports
# (logger.py is imported before database is initialised).

# Re-export the configured logger
logger = _loguru_logger


def setup_logging(logs_dir: Path) -> None:
    """
    Configure loguru sinks.  Call once from run.py after LOGS_DIR is created.

    Args:
        logs_dir: Path to the directory where log files should be written.
    """
    _loguru_logger.remove()  # Remove default sink

    # Console — human-readable with colours
    _loguru_logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
    )

    # File — daily rotation, keep 7 days
    log_file = logs_dir / "birthday_bot.log"
    _loguru_logger.add(
        str(log_file),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
        level="DEBUG",
        rotation="00:00",   # rotate at midnight
        retention="7 days",
        encoding="utf-8",
    )

    _loguru_logger.info(f"Logging initialised — file: {log_file}")


def log_event(level: str, event: str, detail: str | None = None) -> None:
    """
    Write a log entry to loguru AND persist it to the SQLite LogEntry table.

    Args:
        level:  One of 'INFO', 'WARNING', 'ERROR'.
        event:  Short event name (e.g. 'birthday_email_sent').
        detail: Optional longer description or error message.
    """
    message = event if not detail else f"{event} | {detail}"

    level_upper = level.upper()
    if level_upper == "INFO":
        _loguru_logger.info(message)
    elif level_upper == "WARNING":
        _loguru_logger.warning(message)
    elif level_upper == "ERROR":
        _loguru_logger.error(message)
    else:
        _loguru_logger.debug(message)

    # Persist to DB — imported lazily to avoid circular dependency at module load
    try:
        from database.db import SessionLocal
        from database.models import LogEntry

        with SessionLocal() as session:
            entry = LogEntry(level=level_upper, event=event, detail=detail)
            session.add(entry)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        # Never let DB write failure break the caller
        _loguru_logger.warning(f"Could not persist LogEntry to DB: {exc}")
