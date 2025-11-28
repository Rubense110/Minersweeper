from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Count, Q
import traceback
from .models import DSolution, Execution  
import os
from .forms import DiscoveryForm, LogUploadForm, JsonImportForm, DiscFormConstraints, DiscFormMetrics, DiscFormMiner, DiscFormOptimizer
from .utils.discovery import *
from .pm_py import  config
from .utils.petri import  get_heatmap_data
from .utils.hiperparameters import get_hipparam_dict
import io
import csv
import json
import ast
import zipfile
from django.contrib import messages
from .utils.JSON_importer import import_from_json
import random
import time
from formtools.wizard.views import SessionWizardView
from django.shortcuts import render, redirect
from django.conf import settings
import os, traceback
from .forms import DiscFormMetrics, DiscFormMiner, DiscFormOptimizer
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import ast
import io
import numpy as np
from django.shortcuts import render, get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pymoo.decomposition.weighted_sum import WeightedSum
from pm4py.visualization.petri_net import visualizer as pn_visualizer
from pm4py.objects.petri_net.importer import importer as pnml_importer
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.visualization.petri_net import visualizer as pn_vis

def history(request):
    query = request.GET.get('query', '')
    filter_option = request.GET.get('filter_option', 'no_filter')

    executions = Execution.objects.all().annotate(
        pareto_size=Count('dsolution__id', filter=Q(dsolution__is_pareto=True))
    )

    if query:
        if filter_option == 'name':
            executions = executions.filter(name__icontains=query)
        elif filter_option == 'miner':
            executions = executions.filter(miner__icontains=query)
        elif filter_option == 'optimizer':
            executions = executions.filter(optimizer__name__icontains=query)
        elif filter_option == 'log':
            executions = executions.filter(path_events_log__icontains=query)
        elif filter_option == 'metrics':
            executions = executions.filter(metrics__icontains=query)
        elif filter_option == 'id':
            try:
                executions = executions.filter(id=query)
            except ValueError:
                pass 

    paginator = Paginator(executions, 10)
    page_number = request.GET.get('page')
    executions_to_show = paginator.get_page(page_number)

    return render(request, 'history.html', 
                  {'executions': executions_to_show, 
                   'query': query, 'filter_option': filter_option})

def delete_execution(request, execution_id):
    execution = get_object_or_404(Execution, id=execution_id)
    optimizer = Optimizer.objects.filter(execution=execution).first()
    if optimizer:
        optimizer.delete()
    DSolution.objects.filter(execution=execution).delete()
    execution.delete()
    messages.info(request, f'Eliminada la ejecución {execution.name}')
    return redirect('history') 

def intro(request):
    return render(request, 'intro.html')

def manual(request):
    return render(request, 'manual.html')

@method_decorator(csrf_exempt, name='dispatch')
class DiscoveryWizard(SessionWizardView):
    form_list = [
        ("metrics", DiscFormMetrics),
        #("constraints", DiscFormConstraints),
        ("miner", DiscFormMiner),
        ("optimizer", DiscFormOptimizer),
    ]
    template_name = "discovery.html"

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context['log_files'] = os.listdir(settings.LOGS_FOLDER) if os.path.exists(settings.LOGS_FOLDER) else []
        return context

    def done(self, form_list, **kwargs):
        try:
            time_init_form = time.time()
            form_data = {field.name: field.value() for form in form_list for field in form}
            execution_name = form_data['execution_name']
            optimization_method = form_data['optimization_method']
            selected_log = form_data['event_log']
            miner_name = form_data['miner_type']
            evaluation_metrics = form_data['evaluation_metrics']
            
            opt_parameters_dict = get_hipparam_dict(form_data)
            logpath = os.path.join(settings.LOGS_FOLDER, selected_log)
            time_fin_form = time.time()

            time_init_disc = time.time()
            execution_id = discover(
                execution_name=execution_name,
                optimization_method=optimization_method,
                opt_parameters_dict=opt_parameters_dict,
                miner_name=miner_name, 
                evaluation_metrics=evaluation_metrics, 
                logpath=logpath,
                form_data=form_data,
            )
            time_fin_disc = time.time()

            print(f"{datetime.now().strftime('[%d/%b/%Y %H:%M:%S]')} tiempo discover    - {time_fin_disc - time_init_disc}")
            print(f"#################################################################################\n")
            return redirect('discovery_result', execution_id)
        
        except Exception as e:
            print(f"Error durante el descubrimiento: {e}")
            print(traceback.format_exc())
            return render(self.request, 'discovery_error.html', {
                'error_message': "Error en el proceso de descubrimiento. Por favor, inténtelo de nuevo.",
                'exception': e
            })


