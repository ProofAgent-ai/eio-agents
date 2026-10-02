"""Independent record-check mutations on a valid native rc2 baseline.

The original 31 producer-specific mutations are preserved byte-for-byte in the external
producer-adapter compatibility corpus. Running them on a mismatched neutral
release gave false positives: every mutation appeared caught because the
unmodified historical record already failed. This suite first proves its
native baseline is clean, then requires the named check to catch each defect.
"""
import copy
import json
from pathlib import Path

import pytest

from eio_agents.validation.checker import Checker
from eio_agents.validation.reader import EIO, EIO_DIR, load_catalogue

NATIVE = Path(__file__).parent / "data/native/v0_6/native.per.jcs"
CHECKS = tuple(name for name in dir(Checker) if name.startswith("c_") and name != "c_per_sha")


@pytest.fixture(scope="module")
def verifier():
    return EIO(EIO_DIR), load_catalogue()


def _record():
    return json.loads(NATIVE.read_text(encoding="utf-8"))


def _failed(verifier, record, checks=CHECKS):
    eio, catalogue = verifier
    checker = Checker(record, eio, catalogue, "native")
    for name in checks:
        checker.run(name, "", getattr(checker, name))
    return {name: detail for name, _, status, detail in checker.rows if status == "FAIL"}


def _user_input_proves(record):
    next(ref for ref in record["evidence"]["refs"] if ref["kind"] == "USER_INPUT")["can_prove_agent_behaviour"] = True


def _count_changed(record):
    record["evidence"]["counts"]["refs"] += 1


def _claim_id_changed(record):
    record["claims"][0]["id"] = "0" * 20


def _unknown_predicate(record):
    record["claims"][0]["predicate"] = "eio.predicate.no-such-predicate"


def _module_hash_changed(record):
    record["header"]["eio"]["modules"]["eio.core.flow"] = "sha256:" + "0" * 64


def _ref_dropped(record):
    record["evidence"]["refs"].pop(0)


def _contract_dropped(record):
    next(claim for claim in record["claims"] if claim["state"] == "APPLICABLE_PASS")["parameters"].pop("contract_check")


def _limitation_text_changed(record):
    record["limitations"][0]["reason"] = "Different reason."


def _gate_result_changed(record):
    next(gate for gate in record["release_recommendation"]["gate_results"] if gate["met"] is False)["met"] = True


def _release_state_changed(record):
    record["release_recommendation"]["state"] = "BLOCK"


def _finding_fidelity_removed(record):
    next(f for f in record["findings"] if f["kind"] == "BEHAVIOURAL")["fidelity"] = None


def _claims_reordered(record):
    record["claims"].reverse()


MUTATIONS = (
    ("user input cannot prove behaviour", "c_witness", _user_input_proves),
    ("evidence count recomputes", "c_counts", _count_changed),
    ("claim identifier recomputes", "c_claim_ids", _claim_id_changed),
    ("predicate is in the ontology", "c_eio_ids", _unknown_predicate),
    ("module digest is pinned", "c_eio_digests", _module_hash_changed),
    ("cited refs resolve", "c_refs_resolve", _ref_dropped),
    ("contract check is present", "c_contract", _contract_dropped),
    ("limitation text is canonical", "c_limitations", _limitation_text_changed),
    ("gate result recomputes", "c_gates", _gate_result_changed),
    ("release state recomputes", "c_release", _release_state_changed),
    ("behavioural fidelity is declared", "c_schema", _finding_fidelity_removed),
    ("claim order is canonical", "c_order", _claims_reordered),
)


def test_native_baseline_passes_every_independent_record_check(verifier):
    assert _failed(verifier, _record()) == {}


@pytest.mark.parametrize("name,check,mutate", MUTATIONS, ids=[row[0] for row in MUTATIONS])
def test_native_defect_is_caught_by_its_named_independent_check(verifier, name, check, mutate):
    baseline = _record()
    assert _failed(verifier, baseline, (check,)) == {}, f"dirty baseline for {name}"
    changed = copy.deepcopy(baseline)
    mutate(changed)
    failures = _failed(verifier, changed, (check,))
    assert check in failures, f"{name} escaped {check}"
