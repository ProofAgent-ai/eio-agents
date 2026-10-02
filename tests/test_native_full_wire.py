"""rc4 full-score producer checks against an independently prechecked native source."""
import copy
import json
from pathlib import Path

import pytest

from eio_agents import convert
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per.bundle import stage_digest
from eio_agents.per.native_full_wire import (
    PER_VERSION, SCORE_BASIS_VERSION, full_score_block_problems, project_native_full_per,
)
from eio_agents.per.native_preview import project_native_preview
from eio_agents.scoring import profiles
from eio_agents.schemas import per_schema
from eio_agents.validation.canon import jb, sha
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO
from eio_agents.validation.validate import check_one
from eio_agents.validation.verify import c_sources


SOURCE = Path(__file__).parent / "data/native/v0_6/synthetic-cited-native.bundle.json"


def _checked_input(bundle):
    ontology = load()
    unscored = project_native_preview(bundle, ontology=ontology)
    eio = EIO(ontology.root)
    checks = check_one(unscored, eio)
    checks.run("D2 source", "VER-5", lambda: c_sources(unscored, bundle, eio))
    checks.run("D5 proof", "VER-5", lambda: native_proof_status_gate(bundle, unscored, eio))
    assert not [row for row in checks.rows if row[2] == "FAIL"]
    verification = {"valid": True, "digest_match": True, "per_sha256": sha(jb(unscored))}
    return ontology, unscored, verification


def test_rc4_producer_binds_exact_proof_and_withholds_missing_axes():
    bundle = json.loads(SOURCE.read_text())
    ontology, unscored, verification = _checked_input(bundle)
    record = project_native_full_per(bundle, unscored, verification, ontology=ontology)
    score = record["scores"]
    assert record["header"]["per_version"] == PER_VERSION
    assert record["header"]["schema_uri"] == per_schema(PER_VERSION)["$id"]
    assert score["score_basis_version"] == SCORE_BASIS_VERSION
    assert score["proof_sets"]["decisive_claim_ids"] == score["readiness"]["cap"]["claim_ids"]
    assert score["readiness"]["status"] == "WITHHELD"
    assert score["readiness"]["withheld_codes"] == ["REQUIRED_AXIS_WITHHELD"]
    assert not score["readiness"]["cap"]["applied"]
    assert score["axes"][3]["value"] == 25.0
    assert score["axes"][3]["basis_ids"] == profiles.reference_full_document(ontology)["g_component_ids"]
    assert full_score_block_problems(score, {**record, "scores": None,
           "limitations": unscored["limitations"]}, ontology=ontology) == []
    assert convert(bundle)["header"]["per_version"] == PER_VERSION
    assert convert(bundle)["scores"]["readiness"]["value"] is None


def test_rc4_rejects_unbound_proof_sets_and_false_verification():
    bundle = json.loads(SOURCE.read_text())
    ontology, unscored, verification = _checked_input(bundle)
    with pytest.raises(ConversionError):
        project_native_full_per(bundle, unscored, {**verification, "per_sha256": "sha256:" + "0" * 64},
                                ontology=ontology)
    missing = copy.deepcopy(bundle)
    del missing["native_scoring"]["proof_citations"]
    for stage in missing["stage_records"]:
        if "native_scoring" in stage["sections"]:
            stage["output_sha256"] = stage_digest(missing, stage["sections"])
    ontology, unscored, verification = _checked_input(missing)
    with pytest.raises(ConversionError, match="proof sets"):
        project_native_full_per(missing, unscored, verification, ontology=ontology)
