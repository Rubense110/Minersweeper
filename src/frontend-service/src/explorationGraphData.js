// Support filtering changes the display, never the population counts.
export function originalIdsForBpmn(graph, ids) {
  const selected = new Set(ids)
  return [...new Set([...(graph?.nodes || []), ...(graph?.edges || [])].filter(n => selected.has(n.id)).flatMap(n => [...(n.original_ids?.node_ids || []), ...(n.original_ids?.arc_ids || [])]))]
}

export function visibleExplorationGraph(graph, { minSupport = 1, modelId = '', onlyModel = false, contextConnections = false, connectionSupport = minSupport, allConnections = false, focusId = '' } = {}) {
  const eligible = item => !onlyModel || item.model_ids?.includes(modelId)
  let nodes = (graph?.nodes || []).filter(n => n.support >= minSupport && eligible(n))
  if (focusId) {
    const neighbours = new Set([focusId])
    for (const e of graph?.edges || []) if (eligible(e) && (e.source === focusId || e.target === focusId)) { neighbours.add(e.source); neighbours.add(e.target) }
    nodes = nodes.filter(n => neighbours.has(n.id))
  }
  const ids = new Set(nodes.map(n => n.id))
  const candidates = (graph?.edges || []).filter(e => ids.has(e.source) && ids.has(e.target) && eligible(e))
  if (!contextConnections || allConnections) return { nodes, edges: candidates, hiddenEdges: 0 }
  const retained = new Set(candidates.filter(e => e.support >= connectionSupport).map(e => e.id))
  // Retain real context when every incoming/outgoing connection is below the threshold.
  for (const node of nodes) for (const direction of ['source', 'target']) {
    const edges = candidates.filter(e => e[direction] === node.id).sort((a, b) => b.support - a.support || a.id.localeCompare(b.id))
    if (edges.length && !edges.some(e => retained.has(e.id))) retained.add(edges[0].id)
  }
  const edges = candidates.filter(e => retained.has(e.id)).map(e => ({ ...e, context: e.support < connectionSupport }))
  return { nodes, edges, hiddenEdges: candidates.length - edges.length }
}
