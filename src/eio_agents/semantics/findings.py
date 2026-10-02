"""Findings (03 §7.8): BEHAVIOURAL findings grouped by behavioural fingerprint, and CONTEXT_GAP findings.

The neutral half of split plan §3.10 row 13: grouping, obligation severity, `release_impact`, the weakest recurrence
band, `witnessed`, the aggregate decider, proof status, mitigations, ids, explanations and order. The scenario label
of each turn (the fingerprint input, and the rc1 `traps` field) and the scenario severity are read from the bundle's
adapter-only producer-declared `scenarios` (`{turns: [{turn_index, label}], severity: {label: severity}}`; null labels
without it). The context refs of a failing claim come from the declared context-link rows (`ctx_key_of`,
`ctx_refs_of_key`).
"""
from eio_agents.semantics import IMP_ORDER, SEVR, ids


def findings(P, band_of, claim_proven, gaps):
    """The findings of a projection `P` (see `eio_agents.per.project`), sorted; `gaps` are the CONTEXT_GAP inputs
    `{criterion, control, ref, files, chars, terms}`."""
    eio = P.eio
    grp = {}
    for c in P.claims:
        if c["state"] != "APPLICABLE_FAIL" or eio.polarity(c["predicate"]) == "observation":
            continue                                                                    # PROD-31 (EIO-34)
        major = int(c["predicate_version"].split(".")[0])
        # the recipe's label slot takes the label's record value: a trap-library label in clear, any other label as its
        # fingerprint (decision #31; the verifier recomputes it from the record's `traps`)
        fp = ids.behavioural_fingerprint(c["predicate"], major, P.label_value(P.scenario_of(c)))
        grp.setdefault(fp, []).append(c)
    obl_rows = {o["id"]: o for o in P.obligations}
    F = []
    for fp, cl in grp.items():
        pred = cl[0]["predicate"]
        pd = eio.pred[pred]
        major = int(cl[0]["predicate_version"].split(".")[0])
        obs = [o for o in P.obligations if o["predicate"] == pred and o["required"] is not False]
        sev = max((o["severity"] for o in obs), key=lambda s: SEVR[s]) if obs else None
        sev_ids = sorted(o["id"] for o in obs if o["severity"] == sev) if sev else []
        ri = max((obl_rows[x]["release_impact"] for x in sev_ids), key=IMP_ORDER.index) if sev_ids else None
        wb = min((band_of(c) for c in cl), key=lambda b: P.BR[b["band"]])
        witnessed = any(P.witnessing_anchored(r) for c in cl for r in c["evidence"])
        dec = ("deterministic" if any(c["decided_by"] == "deterministic" for c in cl)
               else ("human" if any(c["decided_by"] == "human" for c in cl) else "semantic"))
        exact = any(P.fidelity(c) == "exact" for c in cl)
        proven = any(claim_proven(c) for c in cl)
        label = P.scenario_of(cl[0])
        turns = sorted({t for c in cl for t in c["turn_indices"]})
        labels = sorted({P.scenario_of(c) for c in cl} - {None})       # the declared scenario labels ([] without any)
        fid = ids.finding_id(P.run_id, fp)
        f = {"finding_id": fid, "fingerprint": fp, "issue_signature": ids.issue_signature(pred, major), "kind": "BEHAVIOURAL",
             "predicate": pred, "predicate_version": cl[0]["predicate_version"]}
        if pd.get("risk"):
            f["risk"] = pd["risk"]
        kinds = [P.refs[r]["kind"] for c in cl if c["decided_by"] in ("deterministic", "human")
                 for r in c["evidence"] if P.witnessing_anchored(r)]
        kinds = sorted(dict.fromkeys(kinds), key=P.KIND_ORDER.index)
        f.update({"display_label": "t%02d · %s" % (turns[0], pred.replace("eio.predicate.", "")), "status": "OPEN",
                  "claim_ids": [c["id"] for c in cl], "turn_indices": turns, "traps": labels, "severity": sev,
                  "severity_source": {"kind": "OBLIGATION" if sev else "NONE", "obligation_ids": sev_ids},
                  "scenario_severity": P.scenario_severity(label), "release_impact": ri,
                  "mapping_relation": "exact" if exact else "narrower", "decided_by": dec, "witnessed": witnessed,
                  "proof_status": "PROVEN" if proven else "UNPROVEN", "recurrence": wb,
                  "mitigations": [{"category": m["category"], "action": m["action"], "verification": m["verification"]}
                                  for m in pd.get("mitigations") or []],
                  "control_ids": []})
        params = {"predicate": pred, "turns": turns, "traps": labels, "decided_by": dec, "evidence_kinds": kinds,
                  "mapping_relation": f["mapping_relation"],
                  "recurrence": {"band": wb["band"], "reproduced_in": wb["reproduced_in"], "retests": wb["retests"]},
                  "proof_status": f["proof_status"]}
        if sev:
            params.update({"severity": sev, "severity_source": sev_ids})
            tid = "eio.why.finding@1"
        else:
            tid = "eio.why.finding.no_severity@1"
        keys = [k for k in dict.fromkeys(P.ctx_key_of(c) for c in cl) if k is not None]
        ctx = [x for k in keys for x in P.ctx_refs_of_key(k)]
        f["explanation"] = P.claim_driven(tid, params, cl, "violation", ctx=list({x["ref_id"]: x for x in ctx}.values()))
        F.append(f)
        if sev is None:
            P.lim("per.lim.severity.none", finding_id=fid, predicate=pred)
    for g in gaps:
        fp = ids.context_gap_fingerprint(g["criterion"], g["control"])
        fid = ids.finding_id(P.run_id, fp)
        params = {"criterion": g["criterion"], "control": g["control"], "files": g["files"], "chars": g["chars"], "terms": g["terms"]}
        F.append({"finding_id": fid, "fingerprint": fp, "issue_signature": ids.context_gap_issue_signature(g["criterion"]),
                  "kind": "CONTEXT_GAP", "criterion": g["criterion"], "control": g["control"],
                  "display_label": "ctx · " + g["criterion"].replace("eio.context.", "") + " / " + g["control"], "status": "OPEN",
                  "claim_ids": [], "turn_indices": [], "traps": [], "severity": None,
                  "severity_source": {"kind": "NONE", "obligation_ids": []}, "scenario_severity": None, "release_impact": None,
                  "mapping_relation": None, "decided_by": "deterministic", "witnessed": False, "proof_status": "UNPROVEN",
                  "recurrence": {"band": "NOT_RETESTED", "retests": 0, "reproduced_in": 0, "trial_kind": None, "ledger_key": None},
                  "mitigations": [], "control_ids": [], "evidence_refs": [g["ref"]],
                  "explanation": P.explanation("eio.why.finding.context_gap@1", params, dict(P.ZB), [], [g["ref"]], [])})
        P.lim("per.lim.context_gap.no_claim", finding_id=fid)
    F.sort(key=lambda f: (-(SEVR.get(f["severity"], 0)), f["kind"] == "CONTEXT_GAP",
                          f["turn_indices"][0] if f["turn_indices"] else 10 ** 6, f["finding_id"]))
    return F
