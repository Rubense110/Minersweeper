import os
import sys
import unittest
from unittest.mock import Mock, patch


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from java_service_client import ProMServiceClient


class ProMServiceClientTest(unittest.TestCase):
    @patch("java_service_client.requests.post")
    def test_evaluate_pipeline_reads_metrics_field(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "metrics": {
                "fitness": 0.9,
                "precision": 0.8,
                "simplicity": 0.7,
                "generalization": 0.6,
            }
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service")
        result = client.evaluate_pipeline(
            log_path="dummy.xes",
            pipeline={"miner": {}, "preprocessing": {}},
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )

        self.assertEqual(result["fitness"], 0.9)
        self.assertEqual(result["generalisation"], 0.6)
        mock_post.assert_called_once()

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

        client = ProMServiceClient(base_url="http://service")
        result = client.evaluate_pipeline(
            log_path="dummy.xes",
            pipeline={"miner": {}, "preprocessing": {}},
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        self.assertEqual(result["generalisation"], 0.4)

    @patch("java_service_client.requests.post")
    def test_missing_metric_raises(self, mock_post):
        response = Mock()
        response.json.return_value = {"metrics": {"fitness": 0.9}}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = ProMServiceClient(base_url="http://service")
        with self.assertRaises(KeyError):
            client.evaluate_pipeline(
                log_path="dummy.xes",
                pipeline={"miner": {}, "preprocessing": {}},
                metrics=["fitness", "precision"],
            )


if __name__ == "__main__":
    unittest.main()

