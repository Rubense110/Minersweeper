import copy
import csv
import io
import zipfile
import json
import math
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_model_exploration as fixtures
from constraints import normalize_constraints, evaluate_constraints
from model_selection import select_weighted_model, ModelSelectionUnavailable
from pareto import CONSTRAINT_DOMINANCE_COMPARATOR, feasible_non_dominated
from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem
from api.serialization import _serialize_solution, _build_experiment_export_archive
from model_exploration.importing import import_export
from job_store import JobStore
from api.manager import OptimizationJobManager


def rule(metric='precision', operator='>=', value=.8):
    return {'metric': metric, 'operator': operator, 'value': value}


def problem(constraints=None, feasible=True, missing=False):
    def evaluate(_log, _pipeline, metrics):
        values = {'fitness': .95, 'precision': .5, 'places': 8.}
        return {'model_schema_version': 3, 'visible_transition_count': 2, 'is_feasible': feasible,
                'constraint_violations': [] if feasible else ['FINAL_NOT_REACHABLE'],
                'metrics_status': 'computed' if feasible else 'skipped_infeasible',
                'metrics': {key: values[key] for key in metrics if key in values and not (missing and key == 'precision')}}
    return PipelineOptimizationProblem(log_path='dummy.xes', metrics_list=['fitness'], required_metrics=['fitness'],
                                       search_space=PipelineSearchSpace(excluded_miners=('split',)), evaluator=evaluate,
                                       constraints=constraints)


