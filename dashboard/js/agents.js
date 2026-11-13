'use strict'
// agents tab: cards, the session canvas and the list

/* ---------- list ---------- */
const SUB_STATE = { busy: '작업 중', done: '끝남', idle: '응답 없음' }
const openSubs = new Set()
try { JSON.parse(localStorage.getItem('openSubs') || '[]').forEach(x => openSubs.add(x)) } catch (e) {}
const saveSubs = () => { try { localStorage.setItem('openSubs', JSON.stringify([...openSubs])) } catch (e) {} }

function subItem(s) {
  return h('li', { class: 'sub ' + s.state },
    h('span', { class: 'dot', 'aria-hidden': 'true' }),
    h('div', { class: 'sd' }, h('span', { class: 'st' }, s.type || '서브에이전트'), s.desc || '설명 없음'),
    h('time', {}, ago(s.at)),
    h('div', { class: 'sl' }, SUB_STATE[s.state] || s.state))
}
function subList(a) {
  return h('ul', { class: 'sublist' }, (a.subagents || []).map(subItem))
}
function subFold(a) {
  const subs = a.subagents || []
  if (!subs.length) return null
  const run = subs.filter(s => s.state === 'busy').length, open = openSubs.has(a.sessionId)
  return h('div', { class: 'subs' },
    h('button', {
      class: 'subs-t', 'aria-expanded': String(open),
      onclick() { open ? openSubs.delete(a.sessionId) : openSubs.add(a.sessionId); saveSubs(); renderList() }
    }, '서브에이전트 ', h('b', {}, subs.length + '개'), run ? h('span', { class: 'run' }, `${run}개 작업 중`) : null,
      h('span', { class: 'chev', 'aria-hidden': 'true' }, open ? '접기' : '펼치기')),
    open ? subList(a) : null)
}

/* who started a session with `claude --bg` (server link_parents): the listed parent, or the starter that has closed */
const hubRow = () => agents.find(a => a.lane === 'HUB')
function upOf(a) {
  const p = a.parent && a.parent !== hubRow()?.sessionId ? agents.find(b => b.sessionId === a.parent) : null
  return p ? p.name || p.sessionId.slice(0, 8) : null
}
const goneEl = a => a.launcherGone ? h('span', { title: '이 세션을 띄운 세션이 목록에 없습니다' }, '띄운 세션 ', h('b', {}, a.launcher), ' 닫힘') : null

function agentCard(a) {
  const s = status(a), up = upOf(a)
  return h('article', { class: `agent ${s.key} g-${a.group || 'other'}` },
    h('a', { class: 'amain', href: '#/s/' + a.sessionId },
      h('div', { class: 'r1' }, h('span', { class: 'name' }, a.name || a.sessionId.slice(0, 8)), badge(a), stateEl(s)),
      a.detail ? h('div', { class: 'why' }, a.detail) : null,
      s.key === 'blocked' && a.needs ? h('div', { class: 'needs' }, a.needs) : null,
      h('div', { class: 'meta' },
        h('span', {}, '활동 ', h('b', {}, ago(a.lastActivity)), hm(a.lastActivity)),
        h('span', {}, '시작 ', h('b', {}, ago(a.startedAt))),
        h('span', {}, kindLabel(a)),
        h('span', { class: 'mono', title: home(a.cwd) }, home(a.cwd).split('/').pop()),
        a.tokens ? h('span', { title: tokTip(a.tokens) }, '토큰 ', h('b', {}, tok(a.tokens.total))) : null,
        up ? h('span', { title: '이 세션을 띄운 세션' }, '상위 ', h('b', {}, up)) : null, goneEl(a))),
    subFold(a))
}

/* 3D office: off by default. Turning it on loads three.js and js/office.js once, then keeps the choice. */
let hero = null   // office.js fills it; flow.js and main.js only look at hero?.ok
let officeOn = store.get('office', false) === true
let officeLoad = null   // the promise of loading three.js and office.js, once
function loadOffice() {
  const add = src => new Promise((ok, fail) => document.head.append(h('script', { src, onload: ok, onerror: () => fail(new Error(src)) })))
  officeLoad ||= add('/vendor/three.min.js').then(() => add('/vendor/OrbitControls.js')).then(() => add('/js/office.js'))
  return officeLoad
}
function officeToggle() {
  return h('button', {
    class: 'segb', 'aria-pressed': String(officeOn), title: '세션을 3D 오피스로도 봅니다. 켤 때 three.js 를 불러옵니다',
    onclick() { officeOn = !officeOn; store.set('office', officeOn); renderList() }
  }, '3D 오피스')
}
function officeSlot(slot) {
  if (!officeOn || !agents.length) return put(slot)   // a box left behind stops its loop by itself (heroLoop checks isConnected)
  if (typeof heroBox !== 'function') {
    put(slot, h('div', { class: 'empty' }, '3D 오피스를 불러오는 중'))
    loadOffice().then(() => { if (page === 'agents' && !cur) renderList() },
      () => put(slot, h('div', { class: 'empty' }, '3D 오피스를 불러오지 못했습니다')))
    return
  }
  try { if (slot.firstChild !== heroBox()) put(slot, heroBox()); updateHero() } catch (e) { put(slot) }   // the list below still draws
}

