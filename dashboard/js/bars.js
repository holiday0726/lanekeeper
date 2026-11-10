'use strict'
// usage bar and dev occupancy line

/* ---------- usage bar ---------- */
const usageBar = document.getElementById('usage')
const winName = w => ({ 300: '5시간', 10080: '주간' })[w.minutes] || (w.minutes ? (w.minutes % 60 ? w.minutes + '분' : w.minutes / 60 + '시간') : w.key)
const until = ms => { const t = span(2 * Date.now() - ms); return t === '방금' ? '곧' : t + ' 뒤' }   // span() counts back; mirror it
let usage = null

// a ring per window: the orange arc is what has been used; beside it the used share, then what is left and the reset a step fainter
const RC = 2 * Math.PI * 15
const ring = used => sv('svg', { class: 'ring', viewBox: '0 0 36 36', width: 30, height: 30, 'aria-hidden': 'true' },
  sv('circle', { class: 'rt', cx: 18, cy: 18, r: 15 }),
  used > 0 ? sv('circle', { class: 'rv', cx: 18, cy: 18, r: 15, 'stroke-dasharray': `${(used / 100 * RC).toFixed(1)} ${RC.toFixed(1)}`, transform: 'rotate(-90 18 18)' }) : null)
function renderUsage() {
  put(usageBar, [['claude', 'Claude'], ['codex', 'Codex']].map(([k, label]) => {
    const e = usage?.[k]
    if (!e) return null
    if (e.state === 'missing') return h('div', { class: 'use missing' }, h('span', { class: 'ul' }, label), h('span', { class: 'wn' }, '기록 없음'))
    if (e.state === 'broken') return h('div', { class: 'use broken', title: e.error }, h('span', { class: 'ul' }, label), h('span', { class: 'wn' }, '읽지 못함'))
    return h('div', { class: 'use ' + e.state, title: `기록 ${clock(e.at)}` + (e.plan ? `, ${e.plan}` : '') },
      h('span', { class: 'ul' }, label, h('span', { class: 'ago num' }, e.state === 'stale' ? '갱신 안 됨, ' + ago(e.at) : '갱신 ' + ago(e.at))),
      h('div', { class: 'wins' }, e.windows.map(w => {
        const used = Math.min(100, Math.max(0, Math.round(w.used))), left = 100 - used
        if (w.reset) return h('span', { class: 'win', title: '리셋 시각이 지나 남은 양을 모름' }, ring(0), h('span', { class: 'wt' }, h('b', {}, '리셋됨'), h('span', { class: 'wn' }, winName(w))))
        return h('span', { class: 'win', title: w.resets ? '리셋 ' + clock(w.resets) : null },
          ring(used),
          h('span', { class: 'wt' }, h('b', { class: 'num' }, used + '%'), h('span', { class: 'wn' }, `${winName(w)} 사용, 남은 ${left}%` + (w.resets ? ', ' + until(w.resets) : ''))))
      })))
  }), tokTotal())
}
// every listed session summed; the split by engine and the left out cache reads are in the tooltip
function tokTotal() {
  const rows = withTokens()
  if (!rows.length) return null
  const by = {}
  let read = 0
  for (const a of rows) { by[a.tokens.engine] = (by[a.tokens.engine] || 0) + a.tokens.total; read += a.tokens.cacheRead || 0 }
  const sum = Object.values(by).reduce((x, y) => x + y, 0)
  return h('div', { class: 'use', title: `${TOK_DEF}. 목록의 세션 ${rows.length}개 합. ` + Object.entries(by).map(([k, v]) => `${ENGINE[k] || k} ${tok(v)}`).join(', ') + `. 넣지 않은 캐시 읽기 ${tok(read)}` },
    h('span', { class: 'ul' }, '처리 토큰'),
    h('div', { class: 'wins' }, h('span', { class: 'win' }, h('span', { class: 'wt' }, h('b', { class: 'num' }, tok(sum)), h('span', { class: 'wn' }, `목록의 세션 ${rows.length}개 합계`)))))
}

async function pollUsage() {
  try { usage = await getJSON('/api/usage') } catch (err) {}   // keep the last reading; its age keeps growing
  renderUsage()
}

/* ---------- dev occupancy ---------- */
const devBar = document.getElementById('dev')
const DEV_KIND = { run: '', restart: '재기동 예정', deploy: '배포' }
let dev = null, devOpen = store.get('devOpen', false)
const elapsed = ms => !ms ? '' : ms > Date.now() ? until(ms) : span(ms) === '방금' ? '방금' : span(ms) + '째'
function devItem(i) {
  const kind = DEV_KIND[i.kind] ?? i.kind
  return h('div', {
    class: 'devi ' + (i.kind || ''),
    title: [kind || '실행', i.sinceAt ? '시작 ' + clock(i.sinceAt) : i.since, i.until ? '끝 ' + (i.untilAt ? clock(i.untilAt) : i.until) : '', i.note].filter(Boolean).join(', ')
  }, h('span', { class: 'dk' }, 'dev'), kind ? h('span', { class: 'kd' }, kind) : null, h('b', {}, i.who || '?'), h('span', { class: 'dw' }, i.what), h('span', { class: 'num' }, elapsed(i.sinceAt)))
}
// a missing or broken file hides the line; the reason stays in /api/dev and the hidden line's title
function renderDev() {
  const d = dev
  devBar.hidden = !d || d.state === 'missing' || d.state === 'broken'
  devBar.title = d?.error ? 'dev-occupancy.json: ' + d.error : ''
  if (!cur && page === 'status') renderStatus()   // the reason for a hidden line shows in the status header
  if (devBar.hidden) return put(devBar)
  const items = d.items, many = items.length > 1
  devBar.className = d.state
  put(devBar,
    h('div', { class: 'devl' }, items.length ? (devOpen ? items : items.slice(0, 1)).map(devItem) : h('div', { class: 'devi' }, h('span', { class: 'dk' }, 'dev'), '쓰는 세션 없음')),
    many ? h('button', {
      class: 'more', 'aria-expanded': String(devOpen),
      onclick() { devOpen = !devOpen; store.set('devOpen', devOpen); renderDev() }
    }, devOpen ? '접기' : `${items.length}건 펼치기`) : null,
    d.state === 'stale' ? h('span', { class: 'ago', title: d.updatedAt ? '갱신 ' + clock(d.updatedAt) : 'updated_at 없음' }, d.updatedAt ? '갱신 ' + ago(d.updatedAt) : '갱신 시각 없음') : null)
}
async function pollDev() {
  try { dev = await getJSON('/api/dev') } catch (err) {}   // keep the last answer
  renderDev()
}