class UserConstraintIntegrationTest(unittest.TestCase):
    def test_observation_metrics_do_not_add_objectives_or_constraints(self):
        from process_miner import OptimizedProcessMiner
        miner = OptimizedProcessMiner('observed', 'dummy.xes', metrics=['fitness'],
                                      observation_metrics=['elc', 'cfc', 'elc'])
        self.assertEqual(['fitness'], miner.metrics_list)
        self.assertEqual([], miner.constraints)
        self.assertEqual(['fitness', 'elc', 'cfc'], miner.required_metrics)
        with tempfile.TemporaryDirectory() as directory:
            manager = OptimizationJobManager('http://unused', 'sqlite:///' + directory + '/api.db', 10)
            try:
                with patch('api.manager.threading.Thread'):
                    submitted = manager.submit({'log_path': 'dummy.xes', 'metrics': ['fitness'],
                                                'observation_metrics': ['elc', 'cfc'], 'constraints': []})
                request = manager.get(submitted['job_id'])['request']
                self.assertEqual(['fitness'], request['metrics'])
                self.assertEqual([], request['constraints'])
                self.assertEqual(['fitness', 'elc', 'cfc'], request['required_metrics'])
                for invalid in ('elc', ['unknown'], None):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                        manager.submit({'log_path': 'dummy.xes', 'observation_metrics': invalid})
            finally:
                manager.job_store.engine.dispose()

    def test_seed_with_constraints_is_independent_of_worker_scheduling(self):
        from optimizer import PipelineNSGAIIIOptimizer
        def run(workers, rules):
            def evaluate(_log, pipeline, _metrics):
                value = int(hashlib.sha256(json.dumps(pipeline, sort_keys=True).encode()).hexdigest()[:8], 16) / (2**32 - 1)
                return {'metrics': {'fitness': value, 'precision': 1 - value, 'places': int(value * 20) + 2},
                        'model_schema_version': 3, 'is_feasible': True, 'visible_transition_count': 2, 'constraint_violations': []}
            p = PipelineOptimizationProblem('dummy.xes', ['fitness', 'precision'], ['fitness', 'precision'],
                                            PipelineSearchSpace(excluded_miners=('split',)), evaluate,
                                            constraints=rules)
            optimizer = PipelineNSGAIIIOptimizer(p, population_size=8, max_evaluations=24, n_partitions=2, n_workers=workers, seed=444)
            optimizer.run()
            return [(s.variables, s.objectives, s.constraints) for s in optimizer.get_result()]
        for rules in ([rule('places', '<=', 10)], [{'any': [rule('places', '<=', 10), {'all': [rule('fitness', '>', .7), rule('precision', '<', .3)]}]}]):
            with self.subTest(rules=rules):
                self.assertEqual(run(1, rules), run(4, rules))

    def test_compound_rules_request_all_metrics_cache_and_preserve_native_validity(self):
        rules = [{'any': [rule(), {'all': [rule('places', '<=', 10), rule('fitness', '>=', .9)]}]}]
        p = problem(rules)
        self.assertEqual(['fitness', 'precision', 'places'], p.required_metrics)
        first = p.evaluate(p.create_solution())
        second = p.evaluate(copy.deepcopy(first))
        self.assertEqual(2, p.number_of_constraints())
        self.assertEqual(first.constraints, second.constraints)
        self.assertTrue(first.attributes['is_feasible'])
        self.assertTrue(_serialize_solution(first, set())['optimization_feasible'])
        self.assertEqual([first], feasible_non_dominated([first]))
        missing = problem(rules, missing=True).evaluate(p.create_solution())
        self.assertEqual(-1, missing.constraints[0])
        self.assertIn('precision', missing.attributes['evaluation_error'])

    def test_compound_api_and_export_import_roundtrip(self):
        rules = [{'any': [rule(), {'all': [rule('places', '<=', 10), rule('fitness', '>=', .9)]}]}]
        with tempfile.TemporaryDirectory() as directory:
            manager = OptimizationJobManager('http://unused', 'sqlite:///' + directory + '/api.db', 10)
            store = manager.job_store
            try:
                with patch('api.manager.threading.Thread'):
                    response = manager.submit({'log_path': 'dummy.xes', 'metrics': ['fitness'], 'constraints': rules})
                request = manager.get(response['job_id'])['request']
                self.assertEqual(rules, request['constraints'])
                self.assertEqual(['fitness', 'precision', 'places'], request['required_metrics'])
                row = fixtures.source(1)
                row['constraints'] = [0., .2]
                data = {**fixtures.data(), 'constraints': rules}
                store.save_completed_experiment(data, [row], [{**row, 'snapshot_index': 1, 'member_index': 1, 'evaluations_done': 2}])
                saved = store.get_experiment_solutions('original-exp')
                archive, _ = _build_experiment_export_archive(store.get_experiment('original-exp'), saved,
                    store.get_experiment_snapshot_solutions('original-exp'), store.get_original_artifacts('original-exp'))
                imported_id = import_export(store, archive)
                self.assertEqual(rules, store.get_experiment(imported_id)['constraints'])
                self.assertEqual([0., .2], store.get_experiment_solutions(imported_id)[0]['constraints'])
                self.assertEqual([0., .2], store.get_experiment_snapshot_solutions('original-exp')[0]['constraints'])
                with zipfile.ZipFile(io.BytesIO(archive)) as exported:
                    snapshot = next(csv.DictReader(io.StringIO(exported.read('snapshot_solutions.csv').decode())))
                    self.assertEqual([0., .2], json.loads(snapshot['constraints']))
                # Exploration import intentionally imports only the final population.
                self.assertEqual(row['original_pnml'], store.get_original_artifacts(imported_id)['e-1']['pnml'])
            finally:
                store.engine.dispose()

    def test_constraint_only_metric_is_requested_and_native_feasibility_remains_unchanged(self):
        p = problem([rule()])
        self.assertEqual(['fitness', 'precision'], p.required_metrics)
        first = p.evaluate(p.create_solution())
        second = p.evaluate(copy.deepcopy(first))
        self.assertEqual(2, p.number_of_constraints())
        self.assertTrue(first.attributes['is_feasible'])
        self.assertEqual([], first.attributes['constraint_violations'])
        self.assertEqual([0., -.3], [round(v, 5) for v in first.constraints])
        self.assertEqual(first.constraints, second.constraints)
        self.assertEqual(first.objectives, second.objectives)
        self.assertFalse(_serialize_solution(first, set())['optimization_feasible'])
        self.assertEqual([], feasible_non_dominated([first, second]))

    def test_semantic_failure_never_beats_large_user_violation(self):
        p = problem([rule('places', '<=', -1000)])
        valid = p.evaluate(p.create_solution())
        invalid_problem = problem([rule('places', '<=', -1000)], feasible=False)
        invalid = invalid_problem.evaluate(invalid_problem.create_solution())
        self.assertEqual(-1, CONSTRAINT_DOMINANCE_COMPARATOR.compare(valid, invalid))
        self.assertEqual(1, CONSTRAINT_DOMINANCE_COMPARATOR.compare(invalid, valid))
        self.assertTrue(all(math.isfinite(v) for v in invalid.constraints))

    def test_missing_constraint_metric_is_a_technical_failure_not_an_eligible_model(self):
        p = problem([rule()], missing=True)
        candidate = p.evaluate(p.create_solution())
        self.assertEqual(-1., candidate.constraints[0])
        self.assertIn('precision', candidate.attributes['evaluation_error'])
        self.assertFalse(_serialize_solution(candidate, set())['optimization_feasible'])

    def test_strict_operators_accept_adjacent_values_and_reject_equality(self):
        self.assertGreater(evaluate_constraints({'fitness': math.nextafter(.5, math.inf)}, [rule('fitness', '>', .5)])[0], 0)
        self.assertGreater(evaluate_constraints({'fitness': math.nextafter(.5, -math.inf)}, [rule('fitness', '<', .5)])[0], 0)
        for op in ('<', '>'):
            self.assertLess(evaluate_constraints({'fitness': .5}, [rule('fitness', op, .5)])[0], 0)
        for value in (True, math.nan, math.inf, None, ''):
            with self.assertRaises(ValueError): normalize_constraints([rule(value=value)])
        for rules in ({}, [rule(metric='unknown')], [rule(operator='!=')]):
            with self.assertRaises(ValueError): normalize_constraints(rules)

    def test_asf_rejects_violating_candidates_in_all_scope_and_empty_pareto(self):
        experiment = {'metrics': ['fitness'], 'constraints': [rule()]}
        candidates = [{'solution_id': 1, 'is_feasible': True, 'objectives': [-.99], 'metrics': {'precision': .5}, 'constraints': [0., -.3]},
                      {'solution_id': 2, 'is_feasible': True, 'objectives': [-.8], 'metrics': {'precision': .9}, 'constraints': [0., .1]}]
        result = select_weighted_model(experiment, candidates, None, 'all')
        self.assertEqual(2, result['selected_solution_id'])
        self.assertEqual(1, result['candidate_count'])
        with self.assertRaises(ModelSelectionUnavailable):
            select_weighted_model(experiment, candidates[:1], None, 'all')

    def test_api_normalizes_rules_and_requests_additional_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = OptimizationJobManager('http://unused', 'sqlite:///' + directory + '/api.db', 10)
            try:
                with patch('api.manager.threading.Thread'):
                    response = manager.submit({'log_path': 'dummy.xes', 'metrics': ['fitness'], 'constraints': [rule(), rule()]})
                request = manager.get(response['job_id'])['request']
                self.assertEqual([rule()], request['constraints'])
                self.assertEqual(['fitness', 'precision'], request['required_metrics'])
                with self.assertRaises(ValueError): manager.submit({'log_path': 'dummy.xes', 'constraints': [rule(operator='bad')]})
            finally:
                manager.job_store.engine.dispose()

    def test_persistence_export_import_and_snapshots_keep_rules_and_native_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore('sqlite:///' + directory + '/constraints.db')
            try:
                row = fixtures.source(1)
                row['constraints'] = [0., -.3]
                data = {**fixtures.data(), 'constraints': [rule()]}
                store.save_completed_experiment(data, [row], [{**row, 'snapshot_index': 1, 'member_index': 1, 'evaluations_done': 2}])
                original = store.get_original_artifacts('original-exp')
                saved = store.get_experiment_solutions('original-exp')
                self.assertEqual([rule()], store.get_experiment('original-exp')['constraints'])
                self.assertTrue(saved[0]['is_feasible'])
                self.assertFalse(saved[0]['optimization_feasible'])
                self.assertFalse(saved[0]['is_pareto'])
                snapshot = store.get_experiment_snapshot_solutions('original-exp')[0]
                self.assertEqual([0., -.3], snapshot['constraints'])
                self.assertTrue(snapshot['is_feasible'])
                self.assertFalse(snapshot['optimization_feasible'])
                self.assertEqual([], store.get_experiment_solutions('original-exp', 'pareto'))
                archive, _ = _build_experiment_export_archive(store.get_experiment('original-exp'), saved, [], original)
                imported_id = import_export(store, archive)
                imported = store.get_experiment_solutions(imported_id)[0]
                self.assertEqual([rule()], store.get_experiment(imported_id)['constraints'])
                self.assertEqual([0., -.3], imported['constraints'])
                self.assertFalse(imported['optimization_feasible'])
                self.assertTrue(imported['is_feasible'])
                self.assertEqual(row['original_pnml'], store.get_original_artifacts(imported_id)['e-1']['pnml'])
            finally:
                store.engine.dispose()
