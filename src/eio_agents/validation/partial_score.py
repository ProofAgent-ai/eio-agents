"""Candidate public D4 rule for a measured/withheld native score block.

No producer, PER projector, or scoring implementation is imported here. The
public verifier may call this only after its own D1/D2 record and source
checks, with a separately pinned profile document and score-block schema.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from eio_agents.validation.canon import jb, sha
from eio_agents.validation.native_score import (
    ScoreInputError,
    checked_native_finding_severity,
    derive_proof_sets,
    high_review_guard,
    native_proof_status_gate,
)
from eio_agents.validation.score_basis import SCORE_BASIS_VERSION
from eio_agents.validation.score_block_diagnostic import diagnose_draft_score_block


PROFILE_ID = "eio-agents.reference-scoring"
PROFILE_VERSION = "0.2.0-draft.1"
EIO_RELEASE = "0.5.0-draft.1"
_INTENTIONAL_HOLD = "D4: G/readiness intentionally withheld pending freshness and HIGH severity"
PINNED_PROFILE_SHA256 = "sha256:162469a405345a36a345d4ee8d2de6671a5c8462dde24a721bc5e7e1533898e2"
PINNED_SCORE_SCHEMA_SHA256 = "sha256:6c6db2d20a20f831d15e1dab6fdc2420e0aceb7b2c84fb8dc714e544a86a70a2"
_PACKAGE = Path(__file__).resolve().parents[1]


def load_verifier_score_resources():
    """Read verifier-owned frozen resources, independent of scoring registry."""
    profile_path = Path(__file__).resolve().parent / "data/reference-profile-0.2.0-draft.1.json"
    schema_path = _PACKAGE / "schemas/scoring/native-score-block-0.2.0-draft.1.schema.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    schema_raw = schema_path.read_bytes()
    if sha(jb(profile)) != PINNED_PROFILE_SHA256 or sha(schema_raw) != PINNED_SCORE_SCHEMA_SHA256:
        raise ScoreInputError("verifier-owned score profile or schema digest differs from the pinned draft")
    return profile, json.loads(schema_raw)


def partial_native_score_gate(bundle, record, eio, *, source_checked,
                              approved_profile=None, approved_schema=None):
    """Return VER-style problems for a 0.2 partial native score candidate.

    G and readiness MUST be null/WITHHELD while freshness is unresolved. All
    emitted metric/Q/E/C values, statuses, ids, cap/context fields, profile
    and digests must match the independent source recomputation. The caller
    must source the profile and schema from verifier-owned pinned resources,
    never from this PER or its producer. Missing resources fail closed.
    """
    if source_checked is not True:
        return ["D2 source locator checks are not independently passed"], ""
    if eio.release != EIO_RELEASE:
        return ["partial native scoring requires the pinned draft EIO 0.5 release"], ""
    if (eio.profiles.get("eio.profile.proof-status") or {}).get("native_claim_proves") is not False:
        return ["partial native scoring requires the strict pinned S1b proof rule"], ""
    if not isinstance(approved_profile, dict) or not isinstance(approved_schema, dict):
        return ["verifier-owned 0.2 profile document and score schema are not pinned"], ""
    if (approved_profile.get("id") != PROFILE_ID
            or approved_profile.get("version") != PROFILE_VERSION
            or approved_profile.get("ontology_sha256") != sha(jb(dict(sorted(eio.module_sha.items()))))):
        return ["verifier-owned scoring profile does not bind the pinned release"], ""
    block = record.get("scores") if isinstance(record, dict) else None
    if not isinstance(block, dict) or block.get("score_basis_version") != SCORE_BASIS_VERSION:
        return ["scored PER lacks the 0.2 versioned score basis"], ""
    try:
        Draft202012Validator.check_schema(approved_schema)
        schema_problems = [error.message for error in Draft202012Validator(approved_schema).iter_errors(block)]
        if schema_problems:
            return [f"score block schema: {problem}" for problem in schema_problems], ""
        proof_problems, _ = native_proof_status_gate(bundle, record, eio)
        if proof_problems:
            return [f"D5 native proof: {problem}" for problem in proof_problems], ""
        severity = checked_native_finding_severity(bundle, record, eio)
        proof = derive_proof_sets(bundle, record, eio)
        if proof["reportable_finding_ids"] is None:
            # No proof-role extension means no S1b reportable proof. The D5
            # gate independently requires every finding be UNPROVEN.
            if (bundle.get("native_scoring") or {}).get("proof_citations") is not None:
                return [f"HIGH-review proof set cannot be derived: {proof['withheld']}"], ""
            proof = {"reportable_finding_ids": []}
        state = (record.get("release_recommendation") or {}).get("state")
        review = high_review_guard(state, record["findings"], proof, checked_severity=severity)
        if review["state"] != state:
            return ["claimed PASS bypasses a source-bound unresolved HIGH review item"], ""
        source_token = {"valid": True, "digest_match": True, "per_sha256": sha(jb(record))}
        diagnostic = diagnose_draft_score_block(
            bundle, record, block, eio, approved_profile=approved_profile, verification=source_token
        )
    except (SchemaError, ScoreInputError, KeyError, TypeError, ValueError) as exc:
        return [f"partial native score cannot be independently rederived: {exc}"], ""
    if diagnostic["mismatches"]:
        return [f"independent score mismatch at {path}" for path in diagnostic["mismatches"]], ""
    if diagnostic["withheld"] != [_INTENTIONAL_HOLD]:
        return [f"independent score input withheld: {reason}" for reason in diagnostic["withheld"]
                if reason != _INTENTIONAL_HOLD], ""
    return [], "all emitted partial native score values independently rederived; G/readiness withheld"
