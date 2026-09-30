import os
import sys
import unittest
import math
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem
from execution_control import JobCancelled
from api.serialization import _serialize_solution


class PipelineOptimizationProblemTest(unittest.TestCase):
    @staticmethod
    def _v2_payload(evaluation_id, visible_transition_count):
        is_feasible = visible_transition_count > 0
        return {
            "experiment_id": "exp-1",
            "evaluation_id": evaluation_id,
            "fingerprint": f"fp-{evaluation_id}",
            "model_schema_version": 2,
            "visible_transition_count": visible_transition_count,
            "is_feasible": is_feasible,
            "constraint_violations": [] if is_feasible else ["NO_VISIBLE_TRANSITIONS"],
            "metrics": {"fitness": 0.8},
        }

    def test_objectives_are_negated_for_maximization(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "experiment_id": "exp-1",
                "evaluation_id": "ev-1",
                "fingerprint": "fp-1",
                "runtime_ms": 123,
                "metrics": {
                    "fitness": 0.9,
                    "precision": 0.8,
                    "simplicity": 0.7,
                    "generalisation": 0.6,
                },
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
            maximize_metrics=[True, True, True, True],
        )

        solution = problem.create_solution()
        evaluated = problem.evaluate(solution)
        self.assertEqual(evaluated.objectives, [-0.9, -0.8, -0.7, -0.6])
        self.assertIn("pipeline", evaluated.attributes)
        self.assertIn("metrics", evaluated.attributes)
        self.assertEqual(evaluated.attributes["evaluation_id"], "ev-1")
        self.assertEqual(evaluated.attributes["experiment_id"], "exp-1")
        self.assertEqual(evaluated.attributes["fingerprint"], "fp-1")
        self.assertEqual(evaluated.attributes["runtime_ms"], 123)

    def test_infeasible_feasibility_is_a_constraint_without_replacing_metrics(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "metrics": {"fitness": 0.9, "precision": 0.8, "simplicity": 0.7, "generalisation": 0.6},
                "visible_transition_count": 0,
                "is_feasible": False,
                "constraint_violations": ["NO_VISIBLE_TRANSITIONS"],
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"], search_space=space, evaluator=evaluator,
        )
        evaluated = problem.evaluate(problem.create_solution())

        self.assertEqual(1, problem.number_of_constraints())
        self.assertEqual([-0.9, -0.8, -0.7, -0.6], evaluated.objectives)
        self.assertEqual([-1.0], evaluated.constraints)
        self.assertFalse(evaluated.attributes["is_feasible"])
        self.assertEqual(["NO_VISIBLE_TRANSITIONS"], evaluated.attributes["constraint_violations"])
        self.assertEqual(0, evaluated.attributes["visible_transition_count"])

    def test_v3_structurally_broken_model_is_infeasible_despite_good_metrics(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "model_schema_version": 3,
                "metrics": {"fitness": 0.99},
                "visible_transition_count": 2,
                "is_feasible": False,
                "constraint_violations": ["FINAL_NOT_REACHABLE", "DEAD_VISIBLE_TRANSITION"],
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        evaluated = problem.evaluate(problem.create_solution())
        self.assertEqual([-0.99], evaluated.objectives)
        self.assertEqual([-1.0], evaluated.constraints)
        self.assertFalse(evaluated.attributes["is_feasible"])
        self.assertEqual(3, evaluated.attributes["model_schema_version"])

    def test_visible_tau_is_feasible_when_semantic_flag_says_visible(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "metrics": {"fitness": 0.1},
                "visible_transition_count": 1,
                "is_feasible": True,
                "constraint_violations": [],
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"], search_space=space, evaluator=evaluator,
        )
        evaluated = problem.evaluate(problem.create_solution())
        self.assertEqual([0.0], evaluated.constraints)
        self.assertTrue(evaluated.attributes["is_feasible"])

    def test_cache_prevents_duplicate_evaluations(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        call_count = {"n": 0}

        def evaluator(_log, _pipeline, _metrics):
            call_count["n"] += 1
            return {
                "fitness": 0.1,
                "precision": 0.2,
                "simplicity": 0.3,
                "generalisation": 0.4,
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )
        solution = problem.create_solution()

        problem.evaluate(solution)
        problem.evaluate(solution)
        self.assertEqual(call_count["n"], 1)

    def test_cache_uses_decoded_pipeline_not_inactive_genes_or_selector_float(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = []
        events = []

        def evaluator(_log, pipeline, _metrics):
            calls.append(pipeline)
            return {"fitness": 0.8}

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator, on_evaluation=events.append,
        )
        first = problem.create_solution()
        first.variables = list(first.lower_bound)
        second = problem.create_solution()
        second_variables = list(first.variables)
        # Both selector floats decode to the first miner. The Heuristics gene
        # is inactive while Alpha is selected, so it cannot change the request.
        second_variables[space.index_by_key["miner::selected"]] = 0.2
        inactive_index = space.index_by_key["miner::heuristics::param::dependency_threshold"]
        second_variables[inactive_index] = second.upper_bound[inactive_index]
        second.variables = second_variables

        problem.evaluate(first)
        problem.evaluate(second)

        self.assertEqual(len(calls), 1)
        self.assertEqual([False, True], [event["cache_hit"] for event in events])
        self.assertEqual(first.attributes["pipeline"], second.attributes["pipeline"])

    def test_cache_keeps_distinct_active_float_parameters_separate(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = []

        def evaluator(_log, pipeline, _metrics):
            calls.append(pipeline)
            return {"fitness": 0.8}

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        first = problem.create_solution()
        first_variables = list(first.lower_bound)
        first_variables[space.index_by_key["miner::selected"]] = float(space.miner_keys.index("heuristics"))
        active_index = space.index_by_key["miner::heuristics::param::dependency_threshold"]
        first_variables[active_index] = 0.25
        first.variables = first_variables
        second = problem.create_solution()
        second_variables = list(first.variables)
        # These values collided under the old eight-decimal raw-vector key.
        second_variables[active_index] = 0.250000001
        second.variables = second_variables

        problem.evaluate(first)
        problem.evaluate(second)

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(problem.evaluation_cache), 2)

    def test_cache_key_is_built_after_pipeline_repair(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = {"n": 0}

        def evaluator(_log, _pipeline, _metrics):
            calls["n"] += 1
            return {"fitness": 0.8}

        def repair(_log, pipeline):
            repaired = copy.deepcopy(pipeline)
            repaired["preprocessing"]["parameters"]["keep_threshold_p"] = 50
            return repaired

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        first = problem.create_solution()
        first_variables = list(first.lower_bound)
        first_variables[space.index_by_key["preprocessing::selected"]] = float(
            space.preprocessing_keys.index("projection_filter")
        )
        first.variables = first_variables
        second = problem.create_solution()
        second_variables = list(first.variables)
        threshold_index = space.index_by_key["preprocessing::projection_filter::param::keep_threshold_p"]
        second_variables[threshold_index] = second.upper_bound[threshold_index]
        second.variables = second_variables

        with patch("problem.repair_pipeline_preprocessing", side_effect=repair):
            problem.evaluate(first)
            problem.evaluate(second)

        self.assertEqual(calls["n"], 1)
        self.assertEqual(first.attributes["pipeline"], second.attributes["pipeline"])

    def test_cache_does_not_reuse_transient_evaluation_error(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = {"n": 0}

        def evaluator(_log, _pipeline, _metrics):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("temporary outage")
            return {"fitness": 0.8}

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        solution = problem.create_solution()
        problem.evaluate(solution)
        self.assertIn("evaluation_error", solution.attributes)
        self.assertEqual(len(problem.evaluation_cache), 0)

        problem.evaluate(solution)
        self.assertNotIn("evaluation_error", solution.attributes)
        problem.evaluate(solution)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(problem.evaluation_cache), 1)

    def test_concurrent_equal_pipelines_share_one_inflight_evaluation(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        started = threading.Event()
        release = threading.Event()
        calls = {"n": 0}

        def evaluator(_log, _pipeline, _metrics):
            calls["n"] += 1
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test evaluation was not released")
            return {"fitness": 0.8}

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        first = problem.create_solution()
        second = problem.create_solution()
        second.variables = list(first.variables)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_result = executor.submit(problem.evaluate, first)
                self.assertTrue(started.wait(timeout=5))
                second_result = executor.submit(problem.evaluate, second)
                release.set()
                self.assertEqual(first_result.result(timeout=5).objectives, [-0.8])
                self.assertEqual(second_result.result(timeout=5).objectives, [-0.8])
        finally:
            release.set()
        self.assertEqual(calls["n"], 1)

    def test_maximize_metrics_length_mismatch_raises(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {"fitness": 0.1}

        with self.assertRaises(ValueError):
            PipelineOptimizationProblem(
                log_path="dummy.xes",
                metrics_list=["fitness"],
                required_metrics=["fitness"],
                    search_space=space,
                evaluator=evaluator,
                maximize_metrics=[True, False],
            )

    def test_cache_restores_attributes(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "experiment_id": "exp-1",
                "evaluation_id": "ev-2",
                "fingerprint": "fp-2",
                "runtime_ms": 77,
                "visible_transition_count": 0,
                "is_feasible": False,
                "constraint_violations": ["NO_VISIBLE_TRANSITIONS"],
                "metrics": {
                    "fitness": 0.4,
                    "precision": 0.3,
                    "simplicity": 0.2,
                    "generalisation": 0.1,
                },
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )
        solution = problem.create_solution()
        problem.evaluate(solution)

        cached_solution = problem.create_solution()
        cached_solution.variables = list(solution.variables)
        evaluated_cached = problem.evaluate(cached_solution)
        self.assertEqual(evaluated_cached.attributes["evaluation_id"], "ev-2")
        self.assertEqual(evaluated_cached.attributes["fingerprint"], "fp-2")
        self.assertEqual(evaluated_cached.attributes["runtime_ms"], 77)
        self.assertEqual([-1.0], evaluated_cached.constraints)
        self.assertFalse(evaluated_cached.attributes["is_feasible"])
        self.assertEqual(["NO_VISIBLE_TRANSITIONS"], evaluated_cached.attributes["constraint_violations"])

    def test_evaluator_error_is_penalized_without_crash(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            raise RuntimeError("service unavailable")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )

        solution = problem.create_solution()
        evaluated = problem.evaluate(solution)
        self.assertEqual(evaluated.objectives, [0.0, 0.0, 0.0, 0.0])
        self.assertIn("evaluation_error", evaluated.attributes)
        self.assertIn("runtime_ms", evaluated.attributes)
        self.assertGreaterEqual(evaluated.attributes["runtime_ms"], 0)
        self.assertEqual([-1.0], evaluated.constraints)
        self.assertNotIn("NO_VISIBLE_TRANSITIONS", evaluated.attributes.get("constraint_violations", []))

    def test_infeasible_parent_metadata_is_cleared_when_child_evaluation_fails(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = {"count": 0}

        def evaluator(_log, _pipeline, _metrics):
            calls["count"] += 1
            if calls["count"] == 1:
                return self._v2_payload("infeasible-parent", 0)
            raise RuntimeError("child failed")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator, use_cache=False,
        )
        parent = problem.evaluate(problem.create_solution())
        child = copy.deepcopy(parent)
        child.variables[0] = child.upper_bound[0] if child.variables[0] != child.upper_bound[0] else child.lower_bound[0]

        evaluated = problem.evaluate(child)

        self.assertEqual([-1.0], evaluated.constraints)
        self.assertEqual("child failed", evaluated.attributes["evaluation_error"])
        for key in (
            "evaluation_id", "experiment_id", "fingerprint", "model_schema_version",
            "is_feasible", "constraint_violations", "visible_transition_count",
        ):
            self.assertNotIn(key, evaluated.attributes)

    def test_feasible_pareto_parent_id_is_not_inherited_by_failed_child(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        calls = {"count": 0}

        def evaluator(_log, _pipeline, _metrics):
            calls["count"] += 1
            if calls["count"] == 1:
                return self._v2_payload("pareto-parent", 1)
            raise RuntimeError("child failed")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator, use_cache=False,
        )
        parent = problem.evaluate(problem.create_solution())
        parent.attributes["is_pareto"] = True
        child = copy.deepcopy(parent)
        child.variables[0] = child.upper_bound[0] if child.variables[0] != child.upper_bound[0] else child.lower_bound[0]

        evaluated = problem.evaluate(child)
        serialized = _serialize_solution(evaluated, {"pareto-parent"})

        self.assertNotIn("evaluation_id", evaluated.attributes)
        self.assertNotIn("is_feasible", evaluated.attributes)
        self.assertNotIn("is_pareto", evaluated.attributes)
        self.assertIsNone(serialized["evaluation_id"])
        self.assertFalse(serialized["is_pareto"])

    def test_cache_hit_replaces_all_evaluation_metadata_in_deepcopied_child(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        responses = [
            self._v2_payload("cached-target", 1),
            self._v2_payload("infeasible-parent", 0),
        ]

        def evaluator(_log, _pipeline, _metrics):
            return responses.pop(0)

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator,
        )
        cached_target = problem.create_solution()
        cached_target.variables = [bound for bound in cached_target.lower_bound]
        problem.evaluate(cached_target)
        parent = problem.create_solution()
        parent.variables = [bound for bound in parent.upper_bound]
        problem.evaluate(parent)
        child = copy.deepcopy(parent)
        child.variables = list(cached_target.variables)

        evaluated = problem.evaluate(child)

        self.assertEqual("cached-target", evaluated.attributes["evaluation_id"])
        self.assertEqual("fp-cached-target", evaluated.attributes["fingerprint"])
        self.assertTrue(evaluated.attributes["is_feasible"])
        self.assertEqual([], evaluated.attributes["constraint_violations"])
        self.assertEqual(1, evaluated.attributes["visible_transition_count"])
        self.assertEqual([0.0], evaluated.constraints)
        self.assertNotIn("evaluation_error", evaluated.attributes)

    def test_successful_reevaluation_replaces_previous_evaluation_state(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        responses = [
            self._v2_payload("first-evaluation", 0),
            self._v2_payload("second-evaluation", 1),
        ]

        def evaluator(_log, _pipeline, _metrics):
            return responses.pop(0)

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=space, evaluator=evaluator, use_cache=False,
        )
        solution = problem.evaluate(problem.create_solution())
        solution.attributes["evaluation_error"] = "stale error"
        solution.variables[0] = solution.upper_bound[0] if solution.variables[0] != solution.upper_bound[0] else solution.lower_bound[0]

        reevaluated = problem.evaluate(solution)

        self.assertEqual("second-evaluation", reevaluated.attributes["evaluation_id"])
        self.assertEqual("fp-second-evaluation", reevaluated.attributes["fingerprint"])
        self.assertTrue(reevaluated.attributes["is_feasible"])
        self.assertEqual([0.0], reevaluated.constraints)
        self.assertNotIn("evaluation_error", reevaluated.attributes)

    def test_non_finite_metric_values_are_sanitized(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "metrics": {
                    "fitness": 0.5,
                    "precision": float("nan"),
                    "simplicity": 0.8,
                    "generalisation": 1.0,
                }
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
            maximize_metrics=[True, True, True, True],
        )

        solution = problem.create_solution()
        evaluated = problem.evaluate(solution)
        self.assertTrue(all(math.isfinite(value) for value in evaluated.objectives))
        self.assertEqual(evaluated.objectives[0], -0.5)
        self.assertEqual(evaluated.objectives[1], -0.0)
        self.assertIn("evaluation_error", evaluated.attributes)
        self.assertEqual([-1.0], evaluated.constraints)

    def test_invalid_metrics_penalize_even_a_feasible_versioned_model(self):
        space = PipelineSearchSpace(excluded_miners=("ilp", "hybrid_ilp"))
        for schema in (2, 3):
            for invalid in (None, "invalid", float("nan"), float("inf"), float("-inf")):
                with self.subTest(schema=schema, metric=invalid):
                    payload = self._v2_payload("invalid-metric", 1)
                    payload["model_schema_version"] = schema
                    payload["metrics"]["fitness"] = invalid
                    problem = PipelineOptimizationProblem(
                        log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
                        search_space=space, evaluator=lambda *_: payload,
                    )
                    evaluated = problem.evaluate(problem.create_solution())
                    self.assertEqual([-1.0], evaluated.constraints)
                    self.assertTrue(evaluated.attributes["is_feasible"])
                    self.assertEqual([], evaluated.attributes["constraint_violations"])
                    self.assertIn("evaluation_error", evaluated.attributes)
                    self.assertFalse(_serialize_solution(evaluated, {"invalid-metric"})["is_pareto"])
                    self.assertEqual({}, problem.evaluation_cache)

    def test_exception_without_message_is_still_recorded_as_error(self):
        def evaluator(*_):
            raise RuntimeError()

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes", metrics_list=["fitness"], required_metrics=["fitness"],
            search_space=PipelineSearchSpace(), evaluator=evaluator,
        )
        evaluated = problem.evaluate(problem.create_solution())
        self.assertEqual([-1.0], evaluated.constraints)
        self.assertEqual("RuntimeError", evaluated.attributes["evaluation_error"])
        self.assertEqual({}, problem.evaluation_cache)

    def test_job_cancelled_is_propagated(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            raise JobCancelled("job cancelled")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )

        with self.assertRaises(JobCancelled):
            problem.evaluate(problem.create_solution())



if __name__ == "__main__":
    unittest.main()
