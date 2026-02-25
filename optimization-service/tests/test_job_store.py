import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from sqlalchemy import inspect


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from job_store import JobStore, Solution


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


if __name__ == "__main__":
    unittest.main()
