import { useMemo, useState } from 'react'
import {
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Filter,
  History,
  MessageSquare,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'

function formatDate(value) {
  if (!value) return 'Unknown time'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown time'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function relativeTime(value) {
  if (!value) return ''
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return ''
  const delta = Date.now() - time
  const minutes = Math.max(1, Math.round(delta / 60000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(value)
}

function sessionKind(session) {
  return session?.socratic_state ? 'Socratic Tutor' : 'Chat'
}

export default function PastSessionsPage({
  sessions,
  notebooks,
  activeSessionId,
  loading,
  onOpen,
  onRename,
  onDelete,
  onRefresh,
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')

  const notebookTitles = useMemo(
    () => new Map(notebooks.map((notebook) => [notebook.id, notebook.title])),
    [notebooks],
  )

  const filteredSessions = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return sessions.filter((session) => {
      const matchesFilter = filter === 'all'
        || (filter === 'socratic' && Boolean(session.socratic_state))
        || (filter === 'chat' && !session.socratic_state)
      if (!matchesFilter) return false
      if (!needle) return true
      const haystack = [
        session.title,
        notebookTitles.get(session.notebook_id),
        session.socratic_state?.topic,
        session.socratic_state?.phase,
        session.socratic_state?.mastery_tier,
      ].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(needle)
    })
  }, [filter, notebookTitles, query, sessions])

  return (
    <main className="main-content past-sessions-page">
      <div className="past-sessions-header">
        <div>
          <div className="eyebrow">HISTORY</div>
          <div className="past-sessions-title-row">
            <div className="page-icon"><History size={22} /></div>
            <div>
              <h1>Past Sessions</h1>
              <p>Return to previous Apollo conversations across all of your notebooks.</p>
            </div>
          </div>
        </div>
        <button className="chat-header-action" onClick={onRefresh} disabled={loading} title="Refresh sessions" aria-label="Refresh sessions">
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
        </button>
      </div>

      <div className="past-sessions-toolbar">
        <label className="past-sessions-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search sessions, notebooks or topics…"
            aria-label="Search past sessions"
          />
        </label>
        <label className="past-sessions-filter">
          <Filter size={14} />
          <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter past sessions">
            <option value="all">All sessions</option>
            <option value="socratic">Socratic sessions</option>
            <option value="chat">Regular chats</option>
          </select>
        </label>
        <div className="past-sessions-count">{filteredSessions.length} shown · {sessions.length} total</div>
      </div>

      {loading ? (
        <div className="past-sessions-empty">
          <Clock3 size={26} className="spin" />
          <strong>Loading your sessions…</strong>
          <span>Gathering conversations from your notebooks.</span>
        </div>
      ) : !filteredSessions.length ? (
        <div className="past-sessions-empty">
          <History size={30} />
          <strong>{sessions.length ? 'No matching sessions' : 'No past sessions yet'}</strong>
          <span>{sessions.length ? 'Try a different search or filter.' : 'Start a chat or Socratic Tutor session and it will appear here.'}</span>
        </div>
      ) : (
        <div className="past-sessions-grid">
          {filteredSessions.map((session) => {
            const state = session.socratic_state
            const isActive = session.id === activeSessionId
            const notebookTitle = notebookTitles.get(session.notebook_id) || 'Notebook'
            return (
              <article key={session.id} className={`past-session-card ${isActive ? 'is-active' : ''}`}>
                <div className="past-session-card-top">
                  <div className="past-session-icon"><MessageSquare size={17} /></div>
                  <div className="past-session-meta">
                    <span className="past-session-kind">{sessionKind(session)}</span>
                    <span title={formatDate(session.updated)}>{relativeTime(session.updated)}</span>
                  </div>
                  {isActive && <span className="past-session-active"><CheckCircle2 size={13} /> Open</span>}
                </div>

                <h2>{session.title || 'Untitled session'}</h2>
                <div className="past-session-notebook">{notebookTitle}</div>

                {state && (
                  <div className="past-session-mastery">
                    <div>
                      <span className="past-session-topic">{state.topic || 'Socratic study'}</span>
                      <span className="past-session-phase">{state.phase || 'elicitation'}</span>
                    </div>
                    {typeof state.mastery_score === 'number' && (
                      <strong>{Math.round(state.mastery_score)}% mastery</strong>
                    )}
                  </div>
                )}

                <div className="past-session-stats">
                  <span><CalendarClock size={13} /> {formatDate(session.created)}</span>
                  <span><MessageSquare size={13} /> {session.message_count || 0} messages</span>
                </div>

                <div className="past-session-actions">
                  <button className="upload-button" onClick={() => onOpen(session)}>
                    <History size={14} /> Open session
                  </button>
                  <button className="icon-button" onClick={() => onRename(session)} title="Rename session" aria-label={`Rename ${session.title}`}>
                    <Pencil size={14} />
                  </button>
                  <button className="icon-button" onClick={() => onDelete(session)} title="Delete session" aria-label={`Delete ${session.title}`}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}

      <div className="past-sessions-note">
        <BrainCircuit size={16} />
        <span>Socratic sessions keep their phase, mastery, topic, and conversation history together so reopening one continues from where you stopped.</span>
      </div>
    </main>
  )
}
