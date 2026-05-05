import os
import sys
import unittest
from unittest.mock import ANY, Mock, patch


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from process_miner import OptimizedProcessMiner


class OptimizedProcessMinerTest(unittest.TestCase):
    def test_default_excluded_miners_only_ilp(self):
        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        self.assertEqual(miner.excluded_miners, ("ilp",))

    def test_discover_requires_service_url(self):
        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        with self.assertRaises(ValueError):
            miner.discover()

    @patch("process_miner.PipelineNSGAIIIOptimizer")
    @patch("process_miner.PipelineOptimizationProblem")
    @patch("process_miner.ProMServiceClient")
    @patch("process_miner.PipelineSearchSpace")
    def test_discover_wires_components(
        self,
        mock_space_cls,
        mock_client_cls,
        mock_problem_cls,
        mock_optimizer_cls,
    ):
        mock_space = Mock()
        mock_space_cls.return_value = mock_space

        mock_client = Mock()
        mock_client.evaluate_pipeline = Mock()
        mock_client_cls.return_value = mock_client

        mock_problem = Mock()
        mock_problem_cls.return_value = mock_problem

        mock_optimizer = Mock()
        mock_optimizer.get_result.return_value = ["sol"]
        mock_optimizer.get_non_dominated.return_value = []
        mock_optimizer.get_population_snapshots.return_value = [{"snapshot_index": 1, "evaluations_done": 20, "solutions": []}]
        mock_optimizer_cls.return_value = mock_optimizer

        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
            service_url="http://service",
            excluded_miners=("split", "ilp"),
        )
        result = miner.discover(max_evaluations=50, population_size=20, n_partitions=3, n_workers=4)

        self.assertEqual(result, ["sol"])
        self.assertEqual([{"snapshot_index": 1, "evaluations_done": 20, "solutions": []}], miner.population_snapshots)
        mock_space_cls.assert_called_once_with(excluded_miners=("split", "ilp"), log_path="dummy.xes")
        mock_client_cls.assert_called_once_with(
            base_url="http://service",
            experiment_id="exec",
            timeout_seconds=300,
            conformance_mode=None,
            excluded_miners=("split", "ilp"),
        )

        _, kwargs = mock_problem_cls.call_args
        self.assertEqual(kwargs["log_path"], "dummy.xes")
        self.assertEqual(kwargs["metrics_list"], ["fitness", "precision", "simplicity", "generalisation"])
        self.assertEqual(kwargs["maximize_metrics"], [True, True, True, True])
        self.assertIs(kwargs["search_space"], mock_space)
        self.assertIs(kwargs["evaluator"], mock_client.evaluate_pipeline)

        mock_optimizer_cls.assert_called_once_with(
            problem=mock_problem,
            max_evaluations=50,
            population_size=20,
            n_partitions=3,
            n_workers=4,
            execution_control=ANY,
        )
        mock_optimizer.run.assert_called_once()

    def test_non_dominated_accessors(self):
        class Sol:
            def __init__(self, pipeline, metrics, evaluation_id=None):
                self.attributes = {"pipeline": pipeline, "metrics": metrics}
                if evaluation_id:
                    self.attributes["evaluation_id"] = evaluation_id

        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        miner.non_dominated = [
            Sol({"miner": {"key": "inductive"}}, {"fitness": 0.8}, evaluation_id="ev-1"),
            Sol({"miner": {"key": "heuristics"}}, {"fitness": 0.7}, evaluation_id="ev-2"),
        ]

        pipelines = miner.get_non_dominated_pipelines()
        metrics = miner.get_non_dominated_metrics()
        self.assertEqual(len(pipelines), 2)
        self.assertEqual(len(metrics), 2)
        self.assertEqual(pipelines[0]["miner"]["key"], "inductive")
        self.assertEqual(metrics[0]["fitness"], 0.8)
        self.assertEqual(miner.get_non_dominated_evaluation_ids(), ["ev-1", "ev-2"])

    def test_fetch_non_dominated_artifacts(self):
        class Sol:
            def __init__(self, evaluation_id):
                self.attributes = {"evaluation_id": evaluation_id}

        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        miner.non_dominated = [Sol("ev-1"), Sol("ev-2")]
        miner.service_client = Mock()
        miner.service_client.fetch_artifacts.return_value = [{"evaluation_id": "ev-1"}]

        artifacts = miner.fetch_non_dominated_artifacts(include_pnml=True)
        self.assertEqual(len(artifacts), 1)
        miner.service_client.fetch_artifacts.assert_called_once_with(
            evaluation_ids=["ev-1", "ev-2"],
            include_pnml=True,
            experiment_id="exec",
        )

    def test_cleanup_experiment_artifacts(self):
        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        miner.service_client = Mock()
        miner.service_client.cleanup_experiment.return_value = {"deleted": True}

        result = miner.cleanup_experiment_artifacts()
        self.assertTrue(result["deleted"])
        miner.service_client.cleanup_experiment.assert_called_once_with(experiment_id="exec")

    def test_request_cancel_propagates_to_optimizer(self):
        miner = OptimizedProcessMiner(
            execution_name="exec",
            log="dummy.xes",
            metrics=["fitness", "precision", "simplicity", "generalisation"],
        )
        miner.optimizer = Mock()

        miner.request_cancel()

        self.assertTrue(miner.execution_control.is_cancel_requested())
        miner.optimizer.cancel.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
