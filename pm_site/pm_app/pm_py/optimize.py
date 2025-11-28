from pm_app.pm_py import metrics 
from pm_app.pm_py import parameters 
from pm_app.pm_py.utils.pareto import calculate_pareto_front, plot_pareto_front
from pm_app.pm_py.problem import PMProblem

from pm4py.algo.discovery.heuristics import algorithm as heuristics_miner
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.convert import convert_to_petri_net
from jmetal.algorithm.multiobjective.nsgaii import NSGAII
from jmetal.util.observer import WriteFrontToFileObserver
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.termination_criterion import StoppingByEvaluations
from jmetal.util.solution import get_non_dominated_solutions
import os
import contextlib
import logging
from tqdm import tqdm
import sys
from jmetal.core.observer import Observer

class TqdmProgressObserver:
    def __init__(self, total_evaluations):
        self.total = total_evaluations
        self.pbar = tqdm(
            total=total_evaluations,
            dynamic_ncols=True,
            disable=False,
            file=sys.stdout  # explícitamente escribir a stdout
        )

    def update(self, *args, **kwargs):
        evaluations = kwargs.get("EVALUATIONS", None)
        if evaluations is not None:
            delta = evaluations - self.pbar.n
            if delta > 0:
                self.pbar.update(delta)

    def finalize(self):
        self.pbar.close()


class FrontCollectorObserver(Observer):
    def __init__(self):
        self.fronts = []

    def update(self, *args, **kwargs):
        evaluations = kwargs.get("EVALUATIONS")
        solutions = kwargs.get("SOLUTIONS")
        if solutions:
            objectives = [s.objectives.tolist() for s in solutions]
            self.fronts.append({"evaluations": evaluations, "front": objectives})


