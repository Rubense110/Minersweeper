from pm_app.pm_py import metrics
from pm_app.pm_py import parameters
from dask.distributed import Client
from dask.distributed import LocalCluster

from pm4py.algo.discovery.heuristics import algorithm as heuristics_miner
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.termination_criterion import StoppingByEvaluations

"""
This file defines mappings and configurations for various components of the process mining framework.
"""

miner_mapping = {
    'inductive': inductive_miner, 
    'heuristic': heuristics_miner,
}

parameter_mapping = {
    'inductive': parameters.InductiveParametersConfig(),
    'heuristic': parameters.HeuristicParametersConfig(),
    'alpha': parameters.AlphaParametersConfig()
}

max_evaluations = 1000

nsgaii_params = {'population_size': 100,
                 'offspring_population_size': 100,
                 'mutation': PolynomialMutation(probability=0.17, distribution_index=20),
                 'crossover': SBXCrossover(probability=1.0, distribution_index=20),
                 'termination_criterion': StoppingByEvaluations(max_evaluations=max_evaluations)}



def get_distributed_nsgaii_params():

    # setup Dask client
    client = Client(LocalCluster(n_workers=10))
    ncores = sum(client.ncores().values())

    d_nsgaii_params = { 'population_size': 100,
                        'mutation': PolynomialMutation(probability=0.17, distribution_index=20),
                        'crossover': SBXCrossover(probability=1.0, distribution_index=20),
                        'termination_criterion': StoppingByEvaluations(max_evaluations=max_evaluations),
                        'number_of_cores' : ncores,
                        'client' : client}

    return d_nsgaii_params
