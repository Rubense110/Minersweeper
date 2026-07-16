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
    const error = new Error(msg)
    error.status = response.status
    error.payload = body
    throw error
  }

  return body
}

export async function listLogs() {
  return request('/logs')
}

export async function listOptimizations() {
  return request('/optimizations')
}

export async function createOptimization(payload) {
  return request('/optimizations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function cancelOptimization(jobId) {
  return request(`/optimizations/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export async function listExperiments() {
  return request('/experiments')
}

export async function getExperiment(experimentId) {
  return request(`/experiments/${encodeURIComponent(experimentId)}`)
}

export async function getExperimentSolutions(experimentId, scope = 'all') {
  return request(`/experiments/${encodeURIComponent(experimentId)}/solutions?scope=${encodeURIComponent(scope)}`)
}

export async function selectExperimentModel(experimentId, payload) {
  return request(`/experiments/${encodeURIComponent(experimentId)}/select-model`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  })
}

export async function downloadExperimentData(experimentId) {
  const response = await fetch(`${API_BASE}/experiments/${encodeURIComponent(experimentId)}/download`)

  if (!response.ok) {
    const text = await response.text()
    let body = null
    try {
      body = text ? JSON.parse(text) : null
    } catch (_error) {
      body = { raw: text }
    }
    const msg = body?.message || body?.error || `HTTP ${response.status}`
    const error = new Error(msg)
    error.status = response.status
    error.payload = body
    throw error
  }

  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  return {
    blob: await response.blob(),
    filename: match?.[1] || `experiment_${experimentId}.zip`,
  }
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

export async function renderPetriImage(payload, format = 'svg') {
  const response = await fetch(`${API_BASE}/petri/render?format=${encodeURIComponent(format)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload || {}),
  })

  if (!response.ok) {
    const text = await response.text()
    let body = null
    try {
      body = text ? JSON.parse(text) : null
    } catch (_error) {
      body = { raw: text }
    }
    const msg = body?.message || body?.error || `HTTP ${response.status}`
    const error = new Error(msg)
    error.status = response.status
    error.payload = body
    throw error
  }

  return response.blob()
}

export function getEventsUrl(jobId) {
  return `${API_BASE}/optimizations/${encodeURIComponent(jobId)}/events`
}
