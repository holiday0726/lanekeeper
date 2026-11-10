'use strict'
// decisions tab

/* ---------- decisions ---------- */
let dec = null, decKey = ''
const openDetails = new Set()
let decidedOpen = false
try { decidedOpen = localStorage.getItem('decidedOpen') === '1' } catch (e) {}
const today = () => { const d = new Date(), p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` }
const when = s => {   // 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD'
  if (s && s.startsWith(today()) && s.length > 10) return s.slice(11)
  const m = (s || '').match(/^\d{4}-(\d\d)-(\d\d)(?: (\d\d:\d\d))?/)
  return m ? `${+m[1]}월 ${+m[2]}일${m[3] ? ' ' + m[3] : ''}` : (s || '')
}

async function copyText(btn, text) {
  try { await navigator.clipboard.writeText(text); btn.dataset.done = '1' }
  catch (e) { const r = document.createRange(); r.selectNodeContents(btn); getSelection().removeAllRanges(); getSelection().addRange(r) }
}
// URLs open in a new tab; anything else is a path or note, and clicking copies it
const refEl = r => /^https?:\/\//.test(r)
  ? h('a', { class: 'ref', href: r, target: '_blank', rel: 'noopener noreferrer', title: '새 탭에서 열기' }, r, h('span', { class: 'ic' }, icon('ext')))
  : h('button', {
    class: 'ref', title: '눌러서 복사',
    onclick(ev) {
      const b = ev.currentTarget, ic = b.querySelector('.ic')
      copyText(b, r).then(() => { ic.textContent = b.dataset.done ? '복사됨' : 'Ctrl+C'; setTimeout(() => { ic.textContent = '복사' }, 1500) })
    }
  }, r, h('span', { class: 'ic' }, '복사'))

// a decision reads top down: its state and dates as chips, the question as one large line, who raised it,
// then the detail at a reading measure and the options as a numbered list; open ones show their detail unfolded
const DEC_STATE = { now: '열림', waiting: '미룸', decided: '정해짐' }
const closedDetails = new Set()
function decCard(d, sec) {
  const w = d.who || {}
  const key = d.id || 'live:' + d.sid
  const open = sec === 'now' ? !closedDetails.has(key) : openDetails.has(key)
  return h('article', { class: `dcard ${sec}${d.live ? ' live' : ''}` },
    h('div', { class: 'dchips' },
      h('span', { class: 'dstate ' + (d.live ? 'live' : sec), title: d.live ? '이 세션이 지금 입력을 기다리며 묻고 있습니다' : null }, d.live ? '세션이 지금 묻는 중' : DEC_STATE[sec] || d.status || ''),
      d.live ? h('span', { class: 'dchip' }, '활동 ', h('b', {}, ago(d.at)), hm(d.at)) : d.raised ? h('span', { class: 'dchip' }, '올라옴 ', h('b', {}, when(d.raised))) : null,
      d.until ? h('span', { class: 'dchip' }, '미룸 ', h('b', {}, d.until)) : null,
      d.decided_at ? h('span', { class: 'dchip' }, '결정 ', h('b', {}, when(d.decided_at))) : null,
      d.id ? h('span', { class: 'did mono' }, d.id) : null),
    h('h3', { class: 'dq' }, d.title || d.id || '(제목 없음)'),
    d.source || d.task ? h('div', { class: 'dsrc' },
      d.source ? [h('b', {}, d.source), badge(w), w.closed ? h('span', { title: '목록에도 agents.json 에도 없어 닫힌 일회성 세션으로 봅니다' }, '닫힘') : null] : null,
      d.task ? h('span', { class: 'mono' }, d.task) : null) : null,
    d.detail ? h('details', {
      class: 'dmore', open,
      ontoggle(ev) {
        const o = ev.currentTarget.open
        if (sec === 'now') o ? closedDetails.delete(key) : closedDetails.add(key)
        else o ? openDetails.add(key) : openDetails.delete(key)
      }
    }, h('summary', {}, '자세히'), h('p', { class: 'dtext' }, d.detail)) : null,
    d.options?.length ? h('ol', { class: 'opts' }, d.options.map(o => h('li', {}, h('span', {}, o)))) : null,
    d.decision ? h('div', { class: 'decision' }, h('b', {}, '결정'), h('span', {}, d.decision)) : null,
    d.refs?.length ? h('div', { class: 'refs' }, d.refs.map(refEl)) : null,
    d.live ? h('a', { class: 'golink', href: '#/s/' + d.sid }, '세션 대화 보기') : null)
}

function renderDecisions() {
  const scroll = view.querySelector('.scroll.decisions') || h('div', { class: 'scroll decisions' })
  const d = dec || {}
  const asking = (d.now || []).filter(x => x.live).length
  put(scroll,
    !dec ? h('div', { class: 'empty' }, '불러오는 중…') : null,
    d.error ? h('div', { class: 'banner' }, `decisions.json 을 읽지 못했습니다(${d.error}). 떠 있는 세션의 질문만 보입니다.`) : null,
    dec ? [['now', '지금 결정 필요'], ['waiting', '미뤄 둔 것'], ['decided', '결정됨']].map(([key, title]) => {
      const list = d[key] || []
      const fold = key === 'decided', open = !fold || decidedOpen
      const head = [h('h2', {}, title), h('span', { class: 'num' }, list.length),
        key === 'now' && asking ? h('span', { class: 'hint' }, `세션이 묻는 중 ${asking}`) : null,
        fold ? h('span', { class: 'chev', 'aria-hidden': 'true' }, open ? '접기' : '펼치기') : null]
      return h('section', { class: 'sec', 'data-sec': key },
        fold ? h('button', {
          class: 'sec-h', 'aria-expanded': String(open),
          onclick() { decidedOpen = !decidedOpen; try { localStorage.setItem('decidedOpen', decidedOpen ? '1' : '0') } catch (e) {} renderDecisions() }
        }, head) : h('div', { class: 'sec-h' }, head),
        open ? (list.length ? list.map(x => decCard(x, key)) : h('div', { class: 'sec-empty' }, '없음')) : null)
    }) : null)
  if (!scroll.isConnected) put(view, scroll)
}

async function pollDecisions() {
  try {
    const r = await fetch('/api/decisions')
    const text = await r.text()
    if (!r.ok) throw new Error(r.status)
    if (text === decKey) return   // unchanged: keep open details and scroll as they are
    decKey = text; dec = JSON.parse(text)
  } catch (err) { if (!dec) dec = { now: [], waiting: [], decided: [], error: '서버 응답 없음: ' + err.message } }
  if (!cur) { renderTop(); if (page === 'decisions') renderDecisions() }
}
