import os
import sys
import threading
import unittest
from unittest.mock import Mock, patch


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from execution_control import ExecutionControl
from api.manager_persistence import persist_completed_experiment


class _FakeManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self.default_service_url = "http://java-service"
        self.java_service_timeout_seconds = 123
        self.job_store = Mock()


class ManagerPersistenceTest(unittest.TestCase):
    def test_persist_completed_experiment_cleans_remote_artifacts_after_save(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "started_at": "2026-06-14T11:29:25.723111+00:00",
            "finished_at": "2026-06-14T11:29:33.884817+00:00",
            "request": {
                "execution_name": "exp-1",
                "service_url": "http://remote-service",
                "log_path": "/data/log.xes",
                "metrics": ["fitness"],
                "discover": {"max_evaluations": 100, "population_size": 20, "n_workers": 8},
            },
            "result": {
                "all_solutions": [],
                "population_snapshots": [],
                "catalogs": {"miners": ["inductive"], "preprocessing": ["variant_filter"]},
                "metrics_order": ["fitness"],
            },
            "_control": ExecutionControl(),
        }

        with patch("api.manager_persistence.ProMServiceClient") as client_cls:
            client = client_cls.return_value
            persist_completed_experiment(manager, "job-1")

        manager.job_store.save_completed_experiment.assert_called_once()
        client_cls.assert_called_once_with(
            base_url="http://remote-service",
            experiment_id="exp-1",
            timeout_seconds=123,
        )
        client.fetch_artifacts.assert_not_called()
        client.cleanup_experiment.assert_called_once_with(experiment_id="exp-1")

    def test_persist_completed_experiment_ignores_cleanup_failures(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "started_at": "2026-06-14T11:29:25.723111+00:00",
            "finished_at": "2026-06-14T11:29:33.884817+00:00",
            "request": {
                "execution_name": "exp-1",
                "service_url": "http://remote-service",
                "log_path": "/data/log.xes",
                "metrics": ["fitness"],
                "discover": {"max_evaluations": 100, "population_size": 20, "n_workers": 8},
            },
            "result": {
                "all_solutions": [],
                "population_snapshots": [],
                "catalogs": {"miners": [], "preprocessing": []},
                "metrics_order": ["fitness"],
            },
            "_control": ExecutionControl(),
        }

        with patch("api.manager_persistence.ProMServiceClient") as client_cls:
            client_cls.return_value.cleanup_experiment.side_effect = RuntimeError("cleanup failed")
            persist_completed_experiment(manager, "job-1")

        manager.job_store.save_completed_experiment.assert_called_once()

    def test_persist_completed_experiment_uses_artifact_markings(self):
        manager = _FakeManager()
        manager._jobs["job-1"] = {
            "job_id": "job-1",
            "started_at": "2026-06-14T11:29:25.723111+00:00",
            "finished_at": "2026-06-14T11:29:33.884817+00:00",
            "request": {
                "execution_name": "exp-1",
                "service_url": "http://remote-service",
                "log_path": "/data/log.xes",
                "metrics": ["fitness"],
                "discover": {"max_evaluations": 100, "population_size": 20, "n_workers": 8},
            },
            "result": {
                "all_solutions": [
                    {
                        "evaluation_id": "eval-1",
                        "variables": [0.1],
                        "objectives": [-1.0],
                        "metrics": {"fitness": 1.0},
                        "pipeline": {},
                        "runtime_ms": 12,
                        "is_pareto": True,
                    }
                ],
                "population_snapshots": [],
                "catalogs": {"miners": [], "preprocessing": []},
                "metrics_order": ["fitness"],
            },
            "_control": ExecutionControl(),
        }

        pnml = """
        <pnml>
          <net id="n1">
            <place id="p1" />
            <transition id="t1"><name><text>A</text></name></transition>
            <arc id="a1" source="p1" target="t1" />
          </net>
        </pnml>
        """
        with patch("api.manager_persistence.ProMServiceClient") as client_cls:
            client = client_cls.return_value
            client.fetch_artifacts.return_value = [
                {
                    "evaluation_id": "eval-1",
                    "pnml": pnml,
                    "initial_marking": [{"place_id": "real-start", "tokens": 1}],
                    "final_markings": [[{"place_id": "real-end", "tokens": 1}]],
                }
            ]
            persist_completed_experiment(manager, "job-1")

        _experiment_data, solutions, _snapshots = manager.job_store.save_completed_experiment.call_args.args
        self.assertEqual([{"place_id": "real-start", "tokens": 1}], solutions[0]["initial_marking"])
        self.assertEqual([[{"place_id": "real-end", "tokens": 1}]], solutions[0]["final_markings"])


if __name__ == "__main__":
    unittest.main()
