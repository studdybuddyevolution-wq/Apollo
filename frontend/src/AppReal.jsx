import { useState } from 'react'
import {
  Activity,
  Archive,
  ArrowUp,
  BookOpen,
  BrainCircuit,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  FolderOpen,
  History,
  ImagePlus,
  LayoutDashboard,
  Lightbulb,
  LoaderCircle,
  Menu,
  Mic,
  MoreHorizontal,
  Paperclip,
  Plus,
  Search,
  Settings,
  Sparkles,
  Upload,
  User,
  Video,
  WandSparkles,
  X,
} from 'lucide-react'
import { streamChat } from './api/apolloApi'
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
  { id: 'report', label: 'Study Report', description: 'Generate structured revision notes', icon: Archive },
  { id: 'mindmap', label: 'Mind Map', description: 'Build a visual concept structure', icon: BrainCircuit },
  { id: 'video', label: 'Video Overview', description: 'Create an explainer storyboard', icon: Video },
]

function Sidebar({ active, onNavigate, collapsed, onToggle }) {
  const [notebookOpen, setNotebookOpen] = useState(true)

  return (
    <aside className={`apollo-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="brand-mark"><Sparkles size={18} strokeWidth={2.4} /></div>
        {!collapsed && (
          <div>
            <div className="brand-name">APOLLO</div>
            <div className="brand-subtitle">OMNI AI</div>
          </div>
        )}
        <button className="icon-button sidebar-toggle" onClick={onToggle} aria-label="Toggle sidebar">
          {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
        </button>
      </div>

      {!collapsed && <div className="sidebar-label">NAVIGATION</div>}
      <nav className="nav-list" aria-label="Apollo navigation">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={`nav-item ${active === id ? 'active' : ''}`} onClick={() => onNavigate(id)} title={collapsed ? label : undefined}>
            <Icon size={18} strokeWidth={1.9} />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      {!collapsed && (
        <div className="notebook-section">
          <button className="section-heading" onClick={() => setNotebookOpen((v) => !v)}>
            <span><BookOpen size={15} /> NOTEBOOK</span>
            <ChevronDown className={notebookOpen ? '' : 'rotate'} size={15} />
          </button>
          {notebookOpen && (
            <div className="notebook-content">
              <div className="notebook-row">
                <span className="notebook-title"><BookOpen size={15} /> No notebook selected</span>
                <span className="source-count">0 src</span>
              </div>
              <button className="new-notebook" type="button" disabled>
                <Plus size={15} /> New Notebook
              </button>
            </div>
          )}
        </div>
      )}

      <div className="sidebar-footer">
        {!collapsed && <div className="system-status"><span className="status-dot" /> System ready</div>}
        <button className="help-button" title="Help"><CircleHelp size={17} />{!collapsed && 'Help & feedback'}</button>
      </div>
    </aside>
  )
}

function TopBar({ active, onMenu, onToggleSources, onToggleStudio }) {
  const current = NAV_ITEMS.find((item) => item.id === active) ?? NAV_ITEMS[0]
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="mobile-menu icon-button" onClick={onMenu} aria-label="Open menu"><Menu size={20} /></button>
        <div className="breadcrumb"><span className="breadcrumb-muted">Apollo</span><span>/</span><strong>{current.label}</strong></div>
      </div>
      <div className="topbar-actions">
        {active === 'console' && (
          <>
            <button className="topbar-tool" onClick={onToggleSources}><FolderOpen size={16} /> Sources</button>
            <button className="topbar-tool" onClick={onToggleStudio}><WandSparkles size={16} /> Studio</button>
          </>
        )}
        <button className="topbar-chip"><span className="status-dot" /> Online</button>
        <button className="avatar-button" aria-label="Profile">A</button>
      </div>
    </header>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  return (
    <article className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`message-avatar ${isUser ? 'user-avatar' : ''}`}>
        {isUser ? <User size={15} /> : <Sparkles size={15} />}
      </div>
      <div className="message-content">
        <div className="message-meta">
          <span>{isUser ? 'You' : 'Apollo'}</span>
          {!isUser && message.model && <span className="message-model">{message.model}</span>}
        </div>
        <div className="message-text">{message.content || (message.streaming && <span className="streaming-caret" />)}</div>
        {!!message.sources?.length && (
          <div className="message-sources">
            {message.sources.map((source) => <span key={source} className="citation-pill"><BookOpen size={11} /> {source}</span>)}
          </div>
        )}
      </div>
    </article>
  )
}

function Composer({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const [recording, setRecording] = useState(false)

  const submit = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
  }

  return (
    <div className="composer-wrap chat-composer-wrap">
      <div className="composer composer-live">
        <button className="composer-icon" title="Attach" disabled><Paperclip size={18} /></button>
        <button className="composer-icon" title="Ask with image" disabled><ImagePlus size={18} /></button>
        <input
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder="Message Apollo..."
          aria-label="Message Apollo"
        />
        <button className={`composer-icon ${recording ? 'is-recording' : ''}`} title="Voice" onClick={() => setRecording((v) => !v)} disabled={disabled}>
          <Mic size={18} />
        </button>
        <button className="send-button" title="Send" onClick={submit} disabled={disabled || !value.trim()}>
          <ArrowUp size={18} />
        </button>
      </div>
      <div className="composer-meta-row"><span>Enter to send</span><span>Shift + Enter for a new line</span><span>Apollo can make mistakes.</span></div>
    </div>
  )
}

function SourcePanel({ onClose }) {
  return (
    <aside className="context-panel source-panel">
      <div className="context-header">
        <div><div className="context-kicker">KNOWLEDGE BASE</div><h2><FolderOpen size={17} /> Sources</h2></div>
        <button className="icon-button context-close" onClick={onClose}><X size={17} /></button>
      </div>
      <div className="notebook-picker">
        <span className="muted-label">ACTIVE NOTEBOOK</span>
        <button className="notebook-picker-button" disabled><BookOpen size={15} /><span>No notebook selected</span><ChevronDown size={14} /></button>
      </div>
      <div className="source-search"><Search size={15} /><input placeholder="Search sources..." disabled /></div>
      <div className="source-empty-state"><FolderOpen size={22} /><strong>No sources connected</strong><span>Sources will appear here after the notebook/source API is connected.</span></div>
      <div className="source-footer">
        <div className="source-stats"><span><strong>0</strong> active</span><span><strong>0</strong> total</span></div>
        <button className="upload-button" disabled><Upload size={15} /> Add sources</button>
      </div>
    </aside>
  )
}

function StudioPanel({ onClose, selectedTool, setSelectedTool }) {
  const tool = STUDIO_TOOLS.find((item) => item.id === selectedTool) ?? STUDIO_TOOLS[0]
  return (
    <aside className="context-panel studio-panel">
      <div className="context-header">
        <div><div className="context-kicker">WORKSPACE</div><h2><WandSparkles size={17} /> Studio</h2></div>
        <button className="icon-button context-close" onClick={onClose}><X size={17} /></button>
      </div>
      <p className="context-description">Studio controls are visible, but generation stays disabled until the real Studio backend is connected.</p>
      <div className="studio-tool-list">
        {STUDIO_TOOLS.map(({ id, label, description, icon: Icon }) => (
          <button key={id} className={`studio-tool ${selectedTool === id ? 'selected' : ''}`} onClick={() => setSelectedTool(id)}>
            <span className="studio-tool-icon"><Icon size={17} /></span><span><strong>{label}</strong><small>{description}</small></span>
          </button>
        ))}
      </div>
      <div className="studio-config">
        <div className="muted-label">OUTPUT LENGTH</div>
        <div className="segmented-control"><button className="selected">Concise</button><button>Balanced</button><button>Deep</button></div>
        <div className="muted-label studio-margin-top">SOURCE SCOPE</div>
        <label className="check-row"><input type="checkbox" disabled /> Use active sources</label>
        <label className="check-row"><input type="checkbox" disabled /> Include web research</label>
      </div>
      <div className="studio-footer"><div><strong>{tool.label}</strong><span>Waiting for backend</span></div><button className="studio-generate" disabled><Sparkles size={15} /> Generate</button></div>
    </aside>
  )
}

function ChatView({ messages, onSend, busy }) {
  return (
    <main className="chat-main">
      <div className="chat-scroll">
        <div className="chat-header-row">
          <div><div className="context-kicker">CONSOLE</div><h1>Study with Apollo</h1><p>Start a conversation with the connected Apollo backend.</p></div>
          <button className="chat-header-action"><MoreHorizontal size={18} /></button>
        </div>
        <div className="conversation">
          {messages.length === 0 ? (
            <div className="empty-chat-state">
              <div className="empty-chat-mark"><Sparkles size={25} /></div>
              <h2>Start a conversation</h2>
              <p>No demo messages or sources are loaded. Your next message will use the real Python backend.</p>
            </div>
          ) : messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          {busy && messages[messages.length - 1]?.role === 'user' && (
            <article className="message-row assistant">
              <div className="message-avatar"><Sparkles size={15} /></div>
              <div className="message-content"><div className="message-meta"><span>Apollo</span><span className="message-model">thinking</span></div><div className="thinking-line"><LoaderCircle size={14} className="spin" /> Connecting to Apollo backend…</div></div>
            </article>
          )}
        </div>
      </div>
      <div className="chat-bottom">
        <div className="suggestion-row">
          <button onClick={() => onSend('Explain a concept simply')} disabled={busy}><Lightbulb size={13} /> Explain a concept simply</button>
          <button onClick={() => onSend('Help me study for an exam')} disabled={busy}><BookOpen size={13} /> Help me study for an exam</button>
        </div>
        <Composer onSend={onSend} disabled={busy} />
      </div>
    </main>
  )
}

function ConsoleView({ sourcePanelOpen, studioPanelOpen, setSourcePanelOpen, setStudioPanelOpen }) {
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [model, setModel] = useState('')
  const [selectedTool, setSelectedTool] = useState('slides')

  const sendMessage = async (text) => {
    const userMessage = { id: `${Date.now()}-user`, role: 'user', content: text, sources: [] }
    const assistantId = `${Date.now()}-assistant`
    const requestMessages = [...messages.map(({ role, content }) => ({ role, content })), userMessage]
    setMessages((current) => [...current, userMessage, { id: assistantId, role: 'assistant', content: '', model, sources: [], streaming: true }])
    setBusy(true)
    let streamedText = ''

    try {
      await streamChat({
        messages: requestMessages,
        onStart: ({ model: startedModel }) => {
          setModel(startedModel || '')
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, model: startedModel || undefined } : message))
        },
        onToken: (token) => {
          streamedText += token
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: streamedText, streaming: true } : message))
        },
        onDone: () => {
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, streaming: false } : message))
          setBusy(false)
        },
        onError: (errorMessage) => {
          setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: errorMessage, streaming: false, error: true } : message))
          setBusy(false)
        },
      })
    } catch (error) {
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: error instanceof Error ? error.message : 'Apollo backend request failed.', streaming: false, error: true } : message))
      setBusy(false)
    }
  }

  return (
    <div className="console-layout">
      <ChatView messages={messages} onSend={sendMessage} busy={busy} />
      {sourcePanelOpen && <SourcePanel onClose={() => setSourcePanelOpen(false)} />}
      {studioPanelOpen && <StudioPanel onClose={() => setStudioPanelOpen(false)} selectedTool={selectedTool} setSelectedTool={setSelectedTool} />}
    </div>
  )
}

function PlaceholderPage({ active }) {
  const item = NAV_ITEMS.find((navItem) => navItem.id === active) ?? NAV_ITEMS[0]
  const Icon = item.icon
  return (
    <main className="main-content placeholder-page"><div className="page-heading"><div className="page-icon"><Icon size={22} /></div><div><div className="eyebrow">APOLLO MODULE</div><h1>{item.label}</h1><p>This module is not connected to the backend yet.</p></div></div><div className="placeholder-card"><Sparkles size={20} /><div><strong>No demo data</strong><span>This page stays empty until its real Python service is migrated.</span></div></div></main>
  )
}

export default function AppReal() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sourcePanelOpen, setSourcePanelOpen] = useState(true)
  const [studioPanelOpen, setStudioPanelOpen] = useState(false)

  const navigate = (id) => { setActive(id); setMobileOpen(false) }

  return (
    <div className="apollo-app">
      <div className={`mobile-overlay ${mobileOpen ? 'visible' : ''}`} onClick={() => setMobileOpen(false)} />
      <div className={mobileOpen ? 'mobile-sidebar-open' : ''}>
        <Sidebar active={active} onNavigate={navigate} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      </div>
      <div className="apollo-main">
        <TopBar active={active} onMenu={() => setMobileOpen(true)} onToggleSources={() => { setSourcePanelOpen((v) => !v); setStudioPanelOpen(false) }} onToggleStudio={() => { setStudioPanelOpen((v) => !v); setSourcePanelOpen(false) }} />
        {active === 'console' ? <ConsoleView sourcePanelOpen={sourcePanelOpen} studioPanelOpen={studioPanelOpen} setSourcePanelOpen={setSourcePanelOpen} setStudioPanelOpen={setStudioPanelOpen} /> : <PlaceholderPage active={active} />}
      </div>
    </div>
  )
}
