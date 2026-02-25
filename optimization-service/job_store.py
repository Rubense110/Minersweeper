"""Database persistence for completed optimization experiments."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, create_engine
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
    pipeline: Mapped[Any] = mapped_column(JSON, nullable=False)
    is_pareto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    places: Mapped[Any] = mapped_column(JSON, nullable=False)
    transitions: Mapped[Any] = mapped_column(JSON, nullable=False)
    arcs: Mapped[Any] = mapped_column(JSON, nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="solutions")


class JobStore:
    """Stores completed experiments and final population solutions."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, future=True, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        Base.metadata.create_all(self.engine)

    def save_completed_experiment(self, experiment_data: Dict[str, Any], solutions: List[Dict[str, Any]]) -> None:
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
                            variables=item.get("variables", []),
                            objectives=item.get("objectives", []),
                            pipeline=item.get("pipeline", {}),
                            is_pareto=bool(item.get("is_pareto")),
                            places=item.get("places", []),
                            transitions=item.get("transitions", []),
                            arcs=item.get("arcs", []),
                        )
                    )
