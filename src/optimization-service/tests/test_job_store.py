import os
import sqlite3
import sys
import tempfile
import unittest
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from job_store import Base, JobStore, PopulationSnapshot, SnapshotSolution, Solution


class JobStoreRuntimeTest(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("TEST_POSTGRES_URL"),
        "TEST_POSTGRES_URL is required for the PostgreSQL legacy-schema compatibility test",
    )
    def test_postgres_legacy_constraints_schema_can_persist_current_experiment(self):
        admin_url = os.environ["TEST_POSTGRES_URL"]
        schema = f"job_store_legacy_{uuid.uuid4().hex}"
        admin_engine = create_engine(admin_url, future=True)
        scoped_url = make_url(admin_url).update_query_dict(
            {"options": f"-csearch_path={schema}"}
        )
        scoped_engine = create_engine(scoped_url, future=True)

        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            Base.metadata.create_all(scoped_engine)
            with scoped_engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE experiments ALTER COLUMN constraints SET NOT NULL")
                )
                connection.execute(
                    text("ALTER TABLE solutions ALTER COLUMN is_feasible SET NOT NULL")
                )
                connection.execute(
                    text("ALTER TABLE snapshot_solutions ALTER COLUMN is_feasible SET NOT NULL")
                )

            store = JobStore(db_url=scoped_url)
            experiment_columns = {
                column["name"]: column
                for column in inspect(store.engine).get_columns("experiments")
            }
            solution_columns = {
                column["name"]: column
                for column in inspect(store.engine).get_columns("solutions")
            }
            snapshot_columns = {
                column["name"]: column
                for column in inspect(store.engine).get_columns("snapshot_solutions")
            }
            self.assertIsNotNone(experiment_columns["constraints"]["default"])
            self.assertTrue(solution_columns["is_feasible"]["nullable"])
            self.assertTrue(snapshot_columns["is_feasible"]["nullable"])

            now = datetime.now(timezone.utc)
            store.save_completed_experiment(
                {
                    "experiment_id": "legacy-compatible",
                    "experiment_name": "legacy-compatible",
                    "start_at": now,
                    "end_at": now,
                    "max_evals": 1,
                    "pop_size": 1,
                    "seed": 1,
                    "miners": ["alpha"],
                    "preprocessing": ["matrix_filter"],
                    "log_path": "/data/logs/log.xes",
                    "metrics": ["fitness"],
                    "workers": 1,
                },
                [
                    {
                        "variables": [],
                        "objectives": [0.0],
                        "metrics": {},
                        "pipeline": {},
                        "is_pareto": False,
                        "places": [],
                        "transitions": [],
                        "arcs": [],
                        "is_feasible": None,
                    }
                ],
            )

            with store.engine.connect() as connection:
                constraints = connection.execute(
                    text(
                        "SELECT constraints::text FROM experiments "
                        "WHERE experiment_id = 'legacy-compatible'"
                    )
                ).scalar_one()
                persisted_feasibility = connection.execute(
                    text(
                        "SELECT is_feasible FROM solutions "
                        "WHERE experiment_id = 'legacy-compatible'"
                    )
                ).scalar_one()
            self.assertEqual("[]", constraints)
            self.assertIsNone(persisted_feasibility)
        finally:
            scoped_engine.dispose()
            admin_engine.dispose()
            cleanup_engine = create_engine(admin_url, future=True)
            try:
                with cleanup_engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            finally:
                cleanup_engine.dispose()

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
                "seed": 123456789,
                "miners": ["inductive"],
                "preprocessing": ["matrix_filter"],
                "log_path": "/data/logs/log.xes",
                "metrics": ["fitness"],
                "workers": 1,
                "actual_evaluations": 10,
                "conformance_mode": "replay-token",
                "log_sha256": "a" * 64,
                "optimizer_source_sha256": "b" * 64,
                "prom_revision": "prom-test-revision",
                "quality_policy_version": "quality-v3",
                "optimizer_config": {"n_partitions": 2, "reference_direction_count": 10},
            }
            solutions = [
                {
                    "variables": [0.1],
                    "objectives": [-0.9],
                    "metrics": {"fitness": 0.9, "places": 8.0},
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "pipeline_full": {"miner": {"key": "inductive", "variant": "Inductive Miner (IM)", "parameters": {}}},
                    "evaluation_id": "eval-final",
                    "fingerprint": "fp-final",
                    "evaluation_status": "feasible",
                    "logical_attempt_id": 7,
                    "constraints": [0.0],
                    "evaluation_policy_version": "minersweeper-evaluation-v1",
                    "model_semantic_sha256": "d" * 64,
                    "discovery_metadata": {"policy_version": "minersweeper-split-v2", "route": "standard"},
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
                self.assertEqual({"fitness": 0.9, "places": 8.0}, persisted.metrics)

            experiment = store.get_experiment("exp-1")
            self.assertEqual(123456789, experiment["seed"])
            saved = store.get_experiment_solutions("exp-1", scope="all")[0]
            self.assertEqual(7, saved["logical_attempt_id"])
            self.assertEqual([0.0], saved["constraints"])
            self.assertEqual("minersweeper-evaluation-v1", saved["evaluation_policy_version"])
            self.assertEqual("d" * 64, saved["model_semantic_sha256"])
            self.assertEqual(solutions[0]["discovery_metadata"], saved["discovery_metadata"])

            with store._session_factory() as session:
                session.add_all(
                    [
                        Solution(
                            experiment_id="exp-1",
                            variables=[],
                            objectives=[-0.8],
                            metrics={"fitness": 0.8},
                            pipeline={},
                            is_pareto=True,
                            places=[],
                            transitions=[],
                            arcs=[],
                            is_feasible=True,
                        ),
                        Solution(
                            experiment_id="exp-1",
                            variables=[],
                            objectives=[-1.0],
                            metrics={"fitness": 1.0},
                            pipeline={},
                            is_pareto=True,
                            places=[],
                            transitions=[],
                            arcs=[],
                            is_feasible=False,
                        ),
                    ]
                )
                session.commit()

            pareto_solutions = store.get_experiment_solutions("exp-1", scope="pareto")
            self.assertEqual([None, True], [item["is_feasible"] for item in pareto_solutions])
            self.assertEqual(2, store.get_experiment("exp-1")["counts"]["pareto_solutions"])

            with store._session_factory() as session:
                for failure in ({"evaluation_error": "invalid metric"}, {"evaluation_error": ""}, {"evaluation_status": "error"}):
                    session.add(Solution(
                        experiment_id="exp-1", variables=[], objectives=[-1.0], metrics={"fitness": 1.0},
                        pipeline={}, is_pareto=True, places=[], transitions=[], arcs=[], is_feasible=True,
                        **failure,
                    ))
                session.commit()
            all_solutions = store.get_experiment_solutions("exp-1", scope="all")
            self.assertEqual(6, len(all_solutions))
            errors = [item for item in all_solutions if item["evaluation_error"] is not None or item["evaluation_status"] == "error"]
            self.assertEqual(3, len(errors))
            self.assertTrue(all(item["is_pareto"] is False for item in errors))
            self.assertEqual(2, len(store.get_experiment_solutions("exp-1", scope="pareto")))
            self.assertEqual(2, store.get_experiment("exp-1")["counts"]["pareto_solutions"])
            self.assertEqual(2, store.list_experiments()[0]["counts"]["pareto_solutions"])

    def test_snapshot_serialization_excludes_historical_errors_from_pareto(self):
        for failure in ({"evaluation_error": "invalid metric"}, {"evaluation_error": ""}, {"evaluation_status": "error"}):
            with self.subTest(failure=failure):
                solution = SnapshotSolution(
                    snapshot_solution_id=1, snapshot_index=0, evaluations_done=1,
                    member_index=0, is_pareto=True, is_feasible=True, **failure,
                )
                self.assertFalse(JobStore._serialize_snapshot_solution(solution)["is_pareto"])

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
                    CREATE TABLE snapshot_solutions (
                        snapshot_solution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        experiment_id VARCHAR(64) NOT NULL,
                        snapshot_index INTEGER NOT NULL,
                        evaluations_done INTEGER NOT NULL,
                        member_index INTEGER NOT NULL,
                        variables JSON NOT NULL,
                        objectives JSON NOT NULL,
                        pipeline JSON NOT NULL,
                        runtime_ms INTEGER,
                        is_pareto BOOLEAN NOT NULL,
                        places JSON NOT NULL,
                        transitions JSON NOT NULL,
                        arcs JSON NOT NULL
                    );
                    INSERT INTO experiments
                    (experiment_id, experiment_name, start_at, end_at, max_evals, pop_size,
                     miners, preprocessing, log_path, metrics, workers)
                    VALUES ('old', 'old', '2026-01-01', '2026-01-01', 2, 1,
                            '[]', '[]', '/data/old.xes', '["fitness"]', 1);
                    INSERT INTO snapshot_solutions
                    (experiment_id, snapshot_index, evaluations_done, member_index,
                     variables, objectives, pipeline, is_pareto, places, transitions, arcs)
                    VALUES ('old', 1, 1, 1, '[]', '[-0.5]', '{}', 0, '[]', '[]', '[]');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            store = JobStore(db_url=f"sqlite:///{db_path}")
            columns = {column["name"] for column in inspect(store.engine).get_columns("solutions")}
            self.assertIn("runtime_ms", columns)
            self.assertIn("metrics", columns)
            self.assertIn("initial_marking", columns)
            self.assertIn("final_marking", columns)
            self.assertIn("final_markings", columns)
            self.assertIn("model_schema_version", columns)
            self.assertIn("reproducibility_metadata", columns)
            self.assertIn("visible_transition_count", columns)
            self.assertIn("is_feasible", columns)
            self.assertIn("constraint_violations", columns)
            self.assertIn("pipeline_full", columns)
            self.assertIn("evaluation_status", columns)
            experiment_columns = {column["name"] for column in inspect(store.engine).get_columns("experiments")}
            self.assertIn("seed", experiment_columns)
            self.assertIn("optimizer_config", experiment_columns)
            old = store.get_experiment("old")
            self.assertIsNone(old["optimizer_config"])
            self.assertEqual(1, old["population_snapshots"][0]["snapshot_index"])
            self.assertIsNone(old["population_snapshots"][0]["cache_hits_since_previous"])
            self.assertEqual(
                old["population_snapshots"][0]["snapshot_id"],
                store.get_experiment_snapshot_solutions("old")[0]["snapshot_id"],
            )

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
                    "metrics": {"fitness": 0.5, "precision": float("nan")},
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
                self.assertEqual(persisted.metrics, {"fitness": 0.5, "precision": 0.0})

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
                "actual_evaluations": 10,
                "conformance_mode": "replay-token",
                "log_sha256": "a" * 64,
                "optimizer_source_sha256": "b" * 64,
                "prom_revision": "prom-test-revision",
                "quality_policy_version": "quality-v3",
                "optimizer_config": {"n_partitions": 2, "reference_direction_count": 10},
            }
            solutions = [
                {
                    "variables": [0.1],
                    "objectives": [-0.9],
                    "metrics": {"fitness": 0.9},
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "pipeline_full": {"miner": {"key": "inductive", "variant": "Inductive Miner (IM)", "parameters": {}}},
                    "evaluation_id": "eval-final",
                    "fingerprint": "fp-final",
                    "evaluation_status": "feasible",
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
                    "metrics": {"fitness": 0.8, "places": 9.0},
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "pipeline_full": {"miner": {"key": "inductive", "variant": "Inductive Miner (IM)", "parameters": {}}},
                    "evaluation_id": "eval-snapshot",
                    "logical_attempt_id": 4,
                    "constraints": [0.0],
                    "evaluation_policy_version": "minersweeper-evaluation-v1",
                    "model_semantic_sha256": "e" * 64,
                    "discovery_metadata": {"policy_version": "minersweeper-split-v2", "route": "standard"},
                    "fingerprint": "fp-snapshot",
                    "evaluation_status": "feasible",
                    "runtime_ms": 200,
                    "is_pareto": True,
                    "places": [{"id": "p1"}],
                    "transitions": [{"id": "t1", "is_invisible": False}],
                    "arcs": [{"source": "p1", "target": "t1"}],
                    "visible_transition_count": 1,
                    "is_feasible": True,
                    "constraint_violations": [],
                    "model_schema_version": 2,
                    "initial_marking": [{"place_id": "p1", "tokens": 1}],
                    "final_marking": [{"place_id": "p2", "tokens": 2}],
                    "final_markings": [[{"place_id": "p2", "tokens": 1}]],
                },
                {
                    "snapshot_index": 1,
                    "evaluations_done": 5,
                    "member_index": 2,
                    "variables": [0.2],
                    "objectives": [-0.7],
                    "metrics": {"fitness": 0.7, "places": 14.0},
                    "pipeline": {"miner": {"variant": "Inductive Miner (IM)", "parameters": {}}},
                    "runtime_ms": 210,
                    "is_pareto": False,
                    "places": [],
                    "transitions": [],
                    "arcs": [],
                    "initial_marking": [],
                    "final_markings": [],
                },
            ]

            snapshot_stats = [{
                "snapshot_index": 1,
                "evaluations_done": 5,
                "attempts_since_previous": 5,
                "cache_hits_since_previous": 2,
                "errors_since_previous": 1,
                "unique_pipelines_since_previous": 3,
            }]
            store.save_completed_experiment(experiment_data, solutions, snapshot_solutions, snapshot_stats)

            with store._session_factory() as session:
                persisted = session.query(SnapshotSolution).order_by(SnapshotSolution.member_index.asc()).all()
                self.assertEqual(2, len(persisted))
                self.assertEqual(1, persisted[0].snapshot_index)
                self.assertEqual(5, persisted[0].evaluations_done)
                self.assertEqual(1, persisted[0].member_index)
                self.assertEqual([{"id": "p1"}], persisted[0].model.payload["places"])
                self.assertEqual([{"place_id": "p1", "tokens": 1}], persisted[0].model.payload["initial_marking"])
                self.assertEqual([{"place_id": "p2", "tokens": 2}], persisted[0].model.payload["final_marking"])
                self.assertEqual([[{"place_id": "p2", "tokens": 1}]], persisted[0].model.payload["final_markings"])
                self.assertEqual(2, persisted[0].model_schema_version)
                self.assertEqual(1, persisted[0].visible_transition_count)
                self.assertTrue(persisted[0].is_feasible)
                self.assertEqual([], persisted[0].constraint_violations)
                self.assertFalse(persisted[1].is_pareto)
                parent = session.query(PopulationSnapshot).one()
                self.assertEqual(parent.snapshot_id, persisted[0].snapshot_id)
                self.assertEqual(5, parent.attempts_since_previous)
                self.assertEqual(2, parent.cache_hits_since_previous)

            exported = store.get_experiment_snapshot_solutions("exp-snap")
            self.assertEqual(2, len(exported))
            self.assertEqual(1, exported[0]["snapshot_index"])
            self.assertEqual(2, exported[1]["member_index"])
            self.assertEqual([{"place_id": "p1", "tokens": 1}], exported[0]["initial_marking"])
            self.assertEqual([{"place_id": "p2", "tokens": 2}], exported[0]["final_marking"])
            self.assertTrue(exported[0]["is_feasible"])
            self.assertEqual([[{"place_id": "p2", "tokens": 1}]], exported[0]["final_markings"])
            self.assertEqual("eval-snapshot", exported[0]["evaluation_id"])
            self.assertEqual(4, exported[0]["logical_attempt_id"])
            self.assertEqual([0.0], exported[0]["constraints"])
            self.assertEqual("e" * 64, exported[0]["model_semantic_sha256"])
            self.assertEqual(snapshot_solutions[0]["discovery_metadata"], exported[0]["discovery_metadata"])
            self.assertEqual("inductive", exported[0]["pipeline_full"]["miner"]["key"])
            experiment = store.get_experiment("exp-snap")
            self.assertEqual("replay-token", experiment["conformance_mode"])
            self.assertEqual(10, experiment["actual_evaluations"])
            self.assertEqual(2, experiment["optimizer_config"]["n_partitions"])
            self.assertEqual(2, experiment["population_snapshots"][0]["cache_hits_since_previous"])
            self.assertEqual("eval-final", store.get_experiment_solutions("exp-snap")[0]["evaluation_id"])


if __name__ == "__main__":
    unittest.main()
