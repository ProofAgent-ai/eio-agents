"""PER 2.1 source-bound HIGH review condition; historical 2.0 stays immutable."""

import copy

import pytest

import eio_agents
from eio_agents import build_bundle
from eio_agents.per import canonical_bytes
from eio_agents.schemas import per_schema
from test_build_semantic import OVERCLAIM, _args


@pytest.fixture(scope="module")
def guarded_case():
    bundle = build_bundle(**_args(dict(OVERCLAIM, predicate="applicable-policy-abandoned")))
    record = eio_agents.convert(bundle)
    assert eio_agents.verify(record, bundle)["valid"]
    return bundle, record


def test_new_wire_is_deterministic_and_source_bound(guarded_case):
    bundle, record = guarded_case
    assert record["header"]["per_version"] == "2.1.0"
    assert record["header"]["release_semantics"] == "2.2"
    assert per_schema("2.1.0")["$id"] == record["header"]["schema_uri"]
    assert canonical_bytes(record) == canonical_bytes(eio_agents.convert(bundle))
    guard = [d for d in record["release_recommendation"]["decisive"] if d["id"] == "eio.release.high-review-queue"]
    assert len(guard) == 1 and guard[0]["effect"] == "REVIEW"
    assert guard[0]["finding_ids"] == sorted(guard[0]["finding_ids"])
    assert record["release_recommendation"]["state"] == "REVIEW"


def test_no_high_queue_has_no_guard():
    bundle = build_bundle(**_args(OVERCLAIM))
    record = eio_agents.convert(bundle)
    assert eio_agents.verify(record, bundle)["valid"]
    # no HIGH-review guard; the record declares no policy, so the release semantics 2.2 default floor reviews it
    decisive = record["release_recommendation"]["decisive"]
    assert not any(d["id"] == "eio.release.high-review-queue" for d in decisive)
    assert record["release_recommendation"]["state"] == "REVIEW"
    assert {d["id"] for d in decisive} <= {"eio.release.default-readiness-floor", "eio.release.hard-block-unmet"}


@pytest.mark.parametrize("mutation", ["forged_pass", "missing_guard", "wrong_guard_id", "wrong_finding_id",
                                      "fake_reportable", "fake_severity"])
def test_forged_guard_or_proof_cannot_verify(guarded_case, mutation):
    bundle, original = guarded_case
    record = copy.deepcopy(original)
    release = record["release_recommendation"]
    guard = next(d for d in release["decisive"] if d["kind"] == "review_guard")
    if mutation == "forged_pass":
        release["state"] = "PASS"
    elif mutation == "missing_guard":
        release["decisive"].remove(guard)
    elif mutation == "wrong_guard_id":
        guard["id"] = "eio.release.not-the-guard"
    elif mutation == "wrong_finding_id":
        guard["finding_ids"] = ["00000000000000000000"]
    elif mutation == "fake_reportable":
        record["scores"]["proof_sets"]["reportable_finding_ids"] = guard["finding_ids"]
    else:
        next(f for f in record["findings"] if f["finding_id"] == guard["finding_ids"][0])["severity"] = "LOW"
    result = eio_agents.verify(record, bundle)
    assert not result["valid"]
    assert any(row["check"].startswith("D4") for row in result["failures"]), result["failures"]
