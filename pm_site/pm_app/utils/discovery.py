import io
import tempfile
import os
import json
from time import time
from datetime import timedelta, datetime
from django.conf import settings
from ..models import *
import ast
from ..pm_py.process_miner import ProcessMiner
from pm4py.objects.log.importer.xes import importer as xes_importer
from ..pm_py import parameters
from jmetal.util.termination_criterion import *
from jmetal.algorithm.multiobjective.nsgaiii import UniformReferenceDirectionFactory
from .petri import clean_transition_data
from django.utils import timezone
import psutil
import numpy as np
from jmetal.util.evaluator import MultiprocessEvaluator
import requests
from pm4py.objects.petri_net.importer import importer as pnml_importer
from ..pm_py import metrics


def is_log(event_log):
    try:
        log = xes_importer.apply(event_log)
        return True
    except:   
        return False 

def store_log(event_log):
    '''
    Guarda el log subido por el usuario en el sistema.
    '''

    file_name = event_log.name
    file_path = os.path.join(settings.LOGS_FOLDER, file_name)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb+') as destination:
        for chunk in event_log.chunks():
            destination.write(chunk)

    if not is_log(file_path):
        os.remove(file_path)
        raise Exception
        
    
    
def convert_to_serializable(obj, parent_key=None):
    """Convierte un objeto a un formato serializable para almacenarlo en la base de datos,
    pero si encuentra 'population_evaluator' no recurre más y deja el objeto como está."""
    
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "population_evaluator":
                result[key] = 'MultiProcessEvaluator'  
            else:
                result[key] = convert_to_serializable(value, parent_key=key)
        return result

    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item, parent_key=parent_key) for item in obj]

    elif hasattr(obj, '__dict__') and parent_key != "population_evaluator":
        return {key: convert_to_serializable(value, parent_key=key) for key, value in obj.__dict__.items()}

    else:
        return obj



def discover(execution_name, optimization_method, opt_parameters_dict, miner_name, evaluation_metrics, logpath, form_data, constrs_string=None):
    '''
    Ejecuta el proceso de descubrimiento con los datos aportados por el usuario.
    Guarda los resultados en la BD y genera la imagen del frente de pareto. 
    Devuelve el id de la ejecución.
    '''

    discovery_start = time()
    print(f"\n#################################################################################")
    print(f"{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')} Starting. Selected parameters :")
    for key, value in form_data.items():
        print(f"{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')}    {key}: {value}")
    print(f"{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')} Begining Optimization process\n")

    if miner_name == "alpha":
        return discover_alpha(
            execution_name=execution_name,
            evaluation_metrics=evaluation_metrics,
            logpath=logpath,
            miner_name=miner_name,
            alpha_version="CLASSIC"
        )
    else:
        process_miner = ProcessMiner(
                        execution_name = execution_name,
                        miner_name=miner_name,
                        metrics=evaluation_metrics,
                        log = logpath, 
                        constraints_string=constrs_string)

        parallel_algorithms = {
            'PARALLEL - NSGAII': 'NSGAII',
            'PARALLEL - NSGAIII': 'NSGAIII',
            'PARALLEL - SPEA2': 'SPEA2',
        }
        algorithm_to_run = parallel_algorithms.get(optimization_method, optimization_method)
        requested_cores = opt_parameters_dict.pop('requested_cores', None)

        if algorithm_to_run == 'NSGAIII':
            if isinstance(evaluation_metrics, str):
                metrics_selected = ast.literal_eval(evaluation_metrics)
            else:
                metrics_selected = list(evaluation_metrics)
            reference_directions = UniformReferenceDirectionFactory(
                n_dim=len(metrics_selected),
                n_points=100,
            )
            opt_parameters_dict['reference_directions'] = reference_directions


        if optimization_method in parallel_algorithms:
            if requested_cores is None:
                try:
                    requested_cores = int(form_data.get('parallel_cores', 0))
                except (TypeError, ValueError):
                    requested_cores = 0

            system_cores = psutil.cpu_count(logical=True) or os.cpu_count() or 1
            cpu_cores = min(system_cores, requested_cores) if requested_cores and requested_cores > 0 else system_cores
            cpu_cores = max(cpu_cores, 1)  # safety guard

            population_evaluator = MultiprocessEvaluator(cpu_cores)
            opt_parameters_dict['population_evaluator'] = population_evaluator
            opt_parameters_dict['cores'] = cpu_cores
            print(opt_parameters_dict)
            try:
                process_miner.parallel_discover(algorithm_name=algorithm_to_run, **opt_parameters_dict)
            finally:
                # MultiprocessEvaluator manages its own multiprocessing.Pool; close to avoid leaks.
                population_evaluator.pool.close()
                population_evaluator.pool.join()
            opt_parameters_dict['requested_cores'] = requested_cores
        else:
            process_miner.discover(algorithm_name=algorithm_to_run, **opt_parameters_dict)
            opt_parameters_dict['requested_cores'] = requested_cores if requested_cores is not None else 0

        discovery_end = time()
        runtime = (discovery_end - discovery_start)
        print(f"\n{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')} algorithm runtime - {runtime}")
        runtime = timedelta(seconds=runtime)
        
        #### BBDD ####

        bbdd_time_init = time()
        execution = Execution.objects.create(
            name = execution_name,
            runtime = runtime,
            path_events_log = logpath.split('/')[-1], # ruta relativa
            metrics = evaluation_metrics,
            miner = miner_name,
            constraints = ", ".join(process_miner.constraints_list)
        )
        optimizer = Optimizer.objects.create(
            execution=execution,  
            name=optimization_method,  
            hip_params = convert_to_serializable(opt_parameters_dict),
            #hip_params=convert_to_serializable(process_miner.extract_params())
        )
        front_history = process_miner.opt.get_front_history()
        if front_history:
            snapshots = [
                FrontSnapshot(
                    execution=execution,
                    step=index,
                    evaluations=front.get("evaluations"),
                    objectives=front.get("front", []),
                )
                for index, front in enumerate(front_history)
            ]
            FrontSnapshot.objects.bulk_create(snapshots)

        execution_result = process_miner.opt.get_result()
        non_dom_sols = process_miner.opt.get_non_dominated_sols()
        non_dom_sols_array = non_dom_sols.to_numpy().tolist()
        non_dom_objectives = {tuple(obj) for obj in non_dom_sols_array}
        petri_nets = process_miner.opt.get_result_petri_nets()
        #process_miner.save_petri_nets_imgs()
        seen_objectives = set()

        for i, (solution, petri) in enumerate(zip(execution_result, petri_nets)):
            petri_net = petri[0]
            places_data = json.dumps([str(place) for place in petri_net.places])
            transitions_data, arcs_data = clean_transition_data(petri_net.transitions, petri_net.arcs, miner_name)
            transitions_data = json.dumps(transitions_data)
            arcs_data = json.dumps(arcs_data)

            objectives_list = solution.objectives
            objectives_tuple = tuple(objectives_list)
            already_seen = objectives_tuple in seen_objectives
            is_pareto = objectives_tuple in non_dom_objectives and not already_seen
            seen_objectives.add(objectives_tuple)

            petri_instance = Petri.objects.create(
                execution = execution,
                places = places_data,
                transitions = transitions_data,
                arcs = arcs_data,
                is_pareto = is_pareto,
                id_on_exec = i,
            )

            solution_instance = DSolution.objects.create(
                variables = solution.variables,
                objectives = solution.objectives,
                constraints = solution.constraints,
                execution = execution,
                is_pareto = is_pareto,
                petri = petri_instance,
            )

        execution.save()
        optimizer.save()

        bbdd_time_fin = time()
        print(f"{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')} BBDD runtime      - {bbdd_time_fin-bbdd_time_init}")
        return execution.id 


