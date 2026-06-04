# Minersweeper

Minersweeper is a web-based platform for multi-objective optimization of process mining pipelines. It combines preprocessing selection, process discovery configuration, and quality evaluation into a single optimization workflow driven by NSGA-III and executed against real ProM operators.

The system is designed as a research software artifact: it exposes a user-facing web application for running experiments, inspecting Pareto-optimal solutions, and comparing discovered models, while keeping the full optimization and evaluation workflow reproducible from the repository.

## Purpose

Given an event log in XES format, Minersweeper searches over:

- log preprocessing strategies
- process discovery algorithms and their parameterizations
- evaluation criteria used to score candidate pipelines

The objective is not to tune a single miner in isolation, but to optimize the full discovery pipeline under multiple quality criteria such as fitness, precision, simplicity, and generalisation.

## System Overview

The platform is organized as three services plus PostgreSQL:

- `src/frontend-service`
  - React/Vite web client
  - entry point for end users
  - supports experiment launch, history browsing, result inspection, model selection, and Petri net rendering
- `src/optimization-service`
  - Flask application served with `gunicorn`
  - orchestrates NSGA-III optimization
  - manages jobs, progress tracking, persistence, and web/API integration
- `src/mining-service`
  - Java service built on SparkJava and ProM
  - executes preprocessing, process discovery, conformance evaluation, and artifact generation
- `postgres`
  - stores completed experiments and their final solution sets

Supporting assets:

- `tools/prom-lite-1.4-all-platforms`
  - ProM Lite distribution used by the mining service
- `tools/install_prom_jars.sh`
  - installs required ProM jars into the local Maven repository
- `tools/build_splitminer_slim.sh`
  - generates the slim Split Miner jar required by the Java service
- `event_logs`
  - input XES logs mounted into the containers
- `logs`
  - runtime service logs

## End-to-End Workflow

The intended interaction mode is the web interface exposed by `frontend_service`.

### 1. Create an experiment

From the **New Experiment** page, the user selects:

- an event log
- the optimization budget (`max_evaluations`)
- the population size
- the number of workers
- the conformance mode (`alignment` or `replay`)
- the metrics to optimize

The optimization service then creates an optimization job and starts evaluating candidate pipelines.

### 2. Search the pipeline space

The optimizer explores combinations of:

- preprocessing filters
  - `projection_filter`
  - `variant_filter`
  - `matrix_filter`
  - `repair_log_filter`
- discovery miners
  - `alpha`
  - `inductive`
  - `heuristics`
  - `split`
  - `ilp`
  - `hybrid_ilp`

Each candidate pipeline is sent to the mining service, which:

- loads the log
- applies preprocessing
- discovers a Petri net
- computes the requested metrics
- stores artifacts associated with the evaluation

### 3. Inspect results

The **Results** page presents:

- optimization progress
- final solution sets
- Pareto-optimal candidates
- pipeline configurations
- objective values and runtime
- Petri net renderings

The interface also supports weighted model selection from the solution set and allows interactive or rendered views of discovered Petri nets.

### 4. Revisit completed experiments

The **History** page exposes persisted experiments from PostgreSQL and provides access to previously completed runs and their stored solutions.

## Optimization Model

Minersweeper frames process discovery as a multi-objective optimization problem.

### Search space

The decision space includes:

- the selected preprocessing method
- the selected miner family and variant
- the active hyperparameters of the chosen preprocessing/miner pair

The search space is hierarchical: only the parameters relevant to the selected preprocessing and miner remain active for a candidate solution.

### Optimization algorithm

- algorithm: NSGA-III
- implementation: `jmetalpy`
- objective handling: maximization objectives are internally negated for optimizer compatibility
- execution mode: sequential or threaded evaluation depending on the configured worker count

### Evaluation metrics

The platform supports both conformance-oriented and structural metrics.

Main metrics:

- `fitness`
- `precision`
- `simplicity`
- `generalisation`

Additional structural metrics available through the UI/API:

