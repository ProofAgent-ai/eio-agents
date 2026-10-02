"""Synthetic NEW-release S1b proof vectors; no ontology digest is reissued here."""
from __future__ import annotations

import copy
import importlib

import pytest

from eio_agents import convert
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.per.projection import strict_native_proof_required
from eio_agents.semantics.proof import native_claim_proven
from eio_agents.validation import validate_bundle
from test_native_score_inputs import candidate


def new_draft_ontology():
    ontology = load()
    # Exercise the owner-approved branch before the coordinated release reissue.
    # This in-memory object must never be passed off as a signed public pin.
    ontology.profiles["eio.profile.proof-status"]["native_claim_proves"] = False
    return ontology


def test_rc_package_version_is_accepted_only_in_version_fields():
    bundle = candidate()
    bundle["header"]["eio_agents"]["version"] = "0.5.0rc1"
    ontology = load()
    validation_twin = importlib.import_module("eio_agents.validation.validate")
    assert B.shape_problems(bundle, ontology) == []
    assert validation_twin.shape_problems(bundle, ontology) == []
    assert validate_bundle(bundle) == []

    bundle["provenance"]["producer"]["name"] = "alpha@example.com"
    assert B.shape_problems(bundle, ontology)
    assert validation_twin.shape_problems(bundle, ontology)


def with_citation():
    bundle = candidate()
    claim = next(c for c in bundle["claims"] if c["predicate"] == "eio.predicate.authority-or-deadline-invented")
    ref = next(r for r in bundle["graph"]["refs"] if r["id"] in claim["evidence"] and r["kind"] == "AGENT_SPAN")
    bundle["native_scoring"]["proof_citations"] = [
        {"claim_id": claim["id"], "ref_id": ref["id"], "role": "proof",
         "citation_anchor": ref["anchor"], "locator_sha256": H(jb(ref))}]
    return bundle, claim, ref


def project(bundle):
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    return convert(bundle, ontology=new_draft_ontology())


def finding(record):
    return next(f for f in record["findings"] if f["predicate"] == "eio.predicate.authority-or-deadline-invented")


def test_strong_ref_without_claim_level_proof_citation_has_no_partial_profile():
    bundle, claim, _ = with_citation()
    claim["parameters"]["fidelity"] = "exact"
    bundle["native_scoring"].pop("proof_citations")
    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        project(bundle)


def test_exact_verified_citation_with_unmet_contract_is_unproven():
    bundle, claim, _ = with_citation()
    claim["parameters"]["fidelity"] = "exact"
    assert finding(project(bundle))["proof_status"] == "UNPROVEN"


def test_narrower_needs_confirmed_recurrence_even_with_citation():
    bundle, _, _ = with_citation()
    assert finding(project(bundle))["proof_status"] == "UNPROVEN"
    claim = {"decided_by": "deterministic", "parameters": {"contract_check": {"unmet": []}}}
    assert native_claim_proven(claim, "INTERMITTENT", "narrower", [{"role": "proof"}]) is False
    assert native_claim_proven(claim, "CONFIRMED", "narrower", [{"role": "proof"}]) is True
    assert native_claim_proven(claim, "CONFIRMED", "narrower", []) is False


@pytest.mark.parametrize("change", [
    lambda bundle: bundle["native_scoring"]["proof_citations"][0].update(citation_anchor="turn"),
    lambda bundle: bundle["native_scoring"]["proof_citations"][0].update(locator_sha256="sha256:" + "0" * 64),
    lambda bundle: bundle["native_scoring"]["proof_citations"][0].update(role="context"),
])
def test_forged_role_anchor_or_locator_never_upgrades_ref_level_proof(change):
    bundle, claim, _ = with_citation()
    claim["parameters"]["fidelity"] = "exact"
    change(bundle)
    with pytest.raises(ConversionError):
        project(bundle)


def test_typed_absence_is_not_a_proof_citation():
    bundle, _, _ = with_citation()
    absence = next(c for c in bundle["claims"] if c["predicate"] == "eio.predicate.prohibited-tool-invoked")
    typed = next(r for r in bundle["graph"]["refs"] if r["id"] in absence["evidence"] and r["kind"] == "TYPED_ABSENCE")
    bundle["native_scoring"]["proof_citations"].append(
        {"claim_id": absence["id"], "ref_id": typed["id"], "role": "proof",
         "citation_anchor": typed["anchor"], "locator_sha256": H(jb(typed))})
    with pytest.raises(ConversionError):
        project(bundle)


def test_semantic_decision_never_proven_even_with_valid_citation():
    claim = {"decided_by": "semantic", "parameters": {"contract_check": {"unmet": []}}}
    assert native_claim_proven(claim, "CONFIRMED", "exact", [{"role": "proof"}]) is False


def test_spoofed_historical_proof_flag_cannot_bypass_draft_score_checks():
    bundle, claim, _ = with_citation()
    claim["parameters"]["fidelity"] = "exact"
    bundle["native_scoring"].pop("proof_citations")
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    # A historical pinned loader is external to this new-release package.
    # Flipping one flag in the new release must not spoof a compatible old pin.
    old_rule = load()
    old_rule.profiles["eio.profile.proof-status"]["native_claim_proves"] = True
    assert strict_native_proof_required(old_rule, "native") is False
    with pytest.raises(ConversionError, match="NATIVE_SCORE_PREVIEW"):
        convert(copy.deepcopy(bundle), ontology=old_rule)


def test_rule_selection_is_pinned_and_per_version_agnostic():
    # The same selector serves an rc3-draft or later PER projection; it takes
    # neither a bridge switch nor a PER schema/version string.
    assert strict_native_proof_required(new_draft_ontology(), "native") is True
    assert strict_native_proof_required(new_draft_ontology(), "adapter") is False
    assert strict_native_proof_required(load(), "native") is True


def test_new_release_rejects_an_old_release_bundle():
    bundle, _, _ = with_citation()
    bundle["header"]["eio"]["release"] = "0.4.0"
    with pytest.raises(ConversionError, match="BUNDLE_RECOMPUTE"):
        convert(bundle)
