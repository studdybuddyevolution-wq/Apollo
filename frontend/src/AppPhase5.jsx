import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowUp, BookOpen, BrainCircuit, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, FileText, FolderOpen, History, ImagePlus, LayoutDashboard, LoaderCircle,
  Menu, Mic, MoreHorizontal, Paperclip, Plus, Search, Settings, Sparkles, Trash2, Upload,
  User, Video, WandSparkles, X, Pencil,
} from 'lucide-react'
import { streamChat } from './api/apolloApi'
import { createNotebook, deleteNotebook, listNotebooks, listSources, renameNotebook, uploadSource } from './api/notebooksApi'
import './console-clean.css'

const NAV_ITEMS = [
  { id: 'console', label: 'Console & Tools', icon: Sparkles },
  { id: 'tutor', label: 'Socratic Tutor', icon: BrainCircuit },
  { id: 'progress', label: 'Progress Dashboard', icon: LayoutDashboard },
  { id: 'planner', label: 'Study Planner', icon: Activity },
  { id: 'sessions', label: 'Past Sessions', icon: History },
  { id: 'settings', label: 'User Settings & Profile', icon: Settings },
]

const STUDIO_TOOLS = [
  { id: 'slides', label: 'Slide Deck', description: 'Turn selected sources into slides', icon: FileText },
  { id: 'report', label: 'Study Report', description: 'Generate structured revision notes', icon: FileText },
  { id: 'mindmap', label: 'Mind Map', description: 'Build a visual concept structure', icon: BrainCircuit },
  { id: 'video', label: 'Video Overview', description: 'Create an explainer storyboard', icon: Video },
]

function getUserId() {
  const key = 'apollo-user-id'
  const existing = window.localStorage.getItem(key)
  if (existing) return existing
  const created = `user_${crypto.randomUUID()}`
  window.localStorage.setItem(key, created)
  return created
}

