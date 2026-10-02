"""Experimental native D9 R1–R5 reportability and exact decisive-claim derivation.

The citation role/anchor is a native resolution declaration, never inferred
from a ref-level anchor. Source locator recomputation and the PER finding map
must already have passed the independent public verifier before this function
is called. The independent verifier implements its own twin of this rule.
"""
from __future__ import annotations

from collections import Counter

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require
from eio_agents.evidence.contract import contract_check, in_scope
from eio_agents.reliability import band_of, trial_index
from eio_agents.semantics.proof import native_claim_proven, witnesses


def _proof_group(ontology, predicate):
    """First evidence-contract group containing a can-prove kind (D9 R2)."""
    ec = ontology.pred[predicate].get("evidence_contract") or {}
    for index, group in enumerate(ec.get("require_groups") or [], 1):
        if any(ontology.kind[k]["can_prove_agent_behaviour"] for k in group):
            return index, set(group)
    return None


def derive_native_proof_sets(bundle, record, *, ontology, native_ids, verification):
    """Return D9 ID sets from verified sources, or ``None`` for an ontology gap.

    ``native_ids`` maps old bundle claim ID to its neutral PER ID. No PER release
    row, producer numeric input, or blanket all-findings assumption is read.
    Missing proof-citation declaration is unknown, not an empty proof set.
    """
    require(isinstance(verification, dict) and verification.get("valid") is True
            and verification.get("digest_match") is True
            and verification.get("per_sha256") == H(jb(record)), "NATIVE_PROOF",
            "proof sets need the independent verifier's digest-matched result for this exact record")
    scoring = bundle["native_scoring"]
    if "proof_citations" not in scoring:
        return None
    raw_claims = {c["id"]: c for c in bundle["claims"]}
    refs = {r["id"]: r for r in bundle["graph"]["refs"]}
    require(len(refs) == len(bundle["graph"]["refs"]), "NATIVE_PROOF", "duplicate evidence ref ID")
    citations = scoring["proof_citations"]
    pairs = Counter((row["claim_id"], row["ref_id"]) for row in citations)
    require(all(count == 1 for count in pairs.values()), "NATIVE_PROOF", "duplicate claim/ref proof citation")
    by_claim = {}
    for row in citations:
        cid, rid = row["claim_id"], row["ref_id"]
        require(cid in raw_claims and rid in refs and rid in raw_claims[cid]["evidence"], "NATIVE_PROOF",
                "a proof citation must name a ref cited by its source claim")
        ref = refs[rid]
        require(row["role"] == "proof" and row["citation_anchor"] in ontology.witnessing_anchors
                and row["citation_anchor"] == ref["anchor"] and row["locator_sha256"] == H(jb(ref)), "NATIVE_PROOF",
                "proof role, witnessing anchor and locator digest must bind this exact citation")
        group = _proof_group(ontology, raw_claims[cid]["predicate"])
        require(group is not None and ref["kind"] in group[1] and witnesses(ontology, ref, raw_claims[cid]["predicate"]),
                "NATIVE_PROOF", "proof ref kind is not in the first eligible evidence-contract group")
        by_claim.setdefault(cid, []).append(ref)

    episodes = [set(row) for row in bundle["graph"]["episodes"]]
    def episode_turns(turn_indices):
        matches = [ep for ep in episodes if set(turn_indices) <= ep]
        require(len(matches) == 1, "NATIVE_PROOF", "claim turns do not identify exactly one source episode")
        return matches[0]

    trials = trial_index(bundle["trials"])
    passes = int(bundle["trials"]["passes"]) if bundle["trials"] else 0
    reportable, decisive, diagnostics = set(), set(), {}
    for cid, claim in raw_claims.items():
        if claim["state"] != "APPLICABLE_FAIL" or ontology.polarity(claim["predicate"]) not in ("risk", "safeguard"):
            continue
        group = _proof_group(ontology, claim["predicate"])
        if group is None:
            # EIO 0.4.0 lacks a proof-eligible group for some predicates. An
            # empty result would incorrectly assert that these were assessed.
            return None
        ec = ontology.pred[claim["predicate"]]["evidence_contract"]
        check = contract_check(ontology, claim, refs, episode_turns)
        scoped = [ref for ref in by_claim.get(cid, []) if in_scope(ref, ec["scope"], claim, episode_turns)]
        band = band_of(trials.get(cid), passes)["band"]
        for_proof = dict(claim)
        for_proof["parameters"] = dict(claim["parameters"], contract_check=check)
        proven = native_claim_proven(for_proof, band, claim["parameters"]["fidelity"], by_claim.get(cid, []))
        r2 = bool(scoped)
        r3 = r2 and all(item == "counterevidence" for item in check["unmet"])
        r4 = proven or (claim["decided_by"] == "deterministic" and any(ref["anchor"] in ("exact", "receipt") for ref in scoped)
                        and (claim["parameters"]["fidelity"] == "exact"
                             or (claim["parameters"]["fidelity"] == "narrower" and band != "UNCONFIRMED")))
        r5 = proven or cid not in trials or band != "UNCONFIRMED"
        ok = r2 and r3 and r4 and r5
        diagnostics[native_ids[cid]] = {"reportable": ok, "proven": proven,
                                        "unmet": [key for key, good in (("R2", r2), ("R3", r3), ("R4", r4), ("R5", r5))
                                                  if not good],
                                        "deferred": [x for x in check["unmet"] if x == "counterevidence"]}
        if ok:
            reportable.add(native_ids[cid])
            if proven:
                decisive.add(native_ids[cid])

    found = {c for finding in record["findings"] for c in finding["claim_ids"] if finding["kind"] == "BEHAVIOURAL"}
    require(reportable <= found and decisive <= found, "NATIVE_PROOF",
            "a source-derived reportable claim has no verified behavioural finding")
    reportable_findings = sorted(f["finding_id"] for f in record["findings"] if set(f["claim_ids"]) & reportable)
    decisive_findings = sorted(f["finding_id"] for f in record["findings"] if set(f["claim_ids"]) & decisive)
    return {"reportable_finding_ids": reportable_findings, "decisive_finding_ids": decisive_findings,
            "decisive_claim_ids": sorted(decisive), "cap_decisive_claim_ids": sorted(
                cid for cid in decisive if next(c for c in record["claims"] if c["id"] == cid)["predicate"] in ontology.cap_preds),
            "reportability": diagnostics}
