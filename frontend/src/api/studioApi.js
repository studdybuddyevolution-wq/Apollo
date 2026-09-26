const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function friendlyError(detail, status) {
  const text = String(detail || '').trim()
  if (text) return text
  if (status === 429) return 'Marklyf is rate-limited right now. Please try again shortly.'
  if (status >= 500) return 'Marklyf could not complete this Studio generation right now.'
  return `Marklyf API returned ${status}`
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

export async function generateStudyReport(
  notebookId,
  activeSources = [],
  {
    reportMode = 'study',
    reportFocus = '',
    requestedSections = [],
    userId = 'default',
    signal,
    onProgress,
  } = {},
) {
  if (!notebookId) throw new Error('No active notebook selected')
  const response = await fetch(
    `${API_BASE}/api/notebooks/${encodeURIComponent(notebookId)}/studio/report/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      signal,
      body: JSON.stringify({
        tool: 'report',
        active_sources: activeSources,
        user_id: userId,
        report_mode: reportMode,
        report_focus: reportFocus || null,
        requested_sections: requestedSections,
      }),
    },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(friendlyError(payload?.detail, response.status))
  }
  if (!response.body) throw new Error('Marklyf did not return a report stream.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  const consume = (chunk) => {
    buffer += decoder.decode(chunk, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const line = frame
        .split('\n')
        .find((entry) => entry.startsWith('data:'))
      if (!line) continue
      try {
        const event = JSON.parse(line.slice(5).trim())
        if (event.type === 'progress') onProgress?.(event)
        if (event.type === 'error') throw new Error(event.message || 'Study Report generation failed.')
        if (event.type === 'done') result = event.result
      } catch (error) {
        if (error instanceof SyntaxError) continue
        throw error
      }
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    consume(value)
  }
  consume(new Uint8Array())

  if (!result) throw new Error('Marklyf did not return a completed Study Report.')
  return result
}

export async function regenerateStudyReportSection(
  notebookId,
  sectionHeading,
  activeSources = [],
  { reportMode = 'study', reportFocus = '', userId = 'default', signal } = {},
) {
  if (!notebookId) throw new Error('No active notebook selected')
  return requestJson(
    `/api/notebooks/${encodeURIComponent(notebookId)}/studio/report/section`,
    {
      report_mode: reportMode,
      report_focus: reportFocus || null,
      section_heading: sectionHeading,
      active_sources: activeSources,
      user_id: userId,
    },
    signal,
  )
}

export async function exportStudyReportDocx(
  notebookId,
  markdown,
  title,
  userId = 'default',
  signal,
) {
  if (!notebookId) throw new Error('No active notebook selected')
  return requestJson(
    `/api/notebooks/${encodeURIComponent(notebookId)}/studio/report/docx`,
    {
      markdown,
      title: title || 'Marklyf Study Report',
    },
    signal,
  )
}
