"""Owner decision #46 (EIO-Agents 0.8.0): release semantics 2.2 (no declared policy -> REVIEW below the default
readiness floor 85 or with an unmet HARD_BLOCK obligation; BLOCK still needs a proven failure), PER 2.1.0 as the
default with no "draft" in a public version, and "unrated" for a finding without a severity."""

import copy
import json

import pytest

import eio_agents
from eio_agents import cli
from eio_agents.ontology import load
from eio_agents.per import native_full_wire
from eio_agents.schemas import per_schema
from eio_agents.semantics import why
from eio_agents.validation import full_score

from full_native_score_case import reseal_stages, source_complete_bundle
from test_build_semantic import OVERCLAIM, _args

FLOOR, HARD = "eio.release.default-readiness-floor", "eio.release.hard-block-unmet"
GUARDS = (FLOOR, HARD)


@pytest.fixture(scope="module")
def case():
    bundle = source_complete_bundle()
    record = eio_agents.convert(bundle)
    return bundle, record


def _record(readiness, unmet, *, source="none", state="PASS", decisive=()):
    """A minimal record shape for the guard rules: readiness, coverage obligations and the declared policy source."""
    obligations = [{"id": f"o{i}", "met": False, "release_impact": "HARD_BLOCK"} for i in range(unmet)]
    obligations.append({"id": "met", "met": True, "release_impact": "HARD_BLOCK"})
    return {"scores": {"readiness": {"value": readiness}},
            "coverage": {"obligations": obligations, "summary": {"hard_block_unmet": unmet}},
            "release_recommendation": {"state": state, "decisive": list(decisive), "contributing": [],
                                       "policy": {"source": source}}}


def _ids(guards):
    return [g["id"] for g in guards]


# ---------------------------------------------------------------- (1) no policy -> REVIEW, by construction

@pytest.mark.parametrize("readiness, unmet, expected", [
    (41.0227, 0, [FLOOR]),             # no policy + low readiness -> REVIEW
    (90.0, 2, [HARD]),                 # no policy + unmet HARD_BLOCK obligation -> REVIEW
    (84.9999, 1, [FLOOR, HARD]),
    (None, 0, [FLOOR]),                # withheld readiness does not clear the floor
    (85.0, 0, []),                     # at the floor, nothing unmet: no guard
])
def test_producer_and_verifier_guards_agree(readiness, unmet, expected):
    record = _record(readiness, unmet)
    producer = native_full_wire.default_floor_guards(record, readiness)
    verifier = full_score.default_floor_guards(record)
    assert _ids(producer) == _ids(verifier) == expected
    assert producer == verifier
    assert all(g["effect"] == "REVIEW" and g["kind"] == "review_guard" and "proof_status" not in g for g in producer)


def test_a_declared_policy_has_no_default_floor():
    record = _record(10.0, 3, source="embedded_profile")
    assert native_full_wire.default_floor_guards(record, 10.0) == full_score.default_floor_guards(record) == []


