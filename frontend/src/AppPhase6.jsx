import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp, BookOpen, BrainCircuit, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, FileText, FolderOpen, Globe, History, ImagePlus, LayoutDashboard,
  LoaderCircle, Paperclip, Plus, Search, Save, Settings, Sparkles, Upload, User,
  Video, Mic, WandSparkles, X, Activity, SlidersHorizontal, MessageSquarePlus, Trash2, RefreshCw, Square, Pencil,
} from 'lucide-react'
import { getSocraticState, generateSocraticQuickCheck, gradeSocraticQuickCheck, streamChat } from './api/apolloApi'
import { generateNotebookMindMap, generateStudioOutput } from './api/studioApi'
import PastSessionsPage from './PastSessionsPage'
import ProgressDashboardPage from './ProgressDashboardPage'
import {
  createNote, createNotebook, createSession, deleteNote, deleteSession,
  getSessionMessages, listNotes, listNotebooks, listSessions, listSources,
  renameSession, uploadSource, deleteNotebook, renameNotebook, deleteSource, retrySource, refreshSource, getCapabilities, searchNotebook,
} from './api/notebooksApi'
import MarkdownMessage from './MarkdownMessage'
import SourceImportBar from './SourceImportBar'
import './console-clean.css'

const NAV_ITEMS = [
  { id: 'console', label: 'Console & Tools', icon: Sparkles },
  { id: 'tutor', label: 'Socratic Tutor', icon: BrainCircuit },
  { id: 'progress', label: 'Progress Dashboard', icon: LayoutDashboard },
  { id: 'planner', label: 'Study Planner', icon: Activity },
  { id: 'sessions', label: 'Past Sessions', icon: History },
  { id: 'settings', label: 'User Settings & Profile', icon: Settings },
]

const RESEARCH_MODES = [
  { id: 'quick', label: 'Quick answer', icon: Sparkles, description: 'Fast answer from Marklyf' },
  { id: 'socratic', label: 'Socratic Tutor', icon: BrainCircuit, description: 'Guided reasoning instead of direct answers' },
  { id: 'web', label: 'Web search', icon: Globe, description: 'Current information + sources' },
  { id: 'deep', label: 'Deep Research', icon: SlidersHorizontal, description: 'Multi-step web research' },
  { id: 'study', label: 'Study Research', icon: BookOpen, description: 'Notebook + web synthesis' },
]

const STUDIO_TOOLS = [
  { id: 'slides', label: 'Slide Deck', description: 'Build a grounded presentation', icon: FileText },
  { id: 'report', label: 'Study Report', description: 'Create structured revision notes', icon: FileText },
  { id: 'mindmap', label: 'Mind Map', description: 'Build a visual concept structure', icon: BrainCircuit },
  { id: 'transform', label: 'Transformations', description: 'Extract reusable study insights', icon: WandSparkles },
  { id: 'podcast', label: 'Podcast / Audio', description: 'Create a narrated source overview', icon: Mic },
  { id: 'video', label: 'Video Overview', description: 'Storyboard support coming next', icon: Video },
]

const SOURCE_MODES = [
  { id: 'full', label: 'Full source', description: 'Use source text + saved insights' },
  { id: 'summary', label: 'Summary', description: 'Use the saved source summary only' },
  { id: 'insights', label: 'Insights only', description: 'Use only saved AI insights' },
  { id: 'off', label: 'Off', description: 'Exclude this source' },
]

function toDisplayText(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(toDisplayText).filter(Boolean).join('\n')
  if (typeof value === 'object') {
    const preferred = ['text', 'content', 'message', 'answer', 'feedback', 'verdict', 'question']
    for (const key of preferred) {
      if (value[key] != null) {
        const rendered = toDisplayText(value[key])
        if (rendered) return rendered
      }
    }
    try { return JSON.stringify(value, null, 2) } catch { return '' }
  }
  return String(value)
}

function normalizeMessage(message) {
  if (!message || typeof message !== 'object') return message
  return { ...message, content: toDisplayText(message.content) }
}

function getUserId() {
  const key = 'apollo-user-id'
  let value = localStorage.getItem(key)
  if (!value) {
    value = `user_${crypto.randomUUID()}`
    localStorage.setItem(key, value)
  }
  return value
}

function recentKey(type, userId, notebookId = '') {
  return type === 'notebooks'
    ? `apollo-recent-notebooks:${userId}`
    : `apollo-recent-sources:${userId}:${notebookId}`
}

function readRecent(type, userId, notebookId = '') {
  try {
    const value = JSON.parse(localStorage.getItem(recentKey(type, userId, notebookId)) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

function rememberRecent(type, id, userId, notebookId = '') {
  if (!id) return
  const key = recentKey(type, userId, notebookId)
  const current = readRecent(type, userId, notebookId).filter((value) => value !== id)
  localStorage.setItem(key, JSON.stringify([id, ...current].slice(0, 12)))
}

function readSourceModes(userId, notebookId) {
  try {
    const value = JSON.parse(localStorage.getItem(`apollo-source-modes:${userId}:${notebookId}`) || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch {
    return {}
  }
}

function saveSourceModes(userId, notebookId, modes) {
  localStorage.setItem(`apollo-source-modes:${userId}:${notebookId}`, JSON.stringify(modes))
}

function Sidebar({ active, setActive, collapsed, setCollapsed, notebooks, activeId, setNotebook, create, renameNotebookUi, removeNotebook }) {
  const [open, setOpen] = useState(true)
  return (
    <aside className={`apollo-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="brand-mark"><img src="/apollo-logo-mark.svg" alt="Marklyf" width="28" height="28" /></div>
        {!collapsed && <div><div className="brand-name">MARKLYF</div><div className="brand-subtitle">OMNI AI</div></div>}
        <button className="icon-button sidebar-toggle" onClick={() => setCollapsed((v) => !v)} aria-label="Toggle sidebar">
          {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
        </button>
      </div>
      {!collapsed && <div className="sidebar-label">NAVIGATION</div>}
      <nav className="nav-list">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => setActive(id)}>
            <Icon size={18} />{!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>
      {!collapsed && (
        <div className="notebook-section">
          <button className="section-heading" onClick={() => setOpen((v) => !v)}>
            <span><BookOpen size={15} /> NOTEBOOK</span><ChevronDown size={15} className={open ? '' : 'rotate'} />
          </button>
          {open && <div className="notebook-content">
            {notebooks.map((nb) => (
              <div
                key={nb.id}
                className={`notebook-row ${activeId === nb.id ? 'active' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => setNotebook(nb.id)}
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setNotebook(nb.id) } }}
              >
                <span className="notebook-title"><BookOpen size={15} />{nb.title}</span>
                <span className="notebook-row-right"><span className="source-count">{nb.source_count || 0} src</span><button className="notebook-rename" title={`Rename ${nb.title}`} aria-label={`Rename ${nb.title}`} onClick={(event) => { event.stopPropagation(); renameNotebookUi(nb) }}><Pencil size={12} /></button><button className="notebook-delete" title={`Delete ${nb.title}`} aria-label={`Delete ${nb.title}`} onClick={(event) => { event.stopPropagation(); removeNotebook(nb) }}><Trash2 size={13} /></button></span>
              </div>
            ))}
            {!notebooks.length && <div className="notebook-row"><span className="notebook-title">No notebooks yet</span></div>}
            <button className="new-notebook" onClick={create}><Plus size={15} /> New Notebook</button>
          </div>}
        </div>
      )}
      <div className="sidebar-footer">
        {!collapsed && <div className="system-status"><span className="status-dot" /> System ready</div>}
        <button className="help-button"><CircleHelp size={17} />{!collapsed && 'Help & feedback'}</button>
      </div>
    </aside>
  )
}

