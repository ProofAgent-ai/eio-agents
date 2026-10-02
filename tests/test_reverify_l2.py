"""Native and generic re-verification checks; historical adapter cases live externally."""

import copy
import json
import pytest
from test_bundle import KP, SP, _base, _eio, _hand_named_absence, _restamp
import eio_agents
from eio_agents import validation
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError
from eio_agents.evidence import context_refs
from eio_agents.evidence.refs import no_call_ref, no_matching_call_ref
from eio_agents.per import canonical_bytes, project
from eio_agents.semantics import ids
from eio_agents.semantics.claims import make_claim
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.verify import c_sources

TURN_FIELDS = ("AGENT_ANSWER", "USER_INPUT")
OFFSET_ANCHORS = ("exact", "casefold", "turn", "line")
LOCATORS = ("char_start", "char_end", "span_sha256", "source_sha256")
EXCERPTS = ("excerpt", "excerpt_truncated", "excerpt_redacted")


def _outcome(b):
    """`convert` on a copy of `b`: the record, or the typed code of the failure (an untyped exception fails the test)."""
    try:
        return eio_agents.convert(copy.deepcopy(b), ontology=_eio())
    except ConversionError as e:
        assert e.code, f"a ConversionError without a code: {e}"
        return e.code


def _locates(r):
    return any((r.get(k) is not None for k in LOCATORS)) or any((k in r for k in EXCERPTS))


STATEMENT_REQUIRED = ("TYPED_ABSENCE", "CALCULATION")
STATEMENT_OPTIONAL = ("STATE_FACT", "STATE_TRANSITION", "PROVENANCE")


def _synthetic(eio, kind, st, anchor, turn_source, t=1, statement=False):
    """A producer-declared ref of (kind, source type, anchor) that no builder made, with the witness flag the release gives
    it (unpaired), offsets iff an offset anchor (the anchor rules the schema states), and a statement iff `statement`. It
    names the declared turn source: from L3 fix round 1 (issue 1) a ref that no recipe rebuilds names a source the bundle
    declares, a rule the `test_bundle.INVALID` entries 'L3r1 issue 1' test on their own (it was 'declared/source' before)."""
    offsets = anchor in OFFSET_ANCHORS
    x = "a declared text"
    (a, b) = (0, len(x)) if offsets else (None, None)
    r = {
        "id": ids.ref_id(kind, st, t, x, a, b),
        "kind": kind,
        "source_type": st,
        "can_prove_agent_behaviour": eio.can_prove(kind, st),
        "anchor": anchor,
        "turn_index": t,
        "char_start": a,
        "char_end": b,
        "span_sha256": H(x) if offsets else None,
        "source_ref": turn_source,
        "source_sha256": None,
    }
    if statement:
        r["statement"] = {"inputs": {"declared": True}, "formula": "declared()", "output": 0}
    if kind == "TOOL_RECEIPT":
        r["tool"] = {
            "name": "declared_tool",
            "call_index": 0,
            "arguments_sha256": H(jb({})),
            "arguments_pointer": "/sources/turns/0/tool_calls/0/arguments",
            "output": "NOT_CAPTURED",
        }
    return r


def _matrix(eio):
    """Every (kind, compatible source type, anchor, statement) of the loaded release, the statement in the forms the rc1
    schema admits for the kind: always for TYPED_ABSENCE and CALCULATION, with and without for STATE_FACT,
    STATE_TRANSITION and PROVENANCE, never for the others."""
    forms = {
        k: (True,) if k in STATEMENT_REQUIRED else (False, True) if k in STATEMENT_OPTIONAL else (False,)
        for k in eio.kind
    }
    return [
        (k, s, a, w)
        for (k, kd) in eio.kind.items()
        for s in kd["compatible_source_types"]
        for a in sorted(eio.anchors)
        for w in forms[k]
    ]


