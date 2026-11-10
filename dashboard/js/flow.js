'use strict'
// flow tab: messages between sessions

/* ---------- flow: messages between sessions ---------- */
const WINDOWS = [[1, '1시간'], [6, '6시간'], [24, '24시간'], [0, '전체']]
const KIND_LABEL = { assign: '배정', report: '보고', notice: '알림', other: '기타' }
const GROUP_RANK = { resident: 0, task: 1, codex: 2, other: 3 }
let flowHours = 24, flow = null, flowKey = '', flowSel = null
try { const v = localStorage.getItem('flowHours'); if (WINDOWS.some(([x]) => String(x) === v)) flowHours = +v } catch (e) {}
const openMsgs = new Set()
const short = ms => clock(ms).replace(/:\d\d$/, '')
const nodeKey = n => n.listed ? status(n).key : 'closed'
const nodeTip = n => [n.name,
  n.group === 'resident' ? '상시 ' + (n.lane || '') : n.group === 'task' ? '일회성 ' + (n.task || '') : n.group === 'codex' ? 'codex' : '',
  n.listed ? status(n).label : '목록에 없음(닫힘)', `보냄 ${n.sent}, 받음 ${n.got}`].filter(x => x && x.trim()).join(', ')
const related = (m, sel) => !sel || (sel.node ? m.from === sel.node || m.to === sel.node : m.from === sel.edge[0] && m.to === sel.edge[1])
function select(sel) {
  const same = sel && flowSel && JSON.stringify(sel) === JSON.stringify(flowSel)
  flowSel = same ? null : sel
  renderFlowTab()
}

// the orbit: hub in the middle, the busiest RING sessions named on a ring around it, any others as small unnamed dots
// on an inner ring (name on hover or when picked). 입체 lays the rings on a tilted plane that a drag or the arrow keys
// turn, and each route arcs above it; 평면 looks straight down. Edges bend left of travel so the two directions part.
const RING = 16
let flowView = store.get('flowView', 'orbit') === 'flat' ? 'flat' : 'orbit'
const cam = { yaw: -0.5, pitch: 0.62 }
try { const c = store.get('flowCam', null); if (c && isFinite(c.yaw) && isFinite(c.pitch)) Object.assign(cam, { yaw: c.yaw, pitch: c.pitch }) } catch (e) {}
const PITCH = [0.45, 1.45]   // radians above the plane: flat on the edge to nearly straight down
let dragged = false   // a drag that turned the orbit is not a click
const unit = (p, q) => { const l = Math.hypot(q.x - p.x, q.y - p.y) || 1; return { x: (q.x - p.x) / l, y: (q.y - p.y) / l } }

