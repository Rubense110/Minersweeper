export const API_BASE = (import.meta.env.VITE_OPTIMIZATION_API_URL || 'http://localhost:8080').replace(/\/$/, '')

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  })

  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch (_error) {
    body = { raw: text }
  }

  if (!response.ok) {
    const msg = body?.message || body?.error || `HTTP ${response.status}`
    throw new Error(msg)
  }

  return body
}

export async function createOptimization(payload) {
  return request('/optimizations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getOptimization(jobId) {
  return request(`/optimizations/${jobId}`)
}

export async function getProgress(jobId) {
  return request(`/optimizations/${jobId}/progress`)
}

export async function getSolutions(jobId, scope = 'pareto') {
  return request(`/optimizations/${jobId}/solutions?scope=${encodeURIComponent(scope)}`)
}

export async function getArtifacts(jobId, scope = 'pareto', includePnml = true) {
  return request(
    `/optimizations/${jobId}/artifacts?scope=${encodeURIComponent(scope)}&include_pnml=${includePnml ? 'true' : 'false'}`
  )
}

export function getEventsUrl(jobId) {
  return `${API_BASE}/optimizations/${encodeURIComponent(jobId)}/events`
}
