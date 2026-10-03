"""Tests of the DeepEval converter: python -m pytest -q test_convert.py"""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.validation import validate_bundle

from convert import load, to_bundle

RUN, DIGEST = load(str(Path(__file__).parent / "test_run.json"))


@pytest.fixture(scope="module")
def converted():
    bundle = to_bundle(RUN, DIGEST)
    return bundle, eio_agents.convert(bundle)


def test_the_test_run_converts_to_a_valid_verifiable_per(converted):
    bundle, record = converted
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    assert record["header"]["per_version"] == "2.1.0" and eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_mapped_metrics_become_claims_and_unmapped_ones_do_not(converted):
    bundle, _ = converted
    decided = sorted((c["turn_indices"][0], c["predicate"].removeprefix("eio.predicate."), c["decided_by"], c["state"])
                     for c in bundle["claims"])
    assert decided == [(2, "authority-or-deadline-invented", "semantic", "APPLICABLE_FAIL")]
    assert {c["provenance"].get("model") for c in bundle["claims"] if c["decided_by"] == "semantic"} == {"gpt-4o"}


def test_the_tool_calls_are_receipts_and_nothing_is_proven(converted):
    bundle, record = converted
    assert [c["name"] for c in bundle["sources"]["turns"][0]["tool_calls"]] == ["book_repair"]
    assert {f["proof_status"] for f in record["findings"]} == {"UNPROVEN"}


def test_an_edited_output_breaks_verification(converted):
    bundle, record = converted
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][1]["answer"] = "Burst pipes are covered after the deductible."
    assert not eio_agents.verify(record, tampered)["digest_match"]


def test_generic_tool_correctness_and_hallucination_are_not_eio_claims():
    bundle = to_bundle(RUN, DIGEST)
    assert len(bundle["claims"]) == 1
    assert bundle["claims"][0]["turn_indices"] == [2]


def test_missing_tool_output_is_not_marked_captured():
    run = copy.deepcopy(RUN)
    run["testCases"][0]["toolsCalled"][0].pop("output")
    bundle = to_bundle(run, DIGEST)
    assert "result" not in bundle["sources"]["turns"][0]["tool_calls"][0]
    assert bundle["sources"]["completeness"]["tool_outputs"] == "NOT_CAPTURED"
