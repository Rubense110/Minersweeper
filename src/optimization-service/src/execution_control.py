"""Execution control primitives shared across optimization components."""

from __future__ import annotations

import threading


class JobCancelled(Exception):
    """Raised when an optimization job is cancelled."""


class ExecutionControl:
    """Thread-safe control channel for a single optimization job."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def is_cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancel_requested(self) -> None:
        if self.is_cancel_requested():
            raise JobCancelled("job cancelled")
