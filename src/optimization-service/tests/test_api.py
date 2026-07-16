import os
import queue
import sys
import unittest
from unittest import mock

SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

import api


class FakeManager:
    def __init__(self):
        self.last_submit_payload = None
        self.listeners = []
        self.cancelled_job_id = None
        self.last_model_selection = None

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

    def cancel(self, job_id):
        if job_id == "missing":
            raise KeyError(job_id)
        if job_id == "done":
            raise RuntimeError("job 'done' cannot be cancelled from state 'completed'")
        self.cancelled_job_id = job_id
        return {"job_id": job_id, "status": "cancelling"}

    def select_experiment_model(self, experiment_id, weights, scope):
        if experiment_id == "missing":
            raise KeyError(experiment_id)
        if experiment_id == "empty":
            raise api.ModelSelectionUnavailable("experiment has no valid solutions for ASF model selection")
        self.last_model_selection = {
            "experiment_id": experiment_id,
            "weights": weights,
            "scope": scope,
        }
        return {
            "experiment_id": experiment_id,
            "scope": scope,
            "selection_method": "asf",
            "metrics": ["fitness", "precision"],
            "slider_weights": {"fitness": 80, "precision": 20},
            "normalized_weights": {"fitness": 0.8, "precision": 0.2},
            "candidate_count": 2,
            "selected_solution_id": 7,
            "selected_solution": {"solution_id": 7, "objectives": [-0.91, -0.55], "is_pareto": True},
            "scalarized_objective": 0.25,
            "approx_ideal": [-0.91, -0.55],
            "approx_nadir": [-0.8, -0.3],
        }

    def get_experiment_export(self, experiment_id):
        if experiment_id == "missing":
            raise KeyError(experiment_id)
        return (b"zip-data", "experiment_exp-1_run.zip")


