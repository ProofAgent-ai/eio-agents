"""Tests of the OpenTelemetry GenAI converter: python -m pytest -q test_convert.py"""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.validation import validate_bundle

from convert import to_bundle, turns_of

EXPORT = json.loads((Path(__file__).parent / "traces.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def converted():
    bundle = to_bundle(EXPORT)
    return bundle, eio_agents.convert(bundle)


def test_the_traces_convert_to_a_valid_verifiable_per(converted):
    bundle, record = converted
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    assert record["header"]["per_version"] == "2.1.0" and eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_each_agent_invocation_is_a_turn_with_its_tool_spans(converted):
    bundle, _ = converted
    turns = bundle["sources"]["turns"]
    assert [t["question"] for t in turns][0] == "My laptop won't connect to the VPN."
    assert [[c["name"] for c in t["tool_calls"]] for t in turns] == [["get_vpn_status"], ["reset_password"], []]
    assert turns[1]["tool_calls"][0]["result"] == {"reset": True}


def test_only_the_specific_prohibited_disclosure_refusal_becomes_a_claim(converted):
    bundle, record = converted
    decided = [(c["predicate"].removeprefix("eio.predicate."), c["decided_by"], c["state"]) for c in record["claims"]]
    assert decided == [("prohibited-part-clearly-refused", "semantic", "APPLICABLE_PASS")]
    assert record["findings"] == []


def test_the_dated_model_names_are_in_clear(converted):
    _, record = converted
    assert record["subject"]["agent"]["model"] == "gpt-4o-mini-2024-07-18"
    assert {c["provenance"].get("model") for c in record["claims"] if c["decided_by"] == "semantic"} == {"openai/gpt-4o"}


def test_generic_groundedness_and_tool_policy_labels_are_not_mapped(converted):
    bundle, _ = converted
    assert len(bundle["claims"]) == 1
    assert bundle["claims"][0]["turn_indices"] == [3]


def test_mapped_llm_evaluation_requires_observed_judge_model():
    export = copy.deepcopy(EXPORT)
    spans = export["resourceSpans"][0]["scopeSpans"][0]["spans"]
    event = next(e for s in spans for e in s.get("events", []) if any(
        a["key"] == "gen_ai.evaluation.name" and a["value"].get("stringValue") == "prohibited_disclosure_refused"
        for a in e["attributes"]))
    event["attributes"] = [a for a in event["attributes"] if a["key"] != "eio.evaluator.model"]
    with pytest.raises(ValueError, match="lacks eio.evaluator.model"):
        to_bundle(export)


def test_an_edited_span_breaks_verification(converted):
    bundle, record = converted
    tampered = copy.deepcopy(bundle)
    tampered["sources"]["turns"][1]["tool_calls"][0]["arguments"] = {"account": "OTHER"}
    assert not eio_agents.verify(record, tampered)["digest_match"]


def test_a_reused_parent_span_id_in_another_trace_is_not_a_child():
    spans = EXPORT["resourceSpans"][0]["scopeSpans"][0]["spans"]
    foreign = copy.deepcopy(next(s for s in spans if s.get("parentSpanId") == spans[0]["spanId"]
                                 and any(a["value"].get("stringValue") == "execute_tool"
                                         for a in s["attributes"])))
    foreign["traceId"] = "f" * 32
    foreign["spanId"] = "f" * 16
    foreign["attributes"] = [a for a in foreign["attributes"] if a["key"] != "gen_ai.tool.name"] + [
        {"key": "gen_ai.tool.name", "value": {"stringValue": "foreign_tool"}}]
    rows = turns_of(spans + [foreign])
    assert [[tool["name"] for tool in row["turn"]["tools"]] for row in rows] == [
        ["get_vpn_status"], ["reset_password"], []]


def test_missing_invocation_or_chat_fails_closed():
    with pytest.raises(ValueError, match="no invoke_agent"):
        turns_of([])
    root = copy.deepcopy(EXPORT["resourceSpans"][0]["scopeSpans"][0]["spans"][0])
    with pytest.raises(ValueError, match="no chat child"):
        turns_of([root])


def test_multiple_agents_cannot_be_reported_as_one_subject():
    export = copy.deepcopy(EXPORT)
    spans = export["resourceSpans"][0]["scopeSpans"][0]["spans"]
    second_root = next(s for s in spans if s["spanId"].startswith("02a"))
    next(a for a in second_root["attributes"] if a["key"] == "gen_ai.agent.name")["value"]["stringValue"] = "other-agent"
    with pytest.raises(ValueError, match="multiple agents"):
        to_bundle(export)
