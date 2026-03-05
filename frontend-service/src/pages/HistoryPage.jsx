import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listExperiments, listOptimizations } from '../api'

function toLocalDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function normalizeDbExperiment(item) {
  return {
    id: item.experiment_id,
    name: item.experiment_name || item.experiment_id,
    status: 'completed',
    logPath: item.log_path || '-',
    metrics: Array.isArray(item.metrics) ? item.metrics : [],
    maxEvaluations: item.max_evals ?? '-',
    populationSize: item.pop_size ?? '-',
    workers: item.workers ?? '-',
    createdAt: item.start_at,
    finishedAt: item.end_at,
    counts: item.counts || { all_solutions: 0, pareto_solutions: 0 },
  }
}

function normalizeLiveJob(item) {
  const discover = item.request?.discover || {}
  const counts = item.result_summary?.counts || { all_solutions: 0, pareto_solutions: 0 }
  return {
    id: item.job_id,
    name: item.request?.execution_name || item.job_id,
    status: item.status || 'unknown',
    logPath: item.request?.log_path || '-',
    metrics: Array.isArray(item.request?.metrics) ? item.request.metrics : [],
    maxEvaluations: discover.max_evaluations ?? '-',
    populationSize: discover.population_size ?? '-',
    workers: discover.n_workers ?? '-',
    createdAt: item.created_at,
    finishedAt: item.finished_at,
    counts,
  }
}

export default function HistoryPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [source, setSource] = useState('db')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      setError('')
      try {
        const fromDb = await listExperiments()
        if (!active) return
        setSource('db')
        setItems((fromDb.experiments || []).map(normalizeDbExperiment))
      } catch (_dbError) {
        try {
          const fromLive = await listOptimizations()
          if (!active) return
          setSource('jobs')
          setItems((fromLive.jobs || []).map(normalizeLiveJob))
        } catch (loadError) {
          if (!active) return
          setError(loadError.message || 'Could not load history')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  return (
    <main className="page">
      <section className="card">
        <div className="header-row">
          <h2>Experiment History</h2>
          <p className="small muted">Source: {source === 'db' ? 'database' : 'in-memory jobs'}</p>
        </div>

        {loading ? <p>Loading history...</p> : null}
        {error ? <p className="error">{error}</p> : null}
        {!loading && !error && items.length === 0 ? <p>No saved experiments yet.</p> : null}

        <div className="history-grid">
          {items.map((item) => (
            <article className="history-card" key={item.id}>
              <div className="header-row">
                <h3>{item.name}</h3>
                <span className={`status-pill status-${item.status}`}>{item.status}</span>
              </div>

              <p className="small muted">{item.id}</p>
              <p><strong>Log:</strong> {item.logPath}</p>
              <p>
                <strong>Metrics:</strong> {item.metrics.length ? item.metrics.join(', ') : 'Default'}
              </p>
              <p>
                <strong>Evaluations:</strong> {item.maxEvaluations} | <strong>Population:</strong> {item.populationSize} |{' '}
                <strong>Workers:</strong> {item.workers}
              </p>
              <p>
                <strong>Solutions:</strong> {item.counts.all_solutions ?? 0} (pareto: {item.counts.pareto_solutions ?? 0})
              </p>
              <p className="small muted">
                Start: {toLocalDate(item.createdAt)} | End: {toLocalDate(item.finishedAt)}
              </p>

              <Link className="link-button" to={`/results/${item.id}`}>
                View Results
              </Link>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}