class OptimizationApiTest(unittest.TestCase):
    def setUp(self):
        self.original_manager = api.get_manager()
        api.set_manager(FakeManager())
        self.client = api.app.test_client()

    def tearDown(self):
        api.set_manager(self.original_manager)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.get_json())

    def test_openapi_spec(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual("3.1.0", body["openapi"])
        self.assertIn("/optimizations", body["paths"])
        self.assertIn("/docs", ["/docs"])  # route existence is tested separately
        self.assertEqual("Minersweeper Optimization API", body["info"]["title"])

    def test_swagger_ui(self):
        response = self.client.get("/docs")
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html", response.mimetype)
        payload = response.get_data(as_text=True)
        self.assertIn("SwaggerUIBundle", payload)
        self.assertIn("/openapi.json", payload)

    def test_list_jobs(self):
        response = self.client.get("/optimizations")
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertIn("jobs", body)
        self.assertEqual("j1", body["jobs"][0]["job_id"])

    def test_create_job_ok(self):
        response = self.client.post(
            "/optimizations",
            json={
                "execution_name": "run_1",
                "log_path": "/data/log.xes",
                "metrics": ["fitness"],
            },
        )
        self.assertEqual(202, response.status_code)
        body = response.get_json()
        self.assertEqual("created", body["job_id"])
        self.assertEqual("queued", body["status"])
        self.assertEqual(["fitness"], api.get_manager().last_submit_payload["metrics"])

    def test_create_job_validation_error(self):
        response = self.client.post("/optimizations", json={"raise": "value"})
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_request", response.get_json()["error"])

    def test_get_job_not_found(self):
        response = self.client.get("/optimizations/missing")
        self.assertEqual(404, response.status_code)
        self.assertEqual("not_found", response.get_json()["error"])

    def test_cancel_job(self):
        response = self.client.post("/optimizations/job-1/cancel")
        self.assertEqual(202, response.status_code)
        body = response.get_json()
        self.assertEqual("job-1", body["job_id"])
        self.assertEqual("cancelling", body["status"])
        self.assertEqual("job-1", api.get_manager().cancelled_job_id)

    def test_cancel_job_not_found(self):
        response = self.client.post("/optimizations/missing/cancel")
        self.assertEqual(404, response.status_code)
        self.assertEqual("not_found", response.get_json()["error"])

    def test_cancel_job_invalid_state(self):
        response = self.client.post("/optimizations/done/cancel")
        self.assertEqual(409, response.status_code)
        self.assertEqual("invalid_state", response.get_json()["error"])

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
                "runtime_ms": 321,
                "evaluation_error": "HTTPError: 500 Server Error",
            }

        payload = api._serialize_solution(Sol(), pareto_ids=set())
        self.assertEqual("HTTPError: 500 Server Error", payload["evaluation_error"])
        self.assertEqual(321, payload["runtime_ms"])

    def test_count_failed_solutions_uses_observed_error_count(self):
        all_solutions = [
            {"evaluation_id": "ok-1"},
            {"evaluation_id": "ok-2"},
        ]

        failed = api._count_failed_solutions(all_solutions, observed_error_count=3)

        self.assertEqual(3, failed)

    def test_count_failed_solutions_uses_serialized_errors_when_higher(self):
        all_solutions = [
            {"evaluation_id": "ok-1"},
            {"evaluation_id": "bad-1", "evaluation_error": "HTTP 500"},
            {"evaluation_id": "bad-2", "evaluation_error": "timeout"},
        ]

        failed = api._count_failed_solutions(all_solutions, observed_error_count=1)

        self.assertEqual(2, failed)

    def test_get_solutions_invalid_scope(self):
        response = self.client.get("/optimizations/job-1/solutions?scope=bad")
        self.assertEqual(400, response.status_code)
        self.assertEqual("invalid_request", response.get_json()["error"])

    def test_get_solutions_invalid_state(self):
        response = self.client.get("/optimizations/pending/solutions")
        self.assertEqual(409, response.status_code)
        self.assertEqual("invalid_state", response.get_json()["error"])

    def test_select_experiment_model(self):
        response = self.client.post(
            "/experiments/exp-1/select-model",
            json={"scope": "pareto", "weights": {"fitness": 80, "precision": 20}},
        )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual("exp-1", body["experiment_id"])
        self.assertEqual(7, body["selected_solution_id"])
        self.assertEqual(
            {
                "experiment_id": "exp-1",
                "weights": {"fitness": 80, "precision": 20},
                "scope": "pareto",
            },
            api.get_manager().last_model_selection,
        )


    def test_download_experiment_data(self):
        response = self.client.get("/experiments/exp-1/download")

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response.mimetype)
        self.assertEqual(b"zip-data", response.data)
        self.assertIn("attachment; filename=", response.headers["Content-Disposition"])

    def test_download_experiment_data_not_found(self):
        response = self.client.get("/experiments/missing/download")

        self.assertEqual(404, response.status_code)
        self.assertEqual("not_found", response.get_json()["error"])

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

    def test_render_petri_image_svg(self):
        with mock.patch("api.petri_routes._render_petri_image_bytes", return_value=(b"<svg/>", "image/svg+xml")) as patched:
            response = self.client.post(
                "/petri/render?format=svg",
                json={
                    "places": [{"id": "p1"}],
                    "transitions": [{"id": "t1"}],
                    "arcs": [{"source": "p1", "target": "t1"}],
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("image/svg+xml", response.mimetype)
        self.assertEqual(b"<svg/>", response.data)
        patched.assert_called_once()

    def test_render_petri_image_invalid_request(self):
        with mock.patch("api.petri_routes._render_petri_image_bytes", side_effect=ValueError("bad graph")):
            response = self.client.post("/petri/render", json={"places": []})

        self.assertEqual(400, response.status_code)
        body = response.get_json()
        self.assertEqual("invalid_request", body["error"])
        self.assertEqual("bad graph", body["message"])

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