def test_no_policy_low_readiness_and_hard_block_review_end_to_end(case):
    bundle, record = case
    rr = record["release_recommendation"]
    assert record["header"]["per_version"] == "2.1.0" and record["header"]["release_semantics"] == "2.2"
    assert rr["policy"]["source"] == "none" and rr["state"] == "REVIEW"
    assert record["scores"]["readiness"]["value"] < 85 and record["coverage"]["summary"]["hard_block_unmet"] > 0
    guards = [d for d in rr["decisive"] if d["id"] in GUARDS]
    assert _ids(guards) == [FLOOR, HARD]
    assert guards[0]["expected"] == "readiness >= 85.0"
    assert guards[0]["observed"] == why.fmt_score(record["scores"]["readiness"]["value"])
    assert guards[1]["observed"] == str(record["coverage"]["summary"]["hard_block_unmet"])
    assert len(guards[1]["obligation_ids"]) == record["coverage"]["summary"]["hard_block_unmet"]
    summary = rr["explanation"]["summary"]
    assert rr["explanation"]["template_id"] == "eio.why.release.review@1"
    assert f"{FLOOR} (expected readiness >= 85.0" in summary and f"{HARD} (expected 0, observed" in summary
    assert "under semantics 2.2" in summary
    assert eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_a_declared_policy_that_passes_is_not_floored():
    bundle = source_complete_bundle()
    bundle["scope"]["policy"] = {
        "source": "embedded_profile", "origin": "local",
        "profile_sha256": "sha256:1aceedc4cb30160cb4edcd6888ef1699be7b98d348ad890fc0516d7b5f07c5d5",
        "name": "native-eio-test-profile", "declared": None, "prohibited": False,
        "rules": {"min_score": 30, "block_severity": "HIGH", "signoff_required": False}}
    bundle["provenance"]["record"]["inputs"]["governance_profile"] = {
        "name": "native-eio-test-profile",
        "profile_sha256": "sha256:1aceedc4cb30160cb4edcd6888ef1699be7b98d348ad890fc0516d7b5f07c5d5", "embedded": True}
    bundle = reseal_stages(bundle)
    record = eio_agents.convert(bundle)
    rr = record["release_recommendation"]
    assert record["scores"]["readiness"]["value"] < 85
    assert rr["state"] == "PASS" and not any(d["id"] in GUARDS for d in rr["decisive"])
    assert eio_agents.verify(record, bundle)["valid"]


@pytest.mark.parametrize("mutation", ["forged_pass", "drop_floor", "drop_hard_block", "wrong_count", "old_semantics"])
def test_the_verifier_rejects_a_forged_pass(case, mutation):
    bundle, original = case
    record = copy.deepcopy(original)
    rr = record["release_recommendation"]
    if mutation == "forged_pass":      # a record claiming PASS with no decisive condition, its explanation re-rendered
        rr["decisive"] = [d for d in rr["decisive"] if d["id"] not in GUARDS]
        rr["state"] = "PASS"
        rr["explanation"]["template_id"] = "eio.why.release.pass@1"
        rr["explanation"]["params"] = {"n_contributing": len(rr["contributing"]), "semantics": "2.2"}
        rr["explanation"]["summary"] = why.render(load(), "eio.why.release.pass@1",
                                                  rr["explanation"]["params"])
    elif mutation == "drop_floor":
        rr["decisive"] = [d for d in rr["decisive"] if d["id"] != FLOOR]
    elif mutation == "drop_hard_block":
        rr["decisive"] = [d for d in rr["decisive"] if d["id"] != HARD]
    elif mutation == "wrong_count":
        next(d for d in rr["decisive"] if d["id"] == HARD)["obligation_ids"].pop()
    else:
        record["header"]["release_semantics"] = rr["semantics"] = "2.1"
    problems = eio_agents.validate(record)
    assert problems, mutation
    if mutation == "forged_pass":
        assert any("claimed PASS with no declared policy" in p["detail"] for p in problems), problems
    result = eio_agents.verify(record, bundle)
    assert not result["valid"] and not result["digest_match"]


def test_a_proven_failure_still_blocks_and_the_guards_never_block():
    """BLOCK still requires a proven failure (owner decision #2): a PROVEN cap keeps BLOCK when the no-policy guards
    are added, and the guards alone only REVIEW."""
    ontology = load()
    cap = {"kind": "cap", "id": "eio.cap.proven-critical-breach", "expected": "x", "observed": "y",
           "claim_ids": ["c1"], "finding_ids": ["f1"], "proof_status": "PROVEN", "effect": "BLOCK"}
    record = _record(20.0, 1, state="BLOCK", decisive=[cap])
    record["release_recommendation"]["explanation"] = {}
    record["claims"] = [{"id": "c1", "turn_indices": [2], "predicate": "eio.predicate.prohibited-tool-invoked"}]
    native_full_wire._apply_default_floor_guards(record, 20.0, ontology=ontology)
    rr = record["release_recommendation"]
    assert rr["state"] == "BLOCK" and rr["explanation"]["template_id"] == "eio.why.release.block@1"
    assert _ids(rr["decisive"]) == ["eio.cap.proven-critical-breach", FLOOR, HARD]
    alone = _record(20.0, 1)
    alone["release_recommendation"]["explanation"] = {}
    native_full_wire._apply_default_floor_guards(alone, 20.0, ontology=ontology)
    assert alone["release_recommendation"]["state"] == "REVIEW"


