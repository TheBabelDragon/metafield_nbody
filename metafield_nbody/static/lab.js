/** Lab tab UI for Interactive Dynamics Laboratory */
const labState = { lastIds: [] };

async function labPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return await r.json();
}

function labDim() {
  const el = document.getElementById("lab-dim");
  return el ? parseInt(el.value, 10) || 3 : 3;
}

async function labLoadIntegrators() {
  const sel = document.getElementById("lab-integrator");
  if (!sel) return;
  try {
    const r = await fetch("/api/lab/integrators");
    const data = await r.json();
    sel.innerHTML = "";
    (data.integrators || []).forEach((it) => {
      const o = document.createElement("option");
      o.value = it.id;
      o.textContent = it.name + (it.symplectic ? " · symplectic" : "");
      sel.appendChild(o);
    });
  } catch (e) {
    console.error(e);
  }
}

function labSyncScenarioSelect() {
  const sel = document.getElementById("lab-scenario");
  const src = document.getElementById("sel-scenario");
  if (!sel || !src) return;
  sel.innerHTML = src.innerHTML;
}

function labDrawDrift(series) {
  const canvas = document.getElementById("lab-plot-drift");
  if (!canvas || !series || !series.t || series.t.length < 2) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0c1220";
  ctx.fillRect(0, 0, w, h);
  const ys = series.rel_drift;
  let ymin = Math.min(...ys), ymax = Math.max(...ys);
  if (ymin === ymax) { ymin -= 1e-16; ymax += 1e-16; }
  const pad = (ymax - ymin) * 0.08 || 1e-16;
  ymin -= pad; ymax += pad;
  const xmin = series.t[0], xmax = series.t[series.t.length - 1] || xmin + 1;
  const lx = 36, rx = 8, ty = 10, by = 18;
  const pw = w - lx - rx, ph = h - ty - by;
  ctx.strokeStyle = "#1a2740";
  ctx.beginPath();
  ctx.moveTo(lx, ty);
  ctx.lineTo(lx, ty + ph);
  ctx.lineTo(lx + pw, ty + ph);
  ctx.stroke();
  ctx.strokeStyle = "#f0b429";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < ys.length; i++) {
    const x = lx + ((series.t[i] - xmin) / (xmax - xmin || 1)) * pw;
    const y = ty + ph - ((ys[i] - ymin) / (ymax - ymin || 1)) * ph;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

async function labRun(overrides = {}) {
  const body = {
    scenario: (document.getElementById("lab-scenario") || {}).value || "1",
    integrator_id: overrides.integrator_id || (document.getElementById("lab-integrator") || {}).value || "forest_ruth4_fixed",
    dt: parseFloat((document.getElementById("lab-dt") || {}).value || "0.001"),
    n_steps: parseInt((document.getElementById("lab-steps") || {}).value || "1000", 10),
    dim: overrides.dim != null ? overrides.dim : labDim(),
    label: overrides.label || "",
    record_trajectories: true,
  };
  const el = document.getElementById("lab-result");
  if (el) el.textContent = "running…";
  try {
    const data = await labPost("/api/lab/run", body);
    if (!data.ok) {
      if (el) el.textContent = "ERR " + (data.msg || JSON.stringify(data));
      return;
    }
    const r = data.result;
    labState.lastIds.push(r.experiment_id);
    if (labState.lastIds.length > 20) labState.lastIds = labState.lastIds.slice(-20);
    if (el) {
      el.textContent = JSON.stringify({
        experiment_id: r.experiment_id,
        status: r.status,
        method: r.config && r.config.integration && r.config.integration.method,
        dim: r.dim != null ? r.dim : (r.config && r.config.model && r.config.model.dim),
        rel_drift: r.energy_analysis && r.energy_analysis.rel_drift,
        max_abs_drift: r.energy_analysis && r.energy_analysis.max_abs_drift,
        run_digest: (r.run_digest || "").slice(0, 16) + "…",
      }, null, 2);
    }
    if (r.series) labDrawDrift(r.series);
    const set = (id, v) => { const n = document.getElementById(id); if (n) n.textContent = v; };
    if (r.energy_analysis) {
      set("lab-e0", r.energy_analysis.E0 != null ? Number(r.energy_analysis.E0).toExponential(6) : "—");
      set("lab-rel", r.energy_analysis.rel_drift != null ? Number(r.energy_analysis.rel_drift).toExponential(6) : "—");
      set("lab-maxd", r.energy_analysis.max_abs_drift != null ? Number(r.energy_analysis.max_abs_drift).toExponential(6) : "—");
      set("lab-meand", r.energy_analysis.mean_abs_drift != null ? Number(r.energy_analysis.mean_abs_drift).toExponential(6) : "—");
    }
    labRefreshHistory();
    // Pull trails for viewport overlay (dim-aware projection in app.js)
    if (r.experiment_id && window.metafieldSetLabTrails) {
      fetch("/api/lab/experiment?id=" + encodeURIComponent(r.experiment_id) + "&include=trails")
        .then((resp) => resp.json())
        .then((full) => {
          const res = full.result || {};
          if (res.trails) {
            window.metafieldSetLabTrails(res.trails, res.dim || 3);
          }
        })
        .catch(() => {});
    }
  } catch (e) {
    if (el) el.textContent = String(e);
  }
}

async function labRefreshHistory() {
  const el = document.getElementById("lab-history");
  if (!el) return;
  try {
    const r = await fetch("/api/lab/experiments");
    const data = await r.json();
    const list = data.experiments || [];
    if (!list.length) { el.textContent = "no experiments yet"; return; }
    el.textContent = list.map((e) =>
      e.experiment_id + " · " + e.method +
      (e.dim != null ? " · D" + e.dim : "") +
      " · dt=" + e.dt + " · drift=" +
      (e.rel_drift != null ? Number(e.rel_drift).toExponential(3) : "—") + " · " + e.status
    ).join("\n");
  } catch (e) {
    el.textContent = String(e);
  }
}

async function labSweepDt() {
  const stEl = document.getElementById("lab-sweep-status");
  if (stEl) stEl.textContent = "starting…";
  const data = await labPost("/api/lab/sweep", {
    scenario: (document.getElementById("lab-scenario") || {}).value || "1",
    integrator_id: (document.getElementById("lab-integrator") || {}).value || "rk4",
    dt: 1e-3,
    n_steps: 200,
    dim: labDim(),
    parameter: "dt",
    values: [1e-3, 2e-3, 5e-3],
    label_prefix: "dt-sweep",
  });
  if (!data.ok && data.msg) {
    if (stEl) stEl.textContent = "ERR " + data.msg;
    return;
  }
  const poll = async () => {
    const st = await (await fetch("/api/lab/sweep_status")).json();
    if (stEl) stEl.textContent = JSON.stringify(st, null, 2);
    if (st.active) setTimeout(poll, 200);
    else labRefreshHistory();
  };
  poll();
}

async function labCompare() {
  const el = document.getElementById("lab-compare-out");
  if (labState.lastIds.length < 2) {
    if (el) el.textContent = "run at least two experiments first";
    return;
  }
  const data = await labPost("/api/lab/compare", { ids: labState.lastIds.slice(-2) });
  if (el) el.textContent = JSON.stringify(data, null, 2);
}

function labBind() {
  if (!document.getElementById("lab-run")) return;
  document.getElementById("lab-run").addEventListener("click", () => labRun());
  document.getElementById("lab-run-rk4").addEventListener("click", () => labRun({ integrator_id: "rk4", label: "ui-rk4" }));
  document.getElementById("lab-run-fr").addEventListener("click", () => labRun({ integrator_id: "forest_ruth4_fixed", label: "ui-fr" }));
  const logh2 = document.getElementById("lab-run-logh");
  if (logh2) logh2.addEventListener("click", () => labRun({ integrator_id: "logh_leapfrog", label: "ui-logh2" }));
  const logh4 = document.getElementById("lab-run-logh4");
  if (logh4) logh4.addEventListener("click", () => labRun({ integrator_id: "logh_yoshida4", label: "ui-logh4" }));
  document.getElementById("lab-sweep-dt").addEventListener("click", labSweepDt);
  document.getElementById("lab-sweep-cancel").addEventListener("click", () => labPost("/api/lab/sweep_cancel", {}));
  document.getElementById("lab-compare").addEventListener("click", labCompare);
  labLoadIntegrators();
  labSyncScenarioSelect();
  const src = document.getElementById("sel-scenario");
  if (src) src.addEventListener("change", labSyncScenarioSelect);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => setTimeout(labBind, 300));
} else {
  setTimeout(labBind, 300);
}
