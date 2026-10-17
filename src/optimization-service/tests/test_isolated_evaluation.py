import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from java_service_client import ProMServiceClient
from execution_control import EvaluationInfrastructureError, ExecutionControl, JobCancelled
from problem import PipelineOptimizationProblem
from pipeline_space import PipelineSearchSpace


class IsolatedEvaluationTest(unittest.TestCase):
    def test_negotiation_adapts_transport_and_limits_parallelism(self):
        client = ProMServiceClient('http://service', experiment_id='exp', timeout_seconds=10)
        response = Mock()
        response.json.return_value = {'mode': 'isolated-jvm-pool-v1', 'workers': 1, 'http_timeout_seconds': 605}
        with patch('java_service_client.requests.get', return_value=response):
            limits = client.configure_pool()
        self.assertEqual(605, client.timeout_seconds)
        self.assertEqual(1, limits['workers'])
        active = peak = 0
        lock = threading.Lock()
        def evaluate(*args):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with lock:
                active -= 1
            return {'metrics': {'fitness': .8}}
        with patch.object(client, '_evaluate_pipeline', side_effect=evaluate), ThreadPoolExecutor(4) as threads:
            list(threads.map(lambda _: client.evaluate_pipeline('log', {}, ['fitness']), range(8)))
        self.assertEqual(1, peak)

    def test_timeout_is_penalized_and_next_candidate_is_evaluated(self):
        control = ExecutionControl()
        client = ProMServiceClient('http://service', experiment_id='exp')
        timeout = Mock(status_code=504)
        timeout.json.return_value = {'error': 'evaluation_timeout', 'message': 'worker terminated and replaced'}
        timeout.raise_for_status.side_effect = requests.HTTPError('504 Gateway Timeout', response=timeout)
        good = Mock()
        good.json.return_value = {'metrics': {'fitness': .8}, 'is_feasible': True, 'model_schema_version': 3, 'visible_transition_count': 1, 'constraint_violations': []}
        problem = PipelineOptimizationProblem('log', ['fitness'], ['fitness'], PipelineSearchSpace(), client.evaluate_pipeline, execution_control=control)
        a, b = problem.create_solution(), problem.create_solution()
        with patch('java_service_client.requests.post', side_effect=[timeout, good]):
            problem.evaluate(a)
            control.raise_if_cancel_requested()
            problem.evaluate(b)
        self.assertIn('evaluation_timeout', a.attributes['evaluation_error'])
        self.assertLess(a.constraints[0], 0)
        self.assertNotIn('evaluation_error', b.attributes)
        self.assertEqual(.8, b.attributes['metrics']['fitness'])

    def test_infrastructure_failure_is_not_converted_to_model_penalty(self):
        control = ExecutionControl()
        response = Mock(status_code=503)
        response.json.return_value = {'error': 'evaluation_infrastructure_unavailable', 'message': 'replacement failed'}
        response.raise_for_status.side_effect = requests.HTTPError('503', response=response)
        client = ProMServiceClient('http://service', experiment_id='exp')
        problem = PipelineOptimizationProblem('log', ['fitness'], ['fitness'], PipelineSearchSpace(), client.evaluate_pipeline, execution_control=control)
        with patch('java_service_client.requests.post', return_value=response) as post:
            with self.assertRaises(EvaluationInfrastructureError):
                problem.evaluate(problem.create_solution())
            with self.assertRaises(EvaluationInfrastructureError):
                problem.evaluate(problem.create_solution())
            self.assertEqual(1, post.call_count)

    def test_cancellation_while_waiting_for_slot_never_dispatches(self):
        control = ExecutionControl()
        client = ProMServiceClient('http://service', experiment_id='exp')
        client._pipeline_slots = threading.BoundedSemaphore(1)
        client._pipeline_slots.acquire()
        client._execution_control = control
        control.request_cancel()
        with patch.object(client, '_evaluate_pipeline') as evaluate:
            with self.assertRaises(JobCancelled):
                client.evaluate_pipeline('log', {}, ['fitness'])
            evaluate.assert_not_called()
