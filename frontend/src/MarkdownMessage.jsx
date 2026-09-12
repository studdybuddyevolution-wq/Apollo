import React from 'react'

const stripWebArtifacts = (value) => value
  .replace(/<br\s*\/?>/gi, '\n')
  .replace(/【[^】]{1,120}】/g, '')
  .replace(/\s+\.{3,}\s+/g, ' ')
  .replace(/[ \t]{2,}/g, ' ')

function inlineParts(text) {
  const parts = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g
  let last = 0
  let match
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const token = match[0]
    if (token.startsWith('**')) {
      parts.push(<strong key={`${match.index}-b`}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      parts.push(<code key={`${match.index}-c`}>{token.slice(1, -1)}</code>)
    } else {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/)
      if (link) parts.push(<a key={`${match.index}-a`} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>)
      else parts.push(token)
    }
    last = re.lastIndex
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function cleanLine(line) {
  return line
    .replace(/\s*\[\d+†L?\d+(?:-L?\d+)?\]\s*/g, ' ')
    .replace(/\s*<[^>]+>\s*/g, ' ')
    .trim()
}

function isTableDivider(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
}

function parseTable(lines, start) {
  if (start + 1 >= lines.length || !lines[start].includes('|') || !isTableDivider(lines[start + 1])) return null
  const parse = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
  const headers = parse(lines[start])
  let end = start + 2
  const rows = []
  while (end < lines.length && lines[end].includes('|') && lines[end].trim()) {
    rows.push(parse(lines[end]))
    end += 1
  }
  return { headers, rows, end }
}

export default function MarkdownMessage({ content }) {
  const text = stripWebArtifacts(content || '')
  const lines = text.split(/\r?\n/)
  const blocks = []
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const line = cleanLine(raw)
    if (!line) { i += 1; continue }

    const table = parseTable(lines, i)
    if (table) {
      blocks.push(
        <div className="md-table-wrap" key={`table-${i}`}>
          <table className="md-table">
            <thead><tr>{table.headers.map((h, idx) => <th key={idx}>{inlineParts(cleanLine(h))}</th>)}</tr></thead>
            <tbody>{table.rows.map((row, ridx) => <tr key={ridx}>{table.headers.map((_, cidx) => <td key={cidx}>{inlineParts(cleanLine(row[cidx] || ''))}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      )
      i = table.end
      continue
    }

    if (/^#{1,3}\s+/.test(line)) {
      const level = line.match(/^#+/)?.[0].length || 2
      blocks.push(React.createElement(`h${Math.min(level + 1, 4)}`, { key: `h-${i}` }, inlineParts(line.replace(/^#{1,3}\s+/, ''))))
      i += 1
      continue
    }

    const numbered = line.match(/^\d+[.)]\s+(.*)$/)
    if (numbered) {
      const items = []
      let cursor = i
      while (cursor < lines.length) {
        const match = cleanLine(lines[cursor]).match(/^\d+[.)]\s+(.*)$/)
        if (!match) break
        items.push(<li key={cursor}>{inlineParts(match[1])}</li>)
        cursor += 1
      }
      blocks.push(<ol className="md-list" key={`ol-${i}`}>{items}</ol>)
      i = cursor
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items = []
      let cursor = i
      while (cursor < lines.length) {
        const match = cleanLine(lines[cursor]).match(/^[-*]\s+(.*)$/)
        if (!match) break
        items.push(<li key={cursor}>{inlineParts(match[1])}</li>)
        cursor += 1
      }
      blocks.push(<ul className="md-list" key={`ul-${i}`}>{items}</ul>)
      i = cursor
      continue
    }

    const paragraph = [line]
    let cursor = i + 1
    while (cursor < lines.length) {
      const next = cleanLine(lines[cursor])
      if (!next || /^#{1,3}\s+/.test(next) || /^\d+[.)]\s+/.test(next) || /^[-*]\s+/.test(next) || parseTable(lines, cursor)) break
      paragraph.push(next)
      cursor += 1
    }
    blocks.push(<p key={`p-${i}`}>{inlineParts(paragraph.join(' '))}</p>)
    i = cursor
  }

  return <div className="markdown-message">{blocks}</div>
}
