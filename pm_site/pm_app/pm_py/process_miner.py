import time
import os
import sys

from jmetal.algorithm.multiobjective.nsgaii import DistributedNSGAII, NSGAII
from jmetal.algorithm.multiobjective.nsgaiii import NSGAIII
from jmetal.algorithm.multiobjective.spea2 import SPEA2

from pm_app.pm_py import optimize
from pm_app.pm_py.utils.constrains_parser import ConstraintParser
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class ProcessMiner:
    '''
    A class with the objective of mining useful process models from event logs using various optimization algorithms.

    The actual optimizacion process is abstracted to the class 'optimize.Optimizer()'.
    Here the user can specify log files, the out folder for the petri net representation of the processes among others.
    
    The result of the execution is an approximation ot the pareto front of the optimal solutions returned from the optimizer.

    Attributes
    ----------
    miner_name : str
        The type of mining algorithm to be used (e.g., "Heuristic").
    metrics_list : str
        The string defining the type of metrics used for evaluation. Must be one of te implementations from the 'metrics' module.
    '''

    out_folder = 'out/'
    available_opts = {'NSGAII' : NSGAII,
                      'NSGAIII' : NSGAIII,
                      'SPEA2': SPEA2,
                      'NSGAII-D': DistributedNSGAII}


    def __init__(self, execution_name, miner_name, metrics,  log:tuple[str, str], outpath=None, constraints_string=None):

        self.execution_name = execution_name
        self.miner_name = miner_name
        self.metrics_list = metrics
        self.log_path = log
        self.constraints_list = self._parse_constraints(constraints_string)

        if outpath == None:
            self.outpath = f'{self.out_folder}/{self.execution_name}'
        else:
            self.outpath = f'{self.out_folder}/{outpath}'
        self.opt = optimize.Optimizer(self.execution_name, self.miner_name, 
                                      self.log_path, self.metrics_list, 
                                      self.outpath, self.constraints_list)

    def _parse_constraints(self, constraints_string):
        if constraints_string:
            parser = ConstraintParser(constraints_string)
            parser.parse()
            constraints_list = parser.extract_constraints()
        else:
            constraints_list=[]
        
        return constraints_list
    
    def parallel_discover(self, algorithm_name, **params):
        if algorithm_name not in self.available_opts:
            return ValueError(f"Optmizador '{algorithm_name}' no está soportado. Los optmizadores disponibles son: {list(self.available_opts.keys())}")
        algorithm_class = self.available_opts[algorithm_name]

        self.opt_type = algorithm_name
        self.params = params
        self.opt.discover_parallel(algorithm_class=algorithm_class, **params)
        self.opt_type = algorithm_class.__name__
        self.end_time = time.time()
            
    def discover(self, algorithm_name, **params):
        '''
        Performs the hiperparameter optimization of the miner specified when instanciating
        the class using the algorithm class and its hiperparameters entered as attributes.

        It does not return anything, but other methods are available to retrieve information
        about the execution.

        Parameters
        ----------
        algorithm_name : class
            The name of the optimization algorithm to be used. Must be one of the avalilable names.
        **params : dict, optional
            Additional keyword arguments representing the hyperparameters to be passed to the algorithm class.
        
        '''
        if algorithm_name not in self.available_opts:
            return ValueError(f"Optmizador '{algorithm_name}' no está soportado. Los optmizadores disponibles son: {list(self.available_opts.keys())}")
        else:
            algorithm_class = self.available_opts[algorithm_name]
            
        self.opt_type = algorithm_name
        self.params = params
        self.opt.discover(algorithm_class=algorithm_class, **params)

        self.opt_type = algorithm_class.__name__
        self.end_time = time.time()