def _rebuilt(kind, st, anchor):
    """The combinations a recipe of EIO-Agents rebuilds from the bundle's sources (so a synthetic ref never matches it)."""
    return (
        kind in ("TOOL_RECEIPT", "POLICY_SPAN")
        or (kind == "TYPED_ABSENCE" and st in ("AGENT_TOOL_CALL", "POLICY_SOURCE"))
        or (st in TURN_FIELDS and anchor in OFFSET_ANCHORS)
    )


def _declared_ok(eio, kind, st, anchor, statement):
    """The rule, stated independently of the code: a combination that no recipe rebuilds converts iff it obeys the anchor
    rules (TYPED_ABSENCE/CALCULATION computed; a juror citation none; offsets only on rebuilt kinds, receipt only on a
    TOOL_RECEIPT, line/document only on a POLICY_SPAN), does not witness, and carries no statement (L2 exit D-31: nothing
    checks a declared statement against the bundle's sources, so a declared TYPED_ABSENCE or CALCULATION never converts)."""
    rebuilt = _rebuilt(kind, st, anchor)
    if kind in ("TYPED_ABSENCE", "CALCULATION"):
        anchor_ok = anchor == "computed"
    elif st == "JUROR_INFERENCE":
        anchor_ok = anchor == "none"
    else:
        anchor_ok = anchor in ("none", "computed")
    witnessing = eio.can_prove(kind, st) and anchor in eio.witnessing_anchors
    return not rebuilt and anchor_ok and (not witnessing) and (not statement)


def test_a_ref_converts_only_when_rebuilt_or_as_a_non_witnessing_ref_that_locates_no_text():
    """Review R-1. Each combination is a producer-declared ref that no builder made (so no recipe accepts it), in the
    native bundle (juror citations are excluded because a native producer never mints them). A combination that converts
    neither witnesses nor locates text, and it is exactly the set the rule states; every witnessing one fails closed."""
    eio = _eio()
    base = _base("native")
    (converted, witnessing_seen, with_statement) = (set(), 0, 0)
    for kind, st, anchor, statement in _matrix(eio):
        if st == "JUROR_INFERENCE":
            continue
        r = _synthetic(eio, kind, st, anchor, base["sources"]["turn_source_ref"], statement=statement)
        b = copy.deepcopy(base)
        b["graph"]["refs"].append(r)
        got = _outcome(_restamp(b))
        if isinstance(got, dict):
            converted.add((kind, st, anchor, statement))
            assert not eio.witnessing_anchored(r) and (not _locates(r)) and ("statement" not in r), (
                kind,
                st,
                anchor,
                statement,
            )
        else:
            assert got == "BUNDLE_RECOMPUTE", (kind, st, anchor, statement, got)
        if eio.witnessing_anchored(r):
            witnessing_seen += 1
            assert got == "BUNDLE_RECOMPUTE", (kind, st, anchor, statement)
        if statement and (not _rebuilt(kind, st, anchor)):
            with_statement += 1
            assert got == "BUNDLE_RECOMPUTE", (kind, st, anchor, got)
    assert converted == {c for c in _matrix(eio) if c[1] != "JUROR_INFERENCE" and _declared_ok(eio, *c)}
    assert witnessing_seen >= 40 and len(converted) >= 8 and (with_statement >= 100)
    assert {
        ("STATE_FACT", "STATE_LEDGER", "none", False),
        ("STATE_TRANSITION", "STATE_LEDGER", "none", False),
        ("PROVENANCE", "HARNESS_SIGNAL", "none", False),
        ("HUMAN_SIGNOFF", "HUMAN_REVIEW", "none", False),
        ("AGENT_SPAN", "AGENT_ANSWER", "none", False),
    } <= converted
    assert not any((k in STATEMENT_REQUIRED or w for (k, _s, _a, w) in converted))


