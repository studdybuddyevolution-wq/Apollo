const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    let message = `Marklyf API returned ${response.status}`
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

export function importSourceUrl(notebookId, url, userId = 'default') {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/sources/url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, user_id: userId }),
  })
}

export function importYouTubeSource(notebookId, url, userId = 'default', languages = ['en']) {
  return request(`/api/notebooks/${encodeURIComponent(notebookId)}/sources/youtube`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, languages, user_id: userId }),
  })
}
