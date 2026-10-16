import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getExplorationModel } from '../api'
import PnmlViewer from './PnmlViewer'
import BpmnViewer from './BpmnViewer'

const isVariation = region => region.is_variation_point === true && region.scope === 'local' && region.interface_status === 'validated_shared_entry_exit'
const metrics = m => `F ${m?.fitness?.toFixed(3) ?? '—'} · P ${m?.precision?.toFixed(3) ?? '—'} · G ${(m?.generalisation ?? m?.generalization)?.toFixed(3) ?? '—'} · S ${m?.simplicity?.toFixed(3) ?? '—'}`

function FragmentPreview({ alternative, explorationId, models, total, onSelect, boundaryDetails, wholeModel, representation }) {
  const [modelId, setModelId] = useState(alternative.model_ids[0])
  const [source, setSource] = useState(null), [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false), [finalIndex, setFinalIndex] = useState(0)
  const dialogRef = useRef(null)
  // Open before the child graph measures its container for layout.
  useLayoutEffect(() => { if (expanded) dialogRef.current?.showModal() }, [expanded])
  useEffect(() => {
    let active = true
    setSource(null); setError(''); setFinalIndex(0)
    getExplorationModel(explorationId, modelId).then(r => { if (active) setSource(r) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [explorationId, modelId])
  const fragment = alternative.sources.find(f => f.model_id === modelId)
  const boundaryIds = useMemo(() => [...new Set([...(fragment?.entry_ids || []), ...(fragment?.exit_ids || [])])], [fragment])
  const nodeLabels = useMemo(() => Object.fromEntries(Object.entries(fragment?.boundary_mapping || {}).map(([nid, key]) => [nid, boundaryDetails[key]?.label || key])), [fragment, boundaryDetails])
  const petri = useMemo(() => {
    if (!source || !fragment) return null
    const ids = new Set([...fragment.node_ids, ...boundaryIds]), arcs = new Set(fragment.arc_ids)
    const project = marking => marking.filter(e => ids.has(e.place_id))
    return { ...source, places: source.places.filter(n => ids.has(n.id)), transitions: source.transitions.filter(n => ids.has(n.id)), arcs: source.arcs.filter(a => arcs.has(a.id)), initial_marking: project(source.initial_marking), final_markings: source.final_markings.map(project) }
  }, [source, fragment, boundaryIds])
  const bpmn = useMemo(() => {
    if (!source?.bpmn || !fragment) return null
    const ids = new Set([...fragment.node_ids, ...boundaryIds]), arcs = new Set(fragment.arc_ids)
    return { nodes: source.bpmn.nodes.filter(n => ids.has(n.id)), edges: source.bpmn.edges.filter(a => arcs.has(a.id)) }
  }, [source, fragment, boundaryIds])
  const loaded = representation === 'bpmn' ? bpmn : petri
  const preview = () => representation === 'bpmn' ? <BpmnViewer graph={bpmn} modelId={modelId} boundaryIds={boundaryIds} nodeLabels={nodeLabels} /> : <PnmlViewer petri={petri} selectedFinalIndex={finalIndex} boundaryIds={boundaryIds} nodeLabels={nodeLabels} controls compactPlaces />
  return <article className="fragment-preview">
    <div className="header-row"><strong>{alternative.support}/{total} individuos</strong><button type="button" onClick={() => onSelect(alternative)}>Ver procedencia</button></div>
    <p className="small">{alternative.node_count} nodos{wholeModel ? '' : ' interiores'}{representation !== 'bpmn' ? ` · ${alternative.invisible_transitions} τ` : ' BPMN'} · {alternative.arc_count} conexiones incluidas</p>
    <label>Original mostrado <select value={modelId} onChange={e => setModelId(e.target.value)}>{alternative.model_ids.map(mid => <option key={mid} value={mid}>{models.find(m => m.model_id === mid)?.display_name || mid}</option>)}</select></label>
    <p className="small">{metrics(source?.metrics)} (métricas del modelo completo)</p>
    {error && <p role="alert">{error}</p>}
    {!loaded && !error && <p>Cargando fragmento…</p>}
    {loaded && <><div className="inline-actions"><button type="button" onClick={() => setExpanded(true)}>Ampliar fragmento</button>{representation !== 'bpmn' && <label>Final marking mostrado <select value={finalIndex} onChange={e => setFinalIndex(Number(e.target.value))}>{source.final_markings.map((_, i) => <option key={i} value={i}>#{i + 1}</option>)}</select></label>}</div>{preview()}</>}
    {expanded && loaded && <dialog className="fragment-dialog" ref={dialogRef} onCancel={() => setExpanded(false)}><div className="header-row"><h3>Fragmento de {source.display_name} · {metrics(source.metrics)}</h3><button type="button" onClick={() => setExpanded(false)}>Cerrar fragmento</button></div><p>{alternative.node_count} nodos{wholeModel ? '' : ' interiores'}. Usa el zoom para inspeccionar la estructura.</p>{preview()}</dialog>}
    <p className="small muted">{representation === 'bpmn' ? 'BPMN derivado del original. Borde discontinuo: entrada/salida de la región. Puedes consultar debajo la Petri net y sus markings.' : wholeModel ? "Modelo original completo, con sus markings y transiciones invisibles." : "Recorte de arcos originales validado por fronteras. Borde discontinuo: entrada/salida; P y τ identifican sus ports. Este fragmento no es una red ejecutable independiente."}</p>
    <button type="button" onClick={() => onSelect({ ...alternative, model_ids: [modelId, ...alternative.model_ids.filter(mid => mid !== modelId)] }, modelId)}>Inspeccionar este original completo y sus markings</button>
  </article>
}

function RegionComparison({ region, explorationId, models, total, onSelect, boundaryDetails, representation }) {
  const alternatives = region.alternatives
  const [left, setLeft] = useState(alternatives[0]?.id), [right, setRight] = useState(alternatives[1]?.id || '')
  const choice = (value, change, title) => <label>{title}<select value={value} onChange={e => change(e.target.value)}>{alternatives.map((alt, i) => <option key={alt.id} value={alt.id}>A{i + 1} · {alt.support}/{total} · {alt.node_count} nodos{representation !== 'bpmn' ? ` · ${alt.invisible_transitions} τ` : ' BPMN'} · {alt.visible_activities.join(', ') || 'routing'}</option>)}</select></label>
  return <>
    <h4>{region.scope === 'global' ? 'Comparar variación global: modelos completos' : region.comparison?.status === 'unresolved' ? 'Comparación estructural sin resolver' : isVariation(region) ? 'Comparar alternativas del punto de variación' : 'Fragmento sin alternativas distintas en esta región'}</h4>
    {region.comparison?.status === 'unresolved' && <p className="exploration-notice">Se alcanzó el límite de alguna comparación. Los grupos son provisionales y no demuestran diferencias estructurales. Se conservan todos los originales para inspección.</p>}
    <div className="fragment-comparison"><div>{choice(left, setLeft, 'Alternativa A')}<FragmentPreview key={left} alternative={alternatives.find(a => a.id === left)} explorationId={explorationId} models={models} total={total} onSelect={onSelect} boundaryDetails={boundaryDetails} wholeModel={region.scope === 'global'} representation={representation} /></div>{right && <div>{choice(right, setRight, 'Alternativa B')}<FragmentPreview key={right} alternative={alternatives.find(a => a.id === right)} explorationId={explorationId} models={models} total={total} onSelect={onSelect} boundaryDetails={boundaryDetails} wholeModel={region.scope === 'global'} representation={representation} /></div>}</div>
    {left === right && <p className="exploration-notice">Estás mostrando la misma alternativa en ambos paneles.</p>}
  </>
}

export default function VariationExplorer({ variation, overlay, regionId, onRegion, explorationId, models, total, onSelect, representation = 'petri' }) {
  const [showStable, setShowStable] = useState(false)
  const treeRef = useRef(null)
  useEffect(() => {
    const container = treeRef.current, selected = container?.querySelector('.active')
    if (!selected) return
    const box = container.getBoundingClientRect(), node = selected.getBoundingClientRect()
    if (node.bottom > box.bottom) container.scrollTop += node.bottom - box.bottom + 8
    else if (node.top < box.top) container.scrollTop -= box.top - node.top + 8
  }, [regionId, showStable])
  const treeRegions = variation?.regions || [], extra = variation?.additional_regions || []
  const regions = [...treeRegions, ...extra], current = regions.find(r => r.id === regionId)
  const boundaryDetails = variation?.boundary_details || {}
  const lookup = new Map((overlay?.nodes || []).map(n => [n.id, n]))
  const points = regions.filter(isVariation), numbers = new Map(points.map((r, i) => [r.id, i + 1]))
  const byId = new Map(regions.map(r => [r.id, r]))
  const relevant = new Set(points.map(r => r.id))
  for (const point of points) { let r = point; while (r?.parent_id) { relevant.add(r.parent_id); r = byId.get(r.parent_id) } }
  const names = ids => ids.map(id => boundaryDetails[id]?.description || lookup.get(id)?.label || id).join(' + ')
  const title = r => !r.parent_id ? 'Población completa' : `${names(r.entries) || 'Frontera sin entradas'} → ${names(r.exits) || 'Frontera sin salidas'}`
  function tree(id) {
    const r = byId.get(id)
    if (!r || (!showStable && r.parent_id && !relevant.has(id))) return null
    return <li key={r.id}><button type="button" className={`hierarchy-node ${r.id === regionId ? 'active' : ''}`} onClick={() => onRegion(r.id)}>
      <span className="region-badge">{isVariation(r) ? `VP${numbers.get(r.id)}` : r.parent_id ? 'Fragmento' : 'Raíz'}</span><strong>{title(r)}</strong><small>{r.support}/{total} individuos{r.parent_id ? ` · ${r.alternatives.length} alternativa${r.alternatives.length === 1 ? '' : 's'}` : ''}</small>
    </button>{r.children.length > 0 && <ul>{r.children.map(tree)}</ul>}</li>
  }
  const ancestors = []; let parent = current
  while (parent) { ancestors.unshift(parent); parent = byId.get(parent.parent_id) }
  const visibleChildren = (current?.children || []).filter(id => showStable || relevant.has(id))
  return <div className="variation-workspace">
    <aside className="variation-hierarchy"><h4>Árbol de regiones</h4><p>{points.length} puntos de variación · {Math.max(0, regions.length - points.length - 1)} otras regiones</p><label><input type="checkbox" checked={showStable} onChange={e => setShowStable(e.target.checked)} /> Mostrar también regiones sin VP verificado</label><p className="small muted">Las líneas del árbol indican inclusión de fragmentos, no flujo de ejecución.</p><div className="hierarchy-scroll" ref={treeRef}><ul className="hierarchy-tree">{regions[0] && tree(regions[0].id)}</ul>{extra.length > 0 && <div><h4>Regiones validadas fuera del árbol</h4><p>Se solapan con otras regiones; no se fuerza una relación de inclusión.</p>{extra.filter(r => showStable || isVariation(r)).map(r => <button type="button" key={r.id} className="hierarchy-node" onClick={() => onRegion(r.id)}>{numbers.has(r.id) ? `VP${numbers.get(r.id)}` : 'Fragmento'} · {title(r)}</button>)}</div>}</div></aside>
    <section className="variation-region">
      <nav className="region-breadcrumb" aria-label="Ruta de región">{ancestors.map(r => <button type="button" key={r.id} onClick={() => onRegion(r.id)}>{r.parent_id ? numbers.has(r.id) ? `VP${numbers.get(r.id)}` : r.label : 'Población'}</button>)}</nav>
      {current && <>
        {!current.parent_id ? <><h3>Variación global de la población</h3>{points.length === 0 && <p className="exploration-notice">No se han encontrado puntos de variación locales validados con las correspondencias y los candidatos actuales. Esto no significa que los modelos sean equivalentes.</p>}<p>La población tiene {current.alternatives.length} estructuras completas. Puedes compararlas aquí. Las regiones locales del árbol verifican participación y direcciones de todas sus fronteras, además de accesibilidad dirigida en cada original.</p><RegionComparison key={current.id} region={current} explorationId={explorationId} models={models} total={total} onSelect={onSelect} boundaryDetails={boundaryDetails} representation={representation} /></> : <>
          <div className="variation-interface"><div><small>Entradas compartidas</small><strong>{names(current.entries) || 'Sin arcos externos entrantes'}</strong></div><div className="variation-point"><strong>{isVariation(current) ? `VP${numbers.get(current.id)}` : current.comparison?.status === 'unresolved' ? 'Comparación sin resolver' : 'Fragmento estable en esta región'}</strong><span>{current.alternatives.length} alternativas · {current.support}/{total} individuos</span></div><div><small>Salidas compartidas</small><strong>{names(current.exits) || 'Sin arcos externos salientes'}</strong></div></div>
          <p className="small muted">Interfaz común al grupo de {current.support} individuos. El esquema sitúa las fronteras; no impone un orden ni independencia entre los VP.</p>
          <button type="button" onClick={() => onSelect(current)}>Localizar región en un modelo completo</button>
          <RegionComparison key={current.id} region={current} explorationId={explorationId} models={models} total={total} onSelect={onSelect} boundaryDetails={boundaryDetails} representation={representation} />
        </>}
        {visibleChildren.length > 0 && <div className="region-children"><h4>Subregiones interiores</h4>{visibleChildren.map(id => { const r = byId.get(id); return <button type="button" key={id} onClick={() => onRegion(id)}>{numbers.has(id) ? `VP${numbers.get(id)}` : 'Fragmento'} · {title(r)} · {r.alternatives.length} alternativas</button> })}</div>}
        <p className="small muted">Jerarquía por inclusión de arcos originales · profundidad {variation.max_depth}. La búsqueda de candidatos es conservadora; no demuestra equivalencia conductual ni enumera todos los SHESHE máximos.</p>
      </>}
    </section>
  </div>
}
