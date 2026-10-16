import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import { markingTokenMap, selectedFinalMarking } from '../petriMarkings'

const NO_HIGHLIGHTS = []
const NO_LABELS = {}

function toArray(value) {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

function parseStoredPetri(petri, finalIndex, compactPlaces, nodeLabels) {
  if (!petri || typeof petri !== 'object') return { nodes: [], edges: [] }

  const initialTokens = markingTokenMap(petri.initial_marking)
  const finalTokens = markingTokenMap(selectedFinalMarking(petri, finalIndex))

  const placeNodes = Array.isArray(petri.places)
    ? petri.places.map((item, index) => {
        const id = item?.id || `place-${index + 1}`
        const label = nodeLabels[id] || (compactPlaces ? '' : item?.label || id)
        const tokenCount = initialTokens.get(id) || 0
        return {
          data: {
            id,
            label: tokenCount ? `${label}\n${tokenCount === 1 ? '●' : tokenCount}` : label,
            kind: 'place',
            hasInitialTokens: tokenCount > 0,
            hasFinalTokens: (finalTokens.get(id) || 0) > 0,
          },
        }
      })
    : []

  const transitionNodes = Array.isArray(petri.transitions)
    ? petri.transitions.map((item, index) => {
        const id = item?.id || `transition-${index + 1}`
        const isInvisible = item?.invisible === true || item?.is_invisible === true
        const label = nodeLabels[id] || (isInvisible ? '' : item?.label || id)
        const data = { id, label, kind: 'transition' }
        if (isInvisible) data.isInvisible = true
        return { data }
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
              weightLabel: item.weight > 1 ? `×${item.weight}` : '',
            },
          }
        })
        .filter(Boolean)
    : []

  return { nodes: [...placeNodes, ...transitionNodes], edges }
}

export default function PnmlViewer({ petri = null, selectedFinalIndex = 0, highlightedIds = NO_HIGHLIGHTS, boundaryIds = NO_HIGHLIGHTS, controls = false, compactPlaces = false, nodeLabels = NO_LABELS }) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  const elements = useMemo(() => parseStoredPetri(petri, selectedFinalIndex, compactPlaces, nodeLabels), [petri, selectedFinalIndex, compactPlaces, nodeLabels])

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
          selector: 'node[?hasInitialTokens]',
          style: {
            'background-color': '#d5ebff',
          },
        },
        {
          selector: 'node[?hasFinalTokens]',
          style: {
            'border-color': '#16845b',
            'border-width': 4,
          },
        },
        {
          selector: 'node[isInvisible]',
          style: {
            'background-color': '#777777',
            'border-width': 1,
            'border-color': '#333333',
          },
        },
        {
          selector: 'edge',
          style: {
            label: 'data(weightLabel)',
            'font-size': 11,
            width: 1.6,
            'line-color': '#444444',
            'target-arrow-color': '#444444',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
          },
        },
        {
          selector: '.fragment-boundary',
          style: { 'border-style': 'dashed', 'border-color': '#175c96', 'border-width': 3 },
        },
        {
          selector: '.source-highlight',
          style: {
            'border-color': '#df8714',
            'border-width': 4,
            'line-color': '#df8714',
            'target-arrow-color': '#df8714',
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

    const observer = new ResizeObserver(() => cyRef.current?.resize())
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [elements])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('source-highlight')
    highlightedIds.forEach(id => cy.getElementById(id).addClass('source-highlight'))
  }, [elements, highlightedIds])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('fragment-boundary')
    boundaryIds.forEach(id => cy.getElementById(id).addClass('fragment-boundary'))
  }, [elements, boundaryIds])

  if (!petri) {
    return <div className="pnml-empty">No Petri model is available for this solution.</div>
  }

  if (!elements.nodes.length) {
    return <div className="pnml-empty">Petri model is empty or not compatible.</div>
  }

  function zoom(factor) { const cy = cyRef.current; if (cy) cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }
  return <div>{controls && <div className="graph-toolbar"><span>● marking inicial · borde verde: marking final · barra gris: τ</span><div><button type="button" aria-label="Acercar Petri net" onClick={() => zoom(1.4)}>+</button><button type="button" aria-label="Alejar Petri net" onClick={() => zoom(1 / 1.4)}>−</button><button type="button" onClick={() => cyRef.current?.fit(undefined, 18)}>Encajar red</button></div></div>}<div className="pnml-canvas" ref={containerRef} /></div>
}
