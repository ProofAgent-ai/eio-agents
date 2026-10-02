"""Control statuses (03 §7.9; eio.profile.compliance-materialization).

Two inputs are injected: `census(predicate, claims)` (`semantics.coverage.census` over the bundle's declared producer
capability registry), and `fidelity(claim)` (`exact` or `narrower`): the claim's declared `parameters.fidelity` in the
bundle (split plan §3.10 row 14; for an adapter claim it equals the rc1 mapping relation).
"""
from collections import Counter

from eio_agents.semantics import FAULT
from eio_agents.semantics import why as sem_why


def controls_step(eio, frameworks, byp, cidx, refs, ref_order, findings, census, fidelity):
    """One row per control of every framework in `frameworks` (the scope's) that is not NOT_APPLICABLE, in (framework,
    control) order, from the claims by predicate `byp` (claim id -> position `cidx`). Sets each finding's `control_ids`.
    Returns the rows."""
    rows = []
    for fw in frameworks:
        if fw["state"] == "NOT_APPLICABLE":
            continue
        for ctl_id in eio.frameworks[fw["id"]]["controls"]:
            k = eio.controls[ctl_id]
            tg = k["predicate_targets"]
            cl = sorted({c["id"]: c for p in tg for c in byp.get(p, [])}.values(), key=lambda c: cidx[c["id"]])
            stc = Counter(c["state"] for c in cl)
            fails = [c for c in cl if c["state"] == "APPLICABLE_FAIL"]
            passes = [c for c in cl if c["state"] == "APPLICABLE_PASS"]
            if fails:
                s = "observed_violation"
            elif passes:
                s = "observed_satisfaction"
            elif stc["UNRESOLVED"] or any(stc[x] for x in FAULT):
                s = "inconclusive"
            elif not cl and all(census(p, []) == "UNREACHABLE" for p in tg):
                s = "not_observable"
            else:
                s = "not_tested"
            deciding = fails or passes
            agent = sem_why.cited_first(eio, refs, ref_order,
                                        [r for c in deciding for r in c["evidence"] if refs[r]["can_prove_agent_behaviour"]], deciding)
            b = sem_why.basis(cl)
            ms, lr = k["mapping_status"], bool(k["legal_review_required"])
            row = {"control_id": ctl_id, "framework": fw["id"], "external_ref": k["external_ref"], "title": k["title"],
                   "framework_state": fw["state"], "status": s,
                   "claim_ids": [c["id"] for c in fails] + [c["id"] for c in passes] + [c["id"] for c in cl if c not in fails and c not in passes],
                   "evidence_refs": agent[:12], "evidence_refs_omitted": max(0, len(agent) - 12)}
            if s == "observed_violation":
                proxy = all(fidelity(c) == "narrower" for c in fails)
                row["proxy_only"] = proxy
                params = {"external_ref": k["external_ref"], "fail": b["fail"],
                          "decided_split": dict(sorted(Counter(c["decided_by"] for c in fails).items())),
                          "predicates_failed": list(dict.fromkeys(c["predicate"] for c in fails)), "pass": b["pass"],
                          "evaluator_fault": b["evaluator_fault"], "proxy_note": proxy, "mapping_status": ms, "legal_review": lr}
                expl = sem_why.explanation(eio, "eio.why.control.observed_violation@2", params, b,
                                           [{"rank": i + 1, "claim_id": c["id"], "role": "violation", "contribution": None} for i, c in enumerate(fails)], agent, [])
            elif s == "observed_satisfaction":
                params = {"external_ref": k["external_ref"], "pass": b["pass"],
                          "predicates_passed": list(dict.fromkeys(c["predicate"] for c in passes)), "mapping_status": ms, "legal_review": lr}
                expl = sem_why.explanation(eio, "eio.why.control.observed_satisfaction@1", params, b,
                                           [{"rank": i + 1, "claim_id": c["id"], "role": "satisfaction", "contribution": None} for i, c in enumerate(passes)], agent, [])
            elif s == "inconclusive":
                params = {"external_ref": k["external_ref"], "evaluator_fault": b["evaluator_fault"], "unresolved": b["unresolved"],
                          "predicates": list(tg), "mapping_status": ms, "legal_review": lr}
                expl = sem_why.explanation(eio, "eio.why.control.inconclusive@1", params, b, [], [], [])
            elif s == "not_observable":
                expl = sem_why.explanation(eio, "eio.why.control.not_observable@1", {"external_ref": k["external_ref"], "predicates": list(tg)}, b, [], [], [])
            elif cl:
                expl = sem_why.explanation(eio, "eio.why.control.not_tested.preconditions@1",
                                           {"external_ref": k["external_ref"], "n_claims": b["claims"], "predicates": list(tg)}, b, [], [], [])
            else:
                expl = sem_why.explanation(eio, "eio.why.control.not_tested@1", {"external_ref": k["external_ref"], "predicates": list(tg)}, b, [], [], [])
            row.update({"mapping_status": ms, "legal_review_required": lr, "assurance_boundary": k["assurance_boundary"],
                        "explanation": expl})
            rows.append(row)
    rows.sort(key=lambda r: (r["framework"], r["control_id"]))
    for f in findings:
        f["control_ids"] = [r["control_id"] for r in rows if set(f["claim_ids"]) & set(r["claim_ids"])]
    return rows
