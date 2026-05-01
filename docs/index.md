---
layout: default
title: Minersweeper Manual
---

# Minersweeper Manual

Minersweeper is a platform for process mining pipeline optimization using NSGA-III and real evaluation in ProM.

This manual is intended to support the SoftwareX publication and provide a stable reference for installation, execution, API usage, and reproducibility.

## Contents

- [Installation](installation.md)
- [Running with Docker](docker-usage.md)
- [API Reference](api.md)
- [Reproducibility Notes](reproduction.md)
- [Troubleshooting](troubleshooting.md)

## Repository overview

The project is organized into three main services:

- `prom_service` (`java-service`): evaluates pipelines, discovers Petri nets, computes metrics, and stores artifacts.
- `optimization_service` (`optimization-service`): runs the NSGA-III optimization and exposes the HTTP API.
- `frontend_service` (`frontend-service`): provides the user interface for launching and inspecting experiments.

The main runtime stack also includes PostgreSQL for persistence.

## Recommended reading order

1. [Installation](installation.md)
2. [Running with Docker](docker-usage.md)
3. [API Reference](api.md)
4. [Reproducibility Notes](reproduction.md)
5. [Troubleshooting](troubleshooting.md)

