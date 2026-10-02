"""NBodyField: deterministic, schema-compliant gravitational N-body Field."""
import json

from . import contract as C
from . import physics as P
from . import scenarios as S

DEFAULT_SCENARIO = "1"


class NBodyField:
    def __init__(self, scenario=DEFAULT_SCENARIO, steps_per_tick=1, schemas=None):
        self.steps_per_tick = steps_per_tick
        self.schemas = schemas or C.SchemaSet()
        self.paused = False
        self.quit = False
        self.log = []
        self._src_sha = C.operator_src_sha256()
        self._load(scenario)

    # ---- behavioural interface -------------------------------------------
    def command(self, cmd, arg=None):
        """Behavioural laws surface.  Returns (ok, message).  Rejected commands
        never mutate state and never emit deltas."""
        if self.quit:
            return False, "quit"
        cmd = str(cmd).strip().lower()
        if cmd in ("select", "scenario"):
            if S.lookup(arg) is None:
                return False, "unknown scenario %r" % (arg,)
            self._load(arg)
            return True, "selected %s" % self.name
        if cmd in S_KEYS:                       # bare '1'..'0'
            self._load(cmd)
            return True, "selected %s" % self.name
        if cmd == "pause":
            self.paused = True
            return True, "paused"
        if cmd == "resume":
            self.paused = False
            return True, "resumed"
        if cmd == "toggle":
            self.paused = not self.paused
            return True, "paused" if self.paused else "resumed"
        if cmd == "reset":
            self._load(self.key)
            return True, "reset"
        if cmd == "step":
            n = int(arg) if arg is not None else 1
            return True, "%d ticks" % len(self.advance(n))
        if cmd == "quit":
            self.quit = True
            return True, "quit"
        return False, "unknown command %r" % cmd

    def select(self, sel):
        return self.command("select", sel)

    # ---- state ---------------------------------------------------------------
    def _load(self, sel):
        sc = S.build(sel)
        self.key, self.name, self.eta = sc["key"], sc["name"], sc["eta"]
        self.period, self.t_default, self.note = sc["period"], sc["t_default"], sc["note"]
        self.m, self.x, self.v = sc["m"], sc["x"], sc["v"]
        self.t = 0.0
        self.tick_no = 0
        self.log = []
        self.digest = C.genesis_digest(self.name)
        self.inv0 = P.invariants(self.m, self.x, self.v)
        self._emit(dt=0.0)                      # tick 0 = genesis, full state

    def invariants(self):
        inv = P.invariants(self.m, self.x, self.v)
        e0 = self.inv0["energy"]
        inv["energy_drift"] = abs(inv["energy"] - e0) / abs(e0)
        return inv

    # ---- emission ----------------------------------------------------------------
    def _emit(self, dt):
        prov = C.provenance(self.name, self.eta, self.digest, self._src_sha)
        deltas = []
        for i in range(len(self.m)):
            deltas.append(C.build_delta(
                self.name, self.tick_no, i, self.t, C.body_cell(i), C.FIELDMAP["body_field"],
                {"m": self.m[i], "x": list(self.x[i]), "v": list(self.v[i])}, prov))
        inv = P.invariants(self.m, self.x, self.v)
        deltas.append(C.build_delta(
            self.name, self.tick_no, len(self.m), self.t, C.FIELDMAP["system_cell"],
            C.FIELDMAP["inv_field"],
            {"energy": inv["energy"], "kinetic": inv["kinetic"], "potential": inv["potential"],
             "momentum": inv["momentum"], "angular_momentum": inv["angular_momentum"],
             "dt": dt}, prov))
        tk = C.build_tick(self.name, self.tick_no, self.t, dt, self.digest, deltas)
        errs = C.check_tick(tk, self.digest, self.tick_no, self.schemas)
        if errs:                                 # emit ONLY valid deltas
            raise C.ContractViolation("; ".join(errs))
        self.log.append(tk)
        self.digest = tk["digest"]
        return tk

    # ---- dynamics -----------------------------------------------------------------
    def _one_tick(self, t_limit=None):
        spent = 0.0
        for _ in range(self.steps_per_tick):
            dt = P.adaptive_dt(self.m, self.x, self.v, self.eta)
            if t_limit is not None:
                rem = t_limit - self.t - spent
                if rem <= 0.0:
                    break
                if rem <= dt * (1.0 + 1e-12):
                    dt = rem
            self.x, self.v = P.forest_ruth4_step(self.m, self.x, self.v, dt)
            spent += dt
            if t_limit is not None and t_limit - (self.t + spent) <= 0.0:
                break
        if spent == 0.0:
            return None
        self.t = self.t + spent if t_limit is None or self.t + spent < t_limit else t_limit
        self.tick_no += 1
        return self._emit(spent)

    def advance(self, n=1):
        """Advance n ticks (no-op while paused or after quit)."""
        out = []
        if self.paused or self.quit:
            return out
        for _ in range(n):
            tk = self._one_tick()
            if tk:
                out.append(tk)
        return out

    def run_until(self, t_target):
        """Advance so that self.t == t_target exactly (final step clamped)."""
        out = []
        if self.paused or self.quit:
            return out
        while self.t < t_target:
            tk = self._one_tick(t_limit=t_target)
            if tk is None:
                break
            out.append(tk)
        return out

    # ---- contract edges --------------------------------------------------------
    def ingest_observation(self, obs):
        raise C.ContractViolation(
            "synthetic field: physical observations are not admitted (origin=%r)"
            % (obs.get("origin") if isinstance(obs, dict) else None))

    def export_log(self, path):
        with open(path, "w", encoding="utf-8") as f:
            for tk in self.log:
                f.write(C.canonical(tk) + "\n")


S_KEYS = tuple(rec[0] for rec in S.SCENARIOS)


def load_log(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def replay(ticks, schemas=None):
    """Rebuild state purely from deltas (no physics) after admitting the whole log.
    Returns {'t','tick','bodies':{cell:value},'system':value,'digest'}."""
    errs = C.check_log(ticks, schemas)
    if errs:
        raise C.ContractViolation("; ".join(errs))
    state = {}
    for tk in ticks:
        for d in tk["deltas"]:                   # already deterministically ordered
            state[(d["address"]["cell"], d["field"])] = d["value"]
    last = ticks[-1]
    return {"t": last["t"], "tick": last["tick"], "digest": last["digest"],
            "bodies": [state[(C.body_cell(i), C.FIELDMAP["body_field"])]
                       for i in range(sum(1 for k in state if k[1] == C.FIELDMAP["body_field"]))],
            "system": state[(C.FIELDMAP["system_cell"], C.FIELDMAP["inv_field"])]}
