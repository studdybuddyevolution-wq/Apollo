import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp, BookOpen, BrainCircuit, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, FileText, FolderOpen, Globe, History, ImagePlus, LayoutDashboard,
  LoaderCircle, Menu, Paperclip, Plus, Search, Settings, Sparkles, Upload, User,
  Video, WandSparkles, X, Activity, SlidersHorizontal,
} from 'lucide-react'
import { streamChat } from './api/apolloApi'
import { createNotebook, listNotebooks, listSources, uploadSource } from './api/notebooksApi'
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
  { id: 'quick', label: 'Quick answer', icon: Sparkles, description: 'Fast answer from Apollo' },
  { id: 'web', label: 'Web search', icon: Globe, description: 'Current information + sources' },
  { id: 'deep', label: 'Deep Research', icon: SlidersHorizontal, description: 'Multi-step web research' },
  { id: 'study', label: 'Study Research', icon: BookOpen, description: 'Notebook + web synthesis' },
]

const STUDIO_TOOLS = [
  { id: 'slides', label: 'Slide Deck', description: 'Turn selected sources into slides', icon: FileText },
  { id: 'report', label: 'Study Report', description: 'Generate structured revision notes', icon: FileText },
  { id: 'mindmap', label: 'Mind Map', description: 'Build a visual concept structure', icon: BrainCircuit },
  { id: 'video', label: 'Video Overview', description: 'Create an explainer storyboard', icon: Video },
]

function getUserId() {
  const key = 'apollo-user-id'
  let value = localStorage.getItem(key)
  if (!value) {
    value = `user_${crypto.randomUUID()}`
    localStorage.setItem(key, value)
  }
  return value
}

