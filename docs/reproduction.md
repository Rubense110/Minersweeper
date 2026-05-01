---
layout: default
title: Reproducibility Notes
---

# Reproducibility Notes

## Scope

This project is distributed to support the SoftwareX publication with an executable and inspectable implementation of the Minersweeper platform.

## Reproducibility assumptions

The expected execution model is based on:

- Dockerized execution through `docker compose`
- a local ProM Lite bundle stored at `prom-lite-1.4-all-platforms/`
- local event logs stored under `event_logs/`

## Published images

The project repository defines and publishes three images:

- `rubjimjim/minersweeper-mining`
- `rubjimjim/minersweeper-optimization`
- `rubjimjim/minersweeper-frontend`

## Reference execution flow

The recommended reproducibility flow is:

1. Prepare the ProM bundle and the event logs.
2. Generate the Split Miner slim JAR.
3. Start the stack with Docker Compose.
4. Submit an optimization job through the API or frontend.
5. Inspect solutions, artifacts, and stored experiment data.

## Persistence

Final experiment results are stored in PostgreSQL by `optimization_service`.

Stored information includes:

- experiment metadata
- final population solutions
- Pareto membership
- runtime metadata
- exported artifact structures used by the frontend and API

## Notes for reviewers and readers

The Java service contains both lightweight tests and a real evaluator test that depends on a valid ProM runtime environment. This separation exists to keep routine CI practical while preserving a path for end-to-end validation with the real ProM stack.