def call_prom_alpha(logpath, alpha_version="CLASSIC"):
    url = os.environ.get("PROM_SERVICE_URL", "http://prom_service:7070")
    payload = {
        "log_path": os.path.basename(logpath),
        "miner": "alpha",
        "alpha_version": alpha_version,  # opcional (si luego lo soportas en Java)
    }
    resp = requests.post(f"{url}/mine", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.text  # PNML string


def pnml_to_petri(pnml_str):
    with io.BytesIO(pnml_str.encode("utf-8")) as fh:
        with tempfile.NamedTemporaryFile(suffix=".pnml", delete=False) as tmp:
            tmp.write(fh.getvalue())
            tmp_path = tmp.name
    try:
        net, im, fm = pnml_importer.apply(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return net, im, fm

def discover_alpha(execution_name, evaluation_metrics, logpath, miner_name="alpha", alpha_version="CLASSIC"):
    pnml_str = call_prom_alpha(logpath, alpha_version=alpha_version)
    petri, im, fm = pnml_to_petri(pnml_str)

    if isinstance(evaluation_metrics, str):
        metrics_list = ast.literal_eval(evaluation_metrics)
    else:
        metrics_list = list(evaluation_metrics)

    log = xes_importer.apply(logpath)
    metrics_obj = metrics.CustomMetrics(metrics_list)
    objectives = metrics_obj.get_metrics_array(petri, im, fm, log).tolist()

    execution = Execution.objects.create(
        name=execution_name,
        runtime=timedelta(seconds=0),
        path_events_log=os.path.basename(logpath),
        metrics=str(metrics_list),
        miner=miner_name,
        constraints=""
    )
    Optimizer.objects.create(
        execution=execution,
        name="alpha",
        hip_params={"alpha_version": alpha_version}
    )

    places_data = json.dumps([str(place) for place in petri.places])
    if miner_name == "alpha":
        transitions_data = json.dumps([str(t) for t in petri.transitions])
        arcs_data = json.dumps([(str(a.source), str(a.target)) for a in petri.arcs])
    else:
        transitions_data, arcs_data = clean_transition_data(petri.transitions, petri.arcs, miner_name)
        transitions_data = json.dumps(list(transitions_data))
        arcs_data = json.dumps(list(arcs_data))

    petri_instance = Petri.objects.create(
        execution=execution,
        places=places_data,
        transitions=transitions_data,
        arcs=arcs_data,
        is_pareto=True,
        id_on_exec=0
    )

    DSolution.objects.create(
        variables=[],
        objectives=objectives,
        constraints=[],
        execution=execution,
        is_pareto=True,
        petri=petri_instance
    )

    return execution.id
