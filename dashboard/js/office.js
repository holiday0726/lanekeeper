'use strict'
// 3D office, loaded only when it is turned on (agents.js loadOffice); `hero` itself is declared in agents.js

/* office: the sessions as low-poly figures in an isometric room (three.js r128, vendored).
   The hub sits at its own desk; a session at work sits at its desk with a typing bubble and a lit screen, a waiting
   one shows an orange "!" and a blinking screen, one at rest or finished sits in the lounge. A new [배정] from the hub
   flies a sheet from the hub to that desk, a [보고] flies one back. Drag turns the room. It pauses on hover or focus;
   under reduced motion nothing walks or flies; without WebGL the list beside it stays. #/demo adds buttons that
   override a session's scene locally, for trying the scenes; nothing is sent anywhere. */
const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches
const demoOn = () => location.hash === '#/demo'
const sceneOverride = new Map()   // #/demo only: sessionId -> 'working' | 'waiting' | 'rest'
const sceneOf = a => sceneOverride.get(a.sessionId) || { busy: 'working', blocked: 'waiting' }[status(a).key] || 'rest'
const SCENE_LABEL = { working: '작업 중', waiting: '대기 중', rest: '쉬는 중' }

function heroBox() {
  if (hero) return hero.box
  const labels = h('div', { class: 'hlabels' })
  const stage = h('div', { class: 'hstage' }, labels)
  const info = h('div', { class: 'hinfo' })
  const box = h('section', { class: 'hero', 'aria-label': '세션 오피스' }, stage, info)
  hero = { box, stage, labels, info, ok: false, figs: new Map(), raf: 0, paused: false, last: 0, mark: null, o: null }
  const hold = v => () => { hero.paused = v; heroLoop() }
  box.addEventListener('mouseenter', hold(true)); box.addEventListener('mouseleave', hold(false))
  box.addEventListener('focusin', hold(true)); box.addEventListener('focusout', hold(false))
  try { officeInit(); hero.ok = true } catch (e) { box.classList.add('flat') }   // no THREE or no WebGL: the list alone
  return box
}

function officeInit() {
  if (typeof THREE === 'undefined' || !THREE.OrbitControls) throw new Error('three.js not loaded')
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2))
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap
  hero.stage.prepend(renderer.domElement)
  const scene = new THREE.Scene()
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 200)
  camera.position.set(16, 15, 16); camera.lookAt(0, 0, 0)
  const controls = new THREE.OrbitControls(camera, renderer.domElement)
  Object.assign(controls, { enableDamping: !calm(), enablePan: false, enableZoom: false, minPolarAngle: Math.PI * 0.12, maxPolarAngle: Math.PI * 0.42 })
  controls.addEventListener('change', () => { if (!hero.raf) officeRender() })
  controls.addEventListener('end', () => officeResize())
  const hemi = new THREE.HemisphereLight(0xffffff, 0x808080, 0.7); scene.add(hemi)
  const sun = new THREE.DirectionalLight(0xffffff, 0.7)
  sun.position.set(-6, 16, 10); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0006
  scene.add(sun, sun.target)
  const std = () => new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.85, metalness: 0 })
  const M = { floor: std(), wall: std(), rug: std(), desk: std(), leg: std(), sofa: std(), seat: std(), hubSeat: std(), plant: std(), pot: std(), bean: std(), body: std(), skull: std(), hubTile: std(),
    dark: new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.55 }) }
  hero.o = { renderer, scene, camera, controls, hemi, sun, M, room: null, rows: -1, desks: [], hub: null, lounge: [], packets: [], tex: {}, v: new THREE.Vector3(), down: null }
  officeColors()
  new MutationObserver(() => { officeColors(); officeRender() }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  new ResizeObserver(officeResize).observe(hero.stage)
  // a click (not a drag) on a figure or its desk opens that session
  const el = renderer.domElement, ray = new THREE.Raycaster(), ptr = new THREE.Vector2()
  el.addEventListener('pointerdown', e => { hero.o.down = [e.clientX, e.clientY] })
  el.addEventListener('pointerup', e => {
    const d = hero.o.down; hero.o.down = null
    if (!d || Math.hypot(e.clientX - d[0], e.clientY - d[1]) > 5) return
    const r = el.getBoundingClientRect()
    ptr.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1)
    ray.setFromCamera(ptr, camera)
    const hit = ray.intersectObjects([...hero.figs.values()].map(f => f.g), true)[0]
    if (hit) { let o = hit.object; while (o && !o.userData.sid) o = o.parent; if (o) location.hash = '#/s/' + o.userData.sid }
  })
}

