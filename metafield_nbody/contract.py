"""field-os contract layer: canonical encoding, deterministic digests,
schema validation (stdlib JSON-Schema subset) and semantic admission rules.

ALL field-os wire names live in this file (FIELDMAP + build_* functions).
If the locked field-os schemas differ from .babel/schemas, adapt here only,
then run:  python -m metafield_nbody.checker --schema-dir ../field-os/schema
"""
import hashlib
import inspect
import json
import math
import os
import re

from . import physics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCHEMA_DIR = os.path.join(ROOT, ".babel", "schemas")

VERSION = "0.1"
FIELDMAP = {
    "delta_kind": "FieldDelta", "tick_kind": "FieldTick",
    "body_field": "gravity.body_state", "inv_field": "gravity.invariants",
    "space_prefix": "nbody/", "system_cell": "system",
}


class ContractViolation(ValueError):
    pass


# ---------- canonical encoding / digests -------------------------------------

def canonical(obj):
    """Deterministic JSON: sorted keys, no whitespace, shortest round-trip floats,
    NaN/Inf forbidden."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=True)


def sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()


def genesis_digest(scenario_name):
    return sha256_hex("metafield-nbody/genesis/" + scenario_name)


def operator_src_sha256():
    src = inspect.getsource(physics.forest_ruth4_step) + inspect.getsource(physics._leapfrog) \
        + inspect.getsource(physics.accelerations) + inspect.getsource(physics.adaptive_dt) \
        + inspect.getsource(physics.invariants)
    return sha256_hex(src.replace("\r\n", "\n"))


def params_block(eta):
    return {"G": physics.G, "softening": physics.SOFTENING, "eta": eta,
            "dt_min": physics.DT_MIN, "dt_max": physics.DT_MAX, "theta": physics.THETA}


def provenance(scenario, eta, prev_digest, src_sha=None):
    return {
        "source": "metafield-nbody",
        "operator": {"name": physics.OPERATOR_NAME, "version": physics.OPERATOR_VERSION,
                     "src_sha256": src_sha or operator_src_sha256()},
        "origin": "synthetic", "physical": False,
        "inputs": [prev_digest], "params": params_block(eta), "scenario": scenario,
    }


# ---------- builders ----------------------------------------------------------

def body_cell(i):
    return "body/%04d" % i


def build_delta(scenario, tick, seq, t, cell, field, value, prov):
    return {
        "kind": FIELDMAP["delta_kind"], "version": VERSION,
        "delta_id": "%s:%d:%d" % (scenario, tick, seq),
        "address": {"space": FIELDMAP["space_prefix"] + scenario, "cell": cell},
        "field": field, "op": "set", "value": value, "t": t,
        "origin": "synthetic", "provenance": prov,
    }


def delta_sort_key(d):
    return (d["address"]["space"], d["address"]["cell"], d["field"])


def build_tick(scenario, tick, t, dt, prev_digest, deltas):
    deltas = sorted(deltas, key=delta_sort_key)
    body = {"kind": FIELDMAP["tick_kind"], "version": VERSION, "scenario": scenario,
            "tick": tick, "t": t, "dt": dt, "prev_digest": prev_digest, "deltas": deltas}
    body["digest"] = sha256_hex(canonical(body))
    return body


def tick_digest(tick):
    b = {k: v for k, v in tick.items() if k != "digest"}
    return sha256_hex(canonical(b))


# ---------- JSON-Schema subset validator --------------------------------------

class SchemaSet:
    def __init__(self, schema_dir=None):
        self.dir = schema_dir or DEFAULT_SCHEMA_DIR
        self._cache = {}

    def load(self, name):
        if name not in self._cache:
            with open(os.path.join(self.dir, name), "r", encoding="utf-8") as f:
                self._cache[name] = json.load(f)
        return self._cache[name]

    def validate(self, name, instance):
        errs = []
        self._v(self.load(name), instance, "$", errs)
        return errs

    def _v(self, sch, inst, path, errs):
        if "$ref" in sch:
            return self._v(self.load(sch["$ref"]), inst, path, errs)
        if "const" in sch and not _eq(inst, sch["const"]):
            errs.append("%s: expected const %r" % (path, sch["const"]))
        if "enum" in sch and not any(_eq(inst, e) for e in sch["enum"]):
            errs.append("%s: %r not in enum" % (path, inst))
        t = sch.get("type")
        if t and not _type_ok(inst, t):
            errs.append("%s: expected type %s" % (path, t))
            return
        if isinstance(inst, float) and not math.isfinite(inst):
            errs.append("%s: non-finite number" % path)
        if isinstance(inst, (int, float)) and not isinstance(inst, bool) and "minimum" in sch \
                and inst < sch["minimum"]:
            errs.append("%s: below minimum" % path)
        if isinstance(inst, str) and "pattern" in sch and not re.search(sch["pattern"], inst):
            errs.append("%s: pattern mismatch" % path)
        if isinstance(inst, dict):
            for r in sch.get("required", []):
                if r not in inst:
                    errs.append("%s: missing %s" % (path, r))
            props = sch.get("properties", {})
            for k, v in inst.items():
                if k in props:
                    self._v(props[k], v, path + "." + k, errs)
                elif sch.get("additionalProperties") is False:
                    errs.append("%s: unexpected property %s" % (path, k))
        if isinstance(inst, list):
            if "minItems" in sch and len(inst) < sch["minItems"]:
                errs.append("%s: too few items" % path)
            if "maxItems" in sch and len(inst) > sch["maxItems"]:
                errs.append("%s: too many items" % path)
            if "items" in sch:
                for i, it in enumerate(inst):
                    self._v(sch["items"], it, "%s[%d]" % (path, i), errs)


def _eq(a, b):
    return type(a) is type(b) and a == b if isinstance(a, bool) or isinstance(b, bool) else a == b


def _type_ok(v, t):
    if isinstance(t, list):
        return any(_type_ok(v, x) for x in t)
    if t == "object": return isinstance(v, dict)
    if t == "array": return isinstance(v, list)
    if t == "string": return isinstance(v, str)
    if t == "boolean": return isinstance(v, bool)
    if t == "integer": return isinstance(v, int) and not isinstance(v, bool)
    if t == "number": return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "null": return v is None
    return True


# ---------- admission (schema + semantic rules) -------------------------------

def check_tick(tick, prev_digest, expected_tick, schemas=None):
    """Return a list of violations for one tick (empty list == admitted)."""
    schemas = schemas or SchemaSet()
    errs = list(schemas.validate("field_tick.schema.json", tick))
    if errs:
        return errs
    if tick["tick"] != expected_tick:
        errs.append("tick index %d != expected %d" % (tick["tick"], expected_tick))
    if tick["prev_digest"] != prev_digest:
        errs.append("prev_digest does not chain")
    if tick["digest"] != tick_digest(tick):
        errs.append("digest mismatch (content tampered)")
    keys = [delta_sort_key(d) for d in tick["deltas"]]
    if keys != sorted(keys):
        errs.append("deltas not in deterministic order")
    if len(set(keys)) != len(keys):
        errs.append("duplicate (address, field) in tick")
    ids = [d["delta_id"] for d in tick["deltas"]]
    if len(set(ids)) != len(ids):
        errs.append("duplicate delta_id")
    for d in tick["deltas"]:
        if d["origin"] != "synthetic" or d["provenance"]["origin"] != "synthetic" \
                or d["provenance"]["physical"] is not False:
            errs.append("synthetic/physical separation violated in %s" % d["delta_id"])
        if d["provenance"]["inputs"] != [prev_digest]:
            errs.append("provenance.inputs does not reference predecessor tick")
        if d["provenance"]["operator"]["version"] != physics.OPERATOR_VERSION:
            errs.append("operator version mismatch in %s" % d["delta_id"])
        if d["t"] != tick["t"]:
            errs.append("delta.t != tick.t")
        if d["address"]["space"] != FIELDMAP["space_prefix"] + tick["scenario"]:
            errs.append("delta space != tick scenario")
    return errs


def check_log(ticks, schemas=None):
    """Whole-log admission: every tick valid, chained, consecutive from 0."""
    schemas = schemas or SchemaSet()
    if not ticks:
        return ["empty log"]
    prev = genesis_digest(ticks[0]["scenario"]) if isinstance(ticks[0], dict) and "scenario" in ticks[0] else ""
    errs = []
    for i, tk in enumerate(ticks):
        e = check_tick(tk, prev, i, schemas)
        if e:
            return ["tick %d: %s" % (i, x) for x in e]
        prev = tk["digest"]
    return errs
