export const CONSTRAINT_OPERATORS = ['<=', '<', '>=', '>', '==']
export const MAX_CONSTRAINT_DEPTH = 8
export const MAX_CONSTRAINT_NODES = 256
export const newConstraint = () => ({ metric: 'fitness', operator: '>=', value: '' })

export function parseConstraints(rows) {
  let count = 0
  function parse(row, path, depth) {
    if (++count > MAX_CONSTRAINT_NODES || depth > MAX_CONSTRAINT_DEPTH) throw new Error('Too many constraints or nested groups.')
    if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error(`Constraint ${path}: invalid condition.`)
    const groups = ['all', 'any'].filter(key => key in row)
    if (groups.length) {
      if (groups.length !== 1 || Object.keys(row).length !== 1) throw new Error(`Constraint ${path}: ambiguous group.`)
      const key = groups[0]
      if (!Array.isArray(row[key]) || !row[key].length) throw new Error(`Constraint ${path}: add at least one condition to the group.`)
      return { [key]: row[key].map((child, i) => parse(child, `${path}.${i + 1}`, depth + 1)) }
    }
    const text = String(row.value ?? '').trim(), value = Number(text)
    if (!row.metric || !CONSTRAINT_OPERATORS.includes(row.operator) || typeof row.value === 'boolean' || !text || !Number.isFinite(value)) {
      throw new Error(`Constraint #${path}: select a metric, an operator and a finite threshold.`)
    }
    return { metric: row.metric, operator: row.operator, value }
  }
  if (!Array.isArray(rows)) throw new Error('Constraints must be a list.')
  return rows.map((row, index) => parse(row, `${index + 1}`, 1))
}

export function formatConstraint(node, metrics) {
  for (const [key, join] of [['all', ' AND '], ['any', ' OR ']]) {
    if (key in node) return `(${node[key].map(child => formatConstraint(child, metrics)).join(join)})`
  }
  const actual = metrics ? ` [actual: ${metrics[node.metric] ?? 'not evaluated'}]` : ''
  return `${node.metric} ${node.operator} ${node.value}${actual}`
}