function officeColors() {
  const o = hero.o, c = k => new THREE.Color(tokenRGB(k)), light = document.documentElement.dataset.theme === 'light'
  const set = { floor: light ? '--color-paper-3' : '--color-paper-3', wall: light ? '--color-side' : '--color-paper-2', rug: '--color-paper-3', desk: light ? '--color-paper' : '--color-rule-2', leg: '--color-rule',
    sofa: light ? '--color-rule-2' : '--color-paper-3', seat: '--color-rule-2', hubSeat: '--color-accent', plant: '--color-muted', pot: '--color-rule-2', bean: '--color-accent',
    body: light ? '--color-rule-2' : '--color-muted', skull: light ? '--color-paper-2' : '--color-ink', hubTile: '--color-paper-3', dark: light ? '--color-ink-2' : '--color-side' }
  for (const [k, v] of Object.entries(set)) o.M[k].color.copy(c(v))
  o.hemi.intensity = light ? 0.55 : 0.95; o.sun.intensity = light ? 0.6 : 0.85
  o.col = { working: tokenRGB('--color-live'), waiting: tokenRGB('--color-accent'), rest: tokenRGB('--color-faint'), ink: tokenRGB('--color-ink'), paper: tokenRGB('--color-paper-2'), side: tokenRGB('--color-side') }
  officeTextures()
  for (const f of hero.figs.values()) f.ringMat.color.set(o.col[f.state] || o.col.rest)
}

function officeTextures() {
  const o = hero.o, col = o.col, font = getComputedStyle(document.body).fontFamily
  for (const t of Object.values(o.tex).flat()) t?.dispose?.()
  const tex = draw => { const c = document.createElement('canvas'); c.width = c.height = 128; draw(c.getContext('2d')); return new THREE.CanvasTexture(c) }
  const pill = (x, X, Y, W, H, R) => { x.beginPath(); x.moveTo(X + R, Y); x.arcTo(X + W, Y, X + W, Y + H, R); x.arcTo(X + W, Y + H, X, Y + H, R); x.arcTo(X, Y + H, X, Y, R); x.arcTo(X, Y, X + W, Y, R); x.closePath() }
  o.tex.zzz = tex(x => { x.fillStyle = col.rest; [['z', 34, 98, 30], ['z', 62, 70, 38], ['Z', 88, 40, 46]].forEach(([s, X, Y, size]) => { x.font = `800 ${size}px ${font}`; x.fillText(s, X, Y) }) })
  o.tex.bang = tex(x => {
    x.fillStyle = col.waiting; x.beginPath(); x.arc(64, 60, 40, 0, Math.PI * 2); x.fill()
    x.beginPath(); x.moveTo(54, 96); x.lineTo(64, 118); x.lineTo(74, 96); x.fill()
    x.fillStyle = col.side; x.font = `900 60px ${font}`; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText('!', 64, 62)
  })
  o.tex.dots = [0, 1, 2].map(i => tex(x => {
    x.fillStyle = col.ink; pill(x, 14, 30, 100, 56, 22); x.fill()
    x.beginPath(); x.moveTo(52, 86); x.lineTo(60, 104); x.lineTo(70, 86); x.fill()
    ;[0, 1, 2].forEach(k => { x.fillStyle = k === i ? col.side : col.rest; x.beginPath(); x.arc(42 + k * 22, 58, 8, 0, Math.PI * 2); x.fill() })
  }))
  for (const f of hero.figs.values()) f.sprite.material.map = null
}

