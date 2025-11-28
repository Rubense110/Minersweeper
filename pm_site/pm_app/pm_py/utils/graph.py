import json
import sqlite3
from django.shortcuts import get_object_or_404
import networkx as nx
import numpy as np

from pm_app.models import Execution, Petri

def save_petri_nets_db(DB_path, ProcessMinerObject):
        """
        Receives the Database path and a ProcessMiner object and saves the discovered petri nets in an sqlite database, 
        all petris will be stored associated with the execution that produced them with all relevant information.
        """

        conn = sqlite3.connect(DB_path)
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
                    (ProcessMinerObject.opt_type, ProcessMinerObject.miner_name, ProcessMinerObject.log_path, ProcessMinerObject.metrics_name))
        
        ProcessMinerObject.execution_id = cursor.lastrowid

        for petri in ProcessMinerObject.opt.get_pareto_front_petri_nets():
            petri_net = petri[0]

            places = json.dumps([str(place) for place in petri_net.places])
            transitions = json.dumps([str(t) for t in petri_net.transitions]) 
            arcs = json.dumps([str(arc) for arc in petri_net.arcs])


            cursor.execute("INSERT INTO petri_nets (execution_id, places, transitions, arcs) VALUES (?, ?, ?, ?)",
                        (ProcessMinerObject.execution_id, places, transitions, arcs))
            
        conn.commit()
        conn.close()

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