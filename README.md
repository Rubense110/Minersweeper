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

The default search uses **36 candidates**, **4 reference partitions** (`n_partitions`, giving 35 directions for the four quality objectives), and **1,836 evaluations**. This budget covers the initial population and 50 complete offspring generations. The web form sends these defaults, and the API and Python entry points use them when the settings are omitted. The number of directions depends on the number of selected objectives. Cache hits and failed evaluations also consume the evaluation budget.

The search keeps SBX crossover with probability 0.9 and distribution index 20, and polynomial mutation with probability `1 / number_of_genes` and distribution index 20. These are initial settings to measure, rather than an established optimum for every log. Population, budget and reference partitions can be overridden through the API.

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

OpenAPI documentation for the optimization service:

- OpenAPI spec: `http://localhost:8080/openapi.json`
- Swagger UI: `http://localhost:8080/docs`

OpenAPI documentation for the mining service:

- OpenAPI spec: `http://localhost:7070/openapi.json`
- Swagger UI: `http://localhost:7070/docs`
- PostgreSQL: `localhost:5432`

### Recommended Usage

For normal operation:

1. Open `http://localhost:5173`
2. Launch a new experiment from the web interface
3. Monitor progress in the results view
4. Inspect stored runs from the history page

Although the backend also exposes HTTP endpoints, the repository is documented around the web workflow because that is the intended user interaction path.

### Resource limits and cancellation

Evaluation uses `replay-token` when the mode is omitted. The service skips scoring
models rejected by the quality policy and returns `metrics: {}` with
`metrics_status: "skipped_infeasible"`; these are unmeasured metrics. The optimizer
uses penalty objectives for these candidates, which can change the search trajectory.
Projection now applies its requested frequency threshold. The former adapter
inverted the selection/options arguments and inadvertently kept every activity;
this correction can change discovered models.

The Compose defaults admit four Java evaluations, four Python evaluation workers,
and one optimization job at a time. Adjust these variables together:

| Variable | Default | Role |
|---|---:|---|
| `PROM_MAX_CONCURRENT_EVALUATIONS` | 4 | Java evaluation slots; released after execution and owned tasks stop |
| `PROM_EVALUATION_RESERVE_MB` | 512 | Heap headroom signal; not a bound on plugin allocation |
| `PROM_PREPROCESS_CACHE_MB` | 256 | Estimated retained payload budget for filtered logs; 0 disables this cache |
| `OPT_MAX_EVALUATION_WORKERS` | 4 | Worker cap for the API and direct optimizer |
| `OPT_MAX_CONCURRENT_JOBS` | 1 | Optimization jobs allowed to run together |
| `OPT_MAX_QUEUED_JOBS` | 16 | Jobs allowed to wait for execution |
| `PROM_ALLOW_MINER_MULTITHREADING` | false | Enables IM internal threads only if requested by the pipeline too |
| `JAVA_CANCEL_GRACE_SECONDS` | 10 | Time to confirm termination after an ambiguous HTTP failure |

Filtered logs can be reused across different miners within an experiment. The cache
uses source identity and the ordered effective filter parameters, coordinates
identical concurrent requests, and gives each cached consumer a private deep copy.
When a result consists of whole original traces, the cache stores their indices
instead of event payloads. It holds at most 32 entries and is cleared on experiment
cleanup. Other filtered logs larger than the budget bypass storage: each request
computes its own result using the existing uncached path, without an extra copy. This budget estimates retained payload; private
copies, in-flight filters, and plugin allocations consume additional memory.

Variant filtering uses compact statistics (a separate 64 MiB / 16-entry bound)
and sorts variants by frequency, with later first appearances winning ties.
It retains whole variants until the next would exceed the percentage of traces,
then stops, preserving input trace order. Sequence keys distinguish ambiguous
activity-name concatenations such as `[AB, C]` and `[A, BC]`; global attribute
declarations are now preserved. These corrections can change affected models.
Neither cache changes the optimization population or uses log-specific rules.

The Java waiting queue is bounded. Insufficient heap headroom for five seconds
rejects admission rather than waiting indefinitely. For a 32 GB machine, begin
with 2–4 evaluations and leave memory for Python, PostgreSQL, native memory, and
the OS. A slot limit does not guarantee that one very large plugin call fits.