// the room grows by a row of three desks for every three sessions past six; the lounge and the camera follow it
function officeLayout(n) {
  const o = hero.o, rows = Math.max(2, Math.ceil(n / 3))
  if (rows === o.rows) return false
  if (o.room) { o.scene.remove(o.room); o.room.traverse(m => m.geometry?.dispose?.()) }
  const g = new THREE.Group(); o.scene.add(g); o.room = g; o.rows = rows
  const box = (w, hh, d, mat, x, y, z, parent = g, shadow = true) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, hh, d), mat); m.position.set(x, y, z); m.castShadow = shadow; m.receiveShadow = true; parent.add(m); return m
  }
  const deskBottom = -5 + (rows - 1) * 3.2, loungeZ = deskBottom + 4.8, front = loungeZ + 4.5, depth = front + 7.6, cz = (front - 7.6) / 2
  o.geo = { deskBottom, loungeZ, corridor: deskBottom + 2.8, entry: loungeZ + 0.9, cz, depth }
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(22, depth), o.M.floor)
  floor.rotation.x = -Math.PI / 2; floor.position.z = cz; floor.receiveShadow = true; g.add(floor)
  box(22, 2.4, 0.2, o.M.wall, 0, 1.2, -7.6, g, false)
  box(0.2, 2.4, depth + 0.2, o.M.wall, -11.1, 1.2, cz, g, false)
  box(3.2, 1.2, 0.05, o.M.desk, -2.5, 1.45, -7.47, g, false)
  const plant = (x, z) => {
    box(0.5, 0.5, 0.5, o.M.pot, x, 0.25, z)
    const leaves = new THREE.Mesh(new THREE.IcosahedronGeometry(0.48, 0), o.M.plant); leaves.position.set(x, 0.9, z); leaves.castShadow = true; g.add(leaves)
  }
  plant(-10.3, -6.8); plant(10.2, -6.8); plant(10.2, front - 0.9); plant(-10.3, front - 0.9)
  const desk = (x, z, wide) => {
    const d = new THREE.Group(); d.position.set(x, 0, z); g.add(d)
    const w = wide ? 2.6 : 1.7
    box(w, 0.08, 0.9, o.M.desk, 0, 0.76, 0, d)
    ;[[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz]) => box(0.06, 0.72, 0.06, o.M.leg, sx * (w / 2 - 0.08), 0.36, sz * 0.36, d))
    const screens = (wide ? [-0.58, 0.58] : [0]).map(mx => {
      box(0.08, 0.28, 0.08, o.M.dark, mx, 0.94, -0.24, d); box(0.88, 0.54, 0.06, o.M.dark, mx, 1.32, -0.26, d)
      const sm = new THREE.MeshStandardMaterial({ color: 0x141414, emissive: 0x000000, roughness: 0.35 })
      const s = new THREE.Mesh(new THREE.PlaneGeometry(0.78, 0.44), sm); s.position.set(mx, 1.32, -0.225); d.add(s); return sm
    })
    box(0.52, 0.03, 0.18, o.M.dark, 0, 0.815, 0.12, d)
    const seatMat = wide ? o.M.hubSeat : o.M.seat
    box(0.56, 0.08, 0.52, seatMat, 0, 0.46, 0.86, d); box(0.56, 0.52, 0.08, seatMat, 0, 0.76, 1.12, d); box(0.07, 0.42, 0.07, o.M.dark, 0, 0.21, 0.86, d)
    return { screens, seat: new THREE.Vector3(x, 0, z + 0.82), anchor: new THREE.Vector3(x, 1.4, z - 0.2) }
  }
  const hubZ = deskBottom + 3.0
  o.hubDesk = desk(-7.5, hubZ, true)
  const tile = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 3.4), o.M.hubTile); tile.rotation.x = -Math.PI / 2; tile.position.set(-7.5, 0.008, hubZ + 0.4); g.add(tile)
  o.hubAnchor = new THREE.Vector3(o.hubDesk.seat.x, 1.5, o.hubDesk.seat.z)
  o.desks = []
  for (let r = 0; r < rows; r++) for (const x of [-2.5, 1.5, 5.5]) o.desks.push(desk(x, -5 + r * 3.2, false))
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(7, 4.4), o.M.rug); rug.rotation.x = -Math.PI / 2; rug.position.set(6, 0.01, loungeZ + 1.4); rug.receiveShadow = true; g.add(rug)
  box(3.0, 0.4, 0.9, o.M.sofa, 5.6, 0.2, loungeZ); box(3.0, 0.62, 0.22, o.M.sofa, 5.6, 0.6, loungeZ - 0.42)
  box(0.22, 0.58, 0.9, o.M.sofa, 4.0, 0.29, loungeZ); box(0.22, 0.58, 0.9, o.M.sofa, 7.2, 0.29, loungeZ)
  box(1.6, 0.06, 0.7, o.M.desk, 5.6, 0.42, loungeZ + 1.6)
  const beans = [[3.6, loungeZ + 2.5], [7.7, loungeZ + 2.5], [8.7, loungeZ + 1.1]]
  beans.forEach(([x, z]) => { const b = new THREE.Mesh(new THREE.SphereGeometry(0.5, 12, 8), o.M.bean); b.scale.set(1, 0.5, 1); b.position.set(x, 0.2, z); b.castShadow = b.receiveShadow = true; g.add(b) })
  const seats = [{ x: 4.8, z: loungeZ + 0.1, y: 0.2, rot: 0 }, { x: 5.6, z: loungeZ + 0.1, y: 0.2, rot: 0 }, { x: 6.4, z: loungeZ + 0.1, y: 0.2, rot: 0 },
    ...beans.map(([x, z]) => ({ x, z, y: 0.22, rot: Math.atan2(5.6 - x, loungeZ + 1.6 - z) }))]
  for (let i = 0; seats.length < 40; i++) seats.push({ x: 2.6 + (i % 7) * 1.0, z: loungeZ + 3.4 + Math.floor(i / 7) * 0.9, y: 0, rot: Math.PI * 0.75 })   // standing room past six
  o.lounge = seats.map(s => ({ ...s, taken: null }))
  Object.assign(o.sun.shadow.camera, { left: -15, right: 15, top: depth / 2 + 2, bottom: -depth / 2 - 2, near: 1, far: 60 }); o.sun.shadow.camera.updateProjectionMatrix()
  o.sun.position.set(-6, 16, cz + 10); o.sun.target.position.set(0, 0, cz)
  o.controls.target.set(0, 1.2, cz); o.camera.position.set(16, 16.2, cz + 16); o.controls.update()
  officeResize()
  return true
}

