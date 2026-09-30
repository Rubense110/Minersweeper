import os
import sys
import tempfile
import unittest
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from execution_control import ExecutionControl, EvaluationTerminationUnconfirmed
from java_service_client import ProMServiceClient
from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem
from job_store import JobStore, ModelArtifact, Solution, SnapshotSolution


class PerformanceSafetyTest(unittest.TestCase):
    def test_job_queue_has_a_bound_and_cancelled_jobs_free_capacity(self):
        from api.manager import OptimizationJobManager
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OPT_MAX_QUEUED_JOBS": "2"}):
            manager = OptimizationJobManager("http://service", "sqlite:///" + os.path.join(directory, "jobs.db"), 30)
            with patch("api.manager.threading.Thread"):
                first = manager.submit({"log_path": "log.xes"})
                manager.submit({"log_path": "log.xes"})
                with self.assertRaisesRegex(ValueError, "queue is full"):
                    manager.submit({"log_path": "log.xes"})
                manager.cancel(first["job_id"])
                third = manager.submit({"log_path": "log.xes"})
                self.assertEqual("queued", third["status"])
                self.assertNotEqual(first["request"]["execution_name"], third["request"]["execution_name"])

    def test_timeout_polls_until_matching_request_has_stopped(self):
        client = ProMServiceClient("http://service", experiment_id="exp")
        response = Mock()
        response.json.return_value = {"experiment_id": "exp", "request_id": "req", "termination_confirmed": True}
        with patch("java_service_client.uuid.uuid4") as uuid, patch("java_service_client.requests.post", side_effect=requests.Timeout()), patch.object(client, "cancel_evaluation", return_value={"termination_confirmed": False}), patch("java_service_client.requests.get", return_value=response) as get:
            uuid.return_value.hex = "req"
            with self.assertRaises(requests.Timeout):
                client.evaluate_pipeline("log.xes", {}, ["fitness"])
            self.assertTrue(get.call_args.args[0].endswith("/req/status"))

    def test_cancellation_acknowledgement_for_other_request_is_not_confirmation(self):
        client = ProMServiceClient("http://service", experiment_id="exp")
        with patch.dict(os.environ, {"JAVA_CANCEL_GRACE_SECONDS": "0"}), patch.object(client, "cancel_evaluation", return_value={"experiment_id": "exp", "request_id": "other", "termination_confirmed": True}):
            with self.assertRaises(EvaluationTerminationUnconfirmed):
                client._request_evaluation_cancel("exp", "req")

    def test_uncertain_termination_stops_other_candidates_instead_of_penalizing_one(self):
        control = ExecutionControl()
        evaluator = Mock(side_effect=EvaluationTerminationUnconfirmed("still running"))
        problem = PipelineOptimizationProblem(log_path="log.xes", metrics_list=["fitness"], required_metrics=["fitness"], search_space=PipelineSearchSpace(), evaluator=evaluator, execution_control=control)
        with self.assertRaises(EvaluationTerminationUnconfirmed):
            problem.evaluate(problem.create_solution())
        with self.assertRaises(EvaluationTerminationUnconfirmed):
            control.raise_if_cancel_requested()
        with self.assertRaises(EvaluationTerminationUnconfirmed):
            problem.evaluate(problem.create_solution())
        self.assertEqual(1, evaluator.call_count)

    def test_infeasible_metrics_remain_unmeasured_and_cache_reuses_rejection(self):
        evaluator = Mock(return_value={"metrics": {}, "metrics_status": "skipped_infeasible", "model_schema_version": 3, "visible_transition_count": 1, "is_feasible": False, "constraint_violations": ["FINAL_NOT_REACHABLE"]})
        problem = PipelineOptimizationProblem(log_path="log.xes", metrics_list=["fitness"], required_metrics=["fitness"], search_space=PipelineSearchSpace(), evaluator=evaluator)
        first = problem.create_solution()
        second = problem.create_solution()
        second.variables = list(first.variables)
        problem.evaluate(first)
        problem.evaluate(second)
        self.assertEqual({}, first.attributes["metrics"])
        self.assertEqual("skipped_infeasible", second.attributes["metrics_status"])
        self.assertLess(first.constraints[0], 0)
        self.assertNotIn("evaluation_error", first.attributes)
        self.assertEqual(1, evaluator.call_count)

    def test_models_are_shared_across_snapshots_and_deleted_with_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(db_url="sqlite:///" + os.path.join(directory, "models.db"))
            self._check_shared_models(store)

    @unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is required")
    def test_postgres_normalized_models_replace_and_delete_with_foreign_keys(self):
        url = os.environ["TEST_POSTGRES_URL"]
        schema = "models_test_" + uuid.uuid4().hex
        admin = create_engine(url)
        store = None
        try:
            with admin.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            scoped = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
            store = JobStore(db_url=scoped)
            self._check_shared_models(store)
        finally:
            if store is not None:
                store.engine.dispose()
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            admin.dispose()

    def _check_shared_models(self, store):
        now = datetime.now(timezone.utc)
        experiment = {"experiment_id": "exp", "experiment_name": "exp", "start_at": now, "end_at": now, "max_evals": 1, "metrics": ["fitness"], "miners": [], "preprocessing": [], "workers": 1, "log_path": "log.xes"}
        solution = {"evaluation_id": "eval", "variables": [], "objectives": [-0.8], "metrics": {"fitness": .8}, "pipeline": {}, "places": [{"id": "p"}], "transitions": [], "arcs": [], "initial_marking": [], "final_marking": [], "final_markings": []}
        snapshots = [dict(solution, snapshot_index=index, evaluations_done=index, member_index=1) for index in range(1, 4)]
        store.save_completed_experiment(experiment, [solution], snapshots)
        with store._session_factory() as session:
            self.assertEqual(1, session.query(ModelArtifact).count())
            model_id = session.query(ModelArtifact).one().model_id
            self.assertEqual(model_id, session.query(Solution).one().model_id)
            self.assertTrue(all(row.model_id == model_id and row.places == [] for row in session.query(SnapshotSolution)))
        self.assertEqual(solution["places"], store.get_experiment_solutions("exp")[0]["places"])
        store.save_completed_experiment(experiment, [solution], snapshots)
        self.assertTrue(store.delete_experiment("exp"))
        with store._session_factory() as session:
            self.assertEqual(0, session.query(ModelArtifact).count())
            self.assertEqual(0, session.query(SnapshotSolution).count())


if __name__ == "__main__":
    unittest.main()
