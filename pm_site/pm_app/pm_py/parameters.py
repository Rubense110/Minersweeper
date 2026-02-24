

from pm4py.algo.discovery.heuristics.variants.classic import Parameters as HeuristicsParameters
import pm4py
from abc import abstractmethod
from pm4py.objects.log.importer.xes import importer as xes_importer
import os
import contextlib

class BaseParametersConfig():
    base_params = {}
    param_range = {}
    param_type = {}

    @abstractmethod
    def get_param_names(self):
        pass

class HeuristicParametersConfig(BaseParametersConfig):

    def __init__(self, log = None):
        super().__init__()
        # Heuristic miner default params to begin discovery
        self.base_params = {
            HeuristicsParameters.DEPENDENCY_THRESH.value: 0.5,
            HeuristicsParameters.AND_MEASURE_THRESH.value: 0.65,
            HeuristicsParameters.MIN_ACT_COUNT.value: 1,
            HeuristicsParameters.MIN_DFG_OCCURRENCES.value: 2,
            HeuristicsParameters.DFG_PRE_CLEANING_NOISE_THRESH.value: 0.05,
            HeuristicsParameters.LOOP_LENGTH_TWO_THRESH.value: 0.5,
        }

        # range of posible values for the parameters of the heurisic miner
        self.param_range = {
            HeuristicsParameters.DEPENDENCY_THRESH : [0, 1],
            HeuristicsParameters.AND_MEASURE_THRESH : [0, 1],
            HeuristicsParameters.MIN_ACT_COUNT: [1, 1000],
            HeuristicsParameters.MIN_DFG_OCCURRENCES: [1, 1000],
            HeuristicsParameters.DFG_PRE_CLEANING_NOISE_THRESH: [0, 1],
            HeuristicsParameters.LOOP_LENGTH_TWO_THRESH: [0, 1]
        }

        # Data type for each parameter
        self.param_type = {
            HeuristicsParameters.DEPENDENCY_THRESH : float,
            HeuristicsParameters.AND_MEASURE_THRESH : float,
            HeuristicsParameters.MIN_ACT_COUNT: int,
            HeuristicsParameters.MIN_DFG_OCCURRENCES: int,
            HeuristicsParameters.DFG_PRE_CLEANING_NOISE_THRESH: float,
            HeuristicsParameters.LOOP_LENGTH_TWO_THRESH: float
        }
        if log is not None:
            self.adjust_heu_params(log)

    def adjust_heu_params(self, log):
        with open(os.devnull, 'w') as fnull:
            with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
                log = xes_importer.apply(log)  
        log = pm4py.convert_to_dataframe(log)

        max_activity_count = log['concept:name'].value_counts().max()
        self.param_range[HeuristicsParameters.MIN_ACT_COUNT] = [0, max_activity_count]
        
    def get_param_names(self):
        param_names = list(self.base_params.keys())
        return param_names

class InductiveParametersConfig(BaseParametersConfig):
    def __init__(self) -> None:
        super().__init__()
    
        self.base_params = {'noise_threshold' : 0,
                            'multi_processing': False,
                            'disable_fallthroughs': False}
        
        self.param_range = {'noise_threshold' : [0, 1],
                            'multi_processing': [0, 1],
                            'disable_fallthroughs': [0, 1]}
        
        self.param_type  = {'noise_threshold' : float,
                            'multi_processing': float,
                            'disable_fallthroughs': float}
        
    def get_param_names(self):
        param_names = list(self.base_params.keys())
        return param_names


class AlphaParametersConfig(BaseParametersConfig):
    def __init__(self) -> None:
        super().__init__()
        self.base_params = {}
        self.param_range = {}
        self.param_type = {}

    def get_param_names(self):
        return []
    