function graphBox(f, W) {
  const H = Math.round(Math.min(500, Math.max(360, W * 0.7)))
  const load = n => n.sent + n.got
  const hub = f.nodes.find(n => n.name === f.hub) || [...f.nodes].sort((a, b) => load(b) - load(a))[0]
  const rest = f.nodes.filter(n => n !== hub)
    .sort((a, b) => (GROUP_RANK[a.group] ?? 9) - (GROUP_RANK[b.group] ?? 9) || load(b) - load(a) || a.name.localeCompare(b.name))
  const named = new Set([...rest].sort((a, b) => load(b) - load(a)).slice(0, RING).map(n => n.name))
  const outer = rest.filter(n => named.has(n.name)), inner = rest.filter(n => !named.has(n.name))
  const world = new Map([[hub.name, { x: 0, y: 0, r: 18 }]])   // the plane: outer ring radius 1
  outer.forEach((n, i) => {
    const a = -Math.PI / 2 + 2 * Math.PI * i / outer.length
    world.set(n.name, { x: Math.cos(a), y: Math.sin(a), r: 7 + Math.min(9, Math.sqrt(load(n)) * 1.3) })
  })
  inner.forEach((n, i) => {
    const a = -Math.PI / 2 + 2 * Math.PI * (i + 0.5) / inner.length
    world.set(n.name, { x: 0.58 * Math.cos(a), y: 0.58 * Math.sin(a), r: 4.5, dot: true })
  })
  const orbit = flowView === 'orbit', sel = flowSel
  const svg = sv('svg', {
    viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'group', tabindex: 0,
    'aria-label': '세션 사이 메시지 그래프' + (orbit ? '. 끌거나 화살표 키로 돌립니다' : ''),
    onclick: () => { if (!dragged && flowSel) select(null) }
  })

  function draw() {
    const yaw = orbit ? cam.yaw : 0, pitch = orbit ? cam.pitch : Math.PI / 2
    const cs = Math.cos(yaw), sn = Math.sin(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch)
    // fit the tilted disc, its rising arcs and the front labels inside the box at any angle and width
    const R0 = Math.min(W / 2 - 84, H), V0 = Math.min(R0 * sp, H / 2 - 52), k1 = 0.19 * cp
    const up = 1.16 * V0 * (1 - k1) + 0.4 * R0 * cp, down = 1.16 * V0 * (1 + k1)
    const fit = Math.min(1, (H - 72) / (up + down)), Rx = R0 * fit, V = V0 * fit, lift = R0 * cp * fit
    const cx = W / 2, cy = 36 + up * fit + Math.max(0, (H - 72 - (up + down) * fit) / 2)
    const proj = (x, y, z = 0) => {
      const xr = x * cs - y * sn, yr = x * sn + y * cs, k = 1 + 0.16 * yr * cp   // nearer the viewer, a little larger
      return { x: cx + xr * Rx * k, y: cy + yr * V * k - z * lift * k, k, d: yr }
    }
    const pos = new Map([...world].map(([name, p]) => { const q = proj(p.x, p.y); return [name, Object.assign(q, { r: p.r * q.k, dot: p.dot })] }))
    const f1 = v => v.toFixed(1)
    const ring = r => 'M' + Array.from({ length: 73 }, (_, i) => { const a = i / 72 * 2 * Math.PI, q = proj(r * Math.cos(a), r * Math.sin(a)); return f1(q.x) + ',' + f1(q.y) }).join(' L')
    const ground = sv('g', { 'aria-hidden': 'true' },
      sv('path', { class: 'odisc', d: ring(1.16) + 'Z' }),
      [1, 0.58].map(r => sv('path', { class: 'oring', d: ring(r) })))   // the two orbits the sessions sit on
    const edges = f.edges.map(e => {
      const A = world.get(e.from), B = world.get(e.to), a = pos.get(e.from), b = pos.get(e.to)
      if (!A || !B || A === B) return null
      const len = Math.hypot(B.x - A.x, B.y - A.y) || 1, off = Math.min(0.2, len * 0.14)
      const Cp = { x: (A.x + B.x) / 2 + (B.y - A.y) / len * off, y: (A.y + B.y) / 2 - (B.x - A.x) / len * off, z: 0.1 + 0.3 * len }
      const pts = []
      for (let i = 0; i <= 32; i++) {
        const t = i / 32, u = 1 - t
        pts.push(proj(u * u * A.x + 2 * u * t * Cp.x + t * t * B.x, u * u * A.y + 2 * u * t * Cp.y + t * t * B.y, 2 * u * t * Cp.z))
      }
      const w = Math.min(7, 1.2 + 1.6 * Math.log2(e.count)) * (a.k + b.k) / 2, L = 6 + w, hw = 3.5 + w / 2
      const far = (p, c, r) => Math.hypot(p.x - c.x, p.y - c.y) >= r
      let i0 = 0; while (i0 < pts.length - 2 && !far(pts[i0], a, a.r + 2)) i0++
      let i1 = pts.length - 1; while (i1 > i0 + 1 && !far(pts[i1], b, b.r + 2)) i1--
      const tip = pts[i1]
      let i2 = i1; while (i2 > i0 && !far(pts[i2], tip, L)) i2--
      const base = pts[i2], u = unit(tip, base)
      const d = 'M' + pts.slice(i0, i2 + 1).map(p => f1(p.x) + ',' + f1(p.y)).join(' L')
      const head = [tip, { x: base.x - u.y * hw, y: base.y + u.x * hw }, { x: base.x + u.y * hw, y: base.y - u.x * hw }]
      const on = sel && (sel.edge ? sel.edge[0] === e.from && sel.edge[1] === e.to : e.from === sel.node || e.to === sel.node)
      return sv('g', {
        class: 'fe' + (on ? ' on' : sel ? ' dim' : ''),
        onclick(ev) { ev.stopPropagation(); if (!dragged) select({ edge: [e.from, e.to] }) }
      }, sv('title', {}, `보낸 쪽 ${e.from}, 받는 쪽 ${e.to}, ${e.count}건, 마지막 ${short(e.last)}`),
        sv('path', { class: 'fhit', d }), sv('path', { class: 'fedge', d, 'stroke-width': f1(w) }),
        sv('polygon', { class: 'farrow', points: head.map(p => f1(p.x) + ',' + f1(p.y)).join(' ') }))
    })
    const nodes = [hub, ...inner, ...outer].sort((m, n) => pos.get(m.name).d - pos.get(n.name).d).map(n => {   // far first
      // ~7.4 px per character: centred when it fits, else anchored to the nearer box edge, cut only past the box width
      const p = pos.get(n.name), wide = n.name.length * 7.4, centred = p.x - wide / 2 > 6 && p.x + wide / 2 < W - 6
      const anchor = centred ? 'middle' : p.x > W / 2 ? 'end' : 'start', tx = centred ? 0 : p.x > W / 2 ? Math.max(0, W - 6 - p.x) : Math.min(0, 6 - p.x)
      const fit = Math.max(6, Math.floor((W - 12) / 7.4))
      const on = sel && (sel.node ? sel.node === n.name : sel.edge.includes(n.name))
      const pick = () => { if (!dragged) select({ node: n.name }) }
      return sv('g', {
        class: `fnode ${nodeKey(n)} g-${n.group}${n === hub ? ' hub' : ''}${on ? ' on' : sel && !on ? ' dim' : ''}`,
        transform: `translate(${f1(p.x)},${f1(p.y)})`, tabindex: 0, role: 'button', 'aria-label': nodeTip(n), 'data-name': n.name,
        onclick(ev) { ev.stopPropagation(); pick() },
        onkeydown(ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ev.stopPropagation(); pick() } }
      }, sv('title', {}, nodeTip(n)), sv('circle', { r: f1(p.r) }),
        sv('text', { x: f1(tx), y: f1(p.r + 15), 'text-anchor': anchor, class: p.dot && !on ? 'hover' : null }, n.name.length > fit ? n.name.slice(0, fit - 1) + '…' : n.name))
    })
    const focused = svg.contains(document.activeElement) ? document.activeElement.getAttribute('data-name') : null
    put(svg, ground, edges, nodes)
    if (focused) [...svg.querySelectorAll('.fnode')].find(g => g.getAttribute('data-name') === focused)?.focus()
  }
  draw()

  const box = h('div', { class: 'graph' + (orbit ? ' orbit' : '') }, svg,
    orbit ? h('div', { class: 'ghelp', 'aria-hidden': 'true' }, '끌어서 돌리기') : null,
    inner.length ? h('div', { class: 'gnote' }, `건수가 많은 ${RING}개만 이름을 붙였습니다. 안쪽 점 ${inner.length}개는 올리거나 누르면 이름이 보입니다.`) : null)
  if (!orbit) return box
  let start = null, raf = 0
  const turn = (yaw, pitch) => {
    cam.yaw = yaw; cam.pitch = Math.min(PITCH[1], Math.max(PITCH[0], pitch))
    cancelAnimationFrame(raf); raf = requestAnimationFrame(draw)
  }
  svg.addEventListener('pointerdown', ev => { if (ev.button === 0) { start = { x: ev.clientX, y: ev.clientY, yaw: cam.yaw, pitch: cam.pitch }; dragged = false } })
  svg.addEventListener('pointermove', ev => {
    if (!start) return
    const dx = ev.clientX - start.x, dy = ev.clientY - start.y
    if (!dragged && Math.hypot(dx, dy) < 5) return
    if (!dragged) { dragged = true; box.classList.add('drag'); try { svg.setPointerCapture(ev.pointerId) } catch (e) {} }
    turn(start.yaw + dx * 0.008, start.pitch - dy * 0.006)
  })
  const end = () => {
    if (!start) return
    start = null; box.classList.remove('drag')
    if (dragged) { store.set('flowCam', cam); setTimeout(() => { dragged = false }, 0) }   // the click after a drag is swallowed
  }
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end)
  svg.addEventListener('keydown', ev => {
    const step = { ArrowLeft: [-0.2, 0], ArrowRight: [0.2, 0], ArrowUp: [0, 0.12], ArrowDown: [0, -0.12] }[ev.key]
    if (!step) return
    ev.preventDefault(); turn(cam.yaw + step[0], cam.pitch + step[1]); store.set('flowCam', cam)
  })
  return box
}

