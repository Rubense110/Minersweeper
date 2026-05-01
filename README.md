# Minersweeper

Platform for process mining pipeline optimization with NSGA-III and real evaluation in ProM.

## Architecture

- `prom_service` (`java-service`, SparkJava + ProM):
  - evaluates pipelines
  - discovers Petri models (PNML)
  - computes metrics
  - persists artifacts per evaluation
- `optimization_service` (`optimization-service`, Flask + jMetalPy):
  - runs NSGA-III optimization
  - exposes HTTP jobs (`queued/running/completed/failed`)
  - persists final experiment results in PostgreSQL
- `frontend_service` (`frontend-service`, React + Vite):
  - launches optimizations
  - consumes progress SSE
  - visualizes solutions and PNML
- `postgres`:
  - single DB for `optimization_service` persistence

## Prerequisites

- Docker + Docker Compose
- `prom-lite-1.4-all-platforms/` at the repo root
- XES logs in `event_logs/` at the project root

## Startup with Docker

Before the first build (only once), generate the Split Miner slim jar:

```bash
./tools/build_splitminer_slim.sh
```

```bash
cd Minersweeper
docker compose up --build -d
```

Services:

- `prom_service`: `http://localhost:7070`
- `optimization_service`: `http://localhost:8080`
- `frontend_service`: `http://localhost:5173`
- `postgres`: `localhost:5432` (`minersweeper/minersweeper`)

Published images:

- `rubjimjim/minersweeper-mining`
- `rubjimjim/minersweeper-optimization`
- `rubjimjim/minersweeper-frontend`

Health checks:

```bash
curl -sS http://localhost:7070/health
curl -sS http://localhost:8080/health
```

## Quick flow

1. Launch an optimization:

```bash
curl -sS -X POST http://localhost:8080/optimizations \
  -H 'Content-Type: application/json' \
  -d '{
    "execution_name":"run_test_python_api",
    "log_path":"/data/logs/BPI_Challenge_2013_open_problems.xes",
    "max_evaluations":50,
    "population_size":20,
    "n_workers":1,
    "excluded_miners":["ilp"]
  }'
```

2. Check status:

```bash
curl -sS http://localhost:8080/optimizations/<job_id>
curl -sS http://localhost:8080/optimizations/<job_id>/progress
```

3. Get results:

```bash
curl -sS "http://localhost:8080/optimizations/<job_id>/solutions?scope=pareto"
curl -sS "http://localhost:8080/optimizations/<job_id>/artifacts?scope=pareto&include_pnml=true"
```

## `optimization_service` API

Endpoints:

- `GET /health`
- `GET /optimizations`
- `POST /optimizations`
- `GET /optimizations/:job_id`
- `GET /optimizations/:job_id/progress`
- `GET /optimizations/:job_id/events` (SSE)
- `GET /optimizations/:job_id/solutions?scope=pareto|all`
- `GET /optimizations/:job_id/artifacts?scope=pareto|all&include_pnml=true|false`

SSE events:

- `status_changed`
- `progress`
- `result_ready`
- `error`

## `prom_service` API

Endpoints:

- `GET /health`
- `POST /pipeline`
- `POST /artifacts/bulk`
- `POST /experiments/:experimentId/cleanup`
- `GET /experiments/:experimentId/fingerprints`

### Metrics and `conformance_mode`

`POST /pipeline` now accepts functional metrics and an explicit conformance mode selector:

- `conformance_mode`: `alignment` | `replay` (default: `alignment`)
- canonical metrics supported in the request:
  - `fitness`
  - `precision`
  - `simplicity`
  - `generalisation`

Backward compatibility (normalized internally):

- `precision_alignment` -> `precision`
- `simplicity_structural` -> `simplicity`
- `generalization` / `generalization_alignment` -> `generalisation`

Example request:

```json
{
  "experiment_id": "run_001",
  "log_path": "/data/logs/BPI_Challenge_2013_open_problems.xes",
  "conformance_mode": "replay",
  "pipeline": {
    "preprocessing": { "key": "variant_filter", "variant": "Variant Log Filter", "parameters": { "keep_threshold_vf": 45 } },
    "miner": { "key": "inductive", "family": "inductive", "variant": "Inductive Miner (IM)", "parameters": { "is_debug": false, "use_multithreading": true } }
  },
  "metrics": ["fitness", "precision", "simplicity", "generalisation"]
}
```

### Log preprocessing (pipeline)

`POST /pipeline` supports two input formats for preprocessing:

- `pipeline.preprocessing` (legacy, a single step)
- `pipeline.preprocessings` (new, ordered list of steps)

Contract rules:

- If `preprocessings` is provided, it is applied in order (`[0] -> [1] -> ...`) on the current log.
- If only `preprocessing` is provided, it is internally normalized to `preprocessings` of size 1.
- `pipeline.preprocessing` is kept in metadata as an alias of the first step for compatibility.
- Supported keys (`key`):
  - `projection_filter`
  - `variant_filter`
  - `repair_log_filter`
  - `matrix_filter`

Example with a preprocessing chain:

```json
{
  "experiment_id": "run_chain_001",
  "log_path": "/data/logs/BPI_Challenge_2013_open_problems.xes",
  "conformance_mode": "alignment",
  "pipeline": {
    "preprocessings": [
      {
        "key": "projection_filter",
        "variant": "Projection Log Filter",
        "parameters": { "keep_threshold_p": 60 }
      },
      {
        "key": "variant_filter",
        "variant": "Variant Log Filter",
        "parameters": { "keep_threshold_vf": 50 }
      },
      {
        "key": "matrix_filter",
        "variant": "Conditional Probabilities (MF)",
        "parameters": {
          "subsequence_length_mf": 2,
          "probability_of_removal_mf": 0.15
        }
      }
    ],
    "miner": {
      "key": "inductive",
      "family": "inductive",
      "variant": "Inductive Miner (IM)",
      "parameters": { "is_debug": false, "use_multithreading": true }
    }
  },
  "metrics": ["fitness", "precision", "simplicity", "generalisation"]
}
```

