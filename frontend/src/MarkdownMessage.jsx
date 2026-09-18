import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSanitize from 'rehype-sanitize'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import 'katex/dist/katex.min.css'

const stripWebArtifacts = (value) => String(value || '')
  .replace(/<br\s*\/?>/gi, '\n')
  .replace(/【[^】]{1,120}】/g, '')
  .replace(/\s+\.{3,}\s+/g, ' ')

function linkNumericCitations(content, sources) {
  const sourceByIndex = new Map((sources || []).map((source, index) => [Number(source.index ?? index + 1), source]))
  return String(content || '').replace(/\[(\d+(?:,\s*\d+)*)\](?!\()/g, (match, raw) => {
    const linked = raw.split(',').map((item) => Number(item.trim())).map((index) => {
      const source = sourceByIndex.get(index)
      return source?.url ? '[' + index + '](' + source.url + ')' : '[' + index + ']'
    })
    return linked.join(', ')
  })
}

const markdownComponents = {
  h1: ({ children }) => <h2>{children}</h2>,
  h2: ({ children }) => <h3>{children}</h3>,
  h3: ({ children }) => <h4>{children}</h4>,
  code: ({ inline, className, children, ...props }) => {
    if (inline) return <code {...props}>{children}</code>
    const match = /language-([\w-]+)/.exec(className || '')
    return (
      <SyntaxHighlighter
        language={match?.[1] || 'text'}
        style={oneDark}
        PreTag="div"
        customStyle={{ margin: '10px 0', borderRadius: 9, fontSize: 12, lineHeight: 1.5 }}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    )
  },
  a: ({ href, children, ...props }) => {
    if (!/^https?:\/\//i.test(String(href || ''))) return <span>{children}</span>
    return <a href={href} target="_blank" rel="noreferrer" {...props}>{children}</a>
  },
}

export default function MarkdownMessage({ content, sources = [] }) {
  const text = linkNumericCitations(stripWebArtifacts(content), sources)
  return (
    <div className="markdown-message">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeSanitize, rehypeKatex]}
        components={markdownComponents}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
