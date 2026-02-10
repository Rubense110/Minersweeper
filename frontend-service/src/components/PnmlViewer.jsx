import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'

function toArray(value) {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

function parsePnml(pnmlText) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(pnmlText, 'application/xml')

  const nodes = []
  const edges = []

  const placeEls = Array.from(doc.querySelectorAll('place'))
  const transEls = Array.from(doc.querySelectorAll('transition'))
  const arcEls = Array.from(doc.querySelectorAll('arc'))

  placeEls.forEach((el) => {
    const id = el.getAttribute('id') || `place-${Math.random()}`
    const labelNode = el.querySelector('name > text')
    const label = labelNode?.textContent?.trim() || id
    nodes.push({ data: { id, label, kind: 'place' } })
  })

  transEls.forEach((el) => {
    const id = el.getAttribute('id') || `transition-${Math.random()}`
    const labelNode = el.querySelector('name > text')
    const label = labelNode?.textContent?.trim() || id
    nodes.push({ data: { id, label, kind: 'transition' } })
  })

  arcEls.forEach((el, index) => {
    const source = el.getAttribute('source')
    const target = el.getAttribute('target')
    if (!source || !target) return
    edges.push({ data: { id: `e-${index}-${source}-${target}`, source, target } })
  })

  return { nodes, edges }
}

export default function PnmlViewer({ pnml }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  const elements = useMemo(() => {
    if (!pnml) return { nodes: [], edges: [] }
    try {
      return parsePnml(pnml)
    } catch (_error) {
      return { nodes: [], edges: [] }
    }
  }, [pnml])

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
      },
    })

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [elements])

  if (!pnml) {
    return <div className="pnml-empty">No PNML available for this solution.</div>
  }

  if (!elements.nodes.length) {
    return <div className="pnml-empty">Invalid or unsupported PNML content.</div>
  }

  return <div className="pnml-canvas" ref={containerRef} />
}
