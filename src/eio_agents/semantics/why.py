"""Explanations (03 §8; eio.profile.why-rendering): template rendering, the claim basis, the cited-first ref order and the
explanation object.

Every stored summary is `render(template_id, params)` of a template of eio.template.why (EIO-49).
"""
import json
import re
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from eio_agents.base.canon import q4
from eio_agents.base.errors import ConversionError, require
from eio_agents.semantics import FAULT

KIND_PHRASE = {"AGENT_SPAN": "the agent answer", "TOOL_RECEIPT": "a tool receipt", "TYPED_ABSENCE": "a typed absence",
               "STATE_FACT": "a state fact", "STATE_TRANSITION": "a state transition", "CALCULATION": "a calculation",
               "HUMAN_SIGNOFF": "a human sign-off"}
AXIS_SYMBOLS = ["Q", "E", "C", "G"]


def fmt_score(v):
    return str(Decimal(repr(q4(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fmt_decimal(v):
    if isinstance(v, int) or float(v) == int(v):
        return f"{int(v)}.0"
    return repr(float(v))


def fmt_ids(xs):
    xs = [str(x) for x in xs]
    return ", ".join(xs[:5]) + (f" and {len(xs) - 5} more" if len(xs) > 5 else "")


def fmt_turn_list(ts):
    """03 E-3 turn lists: `turn 5` / `turns 5, 14`, longer than 5 as the first 5 plus ` and N more`."""
    ts = [str(t) for t in ts]
    return ("turn " if len(ts) == 1 else "turns ") + ", ".join(ts[:5]) + (f" and {len(ts) - 5} more" if len(ts) > 5 else "")


def render_param(p, v):
    t = p["type"]
    labels = p.get("labels")
    if t == "label":
        key = json.dumps(v) if not isinstance(v, str) else v
        require(key in labels, "TEMPLATE_LABEL", f"{p['name']}={key}")
        return labels[key]
    if v is None:
        return labels["null"] if labels and "null" in labels else "null"
    if t in ("id", "text"):
        return str(v)
    if t == "token":
        return str(v)
    if t == "ids":
        return fmt_ids(v)
    if t == "integer":
        require(isinstance(v, int) and not isinstance(v, bool), "TEMPLATE_TYPE", p["name"])
        return str(v)
    if t == "score":
        return fmt_score(v)
    if t == "decimal":
        return fmt_decimal(v)
    if t == "fraction":
        return f"{q4(v):.4f}"
    if t == "turns":
        ts = sorted(set(v))
        return ("turn " if len(ts) == 1 else "turns ") + ", ".join(map(str, ts))
    if t == "count_map":
        return ", ".join(f"{v[k]} {k}" for k in sorted(v))
    if t == "kinds_phrase":
        seen = list(dict.fromkeys(v))
        return "" if not seen else " from " + " and ".join(KIND_PHRASE[k] for k in seen)
    if t == "recurrence":
        return "NOT_RETESTED" if v["band"] == "NOT_RETESTED" else f"{v['band']} {v['reproduced_in']}/{v['retests']}"
    if t == "required_text":
        nulls = [k for k in sorted(v) if v[k] is None]
        if nulls:
            return "required status unknown: required_when fact " + ", ".join(nulls) + " is not declared"
        return "required because " + ", ".join(f"{k}={json.dumps(v[k])}" for k in sorted(v))
    if t == "axes_list":
        ev = [f"{s} {fmt_score(v[s])}" for s in AXIS_SYMBOLS if s in v and v[s] is not None]
        miss = [s for s in AXIS_SYMBOLS if s in v and v[s] is None]
        return ", ".join(ev) + (f" ({', '.join(miss)} not evaluated)" if miss else "")
    if t == "decisive_list":
        return ", ".join(v)
    raise ConversionError(f"TEMPLATE_PARAM_TYPE: {t} is not renderable in a stored explanation", code="TEMPLATE_PARAM_TYPE")


def render(eio, tid, params):
    """render(template_id, params): every placeholder is a declared param and every param is rendered."""
    t = eio.templates.get(tid)
    require(t is not None, "UNKNOWN_TEMPLATE", tid)
    declared = [p["name"] for p in t["params"]]
    require(sorted(declared) == sorted(params), "TEMPLATE_PARAMS", f"{tid}: declared {sorted(declared)} given {sorted(params)}")
    spec = {p["name"]: p for p in t["params"]}
    out = re.sub(r"\{([a-z][a-z0-9_]*)\}", lambda m: render_param(spec[m.group(1)], params[m.group(1)]), t["text"])
    require(len(out) <= int(t.get("max_length", 600)), "TEMPLATE_TOO_LONG", f"{tid} {len(out)}")
    return out


ZB = {"claims": 0, "applicable": 0, "pass": 0, "fail": 0, "not_applicable": 0, "unresolved": 0, "evaluator_fault": 0}


def basis(cl):
    """The state counts of the claims an explanation rests on."""
    s = Counter(c["state"] for c in cl)
    return {"claims": len(cl), "applicable": s["APPLICABLE_PASS"] + s["APPLICABLE_FAIL"], "pass": s["APPLICABLE_PASS"],
            "fail": s["APPLICABLE_FAIL"], "not_applicable": s["NOT_APPLICABLE"], "unresolved": s["UNRESOLVED"],
            "evaluator_fault": sum(s[x] for x in FAULT)}


def cited_first(eio, refs, ref_order, ref_ids, driver_claims):
    """03 §5.6 rule 4: witnessing anchored refs first, then other agent refs, then the rest; within a group by the first
    driver claim that cites the ref, then record ref order. `refs` maps id -> ref; `ref_order` maps id -> record index."""
    rank = {}
    for i, c in enumerate(driver_claims):
        for r in c["evidence"]:
            rank.setdefault(r, i)

    def key(r):
        x = refs[r]
        g = 0 if eio.witnessing_anchored(x) else (1 if x["can_prove_agent_behaviour"] else 2)
        return (g, rank.get(r, 10 ** 6), ref_order.get(r, 10 ** 6), r)
    return sorted(dict.fromkeys(ref_ids), key=key)


def explanation(eio, tid, params, bas, drivers, refs, ctx=None):
    """The explanation object: the rendered summary, its basis, at most 20 drivers and 12 evidence refs (the rest counted
    in `omitted`) and the context refs."""
    e = {"template_id": tid, "params": params, "summary": render(eio, tid, params), "basis": bas,
         "drivers": drivers[:20], "evidence_refs": refs[:12], "context_refs": ctx or []}
    if len(drivers) > 20 or len(refs) > 12:
        e["omitted"] = {"drivers": max(0, len(drivers) - 20), "evidence_refs": max(0, len(refs) - 12)}
    return e


def claim_driven(eio, refs, ref_order, tid, params, cl, role, ctx=None, bas=None):
    """An explanation whose drivers are the claims `cl`, in order, all with one role, citing their refs cited-first."""
    drivers = [{"rank": i + 1, "claim_id": c["id"], "role": role, "contribution": None} for i, c in enumerate(cl)]
    return explanation(eio, tid, params, bas if bas is not None else basis(cl), drivers,
                       cited_first(eio, refs, ref_order, [r for c in cl for r in c["evidence"]], cl), ctx)
