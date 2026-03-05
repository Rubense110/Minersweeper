import { useMemo } from 'react'

function asFiniteNumber(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value
}

function metricOptionsFromSolutions(solutions, metricOrder) {
  const ordered = Array.isArray(metricOrder) ? metricOrder.filter(Boolean) : []
  const seen = new Set(ordered)

  for (const solution of solutions) {
    for (const key of Object.keys(solution.metrics || {})) {
      if (!seen.has(key)) {
        seen.add(key)
        ordered.push(key)
      }
    }
  }

  return ordered.map((key) => ({ value: key, label: key }))
}

function rangeFromValues(values) {
  if (!values.length) return { min: 0, max: 1 }
  let min = values[0]
  let max = values[0]
  for (const value of values) {
    if (value < min) min = value
    if (value > max) max = value
  }
  if (min === max) return { min: min - 1, max: max + 1 }
  return { min, max }
}

function normalize(value, range) {
  const size = range.max - range.min
  if (size === 0) return 0.5
  return (value - range.min) / size
}

export default function ParetoFrontScatter({ metricOrder = [], selectedSolutionIds = [], solutions = [] }) {
  const metricOptions = useMemo(() => metricOptionsFromSolutions(solutions, metricOrder), [solutions, metricOrder])
  const metricKeys = useMemo(() => metricOptions.map((item) => item.value), [metricOptions])
  const selectedIdsSet = useMemo(() => new Set(selectedSolutionIds), [selectedSolutionIds])

  const paretoSolutions = useMemo(() => {
    const onlyPareto = solutions.filter((item) => item.isPareto)
    return onlyPareto.length ? onlyPareto : solutions
  }, [solutions])

  const series = useMemo(() => {
    if (metricKeys.length === 0) return []
    return paretoSolutions
      .map((solution) => {
        const values = metricKeys.map((metric) => asFiniteNumber(solution.metrics?.[metric]))
        if (values.some((value) => value === null)) return null
        return {
          id: solution.id,
          label: solution.label,
          values,
          highlighted: selectedIdsSet.has(solution.id),
        }
      })
      .filter(Boolean)
  }, [paretoSolutions, metricKeys, selectedIdsSet])

  const yValues = useMemo(() => series.flatMap((item) => item.values), [series])
  const yRange = useMemo(() => rangeFromValues(yValues), [yValues])
  const maxMetricLabelLength = useMemo(
    () => metricKeys.reduce((max, key) => Math.max(max, String(key).length), 0),
    [metricKeys]
  )

  const width = 640
  const xLabelAngle = -32
  const projectedLabelDepth = maxMetricLabelLength * 6.6 * Math.sin((Math.abs(xLabelAngle) * Math.PI) / 180)
  const bottomPadding = Math.max(74, Math.min(180, Math.ceil(projectedLabelDepth + 24)))
  const height = 280 + bottomPadding
  const margin = { top: 20, right: 20, bottom: bottomPadding, left: 56 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const xStep = metricKeys.length > 1 ? plotWidth / (metricKeys.length - 1) : 0
  const gridLines = 4
  const xAt = (index) => margin.left + index * xStep
  const yAt = (value) => margin.top + (1 - normalize(value, yRange)) * plotHeight
  const xLabelY = margin.top + plotHeight + 14

  return (
    <details className="pareto-front-panel" open>
      <summary>Pareto Front (objective profile)</summary>

      {metricKeys.length === 0 ? (
        <p className="small muted">Not enough metrics to draw the front.</p>
      ) : (
        <>
          <div className="pareto-front-legend small muted">
            Series shown: {series.length} (pareto front) | highlighted from group: {series.filter((item) => item.highlighted).length}
          </div>

          {series.length === 0 ? (
            <p className="small muted">No solutions have all available metrics.</p>
          ) : (
            <svg
              aria-label="Pareto front profile plot"
              className="pareto-front-svg"
              role="img"
              viewBox={`0 0 ${width} ${height}`}
            >
              <rect
                fill="#ffffff"
                height={plotHeight}
                stroke="#d2d8d3"
                width={plotWidth}
                x={margin.left}
                y={margin.top}
              />

              {Array.from({ length: gridLines + 1 }).map((_, idx) => {
                const t = idx / gridLines
                const y = margin.top + t * plotHeight
                const value = yRange.max - t * (yRange.max - yRange.min)
                return (
                  <g key={`grid-${idx}`}>
                    <line
                      stroke="#e4e9e4"
                      strokeWidth="1"
                      x1={margin.left}
                      x2={margin.left + plotWidth}
                      y1={y}
                      y2={y}
                    />
                    <text className="pareto-axis-value" textAnchor="end" x={margin.left - 6} y={y + 4}>
                      {value.toFixed(4)}
                    </text>
                  </g>
                )
              })}

              {metricKeys.map((metric, index) => {
                const x = xAt(index)
                return (
                  <g key={metric}>
                    <line
                      stroke="#e8ece8"
                      strokeWidth="1"
                      x1={x}
                      x2={x}
                      y1={margin.top}
                      y2={margin.top + plotHeight}
                    />
                    <line
                      stroke="#6d7672"
                      strokeWidth="1.2"
                      x1={x}
                      x2={x}
                      y1={margin.top + plotHeight}
                      y2={margin.top + plotHeight + 6}
                    />
                    <text
                      className="pareto-axis-label"
                      textAnchor="end"
                      transform={`translate(${x + 5} ${xLabelY}) rotate(${xLabelAngle})`}
                    >
                      {metric}
                    </text>
                  </g>
                )
              })}

              <line
                stroke="#6d7672"
                strokeWidth="1.5"
                x1={margin.left}
                x2={margin.left + plotWidth}
                y1={margin.top + plotHeight}
                y2={margin.top + plotHeight}
              />
              <line
                stroke="#6d7672"
                strokeWidth="1.5"
                x1={margin.left}
                x2={margin.left}
                y1={margin.top}
                y2={margin.top + plotHeight}
              />

              {series.map((solution) => {
                const polyline = solution.values.map((value, index) => `${xAt(index)},${yAt(value)}`).join(' ')
                return (
                  <g key={solution.id}>
                    <polyline
                      fill="none"
                      opacity={solution.highlighted ? 0.9 : 0.26}
                      points={polyline}
                      stroke={solution.highlighted ? '#c75213' : '#0a7a80'}
                      strokeWidth={solution.highlighted ? 2.1 : 1.1}
                    />
                    {solution.values.map((value, index) => (
                      <circle
                        cx={xAt(index)}
                        cy={yAt(value)}
                        fill={solution.highlighted ? '#cf5d16' : '#0a7a80'}
                        key={`${solution.id}-${metricKeys[index]}`}
                        opacity={solution.highlighted ? 0.95 : 0.45}
                        r={solution.highlighted ? 3.4 : 2.1}
                      >
                        <title>{`${solution.label}: ${metricKeys[index]}=${value.toFixed(6)}`}</title>
                      </circle>
                    ))}
                  </g>
                )
              })}
            </svg>
          )}
        </>
      )}
    </details>
  )
}
