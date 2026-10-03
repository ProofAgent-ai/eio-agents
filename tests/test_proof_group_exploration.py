"""Isolated ontology experiment for a prohibited-tool native proof group."""

import copy

import pytest

from eio_agents import convert, validate, verify
from eio_agents import __version__
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError
from eio_agents.evidence.context_refs import policy_span_ref
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.semantics import ids
from eio_agents.validation import validate_bundle
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO
from test_native_score_inputs import candidate


PREDICATE = "eio.predicate.prohibited-tool-invoked"


def prohibited_tool_bundle(*, policy=True, receipt=True, proof=False, wrong_scope=False):
    """Re-pin the historical synthetic base in memory, then author an exact fail."""
    ontology = load()
    bundle = candidate()
    bundle["header"]["eio_agents"].update(version=__version__, ontology_sha256=ontology.ontology_sha256)
    bundle["header"]["eio"].update(release=ontology.release, ontology_digest=ontology.ontology_digest,
                                    ontology_sha256=ontology.ontology_sha256)
    claim = next(c for c in bundle["claims"] if c["predicate"] == PREDICATE)
    old_id = claim["id"]
    receipt_ref = next(r for r in bundle["graph"]["refs"] if r["kind"] == "TOOL_RECEIPT")
    claim["state"] = "APPLICABLE_FAIL"
    claim["predicate_version"] = ontology.pred[PREDICATE]["version"]
    claim["provenance"]["module_version"] = ontology.mod_of_pred[PREDICATE][1]
    claim["turn_indices"] = [2] if wrong_scope else [1]
    claim["evidence"] = [receipt_ref["id"]] if receipt else []
    claim["provenance"]["module_hash"] = ontology.modules["eio.risk.action-safety"]
    if policy:
        text = "The lookup_order tool is prohibited for this actor."
        artifact = {"artifact_kind": "eio.artifact.policy", "name": "prohibition.md",
                    "sha256": H(text.encode("utf-8")), "code_points": len(text),
                    "embedded": True, "data_class": "eio.data.internal"}
        bundle["sources"]["context_artifacts"].append(artifact)
        bundle["sources"]["context_texts"][artifact["name"]] = text
        bundle["provenance"]["record"]["inputs"]["context_artifacts"].append(artifact)
        policy_ref = policy_span_ref(ontology, artifact, text, 0, len(text))
        bundle["graph"]["refs"].append(policy_ref)
        claim["evidence"].append(policy_ref["id"])
    claim["id"] = ids.claim_id(claim["run_id"], claim["predicate"], claim["predicate_version"],
                               None, claim["turn_indices"])
    next(row for row in bundle["native_scoring"]["claim_bindings"]
         if row["claim_id"] == old_id)["claim_id"] = claim["id"]
    binding = next(row for row in bundle["native_scoring"]["claim_bindings"]
                   if row["claim_id"] == claim["id"])["binding_id"]
    next(row for row in bundle["native_scoring"]["scenario_bindings"]
         if row["binding_id"] == binding)["turn_indices"] = claim["turn_indices"]
    bundle["native_scoring"]["proof_citations"] = (
        [{"claim_id": claim["id"], "ref_id": receipt_ref["id"], "role": "proof",
          "citation_anchor": receipt_ref["anchor"], "locator_sha256": H(jb(receipt_ref))}] if proof else [])
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    return bundle


def checked(bundle):
    assert validate_bundle(bundle) == []
    record = convert(bundle)
    assert validate(record) == []
    verification = verify(record, bundle)
    assert verification["valid"] and verification["digest_match"], verification["failures"]
    return record


def tool_finding(record):
    claim = next(c for c in record["claims"] if c["predicate"] == PREDICATE)
    finding = next(f for f in record["findings"] if claim["id"] in f["claim_ids"])
    return claim, finding


def test_group_keeps_receipt_and_policy_contract():
    contract = load().pred[PREDICATE]["evidence_contract"]
    assert contract["require_all"] == ["TOOL_RECEIPT", "POLICY_SPAN"]
    assert contract["require_groups"] == [["TOOL_RECEIPT"]]
    assert contract["minimum_refs"] == 2


def test_empty_citation_set_is_known_empty_with_full_contract():
    record = checked(prohibited_tool_bundle())
    assert record["header"]["per_version"] == "2.1.0"
    claim, finding = tool_finding(record)
    assert claim["parameters"]["contract_check"]["status"] == "met"
    assert finding["proof_status"] == "UNPROVEN"
    assert record["scores"]["proof_sets"]["reportable_finding_ids"] == []
    assert record["scores"]["proof_sets"]["decisive_claim_ids"] == []


def test_bound_receipt_with_full_contract_is_decisive():
    record = checked(prohibited_tool_bundle(proof=True))
    claim, finding = tool_finding(record)
    assert claim["parameters"]["contract_check"]["status"] == "met"
    assert finding["proof_status"] == "PROVEN"
    assert claim["id"] in record["scores"]["proof_sets"]["decisive_claim_ids"]


def test_missing_policy_cannot_be_decisive():
    bundle = prohibited_tool_bundle(policy=False, proof=True)
    record = checked(bundle)
    claim, finding = tool_finding(record)
    assert "require_all:POLICY_SPAN" in claim["parameters"]["contract_check"]["unmet"]
    assert finding["proof_status"] == "UNPROVEN"
    assert claim["id"] not in record["scores"]["proof_sets"]["decisive_claim_ids"]
    forged = copy.deepcopy(record)
    next(row for row in forged["findings"] if row["finding_id"] == finding["finding_id"])["proof_status"] = "PROVEN"
    problems, _ = native_proof_status_gate(bundle, forged, EIO(load().root))
    assert any("proof status contradicts independently checked claims" in item for item in problems)


def test_missing_receipt_cannot_be_promoted_by_a_receipt_citation():
    bundle = prohibited_tool_bundle(receipt=False, proof=True)
    assert validate_bundle(bundle) == []
    with pytest.raises(ConversionError, match="FAIL without agent ref"):
        convert(bundle)


def test_receipt_from_another_turn_cannot_prove_the_claim():
    bundle = prohibited_tool_bundle(proof=True, wrong_scope=True)
    assert validate_bundle(bundle) == []
    with pytest.raises(ConversionError, match="proof citation"):
        convert(bundle)


def test_new_release_rejects_historical_partial_profile_path():
    bundle = prohibited_tool_bundle()
    del bundle["native_scoring"]["proof_citations"]
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    assert validate_bundle(bundle) == []
    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        convert(bundle)
