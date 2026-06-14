import os
import queue
import sys
import threading
import unittest
from unittest.mock import Mock, patch


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from execution_control import ExecutionControl
from api.manager_runtime import finalize_cancelled_job, request_java_experiment_cancel
from api.manager_state import publish_event, subscribe_events, unsubscribe_events, update_progress


class _FakeManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self._subscribers = {}
        self.default_service_url = "http://java-service"
        self.java_service_timeout_seconds = 123
        self.job_store = Mock()


class ManagerStateTest(unittest.TestCase):
    def test_update_progress_is_monotonic(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "status": "running",
            "progress": {"evaluations_done": 7, "max_evaluations": 10},
        }

        update_progress(manager, "job-1", 5)

        self.assertEqual(7, manager._jobs["job-1"]["progress"]["evaluations_done"])

    def test_update_progress_caps_at_max_evaluations(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "status": "running",
            "progress": {"evaluations_done": 7, "max_evaluations": 10},
        }

        update_progress(manager, "job-1", 99)

        self.assertEqual(10, manager._jobs["job-1"]["progress"]["evaluations_done"])

    def test_subscribe_events_includes_result_ready_for_completed_job(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "status": "completed",
            "progress": {"evaluations_done": 10, "max_evaluations": 10},
            "result": {
                "execution_name": "exp-1",
                "counts": {"pareto_solutions": 2},
                "pareto_evaluation_ids": ["ev-1", "ev-2"],
            },
        }

        listener, initial = subscribe_events(manager, "job-1")

        self.assertEqual(3, len(initial))
        self.assertEqual("result_ready", initial[-1]["event"])
        self.assertIs(listener, manager._subscribers["job-1"][0])

    def test_unsubscribe_events_removes_empty_subscriber_bucket(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {"job_id": "job-1", "status": "queued", "progress": {"evaluations_done": 0, "max_evaluations": 1}}

        listener, _initial = subscribe_events(manager, "job-1")
        unsubscribe_events(manager, "job-1", listener)

        self.assertNotIn("job-1", manager._subscribers)

    def test_publish_event_replaces_oldest_item_when_queue_is_full(self):
        manager = _FakeManager()
        listener = queue.Queue(maxsize=1)
        listener.put_nowait({"event": "old", "data": {"job_id": "job-1"}})
        manager._subscribers["job-1"] = [listener]

        publish_event(manager, "job-1", "progress", {"job_id": "job-1", "status": "running"})

        delivered = listener.get_nowait()
        self.assertEqual("progress", delivered["event"])
        self.assertEqual("running", delivered["data"]["status"])


class ManagerRuntimeTest(unittest.TestCase):
    def test_finalize_cancelled_job_resets_job_and_publishes_events(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "status": "cancelling",
            "finished_at": None,
            "result": {"execution_name": "exp-1"},
            "error": {"message": "boom"},
            "request": {"execution_name": "exp-1", "service_url": "http://java-service"},
            "progress": {"evaluations_done": 3, "max_evaluations": 10},
            "_runtime_miner": object(),
            "_control": ExecutionControl(),
        }

        with patch("api.manager_runtime.cleanup_cancelled_experiment") as cleanup_mock, patch(
            "api.manager_runtime.publish_event"
        ) as publish_mock:
            finalize_cancelled_job(manager, "job-1")

        job = manager._jobs["job-1"]
        self.assertEqual("cancelled", job["status"])
        self.assertIsNone(job["_runtime_miner"])
        self.assertIsNone(job["result"])
        self.assertIsNone(job["error"])
        self.assertIsNotNone(job["finished_at"])
        manager.job_store.delete_experiment.assert_called_once_with("job-1")
        cleanup_mock.assert_called_once()
        self.assertEqual(2, publish_mock.call_count)

    def test_request_java_experiment_cancel_calls_service_when_context_is_complete(self):
        manager = _FakeManager()

        with patch("api.manager_runtime.ProMServiceClient") as client_cls:
            client = client_cls.return_value
            request_java_experiment_cancel(
                manager,
                "job-1",
                {"execution_name": "exp-1", "service_url": "http://remote-service"},
            )

        client_cls.assert_called_once_with(
            base_url="http://remote-service",
            experiment_id="exp-1",
            timeout_seconds=123,
        )
        client.cancel_experiment.assert_called_once_with(experiment_id="exp-1")

    def test_request_java_experiment_cancel_ignores_missing_execution_name(self):
        manager = _FakeManager()

        with patch("api.manager_runtime.ProMServiceClient") as client_cls:
            request_java_experiment_cancel(manager, "job-1", {"service_url": "http://remote-service"})

        client_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
