import contextlib
import os

import numpy as np
from pm4py.algo.evaluation.generalization import algorithm as generalization_pm4py
from pm4py.algo.evaluation.precision import algorithm as precision_evaluator
from pm4py.algo.evaluation.precision.variants.etconformance_token import Parameters
from pm4py.algo.evaluation.replay_fitness import algorithm as replay_fitness
from pm4py.algo.evaluation.simplicity import algorithm as simplicity_pm4py
from pm4py.objects.petri_net.obj import PetriNet

distance_metrics = ['fpd', 'sgd']

def get_n_places(petri:PetriNet, im, fm, events_log):
    return len (petri.places)

def get_n_transitions(petri:PetriNet, im, fm, events_log):
    return len (petri.transitions)

def get_n_arcs(petri:PetriNet, im, fm, events_log):
    return len (petri.arcs)

def get_cycl_complx(petri:PetriNet, im, fm, events_log):
    return  len(petri.arcs )- (len(petri.places) + len(petri.transitions)) + 2

def get_ratio_place_trans(petri:PetriNet, im, fm, events_log):
    return len(petri.places)/len(petri.transitions)

def get_joins(petri:PetriNet, im, fm, events_log):
    joins, _ = get_joins_splits(petri.arcs)
    return joins

def get_splits(petri:PetriNet, im, fm, events_log):
    _, splits = get_joins_splits(petri.arcs)
    return splits

def get_fitness(petri:PetriNet, im, fm, events_log):
    #fitness_token_dict = fitness_token_based_replay(log=events_log, petri_net=petri, initial_marking=im, final_marking=fm)
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            fitness_token_dict = replay_fitness.apply(log=events_log, petri_net=petri, 
                                                    initial_marking=im, final_marking=fm, 
                                                    variant=replay_fitness.Variants.TOKEN_BASED, 
                                                    parameters={"show_progress_bars" : False})
    
    fitness_token = fitness_token_dict['average_trace_fitness']
    return -fitness_token # Minimize

def get_precision(petri:PetriNet, im, fm, events_log):
    #precission_token = precision_token_based_replay(log=events_log, petri_net=petri, initial_marking=im, final_marking=fm)
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            precission_token = precision_evaluator.apply(log=events_log, net=petri, marking=im, 
                                                        final_marking=fm, 
                                                        variant=precision_evaluator.Variants.ETCONFORMANCE_TOKEN, 
                                                        parameters={"show_progress_bar" : False,
                                                                    Parameters.SHOW_PROGRESS_BAR: False})

    return -precission_token # Minimize

def get_simplicity_pm4py(petri:PetriNet, im, fm, events_log):
    # Si no se hace print a petri no funciona xd con este assert hacemos lo mismo 
    # pero sin petar la consola a prints.
    assert hasattr(petri, 'places') and isinstance(petri.places, (set, list)), "petri_net.places no es iterable"
    return -simplicity_pm4py.apply(petri_net=petri,
                                   parameters={"show_progress_bars" : False}) # Minimize

def get_generalization_pm4py(petri, im, fm, events_log):
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            generalization = -generalization_pm4py.apply(
                log=events_log,
                petri_net=petri,
                initial_marking=im,
                final_marking=fm,
                parameters={"show_progress_bars": False}
            )
    return generalization

### Solucion poco elegante para el problema con las restricciones positivas...
def get_fitness_positive(petri:PetriNet, im, fm, events_log):
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            fitness_token_dict = replay_fitness.apply(log=events_log, petri_net=petri, 
                                                    initial_marking=im, final_marking=fm, 
                                                    variant=replay_fitness.Variants.TOKEN_BASED, 
                                                    parameters={"show_progress_bars" : False})
    fitness_token = fitness_token_dict['average_trace_fitness']
    return fitness_token # Minimize

def get_precision_positive(petri:PetriNet, im, fm, events_log):
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            precission_token = precision_evaluator.apply(log=events_log, net=petri, marking=im, 
                                                        final_marking=fm, 
                                                        variant=precision_evaluator.Variants.ETCONFORMANCE_TOKEN, 
                                                        parameters={"show_progress_bar" : False,
                                                                    Parameters.SHOW_PROGRESS_BAR: False})
    return precission_token # Minimize

def get_simplicity_pm4py_positive(petri:PetriNet, im, fm, events_log):
    # Si no se hace print a petri no funciona xd con este assert hacemos lo mismo 
    # pero sin petar la consola a prints.
    assert hasattr(petri, 'places') and isinstance(petri.places, (set, list)), "petri_net.places no es iterable"
    return simplicity_pm4py.apply(petri_net=petri, parameters={"show_progress_bars" : False}) # Minimize

