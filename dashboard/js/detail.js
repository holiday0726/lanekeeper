'use strict'
// session detail: transcript and the session window (claude logs)

/* ---------- detail ---------- */
function copyRow(cmd) {
  const code = h('code', {}, cmd)
  const btn = h('button', {
    async onclick() {
      try { await navigator.clipboard.writeText(cmd); btn.textContent = '복사됨' }
      catch (e) {
        const r = document.createRange(); r.selectNodeContents(code)
        getSelection().removeAllRanges(); getSelection().addRange(r); btn.textContent = 'Ctrl+C'
      }
      setTimeout(() => { btn.textContent = '복사' }, 1500)
    }
  }, '복사')
  return h('div', { class: 'cmd' }, code, btn)
}

function renderDetailHead() {
  const a = cur.agent
  const head = cur.head
  if (!a) {
    put(head, h('div', { class: 'dtitle' }, h('h2', {}, cur.sid.slice(0, 8))),
      h('div', { class: 'hint' }, '지금 목록에 없는 세션입니다. 이미 끝났을 수 있습니다.'))
    return
  }
  const s = status(a), bg = a.kind === 'background', codex = a.engine === 'codex'
  head.className = 'dhead ' + s.key
  put(head, 
    h('div', { class: 'dtitle' }, h('h2', {}, a.name || a.sessionId.slice(0, 8)), badge(a), stateEl(s)),
    h('div', { class: 'dcwd' }, home(a.cwd)),
    a.detail ? h('div', { class: 'why' }, a.detail) : null,
    s.key === 'blocked' && a.needs ? h('div', { class: 'needs' }, a.needs) : null,
    h('div', { class: 'meta' },
      h('span', {}, kindLabel(a)),
      a.id ? h('span', {}, 'id ', h('b', {}, a.id)) : null,
      h('span', {}, 'pid ', h('b', {}, a.pid)),
      h('span', {}, '시작 ', h('b', {}, ago(a.startedAt))),
      h('span', {}, '활동 ', h('b', {}, ago(a.lastActivity)), hm(a.lastActivity))),
    codex ? h('div', { class: 'cmds' }, h('div', { class: 'hint' },
      'Codex 세션은 대화 기록만 봅니다. 상태는 codex 프로세스가 기록 파일을 열고 있는지와 마지막 턴이 끝났는지로 정합니다.'))
    : h('div', { class: 'cmds' },
      bg ? copyRow('claude attach ' + a.id) : copyRow(`cd ${a.cwd} && claude --resume ${a.sessionId} --fork-session`),
      bg ? null : h('div', { class: 'hint' }, '대화형 세션은 붙는 명령이 없습니다. 위 명령은 이 기록을 새 세션 id 로 복사해 새 창에서 엽니다. 원래 세션의 기록에는 쓰지 않습니다.')),
    (a.subagents || []).length ? h('div', { class: 'subs dsubs' }, h('div', { class: 'subs-t' }, '서브에이전트 ', h('b', {}, a.subagents.length + '개')), subList(a)) : null,
    h('div', { class: 'tabs', role: 'tablist' },
      h('button', { class: 'tab', role: 'tab', 'aria-selected': String(cur.tab === 'chat'), onclick: () => { location.hash = '#/s/' + cur.sid } }, '대화'),
      h('button', {
        class: 'tab', role: 'tab', 'aria-selected': String(cur.tab === 'logs'), disabled: !bg,
        title: bg ? null : codex ? 'Codex 세션은 터미널 출력을 볼 수 없습니다' : '대화형 세션은 터미널 출력을 볼 수 없습니다',
        onclick: () => { location.hash = '#/s/' + cur.sid + '/logs' }
      }, '세션 창')))
}

function showDetail(sid, tab) {
  if (!cur || cur.sid !== sid) {
    cur = { sid, offset: -1, tools: new Map(), head: h('div', { class: 'dhead' }), feed: h('div', { class: 'scroll' }), pane: h('div', { class: 'scroll' }) }
  }
  cur.tab = tab
  cur.agent = agents.find(a => a.sessionId === sid)
  renderTop(); renderDetailHead()
  put(view, cur.head, tab === 'logs' ? cur.pane : cur.feed)
  if (tab === 'logs') pollLogs(); else pollTranscript()
}

function textBlock(text) {
  const t = h('div', { class: 'txt' }, text)
  if (text.length < 700 && text.split('\n').length <= 10) return t
  t.classList.add('clamp')
  const more = h('button', {
    class: 'more', onclick() { more.textContent = t.classList.toggle('clamp') ? '펼치기' : '접기' }
  }, '펼치기')
  return [t, more]
}