function officeResize() {
  const o = hero.o, w = hero.stage.clientWidth, hh = hero.stage.clientHeight
  if (!o || !w || !hh || !o.geo) return
  o.renderer.setSize(w, hh, false)
  // every corner of the room box (walls, plants, the top of a flying sheet) as the camera sees it now, plus a margin;
  // it runs again when a drag ends, so a turned room is framed again
  const front = o.geo.cz + o.geo.depth / 2, pts = []
  for (const x of [-11.3, 11.1]) for (const y of [0, 3.6]) for (const z of [-7.8, front + 0.2]) pts.push(new THREE.Vector3(x, y, z))
  o.camera.updateMatrixWorld()
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
  for (const p of pts) { const q = p.clone().applyMatrix4(o.camera.matrixWorldInverse); x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x); y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y) }
  // frame the box itself (an off-centre frustum), widened on one axis to the canvas shape, with about 4% to spare
  const asp = w / hh, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2
  let hw = (x1 - x0) / 2, hy = (y1 - y0) / 2
  if (hw / hy > asp) hy = hw / asp; else hw = hy * asp
  hw *= 1.04; hy *= 1.04
  Object.assign(o.camera, { left: cx - hw, right: cx + hw, top: cy + hy, bottom: cy - hy }); o.camera.updateProjectionMatrix()
  officeRender()
}

