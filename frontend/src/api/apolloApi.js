const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function cleanWebText(value) {
  return String(value || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/【[^】]{1,160}】/g, '')
    .replace(/\[[0-9]+†L?[0-9]+(?:-L?[0-9]+)?\]/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/^\s*\|[-:| ]+\|\s*$/gm, '')
    .replace(/^\s*\|\s*(.+?)\s*\|\s*$/gm, (_, row) => row.split('|').map((cell) => cell.trim()).filter(Boolean).join('  •  '))
    .replace(/^\s*#{1,3}\s*/gm, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

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

export async function streamChat({
  messages,
  model = 'openai/gpt-oss-120b',
  notebookId,
  notebookTitle,
  activeSources = [],
  userId = 'default',
  webEnabled = false,
  onToken,
  onStart,
  onFallback,
  onSources,
  onDone,
  onError,
  signal,
}) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      messages,
      model,
      notebook_id: notebookId,
      notebook_title: notebookTitle,
      active_sources: activeSources,
      user_id: userId,
      web_enabled: webEnabled,
    }),
  })

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

  if (!response.body) throw new Error('Apollo API did not return a streaming response')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let serverWebMode = webEnabled

  const consumeEvent = (rawEvent) => {
    const data = rawEvent
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('')
    if (!data) return

    const payload = JSON.parse(data)
    if (payload.type === 'start') {
      serverWebMode = Boolean(payload.web)
      onStart?.(payload)
    }
    if (payload.type === 'fallback') onFallback?.(payload)
    if (payload.type === 'token') onToken?.(serverWebMode ? cleanWebText(payload.text || '') : (payload.text || ''))
    if (payload.type === 'sources') onSources?.(payload.sources || [])
    if (payload.type === 'done') onDone?.(payload)
    if (payload.type === 'error') {
      onError?.(payload.message || 'Apollo backend error')
      throw new Error(payload.message || 'Apollo backend error')
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex !== -1) {
      const event = buffer.slice(0, separatorIndex)
      buffer = buffer.slice(separatorIndex + 2)
      consumeEvent(event)
      separatorIndex = buffer.indexOf('\n\n')
    }
    if (done) break
  }

  if (buffer.trim()) consumeEvent(buffer)
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`)
  return response.json()
}
