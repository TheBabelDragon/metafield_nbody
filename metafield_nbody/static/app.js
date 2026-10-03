/**
 * MetaField N-Body \u00b7 Celestial Field Observatory
 * Three.js scientific visualization frontend.
 * Authoritative state comes exclusively from the Python NBodyField via /api/state.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const BODY_COLORS = [0x3ecfef, 0xf0b429, 0xa78bfa, 0x34d399, 0xf87171, 0x60a5fa];

const state = {
  data: null,
  selectedBody: null,
  trails: true,
  permTrails: true,
  trailVecs: true,
  showVel: true,
  showAcc: false,
  showLabels: true,
  showGrid: true,
  showCom: true,
  showAxes: true,
  bloom: true,
  cinematic: false,
  trailLen: 600,
  trailVecStride: 8,
  vecScale: 20,
  bodyScale: 12,
  fps: 0,
  pollHz: 0,
  latency: 0,
};

const $ = (id) => document.getElementById(id);
const canvas = $("c");

document.querySelectorAll("#tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`panel-${btn.dataset.tab}`).classList.add("active");
  });
});

const bindToggle = (id, key) => {
  const el = $(id);
  if (!el) return;
  el.addEventListener("change", (e) => {
    state[key] = e.target.checked;
    if (key === "cinematic") {
      document.body.classList.toggle("cinematic", state.cinematic);
      $("cinematic-badge").classList.toggle("hidden", !state.cinematic);
    }
    if (key === "bloom" && composer) bloomPass.enabled = state.bloom;
    updateSceneVisibility();
  });
};
bindToggle("tog-trails", "trails");
bindToggle("tog-perm-trails", "permTrails");
bindToggle("tog-trail-vecs", "trailVecs");
bindToggle("tog-vel", "showVel");
bindToggle("tog-acc", "showAcc");
bindToggle("tog-labels", "showLabels");
bindToggle("tog-grid", "showGrid");
bindToggle("tog-com", "showCom");
bindToggle("tog-axes", "showAxes");
bindToggle("tog-bloom", "bloom");
bindToggle("tog-cinematic", "cinematic");

$("trail-len").addEventListener("input", (e) => {
  state.trailLen = +e.target.value;
  $("trail-len-val").textContent = state.trailLen;
});
const tvs = $("trail-vec-stride");
if (tvs) {
  tvs.addEventListener("input", (e) => {
    state.trailVecStride = Math.max(1, +e.target.value);
    $("trail-vec-stride-val").textContent = state.trailVecStride;
    if (state.data) updatePermanentTrails(state.data);
  });
}
$("vec-scale").addEventListener("input", (e) => {
  state.vecScale = +e.target.value;
  $("vec-scale-val").textContent = state.vecScale;
});
$("body-scale").addEventListener("input", (e) => {
  state.bodyScale = +e.target.value;
  $("body-scale-val").textContent = state.bodyScale;
  if (state.data) resizeBodies(state.data.bodies);
});
const bcp = $("btn-clear-perm");
if (bcp) bcp.addEventListener("click", () => cmd("clear_permanent_trails"));

$("btn-play").addEventListener("click", () => cmd("toggle"));
$("btn-step").addEventListener("click", () => cmd("step", 1));
$("btn-reset").addEventListener("click", () => cmd("reset"));
$("speed").addEventListener("input", (e) => {
  const v = +e.target.value;
  $("speed-val").textContent = v;
  cmd("speed", v);
});
$("sel-scenario").addEventListener("change", (e) => cmd("select", e.target.value));
$("btn-load-tick").addEventListener("click", loadTick);
$("btn-export").addEventListener("click", async () => {
  const r = await cmd("export_log");
  $("export-status").textContent = r?.ok ? `Exported ${r.ticks} ticks \u2192 ${r.msg}` : r?.msg || "failed";
});
$("btn-frame").addEventListener("click", () => frameAll());
$("btn-top").addEventListener("click", () => {
  controls.object.position.set(0, 8, 0.001);
  controls.target.set(0, 0, 0);
  controls.update();
});
$("btn-side").addEventListener("click", () => {
  controls.object.position.set(8, 0, 0);
  controls.target.set(0, 0, 0);
  controls.update();
});

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x070b12, 0.035);

const camera = new THREE.PerspectiveCamera(50, canvas.clientWidth / canvas.clientHeight, 0.01, 500);
camera.position.set(2.8, 1.8, 2.8);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.3;
controls.maxDistance = 80;

function makeStars(n = 2500) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = 40 + Math.random() * 80;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = r * Math.cos(phi);
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  return new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0xaabbcc, size: 0.15, sizeAttenuation: true, transparent: true, opacity: 0.7,
  }));
}
scene.add(makeStars());
scene.add(new THREE.AmbientLight(0x334455, 0.6));
const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(5, 8, 4);
scene.add(keyLight);

const grid = new THREE.GridHelper(12, 24, 0x1a3050, 0x122033);
grid.material.transparent = true;
grid.material.opacity = 0.45;
scene.add(grid);

const axes = new THREE.AxesHelper(1.5);
axes.position.y = 0.001;
scene.add(axes);

const comMesh = new THREE.Mesh(
  new THREE.SphereGeometry(0.04, 16, 16),
  new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.7 })
);
scene.add(comMesh);

const bodyGroup = new THREE.Group();
scene.add(bodyGroup);
const permTrailGroup = new THREE.Group();
scene.add(permTrailGroup);
const trailVecGroup = new THREE.Group();
scene.add(trailVecGroup);
let bodyMeshes = [];
let trailLines = [];
let permTrailLines = [];
let trailVecLines = [];
let velArrows = [];
let accArrows = [];
let labelSprites = [];

function makeLabel(text, color) {
  const c = document.createElement("canvas");
  c.width = 128; c.height = 64;
  const ctx = c.getContext("2d");
  ctx.font = "bold 28px sans-serif";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.fillText(text, 64, 40);
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthTest: false }));
  spr.scale.set(0.35, 0.18, 1);
  return spr;
}

function rebuildBodies(bodies) {
  while (bodyGroup.children.length) bodyGroup.remove(bodyGroup.children[0]);
  while (permTrailGroup.children.length) permTrailGroup.remove(permTrailGroup.children[0]);
  while (trailVecGroup.children.length) trailVecGroup.remove(trailVecGroup.children[0]);
  bodyMeshes = []; trailLines = []; permTrailLines = []; trailVecLines = [];
  velArrows = []; accArrows = []; labelSprites = [];
  bodies.forEach((b, i) => {
    const color = BODY_COLORS[i % BODY_COLORS.length];
    const r = massRadius(b.m);
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(r, 32, 32),
      new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.45, roughness: 0.35, metalness: 0.2 })
    );
    mesh.userData.bodyId = i;
    bodyGroup.add(mesh);
    bodyMeshes.push(mesh);
    mesh.add(new THREE.Mesh(
      new THREE.SphereGeometry(r * 1.6, 16, 16),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.12, depthWrite: false })
    ));
    const line = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 }));
    bodyGroup.add(line);
    trailLines.push(line);
    const pLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 }));
    permTrailGroup.add(pLine);
    permTrailLines.push(pLine);
    const tvLine = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.75 }));
    trailVecGroup.add(tvLine);
    trailVecLines.push(tvLine);
    const vLine = makeArrow(color, 0.9);
    bodyGroup.add(vLine);
    velArrows.push(vLine);
    const aLine = makeArrow(0xf87171, 0.7);
    bodyGroup.add(aLine);
    accArrows.push(aLine);
    const spr = makeLabel(`B${i}`, "#" + color.toString(16).padStart(6, "0"));
    bodyGroup.add(spr);
    labelSprites.push(spr);
  });
  updateSceneVisibility();
}

function makeArrow(color, opacity) {
  const g = new THREE.Group();
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 0, 0, 1], 3));
  g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity })));
  return g;
}

function massRadius(m) {
  const base = 0.04 * (state.bodyScale / 12);
  return base * Math.pow(Math.max(m, 1e-9), 0.28);
}

function resizeBodies(bodies) {
  bodies.forEach((b, i) => {
    if (!bodyMeshes[i]) return;
    bodyMeshes[i].geometry.dispose();
    bodyMeshes[i].geometry = new THREE.SphereGeometry(massRadius(b.m), 32, 32);
  });
}

function updateSceneVisibility() {
  grid.visible = state.showGrid;
  axes.visible = state.showAxes;
  comMesh.visible = state.showCom;
  trailLines.forEach((l) => (l.visible = state.trails));
  permTrailLines.forEach((l) => (l.visible = state.permTrails));
  trailVecLines.forEach((l) => (l.visible = state.trailVecs));
  velArrows.forEach((a) => (a.visible = state.showVel));
  accArrows.forEach((a) => (a.visible = state.showAcc));
  labelSprites.forEach((s) => (s.visible = state.showLabels));
}

function updatePermanentTrails(data) {
  if (!data.permanent_trails || !permTrailLines.length) return;
  const stride = Math.max(1, state.trailVecStride);
  const vScale = state.vecScale * 0.012;
  data.permanent_trails.forEach((samples, i) => {
    if (!permTrailLines[i]) return;
    const n = samples.length;
    const arr = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) {
      const x = samples[k].x;
      arr[k * 3] = x[0]; arr[k * 3 + 1] = x[1]; arr[k * 3 + 2] = x[2];
    }
    permTrailLines[i].geometry.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    permTrailLines[i].geometry.setDrawRange(0, n);
    permTrailLines[i].geometry.attributes.position.needsUpdate = true;
    if (permTrailLines[i].geometry.computeBoundingSphere) {
      permTrailLines[i].geometry.computeBoundingSphere();
    }
    if (!trailVecLines[i]) return;
    const indices = [];
    for (let k = 0; k < n; k += stride) indices.push(k);
    if (n > 0 && indices[indices.length - 1] !== n - 1) indices.push(n - 1);
    const seg = new Float32Array(indices.length * 6);
    for (let j = 0; j < indices.length; j++) {
      const s = samples[indices[j]];
      const x = s.x, v = s.v, o = j * 6;
      seg[o] = x[0]; seg[o + 1] = x[1]; seg[o + 2] = x[2];
      seg[o + 3] = x[0] + v[0] * vScale;
      seg[o + 4] = x[1] + v[1] * vScale;
      seg[o + 5] = x[2] + v[2] * vScale;
    }
    trailVecLines[i].geometry.setAttribute("position", new THREE.BufferAttribute(seg, 3));
    trailVecLines[i].geometry.setDrawRange(0, indices.length * 2);
    trailVecLines[i].geometry.attributes.position.needsUpdate = true;
  });
}

function setArrow(group, origin, dir, scale) {
  const len = Math.sqrt(dir[0] ** 2 + dir[1] ** 2 + dir[2] ** 2) || 1e-12;
  const s = (scale * 0.015) / Math.max(len, 0.01);
  const positions = group.children[0].geometry.attributes.position.array;
  positions[0] = origin[0]; positions[1] = origin[1]; positions[2] = origin[2];
  positions[3] = origin[0] + dir[0] * s;
  positions[4] = origin[1] + dir[1] * s;
  positions[5] = origin[2] + dir[2] * s;
  group.children[0].geometry.attributes.position.needsUpdate = true;
}

function updateBodies(data) {
  const bodies = data.bodies;
  if (bodyMeshes.length !== bodies.length) rebuildBodies(bodies);
  bodies.forEach((b, i) => {
    bodyMeshes[i].position.set(b.x[0], b.x[1], b.x[2]);
    if (state.showVel) setArrow(velArrows[i], b.x, b.v, state.vecScale);
    if (state.showAcc) setArrow(accArrows[i], b.x, b.a, state.vecScale * 0.5);
    labelSprites[i].position.set(b.x[0], b.x[1] + massRadius(b.m) + 0.08, b.x[2]);
    if (state.trails && data.trails && data.trails[i]) {
      const pts = data.trails[i].slice(-state.trailLen);
      const arr = new Float32Array(pts.length * 3);
      for (let k = 0; k < pts.length; k++) {
        arr[k * 3] = pts[k][0]; arr[k * 3 + 1] = pts[k][1]; arr[k * 3 + 2] = pts[k][2];
      }
      trailLines[i].geometry.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      trailLines[i].geometry.setDrawRange(0, pts.length);
      trailLines[i].geometry.attributes.position.needsUpdate = true;
    }
  });
  updatePermanentTrails(data);
  const com = data.invariants.com;
  comMesh.position.set(com[0], com[1], com[2]);
}

function frameAll() {
  if (!state.data || !state.data.bodies.length) return;
  const box = new THREE.Box3();
  state.data.bodies.forEach((b) => box.expandByPoint(new THREE.Vector3(b.x[0], b.x[1], b.x[2])));
  const size = box.getSize(new THREE.Vector3()).length() || 2;
  const center = box.getCenter(new THREE.Vector3());
  const dist = Math.max(size * 0.9, 1.5);
  const dir = camera.position.clone().sub(controls.target).normalize();
  camera.position.copy(center).add(dir.multiplyScalar(dist));
  controls.target.copy(center);
  controls.update();
}

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloomPass = new UnrealBloomPass(new THREE.Vector2(canvas.clientWidth, canvas.clientHeight), 0.45, 0.4, 0.85);
composer.addPass(bloomPass);

function onResize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w || canvas.height !== h) {
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
}
window.addEventListener("resize", onResize);

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
canvas.addEventListener("pointerdown", (e) => {
  const rect = canvas.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(bodyMeshes, false);
  state.selectedBody = hits.length ? hits[0].object.userData.bodyId : null;
  updateSelectionUI();
});

async function cmd(c, arg) {
  try {
    const r = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd: c, arg }),
    });
    return await r.json();
  } catch (e) {
    console.error(e);
    return { ok: false, msg: String(e) };
  }
}

async function loadScenarios() {
  const r = await fetch("/api/scenarios");
  const data = await r.json();
  const sel = $("sel-scenario");
  sel.innerHTML = "";
  data.scenarios.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.key;
    opt.textContent = `${s.key} \u00b7 ${s.name}`;
    sel.appendChild(opt);
  });
}

async function loadTick() {
  const i = +$("tick-idx").value;
  const r = await fetch(`/api/tick?i=${i}`);
  const data = await r.json();
  $("tick-payload").textContent = data.ok ? JSON.stringify(data.tick, null, 2) : (data.msg || "unavailable");
}

function fmt(x, dig = 6) {
  if (x === null || x === undefined || Number.isNaN(x)) return "\u2014";
  if ((Math.abs(x) > 0 && Math.abs(x) < 1e-4) || Math.abs(x) >= 1e5) return x.toExponential(dig - 1);
  return x.toPrecision(dig);
}
function fmtVec(v) { return v.map((c) => fmt(c, 5)).join(", "); }

function updateUI(data) {
  $("scenario-label").textContent = data.scenario.name;
  $("time-label").textContent = `t = ${fmt(data.sim.t, 8)}`;
  $("t-scenario").textContent = data.scenario.name;
  $("t-bodies").textContent = data.sim.body_count;
  $("t-time").textContent = fmt(data.sim.t, 9);
  $("t-tick").textContent = data.sim.tick;
  $("t-state").textContent = data.sim.playing ? "running" : "paused";
  $("t-state").style.color = data.sim.playing ? "var(--green)" : "var(--amber)";
  $("t-speed").textContent = data.sim.speed;
  const inv = data.invariants;
  $("t-energy").textContent = fmt(inv.energy, 8);
  $("t-e0").textContent = fmt(inv.energy0, 8);
  $("t-drift").textContent = fmt(inv.energy_drift, 4);
  $("t-ke").textContent = fmt(inv.kinetic, 7);
  $("t-pe").textContent = fmt(inv.potential, 7);
  $("t-pmag").textContent = fmt(Math.hypot(...inv.momentum), 4);
  $("t-lmag").textContent = fmt(Math.hypot(...inv.angular_momentum), 6);
  $("t-mass").textContent = fmt(inv.mass, 6);
  $("t-com").textContent = fmtVec(inv.com);
  $("t-fps").textContent = state.fps.toFixed(0);
  $("t-poll").textContent = state.pollHz.toFixed(1);
  const eph = data.trails ? data.trails.reduce((s, t) => s + t.length, 0) : 0;
  const perm = data.permanent_trail_meta ? data.permanent_trail_meta.points : 0;
  $("t-trail").textContent = `${eph} / ${perm}`;
  $("t-lat").textContent = state.latency.toFixed(0) + " ms";

  let html = "<table><tr><th>#</th><th>m</th><th>|v|</th><th>|a|</th></tr>";
  data.bodies.forEach((b, i) => {
    const sel = state.selectedBody === i ? ' class="selected"' : "";
    html += `<tr data-id="${i}"${sel}><td>B${i}</td><td>${fmt(b.m, 4)}</td><td>${fmt(Math.hypot(...b.v), 4)}</td><td>${fmt(Math.hypot(...b.a), 4)}</td></tr>`;
  });
  html += "</table>";
  $("body-table").innerHTML = html;
  $("body-table").querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", () => { state.selectedBody = +tr.dataset.id; updateSelectionUI(); });
  });

  const p = data.field.params;
  $("m-theta").textContent = fmt(p.theta, 8);
  $("m-soft").textContent = p.softening;
  $("m-eta").textContent = data.scenario.eta;
  $("m-dtrange").textContent = `[${p.dt_min}, ${p.dt_max}]`;
  const notes = $("math-notes");
  notes.innerHTML = "";
  (data.math.notes || []).forEach((n) => {
    const li = document.createElement("li");
    li.textContent = n;
    notes.appendChild(li);
  });

  $("f-digest").textContent = data.field.digest?.slice(0, 16) + "\u2026";
  $("f-prev").textContent = data.field.prev_digest ? data.field.prev_digest.slice(0, 16) + "\u2026" : "\u2014";
  $("f-count").textContent = data.field.tick_count;
  $("f-dt").textContent = fmt(data.field.last_dt, 6);
  $("f-contract").textContent = data.field.contract_ok ? "admitted" : "fail";
  $("f-contract").style.color = data.field.contract_ok ? "var(--green)" : "var(--red)";
  $("f-op").textContent = `${data.field.operator.name} v${data.field.operator.version}`;

  const pt = $("pair-table");
  if (data.pairs && data.pairs.length) {
    let ph = "<table><tr><th>i\u2013j</th><th>r</th><th>|F|</th></tr>";
    data.pairs.forEach((p) => {
      ph += `<tr><td>${p.i}\u2013${p.j}</td><td>${fmt(p.r, 5)}</td><td>${fmt(p.force_mag, 4)}</td></tr>`;
    });
    pt.innerHTML = ph + "</table>";
  }

  $("btn-play").textContent = data.sim.playing ? "\u23F8" : "\u25B6";
  const sel = $("sel-scenario");
  if (sel.value !== data.scenario.key && [...sel.options].some((o) => o.value === data.scenario.key)) {
    sel.value = data.scenario.key;
  }
  updateSelectionUI();
  drawPlots(data.history);
}

function updateSelectionUI() {
  const info = $("sel-body-info");
  const tip = $("body-tooltip");
  if (state.selectedBody === null || !state.data) {
    info.textContent = "Click a body in the scene";
    tip.classList.add("hidden");
    return;
  }
  const b = state.data.bodies[state.selectedBody];
  if (!b) return;
  const txt = `Body ${state.selectedBody}\nm = ${fmt(b.m, 6)}\nx = (${fmtVec(b.x)})\nv = (${fmtVec(b.v)})\na = (${fmtVec(b.a)})`;
  info.textContent = txt;
  tip.textContent = txt;
  tip.classList.remove("hidden");
}

function drawPlots(hist) {
  if (!hist || !hist.t || hist.t.length < 2) return;
  drawSeries($("plot-energy"), hist.t, [hist.energy], ["E"], ["#3ecfef"]);
  drawSeries($("plot-drift"), hist.t, [hist.energy_drift], ["|\u0394E|/|E\u2080|"], ["#f0b429"]);
  drawSeries($("plot-mom"), hist.t, [hist.momentum_mag, hist.L_mag], ["|P|", "|L|"], ["#a78bfa", "#34d399"]);
}

function drawSeries(canvas, xs, series, labels, colors) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0c1220";
  ctx.fillRect(0, 0, w, h);
  let ymin = Infinity, ymax = -Infinity;
  series.forEach((s) => s.forEach((v) => { if (v < ymin) ymin = v; if (v > ymax) ymax = v; }));
  if (!isFinite(ymin) || !isFinite(ymax)) return;
  if (ymin === ymax) { ymin -= 1; ymax += 1; }
  const pad = (ymax - ymin) * 0.08 || 1e-15;
  ymin -= pad; ymax += pad;
  const xmin = xs[0], xmax = xs[xs.length - 1] || xmin + 1;
  const lx = 36, rx = 8, ty = 10, by = 18;
  const pw = w - lx - rx, ph = h - ty - by;
  ctx.strokeStyle = "#1a2740"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(lx, ty); ctx.lineTo(lx, ty + ph); ctx.lineTo(lx + pw, ty + ph); ctx.stroke();
  ctx.fillStyle = "#6b7c96"; ctx.font = "9px monospace"; ctx.textAlign = "right";
  ctx.fillText(fmt(ymax, 3), lx - 3, ty + 8);
  ctx.fillText(fmt(ymin, 3), lx - 3, ty + ph);
  series.forEach((s, si) => {
    ctx.strokeStyle = colors[si]; ctx.lineWidth = 1.5; ctx.beginPath();
    for (let i = 0; i < s.length; i++) {
      const x = lx + ((xs[i] - xmin) / (xmax - xmin || 1)) * pw;
      const y = ty + ph - ((s[i] - ymin) / (ymax - ymin || 1)) * ph;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });
  ctx.textAlign = "left";
  labels.forEach((lab, i) => { ctx.fillStyle = colors[i]; ctx.fillText(lab, lx + 6 + i * 50, ty + 10); });
}

let frames = 0, fpsT = performance.now();
function renderLoop(now) {
  requestAnimationFrame(renderLoop);
  onResize();
  controls.update();
  if (state.bloom) composer.render(); else renderer.render(scene, camera);
  frames++;
  if (now - fpsT > 500) {
    state.fps = (frames * 1000) / (now - fpsT);
    frames = 0; fpsT = now;
  }
}
requestAnimationFrame(renderLoop);

let pollCount = 0, pollT = performance.now(), framedOnce = false;
async function poll() {
  const t0 = performance.now();
  try {
    const r = await fetch("/api/state");
    const data = await r.json();
    state.latency = performance.now() - t0;
    state.data = data;
    updateBodies(data);
    updateUI(data);
    $("conn-status").textContent = "connected \u00b7 live";
    $("conn-status").style.color = "var(--green)";
    if (!framedOnce && data.bodies.length) { frameAll(); framedOnce = true; }
  } catch (e) {
    $("conn-status").textContent = "disconnected";
    $("conn-status").style.color = "var(--red)";
  }
  pollCount++;
  const now = performance.now();
  if (now - pollT > 1000) {
    state.pollHz = (pollCount * 1000) / (now - pollT);
    pollCount = 0; pollT = now;
  }
}

(async () => {
  await loadScenarios();
  await poll();
  setInterval(poll, 50);
})();
