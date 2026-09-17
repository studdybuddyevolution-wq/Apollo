const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function cleanResearchText(value) {
  return String(value || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/【[^】]{1,160}】/g, '')
    .replace(/\[[0-9]+†L?[0-9]+(?:-L?[0-9]+)?\]/g, '')
    .replace(/\n{3,}/g, '\n\n')
}

async function openChat({
  messages,
  model,
  notebookId,
  notebookTitle,
  activeSources,
  sourceModes,
  sessionId,
  userId,
  webEnabled,
  researchMode,
  onToken,
  onSession,
  onStart,
  onFallback,
  onRestart,
  onSources,
  onDone,
  onError,
  signal,
}) {
  const workspace = Boolean(notebookId)
  const response = await fetch(`${API_BASE}${workspace ? '/api/chat/workspace' : '/api/chat'}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      messages,
      model,
      notebook_id: notebookId,
      notebook_title: notebookTitle,
      active_sources: activeSources,
      source_modes: sourceModes || {},
      session_id: sessionId || null,
      user_id: userId,
      web_enabled: webEnabled,
      research_mode: researchMode,
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
  let serverResearch = researchMode

  const consumeEvent = (rawEvent) => {
    const data = rawEvent
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('')
    if (!data) return

    const payload = JSON.parse(data)
    if (payload.type === 'session') onSession?.(payload.session)
    if (payload.type === 'start') {
      serverResearch = payload.research || researchMode
      onStart?.(payload)
    }
    if (payload.type === 'fallback') onFallback?.(payload)
    if (payload.type === 'restart') onRestart?.(payload)
    if (payload.type === 'token') {
      const token = serverResearch === 'quick' ? (payload.text || '') : cleanResearchText(payload.text || '')
      onToken?.(token)
    }
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

export async function streamChat({
  messages,
  model = 'openai/gpt-oss-120b',
  notebookId,
  notebookTitle,
  activeSources = [],
  sourceModes = {},
  sessionId = null,
  userId = 'default',
  webEnabled = false,
  researchMode = 'quick',
  onToken,
  onSession,
  onStart,
  onFallback,
  onRestart,
  onSources,
  onDone,
  onError,
  signal,
}) {
  return openChat({
    messages,
    model,
    notebookId,
    notebookTitle,
    activeSources,
    sourceModes,
    sessionId,
    userId,
    webEnabled: webEnabled || researchMode !== 'quick',
    researchMode,
    onToken,
    onSession,
    onStart,
    onFallback,
    onRestart,
    onSources,
    onDone,
    onError,
    signal,
  })
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`)
  return response.json()
}

async function parseError(response, fallback) {
  const err = await response.json().catch(() => ({}))
  return err?.detail || fallback
}

export async function generatePortfolioDiagram(content, diagramHint, userId = 'default', signal) {
  const response = await fetch(`${API_BASE}/api/portfolio/diagram`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({ content, diagram_hint: diagramHint || null, user_id: userId }),
  })
  if (!response.ok) throw new Error(await parseError(response, 'Diagram generation failed'))
  return response.json()
}

export async function generateNotebookDiagram(notebookId, activeSources = [], diagramHint = null, userId = 'default', signal) {
  if (!notebookId) throw new Error('No active notebook selected')
  const response = await fetch(`${API_BASE}/api/notebooks/${encodeURIComponent(notebookId)}/mindmap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({ active_sources: activeSources, diagram_hint: diagramHint || null, user_id: userId }),
  })
  if (!response.ok) throw new Error(await parseError(response, 'Diagram generation failed'))
  return response.json()
}

export async function getJob(jobId, signal) {
  const response = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`, { signal })
  if (!response.ok) throw new Error(await parseError(response, 'Job lookup failed'))
  return response.json()
}

export async function pollJob(jobId, onProgress, signal, intervalMs = 1000) {
  while (true) {
    const job = await getJob(jobId, signal)
    onProgress?.(job)
    if (job.status === 'completed') return job
    if (job.status === 'failed') throw new Error(job.error || 'Background job failed')
    await new Promise((resolve, reject) => {
      let settled = false
      const onAbort = () => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      }
      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        signal?.removeEventListener('abort', onAbort)
        resolve()
      }, intervalMs)
      signal?.addEventListener('abort', onAbort, { once: true })
    })
  }
}
