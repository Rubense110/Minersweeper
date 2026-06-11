"""Minimal HTTP API for optimization jobs."""

from __future__ import annotations

import os

from flask import Flask
from flask_cors import CORS

from model_selection import ModelSelectionUnavailable

from .common import LOGGER, _QuietRequestHandler, _java_service_timeout_seconds, _normalize_log_path
from .experiment_routes import bp as experiment_bp
from .job_routes import bp as job_bp
from .manager import OptimizationJobManager
from .petri_routes import bp as petri_bp
from .serialization import _count_failed_solutions, _serialize_solution
from .system_routes import bp as system_bp


app = Flask(__name__)
CORS(app)
app.register_blueprint(system_bp)
app.register_blueprint(petri_bp)
app.register_blueprint(job_bp)
app.register_blueprint(experiment_bp)
app.config["optimization_manager"] = OptimizationJobManager(
    default_service_url=os.getenv("JAVA_SERVICE_URL", ""),
    db_url=os.getenv("OPT_DB_URL", "sqlite:////tmp/minersweeper-optimization.db"),
    java_service_timeout_seconds=_java_service_timeout_seconds(),
)


def get_manager() -> OptimizationJobManager:
    return app.config["optimization_manager"]


def set_manager(manager: OptimizationJobManager) -> None:
    app.config["optimization_manager"] = manager


def main() -> None:
    host = os.getenv("OPTIMIZATION_HOST", "0.0.0.0")
    port = int(os.getenv("OPTIMIZATION_PORT", "8080"))
    app.run(host=host, port=port, debug=False, threaded=True, request_handler=_QuietRequestHandler)


__all__ = [
    "LOGGER",
    "ModelSelectionUnavailable",
    "_count_failed_solutions",
    "_normalize_log_path",
    "_serialize_solution",
    "app",
    "get_manager",
    "main",
    "set_manager",
]
