from django import forms
from .models import *
import os
from django.conf import settings


class JsonImportForm(forms.Form):
    json_file = forms.FileField(
        label="Import from JSON file",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        required=True
    )

class LogUploadForm(forms.Form):
    event_log = forms.FileField(
        label="Upload new events log",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

class DiscoveryForm(forms.Form):
    OPTIMIZATION_METHODS = [
        ('NSGAII', 'NSGAII'),
        ('NSGAIII', 'NSGAIII'),
        ('SPEA2', 'SPEA2'),
        ('PARALLEL - NSGAII', 'Parallel NSGAII'),
        ('PARALLEL - NSGAIII', 'Parallel NSGAIII'),
        ('PARALLEL - SPEA2', 'Parallel SPEA2'),
    ]
    
    MINER_TYPES = [
        ('heuristic', 'Heuristic Miner'),
        ('inductive', 'Inductive Miner'),
        ('alpha', 'Alpha Miner'),
    ]
    
    METRICS = [
        ('basic', 'Basic metrics'),
        ('basic_useful_simple', 'Basic Useful Metrics'),
        ('quality', 'Quality metrics'),
        ('distance_quality', 'Distance Quality Metrics'),
    ]
    
    execution_name = forms.CharField(
        label="Nombre", 
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    optimization_method = forms.ChoiceField(
        choices=[('', '')] + OPTIMIZATION_METHODS,
        label="Método de Optimización",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    miner_type = forms.ChoiceField(
        choices=MINER_TYPES, 
        label="Tipo de Minero",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    event_log = forms.ChoiceField(
        label="Log de Eventos",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    evaluation_metrics = forms.ChoiceField(
        choices=METRICS, 
        label="Métricas de Evaluación",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    constraint_metrics = forms.CharField(
        label="Restricciones", 
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control', 
                                      'placeholder': '(x1 > 1) ∧ (x2 < 2) ∧ (x1 + x2 ≤ 10)'}),
        required=False,
    )

    parallel_cores = forms.IntegerField(
        required=False,
        label="Cores en paralelo (0 = máximo disponible)",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=0,
        min_value=0,
    )

    ## Hiperparametros

    population_size = forms.IntegerField(
        required=False,
        label="Tamaño de Población",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    offspring_population_size = forms.IntegerField(
        required=False,
        label="Tamaño de Población de Descendencia",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    mutation_type = forms.ChoiceField(
        required=False,
        choices=[('polynomial', 'Polynomial Mutation'),
                 ('random', 'Random Mutation'),
                 ('uniform', 'Uniform Mutation'),
                 ('non_uniform', 'Non-Uniform Mutation'),],
        label="Tipo de Mutación",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    mutation_probability = forms.FloatField(
        required=False,
        label="Probabilidad de Mutación",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    crossover_type = forms.ChoiceField(
        required=False,
        choices=[('pmx', 'PMX Crossover'), ('sbx', 'SBX Crossover')],
        label="Tipo de Crossover",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    crossover_probability = forms.FloatField(
        required=False,
        label="Probabilidad de Crossover",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    max_evaluations = forms.IntegerField(
        required=False,
        label="Número de Evaluaciones",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        log_files = [(f, f) for f in os.listdir(settings.LOGS_FOLDER) if os.path.isfile(os.path.join(settings.LOGS_FOLDER, f))]
        self.fields['event_log'].choices = log_files

    def clean(self):
        cleaned_data = super().clean()
        optimization_method = cleaned_data.get("optimization_method")

        if optimization_method in ['NSGAII', 'SPEA2', 'PARALLEL - NSGAII', 'PARALLEL - SPEA2']:
            if not cleaned_data.get('offspring_population_size'):
                self.add_error('offspring_population_size', 'campo obligatorio')

        if optimization_method in ['NSGAII', 'NSGAIII', 'SPEA2', 'PARALLEL - NSGAII', 'PARALLEL - NSGAIII', 'PARALLEL - SPEA2']:
            if not cleaned_data.get('mutation_type'):
                self.add_error('mutation_type', 'campo obligatorio')
            if not cleaned_data.get('mutation_probability'):
                self.add_error('mutation_probability', 'campo obligatorio')
            if not cleaned_data.get('crossover_type'):
                self.add_error('crossover_type', 'campo obligatorio')
            if not cleaned_data.get('crossover_probability'):
                self.add_error('crossover_probability', 'campo obligatorio')
            if not cleaned_data.get('max_evaluations'):
                self.add_error('max_evaluations', 'campo obligatorio')

        cores = cleaned_data.get('parallel_cores')
        if cores is not None and cores < 0:
            self.add_error('parallel_cores', 'El número de cores debe ser 0 o mayor.')

        return cleaned_data
    

class DiscFormMetrics(forms.Form):

    METRICAS_CHOICES = [
    ("places", "Nº of places"),
    ("transitions", "Nº of transitions"),
    ("arcs", "Nº of arcs"),
    ("cycl_complx", "Cyclomatic complexity"),
    ("ratio", "ratio states/transition"),
    ("joins", "Nº of joins"),
    ("splits", "Nº of splits"),
    ("fitness", "Model fitness"),
    ("precision", "Model precision"),
    ("simplicity", "Model simplicity"),
    ("generalisation", "Model generalisation"),
    ("fpd", "fitness-precission distance"),
    ("sgd", "simplicity-generalisation distance"),
    ]
    
    execution_name = forms.CharField(
        label="Execution Name", 
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    event_log = forms.ChoiceField(
        label="Events log",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    evaluation_metrics = forms.MultipleChoiceField(
        choices=METRICAS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Select metrics to optimize"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        log_files = [(f, f) for f in os.listdir(settings.LOGS_FOLDER) if os.path.isfile(os.path.join(settings.LOGS_FOLDER, f))]
        self.fields['event_log'].choices = log_files

class DiscFormConstraints(forms.Form):
    constraint_metrics = forms.CharField(
        label="Constraints", 
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control', 
                                      'placeholder': '(fitness > 0.9) ∧ (precision < 0.9) ∧ (n_arcs ≤ 10)'}),
        required=False,
    )

class DiscFormMiner(forms.Form):
    MINER_TYPES = [
        ('heuristic', 'Heuristic Miner'),
        ('inductive', 'Inductive Miner'),
        ('alpha', 'Alpha Miner'),
    ]

    miner_type = forms.ChoiceField(
        choices=MINER_TYPES, 
        label="Discovery algorithm",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class DiscFormOptimizer(forms.Form):

    OPTIMIZATION_METHODS = [
        ('NSGAII', 'NSGAII'),
        ('NSGAIII', 'NSGAIII'),
        ('SPEA2', 'SPEA2'),
        ('PARALLEL - NSGAII', 'Parallel NSGAII'),
        ('PARALLEL - NSGAIII', 'Parallel NSGAIII'),
        ('PARALLEL - SPEA2', 'Parallel SPEA2'),
    ]

    def clean(self):
        cleaned_data = super().clean()
        optimization_method = cleaned_data.get("optimization_method")

        if optimization_method in ['NSGAII', 'SPEA2', 'PARALLEL - NSGAII', 'PARALLEL - SPEA2']:
            if not cleaned_data.get('offspring_population_size'):
                self.add_error('offspring_population_size', 'campo obligatorio')

        if optimization_method in ['NSGAII', 'NSGAIII', 'SPEA2', 'PARALLEL - NSGAII', 'PARALLEL - NSGAIII', 'PARALLEL - SPEA2']:
            if not cleaned_data.get('mutation_type'):
                self.add_error('mutation_type', 'campo obligatorio')
            if not cleaned_data.get('mutation_probability'):
                self.add_error('mutation_probability', 'campo obligatorio')
            if not cleaned_data.get('crossover_type'):
                self.add_error('crossover_type', 'campo obligatorio')
            if not cleaned_data.get('crossover_probability'):
                self.add_error('crossover_probability', 'campo obligatorio')
            if not cleaned_data.get('max_evaluations'):
                self.add_error('max_evaluations', 'campo obligatorio')

        cores = cleaned_data.get('parallel_cores')
        if cores is not None and cores < 0:
            self.add_error('parallel_cores', 'Number of cores must be 0 or greater.')

        return cleaned_data
    
    optimization_method = forms.ChoiceField(
        choices=[('', '')] + OPTIMIZATION_METHODS,
        label="Optimization Algorithm",
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial=OPTIMIZATION_METHODS[3][0],
    )

    parallel_cores = forms.IntegerField(
        required=False,
        label="Parallel cores (0 = use all logical cores)",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=0,
        min_value=0,
    )
    
    ## Hiperparametros

    population_size = forms.IntegerField(
        required=False,
        label="Population Size",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=100,
    )
    offspring_population_size = forms.IntegerField(
        required=False,
        label="Offspring Population Size",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=100,
    )
    mutation_type = forms.ChoiceField(
        required=False,
        choices=[('polynomial', 'Polynomial Mutation'),
                 ('random', 'Random Mutation'),
                 ('uniform', 'Uniform Mutation'),
                 ('non_uniform', 'Non-Uniform Mutation'),],
        label="Mutation Type",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    mutation_probability = forms.FloatField(
        required=False,
        label="Mutation Probability",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=0.17,
    )
    crossover_type = forms.ChoiceField(
        required=False,
        choices=[('sbx', 'SBX Crossover'), ('pmx', 'PMX Crossover')],
        label="Crossover type",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    crossover_probability = forms.FloatField(
        required=False,
        label="Crossover Probability",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),

        initial=0.2,
    )
    max_evaluations = forms.IntegerField(
        required=False,
        label="Maximum Evaluations",
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        initial=100
    )
