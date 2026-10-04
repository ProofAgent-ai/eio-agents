"""Id recipes: evidence-ref ids, claim ids, finding fingerprints and ids, issue signatures and the cited-refs hash.

Every id is `stable_digest(payload, 20)` over the payloads below (03 PROD-13, §6.2); a fingerprint is the full sha256 hex.
"""
import hashlib

from eio_agents.base.canon import jb, sd


def ref_id(kind, source_type, turn_index, x, char_start=None, char_end=None, valid_from=None, valid_until=None):
    """Evidence-ref id: content-addressed; excludes the predicate and the anchor (03 ID-3)."""
    return sd({"k": kind, "s": source_type, "t": turn_index, "x": x, "a": char_start, "b": char_end,
               "vf": valid_from, "vu": valid_until})


def claim_id(run_id, predicate, predicate_version, legacy_check, turn_indices):
    """Claim id (03 ID-1, ID-2). The rc1 recipe keeps the `legacy_check` slot; a native claim puts null there."""
    return sd({"run_id": run_id, "predicate": predicate, "predicate_version": predicate_version,
               "legacy_check": legacy_check, "turn_indices": turn_indices})


def claim_id_slot(parameters):
    """The value of the claim-id recipe's source-key slot for a claim's parameters: the rc1 `legacy_check` (null for a
    native claim). The one place outside the adapter that reads this parameter (renamed `source_key` at L5a, LS4)."""
    return parameters.get("legacy_check")


def claim_id_of(claim):
    """The id a claim object recomputes to."""
    return claim_id(claim["run_id"], claim["predicate"], claim["predicate_version"], claim_id_slot(claim["parameters"]),
                    claim["turn_indices"])


def behavioural_fingerprint(predicate, predicate_major, trap):
    """Fingerprint v1 of a BEHAVIOURAL finding (03 ID-4 to ID-6). `trap` is the scenario label (LS5 keeps the key until S7)."""
    return hashlib.sha256(jb({"v": 1, "predicate": predicate, "predicate_major": predicate_major, "trap": trap})).hexdigest()


def context_gap_fingerprint(criterion, control):
    """Fingerprint v1 of a CONTEXT_GAP finding."""
    return hashlib.sha256(jb({"v": 1, "criterion": criterion, "control": control})).hexdigest()


def finding_id(run_id, fingerprint, proof_status=None):
    """Finding id. `proof_status` is given only for the UNPROVEN part of a behavioural fingerprint that is split by
    proof status (strict native proof, 0.8.3): its PROVEN part keeps the plain recipe, so the two ids differ."""
    if proof_status is None:
        return sd({"run_id": run_id, "fingerprint": fingerprint})
    return sd({"run_id": run_id, "fingerprint": fingerprint, "proof_status": proof_status})


def issue_signature(predicate, major):
    """Issue signature of a BEHAVIOURAL finding: predicate and predicate major version."""
    return sd({"predicate": predicate, "major": major})


def context_gap_issue_signature(criterion, major=1):
    """Issue signature of a CONTEXT_GAP finding."""
    return sd({"criterion": criterion, "major": major})


def cited_refs_hash(ref_ids):
    """`evidence.cited_refs_hash`: stable_digest of the sorted ids of the carried refs."""
    return sd(sorted(ref_ids))
