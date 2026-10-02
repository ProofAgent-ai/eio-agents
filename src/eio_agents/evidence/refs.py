"""Evidence refs (03 §7.5; 04 §5.4-§5.5): the ref store and the ref constructors.

Ref ids are content-addressed (`semantics.ids.ref_id`), so two citations of one text share one id. The store keeps the
first ref stored under an id and never merges a later citation's anchor into it.

The constructors take the source they point into as parameters (`source_ref`, the name of the tool-call list, the
argument pointer): a producer's source layout is declared by the bundle `sources` section and passed in by the caller,
never assumed here (split plan §3.10 row 3).
"""
import re

from eio_agents.base.canon import H, jb, jcs
from eio_agents.base.errors import require
from eio_agents.evidence.redaction import excerpt_of
from eio_agents.evidence.witness import can_prove
from eio_agents.semantics import ids


# A named-call term: lower case (the formula lower-cases the call name, not the term: review R-5) and ASCII, with no
# quote, space or look-alike letter, so the statement text reads as what it counts (L2 exit D-35, F-8)
CALL_TERM = re.compile(r"[a-z0-9_.:-]+")
# The anchors that quote text: a quote of nothing holds in every text, so it is never built (L2 exit D-35, F-10)
QUOTE_ANCHORS = ("exact", "casefold")


class RefStore:
    """The refs of one record by id, in insertion order."""

    def __init__(self, refs=None):
        self.refs = {}
        for r in refs or []:
            require(r["id"] not in self.refs, "BUNDLE_RECOMPUTE", f"duplicate ref id {r['id']}")
            self.refs[r["id"]] = r

    def put(self, r):
        """Store `r` unless a ref with its id is stored already; returns the id."""
        rid = r["id"]
        if rid not in self.refs:
            self.refs[rid] = r
        return rid


def span_ref(eio, kind, source_type, turn_index, source_text, a, b, anchor, source_ref):
    """A span ref over `source_text[a:b]` (`source_text` is the whole source string, hashed into `source_sha256`). An exact
    or casefold span quotes at least one character (`QUOTE_ANCHORS`)."""
    require(a < b or anchor not in QUOTE_ANCHORS, "INVARIANT", f"an {anchor} span [{a}, {b}) quotes nothing")
    x = source_text[a:b]
    rid = ids.ref_id(kind, source_type, turn_index, x, a, b)
    ex, cut, red = excerpt_of(x)
    r = {"id": rid, "kind": kind, "source_type": source_type, "can_prove_agent_behaviour": can_prove(eio, kind, source_type),
         "anchor": anchor, "turn_index": turn_index, "char_start": a, "char_end": b, "span_sha256": H(x), "excerpt": ex}
    if cut:
        r["excerpt_truncated"] = True
    if red:
        r["excerpt_redacted"] = True
    r.update({"source_ref": source_ref, "source_sha256": H(source_text)})
    return r


def receipt_ref(eio, turn_index, call_index, name, arguments, occurrence, output_captured, output, arguments_pointer,
                source_ref):
    """The TOOL_RECEIPT of one tool call. `occurrence` is k for the k-th call of the turn with the same (name,
    arguments_sha256) (03 §6 collision rule: k > 1 appends "|k"); `arguments_pointer` locates the raw arguments."""
    ah = H(jb(arguments))
    x = name + "|" + ah + ("" if occurrence == 1 else "|" + str(occurrence))
    rid = ids.ref_id("TOOL_RECEIPT", "AGENT_TOOL_CALL", turn_index, x)
    return {"id": rid, "kind": "TOOL_RECEIPT", "source_type": "AGENT_TOOL_CALL",
            "can_prove_agent_behaviour": can_prove(eio, "TOOL_RECEIPT", "AGENT_TOOL_CALL"),
            "anchor": "receipt", "turn_index": turn_index, "char_start": None, "char_end": None, "span_sha256": None,
            "source_ref": source_ref, "source_sha256": None,
            "tool": {"name": name, "call_index": call_index, "arguments_sha256": ah, "arguments_pointer": arguments_pointer,
                     "output": {"sha256": H(jb(output))} if output_captured else "NOT_CAPTURED"}}


