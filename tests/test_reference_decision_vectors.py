"""Prevent draft scoring-choice vectors from being mistaken for approved numbers."""

import json
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.scoring import engine, profiles, reference


VECTORS = json.loads((Path(__file__).parent / "data" / "reference" / "decision_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_unapproved_native_choice_does_not_emit_a_number(vector):
    assert vector["current_expected"] == "NO_NUMERIC_SCORE"
    assert vector["required_decision"] and vector["candidate_effect"]
    doc = profiles.reference_document(load())
    with pytest.raises(NotImplementedError, match="draft"):
        reference.score([], [], [], None, {}, {}, doc, ontology=load())


def test_current_reference_profile_cannot_feed_the_readiness_engine():
    doc = profiles.reference_document(load())
    assert doc["status"] == "draft" and doc["gaps"]
    assert (doc["id"], doc["version"]) == ("eio-agents.reference-scoring", "0.2.0-draft.1")
    assert doc["parameters"]["readiness_ceiling"] == 49.0
    missing = {k for k, v in doc["parameters"].items() if v is None}
    assert {"band_ramp", "verdict_ramp", "max_margin", "sampling_axis"} <= missing
    with pytest.raises(ConversionError) as exc:
        engine.check_parameters(doc["parameters"])
    assert exc.value.code == "SCORING_PROFILE"


def test_attested_numeric_profile_is_not_available_to_native_producers():
    with pytest.raises(ConversionError) as exc:
        profiles.resolve_profile({"verifiability": "attested"}, producer_kind="native", ontology=load())
    assert exc.value.code == "SCORING_PROFILE"
