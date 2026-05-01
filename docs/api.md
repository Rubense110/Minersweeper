---
layout: default
title: API Reference
---

# API Reference

## `optimization_service`

Base URL:

```text
http://localhost:8080
```

### Endpoints

- `GET /health`
- `GET /logs`
- `GET /optimizations`
- `POST /optimizations`
- `POST /optimizations/:job_id/cancel`
- `GET /optimizations/:job_id`
- `GET /optimizations/:job_id/progress`
- `GET /optimizations/:job_id/events`
- `GET /optimizations/:job_id/solutions?scope=pareto|all`
- `GET /optimizations/:job_id/artifacts?scope=pareto|all&include_pnml=true|false`
- `GET /experiments`
- `GET /experiments/:experiment_id`
- `GET /experiments/:experiment_id/solutions?scope=pareto|all`
- `POST /experiments/:experiment_id/select-model`
- `GET /experiments/:experiment_id/download`
- `POST /petri/render`

### SSE events

The optimization event stream can emit:

- `status_changed`
- `progress`
- `result_ready`
- `error`

## `prom_service`

Base URL:

```text
http://localhost:7070
```

### Endpoints

- `GET /health`
- `POST /pipeline`
- `POST /artifacts/bulk`
- `POST /experiments/:experimentId/cleanup`
- `GET /experiments/:experimentId/fingerprints`

## Metrics and conformance mode

`POST /pipeline` accepts:

- `conformance_mode`: `alignment` or `replay`
- canonical metrics:
  - `fitness`
  - `precision`
  - `simplicity`
  - `generalisation`

Backward-compatible aliases are normalized internally:

- `precision_alignment` -> `precision`
- `simplicity_structural` -> `simplicity`
- `generalization` / `generalization_alignment` -> `generalisation`

## Example `POST /pipeline` request

```json
{
  "experiment_id": "run_001",
  "log_path": "/data/logs/BPI_Challenge_2013_open_problems.xes",
  "conformance_mode": "replay",
  "pipeline": {
    "preprocessing": {
      "key": "variant_filter",
      "variant": "Variant Log Filter",
      "parameters": { "keep_threshold_vf": 45 }
    },
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

