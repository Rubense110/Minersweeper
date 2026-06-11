from __future__ import annotations

import queue
from typing import Any, Dict, List, Tuple


def subscribe_events(manager: Any, job_id: str) -> Tuple[queue.Queue, List[Dict[str, Any]]]:
    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        listener: queue.Queue = queue.Queue(maxsize=200)
        manager._subscribers.setdefault(job_id, []).append(listener)
        initial = [
            {"event": "status_changed", "data": {"job_id": job_id, "status": job["status"]}},
            {"event": "progress", "data": public_progress(job)},
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


def unsubscribe_events(manager: Any, job_id: str, listener: queue.Queue) -> None:
    with manager._lock:
        subscribers = manager._subscribers.get(job_id)
        if not subscribers:
            return
        if listener in subscribers:
            subscribers.remove(listener)
        if not subscribers:
            manager._subscribers.pop(job_id, None)


def update_progress(manager: Any, job_id: str, evaluations_done: int) -> None:
    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            return
        progress = job.setdefault("progress", {})
        max_evaluations = int(progress.get("max_evaluations") or 0)
        current = int(progress.get("evaluations_done") or 0)
        next_value = evaluations_done if evaluations_done > current else current
        if max_evaluations > 0:
            next_value = min(next_value, max_evaluations)
        progress["evaluations_done"] = next_value
        payload = public_progress(job)
    publish_event(manager, job_id, "progress", payload)


def publish_event(manager: Any, job_id: str, event_name: str, data: Dict[str, Any]) -> None:
    with manager._lock:
        subscribers = list(manager._subscribers.get(job_id, []))
    if not subscribers:
        return

    envelope = {"event": event_name, "data": data}
    for listener in subscribers:
        try:
            listener.put_nowait(envelope)
        except queue.Full:
            try:
                _ = listener.get_nowait()
            except queue.Empty:
                pass
            try:
                listener.put_nowait(envelope)
            except queue.Full:
                pass


def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    output = {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "error": job["error"],
        "request": job["request"],
        "progress": public_progress(job),
    }
    if job["status"] == "completed":
        result = job.get("result") or {}
        output["result_summary"] = {
            "execution_name": result.get("execution_name"),
            "counts": result.get("counts", {}),
            "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
        }
    return output


def public_progress(job: Dict[str, Any]) -> Dict[str, Any]:
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