Current implementation by filter:

- `projection_filter`:
  - `FilterdEventRateFilter.filter(...)`
  - `Toolbox.computeDesiredEventsFromThreshold(...)`
  - Supported parameter:
    - `keep_threshold_p` (`0..100`)
- `variant_filter`:
  - `FilterdTraceFrequencyFilter.filter(...)`
  - Supported parameter:
    - `keep_threshold_vf` (`0..100`)
- `matrix_filter`:
  - Causal matrix discovery: `DiscoverFromEventLogAlgorithm.apply(...)`
  - Filtering on the matrix: `FilterLogUsingMatrixAlgorithm.apply(...)`
  - Supported parameters:
    - `subsequence_length_mf` (`1..3`)
    - `probability_of_removal_mf` (`0..1`)
- `repair_log_filter`:
  - Custom window-based implementation (deterministic) on the XES log.
  - Supported parameters:
    - `subsequence_length_rl` (`1..5`)
    - `probability_of_removal_rl` (`0..1`)
  - Note:
    - In the `prom-lite-1.4-all-platforms` bundle used by the project, the classes from `LogFiltering`
      (`VariantCounterPlugin`, `RepairBasedOnWindows`, `FilterBasedOnRelationMatrixK`) are not present, so this equivalent implementation available in the current classpath is used.

Operational notes:

- Preprocessing time is traced in logs as `preprocess_ms`.
- The fingerprint includes the full preprocessing chain in order to avoid collisions.
- Model discovery is executed on the preprocessed log, but conformance metrics are computed on the original log.

#### Technical implementation by mode

`alignment` (default):

- `fitness`:
  - Replay on the Petri net with `PNLogReplayer` + `PetrinetReplayerWithILP` (`PNetReplayer`).
  - `PNRepResult.TRACEFITNESS` is used.
- `precision` and `generalisation`:
  - `AlignmentPrecGen.measureConformanceAssumingCorrectAlignment` (`PNetAlignmentAnalysis`) on the previous replay.
- `simplicity`:
  - Custom structural metric (places/transitions/arcs + branching penalty).

`replay`:

- `fitness`:
  - Replay with `PNLogReplayer` + `PetrinetReplayerWithoutILP` (`PNetReplayer`).
  - PM4Py-legacy-like approach (token-based-like): combines two replay components:
    - `Move-Log Fitness`
    - `Move-Model Fitness`
  - final score: average of both (`(move_log + move_model) / 2`), with fallback to `TRACEFITNESS` if components are missing.
- `precision`:
  - Replay-based ETConformance (`ETCAlgorithm`, plugin `ETConformance`), `ETCp` value (`ETCResults.getEtcp()`).
- `generalisation`:
  - Replay-based (inspired by PM4Py's activation counting approach):
    - transition activations are counted from `PNRepResult` (weighted by the multiplicity of represented traces),
    - penalty per transition: `1` if it does not appear, if it appears `1/sqrt(n_activations)`,
    - final score: `1 - average_penalty`.
- `simplicity`:
  - Same as in `alignment`.

Notes:

- Both modes reuse the same discovered model and the same log->transition mapping.
- The `fingerprint` includes `conformance_mode` to avoid collisions between evaluations with different modes.

### New endpoint: fingerprints by experiment

Returns `evaluation_id` + `fingerprint` for all evaluations found in that experiment.

```bash
curl -sS "http://localhost:7070/experiments/<experiment_id>/fingerprints"
```

Response:

```json
{
  "experiment_id": "run_001",
  "fingerprints": [
    { "evaluation_id": "1770734531539-1", "fingerprint": "..." }
  ]
}
```

## Persistence in PostgreSQL (`optimization_service`)

Persistence is performed when the job finishes, storing the final population of the experiment.

### `Experiment`

- `ExperimentID` (PK)
- `ExperimentName`
- `StartAt`
- `EndAt`
- `Max_evals`
- `Pop_size`
- `Miners` (catalog used)
- `Preprocessing` (catalog used)
- `log_path`
- `metrics` (official order)
- `workers`

### `Solution`

- `SolutionID` (PK)
- `ExperimentID` (FK)
- `variables`
- `objectives`
- `pipeline` (compacted: `variant` + `parameters`)
- `runtime_ms` (evaluation time of that solution, in milliseconds)
- `is_pareto`
- `places`
- `transitions`
- `arcs`

`metrics/objectives` contract:

- `Experiment.metrics[i]` corresponds to `Solution.objectives[i]`.
- `objectives` are in optimizer space (if maximized, they are stored negated).

## Local development by service

### Java service

Prerequisites:

- Java 8+
- Maven
- `install_prom_jars.sh` executed

Compile:

```bash
cd java-service
mvn -DskipTests package dependency:copy-dependencies
```

Recommended run:

```bash
cd java-service
./run_prom_service.sh
```

### Optimization service

Tests:

```bash
venv/bin/python -m unittest discover -s optimization-service/tests -p "test_*.py" -v
```

### Frontend service

```bash
cd frontend-service
npm install
npm run dev
```

`VITE_OPTIMIZATION_API_URL` default: `http://localhost:8080`.

## Useful logs

```bash
docker compose logs -f prom_service
docker compose logs -f optimization_service
docker compose logs -f postgres
```

## Shutdown

```bash
docker compose down
docker compose down -v
```

The legacy Django version was removed. The supported release is the one defined by `docker-compose.yml`.
