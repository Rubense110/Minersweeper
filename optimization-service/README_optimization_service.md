# Optimization Service (Python)

Servicio Python para optimizar un pipeline de descubrimiento de procesos con **NSGA-III (jMetalPy)**.
El pipeline optimizado tiene tres bloques:

1. Preprocesado (metodo + parametros)
2. Minero (familia + variante)
3. Parametros del minero (con gating condicional cuando aplica)

La evaluacion real del pipeline se delega a un servicio Java/ProM via HTTP.
Cada evaluacion queda asociada a un `experiment_id` y devuelve `evaluation_id`, para recuperar luego el PNML del frente no dominado sin re-ejecutar discovery.

## Arquitectura

- `process_miner.py`
  - Orquestador de alto nivel (`OptimizedProcessMiner`).
  - Construye espacio, problema y optimizador, ejecuta y expone frente no dominado.
- `pipeline_space.py`
  - Define el espacio de decision plano para jMetalPy.
  - Decodifica un vector de decision a un `pipeline` interpretable.
- `problem.py`
  - Implementa `FloatProblem` para jMetalPy.
  - Evalua cada solucion llamando al evaluador externo (servicio Java).
  - Convierte maximizacion de metricas a minimizacion negando objetivos.
- `optimizer.py`
  - Wrapper de NSGA-III.
  - Configura operadores SBX + Polynomial Mutation + direcciones de referencia.
  - Soporta evaluacion secuencial o en hilos (`n_workers`).
- `java_service_client.py`
  - Cliente HTTP para evaluar (`POST /pipeline`) y recuperar artefactos (`POST /artifacts/bulk`).

## API HTTP (servicio de optimizacion)

Archivo: `optimization-service/api.py`

El servicio expone jobs asincronos en memoria (sin BBDD por ahora):

- `GET /health`
- `GET /optimizations`
- `POST /optimizations`
- `GET /optimizations/:job_id`
- `GET /optimizations/:job_id/progress`
- `GET /optimizations/:job_id/events` (SSE)
- `GET /optimizations/:job_id/solutions?scope=pareto|all`
- `GET /optimizations/:job_id/artifacts?scope=pareto|all&include_pnml=true|false`

### Crear ejecucion

`POST /optimizations`

Body minimo:

```json
{
  "execution_name": "run_001",
  "log_path": "/data/logs/BPI_Challenge_2013_open_problems.xes"
}
```

Opcionales:
- `service_url` (si no, usa `JAVA_SERVICE_URL`)
- `metrics`
- `excluded_miners`
- `max_evaluations`
- `population_size`
- `n_partitions`
- `n_workers`

Respuesta:
- `202 Accepted` con `job_id` y estado `queued`.

### Recuperar resultados

1. Estado del job:
- `GET /optimizations/:job_id`
- `GET /optimizations/:job_id/progress`

2. Soluciones:
- `GET /optimizations/:job_id/solutions?scope=all`
- `GET /optimizations/:job_id/solutions?scope=pareto`

Cada solucion incluye:
- `pipeline`
- `metrics`
- `evaluation_id`
- `objectives`
- `variables`
- `is_pareto`

3. Artefactos PNML:
- `GET /optimizations/:job_id/artifacts?scope=pareto&include_pnml=true`

Internamente usa los `evaluation_id` del job para pedir `POST /artifacts/bulk` al servicio Java.

### Streaming de estado (SSE)

Para evitar polling agresivo, el servicio expone:

- `GET /optimizations/:job_id/events`

`Content-Type: text/event-stream`

Eventos emitidos:
- `status_changed`: cambios de estado (`queued`, `running`, `completed`, `failed`)
- `progress`: avance de evaluaciones (`evaluations_done`, `max_evaluations`, `percentage`)
- `result_ready`: resumen final al completar
- `error`: detalle al fallar

## Flujo end-to-end

1. Se construye `PipelineSearchSpace` con catalogos de preprocesado y mineros.
2. NSGA-III genera un vector float candidato.
3. `PipelineSearchSpace.decode(...)` lo transforma en:
   - `preprocessing: {key, method, variant, parameters}`
   - `miner: {key, family, variant, parameters}`
4. `PipelineOptimizationProblem.evaluate(...)` envia ese pipeline al servicio Java.
5. El servicio devuelve metricas + identificadores (`evaluation_id`, `fingerprint`).
6. El problema las pasa a objetivos de minimizacion para jMetalPy.
7. Se obtiene conjunto final y frente no dominado.
8. Se recuperan los PNML del no dominado final por `evaluation_id` sin reevaluar.

