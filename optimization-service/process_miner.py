

from typing import List


class OptimizedProcessMiner:
    '''
    Class to perform optimized process miner. Given an event log 
    and metrics it will handle:

    1. Log Preprocessing
    2. Discovery algorithm
    3. Algorithm Variant and Parametrization

    '''

    def __init__(self, execution_name:str, log:str, metrics:List[str]):
        self.execution_name = execution_name
        self.log = log
        self.metrics_list = metrics