def test_the_verifier_twin_applies_the_same_rule_to_every_declared_ref():
    """Review R-1, the twin (VER-5): the same matrix, each ref carried by the native record. A ref that witnesses or locates
    text is a D2 problem unless the twin rebuilt it (and a synthetic ref never rebuilds); a declared ref the rule accepts is
    none. The twin reads the witness rule with its own reader of the release."""
    (eio, reader) = (_eio(), EIO(EIO_DIR))
    nb = _base("native")
    rec0 = eio_agents.convert(copy.deepcopy(nb), ontology=eio)
    assert c_sources(rec0, nb, reader)[0] == []
    for kind, st, anchor, statement in _matrix(eio):
        if st == "JUROR_INFERENCE":
            continue
        r = _synthetic(eio, kind, st, anchor, nb["sources"]["turn_source_ref"], statement=statement)
        rec = copy.deepcopy(rec0)
        rec["evidence"]["refs"].append(r)
        problems = c_sources(rec, nb, reader)[0]
        if eio.witnessing_anchored(r) or _locates(r):
            assert any((r["id"] in x for x in problems)), (kind, st, anchor, statement)
        elif _declared_ok(eio, kind, st, anchor, statement):
            assert problems == [], (kind, st, anchor, statement, problems)
        if statement and (not _rebuilt(kind, st, anchor)):
            assert any((r["id"] in x and "carries a statement" in x for x in problems)), (kind, st, anchor, problems)


def test_the_twin_flags_a_declared_witnessing_or_locating_ref_by_name():
    b = _base("native")
    rec0 = eio_agents.convert(copy.deepcopy(b), ontology=_eio())
    calc = {
        "id": ids.ref_id("CALCULATION", "AGENT_TOOL_CALL", 1, "no tool call on turn 1"),
        "kind": "CALCULATION",
        "source_type": "AGENT_TOOL_CALL",
        "can_prove_agent_behaviour": True,
        "anchor": "computed",
        "turn_index": 1,
        "char_start": None,
        "char_end": None,
        "span_sha256": None,
        "source_ref": "turns",
        "source_sha256": None,
        "statement": {"inputs": {"source": "tool_calls", "turns": [1]}, "formula": "len(tool_calls[t])", "output": 0},
    }
    x = "quoted from nowhere"
    retr = {
        "id": ids.ref_id("RETRIEVAL", "RETRIEVAL", 1, x, 0, len(x)),
        "kind": "RETRIEVAL",
        "source_type": "RETRIEVAL",
        "can_prove_agent_behaviour": False,
        "anchor": "exact",
        "turn_index": 1,
        "char_start": 0,
        "char_end": len(x),
        "span_sha256": H(x),
        "excerpt": x,
        "source_ref": "retrieved/doc-1",
        "source_sha256": None,
    }
    for r, words in (
        (calc, "a witnessing CALCULATION ref over AGENT_TOOL_CALL that does not recompute"),
        (retr, "with its text in no source of the bundle carries ['char_start', 'char_end', 'span_sha256', 'excerpt']"),
    ):
        rec = copy.deepcopy(rec0)
        rec["evidence"]["refs"].append(r)
        assert any((words in p for p in c_sources(rec, b)[0])), words


def _ref_where(b, **kw):
    return next((r for r in b["graph"]["refs"] if all((r.get(k) == v for (k, v) in kw.items()))))


def _v2e(b):
    text = "Returns are accepted within 30 days."
    r = context_refs.policy_span_ref(
        _eio(), {"name": "policy.md", "sha256": H(text.encode()), "data_class": "eio.data.internal"}, text, 0, 20
    )
    b["graph"]["refs"].append(r)
    b["claims"][0]["evidence"].append(r["id"])


def _v3e(b):
    old = _ref_where(b, kind="TYPED_ABSENCE")
    old_id = old["id"]
    old["turn_index"] = 1
    old["statement"]["inputs"]["turns"] = [2]
    old["id"] = ids.ref_id("TYPED_ABSENCE", "AGENT_TOOL_CALL", 1, "no tool call on turn 1")
    for c in b["claims"]:
        c["evidence"] = [old["id"] if e == old_id else e for e in c["evidence"]]


