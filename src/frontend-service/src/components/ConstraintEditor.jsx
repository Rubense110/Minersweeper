import FancySelect from './FancySelect'
import { CONSTRAINT_OPERATORS, MAX_CONSTRAINT_DEPTH, newConstraint } from '../optimizationConstraints'

export default function ConstraintEditor({ rows, onChange, metrics, path = '', depth = 1 }) {
  const replace = (index, node) => onChange(rows.map((row, i) => i === index ? node : row))
  return <div className="constraint-list">
    {rows.map((node, index) => {
      const label = path ? `${path}.${index + 1}` : `${index + 1}`
      const group = 'any' in node ? 'any' : 'all' in node ? 'all' : null
      const remove = <button type="button" className="link-button danger" aria-label={`Remove constraint ${label}`} onClick={() => onChange(rows.filter((_, i) => i !== index))}>Remove</button>
      if (group) return <fieldset className="constraint-group" key={index}>
        <legend>Group {label}</legend>
        <div className="row row-compact">
          <FancySelect ariaLabel={`Logic for group ${label}`} value={group} options={[{ value: 'any', label: 'OR — any condition' }, { value: 'all', label: 'AND — all conditions' }]} onChange={key => replace(index, { [key]: node[group] })} />
          {remove}
        </div>
        <ConstraintEditor rows={node[group]} onChange={children => replace(index, { [group]: children })} metrics={metrics} path={label} depth={depth + 1} />
      </fieldset>
      const update = (key, value) => replace(index, { ...node, [key]: value })
      return <div className="constraint-row" key={index}>
        <FancySelect ariaLabel={`Metric for constraint ${label}`} value={node.metric} options={metrics} onChange={value => update('metric', value)} />
        <FancySelect ariaLabel={`Operator for constraint ${label}`} value={node.operator} options={CONSTRAINT_OPERATORS.map(value => ({ value, label: value }))} onChange={value => update('operator', value)} />
        <input aria-label={`Threshold for constraint ${label}`} type="number" step="any" placeholder="Threshold" value={node.value} required onChange={e => update('value', e.target.value)} />
        {remove}
      </div>
    })}
    <div className="row row-compact">
      <button type="button" className="link-button secondary" onClick={() => onChange([...rows, newConstraint()])}>Add constraint</button>
      {depth < MAX_CONSTRAINT_DEPTH && <>
        <button type="button" className="link-button secondary" onClick={() => onChange([...rows, { any: [newConstraint()] }])}>Add OR group</button>
        <button type="button" className="link-button secondary" onClick={() => onChange([...rows, { all: [newConstraint()] }])}>Add AND group</button>
      </>}
    </div>
  </div>
}
