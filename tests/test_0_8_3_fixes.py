"""EIO-Agents 0.8.3: native proof is per claim (D-47), and a failure the proof rule cannot prove is still recorded.

The vector `data/native/v0_8_3/proof-per-claim.bundle.json` (authored by `author_v0_8_3.py` beside it) is a synthetic
three-turn native run with four failures: an exact, cited, code-verified refusal failure (turn 1); a narrower, cited one
of the same predicate (turn 2); a jury failure of the same predicate (turn 3); and a jury failure of
`claim-contradicts-grounding`, whose evidence contract has no group that can prove agent behaviour (turn 3).

Each test fails on 0.8.2: there, claims 1-3 formed one finding that was PROVEN because one of its claims was (so the two
unproven claims counted as PROVEN), and claim 4 withheld every proof set, so `build_bundle` refused the run.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents import ConversionError, canonical_bytes, convert, validate, verify
from eio_agents.base.canon import sd
from eio_agents.ontology import load
from eio_agents.validation.native_score import ScoreInputError, derive_proof_sets
from eio_agents.validation.reader import EIO
from full_native_score_case import reseal_stages
from released_version import library_version

HERE = Path(__file__).parent / "data/native/v0_8_3"
ISSUED = "0.8.3"
BUNDLE_SHA256 = "263ce918d16537253ce9afb2387f8c54f79897d0f4875a901a981471b728f674"
P46 = "eio.predicate.prohibited-part-clearly-refused"
UNPROVABLE = "eio.predicate.claim-contradicts-grounding"


def _author():
    spec = importlib.util.spec_from_file_location("author_v0_8_3", HERE / "author_v0_8_3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle_bytes():
    return (HERE / "proof-per-claim.bundle.json").read_bytes()


def _checked(bundle):
    record = convert(bundle)
    assert validate(record) == []
    result = verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]
    return record


def _by_turn(record):
    claims = {c["id"]: c for c in record["claims"]}
    return {f["finding_id"]: (f, sorted((claims[c]["turn_indices"][0], claims[c]["decided_by"]) for c in f["claim_ids"]))
            for f in record["findings"]}


# ------------------------------------------------------------------------------------------------ the vector
def test_vector_is_exact_valid_and_verified():
    bundle_bytes = _bundle_bytes()
    assert hashlib.sha256(bundle_bytes).hexdigest() == BUNDLE_SHA256
    with library_version(ISSUED):
        record = convert(bundle_bytes)
        assert canonical_bytes(record) == (HERE / "proof-per-claim.per.jcs").read_bytes()
        assert validate(record) == []
        result = verify(record, bundle_bytes)
        assert result["valid"] and result["digest_match"], result["failures"]


def test_the_author_script_rebuilds_the_vector():
    with library_version(ISSUED):
        bundle = _author().build()
    assert (json.dumps(bundle, indent=1, ensure_ascii=False) + "\n").encode("utf-8") == _bundle_bytes()


# ------------------------------------------------------------------------------------------- proof per claim
def test_a_proven_finding_holds_only_proven_claims():
    record = _checked(json.loads(_bundle_bytes()))
    p46 = [f for f in record["findings"] if f["predicate"] == P46]
    assert sorted(f["proof_status"] for f in p46) == ["PROVEN", "UNPROVEN"]
    proven = next(f for f in p46 if f["proof_status"] == "PROVEN")
    unproven = next(f for f in p46 if f["proof_status"] == "UNPROVEN")
    claims = {c["id"]: c for c in record["claims"]}
    assert [claims[c]["turn_indices"] for c in proven["claim_ids"]] == [[1]]
    assert sorted(claims[c]["turn_indices"][0] for c in unproven["claim_ids"]) == [2, 3]
    assert proven["fingerprint"] == unproven["fingerprint"]
    run_id = record["provenance"]["run"]["run_id"]
    assert proven["finding_id"] == sd({"run_id": run_id, "fingerprint": proven["fingerprint"]})
    assert unproven["finding_id"] == sd({"run_id": run_id, "fingerprint": unproven["fingerprint"],
                                         "proof_status": "UNPROVEN"})
    sets = record["scores"]["proof_sets"]
    assert sets["decisive_finding_ids"] == [proven["finding_id"]]
    assert sets["decisive_claim_ids"] == proven["claim_ids"]
    # the unproven part holds a jury claim that is not reportable, so it is not reported
    assert sets["reportable_finding_ids"] == [proven["finding_id"]]


def test_a_finding_is_reported_only_when_every_claim_it_counts_is_reportable():
    record = _checked(_author().build(with_jury_refusal=False))
    unproven = next(f for f in record["findings"] if f["predicate"] == P46 and f["proof_status"] == "UNPROVEN")
    claims = {c["id"]: c for c in record["claims"]}
    assert [(claims[c]["turn_indices"], claims[c]["parameters"]["fidelity"]) for c in unproven["claim_ids"]] == [
        ([2], "narrower")]
    assert unproven["finding_id"] in record["scores"]["proof_sets"]["reportable_finding_ids"]
    assert unproven["finding_id"] not in record["scores"]["proof_sets"]["decisive_finding_ids"]


def test_a_finding_with_one_part_keeps_the_plain_id():
    record = _checked(_author().build(with_jury_refusal=False))
    gap = next(f for f in record["findings"] if f["predicate"] == UNPROVABLE)
    assert gap["finding_id"] == sd({"run_id": record["provenance"]["run"]["run_id"], "fingerprint": gap["fingerprint"]})


# ----------------------------------------------------------------- a failure the proof rule cannot prove is recorded
def test_a_failure_on_a_proof_ineligible_predicate_is_an_unproven_finding():
    record = _checked(json.loads(_bundle_bytes()))
    [gap] = [f for f in record["findings"] if f["predicate"] == UNPROVABLE]
    assert gap["proof_status"] == "UNPROVEN"
    sets = record["scores"]["proof_sets"]
    assert sets["reportable_finding_ids"] is not None                       # 0.8.2 withheld every set
    assert gap["finding_id"] not in sets["reportable_finding_ids"]


def test_verifier_twin_derives_the_same_sets():
    bundle = json.loads(_bundle_bytes())
    record = _checked(bundle)
    eio = EIO(load().root)
    derived = derive_proof_sets(bundle, record, eio)
    assert derived["withheld"] is None
    sets = record["scores"]["proof_sets"]
    assert derived["reportable_finding_ids"] == sets["reportable_finding_ids"]
    assert derived["decisive_finding_ids"] == sets["decisive_finding_ids"]
    assert derived["decisive_claim_ids"] == sets["decisive_claim_ids"]


# --------------------------------------------------------------------------------------------- forged records
def _merged(record):
    """The 0.8.2 shape: the split refusal findings joined into one PROVEN finding with the plain id."""
    forged = copy.deepcopy(record)
    p46 = [f for f in forged["findings"] if f["predicate"] == P46]
    keep = next(f for f in p46 if f["proof_status"] == "PROVEN")
    other = next(f for f in p46 if f["proof_status"] == "UNPROVEN")
    keep["claim_ids"] = keep["claim_ids"] + other["claim_ids"]
    keep["turn_indices"] = sorted(set(keep["turn_indices"]) | set(other["turn_indices"]))
    forged["findings"] = [f for f in forged["findings"] if f is not other]
    return forged


def test_a_proven_finding_with_an_unproven_claim_fails_both_twins():
    bundle = json.loads(_bundle_bytes())
    forged = _merged(_checked(bundle))
    assert validate(forged) != []
    result = verify(forged, bundle)
    assert not result["valid"]
    with pytest.raises(ScoreInputError):
        derive_proof_sets(bundle, forged, EIO(load().root))


def test_the_unproven_part_must_carry_the_discriminated_id():
    bundle = json.loads(_bundle_bytes())
    record = _checked(bundle)
    forged = copy.deepcopy(record)
    unproven = next(f for f in forged["findings"] if f["predicate"] == P46 and f["proof_status"] == "UNPROVEN")
    unproven["finding_id"] = sd({"run_id": record["provenance"]["run"]["run_id"], "fingerprint": unproven["fingerprint"]})
    assert any("finding_id" in row["detail"] for row in validate(forged))


# ------------------------------------------------------------------- D-47: a proof cites a relevant witness only
def test_a_proof_citation_of_a_kind_outside_the_contract_group_is_refused():
    """The cited ref must be of a kind the predicate's evidence contract names in its first group that can prove agent
    behaviour (D-47): citing the user's own message as the proof of a refusal failure is refused by both twins."""
    bundle = json.loads(_bundle_bytes())
    claims = {c["id"]: c for c in bundle["claims"]}
    row = next(r for r in bundle["native_scoring"]["proof_citations"] if claims[r["claim_id"]]["turn_indices"] == [1])
    refs = {r["id"]: r for r in bundle["graph"]["refs"]}
    user = next(refs[rid] for rid in claims[row["claim_id"]]["evidence"] if refs[rid]["kind"] == "USER_INPUT")
    row.update(ref_id=user["id"], citation_anchor=user["anchor"],
               locator_sha256="sha256:" + hashlib.sha256(canonical_bytes(user)).hexdigest())
    with pytest.raises(ConversionError):
        convert(reseal_stages(bundle))
    record = _checked(json.loads(_bundle_bytes()))
    with pytest.raises(ScoreInputError):
        derive_proof_sets(bundle, record, EIO(load().root))


def test_build_bundle_cites_only_contract_kinds():
    bundle = json.loads(_bundle_bytes())
    ontology = eio_agents.ontology.load()
    refs = {r["id"]: r for r in bundle["graph"]["refs"]}
    claims = {c["id"]: c for c in bundle["claims"]}
    for row in bundle["native_scoring"]["proof_citations"]:
        predicate = claims[row["claim_id"]]["predicate"]
        groups = ontology.pred[predicate]["evidence_contract"]["require_groups"]
        first = next(set(g) for g in groups if any(ontology.kind[k]["can_prove_agent_behaviour"] for k in g))
        assert refs[row["ref_id"]]["kind"] in first
