"""0.8.5 evaluator usage: the optional, OpenTelemetry-GenAI-aligned `telemetry.evaluator_usage` block (the evaluator's
own LLM usage, speed and reliability; no cost). A record carrying it is PER 2.1.2; every other record keeps its bytes."""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from build_reference import build_arguments
from eio_agents import build_bundle
from eio_agents.base.errors import ConversionError
from eio_agents.schemas import per_schema

REPORT = json.loads((Path(__file__).parent / "data" / "report" / "travel_report.json").read_text(encoding="utf-8"))
QUOTE = "I found a direct flight to Lisbon on Friday morning."
CERTAINTY = "eio.predicate.certainty-exceeds-evidence"
TELEMETRY_UNAVAILABLE = {"llm_calls": None, "tokens": None, "latency_ms": None, "error_rate": None, "cost_usd": None,
                         "cost_provenance": "UNAVAILABLE"}


def _usage():
    return {"conventions": "otel-gen-ai", "provenance": "MEASURED", "wall_clock_seconds": 42.5, "llm_calls": 7,
            "tokens": {"input": 12000, "output": 900},
            "duration_ms": {"p50": 640.0, "p95": 1810.25, "max": 2400},
            "errors": {"count": 1, "types": ["timeout"]}, "retries": 1,
            "by_role": [
                {"role": "planner", "model": "openai/gpt-4.1-nano", "llm_calls": 1,
                 "tokens": {"input": 2000, "output": 300}, "duration_ms": {"p50": 900, "p95": 900, "max": 900},
                 "errors": 0},
                {"role": "jury", "model": "openai/gpt-4.1-nano", "llm_calls": 6,
                 "tokens": {"input": 10000, "output": 600}, "duration_ms": {"p50": 600, "p95": 1800, "max": 2400},
                 "errors": 1},
                {"role": "other", "model": None, "llm_calls": 0, "tokens": {"input": None, "output": None},
                 "duration_ms": None, "errors": 0}]}


def _args(usage=None, check=None):
    args = copy.deepcopy(build_arguments(REPORT))
    if usage is not None:
        args["telemetry"] = {"agent_under_test": dict(TELEMETRY_UNAVAILABLE, llm_calls=len(REPORT["conversation"])),
                             "wall_clock_seconds": None, "evaluator_usage": usage}
    if check is not None:
        args["checks"] += [check]
    return args


def _projected(args):
    bundle = build_bundle(**args)
    record = eio_agents.convert(bundle)
    assert eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]
    return bundle, record


def test_a_record_with_evaluator_usage_is_per_2_1_2_with_the_block_intact():
    _, record = _projected(_args(_usage()))
    assert record["header"]["per_version"] == "2.1.2"
    assert record["header"]["schema_uri"].endswith("/per/2.1.2/per.schema.json")
    usage, want = record["telemetry"]["evaluator_usage"], _usage()
    # the known role and error-type labels and every model id are in clear
    assert usage["by_role"] == want["by_role"]
    # per-call durations are integer milliseconds rounded half-up (PROD-10), as the agent's latency_ms
    assert usage["duration_ms"] == {"p50": 640, "p95": 1810, "max": 2400}
    assert {k: v for k, v in usage.items() if k not in ("by_role", "errors", "duration_ms")} == {
        k: v for k, v in want.items() if k not in ("by_role", "errors", "duration_ms")}
    assert usage["errors"] == {"count": 1, "types": ["timeout"]}
    assert "cost_usd" not in json.dumps(usage)


def test_without_evaluator_usage_the_record_is_unchanged():
    args = _args()
    bundle = build_bundle(**args)
    record = eio_agents.convert(bundle)
    assert record["header"]["per_version"] == "2.1.0"
    assert "evaluator_usage" not in record["telemetry"]
    assert eio_agents.per_sha256(record) == eio_agents.per_sha256(eio_agents.convert(build_bundle(**_args())))


@pytest.mark.parametrize("mutate,why", [
    (lambda u: u.update(llm_calls=-1), "negative count"),
    (lambda u: u["tokens"].update(input=-5), "negative tokens"),
    (lambda u: u.update(retries=1.5), "fractional count"),
    (lambda u: u["by_role"][0].update(role="Planner Agent"), "bad role label"),
    (lambda u: u["errors"].update(types=["Timeout!"]), "bad error type"),
    (lambda u: u.update(cost_usd=0.12), "cost field"),
    (lambda u: u["by_role"][0].update(cost_usd=0.01), "cost field in a role"),
    (lambda u: u.update(spans=[]), "unknown key"),
    (lambda u: u.update(conventions="otel"), "wrong conventions"),
    (lambda u: u.update(provenance="DECLARED"), "unknown provenance"),
    (lambda u: u.update(duration_ms={"p50": 10, "p95": 5, "max": 20}), "unordered percentiles"),
    (lambda u: u.pop("by_role"), "missing key"),
])
def test_a_malformed_block_is_refused(mutate, why):
    usage = _usage()
    mutate(usage)
    with pytest.raises(ConversionError):
        build_bundle(**_args(usage))
    # a bundle carrying it directly is refused by convert too
    bundle = build_bundle(**_args(_usage()))
    mutate(bundle["provenance"]["telemetry"]["evaluator_usage"])
    with pytest.raises(ConversionError):
        eio_agents.convert(bundle)