class Optimizer():
    '''
    This class performs hyperparameter optimization of process mining algorithms using different techniques implemented
    on the Jmetal metaheuristic algorithm optimization framework

    This class manages the main optimization process, storing the results and extracting the pareto front approximation,
    it also provides methods to retrieve solutions, visualize them, and convert them to petri nets.

    The class extends the PMProblem class, wich specifies the optimization problem, including how solutions are created and evaluated.

    Attributes
    ----------
    miner : class
        The mining algorithm class being optimized (e.g., heuristics_miner, inductive_miner).
    log : object
        The loaded event log data.
    metrics_obj : object
        The type of metrics used for evaluation. Must be one of te implementations from the 'metrics' module
    
    '''

    def __init__(self, execution_name, miner_name, log_path, metrics_list, out_folder, constraints_list=[]):

        self.execution_name = execution_name
        self.miner_name = miner_name
        self.log_path = log_path
        self.metrics_list = metrics_list
        self.parameters_info = self.__get_parameters(miner_name, log_path)
        self.out_folder = out_folder
        self.metrics_list = metrics_list
        with open(os.devnull, 'w') as fnull:
            with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
                self.log = xes_importer.apply(log_path)
        self.constraints_list = constraints_list
        self.problem=PMProblem(
            miner_name= miner_name,
            log_path=log_path,
            metrics_list=metrics_list,
            parameters_info=self.parameters_info,
            constraints_list=self.constraints_list,
        )
    
    def __get_parameters(self, miner, log):
        '''
        Returns the hiperparameters to be optimized, as each miner has its own hiperparameters each one requires a different approach.

        Parameters
        ----------
        miner : class
            The mining algorithm class for which to retrieve hyperparameters (e.g., heuristics_miner, inductive_miner).
        log : object
            The loaded event log data.

        Returns
        -------
        parameters.BaseParametersConfig : An instance of the hyperparameters class corresponding to the specified miner.

        '''
        if miner == 'heuristic':
            params = parameters.HeuristicParametersConfig(log)
            return params
        elif miner == 'inductive':
            params = parameters.InductiveParametersConfig()
            return params
        else:
            raise ValueError(f"Miner '{miner}' not supported. Available miners are: heuristic, inductive")

    def show_result(self):
        '''
        Displays the solutions obtained by the algorithm in the console.
        '''

        print("\n### RESULT ###\n")
        for (i,j)in enumerate(self.result):
            print("Solution ",i," :")
            print("     variables: ",j.variables)
            print("     objectives:",j.objectives.tolist(),"\n")
        print("##############")

    def discover_parallel(self, algorithm_class, **params):
        '''
        Executes parallel hyperparameter optimization
        '''
        
        max_evaluations = params.pop('max_evals')
        self.cores_employed = params.pop('cores')
        self.algorithm = algorithm_class(problem=self.problem, **params)
        progress_observer = TqdmProgressObserver(max_evaluations)
        front_collector = FrontCollectorObserver()
        for name in [
            "jmetal",
            "jmetal.core.algorithm",
            "jmetal.util.solution",
        ]:
            logging.getLogger(name).setLevel(logging.ERROR)

        self.algorithm.observable.register(observer=WriteFrontToFileObserver(os.path.join(self.out_folder, f"FRONTS")))
        self.algorithm.observable.register(observer=progress_observer)
        self.algorithm.observable.register(observer=front_collector)
        self.algorithm.run()

        for name in [
            "jmetal",
            "jmetal.core.algorithm",
            "jmetal.util.solution",
        ]:
            logging.getLogger(name).setLevel(logging.DEBUG)
        progress_observer.finalize()
        self.result = self.algorithm.result()
        self.non_dom_sols = calculate_pareto_front(self.result, self.metrics_list)
        self.front_history = front_collector.fronts

    def discover(self,algorithm_class, **params):
        '''
        Executes hyperparameter optimization using the specified algorithm.

        This method initializes and runs the optimization process using a given Jmetal algorithm class. 
        The algorithm is executed with the specified hyperparameters, and the method stores the results, including 
        the final solutions and non-dominated solutions (Pareto front).

        Parameters
        ----------
        algorithm_class : class
            The class of the optimization algorithm to be used. This class must be from the Jmetal optimization framework.
        **params : dict, optional
            Additional keyword arguments representing the hyperparameters to be passed to the algorithm class.
        '''

        max_evaluations = params.pop('max_evals')
        self.algorithm = algorithm_class(problem=self.problem, **params)
        progress_observer = TqdmProgressObserver(max_evaluations)
        front_collector = FrontCollectorObserver()
        #self.algorithm.observable.register(observer=WriteFrontToFileObserver(os.path.join(self.out_folder, f"FRONTS")))
        self.algorithm.observable.register(observer=progress_observer)
        self.algorithm.observable.register(observer=front_collector)
        self.algorithm.run()
        progress_observer.finalize()
        self.result = self.algorithm.result()
        self.non_dom_sols = calculate_pareto_front(self.result, self.metrics_list)
        self.front_history = front_collector.fronts



    def get_result(self):
        '''
        Returns
        -------
        List[FloatSolutions] : A list contaning all Solutions generated by the algorithm in the last iteration.
        '''
        return self.result
        
    def get_best_solution(self):
        '''
        Returns
        -------
        FloatSolution : The best solution found by the algorithm
        '''
        return self.get_non_dominated_sols()[0]  # TO-DO

    def get_petri_net(self, sol=None):
        '''
        Parameters
        ----------
        sol : FloatSolution
            The solution to be converted to petri net. 

        Returns
        -------
        Tuple(net, initial marking, final marking) : A tuple contaning the petri net and the initial and final marking
                                                     for the specified solution, or the best solution if none is specified.
        '''
        if sol is None:
            sol = self.get_best_solution()

        params = {key: sol.variables[idx] for idx, key in enumerate(self.parameters_info.param_range.keys())}

        petri_net, initial_marking, final_marking = self._create_petri_net_sol(params)
        return petri_net, initial_marking, final_marking
    
    def get_non_dominated_sols(self):
        '''
        Returns
        -------
        List[FloatSolution] :  A list contaning the non-dominated solutions found by the algorithm
        '''
        return self.non_dom_sols

    def get_front_history(self):
        '''
        Returns the sequence of Pareto fronts collected during execution.
        '''
        return getattr(self, "front_history", [])
    
    def plot_pareto_front(self, title, filename):
        '''
        Plots the pareto front aproximation based on the algorithm's results.

        This method plots and saves the front in the specified file

        Parameters
        ----------
        title : str
            The title of the plot.
        filename : str
            The path of the file where the plot will be saved.
        '''
        plot_pareto_front(self.result,
                                axis_labels=self.problem.metrics_obj.get_labels(),
                                title = title,
                                filename=filename)


    def get_pareto_front_petri_nets(self):
        '''
        Returns
        -------
        List[Tuple(net, initial marking, final marking)] :  A list containing the petri nets of all solutions from 
                                                            the pareto front approximation.
        '''
        front = self.get_non_dominated_sols()
        petri_nets_from_pareto_sols = list()
        for sol in front:
            petri_nets_from_pareto_sols.append(self.get_petri_net(sol))
        return petri_nets_from_pareto_sols
    
    def get_result_petri_nets(self):
        '''
        Returns
        -------
        List[Tuple(net, initial marking, final marking)] :  A list containing the petri nets of all solutions from 
                                                            the last iteration of the optimization algorithm
        '''

        result = self.get_result()
        petri_nets = list()
        for sol in result:
            petri_nets.append(self.get_petri_net(sol))
        return petri_nets
    
    def _create_petri_net_sol(self, params):
        '''
        Auxiliary function to manage the petri net generation, as its particularities depend of the selected miner.
        Currently only inductive and heuristic miners are suported.
        '''
        
        if self.miner_name == 'heuristic':
            petri, initial_marking, final_marking = heuristics_miner.apply(self.log, parameters= params)
        elif self.miner_name == 'inductive':
            inductive_variant = inductive_miner.Variants.IMf if params["noise_threshold"] > 0 else inductive_miner.Variants.IM
            params["multi_processing"] = True if params["multi_processing"] > 0.5 else False
            params["disable_fallthroughs"] = True if params["disable_fallthroughs"] > 0.5 else False
            process_tree = inductive_miner.apply(self.log, variant = inductive_variant,  parameters= params )
            petri, initial_marking, final_marking = convert_to_petri_net(process_tree)    
        return petri, initial_marking, final_marking

    
