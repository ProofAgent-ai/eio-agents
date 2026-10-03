"""Record-only rc4 score explanations without producer template objects."""

import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents import cli
from eio_agents.per.bundle import stage_digest
from full_native_score_case import PRIVATE_MARKER, replace_context_text, source_complete_bundle


@pytest.fixture(scope="module")
def measured():
    bundle = replace_context_text(source_complete_bundle(),
                                  "Synthetic public instructions. " + PRIVATE_MARKER)
    record = eio_agents.convert(bundle)
    assert eio_agents.verify(record, bundle)["valid"]
    return bundle, record


@pytest.fixture(scope="module")
def partial_no_citation():
    source = Path(__file__).parent / "data/native/v0_6/synthetic-cited-native.bundle.json"
    bundle = json.loads(source.read_text(encoding="utf-8"))
    bundle["native_scoring"]["proof_citations"] = []
    for stage in bundle["stage_records"]:
        if "native_scoring" in stage["sections"]:
            stage["output_sha256"] = stage_digest(bundle, stage["sections"])
    record = eio_agents.convert(bundle)
    assert eio_agents.verify(record, bundle)["valid"]
    return bundle, record


def test_measured_scores_and_metric_card_use_exact_public_ids_counts_and_turns(measured):
    bundle, record = measured
    assert record["header"]["per_version"] == "2.1.0"
    assert "40.0/100" in eio_agents.explain(record, "Q")
    assert "25.0/100" in eio_agents.explain(record, "G")
    assert "42.0448/100" in eio_agents.explain(record, "readiness")
    card = eio_agents.metric_card(record, "eio.metric.safety")
    assert card["id"] == "eio.metric.safety"
    assert card["member_count"] == 2 and card["passed"] == 2 and card["failed"] == 0
    assert card["turns"] == [2] and card["primary_failures"] == []
    text = eio_agents.explain(record, card["id"], local=bundle)
    assert "eio.metric.safety" in text and "Member claims: 2" in text and "turn indices: 2" in text
    assert PRIVATE_MARKER not in text


def test_no_citation_partial_score_explains_withheld_without_promoting_proof(partial_no_citation):
    _bundle, record = partial_no_citation
    assert record["scores"]["proof_sets"]["decisive_claim_ids"] == []
    assert "WITHHELD" in eio_agents.explain(record, "readiness")
    assert "required axis" in eio_agents.explain(record, "readiness")
    assert "no context criterion" in eio_agents.explain(record, "Q")
    assert "fewer than six control statuses" in eio_agents.explain(record, "C")
    assert "46.25/100" in eio_agents.explain(record, "E")
    assert "25.0/100" in eio_agents.explain(record, "G")
    metric = eio_agents.metric_card(record, "eio.metric.safety")
    assert metric["member_count"] == 2 and metric["turns"] == [2]
    assert "Member claims: 2" in eio_agents.explain(record, metric["id"])
    assert "PROVEN" not in eio_agents.explain(record, "readiness")


def test_rc4_cli_list_explain_and_unknown_target_exit_code(measured, partial_no_citation, tmp_path, capsys):
    bundle, measured_record = measured
    partial_record = partial_no_citation[1]
    measured_path = tmp_path / "measured.per.json"
    measured_path.write_text(json.dumps(measured_record), encoding="utf-8")
    partial_path = tmp_path / "partial.per.json"
    partial_path.write_text(json.dumps(partial_record), encoding="utf-8")
    local_path = tmp_path / "local.bundle.json"
    local_path.write_text(json.dumps(bundle), encoding="utf-8")
    assert cli.main(["explain", str(measured_path), "--list"]) == 0
    listing = capsys.readouterr().out
    assert "eio.metric.safety | Safety | 75.0" in listing
    assert "eio.axis.governance | Governance (G) | 25.0" in listing
    assert PRIVATE_MARKER not in listing
    assert cli.main(["explain", str(measured_path), "eio.metric.safety", "--local", str(local_path)]) == 0
    output = capsys.readouterr().out
    assert "Member claims: 2" in output and "turn indices: 2" in output
    assert PRIVATE_MARKER not in output
    assert cli.main(["explain", str(partial_path), "--list"]) == 0
    listing = capsys.readouterr().out
    assert "readiness | Readiness | WITHHELD — at least one required axis is withheld" in listing
    assert "eio.metric.instruction-following" in listing
    assert cli.main(["explain", str(partial_path), "eio.metric.unknown"]) == 2
    assert "no explanation for this target" in capsys.readouterr().err


def test_invalid_score_text_is_never_echoed_as_a_number(measured, tmp_path, capsys):
    record = copy.deepcopy(measured[1])
    record["scores"]["readiness"]["raw"] = PRIVATE_MARKER
    record["scores"]["axes"][0]["value"] = PRIVATE_MARKER
    record["scores"]["metrics"][0]["value"] = PRIVATE_MARKER
    assert PRIVATE_MARKER not in eio_agents.explain(record, "readiness")
    assert PRIVATE_MARKER not in eio_agents.explain(record, "Q")
    assert PRIVATE_MARKER not in eio_agents.explain(record, "eio.metric.safety")
    path = tmp_path / "invalid.per.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert cli.main(["explain", str(path), "--list"]) == 0
    assert PRIVATE_MARKER not in capsys.readouterr().out
