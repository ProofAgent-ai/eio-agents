"""Verifier-owned full-score profile and no-freshness governance vectors."""

import copy

from eio_agents.validation.full_score import (
    full_native_score_gate,
    governance_without_freshness,
    load_full_score_resources,
)
from eio_agents.validation.reader import EIO, EIO_DIR


def test_four_component_governance_uses_no_freshness_and_normalizes_to_100_scale():
    policy = {"source": "declared", "prohibited": False, "signoff_required": False,
              "named_frameworks": ["fw"], "tier": "low"}
    controls = [{"framework": "fw", "control_id": "c", "status": "observed_satisfaction"}]
    got = governance_without_freshness(policy, [], controls, reportable_ids=[], decisive_ids=[])
    assert got == {"value": 92.5, "components": {
        "release_gate": 20, "human_oversight": 14,
        "policy_conformance": 20, "obligation_coverage": 20}}
    assert "evidence_freshness" not in got["components"]
    prohibited = dict(policy, prohibited=True)
    assert governance_without_freshness(prohibited, [], controls,
                                        reportable_ids=[], decisive_ids=[])["value"] == 0.0


def test_direct_gate_refuses_rogue_schema_or_profile_before_source_computation():
    profile, schema = load_full_score_resources()
    assert profile["version"] == "0.3.1-draft.1"
    assert schema["properties"]["proof_sets"]["required"] == [
        "reportable_finding_ids", "decisive_finding_ids", "decisive_claim_ids"]
    eio = EIO(EIO_DIR)
    eio.profiles["eio.profile.proof-status"]["native_claim_proves"] = False
    fake_record = {"scores": {"kind": "reference-draft"}}
    rogue_profile = copy.deepcopy(profile)
    rogue_profile["parameters"]["readiness_ceiling"] = 100
    assert "differs from verifier-owned" in full_native_score_gate(
        {}, fake_record, eio, source_checked=True,
        approved_profile=rogue_profile, approved_schema=schema)[0][0]
    rogue_schema = copy.deepcopy(schema)
    rogue_schema["additionalProperties"] = True
    assert "differs from verifier-owned" in full_native_score_gate(
        {}, fake_record, eio, source_checked=True,
        approved_profile=profile, approved_schema=rogue_schema)[0][0]
