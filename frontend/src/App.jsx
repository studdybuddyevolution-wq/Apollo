import { useMemo, useState } from 'react'
import {
  Activity,
  Archive,
  ArrowUp,
  BookOpen,
  Bot,
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
  Trash2,
  Upload,
  User,
  Video,
  WandSparkles,
  X,
} from 'lucide-react'

const NAV_ITEMS = [
  { id: 'console', label: 'Console & Tools', icon: Sparkles },
  { id: 'tutor', label: 'Socratic Tutor', icon: BrainCircuit },
  { id: 'progress', label: 'Progress Dashboard', icon: LayoutDashboard },
  { id: 'planner', label: 'Study Planner', icon: Activity },
  { id: 'sessions', label: 'Past Sessions', icon: History },
  { id: 'settings', label: 'User Settings & Profile', icon: Settings },
]

const NOTEBOOKS = [
  { id: 'main', title: 'My Notebook', sources: 12 },
  { id: 'dbms', title: 'DBMS — Semester 5', sources: 7 },
  { id: 'ai', title: 'AI Revision', sources: 18 },
]

const INITIAL_SOURCES = [
  { id: 1, icon: FileText, name: 'DBMS_Notes.pdf', meta: 'PDF · 84 pages', active: true },
  { id: 2, icon: FileText, name: 'Normalization.pdf', meta: 'PDF · 21 pages', active: true },
  { id: 3, icon: FolderOpen, name: 'Lecture 07 — SQL.txt', meta: 'Text · 4.2 KB', active: true },
  { id: 4, icon: FileText, name: 'Previous Exam.docx', meta: 'DOCX · 11 pages', active: false },
]

const INITIAL_MESSAGES = [
  {
    id: 1,
    role: 'assistant',
    content: 'Welcome back. I\'m Apollo. I can work across your notebook sources, search the web, reason through problems, and turn what you learn into study material.',
    sources: ['DBMS_Notes.pdf', 'Normalization.pdf'],
  },
  {
    id: 2,
    role: 'assistant',
    content: 'Your current notebook has 3 active sources. Ask me something specific, or use one of the Studio tools below to turn your sources into a report, slide deck, mind map, or video outline.',
    sources: [],
  },
]

const STUDIO_TOOLS = [
  { id: 'slides', label: 'Slide Deck', description: 'Presentation from selected sources', icon: FileText },
  { id: 'report', label: 'Study Report', description: 'Structured revision notes', icon: Archive },
  { id: 'mindmap', label: 'Mind Map', description: 'Visual concept structure', icon: BrainCircuit },
  { id: 'video', label: 'Video Overview', description: 'Short explainer storyboard', icon: Video },
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
              <div className="notebook-row active">
                <span className="notebook-title"><BookOpen size={15} /> My Notebook</span>
                <span className="source-count">12 src</span>
              </div>
              <button className="new-notebook"><Plus size={15} /> New Notebook</button>
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
            <button className="topbar-tool" onClick={onToggleSources} title="Sources"><FolderOpen size={16} /> Sources</button>
            <button className="topbar-tool" onClick={onToggleStudio} title="Studio"><WandSparkles size={16} /> Studio</button>
          </>
        )}
        <button className="topbar-chip"><span className="status-dot" /> Online</button>
        <button className="avatar-button" aria-label="Profile">A</button>
      </div>
    </header>
  )
}

function MessageBubble({ message, onRegenerate }) {
  const isUser = message.role === 'user'
  return (
    <article className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`message-avatar ${isUser ? 'user-avatar' : ''}`}>{isUser ? <User size={15} /> : <Sparkles size={15} />}</div>
      <div className="message-content">
        <div className="message-meta">
          <span>{isUser ? 'You' : 'Apollo'}</span>
          {!isUser && <span className="message-model">Qwen · Groq</span>}
        </div>
        <div className="message-text">{message.content}</div>
        {!!message.sources?.length && (
          <div className="message-sources">
            {message.sources.map((source) => <span key={source} className="citation-pill"><BookOpen size={11} /> {source}</span>)}
          </div>
        )}
        {!isUser && (
          <div className="message-actions">
            <button title="Copy"><FileText size={13} /></button>
            <button title="Regenerate" onClick={onRegenerate}><Sparkles size={13} /></button>
            <button title="More"><MoreHorizontal size={13} /></button>
          </div>
        )}
      </div>
    </article>
  )
}

