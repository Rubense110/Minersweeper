import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline_space import PipelineSearchSpace
from parameters.miners import MINER_CATALOG


class PipelineSearchSpaceTest(unittest.TestCase):
    def test_split_catalog_exposes_single_sm_variant(self):
        split_spec = MINER_CATALOG["split"]
        variant_keys = [variant.key for variant in split_spec.variants]
        self.assertEqual(variant_keys, ["sm"])
        self.assertEqual(set(split_spec.parameters.keys()), {"epsilon", "eta"})

    def test_build_space_has_basic_selectors(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        self.assertIn("preprocessing::selected", space.index_by_key)
        self.assertIn("miner::selected", space.index_by_key)
        self.assertNotIn("split", space.miner_keys)
        self.assertGreater(len(space.variables), 0)

    def test_decode_returns_pipeline_shape(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        values = [(var.min_val + var.max_val) / 2 for var in space.variables]
        decoded = space.decode(values)

        self.assertIn("preprocessing", decoded)
        self.assertIn("miner", decoded)
        self.assertIn("parameters", decoded["preprocessing"])
        self.assertIn("parameters", decoded["miner"])
        self.assertIn(decoded["preprocessing"]["key"], space.preprocessing_keys)
        self.assertIn(decoded["miner"]["key"], space.miner_keys)

    def test_hybrid_ilp_lp_filter_gating_none(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        values = [var.min_val for var in space.variables]

        values[space.index_by_key["miner::selected"]] = space.miner_keys.index("hybrid_ilp")
        values[space.index_by_key["miner::hybrid_ilp::variant"]] = 0.0
        values[space.index_by_key["miner::hybrid_ilp::param::lp_filter"]] = 0.0  # None
        decoded = space.decode(values)
        params = decoded["miner"]["parameters"]

        self.assertEqual(decoded["miner"]["key"], "hybrid_ilp")
        self.assertEqual(params["lp_filter"], "None")
        self.assertNotIn("slack_variable_filter_threshold", params)
        self.assertNotIn("sequence_encoding_cutoff_level", params)

    def test_hybrid_ilp_lp_filter_gating_slack(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        values = [var.min_val for var in space.variables]

        values[space.index_by_key["miner::selected"]] = space.miner_keys.index("hybrid_ilp")
        values[space.index_by_key["miner::hybrid_ilp::variant"]] = 0.0
        values[space.index_by_key["miner::hybrid_ilp::param::lp_filter"]] = 2.0  # Slack Variable Filter
        decoded = space.decode(values)
        params = decoded["miner"]["parameters"]

        self.assertEqual(params["lp_filter"], "Slack Variable Filter")
        self.assertIn("slack_variable_filter_threshold", params)
        self.assertNotIn("sequence_encoding_cutoff_level", params)

    def test_hybrid_ilp_lp_filter_gating_sequence(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        values = [var.min_val for var in space.variables]

        values[space.index_by_key["miner::selected"]] = space.miner_keys.index("hybrid_ilp")
        values[space.index_by_key["miner::hybrid_ilp::variant"]] = 0.0
        values[space.index_by_key["miner::hybrid_ilp::param::lp_filter"]] = 1.0  # Sequence Encoding Filter
        decoded = space.decode(values)
        params = decoded["miner"]["parameters"]

        self.assertEqual(params["lp_filter"], "Sequence Encoding Filter")
        self.assertNotIn("slack_variable_filter_threshold", params)
        self.assertIn("sequence_encoding_cutoff_level", params)


if __name__ == "__main__":
    unittest.main()
