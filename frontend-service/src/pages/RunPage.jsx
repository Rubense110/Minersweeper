import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createOptimization } from '../api'

const DEFAULT_LOG_PATH = 'BPI_Challenge_2013_open_problems.xes'
const HW_CONCURRENCY =
  typeof navigator !== 'undefined' && Number.isFinite(navigator.hardwareConcurrency)
    ? Math.max(1, Math.floor(navigator.hardwareConcurrency))
    : 1
const DEFAULT_N_WORKERS = HW_CONCURRENCY

function normalizeWorkers(value) {
  const parsed = Number.parseInt(String(value), 10)
  if (!Number.isFinite(parsed)) {
    return 1
  }
  return Math.max(1, parsed)
}

export default function RunPage() {
  const navigate = useNavigate()
  const [executionName, setExecutionName] = useState(`run_${Date.now()}`)
  const [logPath, setLogPath] = useState(DEFAULT_LOG_PATH)
  const [maxEvaluations, setMaxEvaluations] = useState(50)
  const [populationSize, setPopulationSize] = useState(20)
  const [nWorkers, setNWorkers] = useState(DEFAULT_N_WORKERS)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      const job = await createOptimization({
        execution_name: executionName,
        log_path: logPath,
        max_evaluations: Number(maxEvaluations),
        population_size: Number(populationSize),
        n_workers: normalizeWorkers(nWorkers),
        excluded_miners: ['ilp', 'hybrid_ilp'],
        //metrics: ['simplicity']
      })
      navigate(`/results/${job.job_id}`)
    } catch (submitError) {
      setError(submitError.message || 'Failed to create optimization job')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="page">
      <section className="card card-wide">
        <h1>Minersweeper Front</h1>
        <p className="muted">Launch a simple optimization run and track it.</p>

        <form className="form" onSubmit={onSubmit}>
          <label>
            Execution Name
            <input
              value={executionName}
              onChange={(event) => setExecutionName(event.target.value)}
              required
              placeholder="run_001"
            />
          </label>

          <label>
            Log Path
            <input
              value={logPath}
              onChange={(event) => setLogPath(event.target.value)}
              required
              placeholder="BPI_Challenge_2013_open_problems.xes"
            />
          </label>

          <div className="row">
            <label>
              Max Evaluations
              <input
                type="number"
                min="1"
                value={maxEvaluations}
                onChange={(event) => setMaxEvaluations(event.target.value)}
                required
              />
            </label>

            <label>
              Population Size
              <input
                type="number"
                min="1"
                value={populationSize}
                onChange={(event) => setPopulationSize(event.target.value)}
                required
              />
            </label>
          </div>

          <label>
            Parallel Workers
            <input
              type="number"
              min="1"
              value={nWorkers}
              onChange={(event) => setNWorkers(normalizeWorkers(event.target.value))}
              required
            />
          </label>
          <p className="small muted">
            Detected logical cores in browser: {HW_CONCURRENCY}. Backend will clamp to the server limit.
          </p>

          {error ? <p className="error">{error}</p> : null}

          <button disabled={submitting} type="submit">
            {submitting ? 'Starting...' : 'Start Optimization'}
          </button>
        </form>
      </section>
    </main>
  )
}
