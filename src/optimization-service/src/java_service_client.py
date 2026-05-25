"""HTTP client for the Java ProM service."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

import requests

from constraints import summarize_constraints
from execution_control import JobCancelled


LOGGER = logging.getLogger("optimization_service.jobs")


class ProMServiceClient:
    def __init__(
        self,
        base_url: str,
        endpoint: str = "/pipeline",
        timeout_seconds: int = 300,
        experiment_id: Optional[str] = None,
        conformance_mode: Optional[str] = None,
        excluded_miners: Optional[Sequence[str]] = None,
        constraints: Optional[Sequence[Dict[str, Any]]] = None,
        artifacts_bulk_endpoint: str = "/artifacts/bulk",
        cleanup_endpoint_template: str = "/experiments/{experiment_id}/cleanup",
        cancel_endpoint_template: str = "/experiments/{experiment_id}/cancel",
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.experiment_id = experiment_id
        self.conformance_mode = (conformance_mode or "").strip() or None
        self.excluded_miners = tuple(excluded_miners or ())
        self.constraints_summary = summarize_constraints(constraints or [])
        self.artifacts_bulk_endpoint = artifacts_bulk_endpoint
        self.cleanup_endpoint_template = cleanup_endpoint_template
        self.cancel_endpoint_template = cancel_endpoint_template

    @staticmethod
    def _to_service_metric(metric_name: str) -> str:
        if metric_name is None:
            return ""
        return str(metric_name).strip()

    @staticmethod
    def _extract_metric(metrics_payload: Dict[str, Any], metric_name: str) -> float:
        key = ProMServiceClient._to_service_metric(metric_name)
        if key in metrics_payload:
            return float(metrics_payload[key])
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
        service_metrics = [self._to_service_metric(metric) for metric in metrics]
        payload = {
            "experiment_id": resolved_experiment_id,
            "log_path": log_path,
            "pipeline": pipeline,
            "metrics": service_metrics,
        }
        if self.conformance_mode:
            payload["conformance_mode"] = self.conformance_mode
        if self.excluded_miners:
            payload["excluded_miners"] = list(self.excluded_miners)

        pipeline_text = json.dumps(pipeline or {}, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        LOGGER.info(
            "evaluation dispatch experiment_id=%s log_path=%s metrics=%s constraints=%s pipeline=%s",
            resolved_experiment_id,
            log_path,
            ",".join(service_metrics),
            self.constraints_summary or "-",
            pipeline_text,
        )

        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        self._raise_for_status_with_details(response)
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
        self._raise_for_status_with_details(response)
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
        self._raise_for_status_with_details(response)
        return response.json()

    def cancel_experiment(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_experiment_id = self._resolve_experiment_id(experiment_id)
        endpoint = self.cancel_endpoint_template.format(experiment_id=resolved_experiment_id)
        response = requests.post(
            f"{self.base_url}{endpoint}",
            timeout=self.timeout_seconds,
        )
        self._raise_for_status_with_details(response)
        return response.json()

    @staticmethod
    def _raise_for_status_with_details(response: requests.Response) -> None:
        try:
            response.raise_for_status()
            return
        except requests.HTTPError as error:
            details = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    code = payload.get("error")
                    message = payload.get("message")
                    if response.status_code == 409 and code == "experiment_cancelled":
                        raise JobCancelled(message or "job cancelled")
                    if code or message:
                        details = f"{code}: {message}".strip()
                elif payload is not None:
                    details = str(payload)
            except JobCancelled:
                raise
            except Exception:
                text = (response.text or "").strip()
                if text:
                    details = text
            if details:
                raise requests.HTTPError(f"{error} - {details}", response=response) from error
            raise