// a round body, a head nearly as big, stubby arms and feet, two dot eyes: about two heads tall, low poly
function makeFigure(sid, isHub) {
  const o = hero.o, g = new THREE.Group(); g.userData.sid = sid; o.scene.add(g)
  const ball = (r, mat, x, y, z, sx = 1, sy = 1, sz = 1, parent = g) => {
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 1), mat); m.position.set(x, y, z); m.scale.set(sx, sy, sz); m.castShadow = true; parent.add(m); return m
  }
  const body = new THREE.Group(); g.add(body)
  ball(0.36, o.M.body, 0, 0.42, 0, 1.08, 0.92, 1.0, body)
  ball(0.11, o.M.body, -0.36, 0.42, 0.04, 0.9, 1.15, 0.9, body); ball(0.11, o.M.body, 0.36, 0.42, 0.04, 0.9, 1.15, 0.9, body)   // arms
  ball(0.12, o.M.dark, -0.15, 0.08, 0.06, 1.1, 0.55, 1.3); ball(0.12, o.M.dark, 0.15, 0.08, 0.06, 1.1, 0.55, 1.3)   // feet
  const head = new THREE.Group(); head.position.y = 0.98; body.add(head)
  ball(0.34, o.M.skull, 0, 0, 0, 1.05, 0.95, 1.0, head)
  ball(0.045, o.M.dark, -0.11, 0.02, 0.31, 1, 1.3, 0.6, head); ball(0.045, o.M.dark, 0.11, 0.02, 0.31, 1, 1.3, 0.6, head)   // eyes
  if (isHub) { const hat = new THREE.Mesh(new THREE.ConeGeometry(0.17, 0.32, 6), o.M.hubSeat); hat.position.y = 0.42; hat.castShadow = true; head.add(hat) }
  const ringMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide })
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.44, 0.56, 32), ringMat); ring.rotation.x = -Math.PI / 2; ring.position.y = 0.02; o.scene.add(ring)
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: null, transparent: true, depthTest: false })); sprite.scale.set(1.05, 1.05, 1.05); sprite.renderOrder = 10; o.scene.add(sprite)   // bubbles, the ! and zzz a size up
  const tag = h('a', { class: 'tag' + (isHub ? ' hub' : ''), href: '#/s/' + sid, tabindex: -1, 'aria-hidden': 'true' })
  hero.labels.append(tag)
  return { sid, g, body, head, ring, ringMat, sprite, tag, state: null, desk: -1, spot: null, path: [], rest: null, loc: 'desk', hub: isHub }
}
function dropFigure(f) {
  const o = hero.o
  o.scene.remove(f.g, f.ring, f.sprite); f.g.traverse(m => m.geometry?.dispose?.()); f.ring.geometry.dispose(); f.ringMat.dispose(); f.sprite.material.dispose(); f.tag.remove()
  if (f.spot) f.spot.taken = null
}

