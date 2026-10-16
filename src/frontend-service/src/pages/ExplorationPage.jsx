import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelExploration, createExploration, downloadExperimentData, explorationPnmlUrl, getExploration, getExplorationModel, getExplorationView, importExploration, listExperiments } from '../api'
import ExplorationGraph from '../components/ExplorationGraph'
import PnmlViewer from '../components/PnmlViewer'
import PetriMarkings from '../components/PetriMarkings'
import VariationExplorer from '../components/VariationExplorer'
import BpmnViewer from '../components/BpmnViewer'
import { originalIdsForBpmn } from '../explorationGraphData'

const METHODS = [
  ['merging', 'Superposición', 'Elementos y conexiones alineados; el soporte cuenta individuos, no trazas.'],
  ['variation', 'Puntos de variación', 'Regiones con interfaces comprobadas. Despliega la jerarquía y consulta sus alternativas.'],
  ['template', 'Plantilla común / variable', 'Núcleo presente en todos los individuos y bloques de estructura variable.'],
]
const metric = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '—'
function saveDownload({ blob, filename }) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function ExplorationPage() {
  const { explorationId, experimentId } = useParams()
  const navigate = useNavigate()
  const [experiments, setExperiments] = useState([])
  const [experiment, setExperiment] = useState('')
  const [archive, setArchive] = useState(null)
  const [originals, setOriginals] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [views, setViews] = useState({})
  const [method, setMethod] = useState('merging')
  const [representation, setRepresentation] = useState('petri')
  const [selected, setSelected] = useState(null)
  const [combination, setCombination] = useState({})
  const [regionId, setRegionId] = useState('')
  const [modelId, setModelId] = useState('')
  const [source, setSource] = useState(null)
  const [finalIndex, setFinalIndex] = useState(0)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [minSupport, setMinSupport] = useState(40)
  const [overlayDetail, setOverlayDetail] = useState(false)
  const [allConnections, setAllConnections] = useState(false)
  const [focusId, setFocusId] = useState('')
  const [connectionSupport, setConnectionSupport] = useState(40)
  const [onlyModel, setOnlyModel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [modelFilter, setModelFilter] = useState('')
  const requestSequence = useRef(0)

  useEffect(() => { let active = true; listExperiments().then(r => { if (active) setExperiments(r.experiments || []) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [explorationId])
  useEffect(() => {
    if (!experimentId) return undefined
    let active = true
    setBusy(true); setError('')
    createExploration(experimentId).then(r => { if (active) navigate(`/exploration/${r.exploration_id}`, { replace: true }) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [experimentId, navigate])
  useEffect(() => {
    let active = true, timer
    setAnalysis(null); setViews({}); setSelected(null); setCombination({}); setSource(null); setModelId(''); setMinSupport(40); setOnlyModel(false); setRegionId(''); setModelFilter(''); setOverlayDetail(false); setAllConnections(false); setFocusId('')
    if (!explorationId) return undefined
    async function poll() {
      try {
        const result = await getExploration(explorationId)
        if (!active) return
        // Older cached analyses remain available, but the new display projection
        // needs a versioned analysis of the same originals (no mining/replay).
        if (result.status === 'completed' && ['structural-exploration-v1', 'structural-exploration-v1.1', 'structural-exploration-v1.2', 'structural-exploration-v1.3'].includes(result.version)) {
          const refreshed = await createExploration(result.experiment_id, result.representation || 'petri')
          if (active) navigate(`/exploration/${refreshed.exploration_id}`, { replace: true })
          return
        }
        setAnalysis(result)
        setRepresentation(result.representation || 'petri')
        if (result.status === 'running') timer = setTimeout(poll, 700)
        else if (result.status === 'completed') {
          const entries = await Promise.all(METHODS.map(async ([kind]) => [kind, await getExplorationView(explorationId, kind)]))
          if (active) { const data = Object.fromEntries(entries); setViews(data); setOverlayDetail(result.representation === 'bpmn'); setOnlyModel(result.representation === 'bpmn'); if (result.representation === 'bpmn') setModelId(result.models[0]?.model_id || ''); setMinSupport(Math.max(1, Math.ceil(result.population_size / 2))); setConnectionSupport(Math.max(1, Math.ceil(result.population_size / 2))); setRegionId([...data.variation.regions].filter(r => r.is_variation_point).sort((a, b) => a.depth - b.depth || b.support - a.support)[0]?.id || data.variation.regions[0]?.id || '') }
        }
      } catch (e) { if (active) setError(e.message) }
    }
    poll()
    return () => { active = false; clearTimeout(timer) }
  }, [explorationId, navigate])
  useEffect(() => {
    const sequence = ++requestSequence.current
    setSource(null); setFinalIndex(0)
    if (!modelId || !explorationId || analysis?.exploration_id !== explorationId || analysis?.status !== 'completed') { setSourceLoading(false); return }
    setSourceLoading(true)
    getExplorationModel(explorationId, modelId).then(r => { if (requestSequence.current === sequence) setSource(r) }).catch(e => { if (requestSequence.current === sequence) setError(e.message) }).finally(() => { if (requestSequence.current === sequence) setSourceLoading(false) })
  }, [modelId, explorationId, analysis?.exploration_id, analysis?.status])

  async function start(id, notation = representation) {
    setBusy(true); setError('')
    try { const result = await createExploration(id, notation); navigate(`/exploration/${result.exploration_id}`) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function upload() {
    setBusy(true); setError('')
    try { const result = await importExploration(archive, originals); await start(result.experiment_id) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  function choose(item, originalId) { setSelected(item); if (originalId) setModelId(originalId); else if (item.model_ids?.length && !item.model_ids.includes(modelId)) setModelId(item.model_ids[0]); if (originalId) requestAnimationFrame(() => document.getElementById('exploration-original')?.scrollIntoView({ behavior: 'smooth', block: 'start' })) }
  const models = analysis?.models || []
  const total = analysis?.population_size || 0
  const currentRegion = views.variation?.regions.find(r => r.id === regionId)
  const blocks = method === 'template' ? views.template?.blocks || [] : currentRegion?.alternatives || []
  const graph = method === 'merging' && !overlayDetail ? views.merging?.activities : views[method]
  const combinationModels = models.filter(m => Object.values(combination).every(alt => alt.model_ids.includes(m.model_id)))
  const associated = new Set((method === 'template' ? combinationModels : models).filter(m => !selected || selected.model_ids.includes(m.model_id)).map(m => m.model_id))
  const shownModels = models.filter(m => associated.has(m.model_id) && `${m.display_name} ${m.solution_id} ${m.evaluation_id} ${m.pipeline?.miner?.variant}`.toLowerCase().includes(modelFilter.toLowerCase()))
  const highlights = useMemo(() => {
    if (!modelId) return []
    return [selected, ...Object.values(combination)].filter(Boolean).flatMap(item => {
      if (Array.isArray(item.sources)) {
        return item.sources.filter(f => f.model_id === modelId).flatMap(f => [...f.node_ids, ...f.arc_ids, ...(f.entry_ids || []), ...(f.exit_ids || [])])
      }
      if (item.alternatives) return item.alternatives.flatMap(a => a.sources.filter(f => f.model_id === modelId).flatMap(f => [...f.node_ids, ...f.arc_ids, ...f.entry_ids, ...f.exit_ids]))
      return item.sources?.[modelId] || []
    })
  }, [selected, combination, modelId])
  const originalHighlights = useMemo(() => representation === 'bpmn' ? originalIdsForBpmn(source?.bpmn, highlights) : highlights, [representation, source, highlights])
  function changeMethod(kind) { setMethod(kind); setSelected(null); setCombination({}); setOnlyModel(false) }
  function chooseTemplateAlternative(block, alt) {
    setCombination(previous => { const next = { ...previous }; if (next[block.id]?.id === alt.id) delete next[block.id]; else next[block.id] = alt; return next })
    setSelected(null)
  }

  return <main className="page exploration-page">
    <section className="card exploration-heading">
      <div className="header-row"><div><p className="eyebrow">Experimental · población final completa</p><h2>Exploración de modelos</h2></div><button type="button" onClick={() => navigate('/exploration')}>Nueva exploración</button></div>
      <p>Compara estructuras y consulta sus modelos de origen. Todos los individuos se conservan, también cuando comparten un artefacto.</p>
      <label>Representación para el análisis <select aria-label="Representación para el análisis" value={representation} disabled={busy || analysis?.status === 'running'} onChange={e => { const value = e.target.value; if (analysis?.status === 'completed') start(analysis.experiment_id, value); else setRepresentation(value) }}><option value="petri">Petri nets</option><option value="bpmn">BPMN (experimental)</option></select></label>
      <details open={!explorationId && !experimentId} className="exploration-import-panel"><summary>Elegir experimento o importar población</summary><div className="exploration-import-grid">
        <div><label htmlFor="exploration-experiment">Experimento guardado</label><select id="exploration-experiment" value={experiment} onChange={e => setExperiment(e.target.value)}><option value="">Elige un experimento</option>{experiments.map(e => <option key={e.experiment_id} value={e.experiment_id}>{e.experiment_name} · {e.counts?.all_solutions} individuos</option>)}</select><button type="button" disabled={!experiment || busy} onClick={() => start(experiment)}>Explorar población final</button></div>
        <div><label htmlFor="exploration-archive">Importar ZIP exportado por la app</label><input id="exploration-archive" type="file" accept=".zip" onChange={e => setArchive(e.target.files[0])} /><label htmlFor="exploration-originals">Originales históricos complementarios (PNML + JSON, o ZIP)</label><input id="exploration-originals" type="file" multiple accept=".pnml,.json,.zip" onChange={e => setOriginals(Array.from(e.target.files))} /><label className="small">O elegir carpeta de originales <input type="file" multiple webkitdirectory="" onChange={e => setOriginals(Array.from(e.target.files).filter(f => /\.(pnml|json)$/i.test(f.name)))} /></label><p className="small muted">{originals.length} ficheros complementarios. Los nuevos ZIP ya incorporan los originales.</p><button type="button" disabled={!archive || busy} onClick={upload}>{busy ? 'Preparando…' : 'Importar y explorar'}</button></div>
      </div></details>
      {error && <p role="alert" className="error">{error}</p>}
      {analysis && analysis.status !== 'completed' && <div role="status"><p>{analysis.phase} · {analysis.status}{analysis.error ? `: ${analysis.error}` : ''}</p>{analysis.status === 'running' && <button type="button" onClick={() => cancelExploration(explorationId).catch(e => setError(e.message))}>Cancelar análisis</button>}</div>}
    </section>
    {analysis?.status === 'completed' && analysis.exploration_id === explorationId && <>
      <section className="card">
        <div className="header-row"><h3>{analysis.experiment_name} · {total} individuos</h3><button type="button" onClick={() => downloadExperimentData(analysis.experiment_id).then(saveDownload).catch(e => setError(e.message))}>Exportar datos y PNML originales</button></div>
        <div className="exploration-stats"><span>{analysis.statistics.common_nodes} nodos comunes</span><span>{analysis.statistics.common_arcs} arcos comunes</span><span>{analysis.statistics.ambiguous_original_nodes} nodos ambiguos</span><span>{analysis.statistics.variation_regions} regiones · profundidad {analysis.statistics.variation_depth}</span><span>{analysis.statistics.analysis_seconds.toFixed(2)} s de análisis</span></div>
        <nav className="exploration-tabs" aria-label="Representaciones">{METHODS.map(([kind, title]) => <button type="button" key={kind} aria-pressed={method === kind} className={method === kind ? 'active' : ''} onClick={() => changeMethod(kind)}>{title}</button>)}</nav>
        <p>{METHODS.find(([kind]) => kind === method)[2]} <a href={analysis.references[method].url} target="_blank" rel="noreferrer">Basado en {analysis.references[method].title}</a>.</p>
        <p className="small muted">Adaptación estructural a {representation === 'bpmn' ? 'BPMN derivado de las Petri nets originales' : 'Petri nets'}. Las vistas consolidadas no son redes ejecutables ni demuestran equivalencia conductual. Una actividad común puede tener un contexto distinto.</p>
        {representation === 'bpmn' && <p className="small muted">Rectángulos: actividades · ×: elección · +: paralelismo · círculos: inicio/final. Las métricas pertenecen a la Petri net original.</p>}
        <div className="exploration-legend"><span>■ Azul oscuro: {total}/{total}</span><span>■ Azul claro: variable</span><span>┄ Borde discontinuo: correspondencia ambigua</span>{representation === 'petri' && <span>τ: transición invisible</span>}<span>Enlaces discontinuos en bloques: interfaces abstractas</span></div>
        {method === 'merging' && <div className="overlay-controls">
          <div className="inline-actions"><button type="button" aria-pressed={!overlayDetail} className={!overlayDetail ? 'active' : ''} onClick={() => { setOverlayDetail(false); setOnlyModel(false) }}>Resumen de actividades</button><button type="button" aria-pressed={overlayDetail} className={overlayDetail ? 'active' : ''} onClick={() => { setOverlayDetail(true); setModelId(modelId || models[0]?.model_id); setOnlyModel(true) }}>{representation === 'bpmn' ? 'Detalle BPMN con compuertas' : 'Detalle de places y τ'}</button></div>
          {!overlayDetail ? <><div className="overlay-filter-row"><label>Soporte de actividades: {minSupport}/{total} ({Math.round(100 * minSupport / total)}%)<input aria-label="Soporte de actividades" type="range" min="1" max={total} value={minSupport} onChange={e => { setMinSupport(Number(e.target.value)); setFocusId('') }} /></label><label>Soporte de conexiones: {connectionSupport}/{total}<input aria-label="Soporte de conexiones" type="range" min="1" max={total} value={connectionSupport} disabled={allConnections} onChange={e => setConnectionSupport(Number(e.target.value))} /></label><label>Centrar en actividad<select aria-label="Centrar en actividad" value={focusId} onChange={e => setFocusId(e.target.value)}><option value="">Todas las actividades visibles</option>{(graph?.nodes || []).filter(n => n.support >= minSupport).map(n => <option key={n.id} value={n.id}>{n.label} · {n.support}/{total}</option>)}</select></label></div><div className="inline-actions">{[1, Math.ceil(total / 2), total].map(n => <button type="button" key={n} onClick={() => { setMinSupport(n); setFocusId('') }}>{n === 1 ? 'Todas' : n === total ? 'Universales' : 'Al menos 50%'}</button>)}<label><input type="checkbox" checked={allConnections} onChange={e => setAllConnections(e.target.checked)} /> Ver todas las conexiones entre actividades visibles</label></div>
            <p className="small muted">Cada flecha resume un camino dirigido a través de {representation === 'bpmn' ? 'compuertas del BPMN derivado' : 'places y τ'}, sin actividades intermedias. Su cifra cuenta modelos, no trazas. Los enlaces débiles necesarios como contexto se conservan discontinuos. Pulsa una flecha para ver un camino testigo.</p>
          </> : <p className="small muted">Vista detallada {representation === 'bpmn' ? 'del BPMN derivado' : 'de la estructura Petri original'} alineada. Empieza con un individuo; desmarca el filtro para superponer todos los modelos. No se eliminan sus conexiones por soporte.</p>}
          <label><input type="checkbox" checked={onlyModel} disabled={!modelId} onChange={e => setOnlyModel(e.target.checked)} /> Mostrar solo el individuo inspeccionado</label>
          {onlyModel && <label>Individuo <select value={modelId} onChange={e => setModelId(e.target.value)}>{models.map(m => <option key={m.model_id} value={m.model_id}>{m.display_name}</option>)}</select></label>}
          {overlayDetail && !onlyModel && <p className="exploration-notice">Superposición completa: {views.merging?.nodes.length} nodos y {views.merging?.edges.length} arcos. Para inspeccionar zonas densas, usa un individuo o vuelve al resumen.</p>}
        </div>}
        {method === 'template' && views.template?.common_core_empty && <p className="exploration-notice">No hay núcleo común universal. Los bloques conservan las alternativas y su procedencia.</p>}
        {method === 'variation' ? <VariationExplorer key={representation} representation={representation} variation={views.variation} overlay={views.merging} regionId={regionId} onRegion={id => { setRegionId(id); setSelected(null) }} explorationId={explorationId} models={models} total={total} onSelect={choose} /> : <ExplorationGraph representation={representation} graph={graph} populationSize={total} modelId={modelId} minSupport={method === 'merging' && !overlayDetail ? minSupport : 1} onlyModel={onlyModel} contextConnections={method === 'merging' && !overlayDetail} connectionSupport={connectionSupport} allConnections={allConnections} focusId={method === 'merging' && !overlayDetail ? focusId : ''} onSelect={choose} />}
        {selected && <div className="selection-summary"><strong>{selected.label || 'Alternativa seleccionada'} · {selected.support}/{total} individuos</strong><button type="button" onClick={() => document.getElementById('exploration-original')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>Ver original resaltado y métricas</button><button type="button" onClick={() => { setSelected(null); setModelId(''); setOnlyModel(false) }}>Limpiar selección</button></div>}
        {method === 'template' && <div className="alternative-grid">{blocks.map(block => <button type="button" key={block.id} className={selected?.id === block.id ? 'alternative-card active' : 'alternative-card'} onClick={() => choose(block)}><strong>{block.label}</strong><span>{block.support}/{total} individuos · {block.alternatives.length} estructuras</span>{block.multiple_occurrences && <span>Varios fragmentos simultáneos posibles</span>}</button>)}</div>}
        {method === 'template' && <details className="template-combination"><summary>Consultar qué estructuras de distintos bloques aparecen juntas</summary><p className="small">Estos filtros consultan individuos existentes. Puedes elegir una estructura por bloque.</p>{blocks.map(block => <div key={block.id}><strong>{block.label}</strong><div className="alternative-grid">{block.alternatives.map((alt, i) => <button type="button" key={alt.id} aria-pressed={combination[block.id]?.id === alt.id} className={combination[block.id]?.id === alt.id ? 'active' : ''} onClick={() => chooseTemplateAlternative(block, alt)}>Estructura {i + 1} · {alt.support}/{total} · {alt.visible_activities?.join(', ') || 'Routing'} · {alt.node_count} nodos</button>)}</div></div>)}<p role="status">{combinationModels.length}/{total} individuos contienen las estructuras elegidas.{combinationModels.length === 0 ? ' Esta combinación no aparece en la población.' : ''}</p><button type="button" onClick={() => setCombination({})}>Limpiar combinación</button></details>}
      </section>
      <div className="exploration-detail-grid">
        <section className="card"><h3>Procedencia y métricas</h3>
          {selected ? <><p><strong>{selected.label || selected.kind || 'Alternativa'}</strong> · {selected.support}/{total} individuos</p>{selected.context_varies && <p className="exploration-notice">La actividad coincide, pero sus conexiones/contexto cambian entre modelos.</p>}{selected.matching === 'ambiguous' && <p className="exploration-notice">Correspondencia ambigua. Este elemento se mantiene separado.</p>}{selected.alternatives && <div className="alternative-grid">{selected.alternatives.map((alt, i) => <button type="button" key={alt.id} onClick={() => choose(alt)}>Estructura {i + 1} · {alt.support}/{total}</button>)}</div>}<button type="button" onClick={() => setSelected(null)}>Quitar filtro de procedencia</button></> : <p className="small muted">Pulsa un elemento, región o alternativa para consultar sus individuos. Ahora se muestran {shownModels.length} de {total}.</p>}
          <label>Buscar individuo <input value={modelFilter} onChange={e => setModelFilter(e.target.value)} placeholder="ID o minero" /></label>
          <div className="exploration-table-wrap"><table className="exploration-table"><thead><tr><th>Modelo</th><th>Fitness</th><th>Precision</th><th>Generalization</th><th>Simplicity</th></tr></thead><tbody>{shownModels.map(m => <tr key={m.model_id} className={modelId === m.model_id ? 'active' : ''}><td><button type="button" onClick={() => setModelId(m.model_id)}>{m.display_name}</button><small>Solución {m.import_provenance?.solution_id ?? m.solution_id} · {m.pipeline?.miner?.variant || m.pipeline?.miner?.key || '—'}</small></td><td>{metric(m.metrics?.fitness)}</td><td>{metric(m.metrics?.precision)}</td><td>{metric(m.metrics?.generalisation ?? m.metrics?.generalization)}</td><td>{metric(m.metrics?.simplicity)}</td></tr>)}</tbody></table></div>
          <p className="small muted">{shownModels.length} individuos mostrados. El soporte siempre se calcula sobre los {total} originales.</p>
        </section>
        <section className="card" id="exploration-original"><h3>{representation === 'bpmn' ? 'BPMN derivado y Petri net original' : 'Petri net original'}</h3>
          {sourceLoading && <p>Cargando original…</p>}{!source && !sourceLoading && <p>Elige un individuo en la tabla.</p>}
          {source && <><div className="header-row"><strong>{source.display_name} · solución {source.import_provenance?.solution_id ?? source.solution_id}</strong><a className="link-button" href={explorationPnmlUrl(explorationId, modelId)}>Descargar PNML original</a></div>
            <p className="small">{source.places.length} places · {source.transitions.length} transiciones · métricas: {source.metrics_status}{source.is_feasible === false ? ' · no factible' : ''}</p>
            {source.bpmn && <><BpmnViewer graph={source.bpmn} modelId={modelId} highlightedIds={highlights} /><p className="small muted">BPMN derivado para explorar la estructura. Los elementos seleccionados se resaltan también en su Petri net de origen.</p></>}
            <PnmlViewer petri={source} selectedFinalIndex={finalIndex} highlightedIds={originalHighlights} controls compactPlaces />
            <PetriMarkings petri={source} selectedFinalIndex={finalIndex} onSelectFinal={setFinalIndex} />
            <details><summary>Configuración y procedencia originales</summary><pre>{JSON.stringify({ evaluation_id: source.evaluation_id, import_provenance: source.import_provenance, pipeline: source.pipeline_full || source.pipeline, pnml_sha256: source.pnml_sha256, constraint_violations: source.constraint_violations }, null, 2)}</pre></details>
          </>}
        </section>
      </div>
    </>}
  </main>
}
