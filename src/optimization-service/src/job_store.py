"""Database persistence for completed optimization experiments."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Dict, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    func,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_evals: Mapped[int] = mapped_column(Integer, nullable=False)
    pop_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    miners: Mapped[Any] = mapped_column(JSON, nullable=False)
    preprocessing: Mapped[Any] = mapped_column(JSON, nullable=False)
    log_path: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[Any] = mapped_column(JSON, nullable=False)
    workers: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_evaluations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conformance_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    log_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimizer_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prom_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality_policy_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    optimizer_config: Mapped[Any] = mapped_column(JSON, nullable=True)

    solutions: Mapped[List["Solution"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    snapshot_solutions: Mapped[List["SnapshotSolution"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    population_snapshots: Mapped[List["PopulationSnapshot"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )


class PopulationSnapshot(Base):
    __tablename__ = "population_snapshots"
    __table_args__ = (
        Index("ux_population_snapshots_experiment_index", "experiment_id", "snapshot_index", unique=True),
    )

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.experiment_id", ondelete="CASCADE"), nullable=False)
    snapshot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluations_done: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts_since_previous: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hits_since_previous: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors_since_previous: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unique_pipelines_since_previous: Mapped[int | None] = mapped_column(Integer, nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="population_snapshots")
    members: Mapped[List["SnapshotSolution"]] = relationship(back_populates="snapshot")


class Solution(Base):
    __tablename__ = "solutions"
    __table_args__ = (
        Index("ix_solutions_experiment", "experiment_id"),
        Index("ix_solutions_experiment_pareto", "experiment_id", "is_pareto"),
    )

    solution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("experiments.experiment_id", ondelete="CASCADE"),
        nullable=False,
    )
    variables: Mapped[Any] = mapped_column(JSON, nullable=False)
    objectives: Mapped[Any] = mapped_column(JSON, nullable=False)
    metrics: Mapped[Any] = mapped_column(JSON, nullable=False)
    pipeline: Mapped[Any] = mapped_column(JSON, nullable=False)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_pareto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    places: Mapped[Any] = mapped_column(JSON, nullable=False)
    transitions: Mapped[Any] = mapped_column(JSON, nullable=False)
    arcs: Mapped[Any] = mapped_column(JSON, nullable=False)
    visible_transition_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_feasible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    constraint_violations: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    model_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_marking: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    final_marking: Mapped[Any] = mapped_column(JSON, nullable=True)
    final_markings: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    pipeline_full: Mapped[Any] = mapped_column(JSON, nullable=True)
    evaluation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="solutions")


class SnapshotSolution(Base):
    __tablename__ = "snapshot_solutions"
    __table_args__ = (
        Index("ix_snapshot_solutions_experiment_snapshot", "experiment_id", "snapshot_index"),
        Index("ix_snapshot_solutions_experiment_evaluations", "experiment_id", "evaluations_done"),
        Index("ux_snapshot_solutions_member", "experiment_id", "snapshot_index", "member_index", unique=True),
    )

    snapshot_solution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("population_snapshots.snapshot_id", ondelete="CASCADE"), nullable=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("experiments.experiment_id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluations_done: Mapped[int] = mapped_column(Integer, nullable=False)
    member_index: Mapped[int] = mapped_column(Integer, nullable=False)
    variables: Mapped[Any] = mapped_column(JSON, nullable=False)
    objectives: Mapped[Any] = mapped_column(JSON, nullable=False)
    metrics: Mapped[Any] = mapped_column(JSON, nullable=False)
    pipeline: Mapped[Any] = mapped_column(JSON, nullable=False)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_pareto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    places: Mapped[Any] = mapped_column(JSON, nullable=False)
    transitions: Mapped[Any] = mapped_column(JSON, nullable=False)
    arcs: Mapped[Any] = mapped_column(JSON, nullable=False)
    visible_transition_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_feasible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    constraint_violations: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    model_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_marking: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    final_marking: Mapped[Any] = mapped_column(JSON, nullable=True)
    final_markings: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    pipeline_full: Mapped[Any] = mapped_column(JSON, nullable=True)
    evaluation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="snapshot_solutions")
    snapshot: Mapped[PopulationSnapshot | None] = relationship(back_populates="members")


class JobStore:
    """Stores completed experiments and final population solutions."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, future=True, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        Base.metadata.create_all(self.engine)
        self._ensure_schema_columns()

    def _ensure_schema_columns(self) -> None:
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        with self.engine.begin() as connection:
            if "experiments" in table_names:
                experiment_columns = {
                    column["name"]: column for column in inspector.get_columns("experiments")
                }
                if "seed" not in experiment_columns:
                    connection.execute(text("ALTER TABLE experiments ADD COLUMN seed BIGINT"))
                for name, sql_type in {
                    "actual_evaluations": "INTEGER",
                    "conformance_mode": "VARCHAR(32)",
                    "log_sha256": "VARCHAR(64)",
                    "optimizer_source_sha256": "VARCHAR(64)",
                    "prom_revision": "VARCHAR(128)",
                    "quality_policy_version": "VARCHAR(128)",
                    "optimizer_config": "JSON",
                }.items():
                    if name not in experiment_columns:
                        connection.execute(text(f"ALTER TABLE experiments ADD COLUMN {name} {sql_type}"))
                if (
                    "constraints" in experiment_columns
                    and self.engine.dialect.name == "postgresql"
                    and experiment_columns["constraints"].get("default") is None
                ):
                    # The removed experiment-constraints feature left this JSON
                    # column NOT NULL in existing PostgreSQL databases.  Keep its
                    # historical values, while allowing current ORM inserts that
                    # intentionally no longer map the obsolete column.
                    connection.execute(
                        text("ALTER TABLE experiments ALTER COLUMN constraints SET DEFAULT '[]'::json")
                    )

            if "solutions" in table_names:
                solution_columns = {
                    column["name"]: column for column in inspector.get_columns("solutions")
                }
                if "runtime_ms" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN runtime_ms INTEGER"))
                if "metrics" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN metrics JSON NOT NULL DEFAULT '{}'"))
                if "initial_marking" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN initial_marking JSON NOT NULL DEFAULT '[]'"))
                if "final_markings" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN final_markings JSON NOT NULL DEFAULT '[]'"))
                if "model_schema_version" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN model_schema_version INTEGER"))
                if "final_marking" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN final_marking JSON"))
                if "visible_transition_count" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN visible_transition_count INTEGER"))
                if "is_feasible" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN is_feasible BOOLEAN"))
                elif (
                    self.engine.dialect.name == "postgresql"
                    and not solution_columns["is_feasible"]["nullable"]
                ):
                    connection.execute(text("ALTER TABLE solutions ALTER COLUMN is_feasible DROP NOT NULL"))
                if "constraint_violations" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN constraint_violations JSON NOT NULL DEFAULT '[]'"))
                for name, sql_type in {
                    "pipeline_full": "JSON",
                    "evaluation_id": "VARCHAR(128)",
                    "fingerprint": "TEXT",
                    "evaluation_error": "TEXT",
                    "evaluation_status": "VARCHAR(32)",
                }.items():
                    if name not in solution_columns:
                        connection.execute(text(f"ALTER TABLE solutions ADD COLUMN {name} {sql_type}"))

            if "snapshot_solutions" in table_names:
                snapshot_columns = {
                    column["name"]: column for column in inspector.get_columns("snapshot_solutions")
                }
                if "metrics" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN metrics JSON NOT NULL DEFAULT '{}'"))
                if "initial_marking" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN initial_marking JSON NOT NULL DEFAULT '[]'"))
                if "final_markings" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN final_markings JSON NOT NULL DEFAULT '[]'"))
                if "model_schema_version" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN model_schema_version INTEGER"))
                if "final_marking" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN final_marking JSON"))
                if "visible_transition_count" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN visible_transition_count INTEGER"))
                if "is_feasible" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN is_feasible BOOLEAN"))
                elif (
                    self.engine.dialect.name == "postgresql"
                    and not snapshot_columns["is_feasible"]["nullable"]
                ):
                    connection.execute(
                        text("ALTER TABLE snapshot_solutions ALTER COLUMN is_feasible DROP NOT NULL")
                    )
                if "constraint_violations" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN constraint_violations JSON NOT NULL DEFAULT '[]'"))
                for name, sql_type in {
                    "snapshot_id": "INTEGER REFERENCES population_snapshots(snapshot_id) ON DELETE CASCADE",
                    "pipeline_full": "JSON",
                    "evaluation_id": "VARCHAR(128)",
                    "fingerprint": "TEXT",
                    "evaluation_error": "TEXT",
                    "evaluation_status": "VARCHAR(32)",
                }.items():
                    if name not in snapshot_columns:
                        connection.execute(text(f"ALTER TABLE snapshot_solutions ADD COLUMN {name} {sql_type}"))

                # Historical members remain valid: reconstruct their parent
                # snapshots, but leave unavailable evaluation counters NULL.
                old_snapshots = connection.execute(text(
                    "SELECT DISTINCT experiment_id, snapshot_index, evaluations_done "
                    "FROM snapshot_solutions WHERE snapshot_id IS NULL"
                )).all()
                for experiment_id, snapshot_index, evaluations_done in old_snapshots:
                    parent_id = connection.execute(text(
                        "SELECT snapshot_id FROM population_snapshots "
                        "WHERE experiment_id=:experiment_id AND snapshot_index=:snapshot_index"
                    ), {"experiment_id": experiment_id, "snapshot_index": snapshot_index}).scalar_one_or_none()
                    if parent_id is None:
                        connection.execute(text(
                            "INSERT INTO population_snapshots "
                            "(experiment_id, snapshot_index, evaluations_done) "
                            "VALUES (:experiment_id, :snapshot_index, :evaluations_done)"
                        ), {
                            "experiment_id": experiment_id,
                            "snapshot_index": snapshot_index,
                            "evaluations_done": evaluations_done,
                        })
                        parent_id = connection.execute(text(
                            "SELECT snapshot_id FROM population_snapshots "
                            "WHERE experiment_id=:experiment_id AND snapshot_index=:snapshot_index"
                        ), {"experiment_id": experiment_id, "snapshot_index": snapshot_index}).scalar_one()
                    connection.execute(text(
                        "UPDATE snapshot_solutions SET snapshot_id=:snapshot_id "
                        "WHERE experiment_id=:experiment_id AND snapshot_index=:snapshot_index AND snapshot_id IS NULL"
                    ), {
                        "snapshot_id": parent_id,
                        "experiment_id": experiment_id,
                        "snapshot_index": snapshot_index,
                    })

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sanitize_json(value: Any) -> Any:
        if isinstance(value, float):
            return value if math.isfinite(value) else 0.0
        if isinstance(value, list):
            return [JobStore._sanitize_json(item) for item in value]
        if isinstance(value, tuple):
            return [JobStore._sanitize_json(item) for item in value]
        if isinstance(value, dict):
            return {str(key): JobStore._sanitize_json(item) for key, item in value.items()}
        return value

    def save_completed_experiment(
        self,
        experiment_data: Dict[str, Any],
        solutions: List[Dict[str, Any]],
        snapshot_solutions: List[Dict[str, Any]] | None = None,
        population_snapshots: List[Dict[str, Any]] | None = None,
    ) -> None:
        experiment_id = str(experiment_data["experiment_id"])

        with self._session_factory() as session:
            with session.begin():
                existing = session.get(Experiment, experiment_id)
                if existing is not None:
                    session.delete(existing)
                    session.flush()

                experiment = Experiment(
                    experiment_id=experiment_id,
                    experiment_name=str(experiment_data["experiment_name"]),
                    start_at=experiment_data["start_at"],
                    end_at=experiment_data["end_at"],
                    max_evals=int(experiment_data["max_evals"]),
                    pop_size=experiment_data.get("pop_size"),
                    seed=self._to_int_or_none(experiment_data.get("seed")),
                    miners=experiment_data.get("miners", []),
                    preprocessing=experiment_data.get("preprocessing", []),
                    log_path=str(experiment_data["log_path"]),
                    metrics=experiment_data.get("metrics", []),
                    workers=int(experiment_data["workers"]),
                    actual_evaluations=self._to_int_or_none(experiment_data.get("actual_evaluations")),
                    conformance_mode=experiment_data.get("conformance_mode"),
                    log_sha256=experiment_data.get("log_sha256"),
                    optimizer_source_sha256=experiment_data.get("optimizer_source_sha256"),
                    prom_revision=experiment_data.get("prom_revision"),
                    quality_policy_version=experiment_data.get("quality_policy_version"),
                    optimizer_config=self._sanitize_json(experiment_data.get("optimizer_config")),
                )
                session.add(experiment)

                snapshot_data = {
                    int(item["snapshot_index"]): item for item in (population_snapshots or [])
                }
                for item in snapshot_solutions or []:
                    index = int(item.get("snapshot_index") or 0)
                    snapshot_data.setdefault(index, {
                        "snapshot_index": index,
                        "evaluations_done": int(item.get("evaluations_done") or 0),
                    })
                snapshot_rows: Dict[int, PopulationSnapshot] = {}
                for index, item in sorted(snapshot_data.items()):
                    snapshot = PopulationSnapshot(
                        experiment_id=experiment_id,
                        snapshot_index=index,
                        evaluations_done=int(item.get("evaluations_done") or 0),
                        attempts_since_previous=self._to_int_or_none(item.get("attempts_since_previous")),
                        cache_hits_since_previous=self._to_int_or_none(item.get("cache_hits_since_previous")),
                        errors_since_previous=self._to_int_or_none(item.get("errors_since_previous")),
                        unique_pipelines_since_previous=self._to_int_or_none(item.get("unique_pipelines_since_previous")),
                    )
                    session.add(snapshot)
                    snapshot_rows[index] = snapshot
                session.flush()

                for item in solutions:
                    session.add(
                        Solution(
                            experiment_id=experiment_id,
                            variables=self._sanitize_json(item.get("variables", [])),
                            objectives=self._sanitize_json(item.get("objectives", [])),
                            metrics=self._sanitize_json(item.get("metrics", {})),
                            pipeline=self._sanitize_json(item.get("pipeline", {})),
                            runtime_ms=self._to_int_or_none(item.get("runtime_ms")),
                            is_pareto=bool(item.get("is_pareto")),
                            places=self._sanitize_json(item.get("places", [])),
                            transitions=self._sanitize_json(item.get("transitions", [])),
                            arcs=self._sanitize_json(item.get("arcs", [])),
                            visible_transition_count=self._to_int_or_none(item.get("visible_transition_count")),
                            is_feasible=item.get("is_feasible") if isinstance(item.get("is_feasible"), bool) else None,
                            constraint_violations=self._sanitize_json(item.get("constraint_violations", [])),
                            model_schema_version=self._to_int_or_none(item.get("model_schema_version")),
                            initial_marking=self._sanitize_json(item.get("initial_marking", [])),
                            final_marking=self._sanitize_json(item.get("final_marking")),
                            final_markings=self._sanitize_json(item.get("final_markings", [])),
                            pipeline_full=self._sanitize_json(item.get("pipeline_full")),
                            evaluation_id=item.get("evaluation_id"),
                            fingerprint=item.get("fingerprint"),
                            evaluation_error=item.get("evaluation_error"),
                            evaluation_status=item.get("evaluation_status"),
                        )
                    )

                for item in snapshot_solutions or []:
                    session.add(
                        SnapshotSolution(
                            experiment_id=experiment_id,
                            snapshot_id=snapshot_rows[int(item.get("snapshot_index") or 0)].snapshot_id,
                            snapshot_index=int(item.get("snapshot_index") or 0),
                            evaluations_done=int(item.get("evaluations_done") or 0),
                            member_index=int(item.get("member_index") or 0),
                            variables=self._sanitize_json(item.get("variables", [])),
                            objectives=self._sanitize_json(item.get("objectives", [])),
                            metrics=self._sanitize_json(item.get("metrics", {})),
                            pipeline=self._sanitize_json(item.get("pipeline", {})),
                            runtime_ms=self._to_int_or_none(item.get("runtime_ms")),
                            is_pareto=bool(item.get("is_pareto")),
                            places=self._sanitize_json(item.get("places", [])),
                            transitions=self._sanitize_json(item.get("transitions", [])),
                            arcs=self._sanitize_json(item.get("arcs", [])),
                            visible_transition_count=self._to_int_or_none(item.get("visible_transition_count")),
                            is_feasible=item.get("is_feasible") if isinstance(item.get("is_feasible"), bool) else None,
                            constraint_violations=self._sanitize_json(item.get("constraint_violations", [])),
                            model_schema_version=self._to_int_or_none(item.get("model_schema_version")),
                            initial_marking=self._sanitize_json(item.get("initial_marking", [])),
                            final_marking=self._sanitize_json(item.get("final_marking")),
                            final_markings=self._sanitize_json(item.get("final_markings", [])),
                            pipeline_full=self._sanitize_json(item.get("pipeline_full")),
                            evaluation_id=item.get("evaluation_id"),
                            fingerprint=item.get("fingerprint"),
                            evaluation_error=item.get("evaluation_error"),
                            evaluation_status=item.get("evaluation_status"),
                        )
                    )

    def delete_experiment(self, experiment_id: str) -> bool:
        with self._session_factory() as session:
            with session.begin():
                existing = session.get(Experiment, experiment_id)
                if existing is None:
                    return False
                session.delete(existing)
                return True

    @staticmethod
    def _serialize_experiment(experiment: Experiment) -> Dict[str, Any]:
        return {
            "experiment_id": experiment.experiment_id,
            "experiment_name": experiment.experiment_name,
            "start_at": experiment.start_at.isoformat() if experiment.start_at else None,
            "end_at": experiment.end_at.isoformat() if experiment.end_at else None,
            "max_evals": int(experiment.max_evals),
            "pop_size": experiment.pop_size,
            "seed": experiment.seed,
            "miners": experiment.miners or [],
            "preprocessing": experiment.preprocessing or [],
            "log_path": experiment.log_path,
            "metrics": experiment.metrics or [],
            "workers": int(experiment.workers),
            "actual_evaluations": experiment.actual_evaluations,
            "conformance_mode": experiment.conformance_mode,
            "log_sha256": experiment.log_sha256,
            "optimizer_source_sha256": experiment.optimizer_source_sha256,
            "prom_revision": experiment.prom_revision,
            "quality_policy_version": experiment.quality_policy_version,
            "optimizer_config": experiment.optimizer_config,
        }

    @staticmethod
    def _serialize_population_snapshot(snapshot: PopulationSnapshot) -> Dict[str, Any]:
        return {
            "snapshot_id": int(snapshot.snapshot_id),
            "experiment_id": snapshot.experiment_id,
            "snapshot_index": int(snapshot.snapshot_index),
            "evaluations_done": int(snapshot.evaluations_done),
            "attempts_since_previous": snapshot.attempts_since_previous,
            "cache_hits_since_previous": snapshot.cache_hits_since_previous,
            "errors_since_previous": snapshot.errors_since_previous,
            "unique_pipelines_since_previous": snapshot.unique_pipelines_since_previous,
        }

    @staticmethod
    def _serialize_solution(solution: Solution) -> Dict[str, Any]:
        return {
            "solution_id": int(solution.solution_id),
            "experiment_id": solution.experiment_id,
            "variables": solution.variables or [],
            "objectives": solution.objectives or [],
            "metrics": solution.metrics or {},
            "pipeline": solution.pipeline or {},
            "runtime_ms": solution.runtime_ms,
            "is_pareto": bool(solution.is_pareto),
            "places": solution.places or [],
            "transitions": solution.transitions or [],
            "arcs": solution.arcs or [],
            "visible_transition_count": solution.visible_transition_count,
            "is_feasible": solution.is_feasible,
            "constraint_violations": solution.constraint_violations or [],
            "model_schema_version": solution.model_schema_version,
            "initial_marking": solution.initial_marking or [],
            "final_marking": solution.final_marking,
            "final_markings": solution.final_markings or [],
            "pipeline_full": solution.pipeline_full,
            "evaluation_id": solution.evaluation_id,
            "fingerprint": solution.fingerprint,
            "evaluation_error": solution.evaluation_error,
            "evaluation_status": solution.evaluation_status,
        }

    @staticmethod
    def _serialize_snapshot_solution(solution: SnapshotSolution) -> Dict[str, Any]:
        return {
            "snapshot_solution_id": int(solution.snapshot_solution_id),
            "snapshot_id": solution.snapshot_id,
            "experiment_id": solution.experiment_id,
            "snapshot_index": int(solution.snapshot_index),
            "evaluations_done": int(solution.evaluations_done),
            "member_index": int(solution.member_index),
            "variables": solution.variables or [],
            "objectives": solution.objectives or [],
            "metrics": solution.metrics or {},
            "pipeline": solution.pipeline or {},
            "runtime_ms": solution.runtime_ms,
            "is_pareto": bool(solution.is_pareto),
            "places": solution.places or [],
            "transitions": solution.transitions or [],
            "arcs": solution.arcs or [],
            "visible_transition_count": solution.visible_transition_count,
            "is_feasible": solution.is_feasible,
            "constraint_violations": solution.constraint_violations or [],
            "model_schema_version": solution.model_schema_version,
            "initial_marking": solution.initial_marking or [],
            "final_marking": solution.final_marking,
            "final_markings": solution.final_markings or [],
            "pipeline_full": solution.pipeline_full,
            "evaluation_id": solution.evaluation_id,
            "fingerprint": solution.fingerprint,
            "evaluation_error": solution.evaluation_error,
            "evaluation_status": solution.evaluation_status,
        }

    def list_experiments(self) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            experiments = session.execute(select(Experiment).order_by(Experiment.end_at.desc())).scalars().all()

            rows: List[Dict[str, Any]] = []
            for experiment in experiments:
                all_count = session.execute(
                    select(func.count(Solution.solution_id)).where(Solution.experiment_id == experiment.experiment_id)
                ).scalar_one()
                pareto_count = session.execute(
                    select(func.count(Solution.solution_id)).where(
                        Solution.experiment_id == experiment.experiment_id,
                        Solution.is_pareto.is_(True),
                        or_(Solution.is_feasible.is_(True), Solution.is_feasible.is_(None)),
                    )
                ).scalar_one()
                payload = self._serialize_experiment(experiment)
                payload["counts"] = {
                    "all_solutions": int(all_count),
                    "pareto_solutions": int(pareto_count),
                }
                rows.append(payload)
            return rows

    def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        with self._session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)

            all_count = session.execute(
                select(func.count(Solution.solution_id)).where(Solution.experiment_id == experiment_id)
            ).scalar_one()
            pareto_count = session.execute(
                select(func.count(Solution.solution_id)).where(
                    Solution.experiment_id == experiment_id,
                    Solution.is_pareto.is_(True),
                    or_(Solution.is_feasible.is_(True), Solution.is_feasible.is_(None)),
                )
            ).scalar_one()
            payload = self._serialize_experiment(experiment)
            payload["counts"] = {
                "all_solutions": int(all_count),
                "pareto_solutions": int(pareto_count),
            }
            snapshots = session.execute(
                select(PopulationSnapshot)
                .where(PopulationSnapshot.experiment_id == experiment_id)
                .order_by(PopulationSnapshot.snapshot_index.asc())
            ).scalars().all()
            payload["population_snapshots"] = [self._serialize_population_snapshot(item) for item in snapshots]
            return payload

    def get_experiment_population_snapshots(self, experiment_id: str) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            if session.get(Experiment, experiment_id) is None:
                raise KeyError(experiment_id)
            snapshots = session.execute(
                select(PopulationSnapshot)
                .where(PopulationSnapshot.experiment_id == experiment_id)
                .order_by(PopulationSnapshot.snapshot_index.asc())
            ).scalars().all()
            return [self._serialize_population_snapshot(item) for item in snapshots]

    def get_experiment_solutions(self, experiment_id: str, scope: str = "all") -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)

            stmt = select(Solution).where(Solution.experiment_id == experiment_id).order_by(Solution.solution_id.asc())
            if scope == "pareto":
                stmt = stmt.where(
                    Solution.is_pareto.is_(True),
                    or_(Solution.is_feasible.is_(True), Solution.is_feasible.is_(None)),
                )
            solutions = session.execute(stmt).scalars().all()
            return [self._serialize_solution(item) for item in solutions]

    def get_experiment_snapshot_solutions(self, experiment_id: str) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)

            stmt = (
                select(SnapshotSolution)
                .where(SnapshotSolution.experiment_id == experiment_id)
                .order_by(
                    SnapshotSolution.snapshot_index.asc(),
                    SnapshotSolution.member_index.asc(),
                )
            )
            snapshot_solutions = session.execute(stmt).scalars().all()
            return [self._serialize_snapshot_solution(item) for item in snapshot_solutions]
