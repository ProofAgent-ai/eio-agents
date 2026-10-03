"""Versioned PER 2.1.0 native full-score producer (reference scoring profile 0.3.1, release semantics 2.2).

The input is a null-score rc3 native PER that has passed independent D1/D2/D5
source checks. The source extractor rederives reportable and decisive IDs from
bundle citations. This unit never treats a producer's score or freshness flag
as authority. Historical rc3 conversion remains on its existing route.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require
from eio_agents.per.privacy import decisive_entry_text
from eio_agents.per.native_score_inputs import extract_native_inputs
from eio_agents.per.native_score_preview import _reason, _score_basis_sha256, NO_SCORING_PROFILE_ID
from eio_agents.scoring import profiles
from eio_agents.scoring.reference import score_native
from eio_agents.semantics import why as sem_why


PER_VERSION = "2.1.0"
SCHEMA_URI = "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
# Release semantics of PER 2.1.0 records. "2.1" (the unpublished 0.8.0 candidate) added the HIGH-review guard; "2.2"
# adds the no-policy default floor (owner decision #46): with no declared policy the state is REVIEW whenever
# readiness is below DEFAULT_READINESS_FLOOR (or withheld) or any HARD_BLOCK obligation is unmet. Never BLOCK.
RELEASE_SEMANTICS = "2.2"
HIGH_REVIEW_GUARD = "eio.release.high-review-queue"
DEFAULT_FLOOR_GUARD = "eio.release.default-readiness-floor"
HARD_BLOCK_GUARD = "eio.release.hard-block-unmet"
DEFAULT_READINESS_FLOOR = 85.0
POLICY_PER_VERSION = PER_VERSION
POLICY_SCHEMA_URI = SCHEMA_URI
SCORE_BASIS_VERSION = "eio-agents.score-basis/0.3.0"
SCORE_KIND = "reference"
REFERENCE_FULL_ID = profiles.REFERENCE_ID
REFERENCE_FULL_VERSION = profiles.REFERENCE_PUBLIC_VERSION
_ROOT = Path(__file__).resolve().parents[1] / "schemas"
SCORE_SCHEMA = _ROOT / "scoring/native-score-block-0.3.1.schema.json"
PER_SCHEMA = _ROOT / "per/per-2.1.0.schema.json"
POLICY_PER_SCHEMA = PER_SCHEMA


def _checked_schema(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _versioned_unscored(record):
    require(record["header"]["per_version"] == "2.0.0-rc3-draft" and record.get("scores") is None,
            "NATIVE_FULL_WIRE", "a verified rc3 null-score native PER is required")
    result = copy.deepcopy(record)
    result["header"]["per_version"] = PER_VERSION
    result["header"]["schema_uri"] = SCHEMA_URI
    result["header"]["release_semantics"] = RELEASE_SEMANTICS
    result["release_recommendation"]["semantics"] = RELEASE_SEMANTICS
    return result


def _apply_high_review_guard(record, finding_ids, *, ontology):
    """Promote source-derived unresolved HIGH findings to a versioned REVIEW condition."""
    require(isinstance(finding_ids, list) and finding_ids == sorted(set(finding_ids)),
            "NATIVE_FULL_WIRE", "HIGH review queue is not sorted and unique")
    release = record["release_recommendation"]
    if finding_ids:
        release["decisive"].append({"kind": "review_guard", "id": HIGH_REVIEW_GUARD,
                                    "expected": "no unresolved HIGH or CRITICAL findings",
                                    "observed": f"{len(finding_ids)} unresolved HIGH or CRITICAL finding(s)",
                                    "claim_ids": [], "finding_ids": finding_ids, "effect": "REVIEW"})
    release["state"] = ("BLOCK" if any(d["effect"] == "BLOCK" for d in release["decisive"]) else
                        "REVIEW" if release["decisive"] else "PASS")
    explanation = release["explanation"]
    if release["decisive"]:
        explanation["template_id"] = f"eio.why.release.{release['state'].lower()}@1"
        explanation["params"] = {"n_decisive": len(release["decisive"]),
                                 "decisive_list": [decisive_entry_text(record, d) for d in release["decisive"]],
                                 "n_contributing": len(release["contributing"]),
                                 "semantics": RELEASE_SEMANTICS}
    else:
        explanation["template_id"] = "eio.why.release.pass@1"
        explanation["params"] = {"n_contributing": len(release["contributing"]),
                                 "semantics": RELEASE_SEMANTICS}
    explanation["summary"] = sem_why.render(ontology, explanation["template_id"], explanation["params"])


def default_floor_guards(record, readiness):
    """The release-semantics 2.2 no-policy guards (owner decision #46) of a scored PER 2.1.0 record, in order: the
    default readiness floor (readiness below 85, or withheld) and unmet HARD_BLOCK obligations
    (`coverage.summary.hard_block_unmet > 0`). Empty when a policy is declared. Each is a REVIEW: no proven failure is
    implied, so it never BLOCKs (owner decision #2)."""
    release = record["release_recommendation"]
    if release["policy"]["source"] != "none":
        return []
    guards = []
    if readiness is None or readiness < DEFAULT_READINESS_FLOOR:
        guards.append({"kind": "review_guard", "id": DEFAULT_FLOOR_GUARD,
                       "expected": default_floor_text("expected", readiness),
                       "observed": default_floor_text("observed", readiness),
                       "claim_ids": [], "finding_ids": [], "field_refs": ["/scores/readiness/value"],
                       "effect": "REVIEW"})
    unmet = [o["id"] for o in record["coverage"]["obligations"]
             if o["met"] is False and o["release_impact"] == "HARD_BLOCK"]
    require(len(unmet) == record["coverage"]["summary"]["hard_block_unmet"], "NATIVE_FULL_WIRE",
            "coverage summary hard_block_unmet differs from the obligations")
    if unmet:
        guards.append({"kind": "review_guard", "id": HARD_BLOCK_GUARD,
                       "expected": "0",
                       "observed": str(len(unmet)),
                       "claim_ids": [], "finding_ids": [], "obligation_ids": sorted(unmet),
                       "field_refs": ["/coverage/summary/hard_block_unmet"], "effect": "REVIEW"})
    return guards


def default_floor_text(field, readiness):
    """The `expected`/`observed` text of the default readiness floor guard."""
    if field == "expected":
        return f"readiness >= {sem_why.fmt_score(DEFAULT_READINESS_FLOOR)}"
    return "withheld" if readiness is None else sem_why.fmt_score(readiness)


def _apply_default_floor_guards(record, readiness, *, ontology):
    """Append the no-policy default floor guards and re-render the release state and explanation."""
    release = record["release_recommendation"]
    guards = default_floor_guards(record, readiness)
    if not guards:
        return
    release["decisive"].extend(guards)
    release["state"] = ("BLOCK" if any(d["effect"] == "BLOCK" for d in release["decisive"]) else "REVIEW")
    explanation = release["explanation"]
    explanation["template_id"] = f"eio.why.release.{release['state'].lower()}@1"
    explanation["params"] = {"n_decisive": len(release["decisive"]),
                             "decisive_list": [decisive_entry_text(record, d) for d in release["decisive"]],
                             "n_contributing": len(release["contributing"]),
                             "semantics": RELEASE_SEMANTICS}
    explanation["summary"] = sem_why.render(ontology, explanation["template_id"], explanation["params"])


def _reconcile_scored_policy(record, value, *, ontology):
    """Replace the preview's unknown minimum-score review with the computed rc4 result."""
    release = record["release_recommendation"]
    rules = release["policy"]["rules"]
    row = next((row for row in rules if row["rule"] == "profile.min_score"), None)
    if row is None or row["result"] != "not_evaluated" or value is None:
        return
    floor = row["expected"]
    row["observed"] = value
    row["result"] = "pass" if value >= floor else "fail"
    decisive = [entry for entry in release["decisive"] if entry["id"] != "profile.min_score"]
    if value < floor:
        entry = {"kind": "profile_rule", "id": "profile.min_score",
                 "expected": f">= {sem_why.fmt_score(floor)}", "observed": sem_why.fmt_score(value),
                 "claim_ids": [], "finding_ids": [], "field_refs": ["/scores/readiness/value"],
                 "effect": "REVIEW"}
        index = next((i for i, item in enumerate(decisive)
                      if item["kind"] == "profile_rule" and item["id"] != "profile.prohibited_use_case"),
                     len(decisive))
        decisive.insert(index, entry)
    signoff = next((row for row in rules if row["rule"] == "profile.signoff_required"), None)
    if signoff is not None and release["signoff"]["required"]:
        decisive = [entry for entry in decisive if entry["id"] != "profile.signoff_required"]
        signoff["result"] = "not_reached" if decisive else "fail"
        if not decisive:
            decisive.append({"kind": "profile_rule", "id": "profile.signoff_required",
                             "expected": "human sign-off recorded", "observed": "not recorded",
                             "claim_ids": [], "finding_ids": [],
                             "field_refs": ["/release_recommendation/signoff"], "effect": "REVIEW"})
    release["decisive"] = decisive
    release["state"] = ("BLOCK" if any(entry["effect"] == "BLOCK" for entry in decisive) else
                        "REVIEW" if decisive else "PASS")
    explanation = release["explanation"]
    if decisive:
        explanation["template_id"] = f"eio.why.release.{release['state'].lower()}@1"
        explanation["params"] = {"n_decisive": len(decisive),
                                 "decisive_list": [decisive_entry_text(record, entry) for entry in decisive],
                                 "n_contributing": len(release["contributing"]),
                                 "semantics": release["semantics"]}
    else:
        explanation["template_id"] = "eio.why.release.pass@1"
        explanation["params"] = {"n_contributing": len(release["contributing"]),
                                 "semantics": release["semantics"]}
    explanation["summary"] = sem_why.render(ontology, explanation["template_id"], explanation["params"])


def full_score_block_problems(block, versioned_unscored, *, ontology):
    """Producer-side shape and digest checks; not an independent score verifier."""
    problems = [error.message for error in Draft202012Validator(_checked_schema(SCORE_SCHEMA)).iter_errors(block)]
    if not isinstance(block, dict):
        return problems
    if block.get("score_basis_sha256") != _score_basis_sha256(versioned_unscored):
        problems.append("rc4 score basis digest differs")
    if block.get("score_sha256") != H(jb({key: value for key, value in block.items() if key != "score_sha256"})):
        problems.append("rc4 score block digest differs")
    document = profiles.reference_public_document(ontology)
    expected = {**profiles.record_profile(document), "ontology_sha256": ontology.ontology_sha256}
    if block.get("scoring_profile") != expected:
        problems.append("rc4 score profile identity or digest differs")
    if [m.get("metric") for m in block.get("metrics", [])] != document["published_metrics"]:
        problems.append("rc4 metric order differs")
    if [a.get("axis") for a in block.get("axes", [])] != document["parameters"]["axis_order"]:
        problems.append("rc4 axis order differs")
    return problems


def project_native_full_per(bundle, unscored_per, verification, *, ontology):
    """Produce an rc4 candidate from verified native sources and profile 0.3.

    ``verification`` must bind the exact input null-score rc3 PER. Missing
    source-derived proof sets fail closed. Incomplete Q/E/C inputs produce
    explicit withheld axes and readiness within rc4.
    """
    require(isinstance(unscored_per, dict) and isinstance(verification, dict)
            and verification.get("valid") is True and verification.get("digest_match") is True
            and verification.get("per_sha256") == H(jb(unscored_per)),
            "NATIVE_FULL_WIRE", "null-score PER needs digest-matched D1/D2/D5 source verification")
    inputs = extract_native_inputs(bundle, ontology=ontology, record=unscored_per, verification=verification)
    require(inputs is not None, "NATIVE_FULL_WIRE", "native score inputs are absent")
    proof_sets = {key: inputs[key] for key in (
        "reportable_finding_ids", "decisive_finding_ids", "decisive_claim_ids")}
    require(all(isinstance(value, list) for value in proof_sets.values()),
            "NATIVE_FULL_WIRE", "source citations do not establish all proof sets")
    for value in proof_sets.values():
        require(value == sorted(set(value)), "NATIVE_FULL_WIRE", "source proof IDs are not sorted and unique")
    base = _versioned_unscored(unscored_per)
    document = profiles.reference_public_document(ontology)
    draft = score_native(**inputs, ontology=ontology, profile=document)
    require(draft["profile_sha256"] == profiles.profile_sha256(document)
            and draft["ontology_sha256"] == ontology.ontology_sha256,
            "NATIVE_FULL_WIRE", "score does not bind profile and ontology")
    _reconcile_scored_policy(base, draft["readiness"]["value"], ontology=ontology)
    _apply_high_review_guard(base, draft["high_review_queue"], ontology=ontology)
    _apply_default_floor_guards(base, draft["readiness"]["value"], ontology=ontology)

    claim_ids = {row["id"] for row in base["claims"]}
    metrics = []
    for mid in document["published_metrics"]:
        row = draft["metrics"][mid]
        members, caps = sorted(row["members"]), sorted(row.get("cap_claim_ids", []))
        require(set(members + caps) <= claim_ids, "NATIVE_FULL_WIRE", "metric names an unknown claim")
        metrics.append({"metric": mid, "value": row["value"], "member_claim_ids": members,
                        "pre_cap": row.get("pre_cap"), "cap_claim_ids": caps,
                        "context_ceiling": row.get("context_ceiling"),
                        "status": "MEASURED" if row["value"] is not None else "WITHHELD",
                        "withheld_code": _reason(row.get("withheld"))})
    details = draft["axis_details"]
    basis_ids = {
        "eio.axis.context": sorted(details["context"]["criteria"]),
        "eio.axis.behaviour": [row["metric"] for row in metrics if row["value"] is not None],
        "eio.axis.compliance": sorted(details["compliance_axis"]["per_framework"]),
        "eio.axis.governance": document["g_component_ids"],
    }
    axis_reason = {
        "eio.axis.context": details["context"]["withheld"],
        "eio.axis.behaviour": "no applicable decided claim" if draft["axes"]["eio.axis.behaviour"] is None else None,
        "eio.axis.compliance": details["compliance_axis"]["withheld"],
        "eio.axis.governance": details["governance"]["withheld"],
    }
    axes = [{"axis": aid, "value": draft["axes"][aid], "basis_ids": basis_ids[aid],
             "status": "MEASURED" if draft["axes"][aid] is not None else "WITHHELD",
             "withheld_code": _reason(axis_reason[aid])}
            for aid in document["parameters"]["axis_order"]]
    result = draft["readiness"]
    applied = result["blocked"]
    readiness = {"value": result["value"], "raw": result["raw"],
                 "status": "MEASURED" if result["complete"] else "WITHHELD",
                 "withheld_codes": [] if result["complete"] else ["REQUIRED_AXIS_WITHHELD"],
                 "cap": {"applied": applied, "ceiling": 49.0 if applied else None,
                         "claim_ids": result["cap_claim_ids"],
                         "prohibited_use": inputs["policy"]["prohibited"]}}
    block = {"kind": SCORE_KIND,
             "scoring_profile": {**profiles.record_profile(document), "ontology_sha256": ontology.ontology_sha256},
             "score_basis_version": SCORE_BASIS_VERSION,
             "score_basis_sha256": _score_basis_sha256(base),
             "metrics": metrics, "axes": axes, "proof_sets": proof_sets,
             "readiness": readiness}
    block["score_sha256"] = H(jb(block))
    problems = full_score_block_problems(block, base, ontology=ontology)
    require(not problems, "NATIVE_FULL_WIRE_SCHEMA", f"rc4 score invalid: {problems[:2]}")
    base["scores"] = block
    base["limitations"] = [row for row in base["limitations"]
                           if row["limitation_id"] != NO_SCORING_PROFILE_ID]
    require(_score_basis_sha256(base) == block["score_basis_sha256"],
            "NATIVE_FULL_WIRE", "rc4 score basis changed during assembly")
    schema_path = POLICY_PER_SCHEMA if base["header"]["per_version"] == POLICY_PER_VERSION else PER_SCHEMA
    errors = [error.message for error in Draft202012Validator(_checked_schema(schema_path)).iter_errors(base)]
    require(not errors, "NATIVE_FULL_WIRE_SCHEMA", f"rc4 PER invalid: {errors[:2]}")
    return base
