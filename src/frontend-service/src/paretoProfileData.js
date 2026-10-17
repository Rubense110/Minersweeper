export function objectiveMetricKeys(solutions, metricOrder) {
  if (Array.isArray(metricOrder) && metricOrder.length) return [...new Set(metricOrder.filter(Boolean))]
  return [...new Set(solutions.flatMap(solution => Object.keys(solution.metrics || {})))]
}

export function eligibleParetoSolutions(solutions) {
  return solutions.filter(solution => solution.isPareto && solution.optimizationFeasible !== false && solution.isFeasible !== false)
}