def computed_ref(eio, kind, source_type, turn_index, statement_text, statement, source_ref, valid_from=None, valid_until=None,
                 temporal=False):
    """A computed ref (TYPED_ABSENCE, STATE_FACT, …): its id covers the statement text; `statement` is the
    `{inputs, formula, output}` object. With `temporal`, the ref carries `valid_from`/`valid_until`."""
    rid = ids.ref_id(kind, source_type, turn_index, statement_text, valid_from=valid_from, valid_until=valid_until)
    r = {"id": rid, "kind": kind, "source_type": source_type, "can_prove_agent_behaviour": can_prove(eio, kind, source_type),
         "anchor": "computed", "turn_index": turn_index, "char_start": None, "char_end": None, "span_sha256": None,
         "source_ref": source_ref, "source_sha256": None}
    if temporal:
        r.update({"valid_from": valid_from, "valid_until": valid_until})
    r["statement"] = statement
    return r


def no_call_ref(eio, t, calls, *, source_ref, calls_field):
    """TA(t): the typed absence of any tool call on turn t. `calls` are the tool calls recorded on that turn;
    `source_ref` and `calls_field` name the source and its tool-call list, as the bundle `sources` section declares
    them (carry note 2: no producer layout is assumed here)."""
    require(not calls, "INVARIANT", "TA(t) on a turn with calls")
    x = f"no tool call on turn {t}"
    return computed_ref(eio, "TYPED_ABSENCE", "AGENT_TOOL_CALL", t, x,
                        {"inputs": {"source": calls_field, "turns": [t]}, "formula": f"len({calls_field}[t])", "output": 0},
                        source_ref)


def no_matching_call_ref(eio, t, episode_turns, name_contains, calls, *, source_ref, calls_field):
    """The typed absence, over the listed turns of an episode, of any tool call whose lower-cased name contains one of
    `name_contains`; the ref sits on turn t, one of the listed turns. `calls` are the tool calls recorded on the listed
    turns; `source_ref` and `calls_field` name the source and its tool-call list, as the bundle `sources` section declares
    them. When a producer emits this absence is its own rule; the ref is built here. The formula lower-cases the call name
    and not the terms, so each term is a lower-case ASCII name (`CALL_TERM`: an upper-case term would never match, review
    R-5; a quote or a look-alike letter would make the statement read as another one, L2 exit D-35)."""
    episode_turns, name_contains = list(episode_turns), list(name_contains)
    require(t in episode_turns, "INVARIANT", f"an absence on turn {t} over turns {episode_turns}")
    require(name_contains and all(isinstance(q, str) and CALL_TERM.fullmatch(q) for q in name_contains), "INVARIANT",
            f"name_contains {name_contains!r} is not a list of lower-case ASCII names ({CALL_TERM.pattern})")
    require(not any(q in c["name"].lower() for c in calls for q in name_contains), "INVARIANT", "EA(t) over a matching call")
    x = "no tool call whose name contains " + " or ".join(f"'{q}'" for q in name_contains) + " in episode turns " + jcs(episode_turns)
    return computed_ref(eio, "TYPED_ABSENCE", "AGENT_TOOL_CALL", t, x,
                        {"inputs": {"source": calls_field, "episode_turns": episode_turns, "name_contains": name_contains},
                         "formula": f"count(call for t in episode_turns for call in {calls_field}[t] "
                                    "if any(p in call.name.lower() for p in name_contains))",
                         "output": 0}, source_ref)


def state_fact_ref(eio, t, snapshot, *, source_ref, state_field):
    """A STATE_FACT over the state ledger: the state snapshot recorded for turn t is non-empty (the evidence of a
    persisted-state recipe, 04 §5.4.2 R-PERSIST). `snapshot` is the turn's snapshot (any JSON value) and `state_field` the
    name the bundle's `sources` section declares for it (L2 exit D-34: the projector rebuilds the ref from it). Anchor
    computed, valid from turn t; the id covers the snapshot's JCS text, and the statement carries the snapshot only as its
    digest (subjects only as digests, 03 §13.1)."""
    require(bool(snapshot), "INVARIANT", f"a state fact over the empty state snapshot of turn {t}")
    return computed_ref(eio, "STATE_FACT", "STATE_LEDGER", t, jcs(snapshot),
                        {"inputs": {"source": state_field, "turns": [t], "snapshot_sha256": H(jb(snapshot))},
                         "formula": f"{state_field}[t] is non-empty", "output": 1}, source_ref, valid_from=t, temporal=True)
