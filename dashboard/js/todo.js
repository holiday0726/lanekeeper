'use strict'
// todo tab

/* ---------- todo: sessions' task lists (~/.claude/tasks) ---------- */
let todo = null, todoKey = '', todoStale = store.get('todoStale', false)
const todoOpen = new Set(), todoDone = new Set(store.get('todoDone', []))   // open items (this page), sessions showing 끝남
const TODO_LABEL = { in_progress: '진행 중', pending: '대기', completed: '끝남' }

// one row per item: a mark whose shape is the state (filled, hollow, ticked), the subject, its #id, and what it is doing now
function todoItem(g, t) {
  const key = g.sid + '/' + t.id
  const head = [h('span', { class: 'tmark', role: 'img', 'aria-label': TODO_LABEL[t.status] || t.status || '상태 없음' }, t.status === 'completed' ? icon('check') : null),
    h('span', { class: 'tsub' }, h('span', { class: 'tsj' }, t.subject || '(제목 없음)'), t.status === 'in_progress' && t.activeForm ? h('span', { class: 'tact' }, t.activeForm) : null),
    t.id ? h('span', { class: 'tid mono' }, '#' + t.id) : null]
  const body = [t.description ? h('p', { class: 'dtext' }, t.description) : null,
    t.owner ? h('div', {}, '맡은 세션 ', h('b', {}, t.owner)) : null,
    t.blockedBy.length ? h('div', {}, '막는 일 ', h('b', {}, t.blockedBy.map(x => '#' + x).join(', '))) : null].filter(Boolean)
  if (!body.length) return h('div', { class: 'ti ' + t.status }, h('div', { class: 'tsum' }, head))
  return h('details', {
    class: 'ti ' + t.status, open: todoOpen.has(key),
    ontoggle(ev) { ev.currentTarget.open ? todoOpen.add(key) : todoOpen.delete(key) }
  }, h('summary', {}, head), h('div', { class: 'tnote' }, body))
}

function todoGroup(g) {
  const s = g.closed ? { key: 'done', label: '닫힘' } : status(g)
  const n = k => g.items.filter(t => t.status === k).length
  const done = g.items.filter(t => t.status === 'completed'), open = todoDone.has(g.sid)
  return h('article', { class: `tcard ${s.key} g-${g.group || 'other'}${g.closed ? ' closed' : ''}` },
    h('div', { class: 'r1' },
      g.closed ? h('span', { class: 'name', title: '목록에 없는 세션 ' + g.sid }, g.name) : h('a', { class: 'name', href: '#/s/' + g.sid }, g.name),
      badge(g), stateEl(s)),
    h('div', { class: 'dchips' },
      h('span', { class: 'dchip' }, '수정 ', h('b', {}, ago(g.at)), hm(g.at)),
      ['in_progress', 'pending', 'completed'].map(k => n(k) ? h('span', { class: 'dchip' }, TODO_LABEL[k] + ' ', h('b', {}, n(k))) : null)),
    h('div', { class: 'tlist' }, g.items.filter(t => t.status !== 'completed').map(t => todoItem(g, t)),
      done.length ? h('button', {
        class: 'more tfold', 'aria-expanded': String(open),
        onclick() { open ? todoDone.delete(g.sid) : todoDone.add(g.sid); store.set('todoDone', [...todoDone]); renderTodo() }
      }, `끝남 ${done.length} ${open ? '접기' : '펼치기'}`) : null,
      open ? done.map(t => todoItem(g, t)) : null))
}

// the server already sorts: newest changed session first; in progress, pending, completed inside each
function renderTodo() {
  const scroll = view.querySelector('.scroll.todo-page') || h('div', { class: 'scroll todo-page' })
  const gs = todo?.groups || [], old = gs.filter(g => g.stale), shown = gs.filter(g => todoStale || !g.stale)
  put(scroll,
    h('div', { class: 'mdhead' }, h('span', { class: 'mono' }, '~/.claude/tasks'), h('span', {}, '3초마다 다시 읽음, 읽기만 함')),
    !todo ? h('div', { class: 'empty' }, '불러오는 중…') : null,
    todo?.error ? h('div', { class: 'banner' }, `할 일을 읽지 못했습니다(${todo.error}).`) : null,
    todo && !todo.error && !shown.length ? h('div', { class: 'empty' }, gs.length ? '최근 7일 안에 바뀐 할 일이 없습니다.' : '할 일 목록이 있는 세션이 없습니다.') : null,
    shown.map(todoGroup),
    old.length ? h('button', {
      class: 'more', 'aria-expanded': String(todoStale),
      onclick() { todoStale = !todoStale; store.set('todoStale', todoStale); renderTodo() }
    }, `7일 넘게 안 바뀐 세션 ${old.length}개 ${todoStale ? '숨기기' : '보기'}`) : null)
  if (!scroll.isConnected) put(view, scroll)
}

async function pollTodo() {
  try {
    const r = await fetch('/api/todos')
    const text = await r.text()
    if (!r.ok) throw new Error(r.status)
    if (text === todoKey) return   // unchanged: keep open items and scroll as they are
    todoKey = text; todo = JSON.parse(text)
  } catch (err) { if (!todo) todo = { groups: [], counts: {}, error: '서버 응답 없음: ' + err.message } }
  if (!cur) { renderTop(); if (page === 'todo') renderTodo() }
}
