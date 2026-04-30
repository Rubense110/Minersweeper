import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  cancelOptimization,
  downloadExperimentData,
  getExperiment,
  getExperimentSolutions,
  getEventsUrl,
  getOptimization,
  renderPetriImage,
  selectExperimentModel,
} from '../api'
import ParetoFrontScatter from '../components/ParetoFrontScatter'
import PnmlViewer from '../components/PnmlViewer'

function isCancelableStatus(status) {
  return status === 'queued' || status === 'running'
}

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
    solutionId,
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
        <strong>Variant:</strong> {variant}
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
        <p className="small muted">No parameters</p>
      )}
    </article>
  )
}

function objectiveGroupingKey(objectives, precision = 8) {
  if (!Array.isArray(objectives)) return '[]'
  return objectives
    .map((value) => {
      if (typeof value === 'number' && Number.isFinite(value)) {
        return value.toFixed(precision)
      }
      return String(value)
    })
    .join('|')
}

function runtimeSortValue(value) {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return value
  }
  return Number.MAX_SAFE_INTEGER
}

function sortSolutionsByRuntime(items) {
  return [...items].sort((a, b) => {
    const delta = runtimeSortValue(a.runtimeMs) - runtimeSortValue(b.runtimeMs)
    if (delta !== 0) return delta
    return String(a.id).localeCompare(String(b.id))
  })
}

function buildSolutionGroups(items) {
  const groupsByObjectives = new Map()

  for (const solution of items) {
    const objectivesKey = objectiveGroupingKey(solution.objectives)
    const existing = groupsByObjectives.get(objectivesKey)
    if (existing) {
      existing.solutions.push(solution)
      continue
    }
    groupsByObjectives.set(objectivesKey, {
      id: objectivesKey,
      objectives: Array.isArray(solution.objectives) ? [...solution.objectives] : [],
      solutions: [solution],
    })
  }

  const groups = [...groupsByObjectives.values()].map((group) => {
    const sortedSolutions = sortSolutionsByRuntime(group.solutions)
    const best = sortedSolutions[0] || null
    const paretoCount = sortedSolutions.filter((solution) => solution.isPareto).length
    const uniquePipelines = new Set(sortedSolutions.map((solution) => JSON.stringify(solution.pipeline || {}))).size

    return {
      id: group.id,
      objectives: group.objectives,
      solutions: sortedSolutions,
      best,
      size: sortedSolutions.length,
      paretoCount,
      uniquePipelines,
      bestRuntimeMs: best ? runtimeSortValue(best.runtimeMs) : Number.MAX_SAFE_INTEGER,
    }
  })

  groups.sort((a, b) => {
    const runtimeDelta = a.bestRuntimeMs - b.bestRuntimeMs
    if (runtimeDelta !== 0) return runtimeDelta
    const sizeDelta = b.size - a.size
    if (sizeDelta !== 0) return sizeDelta
    return a.id.localeCompare(b.id)
  })

  return groups
}

function formatRuntime(value) {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return `${value} ms`
  }
  return '-'
}

function formatObjectiveValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number(value.toFixed(8)).toString()
  }
  return String(value)
}

function clampSliderValue(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 50
  return Math.min(100, Math.max(0, Math.round(parsed)))
}

function hasRenderablePetri(petri) {
  if (!petri || typeof petri !== 'object') return false
  const places = Array.isArray(petri.places) ? petri.places : []
  const transitions = Array.isArray(petri.transitions) ? petri.transitions : []
  return places.length > 0 || transitions.length > 0
}