- `places`
- `transitions`
- `arcs`
- `t_edges`
- `cycl_complx`
- `cfc`
- `elc`
- `ratio`
- `joins`
- `splits`

### Conformance modes

Two evaluation modes are supported:

- `alignment`
  - alignment-based conformance evaluation
- `replay`
  - replay-based conformance evaluation

The selected conformance mode is part of the evaluation fingerprint so that results from different modes remain distinguishable.

## Repository Layout

```text
.
├── docker-compose.yml
├── event_logs/
├── logs/
├── src/
│   ├── frontend-service/
│   ├── mining-service/
│   └── optimization-service/
└── tools/
    ├── build_splitminer_slim.sh
    ├── install_prom_jars.sh
    └── prom-lite-1.4-all-platforms/
```

Inside `src/optimization-service`, Python source files live under `src/optimization-service/src`, while tests remain under `src/optimization-service/tests`.

## Running the Platform

### Prerequisites

- Docker and Docker Compose
- `tools/prom-lite-1.4-all-platforms`
- one or more `.xes` logs in `event_logs`

Before the first build, generate the Split Miner slim jar:

```bash
./tools/build_splitminer_slim.sh
```

The mining service memory limits are configured through Docker Compose
variable substitution. For local runs, copy the example environment file and
adjust it to the host:

```bash
cp .env.example .env
```

The main knobs are:

- `PROM_SERVICE_MEM_LIMIT`: hard memory limit for the Java mining container
- `PROM_JAVA_XMS`: initial JVM heap
- `PROM_JAVA_XMX`: maximum JVM heap, which should stay below the container limit

Then start the full stack:

```bash
docker compose up --build -d
```

Default service endpoints:

- frontend: `http://localhost:5173`
- optimization service: `http://localhost:8080`
- mining service: `http://localhost:7070`
- PostgreSQL: `localhost:5432`

### Recommended Usage

For normal operation:

1. Open `http://localhost:5173`
2. Launch a new experiment from the web interface
3. Monitor progress in the results view
4. Inspect stored runs from the history page

Although the backend also exposes HTTP endpoints, the repository is documented around the web workflow because that is the intended user interaction path.

## Persistence and Outputs

Completed experiments are stored in PostgreSQL by the optimization service.

Persisted data includes:

- experiment metadata
- configured metrics
- log path
- optimization budget
- worker count
- final solution set
- Pareto membership
- serialized pipeline definitions
- structural Petri net data
- evaluation runtime per solution

Transient and generated outputs:

- service logs in `logs/services.log`
- runtime artifacts produced by the mining service
- optional analysis reports under `src/optimization-service/reports`

## API Role

The API exists to support the web client and scripted experimentation. It is not the primary interaction mode documented here, but it remains important for reproducibility and integration.

Main API capabilities include:

- job submission and cancellation
- job status and progress tracking
- experiment listing and retrieval
- solution and artifact retrieval
- SSE event streaming
- model selection from completed experiments
- Petri net rendering

## Development Notes

### Frontend

- framework: React
- bundler: Vite
- primary pages:
  - experiment creation
  - experiment history
  - result exploration

### Optimization service

- framework: Flask
- container runtime: `gunicorn`
- responsibilities:
  - request handling
  - optimization orchestration
  - persistence
  - event streaming
  - model selection

For local non-container debugging, the service can still be started directly with:

```bash
python src/optimization-service/src/api.py
```

### Mining service

- language: Java 8
- framework: SparkJava
- dependencies: ProM Lite jars installed through `tools/install_prom_jars.sh`

## Testing

### Optimization service tests

```bash
PYTHONPATH=src/optimization-service/src venv/bin/python -m unittest discover -s src/optimization-service/tests -p "test_*.py" -v
```

### Mining service tests

```bash
cd src/mining-service
mvn -q test
```

### Frontend build validation

```bash
cd src/frontend-service
npm install
npm run build
```

## License

Minersweeper is distributed under the GNU General Public License v3.0 (GPL-3.0). See `LICENSE.txt` for the full license text.
