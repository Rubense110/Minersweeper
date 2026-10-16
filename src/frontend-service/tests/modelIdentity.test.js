import { test } from 'node:test'
import assert from 'node:assert/strict'
import { modelIdentity } from '../src/modelIdentity.js'

test('solution labels use the stored model hash, never metrics or pipeline fingerprint', () => {
  const hash = 'abcde12345' + 'f'.repeat(54)
  const item = { model_semantic_sha256: hash, fingerprint: 'different pipeline', metrics: { fitness: 1 } }
  assert.deepEqual(modelIdentity(item, 569), { modelDigest: hash, shortDigest: 'abcde12345', label: 'Solution #569 abcde12345' })
  assert.equal(modelIdentity({ ...item, fingerprint: 'other', metrics: { fitness: 0 } }, 570).shortDigest, 'abcde12345')
})
test('different full hashes sharing a short prefix remain distinguishable', () => {
  const first = { model_semantic_sha256: 'a'.repeat(10) + '1' + 'f'.repeat(53) }
  const second = { model_semantic_sha256: 'a'.repeat(10) + '2' + 'f'.repeat(53) }
  assert.notEqual(modelIdentity(first, 1, [first, second]).shortDigest, modelIdentity(second, 2, [first, second]).shortDigest)
  assert.equal(modelIdentity(first, 1, [first, first]).shortDigest.length, 10)
})
test('legacy models explicitly show a missing digest rather than inventing an identity', () => {
  assert.equal(modelIdentity({ fingerprint: 'pipeline' }, 4).label, 'Solution #4 (sin digest)')
  assert.equal(modelIdentity({ model_semantic_sha256: 'invalid' }, 5).modelDigest, null)
})
