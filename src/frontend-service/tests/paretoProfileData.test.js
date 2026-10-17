import { test } from 'node:test'
import assert from 'node:assert/strict'
import { objectiveMetricKeys, eligibleParetoSolutions } from '../src/paretoProfileData.js'

test('an empty Pareto never falls back to the full population', () => {
  assert.deepEqual(eligibleParetoSolutions([{ isPareto: false, isFeasible: true, optimizationFeasible: false }]), [])
})
test('constraints and semantic exclusion are respected even with a stale Pareto flag', () => {
  const valid = { isPareto: true, isFeasible: true, optimizationFeasible: true }
  assert.deepEqual(eligibleParetoSolutions([valid, { ...valid, optimizationFeasible: false }, { ...valid, isFeasible: false }]), [valid])
})
test('constraint-only metrics are not presented as objectives', () => {
  const rows = [{ metrics: { fitness: .8, precision: .9, places: 20 } }]
  assert.deepEqual(objectiveMetricKeys(rows, ['fitness', 'precision']), ['fitness', 'precision'])
  assert.deepEqual(objectiveMetricKeys(rows, []), ['fitness', 'precision', 'places'])
})
