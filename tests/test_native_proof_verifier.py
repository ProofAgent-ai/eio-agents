"""Source-independent D5 proof-status check, including D3-bypassed forgery."""

import copy
import json
from pathlib import Path

from eio_agents import convert
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.verify import verify as verify_with_rederived


def _provisional_strict_case():
    bundle = json.loads((Path(__file__).parent / "data/native/v0_6/native.bundle.json").read_text(encoding="utf-8"))
    record = convert(bundle)
    # In-memory provisional new-release rule only. The historical 0.4 bytes
    # and module digest on disk are not changed by this synthetic vector.
    eio = EIO(EIO_DIR)
    eio.profiles["eio.profile.proof-status"]["native_claim_proves"] = False
    for finding in record["findings"]:
        finding["proof_status"] = "UNPROVEN"
    return bundle, record, eio


def test_uncited_new_release_requires_unproven_even_if_d3_is_bypassed():
    bundle, record, eio = _provisional_strict_case()
    problems, _ = native_proof_status_gate(bundle, record, eio)
    assert problems == []
    forged = copy.deepcopy(record)
    behavioural = next(row for row in forged["findings"] if row["kind"] == "BEHAVIOURAL")
    behavioural["proof_status"] = "PROVEN"
    problems, _ = native_proof_status_gate(bundle, forged, eio)
    assert problems and "without source proof citations" in problems[0]
    # Deliberately supply the forged record itself as D3's producer output:
    # independent D5 must reject it even when D3 hashes match exactly.
    verification = verify_with_rederived(forged, bundle, rederived=forged, eio=eio)
    assert verification["digest_match"] is True
    assert not verification["valid"]
    assert any(row["check"].startswith("D5 native proof") for row in verification["failures"])


def test_historical_pinned_rule_is_not_retroactively_changed():
    bundle, _, _ = _provisional_strict_case()
    historical = convert(bundle)
    problems, _ = native_proof_status_gate(bundle, historical, EIO(EIO_DIR))
    assert problems == []