function eventEl(e) {
  const who = (label, ...rest) => h('div', { class: 'who' }, h('b', {}, label), ...rest, h('time', {}, clock(e.t)))
  switch (e.k) {
    case 'user': return h('div', { class: 'ev msg user' }, who('사용자'), textBlock(e.text))
    case 'reply': return h('div', { class: 'ev msg reply' }, who(cur.agent?.engine === 'codex' ? 'Codex' : 'Claude'), textBlock(e.text))
    case 'peer': return h('div', { class: 'ev msg peer' }, who(e.from, '에게서 받음'), textBlock(e.text))
    case 'send': return h('div', { class: 'ev msg send' }, who(e.to, '에게 보냄'),
      e.sum ? h('div', { class: 'sum' }, e.sum) : null, textBlock(e.text))
    case 'note': return h('div', { class: 'note' }, e.text, ' ', h('time', {}, clock(e.t)))
    case 'tool': {
      const mark = h('span', { class: 'mark', 'aria-label': '실행 중' }, '…')
      const body = h('div', { class: 'tbody', hidden: true }, h('pre', {}, e.text))
      const head = h('button', {
        class: 'thead', 'aria-expanded': 'false',
        onclick() { body.hidden = !body.hidden; head.setAttribute('aria-expanded', String(!body.hidden)) }
      }, mark, h('span', { class: 'tname' }, e.name), h('span', { class: 'tsum' }, e.sum), h('time', {}, clock(e.t).slice(-8)))
      cur.tools.set(e.id, { mark, body })
      return h('div', { class: 'ev tool' }, head, body)
    }
  }
}

function addResult(e) {
  const t = cur.tools.get(e.id)
  if (!t) return
  t.mark.textContent = e.err ? '✕' : '✓'
  t.mark.className = 'mark ' + (e.err ? 'err' : 'ok')
  t.mark.setAttribute('aria-label', e.err ? '실패' : '완료')
  t.body.append(h('pre', { class: e.err ? 'err' : '' }, e.text || '(출력 없음)'))
}

async function pollTranscript() {
  const c = cur
  if (!c || c.tab !== 'chat' || c.loading) return
  c.loading = true
  try {
    const r = await getJSON(`/api/transcript?sid=${encodeURIComponent(c.sid)}&from=${c.offset}`)
    if (cur !== c) return
    const feed = c.feed
    const follow = c.offset < 0 || feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120
    if (r.reset) {
      c.tools.clear()
      put(feed, r.missing ? h('div', { class: 'empty' }, '이 세션은 아직 기록 파일이 없습니다. 첫 대화가 오가면 여기에 나옵니다.') : null,
        r.truncated ? h('div', { class: 'note-top' }, `최근 ${r.events.length}건만 보여 줍니다.`) : null)
    }
    for (const e of r.events) e.k === 'result' ? addResult(e) : feed.append(eventEl(e))
    c.offset = r.offset
    if (follow && r.events.length) feed.scrollTop = feed.scrollHeight
  } catch (err) {
    if (c.offset < 0) put(c.feed, h('div', { class: 'banner' }, '기록을 읽지 못했습니다: ' + err.message))
  } finally { c.loading = false }
}

/* ---------- session window (claude logs) ---------- */
// xterm takes hex or rgb; the tokens are oklch, so a 1px canvas resolves them
function tokenRGB(name) {
  const g = document.createElement('canvas').getContext('2d')
  g.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || 'black'
  g.fillRect(0, 0, 1, 1)
  const [r, gr, b] = g.getImageData(0, 0, 1, 1).data
  return '#' + [r, gr, b].map(x => x.toString(16).padStart(2, '0')).join('')
}
const COLS = 300   // wider than any daemon pty seen (~200), so nothing wraps; fitTerm crops to used width
function fitTerm(c) {
  const term = c.term, buf = term.buffer.active
  let used = 20
  for (let y = 0; y < buf.length; y++) {
    const line = buf.getLine(y)
    for (let x = term.cols - 1; x >= used; x--) if (line.getCell(x)?.getChars().trim()) { used = x + 1; break }
  }
  const screen = c.box.querySelector('.xterm-screen')
  const cellW = screen.offsetWidth / term.cols
  if (!cellW) return
  const avail = c.box.parentElement.clientWidth - 20
  const fs = Math.max(7, Math.min(13, Math.floor(term.options.fontSize * avail / (used * cellW) * 2) / 2))
  if (fs !== term.options.fontSize) term.options.fontSize = fs
  requestAnimationFrame(() => { c.box.style.width = Math.ceil(used * screen.offsetWidth / term.cols) + 'px' })
}

