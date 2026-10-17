import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseConstraints, formatConstraint } from '../src/optimizationConstraints.js'

test('constraint thresholds accept zero and preserve strict operators', () => {
  assert.deepEqual(parseConstraints([{ metric: 'fitness', operator: '>', value: '0' }]), [{ metric: 'fitness', operator: '>', value: 0 }])
  assert.deepEqual(parseConstraints([]), [])
})
test('empty, malformed and infinite thresholds are rejected before submission', () => {
  for (const value of ['', ' ', '1x', 'NaN', 'Infinity']) assert.throws(() => parseConstraints([{ metric: 'precision', operator: '>=', value }]))
  assert.throws(() => parseConstraints([{ metric: '', operator: '>=', value: '.8' }]))
})

test('nested OR and AND preserve alternatives and numeric leaf values', () => {
  const rows = [{ any: [{ metric: 'elc', operator: '<=', value: '137.5' }, { all: [
    { metric: 'cfc', operator: '>', value: '69' }, { metric: 'transitions', operator: '<=', value: '178' },
  ] }] }]
  const parsed = parseConstraints(rows)
  assert.equal(parsed[0].any[1].all[0].value, 69)
  assert.equal(rows[0].any[1].all[0].value, '69')
  assert.equal(formatConstraint(parsed[0]), '(elc <= 137.5 OR (cfc > 69 AND transitions <= 178))')
  assert.match(formatConstraint(parsed[0], { elc: 137.5 }), /actual: 137.5/)
})

test('groups reject empty, ambiguous, invalid and oversized trees', () => {
  for (const node of [{ any: [] }, { all: null }, { any: {}, all: [] }, { any: [], metric: 'elc' }, null]) {
    assert.throws(() => parseConstraints([node]))
  }
  let node = { metric: 'elc', operator: '<=', value: 137.5 }
  for (let i = 0; i < 9; i++) node = { all: [node] }
  assert.throws(() => parseConstraints([node]))
  assert.throws(() => parseConstraints(Array(257).fill({ metric: 'elc', operator: '<=', value: 137.5 })))
  assert.throws(() => parseConstraints([{ metric: 'elc', operator: '<=', value: true }]))
})
