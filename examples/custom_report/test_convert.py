"""Tests of my report -> EIO bundle -> PER conversion. Run with: python -m pytest -q test_convert.py"""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.validation import validate_bundle

from convert import to_bundle

REPORT = json.loads((Path(__file__).parent / "my_report.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle():
    return to_bundle(REPORT)


@pytest.fixture(scope="module")
def per(bundle):
    return eio_agents.convert(bundle)


def test_the_bundle_is_valid(bundle):
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []


def test_the_record_is_a_valid_per_2_1_0(per):
    assert per["header"]["per_version"] == "2.1.0"
    assert eio_agents.validate(per) == []


def test_the_record_verifies_against_its_bundle(per, bundle):
    result = eio_agents.verify(per, bundle)
    assert result["valid"] and result["digest_match"]


def test_without_a_policy_the_low_readiness_record_goes_to_review(per):
    release = per["release_recommendation"]
    assert release["policy"]["source"] == "none" and release["state"] == "REVIEW"
    assert [d["id"] for d in release["decisive"]] == ["eio.release.default-readiness-floor", "eio.release.hard-block-unmet"]
    assert "readiness >= 85.0" in release["explanation"]["summary"]


def test_the_conversion_is_deterministic(per):
    assert eio_agents.per_sha256(eio_agents.convert(to_bundle(REPORT))) == eio_agents.per_sha256(per)


def test_every_check_became_a_claim_and_the_failure_a_finding(per):
    assert sorted(c["state"] for c in per["claims"]) == ["APPLICABLE_FAIL", "APPLICABLE_PASS", "APPLICABLE_PASS"]
    assert len(per["findings"]) == 1
    assert eio_agents.explain(per, per["findings"][0]["finding_id"])


def test_ordinary_task_completion_is_not_mapped_to_the_mixed_request_predicate():
    report = copy.deepcopy(REPORT)
    report["checks"][0]["check"] = "task_completed"
    bundle = to_bundle(report)
    assert "eio.predicate.permissible-task-completed" not in {c["predicate"] for c in bundle["claims"]}
    assert len(bundle["claims"]) == 2


def test_editing_the_transcript_breaks_verification(per, bundle):
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][2]["answer"] = "There is no cancellation fee."
    assert not eio_agents.verify(per, tampered)["digest_match"]


def test_a_quote_the_agent_did_not_say_is_refused():
    report = copy.deepcopy(REPORT)
    report["checks"][2]["quote"] = "Airline rules say you may cancel for free"
    with pytest.raises(eio_agents.ConversionError, match="BUILD_QUOTE"):
        to_bundle(report)
