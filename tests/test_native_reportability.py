"""D9 R1–R5 proof-citation vectors over a real synthetic native bundle."""
from __future__ import annotations

import copy

import pytest

from eio_agents import convert, validate, verify
from eio_agents.base.canon import H, jb, sd
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.per.native_score_inputs import extract_native_inputs
from eio_agents.per.native_reportability import derive_native_proof_sets
from eio_agents.semantics import ids
from test_native_score_inputs import candidate


def with_citation():
    b = candidate()
    fail = next(c for c in b["claims"] if c["predicate"] == "eio.predicate.authority-or-deadline-invented")
    ref = next(r for r in b["graph"]["refs"] if r["id"] in fail["evidence"] and r["kind"] == "AGENT_SPAN")
    b["native_scoring"]["proof_citations"] = [{"claim_id": fail["id"], "ref_id": ref["id"],
                                                "role": "proof", "citation_anchor": "exact",
                                                "locator_sha256": H(jb(ref))}]
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    return b, fail["id"], ref["id"]


def extract(b):
    ontology = load()
    rec = convert(b, ontology=ontology)
    assert validate(rec) == []
    checked = verify(rec, b, ontology=ontology)
    assert checked["valid"] and checked["digest_match"]
    return rec, extract_native_inputs(b, ontology=ontology, record=rec, verification=checked)


def proof_sets(b, rec):
    ids_by_source = {c["id"]: sd({"run_id": c["run_id"], "predicate": c["predicate"],
                                  "predicate_version": c["predicate_version"],
                                  "source_key": c["parameters"].get("source_key"),
                                  "turn_indices": sorted(c["turn_indices"])}) for c in b["claims"]}
    return derive_native_proof_sets(b, rec, ontology=load(), native_ids=ids_by_source,
                                    verification=verify(rec, b, ontology=load()))


def cap_claim_bundle():
    """Synthetic exact cap failure with its old claim ID and provenance recomputed."""
    b, cid, _rid = with_citation()
    ontology = load()
    claim = next(c for c in b["claims"] if c["id"] == cid)
    predicate = "eio.predicate.untrusted-instruction-execution"
    claim["predicate"] = predicate
    claim["risk"] = ontology.pred[predicate].get("risk")
    claim["parameters"]["fidelity"] = "exact"
    module, version = ontology.mod_of_pred[predicate]
    claim["provenance"].update(module=module, module_version=version, module_hash=ontology.modules[module])
    new_id = ids.claim_id(claim["run_id"], predicate, claim["predicate_version"], None, claim["turn_indices"])
    claim["id"] = new_id
    next(row for row in b["native_scoring"]["claim_bindings"] if row["claim_id"] == cid)["claim_id"] = new_id
    b["native_scoring"]["proof_citations"][0]["claim_id"] = new_id
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    return b


def test_proof_citation_cannot_bypass_unmet_second_contract_group():
    b, _cid, _rid = with_citation()
    rec, out = extract(b)
    fail = next(c for c in rec["claims"] if c["predicate"] == "eio.predicate.authority-or-deadline-invented")
    assert out["reportable_finding_ids"] == []
    assert out["decisive_finding_ids"] == []
    derived = proof_sets(b, rec)
    assert derived["decisive_claim_ids"] == []
    assert derived["reportability"][fail["id"]]["reportable"] is False
    assert derived["reportability"][fail["id"]]["proven"] is False
    assert derived["reportability"][fail["id"]]["unmet"] == ["R3"]


def test_exact_citation_still_cannot_bypass_unmet_second_contract_group():
    b, cid, _rid = with_citation()
    next(c for c in b["claims"] if c["id"] == cid)["parameters"]["fidelity"] = "exact"
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    rec, out = extract(b)
    fail = next(c for c in rec["claims"] if c["predicate"] == "eio.predicate.authority-or-deadline-invented")
    assert fail["id"] != cid
    derived = proof_sets(b, rec)
    assert derived["decisive_claim_ids"] == []
    assert out["decisive_finding_ids"] == []
    assert derived["reportability"][fail["id"]]["unmet"] == ["R3"]
    assert derived["cap_decisive_claim_ids"] == []  # not a cap predicate


