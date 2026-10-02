"""Evidence, witness and contract rules against a native producer bundle."""
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.evidence import context_refs, contract, redaction, refs, witness
from eio_agents.evidence.locate import locate
from eio_agents.validation import redaction as verifier_redaction

DATA = Path(__file__).parent / "data"
NATIVE = DATA / "native/v0_6/native.bundle.json"
CLASS_VALUES = ("Test values: card 4111 1111 1111 1111; id 123-45-6789; iban DE89370400440532013000; "
                "key AKIAIOSFODNN7EXAMPLE; last 4: 4321; mail a.b@example.com. ")


def _native():
    import eio_agents
    return eio_agents.convert(NATIVE.read_bytes())


def test_witness_recomputes_native_refs(eio):
    rec = _native()
    R = rec["evidence"]["refs"]
    assert all(r["can_prove_agent_behaviour"] == witness.can_prove(eio, r["kind"], r["source_type"]) for r in R)
    assert rec["evidence"]["counts"]["witnessing_anchored"] == sum(1 for r in R if witness.witnessing_anchored(eio, r)) > 0
    assert eio.can_prove("TOOL_RECEIPT", "AGENT_TOOL_CALL") is witness.can_prove(eio, "TOOL_RECEIPT", "AGENT_TOOL_CALL") is True


def test_contract_check_recomputes_native_claims(eio):
    rec = _native()
    R = {r["id"]: r for r in rec["evidence"]["refs"]}
    def episode(turns):
        return set(turns)
    scored = [c for c in rec["claims"] if "contract_check" in c["parameters"]]
    assert scored and {c["parameters"]["contract_check"]["status"] for c in scored} >= {"met"}
    for c in scored:
        assert contract.contract_check(eio, c, R, episode) == c["parameters"]["contract_check"], c["id"]


def test_in_scope_uses_the_injected_episode():
    claim = {"turn_indices": [3]}
    ref = {"turn_index": 4}
    assert contract.in_scope(ref, "run", claim, None) and not contract.in_scope({"turn_index": None}, "turn", claim, None)
    assert not contract.in_scope(ref, "turn", claim, None)
    assert contract.in_scope(ref, "episode", claim, lambda ts: {3, 4})
    assert not contract.in_scope(ref, "episode", claim, lambda ts: {3})


def test_redaction_agrees_with_the_independent_verifier():
    q = "Please review this harmless test string and keep its text local."
    for text in (CLASS_VALUES + q, q, "x " * 190 + CLASS_VALUES, "no sensitive values here"):
        red, n = verifier_redaction.redact_span(text)
        assert redaction.redact(text) == (red, n > 0)
        assert redaction.excerpt_of(text) == verifier_redaction.expected_excerpt(text)
    red, _ = redaction.redact(CLASS_VALUES)
    assert [m.group() for m in redaction.MARKER.finditer(red)] == [
        "[REDACTED:card]", "[REDACTED:national_id]", "[REDACTED:national_id]", "[REDACTED:secret]", "[REDACTED:last4]",
        "[REDACTED:email]"]
    assert redaction.luhn("4111111111111111") and not redaction.luhn("4111111111111112")


def test_excerpt_never_splits_a_marker():
    text = "x" * 395 + " a.b@example.com and more"
    ex, cut, red = redaction.excerpt_of(text)
    assert (ex, cut, red) == ("x" * 395 + " ", True, True)
    assert redaction.excerpt_of("short") == ("short", False, False)


def test_locate_is_exact_then_casefold_never_fuzzy():
    assert locate("Wire", "please wire $10") == (7, 11, "casefold")
    assert locate("wire", "please wire $10") == (7, 11, "exact")
    assert locate("", "abc") is None and locate("wires", "please wire") is None
    assert locate("strasse", "Straße") is None                     # casefold changes the length: no casefold match


def test_ref_store_keeps_the_first_ref_without_anchor_upgrade():
    turn = {"id": "r1", "anchor": "turn", "char_start": 0, "char_end": 9}
    exact = {"id": "r1", "anchor": "exact", "char_start": 2, "char_end": 5}
    store = refs.RefStore()
    assert store.put(dict(turn)) == store.put(dict(exact)) == "r1"
    assert store.refs == {"r1": turn}


def test_no_call_ref_is_the_native_typed_absence(eio):
    rec = _native()
    ta = [r for r in rec["evidence"]["refs"] if r["kind"] == "TYPED_ABSENCE" and r["statement"]["formula"] == "len(tool_calls[t])"]
    assert ta
    for r in ta:
        assert refs.no_call_ref(eio, r["turn_index"], [], source_ref="turns", calls_field="tool_calls") == r
    with pytest.raises(ConversionError, match="INVARIANT"):
        refs.no_call_ref(eio, 1, [{"name": "lookup"}], source_ref="transcript", calls_field="tools_called")


def test_no_call_ref_takes_its_source_from_the_caller(eio):
    """Carry note 2: the source name and the tool-call list come from the bundle's `sources` declaration, not a
    hard-coded producer layout; the id does not depend on them (it covers the statement text)."""
    a = refs.no_call_ref(eio, 3, [], source_ref="transcript", calls_field="tools_called")
    b = refs.no_call_ref(eio, 3, [], source_ref="sources/turns", calls_field="tool_calls")
    assert a["id"] == b["id"] and b["source_ref"] == "sources/turns"
    assert b["statement"] == {"inputs": {"source": "tool_calls", "turns": [3]}, "formula": "len(tool_calls[t])", "output": 0}
    with pytest.raises(TypeError):
        refs.no_call_ref(eio, 3, [])                                   # no default layout


def test_context_absence_ref(eio):
    r = context_refs.ctx_absence_ref(eio, ["b.md", "a.md"], 120, ["never"])
    assert r["source_ref"] == "context" and r["statement"]["inputs"]["files_searched"] == ["a.md", "b.md"]
    assert r["can_prove_agent_behaviour"] is witness.can_prove(eio, "TYPED_ABSENCE", "POLICY_SOURCE")
    assert context_refs.ctx_absence_ref(eio, ["a.md"], 1, ["never"])["source_ref"] == "a.md"
