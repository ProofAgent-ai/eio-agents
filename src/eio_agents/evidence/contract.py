"""The evidence contract of a scored claim (01 §6.5; eio.profile.contract-defaults): `in_scope` and `contract_check`.

The episode of a set of turns is injected as `episode_turns(turn_indices) -> set of turn indices`, so the rule does not
depend on how a producer groups turns into episodes.
"""
from eio_agents.semantics.proof import witnesses


def in_scope(ref, scope, claim, episode_turns):
    """Whether a cited ref lies inside the contract scope of the claim."""
    if scope in ("run", "artifact", "paired-episode"):
        return True
    if ref["turn_index"] is None:
        return False
    if scope in ("span", "turn"):
        return ref["turn_index"] in claim["turn_indices"]
    return ref["turn_index"] in episode_turns(claim["turn_indices"])     # episode


def contract_check(eio, c, refs, episode_turns):
    """01 §6.5 over the FAIL-direction contract; EIO 0.4.0 defaults for APPLICABLE_PASS (eio.profile.contract-defaults).
    `refs` maps ref id -> ref for every ref the claim cites."""
    pd = eio.pred[c["predicate"]]
    ec = pd.get("evidence_contract")
    if not ec:
        return {"status": "not_declared", "unmet": []}
    pol = pd["polarity"]
    cited = [refs[r] for r in c["evidence"]]
    scope_ok = all(in_scope(r, ec["scope"], c, episode_turns) for r in cited if r["kind"] not in ("POLICY_SPAN", "PROVENANCE"))
    # W1: a witnessing anchored ref inside the scope that witnesses the predicate (a STATE_FACT only where the contract names
    # it: `semantics.proof.witnesses`; L3 fix round 1, issue 8)
    wa = any(witnesses(eio, r, c["predicate"]) and in_scope(r, ec["scope"], c, episode_turns) for r in cited)
    unmet = []
    if c["state"] == "APPLICABLE_FAIL":
        kinds = {r["kind"] for r in cited}
        for k in ec.get("require_all") or []:
            if k not in kinds:
                unmet.append(f"require_all:{k}")
        if ec.get("require_any") and not kinds & set(ec["require_any"]):
            unmet.append("require_any")
        for n, g in enumerate(ec.get("require_groups") or [], 1):
            behavioural = any(eio.kind[k]["can_prove_agent_behaviour"] for k in g)
            if not any(r["kind"] in g and (r["can_prove_agent_behaviour"] or not behavioural) for r in cited):
                unmet.append(f"group:{n}")
        if len({r["id"] for r in cited}) < int(ec["minimum_refs"]):
            unmet.append("minimum_refs")
        if not scope_ok:
            unmet.append("scope")
        if ec.get("counterevidence_required") and "counterevidence" not in c:
            unmet.append("counterevidence")
        if pol == "risk" and not wa:
            unmet.append("no_witnessing_ref")                                               # W1
    else:
        if pol == "safeguard":
            ok = True
            w1 = wa
        else:
            ok = any(r["can_prove_agent_behaviour"] and in_scope(r, ec["scope"], c, episode_turns) for r in cited) or (
                pol == "risk" and any(r["kind"] == "TYPED_ABSENCE" and in_scope(r, ec["scope"], c, episode_turns) for r in cited))
            w1 = True
        if not ok:
            unmet.append("require_any")
        if not scope_ok:
            unmet.append("scope")
        if not w1:
            unmet.append("no_witnessing_ref")
    return {"status": "unmet" if unmet else "met", "unmet": unmet}
