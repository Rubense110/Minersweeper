from jmetal.operator.crossover import *
from jmetal.operator.mutation import *
from jmetal.util.termination_criterion import *

mutations = {
      'polynomial'  : PolynomialMutation,
      'random'      : SimpleRandomMutation,
      'uniform'     : UniformMutation,
      'non_uniform' : NonUniformMutation,
}

crossovers = {
      'pmx'     : PMXCrossover,
      'sbx'     : SBXCrossover,
}

def get_hipparam_dict(form_data):
        #print(form_data)
        param_dict = {}
        optimization_method =             form_data['optimization_method']

        mutation_type =                   form_data['mutation_type']
        mutation_probability =            float(form_data['mutation_probability'])
        crossover_type =                  form_data['crossover_type']
        crossover_probability =           float(form_data['crossover_probability'])
        max_evaluations =                 int(form_data['max_evaluations'])
        param_dict['population_size'] =   int(form_data['population_size'])
        termination = StoppingByEvaluations(max_evaluations=int(max_evaluations))
        param_dict['termination_criterion'] = termination
        param_dict['mutation'] = mutations[mutation_type](float(mutation_probability))
        param_dict['crossover'] = crossovers[crossover_type](float(crossover_probability))
        param_dict['max_evals'] = int(max_evaluations)
        if 'NSGAIII' not in optimization_method:
            param_dict['offspring_population_size'] = int(form_data['offspring_population_size'])
        try:
            param_dict['requested_cores'] = int(form_data.get('parallel_cores', 0))
        except (TypeError, ValueError):
            param_dict['requested_cores'] = 0

        return param_dict
