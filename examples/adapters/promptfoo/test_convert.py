"""Tests of the promptfoo converter: python -m pytest -q test_convert.py"""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.validation import validate_bundle

from convert import to_bundle

EXPORT = json.loads((Path(__file__).parent / "results.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def converted():
    bundle = to_bundle(EXPORT)
    return bundle, eio_agents.convert(bundle)


def test_the_results_convert_to_a_valid_verifiable_per(converted):
    bundle, record = converted
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    assert record["header"]["per_version"] == "2.1.0" and eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_only_the_suite_specific_rbac_assertion_becomes_a_claim(converted):
    bundle, _ = converted
    decided = {c["predicate"].removeprefix("eio.predicate."): (c["decided_by"], c["state"]) for c in bundle["claims"]}
    assert decided == {"unverified-authority-accepted": ("semantic", "APPLICABLE_FAIL")}


def test_an_uncaptured_tool_output_stays_uncaptured_without_claiming_a_policy_breach(converted):
    bundle, record = converted
    turn = bundle["sources"]["turns"][1]
    assert turn["answer"] == "" and [c["name"] for c in turn["tool_calls"]] == ["transfer_funds"]
    assert "result" not in turn["tool_calls"][0]                       # promptfoo runs no tool
    assert bundle["sources"]["completeness"]["tool_outputs"] == "NOT_CAPTURED"
    assert all(not f["predicate"].endswith("prohibited-tool-invoked") for f in record["findings"])


def test_ordinary_contains_and_unconfirmed_transfer_assertions_are_unmapped():
    bundle = to_bundle(EXPORT)
    assert len(bundle["claims"]) == 1
    assert all(c["turn_indices"] == [3] for c in bundle["claims"])


def test_the_red_team_finding_is_supported_not_proven(converted):
    _, record = converted
    finding = next(f for f in record["findings"] if f["predicate"].endswith("unverified-authority-accepted"))
    assert finding["decided_by"] == "semantic" and finding["proof_status"] == "UNPROVEN"


def test_an_edited_output_breaks_verification(converted):
    bundle, record = converted
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][2]["answer"] = "I cannot share another account's balance."
    assert not eio_agents.verify(record, tampered)["digest_match"]
