import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { visibleExplorationGraph } from '../explorationGraphData'
import { bpmnNodeGeometry, layoutBpmn } from '../bpmnLayout'

export default function ExplorationGraph({ graph, populationSize, modelId, minSupport = 1, onlyModel = false, onSelect, contextConnections = false, connectionSupport = minSupport, allConnections = false, focusId = '', highlightedIds = [], boundaryIds = [], showSupport = true, representation = 'petri' }) {
  const ref = useRef(null), cyRef = useRef(null), selectRef = useRef(onSelect)
  const isBpmn = representation === 'bpmn'
  const [layout, setLayout] = useState(isBpmn ? 'bpmn' : contextConnections ? 'grid' : 'breadthfirst')
  const [organizing, setOrganizing] = useState(false), [layoutError, setLayoutError] = useState('')
  const [hovered, setHovered] = useState(null), [zoomLevel, setZoomLevel] = useState(1)
  useEffect(() => setLayout(isBpmn ? 'bpmn' : contextConnections ? 'grid' : 'breadthfirst'), [contextConnections, isBpmn])
  selectRef.current = onSelect
  const filterModel = onlyModel ? modelId : ''
  const visible = useMemo(() => visibleExplorationGraph(graph, { minSupport, modelId: filterModel, onlyModel, contextConnections, connectionSupport, allConnections, focusId }), [graph, minSupport, filterModel, onlyModel, contextConnections, connectionSupport, allConnections, focusId])
  useEffect(() => {
    if (!ref.current || !graph) return undefined
    let disposed = false
    setHovered(null); setLayoutError('')
    const elements = [...visible.nodes, ...visible.edges].map(item => ({
      data: { ...item, annotation: contextConnections ? `${item.label}\n${item.support}/${populationSize}` : item.kind?.includes('gateway') || item.kind?.endsWith('_event') ? item.label : item.kind === 'place' || item.invisible ? '' : `${item.label || ''}${showSupport ? `\n${item.support}/${populationSize}` : ''}`,
        edgeLabel: item.kind === 'structural_path' ? `${item.support}/${populationSize}` : item.weight > 1 ? `×${item.weight}` : '' },
      classes: [item.common ? 'common' : 'variable', item.matching === 'ambiguous' ? 'uncertain' : '', item.context ? 'context' : ''].join(' '),
    }))
    if (isBpmn) for (const element of elements) if (!element.data.source) Object.assign(element.data, bpmnNodeGeometry(element.data, element.data.annotation))
    const cy = cytoscape({ container: ref.current, elements,
      style: [
        { selector: 'node', style: { label: 'data(annotation)', 'font-size': 12, 'text-wrap': 'wrap', 'text-max-width': 125, 'text-valign': 'bottom', 'text-margin-y': 6, 'background-color': '#d7eaf9', 'border-width': 2, 'border-color': '#376b99', color: '#17334c', width: 30, height: 30 } },
        { selector: 'node[kind = "place"]', style: { shape: 'ellipse', 'background-color': '#fff', width: 20, height: 20 } },
        { selector: 'node[kind = "transition"]', style: { shape: 'rectangle', width: 22, height: 42 } },
        { selector: 'node[?invisible]', style: { width: 13, height: 28, 'background-color': '#7a9aaf' } },
        { selector: 'node[kind = "task"]', style: { shape: 'round-rectangle', width: 145, height: 62, 'text-valign': 'center', 'text-margin-y': 0 } },
        { selector: 'node[kind = "exclusive_gateway"], node[kind = "parallel_gateway"]', style: { shape: 'diamond', width: 40, height: 40, 'text-valign': 'center', 'text-margin-y': 0, 'font-size': 24 } },
        { selector: 'node[kind = "start_event"], node[kind = "end_event"]', style: { shape: 'ellipse', width: 35, height: 35, 'font-size': 11 } },
        { selector: 'node[kind = "end_event"]', style: { 'border-width': 5 } },
        { selector: 'node[kind = "block"], node[kind = "alternative"]', style: { shape: 'round-rectangle', width: 145, height: 62, 'text-valign': 'center', 'text-margin-y': 0 } },
        ...(contextConnections ? [{ selector: 'node', style: { shape: 'round-rectangle', width: 145, height: 62, 'text-valign': 'center', 'text-margin-y': 0 } }] : []),
        ...(isBpmn ? [
          { selector: 'node', style: { width: 'data(width)', height: 'data(height)', 'font-size': 16, 'font-weight': 600, 'font-family': 'Arial, sans-serif', 'line-height': 1.2, 'text-max-width': n => n.data('width') - 28, 'text-valign': 'center', 'text-margin-y': 0, 'background-color': '#f3f8fd', 'border-color': '#24567c', color: '#102b43', 'min-zoomed-font-size': 0 } },
          { selector: 'node[kind = "exclusive_gateway"], node[kind = "parallel_gateway"]', style: { 'font-size': 28, 'text-max-width': 80 } },
          { selector: 'node[kind = "start_event"], node[kind = "end_event"]', style: { 'font-size': 13, 'text-valign': 'bottom', 'text-margin-y': 8, 'text-background-color': '#fff', 'text-background-opacity': 1, 'text-background-padding': 3 } },
        ] : []),
        { selector: 'edge', style: { label: 'data(edgeLabel)', 'font-size': 11, width: 2, 'line-color': '#79a6cb', 'target-arrow-color': '#79a6cb', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', color: '#234d70', 'text-background-color': '#fff', 'text-background-opacity': 0.95, 'text-background-padding': 3 } },
        { selector: '.common', style: { 'border-color': '#155994', 'line-color': '#155994', 'target-arrow-color': '#155994', 'border-width': 3 } },
        { selector: 'node.common', style: { 'background-color': '#155994', color: '#fff' } },
        { selector: '.uncertain', style: { 'border-style': 'dashed', 'border-color': '#9b6317' } },
        { selector: 'edge[kind = "interface"], edge.context', style: { 'line-style': 'dashed' } },
        { selector: 'edge.context', style: { 'line-color': '#b0bfcc', 'target-arrow-color': '#b0bfcc', width: 1.5 } },
        ...(isBpmn ? [
          { selector: 'edge', style: { width: 2, 'line-color': '#55758f', 'target-arrow-color': '#55758f', 'arrow-scale': 1.2, 'font-size': 13, 'line-cap': 'round' } },
          { selector: 'edge.common', style: { width: 3, 'line-color': '#155994', 'target-arrow-color': '#155994' } },
          { selector: 'edge.routed', style: { 'curve-style': 'segments', 'edge-distances': 'node-position', 'segment-weights': e => e.data('route').weights, 'segment-distances': e => e.data('route').distances, 'source-endpoint': e => e.data('route').sourceEndpoint, 'target-endpoint': e => e.data('route').targetEndpoint } },
          { selector: 'edge.routed-straight', style: { 'curve-style': 'straight', 'source-endpoint': e => e.data('route').sourceEndpoint, 'target-endpoint': e => e.data('route').targetEndpoint } },
        ] : []),
        { selector: '.dim', style: { opacity: 0.2 } },
        { selector: 'node.member', style: { 'border-width': 4 } },
        { selector: 'edge.member', style: { width: 3 } },
        { selector: ':selected', style: { 'border-color': '#e38d14', 'line-color': '#e38d14', 'target-arrow-color': '#e38d14', 'border-width': 4 } },
        { selector: '.highlighted', style: { 'border-color': '#e38d14', 'line-color': '#e38d14', 'target-arrow-color': '#e38d14', 'border-width': 4 } },
        { selector: 'edge.highlighted', style: { width: 4 } },
        { selector: 'node.boundary', style: { 'border-style': 'dashed', 'border-color': '#9b6317', 'border-width': 4 } },
      ], layout: { name: layout.startsWith('bpmn') ? 'preset' : visible.edges.length ? layout : 'grid', cols: Math.ceil(Math.sqrt(visible.nodes.length || 1)), directed: true, padding: 35, spacingFactor: layout === 'grid' ? 1.05 : 1.35, avoidOverlap: true, transform: (_n, p) => layout === 'breadthfirst' && visible.edges.length ? { x: p.y, y: p.x } : p },
      minZoom: 0.03, maxZoom: 4, autoungrabify: isBpmn,
    })
    if (cy.zoom() > 1.2) { cy.zoom(1.2); cy.center() }
    cyRef.current = cy
    cy.on('tap', 'node, edge', event => { setHovered(event.target.data()); selectRef.current?.(event.target.data()) })
    if (isBpmn) cy.on('mouseover', 'node', event => setHovered(event.target.data()))
    cy.on('zoom', () => setZoomLevel(cy.zoom()))
    if (layout.startsWith('bpmn') && visible.nodes.length) {
      setOrganizing(true)
      layoutBpmn(elements.filter(e => !e.data.source).map(e => e.data), visible.edges, layout === 'bpmn-down' ? 'DOWN' : 'RIGHT').then(result => {
        if (disposed) return
        cy.batch(() => {
          cy.nodes().positions(n => result.positions[n.id()])
          cy.edges().forEach(e => {
            const route = result.routes[e.id()]
            if (!route) return
            e.data('route', route); e.addClass(route.weights.length ? 'routed' : 'routed-straight')
          })
        })
        readingViewport(cy)
      }).catch(error => {
        if (disposed) return
        setLayoutError(`No se pudo organizar el flujo: ${error.message}`)
        cy.layout({ name: 'breadthfirst', directed: true, padding: 35 }).run()
        readingViewport(cy)
      }).finally(() => { if (!disposed) { setOrganizing(false); setZoomLevel(cy.zoom()) } })
    } else { setOrganizing(false); setZoomLevel(cy.zoom()) }
    const observer = new ResizeObserver(() => cy.resize()); observer.observe(ref.current)
    return () => { disposed = true; observer.disconnect(); cyRef.current = null; cy.destroy() }
  }, [graph, populationSize, visible, layout, contextConnections, showSupport, isBpmn])
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => cy.elements().forEach(e => { const member = Boolean(modelId && e.data('model_ids')?.includes(modelId)); e.toggleClass('member', member); e.toggleClass('dim', Boolean(modelId && !member)) }))
  }, [modelId, visible, layout])
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    const highlighted = new Set(highlightedIds), boundaries = new Set(boundaryIds)
    cy.batch(() => cy.elements().forEach(e => { e.toggleClass('highlighted', highlighted.has(e.id())); e.toggleClass('boundary', boundaries.has(e.id())) }))
  }, [highlightedIds, boundaryIds, visible, layout])
  function zoom(factor) { const cy = cyRef.current; if (cy) cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }
  function readingViewport(cy = cyRef.current) {
    if (!cy || !cy.nodes().length) return
    cy.fit(undefined, 40)
    const fitted = cy.zoom()
    cy.zoom(Math.min(1.1, Math.max(0.85, fitted)))
    if (fitted >= 0.85) cy.center()
    else {
      const axis = layout === 'bpmn-down' ? 'y' : 'x'
      const anchor = cy.nodes(':selected')[0] || cy.nodes('[kind="start_event"]')[0] || [...cy.nodes()].sort((a, b) => a.position(axis) - b.position(axis) || a.id().localeCompare(b.id()))[0]
      cy.pan(layout === 'bpmn-down' ? { x: cy.width() / 2 - anchor.position('x') * cy.zoom(), y: 60 - (anchor.position('y') - anchor.height() / 2) * cy.zoom() } : { x: 60 - (anchor.position('x') - anchor.width() / 2) * cy.zoom(), y: cy.height() / 2 - anchor.position('y') * cy.zoom() })
    }
  }
  return <div className={`exploration-graph-shell${isBpmn ? ' bpmn-graph-shell' : ''}`}>
    <div className="graph-toolbar"><span role="status">{organizing ? 'Organizando flujo… · ' : ''}{visible.nodes.length} elementos · {visible.edges.length} conexiones{visible.hiddenEdges > 0 ? ` · ${visible.hiddenEdges} conexiones ocultas` : ''}{isBpmn ? ` · ${Math.round(zoomLevel * 100)}%` : ''}</span><div><button type="button" aria-label="Acercar" onClick={() => zoom(1.4)}>+</button><button type="button" aria-label="Alejar" onClick={() => zoom(1 / 1.4)}>−</button>{isBpmn && <button type="button" onClick={() => readingViewport()}>Leer etiquetas</button>}<button type="button" onClick={() => cyRef.current?.fit(undefined, 35)}>{isBpmn ? 'Vista completa' : 'Encajar'}</button><select aria-label="Distribución del grafo" value={layout} onChange={e => setLayout(e.target.value)}>{isBpmn && <><option value="bpmn">Flujo horizontal</option><option value="bpmn-down">Flujo vertical</option></>}<option value="breadthfirst">Por niveles</option><option value="circle">Circular</option><option value="grid">Cuadrícula</option></select></div></div>
    {isBpmn && <div className="bpmn-node-info">{hovered ? <><strong>{hovered.label || hovered.kind || 'Conexión'}</strong>{showSupport && <span>{hovered.support}/{populationSize} individuos</span>}</> : <span>Arrastra el fondo para recorrer el modelo. Pasa sobre una actividad para leer su nombre completo.</span>}</div>}
    {layoutError && <p role="alert" className="error">{layoutError}</p>}
    {visible.nodes.length === 0 && <p className="exploration-notice">Ningún elemento cumple este soporte y estos filtros. Reduce el soporte o limpia el foco.</p>}
    <div className="exploration-canvas" ref={ref} aria-label="Representación estructural interactiva" />
  </div>
}