function Composer({ onSend, disabled = false }) {
  const [value, setValue] = useState('')
  const [recording, setRecording] = useState(false)

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <div className="composer-wrap chat-composer-wrap">
      <div className="composer composer-live">
        <button className="composer-icon" title="Attach"><Paperclip size={18} /></button>
        <button className="composer-icon" title="Ask with image"><ImagePlus size={18} /></button>
        <input
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }}
          placeholder="Message Apollo..."
          aria-label="Message Apollo"
        />
        <button className={`composer-icon ${recording ? 'is-recording' : ''}`} title="Voice" onClick={() => setRecording((v) => !v)}>
          <Mic size={18} />
        </button>
        <button className="send-button" title="Send" onClick={submit} disabled={disabled || !value.trim()}>
          <ArrowUp size={18} />
        </button>
      </div>
      <div className="composer-meta-row">
        <span>Enter to send</span>
        <span>Shift + Enter for a new line</span>
        <span>Apollo can make mistakes.</span>
      </div>
    </div>
  )
}

function SourcePanel({ sources, activeNotebook, onClose, onSetSource }) {
  return (
    <aside className="context-panel source-panel">
      <div className="context-header">
        <div>
          <div className="context-kicker">KNOWLEDGE BASE</div>
          <h2><FolderOpen size={17} /> Sources</h2>
        </div>
        <button className="icon-button context-close" onClick={onClose}><X size={17} /></button>
      </div>

      <div className="notebook-picker">
        <span className="muted-label">ACTIVE NOTEBOOK</span>
        <button className="notebook-picker-button"><BookOpen size={15} /><span>{activeNotebook.title}</span><ChevronDown size={14} /></button>
      </div>

      <div className="source-search">
        <Search size={15} />
        <input placeholder="Search sources..." />
      </div>

      <div className="source-list">
        {sources.map((source) => {
          const Icon = source.icon
          return (
            <button key={source.id} className={`source-card ${source.active ? 'selected' : ''}`} onClick={() => onSetSource(source.id)}>
              <div className="source-icon"><Icon size={16} /></div>
              <div className="source-card-copy"><strong>{source.name}</strong><span>{source.meta}</span></div>
              <span className={`source-check ${source.active ? 'on' : ''}`}>{source.active ? '✓' : ''}</span>
            </button>
          )
        })}
      </div>

      <div className="source-footer">
        <div className="source-stats"><span><strong>{sources.filter((s) => s.active).length}</strong> active</span><span><strong>{activeNotebook.sources}</strong> total</span></div>
        <button className="upload-button"><Upload size={15} /> Add sources</button>
      </div>
    </aside>
  )
}

function StudioPanel({ onClose, selectedTool, setSelectedTool }) {
  const tool = STUDIO_TOOLS.find((item) => item.id === selectedTool) ?? STUDIO_TOOLS[0]
  return (
    <aside className="context-panel studio-panel">
      <div className="context-header">
        <div>
          <div className="context-kicker">WORKSPACE</div>
          <h2><WandSparkles size={17} /> Studio</h2>
        </div>
        <button className="icon-button context-close" onClick={onClose}><X size={17} /></button>
      </div>

      <p className="context-description">Turn your current notebook into a focused study artifact. These controls are local-only for now.</p>

      <div className="studio-tool-list">
        {STUDIO_TOOLS.map(({ id, label, description, icon: Icon }) => (
          <button key={id} className={`studio-tool ${selectedTool === id ? 'selected' : ''}`} onClick={() => setSelectedTool(id)}>
            <span className="studio-tool-icon"><Icon size={17} /></span>
            <span><strong>{label}</strong><small>{description}</small></span>
          </button>
        ))}
      </div>

      <div className="studio-config">
        <div className="muted-label">OUTPUT LENGTH</div>
        <div className="segmented-control"><button className="selected">Concise</button><button>Balanced</button><button>Deep</button></div>
        <div className="muted-label studio-margin-top">SOURCE SCOPE</div>
        <label className="check-row"><input type="checkbox" defaultChecked /> Use active sources</label>
        <label className="check-row"><input type="checkbox" /> Include web research</label>
      </div>

      <div className="studio-footer">
        <div><strong>{tool.label}</strong><span>Ready to generate</span></div>
        <button className="studio-generate"><Sparkles size={15} /> Generate</button>
      </div>
    </aside>
  )
}

