import { test } from 'node:test'
import assert from 'node:assert/strict'
import { visibleExplorationGraph, originalIdsForBpmn } from '../src/explorationGraphData.js'
const nodes = ['A','B','C'].map(id => ({ id, support: 80, model_ids: ['m1', 'm2'] }))
const edge = (id, source, target, support, mids = ['m1']) => ({ id, source, target, support, model_ids: mids, sources: [{ model_id: 'm1', arc_ids: [id] }] })
test('BPMN highlights resolve only to known original Petri elements including contracted routing', () => {
  const graph = { nodes: [{ id: 'task', original_ids: { node_ids: ['t1'], arc_ids: [] } }], edges: [{ id: 'flow', original_ids: { node_ids: ['p1', 't1'], arc_ids: ['a1', 'a2'] } }] }
  assert.deepEqual(originalIdsForBpmn(graph, ['task', 'flow', 'unknown']), ['t1', 'p1', 'a1', 'a2'])
  assert.deepEqual(originalIdsForBpmn(null, ['task']), [])
})
test('high support retains real weaker context with its actual support and provenance', () => {
  const graph = { nodes, edges: [edge('ab','A','B',12),edge('bc','B','C',7),edge('ac','A','C',5)] }
  const result = visibleExplorationGraph(graph, { minSupport: 80, contextConnections: true })
  assert.deepEqual(result.edges.map(e=>e.id),['ab','bc'])
  assert.equal(result.hiddenEdges,1)
  for(const e of result.edges) {
    assert.equal(e.context,true)
    assert.equal(e.support,graph.edges.find(original=>original.id===e.id).support)
    assert.equal(e.sources,graph.edges.find(original=>original.id===e.id).sources)
  }
  assert.equal(visibleExplorationGraph(graph,{minSupport:80,contextConnections:true,allConnections:true}).edges.length,3)
})
test('individual filter and focused activity do not introduce unsupported paths', () => {
  const graph={nodes:[...nodes,{id:'D',support:80,model_ids:['m2']}],edges:[edge('ab','A','B',12),edge('cd','C','D',8,['m2'])]}
  const result=visibleExplorationGraph(graph,{modelId:'m1',onlyModel:true,focusId:'A',contextConnections:true})
  assert.deepEqual(result.nodes.map(n=>n.id),['A','B'])
  assert.deepEqual(result.edges.map(e=>e.id),['ab'])
  assert.equal(visibleExplorationGraph(graph,{minSupport:81}).nodes.length,0)
})
test('showing rare activities does not force every rare connection onto the canvas', () => {
  const graph={nodes,edges:[edge('ab','A','B',60),edge('bc','B','C',50),edge('ac','A','C',2)]}
  const result=visibleExplorationGraph(graph,{minSupport:1,connectionSupport:40,contextConnections:true})
  assert.deepEqual(result.edges.map(e=>e.id),['ab','bc'])
  assert.equal(result.hiddenEdges,1)
})