// portrait friendly view: the terminal is parsed at full width, then its rows are re-flowed as wrapping text
let logMode = 'flow'
try { logMode = localStorage.getItem('logMode') === 'raw' ? 'raw' : 'flow' } catch (e) {}
const RULE = /^[\s\u2500-\u257f]+$/   // box drawing rows
function flowRows(term) {
  const buf = term.buffer.active, rows = []
  for (let y = 0; y < buf.length; y++) rows.push((buf.getLine(y)?.translateToString(true) || '').replace(/\s+$/, ''))
  while (rows.length && !rows.at(-1)) rows.pop()
  const out = []
  for (const l of rows) {
    if (!l) { if (out.length && out.at(-1) !== '') out.push(''); continue }
    out.push(l)
  }
  return out
}
function renderFlow(c) {
  const pane = c.pane, follow = !c.flowShown || pane.scrollHeight - pane.scrollTop - pane.clientHeight < 120
  put(c.flowEl, flowRows(c.term).map(l => {
    if (!l) return h('div', { class: 'll gap' })
    if (RULE.test(l)) return h('div', { class: 'll sep' })
    const k = l.trimStart()[0]
    return h('div', { class: 'll' + (k === '\u25cf' ? ' bul' : k === '\u23bf' ? ' res' : k === '\u276f' ? ' prm' : '') }, l)
  }))
  c.flowShown = true
  if (follow) pane.scrollTop = pane.scrollHeight
}
function applyLogMode(c) {
  const flow = logMode === 'flow'
  c.flowEl.hidden = !flow
  c.rawWrap.classList.toggle('off', flow)
  for (const [m, btn] of Object.entries(c.modeBtns)) btn.setAttribute('aria-pressed', String(m === logMode))
  c.note.textContent = flow
    ? 'claude logs 출력을 3초마다 다시 그립니다. 화면 폭에 맞춰 줄바꿈한 글만 보여 주며 색과 배치는 원본 화면에서 볼 수 있습니다.'
    : 'claude logs 출력을 3초마다 다시 그립니다. 출력이 화면 중간부터 남아 있으면 위쪽이 비어 보일 수 있습니다.'
  if (!flow) requestAnimationFrame(() => fitTerm(c))
}

async function pollLogs() {
  const c = cur
  if (!c || c.tab !== 'logs' || !c.agent?.id || c.loadingLogs || document.hidden) return
  c.loadingLogs = true
  try {
    const r = await fetch('/api/logs?id=' + encodeURIComponent(c.agent.id))
    const text = await r.text()
    if (cur !== c || text === c.logText) return
    c.logText = text
    // The TUI paints with absolute rows (CSI row;col H); the largest row is the screen height.
    let rows = 24
    for (const m of text.matchAll(/\x1b\[(\d+);\d+H/g)) rows = Math.max(rows, +m[1])
    if (!c.term) {
      c.box = h('div', { class: 'term' })
      c.rawWrap = h('div', { class: 'termwrap' }, c.box)
      c.flowEl = h('div', { class: 'logflow' })
      c.note = h('p', { class: 'pane-note' })
      c.modeBtns = {}
      const mk = (m, label) => (c.modeBtns[m] = h('button', {
        class: 'segb', onclick() { logMode = m; try { localStorage.setItem('logMode', m) } catch (e) {} applyLogMode(c) }
      }, label))
      put(c.pane, h('div', { class: 'seg', role: 'group', 'aria-label': '세션 창 보기 방식' }, mk('flow', '세로 보기'), mk('raw', '원본 화면')),
        c.flowEl, c.rawWrap, c.note)
      c.term = new Terminal({
        cols: COLS, rows, fontSize: 10, scrollback: 0, disableStdin: true, cursorBlink: false,
        fontFamily: getComputedStyle(document.body).getPropertyValue('--font-outlier'),
        theme: { background: tokenRGB('--term-bg'), foreground: tokenRGB('--term-ink'), cursor: tokenRGB('--term-bg'), cursorAccent: tokenRGB('--term-bg') }
      })
      c.term.open(c.box)
      applyLogMode(c)
    } else if (c.term.rows !== rows) c.term.resize(COLS, rows)
    const first = !c.fitted
    c.term.reset()
    c.term.write(text + '\x1b[?25l', () => {
      fitTerm(c); c.fitted = true
      renderFlow(c)
      if (first) c.pane.scrollTop = c.pane.scrollHeight
    })
  } catch (err) {
    if (!c.term) put(c.pane, h('div', { class: 'banner' }, '세션 창을 읽지 못했습니다: ' + err.message))
  } finally { c.loadingLogs = false }
}
