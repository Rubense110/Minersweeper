import os
import sqlite3
import sys
import tempfile
import unittest
import math
from datetime import datetime, timezone

from sqlalchemy import inspect


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from job_store import JobStore, SnapshotSolution, Solution


class JobStoreRuntimeTest(unittest.TestCase):
    def test_save_completed_experiment_persists_runtime_ms(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "runtime.db")
            store = JobStore(db_url=f"sqlite:///{db_path}")

            experiment_data = {
                "experiment_id": "exp-1",
                "experiment_name": "exp-1",
                "start_at": datetime.now(timezone.utc),
                "end_at": datetime.now(timezone.utc),
                "max_evals": 10,
                "pop_size": 5,
                "miners": ["inductive"],
                "preprocessing": ["matrix_filter"],
                "log_path": "/data/logs/log.xes",
                "metrics": ["fitness"],
                "workers": 1,
            }
            solutions = [
                {
                    "variables": [0.1],
                    "objectives": [-0.9],
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 245,
                    "is_pareto": True,
                    "places": [],
                    "transitions": [],
                    "arcs": [],
                }
            ]

            store.save_completed_experiment(experiment_data, solutions)

            with store._session_factory() as session:
                persisted = session.query(Solution).one()
                self.assertEqual(245, persisted.runtime_ms)

    def test_init_adds_runtime_ms_column_for_existing_schema(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "legacy.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE experiments (
                        experiment_id VARCHAR(64) PRIMARY KEY,
                        experiment_name VARCHAR(255) NOT NULL,
                        start_at DATETIME NOT NULL,
                        end_at DATETIME NOT NULL,
                        max_evals INTEGER NOT NULL,
                        pop_size INTEGER,
                        miners JSON NOT NULL,
                        preprocessing JSON NOT NULL,
                        log_path TEXT NOT NULL,
                        metrics JSON NOT NULL,
                        workers INTEGER NOT NULL
                    );
                    CREATE TABLE solutions (
                        solution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        experiment_id VARCHAR(64) NOT NULL,
                        variables JSON NOT NULL,
                        objectives JSON NOT NULL,
                        pipeline JSON NOT NULL,
                        is_pareto BOOLEAN NOT NULL DEFAULT 0,
                        places JSON NOT NULL,
                        transitions JSON NOT NULL,
                        arcs JSON NOT NULL,
                        FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            store = JobStore(db_url=f"sqlite:///{db_path}")
            columns = {column["name"] for column in inspect(store.engine).get_columns("solutions")}
            self.assertIn("runtime_ms", columns)

    def test_save_completed_experiment_sanitizes_non_finite_json_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "nan.db")
            store = JobStore(db_url=f"sqlite:///{db_path}")

            experiment_data = {
                "experiment_id": "exp-nan",
                "experiment_name": "exp-nan",
                "start_at": datetime.now(timezone.utc),
                "end_at": datetime.now(timezone.utc),
                "max_evals": 1,
                "pop_size": 1,
                "miners": ["inductive"],
                "preprocessing": ["matrix_filter"],
                "log_path": "/data/logs/log.xes",
                "metrics": ["fitness", "precision"],
                "workers": 1,
            }
            solutions = [
                {
                    "variables": [0.1],
                    "objectives": [-0.5, float("nan")],
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 100,
                    "is_pareto": True,
                    "places": [],
                    "transitions": [],
                    "arcs": [],
                }
            ]

            store.save_completed_experiment(experiment_data, solutions)

            with store._session_factory() as session:
                persisted = session.query(Solution).one()
                self.assertTrue(all(math.isfinite(float(value)) for value in persisted.objectives))
                self.assertEqual(persisted.objectives, [-0.5, 0.0])

    def test_save_completed_experiment_persists_snapshot_solutions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "snapshots.db")
            store = JobStore(db_url=f"sqlite:///{db_path}")

            experiment_data = {
                "experiment_id": "exp-snap",
                "experiment_name": "exp-snap",
                "start_at": datetime.now(timezone.utc),
                "end_at": datetime.now(timezone.utc),
                "max_evals": 10,
                "pop_size": 5,
                "miners": ["inductive"],
                "preprocessing": ["matrix_filter"],
                "log_path": "/data/logs/log.xes",
                "metrics": ["fitness"],
                "workers": 1,
            }
            solutions = [
                {
                    "variables": [0.1],
                    "objectives": [-0.9],
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 245,
                    "is_pareto": True,
                    "places": [],
                    "transitions": [],
                    "arcs": [],
                }
            ]
            snapshot_solutions = [
                {
                    "snapshot_index": 1,
                    "evaluations_done": 5,
                    "member_index": 1,
                    "variables": [0.1],
                    "objectives": [-0.8],
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 200,
                    "is_pareto": True,
                    "places": [{"id": "p1"}],
                    "transitions": [{"id": "t1"}],
                    "arcs": [{"source": "p1", "target": "t1"}],
                },
                {
                    "snapshot_index": 1,
                    "evaluations_done": 5,
                    "member_index": 2,
                    "variables": [0.2],
                    "objectives": [-0.7],
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 210,
                    "is_pareto": False,
                    "places": [],
                    "transitions": [],
                    "arcs": [],
                },
            ]

            store.save_completed_experiment(experiment_data, solutions, snapshot_solutions)

            with store._session_factory() as session:
                persisted = session.query(SnapshotSolution).order_by(SnapshotSolution.member_index.asc()).all()
                self.assertEqual(2, len(persisted))
                self.assertEqual(1, persisted[0].snapshot_index)
                self.assertEqual(5, persisted[0].evaluations_done)
                self.assertEqual(1, persisted[0].member_index)
                self.assertEqual([{"id": "p1"}], persisted[0].places)
                self.assertFalse(persisted[1].is_pareto)

            exported = store.get_experiment_snapshot_solutions("exp-snap")
            self.assertEqual(2, len(exported))
            self.assertEqual(1, exported[0]["snapshot_index"])
            self.assertEqual(2, exported[1]["member_index"])


if __name__ == "__main__":
    unittest.main()