def discovery_result(request, execution_id):
    
    execution = Execution.objects.get(pk=execution_id)
    optimizer = execution.optimizer

    execution_name = execution.name
    miner_type = execution.miner
    evaluation_metrics = execution.metrics
    events_log = execution.path_events_log
    runtime = execution.runtime
    optimization_method = optimizer.name
    optimization_hipparams = optimizer.hip_params
    constraints = execution.constraints
    
    return render(request, 'discovery_results.html', {
        'execution_name': execution_name,  
        'events_log': events_log,  
        'miner_type': miner_type,  
        'evaluation_metrics': evaluation_metrics,  
        'runtime': runtime,  
        'optimization_method': optimization_method,  
        'optimization_hipparams': optimization_hipparams,
        'execution_id': execution.id, 
        'constraints' : constraints
    })

def solutions(request, execution_id):
    execution = get_object_or_404(Execution, pk=execution_id)
    constraints_labels = execution.constraints.split(',')

    # --- Query base ---
    dsolutions_qs = DSolution.objects.filter(execution=execution)

    # --- Filtro por frente de Pareto (sin recomputar) ---
    current_filter = request.GET.get('filter')
    if current_filter == 'pareto':
        dsolutions_qs = dsolutions_qs.filter(is_pareto=True)

    # Paginación (tabla)
    paginator = Paginator(dsolutions_qs, 10)
    page_number = request.GET.get('page')
    solutions_to_show = paginator.get_page(page_number)

    # Etiquetas de objetivos (en el mismo orden que guardaste las objectives)
    metrics_labels = ast.literal_eval(execution.metrics)  # p.ej. ["fitness","precision","generalization","simplicity"]

    # --- Datos para D3: usamos TODO lo filtrado (no solo la página) ---
    pc_data = []
    for s in dsolutions_qs:
        label = getattr(getattr(s, 'petri', None), 'id_on_exec', s.id)
        pc_data.append({
            "id": s.id,
            "label": label,
            "values": [abs(float(v)) for v in s.objectives],
        })

    # Rango Y global del gráfico
    if pc_data:
        all_vals = [v for row in pc_data for v in row["values"] if v is not None]
        y_min = min(all_vals)
        y_max = max(all_vals)
    else:
        y_min, y_max = 0.0, 1.0

    # (Puedes borrar lo del heatmap si ya no lo usas)
    heatmap_data = get_heatmap_data(execution_id)
    heatmap_data = json.loads(heatmap_data)
    heatmap = heatmap_data['heatmap']
    heatmap_indexes = heatmap_data['index_mapping']

    return render(request, 'solutions.html', {
        'execution': execution,
        'constraints_labels': constraints_labels,
        'solutions': solutions_to_show,
        'metrics_labels': metrics_labels,
        'miner_params_names': config.parameter_mapping[execution.miner].get_param_names(),
        'ids': list(range(len(dsolutions_qs))),
        'pareto_image_path': None,
        'heatmap_data': json.dumps(heatmap),
        'heatmap_indexes': json.dumps(heatmap_indexes),

        # nuevo para D3
        'pc_data': json.dumps(pc_data),
        'pc_labels': json.dumps(metrics_labels),
        'pc_y_min': y_min,
        'pc_y_max': y_max,
        'current_filter': current_filter,
    })


 
def solution_details(request, solution_id):
    solution = get_object_or_404(DSolution, id=solution_id)
    petri = solution.petri
    
    execution = solution.execution
    evaluation_metrics = execution.metrics

    miner_params = config.parameter_mapping[execution.miner]
    miner_params_names = miner_params.get_param_names()

    metrics_labels = ast.literal_eval(evaluation_metrics) 

    return render(request, 'solution_details.html', {
        'solution': solution,
        'execution': execution,
        'metrics_labels': metrics_labels,
        'miner_params_names': miner_params_names,
        "places": petri.places,  
        "transitions": petri.transitions, 
        "arcs": petri.arcs, 
    })

