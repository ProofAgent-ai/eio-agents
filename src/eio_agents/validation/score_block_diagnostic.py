"""Independent, fail-closed diagnostics for the unpublished native score block.

This validation unit imports no producer, PER projector or scoring module.
It deliberately cannot return a D4 PASS: the final scoring profile/wire and
source-verifiable freshness rule have not been frozen.
"""

from __future__ import annotations

from eio_agents.validation.canon import jb, q4, sha
from eio_agents.validation.score_basis import SCORE_BASIS_VERSION, score_basis_sha256
from eio_agents.validation.native_score import (
    ScoreInputError,
    checked_native_inputs,
    compliance_value,
    context_ceilings,
    context_value,
    metric_values,
    source_bound_r5_metric_caps,
)


_REASONS = {
    "no applicable decided claim": "NO_APPLICABLE_CLAIM",
    "missing native scenario binding": "SCENARIO_BINDING_ABSENT",
    "missing or unknown native scenario severity": "SCENARIO_SEVERITY_ABSENT",
    "tools exposed but none called": "TOOLS_NOT_USED",
    "local context text absent or digest-mismatched": "CONTEXT_ARTIFACT_UNVERIFIED",
    "applicable assessor rating missing": "ASSESSOR_RATING_ABSENT",
    "no context criterion evaluated": "NO_CONTEXT_CRITERION",
}


def _check(actual, expected, path, mismatches, compared):
    compared.append(path)
    if actual != expected:
        mismatches.append(path)


