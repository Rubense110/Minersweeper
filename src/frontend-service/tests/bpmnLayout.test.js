import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bpmnNodeGeometry, layoutBpmn, routeCoordinates } from '../src/bpmnLayout.js'

const nodes = [{ id: 's', kind: 'start_event', label: 'Inicio' }, { id: 'a', kind: 'task', label: 'W_Completeren aanvraag' }, { id: 'b', kind: 'task', label: 'B' }, { id: 'e', kind: 'end_event', label: 'Fin' }].map(n => ({ ...n, ...bpmnNodeGeometry(n) }))
const edges = [{ id: 'sa', source: 's', target: 'a' }, { id: 'ab', source: 'a', target: 'b' }, { id: 'be', source: 'b', target: 'e' }, { id: 'ba', source: 'b', target: 'a' }]

test('cycles retain their edges, begin/end order and deterministic positions', async () => {
  const original = JSON.stringify({ nodes, edges })
  const first = await layoutBpmn(nodes, edges)
  assert.deepEqual(first, await layoutBpmn([...nodes].reverse(), [...edges].reverse()))
  assert.equal(JSON.stringify({ nodes, edges }), original)
  assert.deepEqual(Object.keys(first.routes).sort(), edges.map(e => e.id).sort())
  assert.ok(first.positions.s.x < first.positions.a.x && first.positions.a.x < first.positions.b.x && first.positions.b.x < first.positions.e.x)
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j], p = first.positions[a.id], q = first.positions[b.id]
    assert.ok(Math.abs(p.x - q.x) >= (a.width + b.width) / 2 || Math.abs(p.y - q.y) >= (a.height + b.height) / 2)
  }
})
test('vertical flow and disconnected individuals have finite coordinates', async () => {
  const all = [...nodes, { id: 'isolated', kind: 'task', width: 200, height: 72 }]
  const result = await layoutBpmn(all, edges, 'DOWN')
  assert.ok(result.positions.s.y < result.positions.a.y && result.positions.a.y < result.positions.b.y && result.positions.b.y < result.positions.e.y)
  for (const p of Object.values(result.positions)) assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y))
})
test('sequence-flow bends retain their actual coordinates, including return routes', () => {
  const source = { x: 20, y: 30 }, target = { x: 220, y: 130 }
  const section = { startPoint: { x: 40, y: 30 }, endPoint: { x: 200, y: 130 }, bendPoints: [{ x: 260, y: 30 }, { x: 260, y: -40 }, { x: 180, y: -40 }, { x: 180, y: 130 }] }
  const result = routeCoordinates(source, target, section), dx = 200, dy = 100, length = Math.hypot(dx, dy)
  for (let i = 0; i < section.bendPoints.length; i++) {
    assert.ok(Math.abs(source.x + result.weights[i] * dx - result.distances[i] * dy / length - section.bendPoints[i].x) < 1e-8)
    assert.ok(Math.abs(source.y + result.weights[i] * dy + result.distances[i] * dx / length - section.bendPoints[i].y) < 1e-8)
  }
  assert.equal(routeCoordinates(source, source, section), null)
})
test('task labels get larger boxes and wrapping without changing the source text', () => {
  const node = { label: 'W_Completeren_aanvraag', kind: 'task' }, original = node.label
  const geometry = bpmnNodeGeometry(node, node.label + '\n80/80')
  assert.ok(geometry.width >= 180 && geometry.height >= 72)
  assert.equal(geometry.annotation.replaceAll('\u200b', ''), original + '\n80/80')
  assert.equal(node.label, original)
})
