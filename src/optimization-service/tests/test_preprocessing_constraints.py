import os
import sys
import tempfile
import unittest


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from pipeline_space import PipelineSearchSpace
from preprocessing_constraints import adjusted_bounds, repair_pipeline_preprocessing


def _write_xes(path: str) -> None:
    xes = """<?xml version="1.0" encoding="UTF-8"?>
<log xes.version="1.0" xes.features="nested-attributes" xmlns="http://www.xes-standard.org/">
  <extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>
  <classifier name="Event Name" keys="concept:name"/>
  <trace>
    <string key="concept:name" value="Case1"/>
    <event><string key="concept:name" value="A"/></event>
    <event><string key="concept:name" value="B"/></event>
  </trace>
  <trace>
    <string key="concept:name" value="Case2"/>
    <event><string key="concept:name" value="A"/></event>
    <event><string key="concept:name" value="B"/></event>
  </trace>
  <trace>
    <string key="concept:name" value="Case3"/>
    <event><string key="concept:name" value="A"/></event>
    <event><string key="concept:name" value="B"/></event>
  </trace>
  <trace>
    <string key="concept:name" value="Case4"/>
    <event><string key="concept:name" value="A"/></event>
    <event><string key="concept:name" value="C"/></event>
  </trace>
</log>
"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(xes)


class PreprocessingConstraintsTest(unittest.TestCase):
    def test_projection_bounds_never_include_zero(self):
        self.assertEqual(adjusted_bounds("projection_filter", "keep_threshold_p", (0, 100), None), (1.0, 100))

    def test_variant_pipeline_is_repaired_to_log_dependent_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "log.xes")
            _write_xes(log_path)
            repaired = repair_pipeline_preprocessing(
                log_path,
                {
                    "preprocessing": {
                        "key": "variant_filter",
                        "parameters": {"keep_threshold_vf": 10},
                    }
                },
            )
            self.assertEqual(repaired["preprocessing"]["parameters"]["keep_threshold_vf"], 75)

    def test_search_space_uses_log_aware_variant_lower_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "log.xes")
            _write_xes(log_path)
            space = PipelineSearchSpace(log_path=log_path, excluded_miners=("split",))
            key = "preprocessing::variant_filter::param::keep_threshold_vf"
            self.assertEqual(space.variables[space.index_by_key[key]].min_val, 75.0)


if __name__ == "__main__":
    unittest.main()
