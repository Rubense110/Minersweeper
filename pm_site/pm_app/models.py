from django.db import models
    
class Execution(models.Model):
    name = models.CharField(max_length=100, help_text='Nombre de la ejecución')
    runtime = models.DurationField(help_text='tiempo de ejecución')
    path_events_log = models.CharField(max_length=2048)
    metrics = models.CharField(max_length=100)
    miner = models.CharField(max_length=100)
    constraints = models.CharField(max_length=1000)

class Optimizer(models.Model):
    
    execution = models.OneToOneField(
        Execution,
        on_delete=models.CASCADE,
        primary_key=True
    )

    name = models.CharField(max_length=100)
    hip_params = models.JSONField()

class Petri(models.Model):
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE)
    places = models.TextField()
    transitions = models.TextField()
    arcs = models.TextField()
    is_pareto = models.BooleanField(default=False)
    id_on_exec = models.PositiveIntegerField()
    
class DSolution(models.Model):
    variables = models.JSONField()
    objectives = models.JSONField()
    constraints = models.JSONField()
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE)
    is_pareto = models.BooleanField(default=False)
    petri = models.OneToOneField(Petri, on_delete=models.CASCADE, related_name="solution")


class FrontSnapshot(models.Model):
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name="fronts")
    step = models.PositiveIntegerField(help_text="Índice de fichero FUN.x")
    evaluations = models.PositiveIntegerField(null=True, blank=True)
    objectives = models.JSONField(help_text="Vectores de objetivos del frente en ese paso")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("execution", "step")

