"""Native rc4 policy preview and scored-policy reconciliation regressions."""

import copy
import json
from pathlib import Path

import pytest

from eio_agents import canonical_bytes, convert, explain, resolve, targets, validate, verify
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per.native_preview import project_native_preview
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.validate import check_one
from eio_agents.validation.verify import c_sources

from full_native_score_case import reseal_stages, source_complete_bundle


PROFILE_SHA = "sha256:1aceedc4cb30160cb4edcd6888ef1699be7b98d348ad890fc0516d7b5f07c5d5"
HISTORICAL = Path(__file__).parent / "data/native/native.bundle.json"


def _policy_bundle(min_score=75):
    bundle = source_complete_bundle()
    bundle["scope"]["policy"] = {
        "source": "embedded_profile", "origin": "local", "profile_sha256": PROFILE_SHA,
        "name": "native-eio-test-profile", "declared": None, "prohibited": False,
        "rules": {"min_score": min_score, "block_severity": "HIGH", "signoff_required": False},
    }
    bundle["provenance"]["record"]["inputs"]["governance_profile"] = {
        "name": "native-eio-test-profile", "profile_sha256": PROFILE_SHA, "embedded": True,
    }
    return reseal_stages(bundle)


def _preview_checks(bundle):
    record = project_native_preview(bundle, ontology=load())
    assert validate(record) == []
    checker = EIO(EIO_DIR)
    checks = check_one(record, checker)
    checks.run("D2 source", "VER-5", lambda: c_sources(record, bundle, checker))
    checks.run("D5 proof", "VER-5", lambda: native_proof_status_gate(bundle, record, checker))
    assert not [row for row in checks.rows if row[2] == "FAIL"]
    return record


def test_uppercase_severity_and_unknown_minimum_score_are_explicit_in_preview():
    record = _preview_checks(_policy_bundle())
    release = record["release_recommendation"]
    assert release["state"] == "REVIEW"
    assert release["policy"]["rules"][1] == {
        "rule": "profile.min_score", "result": "not_evaluated", "expected": 75, "observed": None,
    }
    assert release["policy"]["rules"][2]["rule"] == "profile.block_on_high"
    unknown = next(row for row in release["decisive"] if row["id"] == "profile.min_score")
    assert unknown["field_refs"] == ["/scores"] and unknown["claim_ids"] == []


def test_numeric_readiness_replaces_preview_unknown_with_source_checked_failure():
    bundle = _policy_bundle()
    record = convert(bundle)
    assert record["header"]["per_version"] == "2.0.0"
    assert record["header"]["schema_uri"] == "https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json"
    assert record["scores"]["readiness"]["status"] == "MEASURED"
    assert record["release_recommendation"]["policy"]["rules"][1]["observed"] == record["scores"]["readiness"]["value"]
    assert record["release_recommendation"]["policy"]["rules"][1]["result"] == "fail"
    assert record["release_recommendation"]["state"] == "REVIEW"
    assert validate(record) == []
    assert verify(record, bundle)["valid"]


def test_numeric_readiness_passing_minimum_removes_provisional_review():
    bundle = _policy_bundle(min_score=50)
    record = convert(bundle)
    assert record["release_recommendation"]["policy"]["rules"][1]["result"] == "pass"
    assert not any(row["id"] == "profile.min_score" for row in record["release_recommendation"]["decisive"])
    assert record["release_recommendation"]["state"] == "PASS"
    assert validate(record) == []
    assert verify(record, bundle)["valid"]


def test_rc5_measured_scores_are_discoverable_and_explainable():
    record = convert(_policy_bundle(min_score=50))
    names = {item["id"] for item in targets(record)}
    assert {"readiness", "eio.axis.context", "eio.axis.behaviour",
            "eio.axis.compliance", "eio.axis.governance"} <= names
    assert explain(record, "readiness").startswith("Readiness: ")
    assert explain(record, "governance").startswith("Governance (G): ")


def test_rc5_private_identity_stays_local_and_tampering_fails():
    marker = "zqxjvw-rc5-private-identity"
    bundle = _policy_bundle(min_score=50)
    bundle["provenance"]["agent"]["agent_id"] = marker
    reseal_stages(bundle)
    record = convert(bundle)
    assert marker.encode("utf-8") not in canonical_bytes(record)
    assert validate(record) == []
    assert verify(record, bundle)["valid"]
    assert any(row["text"] == marker for row in resolve(record, bundle))
    forged = copy.deepcopy(record)
    forged["subject"]["agent"]["agent_id"] = marker
    assert validate(forged)
    assert not verify(forged, bundle)["valid"]


def test_forged_policy_pass_does_not_validate():
    record = convert(_policy_bundle())
    forged = copy.deepcopy(record)
    rule = forged["release_recommendation"]["policy"]["rules"][1]
    rule["result"] = "pass"
    assert validate(forged)


def test_missing_score_sources_keep_minimum_unevaluated_in_final_per():
    bundle = _policy_bundle()
    bundle["native_scoring"]["context_ratings"] = []
    reseal_stages(bundle)
    record = convert(bundle)
    assert record["scores"]["readiness"]["status"] == "WITHHELD"
    assert record["release_recommendation"]["policy"]["rules"][1]["result"] == "not_evaluated"
    assert record["release_recommendation"]["state"] == "REVIEW"
    assert validate(record) == []
    assert verify(record, bundle)["valid"]


def test_preserved_0_5_bundle_requires_its_pinned_historical_ontology():
    bundle = json.loads(HISTORICAL.read_text(encoding="utf-8"))
    assert bundle["header"]["eio"]["release"] == "0.5.0-draft.1"
    # A historical 0.5 vector shipped in this repository must fail closed
    # under the 0.6 ontology; its original installed build owns verification.
    with pytest.raises(ConversionError, match="BUNDLE_RECOMPUTE"):
        project_native_preview(copy.deepcopy(bundle), ontology=load())
