import copy
import os
import sys
import random
import time
import warnings
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import numpy as np
import requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from optimizer import PipelineNSGAIIIOptimizer
from seeded_nsgaiii import seeded_niching
from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution
from execution_control import ExecutionControl, ReproducibilityError
from java_service_client import ProMServiceClient
from problem import PipelineOptimizationProblem
from pipeline_space import PipelineSearchSpace

class TradeoffProblem(FloatProblem):
    def __init__(self, delay=False):
        super().__init__()
        self.lower_bound = [0.] * 4
        self.upper_bound = [1.] * 4
        self.rng = random.Random()  # The optimizer must bind initialization itself.
        self.delay = delay
    def name(self): return 'deterministic conflicting objectives'
    def number_of_objectives(self): return 4
    def number_of_constraints(self): return 1
    def create_solution(self):
        s = FloatSolution(self.lower_bound, self.upper_bound, 4, 1)
        s.variables = [self.rng.random() for _ in range(4)]
        return s
    def evaluate(self, s):
        if self.delay: time.sleep((int(s.variables[0]*17) % 4)*.0005)
        x, y = s.variables[:2]
        s.objectives = [x, 1-x, y, 1-y]
        s.constraints = [0.]
        s.attributes['is_feasible'] = True
        return s

def trajectory(seed=42, workers=1):
    optimizer = PipelineNSGAIIIOptimizer(TradeoffProblem(True), max_evaluations=120,
        population_size=12, n_partitions=2, seed=seed, n_workers=workers)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        optimizer.run()
    return [[(s.variables, s.objectives, s.constraints, s.attributes['logical_attempt_id'])
             for s in snap['solutions']] for snap in optimizer.get_population_snapshots()]

class ReproducibilityTest(unittest.TestCase):
    def test_real_niching_is_repeated_and_does_not_use_global_rng(self):
        with patch('seeded_nsgaiii.seeded_niching', wraps=seeded_niching) as niching, \
             patch.object(np.random, 'shuffle', side_effect=AssertionError('global RNG')), \
             patch.object(np.random, 'permutation', side_effect=AssertionError('global RNG')), \
             patch('random.random', side_effect=AssertionError('global Python RNG')):
            first = trajectory()
            self.assertEqual(first, trajectory(workers=4))
            self.assertEqual(10, len(first))
            self.assertEqual(18, niching.call_count)

    def test_external_global_state_does_not_change_trajectory(self):
        expected = trajectory()
        for ambient in [0, 1, 777]:
            random.seed(ambient); np.random.seed(ambient); np.random.random(97)
            self.assertEqual(expected, trajectory())

    def test_jobs_do_not_interfere_and_different_seeds_are_effective(self):
        expected = {seed: trajectory(seed) for seed in [42, 987]}
        self.assertNotEqual(expected[42], expected[987])
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [(seed, executor.submit(trajectory, seed, workers))
                       for seed, workers in [(42,1),(987,4),(42,4),(987,1)]]
            for seed, future in futures:
                self.assertEqual(expected[seed], future.result())

    def test_seed_full_api_range(self):
        self.assertEqual(trajectory(2**53-1), trajectory(2**53-1))

    def test_niching_matches_upstream_with_same_random_stream(self):
        from jmetal.algorithm.multiobjective.nsgaiii import niching
        pop = [FloatSolution([0.], [1.], 4, 1) for _ in range(6)]
        kwargs = dict(pop=pop, n_remaining=4, niche_count=np.array([0,1]),
                      niche_of_individuals=np.array([0,0,0,1,1,1]),
                      dist_to_niche=np.array([.2,.2,.5,.1,.3,.1]))
        reference_rng = np.random.Generator(np.random.PCG64(123))
        with patch.object(np.random, 'shuffle', side_effect=reference_rng.shuffle), \
             patch.object(np.random, 'permutation', side_effect=reference_rng.permutation):
            expected = niching(**copy.deepcopy(kwargs))
        actual = seeded_niching(**copy.deepcopy(kwargs), rng=np.random.Generator(np.random.PCG64(123)))
        self.assertEqual(expected, actual)

    def test_remote_reproducibility_cutoff_is_fatal_and_controls_other_workers(self):
        response = Mock(status_code=503)
        response.raise_for_status.side_effect = requests.HTTPError('503')
        response.json.return_value = {'error':'REPRODUCIBILITY_TIME_LIMIT','message':'cutoff'}
        with self.assertRaises(ReproducibilityError):
            ProMServiceClient._raise_for_status_with_details(response)
        control = ExecutionControl()
        problem = PipelineOptimizationProblem('dummy', ['fitness'], ['fitness'], PipelineSearchSpace(),
            Mock(side_effect=ReproducibilityError('cutoff')), execution_control=control)
        with self.assertRaises(ReproducibilityError): problem.evaluate(problem.create_solution())
        self.assertFalse(problem.evaluation_cache)
        with self.assertRaises(ReproducibilityError): control.raise_if_cancel_requested()

    def test_reusing_orchestrator_resets_initialization_stream(self):
        from process_miner import OptimizedProcessMiner
        miner = OptimizedProcessMiner('run','dummy',service_url='http://service',seed=7)
        states=[]
        def build_problem(**kwargs):
            states.append(kwargs['rng'].random())
            return Mock()
        with patch('process_miner.ProMServiceClient'), patch('process_miner.PipelineOptimizationProblem',side_effect=build_problem), \
             patch('process_miner.PipelineNSGAIIIOptimizer'):
            miner.discover();miner.discover()
        self.assertEqual(states[0],states[1])

    def test_generated_seed_is_shared_by_initialization_and_optimizer(self):
        from process_miner import OptimizedProcessMiner
        with patch('process_miner.secrets.randbits', return_value=123):
            miner = OptimizedProcessMiner('run','dummy',service_url='http://service')
        with patch('process_miner.ProMServiceClient'), patch('process_miner.PipelineOptimizationProblem'), \
             patch('process_miner.PipelineNSGAIIIOptimizer') as optimizer:
            miner.discover()
        kwargs = optimizer.call_args.kwargs
        self.assertEqual(123, kwargs['seed'])
        self.assertEqual(random.Random(123).getstate(), kwargs['rng'].getstate())

    def test_custom_rng_state_is_identified_instead_of_claiming_seed_only_reproduction(self):
        custom = random.Random(42)
        custom.random()
        optimizer = PipelineNSGAIIIOptimizer(TradeoffProblem(), population_size=12,
            max_evaluations=12, seed=42, rng=custom)
        self.assertFalse(optimizer.effective_config['python_rng_from_seed'])
        self.assertEqual(64, len(optimizer.effective_config['python_rng_initial_state_sha256']))

if __name__ == '__main__': unittest.main()
