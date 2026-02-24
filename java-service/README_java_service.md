# Java Service (`java-service`)

Servicio HTTP (SparkJava) para evaluar pipelines de descubrimiento de procesos usando ProM.

Este servicio:
- Recibe un `pipeline` (preprocesado + minero + parametros)
- Descubre un modelo Petri net (PNML)
- Calcula metricas de calidad
- Persiste artefactos por evaluacion para recuperarlos despues sin re-ejecutar

## Que hace y que no hace

- `PromPipelineEvaluator` ejecuta mineria y calculo de metricas reales con ProM.
- El servicio en runtime usa solo el evaluador real.
- Existe un `StubPipelineEvaluator` en tests para pruebas rapidas de contrato.
- El bloque `pipeline.preprocessing` es obligatorio en el contrato y se guarda en metadata/fingerprint.
- En la implementacion actual del evaluador real, el preprocesado todavia no transforma el log.

## Endpoints

- `GET /health`
- `POST /pipeline`
- `POST /artifacts/bulk`
- `POST /experiments/:experimentId/cleanup`

## Contrato: `POST /pipeline`

Request JSON:

```json
{
  "experiment_id": "run_001",
  "log_path": "/abs/path/log.xes",
  "pipeline": {
    "preprocessing": {
      "key": "matrix_filter",
      "method": "Matrix Filtering",
      "variant": "Conditional Probabilities (MF)",
      "parameters": {
        "probability_of_removal_mf": 0.15,
        "subsequence_length_mf": 2
      }
    },
    "miner": {
      "key": "inductive",
      "family": "inductive",
      "variant": "Inductive Miner (IM)",
      "parameters": {
        "noise_threshold": 0.2
      }
    }
  },
  "metrics": ["fitness", "precision_alignment", "simplicity_structural", "generalization_alignment"],
  "excluded_miners": ["split", "ilp"]
}
```

Response JSON:

```json
{
  "experiment_id": "run_001",
  "evaluation_id": "1770734531539-1",
  "fingerprint": "/abs/path/log.xes|matrix_filter|Conditional Probabilities (MF)|{...}|inductive|Inductive Miner (IM)|{noise_threshold=0.2}",
  "metrics": {
    "fitness": 1.0,
    "precision_alignment": 0.90,
    "simplicity_structural": 0.64,
    "generalization_alignment": 0.99
  }
}
```

Validaciones principales:
- `experiment_id`, `log_path`, `pipeline`, `pipeline.preprocessing`, `pipeline.miner`, `metrics` son obligatorios.
- `pipeline.preprocessing.key` y `pipeline.miner.key` no pueden ir vacios.
- Si `parameters` llega `null`, se normaliza a `{}`.

Metricas soportadas:
- `fitness`
- `precision_alignment`
- `simplicity_structural`
- `generalization_alignment`

Nota de contrato:
- Los nombres de metricas son estrictos (sin aliases y case-sensitive).
- Si llega una metrica fuera del catalogo exacto, responde `400 invalid_request`.

Errores tipicos:
- `400 invalid_request`
- `400 invalid_json`
- `500 evaluation_failed`

## Contrato: `POST /artifacts/bulk`

Request JSON:

```json
{
  "experiment_id": "run_001",
  "evaluation_ids": ["1770734531539-1"],
  "include_pnml": true
}
```

Response JSON:

```json
{
  "experiment_id": "run_001",
  "artifacts": [
    {
      "experiment_id": "run_001",
      "evaluation_id": "1770734531539-1",
      "fingerprint": "...",
      "log_path": "/abs/path/log.xes",
      "created_at_epoch_ms": 1770734531542,
      "metrics": {
        "fitness": 1.0,
        "precision_alignment": 0.90,
        "simplicity_structural": 0.64,
        "generalization_alignment": 0.99
      },
      "pipeline": {
        "preprocessing": {"key": "matrix_filter", "method": "Matrix Filtering", "variant": "Conditional Probabilities (MF)", "parameters": {"probability_of_removal_mf": 0.15, "subsequence_length_mf": 2}},
        "miner": {"key": "inductive", "family": "inductive", "variant": "Inductive Miner (IM)", "parameters": {"noise_threshold": 0.2}}
      },
      "pnml": "<?xml ...>..."
    }
  ]
}
```

Notas:
- Si `include_pnml=false`, el campo `pnml` no se incluye.
- Si algun `evaluation_id` no existe en el experimento, responde `404 not_found`.

## Contrato: `POST /experiments/:experimentId/cleanup`

Response JSON:

```json
{
  "experiment_id": "run_001",
  "deleted_paths": 4,
  "deleted": true
}
```

## Almacenamiento de artefactos

Por defecto se guarda en `/tmp/minersweeper-artifacts`.

Estructura por experimento:
- `<evaluation_id>.pnml`
- `<evaluation_id>.json` (metadata + metricas + pipeline)

`evaluation_id` se genera como `<epoch_ms>-<secuencia>`.

## Mineros soportados

- `alpha`
  - variantes: `classic`, `plus`, `plus_plus`, `sharp`, `robust`, `dollar`
- `inductive`
  - variantes: `im`, `imf`, `imlc`, `imflc`, `impt`, `imfpt`, `imfpta`
- `heuristics`
  - `hm` o `fhm` (si la variante contiene `flexible`, usa FHM)
- `hybrid_ilp`
- `ilp`

Si el `miner.key` no esta soportado, responde `400 invalid_request`.
Si el `miner.key` aparece en `excluded_miners`, responde `400 invalid_request`.

## Metricas

- `fitness` via replay result de ProM
- `precision_alignment` y `generalization_alignment` via alignment de ProM
- `simplicity_structural` como proxy estructural normalizado en `[0,1]`