/* session canvas: the hub in the middle, sessions at work on one side, the rest on the other, a line to each;
   a solid line means they messaged in the last 24 hours, the number on it how many. A session another one started
   with `claude --bg` sits under that one, indented away from the hub and joined to it instead of to the hub; a whole
   branch goes to the busy side when anyone in it is busy */
let agentView = store.get('agentView', 'canvas') === 'list' ? 'list' : 'canvas'
let msgs24 = null
const WIDE_CANVAS = 760   // px; matches the container query that sets the three columns
function nodeCard(a, hub) {
  const s = status(a), tag = a.engine === 'codex' ? 'codex' : a.group === 'task' ? a.task : a.lane
  const decs = (dec?.now || []).filter(d => !d.live && d.source && d.source === a.name).length
  const run = (a.subagents || []).filter(x => x.state === 'busy').length
  return h('a', { class: `node ${s.key} g-${a.group || 'other'}${hub ? ' hub' : ''}`, href: '#/s/' + a.sessionId, 'data-sid': a.sessionId },
    tag ? h('span', { class: 'ntag' + (a.group === 'task' || a.engine === 'codex' ? ' mono' : '') }, tag) : null,
    h('span', { class: 'nhead' }, h('span', { class: 'name' }, a.name || a.sessionId.slice(0, 8)), stateEl(s)),
    h('span', { class: 'ndesc' }, a.detail || (hub ? '허브' : '하는 일 기록 없음')),
    h('span', { class: 'nmeta' }, h('span', {}, '활동 ', h('b', {}, ago(a.lastActivity))),
      a.tokens ? h('span', { title: tokTip(a.tokens) }, '토큰 ', h('b', {}, tok(a.tokens.total))) : null,
      run ? h('span', {}, '서브에이전트 ', h('b', {}, run)) : null, goneEl(a)),
    s.key === 'blocked' ? h('span', { class: 'nflag ask' }, a.needs || '대기 중')
      : decs ? h('span', { class: 'nflag' }, `결정 대기 ${decs}`) : null)
}
function canvasEl() {
  const hubName = msgs24?.hub
  const hubA = agents.find(a => a.lane === 'HUB') || agents.find(a => hubName && a.name === hubName)
  const rest = agents.filter(a => a !== hubA)
  const ids = new Set(rest.map(a => a.sessionId)), kids = new Map()
  const up = a => a.parent && ids.has(a.parent) ? a.parent : null   // the server keeps parents a tree
  for (const a of rest) if (up(a)) kids.set(up(a), [...(kids.get(up(a)) || []), a])
  const top = rest.filter(a => !up(a))
  const busy = a => a.section === 'busy' || (kids.get(a.sessionId) || []).some(busy)
  const tree = a => h('div', { class: 'tree' }, nodeCard(a),
    kids.has(a.sessionId) ? h('div', { class: 'kids' }, kids.get(a.sessionId).map(tree)) : null)
  const svg = sv('svg', { class: 'links', 'aria-hidden': 'true' })
  const box = h('div', { class: 'canvas' + (hubA ? '' : ' nohub') }, svg,
    h('div', { class: 'ccol left' }, top.filter(busy).map(tree)),
    hubA ? h('div', { class: 'ccol mid' }, nodeCard(hubA, true)) : null,
    h('div', { class: 'ccol right' }, top.filter(a => !busy(a)).map(tree)))
  const edges = msgs24?.edges || [], c = (f, t) => edges.find(x => x.from === f && x.to === t)?.count || 0
  const count = (from, name) => ({ out: c(from, name), back: c(name, from) })
  box.drawLinks = () => {
    if (!box.isConnected) return
    const B = box.getBoundingClientRect(), wide = B.width >= WIDE_CANVAS
    const hubEl = box.querySelector('.node.hub')
    const r = e => { const q = e.getBoundingClientRect(); return { l: q.left - B.left, r: q.right - B.left, t: q.top - B.top, b: q.bottom - B.top, w: q.width, h: q.height } }
    const hb = hubEl && r(hubEl), f1 = v => v.toFixed(1)
    svg.setAttribute('viewBox', `0 0 ${f1(B.width)} ${f1(B.height)}`)
    svg.setAttribute('width', f1(B.width)); svg.setAttribute('height', f1(B.height))
    const parts = []
    for (const el of box.querySelectorAll('.ccol:not(.mid) .node')) {
      const a = agents.find(x => x.sessionId === el.dataset.sid), q = r(el), left = el.closest('.left')
      const pEl = el.parentElement.parentElement.closest('.tree')?.querySelector(':scope > .node')
      const from = pEl ? agents.find(x => x.sessionId === pEl.dataset.sid)?.name : hubA?.name
      if (!pEl && !hubA) continue
      const { out, back } = count(from, a.name), n = out + back, y = q.t + q.h / 2
      let d, lx, ly, anchor = left ? 'start' : 'end'
      if (pEl) {    // from the parent's foot, down the indent beside the children, a turn into the card
        const p = r(pEl), x0 = left ? p.r - 11 : p.l + 11, x1 = left ? q.r : q.l, k = Math.min(8, Math.abs(x0 - x1))
        d = `M${f1(x0)},${f1(p.b)} V${f1(y - k)} Q${f1(x0)},${f1(y)} ${f1(x0 + (left ? -k : k))},${f1(y)} H${f1(x1)}`
        lx = x0; ly = (p.b + y) / 2 + 4; anchor = 'middle'
      } else if (wide) {   // side to side: hub edge to the card's inner edge
        const x0 = left ? hb.l : hb.r, y0 = hb.t + hb.h / 2, x1 = left ? q.r : q.l, mx = (x0 + x1) / 2
        d = `M${f1(x0)},${f1(y0)} C${f1(mx)},${f1(y0)} ${f1(mx)},${f1(y)} ${f1(x1)},${f1(y)}`; lx = x1 + (left ? 8 : -8); ly = y - 6
      } else {      // a spine down the middle gutter from the hub, a branch to each card
        const cx = hb.l + hb.w / 2, x1 = left ? q.r : q.l, k = Math.min(10, Math.abs(cx - x1))
        d = `M${f1(cx)},${f1(hb.b)} V${f1(y - k)} Q${f1(cx)},${f1(y)} ${f1(cx + (left ? -k : k))},${f1(y)} H${f1(x1)}`; lx = x1 + (left ? 4 : -4); ly = y - 6
      }
      parts.push(sv('path', { class: 'link' + (n ? ' on' : '') + (status(a).key === 'blocked' ? ' ask' : ''), d }))
      if (n) parts.push(sv('text', { class: 'lnum', x: f1(lx), y: f1(ly), 'text-anchor': anchor },
        sv('title', {}, pEl ? `${from}에서 ${out}건, ${from}로 ${back}건(24시간)` : `허브에서 ${out}건, 허브로 ${back}건(24시간)`), n + '건'))
    }
    put(svg, parts)
  }
  return box
}
let canvasObs = null
function canvasBlock() {
  let box
  try { box = canvasEl() } catch (e) { return null }   // the list view stays one click away
  canvasObs?.disconnect()
  canvasObs = new ResizeObserver(() => box.drawLinks())
  canvasObs.observe(box)
  requestAnimationFrame(() => box.drawLinks())
  return h('div', { class: 'canvas-wrap' }, box)   // the container the column query measures
}

