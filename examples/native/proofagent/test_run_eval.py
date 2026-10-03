"""Tests of the native run: python -m pytest -q test_run_eval.py"""
import copy
import json

import eio_agents
from eio_agents.validation import validate_bundle

from run_eval import evaluate


def test_the_run_emits_a_valid_verifiable_per_2_0_0():
    bundle, record = evaluate()
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    assert record["header"]["per_version"] == "2.1.0" and eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_it_is_a_native_producer_with_exact_fidelity():
    bundle, record = evaluate()
    assert bundle["provenance"]["producer"]["kind"] == "native" and bundle["header"]["adapter"] is None
    assert bundle["header"]["crosswalk"] is None
    assert {c["parameters"]["fidelity"] for c in bundle["claims"]} == {"exact"}


def test_the_captured_evidence_proves_the_overclaim_and_the_jury_only_supports():
    _, record = evaluate()
    status = {f["predicate"].removeprefix("eio.predicate."): f["proof_status"] for f in record["findings"]}
    assert status == {"certainty-exceeds-evidence": "PROVEN", "protected-action-requires-verification": "UNPROVEN"}
    graded = [c for c in record["claims"] if c["decided_by"] == "semantic"]
    assert [c["predicate"] for c in graded] == ["eio.predicate.prohibited-part-clearly-refused"]
    assert graded[0]["provenance"]["model"] == "acme/jury-llm-1"             # the jury's model, in clear


def test_the_run_is_deterministic():
    assert eio_agents.per_sha256(evaluate()[1]) == eio_agents.per_sha256(evaluate()[1])


def test_editing_a_captured_turn_breaks_verification():
    bundle, record = evaluate()
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][0]["answer"] = "Your refund arrives in 3 to 5 days."
    assert not eio_agents.verify(record, tampered)["digest_match"]


def test_the_jury_ballots_pool_into_the_claim():
    bundle, _ = evaluate()
    claim = next(c for c in bundle["claims"] if c["decided_by"] == "semantic")
    ballots = [b for b in bundle["ballots"]["ballots"] if b["claim_id"] == claim["id"]]
    assert sorted({(b["persona"], b["round"]) for b in ballots}) == [
        (p, r) for p in ("lenient", "neutral", "strict") for r in (1, 2)]
    assert claim["parameters"]["votes"] == {"distinct_pairs": 6, "observed": 6, "not_observed": 0, "split": 0}
    assert bundle["ballots"]["pooled_claims"] == [claim["id"]]