def test_the_longest_no_policy_explanation_fits_its_template():
    """Cap, HIGH-review queue and both no-policy guards render within the 600-character release template."""
    bundle = eio_agents.build_bundle(**_args({"turn": 1, "predicate": "prohibited-tool-invoked", "passed": False,
                                              "quote": OVERCLAIM["quote"]}))
    record = eio_agents.convert(bundle)
    rr = record["release_recommendation"]
    assert [d["kind"] for d in rr["decisive"]] == ["cap", "review_guard", "review_guard", "review_guard"]
    assert len(rr["explanation"]["summary"]) <= 600
    assert eio_agents.verify(record, bundle)["valid"]


# ---------------------------------------------------------------- (2) PER 2.1.0 default, no "draft" in public versions

def test_version_defaults_to_per_2_1_0_with_no_draft(capsys):
    assert cli.main(["version"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["per_version"] == "2.1.0" and shown["release_semantics"] == "2.2"
    assert shown["per_schema_id"] == "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
    assert shown["native_full_scoring_profile_version"] == "0.3.1"
    assert "draft" not in json.dumps(shown).lower()
    assert eio_agents.standards() == {k: v for k, v in shown.items() if k != "eio_agents"}
    assert per_schema()["$id"] == shown["per_schema_id"]


def test_a_new_record_and_its_schema_name_no_draft(case):
    _, record = case
    body = json.dumps(record)
    assert "draft" not in body.lower()
    assert record["scores"]["kind"] == "reference"
    assert record["scores"]["scoring_profile"]["version"] == "0.3.1"
    assert record["scores"]["score_basis_version"] == "eio-agents.score-basis/0.3.0"
    schema = json.dumps(per_schema("2.1.0"))
    assert "draft" not in schema.replace("https://json-schema.org/draft/2020-12/schema", "")


def test_historical_draft_profile_stays_pinned_for_per_2_0_0():
    profile, schema = full_score.load_full_score_resources("0.3.1-draft.1")
    assert profile["version"] == "0.3.1-draft.1"
    assert full_score.PER_SCORE_IDENTITY["2.0.0"] == ("0.3.1-draft.1", "eio-agents.score-basis/0.3.0-draft.1",
                                                      "reference-draft")
    public, _ = full_score.load_full_score_resources()
    assert public["version"] == "0.3.1" and public["parameters"] == profile["parameters"]
    assert public["formulas"] == profile["formulas"]


# ---------------------------------------------------------------- (3) a finding without a severity shows "unrated"

def test_unrated_severity_in_explain_and_evidence(case, tmp_path, capsys):
    _, record = case
    unrated = [f for f in record["findings"] if f["severity"] is None]
    assert unrated, "the synthetic sample has a finding with no severity"
    path = tmp_path / "r.per.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert cli.main(["evidence", str(path), unrated[0]["finding_id"]]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first.split(" | ")[2] == "unrated" and "None" not in first
    assert cli.main(["explain", str(path), "--list"]) == 0
    rows = [r for r in capsys.readouterr().out.splitlines() if r.startswith(unrated[0]["finding_id"])]
    assert rows and rows[0].endswith("| unrated")
    assert eio_agents.finding_evidence(record, unrated[0]["finding_id"])["severity"] is None   # data stays null
