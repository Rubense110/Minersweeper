from unittest.mock import patch

import pandas as pd
from django.test import TestCase

from pm_app.models import DSolution, Execution, FrontSnapshot, Optimizer as OptimizerModel, Petri
from pm_app.pm_py.optimize import Optimizer
from pm_app.utils import discovery


class DummySolution:
    def __init__(self, variables, objectives, constraints=None):
        self.variables = variables
        self.objectives = objectives
        self.constraints = constraints or []


class DummyPetriNet:
    def __init__(self):
        self.places = {"p1", "p2"}
        self.transitions = {"t1"}
        self.arcs = {("p1", "t1"), ("t1", "p2")}


class PMPyUnitTests(TestCase):
    def test_calculate_pareto_front(self):
        opt = Optimizer.__new__(Optimizer)
        solutions = [
            DummySolution([0], [1.0, 2.0]),
            DummySolution([0], [2.0, 3.0]),
            DummySolution([0], [1.0, 2.0]),
        ]
        df = opt._calculate_pareto_front(solutions, ["m1", "m2"])
        self.assertEqual(list(df.columns), ["m1", "m2"])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0].tolist(), [1.0, 2.0])

class DiscoveryIntegrationTests(TestCase):
    def test_discovery_creates_db_records(self):
        solutions = [
            DummySolution([0.1, 0.2], [1.0, 2.0], [0.0]),
            DummySolution([0.3, 0.4], [2.0, 3.0], [0.0]),
        ]
        pareto_df = pd.DataFrame([[1.0, 2.0]], columns=["fitness", "precision"])
        fronts = [{"evaluations": 10, "front": [[1.0, 2.0]]}]
        petri_nets = [(DummyPetriNet(), None, None), (DummyPetriNet(), None, None)]

        class DummyOpt:
            def get_front_history(self):
                return fronts

            def get_result(self):
                return solutions

            def get_non_dominated_sols(self):
                return pareto_df

            def get_result_petri_nets(self):
                return petri_nets

        class DummyProcessMiner:
            def __init__(self, *args, **kwargs):
                self.constraints_list = []
                self.opt = DummyOpt()

            def discover(self, *args, **kwargs):
                return None

            def parallel_discover(self, *args, **kwargs):
                return None

        def dummy_clean_transition_data(transitions, arcs, miner_name):
            return list(transitions), list(arcs)

        with patch("pm_app.utils.discovery.ProcessMiner", DummyProcessMiner), patch(
            "pm_app.utils.discovery.clean_transition_data", dummy_clean_transition_data
        ):
            execution_id = discovery.discover(
                execution_name="test-run",
                optimization_method="NSGAII",
                opt_parameters_dict={"max_evals": 2, "population_size": 2},
                miner_name="heuristic",
                evaluation_metrics=["fitness", "precision"],
                logpath="dummy.xes",
                form_data={},
                constrs_string=None,
            )

        self.assertEqual(Execution.objects.count(), 1)
        self.assertEqual(OptimizerModel.objects.count(), 1)
        self.assertEqual(Petri.objects.count(), 2)
        self.assertEqual(DSolution.objects.count(), 2)
        self.assertEqual(FrontSnapshot.objects.count(), 1)

        execution = Execution.objects.get(pk=execution_id)
        self.assertEqual(execution.constraints, "")
        self.assertEqual(Petri.objects.filter(is_pareto=True).count(), 1)
        self.assertEqual(DSolution.objects.filter(is_pareto=True).count(), 1)
