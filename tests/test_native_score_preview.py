"""Candidate-only scored-PER wire; public native scoring remains fail-closed."""
import copy
import json
from pathlib import Path

import pytest

from eio_agents import convert, validate, verify
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.per.native_preview import project_native_preview
from eio_agents.per.native_score_preview import (
    SCORE_BASIS_VERSION,
    _score_basis_sha256,
    candidate_scored_per,
    project_native_score_preview,
    score_block_problems,
)
from eio_agents.schemas import PER_SCHEMA, PER_SCHEMA_NATIVE_PREVIEW
from eio_agents.validation.canon import jb as verifier_jb, sha as verifier_sha
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO
from eio_agents.validation.validate import check_one
from eio_agents.validation.verify import c_sources


def _source():
    bundle = json.loads((Path(__file__).parent / "data/native/v0_6/native.bundle.json").read_text(encoding="utf-8"))
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
    return bundle


def _preview():
    bundle = _source()
    ontology = load()
    record = project_native_preview(bundle, ontology=ontology)
    eio = EIO(ontology.root)
    checks = check_one(record, eio)
    checks.run("D2 source", "VER-5", lambda: c_sources(record, bundle, eio))
    checks.run("D5 proof", "VER-5", lambda: native_proof_status_gate(bundle, record, eio))
    assert not [row for row in checks.rows if row[2] == "FAIL"] and validate(record) == []
    verification = {"valid": True, "digest_match": True, "per_sha256": verifier_sha(verifier_jb(record))}
    block = project_native_score_preview(bundle, record, verification, ontology=ontology)
    return bundle, record, block


def test_draft_score_block_is_digest_bound_and_withholds_readiness():
    _, record, block = _preview()
    assert block["scoring_profile"]["ontology_sha256"] == record["header"]["eio"]["ontology_sha256"]
    assert block["score_basis_version"] == SCORE_BASIS_VERSION
    assert block["score_basis_sha256"] == _score_basis_sha256(record)
    assert block["readiness"] == {"value": None, "status": "WITHHELD",
                                  "withheld_codes": ["INDEPENDENT_PROOF_PENDING", "FRESHNESS_UNVERIFIED",
                                                     "DECISIVE_SET_UNVERIFIED"]}
    assert block["axes"][3]["value"] is None
    assert [row["metric"] for row in block["metrics"]] == [row["id"] for row in load().metrics]
    assert score_block_problems(block, record) == []


def test_candidate_per_uses_one_public_static_schema_and_d4_checks_it():
    bundle, record, block = _preview()
    candidate = candidate_scored_per(record, block)
    assert candidate["scores"] == block
    assert _score_basis_sha256(candidate) == block["score_basis_sha256"]
    assert score_block_problems(block, candidate) == []
    assert validate(candidate) == []  # the single rc3 schema accepts this closed draft shape
    result = verify(candidate, bundle)
    assert not result["valid"] and not result["digest_match"]
    assert any(row["check"].startswith("D4") for row in result["failures"])
    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        convert(bundle)


def test_bundle_without_declared_proof_set_has_no_public_partial_score():
    bundle = _source()
    with pytest.raises(ConversionError, match="no versioned partial-score profile"):
        convert(bundle)


def test_rc3_public_schema_has_one_identifier_not_shared_with_preview():
    canonical = json.loads(PER_SCHEMA.read_text(encoding="utf-8"))
    preview = json.loads(PER_SCHEMA_NATIVE_PREVIEW.read_text(encoding="utf-8"))
    assert canonical["$id"] == "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json"
    assert preview["$id"] != canonical["$id"]
    assert canonical["properties"]["scores"]["anyOf"][1] == {"$ref": "#/$defs/native_draft_scores"}


@pytest.mark.parametrize("field, replacement", [
    ("score_sha256", "sha256:" + "0" * 64),
    ("score_basis_sha256", "sha256:" + "0" * 64),
])
def test_candidate_digest_tampering_is_rejected(field, replacement):
    _, record, block = _preview()
    changed = copy.deepcopy(block)
    changed[field] = replacement
    assert score_block_problems(changed, record)
    with pytest.raises(ConversionError):
        candidate_scored_per(record, changed)


def test_candidate_cannot_insert_readiness_or_wrong_profile_ontology():
    _, record, block = _preview()
    changed = copy.deepcopy(block)
    changed["readiness"]["value"] = 95
    changed["score_sha256"] = H(jb({k: v for k, v in changed.items() if k != "score_sha256"}))
    assert score_block_problems(changed, record)
    changed = copy.deepcopy(block)
    changed["scoring_profile"]["ontology_sha256"] = "sha256:" + "0" * 64
    changed["score_sha256"] = H(jb({k: v for k, v in changed.items() if k != "score_sha256"}))
    assert score_block_problems(changed, record)
    changed = copy.deepcopy(block)
    changed["scoring_profile"]["sha256"] = "sha256:" + "0" * 64
    changed["score_sha256"] = H(jb({k: v for k, v in changed.items() if k != "score_sha256"}))
    assert "profile identity or digest differs from loaded registry" in score_block_problems(changed, record)


def test_preview_requires_independent_verification():
    bundle, record, _ = _preview()
    with pytest.raises(ConversionError):
        project_native_score_preview(bundle, record, {"valid": True, "digest_match": False}, ontology=load())


def test_score_basis_rejects_duplicate_or_retained_score_only_limitation():
    _, record, block = _preview()
    duplicate = copy.deepcopy(record)
    no_profile = next(row for row in duplicate["limitations"]
                      if row["limitation_id"] == "per.lim.scoring_profile.none")
    duplicate["limitations"].append(copy.deepcopy(no_profile))
    with pytest.raises(ConversionError):
        _score_basis_sha256(duplicate)
    scored = candidate_scored_per(record, block)
    scored["limitations"].append(copy.deepcopy(no_profile))
    with pytest.raises(ConversionError):
        _score_basis_sha256(scored)
