// Presentation only: retain every node, edge, source ID and model membership.
let engine
async function elk() {
  if (!engine) engine = import('elkjs/lib/elk.bundled.js').then(({ default: ELK }) => new ELK())
  return engine
}

export function bpmnNodeGeometry(node, annotation = node.label || '') {
  if (node.kind?.includes('gateway')) return { width: 48, height: 48, annotation }
  if (node.kind?.endsWith('_event')) return { width: 42, height: 42, annotation }
  const text = String(annotation).replace(/_/g, '_\u200b').replace(/\//g, '/\u200b')
  const longest = Math.max(1, ...text.split('\n').map(line => line.length))
  const width = Math.max(180, Math.min(248, longest * 8 + 28))
  const lines = text.split('\n').reduce((n, line) => n + Math.max(1, Math.ceil(line.length * 8 / (width - 28))), 0)
  return { width, height: Math.max(72, lines * 21 + 24), annotation: text }
}

export function routeCoordinates(source, target, section) {
  const dx = target.x - source.x, dy = target.y - source.y
  const length2 = dx * dx + dy * dy, length = Math.sqrt(length2)
  if (!length || !section) return null
  const bends = section.bendPoints || []
  return {
    weights: bends.map(p => ((p.x - source.x) * dx + (p.y - source.y) * dy) / length2),
    distances: bends.map(p => ((p.y - source.y) * dx - (p.x - source.x) * dy) / length),
    sourceEndpoint: `${section.startPoint.x - source.x}px ${section.startPoint.y - source.y}px`,
    targetEndpoint: `${section.endPoint.x - target.x}px ${section.endPoint.y - target.y}px`,
  }
}

export async function layoutBpmn(nodes, edges, direction = 'RIGHT') {
  const byId = new Map(nodes.map(n => [n.id, n])), successors = new Map(nodes.map(n => [n.id, []]))
  for (const e of edges) successors.get(e.source)?.push(e.target)
  const order = [], seen = new Set(), queue = nodes.filter(n => n.kind === 'start_event').map(n => n.id).sort()
  for (const id of [...queue, ...nodes.map(n => n.id).sort()]) {
    if (seen.has(id)) continue
    const frontier = [id]
    while (frontier.length) {
      const current = frontier.shift()
      if (seen.has(current)) continue
      seen.add(current); order.push(current)
      frontier.push(...successors.get(current).filter(id => !seen.has(id)).sort())
    }
  }
  const layout = await (await elk()).layout({
    id: 'bpmn',
    layoutOptions: {
      'elk.algorithm': 'layered', 'elk.direction': direction, 'elk.edgeRouting': 'ORTHOGONAL',
      'elk.spacing.nodeNode': '42', 'elk.layered.spacing.nodeNodeBetweenLayers': '64',
      'elk.spacing.edgeNode': '22', 'elk.layered.spacing.edgeNodeBetweenLayers': '22',
      'elk.spacing.edgeEdge': '14', 'elk.layered.spacing.edgeEdgeBetweenLayers': '14',
      'elk.layered.feedbackEdges': 'true', 'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.layered.cycleBreaking.strategy': 'DEPTH_FIRST',
      'elk.randomSeed': '1', 'elk.padding': '[top=40,left=40,bottom=40,right=40]',
    },
    children: order.map(id => {
      const n = byId.get(id)
      return { id: n.id, width: n.width, height: n.height,
        ...(n.kind === 'start_event' || n.kind === 'end_event' ? { layoutOptions: { 'elk.layered.layering.layerConstraint': n.kind === 'start_event' ? 'FIRST' : 'LAST' } } : {}) }
    }),
    edges: [...edges].sort((a, b) => a.id.localeCompare(b.id)).map(e => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  })
  const positions = Object.fromEntries(layout.children.map(n => [n.id, { x: n.x + n.width / 2, y: n.y + n.height / 2 }]))
  return { positions, routes: Object.fromEntries(layout.edges.map(e => [e.id, routeCoordinates(positions[e.sources[0]], positions[e.targets[0]], e.sections?.[0])])) }
}
