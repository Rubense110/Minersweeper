from django.urls import path

from . import views
from django.conf import settings
from django.conf.urls.static import static
from .views import DiscoveryWizard
from .forms import DiscFormConstraints, DiscFormMetrics, DiscFormMiner, DiscFormOptimizer


urlpatterns = [
    path('', views.intro),
    path('intro/', views.intro, name = 'intro'),
    #path('discovery/', views.discovery, name = "discovery"),
    path("discovery/", DiscoveryWizard.as_view(), name="discovery"),
    path('history/', views.history, name = "history"),
    path('manual/', views.manual, name = "manual"),
    path('discovery/result/<int:execution_id>/', views.discovery_result, name='discovery_result'),
    path('solutions/', views.solutions, name='solutions'),
    path('solutions/<int:execution_id>/', views.solutions, name='solutions'),
    path('solution/<int:solution_id>/', views.solution_details, name='solution_details'),
    path('select-model/<int:execution_id>/', views.select_model, name='select_model'),
    path('execution/<int:execution_id>/download/', views.get_execution_data, name='get_execution_data'),
    path('logs/', views.logs, name='logs'),
    path('json-import/', views.json_import, name='json_import'),
    path('delete_execution/<int:execution_id>/', views.delete_execution, name='delete_execution'),
    path('solutions/<int:solution_id>/comparar/<int:petri_1_id>-<int:petri_2_id>/', views.compare_nets, name='compare_nets'),
]+ static(settings.PARETO_URL, document_root=settings.PARETO_PATH) # para acceder a las imagenes de pareto desde el navegador (arreglo ruta relativa)