function TopBar({ active, toggleSources, toggleStudio, toggleSessions, toggleNotes, researchMode, setResearchMode }) {
  const item = NAV_ITEMS.find((n) => n.id === active) || NAV_ITEMS[0]
  const currentMode = RESEARCH_MODES.find((m) => m.id === researchMode) || RESEARCH_MODES[0]
  return (
    <header className="topbar">
      <div className="topbar-left"><div className="breadcrumb"><span className="breadcrumb-muted">Marklyf</span><span>/</span><strong>{item.label}</strong></div></div>
      <div className="topbar-actions">
        {(active === 'console' || active === 'tutor') && <>
          <button className="topbar-tool" onClick={toggleSessions}><History size={16} /> Chats</button>
          <button className="topbar-tool" onClick={toggleNotes}><Save size={16} /> Notes</button>
          <button className="topbar-tool" onClick={toggleSources}><FolderOpen size={16} /> Sources</button>
          {active === 'console' && <button className="topbar-tool" onClick={toggleStudio}><WandSparkles size={16} /> Studio</button>}
          {active === 'console' && <label className="research-mode-select" title="Choose how Marklyf researches this question">
            <currentMode.icon size={15} />
            <select value={researchMode} onChange={(e) => setResearchMode(e.target.value)} aria-label="Research mode">
              {RESEARCH_MODES.map((mode) => <option key={mode.id} value={mode.id}>{mode.label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>}
        </>}
        <button className="topbar-chip"><span className="status-dot" /> Online</button>
      </div>
    </header>
  )
}

function Bubble({ message, onSaveNote, canSaveNote = true }) {
  const me = message.role === 'user'
  const content = toDisplayText(message.content)
  return (
    <article className={`message-row ${me ? 'user' : 'assistant'}`}>
      <div className={`message-avatar ${me ? 'user-avatar' : ''}`}>{me ? <User size={15} /> : <img src="/apollo-logo-mark.svg" alt="Marklyf" width="22" height="22" />}</div>
      <div className="message-content">
        <div className="message-meta"><span>{me ? 'You' : 'Marklyf'}</span>{!me && message.model && <span className="message-model">{message.model}</span>}</div>
        <div className="message-text">{content ? <MarkdownMessage content={content} sources={message.sources} /> : (message.streaming && <span className="streaming-caret" />)}</div>
        {message.sources?.length > 0 && <div className="message-sources">
          {message.sources.map((source) => <a className="citation-pill web-citation" key={source.url || source.title} href={source.url} target="_blank" rel="noreferrer"><Globe size={11} /> {source.title || source.url}</a>)}
        </div>}
        {!me && message.groundingWarning && <div role="status" className="grounding-review">
          <strong>Grounding review</strong>
          <span>{message.groundingWarning}</span>
          {typeof message.overlapRatio === 'number' && <span>Source overlap: {Math.round(message.overlapRatio * 100)}%</span>}
        </div>}
        {!me && canSaveNote && content && !message.streaming && <button className="citation-pill" onClick={() => onSaveNote(message)} title="Save this answer to notebook notes"><Save size={11} /> Save note</button>}
      </div>
    </article>
  )
}

function Composer({ send, stop, busy, researchMode }) {
  const [value, setValue] = useState('')
  const mode = RESEARCH_MODES.find((item) => item.id === researchMode) || RESEARCH_MODES[0]
  const submit = () => {
    if (!value.trim() || busy) return
    send(value.trim())
    setValue('')
  }
  return (
    <div className="composer-wrap chat-composer-wrap">
      <div className="composer composer-live">
        <button className="composer-icon" disabled><Paperclip size={18} /></button>
        <button className="composer-icon" disabled><ImagePlus size={18} /></button>
        <input value={value} disabled={busy} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder={`${mode.label} — message Marklyf…`} />
        {busy ? <button className="send-button stop-button" onClick={stop} title="Stop response" aria-label="Stop response"><Square size={16} /></button> : <button className="send-button" onClick={submit} disabled={!value.trim()}><ArrowUp size={18} /></button>}
      </div>
      <div className="composer-meta-row"><span>Enter to send</span><span>Shift + Enter for a new line</span><span>{busy ? 'Generation in progress — press stop to cancel' : mode.description}</span></div>
    </div>
  )
}

function downloadBase64File(base64, filename, mimeType) {
  const binary = window.atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  const blob = new Blob([bytes], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function SourcePanel({ notebooks, activeId, sources, sourceModes, setSourceMode, setAllSourceMode, setActiveId, create, upload, close, userId, refreshSources, removeSource, retrySource, refreshSource }) {
  const input = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [knowledgeQuery, setKnowledgeQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const nb = notebooks.find((n) => n.id === activeId)
  const recentSources = readRecent('sources', userId, activeId)
  const visibleSources = sources
    .filter((source) => source.name.toLowerCase().includes(query.toLowerCase()))
    .filter((source) => statusFilter === 'all' || (statusFilter === 'ready' ? ['indexed', 'completed'].includes(source.status) : source.status === statusFilter))
    .sort((a, b) => {
      const aIndex = recentSources.indexOf(a.name)
      const bIndex = recentSources.indexOf(b.name)
      if (aIndex === -1 && bIndex === -1) return a.name.localeCompare(b.name)
      if (aIndex === -1) return 1
      if (bIndex === -1) return -1
      return aIndex - bIndex
    })
  const enabledCount = sources.filter((source) => (sourceModes[source.name] || 'full') !== 'off').length
  const runContentSearch = async () => {
    if (!activeId || !knowledgeQuery.trim()) return
    setSearching(true)
    try {
      const result = await searchNotebook(activeId, knowledgeQuery.trim(), { topK: 6, sourceNames: sources.filter((source) => (sourceModes[source.name] || 'full') !== 'off').map((source) => source.name), userId })
      setSearchResults(result.results || [])
    } catch (error) {
      setSearchResults([])
      setActionMessage(error?.message || 'Search failed.')
    } finally {
      setSearching(false)
    }
  }

  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !nb) return
    setUploading(true)
    setActionMessage('')
    try {
      await upload(file)
      setActionMessage('Source added and queued for indexing.')
    } catch (error) {
      setActionMessage(error?.message || 'Source upload failed.')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const runSourceAction = async (action, source, successMessage) => {
    setActionMessage('')
    try {
      await action(source)
      setActionMessage(successMessage)
    } catch (error) {
      setActionMessage(error?.message || 'Source action failed.')
    }
  }

  return (
    <aside className="context-panel source-panel">
      <div className="context-header"><div><div className="context-kicker">KNOWLEDGE BASE</div><h2><FolderOpen size={17} /> Sources</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div>
      <p className="context-description">Choose how much of each source Marklyf can use for chat and research.</p>
      <div className="notebook-picker"><span className="muted-label">ACTIVE NOTEBOOK</span><select className="notebook-picker-button" value={activeId} onChange={(e) => setActiveId(e.target.value)}>{notebooks.map((n) => <option key={n.id} value={n.id}>{n.title}</option>)}</select></div>
      <div className="source-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search sources..." /></div>
      <SourceImportBar notebookId={activeId} userId={userId} onImported={refreshSources} />
      <div className="source-bulk-controls">
        <span className="muted-label">CONTEXT PRESET</span>
        <div className="segmented-control source-presets">
          <button onClick={() => setAllSourceMode('full')}>All full</button>
          <button onClick={() => setAllSourceMode('summary')}>Summaries</button>
          <button onClick={() => setAllSourceMode('insights')}>Insights</button>
          <button onClick={() => setAllSourceMode('off')}>None</button>
        </div>
      </div>
      <div className="source-search-tools">
        <div className="knowledge-search">
          <Search size={14} />
          <input value={knowledgeQuery} onChange={(e) => setKnowledgeQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); runContentSearch() } }} placeholder="Search inside indexed sources…" />
          <button onClick={runContentSearch} disabled={searching || !knowledgeQuery.trim()}>{searching ? '…' : 'Ask'}</button>
        </div>
        <div className="source-filter-row">
          {['all', 'ready', 'processing', 'failed'].map((filter) => <button key={filter} className={statusFilter === filter ? 'selected' : ''} onClick={() => setStatusFilter(filter)}>{filter === 'all' ? 'All' : filter === 'ready' ? 'Ready' : filter[0].toUpperCase() + filter.slice(1)}</button>)}
        </div>
        {searchResults.length > 0 && <div className="search-result-list">
          {searchResults.map((result, index) => <button key={(result.id || result.source || 'result') + '-' + index} className="search-result" onClick={() => { if (result.source) { rememberRecent('sources', result.source, userId, activeId); setQuery(result.source) } }}>
            <strong>{result.source}</strong>
            <span>{String(result.text || '').slice(0, 220)}{String(result.text || '').length > 220 ? '…' : ''}</span>
          </button>)}
        </div>}
      </div>
      <input ref={input} hidden type="file" accept=".pdf,.docx,.txt,.md,.csv" onChange={onFile} />
      <div className="source-list">{visibleSources.map((s) => {
        const mode = sourceModes[s.name] || 'full'
        const modeLabel = SOURCE_MODES.find((item) => item.id === mode)?.label || 'Full source'
        const failed = s.status === 'failed'
        const processing = ['pending', 'processing'].includes(s.status)
        const refreshable = s.kind === 'url' || s.kind === 'youtube'
        return <div key={s.name} className={`source-card ${mode !== 'off' ? 'selected' : ''}`} style={{ cursor: 'default' }}>
          <div className="source-icon"><FileText size={16} /></div>
          <div className="source-card-copy"><strong title={s.name}>{s.name}</strong><span>{s.chunks} chunks · {s.kind || 'file'} · {s.status || 'indexed'}</span>{s.error && <small className="source-error">{s.error}</small>}</div>
          <select aria-label={`Context mode for ${s.name}`} value={mode} onChange={(e) => setSourceMode(s.name, e.target.value)} style={{ width: 94, fontSize: 10, borderRadius: 7, padding: '5px 4px' }}>
            {SOURCE_MODES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
          <div className="source-actions">
            {(failed || processing) && <button className="icon-button" title={processing ? 'Retry indexing' : 'Retry source'} onClick={() => runSourceAction(retrySource, s, 'Source retry queued.') }><RefreshCw size={13} /></button>}
            {refreshable && <button className="icon-button" title="Refresh source" onClick={() => runSourceAction(refreshSource, s, 'Source refreshed and queued for indexing.') }><RefreshCw size={13} /></button>}
            <button className="icon-button" title="Delete source" onClick={() => runSourceAction(removeSource, s, 'Source deleted.')}><Trash2 size={13} /></button>
          </div>
          <span className="source-check" title={modeLabel}>{mode === 'full' ? '●' : mode === 'summary' ? '◉' : mode === 'insights' ? '◐' : '○'}</span>
        </div>
      })}{!visibleSources.length && <div className="source-empty-state"><FolderOpen size={22} /><strong>{sources.length ? 'No matching sources' : 'No sources connected'}</strong><span>{sources.length ? 'Try another source name.' : 'Upload a PDF, DOCX, TXT, Markdown or CSV file.'}</span></div>}</div>
      {actionMessage && <div className="source-action-message" role="status">{actionMessage}</div>}
      <div className="source-footer"><div className="source-stats"><span><strong>{enabledCount}</strong> enabled</span><span><strong>{sources.length}</strong> total</span></div><button className="upload-button" disabled={!nb || uploading} onClick={() => input.current?.click()}><Upload size={15} /> {uploading ? 'Indexing…' : 'Add sources'}</button></div>
      <button className="new-notebook" onClick={create}><Plus size={15} /> New Notebook</button>
    </aside>
  )
}
function SessionPanel({ sessions, activeSessionId, selectSession, createNew, rename, remove, close }) {
  return <aside className="context-panel studio-panel">
    <div className="context-header"><div><div className="context-kicker">CONVERSATIONS</div><h2><History size={17} /> Chats</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div>
    <p className="context-description">Keep separate conversations inside the same notebook.</p>
    <button className="upload-button" onClick={createNew}><MessageSquarePlus size={15} /> New chat</button>
    <div style={{ marginTop: 12, display: 'grid', gap: 7 }}>
      {sessions.map((session) => <div key={session.id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: 7, borderRadius: 9, border: '1px solid var(--surface-high)', background: session.id === activeSessionId ? 'var(--surface-container)' : 'transparent' }}>
        <button onClick={() => selectSession(session.id)} style={{ flex: 1, minWidth: 0, textAlign: 'left', background: 'none', border: 0, color: 'var(--text)', cursor: 'pointer', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.title}</button>
        <button className="icon-button" title="Rename" onClick={() => rename(session)}><FileText size={13} /></button>
        <button className="icon-button" title="Delete" onClick={() => remove(session)}><X size={13} /></button>
      </div>)}
      {!sessions.length && <div className="source-empty-state"><History size={22} /><strong>No chats yet</strong><span>Start a new conversation.</span></div>}
    </div>
  </aside>
}

function NotesPanel({ notes, remove, close }) {
  return <aside className="context-panel studio-panel">
    <div className="context-header"><div><div className="context-kicker">NOTEBOOK</div><h2><Save size={17} /> Saved Notes</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div>
    <p className="context-description">Save useful Marklyf answers so they stay with this notebook.</p>
    <div style={{ display: 'grid', gap: 9, marginTop: 12 }}>
      {notes.map((note) => <article key={note.id} style={{ padding: 10, borderRadius: 10, border: '1px solid var(--surface-high)', background: 'var(--surface-container)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><strong style={{ flex: 1, fontSize: 12 }}>{note.title}</strong><button className="icon-button" title="Delete note" onClick={() => remove(note)}><X size={13} /></button></div>
        <p style={{ margin: '8px 0 0', fontSize: 11, lineHeight: 1.55, color: 'var(--tertiary)', whiteSpace: 'pre-wrap' }}>{note.content}</p>
      </article>)}
      {!notes.length && <div className="source-empty-state"><Save size={22} /><strong>No saved notes</strong><span>Use “Save note” on a Marklyf answer.</span></div>}
    </div>
  </aside>
}

function StudioPanel({ close, tool, setTool, activeId, sources, activeSources, userId, openSources }) {
  const current = STUDIO_TOOLS.find((x) => x.id === tool) || STUDIO_TOOLS[0]
  const [diagram, setDiagram] = useState(null)
  const [output, setOutput] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [transformation, setTransformation] = useState('summary')
  const [customPrompt, setCustomPrompt] = useState('')
  const [availableModels, setAvailableModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [speaking, setSpeaking] = useState(false)
  const abortRef = useRef(null)

  const transformations = [
    ['summary', 'Summary'],
    ['key_concepts', 'Key concepts'],
    ['faq', 'FAQ'],
    ['outline', 'Outline'],
    ['glossary', 'Glossary'],
    ['quiz', 'Quiz'],
    ['study_guide', 'Study guide'],
    ['timeline', 'Timeline'],
    ['compare_contrast', 'Compare / contrast'],
    ['explain_simply', 'Explain simply'],
    ['misconceptions', 'Misconceptions'],
    ['custom', 'Custom'],
  ]

  useEffect(() => {
    getCapabilities().then((data) => setAvailableModels(data?.ai_models || [])).catch(() => {})
  }, [])

  useEffect(() => () => {
    abortRef.current?.abort()
    window.speechSynthesis?.cancel()
  }, [])

  const generate = async () => {
    if (!activeId || !activeSources.length || generating) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 65000)
    setGenerating(true)
    setError('')
    setDiagram(null)
    setOutput(null)
    try {
      if (tool === 'mindmap') {
        const result = await generateNotebookMindMap(activeId, activeSources, null, userId, controller.signal)
        setDiagram(result)
      } else {
        const result = await generateStudioOutput(activeId, tool, activeSources, {
          transformationType: tool === 'transform' ? transformation : null,
          customPrompt: tool === 'transform' && transformation === 'custom' ? customPrompt : null,
          model: tool === 'transform' ? (selectedModel || null) : null,
          userId,
          signal: controller.signal,
        })
        setOutput(result)
      }
    } catch (err) {
      if (err?.name === 'AbortError') setError('Studio generation timed out before Marklyf returned a complete result.')
      else setError(err?.message || 'Studio generation failed')
    } finally {
      window.clearTimeout(timeout)
      if (abortRef.current === controller) abortRef.current = null
      setGenerating(false)
    }
  }

  const playPodcast = () => {
    const script = output?.script
    if (!script || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(script)
    utterance.rate = 0.96
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    setSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  const stopPodcast = () => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }

  const activeNames = sources.filter((source) => activeSources.includes(source.name)).map((source) => source.name)
  const canGenerate = Boolean(activeId && activeSources.length && !generating)

  return <aside className="context-panel studio-panel">
    <div className="context-header"><div><div className="context-kicker">WORKSPACE</div><h2><WandSparkles size={17} /> Studio</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div>
    <p className="context-description">Every Studio output is generated from the selected Marklyf notebook sources and saved as a reusable insight.</p>

    {!sources.length ? <div style={{ padding: 14, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)', fontSize: 12, lineHeight: 1.5, marginBottom: 14 }}>
      <strong style={{ display: 'block', marginBottom: 8, color: 'var(--text)' }}>Connect a source first</strong>
      <button className="upload-button" onClick={openSources}><FolderOpen size={15} /> Open Sources</button>
    </div> : <>
      <div style={{ padding: 11, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)', fontSize: 11, lineHeight: 1.5, marginBottom: 12 }}>
        <strong style={{ display: 'block', marginBottom: 5, color: 'var(--text)' }}>Grounded in</strong>
        <span style={{ color: 'var(--tertiary)' }}>{activeNames.join(', ') || 'no active sources'}</span>
      </div>

      {tool === 'transform' && <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
        <label className="muted-label" htmlFor="apollo-transformation">TRANSFORMATION</label>
        <select id="apollo-transformation" value={transformation} onChange={(e) => setTransformation(e.target.value)} style={{ width: '100%', padding: '8px 9px', borderRadius: 8 }}>
          {transformations.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <label className="muted-label" htmlFor="apollo-studio-model">MODEL</label>
        <select id="apollo-studio-model" value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)} style={{ width: '100%', padding: '8px 9px', borderRadius: 8 }}>
          <option value="">Auto (configured fallback)</option>
          {availableModels.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        {transformation === 'custom' && <textarea value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)} placeholder="Describe the transformation you want…" rows={4} style={{ width: '100%', resize: 'vertical', padding: 9, borderRadius: 8 }} />}
      </div>}

      {error && <div role="alert" style={{ marginBottom: 10, padding: 9, borderRadius: 8, background: 'rgba(127,29,29,.32)', border: '1px solid #ef4444', color: '#fecaca', fontSize: 11, lineHeight: 1.45 }}>{error}</div>}

      {diagram?.svg && <div style={{ marginBottom: 12 }}>
        {diagram.warning && <div role="alert" style={{ marginBottom: 8, padding: 9, borderRadius: 8, background: 'rgba(127,29,29,.45)', border: '1px solid #ef4444', color: '#fee2e2', fontSize: 11, lineHeight: 1.45 }}><strong>Review:</strong> {diagram.warning}</div>}
        <div style={{ padding: 8, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)', overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: diagram.svg }} />
        <div style={{ marginTop: 7, color: 'var(--tertiary)', fontSize: 10 }}>Model: {diagram.model_used || 'Gemini'} · {Math.round((diagram.overlap_ratio || 0) * 100)}% source-label overlap</div>
      </div>}

      {output?.tool === 'slides' && <div style={{ display: 'grid', gap: 8, maxHeight: 420, overflow: 'auto', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>{output.title || output.data?.title || 'Slide Deck'}</div>
          {output.pptx_base64 && <button
            className="upload-button"
            style={{ width: 'auto', padding: '0 10px' }}
            onClick={() => downloadBase64File(output.pptx_base64, output.filename || 'Marklyf-Slide-Deck.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')}
          >Download PPTX</button>}
        </div>
        <div style={{ color: 'var(--tertiary)', fontSize: 10 }}>Grounded in: {(output.source_names || activeNames || []).join(', ') || 'selected notebook sources'}</div>
        {(output.slides || output.data?.slides || []).map((slide, index) => <article key={`${slide.title}-${index}`} style={{ padding: 10, borderRadius: 9, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
          <strong style={{ display: 'block', marginBottom: 6 }}>{index + 1}. {slide.title}</strong>
          {(slide.bullets || []).map((bullet, bulletIndex) => <div key={bulletIndex} style={{ fontSize: 11, lineHeight: 1.45, marginBottom: 3 }}>• {bullet}</div>)}
          {slide.speaker_notes && <div style={{ marginTop: 6, fontSize: 10, color: 'var(--tertiary)' }}>Notes: {slide.speaker_notes}</div>}
        </article>)}
      </div>}

      {output?.tool === 'report' && <div style={{ marginBottom: 12, maxHeight: 420, overflow: 'auto', padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
        {output.warning && <div className="grounding-review" role="status"><strong>Grounding review</strong><span>{output.warning}</span><span>Source overlap: {Math.round((output.overlap_ratio || 0) * 100)}%</span></div>}
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 11, lineHeight: 1.5 }}>{output.markdown}</pre>
      </div>}

      {output?.tool === 'transform' && <div style={{ marginBottom: 12, maxHeight: 420, overflow: 'auto', padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}><pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 11, lineHeight: 1.5 }}>{output.content}</pre></div>}

      {output?.tool === 'podcast' && <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 7, marginBottom: 8 }}>
          <button className="upload-button" onClick={speaking ? stopPodcast : playPodcast}>{speaking ? 'Stop audio' : 'Play audio'}</button>
        </div>
        <div style={{ maxHeight: 420, overflow: 'auto', display: 'grid', gap: 7 }}>
          <strong style={{ fontSize: 14 }}>{output.data?.title || 'Marklyf Audio Overview'}</strong>
          {(output.data?.segments || []).map((segment, index) => <article key={index} style={{ padding: 9, borderRadius: 9, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}><strong style={{ fontSize: 10, textTransform: 'uppercase' }}>{segment.speaker}</strong><div style={{ marginTop: 4, fontSize: 11, lineHeight: 1.45 }}>{segment.text}</div></article>)}
        </div>
      </div>}

      {output?.tool === 'video' && <div style={{ marginBottom: 12, maxHeight: 420, overflow: 'auto', display: 'grid', gap: 7 }}>
        <div style={{ padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
          <strong style={{ display: 'block', marginBottom: 4 }}>{output.data?.title || 'Video Overview'}</strong>
          <span style={{ color: 'var(--tertiary)', fontSize: 10 }}>{output.data?.duration_seconds ? `${output.data.duration_seconds}s storyboard` : 'Storyboard'} · Model: {output.model_used || 'Gemini'} · No video file is rendered here</span>
        </div>
        {(output.data?.scenes || []).map((scene, index) => <article key={`${scene.timecode || index}-${scene.title || ''}`} style={{ padding: 9, borderRadius: 9, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}><strong style={{ display: 'block', marginBottom: 4 }}>{scene.timecode || `Scene ${index + 1}`} · {scene.title}</strong><div style={{ fontSize: 10, lineHeight: 1.45, marginBottom: 4 }}><b>Narration:</b> {scene.narration}</div><div style={{ fontSize: 10, lineHeight: 1.45, marginBottom: 4 }}><b>Visual:</b> {scene.visual}</div><div style={{ fontSize: 10, lineHeight: 1.45 }}><b>On screen:</b> {scene.on_screen_text}</div></article>)}
      </div>}
    </>}

    <div className="studio-tool-list">{STUDIO_TOOLS.map(({ id, label, description, icon: Icon }) => <button key={id} className={`studio-tool ${tool === id ? 'selected' : ''}`} onClick={() => { setTool(id); setError(''); setDiagram(null); setOutput(null) }}><span className="studio-tool-icon"><Icon size={17} /></span><span><strong>{label}</strong><small>{description}</small></span></button>)}</div>
    <div className="studio-footer"><div><strong>{current.label}</strong><span>{generating ? 'Generating…' : (diagram || output ? 'Generated' : 'Ready')}</span></div><button className="studio-generate" disabled={!canGenerate || (tool === 'transform' && transformation === 'custom' && !customPrompt.trim())} onClick={generate}><Sparkles size={15} /> {generating ? 'Generating…' : 'Generate'}</button></div>
  </aside>
}

function SocraticTutor({
  notebook,
  activeSources,
  sourceModes,
  userId,
  sessionId,
  messages,
  busy,
  model,
  socraticState,
  setSocraticState,
  send,
  stop,
  newChat,
  onSaveNote,
}) {
  const [topic, setTopic] = useState(socraticState?.topic || '')
  const [quickCheck, setQuickCheck] = useState(null)
  const [quickAnswer, setQuickAnswer] = useState('')
  const [quickBusy, setQuickBusy] = useState(false)
  const [quickFeedback, setQuickFeedback] = useState(null)

  useEffect(() => {
    setTopic(socraticState?.topic || '')
    setQuickCheck(null)
    setQuickAnswer('')
    setQuickFeedback(null)
  }, [sessionId, socraticState?.topic])

  const phase = socraticState?.phase || 'elicitation'
  const displayPhases = [
    ['elenchus', 'Elenchus', 'Question assumptions'],
    ['maieutics', 'Maieutics', 'Guide discovery'],
    ['aporia', 'Aporia', 'Test the idea'],
    ['dialectic', 'Dialectic', 'Synthesize understanding'],
  ]
  const phaseIndex = displayPhases.findIndex((item) => item[0] === phase)
  const progress = phase === 'conclusion' ? 100 : Math.max(0, Math.min(100, ((phaseIndex + 1) / displayPhases.length) * 100))
  const effectiveTopic = topic.trim() || notebook?.title || 'General study'

  const runQuickCheck = async () => {
    if (!notebook || !sessionId || quickBusy) return
    setQuickBusy(true)
    setQuickFeedback(null)
    try {
      const result = await generateSocraticQuickCheck({
        topic: effectiveTopic,
        tier: socraticState?.mastery_tier || 'Developing',
        score: Number(socraticState?.mastery_score ?? 30),
        notebookId: notebook.id,
        activeSources,
        sourceModes,
        userId,
        model: model || null,
      })
      setQuickCheck(result.question)
      setQuickAnswer('')
    } catch (error) {
      setQuickFeedback({ type: 'error', text: error?.message || 'Quick Check could not be prepared.' })
    } finally {
      setQuickBusy(false)
    }
  }

  const submitQuickCheck = async () => {
    if (!quickCheck?.question || !quickAnswer.trim() || quickBusy) return
    setQuickBusy(true)
    try {
      const result = await gradeSocraticQuickCheck({
        topic: effectiveTopic,
        question: quickCheck.question,
        expectedAnswer: quickCheck.expected_answer,
        studentAnswer: quickAnswer.trim(),
        currentScore: Number(socraticState?.mastery_score ?? 30),
        notebookId: notebook.id,
        sessionId,
        userId,
        model: model || null,
      })
      setSocraticState((current) => ({
        ...(current || {}),
        mastery_score: result.score,
        mastery_tier: result.tier,
      }))
      setQuickFeedback({ type: result.correct ? 'success' : 'info', text: result.verdict + (result.feedback ? ' — ' + result.feedback : '') })
      setQuickCheck(null)
      setQuickAnswer('')
    } catch (error) {
      setQuickFeedback({ type: 'error', text: error?.message || 'Quick Check grading failed.' })
    } finally {
      setQuickBusy(false)
    }
  }

  const sendSocratic = (text, options = {}) => {
    if (!notebook) return
    send(text, 'socratic', {
      topic: effectiveTopic,
      score: Number(socraticState?.mastery_score ?? 30),
      forceAdvance: Boolean(options.forceAdvance),
    })
  }

  return (
    <main className="main-content" style={{ overflow: 'hidden' }}>
      <div className="socratic-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div className="page-heading" style={{ marginBottom: 10 }}>
          <div className="page-icon"><BrainCircuit size={22} /></div>
          <div style={{ minWidth: 0 }}>
            <div className="eyebrow">SOCRATIC STUDY</div>
            <h1>Socratic Tutor</h1>
            <p>{notebook ? 'Marklyf guides your reasoning instead of handing over the answer.' : 'Select or create a notebook to start a persistent Socratic session.'}</p>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 7 }}>
            <button className="upload-button" onClick={newChat} disabled={!notebook || busy}>New Socratic session</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 250px', gap: 12, minHeight: 0, flex: 1 }}>
          <section style={{ minHeight: 0, display: 'flex', flexDirection: 'column', border: '1px solid var(--surface-high)', borderRadius: 12, background: 'var(--surface-container-low)', overflow: 'hidden' }}>
            <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-high)', background: 'var(--surface-container)' }}>
              <label className="muted-label" htmlFor="socratic-topic">TOPIC / IDEA</label>
              <input id="socratic-topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Why do I think memorizing formulas is the best way to learn physics?" style={{ width: '100%', marginTop: 5, padding: '9px 10px', borderRadius: 8, border: '1px solid var(--surface-high)', background: 'var(--surface-container-low)', color: 'var(--text)' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginTop: 7, fontSize: 10, color: 'var(--tertiary)' }}>
                <span>{notebook ? notebook.title : 'No notebook selected'} · {activeSources.length} active sources</span>
                <span>{socraticState?.mastery_tier || 'Developing'} · {Math.round(Number(socraticState?.mastery_score ?? 30))}/100</span>
              </div>
            </div>

            <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-high)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <div>
                  <div className="muted-label">DIALOGUE PROGRESS</div>
                  <div style={{ fontSize: 11, color: 'var(--text)', marginTop: 3 }}>{socraticState?.status || (phase === 'conclusion' ? 'Wrapping up what you discovered' : 'Start by sharing a thought or hypothesis')}</div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--tertiary)' }}>{Math.round(progress)}%</div>
              </div>
              <div style={{ marginTop: 8, height: 5, background: 'var(--surface-high)', borderRadius: 999 }}>
                <div style={{ width: progress + '%', height: '100%', borderRadius: 999, background: 'var(--primary)' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginTop: 9 }}>
                {displayPhases.map(([id, label, hint], index) => (
                  <div key={id} title={hint} style={{ minWidth: 0, opacity: phase === 'conclusion' || index <= phaseIndex ? 1 : 0.45 }}>
                    <div style={{ height: 4, borderRadius: 999, background: index <= phaseIndex ? 'var(--primary)' : 'var(--surface-high)' }} />
                    <div style={{ fontSize: 9, marginTop: 4, color: phase === id ? 'var(--text)' : 'var(--tertiary)', fontWeight: phase === id ? 700 : 500 }}>{label}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="chat-scroll" style={{ flex: 1, minHeight: 0, padding: 12 }}>
              {!messages.length ? (
                <div className="empty-chat-state">
                  <div className="empty-chat-mark"><img src="/apollo-logo-mark.svg" alt="Marklyf" width="32" height="32" /></div>
                  <h2>{notebook ? 'Start with a belief, explanation, or question' : 'Select a notebook first'}</h2>
                  <p>{notebook ? 'Marklyf will probe one assumption at a time, guide discovery, and introduce relevant counterexamples before synthesizing what you learned.' : 'Socratic sessions use Marklyf’s existing notebook/session persistence.'}</p>
                </div>
              ) : messages.map((message) => <Bubble key={message.id} message={message} onSaveNote={onSaveNote} canSaveNote={Boolean(notebook)} />)}
              {busy && <div className="thinking-line"><LoaderCircle size={14} className="spin" /> Marklyf is thinking through the next Socratic move…</div>}
            </div>

            <div style={{ padding: '10px 12px', borderTop: '1px solid var(--surface-high)' }}>
              {quickCheck && <div style={{ padding: 10, marginBottom: 8, borderRadius: 9, border: '1px solid var(--surface-high)', background: 'var(--surface-container)' }}>
                <div className="muted-label">QUICK CHECK</div>
                <strong style={{ display: 'block', marginTop: 4, fontSize: 12 }}>{quickCheck.question}</strong>
                <textarea value={quickAnswer} onChange={(e) => setQuickAnswer(e.target.value)} disabled={quickBusy} rows={3} placeholder="Explain your reasoning…" style={{ width: '100%', marginTop: 7, resize: 'vertical', padding: 8, borderRadius: 7, border: '1px solid var(--surface-high)', background: 'var(--surface-container-low)', color: 'var(--text)' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 6 }}>
                  <button className="icon-button" onClick={() => { setQuickCheck(null); setQuickAnswer(''); }} disabled={quickBusy}>Cancel</button>
                  <button className="upload-button" onClick={submitQuickCheck} disabled={quickBusy || !quickAnswer.trim()}>{quickBusy ? 'Grading…' : 'Submit'}</button>
                </div>
              </div>}
              {quickFeedback && <div role="status" style={{ padding: 8, marginBottom: 7, borderRadius: 7, background: 'var(--surface-container)', color: quickFeedback.type === 'error' ? 'var(--error)' : 'var(--text)', fontSize: 10 }}>{quickFeedback.text}</div>}
              <div style={{ display: 'flex', gap: 6, marginBottom: 7 }}>
                <button className="upload-button" onClick={runQuickCheck} disabled={!notebook || !sessionId || busy || quickBusy || Boolean(quickCheck)}>{quickBusy && !quickCheck ? 'Preparing…' : 'Quick Check'}</button>
                {notebook && phase !== 'dialectic' && phase !== 'conclusion' && <button className="upload-button" onClick={() => sendSocratic('Continue to the next stage.', { forceAdvance: true })} disabled={busy}>Move Forward</button>}
              </div>
              {notebook ? <Composer send={(value) => sendSocratic(value)} stop={stop} busy={busy} researchMode="socratic" /> : <div style={{ color: 'var(--tertiary)', fontSize: 11, padding: 8 }}>Create/select a notebook to enable persistent Socratic Study.</div>}
            </div>
          </section>

          <aside style={{ minWidth: 0, border: '1px solid var(--surface-high)', borderRadius: 12, background: 'var(--surface-container-low)', padding: 12, overflow: 'auto' }}>
            <div className="muted-label">CURRENT STATE</div>
            <div style={{ fontSize: 16, fontWeight: 700, marginTop: 5 }}>{phase === 'conclusion' ? 'Conclusion' : (displayPhases.find((item) => item[0] === phase)?.[1] || 'Elenchus')}</div>
            <div style={{ fontSize: 10, lineHeight: 1.45, color: 'var(--tertiary)', marginTop: 3 }}>{socraticState?.status || 'Share your starting idea.'}</div>
            <div style={{ marginTop: 14, padding: 10, borderRadius: 9, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
              <div className="muted-label">MASTERY</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{Math.round(Number(socraticState?.mastery_score ?? 30))}<span style={{ fontSize: 11, color: 'var(--tertiary)' }}>/100</span></div>
              <div style={{ fontSize: 11, marginTop: 1 }}>{socraticState?.mastery_tier || 'Developing'}</div>
              <div style={{ height: 4, background: 'var(--surface-high)', borderRadius: 999, marginTop: 7 }}><div style={{ width: Math.max(0, Math.min(100, Number(socraticState?.mastery_score ?? 30))) + '%', height: '100%', borderRadius: 999, background: 'var(--primary)' }} /></div>
            </div>
            <div style={{ marginTop: 12, display: 'grid', gap: 7 }}>
              {displayPhases.map(([id, label, hint]) => <div key={id} style={{ padding: 8, borderRadius: 8, border: '1px solid var(--surface-high)', background: phase === id ? 'var(--surface-container)' : 'transparent', opacity: phase === 'conclusion' || displayPhases.findIndex((item) => item[0] === id) <= phaseIndex ? 1 : 0.5 }}><strong style={{ fontSize: 10 }}>{label}</strong><div style={{ fontSize: 9, color: 'var(--tertiary)', marginTop: 2 }}>{hint}</div></div>)}
            </div>
            <div style={{ marginTop: 12, fontSize: 10, lineHeight: 1.5, color: 'var(--tertiary)' }}>
              <strong style={{ color: 'var(--text)' }}>How Marklyf teaches</strong>
              <div style={{ marginTop: 4 }}>Questions → your reasoning → guidance → a useful challenge → synthesis.</div>
              <div style={{ marginTop: 5 }}>Maieutics is bounded so the session keeps moving.</div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  )
}
export default function AppPhase6() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [studioOpen, setStudioOpen] = useState(false)
  const [sessionOpen, setSessionOpen] = useState(false)
  const [notesOpen, setNotesOpen] = useState(false)
  const [researchMode, setResearchMode] = useState('quick')
  const [notebooks, setNotebooks] = useState([])
  const [activeId, setActiveId] = useState('')
  const [sources, setSources] = useState([])
  const [sourceModes, setSourceModes] = useState({})
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState([])
  const [notes, setNotes] = useState([])
  const [busy, setBusy] = useState(false)
  const [model, setModel] = useState('')
  const [socraticState, setSocraticState] = useState(null)
  const [tool, setTool] = useState('slides')
  const uid = useMemo(() => getUserId(), [])
  const streamAbortRef = useRef(null)
  const pendingSessionRef = useRef('')
  const notebook = notebooks.find((n) => n.id === activeId) || null
  const activeSources = sources.filter((source) => (sourceModes[source.name] || 'full') !== 'off').map((source) => source.name)

  const refresh = async (preferred) => {
    const data = await listNotebooks(uid)
    const items = data.notebooks || []
    const recent = readRecent('notebooks', uid)
    const ranked = [...items].sort((a, b) => {
      const aIndex = recent.indexOf(a.id)
      const bIndex = recent.indexOf(b.id)
      if (aIndex === -1 && bIndex === -1) return String(b.updated || '').localeCompare(String(a.updated || ''))
      if (aIndex === -1) return 1
      if (bIndex === -1) return -1
      return aIndex - bIndex
    })
    setNotebooks(ranked)
    const nextId = preferred || activeId || recent[0] || ranked[0]?.id || ''
    if (nextId) rememberRecent('notebooks', nextId, uid)
    setActiveId(nextId)
  }

  const loadSources = async (id) => {
    if (!id) { setSources([]); setSourceModes({}); return }
    const data = await listSources(id, uid)
    const nextSources = data.sources || []
    const savedModes = readSourceModes(uid, id)
    const mergedModes = Object.fromEntries(nextSources.map((source) => [source.name, savedModes[source.name] || 'full']))
    setSources(nextSources)
    setSourceModes(mergedModes)
    saveSourceModes(uid, id, mergedModes)
  }

  const loadSessionContent = async (notebookId, id) => {
    const [messageData, socraticData] = await Promise.all([
      getSessionMessages(notebookId, id, uid),
      getSocraticState(notebookId, id, uid).catch(() => ({ state: null })),
    ])
    setSessionId(id)
    setMessages(messageData.messages || [])
    setSocraticState(socraticData.state || null)
  }

  const loadSessionsAndNotes = async (id) => {
    if (!id) { setSessions([]); setSessionId(''); setMessages([]); setNotes([]); return }
    const [sessionData, noteData] = await Promise.all([listSessions(id, uid), listNotes(id, uid)])
    let nextSessions = sessionData.sessions || []
    if (!nextSessions.length) nextSessions = [await createSession(id, 'New chat', uid)]
    setSessions(nextSessions)
    const preferredId = pendingSessionRef.current
    const nextSession = nextSessions.find((item) => item.id === preferredId) || nextSessions[0]
    pendingSessionRef.current = ''
    await loadSessionContent(id, nextSession.id)
    setNotes(noteData.notes || [])
  }

  useEffect(() => {
    refresh('').catch(console.error)
    return () => streamAbortRef.current?.abort()
  }, [])

  useEffect(() => {
    loadSources(activeId).catch(console.error)
    loadSessionsAndNotes(activeId).catch(console.error)
  }, [activeId])

  const create = async () => {
    const name = prompt('Notebook name', 'My Notebook')
    if (!name?.trim()) return
    const nb = await createNotebook(name, uid)
    rememberRecent('notebooks', nb.id, uid)
    await refresh(nb.id)
  }

  const renameNotebookUi = async (nb) => {
    const title = prompt('Notebook name', nb?.title || 'Untitled Notebook')
    if (!nb?.id || !title?.trim()) return
    const updated = await renameNotebook(nb.id, title.trim(), uid)
    setNotebooks((current) => current.map((item) => item.id === nb.id ? { ...item, ...updated } : item))
  }
  const openPastSession = async (session) => {
    if (!session?.notebook_id || !session?.id) return
    setActive('tutor')
    setSourceOpen(false)
    setStudioOpen(false)
    setSessionOpen(false)
    setNotesOpen(false)
    if (session.notebook_id === activeId) {
      await loadSessionContent(session.notebook_id, session.id)
      return
    }
    pendingSessionRef.current = session.id
    setMessages([])
    setSocraticState(null)
    rememberRecent('notebooks', session.notebook_id, uid)
    setActiveId(session.notebook_id)
  }

  const removeNotebook = async (nb) => {
    if (!nb?.id || !confirm(`Delete notebook “${nb.title}”? This will remove its sources, chats, notes, and saved study data.`)) return
    await deleteNotebook(nb.id, uid)
    const remaining = notebooks.filter((item) => item.id !== nb.id)
    setNotebooks(remaining)
    if (nb.id === activeId) {
      const nextId = remaining[0]?.id || ''
      setActiveId(nextId)
      setMessages([])
      setSocraticState(null)
      setSources([])
      setSourceModes({})
      setSessions([])
      setSessionId('')
      setNotes([])
    }
  }
  const upload = async (file) => {
    if (!activeId) return
    await uploadSource(activeId, file, uid)
    rememberRecent('notebooks', activeId, uid)
    await loadSources(activeId)
    await refresh(activeId)
  }

  const setSourceMode = (name, mode) => {
    if (activeId) rememberRecent('sources', name, uid, activeId)
    setSourceModes((current) => {
      const next = { ...current, [name]: mode }
      if (activeId) saveSourceModes(uid, activeId, next)
      return next
    })
  }

  const setAllSourceMode = (mode) => {
    if (!activeId) return
    const next = Object.fromEntries(sources.map((source) => [source.name, mode]))
    sources.forEach((source) => rememberRecent('sources', source.name, uid, activeId))
    setSourceModes(next)
    saveSourceModes(uid, activeId, next)
  }

  const removeSourceUi = async (source) => {
    if (!activeId || !source?.name) return
    if (!confirm(`Delete “${source.name}” from this notebook?`)) return
    await deleteSource(activeId, source.name, uid)
    await loadSources(activeId)
    await refresh(activeId)
  }

  const retrySourceUi = async (source) => {
    if (!activeId || !source?.name) return
    rememberRecent('sources', source.name, uid, activeId)
    try {
      await retrySource(activeId, source.name, uid)
      await loadSources(activeId)
      window.setTimeout(() => loadSources(activeId).catch(() => {}), 1200)
    } catch (error) {
      await loadSources(activeId)
      throw error
    }
  }

  const refreshSourceUi = async (source) => {
    if (!activeId || !source?.name) return
    rememberRecent('sources', source.name, uid, activeId)
    await refreshSource(activeId, source.name, uid)
    await loadSources(activeId)
  }

  const newChat = async () => {
    if (!activeId) return
    const session = await createSession(activeId, 'New chat', uid)
    setSessions((current) => [session, ...current])
    setSessionId(session.id)
    setMessages([])
    setSocraticState(null)
    setSessionOpen(false)
  }

  const selectSession = async (id) => {
    if (!activeId || id === sessionId) return
    setSessionId(id)
    const [data, socraticData] = await Promise.all([
      getSessionMessages(activeId, id, uid),
      getSocraticState(activeId, id, uid).catch(() => ({ state: null })),
    ])
    setMessages((data.messages || []).map(normalizeMessage))
    setSocraticState(socraticData.state || null)
    setSessionOpen(false)
  }

  const rename = async (session) => {
    const title = prompt('Chat name', session.title)
    if (!title?.trim()) return
    const updated = await renameSession(activeId, session.id, title.trim(), uid)
    setSessions((current) => current.map((item) => item.id === session.id ? updated : item))
  }

  const remove = async (session) => {
    if (!confirm(`Delete “${session.title}”?`)) return
    await deleteSession(activeId, session.id, uid)
    const remaining = sessions.filter((item) => item.id !== session.id)
    if (!remaining.length) {
      const created = await createSession(activeId, 'New chat', uid)
      setSessions([created])
      setSessionId(created.id)
      setMessages([])
      setSocraticState(null)
    } else {
      setSessions(remaining)
      if (session.id === sessionId) await selectSession(remaining[0].id)
    }
  }

  const refreshNotes = async () => {
    if (!activeId) return
    const data = await listNotes(activeId, uid)
    setNotes(data.notes || [])
  }

  const saveNote = async (message) => {
    if (!activeId || !message?.content) return
    const firstLine = message.content.split('\n').map((line) => line.replace(/^#+\s*/, '').trim()).find(Boolean) || 'Marklyf answer'
    const title = firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine
    await createNote(activeId, { title, content: message.content, source_type: 'chat', source_ref: sessionId }, uid)
    await refreshNotes()
    setNotesOpen(true)
    setSourceOpen(false)
    setStudioOpen(false)
    setSessionOpen(false)
  }

  const removeNote = async (note) => {
    await deleteNote(activeId, note.id, uid)
    await refreshNotes()
  }

  const stop = () => {
    streamAbortRef.current?.abort()
  }

  const send = async (text, overrideMode = null, socraticOptions = {}) => {
    if (busy || !text?.trim()) return
    const currentNotebook = notebook
    const requestMode = overrideMode || researchMode
    if (requestMode === 'socratic' && !currentNotebook) return
    if (currentNotebook) rememberRecent('notebooks', currentNotebook.id, uid)
    if (!currentNotebook && requestMode === 'study') {
      // Study mode is still useful without notebook context; it becomes web-only research.
    }
    let requestSessionId = sessionId
    if (currentNotebook && !requestSessionId) {
      const session = await createSession(activeId, 'New chat', uid)
      requestSessionId = session.id
      setSessionId(session.id)
      setSessions((current) => [session, ...current])
    }
    const user = { id: `${Date.now()}u`, role: 'user', content: text.trim() }
    const assistantId = `${Date.now()}a`
    const history = [...messages.map((m) => ({ role: m.role, content: toDisplayText(m.content) })), { ...user, content: toDisplayText(user.content) }]
    const needsWeb = requestMode === 'web' || requestMode === 'deep' || requestMode === 'study'
    const controller = new AbortController()
    streamAbortRef.current = controller
    setMessages((v) => [...v, user, { id: assistantId, role: 'assistant', content: '', model, streaming: true, sources: [], researchMode: requestMode }])
    setBusy(true)
    try {
      await streamChat({
        messages: history,
        model: model || 'openai/gpt-oss-120b',
        notebookId: currentNotebook?.id || null,
        notebookTitle: currentNotebook?.title || null,
        activeSources: currentNotebook ? activeSources : [],
        sourceModes: currentNotebook ? sourceModes : {},
        sessionId: currentNotebook ? requestSessionId : null,
        userId: uid,
        webEnabled: needsWeb,
        researchMode: requestMode,
        socraticTopic: socraticOptions.topic || '',
        socraticScore: socraticOptions.score ?? null,
        socraticForceAdvance: Boolean(socraticOptions.forceAdvance),
        signal: controller.signal,
        onSession: (session) => {
          if (!session) return
          setSessionId(session.id)
          setSessions((current) => current.some((item) => item.id === session.id) ? current : [session, ...current])
        },
        onStart: (p) => { setModel(p.model || ''); setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, model: p.model } : m)) },
        onSources: (webSources) => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, sources: webSources } : m)),
        onToken: (token) => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: `${toDisplayText(m.content)}${toDisplayText(token)}` } : m)),
        onRestart: () => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: '', streaming: true } : m)),
        onGroundingCheck: (payload) => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, groundingWarning: payload.warning || null, overlapRatio: payload.overlap_ratio } : m)),
        onSocraticState: (payload) => setSocraticState(payload),
        onDone: () => {
          setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, streaming: false } : m))
          setBusy(false)
          if (currentNotebook) listSessions(activeId, uid).then((data) => setSessions(data.sessions || [])).catch(() => {})
        },
        onError: (message) => {
          const safeMessage = toDisplayText(message) || 'Marklyf returned an unknown error.'
          setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: m.content ? `${toDisplayText(m.content)}\n\n_(Response interrupted: ${safeMessage})_` : safeMessage, streaming: false } : m))
          setBusy(false)
        },
      })
    } catch (error) {
      if (error?.name === 'AbortError') {
        setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: m.content ? `${m.content}\n\n_(Generation stopped.)_` : 'Generation stopped.', streaming: false } : m))
      } else {
        const safeMessage = toDisplayText(error?.message) || 'Marklyf backend request failed.'
        setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: safeMessage, streaming: false } : m))
      }
      setBusy(false)
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null
    }
  }
  const navIcon = (NAV_ITEMS.find((n) => n.id === active) || NAV_ITEMS[0]).icon
  const NavIcon = navIcon

  return <div className="apollo-app">
    <Sidebar active={active} setActive={setActive} collapsed={collapsed} setCollapsed={setCollapsed} notebooks={notebooks} activeId={activeId} setNotebook={(id) => { rememberRecent('notebooks', id, uid); setActiveId(id); setMessages([]); setSocraticState(null) }} create={create} renameNotebookUi={renameNotebookUi} removeNotebook={removeNotebook} />
    <section className="app-shell">
      <TopBar
        active={active}
        toggleSources={() => { setSourceOpen((v) => !v); setStudioOpen(false); setSessionOpen(false); setNotesOpen(false) }}
        toggleStudio={() => { setStudioOpen((v) => !v); setSourceOpen(false); setSessionOpen(false); setNotesOpen(false) }}
        toggleSessions={() => { setSessionOpen((v) => !v); setSourceOpen(false); setStudioOpen(false); setNotesOpen(false) }}
        toggleNotes={() => { setNotesOpen((v) => !v); setSourceOpen(false); setStudioOpen(false); setSessionOpen(false) }}
        researchMode={researchMode}
        setResearchMode={setResearchMode}
      />
      {active === 'console' ? <div className="main-panel"><main className="chat-main"><div className="chat-scroll">
        <div className="chat-header-row"><div><div className="context-kicker">CONSOLE</div><h1>Study with Marklyf</h1><p>{notebook ? `${notebook.title} · ${notebook.source_count || sources.length} sources connected · ${sessions.length} chats` : 'No notebook required for quick or web chat. Create one to save sources, chats and notes.'}</p></div>{notebook && <button className="chat-header-action" onClick={newChat} title="New chat" aria-label="New chat"><MessageSquarePlus size={16} /></button>}</div>
        <div className="conversation">{!messages.length ? <div className="empty-chat-state"><div className="empty-chat-mark"><img src="/apollo-logo-mark.svg" alt="Marklyf" width="32" height="32" /></div><h2>{notebook ? 'Start a conversation' : 'Ask Marklyf directly'}</h2><p>{notebook ? `Choose ${RESEARCH_MODES.find((m) => m.id === researchMode)?.label || 'Quick answer'} and ask Marklyf.` : 'Quick and Web modes work without a notebook. Deep/Study modes can research the web and add notebook context when one is selected.'}</p></div> : messages.map((m) => <Bubble key={m.id} message={m} onSaveNote={saveNote} canSaveNote={Boolean(notebook)}/>)}{busy && <div className="thinking-line"><LoaderCircle size={14} className="spin" /> {researchMode === 'deep' ? 'Deep Research in progress…' : researchMode === 'study' ? 'Researching your notebook + web…' : researchMode === 'web' ? 'Searching the web…' : 'Marklyf is responding…'}</div>}</div>
      </div><div className="chat-bottom"><div className="suggestion-row"><button onClick={() => send('Explain a concept simply')} disabled={busy}><Sparkles size={13}/> Explain a concept simply</button><button onClick={() => send(researchMode === 'quick' ? 'Summarize my notes' : researchMode === 'study' ? 'Compare my notes with the latest information' : 'Research the latest developments related to my notes')} disabled={busy}><BookOpen size={13}/> {researchMode === 'quick' ? 'Summarize my notes' : 'Research latest'}</button></div><Composer send={send} stop={stop} busy={busy} researchMode={researchMode}/></div></main>
        {sourceOpen && <SourcePanel notebooks={notebooks} activeId={activeId} sources={sources} sourceModes={sourceModes} setSourceMode={setSourceMode} setAllSourceMode={setAllSourceMode} setActiveId={(id) => { rememberRecent('notebooks', id, uid); setActiveId(id); setMessages([]); setSocraticState(null) }} create={create} upload={upload} close={() => setSourceOpen(false)} userId={uid} refreshSources={async () => { await loadSources(activeId); await refresh(activeId) }} removeSource={removeSourceUi} retrySource={retrySourceUi} refreshSource={refreshSourceUi} />}
        {sessionOpen && <SessionPanel sessions={sessions} activeSessionId={sessionId} selectSession={selectSession} createNew={newChat} rename={rename} remove={remove} close={() => setSessionOpen(false)} />}
        {notesOpen && <NotesPanel notes={notes} remove={removeNote} close={() => setNotesOpen(false)} />}
        {studioOpen && <StudioPanel close={() => setStudioOpen(false)} tool={tool} setTool={setTool} activeId={activeId} sources={sources} activeSources={activeSources} userId={uid} openSources={() => { setStudioOpen(false); setSourceOpen(true) }} />}
      </div> : active === 'tutor' ? <SocraticTutor
        notebook={notebook}
        activeSources={activeSources}
        sourceModes={sourceModes}
        userId={uid}
        sessionId={sessionId}
        messages={messages}
        busy={busy}
        model={model}
        socraticState={socraticState}
        setSocraticState={setSocraticState}
        send={send}
        stop={stop}
        newChat={newChat}
        onSaveNote={saveNote}
      /> : active === 'progress' ? <ProgressDashboardPage userId={uid} /> : active === 'sessions' ? <PastSessionsPage userId={uid} notebooks={notebooks} activeSessionId={sessionId} onOpen={openPastSession} /> : active === 'progress' ? <ProgressDashboardPage userId={uid} /> : active === 'sessions' ? <PastSessionsPage userId={uid} notebooks={notebooks} activeSessionId={sessionId} onOpen={openPastSession} /> : <main className="main-content placeholder-page"><div className="page-heading"><div className="page-icon"><NavIcon size={22}/></div><div><div className="eyebrow">MARKLYF MODULE</div><h1>{NAV_ITEMS.find(n=>n.id===active)?.label}</h1><p>This module is being migrated from the original Python app.</p></div></div></main>}
    </section>
  </div>
}