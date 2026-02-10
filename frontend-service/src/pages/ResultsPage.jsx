import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getArtifacts, getEventsUrl, getOptimization, getSolutions } from '../api'
import PnmlViewer from '../components/PnmlViewer'

export default function ResultsPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [solutions, setSolutions] = useState([])
  const [artifactsById, setArtifactsById] = useState({})
  const [selectedEvalId, setSelectedEvalId] = useState('')
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!jobId) return undefined

    let active = true
    let stream = null
    let finalLoaded = false

    async function loadCompletedData() {
      if (finalLoaded || !active) return
      finalLoaded = true
      const solutionPayload = await getSolutions(jobId, 'pareto')
      if (!active) return
      const list = solutionPayload.solutions || []
      setSolutions(list)

      const artifactsPayload = await getArtifacts(jobId, 'pareto', true)
      if (!active) return
      const map = {}
      for (const artifact of artifactsPayload.artifacts || []) {
        map[artifact.evaluation_id] = artifact
      }
      setArtifactsById(map)

      const firstWithId = list.find((item) => item.evaluation_id)
      if (firstWithId?.evaluation_id) {
        setSelectedEvalId(firstWithId.evaluation_id)
      }
    }

    function toJsonSafe(raw) {
      try {
        return JSON.parse(raw)
      } catch (_error) {
        return null
      }
    }

    async function bootstrap() {
      try {
        const current = await getOptimization(jobId)
        if (!active) return
        setJob(current)
        setProgress(current.progress || null)

        if (current.status === 'completed') {
          await loadCompletedData()
          return
        }
        if (current.status === 'failed') {
          setError(current?.error?.message || 'Optimization failed')
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
              await loadCompletedData()
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'Failed to load completed job')
            }
          } else if (payload.status === 'failed') {
            stream?.close()
            try {
              const latest = await getOptimization(jobId)
              if (!active) return
              setJob(latest)
              setProgress(latest.progress || null)
              setError(latest?.error?.message || 'Optimization failed')
            } catch (loadError) {
              if (!active) return
              setError(loadError.message || 'Optimization failed')
            }
          }
        })

        stream.addEventListener('progress', (event) => {
          if (!active) return
          const payload = toJsonSafe(event.data)
          if (!payload) return
          setProgress(payload)
        })

        stream.addEventListener('error', (event) => {
          if (!active) return
          const payload = toJsonSafe(event.data)
          if (!payload?.message) return
          setError(payload.message)
        })
      } catch (loadError) {
        if (!active) return
        setError(loadError.message || 'Failed to load job status')
      }
    }

    bootstrap()

    return () => {
      active = false
      if (stream) stream.close()
    }
  }, [jobId])

  const selectedSolution = useMemo(
    () => solutions.find((solution) => solution.evaluation_id === selectedEvalId) || null,
    [solutions, selectedEvalId]
  )

  const selectedArtifact = selectedEvalId ? artifactsById[selectedEvalId] : null

  return (
    <main className="page">
      <section className="card">
        <div className="header-row">
          <h1>Optimization Results</h1>
          <Link className="link-button" to="/">
            New Run
          </Link>
        </div>

        <p className="muted">Job: <code>{jobId}</code></p>

        {job ? (
          <div className="status-box">
            <p>
              <strong>Status:</strong> {job.status}
            </p>
            <p>
              <strong>Execution:</strong> {job.request?.execution_name || '-'}
            </p>
            <p>
              <strong>Finished:</strong> {job.finished_at || '-'}
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
          <p>Loading job status...</p>
        )}

        {error ? <p className="error">{error}</p> : null}

        {job?.status === 'running' || job?.status === 'queued' ? (
          <p>Waiting for optimization updates (SSE)...</p>
        ) : null}

        {job?.status === 'completed' ? (
          <>
            <h2>Pareto Solutions ({solutions.length})</h2>
            {solutions.length === 0 ? <p>No solutions returned.</p> : null}

            <div className="solutions-grid">
              <aside className="solutions-list">
                {solutions.map((solution, index) => {
                  const evalId = solution.evaluation_id || `solution-${index}`
                  return (
                    <button
                      className={evalId === selectedEvalId ? 'solution-item active' : 'solution-item'}
                      key={evalId}
                      onClick={() => setSelectedEvalId(solution.evaluation_id || '')}
                      type="button"
                    >
                      <div><strong>{solution.evaluation_id || `No eval id #${index + 1}`}</strong></div>
                      <div className="small muted">{solution.pipeline?.miner?.variant || '-'}</div>
                      <div className="small">fitness: {solution.metrics?.fitness ?? '-'}</div>
                      <div className="small">precision: {solution.metrics?.precision ?? '-'}</div>
                    </button>
                  )
                })}
              </aside>

              <section className="solution-detail">
                {selectedSolution ? (
                  <>
                    <h3>Selected Solution</h3>
                    <pre className="json-box">{JSON.stringify(selectedSolution, null, 2)}</pre>

                    <h3>Discovered Model (PNML)</h3>
                    <PnmlViewer pnml={selectedArtifact?.pnml || ''} />
                  </>
                ) : (
                  <p>Select a solution.</p>
                )}
              </section>
            </div>
          </>
        ) : null}
      </section>
    </main>
  )
}
