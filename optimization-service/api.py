"""Minimal HTTP API for optimization jobs."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import psutil
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from job_store import JobStore
from java_service_client import ProMServiceClient


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

    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("optimization_service.jobs")


LOGGER = _configure_logging()


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


def _local_xml_name(tag: str) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _xml_node_label(element: ET.Element) -> str:
    for child in element.iter():
        if _local_xml_name(child.tag) == "text":
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def _petri_from_pnml(pnml_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not pnml_text:
        return [], [], []

    try:
        root = ET.fromstring(pnml_text)
    except ET.ParseError:
        return [], [], []

    places: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    arcs: List[Dict[str, Any]] = []

    for node in root.iter():
        tag = _local_xml_name(node.tag)
        if tag == "place":
            places.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "label": _xml_node_label(node),
                }
            )
        elif tag == "transition":
            transitions.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "label": _xml_node_label(node),
                }
            )
        elif tag == "arc":
            arcs.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "source": (node.attrib.get("source") or "").strip(),
                    "target": (node.attrib.get("target") or "").strip(),
                }
            )

    return places, transitions, arcs


def _compact_pipeline_for_storage(pipeline: Any) -> Dict[str, Any]:
    if not isinstance(pipeline, dict):
        return {
            "preprocessing": {"variant": "", "parameters": {}},
            "miner": {"variant": "", "parameters": {}},
        }

    preprocessing = pipeline.get("preprocessing") if isinstance(pipeline.get("preprocessing"), dict) else {}
    miner = pipeline.get("miner") if isinstance(pipeline.get("miner"), dict) else {}

    return {
        "preprocessing": {
            "variant": preprocessing.get("variant") or "",
            "parameters": preprocessing.get("parameters") if isinstance(preprocessing.get("parameters"), dict) else {},
        },
        "miner": {
            "variant": miner.get("variant") or "",
            "parameters": miner.get("parameters") if isinstance(miner.get("parameters"), dict) else {},
        },
    }


def _pipeline_for_log(pipeline: Any, max_length: int = 1500) -> str:
    if not pipeline:
        return ""
    try:
        text = json.dumps(pipeline, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    except Exception:
        text = str(pipeline)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _serialize_solution(solution: Any, pareto_ids: set[str]) -> Dict[str, Any]:
    attrs = getattr(solution, "attributes", {}) or {}
    evaluation_id = attrs.get("evaluation_id")
    payload = {
        "evaluation_id": evaluation_id,
        "experiment_id": attrs.get("experiment_id"),
        "fingerprint": attrs.get("fingerprint"),
        "pipeline": attrs.get("pipeline", {}),
        "metrics": attrs.get("metrics", {}),
        "runtime_ms": _to_int_or_none(attrs.get("runtime_ms")),
        "objectives": list(getattr(solution, "objectives", []) or []),
        "variables": list(getattr(solution, "variables", []) or []),
        "is_pareto": bool(evaluation_id and evaluation_id in pareto_ids),
    }
    if attrs.get("evaluation_error"):
        payload["evaluation_error"] = attrs.get("evaluation_error")
    return payload


class OptimizationJobManager:
    def __init__(self, default_service_url: str, db_url: str, java_service_timeout_seconds: int):
        self.default_service_url = default_service_url
        self.java_service_timeout_seconds = max(1, int(java_service_timeout_seconds))
        self.job_store = JobStore(db_url=db_url)
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, List[queue.Queue]] = {}
        self._lock = threading.Lock()

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload is None:
            payload = {}

        execution_name = payload.get("execution_name") or f"run_{int(time.time() * 1000)}"
        raw_log_path = payload.get("log_path") or payload.get("log")
        log_path = _normalize_log_path(raw_log_path)

        service_url = payload.get("service_url") or self.default_service_url
        if not service_url:
            raise ValueError("'service_url' is required (or JAVA_SERVICE_URL env var)")

        metrics = payload.get("metrics")
        excluded_miners = payload.get("excluded_miners", ["ilp"])

        requested_n_workers = payload.get("n_workers", 1)
        normalized_n_workers = _normalize_n_workers(requested_n_workers)
        discover_cfg = {
            "max_evaluations": int(payload.get("max_evaluations", 1000)),
            "population_size": payload.get("population_size", 100),
            "n_partitions": payload.get("n_partitions"),
            "n_workers": normalized_n_workers,
        }
        if normalized_n_workers != _to_int(requested_n_workers, 1):
            LOGGER.info(
                "n_workers clamped requested=%s normalized=%s logical_cpus=%s",
                requested_n_workers,
                normalized_n_workers,
                _logical_cpu_count(),
            )

        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "progress": {
                "evaluations_done": 0,
                "max_evaluations": discover_cfg["max_evaluations"],
            },
            "request": {
                "execution_name": execution_name,
                "log_path": log_path,
                "service_url": service_url,
                "metrics": metrics,
                "excluded_miners": excluded_miners,
                "discover": discover_cfg,
            },
            "result": None,
        }

        with self._lock:
            self._jobs[job_id] = job

        self._publish_event(
            job_id,
            "status_changed",
            {
                "job_id": job_id,
                "status": "queued",
            },
        )
        self._publish_event(job_id, "progress", self._public_progress(job))

        worker = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        worker.start()
        LOGGER.info(
            "job queued job_id=%s execution=%s log_path=%s max_evaluations=%s population_size=%s n_workers=%s",
            job_id,
            execution_name,
            log_path,
            discover_cfg["max_evaluations"],
            discover_cfg["population_size"],
            discover_cfg["n_workers"],
        )
        return self._public_job(job)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = _utc_now_iso()
            request_data = dict(job["request"])
        LOGGER.info(
            "job running job_id=%s execution=%s metrics=%s service_url=%s",
            job_id,
            request_data.get("execution_name"),
            request_data.get("metrics"),
            request_data.get("service_url"),
        )
        self._publish_event(
            job_id,
            "status_changed",
            {
                "job_id": job_id,
                "status": "running",
            },
        )

        try:
            result = self._execute(job_id, job["request"])
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["finished_at"] = _utc_now_iso()
                job["result"] = result
                progress = job.get("progress", {})
                max_evaluations = int(progress.get("max_evaluations") or 0)
                current = int(progress.get("evaluations_done") or 0)
                if max_evaluations > current:
                    progress["evaluations_done"] = max_evaluations

            self._persist_completed_experiment(job_id)

            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["status"] = "completed"

            all_solutions = result.get("all_solutions", [])
            failed_solutions = sum(1 for item in all_solutions if item.get("evaluation_error"))
            total_solutions = len(all_solutions)
            LOGGER.info(
                "job completed job_id=%s execution=%s total_solutions=%s pareto_solutions=%s failed_solutions=%s",
                job_id,
                result.get("execution_name"),
                total_solutions,
                result.get("counts", {}).get("pareto_solutions", 0),
                failed_solutions,
            )
            self._publish_event(
                job_id,
                "status_changed",
                {
                    "job_id": job_id,
                    "status": "completed",
                },
            )
            self._publish_event(job_id, "progress", self.get_progress(job_id))
            self._publish_event(
                job_id,
                "result_ready",
                {
                    "job_id": job_id,
                    "result_summary": {
                        "execution_name": result.get("execution_name"),
                        "counts": result.get("counts", {}),
                        "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
                    },
                },
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["status"] = "failed"
                job["finished_at"] = _utc_now_iso()
                job["error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            self._publish_event(
                job_id,
                "status_changed",
                {
                    "job_id": job_id,
                    "status": "failed",
                },
            )
            self._publish_event(
                job_id,
                "error",
                {
                    "job_id": job_id,
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            LOGGER.exception("job failed job_id=%s", job_id)

    def _execute(self, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        # Lazy import so API module is lightweight to import and easier to test.
        from process_miner import OptimizedProcessMiner

        discover = config["discover"]
        max_evaluations = int(discover["max_evaluations"])
        progress_log_step = max(1, max_evaluations // 10)
        progress_state = {
            "last_progress_logged": 0,
            "error_count": 0,
            "error_occurrences": {},
            "unique_errors_logged": 0,
        }

        def on_evaluation(event: Dict[str, Any]) -> None:
            evaluations_done = int(event.get("evaluations_done") or 0)
            self._update_progress(job_id, evaluations_done)

            should_log_progress = (
                evaluations_done == 1
                or evaluations_done >= max_evaluations
                or evaluations_done - int(progress_state["last_progress_logged"]) >= progress_log_step
            )
            if should_log_progress:
                progress_state["last_progress_logged"] = evaluations_done
                LOGGER.info(
                    "job progress job_id=%s evaluations=%s/%s cache_hit=%s errors=%s",
                    job_id,
                    evaluations_done,
                    max_evaluations,
                    bool(event.get("cache_hit")),
                    progress_state["error_count"],
                )

            if not event.get("has_error"):
                return

            progress_state["error_count"] = int(progress_state["error_count"]) + 1
            error_message = str(event.get("evaluation_error") or "evaluation_failed")
            error_occurrences = progress_state["error_occurrences"]
            error_count_for_message = int(error_occurrences.get(error_message, 0)) + 1
            error_occurrences[error_message] = error_count_for_message

            if error_count_for_message == 1 and int(progress_state["unique_errors_logged"]) < 5:
                progress_state["unique_errors_logged"] = int(progress_state["unique_errors_logged"]) + 1
                pipeline_text = _pipeline_for_log(event.get("pipeline"))
                LOGGER.warning(
                    "job evaluation failed job_id=%s evaluation=%s/%s error=%s pipeline=%s",
                    job_id,
                    evaluations_done,
                    max_evaluations,
                    error_message,
                    pipeline_text,
                )

        miner = OptimizedProcessMiner(
            execution_name=config["execution_name"],
            log=config["log_path"],
            metrics=config.get("metrics"),
            service_url=config["service_url"],
            service_timeout_seconds=self.java_service_timeout_seconds,
            excluded_miners=tuple(config.get("excluded_miners") or ()),
        )

        miner.discover(
            max_evaluations=discover["max_evaluations"],
            population_size=discover["population_size"],
            n_partitions=discover["n_partitions"],
            n_workers=discover["n_workers"],
            progress_callback=on_evaluation,
        )

        pareto_ids = set(miner.get_non_dominated_evaluation_ids())
        all_solutions_raw = miner.result or []
        pareto_solutions_raw = miner.non_dominated or []

        all_solutions = [_serialize_solution(sol, pareto_ids) for sol in all_solutions_raw]
        pareto_solutions = [_serialize_solution(sol, pareto_ids) for sol in pareto_solutions_raw]

        return {
            "execution_name": config["execution_name"],
            "metrics_order": list(miner.metrics_list),
            "counts": {
                "all_solutions": len(all_solutions),
                "pareto_solutions": len(pareto_solutions),
            },
            "pareto_evaluation_ids": list(pareto_ids),
            "all_solutions": all_solutions,
            "pareto_solutions": pareto_solutions,
            "non_dominated_pipelines": miner.get_non_dominated_pipelines(),
            "non_dominated_metrics": miner.get_non_dominated_metrics(),
            "catalogs": {
                "miners": list(miner.search_space.miner_keys if miner.search_space else []),
                "preprocessing": list(miner.search_space.preprocessing_keys if miner.search_space else []),
            },
        }

    def _persist_completed_experiment(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            request_data = dict(job.get("request") or {})
            result = dict(job.get("result") or {})
            started_at = job.get("started_at")
            finished_at = job.get("finished_at")

        discover = request_data.get("discover") or {}
        all_solutions = list(result.get("all_solutions") or [])

        evaluation_ids: List[str] = []
        seen = set()
        for solution in all_solutions:
            evaluation_id = solution.get("evaluation_id")
            if not evaluation_id or evaluation_id in seen:
                continue
            seen.add(evaluation_id)
            evaluation_ids.append(evaluation_id)

        artifacts_by_evaluation_id: Dict[str, Dict[str, Any]] = {}
        if evaluation_ids:
            client = ProMServiceClient(
                base_url=str(request_data.get("service_url") or self.default_service_url),
                experiment_id=str(request_data.get("execution_name") or ""),
                timeout_seconds=self.java_service_timeout_seconds,
            )
            artifacts = client.fetch_artifacts(
                evaluation_ids=evaluation_ids,
                include_pnml=True,
                experiment_id=str(request_data.get("execution_name") or ""),
            )
            for artifact in artifacts:
                evaluation_id = artifact.get("evaluation_id")
                if not evaluation_id:
                    continue
                artifacts_by_evaluation_id[str(evaluation_id)] = artifact

        parsed_solutions: List[Dict[str, Any]] = []
        for solution in all_solutions:
            places: List[Dict[str, Any]] = []
            transitions: List[Dict[str, Any]] = []
            arcs: List[Dict[str, Any]] = []

            evaluation_id = solution.get("evaluation_id")
            if evaluation_id:
                artifact = artifacts_by_evaluation_id.get(str(evaluation_id))
                if artifact:
                    pnml_text = str(artifact.get("pnml") or "")
                    places, transitions, arcs = _petri_from_pnml(pnml_text)

            parsed_solutions.append(
                {
                    "variables": solution.get("variables", []),
                    "objectives": solution.get("objectives", []),
                    "pipeline": _compact_pipeline_for_storage(solution.get("pipeline")),
                    "runtime_ms": _to_int_or_none(solution.get("runtime_ms")),
                    "is_pareto": bool(solution.get("is_pareto")),
                    "places": places,
                    "transitions": transitions,
                    "arcs": arcs,
                }
            )

        experiment_data = {
            "experiment_id": job_id,
            "experiment_name": request_data.get("execution_name") or job_id,
            "start_at": _parse_utc_iso(started_at) or datetime.now(timezone.utc),
            "end_at": _parse_utc_iso(finished_at) or datetime.now(timezone.utc),
            "max_evals": int(discover.get("max_evaluations") or 0),
            "pop_size": _to_int_or_none(discover.get("population_size")),
            "miners": (result.get("catalogs") or {}).get("miners", []),
            "preprocessing": (result.get("catalogs") or {}).get("preprocessing", []),
            "log_path": request_data.get("log_path") or "",
            "metrics": result.get("metrics_order") or request_data.get("metrics") or [],
            "workers": int(discover.get("n_workers") or 1),
        }

        self.job_store.save_completed_experiment(experiment_data, parsed_solutions)

    def get(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return self._public_job(job)

    def get_progress(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return self._public_progress(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = [self._public_job(job) for job in self._jobs.values()]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return items

    def get_solutions(self, job_id: str, scope: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job["status"] != "completed":
                raise RuntimeError(f"job '{job_id}' is not completed")
            result = job["result"] or {}

        scope_key = "pareto_solutions" if scope == "pareto" else "all_solutions"
        solutions = list(result.get(scope_key, []))
        return {
            "job_id": job_id,
            "scope": scope,
            "count": len(solutions),
            "solutions": solutions,
        }

    def get_artifacts(self, job_id: str, scope: str, include_pnml: bool) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job["status"] != "completed":
                raise RuntimeError(f"job '{job_id}' is not completed")
            request_data = dict(job["request"])
            result = job["result"] or {}

        scope_key = "pareto_solutions" if scope == "pareto" else "all_solutions"
        eval_ids: List[str] = []
        seen = set()
        for solution in result.get(scope_key, []):
            evaluation_id = solution.get("evaluation_id")
            if not evaluation_id or evaluation_id in seen:
                continue
            seen.add(evaluation_id)
            eval_ids.append(evaluation_id)

        if not eval_ids:
            return {
                "job_id": job_id,
                "scope": scope,
                "include_pnml": include_pnml,
                "artifacts": [],
            }

        client = ProMServiceClient(
            base_url=request_data["service_url"],
            experiment_id=request_data["execution_name"],
            timeout_seconds=self.java_service_timeout_seconds,
        )
        artifacts = client.fetch_artifacts(
            evaluation_ids=eval_ids,
            include_pnml=include_pnml,
            experiment_id=request_data["execution_name"],
        )

        return {
            "job_id": job_id,
            "scope": scope,
            "include_pnml": include_pnml,
            "artifacts": artifacts,
        }

    def subscribe_events(self, job_id: str) -> Tuple[queue.Queue, List[Dict[str, Any]]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            listener: queue.Queue = queue.Queue(maxsize=200)
            self._subscribers.setdefault(job_id, []).append(listener)
            initial = [
                {
                    "event": "status_changed",
                    "data": {
                        "job_id": job_id,
                        "status": job["status"],
                    },
                },
                {
                    "event": "progress",
                    "data": self._public_progress(job),
                },
            ]
            if job["status"] == "completed":
                result = job.get("result") or {}
                initial.append(
                    {
                        "event": "result_ready",
                        "data": {
                            "job_id": job_id,
                            "result_summary": {
                                "execution_name": result.get("execution_name"),
                                "counts": result.get("counts", {}),
                                "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
                            },
                        },
                    }
                )
        return listener, initial

    def unsubscribe_events(self, job_id: str, listener: queue.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(job_id)
            if not subscribers:
                return
            if listener in subscribers:
                subscribers.remove(listener)
            if not subscribers:
                self._subscribers.pop(job_id, None)

    def _update_progress(self, job_id: str, evaluations_done: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            progress = job.setdefault("progress", {})
            max_evaluations = int(progress.get("max_evaluations") or 0)
            current = int(progress.get("evaluations_done") or 0)
            next_value = evaluations_done if evaluations_done > current else current
            if max_evaluations > 0:
                next_value = min(next_value, max_evaluations)
            progress["evaluations_done"] = next_value
            payload = self._public_progress(job)
        self._publish_event(job_id, "progress", payload)

    def _publish_event(self, job_id: str, event_name: str, data: Dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(job_id, []))
        if not subscribers:
            return

        envelope = {"event": event_name, "data": data}
        for listener in subscribers:
            try:
                listener.put_nowait(envelope)
            except queue.Full:
                # Drop oldest event to keep stream responsive under backpressure.
                try:
                    _ = listener.get_nowait()
                except queue.Empty:
                    pass
                try:
                    listener.put_nowait(envelope)
                except queue.Full:
                    pass

    @staticmethod
    def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
        output = {
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
            "error": job["error"],
            "request": job["request"],
            "progress": OptimizationJobManager._public_progress(job),
        }
        if job["status"] == "completed":
            result = job.get("result") or {}
            output["result_summary"] = {
                "execution_name": result.get("execution_name"),
                "counts": result.get("counts", {}),
                "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
            }
        return output

    @staticmethod
    def _public_progress(job: Dict[str, Any]) -> Dict[str, Any]:
        progress = job.get("progress", {}) or {}
        evaluations_done = int(progress.get("evaluations_done") or 0)
        max_evaluations = int(progress.get("max_evaluations") or 0)
        percentage = 0.0
        if max_evaluations > 0:
            percentage = round((evaluations_done / max_evaluations) * 100.0, 2)
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "evaluations_done": evaluations_done,
            "max_evaluations": max_evaluations,
            "percentage": percentage,
        }


app = Flask(__name__)
CORS(app)
_manager = OptimizationJobManager(
    default_service_url=os.getenv("JAVA_SERVICE_URL", ""),
    db_url=os.getenv("OPT_DB_URL", "sqlite:////tmp/minersweeper-optimization.db"),
    java_service_timeout_seconds=_java_service_timeout_seconds(),
)


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.get("/optimizations")
def list_jobs() -> Any:
    return jsonify({"jobs": _manager.list_jobs()})


@app.post("/optimizations")
def create_job() -> Any:
    payload = request.get_json(silent=True) or {}
    try:
        job = _manager.submit(payload)
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    return jsonify(job), 202


@app.get("/optimizations/<job_id>")
def get_job(job_id: str) -> Any:
    try:
        return jsonify(_manager.get(job_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404


@app.get("/optimizations/<job_id>/progress")
def get_job_progress(job_id: str) -> Any:
    try:
        return jsonify(_manager.get_progress(job_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


@app.get("/optimizations/<job_id>/events")
def stream_job_events(job_id: str) -> Any:
    try:
        listener, initial_events = _manager.subscribe_events(job_id)
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404

    def generate():
        terminal = False
        try:
            yield "retry: 2000\n\n"
            for item in initial_events:
                yield _format_sse(item["event"], item["data"])
                if item["event"] == "status_changed" and item["data"].get("status") in {"completed", "failed"}:
                    terminal = True
            while not terminal:
                try:
                    item = listener.get(timeout=15.0)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _format_sse(item["event"], item["data"])
                if item["event"] == "status_changed" and item["data"].get("status") in {"completed", "failed"}:
                    terminal = True
        finally:
            _manager.unsubscribe_events(job_id, listener)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers=headers)


@app.get("/optimizations/<job_id>/solutions")
def get_solutions(job_id: str) -> Any:
    scope = (request.args.get("scope") or "pareto").strip().lower()
    if scope not in {"pareto", "all"}:
        return jsonify({"error": "invalid_request", "message": "scope must be 'pareto' or 'all'"}), 400

    try:
        return jsonify(_manager.get_solutions(job_id, scope))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404
    except RuntimeError as exc:
        return jsonify({"error": "invalid_state", "message": str(exc)}), 409


@app.get("/optimizations/<job_id>/artifacts")
def get_artifacts(job_id: str) -> Any:
    scope = (request.args.get("scope") or "pareto").strip().lower()
    include_pnml = _to_bool(request.args.get("include_pnml"), default=True)

    if scope not in {"pareto", "all"}:
        return jsonify({"error": "invalid_request", "message": "scope must be 'pareto' or 'all'"}), 400

    try:
        return jsonify(_manager.get_artifacts(job_id, scope=scope, include_pnml=include_pnml))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404
    except RuntimeError as exc:
        return jsonify({"error": "invalid_state", "message": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": "artifact_fetch_failed", "message": str(exc)}), 500


def main() -> None:
    host = os.getenv("OPTIMIZATION_HOST", "0.0.0.0")
    port = int(os.getenv("OPTIMIZATION_PORT", "8080"))
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
