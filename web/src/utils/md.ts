/**
 * 轻量安全的 Markdown 渲染：先整体转义，再替换为受控的 HTML 片段。
 * 支持标题、有序/无序列表、引用、表格、代码块、行内代码、粗斜体、链接、分割线。
 * 不引入外部依赖，也不允许原始 HTML 透传（防 XSS）。
 */

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 行内元素：代码 → 粗体 → 斜体 → 链接 → 删除线 */
function inline(src: string): string {
  return src
    .replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/~~([^~]+)~~/g, '<del>$1</del>')
    // 链接：只允许 http/https，避免 javascript: 协议
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a class="md-a" href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    )
}

function isTableRow(line: string): boolean {
  return line.trim().startsWith('|') && line.trim().endsWith('|')
}

function isTableSep(line: string): boolean {
  return /^\s*\|[\s:|-]+\|\s*$/.test(line) && line.includes('-')
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())
}

export function renderMarkdown(src: string): string {
  const lines = escapeHtml(src).split(/\r?\n/)
  const out: string[] = []
  let inCode = false
  let codeBuf: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let paraBuf: string[] = []
  let quoteBuf: string[] = []

  const closeCode = () => {
    if (!inCode) return
    out.push(`<pre class="md-code"><code>${codeBuf.join('\n')}</code></pre>`)
    codeBuf = []
    inCode = false
  }
  const closeList = () => {
    if (!listType) return
    out.push(`</${listType}>`)
    listType = null
  }
  const closePara = () => {
    if (!paraBuf.length) return
    out.push(`<p>${inline(paraBuf.join(' '))}</p>`)
    paraBuf = []
  }
  const closeQuote = () => {
    if (!quoteBuf.length) return
    out.push(`<blockquote class="md-quote">${quoteBuf.map((l) => inline(l)).join('<br/>')}</blockquote>`)
    quoteBuf = []
  }
  // 段落 / 列表 / 引用遇到块级元素时统一收束
  const flushText = () => {
    closePara()
    closeList()
    closeQuote()
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // ---- 代码块 ----
    if (trimmed.startsWith('```')) {
      if (inCode) {
        closeCode()
      } else {
        flushText()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }

    // ---- 空行 ----
    if (!trimmed) {
      flushText()
      continue
    }

    // ---- 分割线 ----
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushText()
      out.push('<hr class="md-hr"/>')
      continue
    }

    // ---- 标题 ----
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed)
    if (heading) {
      flushText()
      const level = Math.min(heading[1].length + 2, 6) // # -> h3，避免与页面标题冲突
      out.push(`<h${level} class="md-h">${inline(heading[2])}</h${level}>`)
      continue
    }

    // ---- 表格 ----
    if (isTableRow(trimmed) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushText()
      const head = splitRow(trimmed)
      i += 2
      const body: string[][] = []
      while (i < lines.length && isTableRow(lines[i])) {
        body.push(splitRow(lines[i]))
        i++
      }
      i--
      const thead = `<thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead>`
      const tbody = body.length
        ? `<tbody>${body
            .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
            .join('')}</tbody>`
        : ''
      out.push(`<div class="md-table-wrap"><table class="md-table">${thead}${tbody}</table></div>`)
      continue
    }

    // ---- 引用 ----
    if (trimmed.startsWith('&gt;')) {
      closePara()
      closeList()
      quoteBuf.push(trimmed.replace(/^&gt;\s?/, ''))
      continue
    }
    closeQuote()

    // ---- 列表 ----
    const ul = /^[-*+]\s+(.*)$/.exec(trimmed)
    const ol = /^(\d+)[.)]\s+(.*)$/.exec(trimmed)
    if (ul || ol) {
      closePara()
      const want: 'ul' | 'ol' = ul ? 'ul' : 'ol'
      if (listType !== want) {
        closeList()
        out.push(`<${want} class="md-list">`)
        listType = want
      }
      out.push(`<li>${inline(ul ? ul[1] : ol![2])}</li>`)
      continue
    }
    closeList()

    // ---- 普通段落 ----
    paraBuf.push(trimmed)
  }

  closeCode()
  closeList()
  closePara()
  closeQuote()
  return out.join('')
}
