"""Current-release rejection of the archived EIO 0.5 partial-score profile."""

import pytest

from eio_agents import ConversionError, convert
from eio_agents.per.native_score_preview import candidate_scored_per
from eio_agents.validation.partial_score import load_verifier_score_resources, partial_native_score_gate
from eio_agents.validation.reader import EIO, EIO_DIR
from tests.test_native_score_preview import _preview


def test_0_6_rejects_historical_partial_score_even_when_its_own_gate_agrees():
    bundle, unscored, block = _preview()
    historical_partial = candidate_scored_per(unscored, block)
    eio = EIO(EIO_DIR)
    approved, schema = load_verifier_score_resources()
    problems, _detail = partial_native_score_gate(
        bundle, historical_partial, eio, source_checked=True,
        approved_profile=approved, approved_schema=schema)
    assert problems == ["partial native scoring requires the pinned draft EIO 0.5 release"]
    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        convert(bundle)
