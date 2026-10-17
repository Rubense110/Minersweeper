"""Execution control primitives shared across optimization components."""

from __future__ import annotations

import threading


class JobCancelled(Exception):
    """Raised when an optimization job is cancelled."""


class EvaluationTerminationUnconfirmed(RuntimeError):
    """Fatal: the remote evaluation may still be alive; stop this job."""


class EvaluationInfrastructureError(RuntimeError):
    """Fatal: evaluator capacity could not be safely restored; never penalize a model."""


class ReproducibilityError(RuntimeError):
    """Fatal: evaluation hit a safety cutoff or cannot order the net exactly."""


class ExecutionControl:
    """Thread-safe control channel for a single optimization job."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._failure = None
        self._lock = threading.Lock()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def request_failure(self, error: RuntimeError) -> None:
        with self._lock:
            if self._failure is None:
                # Preserve the error category without retaining its traceback,
                # workers, solutions and HTTP payloads for the lifetime of the job.
                self._failure = (type(error), str(error))
            self._cancel_event.set()

    def is_cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancel_requested(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            error_type, message = failure
            raise error_type(message)
        if self.is_cancel_requested():
            raise JobCancelled("job cancelled")