def test_a_tampered_record_fails_validation():
    bundle, record = _projected(_args(_usage()))
    bad = copy.deepcopy(record)
    bad["telemetry"]["evaluator_usage"]["llm_calls"] = -1
    assert eio_agents.validate(bad)
    bad = copy.deepcopy(record)
    bad["telemetry"]["evaluator_usage"]["cost_usd"] = 0.5
    assert eio_agents.validate(bad)
    # a 2.1.2 record without the block, or the block under 2.1.0, is mislabelled
    stripped = copy.deepcopy(record)
    del stripped["telemetry"]["evaluator_usage"]
    assert eio_agents.validate(stripped)
    relabelled = copy.deepcopy(record)
    relabelled["header"]["per_version"] = "2.1.0"
    relabelled["header"]["schema_uri"] = relabelled["header"]["schema_uri"].replace("/2.1.2/", "/2.1.0/")
    assert not eio_agents.verify(relabelled, bundle)["valid"]
    changed = copy.deepcopy(record)
    changed["telemetry"]["evaluator_usage"]["retries"] = 9
    assert not eio_agents.verify(changed, bundle)["valid"]


def test_model_and_role_strings_pass_the_closed_field_table():
    from eio_agents.per import privacy as producer_privacy
    from eio_agents.validation import privacy as verifier_privacy

    for table in (producer_privacy.TABLE_TEXT, verifier_privacy.TABLE_TEXT):
        for path in ("telemetry.evaluator_usage.by_role.*.role", "telemetry.evaluator_usage.by_role.*.model",
                     "telemetry.evaluator_usage.errors.types.*", "telemetry.evaluator_usage.conventions",
                     "telemetry.evaluator_usage.provenance"):
            assert f"    {path}\n" in table, path
    usage = _usage()
    usage["by_role"][2]["role"] = "custom_role"               # an unknown label is sealed as its fingerprint
    usage["errors"]["types"] = ["timeout", "quota_hit"]
    _, record = _projected(_args(usage))
    sealed = record["telemetry"]["evaluator_usage"]
    assert [r["role"] for r in sealed["by_role"][:2]] == ["planner", "jury"]
    assert sealed["by_role"][2]["role"].startswith("sha256-") and sealed["by_role"][0]["model"] == "openai/gpt-4.1-nano"
    assert sealed["errors"]["types"][0] == "timeout" and sealed["errors"]["types"][1].startswith("sha256-")


def test_jury_proven_with_evaluator_usage_is_2_1_2_and_keeps_semantic_proof():
    check = {"turn": 1, "predicate": "certainty-exceeds-evidence", "decided_by": "semantic", "model": "acme/jury",
             "quote": QUOTE, "jury": [{"persona": p, "observed": True, "quote": QUOTE}
                                      for p in ("rigorous", "lenient", "contrarian")]}
    _, record = _projected(_args(_usage(), check))
    assert record["header"]["per_version"] == "2.1.2"
    finding = next(f for f in record["findings"] if f["predicate"] == CERTAINTY)
    assert finding["proof_status"] == "PROVEN" and finding["decided_by"] == "semantic"
    _, jury_only = _projected(_args(None, check))
    assert jury_only["header"]["per_version"] == "2.1.1"


def test_the_2_1_2_schema_is_2_1_1_plus_the_optional_block():
    s1, s2 = per_schema("2.1.1"), per_schema("2.1.2")
    assert s2["$defs"]["telemetry"]["required"] == s1["$defs"]["telemetry"]["required"]
    assert s2["$defs"]["finding"] == s1["$defs"]["finding"]
    assert "cost_usd" not in json.dumps(s2["$defs"]["evaluator_usage"])
    assert eio_agents.standards()["telemetry_per_version"] == "2.1.2"


# ── model identifiers in telemetry (0.8.5): common provider ids are accepted, sensitive shapes still refused ─────────
PROVIDER_MODELS = ["openai/gpt-4.1-nano", "gpt-4.1-mini", "anthropic/claude-haiku-4-5", "claude-haiku-4-5-20251001",
                   "claude-sonnet-4-5-20250929", "anthropic/claude-opus-4-1@20250805"]


def _with_model(model, where):
    usage = _usage()
    args = _args(usage)
    if where == "evaluator_usage":
        args["telemetry"]["evaluator_usage"]["by_role"][0]["model"] = model
    else:
        args["telemetry"]["evaluator_models"] = [{"role": "jury", "model": model}]
    return args


@pytest.mark.parametrize("where", ["evaluator_usage", "evaluator_models"])
@pytest.mark.parametrize("model", PROVIDER_MODELS)
def test_a_provider_model_id_in_telemetry_is_kept_in_clear(model, where):
    _, record = _projected(_with_model(model, where))
    telemetry = record["telemetry"]
    got = (telemetry["evaluator_usage"]["by_role"][0]["model"] if where == "evaluator_usage"
           else telemetry["evaluator_models"][0]["model"])
    assert got == model


@pytest.mark.parametrize("where", ["evaluator_usage", "evaluator_models"])
@pytest.mark.parametrize("model", ["sk-live-abcdefgh", "john-123-45-6789", "john.doe@example.com"])
def test_a_sensitive_model_shape_in_telemetry_is_still_refused(model, where):
    with pytest.raises(ConversionError) as caught:
        build_bundle(**_with_model(model, where))
    assert caught.value.code == "BUILD_PERSONAL_DATA"


def test_the_model_exemption_does_not_reach_other_telemetry_fields():
    args = _args(_usage())
    args["telemetry"]["evaluator_models"] = [{"role": "claude-haiku-4-5-20251001", "model": None}]
    with pytest.raises(ConversionError) as caught:
        build_bundle(**args)
    assert caught.value.code == "BUILD_PERSONAL_DATA"
