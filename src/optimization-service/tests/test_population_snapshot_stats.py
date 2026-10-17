import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from api.manager_runtime import _interval_evaluation_stats, execute_job
from execution_control import ExecutionControl


class PopulationSnapshotStatsTest(unittest.TestCase):
    def _run(self, evaluation, workers=1, max_workers=4):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = os.path.join(temporary_directory, "tiny.xes")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("<log></log>")
            manager = SimpleNamespace(
                _lock=threading.Lock(),
                _subscribers={},
                _jobs={"job-1": {
                    "job_id": "job-1", "status": "running",
                    "progress": {"evaluations_done": 0, "max_evaluations": 8},
                    "_control": ExecutionControl(),
                }},
                java_service_timeout_seconds=5,
            )
            config = {
                "execution_name": "integration-stats", "log_path": log_path,
                "service_url": "http://unused", "metrics": ["fitness", "precision", "simplicity", "generalisation"],
                "conformance_mode": "replay-token", "excluded_miners": ["ilp", "hybrid_ilp"],
                "discover": {"max_evaluations": 8, "population_size": 4, "n_partitions": 1,
                             "n_workers": workers, "seed": 7},
            }
            with patch.dict(os.environ, {"OPT_MAX_EVALUATION_WORKERS": str(max_workers)}), \
                 patch("java_service_client.ProMServiceClient.configure_pool", return_value={}), \
                 patch("java_service_client.ProMServiceClient.evaluate_pipeline", return_value=evaluation) as mocked:
                result = execute_job(manager, "job-1", config)

            self.assertGreater(mocked.call_count, 0)
            self.assertLessEqual(mocked.call_count, 8)
            self.assertEqual(result["actual_evaluations"], 8)
            self.assertEqual(result["optimizer_config"]["n_partitions"], 1)
            self.assertEqual(result["optimizer_config"]["population_size"], 4)
            self.assertEqual(len(result["log_sha256"]), 64)
            self.assertEqual(len(result["optimizer_source_sha256"]), 64)
            self.assertEqual(len(result["population_snapshots"]), 2)
            self.assertEqual([4, 4], [item["attempts_since_previous"] for item in result["population_snapshots"]])
            self.assertEqual(
                8 - mocked.call_count,
                sum(item["cache_hits_since_previous"] for item in result["population_snapshots"]),
            )
            return result

    def test_runtime_records_effective_config_and_snapshot_intervals(self):
        result = self._run({"metrics": {name: .8 for name in ["fitness", "precision", "simplicity", "generalisation"]}})
        self.assertEqual("not_certified", result["optimizer_config"]["reproducibility_status"])

    def test_effective_workers_and_scientific_result_fingerprint_are_recorded(self):
        evaluation = {"metrics": {name: .8 for name in ["fitness", "precision", "simplicity", "generalisation"]},
                      "evaluation_policy_version": "minersweeper-evaluation-v2", "model_semantic_sha256": "a"*64,
                      "evaluation_environment": {"java_version": "test", "java_classpath_sha256": "b"*64}}
        serial = self._run(evaluation, workers=1)
        parallel = self._run(evaluation, workers=16, max_workers=2)
        self.assertEqual(16, parallel["optimizer_config"]["requested_n_workers"])
        self.assertEqual(2, parallel["optimizer_config"]["n_workers"])
        self.assertEqual("controlled", parallel["optimizer_config"]["reproducibility_status"])
        self.assertEqual(serial["optimizer_config"]["result_sha256"], parallel["optimizer_config"]["result_sha256"])

    def test_counts_attempts_not_only_population_survivors(self):
        events = [
            {"evaluations_done": 3, "cache_hit": False, "has_error": True, "pipeline_key": "C"},
            {"evaluations_done": 1, "cache_hit": False, "has_error": False, "pipeline_key": "A"},
            {"evaluations_done": 2, "cache_hit": True, "has_error": False, "pipeline_key": "A"},
            {"evaluations_done": 4, "cache_hit": False, "has_error": False, "pipeline_key": "D"},
        ]

        self.assertEqual({
            "attempts_since_previous": 2,
            "cache_hits_since_previous": 1,
            "errors_since_previous": 0,
            "unique_pipelines_since_previous": 1,
        }, _interval_evaluation_stats(events, 0, 2))
        self.assertEqual({
            "attempts_since_previous": 2,
            "cache_hits_since_previous": 0,
            "errors_since_previous": 1,
            "unique_pipelines_since_previous": 2,
        }, _interval_evaluation_stats(events, 2, 4))

    def test_previous_evaluation_policy_is_preserved_but_not_announced_as_controlled(self):
        result = self._run({
            "metrics": {name: .8 for name in ["fitness", "precision", "simplicity", "generalisation"]},
            "evaluation_policy_version": "minersweeper-evaluation-v1",
            "model_semantic_sha256": "a" * 64,
            "evaluation_environment": {"java_version": "test", "java_classpath_sha256": "b" * 64},
        })
        self.assertEqual(["minersweeper-evaluation-v1"], result["optimizer_config"]["evaluation_policy_versions"])
        self.assertEqual("not_certified", result["optimizer_config"]["reproducibility_status"])


if __name__ == "__main__":
    unittest.main()
