"""Combined native source extraction, draft arithmetic, and scored PER output."""

import json
from pathlib import Path

import pytest

from eio_agents import ConversionError, convert
from eio_agents.per import bundle as B


def test_verified_native_sources_reach_draft_scorer_but_withhold_readiness():
    path = Path(__file__).parent / "data/native/v0_6/native.bundle.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["native_scoring"] = {
        "scenario_bindings": [
            {"binding_id": f"s{i}", "turn_indices": claim["turn_indices"], "severity": "HIGH"}
            for i, claim in enumerate(bundle["claims"])
        ],
        "claim_bindings": [
            {"claim_id": claim["id"], "binding_id": f"s{i}"}
            for i, claim in enumerate(bundle["claims"])
        ],
        "applicable_controls": [],
        "context_ratings": [],
    }
    bundle["stage_records"].append({
        "stage": "native-score-sources", "producer": "native", "sections": ["native_scoring"],
        "output_sha256": B.stage_digest(bundle, ["native_scoring"]),
    })

    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        convert(bundle)