def _v4f(b):
    x = "no occurrence of 'x' in the answer of turn 7"
    r = {
        "id": ids.ref_id("TYPED_ABSENCE", "AGENT_ANSWER", 7, x),
        "kind": "TYPED_ABSENCE",
        "source_type": "AGENT_ANSWER",
        "can_prove_agent_behaviour": True,
        "anchor": "computed",
        "turn_index": 7,
        "char_start": None,
        "char_end": None,
        "span_sha256": None,
        "source_ref": "turns",
        "source_sha256": None,
        "statement": {"inputs": {"source": "turns", "turns": [7]}, "formula": "count(x in answer[t])", "output": 0},
    }
    b["graph"]["refs"].append(r)
    b["claims"][0]["evidence"].append(r["id"])


def _v3z(b):
    r = no_call_ref(_eio(), 3, [], source_ref="turns", calls_field="tool_calls")
    b["graph"]["refs"].append(r)
    old = b["claims"][0]
    b["claims"].append(
        make_claim(
            _eio(),
            run_id=old["run_id"],
            predicate="eio.predicate.prohibited-tool-invoked",
            turn_indices=[3],
            state="APPLICABLE_PASS",
            parameters={"fidelity": "exact", "votes": None},
            evidence=[r["id"]],
            decided_by="deterministic",
            resolver=None,
            plan_hash=b["header"]["plan_hash"],
            model="acme/judge-small-1",
            seed=7,
        )
    )


PROBES = {
    "V2e POLICY_SPAN in a native bundle without artifacts": ("native", _v2e, "BUNDLE_RECOMPUTE"),
    "V3z control: new native claim on a true TA(3)": ("native", _v3z, "CONVERTS"),
    "V3e TA(t) on a turn with a call, inputs naming another turn": ("native", _v3e, "BUNDLE_RECOMPUTE"),
    "V4c tool receipt on turn 99": (
        "native",
        lambda b: _ref_where(b, kind="TOOL_RECEIPT").update(turn_index=99),
        "BUNDLE_RECOMPUTE",
    ),
    "V4e answer span on turn -1": (
        "native",
        lambda b: _ref_where(b, source_type="AGENT_ANSWER", turn_index=2).update(turn_index=-1),
        "BUNDLE_RECOMPUTE",
    ),
    "V4f declared typed absence over the answer on turn 7 (3 turns)": ("native", _v4f, "BUNDLE_RECOMPUTE"),
}
NATIVE_PROBES = {case: row for (case, row) in PROBES.items() if row[0] == "native"}


@pytest.mark.parametrize("case", list(NATIVE_PROBES))
def test_a_reverification_probe_gives_its_outcome(eio, case):
    (base, edit, want) = NATIVE_PROBES[case]
    b = _base(base)
    edit(b)
    got = _outcome(_restamp(b))
    assert (got if isinstance(got, str) else "CONVERTS") == want
    if isinstance(got, dict):
        v = eio_agents.verify(got, b, ontology=eio)
        assert v["digest_match"], v["failures"]
        fails = [f["check"][:2] for f in v["failures"]]
        assert fails == [], v["failures"]


@pytest.mark.parametrize("names", [(SP, KP), (KP,), (SP,)])
def test_a_native_bundle_with_embedded_context_converts(eio, names):
    """A native producer may embed synthetic private and public context files."""
    b = _base("native")
    contexts = [
        (
            SP,
            "eio.artifact.system-prompt",
            "eio.data.model-confidential",
            "Synthetic confidential instruction that must not be quoted in public output.",
        ),
        (KP, "eio.artifact.knowledge-source", "eio.data.public", "Synthetic public customer data policy."),
    ]
    for n, k, dc, t in contexts:
        if n in names:
            b["sources"]["context_artifacts"].append(
                {
                    "artifact_kind": k,
                    "name": n,
                    "sha256": H(t.encode("utf-8")),
                    "code_points": len(t),
                    "embedded": True,
                    "data_class": dc,
                }
            )
            b["sources"]["context_texts"][n] = t
    _restamp(b)
    assert validation.validate_bundle(copy.deepcopy(b)) == []
    rec = eio_agents.convert(copy.deepcopy(b), ontology=eio)
    v = eio_agents.verify(rec, b, ontology=eio)
    assert v["digest_match"] and v["failures"] == [], v["failures"]
    if SP in names:
        assert not any("Synthetic confidential instruction" in str(ref) for ref in rec["evidence"]["refs"])


