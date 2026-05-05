import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'

function toArray(value) {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

function parseStoredPetri(petri) {
  if (!petri || typeof petri !== 'object') return { nodes: [], edges: [] }

  const placeNodes = Array.isArray(petri.places)
    ? petri.places.map((item, index) => {
        const id = item?.id || `place-${index + 1}`
        const label = item?.label || id
        return { data: { id, label, kind: 'place' } }
      })
    : []

  const transitionNodes = Array.isArray(petri.transitions)
    ? petri.transitions.map((item, index) => {
        const id = item?.id || `transition-${index + 1}`
        const label = item?.label || id
        return { data: { id, label, kind: 'transition' } }
      })
    : []

  const edges = Array.isArray(petri.arcs)
    ? petri.arcs
        .map((item, index) => {
          const source = item?.source
          const target = item?.target
          if (!source || !target) return null
          return {
            data: {
              id: item?.id || `arc-${index + 1}-${source}-${target}`,
              source,
              target,
            },
          }
        })
        .filter(Boolean)
    : []

  return { nodes: [...placeNodes, ...transitionNodes], edges }
}

export default function PnmlViewer({ petri = null }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  const elements = useMemo(() => parseStoredPetri(petri), [petri])

  useEffect(() => {
    if (!containerRef.current) return undefined

    if (cyRef.current) {
      cyRef.current.destroy()
      cyRef.current = null
    }

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: [...toArray(elements.nodes), ...toArray(elements.edges)],
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-size': 10,
            'text-wrap': 'wrap',
            'text-max-width': 90,
          },
        },
        {
          selector: 'node[kind = "place"]',
          style: {
            shape: 'ellipse',
            width: 28,
            height: 28,
            'background-color': '#ffffff',
            'border-width': 2,
            'border-color': '#111111',
          },
        },
        {
          selector: 'node[kind = "transition"]',
          style: {
            shape: 'round-rectangle',
            width: 20,
            height: 48,
            'background-color': '#111111',
            color: '#111111',
            'text-valign': 'bottom',
            'text-margin-y': 8,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.6,
            'line-color': '#444444',
            'target-arrow-color': '#444444',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
          },
        },
      ],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 18,
        spacingFactor: 1.2,
        // Rotate the top-to-bottom breadthfirst result into left-to-right.
        transform(_node, position) {
          return { x: position.y, y: position.x }
        },
      },
    })

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [elements])

  if (!petri) {
    return <div className="pnml-empty">No Petri model is available for this solution.</div>
  }

  if (!elements.nodes.length) {
    return <div className="pnml-empty">Petri model is empty or not compatible.</div>
  }

  return <div className="pnml-canvas" ref={containerRef} />
}