## Contrato HTTP con el servicio Java

### Request

- Metodo: `POST`
- Endpoint por defecto: `/pipeline`
- Body JSON:

```json
{
  "experiment_id": "run_001",
  "log_path": "path/al/log.xes",
  "pipeline": {
    "preprocessing": {
      "key": "matrix_filter",
      "method": "Matrix Filtering",
      "variant": "Conditional Probabilities (MF)",
      "parameters": {
        "probability_of_removal_mf": 0.14,
        "subsequence_length_mf": 2
      }
    },
    "miner": {
      "key": "inductive",
      "family": "inductive",
      "variant": "Inductive Miner - infrequent (IMf)",
      "parameters": {
        "noise_threshold": 0.21,
        "is_debug": false,
        "use_multithreading": true
      }
    }
  },
  "metrics": ["fitness", "precision_alignment", "simplicity_structural", "generalization_alignment"],
  "excluded_miners": ["split", "ilp"]
}
```

### Response esperada:

```json
{
  "experiment_id": "run_001",
  "evaluation_id": "1739190000000-42",
  "fingerprint": "matrix_filter|...|inductive|...",
  "metrics": {
    "fitness": 0.91,
    "precision_alignment": 0.73,
    "simplicity_structural": 0.52,
    "generalization_alignment": 0.64
  }
}
```

Notas:
- Los nombres de metricas deben enviarse exactamente como en el catalogo del servicio Java (sin aliases).
- Si falta alguna metrica pedida, se lanza `KeyError`.

### Recuperacion de artefactos PNML:

`POST /artifacts/bulk`

```json
{
  "experiment_id": "run_001",
  "evaluation_ids": ["1739190000000-42", "1739190000100-43"],
  "include_pnml": true
}
```

La respuesta devuelve `artifacts[]` con `evaluation_id`, `metrics`, `pipeline` y `pnml`.

## Espacio de decision y gating

`PipelineSearchSpace` usa `DecisionVariable` con:

- `key`: identificador estable del gen
- `ptype`: `float | int | bool | enum`
- `min_val`, `max_val`: limites numericos para jMetalPy
- `choices`: opciones para enum

Cada solucion contiene genes para todo el catalogo, pero al decodificar solo se activa:

- El preprocesado elegido y sus parametros activos
- El minero elegido, variante elegida y parametros activos de esa variante

### Gating especial en Hybrid ILP

En `hybrid_ilp`, los parametros activos dependen de `lp_filter`:

- `None`: no incluye umbrales de filtro
- `Sequence Encoding Filter`: activa `sequence_encoding_cutoff_level`
- `Slack Variable Filter`: activa `slack_variable_filter_threshold`

## Catalogo de preprocesados

Definido en `parameters/preprocessing/`:

- `matrix_filter`
  - Parametros: `probability_of_removal_mf`, `subsequence_length_mf`
- `repair_log_filter`
  - Parametros: `probability_of_removal_rl`, `subsequence_length_rl`
- `variant_filter`
  - Parametro: `keep_threshold_vf`
- `projection_filter`
  - Parametro: `keep_threshold_p`

## Catalogo de mineros

Definido en `parameters/miners/`:

- `alpha`
  - Variantes: `classic`, `plus`, `plus_plus`, `sharp`, `robust`, `dollar`
- `inductive`
  - Variantes: `im`, `imf`, `imlc`, `imflc`, `impt`, `imfpt`, `imfpta`
- `heuristics`
  - Variantes: `hm`, `fhm`
- `ilp`
  - Variantes: `petri_net`, `petri_net_variable_fitness`
- `hybrid_ilp`
  - Variante: `hybrid`
  - Gating por `lp_filter`
- `split`
  - Incluido en catalogo, pero excluido por defecto en ejecucion (`excluded_miners=("split", "ilp")`).

## Configuracion de optimizacion (NSGA-III)

Parametros relevantes en `discover(...)`:

- `max_evaluations`: tope de evaluaciones
- `population_size`: tamano de poblacion
- `n_partitions`: particiones para reference directions
- `n_workers`: paralelismo de evaluacion

Reglas actuales:

- Si `population_size` no se indica, se usa el numero de reference directions.
- Si `n_partitions` no se indica:
  - `8` para 4 o mas objetivos
  - `12` para menos de 4 objetivos