def test_exact_cap_failure_is_reportable_decisive_and_cap_eligible():
    b = cap_claim_bundle()
    rec, out = extract(b)
    claim = next(c for c in rec["claims"] if c["predicate"] == "eio.predicate.untrusted-instruction-execution")
    finding = next(f for f in rec["findings"] if claim["id"] in f["claim_ids"])
    assert out["reportable_finding_ids"] == [finding["finding_id"]]
    assert out["decisive_finding_ids"] == [finding["finding_id"]]
    derived = proof_sets(b, rec)
    assert derived["cap_decisive_claim_ids"] == [claim["id"]]
    assert derived["reportability"][claim["id"]]["deferred"] == ["counterevidence"]


def test_semantic_vote_state_contradiction_cannot_enter_scored_per():
    b, _cid, _rid = with_citation()
    semantic = next(c for c in b["claims"] if c["decided_by"] == "semantic")
    semantic["state"] = "APPLICABLE_FAIL"
    b["native_scoring"]["proof_citations"].append({"claim_id": semantic["id"], "ref_id": semantic["evidence"][0],
                                                   "role": "proof", "citation_anchor": "exact",
                                                   "locator_sha256": H(jb(next(r for r in b["graph"]["refs"]
                                                                                if r["id"] == semantic["evidence"][0])))} )
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    with pytest.raises(ConversionError) as error:
        extract(b)
    assert error.value.code == "REFERENCE_VOTES"


def test_missing_citation_declaration_withholds_not_empty():
    b = candidate()
    del b["native_scoring"]["proof_citations"]
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    with pytest.raises(ConversionError) as error:
        extract(b)
    assert error.value.code == "NATIVE_SCORE_PREVIEW"


def test_missing_ontology_proof_group_rejects_cited_proof():
    b = cap_claim_bundle()
    rec, _out = extract(b)
    ontology = load()
    claim = next(c for c in b["claims"] if c["predicate"] == "eio.predicate.untrusted-instruction-execution")
    ontology.pred[claim["predicate"]]["evidence_contract"]["require_groups"] = []
    native_ids = {c["id"]: sd({"run_id": c["run_id"], "predicate": c["predicate"],
                                "predicate_version": c["predicate_version"],
                                "source_key": c["parameters"].get("source_key"),
                                "turn_indices": sorted(c["turn_indices"])}) for c in b["claims"]}
    with pytest.raises(ConversionError) as error:
        derive_native_proof_sets(b, rec, ontology=ontology, native_ids=native_ids,
                                 verification=verify(rec, b, ontology=load()))
    assert error.value.code == "NATIVE_PROOF"


@pytest.mark.parametrize("change", [
    lambda b: b["native_scoring"]["proof_citations"][0].update(role="context"),
    lambda b: b["native_scoring"]["proof_citations"][0].update(citation_anchor="turn"),
    lambda b: b["native_scoring"]["proof_citations"][0].update(citation_anchor="receipt"),
    lambda b: b["native_scoring"]["proof_citations"][0].update(locator_sha256="sha256:" + "0" * 64),
    lambda b: b["native_scoring"]["proof_citations"][0].update(ref_id="not-cited"),
    lambda b: b["native_scoring"]["proof_citations"].append(copy.deepcopy(b["native_scoring"]["proof_citations"][0])),
])
def test_forged_or_duplicate_proof_citations_fail_closed(change):
    b, _cid, _rid = with_citation()
    change(b)
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    with pytest.raises(ConversionError):
        # Schema/locator/citation check may reject before any PER is emitted.
        extract(b)


def test_typed_absence_and_user_input_cannot_be_promoted_to_proof():
    b, cid, _rid = with_citation()
    fail = next(c for c in b["claims"] if c["id"] == cid)
    user_ref = next(r for r in b["graph"]["refs"] if r["id"] in fail["evidence"] and r["kind"] == "USER_INPUT")
    b["native_scoring"]["proof_citations"][0].update(ref_id=user_ref["id"])
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    with pytest.raises(ConversionError):
        extract(b)

    b, _cid, _rid = with_citation()
    absence = next(c for c in b["claims"] if c["predicate"] == "eio.predicate.prohibited-tool-invoked")
    b["native_scoring"]["proof_citations"].append({"claim_id": absence["id"], "ref_id": absence["evidence"][0],
                                                   "role": "proof", "citation_anchor": "computed",
                                                   "locator_sha256": H(jb(next(r for r in b["graph"]["refs"]
                                                                                if r["id"] == absence["evidence"][0])))} )
    for stage in b["stage_records"]:
        stage["output_sha256"] = B.stage_digest(b, stage["sections"])
    with pytest.raises(ConversionError):
        extract(b)
