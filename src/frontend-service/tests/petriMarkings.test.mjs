import assert from 'node:assert/strict'
import test from 'node:test'
import { finalMarkingsFor, markingEntries, markingTokenMap, selectedFinalMarking } from '../src/petriMarkings.js'

const petri = {
  places: [{ id: 'p_start', label: 'Start' }, { id: 'p_a', label: 'A' }, { id: 'p_b', label: 'B' }],
  initial_marking: [{ place_id: 'p_start', tokens: 2 }],
  final_marking: [{ place_id: 'p_a', tokens: 1 }],
  final_markings: [
    [{ place_id: 'p_a', tokens: 1 }],
    [{ place_id: 'p_b', tokens: 3 }],
  ],
}

test('all final markings remain distinct and selectable', () => {
  assert.equal(finalMarkingsFor(petri).length, 2)
  assert.deepEqual(selectedFinalMarking(petri, 0), petri.final_markings[0])
  assert.deepEqual(selectedFinalMarking(petri, 1), petri.final_markings[1])
  assert.equal(markingTokenMap(selectedFinalMarking(petri, 1)).get('p_b'), 3)
  assert.equal(markingTokenMap(petri.initial_marking).get('p_start'), 2)
})

test('legacy representative and valid empty final are not treated as missing', () => {
  assert.deepEqual(finalMarkingsFor({ final_marking: [] }), [[]])
  assert.deepEqual(finalMarkingsFor({ final_marking: [{ place_id: 'p', tokens: 1 }] }), [[{ place_id: 'p', tokens: 1 }]])
  assert.deepEqual(finalMarkingsFor({ final_markings: [[]], final_marking: null }), [[]])
  assert.deepEqual(finalMarkingsFor({}), [])
})

test('marking entries retain place ids and multiplicities', () => {
  assert.deepEqual(markingEntries(petri.initial_marking, petri.places), [
    { placeId: 'p_start', label: 'Start', tokens: 2 },
  ])
  assert.deepEqual(markingEntries([{ place_id: 'p_a', tokens: 0 }], petri.places), [])
})