function setPath(f, wp, rest) {
  f.rest = rest
  if (calm() || !wp.length) { const [x, z] = wp.length ? wp[wp.length - 1] : [f.g.position.x, f.g.position.z]; f.g.position.set(x, rest.y, z); f.g.rotation.y = rest.rot; f.path = []; return }
  f.path = wp.map(([x, z]) => new THREE.Vector3(x, 0, z))
}
function toLoungeWaypoints(f, s) {
  const o = hero.o, seat = o.desks[f.desk].seat, aisle = seat.x + 2
  return [[aisle, seat.z], [aisle, o.geo.corridor], [2.8, o.geo.corridor], [2.8, o.geo.entry], [s.x, o.geo.entry]]
}
function goLounge(f, walk) {
  const o = hero.o, s = o.lounge.find(x => !x.taken) || o.lounge[0]
  s.taken = f; f.spot = s; f.loc = 'lounge'
  if (!walk) { f.g.position.set(s.x, s.y, s.z); f.g.rotation.y = s.rot; f.path = []; f.rest = { y: s.y, rot: s.rot }; return }
  setPath(f, toLoungeWaypoints(f, s).concat([[s.x, s.z]]), { y: s.y, rot: s.rot })
}
function goDesk(f, walk) {
  const o = hero.o, seat = o.desks[f.desk].seat, s = f.spot
  if (s) { s.taken = null; f.spot = null }
  f.loc = 'desk'
  if (!walk) { f.g.position.set(seat.x, 0.18, seat.z); f.g.rotation.y = Math.PI; f.path = []; f.rest = { y: 0.18, rot: Math.PI }; return }
  setPath(f, (s ? toLoungeWaypoints(f, s).reverse() : []).concat([[seat.x, seat.z]]), { y: 0.18, rot: Math.PI })
}
function flySheet(from, to, kind) {
  if (calm()) return
  const o = hero.o, c = new THREE.Color(kind === 'assign' ? o.col.waiting : o.col.ink)   // the assignment sheet carries the orange
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.06, 0.8), new THREE.MeshStandardMaterial({ color: c, roughness: 0.6 }))
  m.castShadow = true; o.scene.add(m)
  o.packets.push({ m, from: from.clone(), to: to.clone(), t: 0, dur: 1.6 })
  if (kind === 'assign') o.hubPulse = 1
  heroLoop()
}

function updateHero() {
  put(hero.info, demoOn() ? demoPanel() : null)   // the sessions themselves are listed in the canvas below
  if (!hero.ok) return
  try { officeSync() } catch (e) { hero.ok = false; hero.box.classList.add('flat'); return }
  heroLoop()
}

function officeSync() {
  const o = hero.o, hubA = agents.find(a => a.lane === 'HUB') || agents.find(a => msgs24?.hub && a.name === msgs24.hub)
  const rest = agents.filter(a => a !== hubA)
  const grew = officeLayout(rest.length)
  for (const [sid, f] of hero.figs) if (!agents.some(a => a.sessionId === sid)) { dropFigure(f); hero.figs.delete(sid) }
  if (grew) for (const f of hero.figs.values()) { f.desk = -1; if (f.spot) { f.spot.taken = null; f.spot = null } f.state = null }
  if (hubA) {
    let f = hero.figs.get(hubA.sessionId)
    if (!f || !f.hub) { if (f) dropFigure(f); f = makeFigure(hubA.sessionId, true); hero.figs.set(hubA.sessionId, f) }
    f.g.position.set(o.hubDesk.seat.x, 0.18, o.hubDesk.seat.z); f.g.rotation.y = Math.PI; f.rest = { y: 0.18, rot: Math.PI }; f.loc = 'hub'
    f.state = sceneOf(hubA); if (f.tag.textContent !== (hubA.name || 'hub')) { f.tag.textContent = hubA.name || 'hub'; f.tag.title = f.tag.textContent; f.tw = 0 }
  }
  const used = new Set([...hero.figs.values()].filter(f => !f.hub && f.desk >= 0).map(f => f.desk))
  for (const a of rest) {
    let f = hero.figs.get(a.sessionId), fresh = false
    if (!f || f.hub) { if (f) dropFigure(f); f = makeFigure(a.sessionId, false); hero.figs.set(a.sessionId, f); fresh = true }
    if (f.desk < 0) { let k = 0; while (used.has(k)) k++; f.desk = k; used.add(k); fresh = true }
    const nm = a.name || a.sessionId.slice(0, 8)
    if (f.tag.textContent !== nm) { f.tag.textContent = nm; f.tag.title = nm; f.tw = 0 }   // the full name on hover; width measured again
    const s = sceneOf(a), was = f.state
    f.state = s
    if (s === 'rest' && (fresh || was !== 'rest')) goLounge(f, !fresh)
    else if (s !== 'rest' && (fresh || was === 'rest')) goDesk(f, !fresh)
  }
  for (const f of hero.figs.values()) f.ringMat.color.set(o.col[f.state] || o.col.rest)
  officeMessages()
}

