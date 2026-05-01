import os
import sys
import unittest
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from java_service_client import ProMServiceClient
from execution_control import JobCancelled


class ProMServiceClientTest(unittest.TestCase):
    @patch("java_service_client.requests.post")
    def test_evaluate_pipeline_reads_metrics_field(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "experiment_id": "exp-1",
            "evaluation_id": "eval-1",
            "fingerprint": "fp-1",
            "metrics": {
                "fitness": 0.9,
                "precision": 0.8,
                "simplicity": 0.7,
                "generalisation": 0.6,
            }
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(
            base_url="http://service",
            experiment_id="exp-1",
            excluded_miners=("split", "ilp"),
        )
        result = client.evaluate_pipeline(
            log_path="dummy.xes",
            pipeline={"miner": {}, "preprocessing": {}},
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )

        self.assertEqual(result["metrics"]["fitness"], 0.9)
        self.assertEqual(result["metrics"]["generalisation"], 0.6)
        self.assertEqual(result["evaluation_id"], "eval-1")
        self.assertEqual(result["fingerprint"], "fp-1")
        mock_post.assert_called_once()
        sent_metrics = mock_post.call_args.kwargs["json"]["metrics"]
        self.assertEqual(
            sent_metrics,
            ["fitness", "precision", "simplicity", "generalisation"],
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["excluded_miners"], ["split", "ilp"])

    @patch("java_service_client.requests.post")
    def test_evaluate_pipeline_works_with_flat_body(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "fitness": 0.1,
            "precision": 0.2,
            "simplicity": 0.3,
            "generalisation": 0.4,
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        result = client.evaluate_pipeline(
            log_path="dummy.xes",
            pipeline={"miner": {}, "preprocessing": {}},
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        self.assertEqual(result["metrics"]["generalisation"], 0.4)
        sent_metrics = mock_post.call_args.kwargs["json"]["metrics"]
        self.assertEqual(
            sent_metrics,
            ["fitness", "precision", "simplicity", "generalisation"],
        )

    @patch("java_service_client.requests.post")
    def test_missing_metric_raises(self, mock_post):
        response = Mock()
        response.json.return_value = {"metrics": {"fitness": 0.9}}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        with self.assertRaises(KeyError):
            client.evaluate_pipeline(
                log_path="dummy.xes",
                pipeline={"miner": {}, "preprocessing": {}},
                metrics=["fitness", "precision"],
            )

    @patch("java_service_client.requests.post")
    def test_new_structural_metrics_are_passthrough(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "metrics": {
                "places": 12.0,
                "transitions": 9.0,
                "arcs": 24.0,
                "cycl_complx": 5.0,
                "ratio": 1.3333333333,
                "joins": 2.0,
                "splits": 3.0,
            }
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        requested = ["places", "transitions", "arcs", "cycl_complx", "ratio", "joins", "splits"]
        result = client.evaluate_pipeline(
            log_path="dummy.xes",
            pipeline={"miner": {}, "preprocessing": {}},
            metrics=requested,
        )
        self.assertEqual(result["metrics"]["places"], 12.0)
        self.assertEqual(result["metrics"]["cycl_complx"], 5.0)
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["metrics"],
            requested,
        )

    @patch("java_service_client.requests.post")
    def test_http_error_includes_service_payload_details(self, mock_post):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
        response.json.return_value = {
            "error": "invalid_request",
            "message": "unsupported metric: foo",
        }
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        with self.assertRaises(requests.HTTPError) as ctx:
            client.evaluate_pipeline(
                log_path="dummy.xes",
                pipeline={"miner": {}, "preprocessing": {}},
                metrics=["fitness", "foo"],
            )
        self.assertIn("invalid_request: unsupported metric: foo", str(ctx.exception))

    @patch("java_service_client.requests.post")
    def test_fetch_artifacts_returns_list(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "experiment_id": "exp-1",
            "artifacts": [
                {"evaluation_id": "e-1", "pnml": "<pnml/>"},
                {"evaluation_id": "e-2", "pnml": "<pnml/>"},
            ],
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        artifacts = client.fetch_artifacts(["e-1", "e-2"], include_pnml=True)
        self.assertEqual(len(artifacts), 2)
        self.assertEqual(artifacts[0]["evaluation_id"], "e-1")

    @patch("java_service_client.requests.post")
    def test_cleanup_experiment_returns_json(self, mock_post):
        response = Mock()
        response.json.return_value = {"experiment_id": "exp-1", "deleted": True}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        result = client.cleanup_experiment()
        self.assertEqual(result["experiment_id"], "exp-1")

    @patch("java_service_client.requests.post")
    def test_cancel_experiment_returns_json(self, mock_post):
        response = Mock()
        response.json.return_value = {"experiment_id": "exp-1", "cancel_requested": True}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        result = client.cancel_experiment()
        self.assertEqual(result["experiment_id"], "exp-1")

    @patch("java_service_client.requests.post")
    def test_cancelled_experiment_raises_job_cancelled(self, mock_post):
        response = Mock()
        response.status_code = 409
        response.raise_for_status.side_effect = requests.HTTPError("409 Client Error")
        response.json.return_value = {
            "error": "experiment_cancelled",
            "message": "experiment 'exp-1' cancelled",
        }
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service", experiment_id="exp-1")
        with self.assertRaises(JobCancelled):
            client.evaluate_pipeline(
                log_path="dummy.xes",
                pipeline={"miner": {}, "preprocessing": {}},
                metrics=["fitness"],
            )

    def test_missing_experiment_id_raises(self):
        client = ProMServiceClient(base_url="http://service")
        with self.assertRaises(ValueError):
            client.evaluate_pipeline(
                log_path="dummy.xes",
                pipeline={"miner": {}, "preprocessing": {}},
                metrics=["fitness"],
            )


if __name__ == "__main__":
    unittest.main()
