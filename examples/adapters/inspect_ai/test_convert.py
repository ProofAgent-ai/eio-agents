"""Tests of the Inspect converter: python -m pytest -q test_convert.py"""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.validation import validate_bundle

from convert import CROSSWALK, to_bundle

LOG = json.loads((Path(__file__).parent / "eval_log.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def converted():
    bundle = to_bundle(LOG)
    return bundle, eio_agents.convert(bundle)


def test_the_log_converts_to_a_valid_verifiable_per(converted):
    bundle, record = converted
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    assert record["header"]["per_version"] == "2.1.0" and eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_each_sample_is_a_turn_and_each_mapped_score_a_claim(converted):
    bundle, record = converted
    assert len(bundle["sources"]["turns"]) == len(LOG["samples"])
    mapped = [(n, s) for n, sample in enumerate(LOG["samples"], 1) for s, v in sample["scores"].items()
              if s in CROSSWALK and v["value"] in ("C", "I")]
    assert len(record["claims"]) == len(mapped) == 1         # generic includes/fact scores are not EIO claims
    calls = [c["name"] for t in bundle["sources"]["turns"] for c in t["tool_calls"]]
    assert calls == ["get_baggage_policy", "cancel_booking"]


def test_only_the_suite_specific_confirmation_check_is_mapped(converted):
    _, record = converted
    assert [(c["predicate"], c["parameters"]["fidelity"]) for c in record["claims"]] == [
        ("eio.predicate.protected-action-requires-verification", "narrower")]
    assert {f["proof_status"] for f in record["findings"]} == {"UNPROVEN"}
    assert record["scores"]["readiness"]["status"] == "WITHHELD"       # the log has no context ratings


def test_uncaptured_tool_output_is_not_misreported_as_captured():
    log = copy.deepcopy(LOG)
    log["samples"][0]["messages"] = [m for m in log["samples"][0]["messages"] if m["role"] != "tool"]
    bundle = to_bundle(log)
    assert "result" not in bundle["sources"]["turns"][0]["tool_calls"][0]
    assert bundle["sources"]["completeness"]["tool_outputs"] == "NOT_CAPTURED"


def test_an_edited_answer_breaks_verification(converted):
    bundle, record = converted
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][2]["answer"] = "Compensation depends on the distance."
    assert not eio_agents.verify(record, tampered)["digest_match"]


def test_the_conversion_is_deterministic(converted):
    assert eio_agents.per_sha256(eio_agents.convert(to_bundle(LOG))) == eio_agents.per_sha256(converted[1])