// new [배정] from the hub and [보고] to it, seen in the 24-hour message read; the history before the page opened is not replayed
function officeMessages() {
  const o = hero.o, d = msgs24
  if (!d?.messages) return
  const top = Math.max(0, ...d.messages.map(m => m.t || 0))
  if (hero.mark == null) { hero.mark = top; return }
  const fresh = d.messages.filter(m => m.t > hero.mark && (m.kind === 'assign' && m.from === d.hub || m.kind === 'report' && m.to === d.hub))
  hero.mark = Math.max(hero.mark, top)
  for (const m of fresh.reverse()) {
    const a = agents.find(x => x.name === (m.kind === 'assign' ? m.to : m.from)), f = a && hero.figs.get(a.sessionId)
    if (!f || f.hub || f.desk < 0) continue
    const desk = o.desks[f.desk].anchor
    m.kind === 'assign' ? flySheet(o.hubAnchor, desk, 'assign') : flySheet(desk, o.hubAnchor, 'report')
  }
}

function demoPanel() {
  const set = (a, s) => () => { s ? sceneOverride.set(a.sessionId, s) : sceneOverride.delete(a.sessionId); updateHero() }
  return h('div', { class: 'hdemo' }, h('p', { class: 'hsub' }, '#/demo: 이 브라우저에서만 장면을 바꿔 봅니다. 세션에는 아무것도 보내지 않습니다.'),
    agents.filter(a => a.lane !== 'HUB').map(a => h('div', { class: 'drow' }, h('b', {}, a.name || a.sessionId.slice(0, 8)),
      ['working', 'waiting', 'rest'].map(s => h('button', { type: 'button', class: 'segb', 'aria-pressed': String(sceneOf(a) === s), onclick: set(a, s) }, SCENE_LABEL[s])),
      h('button', { type: 'button', class: 'segb', onclick: () => { const f = hero.figs.get(a.sessionId); if (f && f.desk >= 0) flySheet(hero.o.hubAnchor, hero.o.desks[f.desk].anchor, 'assign') } }, '배정 흉내'),
      sceneOverride.has(a.sessionId) ? h('button', { type: 'button', class: 'segb', onclick: set(a, null) }, '실제로') : null)))
}

