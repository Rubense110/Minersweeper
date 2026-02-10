"""HTTP client for the Java ProM service."""

from __future__ import annotations

from typing import Any, Dict, List

import requests


class ProMServiceClient:
    def __init__(self, base_url: str, endpoint: str = "/pipeline", timeout_seconds: int = 300):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _extract_metric(metrics_payload: Dict[str, Any], metric_name: str) -> float:
        if metric_name in metrics_payload:
            return float(metrics_payload[metric_name])

        aliases = {
            "generalisation": "generalization",
            "generalization": "generalisation",
        }
        alt = aliases.get(metric_name)
        if alt and alt in metrics_payload:
            return float(metrics_payload[alt])

        raise KeyError(f"Metric '{metric_name}' not found in service response")

    def evaluate_pipeline(self, log_path: str, pipeline: Dict[str, Any], metrics: List[str]) -> Dict[str, float]:
        payload = {
            "log_path": log_path,
            "pipeline": pipeline,
            "metrics": metrics,
        }

        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()

        metrics_payload = body.get("metrics", body)
        return {metric: self._extract_metric(metrics_payload, metric) for metric in metrics}

