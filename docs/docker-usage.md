---
layout: default
title: Running with Docker
---

# Running with Docker

## Start the stack

From the repository root:

```bash
docker compose up --build -d
```

## Services

After startup, the following services are available:

- `prom_service`: `http://localhost:7070`
- `optimization_service`: `http://localhost:8080`
- `frontend_service`: `http://localhost:5173`
- `postgres`: `localhost:5432`

Database credentials used by the default stack:

- database: `minersweeper`
- user: `minersweeper`
- password: `minersweeper`

## Health checks

The following commands can be used to verify the core services:

```bash
curl -sS http://localhost:7070/health
curl -sS http://localhost:8080/health
```

## Launch an optimization

Example request:

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

## Monitor execution

Check status:

```bash
curl -sS http://localhost:8080/optimizations/<job_id>
curl -sS http://localhost:8080/optimizations/<job_id>/progress
```

Fetch results:

```bash
curl -sS "http://localhost:8080/optimizations/<job_id>/solutions?scope=pareto"
curl -sS "http://localhost:8080/optimizations/<job_id>/artifacts?scope=pareto&include_pnml=true"
```

## Logs

Useful runtime logs:

```bash
docker compose logs -f prom_service
docker compose logs -f optimization_service
docker compose logs -f postgres
```

## Shutdown

Stop the stack:

```bash
docker compose down
```

Stop the stack and remove volumes:

```bash
docker compose down -v
```