function Sidebar({ active, onNavigate, collapsed, onToggle, notebooks, activeNotebook, onSelectNotebook, onCreateNotebook }) {
  const [open, setOpen] = useState(true)
  return (
    <aside className={`apollo-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="brand-mark"><Sparkles size={18} strokeWidth={2.4} /></div>
        {!collapsed && <div><div className="brand-name">APOLLO</div><div className="brand-subtitle">OMNI AI</div></div>}
        <button className="icon-button sidebar-toggle" onClick={onToggle}>{collapsed ? <ChevronRight size={17}/> : <ChevronLeft size={17}/>}</button>
      </div>
      {!collapsed && <div className="sidebar-label">NAVIGATION</div>}
      <nav className="nav-list">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => onNavigate(id)} title={collapsed ? label : undefined}><Icon size={18}/>{!collapsed && <span>{label}</span>}</button>)}
      </nav>
      {!collapsed && <div className="notebook-section">
        <button className="section-heading" onClick={() => setOpen(v => !v)}><span><BookOpen size={15}/> NOTEBOOK</span><ChevronDown className={open ? '' : 'rotate'} size={15}/></button>
        {open && <div className="notebook-content">
          {notebooks.length ? notebooks.map(nb => <button key={nb.id} className={`notebook-row ${activeNotebook?.id === nb.id ? 'active' : ''}`} onClick={() => onSelectNotebook(nb.id)}><span className="notebook-title"><BookOpen size={15}/>{nb.title}</span><span className="source-count">{nb.source_count || 0} src</span></button>) : <div className="notebook-row"><span className="notebook-title"><BookOpen size={15}/>No notebooks</span></div>}
          <button className="new-notebook" onClick={onCreateNotebook}><Plus size={15}/> New Notebook</button>
        </div>}
      </div>}
      <div className="sidebar-footer">{!collapsed && <div className="system-status"><span className="status-dot"/> System ready</div>}<button className="help-button"><CircleHelp size={17}/>{!collapsed && 'Help & feedback'}</button></div>
    </aside>
  )
}

function TopBar({ active, onMenu, onToggleSources, onToggleStudio }) {
  const current = NAV_ITEMS.find(x => x.id === active) || NAV_ITEMS[0]
  return <header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={onMenu}><Menu size={20}/></button><div className="breadcrumb"><span className="breadcrumb-muted">Apollo</span><span>/</span><strong>{current.label}</strong></div></div><div className="topbar-actions">{active === 'console' && <><button className="topbar-tool" onClick={onToggleSources}><FolderOpen size={16}/> Sources</button><button className="topbar-tool" onClick={onToggleStudio}><WandSparkles size={16}/> Studio</button></>}<button className="topbar-chip"><span className="status-dot"/> Online</button><button className="avatar-button">A</button></div></header>
}

function MessageBubble({ message }) {
  const user = message.role === 'user'
  return <article className={`message-row ${user ? 'user' : 'assistant'}`}><div className={`message-avatar ${user ? 'user-avatar' : ''}`}>{user ? <User size={15}/> : <Sparkles size={15}/>}</div><div className="message-content"><div className="message-meta"><span>{user ? 'You' : 'Apollo'}</span>{!user && message.model && <span className="message-model">{message.model}</span>}</div><div className="message-text">{message.content || (message.streaming && <span className="streaming-caret"/>)}</div>{message.sources?.length > 0 && <div className="message-sources">{message.sources.map(s => <span className="citation-pill" key={s}><BookOpen size={11}/> {s}</span>)}</div>}</div></article>
}

function Composer({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const submit = () => { const t = value.trim(); if (!t || disabled) return; onSend(t); setValue('') }
  return <div className="composer-wrap chat-composer-wrap"><div className="composer composer-live"><button className="composer-icon" disabled><Paperclip size={18}/></button><button className="composer-icon" disabled><ImagePlus size={18}/></button><input value={value} disabled={disabled} onChange={e => setValue(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }}} placeholder="Message Apollo..."/><button className="composer-icon" disabled><Mic size={18}/></button><button className="send-button" onClick={submit} disabled={disabled || !value.trim()}><ArrowUp size={18}/></button></div><div className="composer-meta-row"><span>Enter to send</span><span>Shift + Enter for a new line</span><span>Apollo can make mistakes.</span></div></div>
}

function SourcePanel({ notebooks, activeNotebook, sources, activeSources, onClose, onSelectNotebook, onToggleSource, onCreateNotebook, onUpload }) {
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const triggerUpload = () => fileRef.current?.click()
  const handleFile = async (event) => { const file = event.target.files?.[0]; if (!file || !activeNotebook) return; setBusy(true); try { await onUpload(file) } finally { setBusy(false); event.target.value = '' } }
  return <aside className="context-panel source-panel"><div className="context-header"><div><div className="context-kicker">KNOWLEDGE BASE</div><h2><FolderOpen size={17}/> Sources</h2></div><button className="icon-button context-close" onClick={onClose}><X size={17}/></button></div>
    <div className="notebook-picker"><span className="muted-label">ACTIVE NOTEBOOK</span><select className="notebook-picker-button" value={activeNotebook?.id || ''} onChange={e => onSelectNotebook(e.target.value)}>{notebooks.map(nb => <option key={nb.id} value={nb.id}>{nb.title}</option>)}</select></div>
    <div className="source-search"><Search size={15}/><input placeholder="Search sources..."/></div>
    <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md,.csv" style={{display:'none'}} onChange={handleFile}/>
    <div className="source-list">{sources.map(source => { const active = activeSources.includes(source.name); return <button key={source.name} className={`source-card ${active ? 'selected' : ''}`} onClick={() => onToggleSource(source.name)}><div className="source-icon"><FileText size={16}/></div><div className="source-card-copy"><strong>{source.name}</strong><span>{source.chunks} chunks · {source.kind || 'file'}</span></div><span className={`source-check ${active ? 'on' : ''}`}>{active ? '✓' : ''}</span></button>})}{sources.length === 0 && <div className="source-empty-state"><FolderOpen size={22}/><strong>No sources connected</strong><span>Upload a PDF, DOCX, TXT or Markdown file to build this notebook.</span></div>}</div>
    <div className="source-footer"><div className="source-stats"><span><strong>{activeSources.length}</strong> active</span><span><strong>{sources.length}</strong> total</span></div><button className="upload-button" onClick={triggerUpload} disabled={!activeNotebook || busy}><Upload size={15}/> {busy ? 'Indexing…' : 'Add sources'}</button></div>
    <button className="new-notebook" onClick={onCreateNotebook}><Plus size={15}/> New Notebook</button>
  </aside>
}

function StudioPanel({ onClose, selectedTool, setSelectedTool }) { const tool = STUDIO_TOOLS.find(x => x.id === selectedTool) || STUDIO_TOOLS[0]; return <aside className="context-panel studio-panel"><div className="context-header"><div><div className="context-kicker">WORKSPACE</div><h2><WandSparkles size={17}/> Studio</h2></div><button className="icon-button context-close" onClick={onClose}><X size={17}/></button></div><p className="context-description">Studio generation will use the connected notebook once those tools are migrated.</p><div className="studio-tool-list">{STUDIO_TOOLS.map(({id,label,description,icon:Icon})=><button key={id} className={`studio-tool ${selectedTool===id?'selected':''}`} onClick={()=>setSelectedTool(id)}><span className="studio-tool-icon"><Icon size={17}/></span><span><strong>{label}</strong><small>{description}</small></span></button>)}</div><div className="studio-footer"><div><strong>{tool.label}</strong><span>Waiting for Studio backend</span></div><button className="studio-generate" disabled><Sparkles size={15}/> Generate</button></div></aside> }

function ChatView({ messages, onSend, busy, activeNotebook }) {
  return <main className="chat-main"><div className="chat-scroll"><div className="chat-header-row"><div><div className="context-kicker">CONSOLE</div><h1>Study with Apollo</h1><p>{activeNotebook ? `${activeNotebook.title} · ${activeNotebook.source_count || 0} sources connected` : 'Create a notebook to get started.'}</p></div><button className="chat-header-action"><MoreHorizontal size={18}/></button></div><div className="conversation">{messages.length===0 ? <div className="empty-chat-state"><div className="empty-chat-mark"><Sparkles size={25}/></div><h2>{activeNotebook ? 'Start a conversation' : 'No notebook selected'}</h2><p>{activeNotebook ? 'Ask Apollo something about your notes, or upload a source from the Sources panel.' : 'Create or select a notebook first.'}</p></div> : messages.map(m => <MessageBubble key={m.id} message={m}/>)}{busy && messages.at(-1)?.role==='user' && <article className="message-row assistant"><div className="message-avatar"><Sparkles size={15}/></div><div className="message-content"><div className="message-meta"><span>Apollo</span><span className="message-model">thinking</span></div><div className="thinking-line"><LoaderCircle size={14} className="spin"/> Connecting to Apollo backend…</div></div></article>}</div></div><div className="chat-bottom"><div className="suggestion-row"><button onClick={()=>onSend('Explain a concept simply')} disabled={busy}><Sparkles size={13}/> Explain a concept simply</button><button onClick={()=>onSend('Summarize my notes')} disabled={busy}><BookOpen size={13}/> Summarize my notes</button></div><Composer onSend={onSend} disabled={busy}/></div></main>
}

export default function AppPhase5() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false)
  const [studioPanelOpen, setStudioPanelOpen] = useState(false)
  const [notebooks, setNotebooks] = useState([])
  const [activeNotebookId, setActiveNotebookId] = useState('')
  const [sources, setSources] = useState([])
  const [activeSources, setActiveSources] = useState([])
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [model, setModel] = useState('')
  const [selectedTool, setSelectedTool] = useState('slides')
  const userId = useMemo(() => getUserId(), [])
  const activeNotebook = notebooks.find(n => n.id === activeNotebookId) || null

  useEffect(() => { (async () => { try { const data = await listNotebooks(userId); const items = data.notebooks || []; setNotebooks(items); if (items[0]) setActiveNotebookId(items[0].id) } catch (e) { console.error(e) } })() }, [userId])
  useEffect(() => { if (!activeNotebookId) { setSources([]); setActiveSources([]); return }; (async () => { try { const data = await listSources(activeNotebookId, userId); setSources(data.sources || []); setActiveSources((data.sources || []).map(s => s.name)) } catch (e) { console.error(e) } })() }, [activeNotebookId, userId])

  const refreshNotebooks = async (preferredId='') => { const data = await listNotebooks(userId); const items = data.notebooks || []; setNotebooks(items); const next = preferredId || activeNotebookId || items[0]?.id || ''; if (next && items.some(x => x.id===next)) setActiveNotebookId(next); else setActiveNotebookId(items[0]?.id || '') }
  const createNewNotebook = async () => { const title = window.prompt('Notebook name'); if (!title?.trim()) return; const created = await createNotebook(title, userId); await refreshNotebooks(created.id); setMessages([]) }
  const handleSelectNotebook = async id => { setActiveNotebookId(id); setMessages([]) }
  const handleRenameNotebook = async () => { if (!activeNotebook) return; const title = window.prompt('Rename notebook', activeNotebook.title); if (!title?.trim()) return; const updated = await renameNotebook(activeNotebook.id, title, userId); setNotebooks(items => items.map(n => n.id === updated.id ? updated : n)) }
  const handleDeleteNotebook = async () => { if (!activeNotebook) return; if (!window.confirm(`Delete ${activeNotebook.title}?`)) return; await deleteNotebook(activeNotebook.id, userId); await refreshNotebooks(''); setMessages([]) }
  const handleUpload = async file => { if (!activeNotebook) return; await uploadSource(activeNotebook.id, file, userId); const data = await listSources(activeNotebook.id, userId); setSources(data.sources || []); setActiveSources((data.sources || []).map(s => s.name)); await refreshNotebooks(activeNotebook.id) }
  const toggleSource = name => setActiveSources(v => v.includes(name) ? v.filter(x => x !== name) : [...v, name])

  const sendMessage = async text => {
    if (!activeNotebook) { setSourcePanelOpen(true); return }
    const userMessage = { id: `${Date.now()}-u`, role:'user', content:text, sources:[] }
    const assistantId = `${Date.now()}-a`
    const requestMessages = [...messages.map(m => ({ role:m.role, content:m.content })), userMessage]
    setMessages(curr => [...curr, userMessage, { id:assistantId, role:'assistant', content:'', model, sources:[], streaming:true }])
    setBusy(true)
    let streamed=''
    try {
      await streamChat({ messages: requestMessages, notebookId: activeNotebook.id, notebookTitle: activeNotebook.title, activeSources, onStart: payload => { setModel(payload.model || ''); setMessages(curr => curr.map(m => m.id===assistantId ? {...m, model:payload.model || ''} : m)) }, onToken: token => { streamed += token; setMessages(curr => curr.map(m => m.id===assistantId ? {...m, content:streamed, streaming:true} : m)) }, onDone: () => { setMessages(curr => curr.map(m => m.id===assistantId ? {...m, streaming:false} : m)); setBusy(false) }, onError: msg => { setMessages(curr => curr.map(m => m.id===assistantId ? {...m, content:msg, streaming:false, error:true} : m)); setBusy(false) } })
    } catch (e) { setMessages(curr => curr.map(m => m.id===assistantId ? {...m, content:e?.message || 'Apollo backend request failed.', streaming:false, error:true} : m)); setBusy(false) }
  }

  const placeholder = NAV_ITEMS.find(n => n.id===active) || NAV_ITEMS[0]
  return <div className="apollo-app"><Sidebar active={active} onNavigate={setActive} collapsed={collapsed} onToggle={()=>setCollapsed(v=>!v)} notebooks={notebooks} activeNotebook={activeNotebook} onSelectNotebook={handleSelectNotebook} onCreateNotebook={createNewNotebook}/><section className="app-shell"><TopBar active={active} onMenu={()=>setMobileOpen(v=>!v)} onToggleSources={()=>setSourcePanelOpen(v=>!v)} onToggleStudio={()=>setStudioPanelOpen(v=>!v)}/>{active==='console' ? <div className="main-panel"><ChatView messages={messages} onSend={sendMessage} busy={busy} activeNotebook={activeNotebook}/>{sourcePanelOpen && <SourcePanel notebooks={notebooks} activeNotebook={activeNotebook} sources={sources} activeSources={activeSources} onClose={()=>setSourcePanelOpen(false)} onSelectNotebook={handleSelectNotebook} onToggleSource={toggleSource} onCreateNotebook={createNewNotebook} onUpload={handleUpload}/>} {studioPanelOpen && <StudioPanel onClose={()=>setStudioPanelOpen(false)} selectedTool={selectedTool} setSelectedTool={setSelectedTool}/>}</div> : <main className="main-content placeholder-page"><div className="page-heading"><div className="page-icon"><placeholder.icon size={22}/></div><div><div className="eyebrow">APOLLO MODULE</div><h1>{placeholder.label}</h1><p>This module is being migrated from the original Python app.</p></div></div></main>}</section></div>
}
