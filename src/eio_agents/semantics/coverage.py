"""Coverage (03 §7.7; eio.profile.coverage-evaluation, eio.profile.coverage-census): the effective release impact of an
obligation and the coverage block (obligations, dispatch, state counts).

The census cause of an unmet obligation is injected (`census(predicate, claims)`); `census` below is the rule over the
bundle's declared producer capability registry (split plan §3.10 row 11, N2; the native registry replaces it at S4).
"""
from collections import Counter, defaultdict

from eio_agents.semantics import IMP_ORDER, SCORED, STATES


def census(capabilities, predicate, claims):
    """eio.profile.coverage-census: why a predicate has no scored claim. UNREACHABLE and NOT_IMPLEMENTED come from the
    producer capability registry `capabilities` (`{reachable_predicates, not_implemented_predicates}`, or None when the
    producer declares none, so neither cause is reported); NEVER_SELECTED, PRECONDITION_ABSENT and INCOMPLETE_COVERAGE
    from the claims."""
    if capabilities is not None:
        if predicate not in capabilities["reachable_predicates"]:
            return "UNREACHABLE"
        if predicate in capabilities["not_implemented_predicates"]:
            return "NOT_IMPLEMENTED"
    if not claims:
        return "NEVER_SELECTED"
    if all(c["state"] == "NOT_APPLICABLE" for c in claims):
        return "PRECONDITION_ABSENT"
    return "INCOMPLETE_COVERAGE"


def eff_impact(eio, declared, required, escalations, tier):
    """The declared release impact raised by the listed escalation rules and the tier's obligation floor, unless the
    obligation is not required."""
    best = IMP_ORDER.index(declared)
    if required is not False:
        for r in escalations:
            if declared in r["promote"]:
                best = max(best, IMP_ORDER.index(r["promote"][declared]))
        if tier:
            best = max(best, IMP_ORDER.index(eio.tiers[tier]["obligation_floor"]))
    return IMP_ORDER[best]


def coverage_step(eio, claims, obligation_ids, fact_values, escalations, tier, census, claim_driven):
    """The coverage of the in-scope obligations `obligation_ids` by `claims`, given the declared fact values, escalations
    and tier. `claim_driven(template_id, params, claims, role)` builds an explanation. Returns (claims by predicate,
    obligation rows, the coverage block)."""
    byp = defaultdict(list)
    for c in claims:
        byp[c["predicate"]].append(c)
    obls = []
    for oid in obligation_ids:
        o = eio.obligation[oid]
        rw = o.get("required_when") or {}
        vals = [None if fact_values.get(k) is None else (fact_values.get(k) == val) for k, val in rw.items()]
        req = False if any(x is False for x in vals) else (None if any(x is None for x in vals) else True)
        cl = byp.get(o["predicate"], [])
        sc = [c for c in cl if c["state"] in SCORED]
        met = None if req is False else len(sc) >= int(o["minimum_cases"])
        cause = census(o["predicate"], cl) if met is False else None
        row = {"id": oid, "predicate": o["predicate"], "domain": o["domain"], "required": req,
               "minimum_cases": int(o["minimum_cases"]), "cases": len(sc), "met": met,
               "release_impact_declared": o["release_impact"],
               "release_impact": eff_impact(eio, o["release_impact"], req, escalations, tier),
               "severity": o["severity"], "cause_if_unmet": cause, "claim_ids": [c["id"] for c in sc]}
        if met is False:
            params = {"obligation": oid, "cause": cause, "cases": len(sc), "minimum": int(o["minimum_cases"]),
                      "predicate": o["predicate"], "required_text": {k: fact_values.get(k) for k in rw},
                      "release_impact": row["release_impact"]}
            row["explanation"] = claim_driven("eio.why.obligation.unmet@1", params, sc, "obligation_unmet")
        obls.append(row)
    dispatch = []
    for p in sorted({o["predicate"] for o in obls}):
        cl = byp.get(p, [])
        stc = Counter(c["state"] for c in cl)
        scored = stc["APPLICABLE_PASS"] + stc["APPLICABLE_FAIL"]
        dispatch.append({"predicate": p, "dispatched": len(cl), "states": {k: stc[k] for k in STATES if stc[k]},
                         "cause_if_silent": None if scored else census(p, cl)})
    sc_ = Counter(c["state"] for c in claims)
    state_counts = {k: sc_.get(k, 0) for k in STATES}
    state_counts["total"] = len(claims)
    dbc = Counter(c["decided_by"] for c in claims)
    cov = {"obligations": obls, "dispatch": dispatch, "state_counts": state_counts,
           "decided_by_counts": {k: dbc.get(k, 0) for k in ("deterministic", "semantic", "human")},
           "summary": {"obligations": len(obls), "required_true": sum(1 for o in obls if o["required"] is True),
                       "unmet": sum(1 for o in obls if o["met"] is False),
                       "hard_block_unmet": sum(1 for o in obls if o["met"] is False and o["release_impact"] == "HARD_BLOCK")}}
    return byp, obls, cov