const lerpAngle = (a, b, k) => { const d = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI; return a + d * k }
function officeStep(dt, t) {
  const o = hero.o, still = calm()
  let i = 0
  for (const f of hero.figs.values()) {
    i++
    const p = f.g.position
    if (f.path.length) {
      const target = f.path[0], dx = target.x - p.x, dz = target.z - p.z, dist = Math.hypot(dx, dz), step = 2.8 * dt
      if (dist <= step) { p.x = target.x; p.z = target.z; f.path.shift() }
      else { p.x += dx / dist * step; p.z += dz / dist * step; f.g.rotation.y = lerpAngle(f.g.rotation.y, Math.atan2(dx, dz), 0.25) }
      p.y = Math.abs(Math.sin(t * 11 + i)) * 0.07
    } else if (f.rest) { p.y += (f.rest.y - p.y) * 0.2; f.g.rotation.y = lerpAngle(f.g.rotation.y, f.rest.rot, 0.15) }
    const settled = !f.path.length, atDesk = settled && (f.loc === 'desk' || f.loc === 'hub')
    const working = atDesk && f.state === 'working' && !still
    f.body.rotation.z = working ? Math.sin(t * 3 + i) * 0.06 : 0
    f.head.position.y = 0.98 + (working ? Math.abs(Math.sin(t * 6 + i)) * 0.03 : 0)
    f.body.scale.y = settled && f.loc === 'lounge' && !still ? 1 + Math.sin(t * 1.7 + i) * 0.03 : 1
    f.ring.position.set(p.x, 0.02, p.z)
    const sp = f.sprite
    let map = null, y = 2.08
    if (settled) {
      if (f.state === 'waiting') { map = o.tex.bang; y += still ? 0 : Math.abs(Math.sin(t * 4)) * 0.18 }
      else if (f.state === 'working' && atDesk) map = o.tex.dots[still ? 0 : Math.floor(t * 3 + i) % 3]
      else if (f.state === 'rest' && f.loc === 'lounge') { map = o.tex.zzz; y += still ? 0 : (t * 0.6 + i * 0.3) % 1 * 0.25 }
    }
    sp.visible = !!map
    if (map && sp.material.map !== map) { sp.material.map = map; sp.material.needsUpdate = true }
    sp.position.set(p.x, p.y + y, p.z)
    const desk = f.hub ? o.hubDesk : o.desks[f.desk]
    if (desk) for (const scr of f.hub ? desk.screens : desk.screens.slice(0, 1)) {
      if (f.state === 'working' && atDesk) { scr.emissive.set(o.col.working); scr.emissiveIntensity = 0.35 + (still ? 0 : Math.sin(t * 6 + i) * 0.08) }
      else if (f.state === 'waiting') { scr.emissive.set(o.col.waiting); scr.emissiveIntensity = still || Math.sin(t * 5) > 0 ? 0.85 : 0.25 }
      else { scr.emissive.setRGB(0, 0, 0); scr.emissiveIntensity = 0 }
    }
  }
  const hub = [...hero.figs.values()].find(f => f.hub)
  o.hubPulse = Math.max(0, (o.hubPulse || 0) - dt * 2)
  if (hub) hub.g.scale.setScalar(1 + o.hubPulse * 0.08)
  for (let k = o.packets.length - 1; k >= 0; k--) {
    const pk = o.packets[k]; pk.t += dt / pk.dur
    const e = Math.min(1, pk.t)
    pk.m.position.lerpVectors(pk.from, pk.to, e); pk.m.position.y += 2.6 * e * (1 - e) * 2
    pk.m.rotation.y += dt * 7; pk.m.rotation.z = Math.sin(e * Math.PI) * 0.4
    if (e >= 1) { o.scene.remove(pk.m); pk.m.geometry.dispose(); pk.m.material.dispose(); o.packets.splice(k, 1); hero.o.hubPulse = Math.max(hero.o.hubPulse, 0.6) }
  }
}

function officeRender() {
  const o = hero?.o
  if (!o || !hero.box.isConnected) return
  o.renderer.render(o.scene, o.camera)
  const w = hero.stage.clientWidth, hh = hero.stage.clientHeight
  const placed = [], figs = [...hero.figs.values()].map(f => {
    o.v.set(f.g.position.x, 0, f.g.position.z).project(o.camera)
    if (!f.tw) { f.tw = f.tag.offsetWidth || 80; f.th = f.tag.offsetHeight || 20 }
    return { f, x: (o.v.x + 1) / 2 * w, y: (1 - o.v.y) / 2 * hh + 10 }
  }).sort((a, b) => a.y - b.y)
  for (const p of figs) {
    const { f } = p, half = f.tw / 2
    for (let k = 0; k < 2; k++) {
      const hit = placed.find(q => Math.abs(q.x - p.x) < (q.half + half + 4) && Math.abs(q.y - p.y) < f.th + 2)
      if (!hit) break
      p.y = hit.y + f.th + 3
    }
    placed.push({ x: p.x, y: p.y, half })
    f.tag.style.transform = `translate(${(p.x - half).toFixed(1)}px, ${p.y.toFixed(1)}px)`
    f.tag.dataset.state = f.state || 'rest'
  }
}

function heroLoop() {
  if (!hero || !hero.ok || hero.raf) return
  const step = now => {
    hero.raf = 0
    if (!hero.box.isConnected || cur || page !== 'agents' || document.hidden) { hero.last = 0; return }
    const moving = !calm(), dt = hero.last ? Math.min(0.05, (now - hero.last) / 1000) : 0
    hero.last = moving ? now : 0
    try {
      officeStep(hero.paused ? 0 : dt, now / 1000)
      hero.o.controls.update(); officeRender()
    } catch (e) { hero.ok = false; hero.box.classList.add('flat'); return }
    if (moving) hero.raf = requestAnimationFrame(step)
  }
  hero.raf = requestAnimationFrame(step)
}