def _text_with_a_member_twice(b, name):
    """The bundle's JSON text with one context name twice (Python's reader keeps the last)."""
    text = json.dumps(b, ensure_ascii=False)
    key = json.dumps(name)
    at = text.index(key + ": ", text.index('"context_texts"'))
    return text[:at] + key + ': "an earlier text", ' + text[at:]


def test_a_json_member_given_twice_fails_closed_everywhere(eio):
    b = _base("native")
    (name, content) = ("policy.md", "Synthetic customer data policy.")
    b["sources"]["context_artifacts"].append(
        {
            "artifact_kind": "eio.artifact.knowledge-source",
            "name": name,
            "sha256": H(content.encode("utf-8")),
            "code_points": len(content),
            "embedded": True,
            "data_class": "eio.data.public",
        }
    )
    b["sources"]["context_texts"][name] = content
    _restamp(b)
    text = _text_with_a_member_twice(b, name)
    assert json.loads(text) == b
    for fn in (
        lambda: eio_agents.convert(text.encode("utf-8"), ontology=eio),
        lambda: project(text, ontology=eio),
        lambda: eio_agents.verify(
            eio_agents.convert(copy.deepcopy(b), ontology=eio), text.encode("utf-8"), ontology=eio
        ),
    ):
        with pytest.raises(ConversionError, match="twice") as e:
            fn()
        assert e.value.code == "BUNDLE_INPUT"
    [row] = validation.validate_bundle(text)
    assert row["check"].startswith("B0") and "twice" in row["detail"]
    rec = eio_agents.convert(copy.deepcopy(b), ontology=eio)
    r = validation.verify(rec, text, rederived=rec)
    assert not r["valid"] and any((f["check"].startswith("D2") and "twice" in f["detail"] for f in r["failures"]))
    assert eio_agents.verify(rec, json.dumps(b).encode("utf-8"), ontology=eio)["valid"]


@pytest.mark.parametrize(
    "text",
    [
        b"\xff\xfe{",
        b'{"archive_schema": 3, "x": NaN}',
        b'{"archive_schema": 3, "x": Infinity}',
        b'{"archive_schema": 3, "x": 1e400}',
        b"[" * 100000 + b"]" * 100000,
    ],
)
def test_bundle_bytes_that_are_not_i_json_fail_closed(eio, text):
    """Undecodable bytes, a NaN or infinite number, a number beyond the double range, nesting too deep to read: typed
    everywhere (before this round `per.project` leaked UnicodeDecodeError, and `convert` RecursionError)."""
    for fn in (lambda: project(text, ontology=eio), lambda: eio_agents.convert(text, ontology=eio)):
        with pytest.raises(ConversionError) as e:
            fn()
        assert e.value.code == "BUNDLE_INPUT"
    assert validation.validate_bundle(text)[0]["check"].startswith("B0")


def _nest(levels):
    o = "leaf"
    for _ in range(levels):
        o = {"x": o}
    return o