function msgEl(m) {
  const open = openMsgs.has(m.id)
  return h('article', { class: 'fmsg' },
    h('div', { class: 'r1' }, h('span', { class: 'kb ' + m.kind }, KIND_LABEL[m.kind] || '기타'),
      h('b', {}, m.from), h('span', { class: 'arrow' }, icon('to', '에서 받는 쪽')), h('b', {}, m.to),
      h('time', { title: clock(m.t) + (m.src === 'recv' ? ', 받은 쪽 기록' : '') }, short(m.t))),
    h('div', { class: 'fsum' }, m.sum || '(내용 없음)'),
    h('button', {
      class: 'more', 'aria-expanded': String(open),
      onclick() { open ? openMsgs.delete(m.id) : openMsgs.add(m.id); renderFlowTab() }
    }, open ? '본문 접기' : '본문 펼치기'),
    open ? h('div', { class: 'txt' }, m.text) : null)
}

function renderFlowTab() {
  const scroll = view.querySelector('.scroll.flow') || h('div', { class: 'scroll flow' })
  if (!scroll.isConnected) put(view, scroll)
  const f = flow, sel = flowSel
  const list = f?.messages ? f.messages.filter(m => related(m, sel)) : []
  const seg = h('div', { class: 'seg flat', role: 'group', 'aria-label': '시간 범위' }, WINDOWS.map(([hrs, label]) => h('button', {
    class: 'segb', 'aria-pressed': String(flowHours === hrs),
    onclick() {
      if (flowHours === hrs) return
      flowHours = hrs; flow = null; flowKey = ''
      try { localStorage.setItem('flowHours', String(hrs)) } catch (e) {}
      renderFlowTab(); pollMessages()
    }
  }, label)))
  const viewSeg = h('div', { class: 'seg flat vseg', role: 'group', 'aria-label': '그래프 보기' }, [['orbit', '입체'], ['flat', '평면']].map(([v, label]) => h('button', {
    class: 'segb', 'aria-pressed': String(flowView === v),
    onclick() { if (flowView !== v) { flowView = v; store.set('flowView', v); renderFlowTab() } }
  }, label)))
  // a graph that fails in 3D falls back to the flat drawing, and a flat failure leaves the list below it intact
  const graph = () => {
    const W = scroll.clientWidth - 34
    try { return graphBox(f, W) } catch (e) {}
    try { flowView = 'flat'; return graphBox(f, W) } catch (e) { return h('div', { class: 'banner' }, '그래프를 그리지 못했습니다: ' + e.message) }
  }
  put(scroll,
    h('div', { class: 'fhead' }, seg, f?.nodes ? h('span', { class: 'hint' }, `메시지 ${f.total}건, 세션 ${f.nodes.length}개`) : null, f?.total ? viewSeg : null),
    !f ? h('div', { class: 'empty' }, '불러오는 중…')
      : f.error ? h('div', { class: 'banner' }, '메시지를 읽지 못했습니다: ' + f.error)
      : !f.total ? h('div', { class: 'empty' }, '이 시간 안에 세션끼리 주고받은 메시지가 없습니다.')
      : [graph(),
        sel ? h('div', { class: 'fsel' },
          sel.node ? [h('b', {}, sel.node), ' 이 보내거나 받은 메시지'] : ['보낸 쪽 ', h('b', {}, sel.edge[0]), ', 받는 쪽 ', h('b', {}, sel.edge[1]), ' 메시지'],
          h('button', { onclick: () => select(null) }, '전체 보기')) : null,
        put(tokBox, tokenBars()) || tokBox,
        h('section', { class: 'sec' },
          h('div', { class: 'sec-h' }, h('h2', {}, '메시지'), h('span', { class: 'num' }, list.length),
            f.total > f.messages.length ? h('span', { class: 'hint' }, `최근 ${f.messages.length}건만 목록에 보입니다`) : null),
          list.length ? list.map(msgEl) : h('div', { class: 'sec-empty' }, '없음'))])
}