function Sidebar({ active, setActive, collapsed, setCollapsed, notebooks, activeId, setNotebook, create }) {
  const [open, setOpen] = useState(true)
  return (
    <aside className={`apollo-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="brand-mark"><img src="/apollo-logo-mark.svg" alt="Apollo" width="28" height="28" /></div>
        {!collapsed && <div><div className="brand-name">APOLLO</div><div className="brand-subtitle">OMNI AI</div></div>}
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
              <button key={nb.id} className={`notebook-row ${activeId === nb.id ? 'active' : ''}`} onClick={() => setNotebook(nb.id)}>
                <span className="notebook-title"><BookOpen size={15} />{nb.title}</span><span className="source-count">{nb.source_count || 0} src</span>
              </button>
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

function TopBar({ active, toggleSources, toggleStudio, researchMode, setResearchMode }) {
  const item = NAV_ITEMS.find((n) => n.id === active) || NAV_ITEMS[0]
  const currentMode = RESEARCH_MODES.find((m) => m.id === researchMode) || RESEARCH_MODES[0]
  return (
    <header className="topbar">
      <div className="topbar-left"><div className="breadcrumb"><span className="breadcrumb-muted">Apollo</span><span>/</span><strong>{item.label}</strong></div></div>
      <div className="topbar-actions">
        {active === 'console' && <>
          <button className="topbar-tool" onClick={toggleSources}><FolderOpen size={16} /> Sources</button>
          <button className="topbar-tool" onClick={toggleStudio}><WandSparkles size={16} /> Studio</button>
          <label className="research-mode-select" title="Choose how Apollo researches this question">
            <currentMode.icon size={15} />
            <select value={researchMode} onChange={(e) => setResearchMode(e.target.value)} aria-label="Research mode">
              {RESEARCH_MODES.map((mode) => <option key={mode.id} value={mode.id}>{mode.label}</option>)}
            </select>
            <ChevronDown size={13} />
          </label>
        </>}
        <button className="topbar-chip"><span className="status-dot" /> Online</button>
      </div>
    </header>
  )
}

function Bubble({ message }) {
  const me = message.role === 'user'
  return (
    <article className={`message-row ${me ? 'user' : 'assistant'}`}>
      <div className={`message-avatar ${me ? 'user-avatar' : ''}`}>{me ? <User size={15} /> : <Sparkles size={15} />}</div>
      <div className="message-content">
        <div className="message-meta"><span>{me ? 'You' : 'Apollo'}</span>{!me && message.model && <span className="message-model">{message.model}</span>}</div>
        <div className="message-text">{message.content || (message.streaming && <span className="streaming-caret" />)}</div>
        {message.sources?.length > 0 && <div className="message-sources">
          {message.sources.map((source) => <a className="citation-pill web-citation" key={source.url || source.title} href={source.url} target="_blank" rel="noreferrer"><Globe size={11} /> {source.title || source.url}</a>)}
        </div>}
      </div>
    </article>
  )
}

function Composer({ send, busy, researchMode }) {
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
        <input value={value} disabled={busy} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder={`${mode.label} — message Apollo…`} />
        <button className="send-button" onClick={submit} disabled={busy || !value.trim()}><ArrowUp size={18} /></button>
      </div>
      <div className="composer-meta-row"><span>Enter to send</span><span>Shift + Enter for a new line</span><span>{mode.description}</span></div>
    </div>
  )
}

function SourcePanel({ notebooks, activeId, sources, activeSources, setActiveId, toggleSource, create, upload, close }) {
  const input = useRef(null)
  const [uploading, setUploading] = useState(false)
  const nb = notebooks.find((n) => n.id === activeId)
  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !nb) return
    setUploading(true)
    try { await upload(file) } finally { setUploading(false); e.target.value = '' }
  }
  return (
    <aside className="context-panel source-panel">
      <div className="context-header"><div><div className="context-kicker">KNOWLEDGE BASE</div><h2><FolderOpen size={17} /> Sources</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div>
      <div className="notebook-picker"><span className="muted-label">ACTIVE NOTEBOOK</span><select className="notebook-picker-button" value={activeId} onChange={(e) => setActiveId(e.target.value)}>{notebooks.map((n) => <option key={n.id} value={n.id}>{n.title}</option>)}</select></div>
      <div className="source-search"><Search size={15} /><input placeholder="Search sources..." /></div>
      <input ref={input} hidden type="file" accept=".pdf,.docx,.txt,.md,.csv" onChange={onFile} />
      <div className="source-list">{sources.map((s) => { const on = activeSources.includes(s.name); return <button key={s.name} className={`source-card ${on ? 'selected' : ''}`} onClick={() => toggleSource(s.name)}><div className="source-icon"><FileText size={16} /></div><div className="source-card-copy"><strong>{s.name}</strong><span>{s.chunks} chunks · {s.kind || 'file'}</span></div><span className={`source-check ${on ? 'on' : ''}`}>{on ? '✓' : ''}</span></button> })}{!sources.length && <div className="source-empty-state"><FolderOpen size={22} /><strong>No sources connected</strong><span>Upload a PDF, DOCX, TXT, Markdown or CSV file.</span></div>}</div>
      <div className="source-footer"><div className="source-stats"><span><strong>{activeSources.length}</strong> active</span><span><strong>{sources.length}</strong> total</span></div><button className="upload-button" disabled={!nb || uploading} onClick={() => input.current?.click()}><Upload size={15} /> {uploading ? 'Indexing…' : 'Add sources'}</button></div>
      <button className="new-notebook" onClick={create}><Plus size={15} /> New Notebook</button>
    </aside>
  )
}

function StudioPanel({ close, tool, setTool }) {
  const current = STUDIO_TOOLS.find((x) => x.id === tool) || STUDIO_TOOLS[0]
  return <aside className="context-panel studio-panel"><div className="context-header"><div><div className="context-kicker">WORKSPACE</div><h2><WandSparkles size={17} /> Studio</h2></div><button className="icon-button context-close" onClick={close}><X size={17} /></button></div><p className="context-description">Studio generation will use the connected notebook once those tools are migrated.</p><div className="studio-tool-list">{STUDIO_TOOLS.map(({ id, label, description, icon: Icon }) => <button key={id} className={`studio-tool ${tool === id ? 'selected' : ''}`} onClick={() => setTool(id)}><span className="studio-tool-icon"><Icon size={17} /></span><span><strong>{label}</strong><small>{description}</small></span></button>)}</div><div className="studio-footer"><div><strong>{current.label}</strong><span>Waiting for backend</span></div><button className="studio-generate" disabled><Sparkles size={15} /> Generate</button></div></aside>
}

export default function AppPhase6() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [studioOpen, setStudioOpen] = useState(false)
  const [researchMode, setResearchMode] = useState('quick')
  const [notebooks, setNotebooks] = useState([])
  const [activeId, setActiveId] = useState('')
  const [sources, setSources] = useState([])
  const [activeSources, setActiveSources] = useState([])
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [model, setModel] = useState('')
  const [tool, setTool] = useState('slides')
  const uid = useMemo(() => getUserId(), [])
  const notebook = notebooks.find((n) => n.id === activeId) || null

  const refresh = async (preferred) => {
    const data = await listNotebooks(uid)
    const items = data.notebooks || []
    setNotebooks(items)
    setActiveId(preferred || activeId || items[0]?.id || '')
  }
  const loadSources = async (id) => {
    if (!id) { setSources([]); setActiveSources([]); return }
    const data = await listSources(id, uid)
    setSources(data.sources || [])
    setActiveSources((data.sources || []).map((s) => s.name))
  }
  useEffect(() => { refresh('').catch(console.error) }, [])
  useEffect(() => { loadSources(activeId).catch(console.error); setMessages([]) }, [activeId])
  const create = async () => { const name = prompt('Notebook name', 'My Notebook'); if (!name?.trim()) return; const nb = await createNotebook(name, uid); await refresh(nb.id) }
  const upload = async (file) => { if (!activeId) return; await uploadSource(activeId, file, uid); await loadSources(activeId); await refresh(activeId) }
  const toggleSource = (name) => setActiveSources((v) => v.includes(name) ? v.filter((x) => x !== name) : [...v, name])

  const send = async (text) => {
    if (!notebook || busy) { if (!notebook) setSourceOpen(true); return }
    const user = { id: `${Date.now()}u`, role: 'user', content: text }
    const assistantId = `${Date.now()}a`
    const history = [...messages.map((m) => ({ role: m.role, content: m.content })), user]
    const needsWeb = researchMode === 'web' || researchMode === 'deep' || researchMode === 'study'
    const requestMode = researchMode
    setMessages((v) => [...v, user, { id: assistantId, role: 'assistant', content: '', model, streaming: true, sources: [], researchMode: requestMode }])
    setBusy(true)
    try {
      await streamChat({
        messages: history,
        model: 'openai/gpt-oss-120b',
        notebookId: notebook.id,
        notebookTitle: notebook.title,
        activeSources,
        userId: uid,
        webEnabled: needsWeb,
        researchMode: requestMode,
        onStart: (p) => { setModel(p.model || ''); setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, model: p.model } : m)) },
        onSources: (webSources) => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, sources: webSources } : m)),
        onToken: (token) => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: `${m.content}${token}` } : m)),
        onRestart: () => setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: '', streaming: true } : m)),
        onDone: () => { setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, streaming: false } : m)); setBusy(false) },
        onError: (message) => { setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: m.content ? `${m.content}\n\n_(Response interrupted: ${message})_` : message, streaming: false } : m)); setBusy(false) },
      })
    } catch (error) {
      setMessages((v) => v.map((m) => m.id === assistantId ? { ...m, content: error?.message || 'Apollo backend request failed.', streaming: false } : m))
      setBusy(false)
    }
  }

  const navIcon = (NAV_ITEMS.find((n) => n.id === active) || NAV_ITEMS[0]).icon
  const NavIcon = navIcon

  return <div className="apollo-app">
    <Sidebar active={active} setActive={setActive} collapsed={collapsed} setCollapsed={setCollapsed} notebooks={notebooks} activeId={activeId} setNotebook={(id) => { setActiveId(id); setMessages([]) }} create={create} />
    <section className="app-shell">
      <TopBar active={active} toggleSources={() => { setSourceOpen((v) => !v); setStudioOpen(false) }} toggleStudio={() => { setStudioOpen((v) => !v); setSourceOpen(false) }} researchMode={researchMode} setResearchMode={setResearchMode} />
      {active === 'console' ? <div className="main-panel"><main className="chat-main"><div className="chat-scroll"><div className="chat-header-row"><div><div className="context-kicker">CONSOLE</div><h1>Study with Apollo</h1><p>{notebook ? `${notebook.title} · ${notebook.source_count || sources.length} sources connected` : 'Create a notebook to get started.'}</p></div></div><div className="conversation">{!messages.length ? <div className="empty-chat-state"><div className="empty-chat-mark"><Sparkles size={25} /></div><h2>{notebook ? 'Start a conversation' : 'Create a notebook'}</h2><p>{notebook ? `Choose ${RESEARCH_MODES.find((m) => m.id === researchMode)?.label || 'Quick answer'} and ask Apollo.` : 'Open Sources and create your first notebook.'}</p></div> : messages.map((m) => <Bubble key={m.id} message={m}/>)}{busy && <div className="thinking-line"><LoaderCircle size={14} className="spin" /> {researchMode === 'deep' ? 'Deep Research in progress…' : researchMode === 'study' ? 'Researching your notebook + web…' : researchMode === 'web' ? 'Searching the web…' : 'Apollo is responding…'}</div>}</div></div><div className="chat-bottom"><div className="suggestion-row"><button onClick={() => send('Explain a concept simply')} disabled={busy}><Sparkles size={13}/> Explain a concept simply</button><button onClick={() => send(researchMode === 'quick' ? 'Summarize my notes' : researchMode === 'study' ? 'Compare my notes with the latest information' : 'Research the latest developments related to my notes')} disabled={busy}><BookOpen size={13}/> {researchMode === 'quick' ? 'Summarize my notes' : 'Research latest'}</button></div><Composer send={send} busy={busy} researchMode={researchMode}/></div></main>{sourceOpen && <SourcePanel notebooks={notebooks} activeId={activeId} sources={sources} activeSources={activeSources} setActiveId={(id) => { setActiveId(id); setMessages([]) }} toggleSource={toggleSource} create={create} upload={upload} close={() => setSourceOpen(false)} />}{studioOpen && <StudioPanel close={() => setStudioOpen(false)} tool={tool} setTool={setTool} />}</div> : <main className="main-content placeholder-page"><div className="page-heading"><div className="page-icon"><NavIcon size={22}/></div><div><div className="eyebrow">APOLLO MODULE</div><h1>{NAV_ITEMS.find(n=>n.id===active)?.label}</h1><p>This module is being migrated from the original Python app.</p></div></div></main>}
    </section>
  </div>
}