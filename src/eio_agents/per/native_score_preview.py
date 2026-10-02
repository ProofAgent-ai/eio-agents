"""Unpublished draft native scored-PER projection.

The block is bound to a source-checked null-score PER and the pinned draft
profile/ontology. The independent public D4 verifier checks its values again
from the original bundle; this producer is never its own score authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require
from eio_agents.ontology import load as load_ontology
from eio_agents.per.native_score_inputs import extract_native_inputs
from eio_agents.scoring import profiles
from eio_agents.scoring.reference import score_native


SCHEMA = Path(__file__).resolve().parents[1] / "schemas/scoring/native-score-block-0.2.0-draft.1.schema.json"
PER_SCHEMA = Path(__file__).resolve().parents[1] / "schemas/per/per-2.0.0-rc3-draft.schema.json"
SCORE_BASIS_VERSION = "eio-agents.score-basis/0.2.0-draft.1"
NO_SCORING_PROFILE_ID = "per.lim.scoring_profile.none"
_WITHHELD = {
    "no applicable decided claim": "NO_APPLICABLE_CLAIM",
    "missing native scenario binding": "SCENARIO_BINDING_ABSENT",
    "missing or unknown native scenario severity": "SCENARIO_SEVERITY_ABSENT",
    "tools exposed but none called": "TOOLS_NOT_USED",
    "local context text absent or digest-mismatched": "CONTEXT_ARTIFACT_UNVERIFIED",
    "applicable assessor rating missing": "ASSESSOR_RATING_ABSENT",
    "no context criterion evaluated": "NO_CONTEXT_CRITERION",
    "fewer than six observed control statuses": "CONTROL_SAMPLE_INSUFFICIENT",
    "evidence freshness not verified": "FRESHNESS_UNVERIFIED",
    "reportable and decisive findings not independently rederived": "DECISIVE_SET_UNVERIFIED",
}


def _reason(text):
    if text is None:
        return None
    require(text in _WITHHELD, "NATIVE_SCORE_PREVIEW", "unreviewed score withholding reason")
    return _WITHHELD[text]


def _schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _score_basis_sha256(record):
    """Hash the versioned PER score basis without producer re-projection.

    The same projection is available from an unscored source PER and from the
    scored PER received by an independent verifier. Only the top-level score
    and the exact no-scoring-profile limitation are excluded; every other PER
    field, including provenance and ontology pins, remains bound to the hash.
    """
    require(isinstance(record, dict) and isinstance(record.get("limitations"), list),
            "NATIVE_SCORE_BASIS", "PER score basis needs an object and limitation rows")
    limitations = record["limitations"]
    require(all(isinstance(row, dict) and isinstance(row.get("limitation_id"), str)
                for row in limitations), "NATIVE_SCORE_BASIS", "PER limitation rows are malformed")
    no_profile = [row for row in limitations if row["limitation_id"] == NO_SCORING_PROFILE_ID]
    require(len(no_profile) <= 1, "NATIVE_SCORE_BASIS", "duplicate score-only limitation")
    if record.get("scores") is None:
        require(len(no_profile) == 1, "NATIVE_SCORE_BASIS", "unscored PER lacks its no-profile limitation")
    else:
        require(not no_profile, "NATIVE_SCORE_BASIS", "scored PER retains its no-profile limitation")
    basis = copy.deepcopy({key: value for key, value in record.items() if key != "scores"})
    basis["limitations"] = [row for row in limitations if row["limitation_id"] != NO_SCORING_PROFILE_ID]
    return H(jb(basis))


def score_block_problems(block, unscored_per, *, ontology=None):
    """Candidate-only shape/digest checks, not independent arithmetic verification."""
    schema = _schema()
    problems = [e.message for e in Draft202012Validator(schema).iter_errors(block)]
    if not isinstance(block, dict):
        return problems
    if ontology is None:
        ontology = load_ontology()
    if block.get("score_basis_version") != SCORE_BASIS_VERSION:
        problems.append("unknown PER score-basis normalization")
    if block.get("score_basis_sha256") != _score_basis_sha256(unscored_per):
        problems.append("PER score-basis digest differs")
    if block.get("score_sha256") != H(jb({k: v for k, v in block.items() if k != "score_sha256"})):
        problems.append("draft score block digest differs")
    profile = block.get("scoring_profile")
    if isinstance(profile, dict) and profile.get("ontology_sha256") != unscored_per["header"]["eio"]["ontology_sha256"]:
        problems.append("profile ontology pin differs from PER header")
    if unscored_per["header"]["eio"]["ontology_sha256"] != ontology.ontology_sha256:
        problems.append("PER ontology pin differs from loaded release")
    document = profiles.reference_document(ontology)
    if profile != {**profiles.record_profile(document), "ontology_sha256": ontology.ontology_sha256}:
        problems.append("profile identity or digest differs from loaded registry")
    if [row.get("metric") for row in block.get("metrics", []) if isinstance(row, dict)] != document["published_metrics"]:
        problems.append("metric rows differ from profile's complete ordered metric set")
    if [row.get("axis") for row in block.get("axes", []) if isinstance(row, dict)] != document["parameters"]["axis_order"]:
        problems.append("axis rows differ from profile's complete ordered axis set")
    checked_claims = {row["id"] for row in unscored_per["claims"]}
    for row in block.get("metrics", []):
        if isinstance(row, dict) and not (set(row.get("member_claim_ids", [])) | set(row.get("cap_claim_ids", []))) <= checked_claims:
            problems.append("metric cites claim outside verified PER")
    return problems


def project_native_score_preview(bundle, unscored_per, verification, *, ontology):
    """Build a draft score block from a D1/D2/D5-checked native null-score PER.

    Numeric readiness and G remain withheld until freshness policy is
    independently approved and verified. The public D4 verifier independently
    recomputes every emitted partial score from the source bundle.
    """
    require(isinstance(unscored_per, dict) and unscored_per.get("scores") is None,
            "NATIVE_SCORE_PREVIEW", "input PER must have null scores")
    require(isinstance(verification, dict) and verification.get("valid") is True
            and verification.get("digest_match") is True
            and verification.get("per_sha256") == H(jb(unscored_per)),
            "NATIVE_SCORE_PREVIEW", "input PER needs digest-matched independent verification")
    inputs = extract_native_inputs(bundle, ontology=ontology, record=unscored_per, verification=verification)
    require(inputs is not None, "NATIVE_SCORE_PREVIEW", "bundle has no native score sources")
    document = profiles.reference_document(ontology)
    # Current R8 scorer expands decisive findings to all their claim IDs.
    # A finding can mix decisive and nondecisive claims.  This preview never
    # supplies finding sets to that path, even if a later extractor derives
    # them, until exact independently checked decisive claim IDs are wired.
    safe_inputs = dict(inputs, reportable_finding_ids=None, decisive_finding_ids=None)
    draft = score_native(**safe_inputs, ontology=ontology, profile=document)
    require(draft["profile_sha256"] == profiles.profile_sha256(document)
            and draft["ontology_sha256"] == ontology.ontology_sha256,
            "NATIVE_SCORE_PREVIEW", "draft scoring basis differs from registry release")

    claim_ids = {claim["id"] for claim in unscored_per["claims"]}
    metrics = []
    for mid in document["published_metrics"]:
        row = draft["metrics"][mid]
        members = sorted(row["members"])
        require(set(members) <= claim_ids, "NATIVE_SCORE_PREVIEW", "metric member is not a checked PER claim")
        metrics.append({"metric": mid, "value": row["value"], "member_claim_ids": members,
                        "pre_cap": row.get("pre_cap"), "cap_claim_ids": sorted(row.get("cap_claim_ids", [])),
                        "context_ceiling": row.get("context_ceiling"),
                        "status": "WITHHELD" if row["value"] is None else "MEASURED",
                        "withheld_code": _reason(row.get("withheld"))})
    details = draft["axis_details"]
    bases = {
        "eio.axis.context": sorted(details["context"]["criteria"]),
        "eio.axis.behaviour": [m["metric"] for m in metrics if m["value"] is not None],
        "eio.axis.compliance": sorted(details["compliance_axis"]["per_framework"]),
        "eio.axis.governance": [],
    }
    axis_reason = {
        "eio.axis.context": details["context"]["withheld"],
        "eio.axis.behaviour": "no applicable decided claim" if draft["axes"]["eio.axis.behaviour"] is None else None,
        "eio.axis.compliance": details["compliance_axis"]["withheld"],
        "eio.axis.governance": details["governance"]["withheld"],
    }
    axes = [{"axis": aid, "value": draft["axes"][aid], "basis_ids": bases[aid],
             "status": "WITHHELD" if draft["axes"][aid] is None else "MEASURED",
             "withheld_code": _reason(axis_reason[aid])}
            for aid in document["parameters"]["axis_order"]]
    # A numeric R8 cap cannot be inferred from all claims in a decisive
    # finding.  Deliberately publish no draft readiness, cap or grade here.
    reasons = ["INDEPENDENT_PROOF_PENDING"]
    if not inputs["freshness_verified"]:
        reasons.append("FRESHNESS_UNVERIFIED")
    reasons.append("DECISIVE_SET_UNVERIFIED")
    block = {"kind": "reference-draft", "scoring_profile": {
                 **profiles.record_profile(document), "ontology_sha256": ontology.ontology_sha256},
             "score_basis_version": SCORE_BASIS_VERSION,
             "score_basis_sha256": _score_basis_sha256(unscored_per), "metrics": metrics, "axes": axes,
             "readiness": {"value": None, "status": "WITHHELD", "withheld_codes": reasons}}
    block["score_sha256"] = H(jb(block))
    problems = score_block_problems(block, unscored_per, ontology=ontology)
    require(not problems, "NATIVE_SCORE_PREVIEW_SCHEMA", f"draft score block invalid: {problems[:2]}")
    return block


def candidate_scored_per(unscored_per, block):
    """Assemble a candidate scored PER against the one static rc3 schema."""
    require(isinstance(unscored_per, dict) and unscored_per.get("scores") is None,
            "NATIVE_SCORE_PREVIEW", "candidate requires a null-score source PER")
    require(not score_block_problems(block, unscored_per), "NATIVE_SCORE_PREVIEW", "draft score block is invalid")
    candidate = copy.deepcopy(unscored_per)
    candidate["scores"] = copy.deepcopy(block)
    candidate["limitations"] = [row for row in candidate["limitations"]
                                if row["limitation_id"] != NO_SCORING_PROFILE_ID]
    require(_score_basis_sha256(candidate) == block["score_basis_sha256"],
            "NATIVE_SCORE_BASIS", "scored PER score basis differs from the checked null-score source")
    schema = json.loads(PER_SCHEMA.read_text(encoding="utf-8"))
    problems = [e.message for e in Draft202012Validator(schema).iter_errors(candidate)]
    require(not problems, "NATIVE_SCORE_PREVIEW_SCHEMA", f"candidate PER invalid: {problems[:2]}")
    return candidate
