# MinerSweeper

MinerSweeper is a web platform that automates process discovery with multiple objectives.  
Upload an event log, pick the metrics that matter (fitness, precision, simplicity, etc.), choose a miner and an optimizer, and let the app search for the best Petri nets. The UI lets you inspect executions, see Pareto fronts, compare models, and download all artifacts for offline analysis.

## What You Can Do
- **Guided discovery wizard** – select metrics, miners (heuristic or inductive) and optimizers (NSGA-II, NSGA-III, SPEA2, parallel NSGA-II).
- **Execution history** – revisit every run, review optimizer parameters, runtime, and log source.
- **Solution explorer** – navigate the Pareto front, inspect Petri nets, download CSV/JSON packages, and compare nets visually.
- **Log manager** – upload/remove XES event logs directly from the interface.

## Quick Start (Docker)
1. Clone the repo and copy the environment template:
   ```bash
   git clone <repo-url>
   cd pm_app_v2
   cp .env.example .env
   ```
   The template already contains demo-friendly defaults (debug enabled, dev secret key, Postgres MS/MS/MS). Change them only if you plan to expose the app publicly.

2. Launch the stack:
   ```bash
   docker compose up --build
   ```
   The `database` service runs PostgreSQL, `django_app` runs migrations automatically and serves the site at http://localhost:8000/.

3. Start exploring: upload an event log under **Logs**, open **Discovery**, follow the wizard, and review the resulting executions in **History** and **Solutions**.

4. Stop the stack:
   ```bash
   docker compose down        # keep database volume
   docker compose down -v     # remove everything, including data
   ```

## Manual Setup (Optional)
If you prefer running Django directly:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python pm_site/manage.py migrate
python pm_site/manage.py runserver
```
Set `DJANGO_USE_SQLITE=1` in `.env` if you want to avoid PostgreSQL for local experiments.

## Configuration
Key environment variables (loaded from `.env`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Session/CSRF signing key | `dev-secret-key-change-me` |
| `DJANGO_DEBUG` | `1` to enable Django debug mode | `1` |
| `DJANGO_ALLOWED_HOSTS` | Space-separated hosts when debug is off | `localhost 127.0.0.1` |
| `DJANGO_USE_SQLITE` | `1` to use SQLite instead of Postgres | `0` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Database connection settings | `MS`, `MS`, `MS`, `database`, `5432` |

For production deployments change the secret key, disable debug, and narrow `DJANGO_ALLOWED_HOSTS`.

## Database Tips
- Enter the Django container console to run management commands:
  ```bash
  docker compose exec web bin/bash
  ```
- Backup the default PostgreSQL instance:
  ```bash
  docker exec -t database pg_dump -U MS MS > backup.sql
  ```
- Restore from a dump:
  ```bash
  docker exec -i database psql -U MS MS < backup.sql
  ```
- Empty the database tables (run inside the container shell):
  ```bash
  python3 manage.py flush --no-input
  ```
- Reset auto-increment after bulk imports:
  ```sql
  SELECT setval(pg_get_serial_sequence('"pm_app_execution"', 'id'), MAX(id)) FROM "pm_app_execution";
  ```

Happy process mining!

## Java service

Prereqs:
- Download ProM Lite 1.4 (all platforms) and place it at the repo root as `prom-lite-1.4-all-platforms/`.
- Run the installer script to register the required jars in your local Maven repo:
  ```bash
  ./install_prom_jars.sh
  ```

Compile:
```bash
mvn -f java-service/pom.xml -DskipTests package
mvn -f java-service/pom.xml -DskipTests dependency:copy-dependencies -DincludeScope=runtime
```

Run:
```bash
java -cp "java-service/target/prom-service-0.1.0.jar:java-service/target/dependency/*" PromService
```

Health check:
```bash
curl http://localhost:7070/health
```

Prueba:

```bash
curl -X POST http://localhost:7070/mine \
  -H "Content-Type: application/json" \
  -d '{"log_path":"BPI_Challenge_2013_open_problems.xes","miner":"alpha"}'
```