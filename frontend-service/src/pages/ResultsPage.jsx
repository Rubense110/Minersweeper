import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getExperiment, getExperimentSolutions, getEventsUrl, getOptimization } from '../api'
import PnmlViewer from '../components/PnmlViewer'

function toLocalDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function toJsonSafe(raw) {
  try {
    return JSON.parse(raw)
  } catch (_error) {
    return null
  }
}

function metricPairsFromObjectives(objectives, metricsOrder) {
  if (!Array.isArray(objectives) || objectives.length === 0) return {}
  const pairs = {}
  objectives.forEach((objective, index) => {
    const key = metricsOrder[index] || `objective_${index + 1}`
    if (typeof objective === 'number' && Number.isFinite(objective)) {
      pairs[key] = Number((-objective).toFixed(6))
    } else {
      pairs[key] = objective
    }
  })
  return pairs
}

function mapDbSolution(item, index, metricsOrder) {
  const solutionId = item.solution_id || index + 1
  return {
    id: `db-${solutionId}`,
    label: `Solution #${solutionId}`,
    pipeline: item.pipeline || {},
    runtimeMs: item.runtime_ms ?? null,
    metrics: metricPairsFromObjectives(item.objectives, metricsOrder),
    objectives: Array.isArray(item.objectives) ? item.objectives : [],
    variables: Array.isArray(item.variables) ? item.variables : [],
    isPareto: Boolean(item.is_pareto),
    petri: {
      places: Array.isArray(item.places) ? item.places : [],
      transitions: Array.isArray(item.transitions) ? item.transitions : [],
      arcs: Array.isArray(item.arcs) ? item.arcs : [],
    },
  }
}

function hasAnyMetric(solution) {
  return solution && solution.metrics && Object.keys(solution.metrics).length > 0
}

function formatMetricValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number(value.toFixed(6)).toString()
  }
  return String(value)
}

function orderedMetricEntries(metrics, preferredOrder) {
  const entries = Object.entries(metrics || {})
  if (entries.length === 0) return []

  const rank = new Map((preferredOrder || []).map((metric, index) => [metric, index]))
  return entries.sort(([a], [b]) => {
    const rankA = rank.has(a) ? rank.get(a) : Number.MAX_SAFE_INTEGER
    const rankB = rank.has(b) ? rank.get(b) : Number.MAX_SAFE_INTEGER
    if (rankA !== rankB) return rankA - rankB
    return a.localeCompare(b)
  })
}

