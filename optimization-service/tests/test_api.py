import os
import queue
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import api


class FakeManager:
    def __init__(self):
        self.last_submit_payload = None
        self.listeners = []

    def list_jobs(self):
        return [{"job_id": "j1", "status": "completed"}]

    def submit(self, payload):
        self.last_submit_payload = payload
        if payload.get("raise") == "value":
            raise ValueError("bad payload")
        return {"job_id": "created", "status": "queued"}

    def get(self, job_id):
        if job_id == "missing":
            raise KeyError(job_id)
        return {"job_id": job_id, "status": "running"}

    def get_progress(self, job_id):
        if job_id == "missing":
            raise KeyError(job_id)
        return {
            "job_id": job_id,
            "status": "running",
            "evaluations_done": 7,
            "max_evaluations": 50,
            "percentage": 14.0,
        }

    def get_solutions(self, job_id, scope):
        if job_id == "missing":
            raise KeyError(job_id)
        if job_id == "pending":
            raise RuntimeError("job not completed")
        return {"job_id": job_id, "scope": scope, "count": 1, "solutions": [{"is_pareto": True}]}

    def get_artifacts(self, job_id, scope, include_pnml):
        if job_id == "missing":
            raise KeyError(job_id)
        if job_id == "pending":
            raise RuntimeError("job not completed")
        return {
            "job_id": job_id,
            "scope": scope,
            "include_pnml": include_pnml,
            "artifacts": [{"evaluation_id": "ev-1"}],
        }

    def subscribe_events(self, job_id):
        if job_id == "missing":
            raise KeyError(job_id)
        listener = queue.Queue()
        self.listeners.append(listener)
        initial = [
            {"event": "status_changed", "data": {"job_id": job_id, "status": "completed"}},
            {"event": "progress", "data": self.get_progress(job_id)},
        ]
        return listener, initial

    def unsubscribe_events(self, _job_id, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)


class OptimizationApiTest(unittest.TestCase):
    def setUp(self):
        self.original_manager = api._manager
        api._manager = FakeManager()
        self.client = api.app.test_client()

    def tearDown(self):
        api._manager = self.original_manager

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.get_json())

    def test_list_jobs(self):
        response = self.client.get("/optimizations")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertIn("jobs", body)
        self.assertEqual("j1", body["jobs"][0]["job_id"])

    def test_create_job_ok(self):
        response = self.client.post("/optimizations", json={"execution_name": "run_1", "log_path": "/data/log.xes"})
        self.assertEqual(202, response.status_code)
        body = response.get_json()
        self.assertEqual("created", body["job_id"])
        self.assertEqual("queued", body["status"])

    def test_create_job_validation_error(self):
        response = self.client.post("/optimizations", json={"raise": "value"})
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_request", response.get_json()["error"])

    def test_get_job_not_found(self):
        response = self.client.get("/optimizations/missing")
        self.assertEqual(404, response.status_code)
        self.assertEqual("not_found", response.get_json()["error"])

    def test_get_solutions(self):
        response = self.client.get("/optimizations/job-1/solutions?scope=pareto")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual("pareto", body["scope"])
        self.assertEqual(1, body["count"])

    def test_serialize_solution_includes_evaluation_error(self):
        class Sol:
            objectives = [0.1]
            variables = [0.2]
            attributes = {
                "evaluation_id": None,
                "pipeline": {"miner": {"key": "heuristics"}},
                "metrics": {"fitness": 0.0},
                "evaluation_error": "HTTPError: 500 Server Error",
            }

        payload = api._serialize_solution(Sol(), pareto_ids=set())
        self.assertEqual("HTTPError: 500 Server Error", payload["evaluation_error"])

    def test_get_solutions_invalid_scope(self):
        response = self.client.get("/optimizations/job-1/solutions?scope=bad")
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_request", response.get_json()["error"])

    def test_get_solutions_invalid_state(self):
        response = self.client.get("/optimizations/pending/solutions")
        self.assertEqual(409, response.status_code)
        self.assertEqual("invalid_state", response.get_json()["error"])

    def test_get_artifacts_defaults(self):
        response = self.client.get("/optimizations/job-1/artifacts")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["include_pnml"])
        self.assertEqual("pareto", body["scope"])

    def test_get_artifacts_scope_all_without_pnml(self):
        response = self.client.get("/optimizations/job-1/artifacts?scope=all&include_pnml=false")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual("all", body["scope"])
        self.assertFalse(body["include_pnml"])

    def test_get_progress(self):
        response = self.client.get("/optimizations/job-1/progress")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual(7, body["evaluations_done"])
        self.assertEqual(50, body["max_evaluations"])

    def test_get_progress_not_found(self):
        response = self.client.get("/optimizations/missing/progress")
        self.assertEqual(404, response.status_code)
        self.assertEqual("not_found", response.get_json()["error"])

    def test_stream_events(self):
        response = self.client.get("/optimizations/job-1/events")
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/event-stream; charset=utf-8", response.content_type)
        payload = response.get_data(as_text=True)
        self.assertIn("event: status_changed", payload)
        self.assertIn("\"status\": \"completed\"", payload)


class LogPathNormalizationTest(unittest.TestCase):
    def test_relative_filename_uses_logs_root(self):
        with mock.patch.dict(os.environ, {"LOGS_ROOT": "/data/logs"}, clear=False):
            self.assertEqual("/data/logs/BPI_Challenge_2013_open_problems.xes", api._normalize_log_path("BPI_Challenge_2013_open_problems.xes"))

    def test_absolute_path_is_kept(self):
        with mock.patch.dict(os.environ, {"LOGS_ROOT": "/data/logs"}, clear=False):
            self.assertEqual("/tmp/custom-log.xes", api._normalize_log_path("/tmp/custom-log.xes"))

    def test_relative_path_with_logs_prefix_is_not_duplicated(self):
        with mock.patch.dict(os.environ, {"LOGS_ROOT": "/data/logs"}, clear=False):
            self.assertEqual("/data/logs/BPI_Challenge_2013_open_problems.xes", api._normalize_log_path("data/logs/BPI_Challenge_2013_open_problems.xes"))

    def test_blank_path_is_rejected(self):
        with self.assertRaises(ValueError):
            api._normalize_log_path("   ")


if __name__ == "__main__":
    unittest.main()
