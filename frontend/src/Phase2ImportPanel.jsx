import { useEffect, useMemo, useState } from 'react'
import { Globe, Link2, Video, X } from 'lucide-react'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

function getUserId() {
  const key = 'apollo-user-id'
  let value = localStorage.getItem(key)
  if (!value) {
    value = `user_${crypto.randomUUID()}`
    localStorage.setItem(key, value)
  }
  return value
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail || `Apollo API returned ${response.status}`)
  }
  return response.json()
}

export default function Phase2ImportPanel() {
  const uid = useMemo(() => getUserId(), [])
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('url')
  const [notebooks, setNotebooks] = useState([])
  const [notebookId, setNotebookId] = useState('')
  const [value, setValue] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [youtubeReady, setYoutubeReady] = useState(true)

  useEffect(() => {
    if (!open) return
    Promise.all([
      request(`/api/notebooks?user_id=${encodeURIComponent(uid)}`),
      request('/api/capabilities'),
    ]).then(([notebookData, capabilities]) => {
      const items = notebookData.notebooks || []
      setNotebooks(items)
      setNotebookId((current) => current || items[0]?.id || '')
      setYoutubeReady(capabilities?.source_ingestion?.youtube !== false)
    }).catch((error) => setStatus(error.message))
  }, [open, uid])

  const importSource = async () => {
    if (!notebookId || !value.trim() || busy) return
    setBusy(true)
    setStatus('Importing…')
    try {
      const path = mode === 'url'
        ? `/api/notebooks/${encodeURIComponent(notebookId)}/sources/url`
        : `/api/notebooks/${encodeURIComponent(notebookId)}/sources/youtube`
      const body = mode === 'url'
        ? { url: value.trim(), user_id: uid }
        : { url: value.trim(), languages: ['en'], user_id: uid }
      const result = await request(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setStatus(`Added ${result.name}. Refresh Apollo to update the active source list.`)
      setValue('')
    } catch (error) {
      setStatus(error.message)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return <button
      onClick={() => setOpen(true)}
      style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 40, border: '1px solid rgba(255,255,255,.12)', borderRadius: 999, background: '#171820', color: '#f4f4f5', padding: '9px 13px', display: 'flex', alignItems: 'center', gap: 8, boxShadow: '0 12px 35px rgba(0,0,0,.28)', cursor: 'pointer' }}
      title="Import a web page or YouTube transcript"
    >
      <Link2 size={15} /> Import web / YouTube
    </button>
  }

  return <aside style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 40, width: 350, border: '1px solid rgba(255,255,255,.1)', borderRadius: 16, background: '#101117', color: '#f4f4f5', boxShadow: '0 20px 60px rgba(0,0,0,.4)', overflow: 'hidden' }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
      <div><strong style={{ display: 'block', fontSize: 14 }}>Phase 2 import</strong><span style={{ display: 'block', marginTop: 3, fontSize: 11, color: '#9ca3af' }}>Add public web pages or YouTube transcripts</span></div>
      <button onClick={() => setOpen(false)} style={{ border: 0, background: 'transparent', color: '#9ca3af', cursor: 'pointer' }}><X size={17} /></button>
    </div>
    <div style={{ padding: 14 }}>
      <div style={{ display: 'flex', gap: 7, marginBottom: 11 }}>
        <button onClick={() => setMode('url')} style={{ flex: 1, border: '1px solid rgba(255,255,255,.08)', borderRadius: 8, padding: '7px 8px', background: mode === 'url' ? '#20232d' : 'transparent', color: '#fff', cursor: 'pointer' }}><Globe size={13} style={{ verticalAlign: -2 }} /> Web URL</button>
        <button disabled={!youtubeReady} onClick={() => setMode('youtube')} style={{ flex: 1, border: '1px solid rgba(255,255,255,.08)', borderRadius: 8, padding: '7px 8px', background: mode === 'youtube' ? '#20232d' : 'transparent', color: youtubeReady ? '#fff' : '#666', cursor: youtubeReady ? 'pointer' : 'not-allowed' }}><Video size={13} style={{ verticalAlign: -2 }} /> YouTube</button>
      </div>
      <select value={notebookId} onChange={(e) => setNotebookId(e.target.value)} style={{ width: '100%', marginBottom: 10, borderRadius: 8, padding: 9, background: '#181a22', color: '#fff', border: '1px solid rgba(255,255,255,.08)' }}>
        <option value="">Choose notebook</option>
        {notebooks.map((notebook) => <option key={notebook.id} value={notebook.id}>{notebook.title}</option>)}
      </select>
      <input value={value} onChange={(e) => setValue(e.target.value)} placeholder={mode === 'url' ? 'https://example.com/article' : 'https://youtube.com/watch?v=…'} style={{ width: '100%', boxSizing: 'border-box', borderRadius: 8, padding: 9, background: '#181a22', color: '#fff', border: '1px solid rgba(255,255,255,.08)' }} />
      <button onClick={importSource} disabled={busy || !notebookId || !value.trim()} style={{ width: '100%', marginTop: 9, border: 0, borderRadius: 8, padding: '9px 10px', background: '#e5e7eb', color: '#111827', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>{busy ? 'Importing…' : 'Add source'}</button>
      {status && <div style={{ marginTop: 10, padding: 9, borderRadius: 8, background: '#171923', color: '#c9cbd2', fontSize: 11, lineHeight: 1.45 }}>{status}</div>}
      {status.startsWith('Added ') && <button onClick={() => window.location.reload()} style={{ width: '100%', marginTop: 8, border: '1px solid rgba(255,255,255,.1)', borderRadius: 8, padding: '8px 10px', background: 'transparent', color: '#fff', cursor: 'pointer' }}>Refresh Apollo</button>}
    </div>
  </aside>
}