## Testing

if __name__ == "__main__":

    from pm4py.objects.log.importer.xes import importer as xes_importer
    from pm4py.visualization.petri_net import visualizer as pn_visualizer
    from jmetal.operator.crossover import SBXCrossover
    from jmetal.operator.mutation import PolynomialMutation
    from jmetal.util.termination_criterion import StoppingByEvaluations


    max_evaluations = 1000

    log = xes_importer.apply('event_logs/Closed/BPI_Challenge_2013_closed_problems.xes')
    metrics_obj = metrics.Basic_Metrics()

    opt = Optimizer(heuristics_miner, log, metrics_obj, '/home/ruben/Escritorio/Proyectos/pm_py/src')

    nsgaii_params = {'population_size': 100,
                     'offspring_population_size': 100,
                     'mutation': PolynomialMutation(probability=1.0 / opt.number_of_variables, distribution_index=20),
                     'crossover': SBXCrossover(probability=1.0, distribution_index=20),
                     'termination_criterion': StoppingByEvaluations(max_evaluations=max_evaluations)}
    
    opt.discover(algorithm_class=NSGAII, **nsgaii_params)
    
    optimal_petri_net, initial_marking, final_marking = opt.get_petri_net()

    # visualize petri net
    gviz = pn_visualizer.apply(optimal_petri_net, initial_marking, final_marking)
    pn_visualizer.view(gviz)

    # plot Pareto front
    opt.plot_pareto_front(title='Pareto front approximation', filename='NSGAII-Pareto-Closed')
