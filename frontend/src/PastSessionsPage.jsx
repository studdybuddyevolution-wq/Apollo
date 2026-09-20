import { useEffect, useMemo, useState } from 'react'
import {
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Filter,
  History,
  MessageSquare,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import {
  deleteSession,
  getSessionMessagesPage,
  listAllSessionsPage,
  renameSession,
} from './api/notebooksApi'

function formatDate(value) {
  if (!value) return 'Unknown time'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown time'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function relativeTime(value) {
  const time = new Date(value || '').getTime()
  if (Number.isNaN(time)) return ''
  const minutes = Math.max(1, Math.round((Date.now() - time) / 60000))
  if (minutes < 60) return minutes + 'm ago'
  const hours = Math.round(minutes / 60)
  if (hours < 24) return hours + 'h ago'
  const days = Math.round(hours / 24)
  if (days < 7) return days + 'd ago'
  return formatDate(value)
}

function normalizeMessage(message) {
  if (!message || typeof message !== 'object') return message
  const value = message.content
  let content = ''
  if (typeof value === 'string') content = value
  else if (value != null) {
    try { content = JSON.stringify(value, null, 2) } catch { content = String(value) }
  }
  return { ...message, content }
}

export default function PastSessionsPage({
  userId = 'default',
  notebooks = [],
  activeSessionId = '',
  onOpen,
}) {
  const [sessions, setSessions] = useState([])
  const [nextCursor, setNextCursor] = useState(null)
  const [hasMore, setHasMore] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [notebookFilter, setNotebookFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [selected, setSelected] = useState(null)
  const [previewMessages, setPreviewMessages] = useState([])
  const [previewCursor, setPreviewCursor] = useState(null)
  const [previewHasMore, setPreviewHasMore] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [message, setMessage] = useState('')

  const notebookTitles = useMemo(
    () => new Map(notebooks.map((item) => [item.id, item.title])),
    [notebooks],
  )

  const loadFirstPage = async () => {
    setLoading(true)
    setMessage('')
    try {
      const result = await listAllSessionsPage({
        userId,
        limit: 30,
        search,
        kind: filter,
        notebookId: notebookFilter,
      })
      const next = result.sessions || []
      setSessions(next)
      setNextCursor(result.next_cursor || null)
      setHasMore(Boolean(result.has_more))
      setSelected(next.find((item) => item.id === activeSessionId) || next[0] || null)
    } catch (error) {
      setMessage(error?.message || 'Could not load past sessions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { loadFirstPage() }, 180)
    return () => window.clearTimeout(timer)
  }, [userId, search, filter, notebookFilter])

  useEffect(() => {
    if (!selected) {
      setPreviewMessages([])
      setPreviewCursor(null)
      setPreviewHasMore(false)
      return
    }
    let cancelled = false
    setPreviewLoading(true)
    getSessionMessagesPage(selected.notebook_id, selected.id, { userId, limit: 30 })
      .then((result) => {
        if (cancelled) return
        setPreviewMessages((result.messages || []).map(normalizeMessage))
        setPreviewCursor(result.next_cursor || null)
        setPreviewHasMore(Boolean(result.has_more))
      })
      .catch((error) => { if (!cancelled) setMessage(error?.message || 'Could not load the session preview.') })
      .finally(() => { if (!cancelled) setPreviewLoading(false) })
    return () => { cancelled = true }
  }, [selected?.id, selected?.notebook_id, userId])

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const result = await listAllSessionsPage({
        userId,
        limit: 30,
        cursor: nextCursor,
        search,
        kind: filter,
        notebookId: notebookFilter,
      })
      setSessions((current) => current.concat(result.sessions || []))
      setNextCursor(result.next_cursor || null)
      setHasMore(Boolean(result.has_more))
    } catch (error) {
      setMessage(error?.message || 'Could not load more sessions.')
    } finally {
      setLoadingMore(false)
    }
  }

  const loadOlderMessages = async () => {
    if (!selected || !previewCursor || previewLoading) return
    setPreviewLoading(true)
    try {
      const result = await getSessionMessagesPage(selected.notebook_id, selected.id, {
        userId,
        limit: 30,
        cursor: previewCursor,
      })
      setPreviewMessages((current) => (result.messages || []).map(normalizeMessage).concat(current))
      setPreviewCursor(result.next_cursor || null)
      setPreviewHasMore(Boolean(result.has_more))
    } catch (error) {
      setMessage(error?.message || 'Could not load older messages.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const renameSelected = async () => {
    if (!selected) return
    const title = window.prompt('Session name', selected.title || 'Chat')
    if (!title?.trim()) return
    try {
      const updated = await renameSession(selected.notebook_id, selected.id, title.trim(), userId)
      setSelected((current) => ({ ...current, ...updated }))
      setSessions((current) => current.map((item) => item.id === selected.id ? { ...item, ...updated } : item))
    } catch (error) {
      setMessage(error?.message || 'Could not rename the session.')
    }
  }

  const deleteSelected = async () => {
    if (!selected) return
    if (!window.confirm('Delete "' + (selected.title || 'this session') + '"? This chat history will be removed.')) return
    try {
      await deleteSession(selected.notebook_id, selected.id, userId)
      const remaining = sessions.filter((item) => item.id !== selected.id)
      setSessions(remaining)
      setSelected(remaining[0] || null)
      setMessage('Session deleted.')
    } catch (error) {
      setMessage(error?.message || 'Could not delete the session.')
    }
  }

  return (
    <main className="main-content past-sessions-page">
      <div className="past-sessions-header">
        <div>
          <div className="eyebrow">HISTORY</div>
          <div className="past-sessions-title-row">
            <div className="page-icon"><History size={22} /></div>
            <div>
              <h1>Past Sessions</h1>
              <p>Browse, search and reopen Apollo conversations without loading your entire history at once.</p>
            </div>
          </div>
        </div>
        <button className="chat-header-action" onClick={loadFirstPage} disabled={loading} title="Refresh" aria-label="Refresh">
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
        </button>
      </div>

      <div className="past-sessions-toolbar">
        <label className="past-sessions-search">
          <Search size={15} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search titles or Socratic topics…" />
        </label>
        <label className="past-sessions-filter">
          <Filter size={14} />
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All sessions</option>
            <option value="socratic">Socratic sessions</option>
            <option value="chat">Regular chats</option>
          </select>
        </label>
        <label className="past-sessions-filter">
          <span aria-hidden="true" className="nb-filter-icon">NB</span>
          <select value={notebookFilter} onChange={(event) => setNotebookFilter(event.target.value)}>
            <option value="">All notebooks</option>
            {notebooks.map((notebook) => <option key={notebook.id} value={notebook.id}>{notebook.title}</option>)}
          </select>
        </label>
      </div>

      {message && <div className="planner-message">{message}</div>}

      <div className="past-session-workspace">
        <section className="past-session-list-panel">
          <div className="past-session-list-heading">
            <div><span className="eyebrow">CONVERSATIONS</span><strong>{sessions.length} loaded</strong></div>
            <span>{hasMore ? 'More available' : 'End of history'}</span>
          </div>

          {loading && !sessions.length ? (
            <div className="past-sessions-empty"><Clock3 size={26} className="spin" /><strong>Loading history…</strong></div>
          ) : !sessions.length ? (
            <div className="past-sessions-empty"><History size={30} /><strong>No matching sessions</strong><span>Try another search or start a new conversation.</span></div>
          ) : (
            <div className="past-session-list">
              {sessions.map((session) => {
                const state = session.socratic_state
                return (
                  <button
                    key={session.id}
                    className={'past-session-list-item ' + (selected?.id === session.id ? 'selected' : '')}
                    onClick={() => setSelected(session)}
                  >
                    <div className="past-session-list-icon"><MessageSquare size={15} /></div>
                    <div className="past-session-list-copy">
                      <strong>{session.title || 'Untitled session'}</strong>
                      <span>{notebookTitles.get(session.notebook_id) || 'Notebook'} · {relativeTime(session.updated)}</span>
                      <small>{state ? 'Socratic · ' + (state.mastery_tier || 'Developing') : (session.message_count || 0) + ' messages'}</small>
                    </div>
                    {session.id === activeSessionId && <CheckCircle2 size={14} className="past-session-open-mark" />}
                  </button>
                )
              })}
            </div>
          )}

          {hasMore && (
            <button className="upload-button past-session-load-more" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load more sessions'}
              <ChevronDown size={14} />
            </button>
          )}
        </section>

        <section className="past-session-detail-panel">
          {!selected ? (
            <div className="past-sessions-empty">
              <BrainCircuit size={30} />
              <strong>Select a session</strong>
              <span>The selected conversation and its Socratic state will appear here.</span>
            </div>
          ) : (
            <>
              <div className="past-session-detail-header">
                <div>
                  <div className="eyebrow">{selected.socratic_state ? 'SOCRATIC SESSION' : 'CHAT SESSION'}</div>
                  <h2>{selected.title || 'Untitled session'}</h2>
                  <p>{notebookTitles.get(selected.notebook_id) || 'Notebook'} · last updated {formatDate(selected.updated)}</p>
                </div>
                <div className="past-session-detail-actions">
                  <button className="icon-button" onClick={renameSelected} title="Rename"><Pencil size={14} /></button>
                  <button className="icon-button" onClick={deleteSelected} title="Delete"><Trash2 size={14} /></button>
                  <button className="upload-button" onClick={() => onOpen?.(selected)}>Continue session</button>
                </div>
              </div>

              {selected.socratic_state && (
                <div className="past-session-state-strip">
                  <div><span>Topic</span><strong>{selected.socratic_state.topic || 'Socratic study'}</strong></div>
                  <div><span>Phase</span><strong>{selected.socratic_state.phase || 'Elenchus'}</strong></div>
                  <div><span>Mastery</span><strong>{Math.round(Number(selected.socratic_state.mastery_score || 0))}/100</strong></div>
                </div>
              )}

              <div className="past-session-messages">
                {previewHasMore && (
                  <button className="past-session-older" onClick={loadOlderMessages} disabled={previewLoading}>
                    {previewLoading ? 'Loading…' : 'Load older messages'}
                  </button>
                )}
                {previewLoading && !previewMessages.length && <div className="past-sessions-empty"><Clock3 size={22} className="spin" /><span>Loading messages…</span></div>}
                {!previewLoading && !previewMessages.length && <div className="past-sessions-empty"><MessageSquare size={26} /><span>This session has no stored messages.</span></div>}
                {previewMessages.map((item) => (
                  <article key={item.id} className={'past-session-message ' + item.role}>
                    <div className="past-session-message-role">{item.role === 'user' ? 'You' : 'Apollo'}</div>
                    <div className="past-session-message-content">{item.content}</div>
                    <div className="past-session-message-time">{formatDate(item.created)}</div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  )
}
