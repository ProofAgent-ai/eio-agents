"""Proof status (eio.profile.proof-status), selected by the pinned release.

The historical 0.4 rule below remains for its own pinned release and adapter
records. A new native S1b release may select citation-bound proof instead; its
ontology/profile digest must be reissued before that branch is public.

Historical rule over declared fidelity (split plan §3.3, §3.10 row 12):

A claim is PROVEN iff
- it is decided deterministically or by a human;
- it cites a witnessing anchored ref that witnesses its predicate (`witnesses`: a STATE_FACT witnesses only a predicate
  whose evidence contract names STATE_FACT; L3 fix round 1, issue 8), and its evidence contract does not record W1 unmet
  (`no_witnessing_ref` in `parameters.contract_check.unmet`: no witnessing ref inside the contract scope;
  eio.profile.witness-rule W1 "the unmet rule is recorded ... and the claim is not PROVEN"; L2 exit D-35, F-7); and
- its declared `parameters.fidelity` is `exact`, or its recurrence band is CONFIRMED.

`fidelity` is required on every bundle claim: an adapter derives it from its crosswalk (the ProofAgent adapter sets it to
the rc1 mapping relation), a native producer declares it. There is no exemption by provenance: the rc1 rule counted a
claim with a null source key as exact, so any claim without a key was PROVEN without recurrence; that exemption is
deleted (L2). Golden bytes are unchanged, because every golden claim has a source key and fidelity = mapping relation.
The native fidelity is disclosed by a core limitation until the S5 registry (from L5a).
"""


from collections import Counter

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require

STATE_FACT = "STATE_FACT"


def contract_kinds(eio, predicate):
    """The evidence kinds the predicate's evidence contract names (require_all, require_any, require_groups); empty when it
    declares none."""
    ec = eio.pred[predicate].get("evidence_contract") or {}
    return set(ec.get("require_all") or []) | set(ec.get("require_any") or []) | {k for g in ec.get("require_groups") or [] for k in g}


def witnesses(eio, ref, predicate):
    """Whether `ref` is a witnessing anchored ref for a claim on `predicate`. A STATE_FACT over a declared state snapshot
    is true when rebuilt, but it states only that the snapshot is non-empty: it witnesses only a predicate whose evidence
    contract names STATE_FACT, and any other claim it cannot prove (L3 fix round 1, issue 8: rebuilt means true, not
    relevant)."""
    return eio.witnessing_anchored(ref) and (ref["kind"] != STATE_FACT or STATE_FACT in contract_kinds(eio, predicate))


def w1_unmet(claim):
    """Whether the claim's recorded evidence contract says W1 is unmet (`no_witnessing_ref`): no witnessing anchored ref
    inside the contract scope (01 §6.5; `evidence.contract.contract_check`)."""
    return "no_witnessing_ref" in (((claim.get("parameters") or {}).get("contract_check") or {}).get("unmet") or [])


def claim_proven(eio, claim, refs, band, fidelity):
    """Whether `claim` is PROVEN; `refs` maps ref id -> ref, `band` is the claim's recurrence band and `fidelity` its
    declared fidelity (`exact` or `narrower`). A witnessing ref outside the contract scope does not prove the claim (W1),
    nor a state fact outside the predicate's evidence contract (`witnesses`)."""
    return (claim["decided_by"] in ("deterministic", "human") and any(witnesses(eio, refs[r], claim["predicate"]) for r in claim["evidence"])
            and not w1_unmet(claim) and (fidelity == "exact" or band == "CONFIRMED"))


def checked_native_citations(eio, claims, refs, rows, in_scope):
    """Validate every draft S1b proof assertion after source ref recomputation.

    The citation's role and anchor must be declared at claim level; a strong
    ref-level anchor alone never upgrades a citation (FINDING7).  ``in_scope``
    is the projector's evidence-contract scope predicate.
    """
    claims_by_id = {claim["id"]: claim for claim in claims}
    pairs = Counter((row["claim_id"], row["ref_id"]) for row in rows)
    require(all(count == 1 for count in pairs.values()), "NATIVE_PROOF", "duplicate proof citation")
    by_claim = {}
    for row in rows:
        cid, rid = row["claim_id"], row["ref_id"]
        require(cid in claims_by_id and rid in refs and rid in claims_by_id[cid]["evidence"],
                "NATIVE_PROOF", "proof citation must target a source claim and its own ref")
        claim, ref = claims_by_id[cid], refs[rid]
        contract = eio.pred[claim["predicate"]].get("evidence_contract") or {}
        first = next((set(group) for group in contract.get("require_groups") or []
                      if any(eio.kind[k]["can_prove_agent_behaviour"] for k in group)), None)
        require(first is not None and ref["kind"] in first and
                eio.kind[ref["kind"]]["can_prove_agent_behaviour"],
                "NATIVE_PROOF", "proof citation requires a proof-eligible kind in the first eligible group")
        require(row["role"] == "proof" and row["citation_anchor"] in eio.witnessing_anchors and
                row["citation_anchor"] == ref["anchor"] and row["locator_sha256"] == H(jb(ref)),
                "NATIVE_PROOF", "proof citation role, anchor and complete locator digest disagree")
        require(witnesses(eio, ref, claim["predicate"]) and in_scope(ref, contract["scope"], claim),
                "NATIVE_PROOF", "proof citation does not witness this claim inside its contract scope")
        by_claim.setdefault(cid, []).append(row)
    return by_claim


def native_claim_proven(claim, band, fidelity, checked_citations):
    """New-release S1b proof rule; never inherit 0.4 native_claim_proves.

    ``checked_citations`` come from ``checked_native_citations`` after the
    bundle, stage digest, ontology and source ref recipes have been verified.
    Missing claim-level proof is UNPROVEN even for exact native claims.
    """
    unmet = (((claim.get("parameters") or {}).get("contract_check") or {}).get("unmet") or [])
    # Counterevidence is disclosed as deferred; every other contract gap
    # blocks proof, including a missing policy or the minimum ref count.
    return (claim["decided_by"] in ("deterministic", "human") and bool(checked_citations)
            and all(item == "counterevidence" for item in unmet)
            and (fidelity == "exact" or band == "CONFIRMED"))