def get_execution_data(_,execution_id):

    execution = get_object_or_404(Execution, pk=execution_id)
    evaluation_metrics = execution.metrics
    solutions = DSolution.objects.filter(execution=execution)
    optimizer = execution.optimizer

    miner_params = config.parameter_mapping[execution.miner]
    miner_params_names = miner_params.get_param_names()

    metrics_labels = ast.literal_eval(evaluation_metrics) 
    

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip:
        csv_solution_variables = io.StringIO()
        writer = csv.writer(csv_solution_variables)
        writer.writerow(miner_params_names)
        for sol in solutions:
            writer.writerow(sol.variables)
        zip.writestr('sol_variables.csv', csv_solution_variables.getvalue())

        csv_solution_objectives = io.StringIO()
        writer = csv.writer(csv_solution_objectives)
        writer.writerow(metrics_labels)
        for sol in solutions:
            writer.writerow(sol.objectives)
        zip.writestr('sol_objectives.csv', csv_solution_objectives.getvalue())

        execution_data = {
            'execution': {
                'name': execution.name,
                'path_events_log': execution.path_events_log,
                'metrics': execution.metrics,
                'miner': execution.miner,
            },
            'optimizer': {
                'name': optimizer.name,
                'hip_params': optimizer.hip_params 
            }
        }
        execution_json = json.dumps(execution_data, indent=4)

        zip.writestr('execution_data.json', execution_json)

    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=execution_{execution_id}_{execution.name}.zip'
    
    return response

def logs(request):
    log_dir = settings.LOGS_FOLDER 
    if request.method == 'POST':
        log_upload_form = LogUploadForm(request.POST, request.FILES)
        if log_upload_form.is_valid():
            event_log = request.FILES['event_log']
            try:
                store_log(event_log)
                return redirect('logs')
            except Exception as e:
                messages.warning(request, 'El archivo subido no es un log de eventos')
                return redirect('logs')
    
        log_to_delete = request.POST.get('log_to_delete')
        if log_to_delete:
            log_path = os.path.join(log_dir, log_to_delete)
            if os.path.exists(log_path):
                os.remove(log_path)
                log_name = log_path.split('/')[-1]
                messages.info(request, f'Eliminado el log {log_name}')
                return redirect('logs') 
    else:
        log_upload_form = LogUploadForm()

    logs = os.listdir(log_dir) if os.path.exists(log_dir) else []

    return render(request, 'logs.html', {
        'log_upload_form': log_upload_form,
        'logs': logs
    })

def json_import(request):
    if request.method == 'POST':
        form = JsonImportForm(request.POST, request.FILES)
        if form.is_valid():
            json_file = form.cleaned_data['json_file']
            try:
                json_data = json.load(json_file)
                try:
                    POST_form_data = import_from_json(json_data)
                except Exception as e:
                    print(f"Error durante al importar JSON: {e}")
                    print(traceback.format_exc())

                    return render(request, 'discovery_error.html', {
                        'error_message': "Ha ocurrido un error importanto el fichero JSON."
                    })
                
                return render(request, 'import_json_redirect.html', {'post_data': POST_form_data})
            except:
                messages.warning(request, 'El archivo subido no es un JSON válido.')
    else:
        form = JsonImportForm()

    return render(request, 'json_import.html', {'form': form})

def compare_nets(request, solution_id, petri_1_id, petri_2_id):
    """
    solution_id should be execution_id but it too much trouble to change it
    now hahaha
    """
    petri_1 = get_object_or_404(Petri, execution=solution_id, id_on_exec=petri_1_id)
    petri_2 = get_object_or_404(Petri, execution=solution_id, id_on_exec=petri_2_id)

    return render(request, 'comparison.html', {
        "execution_id" : solution_id,

        "petri_1_index" : petri_1_id,
        "places_1": petri_1.places,  
        "transitions_1": petri_1.transitions, 
        "arcs_1": petri_1.arcs, 

        "petri_2_index" : petri_2_id,
        "places_2": petri_2.places,  
        "transitions_2": petri_2.transitions, 
        "arcs_2": petri_2.arcs, 
        
    })