def test_a_bundle_nested_deeper_than_the_limit_fails_closed_whoever_reads_it(eio):
    """The M-3 class, nesting (found in this round): a dict bundle nested 350-475 levels in a free-form field raised an
    untyped RecursionError late in the projection (deeper ones in the first deep copy). Now a bundle nested more than
    `MAX_DEPTH` levels fails closed at read time, the same for any caller's stack, and the verifier applies the same
    limit; the shipped bundles nest 7 levels."""
    from eio_agents.per.bundle import MAX_DEPTH, nested_deeper_than

    (at_limit, over) = (_base("native"), _base("native"))
    at_limit["provenance"]["telemetry"]["deep"] = _nest(MAX_DEPTH - 3)
    over["provenance"]["telemetry"]["deep"] = _nest(MAX_DEPTH - 2)
    assert not nested_deeper_than(at_limit, MAX_DEPTH) and nested_deeper_than(over, MAX_DEPTH)
    got = _outcome(_restamp(at_limit))
    assert not got == "BUNDLE_INPUT"
    assert not any((x["check"].startswith("B0") for x in validation.validate_bundle(at_limit)))
    for fn in (
        lambda: eio_agents.convert(over, ontology=eio),
        lambda: project(json.dumps(over), ontology=eio),
        lambda: eio_agents.convert(json.dumps(over).encode("utf-8"), ontology=eio),
    ):
        with pytest.raises(ConversionError, match="nested more than") as e:
            fn()
        assert e.value.code == "BUNDLE_INPUT"
    assert validation.validate_bundle(over)[0]["check"].startswith("B0")
    for levels in range(300, 1000, 75):
        b = _base("native")
        b["header"]["eio_agents"]["version"] = "0.0.0-another"
        b["provenance"]["telemetry"]["deep"] = _nest(levels)
        with pytest.raises(ConversionError) as e:
            eio_agents.convert(b, ontology=eio)
        assert e.value.code == "BUNDLE_INPUT", levels
    cyclic = _base("native")
    cyclic["provenance"]["telemetry"]["self"] = cyclic
    with pytest.raises(ConversionError) as e:
        eio_agents.convert(cyclic, ontology=eio)
    assert e.value.code == "BUNDLE_INPUT"


def test_verify_reports_a_record_without_a_canonical_form_instead_of_raising(eio):
    """`verify` computed the record digest outside its check rows, so a record with a NaN or nested too deeply to
    canonicalise raised (ValueError, RecursionError) where `validate` returns failing rows."""
    b = _base("native")
    rec0 = eio_agents.convert(copy.deepcopy(b), ontology=eio)
    for bad in (float("nan"), _nest(2000)):
        rec = copy.deepcopy(rec0)
        rec["telemetry"]["x"] = bad
        v = eio_agents.verify(rec, b, ontology=eio)
        assert not v["valid"] and (not v["digest_match"]) and (v["per_sha256"] is None)
        assert any((f["check"].startswith("D3") and "no canonical form" in f["detail"] for f in v["failures"]))


def test_validate_bundle_reports_each_name_rule_in_b1():
    """Review R-2: `validate_bundle` agrees with `convert` on the names the sources and the graph are resolved by."""
    duplicate_artifact, _ = _native_context_bundle()
    duplicate_artifact["sources"]["context_artifacts"].append(
        dict(duplicate_artifact["sources"]["context_artifacts"][0], data_class="eio.data.internal")
    )
    not_embedded, name = _native_context_bundle()
    not_embedded["sources"]["context_artifacts"][0]["embedded"] = False
    orphan = _base("native")
    orphan["sources"]["context_texts"]["orphan.md"] = "Synthetic orphan text."
    missing_text, name = _native_context_bundle()
    del missing_text["sources"]["context_texts"][name]
    duplicate_turn = _base("native")
    duplicate_turn["sources"]["turns"].append(copy.deepcopy(duplicate_turn["sources"]["turns"][0]))
    for case, b in (
        ("duplicate artifact", duplicate_artifact),
        ("not embedded but text kept", not_embedded),
        ("orphan context text", orphan),
        ("embedded artifact without text", missing_text),
        ("duplicate turn index", duplicate_turn),
    ):
        rows = validation.validate_bundle(b)
        assert [x["check"][:2] for x in rows] == ["B1"], (case, rows)
    b = _base("native")
    b["graph"]["refs"].append(copy.deepcopy(b["graph"]["refs"][0]))
    assert "graph.refs id" in validation.validate_bundle(_restamp(b))[0]["detail"]
    b = _base("native")
    b["claims"].append(copy.deepcopy(b["claims"][0]))
    assert "claims id" in validation.validate_bundle(_restamp(b))[0]["detail"]