function ChatView({ messages, onSend, busy, activeNotebook }) {
  const [suggestion, setSuggestion] = useState('Summarize normalization with an example')
  const sendSuggestion = () => {
    onSend(suggestion)
    setSuggestion('Give me 5 exam questions from these notes')
  }

  return (
    <main className="chat-main">
      <div className="chat-scroll">
        <div className="chat-header-row">
          <div>
            <div className="context-kicker">CONSOLE</div>
            <h1>Study with Apollo</h1>
            <p>{activeNotebook.title} · {activeNotebook.sources} sources connected</p>
          </div>
          <button className="chat-header-action"><MoreHorizontal size={18} /></button>
        </div>

        <div className="conversation">
          {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          {busy && (
            <article className="message-row assistant">
              <div className="message-avatar"><Sparkles size={15} /></div>
              <div className="message-content">
                <div className="message-meta"><span>Apollo</span><span className="message-model">thinking</span></div>
                <div className="thinking-line"><LoaderCircle size={14} className="spin" /> Searching your sources and preparing a response…</div>
              </div>
            </article>
          )}
        </div>
      </div>

      <div className="chat-bottom">
        <div className="suggestion-row">
          <button onClick={sendSuggestion}><Lightbulb size={13} /> {suggestion}</button>
          <button onClick={() => onSend('Make me a concise revision plan from these sources')}><BookOpen size={13} /> Revision plan</button>
        </div>
        <Composer onSend={onSend} disabled={busy} />
      </div>
    </main>
  )
}

function ConsoleView({ sourcePanelOpen, studioPanelOpen, setSourcePanelOpen, setStudioPanelOpen }) {
  const [activeNotebookId, setActiveNotebookId] = useState('main')
  const [sources, setSources] = useState(INITIAL_SOURCES)
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [busy, setBusy] = useState(false)
  const [selectedTool, setSelectedTool] = useState('slides')

  const activeNotebook = useMemo(
    () => NOTEBOOKS.find((notebook) => notebook.id === activeNotebookId) ?? NOTEBOOKS[0],
    [activeNotebookId],
  )

  const sendMessage = (text) => {
    if (!text.trim() || busy) return
    const userMessage = { id: Date.now(), role: 'user', content: text.trim(), sources: [] }
    setMessages((current) => [...current, userMessage])
    setBusy(true)
    window.setTimeout(() => {
      setMessages((current) => [...current, {
        id: Date.now() + 1,
        role: 'assistant',
        content: `Local preview response: I would answer “${text.trim()}” using ${sources.filter((source) => source.active).length} active sources from ${activeNotebook.title}. The Python backend will replace this fake response in Phase 3.`,
        sources: sources.filter((source) => source.active).slice(0, 2).map((source) => source.name),
      }])
      setBusy(false)
    }, 700)
  }

  const toggleSource = (id) => setSources((current) => current.map((source) => source.id === id ? { ...source, active: !source.active } : source))

  return (
    <div className="console-layout">
      <ChatView messages={messages} onSend={sendMessage} busy={busy} activeNotebook={activeNotebook} />
      {sourcePanelOpen && <SourcePanel sources={sources} activeNotebook={activeNotebook} onClose={() => setSourcePanelOpen(false)} onSetSource={toggleSource} />}
      {studioPanelOpen && <StudioPanel onClose={() => setStudioPanelOpen(false)} selectedTool={selectedTool} setSelectedTool={setSelectedTool} />}
    </div>
  )
}

function PlaceholderPage({ active }) {
  const item = NAV_ITEMS.find((navItem) => navItem.id === active) ?? NAV_ITEMS[0]
  const Icon = item.icon
  return (
    <main className="main-content placeholder-page">
      <div className="page-heading">
        <div className="page-icon"><Icon size={22} /></div>
        <div><div className="eyebrow">APOLLO MODULE</div><h1>{item.label}</h1><p>This module stays in the React shell for now. Its existing Python engine will be connected after the Console migration.</p></div>
      </div>
      <div className="placeholder-card"><Sparkles size={20} /><div><strong>Phase 2 preview</strong><span>The Console is interactive with local fake data. Navigation remains available while the backend boundary is built.</span></div></div>
    </main>
  )
}

export default function App() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sourcePanelOpen, setSourcePanelOpen] = useState(true)
  const [studioPanelOpen, setStudioPanelOpen] = useState(false)

  const navigate = (id) => {
    setActive(id)
    setMobileOpen(false)
  }

  return (
    <div className="apollo-app">
      <div className={`mobile-overlay ${mobileOpen ? 'visible' : ''}`} onClick={() => setMobileOpen(false)} />
      <div className={mobileOpen ? 'mobile-sidebar-open' : ''}>
        <Sidebar active={active} onNavigate={navigate} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      </div>
      <div className="apollo-main">
        <TopBar
          active={active}
          onMenu={() => setMobileOpen(true)}
          onToggleSources={() => { setSourcePanelOpen((v) => !v); setStudioPanelOpen(false) }}
          onToggleStudio={() => { setStudioPanelOpen((v) => !v); setSourcePanelOpen(false) }}
        />
        {active === 'console' ? (
          <ConsoleView
            sourcePanelOpen={sourcePanelOpen}
            studioPanelOpen={studioPanelOpen}
            setSourcePanelOpen={setSourcePanelOpen}
            setStudioPanelOpen={setStudioPanelOpen}
          />
        ) : <PlaceholderPage active={active} />}
      </div>
    </div>
  )
}
