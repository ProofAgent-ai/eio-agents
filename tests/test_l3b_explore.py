"""Explain/evidence navigation over a neutral native PER with no numeric score.

The original producer-specific scored navigation vectors remain in the external
adapter compatibility corpus.
"""

import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents import cli


BUNDLE = Path(__file__).parent / "data" / "native" / "v0_6/native.bundle.json"


@pytest.fixture
def record():
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    return eio_agents.convert(copy.deepcopy(bundle))


def test_targets_and_turn_alias_preserve_registered_explanation(record):
    finding = record["findings"][0]
    assert record["scores"] is None
    targets = eio_agents.targets(record)
    assert any(row["id"] == finding["finding_id"] and row["kind"] == "finding" for row in targets)
    assert not any(row["kind"] == "metric" for row in targets)
    assert eio_agents.explain(record, "t03") == eio_agents.explain(record, finding["finding_id"])
    assert eio_agents.explain(record, "release") == eio_agents.explain(record, "release_recommendation")
    with pytest.raises(LookupError):
        eio_agents.explain(record, "t99")


def test_protected_evidence_uses_supplied_per_only(record, monkeypatch):
    """Evidence navigation must not open the local bundle or unseal fingerprints."""
    monkeypatch.setattr(eio_agents.api, "resolve", lambda *_: pytest.fail("local resolver was called"))
    proofs = eio_agents.findings_at_turn(record, "t03")
    assert len(proofs) == 1
    finding = record["findings"][0]
    assert [row["id"] for row in proofs[0]["refs"]] == finding["explanation"]["evidence_refs"]
    for exposed in proofs[0]["refs"]:
        source = next(row for row in record["evidence"]["refs"] if row["id"] == exposed["id"])
        assert exposed["excerpt"] == source.get("excerpt")
        assert exposed["span_sha256"] == source.get("span_sha256")
    assert eio_agents.finding_evidence(record, "t03") == proofs[0]
    assert "acme/support-llm-2" not in json.dumps(proofs)


def test_cli_explain_and_evidence_native_record(record, tmp_path, capsys):
    path = tmp_path / "native.per.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert cli.main(["explain", str(path), "--list"]) == 0
    assert "t03" in capsys.readouterr().out
    assert cli.main(["explain", str(path), "t03"]) == 0
    assert "authority-or-deadline-invented" in capsys.readouterr().out
    assert cli.main(["evidence", str(path), "t03"]) == 0
    proof = capsys.readouterr().out
    assert "Turn 3" in proof and "By law" in proof
    assert "acme/support-llm-2" not in proof
    assert cli.main(["evidence", str(path), "t99"]) == 2
    assert "no finding" in capsys.readouterr().err


def test_unscored_native_record_does_not_invent_metric_card(record):
    with pytest.raises(LookupError):
        eio_agents.metric_card(record, "instruction following")
