/**
 * Viewport projection helpers for N-D coordinates → Three.js XYZ.
 * Loaded after app.js. Does not touch the golden Field physics path.
 */
(function () {
  const axes = { x: 0, y: 1, z: 2 };
  let labTrails = null;
  let labOverlayLines = [];
  let labOverlay = false;

  function readAxes() {
    const rx = document.getElementById("proj-x");
    const ry = document.getElementById("proj-y");
    const rz = document.getElementById("proj-z");
    if (rx) axes.x = parseInt(rx.value, 10) || 0;
    if (ry) axes.y = parseInt(ry.value, 10) || 1;
    if (rz) axes.z = parseInt(rz.value, 10) || 2;
  }

  function projectPoint(coords) {
    if (!coords || !coords.length) return [0, 0, 0];
    const pick = (i) => (i >= 0 && i < coords.length ? coords[i] : 0);
    return [pick(axes.x), pick(axes.y), pick(axes.z)];
  }

  function clearLabOverlay() {
    if (typeof scene === "undefined") return;
    labOverlayLines.forEach((l) => scene.remove(l));
    labOverlayLines = [];
  }

  function updateLabOverlay() {
    clearLabOverlay();
    if (!labOverlay || !labTrails || typeof THREE === "undefined" || typeof scene === "undefined") return;
    const colors = (typeof BODY_COLORS !== "undefined")
      ? BODY_COLORS
      : [0x3ecfef, 0xf0b429, 0xa78bfa, 0x34d399, 0xf87171, 0x60a5fa];
    labTrails.forEach((trail, i) => {
      if (!trail || !trail.length) return;
      const arr = new Float32Array(trail.length * 3);
      for (let k = 0; k < trail.length; k++) {
        const q = projectPoint(trail[k]);
        arr[k * 3] = q[0];
        arr[k * 3 + 1] = q[1];
        arr[k * 3 + 2] = q[2];
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      const mat = new THREE.LineBasicMaterial({
        color: colors[i % colors.length],
        transparent: true,
        opacity: 0.85,
      });
      const line = new THREE.Line(geo, mat);
      scene.add(line);
      labOverlayLines.push(line);
    });
  }

  function bindUI() {
    ["proj-x", "proj-y", "proj-z"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("change", () => {
        readAxes();
        if (typeof state !== "undefined" && state.data && typeof updateBodies === "function") {
          // Re-render live field with same 3-D data (axis remap is no-op for dim=3 identity).
          updateBodies(state.data);
        }
        if (labOverlay) updateLabOverlay();
      });
    });
    const tog = document.getElementById("tog-lab-overlay");
    if (tog) {
      tog.addEventListener("change", (e) => {
        labOverlay = !!e.target.checked;
        if (labOverlay) updateLabOverlay();
        else clearLabOverlay();
      });
    }
    readAxes();
  }

  // Patch updateBodies to project if coordinates longer than 3 (lab overlay path).
  // Live Field always sends length-3; projection still allows axis permutation.
  function installHooks() {
    if (typeof updateBodies !== "function") return;
    const orig = updateBodies;
    window.updateBodies = function (data) {
      readAxes();
      // Axis permutation for 3-D: rewrite body positions into projected frame for display.
      if (data && data.bodies && (axes.x !== 0 || axes.y !== 1 || axes.z !== 2)) {
        const mapped = JSON.parse(JSON.stringify(data));
        mapped.bodies = data.bodies.map((b) => ({
          ...b,
          x: projectPoint(b.x),
          v: projectPoint(b.v || [0, 0, 0]),
          a: projectPoint(b.a || [0, 0, 0]),
        }));
        if (mapped.trails) {
          mapped.trails = data.trails.map((tr) => (tr || []).map((p) => projectPoint(p)));
        }
        if (mapped.invariants && mapped.invariants.com) {
          mapped.invariants = { ...mapped.invariants, com: projectPoint(mapped.invariants.com) };
        }
        if (mapped.permanent_trails) {
          mapped.permanent_trails = data.permanent_trails.map((samples) =>
            (samples || []).map((s) => ({
              ...s,
              x: projectPoint(s.x),
              v: projectPoint(s.v || [0, 0, 0]),
            }))
          );
        }
        orig(mapped);
      } else {
        orig(data);
      }
      if (labOverlay) updateLabOverlay();
    };
  }

  window.metafieldSetLabTrails = function (trails, dim) {
    labTrails = trails;
    if (labOverlay) updateLabOverlay();
  };

  function boot() {
    bindUI();
    // app.js is a module; globals like updateBodies may appear after a tick
    let tries = 0;
    const t = setInterval(() => {
      tries += 1;
      if (typeof updateBodies === "function" || tries > 50) {
        clearInterval(t);
        installHooks();
      }
    }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