// the server already sorts: section, then task / resident / other, then latest activity
function renderList() {
  const scroll = view.querySelector('.scroll.list') || h('div', { class: 'scroll list' }, h('div', { class: 'slot-top' }), h('div', { class: 'slot-hero' }), h('div', { class: 'slot-rest' }))
  const [top, heroSlot, rest] = scroll.children
  const viewSeg = h('div', { class: 'seg flat', role: 'group', 'aria-label': '세션 보기' }, [['canvas', '흐름도'], ['list', '목록']].map(([v, label]) => h('button', {
    class: 'segb', 'aria-pressed': String(agentView === v),
    onclick() { if (agentView !== v) { agentView = v; store.set('agentView', v); renderList() } }
  }, label)))
  const canvas = agents.length && agentView === 'canvas' ? canvasBlock() : null
  put(top,
    error ? h('div', { class: 'banner' }, `서버에 연결하지 못했습니다(${error}). 폴더에서 ./run.sh 로 다시 띄우세요.`) : null,
    !error && !agents.length ? h('div', { class: 'empty' }, '떠 있는 세션이 없습니다.') : null)
  officeSlot(heroSlot)
  put(rest,
    agents.length ? h('div', { class: 'vhead' }, h('h2', {}, '세션'),
      h('span', { class: 'hint' }, agentView === 'canvas' ? '허브와 지난 24시간 메시지가 오간 세션은 실선, 숫자는 건수' : '구역별 목록'), viewSeg,
      h('div', { class: 'seg flat', role: 'group', 'aria-label': '3D 오피스' }, officeToggle())) : null,
    canvas,
    agents.length && !canvas ? SECTIONS.map(([key, title]) => {
      const list = agents.filter(a => (a.section || 'wait') === key)
      const fold = key === 'done', open = !fold || doneOpen
      const head = [h('h2', {}, title), h('span', { class: 'num' }, list.length),
        fold ? h('span', { class: 'chev', 'aria-hidden': 'true' }, open ? '접기' : '펼치기') : null]
      return h('section', { class: 'sec', 'data-sec': key },
        fold ? h('button', {
          class: 'sec-h', 'aria-expanded': String(open),
          onclick() { doneOpen = !doneOpen; try { localStorage.setItem('doneOpen', doneOpen ? '1' : '0') } catch (e) {} renderList() }
        }, head) : h('div', { class: 'sec-h' }, head),
        open ? (list.length ? list.map(agentCard) : h('div', { class: 'sec-empty' }, '없음')) : null)
    }) : null)
  if (!scroll.isConnected) put(view, scroll)
}
