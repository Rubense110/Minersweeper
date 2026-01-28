from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.visualization.petri_net import visualizer as pn_visualizer
from pm4py.convert import convert_to_petri_net
from django.shortcuts import get_object_or_404
from ..models import DSolution
import io
import os
import base64
from ..pm_py.config import parameter_mapping, miner_mapping, inductive_miner, heuristics_miner
from ..pm_py.utils.graph import load_petris_as_graphs, adjacency_spectral_distance
from django.conf import settings
import itertools
import numpy as np
import json
import re

def get_petri_net(solution_id):
    solution = get_object_or_404(DSolution, pk=solution_id)

    execution = solution.execution
    sol_variables = solution.variables
    miner_name = execution.miner

    parameters_class = parameter_mapping[miner_name]
    miner_params = {key: sol_variables[idx] for idx, key in enumerate(parameters_class.param_range.keys())}
    miner_class = miner_mapping[miner_name]
    event_log_path = os.path.join(settings.LOGS_FOLDER, execution.path_events_log)
    log = xes_importer.apply(event_log_path)

    petri_net, initial_marking, final_marking = generate_petri_net(miner_class, miner_params, log)

    gviz = pn_visualizer.apply(petri_net, initial_marking, final_marking)

    buffer = io.BytesIO(gviz.pipe('png'))
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return img_b64

def generate_petri_net(miner_class, miner_params, log):

    if miner_class == heuristics_miner:
        petri, initial_marking, final_marking = miner_class.apply(log, parameters= miner_params)

    elif miner_class == inductive_miner:
        inductive_variant = inductive_miner.Variants.IMf if miner_params["noise_threshold"] > 0 else inductive_miner.Variants.IM
        miner_params["multi_processing"] = True if miner_params["multi_processing"] > 0.5 else False
        miner_params["disable_fallthroughs"] = True if miner_params["disable_fallthroughs"] > 0.5 else False

        process_tree = miner_class.apply(log, variant = inductive_variant,  parameters= miner_params )
        petri, initial_marking, final_marking = convert_to_petri_net(process_tree)  

    return petri, initial_marking, final_marking

def get_heatmap_data(execution_id):
    graphs_dict = load_petris_as_graphs(execution_id)
    
    # Crear un mapeo de claves originales a índices consecutivos
    keys = list(graphs_dict.keys())  
    key_to_index = {i: key for i, key in enumerate(keys)}
    
    graphs = list(graphs_dict.values())
    n = len(graphs)
    distance_matrix = np.zeros((n, n))

    # Llenar la matriz de distancias
    for idx1, idx2 in itertools.combinations(range(n), 2):
        dist = adjacency_spectral_distance(graphs[idx1], graphs[idx2])
        distance_matrix[idx1, idx2] = distance_matrix[idx2, idx1] = dist

    # Convertir la matriz a formato heatmap con índices normalizados
    heatmap_data = []
    for idx1 in range(n):
        for idx2 in range(n):
            heatmap_data.append({
                'x': idx1,  
                'y': idx2,  
                'value': distance_matrix[idx1, idx2]
            })

    # Devolver el heatmap y el mapeo de índices a claves originales
    return json.dumps({
        "heatmap": heatmap_data,
        "index_mapping": key_to_index
    })

def clean_transition_data(transitions, arcs, miner_name):


    if miner_name == 'heuristic':
        transitions = [re.sub(r"[\(\)']", "", str(transition)).split(",")[0] for transition in transitions]

        arcs = list(arcs)
        for i, arc in enumerate(arcs):
            source, target = str(arc).split("->") 
            target = re.sub(r"[\(\)']", "", str(target)).split(",")[0] 
            source = re.sub(r"[\(\)']", "", str(source)).split(",")[0] 
            arcs[i] = (source, target)

        # Paso 1: Crear un diccionario de reemplazo
        hid_mapping = {}
        for transition in transitions:
            if 'hid' in transition:
                transition_source = None
                transition_target = None
                
                for (source, target) in arcs:
                    if transition == source:
                        transition_target = target
                    if transition == target:
                        transition_source = source
                
                if transition_source and transition_target:
                    new_name = f"{transition_source}-hid-{transition_target}"
                    hid_mapping[transition] = new_name

        # Paso 2: Reemplazar en transitions
        transitions = [hid_mapping.get(t, t) for t in transitions]

        # Paso 3: Reemplazar en arcs
        updated_arcs = set()
        for source, target in arcs:
            new_source = hid_mapping.get(source, source)
            new_target = hid_mapping.get(target, target)
            updated_arcs.add((new_source, new_target))

        arcs = list(updated_arcs)  # Sobrescribimos las aristas actualizadas

    elif miner_name == 'inductive':
        print("\n###################################################################\n")
        print("transitions", transitions)
        ## Esta abominacion es por que en algunos tipos queremos el de la izquierda y en otros el de la derecha
        transitions = [re.sub(r"[\(\)']", "", str(transition)).split(",")[0].strip() if 
                       re.sub(r"[\(\)']", "", str(transition)).split(",")[1].strip()=='None' else
                       re.sub(r"[\(\)']", "", str(transition)).split(",")[1].strip() for transition in transitions]
        
        arcs = list(arcs)
        for i, arc in enumerate(arcs):
            print(arc)
            source, target = str(arc).split("->") 
            print(source, target)

            if '-' in re.sub(r"[\(\)']", "", str(target)).split(",")[0]: ## filtrar los malditos hashes
                target = re.sub(r"[\(\)']", "", str(target)).split(",")[1].strip()
            else:
                target = re.sub(r"[\(\)']", "", str(target)).split(",")[0].strip() 

            if '-' in re.sub(r"[\(\)']", "", str(source)).split(",")[0]:
                source = re.sub(r"[\(\)']", "", str(source)).split(",")[1].strip()
            else:
                source = re.sub(r"[\(\)']", "", str(source)).split(",")[0].strip() 

            arcs[i] = (source, target)

        # Paso 1: Crear un diccionario de reemplazo
        hid_mapping = {}
        for transition in transitions:
            if transition=='None':
                transition_source = None
                transition_target = None
                
                for (source, target) in arcs:
                    if transition == source:
                        transition_target = target
                    if transition == target:
                        transition_source = source
                if transition_source and transition_target:
                    new_name = f"{transition_source}-hid-{transition_target}"
                    hid_mapping[transition] = new_name

        # Paso 2: Reemplazar en transitions
        transitions = [hid_mapping.get(t, t) for t in transitions]


        # Paso 3: Reemplazar en arcs
        updated_arcs = set()
        for source, target in arcs:
            new_source = hid_mapping.get(source, source)
            new_target = hid_mapping.get(target, target)
            updated_arcs.add((new_source, new_target))
        arcs = list(updated_arcs)  # Sobrescribimos las aristas actualizadas
    

    return transitions, arcs


