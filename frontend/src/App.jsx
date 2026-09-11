import { useState } from 'react'
import {
  BookOpen,
  BrainCircuit,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  History,
  LayoutDashboard,
  Menu,
  MoreHorizontal,
  Plus,
  Settings,
  Sparkles,
  X,
} from 'lucide-react'

const NAV_ITEMS = [
  { id: 'console', label: 'Console & Tools', icon: Sparkles },
  { id: 'tutor', label: 'Socratic Tutor', icon: BrainCircuit },
  { id: 'progress', label: 'Progress Dashboard', icon: LayoutDashboard },
  { id: 'planner', label: 'Study Planner', icon: CalendarDays },
  { id: 'sessions', label: 'Past Sessions', icon: History },
  { id: 'settings', label: 'User Settings & Profile', icon: Settings },
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
          <button
            key={id}
            className={`nav-item ${active === id ? 'active' : ''}`}
            onClick={() => onNavigate(id)}
            title={collapsed ? label : undefined}
          >
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
                <span className="source-count">0 src</span>
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

function TopBar({ onMenu }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="mobile-menu icon-button" onClick={onMenu} aria-label="Open menu"><Menu size={20} /></button>
        <div className="breadcrumb"><span className="breadcrumb-muted">Apollo</span><span>/</span><strong>Console & Tools</strong></div>
      </div>
      <div className="topbar-actions">
        <button className="topbar-chip"><span className="status-dot" /> Online</button>
        <button className="avatar-button" aria-label="Profile">A</button>
      </div>
    </header>
  )
}

function MainContent({ active }) {
  const current = NAV_ITEMS.find((item) => item.id === active) ?? NAV_ITEMS[0]
  const Icon = current.icon

  if (active !== 'console') {
    return (
      <main className="main-content placeholder-page">
        <div className="page-heading">
          <div className="page-icon"><Icon size={22} /></div>
          <div>
            <div className="eyebrow">APOLLO MODULE</div>
            <h1>{current.label}</h1>
            <p>This React shell is ready. The existing Apollo Python functionality will connect here during the backend migration.</p>
          </div>
        </div>
        <div className="placeholder-card">
          <Sparkles size={20} />
          <div><strong>Frontend shell complete</strong><span>Next, this module will be connected to the existing Apollo services without changing their core logic.</span></div>
        </div>
      </main>
    )
  }

  return (
    <main className="main-content console-page">
      <section className="hero">
        <div className="hero-kicker"><span className="status-dot" /> COGNITIVE ENGINE ONLINE</div>
        <h1>What are we learning today?</h1>
        <p>Ask Apollo anything, search your sources, or open a tool from the workspace.</p>
      </section>

      <section className="quick-grid">
        <button className="quick-card"><FileText size={19} /><span><strong>Sources</strong><small>Add PDFs, notes, or documents</small></span><ChevronRight size={17} /></button>
        <button className="quick-card"><BookOpen size={19} /><span><strong>Notebook</strong><small>0 sources connected</small></span><ChevronRight size={17} /></button>
        <button className="quick-card"><BrainCircuit size={19} /><span><strong>Socratic Tutor</strong><small>Learn through guided questions</small></span><ChevronRight size={17} /></button>
      </section>

      <section className="composer-wrap">
        <div className="composer">
          <button className="composer-icon" title="Attach"><Plus size={19} /></button>
          <input placeholder="Message Apollo..." aria-label="Message Apollo" />
          <button className="composer-icon" title="More"><MoreHorizontal size={19} /></button>
          <button className="send-button" title="Send"><Sparkles size={18} /></button>
        </div>
        <div className="composer-hint">Apollo can make mistakes. Verify important information.</div>
      </section>
    </main>
  )
}

export default function App() {
  const [active, setActive] = useState('console')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="apollo-app">
      <div className={`mobile-overlay ${mobileOpen ? 'visible' : ''}`} onClick={() => setMobileOpen(false)} />
      <div className={mobileOpen ? 'mobile-sidebar-open' : ''}>
        <Sidebar active={active} onNavigate={(id) => { setActive(id); setMobileOpen(false) }} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      </div>
      <div className="apollo-main">
        <TopBar onMenu={() => setMobileOpen(true)} />
        <MainContent active={active} />
      </div>
    </div>
  )
}
