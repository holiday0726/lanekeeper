'use strict'
// DOM helpers, shared state, header, alerts, token numbers

const topBar = document.getElementById('top'), nav = document.getElementById('nav'), view = document.getElementById('view')

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue
    if (k === 'class') el.className = v
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v)
    else el.setAttribute(k, v === true ? '' : v)
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c)
  return el
}
const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter(c => c != null && c !== false))
const NS = 'http://www.w3.org/2000/svg'   // sv(): h() for SVG elements
function sv(tag, attrs, ...kids) {
  const el = document.createElementNS(NS, tag)
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v)
    else el.setAttribute(k, v)
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c)
  return el
}

// line icons, drawn instead of arrow and symbol glyphs in the screen text
const ICONS = {
  back: ['M10 3 5 8l5 5'],
  check: ['M3.5 8.5 6.5 11.5 12.5 4.5'],
  ext: ['M7 3H3.5v9.5H13V9', 'M9.5 3H13v3.5', 'M13 3 7.5 8.5'],
  to: ['M2.5 8h10', 'M9 4.5 12.5 8 9 11.5'],
  theme: ['M8 2.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 1 0 0-11z', 'M8 2.5v11a5.5 5.5 0 0 0 0-11z']
}
const icon = (name, label) => sv('svg', Object.assign({ class: 'ico', width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' },
  label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true' }), ICONS[name].map((d, i) => sv('path', { d, fill: name === 'theme' && i ? 'currentColor' : null })))

const span = ms => {
  const m = Math.max(0, Math.floor((Date.now() - ms) / 60000))
  if (m < 1) return '방금'
  if (m < 60) return m + '분'
  const hr = Math.floor(m / 60)
  return hr < 24 ? `${hr}시간 ${m % 60}분` : `${Math.floor(hr / 24)}일 ${hr % 24}시간`
}
const ago = ms => ms ? (span(ms) === '방금' ? '방금' : span(ms) + ' 전') : '기록 없음'
const hm = ms => ms ? ' ' + new Date(ms).toTimeString().slice(0, 5) : ''
const home = p => (p || '').replace(/^\/home\/[^/]+/, '~')
const clock = iso => {
  if (!iso) return ''
  const d = new Date(iso), p = n => String(n).padStart(2, '0')
  const t = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  return d.toDateString() === new Date().toDateString() ? t : `${d.getMonth() + 1}월 ${d.getDate()}일 ${t}`
}

function status(a) {
  if (a.state === 'working' || a.status === 'busy') return { key: 'busy', label: '작업 중' }
  if (a.state === 'blocked') return { key: 'blocked', label: '대기 중' }
  if (a.state === 'done') return { key: 'done', label: '끝남' }
  return { key: 'idle', label: a.kind === 'interactive' || a.engine === 'codex' ? '지시 대기' : '쉬는 중' }
}
const stateEl = s => h('span', { class: 'chip ' + s.key }, h('span', { class: 'dot', 'aria-hidden': 'true' }), s.label)
const kindLabel = a => a.engine === 'codex' ? 'codex ' + (a.source || '') : a.kind === 'background' ? '백그라운드' : '대화형'
// resident sessions carry their lane, one-off task sessions their job id; sessions not in agents.json get neither
const badge = a => a.engine === 'codex' ? h('span', { class: 'badge codex', title: 'Codex 세션' }, 'codex')
  : a.group === 'resident' ? h('span', { class: 'badge lane', title: '상시 세션 레인' }, a.lane || '상시')
  : a.group === 'task' ? h('span', { class: 'badge task', title: '일회성 작업' + (a.lane ? ', ' + a.lane : '') }, a.task || '일회성')
  : null
const SECTIONS = [['busy', '진행 중'], ['wait', '입력 대기'], ['done', '종료']]
let doneOpen = false
try { doneOpen = localStorage.getItem('doneOpen') === '1' } catch (e) {}

let agents = [], error = '', cur = null, page = 'agents'

async function getJSON(url) {
  const r = await fetch(url)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status)
  return r.json()
}

/* ---------- header ---------- */
function renderTop() {
  const n = k => agents.filter(a => status(a).key === k).length
  const blocked = n('blocked')
  const themeBtn = h('button', {
    class: 'theme', title: '밝은 화면과 어두운 화면 바꾸기', 'aria-label': '테마 바꾸기',
    onclick() {
      const t = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'
      document.documentElement.dataset.theme = t
      try { localStorage.setItem('theme', t) } catch (e) {}
    }
  }, icon('theme'))
  put(topBar, 
    cur ? h('a', { class: 'back', href: '#/' }, icon('back'), '목록')
      : h('h1', {}, h('span', { class: 'brand-t' }, '에이전트 대시보드'), h('span', { class: 'page-t' }, (PAGES.find(p => p[0] === page) || PAGES[0])[1])),
    h('div', { class: 'counts' },
      blocked ? h('span', { class: 'count blocked' }, '대기 중 ', h('b', { class: 'num' }, blocked)) : null,
      h('span', { class: 'count' + (n('busy') ? ' ok' : '') }, '작업 중 ', h('b', { class: 'num' }, n('busy'))),
      subRun() ? h('span', { class: 'count ok', title: '지금 도는 서브에이전트' }, '서브에이전트 ', h('b', { class: 'num' }, subRun())) : null,
      h('span', { class: 'count' }, '전체 ', h('b', { class: 'num' }, agents.length))),
    notifyBtn(), themeBtn)
  renderTitle()
  nav.classList.toggle('in-detail', !!cur)   // narrow: the tab row hides on a session page; wide: the sidebar stays
  const nNow = dec?.now?.length || 0, tc = todo?.counts || {}
  put(nav, h('a', { class: 'brand', href: '#/' }, '에이전트 대시보드'),
    h('div', { class: 'tabs', role: 'tablist', 'aria-label': '화면' }, PAGES.map(([key, label, href, group], i) => [
      group !== PAGES[i - 1]?.[3] ? h('div', { class: 'navg', 'aria-hidden': 'true' }, group) : null,
      h('button', { class: 'tab', role: 'tab', 'aria-selected': String(!cur && page === key), onclick: () => { location.hash = href } },
        label, key === 'decisions' && nNow ? h('span', { class: 'num', title: '지금 결정 필요' }, nNow) : null,
        key === 'todo' ? [tc.in_progress ? h('span', { class: 'num ok', title: '진행 중인 할 일' }, tc.in_progress) : null,
          tc.pending ? h('span', { class: 'num plain', title: '대기 중인 할 일' }, tc.pending) : null] : null)])))
}
const subRun = () => agents.reduce((n, a) => n + (a.subagents || []).filter(s => s.state === 'busy').length, 0)
// [key, label, hash, sidebar group]; the narrow tab row keeps the same order without the group names
const PAGES = [['agents', '에이전트', '#/', '세션'], ['flow', '흐름', '#/flow', '세션'], ['decisions', '결정', '#/decisions', '할 것'], ['todo', '할 일', '#/todo', '할 것'], ['status', '현황', '#/status', '허브 문서']]

/* ---------- alerts: tab title count and browser notifications ---------- */
// reports to the hub newer than reportMark are new; unread ones count in the title until the page is seen
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v) } catch (e) { return d } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (e) {} }
}
let reportMark = store.get('reportMark', null), notifyOn = store.get('notify', false)
const unread = new Set()
const canNotify = () => 'Notification' in window && Notification.permission === 'granted' && notifyOn
function renderTitle() {
  const n = agents.filter(a => status(a).key === 'blocked').length + unread.size
  document.title = (n ? `(${n}) ` : '') + '에이전트 대시보드'
}
function seen() {
  if (document.visibilityState === 'visible' && unread.size) { unread.clear(); renderTitle() }
}
// remembered across reloads and tabs, so one event is announced once
function firstTime(key) {
  const done = store.get('notified', [])
  if (done.includes(key)) return false
  store.set('notified', [...done, key].slice(-300))
  return true
}
function forget(keys) {
  const done = store.get('notified', [])
  if (done.some(k => keys.includes(k))) store.set('notified', done.filter(k => !keys.includes(k)))
}
function notify(title, body, tag, hash) {
  try {
    const n = new Notification(title, { body: (body || '').slice(0, 300), tag })
    n.onclick = () => { window.focus(); location.hash = hash; n.close() }
  } catch (e) {}
}
// a session that turns blocked is announced once; once it moves on, the next block is new again
function checkBlocked() {
  const blocked = agents.filter(a => status(a).key === 'blocked')
  const keys = blocked.map(a => 'b:' + a.sessionId)
  forget(store.get('notified', []).filter(k => k.startsWith('b:') && !keys.includes(k)))
  if (!canNotify()) return
  for (const a of blocked) if (firstTime('b:' + a.sessionId)) notify(`${a.name || a.sessionId.slice(0, 8)} 대기 중`, a.needs || a.detail, 'b:' + a.sessionId, '#/s/' + a.sessionId)
}
function checkReports(d) {
  const reports = (d.messages || []).filter(m => m.kind === 'report' && m.to === d.hub && m.t)
  const top = Math.max(0, ...reports.map(m => m.t))
  if (reportMark == null) { reportMark = top || Date.now(); store.set('reportMark', reportMark); return }   // history is not news
  const fresh = reports.filter(m => m.t > reportMark).reverse()
  if (!fresh.length) return
  fresh.forEach(m => unread.add(m.id))
  reportMark = top; store.set('reportMark', reportMark)
  const news = canNotify() ? fresh.filter(m => firstTime('r:' + m.id)) : []
  if (news.length > 3) notify(`${d.hub} 에게 보고 ${news.length}건`, news.map(m => `${m.from}: ${m.sum}`).join('\n'), 'reports', '#/flow')
  else news.forEach(m => notify(`${m.from} 보고`, m.sum, 'r:' + m.id, '#/flow'))
  renderTitle(); seen()
}
// the label hides below 620 px and the bell stays (title and aria-label carry the words)
const bell = () => sv('svg', { width: 15, height: 15, viewBox: '0 0 16 16', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linejoin': 'round' },
  sv('path', { d: 'M4 11.5V7a4 4 0 0 1 8 0v4.5l1.2 1.3H2.8z' }), sv('path', { d: 'M6.5 14.2a1.6 1.6 0 0 0 3 0' }))
function notifyBtn() {
  const btn = (attrs, label) => h('button', Object.assign({ class: 'notif', 'aria-label': label }, attrs), bell(), h('span', { class: 'lbl' }, label))
  if (!('Notification' in window)) return btn({ disabled: true, title: '이 브라우저는 알림을 지원하지 않습니다' }, '알림 없음')
  if (Notification.permission === 'denied') return btn({ disabled: true, title: '브라우저 설정에서 이 주소의 알림을 허용해야 켤 수 있습니다' }, '알림 막힘')
  const on = canNotify()
  return btn({
    'aria-pressed': String(on),
    title: on ? '켜져 있음: 세션이 대기 중이 되거나 허브에게 보고가 오면 알립니다. 누르면 끕니다.'
      : '세션이 대기 중이 되거나 허브에게 보고가 오면 브라우저 알림으로 알립니다',
    async onclick() {
      if (on) notifyOn = false
      else {
        if (Notification.permission === 'default') await Notification.requestPermission()
        notifyOn = Notification.permission === 'granted'
        // what is blocked right now is the starting point; only changes from here are announced
        if (notifyOn) agents.filter(a => status(a).key === 'blocked').forEach(a => firstTime('b:' + a.sessionId))
      }
      store.set('notify', notifyOn); renderTop()
    }
  }, on ? '알림 켬' : '알림 켜기')
}

/* ---------- tokens ---------- */
// 792000 -> 79.2만, 115753467 -> 1.2억 (one decimal below 100 of the unit)
const tok = n => {
  if (n >= 1e8) return +(n / 1e8).toFixed(n < 1e10 ? 1 : 0) + '억'
  if (n >= 1e4) return +(n / 1e4).toFixed(n < 1e6 ? 1 : 0) + '만'
  return n.toLocaleString()
}
// 처리 토큰 = input (cache writes in, cache reads out) + output; cache reads only show in the tooltip
const ENGINE = { claude: 'Claude', codex: 'codex' }
const TOK_DEF = '처리 토큰 = 입력(캐시 쓰기 포함, 캐시 읽기 제외) + 출력'
function tokTip(t) {
  const n = x => (x || 0).toLocaleString()
  const read = `. 합에 넣지 않은 캐시 읽기 ${n(t.cacheRead)}`
  if (t.engine === 'codex') return `처리 토큰 ${n(t.total)}: 입력 ${n(t.input)}(캐시 제외), 출력 ${n(t.output)}(그중 추론 ${n(t.reasoning)})` + read
  return `처리 토큰 ${n(t.total)}: 입력 ${n(t.input)}, 캐시 쓰기 ${n(t.cacheWrite)}, 출력 ${n(t.output)}` + read
    + (t.subagents ? `. 서브에이전트 기록 ${t.subagents}개 포함` : '')
}
const withTokens = () => agents.filter(a => a.tokens).sort((a, b) => b.tokens.total - a.tokens.total)
