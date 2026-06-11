from __future__ import annotations

from flask import current_app


def get_manager():
    return current_app.config["optimization_manager"]
