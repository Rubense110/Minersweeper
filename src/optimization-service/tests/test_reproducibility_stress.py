"""Fast adversarial checks for private RNGs and asynchronous evaluation order."""
import json
import logging
import os
import random
import sys
import time
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np
from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from optimizer import PipelineNSGAIIIOptimizer


class AdversarialProblem(FloatProblem):
    def __init__(self, objectives, mode, delay):
        super().__init__()
        self.lower_bound = [0., -1., .5, 0.]
        self.upper_bound = [1., 1., .5, 1.]
        self.rng = random.Random()
        self.objective_count, self.mode, self.delay = objectives, mode, delay
        self.attempts = {}

    def name(self): return 'adversarial reproducibility fixture'
    def number_of_objectives(self): return self.objective_count
    def number_of_constraints(self): return 0 if self.mode == 'no_constraints' else 2

    def create_solution(self):
        solution = FloatSolution(self.lower_bound, self.upper_bound,
                                 self.objective_count, self.number_of_constraints())
        solution.variables = [lo + self.rng.random() * (hi-lo)
                              for lo, hi in zip(self.lower_bound, self.upper_bound)]
        if self.mode == 'duplicates': solution.variables = [.5, 0., .5, .5]
        return solution

    def evaluate(self, solution):
        if self.delay:
            time.sleep(((solution.attributes['logical_attempt_id'] * 7) % 5) * .0001)
        x, y = solution.variables[:2]
        values = [x, 1-x, (y+1)/2, (1-y)/2, x*x, (1-x)**2, abs(y)]
        if self.mode in ('ties', 'duplicates'): values = [.5] * len(values)
        solution.objectives = values[:self.objective_count]
        if self.mode == 'infeasible': solution.constraints = [-1., -2.]
        elif self.mode == 'mixed': solution.constraints = [0., 0.] if x < .5 else [-1., -x]
        elif self.mode == 'no_constraints': solution.constraints = []
        else: solution.constraints = [0., 0.]
        solution.attributes['is_feasible'] = not any(v < 0 for v in solution.constraints)
        # Each attempt is inspected, including offspring absent from snapshots.
        self.attempts[solution.attributes['logical_attempt_id']] = (
            list(solution.variables), list(solution.objectives), list(solution.constraints))
        return solution


def run_case(seed, dimensions, population, partitions, mode, workers,
             probabilities=(.9, .25)):
    problem = AdversarialProblem(dimensions, mode, workers > 1)
    optimizer = PipelineNSGAIIIOptimizer(problem, seed=seed, n_workers=workers,
        population_size=population, n_partitions=partitions,
        max_evaluations=population*4, crossover_probability=probabilities[0],
        mutation_probability=probabilities[1])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        optimizer.run()
    def state(solution):
        return [solution.attributes['logical_attempt_id'], list(solution.variables),
                list(solution.objectives), list(solution.constraints)]
    result = {'attempts': sorted(problem.attempts.items()),
        'snapshots': [[state(s) for s in snap['solutions']]
                      for snap in optimizer.get_population_snapshots()],
        'pareto': [state(s) for s in optimizer.get_non_dominated()]}
    # NaNs must never silently make a JSON digest look reproducible.
    json.dumps(result, allow_nan=False)
    return result


class ReproducibilityStressTest(unittest.TestCase):
    def test_configuration_constraint_and_boundary_seed_matrix(self):
        configs = [(1,4,1),(2,4,3),(3,10,2),(4,4,1),(4,12,2),
                   (4,24,3),(7,12,1)]
        seeds = [0, 1, 42, 2**32-1, 2**32, 2**53-1]
        modes = ['tradeoff','ties','duplicates','mixed','infeasible','no_constraints']
        with patch.dict(os.environ, {'OPT_MAX_EVALUATION_WORKERS':'8'}):
            for dimensions, population, partitions in configs:
                for seed in seeds:
                    for mode in modes:
                        with self.subTest(dimensions=dimensions,population=population,
                                          partitions=partitions,seed=seed,mode=mode):
                            expected = run_case(seed,dimensions,population,partitions,mode,1)
                            for workers in (2,8):
                                random.seed(seed+workers); np.random.seed(workers)
                                self.assertEqual(expected,run_case(seed,dimensions,population,
                                                                 partitions,mode,workers))

    def test_operator_probability_boundaries_and_concurrent_jobs(self):
        with patch.dict(os.environ, {'OPT_MAX_EVALUATION_WORKERS':'8'}):
            for probabilities in ((0.,0.),(0.,1.),(1.,0.),(1.,1.)):
                for mode in ('ties','mixed','duplicates','tradeoff'):
                    with self.subTest(probabilities=probabilities,mode=mode):
                        expected = {s: run_case(s,4,12,2,mode,1,probabilities) for s in (0,42)}
                        with ThreadPoolExecutor(max_workers=4) as pool:
                            jobs = [(seed,pool.submit(run_case,seed,4,12,2,mode,workers,probabilities))
                                    for seed,workers in ((0,1),(42,8),(0,8),(42,2))]
                            for seed,job in jobs: self.assertEqual(expected[seed],job.result())

    def test_no_ambient_rng_is_called_even_with_ties(self):
        with patch('random.random',side_effect=AssertionError('ambient RNG')), \
             patch.object(np.random,'shuffle',side_effect=AssertionError('ambient RNG')), \
             patch.object(np.random,'permutation',side_effect=AssertionError('ambient RNG')):
            self.assertEqual(run_case(0,4,12,2,'ties',1),run_case(0,4,12,2,'ties',8))

    def test_odd_population_is_identical_to_next_even_request(self):
        # Equal budgets must yield the same complete trajectory, not just N survivors.
        for workers in (1,8):
            problem = AdversarialProblem(4, 'tradeoff', workers > 1)
            optimizer = PipelineNSGAIIIOptimizer(problem, seed=42, n_workers=workers,
                population_size=5, n_partitions=2, max_evaluations=24)
            optimizer.run()
            expected = run_case(42,4,6,2,'tradeoff',workers, (.9,.25))
            self.assertEqual(5, optimizer.effective_config['requested_population_size'])
            self.assertEqual(6, optimizer.effective_config['population_size'])
            self.assertEqual(expected['attempts'], sorted(problem.attempts.items()))
            self.assertEqual([6,12,18,24], [s['evaluations_done'] for s in optimizer.get_population_snapshots()])
            self.assertTrue(all(len(s['solutions']) == 6 for s in optimizer.get_population_snapshots()))


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    unittest.main()
