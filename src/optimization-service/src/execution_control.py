"""Execution control primitives shared across optimization components."""

from __future__ import annotations

import threading


class JobCancelled(Exception):
    """Raised when an optimization job is cancelled."""


class EvaluationTerminationUnconfirmed(RuntimeError):
    """Fatal: the remote evaluation may still be alive; stop this job."""


class ExecutionControl:
    """Thread-safe control channel for a single optimization job."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._failure = None
        self._lock = threading.Lock()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def request_failure(self, error: EvaluationTerminationUnconfirmed) -> None:
        with self._lock:
            if self._failure is None:
                self._failure = str(error)
            self._cancel_event.set()

    def is_cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancel_requested(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            raise EvaluationTerminationUnconfirmed(failure)
        if self.is_cancel_requested():
            raise JobCancelled("job cancelled")