export default function ResultsPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [solutions, setSolutions] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [selectedSolutionId, setSelectedSolutionId] = useState('')
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')
  const [solutionsListMaxHeight, setSolutionsListMaxHeight] = useState(null)
  const [petriViewMode, setPetriViewMode] = useState('interactive')
  const [petriImageUrl, setPetriImageUrl] = useState('')
  const [petriImageLoading, setPetriImageLoading] = useState(false)
  const [petriImageError, setPetriImageError] = useState('')
  const [cancelPending, setCancelPending] = useState(false)
  const [downloadPending, setDownloadPending] = useState(false)
  const [modelWeights, setModelWeights] = useState({})
  const [modelSelectionPending, setModelSelectionPending] = useState(false)
  const [modelSelectionError, setModelSelectionError] = useState('')
  const [modelSelectionResult, setModelSelectionResult] = useState(null)
  const [modelPetriViewMode, setModelPetriViewMode] = useState('interactive')
  const [modelPetriImageUrl, setModelPetriImageUrl] = useState('')
  const [modelPetriImageLoading, setModelPetriImageLoading] = useState(false)
  const [modelPetriImageError, setModelPetriImageError] = useState('')
  const solutionDetailRef = useRef(null)
  const petriImageUrlRef = useRef('')
  const modelPetriImageUrlRef = useRef('')

  function replacePetriImageUrl(nextUrl) {
    if (petriImageUrlRef.current) {
      URL.revokeObjectURL(petriImageUrlRef.current)
    }
    petriImageUrlRef.current = nextUrl
    setPetriImageUrl(nextUrl)
  }

  function replaceModelPetriImageUrl(nextUrl) {
    if (modelPetriImageUrlRef.current) {
      URL.revokeObjectURL(modelPetriImageUrlRef.current)
    }
    modelPetriImageUrlRef.current = nextUrl
    setModelPetriImageUrl(nextUrl)
  }

  useEffect(() => {
    if (!jobId) return undefined

    let active = true
    let stream = null
    const autoRefreshKey = `results:auto-refresh:${jobId}`

    function wasAutoRefreshed() {
      try {
        return window.sessionStorage.getItem(autoRefreshKey) === '1'
      } catch (_error) {
        return false
      }
    }

    function markAutoRefreshed() {
      try {
        window.sessionStorage.setItem(autoRefreshKey, '1')
      } catch (_error) {
        // Ignore storage failures.
      }
    }

    function clearAutoRefreshMark() {
      try {
        window.sessionStorage.removeItem(autoRefreshKey)
      } catch (_error) {
        // Ignore storage failures.
      }
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
        setError(loadError.message || 'Could not load historical experiment')
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
          setCancelPending(false)
          clearAutoRefreshMark()
          await loadDbDataWithRetry(jobId)
          return
        }

        if (current.status === 'failed') {
          setCancelPending(false)
          clearAutoRefreshMark()
          setError(current?.error?.message || 'Optimization failed')
          return
        }

        if (current.status === 'cancelled') {
          setCancelPending(false)
          clearAutoRefreshMark()
          return
        }

        stream = new EventSource(getEventsUrl(jobId))

        stream.addEventListener('status_changed', async (event) => {
          if (!active) return
          const payload = toJsonSafe(event.data)
          if (!payload) return
          setJob((previous) => ({ ...(previous || {}), status: payload.status }))

          if (payload.status === 'completed') {
            setCancelPending(false)
            if (!wasAutoRefreshed()) {
              markAutoRefreshed()
              window.location.reload()
              return
            }
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              clearAutoRefreshMark()
              await loadDbDataWithRetry(jobId)
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'Could not load final results')
            }
          } else if (payload.status === 'failed') {
            setCancelPending(false)
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              clearAutoRefreshMark()
              setError(latest?.error?.message || 'Optimization failed')
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'Optimization failed')
            }
          } else if (payload.status === 'cancelled') {
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              clearAutoRefreshMark()
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'Optimization cancelled')
            } finally {
              if (active) setCancelPending(false)
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
        setError(loadError.message || 'Could not load experiment')
      }
    }

    bootstrap()
    return () => {
      active = false
      if (stream) stream.close()
    }
  }, [jobId])

  async function handleCancel() {
    if (!jobId || !isCancelableStatus(job?.status) || cancelPending) return
    setError('')
    setCancelPending(true)
    try {
      const payload = await cancelOptimization(jobId)
      setJob((previous) => ({ ...(previous || {}), status: payload.status || 'cancelling' }))
      setProgress((previous) =>
        previous
          ? {
              ...previous,
              status: payload.status || 'cancelling',
            }
          : previous
      )
    } catch (cancelError) {
      setError(cancelError.message || 'Could not cancel experiment')
      setCancelPending(false)
    }
  }

  async function handleDownloadData() {
    if (!jobId || job?.status !== 'completed' || downloadPending) return
    setError('')
    setDownloadPending(true)
    try {
      const { blob, filename } = await downloadExperimentData(jobId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError(downloadError.message || 'Could not download experiment data')
    } finally {
      setDownloadPending(false)
    }
  }

  const solutionGroups = useMemo(() => buildSolutionGroups(solutions), [solutions])

  useEffect(() => {
    setSelectedGroupId((previous) => {
      if (previous && solutionGroups.some((group) => group.id === previous)) return previous
      return solutionGroups[0]?.id || ''
    })
  }, [solutionGroups])

  const selectedGroup = useMemo(
    () => solutionGroups.find((group) => group.id === selectedGroupId) || null,
    [solutionGroups, selectedGroupId]
  )

  useEffect(() => {
    if (!selectedGroup) {
      setSelectedSolutionId('')
      return
    }
    setSelectedSolutionId((previous) => {
      if (previous && selectedGroup.solutions.some((solution) => solution.id === previous)) {
        return previous
      }
      return selectedGroup.solutions[0]?.id || ''
    })
  }, [selectedGroup])

  const selectedSolution = useMemo(() => {
    if (!selectedGroup) return null
    return selectedGroup.solutions.find((item) => item.id === selectedSolutionId) || selectedGroup.solutions[0] || null
  }, [selectedGroup, selectedSolutionId])

  const preferredMetricOrder = useMemo(() => {
    if (!Array.isArray(job?.request?.metrics)) return []
    return job.request.metrics
  }, [job])

  const weightedSelectedSolution = useMemo(() => {
    if (!modelSelectionResult?.selected_solution_id) return null
    return solutions.find((solution) => solution.solutionId === modelSelectionResult.selected_solution_id) || null
  }, [modelSelectionResult, solutions])

  useEffect(() => {
    setModelWeights((previous) => {
      const next = {}
      preferredMetricOrder.forEach((metric) => {
        next[metric] = clampSliderValue(previous[metric])
      })
      return next
    })
  }, [preferredMetricOrder])

  function handleWeightChange(metric, value) {
    setModelSelectionError('')
    setModelSelectionResult(null)
    replaceModelPetriImageUrl('')
    setModelPetriImageError('')
    setModelPetriImageLoading(false)
    setModelWeights((previous) => ({
      ...previous,
      [metric]: clampSliderValue(value),
    }))
  }

  function handleResetWeights() {
    setModelSelectionError('')
    setModelSelectionResult(null)
    replaceModelPetriImageUrl('')
    setModelPetriImageError('')
    setModelPetriImageLoading(false)
    setModelWeights(
      preferredMetricOrder.reduce((acc, metric) => {
        acc[metric] = 50
        return acc
      }, {})
    )
  }

  async function handleSelectModel() {
    if (!jobId || preferredMetricOrder.length === 0 || modelSelectionPending) return

    setModelSelectionError('')
    setModelSelectionPending(true)
    try {
      const payload = await selectExperimentModel(jobId, {
        scope: 'pareto',
        weights: modelWeights,
      })
      setModelSelectionResult(payload)

      const selected = solutions.find((solution) => solution.solutionId === payload.selected_solution_id)
      if (selected) {
        setSelectedGroupId(objectiveGroupingKey(selected.objectives))
        setSelectedSolutionId(selected.id)
      }
    } catch (selectionError) {
      setModelSelectionError(selectionError.message || 'Could not select model')
    } finally {
      setModelSelectionPending(false)
    }
  }

  useEffect(() => {
    return () => {
      if (petriImageUrlRef.current) {
        URL.revokeObjectURL(petriImageUrlRef.current)
        petriImageUrlRef.current = ''
      }
      if (modelPetriImageUrlRef.current) {
        URL.revokeObjectURL(modelPetriImageUrlRef.current)
        modelPetriImageUrlRef.current = ''
      }
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadPetriImage() {
      if (petriViewMode !== 'image') {
        setPetriImageLoading(false)
        setPetriImageError('')
        return
      }
      if (!selectedSolution || !hasRenderablePetri(selectedSolution.petri)) {
        replacePetriImageUrl('')
        setPetriImageLoading(false)
        setPetriImageError('No renderable Petri model for this solution.')
        return
      }

      setPetriImageLoading(true)
      setPetriImageError('')
      try {
        const blob = await renderPetriImage(
          {
            places: selectedSolution.petri.places || [],
            transitions: selectedSolution.petri.transitions || [],
            arcs: selectedSolution.petri.arcs || [],
          },
          'svg'
        )
        if (cancelled) return
        const imageUrl = URL.createObjectURL(blob)
        replacePetriImageUrl(imageUrl)
      } catch (loadError) {
        if (cancelled) return
        replacePetriImageUrl('')
        setPetriImageError(loadError.message || 'Could not generate PM4Py image.')
      } finally {
        if (!cancelled) setPetriImageLoading(false)
      }
    }

    loadPetriImage()
    return () => {
      cancelled = true
    }
  }, [petriViewMode, selectedSolution])

  useEffect(() => {
    let cancelled = false

    async function loadSelectedModelPetriImage() {
      if (modelPetriViewMode !== 'image') {
        setModelPetriImageLoading(false)
        setModelPetriImageError('')
        return
      }
      if (!weightedSelectedSolution || !hasRenderablePetri(weightedSelectedSolution.petri)) {
        replaceModelPetriImageUrl('')
        setModelPetriImageLoading(false)
        setModelPetriImageError('No renderable Petri model for the selected model.')
        return
      }

      setModelPetriImageLoading(true)
      setModelPetriImageError('')
      try {
        const blob = await renderPetriImage(
          {
            places: weightedSelectedSolution.petri.places || [],
            transitions: weightedSelectedSolution.petri.transitions || [],
            arcs: weightedSelectedSolution.petri.arcs || [],
          },
          'svg'
        )
        if (cancelled) return
        const imageUrl = URL.createObjectURL(blob)
        replaceModelPetriImageUrl(imageUrl)
      } catch (loadError) {
        if (cancelled) return
        replaceModelPetriImageUrl('')
        setModelPetriImageError(loadError.message || 'Could not generate PM4Py image.')
      } finally {
        if (!cancelled) setModelPetriImageLoading(false)
      }
    }

    loadSelectedModelPetriImage()
    return () => {
      cancelled = true
    }
  }, [modelPetriViewMode, weightedSelectedSolution])

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
  }, [selectedGroupId, selectedSolutionId, solutionGroups.length, job?.status])

  return (
    <main className="page">
      <section className="card">
        <div className="header-row">
          <h2>Results Breakdown</h2>
          <div className="inline-actions">
            <Link className="link-button" to="/run">
              New Experiment
            </Link>
            <Link className="link-button secondary" to="/history">
              History
            </Link>
            {job?.status === 'completed' ? (
              <button className="link-button secondary" disabled={downloadPending} onClick={handleDownloadData} type="button">
                {downloadPending ? 'Preparing...' : 'Download Data'}
              </button>
            ) : null}
            {isCancelableStatus(job?.status) ? (
              <button className="link-button danger" disabled={cancelPending} onClick={handleCancel} type="button">
                {cancelPending ? 'Cancelling...' : 'Cancel'}
              </button>
            ) : null}
          </div>
        </div>

        <p className="small muted">
          ID: <code>{jobId}</code>
        </p>

        {job ? (
          <div className="status-box">
            <p>
              <strong>Status:</strong> {job.status}
            </p>
            <p>
              <strong>Experiment:</strong> {job.request?.execution_name || '-'}
            </p>
            <p>
              <strong>Log:</strong> {job.request?.log_path || '-'}
            </p>
            <p>
              <strong>Start:</strong> {toLocalDate(job.started_at || job.created_at)} | <strong>End:</strong>{' '}
              {toLocalDate(job.finished_at)}
            </p>
            <p>
              <strong>Metrics:</strong>{' '}
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
          <p>Loading experiment details...</p>
        )}

        {error ? <p className="error">{error}</p> : null}

        {job?.status === 'running' || job?.status === 'queued' ? <p>Waiting for SSE updates...</p> : null}
        {job?.status === 'cancelling' ? <p>Cancelling experiment...</p> : null}
        {job?.status === 'cancelled' ? <p>Experiment cancelled. No results were kept.</p> : null}

        {job?.status === 'completed' ? (
          <>
            <details className="weighted-selection-card weighted-selection-panel">
              <summary className="weighted-selection-summary">
                <div>
                  <h3>Weighted Model Selection</h3>
                </div>
                <div className="weighted-selection-summary-meta">
                  {modelSelectionResult?.selected_solution_id ? (
                    <span className="status-pill status-completed">
                      Selected: Solution #{modelSelectionResult.selected_solution_id}
                    </span>
                  ) : null}
                  <span className="weighted-selection-chevron" aria-hidden="true">
                    ▾
                  </span>
                </div>
              </summary>

              <div className="weighted-selection-content">
                {preferredMetricOrder.length > 0 ? (
                  <>
                    <div className="weight-slider-grid">
                      {preferredMetricOrder.map((metric) => (
                        <label className="weight-slider-card" key={metric}>
                          <div className="weight-slider-header">
                            <span>{metric}</span>
                            <span className="weight-slider-value">{modelWeights[metric] ?? 50}</span>
                          </div>
                          <input
                            max="100"
                            min="0"
                            onChange={(event) => handleWeightChange(metric, event.target.value)}
                            step="1"
                            type="range"
                            value={modelWeights[metric] ?? 50}
                          />
                        </label>
                      ))}
                    </div>

                    <div className="inline-actions">
                      <button disabled={modelSelectionPending} onClick={handleSelectModel} type="button">
                        {modelSelectionPending ? 'Submitting...' : 'Submit'}
                      </button>
                      <button className="link-button secondary" onClick={handleResetWeights} type="button">
                        Reset Weights
                      </button>
                    </div>

                    {modelSelectionError ? <p className="error">{modelSelectionError}</p> : null}
                    {modelSelectionResult ? (
                      <div className="selection-summary small muted">
                        <p>
                          <strong>Scope:</strong> Pareto front | <strong>Candidates considered:</strong>{' '}
                          {modelSelectionResult.candidate_count ?? 0} | <strong>Scalarized objective:</strong>{' '}
                          {formatObjectiveValue(modelSelectionResult.scalarized_objective)}
                        </p>
                        <p>
                          <strong>Normalized weights:</strong>{' '}
                          {preferredMetricOrder
                            .map((metric) => {
                              const value = modelSelectionResult.normalized_weights?.[metric]
                              return `${metric}: ${formatMetricValue(value ?? 0)}`
                            })
                            .join(' | ')}
                        </p>
                      </div>
                    ) : null}

                    {weightedSelectedSolution ? (
                      <div className="weighted-selection-preview">
                        <div className="header-row">
                          <div>
                            <h4>Selected Model Preview</h4>
                            <p className="small muted">{weightedSelectedSolution.label}</p>
                          </div>
                        </div>

                        <div className="petri-view-toggle" role="group" aria-label="Selected model visualization mode">
                          <button
                            className={modelPetriViewMode === 'interactive' ? 'petri-view-button active' : 'petri-view-button'}
                            onClick={() => setModelPetriViewMode('interactive')}
                            type="button"
                          >
                            Interactive
                          </button>
                          <button
                            className={modelPetriViewMode === 'image' ? 'petri-view-button active' : 'petri-view-button'}
                            onClick={() => setModelPetriViewMode('image')}
                            type="button"
                          >
                            PM4Py image
                          </button>
                        </div>

                        {modelPetriViewMode === 'interactive' ? (
                          <PnmlViewer petri={weightedSelectedSolution.petri} />
                        ) : (
                          <div className="petri-image-panel">
                            {modelPetriImageLoading ? <p className="small muted">Generating model image...</p> : null}
                            {modelPetriImageError ? <p className="error">{modelPetriImageError}</p> : null}
                            {!modelPetriImageLoading && !modelPetriImageError && modelPetriImageUrl ? (
                              <img alt="Selected model rendered with PM4Py" className="petri-image" src={modelPetriImageUrl} />
                            ) : null}
                          </div>
                        )}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <p className="small muted">No metrics were recorded for this experiment, so weighting is unavailable.</p>
                )}
              </div>
            </details>

            <h3>Groups by objectives ({solutionGroups.length})</h3>
            <p className="small muted">Total recorded solutions: {solutions.length}</p>
            {solutions.length === 0 ? <p>No solutions recorded for this experiment.</p> : null}

            <div className="solutions-grid">
              <aside
                className="solutions-list"
                style={solutionsListMaxHeight ? { maxHeight: `${solutionsListMaxHeight}px` } : undefined}
              >
                {solutionGroups.map((group, index) => {
                  const metricEntries = orderedMetricEntries(group.best?.metrics || {}, preferredMetricOrder)
                  return (
                    <button
                      className={group.id === selectedGroupId ? 'solution-item active group-item' : 'solution-item group-item'}
                      key={group.id}
                      onClick={() => setSelectedGroupId(group.id)}
                      type="button"
                    >
                      <div className="header-row">
                        <strong>Group #{index + 1}</strong>
                        {group.paretoCount > 0 ? <span className="pareto-tag">pareto: {group.paretoCount}</span> : null}
                      </div>
                      <div className="small muted">
                        {group.size} solutions | {group.uniquePipelines} pipelines | best runtime:{' '}
                        {formatRuntime(group.best?.runtimeMs)}
                      </div>
                      <div className="small muted">
                        Objectives: [{group.objectives.map((value) => formatObjectiveValue(value)).join(', ')}]
                      </div>
                      {metricEntries.length > 0 ? (
                        <div className="solution-metric-lines small">
                          {metricEntries.map(([key, value]) => (
                            <span className="solution-metric-chip" key={key}>
                              {key}: {formatMetricValue(value)}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </button>
                  )
                })}
              </aside>

              <section className="solution-detail" ref={solutionDetailRef}>
                {selectedGroup && selectedSolution ? (
                  <>
                    <h3>Group details</h3>
                    <p>
                      <strong>Solutions in group:</strong> {selectedGroup.size} | <strong>Distinct pipelines:</strong>{' '}
                      {selectedGroup.uniquePipelines} | <strong>Best runtime:</strong> {formatRuntime(selectedGroup.best?.runtimeMs)}
                    </p>
                    <p>
                      <strong>Group objectives:</strong>{' '}
                      [{selectedGroup.objectives.map((value) => formatObjectiveValue(value)).join(', ')}]
                    </p>

                    <ParetoFrontScatter
                      metricOrder={preferredMetricOrder}
                      selectedSolutionIds={selectedGroup.solutions.map((solution) => solution.id)}
                      solutions={solutions}
                    />

                    <h4>Group solutions (sorted by runtime)</h4>
                    <div className="group-member-list">
                      {selectedGroup.solutions.map((solution) => (
                        <button
                          className={solution.id === selectedSolutionId ? 'group-member-item active' : 'group-member-item'}
                          key={solution.id}
                          onClick={() => setSelectedSolutionId(solution.id)}
                          type="button"
                        >
                          <span>{solution.label}</span>
                          <span className="small muted">{formatRuntime(solution.runtimeMs)}</span>
                        </button>
                      ))}
                    </div>

                    <h3>Solution details</h3>
                    <p>
                      <strong>Runtime (ms):</strong> {selectedSolution.runtimeMs === null ? '-' : selectedSolution.runtimeMs}
                    </p>

                    <h4>Metrics</h4>
                    {hasAnyMetric(selectedSolution) ? (
                      <ul className="metric-list">
                        {orderedMetricEntries(selectedSolution.metrics, preferredMetricOrder).map(([key, value]) => (
                          <li key={key}>
                            <strong>{key}:</strong> {formatMetricValue(value)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>No metrics associated.</p>
                    )}

                    <h4>Pipeline</h4>
                    <div className="pipeline-summary">
                      <PipelineSection node={selectedSolution.pipeline?.preprocessing} title="Preprocessing" />
                      <PipelineSection node={selectedSolution.pipeline?.miner} title="Miner" />
                    </div>

                    <h4>Petri model</h4>
                    <div className="petri-view-toggle" role="group" aria-label="Petri model visualization mode">
                      <button
                        className={petriViewMode === 'interactive' ? 'petri-view-button active' : 'petri-view-button'}
                        onClick={() => setPetriViewMode('interactive')}
                        type="button"
                      >
                        Interactive
                      </button>
                      <button
                        className={petriViewMode === 'image' ? 'petri-view-button active' : 'petri-view-button'}
                        onClick={() => setPetriViewMode('image')}
                        type="button"
                      >
                        PM4Py image
                      </button>
                    </div>

                    {petriViewMode === 'interactive' ? (
                      <PnmlViewer petri={selectedSolution.petri} />
                    ) : (
                      <div className="petri-image-panel">
                        {petriImageLoading ? <p className="small muted">Generating model image...</p> : null}
                        {petriImageError ? <p className="error">{petriImageError}</p> : null}
                        {!petriImageLoading && !petriImageError && petriImageUrl ? (
                          <img alt="Petri model rendered with PM4Py" className="petri-image" src={petriImageUrl} />
                        ) : null}
                      </div>
                    )}

                    <details className="technical-details">
                      <summary>View technical data</summary>

                      <h4>Pipeline (raw)</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.pipeline || {}, null, 2)}</pre>

                      <h4>Objectives</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.objectives || [], null, 2)}</pre>

                      <h4>Variables</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.variables || [], null, 2)}</pre>

                      <h4>Petri model (raw)</h4>
                      <pre className="json-box">{JSON.stringify(selectedSolution.petri || {}, null, 2)}</pre>
                    </details>
                  </>
                ) : (
                  <p>Select a group to view details.</p>
                )}
              </section>
            </div>
          </>
        ) : null}
      </section>
    </main>
  )
}
