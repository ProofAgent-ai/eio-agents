"""Reliability (03 §7.11, §10): the recurrence band of a claim, the band order and the reliability block.

Everything here reads the bundle `trials` section (carry note 3; split plan §3.10 row 17):

    trials = {"trial_kind", "passes", "k", "tasks", "rate": {"pass_1", "pass_k", "pass_1_se", "pass_k_se"},
              "records": [{"claim_id", "ledger_key", "trial_kind", "reproduced_in", "passes", "may_auto_block"}],
              "named_lists": {...}}

or None when no re-test trials were run. How a producer's run log becomes trial records is the producer's part.
"""
from collections import Counter

from eio_agents.base.canon import q4
from eio_agents.base.errors import require

BR = {"NOT_RETESTED": 0, "UNCONFIRMED": 1, "INTERMITTENT": 2, "CONFIRMED": 3}   # band order, weakest first
NOT_RETESTED = {"band": "NOT_RETESTED", "retests": 0, "reproduced_in": 0, "trial_kind": None, "ledger_key": None}


def band_of(trial, passes):
    """The recurrence of one claim from its trial record (None when it has none) and the run's re-test pass count:
    CONFIRMED when reproduced in every pass, UNCONFIRMED in none, else INTERMITTENT."""
    if not trial or not passes:
        return dict(NOT_RETESTED)
    r, n = int(trial["reproduced_in"]), int(trial["passes"])
    b = "CONFIRMED" if r == n > 0 else ("UNCONFIRMED" if r == 0 else "INTERMITTENT")
    return {"band": b, "retests": n, "reproduced_in": r, "trial_kind": trial["trial_kind"], "ledger_key": trial["ledger_key"]}


def trial_index(trials):
    """claim id -> its trial record (the last record of a claim wins, as a re-test ledger keyed by claim)."""
    return {x["claim_id"]: x for x in (trials or {}).get("records") or []}


def reliability_block(eio, trials, claims, findings, claim_finding, claim_driven, basis):
    """The PER reliability block. `claim_finding` maps claim id -> finding id; `claim_driven(tid, params, claims, role,
    bas=None)` and `basis(claims)` build explanations."""
    by_id = {c["id"]: c for c in claims}
    occ = [{"finding_id": f["finding_id"], "claim_ids": f["claim_ids"], "occurred": True} for f in findings if f["kind"] == "BEHAVIOURAL"]
    if trials is None:
        cl = [by_id[x] for o in occ for x in o["claim_ids"]]
        return {"status": "NOT_RETESTED", "trial_kind": None, "passes": 0, "k": None, "tasks": None,
                "occurrence": occ, "recurrence": [], "rate": None, "named_lists": None,
                "explanation": claim_driven("eio.why.reliability.not_retested@1", {"n_findings": len(occ)}, cl, "violation")}
    idx, passes = trial_index(trials), int(trials["passes"])
    recs = []
    for c in claims:
        x = idx.get(c["id"])
        if not x:
            continue
        b = band_of(x, passes)
        recs.append({"ledger_key": b["ledger_key"], "finding_id": claim_finding.get(c["id"]), "claim_id": c["id"], "retests": b["retests"],
                     "reproduced_in": b["reproduced_in"], "band": b["band"], "may_auto_block": bool(x.get("may_auto_block"))})
    nb = Counter(r["band"] for r in recs)
    tasks = int(trials["tasks"] or 0)
    published = tasks >= eio.minimum_tasks
    # below the floor the estimate is suppressed, not shown (03 schema reliability_rate: published false -> values null)
    raw = trials["rate"]
    # L3 fix round 3 (an untyped TypeError before): a published rate states its four values (the schema admits null for the
    # values a rate below the floor suppresses)
    null = sorted(k for k in ("pass_1", "pass_k", "pass_1_se", "pass_k_se") if raw.get(k) is None) if published else []
    require(not null, "BUNDLE_SCHEMA", f"trials.rate {null} null, but the rate is published ({tasks} tasks, the floor "
            f"{eio.minimum_tasks}): a published reliability rate states its values (03 schema reliability_rate)")
    est = (lambda key: q4(raw[key])) if published else (lambda key: None)
    rate = {"pass_1": est("pass_1"), "pass_k": est("pass_k"), "pass_1_se": est("pass_1_se"), "pass_k_se": est("pass_k_se"),
            "published": published, "suppressed_state": None if published else "RATE_NOT_PUBLISHED",
            "floor": eio.minimum_tasks, "denominator": "flagged"}
    k = int(trials["k"])
    conf = [by_id[r["claim_id"]] for r in recs if r["band"] == "CONFIRMED"]
    params = {"passes": passes, "trial_kind": trials["trial_kind"], "tasks": tasks, "confirmed": nb["CONFIRMED"],
              "intermittent": nb["INTERMITTENT"], "unconfirmed": nb["UNCONFIRMED"], "k": k, "pass_k": rate["pass_k"],
              "pass_k_se": rate["pass_k_se"], "publication": published, "floor": eio.minimum_tasks}
    expl = claim_driven("eio.why.reliability@1", params, conf, "violation", bas=basis([by_id[r["claim_id"]] for r in recs]))
    return {"status": "EVALUATED", "trial_kind": trials["trial_kind"], "passes": passes, "k": k,
            "tasks": tasks, "occurrence": occ, "recurrence": recs, "rate": rate, "named_lists": trials["named_lists"],
            "explanation": expl}
