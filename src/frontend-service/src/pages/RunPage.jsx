import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createOptimization, listExperiments, listLogs, listOptimizations } from '../api'
import FancySelect from '../components/FancySelect'

const METRIC_OPTIONS = [
  { value: 'fitness', label: 'fitness' },
  { value: 'precision', label: 'precision' },
  { value: 'simplicity', label: 'simplicity' },
  { value: 'generalisation', label: 'generalisation' },
  { value: 'places', label: 'places' },
  { value: 'transitions', label: 'transitions' },
  { value: 'arcs', label: 'arcs' },
  { value: 't_edges', label: 't_edges' },
  { value: 'cycl_complx', label: 'cycl_complex' },
  { value: 'cfc', label: 'cfc' },
  { value: 'elc', label: 'elc' },
  { value: 'ratio', label: 'ratio' },
  { value: 'joins', label: 'joins' },
  { value: 'splits', label: 'splits' },
]
const DEFAULT_SELECTED_METRICS = ['fitness', 'precision', 'simplicity', 'generalisation']
const CONFORMANCE_MODE_OPTIONS = [
  { value: 'alignment', label: 'Alignments' },
  { value: 'replay', label: 'Replay' },
  { value: 'replay-token', label: 'Token replay' },
]
const DEFAULT_LOG_PREFERENCE = 'BPI_Challenge_2013_closed_problems.xes'
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

function pickDefaultLog(logs, currentValue) {
  if (currentValue && logs.includes(currentValue)) return currentValue
  if (logs.includes(DEFAULT_LOG_PREFERENCE)) return DEFAULT_LOG_PREFERENCE
  return logs[0] || ''
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
  const [maxEvaluations, setMaxEvaluations] = useState(100)
  const [populationSize, setPopulationSize] = useState(20)
  const [nWorkers, setNWorkers] = useState(HW_CONCURRENCY)
  const [conformanceMode, setConformanceMode] = useState('replay')
  const [selectedMetrics, setSelectedMetrics] = useState(DEFAULT_SELECTED_METRICS)
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
        if (normalized.length) setLogPath((previous) => pickDefaultLog(normalized, previous))
      } catch (_primaryError) {
        try {
          const [fromDb, fromJobs] = await Promise.all([listExperiments(), listOptimizations()])
          if (!active) return
          const dbPaths = (fromDb.experiments || []).map((item) => toRelativeLogPath(item.log_path))
          const jobPaths = (fromJobs.jobs || []).map((item) => toRelativeLogPath(item.request?.log_path))
          const fallbackLogs = uniqueSorted([...dbPaths, ...jobPaths])
          setAvailableLogs(fallbackLogs)
          if (fallbackLogs.length) setLogPath((previous) => pickDefaultLog(fallbackLogs, previous))
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
        throw new Error('You must select a log')
      }
      if (selectedMetrics.length === 0) {
        throw new Error('Select at least one metric')
      }
      const parsedMaxEvaluations = parsePositiveInt(maxEvaluations)
      if (!parsedMaxEvaluations) {
        throw new Error('Max evaluations must be an integer greater than or equal to 1')
      }
      const parsedPopulationSize = parsePositiveInt(populationSize)
      if (!parsedPopulationSize) {
        throw new Error('Population size must be an integer greater than or equal to 1')
      }
      const parsedWorkers = parsePositiveInt(nWorkers)
      if (!parsedWorkers) {
        throw new Error('Workers must be an integer greater than or equal to 1')
      }
      if (!CONFORMANCE_MODE_OPTIONS.some((option) => option.value === conformanceMode)) {
        throw new Error('Invalid conformance mode')
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
      setError(submitError.message || 'Could not create optimization')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="page run-page">
      <section className="card card-wide run-card">
        <h2>New Experiment</h2>

        <form className="form run-form" onSubmit={onSubmit}>
          <div className="run-grid">
            <label className="span-2">
              Experiment name
              <input
                onChange={(event) => setExecutionName(event.target.value)}
                placeholder="run_001"
                required
                value={executionName}
              />
            </label>

            <label>
              Log
              <FancySelect
                ariaLabel="Select log"
                disabled={loadingLogs || availableLogs.length === 0}
                onChange={setLogPath}
                options={availableLogs.map((item) => ({ value: item, label: item }))}
                placeholder={loadingLogs ? 'Loading logs...' : 'No logs detected'}
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
                ariaLabel="Select conformance mode"
                onChange={setConformanceMode}
                options={CONFORMANCE_MODE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                value={conformanceMode}
              />
            </label>
          </div>

          <fieldset className="metric-fieldset">
            <legend>Metrics</legend>
            <div className="metric-options">
              {METRIC_OPTIONS.map((metric) => (
                <label className="metric-choice" key={metric.value}>
                  <input
                    checked={selectedMetrics.includes(metric.value)}
                    onChange={() => toggleMetric(metric.value)}
                    type="checkbox"
                  />
                  {metric.label}
                </label>
              ))}
            </div>
            {hasNoMetrics ? <p className="error">Select at least one metric.</p> : null}
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

          <div className="run-form-meta small muted">
            <span>Detected CPU cores: {HW_CONCURRENCY}</span>
            <span>{loadingLogs ? 'Scanning logs...' : `${availableLogs.length} logs detected`}</span>
          </div>

          {error ? <p className="error">{error}</p> : null}

          <button disabled={submitting || hasNoMetrics} type="submit">
            {submitting ? 'Launching...' : 'Start optimization'}
          </button>
        </form>
      </section>
    </main>
  )
}