## Mejoras futuras (roadmap tecnico)

- El calculo ya esta separado por metrica (`ConformanceMetric`) y orquestado desde un catalogo.
- Evolucion prevista: introducir variantes por metrica (por ejemplo, estrategias alternativas
  basadas en alignment o replay) manteniendo claves de contrato explicitas.
- Evitar recalculos costosos por metrica en una misma evaluacion:
  construir un contexto compartido de conformance (mapping, replay, alignment)
  y reutilizarlo entre metricas.

## Prerrequisitos

- Java 8+
- Maven
- `prom-lite-1.4-all-platforms` disponible en la raiz del repo (o via `PROM_HOME`)
- Haber instalado jars de ProM en `~/.m2`:

```bash
./install_prom_jars.sh
```

## Compilar

```bash
cd java-service
mvn -DskipTests package dependency:copy-dependencies
```

## Ejecutar (recomendado)

Usa el launcher incluido para evitar problemas de classpath y librerias nativas:

```bash
cd java-service
./run_prom_service.sh
```

Variables de entorno soportadas:
- `PORT` (default: `7070`)
- `PROM_HOME` (default: `../prom-lite-1.4-all-platforms`)
- `LOGS_ROOT` (default: `../pm_site/pm_app/logs`)
- `ARTIFACTS_ROOT` (default: `/tmp/minersweeper-artifacts`)
- `JAVA_LIBRARY_PATH_EXTRA` (opcional, para rutas nativas extra)
- `PROM_TIMING_ENABLED` (default: `false`)
- `PROM_TIMING_SLOW_MS` (default: `0`; si es `>0`, solo loguea evaluaciones con `total_ms >= umbral`)
- `PROM_LOG_CACHE_MAX_EXPERIMENTS` (default: `8`; cache en memoria de `XLog` por `experiment_id`, expulsa por LRU)

Ejemplo:

```bash
PORT=7070 \
PROM_HOME=/ruta/prom-lite-1.4-all-platforms \
LOGS_ROOT=/ruta/logs \
ARTIFACTS_ROOT=/tmp/minersweeper-artifacts \
PROM_TIMING_ENABLED=true \
PROM_TIMING_SLOW_MS=2000 \
PROM_LOG_CACHE_MAX_EXPERIMENTS=8 \
./run_prom_service.sh
```

Cuando `PROM_TIMING_ENABLED=true`, el servicio emite una linea por evaluacion con desglose de fases
(`log_load_ms`, `discover_ms`, `replay_ms`, `alignment_ms`, `metric_*_ms`, `store_artifact_ms`, etc.)
y un `trace_id` para correlacion. Incluye `log_cache=hit|miss`.
El cache de logs se invalida para un experimento al llamar `POST /experiments/:experimentId/cleanup`.

## Flujo rapido de prueba

1. Salud del servicio:

```bash
curl -sS http://localhost:7070/health
```

2. Evaluar pipeline:

```bash
curl -sS -X POST http://localhost:7070/pipeline \
  -H 'Content-Type: application/json' \
  -d '{
    "experiment_id":"run_001",
    "log_path":"/home/ruben/Documents/work/Minersweeper/pm_site/pm_app/logs/BPI_Challenge_2013_open_problems.xes",
    "pipeline":{
      "preprocessing":{"key":"matrix_filter","method":"Matrix Filtering","variant":"Conditional Probabilities (MF)","parameters":{"probability_of_removal_mf":0.15,"subsequence_length_mf":2}},
      "miner":{"key":"inductive","family":"inductive","variant":"Inductive Miner (IM)","parameters":{"noise_threshold":0.2}}
    },
    "metrics":["fitness","precision_alignment","simplicity_structural","generalization_alignment"]
  }'
```

3. Recuperar PNML por `evaluation_id`:

```bash
curl -sS -X POST http://localhost:7070/artifacts/bulk \
  -H 'Content-Type: application/json' \
  -d '{"experiment_id":"run_001","evaluation_ids":["1770734531539-1"],"include_pnml":true}'
```

4. Limpiar artefactos del experimento:

```bash
curl -sS -X POST http://localhost:7070/experiments/run_001/cleanup
```

## Suite de tests

Tests incluidos:
- `ArtifactStoreTest`: persistencia, lectura bulk y cleanup de artefactos.
- `StubPipelineEvaluatorTest`: contrato de metricas con evaluador stub de tests y fingerprint estable.
- `StubPipelineMatrixTest`: matriz completa de mineros x preprocesados usando evaluador stub de tests.
- `PromPipelineEvaluatorRealTest`: smoke real con ProM para todos los mineros y preprocesados (opcional).

Ejecutar tests unitarios:

```bash
cd java-service
mvn test -Dtest=ArtifactStoreTest,StubPipelineEvaluatorTest,StubPipelineMatrixTest
```

Ejecutar tests reales de ProM (lentos):

```bash
cd java-service
RUN_REAL_PROM_TESTS=1 mvn test -Dtest=PromPipelineEvaluatorRealTest
```

## Troubleshooting

- `NoClassDefFoundError` de clases ProM/terceros:
  - Arranca con `./run_prom_service.sh` (no con classpath manual reducido).
- `UnsatisfiedLinkError: no lpsolve55 in java.library.path`:
  - `run_prom_service.sh` ya configura `java.library.path` y `LD_LIBRARY_PATH`.
- `NoClassDefFoundError: lpsolve/LpSolveException` en tests reales:
  - Ejecuta `./install_prom_jars.sh` para instalar `lpsolve55j.jar` en `~/.m2`.
  - Reintenta con `mvn -U test -Dtest=PromPipelineEvaluatorRealTest`.
- `Unknown extension: http://www.xes-standard.org/...`:
  - warning habitual de XES, no bloquea la evaluacion.
