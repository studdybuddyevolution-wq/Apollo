import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Check,
  Clipboard,
  Download,
  FileDown,
  Printer,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'

function downloadText(content, filename, mimeType = 'text/markdown;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function downloadBase64(base64, filename, mimeType) {
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

export default function StudyReportViewer({
  output,
  progress,
  onRegenerateSection,
  onExportDocx,
}) {
  const [copied, setCopied] = useState(false)
  const [busySection, setBusySection] = useState('')
  const data = output?.data || {}
  const sections = Array.isArray(data.sections) ? data.sections : []
  const plan = Array.isArray(output?.plan) ? output.plan : sections.map((section) => section.heading)
  const sourceNames = Array.isArray(output?.sources) ? output.sources : []
  const verified = Boolean(output?.verified)

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(output?.markdown || '')
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  const regenerate = async (section) => {
    if (!section?.heading || busySection) return
    setBusySection(section.heading)
    try {
      await onRegenerateSection(section.heading)
    } finally {
      setBusySection('')
    }
  }

  return (
    <div className="study-report-viewer" style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
      {progress && progress.percentage < 100 && (
        <div style={{ padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }} role="status" aria-live="polite">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11 }}>
            <strong>{progress.message || 'Generating Study Report…'}</strong>
            <span>{progress.percentage || 0}%</span>
          </div>
          <div style={{ marginTop: 7, height: 6, borderRadius: 999, background: 'var(--surface-high)', overflow: 'hidden' }}>
            <div style={{ width: `${Math.max(0, Math.min(100, progress.percentage || 0))}%`, height: '100%', background: 'var(--primary)', transition: 'width .2s ease' }} />
          </div>
          {progress.plan?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
              {progress.plan.map((item, index) => {
                const complete = progress.current > index || progress.stage === 'generation_complete' || progress.stage === 'complete'
                const active = progress.section === item && progress.stage === 'section'
                return (
                  <span key={`${item}-${index}`} style={{ padding: '3px 6px', borderRadius: 999, border: '1px solid var(--surface-high)', fontSize: 9, color: complete || active ? 'var(--text)' : 'var(--tertiary)' }}>
                    {complete ? '✓ ' : ''}{item}
                  </span>
                )
              })}
            </div>
          )}
        </div>
      )}

      {output?.warning && (
        <div className="grounding-review" role="status">
          <strong>Grounding review</strong>
          <span>{output.warning}</span>
          <span>Source overlap: {Math.round((output.overlap_ratio || 0) * 100)}%</span>
        </div>
      )}

      <div style={{ padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 180 }}>
            <div className="muted-label">{String(output?.mode || 'study').toUpperCase()} REPORT</div>
            <h3 style={{ margin: '4px 0 0', fontSize: 17 }}>{data.title || 'Marklyf Study Report'}</h3>
          </div>
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', fontSize: 9 }}>
            <span style={{ padding: '4px 6px', borderRadius: 999, background: 'var(--surface-container-low)', border: '1px solid var(--surface-high)' }}>{(output?.word_count || 0).toLocaleString()} words</span>
            <span style={{ padding: '4px 6px', borderRadius: 999, background: 'var(--surface-container-low)', border: '1px solid var(--surface-high)' }}>{output?.reference_count || 0} refs</span>
            <span style={{ padding: '4px 6px', borderRadius: 999, background: 'var(--surface-container-low)', border: '1px solid var(--surface-high)' }}><ShieldCheck size={10} style={{ verticalAlign: 'middle', marginRight: 3 }} />{verified ? 'Grounded' : 'Review'}</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 9 }}>
          <button className="upload-button" onClick={copyReport} style={{ width: 'auto', padding: '0 9px' }}>
            {copied ? <Check size={13} /> : <Clipboard size={13} />} {copied ? 'Copied' : 'Copy'}
          </button>
          <button className="upload-button" onClick={() => downloadText(output?.markdown || '', 'Marklyf-Study-Report.md')} style={{ width: 'auto', padding: '0 9px' }}>
            <Download size={13} /> Markdown
          </button>
          <button className="upload-button" onClick={onExportDocx} style={{ width: 'auto', padding: '0 9px' }}>
            <FileDown size={13} /> DOCX
          </button>
          <button className="upload-button" onClick={() => window.print()} style={{ width: 'auto', padding: '0 9px' }}>
            <Printer size={13} /> Print / PDF
          </button>
        </div>

        {sourceNames.length > 0 && (
          <div style={{ marginTop: 8, color: 'var(--tertiary)', fontSize: 9.5, lineHeight: 1.45 }}>
            Grounded in: {sourceNames.join(', ')}
          </div>
        )}
      </div>

      {plan.length > 0 && (
        <div style={{ padding: 10, borderRadius: 10, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
          <div className="muted-label">TABLE OF CONTENTS</div>
          <div style={{ display: 'grid', gap: 4, marginTop: 7 }}>
            {plan.map((item, index) => (
              <div key={`${item}-${index}`} style={{ display: 'flex', gap: 6, fontSize: 10 }}>
                <span style={{ color: 'var(--tertiary)', width: 16 }}>{index + 1}.</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <article style={{ padding: 14, borderRadius: 10, background: 'var(--surface-container-low)', border: '1px solid var(--surface-high)', lineHeight: 1.62, maxHeight: 640, overflow: 'auto' }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {output?.markdown || ''}
        </ReactMarkdown>
      </article>

      {sections.length > 0 && (
        <div style={{ display: 'grid', gap: 7 }}>
          <div className="muted-label">SECTION TOOLS</div>
          {sections.map((section, index) => (
            <div key={`${section.heading || index}-${index}`} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: 8, borderRadius: 8, background: 'var(--surface-container)', border: '1px solid var(--surface-high)' }}>
              <span style={{ flex: 1, minWidth: 0, fontSize: 10.5 }}>
                {index + 1}. {section.heading || 'Section'}
              </span>
              <button
                className="icon-button"
                title="Regenerate section"
                onClick={() => regenerate(section)}
                disabled={Boolean(busySection)}
              >
                {busySection === section.heading ? <RefreshCw size={13} className="spin" /> : <RefreshCw size={13} />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
