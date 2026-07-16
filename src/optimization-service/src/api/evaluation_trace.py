from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from .serialization import _pipeline_for_log


_TRACE_LOCK = threading.Lock()


def evaluation_trace_path() -> str:
    return (os.getenv("OPT_EVALUATION_TRACE_FILE") or "").strip()


def append_evaluation_trace(
    *,
    job_id: str,
    config: Dict[str, Any],
    event: Dict[str, Any],
) -> None:
    path = evaluation_trace_path()
    if not path:
        return

    discover = dict(config.get("discover") or {})
    row = {
        "event": "evaluation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "execution_name": config.get("execution_name"),
        "log_path": config.get("log_path"),
        "workers": discover.get("n_workers"),
        "max_evaluations": discover.get("max_evaluations"),
        "population_size": discover.get("population_size"),
        "seed": discover.get("seed"),
        "conformance_mode": config.get("conformance_mode"),
        "evaluations_done": event.get("evaluations_done"),
        "cache_hit": bool(event.get("cache_hit")),
        "solution_cache_size": event.get("solution_cache_size"),
        "runtime_ms": event.get("runtime_ms"),
        "cached_runtime_ms": event.get("cached_runtime_ms"),
        "has_error": bool(event.get("has_error")),
        "evaluation_error": event.get("evaluation_error"),
        "evaluation_id": event.get("evaluation_id"),
        "experiment_id": event.get("experiment_id"),
        "fingerprint": event.get("fingerprint"),
        "metrics": event.get("metrics") or {},
        "pipeline": _pipeline_for_log(event.get("pipeline")),
    }

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    line = json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    with _TRACE_LOCK:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
