import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createOptimization } from '../api'

const DEFAULT_LOG_PATH = '/data/logs/BPI_Challenge_2013_open_problems.xes'

export default function RunPage() {
  const navigate = useNavigate()
  const [executionName, setExecutionName] = useState(`run_${Date.now()}`)
  const [logPath, setLogPath] = useState(DEFAULT_LOG_PATH)
  const [maxEvaluations, setMaxEvaluations] = useState(50)
  const [populationSize, setPopulationSize] = useState(20)
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
        n_workers: 1,
        excluded_miners: ['split', 'ilp', 'hybrid_ilp'],
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
              placeholder="/data/logs/BPI_Challenge_2013_open_problems.xes"
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

          {error ? <p className="error">{error}</p> : null}

          <button disabled={submitting} type="submit">
            {submitting ? 'Starting...' : 'Start Optimization'}
          </button>
        </form>
      </section>
    </main>
  )
}
