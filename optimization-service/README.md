# Optimization Service (Python)

Servicio Python para optimizar un pipeline de descubrimiento de procesos con **NSGA-III (jMetalPy)**.
El pipeline optimizado tiene tres bloques:

1. Preprocesado (metodo + parametros)
2. Minero (familia + variante)
3. Parametros del minero (con gating condicional cuando aplica)

La evaluacion real del pipeline se delega a un servicio Java/ProM via HTTP.

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
  - Cliente HTTP para el endpoint Java (`POST /pipeline`).

## Flujo end-to-end

1. Se construye `PipelineSearchSpace` con catalogos de preprocesado y mineros.
2. NSGA-III genera un vector float candidato.
3. `PipelineSearchSpace.decode(...)` lo transforma en:
   - `preprocessing: {key, method, variant, parameters}`
   - `miner: {key, family, variant, parameters}`
4. `PipelineOptimizationProblem.evaluate(...)` envia ese pipeline al servicio Java.
5. El servicio devuelve metricas (`fitness`, `precision`, `simplicity`, `generalisation`).
6. El problema las pasa a objetivos de minimizacion para jMetalPy.
7. Se obtiene conjunto final y frente no dominado.

## Contrato HTTP con el servicio Java

### Request

- Metodo: `POST`
- Endpoint por defecto: `/pipeline`
- Body JSON:

```json
{
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
  "metrics": ["fitness", "precision", "simplicity", "generalisation"]
}
```

### Response aceptada

Se aceptan dos formatos:

1. Plano:

```json
{
  "fitness": 0.91,
  "precision": 0.73,
  "simplicity": 0.52,
  "generalisation": 0.64
}
```

2. Envolviendo metricas:

```json
{
  "metrics": {
    "fitness": 0.91,
    "precision": 0.73,
    "simplicity": 0.52,
    "generalization": 0.64
  }
}
```

Notas:
- El cliente soporta alias `generalisation` <-> `generalization`.
- Si falta alguna metrica pedida, se lanza `KeyError`.

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
  - Incluido en catalogo, pero excluido por defecto en ejecucion (`excluded_miners=("split",)`).

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
    service_url="http://localhost:8080",
)

miner.discover(
    max_evaluations=200,
    population_size=92,
    n_partitions=12,
    n_workers=4,
)

pipelines = miner.get_non_dominated_pipelines()
metrics = miner.get_non_dominated_metrics()
```

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

El servicio Python esta listo para conectarse al servicio Java de evaluacion de pipelines.
Siguiente paso natural: fijar el contrato definitivo del endpoint Java (`/pipeline`) y montar una primera implementacion funcional del lado Java con ProM Lite.
