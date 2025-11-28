from pm_app.pm_py import optimize
from pm_app.pm_py import config
from pm_app.pm_py import utils
from pm_app.pm_py.utils.constrains_parser import ConstraintParser

from jmetal.algorithm.multiobjective.nsgaii import NSGAII
from .jmetal_fixed import NSGAIII
from jmetal.algorithm.multiobjective.spea2 import SPEA2
from jmetal.algorithm.multiobjective.nsgaii import DistributedNSGAII
from pm4py.visualization.petri_net import visualizer as pn_visualizer
import time
import os
import json
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class ProcessMiner:
    '''
    A class with the objective of mining useful process models from event logs using various optimization algorithms.

    The actual optimizacion process is abstracted to the class 'optimize.Optimizer()'.
    Here the user can specify log files, the out folder for the petri net representation of the processes among others.
    
    The result of the execution is an approximation ot the pareto front of the optimal solutions returned from the optimizer.

    Attributes
    ----------
    log_file : str
        The path to the log file where results will be recorded.
    out_folder : str
        The output folder path where results and visualizations will be saved.
    miner_name : str
        The type of mining algorithm to be used (e.g., "Heuristic").
    metrics_list : str
        The string defining the type of metrics used for evaluation. Must be one of te implementations from the 'metrics' module.
    log_name : str
        The desired path to the log file, the file will be created if does not exist
    '''

    log_file = 'doc/log.csv'
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
        self.local_time = time.strftime("[%Y_%m_%d - %H:%M:%S]", time.localtime())
        self.constraints_list = self._parse_constraints(constraints_string)

        if outpath == None:
            self.outpath = f'{self.out_folder}/{self.execution_name}'
        else:
            self.outpath = f'{self.out_folder}/{outpath}'
        self.opt = optimize.Optimizer(self.execution_name, self.miner_name, 
                                      self.log_path, self.metrics_list, 
                                      self.outpath, self.constraints_list)
        self.star_time = time.time()

    def _parse_constraints(self, constraints_string):
        if constraints_string:
            parser = ConstraintParser(constraints_string)
            parsed_constraints = parser.parse()
            constraints_list = parser.extract_constraints()

            #print("---PARSE---")
            #print("Expresión traducida a Python:", parsed_constraints)
            #print("Restricciones individuales:", constraints_list)

        else:
            constraints_list=[]
        
        return constraints_list
    
    def __log(self):
        '''
        Stores relevant information about the execution (e.g. runtime, log name, miner type, etc)
        '''
        if os.path.isfile(self.log_file):
            with open(self.log_file, 'a') as log:
                runtime = str(self.end_time - self.star_time)
                log.write(f'\n{self.local_time};{runtime};{self.log_path};{self.miner_name};{self.opt_type};{self.extract_params()};{self.metrics_list};{self.opt.get_best_solution().variables}')
        else:
            with open(self.log_file, 'w') as log:
                log.write('Timestamp,Runtime, Log Name, Miner Type, Opt type, Opt config, Metrics type, Optimal solution')
            self.__log()

    def extract_params(self):
        '''
        Extracts the parameters of the optimization algorithm (e.g. NSGAII) into strings

        Returns
        -------

        dict : Dictionary where the keys are the parameter names and the values are either 
               the corresponding parameter value or, for objects, a list containing the object
               and its atributes.
        '''
        dicc = dict()
        for (attr_name, attr_value) in self.params.items():
            if hasattr(attr_value, '__dict__'):
                dicc[attr_name] = [f"{attr_value.__class__.__module__}.{attr_value.__class__.__name__}", attr_value.__dict__]
            else:
                dicc[attr_name] = attr_value
        return dicc
    
    def save_petri_nets_imgs(self):
        """
        Saves Petri nets for each Pareto optimal solution.
        """
        os.makedirs(self.outpath, exist_ok=True)

        for index, petri in enumerate(self.opt.get_pareto_front_petri_nets()):
            gviz = pn_visualizer.apply(petri[0], petri[1], petri[2])
            pn_visualizer.save(gviz, f'{self.outpath}/petri_pareto_{index}.png')

    def save_petri_nets_db(self):
        """
        Saves the discovered petri nets in an sqlite database, all petris will be stored associated
        with the execution that produced them with all relevant information.
        """

        #conn = sqlite3.connect(common.DB_PATH)
        conn = "placeholder"
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                optimizer TEXT,
                miner TEXT,
                event_log TEXT,
                metrics TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS petri_nets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id INTEGER,
                places TEXT,
                transitions TEXT,
                arcs TEXT,
                FOREIGN KEY (execution_id) REFERENCES executions(id)
            )
        """)
         
        cursor.execute("INSERT INTO executions (optimizer, miner, event_log, metrics) VALUES (?, ?, ?, ?)",
                    (self.opt_type, self.miner_name, self.log_path, self.metrics_list))
        
        self.execution_id = cursor.lastrowid

        for petri in self.opt.get_pareto_front_petri_nets():
            petri_net = petri[0]

            places = json.dumps([str(place) for place in petri_net.places])
            transitions = json.dumps([str(t) for t in petri_net.transitions]) 
            arcs = json.dumps([str(arc) for arc in petri_net.arcs])


            cursor.execute("INSERT INTO petri_nets (execution_id, places, transitions, arcs) VALUES (?, ?, ?, ?)",
                        (self.execution_id, places, transitions, arcs))
            
        conn.commit()
        conn.close()

    def save_pareto_front(self):
        """
        Saves the Pareto front graph as an image.
        """
        os.makedirs(self.outpath, exist_ok=True)
        self.opt.plot_pareto_front(title='Pareto front approximation', filename=f'{self.outpath}/Pareto Front')

    def save_csvs(self):
        """
        Saves CSV files for variables and objectives of each Pareto optimal solution.
        """
        os.makedirs(self.outpath, exist_ok=True)

        # Save result variables to CSV
        with open(f"{self.outpath}/results_variables.csv", 'w') as log:
            parameter_names = ",".join(self.opt.parameters_info.base_params.keys())
            log.write(parameter_names + "\n")
            for sol in self.opt.get_result():
                log.write(f'{",".join(map(str, sol.variables))}\n')

        # Save result objectives to CSV
        with open(f"{self.outpath}/results_objectives.csv", 'w') as log:
            metrics_labels = ",".join(self.opt.problem.metrics_obj.get_labels())
            log.write(metrics_labels + "\n")
            for sol in self.opt.get_result():
                log.write(f'{",".join(map(str, sol.objectives))}\n')
    
    def save_petris_graphs(self):
        graphs = utils.load_petris_as_graphs(execution_id=self.execution_id)
        os.makedirs(f'{self.outpath}/graphs', exist_ok=True)
        os.makedirs(f'{self.outpath}/graphs/comparisons_matrix', exist_ok=True)
        os.makedirs(f'{self.outpath}/graphs/msc', exist_ok=True)
        for index, graph in enumerate(graphs):
            utils.plot_petri_graph_pyvis(graph, filename=f'{self.outpath}/graphs/{index}.html')

        utils.plot_petri_distances(filename=f'{self.outpath}/graphs/adj_spectral_heatmap.png', 
                                   petri_graphs=graphs)
        utils.compare_multiple_petri_nets(output_dir=f'{self.outpath}/graphs/comparisons_matrix',
                                        petri_graphs=graphs)
        utils.analyze_similar_petrinets_MSC(output_dir=f'{self.outpath}/graphs/msc',
                                            petri_graphs=graphs)

    def parallel_discover(self, algorithm_name, store=True, **params):
        if algorithm_name not in self.available_opts:
            return ValueError(f"Optmizador '{algorithm_name}' no está soportado. Los optmizadores disponibles son: {list(self.available_opts.keys())}")
        algorithm_class = self.available_opts[algorithm_name]

        self.opt_type = algorithm_name
        self.params = params
        self.opt.discover_parallel(algorithm_class=algorithm_class, **params)
        self.opt_type = algorithm_class.__name__
        self.end_time = time.time()
        
        if store:
            self.__log()
            self.store()
            
    def discover(self, algorithm_name, store=True, **params):
        '''
        Performs the hiperparameter optimization of the miner specified when instanciating
        the class using the algorithm class and its hiperparameters entered as attributes.
        If the 'store' parameter is True relevant information of the execution will be saved

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
        

        if store:
            self.__log()
            self.store()
        
    def store(self):
        self.save_petri_nets_imgs()
        #self.save_petri_nets_db()
        #self.save_pareto_front()
        self.save_csvs()
    
    def set_log_file(self, logpath):
        '''
        Allows to set up the log file path (default is 'doc/log.csv')
        '''
        self.log_file = logpath
    
    def set_out_folder(self, outpath):
        '''
        Allows to set up the out path where information about each execution will be stored
        (default is 'out/')
        '''
        os.makedirs(outpath, exist_ok=True)
        self.out_folder = outpath

    def show_pareto_iterations(self):
        fronts_path = os.path.join(self.outpath, 'FRONTS')
        files = sorted([f for f in os.listdir(fronts_path) if f.startswith("FUN.") and os.path.isfile(os.path.join(fronts_path, f))])
        
        for file in files:
            with open(os.path.join(fronts_path, file), 'r') as f:
                lines = f.readlines()
                unique_lines = sorted(set(map(str.strip, lines)))
                unique_count = len(unique_lines)
                print(f"{file}: {unique_count}")
        
## TESTING
if __name__ == "__main__":

    #logs = common.generate_logs_dict()
    logs = "placeholder"
    log_closed = ('Closed', logs['Closed'])
    log = log_closed
    
    p_miner = ProcessMiner(miner_name='heuristic',
                            metrics='basic',
                            log = log)
    
    p_miner.discover(algorithm_name='NSGAII', **config.nsgaii_params)
    p_miner.show_pareto_iterations()
    p_miner.save_petris_graphs()