def _native_context_bundle():
    b = _base("native")
    (name, content) = ("policy.md", "Synthetic customer data policy.")
    b["sources"]["context_artifacts"].append(
        {
            "artifact_kind": "eio.artifact.knowledge-source",
            "name": name,
            "sha256": H(content.encode("utf-8")),
            "code_points": len(content),
            "embedded": True,
            "data_class": "eio.data.public",
        }
    )
    b["sources"]["context_texts"][name] = content
    return (_restamp(b), name)


def test_the_twin_checks_the_names_the_sources_are_resolved_by(eio):
    (b, name) = _native_context_bundle()
    rec = eio_agents.convert(copy.deepcopy(b), ontology=eio)
    assert c_sources(rec, b)[0] == []
    b2 = copy.deepcopy(b)
    arts = b2["sources"]["context_artifacts"]
    arts.append(dict(next((a for a in arts if a["name"] == name)), data_class="eio.data.internal"))
    assert any(("are given twice" in p for p in c_sources(rec, b2)[0]))
    b3 = copy.deepcopy(b)
    b3["sources"]["context_texts"]["notes/orphan.md"] = "text"
    assert any(("are not the texts of the embedded context artifacts" in p for p in c_sources(rec, b3)[0]))


def test_a_mixed_context_search_that_holds_over_its_embedded_files_converts(eio):
    """No over-rejection: a gap over an embedded artifact and a name that is not embedded, whose terms occur in neither
    embedded text and whose count covers at least the embedded characters, converts, validates and verifies."""
    (b, name) = _native_context_bundle()
    n = len(b["sources"]["context_texts"][name])
    b["sources"]["context_artifacts"].append(
        {
            "artifact_kind": "eio.artifact.knowledge-source",
            "name": "not_embedded.md",
            "sha256": H(b"An external policy."),
            "code_points": 19,
            "embedded": False,
            "data_class": "eio.data.public",
        }
    )
    b["context_assessment"] = {
        "gaps": [
            {
                "criterion": "eio.context.guardrail-coverage",
                "control": "personal-data",
                "files_searched": [name, "not_embedded.md"],
                "chars_searched": n + 5,
                "terms": ["pii"],
            }
        ]
    }
    rec = eio_agents.convert(_restamp(b), ontology=eio)
    assert eio_agents.validate(rec) == []
    v = eio_agents.verify(rec, b, ontology=eio)
    assert v["valid"] and v["digest_match"], v["failures"]


def test_the_twin_recomputes_a_context_absence_over_every_embedded_file(eio):
    (b, name) = _native_context_bundle()
    rec = eio_agents.convert(copy.deepcopy(b), ontology=eio)
    word = "customer"
    r = context_refs.ctx_absence_ref(
        eio, [name, "not_embedded.md"], len(b["sources"]["context_texts"][name]) + 5, [word]
    )
    rec["evidence"]["refs"].append(r)
    assert any((r["id"] in p and "occurrence(s)" in p for p in c_sources(rec, b)[0]))
    r2 = context_refs.ctx_absence_ref(eio, ["not_embedded.md"], 100, ["zz"])
    r2["statement"]["formula"] = "trust me"
    rec["evidence"]["refs"][-1] = r2
    assert any((r2["id"] in p and "not the recipe's" in p for p in c_sources(rec, b)[0]))


def test_the_named_call_builder_takes_non_empty_lower_case_names_only(eio):
    for terms in (["VERIFY"], ["verify", "Authenticate"], [""], []):
        with pytest.raises(ConversionError) as e:
            no_matching_call_ref(eio, 1, [1], terms, [], source_ref="turns", calls_field="tool_calls")
        assert e.value.code == "INVARIANT"
    assert (
        no_matching_call_ref(eio, 1, [1], ["verify"], [], source_ref="turns", calls_field="tool_calls")["statement"][
            "output"
        ]
        == 0
    )


def test_the_twin_takes_lower_case_names_only():
    """R-5, and since L3 (L2 exit D-35, F-8) lower-case ASCII names: the twin's message names the rule."""
    b = _base("native")
    rec = eio_agents.convert(copy.deepcopy(b), ontology=_eio())
    for terms in (["VERIFY"], ["x' or 'lookup"], ["lооkup"]):
        rec2 = copy.deepcopy(rec)
        rec2["evidence"]["refs"].append(_hand_named_absence(1, [1], terms, "turns", "tool_calls"))
        assert any(("not a list of lower-case ASCII names" in p for p in c_sources(rec2, b)[0])), terms


