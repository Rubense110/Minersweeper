import { useMemo } from 'react'
import ExplorationGraph from './ExplorationGraph'
const EMPTY_LABELS = {}

export default function BpmnViewer({ graph, modelId, highlightedIds = [], boundaryIds = [], nodeLabels = EMPTY_LABELS }) {
  const displayed = useMemo(() => ({
    nodes: (graph?.nodes || []).map(n => ({ ...n, label: nodeLabels[n.id] || n.label, support: 1, common: false, model_ids: [modelId] })),
    edges: (graph?.edges || []).map(e => ({ ...e, support: 1, common: false, model_ids: [modelId] })),
  }), [graph, modelId, nodeLabels])
  return <ExplorationGraph graph={displayed} populationSize={1} highlightedIds={highlightedIds} boundaryIds={boundaryIds} showSupport={false} representation="bpmn" />
}