let tokAll = false
const TOK_TOP = 5   // bars shown before 더 보기, so the message list stays near the graph
const tokBox = h('div')   // redrawn on its own when the agent list refreshes
function tokenBars() {
  const rows = withTokens()
  if (!rows.length) return null
  const max = rows[0].tokens.total || 1, dup = n => rows.filter(a => a.name === n).length > 1
  const shown = tokAll ? rows : rows.slice(0, TOK_TOP)
  return h('section', { class: 'sec' },
    h('div', { class: 'sec-h' }, h('h2', {}, '세션별 처리 토큰'), h('span', { class: 'num' }, rows.length)),
    h('div', { class: 'tleg' }, h('span', { class: 'def' }, TOK_DEF + '. Claude 는 서브에이전트 기록까지 더합니다.'),
      h('span', { class: 'claude' }, 'Claude'), h('span', { class: 'codex' }, 'codex')),
    h('div', { class: 'toks' }, shown.map(a => h('div', { class: 'tok ' + a.tokens.engine, title: tokTip(a.tokens) },
      h('span', { class: 'tn' }, a.name || a.sessionId.slice(0, 8), dup(a.name) ? h('small', {}, a.sessionId.slice(0, 8)) : null),
      h('span', { class: 'tb', 'aria-hidden': 'true' }, h('i', { style: `width:${(100 * a.tokens.total / max).toFixed(2)}%` })),
      h('b', { class: 'num' }, tok(a.tokens.total))))),
    rows.length > TOK_TOP ? h('button', { class: 'more', onclick() { tokAll = !tokAll; put(tokBox, tokenBars()) } }, tokAll ? '접기' : `${rows.length - TOK_TOP}개 더 보기`) : null)
}

// every 5 s on the flow tab; elsewhere every 15 s, only for the report count and alerts
let msgAt = 0
async function pollMessages() {
  const onFlow = !cur && page === 'flow' && !document.hidden
  if (!onFlow && Date.now() - msgAt < 15000) return
  const hours = onFlow ? flowHours : 24
  msgAt = Date.now()
  try {
    const r = await fetch('/api/messages?hours=' + hours)
    const text = await r.text()
    if (!r.ok) throw new Error(r.status)
    if (text === flowKey) return   // nothing new
    const d = JSON.parse(text)
    checkReports(d)
    if (hours === 24) {
      msgs24 = d
      if (!cur && page === 'agents' && agentView === 'canvas') view.querySelector('.canvas')?.drawLinks?.()
      if (hero?.ok) try { officeMessages() } catch (e) {}   // a sheet per new [배정] or [보고]
    }
    if (hours !== flowHours) return   // a background read, or the window changed meanwhile
    flowKey = text; flow = d
  } catch (err) { if (!flow && onFlow) flow = { error: err.message } }
  if (!cur && page === 'flow') renderFlowTab()
}
