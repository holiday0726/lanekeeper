'use strict'
// STATUS.md tab

/* ---------- STATUS.md ---------- */
let stat = null, statShown = null

// tiny Markdown subset: headings, lists (nested by indent), tables, fenced code, quotes, rules, paragraphs;
// inline code, **bold**, [text](url). Builds DOM nodes only, never HTML strings.
function inline(s) {
  const out = [], re = /`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g
  let last = 0, m
  while ((m = re.exec(s))) {
    out.push(s.slice(last, m.index)); last = re.lastIndex
    if (m[1] != null) out.push(h('code', {}, m[1]))
    else if (m[2] != null) out.push(h('strong', {}, inline(m[2])))
    else out.push(/^https?:\/\//.test(m[4]) ? h('a', { href: m[4], target: '_blank', rel: 'noopener noreferrer' }, m[3]) : h('span', { title: m[4] }, m[3]))
  }
  out.push(s.slice(last))
  return out
}
function cells(line) {   // split a table row on |, but not inside `code` or after a backslash
  const out = []; let cell = '', code = false
  line = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (c === '\\' && line[i + 1] === '|') { cell += '|'; i++ }
    else if (c === '`') { code = !code; cell += c }
    else if (c === '|' && !code) { out.push(cell.trim()); cell = '' }
    else cell += c
  }
  return [...out, cell.trim()]
}
function md(src) {
  const lines = src.replace(/\r/g, '').split('\n'), out = []
  const LI = /^(\s*)([-*+]|\d+\.)\s+(.*)/
  let i = 0
  while (i < lines.length) {
    const l = lines[i]; let m
    if (!l.trim()) { i++; continue }
    if (/^\s*```/.test(l)) {
      const buf = []
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) buf.push(lines[i])
      i++; out.push(h('pre', {}, h('code', {}, buf.join('\n')))); continue
    }
    if ((m = l.match(/^(#{1,6})\s+(.*)/))) { out.push(h('h' + m[1].length, {}, inline(m[2]))); i++; continue }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { out.push(h('hr')); i++; continue }
    if (l.trim().startsWith('|') && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || '')) {
      const head = cells(l), rows = []
      for (i += 2; i < lines.length && lines[i].trim().startsWith('|'); i++) rows.push(cells(lines[i]))
      out.push(h('div', { class: 'tablewrap' }, h('table', {},
        h('thead', {}, h('tr', {}, head.map(c => h('th', {}, inline(c))))),
        h('tbody', {}, rows.map(r => h('tr', {}, head.map((_, k) => h('td', {}, inline(r[k] || '')))))))))
      continue
    }
    if (LI.test(l)) {
      const stack = []   // [{indent, list, li}]
      for (; i < lines.length && lines[i].trim(); i++) {
        const it = lines[i].match(LI)
        if (!it) { if (stack.length) stack.at(-1).li.append(' ', ...inline(lines[i].trim())); continue }
        const ind = it[1].replace(/\t/g, '    ').length
        while (stack.length > 1 && ind < stack.at(-1).indent) stack.pop()
        if (!stack.length || ind > stack.at(-1).indent) {
          const list = h(/\d/.test(it[2]) ? 'ol' : 'ul')
          if (stack.length) stack.at(-1).li.append(list); else out.push(list)
          stack.push({ indent: ind, list })
        }
        const li = h('li', {}, inline(it[3]))
        stack.at(-1).list.append(li); stack.at(-1).li = li
      }
      continue
    }
    if (l.startsWith('>')) {
      const buf = []
      for (; i < lines.length && lines[i].startsWith('>'); i++) buf.push(lines[i].replace(/^>\s?/, ''))
      out.push(h('blockquote', {}, inline(buf.join(' ')))); continue
    }
    const buf = [l.trim()]   // always take the first line, so an odd line like a lone '|x' cannot stall the loop
    for (i++; i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*```|\s*\|)/.test(lines[i]) && !LI.test(lines[i]); i++) buf.push(lines[i].trim())
    out.push(h('p', {}, inline(buf.join(' '))))
  }
  return out
}

const statHead = h('div', { class: 'mdhead' }), statBody = h('div', { class: 'md' })
function renderStatus() {
  const scroll = view.querySelector('.scroll.status') || h('div', { class: 'scroll status' }, statHead, statBody)
  if (!scroll.isConnected) put(view, scroll)
  put(statHead, h('span', { class: 'mono' }, stat?.path || 'STATUS.md'),
    stat?.mtime ? h('span', {}, '수정 ', h('b', {}, ago(stat.mtime)), hm(stat.mtime)) : null, h('span', {}, '5초마다 다시 읽음'),
    dev?.error ? h('span', { class: 'devwhy' }, 'dev 점유 줄 숨김: dev-occupancy.json ' + (dev.state === 'missing' ? '파일 없음' : '읽지 못함(' + dev.error + ')')) : null)
  if (stat === statShown) return   // rebuild the body only when the file changed, so scroll stays put
  statShown = stat
  put(statBody,
    !stat ? h('div', { class: 'empty' }, '불러오는 중…')
      : stat.missing ? h('div', { class: 'banner' }, 'STATUS.md 를 찾지 못했습니다.')
      : stat.error ? h('div', { class: 'banner' }, 'STATUS.md 를 읽지 못했습니다: ' + stat.error)
      : md(stat.text || ''))
}

async function pollStatus() {
  if (cur || page !== 'status' || document.hidden) return
  try {
    const r = await getJSON('/api/status')
    if (!stat || r.missing !== stat.missing || r.mtime !== stat.mtime || r.text !== stat.text) stat = r
  } catch (err) { if (!stat) stat = { error: err.message } }
  if (!cur && page === 'status') renderStatus()
}
