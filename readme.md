# Minersweeper

Plataforma para optimizacion de pipelines de process mining con NSGA-III y evaluacion real en ProM.

## Arquitectura

- `prom_service` (`java-service`, SparkJava + ProM):
  - evalua pipelines
  - descubre modelos Petri (PNML)
  - calcula metricas
  - persiste artefactos por evaluacion
- `optimization_service` (`optimization-service`, Flask + jMetalPy):
  - ejecuta optimizacion NSGA-III
  - expone jobs HTTP (`queued/running/completed/failed`)
  - persiste resultados finales de experimento en PostgreSQL
- `frontend_service` (`frontend-service`, React + Vite):
  - lanza optimizaciones
  - consume SSE de progreso
  - visualiza soluciones y PNML
- `postgres`:
  - BBDD unica para persistencia del `optimization_service`

## Prerrequisitos

- Docker + Docker Compose
- `prom-lite-1.4-all-platforms/` en la raiz del repo
- Logs XES en `pm_site/pm_app/logs/`

## Arranque con Docker

Antes del primer build (solo una vez), generar el jar slim de Split Miner:

```bash
./tools/build_splitminer_slim.sh
```

```bash
cd Minersweeper
docker compose up --build -d
```

Servicios:

- `prom_service`: `http://localhost:7070`
- `optimization_service`: `http://localhost:8080`
- `frontend_service`: `http://localhost:5173`
- `postgres`: `localhost:5432` (`minersweeper/minersweeper`)

Healthchecks:

```bash
curl -sS http://localhost:7070/health
curl -sS http://localhost:8080/health
```

## Flujo rapido

1. Lanzar optimizacion:

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

2. Consultar estado:

```bash
curl -sS http://localhost:8080/optimizations/<job_id>
curl -sS http://localhost:8080/optimizations/<job_id>/progress
```

3. Obtener resultados:

```bash
curl -sS "http://localhost:8080/optimizations/<job_id>/solutions?scope=pareto"
curl -sS "http://localhost:8080/optimizations/<job_id>/artifacts?scope=pareto&include_pnml=true"
```

## API de `optimization_service`

Endpoints:

- `GET /health`
- `GET /optimizations`
- `POST /optimizations`
- `GET /optimizations/:job_id`
- `GET /optimizations/:job_id/progress`
- `GET /optimizations/:job_id/events` (SSE)
- `GET /optimizations/:job_id/solutions?scope=pareto|all`
- `GET /optimizations/:job_id/artifacts?scope=pareto|all&include_pnml=true|false`

Eventos SSE:

- `status_changed`
- `progress`
- `result_ready`
- `error`

## API de `prom_service`

Endpoints:

- `GET /health`
- `POST /pipeline`
- `POST /artifacts/bulk`
- `POST /experiments/:experimentId/cleanup`
- `GET /experiments/:experimentId/fingerprints`

### Nuevo endpoint: fingerprints por experimento

Devuelve `evaluation_id` + `fingerprint` para todas las evaluaciones encontradas en ese experimento.

```bash
curl -sS "http://localhost:7070/experiments/<experiment_id>/fingerprints"
```

Respuesta:

```json
{
  "experiment_id": "run_001",
  "fingerprints": [
    { "evaluation_id": "1770734531539-1", "fingerprint": "..." }
  ]
}
```

## Persistencia en PostgreSQL (`optimization_service`)

La persistencia se hace al finalizar el job, guardando la poblacion final del experimento.

### `Experiment`

- `ExperimentID` (PK)
- `ExperimentName`
- `StartAt`
- `EndAt`
- `Max_evals`
- `Pop_size`
- `Miners` (catalogo usado)
- `Preprocessing` (catalogo usado)
- `log_path`
- `metrics` (orden oficial)
- `workers`

### `Solution`

- `SolutionID` (PK)
- `ExperimentID` (FK)
- `variables`
- `objectives`
- `pipeline` (compactado: `variant` + `parameters`)
- `is_pareto`
- `places`
- `transitions`
- `arcs`

Contrato de `metrics/objectives`:

- `Experiment.metrics[i]` corresponde a `Solution.objectives[i]`.
- `objectives` estan en espacio del optimizador (si se maximiza, se almacenan negadas).

## Desarrollo local por servicio

### Java service

Prerequisitos:

- Java 8+
- Maven
- `install_prom_jars.sh` ejecutado

Compilar:

```bash
cd java-service
mvn -DskipTests package dependency:copy-dependencies
```

Run recomendado:

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

## Logs utiles

```bash
docker compose logs -f prom_service
docker compose logs -f optimization_service
docker compose logs -f postgres
```

## Parada

```bash
docker compose down
docker compose down -v
```

`docker-compose.old.yml` queda como referencia historica.
