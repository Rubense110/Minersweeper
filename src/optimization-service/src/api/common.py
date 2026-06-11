from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, List, Optional

import psutil
from werkzeug.serving import WSGIRequestHandler


class ServiceLineFormatter(logging.Formatter):
    _ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level = record.levelname
        message = self._ANSI_RE.sub("", str(record.getMessage()))
        lines = message.splitlines() or [""]
        prefix = f"[{timestamp}] [{self.service_name}] [{level}] "
        rendered = "\n".join(prefix + line for line in lines)

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            if exc_text:
                rendered += "\n" + "\n".join(prefix + line for line in exc_text.splitlines())
        return rendered


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _logical_cpu_count() -> int:
    count = psutil.cpu_count(logical=True)
    if isinstance(count, int) and count > 0:
        return count
    count = os.cpu_count()
    if isinstance(count, int) and count > 0:
        return count
    return 1


def _normalize_n_workers(value: Any) -> int:
    requested = _to_int(value, 1)
    if requested < 1:
        requested = 1
    return min(requested, _logical_cpu_count())


def _normalize_log_path(value: Any) -> str:
    raw = "" if value is None else str(value).strip()
    if not raw:
        raise ValueError("'log_path' is required")

    normalized_input = os.path.normpath(raw)
    if os.path.isabs(normalized_input):
        return normalized_input

    logs_root = (os.getenv("LOGS_ROOT") or "/data/logs").strip() or "/data/logs"
    normalized_root = os.path.normpath(logs_root)

    rel_parts = [part for part in normalized_input.split(os.sep) if part not in ("", ".")]
    root_parts = [part for part in normalized_root.split(os.sep) if part not in ("", ".")]

    if root_parts and rel_parts[: len(root_parts)] == root_parts:
        rel_parts = rel_parts[len(root_parts) :]

    if not rel_parts:
        return normalized_root

    return os.path.normpath(os.path.join(normalized_root, *rel_parts))


def _java_service_timeout_seconds() -> int:
    return max(1, _to_int(os.getenv("JAVA_SERVICE_TIMEOUT_SECONDS"), 300))


def _list_logs_in_root() -> List[str]:
    logs_root = (os.getenv("LOGS_ROOT") or "/data/logs").strip() or "/data/logs"
    if not os.path.isdir(logs_root):
        return []

    items: List[str] = []
    for root, _dirs, files in os.walk(logs_root):
        for file_name in files:
            if not file_name.lower().endswith(".xes"):
                continue
            absolute_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(absolute_path, logs_root)
            normalized = relative_path.replace(os.sep, "/")
            items.append(normalized)

    items.sort()
    return items


def _configure_logging() -> logging.Logger:
    log_level_name = (os.getenv("OPTIMIZATION_LOG_LEVEL") or "INFO").strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    handlers: List[logging.Handler] = [logging.StreamHandler()]

    if _to_bool(os.getenv("OPT_LOG_TO_FILE"), default=False):
        log_file = (os.getenv("OPT_LOG_FILE") or "").strip()
        if log_file:
            log_max_bytes = _to_int(os.getenv("OPT_LOG_MAX_BYTES"), 10 * 1024 * 1024)
            log_backup_count = _to_int(os.getenv("OPT_LOG_BACKUP_COUNT"), 5)
            try:
                log_dir = os.path.dirname(log_file)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                if log_max_bytes > 0 and log_backup_count > 0:
                    handlers.append(
                        RotatingFileHandler(
                            log_file,
                            mode="a",
                            maxBytes=log_max_bytes,
                            backupCount=log_backup_count,
                            encoding="utf-8",
                        )
                    )
                else:
                    handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))
            except OSError as error:
                logging.getLogger("optimization_service.jobs").warning(
                    "file logging disabled: cannot initialize OPT_LOG_FILE=%s (%s)",
                    log_file,
                    error,
                )

    formatter = ServiceLineFormatter(service_name="optimization_service")
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=handlers, force=True)
    return logging.getLogger("optimization_service.jobs")


LOGGER = _configure_logging()
_TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


class _QuietRequestHandler(WSGIRequestHandler):
    """Use the default werkzeug request logging with no extra filtering."""

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        super().log_request(code=code, size=size)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_iso(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