def _call_pointer(p):

    def edit(b):
        b["sources"]["turns"][0]["tool_calls"][0]["arguments_pointer"] = p
        _ref_where(b, kind="TOOL_RECEIPT")["tool"]["arguments_pointer"] = p

    return edit


def _votes(**kw):

    def edit(b):
        next((c for c in b["claims"] if c["parameters"].get("votes")))["parameters"]["votes"].update(kw)

    return edit


def _load(base):
    assert base == "native", base
    return _base("native")


EDGES = {
    "M-1 native an empty episode": (
        "native",
        lambda b: b["graph"].update(episodes=[[1], [2], [3], []]),
        "BUNDLE_SCHEMA",
    ),
    "M-1 native a turn twice in one episode": (
        "native",
        lambda b: b["graph"].update(episodes=[[1], [2], [3, 3]]),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native producer source_format (an N8 name)": (
        "native",
        lambda b: b["provenance"]["record"]["producer"].update(source_format="eio-bundle"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native producer harness_version (an rc1 producer field)": (
        "native",
        lambda b: b["provenance"]["record"]["producer"].update(harness_version="2.0"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native run_id_source archive_digest": (
        "native",
        lambda b: b["provenance"]["record"]["run"].update(run_id_source="archive_digest"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native run_id_source Producer": (
        "native",
        lambda b: b["provenance"]["record"]["run"].update(run_id_source="Producer"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native a second archive pointer into /sources": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(first_turn="/sources/turns/0"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native a second archive pointer named by a layout token": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(tool_calls="/sources/turns/0/tool_calls"),
        "NATIVE_PREVIEW_SCHEMA",
    ),
    "M-2 native archive pointer /sources/nowhere": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(turns="/sources/nowhere"),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native archive pointer /sourcesX": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(turns="/sourcesX"),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native archive pointer with a leading zero": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(turns="/sources/turns/01"),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native archive pointer not a string": (
        "native",
        lambda b: b["sources"]["archive_pointer"].update(turns=7),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native call pointer in the rc1 form": (
        "native",
        _call_pointer("/transcript/0/tools_called/0/arguments"),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native call pointer to another call's slot": (
        "native",
        _call_pointer("/sources/turns/1/tool_calls/0/arguments"),
        "BUNDLE_RECOMPUTE",
    ),
    "M-2 native pooled votes in the rc1 shape": ("native", _votes(archive_observed=3, archive_total=3), "CONVERTS"),
    "M-2 native source_archive {}": ("native", lambda b: b["header"].update(source_archive={}), "BUNDLE_SCHEMA"),
}
NATIVE_EDGES = {case: row for (case, row) in EDGES.items() if row[0] == "native"}


@pytest.mark.parametrize("case", list(NATIVE_EDGES))
def test_an_m1_m2_edge_gives_its_outcome(eio, case):
    (base, edit, want) = NATIVE_EDGES[case]
    b = _load(base)
    edit(b)
    got = _outcome(_restamp(b))
    if want in ("SAME", "CONVERTS"):
        assert isinstance(got, dict), got
        assert (canonical_bytes(got) == canonical_bytes(_outcome(_load(base)))) == (want == "SAME")
    else:
        assert got == want


def test_the_canonical_form_and_render_errors_carry_their_codes():
    from eio_agents.semantics.why import render_param

    for fn, code in (
        (lambda: jb(float("nan")), "NON_FINITE"),
        (lambda: jb("\ud800"), "LONE_SURROGATE"),
        (lambda: render_param({"type": "no-such-type", "name": "x"}, 1), "TEMPLATE_PARAM_TYPE"),
    ):
        with pytest.raises(ConversionError) as e:
            fn()
        assert e.value.code == code and str(e.value).startswith(code + ": ")
