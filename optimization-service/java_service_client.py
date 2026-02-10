"""HTTP client for the Java ProM service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class ProMServiceClient:
    def __init__(
        self,
        base_url: str,
        endpoint: str = "/pipeline",
        timeout_seconds: int = 300,
        experiment_id: Optional[str] = None,
        artifacts_bulk_endpoint: str = "/artifacts/bulk",
        cleanup_endpoint_template: str = "/experiments/{experiment_id}/cleanup",
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.experiment_id = experiment_id
        self.artifacts_bulk_endpoint = artifacts_bulk_endpoint
        self.cleanup_endpoint_template = cleanup_endpoint_template

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

    def _resolve_experiment_id(self, experiment_id: Optional[str]) -> str:
        resolved = experiment_id or self.experiment_id
        if not resolved:
            raise ValueError("experiment_id is required for Java service calls")
        return resolved

    def evaluate_pipeline(
        self,
        log_path: str,
        pipeline: Dict[str, Any],
        metrics: List[str],
        experiment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_experiment_id = self._resolve_experiment_id(experiment_id)
        payload = {
            "experiment_id": resolved_experiment_id,
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
        extracted_metrics = {metric: self._extract_metric(metrics_payload, metric) for metric in metrics}
        return {
            "metrics": extracted_metrics,
            "experiment_id": body.get("experiment_id", resolved_experiment_id),
            "evaluation_id": body.get("evaluation_id"),
            "fingerprint": body.get("fingerprint"),
        }

    def fetch_artifacts(
        self,
        evaluation_ids: List[str],
        include_pnml: bool = True,
        experiment_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        resolved_experiment_id = self._resolve_experiment_id(experiment_id)
        payload = {
            "experiment_id": resolved_experiment_id,
            "evaluation_ids": evaluation_ids,
            "include_pnml": include_pnml,
        }
        response = requests.post(
            f"{self.base_url}{self.artifacts_bulk_endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        artifacts = body.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise ValueError("Invalid artifacts response format")
        return artifacts

    def cleanup_experiment(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_experiment_id = self._resolve_experiment_id(experiment_id)
        endpoint = self.cleanup_endpoint_template.format(experiment_id=resolved_experiment_id)
        response = requests.post(
            f"{self.base_url}{endpoint}",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
