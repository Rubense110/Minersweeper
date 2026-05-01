---
layout: default
title: Installation
---

# Installation

## Prerequisites

To run Minersweeper, the following prerequisites are required:

- Docker
- Docker Compose
- `prom-lite-1.4-all-platforms/` at the repository root
- XES event logs in `event_logs/` at the project root

## Repository layout required for execution

The project expects the following important paths to exist:

- `prom-lite-1.4-all-platforms/`
- `event_logs/`
- `docker-compose.yml`

## First-time setup

Before the first Docker build, generate the Split Miner slim JAR:

```bash
./tools/build_splitminer_slim.sh
```

This step only needs to be performed once unless the ProM bundle is replaced or cleaned.

## Optional local development setup

For local development outside Docker:

- Java service:
  - Java 8+
  - Maven
  - `install_prom_jars.sh` executed successfully
- Optimization service:
  - Python 3.12 recommended
  - project dependencies installed from `requirements.txt`
- Frontend service:
  - Node.js 20 recommended
  - dependencies installed from `frontend-service/package.json`

