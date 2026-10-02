"""Nonnumeric reference-scoring basis over a pinned ontology release."""

import copy

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.scoring import profiles, reference


def claim(cid, predicate, state="APPLICABLE_FAIL", decided_by="deterministic"):
    return {"id": cid, "predicate": predicate, "state": state, "decided_by": decided_by}


def test_basis_is_claim_derived_and_bound_to_the_complete_ontology():
    ontology = load()
    profile = profiles.reference_document(ontology)
    claims = [
        claim("failed-cap", "eio.predicate.prohibited-tool-invoked"),
        claim("passed-cap", "eio.predicate.prohibited-tool-invoked", "APPLICABLE_PASS"),
        claim("semantic-cap", "eio.predicate.prohibited-tool-invoked", decided_by="semantic"),
        claim("unresolved-cap", "eio.predicate.prohibited-tool-invoked", "UNRESOLVED"),
        claim("failed-other", "eio.predicate.authority-or-deadline-invented"),
    ]
    basis = reference.prepare_reference_basis(claims, ontology=ontology, profile=profile)
    assert basis["ontology_sha256"] == ontology.ontology_sha256
    assert basis["profile_sha256"] == profiles.profile_sha256(profile)
    assert basis["cap_predicate_fail_claim_ids"] == ["failed-cap"]
    assert basis["metric_membership"]["eio.metric.tool-use"] == ["failed-cap", "passed-cap", "semantic-cap"]
    assert basis["metric_membership"]["eio.metric.hallucination-resistance"] == ["failed-other"]
    assert basis == reference.prepare_reference_basis(list(reversed(claims)), ontology=ontology, profile=profile)


def test_changed_profile_or_ontology_binding_fails_closed():
    ontology = load()
    profile = profiles.reference_document(ontology)
    assert profile["ontology_sha256"] == ontology.ontology_sha256
    for change in (lambda p: p.update(ontology_sha256="sha256:" + "0" * 64),
                   lambda p: p["parameters"].update(epsilon=1),
                   lambda p: p["published_metrics"].reverse()):
        tampered = copy.deepcopy(profile)
        change(tampered)
        with pytest.raises(ConversionError) as exc:
            reference.prepare_reference_basis([], ontology=ontology, profile=tampered)
        assert exc.value.code == "SCORING_PROFILE_DIGEST"


def test_cap_predicate_fail_is_not_yet_a_decisive_or_numeric_cap():
    ontology = load()
    candidate = claim("unproven", "eio.predicate.prohibited-tool-invoked")
    assert reference.cap_predicate_fail_claim_ids([candidate], ontology) == ["unproven"]
    with pytest.raises(NotImplementedError, match="draft"):
        reference.score([candidate], [], [], None, {}, {}, profiles.reference_document(ontology), ontology=ontology)
