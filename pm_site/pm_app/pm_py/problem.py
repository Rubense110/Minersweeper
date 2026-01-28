import random
import re

from jmetal.core.problem import FloatProblem, FloatSolution
from pm4py.algo.discovery.heuristics import algorithm as heuristics_miner
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.convert import convert_to_petri_net
from pm4py.objects.log.importer.xes import importer as xes_importer

from pm_app.pm_py.metrics import (CustomMetrics, METRICS_FUNCTIONS_PROBLEM,
                                  distance_metrics, get_fitness, get_precision,
                                  get_simplicity_pm4py, get_generalization_pm4py)
from pm_app.pm_py.parameters import BaseParametersConfig


class PMProblem(FloatProblem):
    '''
    Custom optimization problem for process mining. The goal of this problem class is to
    tune the hiperparameters of the chosen process mining algorithm in order to find useful
    process models, measuring them following the specified metrics.

    This class extends 'FloatProblem' from the Jmetal metaheuristic optimization framework.

    Attributes
    ----------
    miner : str
        miner name e.g. : 'heuristic'
    log_path : str
        The event log path 
    metrics_name : str
        An string specifying the metrics that defines how to calculate the fitness of a mined process model. 
        Must be one implementation from the 'metrics' module.
    parameters_info : parameters.BaseParameters
        Contains relevant information about the hiperparameters of the chosen miner such as
        their value range and data type.


    '''

    def __init__(self, miner_name, log_path, metrics_list, parameters_info: BaseParametersConfig, constraints_list=[], use_cached=True):
        super(PMProblem, self).__init__()

        self.miner = miner_name         
        self.log = xes_importer.apply(log_path, parameters={'show_progress_bar' : False})        
        self.metrics_obj = self.__get_metrics_obj(metrics_list)  
        self.parameters_info = parameters_info   
        self.constraints_list = constraints_list
        #print("---constraints--- \n", self.constraints_list)

        self.n_of_objectives = self.metrics_obj.get_n_of_metrics()
        self._n_of_variables = self.__get_n_genes()
        self.n_of_constraints = self.number_of_constraints()

        self.lower_bound, self.upper_bound = self.__get_bounds()
        self.use_cached = use_cached
        self.evaluation_cache = {}


    def __get_bounds(self): 
        '''
        Determines the value range for the parameters of the specified miner
        '''
        lower_bound = [i[0] for i in self.parameters_info.param_range.values()]
        upper_bound = [i[1] for i in self.parameters_info.param_range.values()]
        return lower_bound, upper_bound
    
    def __get_n_genes(self):
        '''
        range of posible values for each gene (miner parameter)
        '''
        return len(self.parameters_info.param_range)
    
    def evaluate(self, solution: FloatSolution) -> FloatSolution :
        '''
        Specifies how solutions will be evaluated. It generates the petri net corresponding to the solution 
        and then uses the specified metrics to evaluate it.
        '''
        solution_key = tuple(round(v, 2) for v in solution.variables)
        if solution_key in self.evaluation_cache and self.use_cached==True :
            cached_data = self.evaluation_cache[solution_key]
            solution.objectives = cached_data['objectives']
            solution.constraints = cached_data.get('constraints', [0.0]*self.n_of_constraints)
            solution.n_of_objectives = self.n_of_objectives
        
        else:
            params = {key: solution.variables[idx] for idx, key in enumerate(self.parameters_info.param_range.keys())}

            petri, im, fm = self._create_petri_net_sol(params)
            solution.objectives = self.metrics_obj.get_metrics_array(petri, im, fm, self.log)
            self.metrics_cache = self.metrics_obj.computed_metrics
            solution.n_of_objectives = self.n_of_objectives

            constraints = []
            if len(self.constraints_list) > 0:
                #print("\n---PROBLEM---")
                #print("constraints: ", self.constraints_list)
                self._evaluate_constraints(solution, petri, im, fm)
                constraints = solution.constraints

            self.evaluation_cache[solution_key] = {
                'objectives': solution.objectives,
                'constraints': constraints
            }
        
        return solution
    
    def _evaluate_constraints(self, solution:FloatSolution, petri, im, fm):

        # initialize generic constraints array
        constrs = [0.0 for _ in range(self.number_of_constraints())]

        # parse an generate correct JmetalPy constraint expressions from input
        constraint_expressions = self._parse_constraint_expresions()
        constraint_expressions = self._generate_constraints_expressions(constraint_expressions)
        #print("constraint_expressions", constraint_expressions)
        self.constraints_cache = self.metrics_cache
        # Now, one by one we generate the correct constraints and replace them in the previous array
        for i, expr in enumerate(constraint_expressions):
            tokens = re.split(r'[-+*/() ]+', expr)         # Divide la expresión en partes
            tokens = [token for token in tokens if token]  # Filtra vacíos

            # Obtain the name of the constrained value from the expresion (i.e. n_arcs, precision, etc)
            for token in tokens:
                if not token.replace(".", "", 1).isdigit():
                    #print("token_check", token)
                    constraint_variable_name = token

            # Get function to calculate the value for the constraint
            constraint_func= METRICS_FUNCTIONS_PROBLEM[constraint_variable_name] 

            # Evaluate, or recover from the objectives array if it was already computed
            if constraint_variable_name not in list(self.constraints_cache.keys()) and constraint_variable_name not in distance_metrics:
                constraint_variable_value = constraint_func(petri, im, fm, self.log)
                self.constraints_cache[constraint_variable_name] = constraint_variable_value
            elif constraint_variable_name not in distance_metrics:
                constraint_variable_value = self.constraints_cache[constraint_variable_name]
            
            # In the case of the distance metrics, if any of their subyacent metrics are already computed, we just recover those values
            elif constraint_variable_name in distance_metrics:
                if constraint_variable_name in self.constraints_cache:
                    constraint_variable_value = self.constraints_cache[constraint_variable_name]
                elif constraint_variable_name == 'fpd':
                    fitness = self.constraints_cache.get('fitness') or get_fitness(petri, im, fm, self.log)
                    precision = self.constraints_cache.get('precision') or get_precision(petri, im, fm, self.log)
                    constraint_variable_value = abs(fitness - precision)

                elif constraint_variable_name == 'sgd':
                    simplicity = self.constraints_cache.get('simplicity') or get_simplicity_pm4py(petri, im, fm, self.log)
                    generalisation = self.constraints_cache.get('generalisation') or get_generalization_pm4py(petri, im, fm, self.log)
                    constraint_variable_value = abs(simplicity - generalisation)
            
            # Map constraint name to its value, then evaluate the expresion and fix the constraint.
            constr_variable = {constraint_variable_name : constraint_variable_value}
            constrs[i] = eval(expr, {}, constr_variable) 

        
        solution.constraints = constrs
        #print(f"Constraints: \n{solution.constraints} \nSuma:{sum(solution.constraints)}")

    def _parse_constraint_expresions(self):
        metric_names = self.metrics_obj.metrics
        metric_names = [metric.name for metric in metric_names]

        translated_constraints = []
        for constraint in self.constraints_list:
            new_constraint = constraint  # Copia original para modificar
            translated_constraints.append(new_constraint)  # Añadir la versión modificada

        return translated_constraints


    
    def _create_petri_net_sol(self, params):
        '''
        Auxiliary function to manage the petri net generation, as its particularities depend of the selected miner.
        Currently only inductive and heuristic miners are suported.
        '''
        if self.miner == 'heuristic':
            petri, initial_marking, final_marking = heuristics_miner.apply(self.log, parameters= params)
        elif self.miner == 'inductive':
            inductive_variant = inductive_miner.Variants.IMf if params["noise_threshold"] > 0 else inductive_miner.Variants.IM
            params["multi_processing"] = True if params["multi_processing"] > 0.5 else False
            params["disable_fallthroughs"] = True if params["disable_fallthroughs"] > 0.5 else False
            process_tree = inductive_miner.apply(self.log, variant = inductive_variant,  parameters= params )
            petri, initial_marking, final_marking = convert_to_petri_net(process_tree)    
        return petri, initial_marking, final_marking
    
    def create_solution(self) -> FloatSolution:
        '''
        Specifies how solutions are created, the actual process depends of the parameter type specified
        in the parameters module.
        '''
        new_solution = FloatSolution(number_of_constraints=self.n_of_constraints,
                                     number_of_objectives=self.n_of_objectives,
                                     lower_bound = self.lower_bound,
                                     upper_bound = self.upper_bound)   
        # Random Solution
        random_sol = list()
        for index, param_and_type in enumerate(self.parameters_info.param_type.items()):
            data_type = param_and_type[1]
            if data_type == int: 
                random_sol.append(random.randint(self.lower_bound[index], self.upper_bound[index]))
            elif data_type == bool:
                random_sol.append(random.choice([True, False]))
            else:
                random_sol.append(random.uniform(self.lower_bound[index], self.upper_bound[index]))


        new_solution.variables = random_sol
        return new_solution
    

    def __get_metrics_obj(self, metrics):
        '''
        Retrieves the custom metrics class based on the specified metrics name list.
        
        Returns
        -------
        class : The custom metrics class corresponding to the specified metrics name list.
        '''
        metrics_obj = CustomMetrics(metrics)
        return metrics_obj

    def name(self) -> str:
        return 'Custom Process Mining Problem'
    
    def number_of_constraints(self) -> int:
        if self.constraints_list:
            number_of_constraints = len(self.constraints_list)
        else: 
            number_of_constraints = 0

        return number_of_constraints
    
    def number_of_variables(self) -> int:
        return self._n_of_variables
    
    def number_of_objectives(self) -> int:
        return self.n_of_objectives
    

    def _generate_constraints_expressions(self, constraint_expressions):
        """Convierte restricciones en formato jMetalPy (≤ 0)"""
        transformed = []
        for constraint in constraint_expressions:
            left, op, right = re.split(r'\s*(=|<|≤|>|≥|<=|>=)\s*', constraint.strip())
            left, right = left.strip(), right.strip()

            if op == '>':  
                transformed.append(f"({left} - {right})")  
            elif op == '≥'or op == '>=':  
                transformed.append(f"({left} - {right})")  
            elif op == '<':  
                transformed.append(f"({right} - {left})")  
            elif op == '≤' or op == '<=':  
                transformed.append(f"({right} - {left})")  

            # Should be fixed to employ an epsion margin value.
            elif op == '=':  
                transformed.append(f"abs({left} - {right})")  

        return transformed
