import { useEffect, useState } from 'react'
import { Globe, Link2, Video } from 'lucide-react'
import { importSourceUrl, importYouTubeSource } from './api/sourceIngestionApi'

export default function SourceImportBar({ notebookId, userId = 'default', onImported }) {
  const [mode, setMode] = useState('youtube')
  const [value, setValue] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [youtubeReady, setYoutubeReady] = useState(true)

  useEffect(() => {
    fetch(`${(import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')}/api/capabilities`)
      .then((response) => response.ok ? response.json() : null)
      .then((capabilities) => setYoutubeReady(capabilities?.source_ingestion?.youtube !== false))
      .catch(() => setYoutubeReady(true))
  }, [])

  const submit = async () => {
    const url = value.trim()
    if (!notebookId || !url || busy) return
    setBusy(true)
    setStatus('Importing…')
    try {
      const result = mode === 'youtube'
        ? await importYouTubeSource(notebookId, url, userId)
        : await importSourceUrl(notebookId, url, userId)
      setStatus(`Added ${result.name}`)
      setValue('')
      await onImported?.()
    } catch (error) {
      setStatus(error?.message || 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginBottom: 12, padding: 10, borderRadius: 10, border: '1px solid var(--surface-high)', background: 'var(--surface-container)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 7 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700 }}><Link2 size={14} /> Import source</div>
        <span style={{ fontSize: 9, color: 'var(--tertiary)' }}>Web + YouTube</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 7 }}>
        <button onClick={() => { setMode('youtube'); setStatus('') }} disabled={!youtubeReady} style={{ border: '1px solid var(--surface-high)', borderRadius: 7, padding: '6px 7px', background: mode === 'youtube' ? 'var(--surface-high)' : 'transparent', color: youtubeReady ? 'var(--text)' : 'var(--tertiary)', cursor: youtubeReady ? 'pointer' : 'not-allowed', fontSize: 10 }}><Video size={12} style={{ verticalAlign: -2, marginRight: 4 }} />YouTube</button>
        <button onClick={() => { setMode('url'); setStatus('') }} style={{ border: '1px solid var(--surface-high)', borderRadius: 7, padding: '6px 7px', background: mode === 'url' ? 'var(--surface-high)' : 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 10 }}><Globe size={12} style={{ verticalAlign: -2, marginRight: 4 }} />Web URL</button>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); submit() } }} placeholder={mode === 'youtube' ? 'Paste a YouTube URL…' : 'Paste a public web URL…'} style={{ flex: 1, minWidth: 0, borderRadius: 7, padding: '7px 8px', background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--surface-high)', fontSize: 10 }} />
        <button className="upload-button" onClick={submit} disabled={busy || !notebookId || !value.trim() || (mode === 'youtube' && !youtubeReady)}>{busy ? 'Adding…' : 'Add'}</button>
      </div>
      {status && <div style={{ marginTop: 7, fontSize: 10, color: status.startsWith('Added ') ? 'var(--text)' : '#fca5a5' }}>{status}</div>}
    </div>
  )
}
