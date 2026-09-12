const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    let message = `Apollo API returned ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) message = body.detail
    } catch {
      // Keep the HTTP status message when the backend does not return JSON.
    }
    throw new Error(message)
  }
  return response.json()
}

export function listNotebooks(userId = 'default') {
  return request(`/api/notebooks?user_id=${encodeURIComponent(userId)}`)
}

export function createNotebook(title, userId = 'default') {
  return request('/api/notebooks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, user_id: userId }),
  })
}

export function renameNotebook(notebookId, title, userId = 'default') {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, user_id: userId }),
  })
}

export function deleteNotebook(notebookId, userId = 'default') {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  })
}

export function listSources(notebookId, userId = 'default') {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/sources?user_id=${encodeURIComponent(userId)}`)
}

export function uploadSource(notebookId, file, userId = 'default') {
  const form = new FormData()
  form.append('file', file)
  form.append('user_id', userId)
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/sources`, {
    method: 'POST',
    body: form,
  })
}

export function deleteSource(notebookId, sourceName, userId = 'default') {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/sources/${encodeURIComponent(sourceName)}?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  })
}

export function searchNotebook(notebookId, query, options = {}) {
  const { topK = 5, sourceNames = [], userId = 'default' } = options
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      top_k: topK,
      source_names: sourceNames,
      user_id: userId,
    }),
  })
}