On timeout or connection failure, Python cancels the request and checks its
termination status. Failure to confirm stops that optimization. This is cooperative
cancellation in a shared JVM: forcibly stopping an uncooperative plugin requires
process isolation. Experiment execution names cannot be reused after cleanup;
use a fresh execution name for each run.

With `PROM_TIMING_ENABLED=true`, phase records include heap usage at phase
boundaries, active/waiting evaluations, and JVM thread and cumulative GC counters.
These are JVM-wide observations, not per-evaluation peak memory or GC attribution.

## Persistence and Outputs

New persisted results store each evaluation graph once in `model_artifacts`.
Population and snapshot members reference it. Existing inline graphs remain
readable; schema initialization adds nullable references without rewriting old
experiments. Artifact transfer uses batches of 16; Java bulk requests accept at
most 32 IDs. Completed jobs release their populations and load results from the
database when requested.

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

The common experiment ZIP contains the four CSV tables and, for retained
originals, `models/*.pnml`, their semantic metadata and `models/index.json`
with SHA-256 hashes. Original PNML and metadata are stored once per evaluation,
before Java artifact cleanup. Historical results without retained originals are
explicitly marked unavailable; PNML is never reconstructed for this export.

## Experimental Model Exploration

Open **Exploración** (`/exploration`) or **Explorar población** from History.
Explore the complete final population through three structural views:

- annotated overlay, inspired by [La Rosa et al. (2013)](https://doi.org/10.1145/2430545.2430547);
- nested regions with verified shared interfaces, inspired by [Assy et al. (2017)](https://www.vdaalst.rwth-aachen.de/publications/p916.pdf);
- strict common core and variable blocks, inspired by [BPFlexTemplate (2017)](https://ijispm.sciencesphere.org/archive/ijispm-050304.pdf).

Choose **Petri nets** or **BPMN (experimental)** in the representation selector.
All three views analyze the chosen graph representation; BPMN is derived with
PM4Py's conversion rules, stable IDs and Petri provenance. Its tasks, XOR/AND
gateways and start/end events retain links to the original individuals. BPMN
fragments can be compared and expanded, with their original Petri net, markings,
metrics and unchanged PNML always available. Analysis caches are separate for
the two representations. Conversion limitations are documented in the session;
conversion success does not certify behavioral equivalence.

The overlay opens as an activity map: each link has a real directed path witness
in its source nets, through places/invisible transitions without intervening
visible activities. Activity and connection support filters are independent;
weak context links keep their actual support. This abstraction does not assert
enabled behavior or enumerate all routing paths. The full typed overlay remains
available, initially focused on one individual.

Variation points are explicit nodes in a region inclusion tree. A local region
must satisfy global shared-boundary participation, inside/outside direction
conditions and directed entry-to-exit coverage in every source. Marking-bearing
places are protected process endpoints. Alternatives are compared by bounded
exact typed graph isomorphism with fixed ports, invisible flags and arc weights;
unknown comparisons do not establish variation. Only validated local regions
with proven structural differences are labelled VP. Complete model differences
are available separately as global variation at the root. Shared interfaces and two original fragment
previews are shown together, with provenance, metrics, zoom and expanded viewing.

Every element or alternative links to its source individuals, metrics, original
Petri graph and PNML. Invisible transitions, arc weights and all final markings
are retained. Template filters query combinations actually present in the
population. No clustering, prior deduplication, final-model selection, discovery
or behavioral-equivalence analysis is performed.

Import the common ZIP directly; historical ZIPs also require their original
PNML/JSON pairs or a ZIP/folder containing them. Imports create a separate saved
experiment containing the final population, not its historical snapshots.
The supplied source export remains unchanged. Limits are 500 individuals,
64 MiB expanded per archive and 2 MiB per PNML. Analyses run one at a time,
support cooperative cancellation and persist their versioned results.
Region candidates are generated conservatively from exact incident-model sets,
validated and merged where adjacent regions share the same participants. The
hierarchy uses inclusion of original arc occurrences. Crossing candidates remain
accessible outside the tree. A log can have no verified local VP under this
candidate policy; that does not imply model equivalence or an exhaustive SHESHE
search. All original models remain accessible.
These are descriptive adaptations to Petri nets or derived BPMN, not executable consolidated
nets or demonstrations of behavioral equivalence.

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
python -m api
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
