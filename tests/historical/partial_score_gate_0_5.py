"""Source-derived 0.2 partial-score gate vectors for the rc3 draft."""

import copy

from eio_agents.per.native_score_preview import candidate_scored_per
from eio_agents.validation.canon import jb, sha
from eio_agents.validation.native_score import native_score_gate
from eio_agents.validation.partial_score import load_verifier_score_resources, partial_native_score_gate
from eio_agents.validation.reader import EIO, EIO_DIR
from tests.test_native_score_preview import _preview


def _synthetic_case():
    bundle, unscored, block = _preview()
    record = candidate_scored_per(unscored, block)
    eio = EIO(EIO_DIR)
    approved, schema = load_verifier_score_resources()
    return bundle, record, eio, approved, schema


def test_partial_gate_recomputes_emitted_values_and_keeps_g_readiness_withheld():
    bundle, record, eio, approved, schema = _synthetic_case()
    problems, detail = partial_native_score_gate(bundle, record, eio, source_checked=True,
                                                  approved_profile=approved, approved_schema=schema)
    assert problems == []
    assert "G/readiness withheld" in detail


def test_partial_gate_rejects_resealed_numeric_basis_and_profile_tamper():
    bundle, record, eio, approved, schema = _synthetic_case()
    numeric = copy.deepcopy(record)
    numeric["scores"]["metrics"][0]["value"] = 99.0
    numeric["scores"]["score_sha256"] = sha(jb({k: v for k, v in numeric["scores"].items()
                                                   if k != "score_sha256"}))
    assert partial_native_score_gate(bundle, numeric, eio, source_checked=True,
                                     approved_profile=approved, approved_schema=schema)[0]
    basis = copy.deepcopy(record)
    basis["findings"][0]["display_label"] = "forged"
    assert any("score_basis_sha256" in problem for problem in partial_native_score_gate(
        bundle, basis, eio, source_checked=True, approved_profile=approved, approved_schema=schema)[0])
    profile = copy.deepcopy(record)
    profile["scores"]["scoring_profile"]["sha256"] = "sha256:" + "0" * 64
    profile["scores"]["score_sha256"] = sha(jb({k: v for k, v in profile["scores"].items()
                                                   if k != "score_sha256"}))
    assert any("scoring_profile.sha256" in problem for problem in partial_native_score_gate(
        bundle, profile, eio, source_checked=True, approved_profile=approved, approved_schema=schema)[0])


def test_partial_gate_fails_closed_without_verifier_owned_inputs():
    bundle, record, eio, approved, schema = _synthetic_case()
    assert partial_native_score_gate(bundle, record, eio, source_checked=False,
                                     approved_profile=approved, approved_schema=schema)[0]
    assert partial_native_score_gate(bundle, record, eio, source_checked=True,
                                     approved_profile=None, approved_schema=schema)[0]
    asserted_g = copy.deepcopy(record)
    asserted_g["scores"]["axes"][3]["value"] = 99.0
    asserted_g["scores"]["axes"][3]["status"] = "MEASURED"
    asserted_g["scores"]["score_sha256"] = sha(jb({k: v for k, v in asserted_g["scores"].items()
                                                   if k != "score_sha256"}))
    assert partial_native_score_gate(bundle, asserted_g, eio, source_checked=True,
                                     approved_profile=approved, approved_schema=schema)[0]
    asserted_pass = copy.deepcopy(record)
    asserted_pass["release_recommendation"]["state"] = "PASS"
    # A PASS can be admissible only when source-bound severity has no HIGH
    # review queue; this fixture has no severity-bearing failing obligation.
    assert partial_native_score_gate(bundle, asserted_pass, eio, source_checked=True,
                                     approved_profile=approved, approved_schema=schema)[0] == []
    lowered = copy.deepcopy(record)
    lowered["coverage"]["obligations"][0]["severity"] = "LOW"
    assert any("obligation predicate, severity" in problem for problem in partial_native_score_gate(
        bundle, lowered, eio, source_checked=True,
        approved_profile=approved, approved_schema=schema)[0])
    forged_finding = copy.deepcopy(record)
    forged_finding["findings"][0]["severity"] = "HIGH"
    assert any("finding severity differs" in problem for problem in partial_native_score_gate(
        bundle, forged_finding, eio, source_checked=True,
        approved_profile=approved, approved_schema=schema)[0])
    forged_proof = copy.deepcopy(record)
    forged_proof["findings"][0]["proof_status"] = "PROVEN"
    assert any("D5 native proof" in problem for problem in partial_native_score_gate(
        bundle, forged_proof, eio, source_checked=True,
        approved_profile=approved, approved_schema=schema)[0])


def test_public_d4_hook_has_pinned_resources_and_rejects_historical_release():
    profile, schema = load_verifier_score_resources()
    assert profile["version"] == "0.2.0-draft.1" and schema["properties"]["score_basis_version"]
    bundle, record, _, _, _ = _synthetic_case()
    old_eio = EIO(EIO_DIR)
    old_eio.release = "0.4.0"
    old_eio.profiles["eio.profile.proof-status"]["native_claim_proves"] = True
    problems, _ = native_score_gate(record, bundle, eio=old_eio, source_checked=True)
    assert any("EIO 0.5" in problem for problem in problems)
