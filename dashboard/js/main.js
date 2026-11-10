'use strict'
// routing and polling; loaded last

/* ---------- routing & polling ---------- */
function route() {
  const m = location.hash.match(/^#\/s\/([\w-]+)(\/logs)?/)
  if (m) return showDetail(m[1], m[2] ? 'logs' : 'chat')
  cur = null
  page = { '#/decisions': 'decisions', '#/status': 'status', '#/flow': 'flow', '#/todo': 'todo' }[location.hash] || 'agents'
  renderTop(); renderPage()
}
function renderPage() {
  if (page === 'decisions') renderDecisions()
  else if (page === 'status') { renderStatus(); pollStatus() }
  else if (page === 'flow') { renderFlowTab(); pollMessages() }
  else if (page === 'todo') renderTodo()
  else renderList()
}

async function pollAgents() {
  try { agents = (await getJSON('/api/agents')).agents; error = ''; checkBlocked(); renderUsage() }   // usage bar carries the token total
  catch (err) { error = err.message }
  if (cur) { cur.agent = agents.find(a => a.sessionId === cur.sid); renderTop(); renderDetailHead() }
  else { renderTop(); if (page === 'agents') renderList(); else if (page === 'flow') put(tokBox, tokenBars()) }
}

window.addEventListener('hashchange', route)
document.addEventListener('visibilitychange', () => { seen(); pollMessages(); if (hero?.ok) heroLoop() })
window.addEventListener('resize', () => { if (cur?.term) fitTerm(cur); else if (!cur && page === 'flow' && flow) renderFlowTab() })
Promise.all([pollAgents(), pollDecisions(), pollTodo()]).then(() => { route(); pollMessages() })
pollUsage(); pollDev()
setInterval(pollAgents, 3000)
setInterval(pollDecisions, 3000)
setInterval(pollTodo, 3000)
setInterval(pollUsage, 3000)
setInterval(pollDev, 3000)
setInterval(pollStatus, 5000)
setInterval(pollMessages, 5000)
setInterval(pollTranscript, 2000)
setInterval(pollLogs, 3000)
