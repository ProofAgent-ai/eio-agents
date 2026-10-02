"""Synthetic native scorer-source vectors; no public PER/profile digest is reissued here."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eio_agents import convert, validate, verify
from eio_agents.base.canon import H
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.per.native_score_inputs import extract_native_inputs
from eio_agents.validation.validate import validate_bundle

BUNDLE = Path(__file__).parent / "data/native/v0_6/native.bundle.json"


def candidate():
    b = json.loads(BUNDLE.read_text(encoding="utf-8"))
    ids = [claim["id"] for claim in b["claims"]]
    b["native_scoring"] = {
        "scenario_bindings": [{"binding_id": f"s{i}", "turn_indices": claim["turn_indices"], "severity": "HIGH"}
                              for i, claim in enumerate(b["claims"])],
        "claim_bindings": [{"claim_id": cid, "binding_id": f"s{i}"} for i, cid in enumerate(ids)],
        "applicable_controls": [], "context_ratings": [], "proof_citations": [],
    }
    b["stage_records"].append({"stage": "native-score-sources", "producer": "native",
                               "sections": ["native_scoring"], "output_sha256": B.stage_digest(b, ["native_scoring"])})
    return b


def test_native_score_sources_map_only_evidence_and_withhold_freshness():
    b, e = candidate(), load()
    assert validate_bundle(b) == []
    out = extract_native_inputs(b, ontology=e)
    assert set(out["claim_bindings"]) == {claim["id"] for claim in out["claims"]}
    assert out["freshness_verified"] is False
    assert out["tools_exposed"] is True
    assert out["tool_calls"] == 1
    assert set(out["refs"]) == {ref["id"] for ref in b["graph"]["refs"]}
    assert out["selected_frameworks"] == []
    assert out["control_statuses"] is None  # requires independently materialized PER
    assert "score_inputs" not in out
    semantic = [claim for claim in out["claims"] if claim["decided_by"] == "semantic"]
    assert semantic[0]["parameters"]["votes"] == {"distinct_pairs": 3, "observed": 3,
                                                   "not_observed": 0, "split": 0}


def test_native_applicability_and_bound_context_rating():
    b, e = candidate(), load()
    fw = next(iter(e.frameworks))
    control = e.frameworks[fw]["controls"][0]
    b["scope"]["frameworks"]["candidates"] = [{"id": fw, "basis": "synthetic scope"}]
    b["native_scoring"]["applicable_controls"] = [{"framework": fw, "control_id": control}]
    criterion = next(iter(e.criteria))
    text = "Synthetic public checklist for a local evaluation."
    digest = H(text.encode("utf-8"))
    b["sources"]["context_artifacts"] = [{"artifact_kind": next(iter(e.artifact_kinds)), "name": "checklist.md",
                                           "sha256": digest, "code_points": len(text), "embedded": True,
                                           "data_class": next(iter(e.data_classes))}]
    b["sources"]["context_texts"] = {"checklist.md": text}
    b["native_scoring"]["context_ratings"] = [{"criterion_id": criterion, "artifact_name": "checklist.md",
                                                "artifact_sha256": digest, "assessor_id": "assessor-1", "rating": 80}]
    out = extract_native_inputs(b, ontology=e)
    assert out["control_statuses"] is None
    assert out["context_assessment"]["assessor_ratings"] == {criterion: 80}
    assert out["context_assessment"]["artifacts"][0]["sha256"] == digest


def test_control_status_comes_only_from_independently_materialized_per():
    b, e = candidate(), load()
    fw = next(iter(e.frameworks))
    control = e.frameworks[fw]["controls"][0]
    b["scope"]["frameworks"]["candidates"] = [{"id": fw, "basis": "synthetic scope"}]
    b["native_scoring"]["applicable_controls"] = [{"framework": fw, "control_id": control}]
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    rec = convert(b)
    verification = verify(rec, b)
    assert validate(rec) == [] and verification["valid"]
    out = extract_native_inputs(b, ontology=e, record=rec, verification=verification)
    expected = next(row["status"] for row in rec["controls"] if row["control_id"] == control)
    assert out["control_statuses"] == [{"framework": fw, "control_id": control, "status": expected}]


def test_native_sources_round_trip_to_rc5_score_with_known_empty_proof_set():
    b, e = candidate(), load()
    rec = convert(b)
    assert rec["scores"] is not None
    assert rec["scores"]["readiness"]["value"] is None
    assert validate(rec) == []
    verification = verify(rec, b)
    assert verification["valid"]
    out = extract_native_inputs(b, ontology=e, record=rec, verification=verification)
    assert out["findings"] == rec["findings"]
    assert out["reportable_finding_ids"] == []
    assert out["decisive_finding_ids"] == []
    assert {c["id"] for c in out["claims"]} == {c["id"] for c in rec["claims"]}


def test_forged_per_witness_and_forged_ballot_count_fail_closed():
    b, e = candidate(), load()
    rec = convert(b)
    verification = verify(rec, b)
    bad = copy.deepcopy(rec)
    bad["claims"][0]["id"] = "forged"
    with pytest.raises(ConversionError):
        extract_native_inputs(b, ontology=e, record=bad, verification=verification)
    with pytest.raises(ConversionError):
        extract_native_inputs(b, ontology=e, record=rec)  # no independent verifier result
    bad = copy.deepcopy(b)
    semantic = next(c for c in bad["claims"] if c["decided_by"] == "semantic")
    semantic["parameters"]["votes"]["observed"] = 2
    with pytest.raises(ConversionError):
        extract_native_inputs(bad, ontology=e)


@pytest.mark.parametrize("change", [
    lambda b: b["native_scoring"]["claim_bindings"].append(copy.deepcopy(b["native_scoring"]["claim_bindings"][0])),
    lambda b: b["native_scoring"]["claim_bindings"][0].update(binding_id="missing"),
    lambda b: b["native_scoring"]["scenario_bindings"][0].update(turn_indices=[999]),
    lambda b: b["native_scoring"]["scenario_bindings"][0].update(severity="FAKE"),
    lambda b: b["native_scoring"].update(score=100),
    lambda b: b["native_scoring"].update(freshness_verified=True),
    lambda b: b["native_scoring"].update(tools_exposed=True),
    lambda b: b["native_scoring"].update(control_statuses=[{"framework": "fake", "control_id": "fake", "status": "VIOLATION"}]),
    lambda b: b["scope"]["frameworks"].update(rule="assessed"),
    lambda b: b["native_scoring"]["context_ratings"].append({"criterion_id": "unknown", "artifact_name": "none",
                                                             "artifact_sha256": "sha256:" + "0" * 64,
                                                             "assessor_id": "fake", "rating": 100}),
    lambda b: b["scope"]["facts"]["tools"].update(value=False),
])
def test_invalid_native_sources_fail_closed(change):
    b = candidate()
    change(b)
    with pytest.raises(ConversionError):
        extract_native_inputs(b, ontology=load())


def test_missing_native_sources_withhold_and_adapter_cannot_claim_them():
    b, e = candidate(), load()
    b.pop("native_scoring")
    b["stage_records"].pop()
    assert extract_native_inputs(b, ontology=e) is None
    b = candidate()
    b["provenance"]["producer"]["kind"] = "adapter"
    assert validate_bundle(b)
    with pytest.raises(ConversionError):
        extract_native_inputs(b, ontology=e)
