import numpy as np
from jmetal.core.problem import FloatSolution
import matplotlib.pyplot as plt
from typing import List
import sys
import os
import pandas as pd
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def calculate_pareto_front(solutions : List[FloatSolution], metrics_labels):
    solution_objectives = np.array([sol.objectives for sol in solutions])
    df = pd.DataFrame(solution_objectives, columns=metrics_labels)

    data = df.values
    is_dominated = np.zeros(len(data), dtype=bool)

    for i, sol1 in enumerate(data):
        for j, sol2 in enumerate(data):
            if i != j:
                if np.all(sol2 <= sol1) and np.any(sol2 < sol1):
                    is_dominated[i] = True
                    break
    
    return df.loc[~is_dominated].drop_duplicates()


def calculate_pareto_front_old(solutions : List[FloatSolution]):
    front = []
    solution_objectives = np.array([sol.objectives for sol in solutions])
    for i, sol1 in enumerate(solution_objectives):
        dominated = False
        for j, sol2 in enumerate(solution_objectives):
            if i!=j:
                if np.all(sol2 <= sol1) and np.any(sol2 < sol1):
                    dominated = True
                    break
        is_already_in_front = any(np.array_equal(sol1, f.objectives) for f in front)
        if not dominated and not is_already_in_front:
            front.append(solutions[i])

    return front

def determine_color(index):
    colors = ['red', 'green', 'black', 'darkslategray', 'purple', 'orange']
    if index >= len(colors):
        index = index - len(colors)
        determine_color(index)
    else:
        color = colors[index]
    return color

def plot_pareto_front(solutions : List[FloatSolution], axis_labels, title, filename):
    pareto_front_objectives = [sol.objectives for sol in calculate_pareto_front(solutions)]
    dominated_solutions_objectives = [sol.objectives for sol in solutions if (any((sol.objectives==pareto_sol).all()) for pareto_sol in pareto_front_objectives)]

    pareto_front_objectives = [[abs(value) for value in sol] for sol in pareto_front_objectives]
    dominated_solutions_objectives = [[abs(value) for value in sol] for sol in dominated_solutions_objectives]
    
    plt.figure(figsize=(10, 6))
    x = np.arange(len(pareto_front_objectives[0]))
                  
    for solution in dominated_solutions_objectives:
       plt.plot(x, solution, color= 'paleturquoise')

    for optimal_solution in pareto_front_objectives:
        plt.plot(x, optimal_solution)

    plt.xlabel('Objetivos', fontweight= 550, fontsize = 14)
    plt.ylabel('Valor', fontweight= 550, fontsize = 14)
    plt.title(title, fontweight= 550, fontsize = 20)
    plt.xticks(x, axis_labels)
    plt.grid()
    plt.savefig(filename)