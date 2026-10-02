"""Isolated native projector evidence; the candidate's digest reissue is pending."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from eio_agents.ontology import load
from tools.l5a_native_projector import (
    NO_SCORING_PROFILE_ID,
    SCHEMA_URI,
    project_native_preview,
    verify_native_preview,
)
from eio_agents.validation.canon import jb, sd, sha

NATIVE = Path(__file__).parent / "data/native/native.bundle.json"


@pytest.fixture(scope="module")
def baseline_ontology():
    """Read the still-pinned live base; never rewrite this non-loadable candidate."""
    base = os.environ.get("L5A_FROZEN_EIO_DATA")
    if not base:
        pytest.skip("set L5A_FROZEN_EIO_DATA to the read-only pre-L5a ontology/data path")
    return load(base)


def test_native_bundle_projects_neutral_per_and_independently_verifies(baseline_ontology) -> None:
    bundle = json.loads(NATIVE.read_text())
    before = copy.deepcopy(bundle)
    rec = project_native_preview(bundle, ontology=baseline_ontology)
    assert bundle == before
    assert rec["header"]["schema_uri"] == SCHEMA_URI
    assert rec["header"]["converter"]["name"] == "eio_agents.convert"
    assert rec["header"]["archive_schema"] == 3
    assert rec["provenance"]["producer"]["kind"] == "native"
    assert rec["scores"] is None
    assert len(rec["claims"]) == 4
    assert len(rec["evidence"]["refs"]) == 6
    assert sum(row["limitation_id"] == NO_SCORING_PROFILE_ID for row in rec["limitations"]) == 1
    assert verify_native_preview(rec, bundle, ontology=baseline_ontology) == {
        "valid": True, "code": "OK", "per_sha256": sha(jb(rec))}
    assert jb(rec) == jb(project_native_preview(bundle, ontology=baseline_ontology))


def test_native_claim_ids_reissued_under_source_key_recipe(baseline_ontology) -> None:
    rec = project_native_preview(json.loads(NATIVE.read_text()), ontology=baseline_ontology)
    for claim in rec["claims"]:
        params = claim["parameters"]
        assert params["source_key"] is None
        assert params["scenario"] is None
        assert params["fidelity"] in {"exact", "narrower"}
        assert "legacy_check" not in params
        assert "mapping_relation" not in params
        assert claim["id"] == sd({
            "run_id": claim["run_id"], "predicate": claim["predicate"],
            "predicate_version": claim["predicate_version"],
            "source_key": None, "turn_indices": sorted(claim["turn_indices"]),
        })


def test_native_preview_verifier_rejects_record_and_bundle_tampering(baseline_ontology) -> None:
    bundle = json.loads(NATIVE.read_text())
    rec = project_native_preview(bundle, ontology=baseline_ontology)
    changed = copy.deepcopy(rec)
    changed["claims"][0]["state"] = "APPLICABLE_FAIL"
    assert verify_native_preview(changed, bundle, ontology=baseline_ontology)["code"] == "REPRODUCTION"
    changed = copy.deepcopy(rec)
    changed["limitations"] = [row for row in changed["limitations"] if row["limitation_id"] != NO_SCORING_PROFILE_ID]
    assert verify_native_preview(changed, bundle, ontology=baseline_ontology)["code"] == "REPRODUCTION"
    changed_bundle = copy.deepcopy(bundle)
    changed_bundle["header"]["run_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert verify_native_preview(rec, changed_bundle, ontology=baseline_ontology)["code"] == "ARCHIVE_DIGEST"


def test_native_preview_rejects_adapter_producer(baseline_ontology) -> None:
    bundle = json.loads(NATIVE.read_text())
    bundle["provenance"]["producer"]["kind"] = "adapter"
    with pytest.raises(Exception, match="producer must be native"):
        project_native_preview(bundle, ontology=baseline_ontology)
