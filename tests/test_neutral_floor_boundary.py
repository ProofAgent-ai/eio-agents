"""The standalone neutral release has no ProofAgent critical-metric floor."""
import json
from pathlib import Path

import pytest

from eio_agents.api import convert, validate, verify
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per.projection import require_metric_floor_for_scoring


NATIVE = Path(__file__).parent / "data/native/v0_6/native.bundle.json"


def test_native_without_scoring_floor_round_trips():
    ontology = load()
    assert ontology.critical_metric_floor is None
    bundle = json.loads(NATIVE.read_text(encoding="utf-8"))
    record = convert(bundle, ontology=ontology)
    assert record["scores"] is None
    assert record["release_recommendation"]["metric_floors"] == []
    assert validate(record) == []
    result = verify(record, bundle, ontology=ontology)
    assert result["valid"] and result["digest_match"]


def test_scoring_without_declared_floor_fails_closed():
    ontology = load()
    require_metric_floor_for_scoring(ontology, None)
    with pytest.raises(ConversionError) as exc:
        require_metric_floor_for_scoring(ontology, {"profile": {"id": "scored"}})
    assert exc.value.code == "SCORING_PROFILE"
