"""Third-party-authored synthetic native bundle through the public scored path."""

import copy
import json
from pathlib import Path

from eio_agents import convert, per_sha256, validate, verify
from eio_agents.schemas import per_schema
from eio_agents.per.bundle import stage_digest
from eio_agents.ontology import load
from eio_agents.per.native_preview import project_native_preview
from eio_agents.validation import verify as independent_verify
from eio_agents.validation.canon import jb, sha
from eio_agents.validation.full_score import full_native_score_gate, load_full_score_resources
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.score_basis import score_basis_sha256
from test_proof_group_exploration import prohibited_tool_bundle


SOURCE = Path(__file__).parent / "data/native/v0_8/synthetic-cited-native.bundle.json"
EXPECTED_PER_SHA256 = "sha256:775abc7319af22f84e7ae44d10795f5437696149d11f7e6271dd7276f32be2c6"


def _bundle():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_external_native_bundle_scores_and_verifies_without_adapter():
    bundle = _bundle()
    record = convert(bundle)
    schema = per_schema("2.1.0")
    assert record["header"]["per_version"] == "2.1.0"
    assert record["header"]["schema_uri"] == schema["$id"]
    assert per_sha256(record) == EXPECTED_PER_SHA256
    assert record["scores"]["kind"] == "reference"
    assert record["scores"]["axes"][3]["value"] == 25.0
    assert record["scores"]["readiness"]["value"] is None
    assert [row["proof_status"] for row in record["findings"]] == ["UNPROVEN"]
    assert validate(record) == []
    result = verify(record, bundle)
    assert result["valid"] and result["digest_match"] and result["failures"] == []


def test_uncited_native_bundle_cannot_claim_proven_even_if_d3_is_bypassed():
    bundle = _bundle()
    bundle["native_scoring"]["proof_citations"] = []
    for stage in bundle["stage_records"]:
        if "native_scoring" in stage["sections"]:
            stage["output_sha256"] = stage_digest(bundle, stage["sections"])
    record = convert(bundle)
    assert [row["proof_status"] for row in record["findings"]] == ["UNPROVEN"]
    assert verify(record, bundle)["valid"]
    forged = copy.deepcopy(record)
    forged["findings"][0]["proof_status"] = "PROVEN"
    result = independent_verify(forged, bundle, rederived=forged)
    assert not result["valid"] and result["digest_match"]
    assert any(row["check"].startswith("D5 native proof") and row["status"] == "FAIL"
               for row in result["failures"])


def test_native_score_suppression_fails_d4_even_if_d3_is_bypassed():
    bundle = _bundle()
    omitted = project_native_preview(bundle, ontology=load())
    result = independent_verify(omitted, bundle, rederived=omitted)
    assert not result["valid"]
    assert any(row["check"].startswith("D4 native score") and row["status"] == "FAIL"
               for row in result["failures"])


def test_unproven_high_finding_cannot_be_forged_into_pass():
    bundle = prohibited_tool_bundle(proof=False)
    record = convert(bundle)
    assert record["findings"][0]["severity"] == "HIGH"
    assert record["findings"][0]["proof_status"] == "UNPROVEN"
    assert record["release_recommendation"]["state"] == "REVIEW"
    forged = copy.deepcopy(record)
    forged["release_recommendation"]["state"] = "PASS"
    forged["scores"]["score_basis_sha256"] = score_basis_sha256(forged, scored=True)
    forged["scores"]["score_sha256"] = sha(jb({key: value for key, value in forged["scores"].items()
                                                 if key != "score_sha256"}))
    profile, schema = load_full_score_resources()
    problems, _ = full_native_score_gate(bundle, forged, EIO(EIO_DIR), source_checked=True,
                                         approved_profile=profile, approved_schema=schema)
    assert any("HIGH_guard" in problem for problem in problems)
    result = independent_verify(forged, bundle, rederived=forged)
    assert not result["valid"]
    assert any(row["check"].startswith("D4 native score") and row["status"] == "FAIL"
               for row in result["failures"])
