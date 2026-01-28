import json
from django.shortcuts import get_object_or_404
import networkx as nx
import numpy as np

from pm_app.models import Execution, Petri


def load_petris_as_graphs(execution_id):
    """
    Loads stored petri nets from the sqlite DB as networkx directed graphs.
    Returns a dictionary with all petri graphs and their index on the solution list.
    """

    """conn = sqlite3.connect(common.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT places, transitions, arcs FROM Petri WHERE execution_id = ?", (execution_id,))
    petri_nets_data = cursor.fetchall()
    conn.close() """

    execution = get_object_or_404(Execution, pk=execution_id)
    petri_nets_data = Petri.objects.filter(execution=execution, is_pareto=True)

    graphs = {}
    for petri in petri_nets_data:
        G = nx.DiGraph()

        places = json.loads(petri.places)
        for place in places:
            G.add_node(place, type="place")

        transitions = json.loads(petri.transitions)
        for transition in transitions:
            if transition.startswith("(") and transition.endswith(")"):
                transition = tuple(e.strip("'") for e in transition.strip("()").split(", "))[0]
            G.add_node(transition, type="transition")

        arcs = json.loads(petri.arcs)
        for arc in arcs: # as they are strings source an target must be divided
            source, target = arc[0], arc[1]

            if source.startswith("(") and source.endswith(")"):
                source = tuple(e.strip("'") for e in source.strip("()").split(", "))[0]

            if target.startswith("(") and target.endswith(")"):
                target = tuple(e.strip("'") for e in target.strip("()").split(", "))[0]

            G.add_edge(source, target)

        graphs.update({petri.id_on_exec : G})

    return graphs

def adjacency_spectral_distance(G1, G2):
    # Obtener matrices de adyacencia
    A1 = nx.adjacency_matrix(G1).todense()
    A2 = nx.adjacency_matrix(G2).todense()

    # Calcular espectros (autovalores)
    eigs1 = np.linalg.eigvalsh(A1)
    eigs2 = np.linalg.eigvalsh(A2)

    # Ordenar los autovalores de mayor a menor
    eigs1 = np.sort(eigs1)[::-1]
    eigs2 = np.sort(eigs2)[::-1]

    # Igualar la longitud si los grafos tienen diferente número de nodos
    n = max(len(eigs1), len(eigs2))
    eigs1 = np.pad(eigs1, (0, n - len(eigs1)), mode='constant')
    eigs2 = np.pad(eigs2, (0, n - len(eigs2)), mode='constant')

    # Calcular la distancia euclidiana entre los espectros
    distance = np.linalg.norm(eigs1 - eigs2)
    
    return distance