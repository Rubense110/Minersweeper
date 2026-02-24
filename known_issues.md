# Known Issues

## Context

- Proyecto: `Minersweeper`
- Ejecucion analizada: `run_1770747769987`
- Job API: `3f0b212d-1e0d-4388-a16f-8fd135bcc219`

## Insights Confirmados

1. `500` evaluaciones del optimizador no implican `500` artefactos persistidos.
- En este run se persistieron `428`.
- Diferencia explicable por cache hits y evaluaciones sin persistencia (errores/timeouts).

2. El reporte por delta temporal (`created_at_epoch_ms` entre evaluaciones consecutivas) identifica outliers, pero no siempre el pipeline culpable directo.
- Un delta grande puede reflejar tiempo consumido por la evaluacion previa o bloqueos en cadena.

3. Se valido con pruebas directas al servicio Java (`POST /pipeline`) usando pipelines sospechosos.
- 7 de 8 pipelines respondieron en ~`0.5s` a `2.3s` (HTTP 200).
- 1 pipeline fallo por timeout y es reproducible.

4. Pipeline problematico reproducible (timeout):
- `miner`: `hybrid_ilp` (`Hybrid ILPMiner`)
- `preprocessing`: `projection_filter`
- `source_evaluation_id`: `1770749165088-301`
- Resultado en prueba aislada:
  - 1/1 timeout a `130s` (test inicial)
  - 3/3 timeouts a `90s` (repeticion dedicada)

5. Señal adicional observada:
- Variantes lifecycle (`IMlc`, `IMflc`) muestran frecuentemente `precision=0` y `generalisation=0`.
- El log de ProM muestra repetidamente `life cycle repair not yet implemented` para esas variantes.

## Impacto

- Progreso aparentemente "congelado" durante optimizacion por evaluaciones que quedan bloqueadas hasta timeout.
- Variabilidad alta en tiempo de evaluacion entre pipelines.
- Calidad de metricas degradada en variantes lifecycle.

## Estado

- Problema principal reproducido y acotado en un pipeline `Hybrid ILPMiner + projection_filter`.
- Pendiente instrumentar tiempos por fase en Java (`discover`, `replay`, `precision/generalisation`) para localizar el cuello exacto.