- `n_workers=1`: `SequentialEvaluator`
- `n_workers>1`: `ThreadPoolEvaluator` (IO-bound friendly)

## Paralelismo y servicio Java

El lado Python ya paraleliza evaluaciones cuando `n_workers > 1`.
Para escalar de verdad, el servicio Java debe aceptar peticiones concurrentes y procesarlas sin bloquearse globalmente.
No es obligatorio usar asincronia explicita en Python para esto porque el paralelismo se resuelve con hilos + HTTP.

## Uso rapido

```python
from process_miner import OptimizedProcessMiner

miner = OptimizedProcessMiner(
    execution_name="run_001",
    log="/data/log.xes",
    service_url="http://localhost:7070",
)

miner.discover(
    max_evaluations=200,
    population_size=92,
    n_partitions=12,
    n_workers=4,
)

pipelines = miner.get_non_dominated_pipelines()
metrics = miner.get_non_dominated_metrics()
evaluation_ids = miner.get_non_dominated_evaluation_ids()
artifacts = miner.fetch_non_dominated_artifacts(include_pnml=True)
```

## Generar reporte por ejecucion (`run_id`)

Script incluido:
- `optimization-service/scripts/generate_run_report.py`

Genera:
- `reports/<run_id>_evaluations_time_desc.json`
- `reports/<run_id>_evaluations_time_desc.csv`

Fuente por defecto (host local):
- `/tmp/minersweeper-artifacts/<run_id>/*.json`

Ejemplo desde artefactos locales:

```bash
cd Minersweeper
venv/bin/python optimization-service/scripts/generate_run_report.py run_1770747769987
```

Ejemplo leyendo directo del contenedor `prom_service`:

```bash
cd Minersweeper
venv/bin/python optimization-service/scripts/generate_run_report.py run_1770747769987 --container prom_service
```

Opciones utiles:
- `--output-dir`: carpeta de salida (default: `optimization-service/reports`)
- `--artifacts-root`: raiz de artefactos en host (default: `/tmp/minersweeper-artifacts`)
- `--input-dir`: carpeta concreta con metadata `*.json` (si quieres controlar origen manualmente)
- `--top`: tamano del bloque `top_20` (default: `20`)

## Tests

Desde raiz del repo:

```bash
venv/bin/python -m unittest discover -s optimization-service/tests -p "test_*.py" -v
```

Cobertura actual de tests:

- Espacio de decision y decode
- Gating de Hybrid ILP
- Problema y cache de evaluaciones
- Cliente Java y parseo de metricas
- Configuracion del optimizador y evaluador paralelo
- Orquestacion en `OptimizedProcessMiner`

## Estado actual

El servicio Python ya maneja trazabilidad por evaluacion (`evaluation_id`) y recuperacion de PNML del no dominado final, sin necesidad de re-ejecutar discovery.

## Base de datos (propuesta actual)

Se usara una unica BBDD en `optimization_service` para persistir resultados de experimentos.
La persistencia se realiza al finalizar cada experimento.

### Tabla `Experiment`

- `ExperimentID` (PK)
- `ExperimentName`
- `StartAt`
- `EndAt`
- `Max_evals`
- `Pop_size`
- `Miners` (catalogo de mineros utilizado)
- `Preprocessing` (catalogo de preprocesados utilizado)
- `log_path`
- `metrics` (metricas utilizadas, en orden)
- `workers`

### Tabla `Solution`

- `SolutionID` (PK)
- `ExperimentID` (FK -> `Experiment.ExperimentID`)
- `variables`
- `objectives`
- `pipeline`
- `is_pareto`
- `places`
- `transitions`
- `arcs`

### Contrato de `metrics` y `objectives`

- `Experiment.metrics` define el orden oficial de metricas del experimento.
- `Solution.objectives[i]` corresponde a `Experiment.metrics[i]`.
- `objectives` se almacenan en el espacio del optimizador (si una metrica se maximiza, su objetivo se guarda negado).
- Para visualizacion de negocio, usar `metrics` o deshacer el signo de `objectives` cuando aplique.

### Notas de modelado recomendadas

- Guardar `variables`, `objectives`, `pipeline`, `places`, `transitions` y `arcs` como JSON/JSONB.
- Guardar `StartAt` y `EndAt` con zona horaria.
- Indices recomendados:
  - `Solution(ExperimentID)`
  - `Solution(ExperimentID, is_pareto)`