def get_generalization_pm4py_positive(petri, im, fm, events_log):
    with open(os.devnull, 'w') as fnull:
        with contextlib.redirect_stdout(fnull), contextlib.redirect_stderr(fnull):
            generalization = generalization_pm4py.apply(
                log=events_log,
                petri_net=petri,
                initial_marking=im,
                final_marking=fm,
                parameters={"show_progress_bars": False}
            )
    return generalization
###

def get_fpd(petri:PetriNet, im, fm, events_log):
    fitness = get_fitness(petri, im, fm, events_log)
    precision = get_precision(petri, im, fm, events_log)

    return abs(fitness-precision)

def get_sgd(petri:PetriNet, im, fm, events_log):
    simplicity = get_simplicity_pm4py(petri, im, fm, events_log)
    generalisation = get_generalization_pm4py(petri, im, fm, events_log)

    return abs(simplicity-generalisation)




###################### ARRAY #####################

METRICS_FUNCTIONS = {
    "places": get_n_places,
    "transitions": get_n_transitions,
    "arcs": get_n_arcs,
    "cycl_complx": get_cycl_complx,
    "ratio": get_ratio_place_trans,
    "joins": get_joins,
    "splits": get_splits,
    "fitness": get_fitness,
    "precision": get_precision,
    "simplicity": get_simplicity_pm4py,
    "generalisation": get_generalization_pm4py,
    "fpd": get_fpd,
    "sgd": get_sgd
}

# Solucion poco elegante a mi problema de metricas negativas en restricciones...
METRICS_FUNCTIONS_PROBLEM = {
    "places": get_n_places,
    "transitions": get_n_transitions,
    "arcs": get_n_arcs,
    "cycl_complx": get_cycl_complx,
    "ratio": get_ratio_place_trans,
    "joins": get_joins,
    "splits": get_splits,
    "fitness": get_fitness_positive,
    "precision": get_precision_positive,
    "simplicity": get_simplicity_pm4py_positive,
    "generalisation": get_generalization_pm4py_positive,
    "fpd": get_fpd,
    "sgd": get_sgd
}

# Clase Metric corregida
class Metric:
    def __init__(self, name):
        if name not in METRICS_FUNCTIONS:
            raise ValueError(f"Métrica '{name}' no reconocida.")
        self.name = name
        self.func = METRICS_FUNCTIONS[name]

    def compute(self, petri, im, fm, log):
        return self.func(petri, im, fm, log)

# Clase CustomMetrics corregida
class CustomMetrics:
    def __init__(self, metrics_list=None):
        self.metrics = []
        if metrics_list:
            for metric_name in metrics_list:
                self.add_metric(Metric(metric_name))

        # Moving these to the end may improve runtime
        distance_metrics = ['fpd', 'sgd']
        non_dist_metrics = [x for x in self.metrics if x not in distance_metrics]
        dist_in_metrics = [x for x in self.metrics if x in distance_metrics]
        self.metrics = non_dist_metrics + dist_in_metrics
        self.computed_metrics = {}

    def add_metric(self, metric):
        self.metrics.append(metric)

    def remove_metric(self, metric_name):
        self.metrics = [m for m in self.metrics if m.name != metric_name]

    def get_metrics_array(self, petri, im, fm, log):
        computed_metrics = {}

        for metric in self.metrics:
            if metric.name not in distance_metrics:
                computed_metrics[metric.name] = metric.compute(petri, im, fm, log)

            elif metric.name in distance_metrics:
                if metric.name  == 'fpd':
                    fitness = computed_metrics.get('fitness') or get_fitness(petri, im, fm, log)
                    precision = computed_metrics.get('precision') or get_precision(petri, im, fm, log)
                    computed_metrics['fpd'] = abs(fitness - precision)

                elif metric.name == 'sgd':
                    simplicity = computed_metrics.get('simplicity') or get_simplicity_pm4py(petri, im, fm, log)
                    generalisation = computed_metrics.get('generalisation') or get_generalization_pm4py(petri, im, fm, log)
                    computed_metrics['sgd'] = abs(simplicity - generalisation)
        
        self.computed_metrics = computed_metrics
        return np.array(list(computed_metrics.values()))
        #return np.array([metric.compute(petri, im, fm, log) for metric in self.metrics])

    def get_labels(self):
        return [metric.name for metric in self.metrics]
    
    def get_n_of_metrics(self):
        return len(self.metrics)

    
###################### AUX ######################

def get_joins_splits(arcs):

    splits = dict()
    joins = dict()
    n_splits = 0
    n_joins = 0

    for arc in arcs:

        # obtain split dict
        if arc.source not in splits:
            splits[arc.source] = [arc.target]
        else:
            splits[arc.source].append(arc.target)

        # obtain join dict
        if arc.target not in joins:
            joins[arc.target] = [arc.source]
        else:
            joins[arc.target].append(arc.source)

    # count joins and splits
    for i in splits.values():
        if len(i) > 1: n_splits+=1

    for i in joins.values():
        if len(i) > 1: n_joins+=1

    return (n_splits, n_joins)