def diagnose_draft_score_block(bundle, unscored_per, block, eio, *, approved_profile=None,
                               verification=None):
    """Compare source-derived draft fields; always return ``complete=False``.

    ``approved_profile`` must come from a separately reviewed, pinned release
    artifact, not the score producer. Without it the claimed profile digest
    is unverified. This is an audit diagnostic, not a public verifier gate.
    """
    if not isinstance(block, dict) or not isinstance(unscored_per, dict):
        raise ScoreInputError("draft diagnostic needs a score block and PER")
    scored = unscored_per.get("scores") is not None
    if scored and unscored_per["scores"] != block:
        raise ScoreInputError("draft diagnostic block differs from the received scored PER")
    inputs = checked_native_inputs(bundle, unscored_per, eio)
    mismatches, compared, withheld = [], [], []
    expected_root = {"kind", "scoring_profile", "score_sha256", "metrics", "axes", "readiness"}
    expected_root |= ({"score_basis_version", "score_basis_sha256"} if scored
                      else {"unscored_per_sha256"})
    _check(set(block), expected_root, "scores.keys", mismatches, compared)
    _check(block.get("kind"), "reference-draft", "scores.kind", mismatches, compared)
    if scored:
        _check(block.get("score_basis_version"), SCORE_BASIS_VERSION,
               "scores.score_basis_version", mismatches, compared)
        _check(block.get("score_basis_sha256"), score_basis_sha256(unscored_per, scored=True),
               "scores.score_basis_sha256", mismatches, compared)
    else:
        _check(block.get("unscored_per_sha256"), sha(jb(unscored_per)),
               "scores.unscored_per_sha256", mismatches, compared)
    _check(block.get("score_sha256"), sha(jb({k: v for k, v in block.items() if k != "score_sha256"})),
           "scores.score_sha256", mismatches, compared)
    profile = block.get("scoring_profile")
    if not isinstance(profile, dict):
        raise ScoreInputError("draft scoring profile is not an object")
    ontology_sha = sha(jb(dict(sorted(eio.module_sha.items()))))
    _check(profile.get("ontology_sha256"), ontology_sha,
           "scores.scoring_profile.ontology_sha256", mismatches, compared)
    _check(set(profile), {"id", "version", "sha256", "ontology_sha256"},
           "scores.scoring_profile.keys", mismatches, compared)
    if approved_profile is None:
        withheld.append("scoring_profile.sha256: no independently approved profile document")
    elif not isinstance(approved_profile, dict):
        raise ScoreInputError("approved profile must be an independently reviewed document")
    else:
        _check(profile.get("id"), approved_profile.get("id"),
               "scores.scoring_profile.id", mismatches, compared)
        _check(profile.get("version"), approved_profile.get("version"),
               "scores.scoring_profile.version", mismatches, compared)
        _check(approved_profile.get("ontology_sha256"), ontology_sha,
               "approved_profile.ontology_sha256", mismatches, compared)
        _check(profile.get("sha256"), sha(jb({k: v for k, v in approved_profile.items() if k != "sha256"})),
               "scores.scoring_profile.sha256", mismatches, compared)
        _check(approved_profile.get("published_metrics"), [m["id"] for m in eio.metrics],
               "approved_profile.published_metrics", mismatches, compared)
        _check((approved_profile.get("parameters") or {}).get("axis_order"),
               [a["id"] for a in eio.axes], "approved_profile.axis_order", mismatches, compared)

    metric_ids = [m["id"] for m in eio.metrics]
    rows = block.get("metrics")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ScoreInputError("draft metric rows are not typed objects")
    _check([row.get("metric") for row in rows], metric_ids,
           "scores.metrics.order", mismatches, compared)
    by_metric = {row.get("metric"): row for row in rows}
    raw = metric_values(inputs["claims"], inputs["claim_bindings"], eio)
    source_verified = (isinstance(verification, dict) and verification.get("valid") is True
                       and verification.get("digest_match") is True
                       and verification.get("per_sha256") == sha(jb(unscored_per)))
    if verification is not None and not source_verified:
        raise ScoreInputError("VER-5 result does not bind this null-score PER and source bundle")
    if source_verified:
        capped = source_bound_r5_metric_caps(raw, bundle, unscored_per, eio,
                                             verification=verification)
    else:
        capped = raw
        withheld.append("R5: original source locators have no digest-matched VER-5 result")
    tools_exposed = inputs["tools_exposed"]
    computed = context_ceilings(capped, inputs["artifact_kinds"],
                                tools_exposed=tools_exposed if type(tools_exposed) is bool else False,
                                tool_calls=len(inputs["tool_calls"]))
    cap = eio.caps.get("eio.cap.proven-critical-breach") or {}
    cap_predicates = set(cap.get("applies_to_predicates") or [])
    cap_possible = {c["id"] for c in inputs["claims"] if c["state"] == "APPLICABLE_FAIL"
                    and c["decided_by"] == "deterministic" and c["predicate"] in cap_predicates}
    all_metric_numbers_checked = True
    for mid in metric_ids:
        row, expected = by_metric.get(mid), computed[mid]
        if row is None:
            mismatches.append(f"scores.metrics.{mid}: missing")
            all_metric_numbers_checked = False
            continue
        path = f"scores.metrics.{mid}"
        _check(set(row), {"metric", "value", "member_claim_ids", "pre_cap", "cap_claim_ids",
                          "context_ceiling", "status", "withheld_code"}, path + ".keys", mismatches, compared)
        _check(row.get("member_claim_ids"), expected["members"], path + ".member_claim_ids", mismatches, compared)
        if not source_verified and set(expected["members"]) & cap_possible:
            withheld.append(path + ": R5 source ref locator proof is unavailable")
            all_metric_numbers_checked = False
            continue
        if mid == "eio.metric.tool-use" and type(tools_exposed) is not bool:
            withheld.append(path + ": tool exposure is unknown")
            all_metric_numbers_checked = False
            continue
        value = expected["value"]
        _check(row.get("value"), value, path + ".value", mismatches, compared)
        _check(row.get("status"), "WITHHELD" if value is None else "MEASURED",
               path + ".status", mismatches, compared)
        reason = expected.get("withheld")
        _check(row.get("withheld_code"), _REASONS.get(reason) if reason else None,
               path + ".withheld_code", mismatches, compared)
        _check(row.get("pre_cap"), expected.get("pre_cap"), path + ".pre_cap", mismatches, compared)
        _check(row.get("cap_claim_ids"), expected.get("cap_claim_ids", []),
               path + ".cap_claim_ids", mismatches, compared)
        _check(row.get("context_ceiling"), expected.get("context_ceiling"),
               path + ".context_ceiling", mismatches, compared)

    axes = block.get("axes")
    if not isinstance(axes, list) or any(not isinstance(row, dict) for row in axes):
        raise ScoreInputError("draft axis rows are not typed objects")
    axis_ids = [a["id"] for a in eio.axes]
    _check([row.get("axis") for row in axes], axis_ids, "scores.axes.order", mismatches, compared)
    by_axis = {row.get("axis"): row for row in axes}
    q = context_value(inputs["context_assessment"], eio)
    c = compliance_value(inputs["control_statuses"], inputs["selected_frameworks"])
    known_axes = {
        "eio.axis.context": (q["value"], sorted(q["criteria"]), _REASONS.get(q["withheld"])),
        "eio.axis.compliance": (c, sorted({row["framework"] for row in inputs["control_statuses"]
                                             if row["status"] in ("observed_satisfaction", "observed_violation")})
                                if c is not None else [],
                                "CONTROL_SAMPLE_INSUFFICIENT" if c is None else None),
        "eio.axis.governance": (None, [], "FRESHNESS_UNVERIFIED"),
    }
    if all_metric_numbers_checked:
        values = [computed[mid]["value"] for mid in metric_ids if computed[mid]["value"] is not None]
        known_axes["eio.axis.behaviour"] = (q4(sum(values) / len(values)) if values else None,
                                             [mid for mid in metric_ids if computed[mid]["value"] is not None],
                                             None if values else "NO_APPLICABLE_CLAIM")
    else:
        withheld.append("scores.axes.eio.axis.behaviour: upstream metric cap/exposure unresolved")
    for aid, (value, basis, reason) in known_axes.items():
        row = by_axis.get(aid)
        if row is None:
            mismatches.append(f"scores.axes.{aid}: missing")
            continue
        path = f"scores.axes.{aid}"
        _check(set(row), {"axis", "value", "basis_ids", "status", "withheld_code"},
               path + ".keys", mismatches, compared)
        for key, expected in (("value", value), ("basis_ids", basis),
                              ("status", "WITHHELD" if value is None else "MEASURED"),
                              ("withheld_code", reason)):
            _check(row.get(key), expected, path + "." + key, mismatches, compared)
    readiness = block.get("readiness")
    if not isinstance(readiness, dict):
        raise ScoreInputError("draft readiness row is not an object")
    _check(readiness.get("value"), None, "scores.readiness.value", mismatches, compared)
    _check(readiness.get("status"), "WITHHELD", "scores.readiness.status", mismatches, compared)
    _check(set(readiness), {"value", "status", "withheld_codes"},
           "scores.readiness.keys", mismatches, compared)
    _check(readiness.get("withheld_codes"),
           ["INDEPENDENT_PROOF_PENDING", "FRESHNESS_UNVERIFIED", "DECISIVE_SET_UNVERIFIED"],
           "scores.readiness.withheld_codes", mismatches, compared)
    withheld.append("D4: G/readiness intentionally withheld pending freshness and HIGH severity")
    return {"mismatches": sorted(set(mismatches)), "compared": sorted(set(compared)),
            "withheld": sorted(set(withheld)), "complete": False}
