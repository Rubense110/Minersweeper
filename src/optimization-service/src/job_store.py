"""Database persistence for completed optimization experiments."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Dict, List

from sqlalchemy import (
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
    miners: Mapped[Any] = mapped_column(JSON, nullable=False)
    preprocessing: Mapped[Any] = mapped_column(JSON, nullable=False)
    log_path: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[Any] = mapped_column(JSON, nullable=False)
    workers: Mapped[int] = mapped_column(Integer, nullable=False)

    solutions: Mapped[List["Solution"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    snapshot_solutions: Mapped[List["SnapshotSolution"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )


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

    experiment: Mapped[Experiment] = relationship(back_populates="solutions")


class SnapshotSolution(Base):
    __tablename__ = "snapshot_solutions"
    __table_args__ = (
        Index("ix_snapshot_solutions_experiment_snapshot", "experiment_id", "snapshot_index"),
        Index("ix_snapshot_solutions_experiment_evaluations", "experiment_id", "evaluations_done"),
        Index("ux_snapshot_solutions_member", "experiment_id", "snapshot_index", "member_index", unique=True),
    )

    snapshot_solution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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

    experiment: Mapped[Experiment] = relationship(back_populates="snapshot_solutions")


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
                experiment_columns = {column["name"] for column in inspector.get_columns("experiments")}
            if "solutions" in table_names:
                solution_columns = {column["name"] for column in inspector.get_columns("solutions")}
                if "runtime_ms" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN runtime_ms INTEGER"))
                if "metrics" not in solution_columns:
                    connection.execute(text("ALTER TABLE solutions ADD COLUMN metrics JSON NOT NULL DEFAULT '{}'"))

            if "snapshot_solutions" in table_names:
                snapshot_columns = {column["name"] for column in inspector.get_columns("snapshot_solutions")}
                if "metrics" not in snapshot_columns:
                    connection.execute(text("ALTER TABLE snapshot_solutions ADD COLUMN metrics JSON NOT NULL DEFAULT '{}'"))

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
                    miners=experiment_data.get("miners", []),
                    preprocessing=experiment_data.get("preprocessing", []),
                    log_path=str(experiment_data["log_path"]),
                    metrics=experiment_data.get("metrics", []),
                    workers=int(experiment_data["workers"]),
                )
                session.add(experiment)

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
                        )
                    )

                for item in snapshot_solutions or []:
                    session.add(
                        SnapshotSolution(
                            experiment_id=experiment_id,
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
                        )
                    )

    def delete_experiment(self, experiment_id: str) -> None:
        with self._session_factory() as session:
            with session.begin():
                existing = session.get(Experiment, experiment_id)
                if existing is not None:
                    session.delete(existing)

    @staticmethod
    def _serialize_experiment(experiment: Experiment) -> Dict[str, Any]:
        return {
            "experiment_id": experiment.experiment_id,
            "experiment_name": experiment.experiment_name,
            "start_at": experiment.start_at.isoformat() if experiment.start_at else None,
            "end_at": experiment.end_at.isoformat() if experiment.end_at else None,
            "max_evals": int(experiment.max_evals),
            "pop_size": experiment.pop_size,
            "miners": experiment.miners or [],
            "preprocessing": experiment.preprocessing or [],
            "log_path": experiment.log_path,
            "metrics": experiment.metrics or [],
            "workers": int(experiment.workers),
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
        }

    @staticmethod
    def _serialize_snapshot_solution(solution: SnapshotSolution) -> Dict[str, Any]:
        return {
            "snapshot_solution_id": int(solution.snapshot_solution_id),
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
                )
            ).scalar_one()
            payload = self._serialize_experiment(experiment)
            payload["counts"] = {
                "all_solutions": int(all_count),
                "pareto_solutions": int(pareto_count),
            }
            return payload

    def get_experiment_solutions(self, experiment_id: str, scope: str = "all") -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)

            stmt = select(Solution).where(Solution.experiment_id == experiment_id).order_by(Solution.solution_id.asc())
            if scope == "pareto":
                stmt = stmt.where(Solution.is_pareto.is_(True))
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
