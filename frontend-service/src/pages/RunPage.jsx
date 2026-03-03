import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createOptimization, listExperiments, listLogs, listOptimizations } from '../api'
import FancySelect from '../components/FancySelect'

const METRIC_OPTIONS = ['fitness', 'precision', 'simplicity', 'generalisation']
const CONFORMANCE_MODE_OPTIONS = [
  { value: 'alignment', label: 'Alignments' },
  { value: 'replay', label: 'Replay' },
]
const HW_CONCURRENCY =
  typeof navigator !== 'undefined' && Number.isFinite(navigator.hardwareConcurrency)
    ? Math.max(1, Math.floor(navigator.hardwareConcurrency))
    : 1

function normalizeWorkers(value) {
  const parsed = Number.parseInt(String(value), 10)
  if (!Number.isFinite(parsed)) return 1
  return Math.max(1, parsed)
}

function parsePositiveInt(value) {
  const parsed = Number.parseInt(String(value), 10)
  if (!Number.isFinite(parsed) || parsed < 1) return null
  return parsed
}

function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b))
}

function toRelativeLogPath(value) {
  if (!value) return ''
  const normalized = String(value).trim().replace(/\\/g, '/')
  if (!normalized) return ''
  if (/^\/?data\/logs(\/|$)/i.test(normalized)) {
    const withoutRoot = normalized.replace(/^\/?data\/logs\/?/i, '')
    return withoutRoot.replace(/^\.?\//, '')
  }
  return normalized
}

export default function RunPage() {
  const navigate = useNavigate()
  const [executionName, setExecutionName] = useState(`run_${Date.now()}`)
  const [logPath, setLogPath] = useState('')
  const [availableLogs, setAvailableLogs] = useState([])
  const [maxEvaluations, setMaxEvaluations] = useState(50)
  const [populationSize, setPopulationSize] = useState(20)
  const [nWorkers, setNWorkers] = useState(HW_CONCURRENCY)
  const [conformanceMode, setConformanceMode] = useState('alignment')
  const [selectedMetrics, setSelectedMetrics] = useState([...METRIC_OPTIONS])
  const [submitting, setSubmitting] = useState(false)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    async function loadLogs() {
      setLoadingLogs(true)
      try {
        const payload = await listLogs()
        if (!active) return
        const normalized = uniqueSorted((payload.logs || []).map((item) => toRelativeLogPath(item)))
        setAvailableLogs(normalized)
        if (normalized.length) setLogPath((previous) => previous || normalized[0])
      } catch (_primaryError) {
        try {
          const [fromDb, fromJobs] = await Promise.all([listExperiments(), listOptimizations()])
          if (!active) return
          const dbPaths = (fromDb.experiments || []).map((item) => toRelativeLogPath(item.log_path))
          const jobPaths = (fromJobs.jobs || []).map((item) => toRelativeLogPath(item.request?.log_path))
          const fallbackLogs = uniqueSorted([...dbPaths, ...jobPaths])
          setAvailableLogs(fallbackLogs)
          if (fallbackLogs.length) setLogPath((previous) => previous || fallbackLogs[0])
        } catch (_fallbackError) {
          if (!active) return
          setAvailableLogs([])
        }
      } finally {
        if (active) setLoadingLogs(false)
      }
    }

    loadLogs()
    return () => {
      active = false
    }
  }, [])

  const hasNoMetrics = selectedMetrics.length === 0

  function toggleMetric(metric) {
    setSelectedMetrics((previous) => {
      if (previous.includes(metric)) {
        return previous.filter((item) => item !== metric)
      }
      return [...previous, metric]
    })
  }

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      if (!logPath.trim()) {
        throw new Error('Debes seleccionar un log')
      }
      if (selectedMetrics.length === 0) {
        throw new Error('Selecciona al menos una métrica')
      }
      const parsedMaxEvaluations = parsePositiveInt(maxEvaluations)
      if (!parsedMaxEvaluations) {
        throw new Error('Max evaluations debe ser un entero mayor o igual que 1')
      }
      const parsedPopulationSize = parsePositiveInt(populationSize)
      if (!parsedPopulationSize) {
        throw new Error('Population size debe ser un entero mayor o igual que 1')
      }
      const parsedWorkers = parsePositiveInt(nWorkers)
      if (!parsedWorkers) {
        throw new Error('Workers debe ser un entero mayor o igual que 1')
      }
      if (!CONFORMANCE_MODE_OPTIONS.some((option) => option.value === conformanceMode)) {
        throw new Error('Modo de conformance inválido')
      }
      const job = await createOptimization({
        execution_name: executionName.trim() || `run_${Date.now()}`,
        log_path: toRelativeLogPath(logPath),
        metrics: selectedMetrics,
        conformance_mode: conformanceMode,
        max_evaluations: parsedMaxEvaluations,
        population_size: parsedPopulationSize,
        n_workers: normalizeWorkers(parsedWorkers),
        excluded_miners: ['ilp', 'hybrid_ilp'],
      })
      navigate(`/results/${job.job_id}`)
    } catch (submitError) {
      setError(submitError.message || 'No se pudo crear la optimización')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="page run-page">
      <section className="card card-wide run-card">
        <h2>Nuevo experimento</h2>
        <p className="muted">Configura y lanza la optimización.</p>

        <form className="form run-form" onSubmit={onSubmit}>
          <div className="run-grid">
            <label className="span-2">
              Nombre del experimento
              <input
                onChange={(event) => setExecutionName(event.target.value)}
                placeholder="run_001"
                required
                value={executionName}
              />
            </label>

            <label>
              Log (volumen del servicio)
              <FancySelect
                ariaLabel="Seleccionar log"
                disabled={loadingLogs || availableLogs.length === 0}
                onChange={setLogPath}
                options={availableLogs.map((item) => ({ value: item, label: item }))}
                placeholder={loadingLogs ? 'Cargando logs...' : 'No hay logs detectados'}
                value={logPath}
              />
            </label>

            <label>
              Workers
              <input
                min="1"
                onChange={(event) => setNWorkers(normalizeWorkers(event.target.value))}
                required
                step="1"
                type="number"
                value={nWorkers}
              />
            </label>

            <label>
              Conformance mode
              <FancySelect
                ariaLabel="Seleccionar conformance mode"
                onChange={setConformanceMode}
                options={CONFORMANCE_MODE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                value={conformanceMode}
              />
            </label>
          </div>

          <p className="small muted">{loadingLogs ? 'Consultando logs...' : `${availableLogs.length} logs detectados`}</p>

          <fieldset className="metric-fieldset">
            <legend>Métricas</legend>
            <div className="metric-options">
              {METRIC_OPTIONS.map((metric) => (
                <label className="metric-choice" key={metric}>
                  <input checked={selectedMetrics.includes(metric)} onChange={() => toggleMetric(metric)} type="checkbox" />
                  {metric}
                </label>
              ))}
            </div>
            {hasNoMetrics ? <p className="error">Selecciona al menos una métrica.</p> : null}
          </fieldset>

          <div className="row row-compact">
            <label>
              Max evaluations
              <input
                min="1"
                onChange={(event) => setMaxEvaluations(event.target.value)}
                required
                step="1"
                type="number"
                value={maxEvaluations}
              />
            </label>

            <label>
              Population size
              <input
                min="1"
                onChange={(event) => setPopulationSize(event.target.value)}
                required
                step="1"
                type="number"
                value={populationSize}
              />
            </label>
          </div>

          <p className="small muted">Núcleos detectados: {HW_CONCURRENCY}</p>

          {error ? <p className="error">{error}</p> : null}

          <button disabled={submitting || hasNoMetrics} type="submit">
            {submitting ? 'Lanzando...' : 'Iniciar optimización'}
          </button>
        </form>
      </section>
    </main>
  )
}
