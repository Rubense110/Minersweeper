---
layout: default
title: Troubleshooting
---

# Troubleshooting

## The Java service does not start

Check the following:

- `prom-lite-1.4-all-platforms/` exists at the repository root
- the Split Miner slim JAR was generated with `./tools/build_splitminer_slim.sh`
- Docker was able to build `java-service/Dockerfile`

## The optimization service cannot evaluate pipelines

Verify:

- `prom_service` is healthy
- `optimization_service` is healthy
- `JAVA_SERVICE_URL` points to `http://prom_service:7070` in Docker

## No logs appear in the UI or API

Verify:

- the XES files exist inside `event_logs/`
- the directory is mounted into `/data/logs`
- the requested `log_path` matches the mounted files

## Frontend cannot reach the API

Verify:

- `optimization_service` is running on port `8080`
- `VITE_OPTIMIZATION_API_URL` is set correctly
- no local firewall or reverse proxy is interfering

## Database-related issues

Check:

- PostgreSQL container health
- the `OPT_DB_URL` value
- whether old volumes need to be removed with `docker compose down -v`

## Useful debug commands

```bash
docker compose ps
docker compose logs -f prom_service
docker compose logs -f optimization_service
docker compose logs -f postgres
```

