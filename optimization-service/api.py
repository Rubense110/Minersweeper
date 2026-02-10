"""Minimal HTTP API for optimization jobs."""

from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

from java_service_client import ProMServiceClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _serialize_solution(solution: Any, pareto_ids: set[str]) -> Dict[str, Any]:
    attrs = getattr(solution, "attributes", {}) or {}
    evaluation_id = attrs.get("evaluation_id")

    return {
        "evaluation_id": evaluation_id,
        "experiment_id": attrs.get("experiment_id"),
        "fingerprint": attrs.get("fingerprint"),
        "pipeline": attrs.get("pipeline", {}),
        "metrics": attrs.get("metrics", {}),
        "objectives": list(getattr(solution, "objectives", []) or []),
        "variables": list(getattr(solution, "variables", []) or []),
        "is_pareto": bool(evaluation_id and evaluation_id in pareto_ids),
    }


class OptimizationJobManager:
    def __init__(self, default_service_url: str):
        self.default_service_url = default_service_url
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload is None:
            payload = {}

        execution_name = payload.get("execution_name") or f"run_{int(time.time() * 1000)}"
        log_path = payload.get("log_path") or payload.get("log")
        if not log_path:
            raise ValueError("'log_path' is required")

        service_url = payload.get("service_url") or self.default_service_url
        if not service_url:
            raise ValueError("'service_url' is required (or JAVA_SERVICE_URL env var)")

        metrics = payload.get("metrics")
        excluded_miners = payload.get("excluded_miners", ["split"])

        discover_cfg = {
            "max_evaluations": int(payload.get("max_evaluations", 1000)),
            "population_size": payload.get("population_size", 100),
            "n_partitions": payload.get("n_partitions"),
            "n_workers": int(payload.get("n_workers", 1)),
        }

        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
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

        worker = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        worker.start()
        return self._public_job(job)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = _utc_now_iso()

        try:
            result = self._execute(job["request"])
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["status"] = "completed"
                job["finished_at"] = _utc_now_iso()
                job["result"] = result
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

    def _execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Lazy import so API module is lightweight to import and easier to test.
        from process_miner import OptimizedProcessMiner

        miner = OptimizedProcessMiner(
            execution_name=config["execution_name"],
            log=config["log_path"],
            metrics=config.get("metrics"),
            service_url=config["service_url"],
            excluded_miners=tuple(config.get("excluded_miners") or ()),
        )

        discover = config["discover"]
        miner.discover(
            max_evaluations=discover["max_evaluations"],
            population_size=discover["population_size"],
            n_partitions=discover["n_partitions"],
            n_workers=discover["n_workers"],
        )

        pareto_ids = set(miner.get_non_dominated_evaluation_ids())
        all_solutions_raw = miner.result or []
        pareto_solutions_raw = miner.non_dominated or []

        all_solutions = [_serialize_solution(sol, pareto_ids) for sol in all_solutions_raw]
        pareto_solutions = [_serialize_solution(sol, pareto_ids) for sol in pareto_solutions_raw]

        return {
            "execution_name": config["execution_name"],
            "counts": {
                "all_solutions": len(all_solutions),
                "pareto_solutions": len(pareto_solutions),
            },
            "pareto_evaluation_ids": list(pareto_ids),
            "all_solutions": all_solutions,
            "pareto_solutions": pareto_solutions,
            "non_dominated_pipelines": miner.get_non_dominated_pipelines(),
            "non_dominated_metrics": miner.get_non_dominated_metrics(),
        }

    def get(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return self._public_job(job)

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
        }
        if job["status"] == "completed":
            result = job.get("result") or {}
            output["result_summary"] = {
                "execution_name": result.get("execution_name"),
                "counts": result.get("counts", {}),
                "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
            }
        return output


app = Flask(__name__)
_manager = OptimizationJobManager(default_service_url=os.getenv("JAVA_SERVICE_URL", ""))


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
