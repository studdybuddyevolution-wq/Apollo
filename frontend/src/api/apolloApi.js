import { authFetch } from './authApi'
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function displayErrorDetail(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (typeof value === 'object') {
    return String(value.detail || value.message || value.error || value.title || '')
  }
  return String(value)
}

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
  socraticTopic = '',
  socraticScore = null,
  socraticForceAdvance = false,
  onToken,
  onSession,
  onStart,
  onFallback,
  onRestart,
  onGroundingCheck,
  onSocraticState,
  onSources,
  onDone,
  onError,
  signal,
}) {
  const workspace = Boolean(notebookId)
  const response = await authFetch(`${API_BASE}${workspace ? '/api/chat/workspace' : '/api/chat'}`, {
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
      socratic_topic: socraticTopic || null,
      socratic_score: socraticScore ?? null,
      socratic_force_advance: Boolean(socraticForceAdvance),
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
    if (payload.type === 'grounding_check') onGroundingCheck?.(payload)
    if (payload.type === 'socratic_state') onSocraticState?.(payload)
    if (payload.type === 'token') {
      const token = serverResearch === 'quick' ? (payload.text || '') : cleanResearchText(payload.text || '')
      onToken?.(token)
    }
    if (payload.type === 'sources') onSources?.(payload.sources || [])
    if (payload.type === 'done') onDone?.(payload)
    if (payload.type === 'error') {
      const safeMessage = displayErrorDetail(payload.message) || 'Apollo backend error'
      onError?.(safeMessage)
      throw new Error(safeMessage)
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
  socraticTopic = '',
  socraticScore = null,
  socraticForceAdvance = false,
  onToken,
  onSession,
  onStart,
  onFallback,
  onRestart,
  onGroundingCheck,
  onSocraticState,
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
    webEnabled: webEnabled || (researchMode !== 'quick' && researchMode !== 'socratic'),
    researchMode,
    socraticTopic,
    socraticScore,
    socraticForceAdvance,
    onToken,
    onSession,
    onStart,
    onFallback,
    onRestart,
    onGroundingCheck,
    onSocraticState,
    onSources,
    onDone,
    onError,
    signal,
  })
}

export async function checkHealth() {
  const response = await authFetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`)
  return response.json()
}

async function parseError(response, fallback) {
  const err = await response.json().catch(() => ({}))
  const detail = err?.detail || fallback
  const normalized = String(detail).toUpperCase()
  if (response.status >= 500 && (normalized.includes('UNAVAILABLE') || normalized.includes('HIGH DEMAND') || normalized.includes('503'))) {
    return 'Gemini is temporarily busy. Apollo will retry automatically.'
  }
  return detail
}

function isTransientDiagramError(error) {
  const text = String(error?.message || '').toUpperCase()
  return text.includes('503') || text.includes('UNAVAILABLE') || text.includes('HIGH DEMAND') || text.includes('TEMPORARILY BUSY')
}

function sleepWithSignal(ms, signal) {
  return new Promise((resolve, reject) => {
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
    }, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
    if (signal?.aborted) onAbort()
  })
}

export async function generatePortfolioDiagram(content, diagramHint, userId = 'default', signal) {
  const response = await authFetch(`${API_BASE}/api/portfolio/diagram`, {
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

  const maxAttempts = 4
  const retryDelays = [1200, 2500, 4500]
  let lastError = null

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const response = await authFetch(`${API_BASE}/api/notebooks/${encodeURIComponent(notebookId)}/mindmap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal,
        body: JSON.stringify({ active_sources: activeSources, diagram_hint: diagramHint || null, user_id: userId }),
      })
      if (!response.ok) {
        throw new Error(await parseError(response, `Apollo API returned ${response.status}`))
      }
      return response.json()
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      lastError = error
      const transient = isTransientDiagramError(error)
      if (!transient || attempt === maxAttempts - 1) {
        throw new Error(transient ? 'Gemini is temporarily busy. Please try again in a moment.' : (error?.message || 'Diagram generation failed'))
      }
      await sleepWithSignal(retryDelays[attempt], signal)
    }
  }

  throw lastError || new Error('Diagram generation failed')
}

export async function getJob(jobId, signal) {
  const response = await authFetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`, { signal })
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


export async function getSocraticState(notebookId, sessionId, userId = 'default') {
  const response = await authFetch(
    `${API_BASE}/api/notebooks/${encodeURIComponent(notebookId)}/sessions/${encodeURIComponent(sessionId)}/socratic-state?user_id=${encodeURIComponent(userId)}`,
  )
  if (!response.ok) throw new Error(await parseError(response, 'Socratic session state lookup failed'))
  return response.json()
}

export async function generateSocraticQuickCheck({
  topic,
  tier,
  score,
  notebookId,
  activeSources = [],
  sourceModes = {},
  userId = 'default',
  model = null,
  signal,
}) {
  const response = await authFetch(`${API_BASE}/api/socratic/quick-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      topic,
      tier,
      score,
      notebook_id: notebookId,
      active_sources: activeSources,
      source_modes: sourceModes,
      user_id: userId,
      model,
    }),
  })
  if (!response.ok) throw new Error(await parseError(response, 'Quick Check generation failed'))
  return response.json()
}

export async function gradeSocraticQuickCheck({
  topic,
  question,
  expectedAnswer,
  studentAnswer,
  currentScore,
  notebookId,
  sessionId,
  userId = 'default',
  model = null,
  signal,
}) {
  const response = await authFetch(`${API_BASE}/api/socratic/quick-check/grade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      topic,
      question,
      expected_answer: expectedAnswer,
      student_answer: studentAnswer,
      current_score: currentScore,
      notebook_id: notebookId,
      session_id: sessionId,
      user_id: userId,
      model,
    }),
  })
  if (!response.ok) throw new Error(await parseError(response, 'Quick Check grading failed'))
  return response.json()
}