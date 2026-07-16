from __future__ import annotations

import queue
import secrets
import threading
import time
import uuid
from typing import Any, Dict, List, Tuple

from execution_control import ExecutionControl, JobCancelled
from job_store import JobStore
from java_service_client import ProMServiceClient
from model_selection import select_weighted_model

from .common import LOGGER, _logical_cpu_count, _normalize_log_path, _normalize_n_workers, _to_int, _utc_now_iso
from .manager_persistence import persist_completed_experiment
from .manager_runtime import cleanup_cancelled_experiment, execute_job, finalize_cancelled_job, request_java_experiment_cancel, run_job
from .manager_state import publish_event, public_job, public_progress, subscribe_events, unsubscribe_events, update_progress
from .serialization import _build_experiment_export_archive


MAX_SAFE_SEED = 2**53 - 1


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

        metrics = _normalize_metric_names(payload.get("metrics") or ["fitness", "precision", "simplicity", "generalisation"])
        required_metrics = list(metrics)
        conformance_mode = payload.get("conformance_mode")
        excluded_miners = payload.get("excluded_miners", ["ilp"])
        seed = _normalize_seed(payload.get("seed"))

        requested_n_workers = payload.get("n_workers", 1)
        normalized_n_workers = _normalize_n_workers(requested_n_workers)
        discover_cfg = {
            "max_evaluations": int(payload.get("max_evaluations", 1000)),
            "population_size": payload.get("population_size", 100),
            "n_partitions": payload.get("n_partitions"),
            "n_workers": normalized_n_workers,
            "seed": seed,
        }
        if normalized_n_workers != _to_int(requested_n_workers, 1):
            LOGGER.info(
                "n_workers clamped requested=%s normalized=%s logical_cpus=%s",
                requested_n_workers,
                normalized_n_workers,
                _logical_cpu_count(),
            )

        job_id = str(uuid.uuid4())
        execution_control = ExecutionControl()
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
                "required_metrics": required_metrics,
                "conformance_mode": conformance_mode,
                "excluded_miners": excluded_miners,
                "discover": discover_cfg,
            },
            "result": None,
            "_control": execution_control,
            "_runtime_miner": None,
        }

        with self._lock:
            self._jobs[job_id] = job

        self._publish_event(job_id, "status_changed", {"job_id": job_id, "status": "queued"})
        self._publish_event(job_id, "progress", self._public_progress(job))

        worker = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        worker.start()
        LOGGER.info(
            "job queued job_id=%s execution=%s log_path=%s metrics=%s max_evaluations=%s population_size=%s n_workers=%s seed=%s",
            job_id,
            execution_name,
            log_path,
            ",".join(metrics),
            discover_cfg["max_evaluations"],
            discover_cfg["population_size"],
            discover_cfg["n_workers"],
            discover_cfg["seed"],
        )
        return self._public_job(job)

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)

            status = str(job.get("status") or "")
            if status in {"completed", "failed"}:
                raise RuntimeError(f"job '{job_id}' cannot be cancelled from state '{status}'")
            if status == "cancelled":
                return self._public_job(job)

            control = job["_control"]
            control.request_cancel()

            request_data = dict(job.get("request") or {})
            runtime_miner = job.get("_runtime_miner")
            if status == "queued":
                job["status"] = "cancelled"
                job["finished_at"] = _utc_now_iso()
                payload = self._public_job(job)
            else:
                job["status"] = "cancelling"
                payload = self._public_job(job)

        if status == "queued":
            self._publish_event(job_id, "status_changed", {"job_id": job_id, "status": "cancelled"})
            self._publish_event(job_id, "progress", self.get_progress(job_id))
            return payload

        if runtime_miner is not None:
            try:
                runtime_miner.request_cancel()
            except Exception:
                LOGGER.warning("job cancel local interrupt failed job_id=%s", job_id, exc_info=True)

        self._request_java_experiment_cancel(job_id, request_data)
        self._publish_event(job_id, "status_changed", {"job_id": job_id, "status": "cancelling"})
        self._publish_event(job_id, "progress", self.get_progress(job_id))
        return payload

    def _run_job(self, job_id: str) -> None:
        run_job(self, job_id)

    def _execute(self, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return execute_job(self, job_id, config)

    def _request_java_experiment_cancel(self, job_id: str, request_data: Dict[str, Any]) -> None:
        request_java_experiment_cancel(self, job_id, request_data)

    def _cleanup_cancelled_experiment(self, request_data: Dict[str, Any]) -> None:
        cleanup_cancelled_experiment(self, request_data)

    def _finalize_cancelled_job(self, job_id: str) -> None:
        finalize_cancelled_job(self, job_id)

    def _persist_completed_experiment(self, job_id: str) -> None:
        persist_completed_experiment(self, job_id)

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

    def list_experiments(self) -> List[Dict[str, Any]]:
        return self.job_store.list_experiments()

    def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        return self.job_store.get_experiment(experiment_id)

    def get_experiment_solutions(self, experiment_id: str, scope: str) -> Dict[str, Any]:
        solutions = self.job_store.get_experiment_solutions(experiment_id=experiment_id, scope=scope)
        return {
            "experiment_id": experiment_id,
            "scope": scope,
            "count": len(solutions),
            "solutions": solutions,
        }

    def select_experiment_model(
        self,
        experiment_id: str,
        weights: Dict[str, Any] | None,
        scope: str,
    ) -> Dict[str, Any]:
        experiment = self.job_store.get_experiment(experiment_id)
        solutions = self.job_store.get_experiment_solutions(experiment_id=experiment_id, scope=scope)
        return select_weighted_model(
            experiment=experiment,
            solutions=solutions,
            raw_weights=weights,
            scope=scope,
        )

    def get_experiment_export(self, experiment_id: str) -> Tuple[bytes, str]:
        experiment = self.job_store.get_experiment(experiment_id)
        solutions = self.job_store.get_experiment_solutions(experiment_id=experiment_id, scope="all")
        snapshot_solutions = self.job_store.get_experiment_snapshot_solutions(experiment_id=experiment_id)
        return _build_experiment_export_archive(experiment, solutions, snapshot_solutions)

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

    def subscribe_events(self, job_id: str) -> Tuple[queue.Queue, List[Dict[str, Any]]]:
        return subscribe_events(self, job_id)

    def unsubscribe_events(self, job_id: str, listener: queue.Queue) -> None:
        unsubscribe_events(self, job_id, listener)

    def _update_progress(self, job_id: str, evaluations_done: int) -> None:
        update_progress(self, job_id, evaluations_done)

    def _publish_event(self, job_id: str, event_name: str, data: Dict[str, Any]) -> None:
        publish_event(self, job_id, event_name, data)

    @staticmethod
    def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
        return public_job(job)

    @staticmethod
    def _public_progress(job: Dict[str, Any]) -> Dict[str, Any]:
        return public_progress(job)


def _normalize_metric_names(raw_metrics: Any) -> List[str]:
    if not isinstance(raw_metrics, list):
        raise ValueError("metrics must be a list")
    metrics: List[str] = []
    seen = set()
    for item in raw_metrics:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        metrics.append(name)
    if not metrics:
        raise ValueError("metrics must contain at least one metric")
    return metrics


def _normalize_seed(value: Any) -> int:
    if value is None or value == "":
        return secrets.randbits(32)
    try:
        seed = int(value)
    except (TypeError, ValueError):
        raise ValueError("seed must be an integer") from None
    if seed < 0:
        raise ValueError("seed must be greater than or equal to 0")
    if seed > MAX_SAFE_SEED:
        raise ValueError(f"seed must be less than or equal to {MAX_SAFE_SEED}")
    return seed
