"""The verifier's own explanation renderer (eio.profile.why-rendering), independent of `eio_agents.semantics.why`."""
import json
import re
from decimal import ROUND_HALF_UP, Decimal

from eio_agents.validation.canon import q4
from eio_agents.validation.privacy import shown


PHRASE = {"AGENT_SPAN": "the agent answer", "TOOL_RECEIPT": "a tool receipt", "TYPED_ABSENCE": "a typed absence",
          "STATE_FACT": "a state fact", "STATE_TRANSITION": "a state transition", "CALCULATION": "a calculation",
          "HUMAN_SIGNOFF": "a human sign-off"}


def r_score(v):
    return str(Decimal(repr(q4(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def r_param(p, v):
    v = shown(v)                                  # a fingerprint renders in its display form (decision #31)
    t, lab = p["type"], p.get("labels")
    if t == "label":
        return lab[v if isinstance(v, str) else json.dumps(v)]
    if v is None:
        return lab["null"] if lab and "null" in lab else "null"
    if t in ("id", "text", "token"):
        return str(v)
    if t == "ids":
        v = [str(x) for x in v]
        return ", ".join(v[:5]) + (f" and {len(v) - 5} more" if len(v) > 5 else "")
    if t == "integer":
        assert isinstance(v, int) and not isinstance(v, bool)
        return str(v)
    if t == "score":
        return r_score(v)
    if t == "decimal":
        return f"{int(v)}.0" if float(v) == int(v) else repr(float(v))
    if t == "fraction":
        return "%.4f" % v
    if t == "turns":
        v = sorted(set(v))
        return ("turn " if len(v) == 1 else "turns ") + ", ".join(map(str, v))
    if t == "count_map":
        return ", ".join(f"{v[k]} {k}" for k in sorted(v))
    if t == "kinds_phrase":
        return "" if not v else " from " + " and ".join(PHRASE[k] for k in dict.fromkeys(v))
    if t == "recurrence":
        return "NOT_RETESTED" if v["band"] == "NOT_RETESTED" else f"{v['band']} {v['reproduced_in']}/{v['retests']}"
    if t == "required_text":
        nulls = [k for k in sorted(v) if v[k] is None]
        return (("required status unknown: required_when fact " + ", ".join(nulls) + " is not declared") if nulls
                else "required because " + ", ".join(f"{k}={json.dumps(v[k])}" for k in sorted(v)))
    if t == "axes_list":
        order = ["Q", "E", "C", "G"]
        ev = [f"{s} {r_score(v[s])}" for s in order if s in v and v[s] is not None]
        miss = [s for s in order if s in v and v[s] is None]
        return ", ".join(ev) + (f" ({', '.join(miss)} not evaluated)" if miss else "")
    if t == "decisive_list":
        return ", ".join(v)
    raise ValueError(f"param type {t} cannot be stored")


def render(eio, tid, params):
    t = eio.templates[tid]
    names = [p["name"] for p in t["params"]]
    if sorted(names) != sorted(params):
        raise ValueError(f"params {sorted(params)} != declared {sorted(names)}")
    spec = {p["name"]: p for p in t["params"]}
    return re.sub(r"\{([a-z][a-z0-9_]*)\}", lambda m: r_param(spec[m.group(1)], params[m.group(1)]), t["text"])
