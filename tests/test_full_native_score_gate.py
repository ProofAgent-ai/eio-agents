"""End-to-end rc4 full-score vectors from a synthetic native source bundle."""

import copy

import pytest

from eio_agents import canonical_bytes, validate, verify
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.per.native_preview import project_native_preview
from eio_agents.per.native_full_wire import project_native_full_per
from eio_agents.validation.canon import jb, sha
from eio_agents.validation.full_score import full_native_score_gate, load_full_score_resources
from eio_agents.validation.native_score import native_proof_status_gate
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.validate import check_one
from eio_agents.validation.verify import c_sources
from full_native_score_case import (
    CONTEXT_TEXT, PRIVATE_MARKER, replace_context_text, reseal_stages, source_complete_bundle,
)


def _checked_unscored(bundle):
    """Establish D1/D2/D5 before asking the producer for a scored rc4 PER."""
    ontology = load()
    unscored = project_native_preview(bundle, ontology=ontology)
    eio = EIO(EIO_DIR)
    checks = check_one(unscored, eio)
    checks.run("D2 source", "VER-5", lambda: c_sources(unscored, bundle, eio))
    checks.run("D5 proof", "VER-5", lambda: native_proof_status_gate(bundle, unscored, eio))
    assert not [row for row in checks.rows if row[2] == "FAIL"]
    assert validate(unscored) == []
    checked = {"valid": True, "digest_match": True, "per_sha256": sha(jb(unscored))}
    return unscored, checked, ontology


def _scored(bundle):
    unscored, checked, ontology = _checked_unscored(bundle)
    return project_native_full_per(bundle, unscored, checked, ontology=ontology)


@pytest.fixture(scope="module")
def full_case():
    bundle = source_complete_bundle()
    return bundle, _scored(bundle)


def _gate(bundle, record, *, source_checked=True, approved_profile=True):
    profile, schema = load_full_score_resources()
    return full_native_score_gate(
        bundle, record, EIO(EIO_DIR), source_checked=source_checked,
        approved_profile=profile if approved_profile else None, approved_schema=schema,
    )[0]


def test_source_complete_native_bundle_measures_q_e_c_g_and_readiness(full_case):
    bundle, record = full_case
    assert record["header"]["per_version"] == "2.0.0"
    assert record["scores"]["scoring_profile"]["version"] == "0.3.1-draft.1"
    assert [axis["value"] for axis in record["scores"]["axes"]] == [40.0, 62.5, 50.0, 25.0]
    assert all(axis["status"] == "MEASURED" for axis in record["scores"]["axes"])
    assert record["scores"]["readiness"]["status"] == "MEASURED"
    assert record["scores"]["readiness"]["value"] is not None
    assert record["scores"]["readiness"]["withheld_codes"] == []
    assert record["scores"]["proof_sets"]["reportable_finding_ids"] == []
    assert record["scores"]["proof_sets"]["decisive_finding_ids"] == []
    assert record["scores"]["proof_sets"]["decisive_claim_ids"] == []
    assert _gate(bundle, record) == []


def test_public_rc4_validation_and_reprojection(full_case):
    bundle, record = full_case
    assert validate(record) == []
    checked = verify(record, bundle)
    assert checked["valid"] and checked["digest_match"] and checked["failures"] == []


def test_resealed_score_and_profile_tamper_fail_independent_gate(full_case):
    bundle, record = full_case
    numeric = copy.deepcopy(record)
    numeric["scores"]["axes"][3]["value"] = 100.0
    numeric["scores"]["score_sha256"] = sha(jb({key: value for key, value in numeric["scores"].items()
                                                 if key != "score_sha256"}))
    assert _gate(bundle, numeric)
    profile = copy.deepcopy(record)
    profile["scores"]["scoring_profile"]["sha256"] = "sha256:" + "0" * 64
    profile["scores"]["score_sha256"] = sha(jb({key: value for key, value in profile["scores"].items()
                                                 if key != "score_sha256"}))
    assert _gate(bundle, profile)
    assert _gate(bundle, record, source_checked=False)
    assert _gate(bundle, record, approved_profile=False)


def test_missing_context_rating_withholds_q_and_readiness():
    bundle = source_complete_bundle()
    bundle["native_scoring"]["context_ratings"] = []
    reseal_stages(bundle)
    record = _scored(bundle)
    q = next(axis for axis in record["scores"]["axes"] if axis["axis"] == "eio.axis.context")
    assert q["status"] == "WITHHELD" and q["value"] is None
    assert record["scores"]["readiness"]["status"] == "WITHHELD"
    assert record["scores"]["readiness"]["value"] is None
    assert _gate(bundle, record) == []


def test_missing_proof_set_blocks_full_projection():
    bundle = source_complete_bundle()
    bundle["native_scoring"].pop("proof_citations")
    reseal_stages(bundle)
    unscored, checked, ontology = _checked_unscored(bundle)
    with pytest.raises(ConversionError):
        project_native_full_per(bundle, unscored, checked, ontology=ontology)


def test_context_source_text_is_not_released_in_full_score_per():
    bundle = source_complete_bundle()
    replace_context_text(bundle, CONTEXT_TEXT + " " + PRIVATE_MARKER)
    record = _scored(bundle)
    assert PRIVATE_MARKER.encode() not in canonical_bytes(record)
    assert _gate(bundle, record) == []


def test_full_score_per_bytes_are_reproducible(full_case):
    bundle, record = full_case
    repeat = _scored(copy.deepcopy(bundle))
    assert canonical_bytes(repeat) == canonical_bytes(record)
    assert repeat["scores"]["score_sha256"] == record["scores"]["score_sha256"]
