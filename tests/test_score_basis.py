"""Versioned score basis binds the received PER without producer inverse."""

import copy

import pytest

from eio_agents.ontology import load
from eio_agents.per.native_score_preview import candidate_scored_per
from eio_agents.scoring.profiles import reference_document
from eio_agents.validation.canon import jb, sha
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.score_basis import ScoreBasisError, score_basis_sha256
from eio_agents.validation.score_block_diagnostic import diagnose_draft_score_block
from tests.test_native_score_preview import _preview


def test_null_and_scored_candidate_share_exact_basis():
    _, unscored, block = _preview()
    scored = candidate_scored_per(unscored, block)
    assert score_basis_sha256(unscored, scored=False) == score_basis_sha256(scored, scored=True)
    altered = copy.deepcopy(scored)
    altered["findings"][0]["display_label"] = "forged"
    assert score_basis_sha256(altered, scored=True) != score_basis_sha256(scored, scored=True)


def test_score_basis_rejects_score_only_limitation_retained_or_duplicated():
    _, unscored, block = _preview()
    scored = candidate_scored_per(unscored, block)
    retained = copy.deepcopy(scored)
    retained["limitations"].append(next(row for row in unscored["limitations"]
                                        if row["limitation_id"] == "per.lim.scoring_profile.none"))
    with pytest.raises(ScoreBasisError, match="retains"):
        score_basis_sha256(retained, scored=True)
    duplicate = copy.deepcopy(unscored)
    duplicate["limitations"].append(duplicate["limitations"][0])
    with pytest.raises(ScoreBasisError, match="duplicate"):
        score_basis_sha256(duplicate, scored=False)
    absent = copy.deepcopy(unscored)
    absent["limitations"] = [row for row in absent["limitations"]
                             if row["limitation_id"] != "per.lim.scoring_profile.none"]
    with pytest.raises(ScoreBasisError, match="exactly one"):
        score_basis_sha256(absent, scored=False)


def test_scored_per_basis_and_resealed_numeric_tamper_are_diagnosed():
    bundle, unscored, block = _preview()
    scored = candidate_scored_per(unscored, block)
    # Test oracle may use producer profile; verifier code never imports it.
    approved = reference_document(load())
    source_check = {"valid": True, "digest_match": True, "per_sha256": sha(jb(scored))}
    diagnostic = diagnose_draft_score_block(bundle, scored, block, EIO(EIO_DIR),
                                            approved_profile=approved, verification=source_check)
    assert diagnostic["mismatches"] == [] and not diagnostic["complete"]
    forged = copy.deepcopy(scored)
    forged["scores"]["metrics"][0]["value"] = 99.0
    forged["scores"]["score_sha256"] = sha(jb({k: v for k, v in forged["scores"].items()
                                                 if k != "score_sha256"}))
    source_check["per_sha256"] = sha(jb(forged))
    detected = diagnose_draft_score_block(bundle, forged, forged["scores"], EIO(EIO_DIR),
                                          approved_profile=approved, verification=source_check)
    assert "scores.metrics.eio.metric.safety.value" in detected["mismatches"]