@require_http_methods(["GET", "POST"])
def select_model(request, execution_id):
    execution = get_object_or_404(Execution, id=execution_id)

    # 1. Obtener métricas como lista (string → lista Python)
    try:
        metrics_list = ast.literal_eval(execution.metrics)
    except Exception:
        metrics_list = []

    # 2. Inicializar valores de sliders
    slider_values = {m: 50 for m in metrics_list}
    selected_model_id = None
    rendered_model_html = None

    if request.method == "POST":
        # a) Leer los pesos enviados
        for m in metrics_list:
            try:
                slider_values[m] = int(request.POST.get(f"weight_{m}", 50))
            except ValueError:
                slider_values[m] = 50

        # b) Normalizar pesos
        weights = np.array(list(slider_values.values()), dtype=float)
        if np.sum(weights) > 0:
            weights /= np.sum(weights)
        else:
            weights = np.ones(len(weights)) / len(weights)

        # c) Obtener soluciones asociadas a la ejecución
        solutions = DSolution.objects.filter(execution=execution)

        if not solutions.exists():
            context = {
                "execution_id": execution_id,
                "metrics_list": metrics_list,
                "slider_values": slider_values,
                "error": "No hay soluciones asociadas a esta ejecución.",
            }
            return render(request, "select_model.html", context)

        # d) Construir matriz de objetivos
        objs = []
        valid_solutions = []
        for sol in solutions:
            arr = np.array(sol.objectives)
            if len(arr) == len(metrics_list):
                objs.append(arr)
                valid_solutions.append(sol)

        objs = np.array(objs)
        if len(objs) == 0:
            context = {
                "execution_id": execution_id,
                "metrics_list": metrics_list,
                "slider_values": slider_values,
                "error": "No se pudieron leer los objetivos de las soluciones.",
            }
            return render(request, "select_model.html", context)

        # e) Seleccionar la mejor solución con WeightedSum
        decomp = WeightedSum()
        scalarized = decomp.do(objs, weights)  # menor = mejor
        best_idx = np.argmin(scalarized)
        best_solution = valid_solutions[best_idx]
        selected_model_id = best_solution.id

        # f) Renderizar la red de Petri asociada
        petri = best_solution.petri

        from pm4py.objects.petri_net.obj import PetriNet, Marking
        from pm4py.visualization.petri_net import visualizer as pn_vis
        import base64, os

        net = PetriNet("DiscoveredNet")

        # Lugares
        places_map = {}
        for p in ast.literal_eval(petri.places):
            place = PetriNet.Place(p)
            net.places.add(place)
            places_map[p] = place

        # Transiciones
        transitions_map = {}
        for t in ast.literal_eval(petri.transitions):
            tr = PetriNet.Transition(t, t)
            net.transitions.add(tr)
            transitions_map[t] = tr

        # Arcos
        for src, tgt in ast.literal_eval(petri.arcs):
            if src in places_map and tgt in transitions_map:
                arc_obj = PetriNet.Arc(places_map[src], transitions_map[tgt])
                net.arcs.add(arc_obj)
            elif src in transitions_map and tgt in places_map:
                arc_obj = PetriNet.Arc(transitions_map[src], places_map[tgt])
                net.arcs.add(arc_obj)
            else:
                # arco raro, lo ignoramos
                pass

        gviz = pn_vis.apply(net)

        img_path = f"/tmp/petri_{best_solution.id}.png"
        pn_vis.save(gviz, img_path)

        with open(img_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        # ESTA versión es la correcta. Mantén SOLO esta.
        rendered_model_html = (
            '<div style="max-height:500px; overflow:auto; border:1px solid #ddd; '
            'border-radius:6px; padding:8px;">'
            f'<img src="data:image/png;base64,{img_base64}" '
            'class="img-fluid" alt="Petri net model">'
            '</div>'
        )

        try:
            os.remove(img_path)
        except OSError:
            pass

    # =====================
    # CONTEXTO FINAL
    # =====================
    context = {
        "execution_id": execution_id,
        "metrics_list": metrics_list,
        "slider_values": slider_values,
        "selected_model_id": selected_model_id,
        "rendered_model_html": rendered_model_html,
    }

    return render(request, "select_model.html", context)
