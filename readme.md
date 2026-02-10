# Minersweeper

Repositorio del backend de optimizacion de pipelines de process mining:

- `prom_service` (Java + ProM): descubre modelos y calcula metricas.
- `optimization_service` (Python + jMetalPy): ejecuta NSGA-III y expone jobs HTTP.
- `frontend_service` (React + Vite): UI simple para lanzar ejecuciones y ver resultados.

## Documentacion por servicio

- `java-service/README_java_service.md`
- `optimization-service/README_optimization_service.md`
- `frontend-service/README_frontend_service.md`

## Lanzar la app con Docker

Prerequisitos:

- Docker y Docker Compose instalados.
- La carpeta `prom-lite-1.4-all-platforms/` presente en la raiz del repo.
- Logs XES en `pm_site/pm_app/logs/` (se montan como `/data/logs` en contenedores).

### 1. Construir y levantar

```bash
cd Minersweeper
docker compose up --build -d
```

Servicios publicados:

- `prom_service`: `http://localhost:7070`
- `optimization_service`: `http://localhost:8080`
- `frontend_service`: `http://localhost:5173`

### 2. Verificar salud

```bash
curl -sS http://localhost:7070/health
curl -sS http://localhost:8080/health
```

### 3. Lanzar una optimizacion (API Python)

```bash
curl -sS -X POST http://localhost:8080/optimizations \
  -H 'Content-Type: application/json' \
  -d '{
    "execution_name":"run_test_python_api",
    "log_path":"/data/logs/BPI_Challenge_2013_open_problems.xes",
    "max_evaluations":50,
    "population_size":20,
    "n_workers":1,
    "excluded_miners":["split"]
  }'
```

La respuesta devuelve `job_id`.

### 4. Consultar estado del job

```bash
curl -sS http://localhost:8080/optimizations/<job_id>
```

Estados terminales:

- `completed`
- `failed`

### 5. Recuperar resultados del frente

Soluciones:

```bash
curl -sS "http://localhost:8080/optimizations/<job_id>/solutions?scope=pareto"
```

Artefactos (PNML):

```bash
curl -sS "http://localhost:8080/optimizations/<job_id>/artifacts?scope=pareto&include_pnml=true"
```

## Logs utiles

```bash
docker compose logs -f prom_service
docker compose logs -f optimization_service
```

## Parar stack

```bash
docker compose down
```

Para eliminar tambien redes/estado de contenedores:

```bash
docker compose down -v
```

## Nota

Existe un compose anterior en `docker-compose.old.yml` para referencia, pero el flujo activo es `docker-compose.yml`.
