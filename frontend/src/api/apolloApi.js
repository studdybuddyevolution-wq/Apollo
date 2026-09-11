const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function streamChat({
  messages,
  model = 'qwen/qwen3.6-27b',
  notebookId,
  notebookTitle,
  activeSources = [],
  onToken,
  onStart,
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
    }),
  })

  if (!response.ok) {
    throw new Error(`Apollo API returned ${response.status}`)
  }

  if (!response.body) {
    throw new Error('Apollo API did not return a streaming response')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const consumeEvent = (rawEvent) => {
    const data = rawEvent
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('')

    if (!data) return

    const payload = JSON.parse(data)
    if (payload.type === 'start') onStart?.(payload)
    if (payload.type === 'token') onToken?.(payload.text || '')
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
