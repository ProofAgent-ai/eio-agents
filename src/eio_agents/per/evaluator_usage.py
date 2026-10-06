"""The optional `telemetry.evaluator_usage` block (PER 2.1.2, EIO-Agents 0.8.5): the evaluator's (harness's) own LLM usage,
speed and reliability, aligned with the OpenTelemetry GenAI semantic conventions. It carries no cost. A producer declares
it in `provenance.telemetry.evaluator_usage`; `check` refuses any other shape before it reaches a record. The record's
schema (`per-2.1.2.schema.json`, `$defs/evaluator_usage`) states the same contract for the sealed record."""
from __future__ import annotations

import re

from eio_agents.base.canon import half_up_int, q4
from eio_agents.base.errors import require

ROLE = re.compile(r"[a-z][a-z0-9_]{0,31}")
PROVENANCE = ("MEASURED", "PARTIAL", "UNAVAILABLE")
KEYS = ("conventions", "provenance", "wall_clock_seconds", "llm_calls", "tokens", "duration_ms", "errors", "retries",
        "by_role")
ROLE_KEYS = ("role", "model", "llm_calls", "tokens", "duration_ms", "errors")
_FIELD = "provenance.telemetry.evaluator_usage"


def _fail(code, where, why):
    require(False, code, f"{_FIELD}{where}: {why}")


def _keys(code, obj, keys, where):
    if not isinstance(obj, dict):
        _fail(code, where, "must be an object")
    costs = sorted(k for k in obj if "cost" in str(k).lower())
    if costs:
        _fail(code, where, f"carries no cost: remove {costs}")
    if set(obj) != set(keys):
        missing, extra = sorted(set(keys) - set(obj)), sorted(set(obj) - set(keys), key=str)
        _fail(code, where, f"must have exactly the keys {list(keys)}" + (f"; missing {missing}" if missing else "")
              + (f"; unknown {extra}" if extra else ""))


def _count(code, v, where, *, null=False):
    if v is None and null:
        return
    if not (type(v) is int and v >= 0):
        _fail(code, where, "must be a non-negative integer" + (" or null" if null else ""))


def _number(v):
    return type(v) in (int, float) and v == v and v not in (float("inf"),) and v >= 0


def _tokens(code, v, where):
    _keys(code, v, ("input", "output"), where)
    _count(code, v["input"], where + ".input", null=True)
    _count(code, v["output"], where + ".output", null=True)


def _duration(code, v, where):
    if v is None:
        return
    _keys(code, v, ("p50", "p95", "max"), where)
    for k in ("p50", "p95", "max"):
        if not _number(v[k]):
            _fail(code, f"{where}.{k}", "must be a non-negative number of milliseconds")
    if not v["p50"] <= v["p95"] <= v["max"]:
        _fail(code, where, "must satisfy p50 <= p95 <= max")


def _label(code, v, where):
    if not (isinstance(v, str) and ROLE.fullmatch(v)):
        _fail(code, where, "must be a short lower-case label [a-z][a-z0-9_]{0,31}")


def check(usage, *, code="BUNDLE_INPUT"):
    """Refuse an `evaluator_usage` block outside the 0.8.5 contract (exact keys, no cost, non-negative counts and
    durations, lower-case role and error-type labels). Returns None."""
    _keys(code, usage, KEYS, "")
    if usage["conventions"] != "otel-gen-ai":
        _fail(code, ".conventions", "must be 'otel-gen-ai'")
    if usage["provenance"] not in PROVENANCE:
        _fail(code, ".provenance", f"must be one of {list(PROVENANCE)}")
    if usage["wall_clock_seconds"] is not None and not _number(usage["wall_clock_seconds"]):
        _fail(code, ".wall_clock_seconds", "must be a non-negative number or null")
    _count(code, usage["llm_calls"], ".llm_calls")
    _tokens(code, usage["tokens"], ".tokens")
    _duration(code, usage["duration_ms"], ".duration_ms")
    _keys(code, usage["errors"], ("count", "types"), ".errors")
    _count(code, usage["errors"]["count"], ".errors.count")
    types = usage["errors"]["types"]
    if not isinstance(types, list):
        _fail(code, ".errors.types", "must be a list")
    for i, t in enumerate(types):
        _label(code, t, f".errors.types[{i}]")
    if len(set(types)) != len(types):
        _fail(code, ".errors.types", "must not repeat a type")
    _count(code, usage["retries"], ".retries")
    if not isinstance(usage["by_role"], list):
        _fail(code, ".by_role", "must be a list")
    for i, row in enumerate(usage["by_role"]):
        where = f".by_role[{i}]"
        _keys(code, row, ROLE_KEYS, where)
        _label(code, row["role"], where + ".role")
        if row["model"] is not None and not (isinstance(row["model"], str) and row["model"]):
            _fail(code, where + ".model", "must be a non-empty string or null")
        _count(code, row["llm_calls"], where + ".llm_calls")
        _tokens(code, row["tokens"], where + ".tokens")
        _duration(code, row["duration_ms"], where + ".duration_ms")
        _count(code, row["errors"], where + ".errors")


def _ms(v):
    return None if v is None else {k: half_up_int(v[k]) for k in ("p50", "p95", "max")}


def in_record(usage):
    """The record's form of a checked block, in place: per-call durations as integer milliseconds rounded half-up
    (PROD-10, as the agent's `latency_ms`), the wall clock at most 4 decimal places (PROD-11). Returns it."""
    secs = usage["wall_clock_seconds"]
    if isinstance(secs, float):
        usage["wall_clock_seconds"] = q4(secs)
    usage["duration_ms"] = _ms(usage["duration_ms"])
    for row in usage["by_role"]:
        row["duration_ms"] = _ms(row["duration_ms"])
    return usage