function formatPipelineParamValue(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number' && Number.isFinite(value)) return Number(value.toFixed(6)).toString()
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function PipelineSection({ title, node }) {
  const variant = node?.variant || node?.key || node?.family || '-'
  const params =
    node && typeof node.parameters === 'object' && !Array.isArray(node.parameters)
      ? Object.entries(node.parameters)
      : []

  return (
    <article className="pipeline-card">
      <p className="small muted">{title}</p>
      <p>
        <strong>Variante:</strong> {variant}
      </p>
      {params.length > 0 ? (
        <ul className="pipeline-param-list">
          {params.map(([key, value]) => (
            <li key={key}>
              <span>{key}</span>
              <code>{formatPipelineParamValue(value)}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p className="small muted">Sin parámetros</p>
      )}
    </article>
  )
}

export default function ResultsPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [solutions, setSolutions] = useState([])
  const [selectedSolutionId, setSelectedSolutionId] = useState('')
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')
  const [solutionsListMaxHeight, setSolutionsListMaxHeight] = useState(null)
  const solutionDetailRef = useRef(null)

  useEffect(() => {
    if (!jobId) return undefined

    let active = true
    let stream = null

    function keepOrPickFirst(mapped) {
      setSelectedSolutionId((previous) => {
        if (previous && mapped.some((item) => item.id === previous)) return previous
        return mapped.length > 0 ? mapped[0].id : ''
      })
    }

    async function loadDbData(experimentId, options = {}) {
      const { allowEmpty = true } = options
      const [experimentPayload, solutionsPayload] = await Promise.all([
        getExperiment(experimentId),
        getExperimentSolutions(experimentId, 'all'),
      ])
      if (!active) return 0

      const mapped = (solutionsPayload.solutions || []).map((item, index) =>
        mapDbSolution(item, index, experimentPayload.metrics || [])
      )

      if (!allowEmpty && mapped.length === 0) {
        return 0
      }

      setJob({
        job_id: experimentPayload.experiment_id,
        status: 'completed',
        created_at: experimentPayload.start_at,
        started_at: experimentPayload.start_at,
        finished_at: experimentPayload.end_at,
        request: {
          execution_name: experimentPayload.experiment_name,
          log_path: experimentPayload.log_path,
          metrics: experimentPayload.metrics || [],
          discover: {
            max_evaluations: experimentPayload.max_evals,
            population_size: experimentPayload.pop_size,
            n_workers: experimentPayload.workers,
          },
        },
      })
      setProgress({
        job_id: experimentPayload.experiment_id,
        status: 'completed',
        evaluations_done: experimentPayload.max_evals || 0,
        max_evaluations: experimentPayload.max_evals || 0,
        percentage: 100,
      })
      setSolutions(mapped)
      keepOrPickFirst(mapped)
      return mapped.length
    }

    async function loadDbDataWithRetry(experimentId, attempts = 8, delayMs = 1200) {
      let lastError = null
      for (let attempt = 0; attempt < attempts; attempt += 1) {
        if (!active) return
        try {
          const isLast = attempt === attempts - 1
          const count = await loadDbData(experimentId, { allowEmpty: isLast })
          if (count > 0 || isLast) return
        } catch (error) {
          lastError = error
        }
        if (attempt < attempts - 1) {
          await new Promise((resolve) => {
            setTimeout(resolve, delayMs)
          })
        }
      }

      if (lastError) throw lastError
    }

    async function loadHistoricalExperiment() {
      try {
        await loadDbData(jobId, { allowEmpty: true })
      } catch (loadError) {
        if (!active) return
        setError(loadError.message || 'No se pudo cargar el experimento histórico')
      }
    }

    async function bootstrap() {
      try {
        setError('')
        const current = await getOptimization(jobId)
        if (!active) return
        setJob(current)
        setProgress(current.progress || null)

        if (current.status === 'completed') {
          await loadDbDataWithRetry(jobId)
          return
        }

        if (current.status === 'failed') {
          setError(current?.error?.message || 'La optimización falló')
          return
        }

        stream = new EventSource(getEventsUrl(jobId))

        stream.addEventListener('status_changed', async (event) => {
          if (!active) return
          const payload = toJsonSafe(event.data)
          if (!payload) return
          setJob((previous) => ({ ...(previous || {}), status: payload.status }))

          if (payload.status === 'completed') {
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              await loadDbDataWithRetry(jobId)
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'No se pudieron cargar los resultados finales')
            }
          } else if (payload.status === 'failed') {
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              setError(latest?.error?.message || 'La optimización falló')
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'La optimización falló')
            }
          }
        })

        stream.addEventListener('progress', (event) => {
          if (!active) return
          const payload = toJsonSafe(event.data)
          if (!payload) return
          setProgress(payload)
        })

        stream.addEventListener('error', () => {
          if (!active) return
        })
      } catch (loadError) {
        if (!active) return
        if (loadError?.status === 404) {
          await loadHistoricalExperiment()
          return
        }
        setError(loadError.message || 'No se pudo cargar el experimento')
      }
    }

    bootstrap()
    return () => {
      active = false
      if (stream) stream.close()
    }
  }, [jobId])

  const selectedSolution = useMemo(
    () => solutions.find((item) => item.id === selectedSolutionId) || null,
    [solutions, selectedSolutionId]
  )

  const preferredMetricOrder = useMemo(() => {
    if (!Array.isArray(job?.request?.metrics)) return []
    return job.request.metrics
  }, [job])

  useEffect(() => {
    if (!solutionDetailRef.current) return undefined

    let frameId = 0
    const detailElement = solutionDetailRef.current

    function syncListHeight() {
      cancelAnimationFrame(frameId)
      frameId = requestAnimationFrame(() => {
        if (typeof window !== 'undefined' && window.matchMedia('(max-width: 980px)').matches) {
          setSolutionsListMaxHeight((previous) => (previous === null ? previous : null))
          return
        }
        const nextHeight = Math.max(0, Math.round(detailElement.getBoundingClientRect().height))
        const normalized = nextHeight > 0 ? nextHeight : null
        setSolutionsListMaxHeight((previous) => (previous === normalized ? previous : normalized))
      })
    }

    syncListHeight()

    let observer = null
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => {
        syncListHeight()
      })
      observer.observe(detailElement)
    }

    window.addEventListener('resize', syncListHeight)

    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('resize', syncListHeight)
      if (observer) observer.disconnect()
    }
  }, [selectedSolutionId, solutions.length, job?.status])

  return (
    <main className="page">
      <section className="card">
        <div className="header-row">
          <h2>Desglose de resultados</h2>
          <div className="inline-actions">
            <Link className="link-button" to="/run">
              Nuevo experimento
            </Link>
            <Link className="link-button secondary" to="/history">
              Historial
            </Link>
          </div>
        </div>

        <p className="small muted">
          ID: <code>{jobId}</code>
        </p>

        {job ? (
          <div className="status-box">
            <p>
              <strong>Estado:</strong> {job.status}
            </p>
            <p>
              <strong>Experimento:</strong> {job.request?.execution_name || '-'}
            </p>
            <p>
              <strong>Log:</strong> {job.request?.log_path || '-'}
            </p>
            <p>
              <strong>Inicio:</strong> {toLocalDate(job.started_at || job.created_at)} | <strong>Fin:</strong>{' '}
              {toLocalDate(job.finished_at)}
            </p>
            <p>
              <strong>Métricas:</strong>{' '}
              {Array.isArray(job.request?.metrics) && job.request.metrics.length
                ? job.request.metrics.join(', ')
                : 'default'}
            </p>
            <p>
              <strong>Progress:</strong>{' '}
              {progress ? `${progress.evaluations_done}/${progress.max_evaluations} (${progress.percentage}%)` : '-'}
            </p>
            {progress ? (
              <div className="progress-bar" aria-label="Optimization progress">
                <span style={{ width: `${Math.max(0, Math.min(100, progress.percentage || 0))}%` }} />
              </div>
            ) : null}
          </div>
        ) : (
          <p>Cargando detalle del experimento...</p>
        )}

        {error ? <p className="error">{error}</p> : null}

        {job?.status === 'running' || job?.status === 'queued' ? <p>Esperando actualizaciones SSE...</p> : null}

        {job?.status === 'completed' ? (
          <>
            <h3>Todas las soluciones ({solutions.length})</h3>
            {solutions.length === 0 ? <p>No hay soluciones registradas para este experimento.</p> : null}

            <div className="solutions-grid">
              <aside
                className="solutions-list"
                style={solutionsListMaxHeight ? { maxHeight: `${solutionsListMaxHeight}px` } : undefined}
              >
                {solutions.map((solution) => {
                  const metricEntries = orderedMetricEntries(solution.metrics, preferredMetricOrder)
                  return (
                    <button
                      className={solution.id === selectedSolutionId ? 'solution-item active' : 'solution-item'}
                      key={solution.id}
                      onClick={() => setSelectedSolutionId(solution.id)}
                      type="button"
                    >
                      <div className="header-row">
                        <strong>{solution.label}</strong>
                        {solution.isPareto ? <span className="pareto-tag">pareto</span> : null}
                      </div>
                      <div className="small muted">{solution.pipeline?.miner?.variant || '-'}</div>
                      {hasAnyMetric(solution) ? (
                        <div className="solution-metric-lines small">
                          {metricEntries.map(([key, value]) => (
                            <span className="solution-metric-chip" key={key}>
                              {key}: {formatMetricValue(value)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <div className="small muted">Sin métricas disponibles</div>
                      )}
                    </button>
                  )
                })}
              </aside>

              <section className="solution-detail" ref={solutionDetailRef}>
                {selectedSolution ? (
                  <>
                    <h3>Detalle individual</h3>
                    <p>
                      <strong>Runtime (ms):</strong> {selectedSolution.runtimeMs === null ? '-' : selectedSolution.runtimeMs}
                    </p>

                    <h4>Métricas</h4>
                    {hasAnyMetric(selectedSolution) ? (
                      <ul className="metric-list">
                        {orderedMetricEntries(selectedSolution.metrics, preferredMetricOrder).map(([key, value]) => (
                          <li key={key}>
                            <strong>{key}:</strong> {formatMetricValue(value)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>No hay métricas asociadas.</p>
                    )}

                    <h4>Pipeline</h4>
                    <div className="pipeline-summary">
                      <PipelineSection node={selectedSolution.pipeline?.preprocessing} title="Preprocessing" />
                      <PipelineSection node={selectedSolution.pipeline?.miner} title="Miner" />
                    </div>

                    <h4>Modelo Petri</h4>
                    <PnmlViewer petri={selectedSolution.petri} />

                    <details className="technical-details">
                      <summary>Ver datos técnicos</summary>

                      <h4>Pipeline (raw)</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.pipeline || {}, null, 2)}</pre>

                      <h4>Objetivos</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.objectives || [], null, 2)}</pre>

                      <h4>Variables</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.variables || [], null, 2)}</pre>

                      <h4>Modelo Petri (raw)</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.petri || {}, null, 2)}</pre>
                    </details>
                  </>
                ) : (
                  <p>Selecciona una solución para ver el detalle.</p>
                )}
              </section>
            </div>
          </>
        ) : null}
      </section>
    </main>
  )
}
