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

async function streamChatOnce({
  messages,
  model,
  notebookId,
  notebookTitle,
  activeSources,
  userId,
  webEnabled,
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
      // Normal chat uses the 120B model. Live web work uses the smaller
      // 20B bucket so research does not consume the 120B daily quota.
      model: webEnabled ? 'openai/gpt-oss-20b' : model,
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
  let collected = ''
  const collectedSources = []

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
    if (payload.type === 'token') {
      const token = serverWebMode ? cleanWebText(payload.text || '') : (payload.text || '')
      collected += token
      onToken?.(token)
    }
    if (payload.type === 'sources') {
      collectedSources.push(...(payload.sources || []))
      onSources?.(payload.sources || [])
    }
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
  return { text: collected.trim(), sources: collectedSources }
}

export async function streamChat({
  messages,
  model = 'openai/gpt-oss-120b',
  notebookId,
  notebookTitle,
  activeSources = [],
  userId = 'default',
  webEnabled = false,
  researchMode = 'quick',
  onToken,
  onStart,
  onFallback,
  onSources,
  onDone,
  onError,
  signal,
}) {
  const isDeep = researchMode === 'deep' || researchMode === 'study'

  if (!isDeep) {
    return streamChatOnce({
      messages,
      model,
      notebookId,
      notebookTitle,
      activeSources,
      userId,
      webEnabled,
      onToken,
      onStart,
      onFallback,
      onSources,
      onDone,
      onError,
      signal,
    })
  }

  // Deep Research is a two-pass workflow: two separate research angles are
  // gathered first, then Apollo synthesizes them into one answer. Study mode
  // keeps the active notebook/RAG context enabled during both passes.
  const originalUser = [...messages].reverse().find((message) => message.role === 'user')?.content || ''
  const angles = researchMode === 'study'
    ? [
        `Research this using the user's notebook context and live web sources. Find the strongest external evidence that complements or challenges the notebook. Question: ${originalUser}`,
        `Research this independently using live web sources. Look for authoritative documentation, recent developments, and important caveats that another researcher might miss. Question: ${originalUser}`,
      ]
    : [
        `Research this from a broad factual angle. Find authoritative sources, recent developments, and the most important evidence. Question: ${originalUser}`,
        `Research this from a skeptical/comparative angle. Look for conflicting claims, primary sources, limitations, and details that would change the conclusion. Question: ${originalUser}`,
      ]

  let dossier = ''
  const dossierSources = []

  for (const angle of angles) {
    const pass = await streamChatOnce({
      messages: [{ role: 'user', content: angle }],
      model,
      notebookId,
      notebookTitle,
      activeSources,
      userId,
      webEnabled: true,
      onSources: (sources) => dossierSources.push(...sources),
      signal,
    })
    dossier += `\n\nRESEARCH PASS:\n${pass.text}`
  }

  const synthesisMessages = [
    ...messages,
    {
      role: 'user',
      content: `You are completing a Deep Research task. Use the research dossier below as evidence. Synthesize it into a clear, original answer to the user's question. Resolve contradictions where possible, prefer stronger/primary evidence, and do not mention the research workflow.\n\nRESEARCH DOSSIER:\n${dossier}`,
    },
  ]

  onStart?.({ type: 'start', model: 'openai/gpt-oss-20b', provider: 'groq', web: false, research: researchMode })
  if (dossierSources.length) {
    const uniqueSources = [...new Map(dossierSources.map((source) => [source.url || source.title, source])).values()]
    onSources?.(uniqueSources.slice(0, 8))
  }

  const result = await streamChatOnce({
    messages: synthesisMessages,
    model: 'openai/gpt-oss-20b',
    notebookId,
    notebookTitle,
    activeSources,
    userId,
    webEnabled: false,
    onToken,
    onError,
    signal,
  })

  onDone?.({ type: 'done', research: researchMode })
  return result
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`)
  return response.json()
}
