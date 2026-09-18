const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function friendlyError(detail, status) {
  const text = String(detail || '').trim()
  if (text) return text
  if (status === 429) return 'Apollo is rate-limited right now. Please try again shortly.'
  if (status >= 500) return 'Apollo could not complete this Studio generation right now.'
  return `Apollo API returned ${status}`
}

async function requestJson(path, body, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(friendlyError(payload?.detail, response.status))
  }
  return response.json()
}

export async function generateStudioOutput(
  notebookId,
  tool,
  activeSources = [],
  { transformationType = null, customPrompt = null, model = null, userId = 'default', signal } = {},
) {
  if (!notebookId) throw new Error('No active notebook selected')
  if (tool === 'slides') {
    return requestJson(`/api/notebooks/${encodeURIComponent(notebookId)}/studio/slides`, {
      active_sources: activeSources,
      user_id: userId,
      page_count: 8,
      aspect_ratio: '16:9',
    }, signal)
  }
  return requestJson(`/api/notebooks/${encodeURIComponent(notebookId)}/studio/generate`, {
    tool,
    active_sources: activeSources,
    transformation_type: transformationType,
    custom_prompt: customPrompt,
    model,
    user_id: userId,
  }, signal)
}

export async function generateNotebookMindMap(notebookId, activeSources = [], diagramHint = null, userId = 'default', signal) {
  if (!notebookId) throw new Error('No active notebook selected')
  return requestJson(`/api/notebooks/${encodeURIComponent(notebookId)}/mindmap`, {
    active_sources: activeSources,
    diagram_hint: diagramHint,
    user_id: userId,
  }, signal)
}
