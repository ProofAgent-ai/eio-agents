"""`build_bundle(...)`: an evaluation bundle (archive schema 3) from a simple evaluation report, for a native producer.

A report that records a conversation (each turn's user message, agent answer and tool calls) and a list of
deterministic checks ("on turn 3, predicate P failed; the agent said Q") is enough. From it this module computes what
a bundle must carry and `convert` recomputes: the evidence refs (an exact span of the agent answer or the user
message, a receipt per tool call, the typed absence of any tool call), the claim ids, the transcript digest, the
episodes, the score inputs (a scenario binding per claim, the applicable controls of the declared frameworks, the
context ratings and a proof citation per failed check that cites a proof-eligible ref) and the stage-record digests.

What a simple report does not record (the scope facts, the capsule, the stage layout) comes from the packaged defaults
`data/build-defaults.json`; nothing is read from the network. A bad input fails closed with a `ConversionError` whose
code is `BUILD_INPUT` (a value of the wrong form), `BUILD_PREDICATE` (an id the release does not define), `BUILD_TURN`
(a turn that does not exist), `BUILD_QUOTE` (a quote that is not in the turn), `BUILD_EVIDENCE` (a check with no
evidence its predicate can be decided on), `BUILD_JURY` (a model-graded check whose jury is missing, malformed or
contradicts its decision) or `BUILD_PERSONAL_DATA` (a value the record would withhold as identifying).
The bundle is not projected here: `eio_agents.convert` does that, and checks everything again.
"""
from __future__ import annotations

import copy
import difflib
import json
import re
from pathlib import Path
from typing import Any

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError
from eio_agents.adjudication import pool
from eio_agents.base.version import VERSION
from eio_agents.evidence.refs import no_call_ref, receipt_ref, span_ref
from eio_agents.ontology import load
from eio_agents.per.bundle import stage_digest
from eio_agents.schemas import BUNDLE_VERSION
from eio_agents.semantics.claims import make_claim
from eio_agents.semantics.proof import jury_consensus

DEFAULTS = Path(__file__).resolve().parent / "data" / "build-defaults.json"
STATES = ("APPLICABLE_PASS", "APPLICABLE_FAIL", "UNRESOLVED", "EVIDENCE_INCOMPLETE")   # NOT_APPLICABLE needs a basis
FIDELITY = ("exact", "narrower")
SEVERITIES = (None, "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")
RUN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
SUPPLIED = {"AGENT_SPAN": "give a 'quote' of turn {t}'s agent answer",
            "TOOL_RECEIPT": "record the tool call on turn {t} in its 'tools' (and keep the check's 'tools' true)"}
SHAPES = {"digits": "a number of four digits or more", "groups": "two digit groups or more (such as a date or an id)",
          "alphanumeric": "a word of six letters and digits or more", "hex": "a long hex token",
          "base64": "a base64 token", "email": "an e-mail address", "userinfo": "a URL with credentials",
          "secret": "a secret-key prefix"}


def defaults() -> dict[str, Any]:
    """The packaged defaults (a new copy on every call)."""
    return json.loads(DEFAULTS.read_text(encoding="utf-8"))


def _fail(code: str, detail: str):
    raise ConversionError(f"{code}: {detail}", code=code)


def _need(cond, code: str, detail: str) -> None:
    if not cond:
        _fail(code, detail)


def _text(v, what: str) -> str:
    _need(isinstance(v, str) and v != "", "BUILD_INPUT", f"{what} must be a non-empty string, not {v!r:.60}")
    return v


def _input_name(pointer: str, b) -> str:
    """The build_bundle input a bundle pointer comes from, in the caller's terms."""
    parts = pointer.strip("/").split("/")
    if parts[:2] == ["graph", "refs"] and len(parts) >= 4 and parts[3] == "tool":
        ref = b["graph"]["refs"][int(parts[2])]
        return f"turn {ref['turn_index']}, tool call {ref['tool']['call_index']}: 'name'"
    named = {("header", "run_id"): "run_id", ("provenance", "agent", "agent_id"): "agent['id']",
             ("provenance", "agent", "version"): "agent['version']", ("provenance", "agent", "model"): "agent['model']",
             ("provenance", "producer", "name"): "producer['name']",
             ("provenance", "producer", "version"): "producer['version']"}
    for key, name in named.items():
        if tuple(parts[:len(key)]) == key:
            return name
    if parts[:2] == ["sources", "turns"] and len(parts) >= 6 and parts[3] == "tool_calls":
        return f"turn {int(parts[2]) + 1}, tool call {parts[4]}: '{parts[5]}'"
    if parts[0] == "claims" and parts[2:] == ["provenance", "model"]:
        return f"the jury 'model' of check {int(parts[1]) + 1}"
    if parts[:2] == ["provenance", "telemetry"]:
        return "telemetry"
    if parts[:3] == ["provenance", "record", "producer"] and len(parts) == 4:
        return f"producer['{parts[3]}']"
    if parts[:2] == ["provenance", "record"]:
        return "producer or run fields"
    return pointer


def _privacy(b, eio) -> None:
    """The record's two privacy backstops (`convert` applies them too), raised with the input field they come from: a
    string the record carries in clear (an id, a name, a version, a model) never holds an identifying-shaped token, and
    never repeats a tool-call value that names a subject."""
    from eio_agents.per import bundle as B
    for problem in B.shape_problems(b, eio):
        pointer, _, shapes = problem.partition(" (")
        names = ", ".join(SHAPES.get(x, x) for x in shapes.rstrip(")").split(", "))
        _fail("BUILD_PERSONAL_DATA", f"{_input_name(pointer, b)} holds {names}. The record carries this field in "
              "clear, and a value of that shape could identify a person or an account, so `convert` refuses it "
              "(privacy rule: identifying-shaped token; a version may have at most three groups of at most two "
              "digits, and a model field accepts a model identifier such as 'gpt-4o-2024-08-06'). Use a value "
              "without it, for example 'travel-bot' rather than 'bot-12345'")
    for problem in B.bundle_content_problems(b, B.Withheld(b["sources"], eio)):
        pointer = problem.split(" ", 1)[0]
        _fail("BUILD_PERSONAL_DATA", f"{_input_name(pointer, b)} repeats a tool-call value that names a subject (two "
              "words or more, an '@' or digits). The record carries this field in clear and keeps tool-call values "
              "only as digests, so `convert` refuses it (privacy rule: withheld content). Use another value")


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.casefold()) if len(w) > 2} - {"eio", "predicate", "the", "and"}


def _same(a: str, b: str) -> bool:
    """Two words match when they are equal or share a stem of five letters ('invented', 'invent', 'invention')."""
    return a == b or (min(len(a), len(b)) >= 5 and a[:5] == b[:5])


def nearest_predicates(eio, text: str, n: int = 3) -> list[str]:
    """The predicates closest to a mistyped or partial id: ranked by the words they share with it (a word of the id
    counts three times, a word of the meaning or the tags once), then by spelling (difflib), which alone decides when
    no word matches."""
    query = _words(text)
    metrics: dict[str, set[str]] = {}
    for edge in eio.module("eio.mapping.metrics")["mappings"]:
        if edge.get("relation") == "derived-view" and edge.get("status") == "normative":
            metrics.setdefault(edge["source"], set()).update(_words(edge["target"].removeprefix("eio.metric.")))
    scored = []
    for pid, pd in eio.pred.items():
        own = _words(pid.removeprefix("eio.predicate."))
        about = (_words(str(pd.get("description") or "")) | _words(" ".join(pd.get("tags") or []))
                 | metrics.get(pid, set()))
        score = sum(3 for q in query if any(_same(q, w) for w in own))
        score += sum(1 for q in query if any(_same(q, w) for w in about))
        ratio = difflib.SequenceMatcher(None, text.removeprefix("eio.predicate."),
                                        pid.removeprefix("eio.predicate.")).ratio()
        scored.append((score, ratio, pid))
    if any(score for score, _, _ in scored):
        return [pid for score, _, pid in sorted(scored, key=lambda x: (-x[0], -x[1], x[2])) if score][:n]
    short = {pid.removeprefix("eio.predicate."): pid for pid in eio.pred}
    return [short[x] for x in difflib.get_close_matches(text.removeprefix("eio.predicate."), sorted(short), n=n,
                                                        cutoff=0.6)]


def _predicate(eio, p) -> str:
    p = _text(p, "a check's 'predicate'")
    full = p if p.startswith("eio.predicate.") else f"eio.predicate.{p}"
    if full not in eio.pred:
        near = nearest_predicates(eio, p)
        hint = (f"; did you mean {', '.join(near)}?" if near
                else "; run `eio-agents predicates --search WORD` to find one")
        _fail("BUILD_PREDICATE", f"{p!r} is not a predicate of EIO {eio.release}{hint}")
    return full


def _criterion(eio, c) -> str:
    c = _text(c, "a context_ratings key")
    full = c if c.startswith("eio.context.") else f"eio.context.{c.replace('_', '-')}"
    if full not in eio.criteria:
        near = difflib.get_close_matches(full, sorted(eio.criteria), n=3, cutoff=0.6)
        _fail("BUILD_PREDICATE", f"{c!r} is not a context criterion of EIO {eio.release}"
              + (f"; did you mean {', '.join(near)}?" if near else ""))
    return full


def _contract_kinds(pd) -> set[str]:
    ec = pd.get("evidence_contract") or {}
    return set(ec.get("require_all") or []) | set(ec.get("require_any") or []) | {
        k for g in ec.get("require_groups") or [] for k in g}


def _turns(raw, layout) -> list[dict[str, Any]]:
    _need(isinstance(raw, list) and raw, "BUILD_INPUT", "'turns' must be a non-empty list of {user, agent, tools}")
    out = []
    for i, t in enumerate(raw):
        n = i + 1
        _need(isinstance(t, dict), "BUILD_INPUT", f"turn {n} must be an object with 'user', 'agent' and 'tools'")
        tools = t.get("tools") or []
        _need(isinstance(tools, list), "BUILD_INPUT", f"turn {n}: 'tools' must be a list")
        calls = []
        for j, c in enumerate(tools):
            _need(isinstance(c, dict), "BUILD_INPUT",
                  f"turn {n}, tool call {j}: must be an object {{name, args, result}}")
            name = _text(c.get("name"), f"turn {n}, tool call {j}: 'name'")
            call = {"name": name, "arguments": c.get("args", {}),
                    "arguments_pointer": f"/sources/{layout}/{i}/tool_calls/{j}/arguments"}
            if "result" in c:                      # a call whose output the evaluator did not capture has no result
                call["result"] = c["result"]
            calls.append(call)
        # an answer may be empty only when the agent answered with tool calls alone
        answer = t.get("agent") if t.get("agent") == "" and calls else _text(t.get("agent"), f"turn {n}: 'agent'")
        out.append({"turn_index": n, "question": _text(t.get("user"), f"turn {n}: 'user'"),
                    "answer": answer, "tool_calls": calls, "retrievals": []})
    return out


def _span(eio, kind, source_type, turn, text, quote, what, layout):
    a = text.find(quote)
    if a < 0:
        windows = [text[k:k + len(quote)] for k in range(max(1, len(text) - len(quote) + 1))]
        near = difflib.get_close_matches(quote, windows, n=1, cutoff=0.6)
        _fail("BUILD_QUOTE", f"check on turn {turn}: the {what} {quote!r:.80} is not an exact substring of turn "
              f"{turn}'s {'agent answer' if kind == 'AGENT_SPAN' else 'user message'} {text!r:.120}"
              + (f"; the closest text is {near[0]!r}" if near else ""))
    return span_ref(eio, kind, source_type, turn, text, a, a + len(quote), "exact", layout)


def _ballots(chk, k: int, p: str) -> list[dict[str, Any]]:
    """A model-graded check's ballots `{persona, round, observed}`, from its `jury`: one ballot per juror (a persona)
    and round, `observed` true when the juror observed what the predicate states, false when it did not, null when it
    abstained. A tool with a single LLM judge is a jury of one."""
    jury = chk.get("jury")
    _need(isinstance(jury, list) and jury, "BUILD_JURY", f"check {k} ({p}) is model-graded: give its 'jury', a list "
          "of ballots {persona, observed} (and 'round', default 1), one per juror and round")
    out = []
    for i, v in enumerate(jury, 1):
        _need(isinstance(v, dict), "BUILD_JURY", f"check {k}, ballot {i}: must be an object {{persona, observed}}")
        persona = v.get("persona")
        _need(isinstance(persona, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", persona or ""), "BUILD_JURY",
              f"check {k}, ballot {i}: 'persona' (the juror) must be a short lower-case label such as 'strict' or "
              f"'juror-a', not {persona!r:.40}")
        rnd = v.get("round", 1)
        _need(isinstance(rnd, int) and not isinstance(rnd, bool) and rnd >= 1, "BUILD_JURY",
              f"check {k}, ballot {i}: 'round' must be a positive integer")
        _need(v.get("observed") is None or isinstance(v.get("observed"), bool), "BUILD_JURY",
              f"check {k}, ballot {i}: 'observed' must be true, false or null (an abstention)")
        _need(v.get("quote") is None or (isinstance(v.get("quote"), str) and v["quote"]), "BUILD_JURY",
              f"check {k}, ballot {i}: 'quote' (the juror's own excerpt of the agent answer) must be a non-empty string")
        out.append({"persona": persona, "round": rnd, "observed": v.get("observed")})
    return out


def _jury_located(answer: str, jury: list[dict], polarity: str, cited: dict | None) -> bool:
    """0.8.4 jury consensus: every juror that stated the failure (`observed` for a risk predicate, not `observed` for a
    safeguard) quoted the agent answer, each quote occurs exactly once in it, and all of them overlap one another and
    the check's cited agent span. Only then may the check's quote stand as the claim's proof citation."""
    if cited is None or polarity not in ("risk", "safeguard"):
        return False
    failing = [v for v in jury if v.get("observed") is (polarity == "risk")]
    if len(failing) < 2 or any(not v.get("quote") or answer.count(v["quote"]) != 1 for v in failing):
        return False
    spans = [(answer.index(v["quote"]), answer.index(v["quote"]) + len(v["quote"])) for v in failing]
    spans.append((cited["char_start"], cited["char_end"]))
    return max(a for a, _ in spans) < min(b for _, b in spans)


def _majority_state(eio, p: str, counts: dict[str, int]) -> str | None:
    """The decision a pooled majority states: for a risk predicate an observed violation is a failure, for a safeguard
    an observed safeguard is a pass; None for a tie or an observation predicate."""
    if counts["observed"] == counts["not_observed"] or eio.pred[p]["polarity"] not in ("risk", "safeguard"):
        return None
    observed = counts["observed"] > counts["not_observed"]
    failed = observed if eio.pred[p]["polarity"] == "risk" else not observed
    return "APPLICABLE_FAIL" if failed else "APPLICABLE_PASS"


def _proof_ref(eio, predicate, evidence) -> list[dict]:
    """The ref a failed check's proof citation names (none, or one): its first cited ref that can prove agent behaviour,
    of a kind in the first evidence group of the predicate's contract that can, under a witnessing anchor (the proof
    rule `semantics.proof.checked_native_citations` applies)."""
    groups = (eio.pred[predicate].get("evidence_contract") or {}).get("require_groups") or []
    first = next((set(g) for g in groups if any(eio.kind[k]["can_prove_agent_behaviour"] for k in g)), set())
    return [r for r in evidence if r["kind"] in first and r["can_prove_agent_behaviour"]
            and r["anchor"] in eio.witnessing_anchors][:1]


def build_bundle(*, run_id: str, producer: dict[str, str], agent: dict[str, str], turns: list[dict[str, Any]],
                 checks: list[dict[str, Any]], started_at: str, completed_at: str, system_prompt: str | None = None,
                 system_prompt_public: bool = False,
                 context_ratings: dict[str, int] | None = None, frameworks: list[str] | None = None,
                 telemetry: dict[str, Any] | None = None, scope_facts: dict[str, Any] | None = None,
                 assessor_id: str | None = None, plan_hash: str | None = None, seed: int | None = None,
                 jury_model: str | None = None, ontology=None) -> dict[str, Any]:
    """An evaluation bundle (bundle format 3.0.0, archive schema 3) of a native producer, ready for `eio_agents.convert`.

    - `run_id`: the run's id, a lower-case UUID version 4; `producer`: `{name, version}` of the evaluator; `agent`:
      `{id, version, model}` of the agent under test; `started_at`, `completed_at`: RFC 3339 UTC (`...Z`).
    - `turns`: `[{user, agent, tools: [{name, args, result}]}]`, turn 1 first; `agent` may be empty only for a turn
      answered with tool calls alone, and a tool call without `result` is recorded as not captured.
    - `checks`: `[{turn, predicate, passed}]`, one decision each, deterministic by default. `predicate` is an EIO
      predicate id (the `eio.predicate.` prefix may be left out); `passed` is a bool, or give `state` (an EIO claim
      state) instead. Optional: `quote`, an exact substring of the agent answer (cited, and the proof of a failure);
      `user_quote`, an exact substring of the user message or `true` for all of it; `tools` (default true), whether the
      turn's tool calls are cited; `fidelity`, `exact` (default) or `narrower`; `severity` of its scenario (default `HIGH`).
      A model-graded check says `decided_by: "semantic"` and gives its `jury`, the ballots `[{persona, observed,
      round}]` of its jurors, and the jury's `model` (or `jury_model` for every check); its decision may be left out
      when the jury has a majority.
    - `system_prompt`: the agent's instructions, embedded in the source bundle as a model-confidential context artifact
      by default. Set `system_prompt_public=True` only when its text is approved for publication in PER excerpts.
      `context_ratings`: `{criterion: 0..100}`, an `eio.context.*` id or its short name (`role-clarity`).
    - `frameworks`: the frameworks in scope (default: OWASP agentic threats and AIUC-1); their controls that target
      a checked predicate are the applicable controls.
    - `telemetry`: the `provenance.telemetry` object (default: every value null, cost UNAVAILABLE); `scope_facts`:
      `{fact: value}` over the packaged defaults; `assessor_id`: who rated the context (default: the producer name);
      `plan_hash`, `seed`: the run plan's digest and seed, when the evaluator records them.
    """
    eio = ontology if ontology is not None else load()
    d = defaults()
    layout = d["turn_source_ref"]
    run_id = _text(run_id, "'run_id'")
    _need(RUN_ID.fullmatch(run_id), "BUILD_INPUT", f"'run_id' must be a lower-case UUID version 4 (for example "
          f"str(uuid.uuid4())), not {run_id!r:.60}")
    _need(isinstance(producer, dict), "BUILD_INPUT", "'producer' must be {name, version}")
    _need(isinstance(agent, dict), "BUILD_INPUT", "'agent' must be {id, version, model}")
    prod = {"name": _text(producer.get("name"), "producer 'name'"),
            "version": _text(producer.get("version"), "producer 'version'")}
    who = {"agent_id": _text(agent.get("id"), "agent 'id'"), "version": _text(agent.get("version"), "agent 'version'"),
           "model": _text(agent.get("model"), "agent 'model'")}
    for name, v in (("started_at", started_at), ("completed_at", completed_at)):
        _need(isinstance(v, str) and TIMESTAMP.fullmatch(v), "BUILD_INPUT",
              f"'{name}' must be an RFC 3339 UTC timestamp such as 2026-10-01T14:00:00Z, not {v!r:.40}")
    _need(seed is None or (isinstance(seed, int) and not isinstance(seed, bool)), "BUILD_INPUT",
          "'seed' must be an integer")
    obs = _turns(turns, layout)
    n = len(obs)
    if plan_hash is None:
        plan_hash = H(jb({"producer": prod["name"], "run_id": run_id, "turns": list(range(1, n + 1))}))
    _need(isinstance(plan_hash, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", plan_hash), "BUILD_INPUT",
          "'plan_hash' must be 'sha256:' and 64 lower-case hex digits")

    # The source bundle retains the text; PER excerpts depend on its declared data class.
    _need(type(system_prompt_public) is bool, "BUILD_INPUT", "'system_prompt_public' must be true or false")
    _need(not system_prompt_public or system_prompt is not None, "BUILD_INPUT",
          "'system_prompt_public' requires 'system_prompt'")
    artifacts, texts = [], {}
    if system_prompt is not None:
        text = _text(system_prompt, "'system_prompt'")
        artifacts = [{"artifact_kind": "eio.artifact.system-prompt", "name": d["system_prompt_name"],
                      "sha256": H(text), "code_points": len(text), "embedded": True,
                      "data_class": "eio.data.public" if system_prompt_public else "eio.data.model-confidential"}]
        texts = {d["system_prompt_name"]: text}

    # evidence refs and claims: one deterministic claim per check
    _need(isinstance(checks, list) and checks, "BUILD_INPUT",
          "'checks' must be a non-empty list of {turn, predicate, passed}")
    refs: dict[str, dict] = {}
    decided = []
    jury_proved: set[str] = set()   # 0.8.4: semantic claims whose jury consensus cites a located quote
    pooled: list[dict[str, Any]] = []
    for k, chk in enumerate(checks, 1):
        _need(isinstance(chk, dict), "BUILD_INPUT", f"check {k}: must be an object {{turn, predicate, passed}}")
        t = chk.get("turn")
        _need(isinstance(t, int) and not isinstance(t, bool), "BUILD_TURN",
              f"check {k}: 'turn' must be a turn number")
        _need(1 <= t <= n, "BUILD_TURN",
              f"check {k}: turn {t} does not exist; the report has turns 1 to {n} (turn 1 is the first)")
        p = _predicate(eio, chk.get("predicate"))
        decided_by = chk.get("decided_by", "deterministic")
        _need(decided_by in ("deterministic", "semantic"), "BUILD_INPUT",
              f"check {k}: 'decided_by' must be deterministic or semantic. A human decision must cite a human "
              "sign-off (a HUMAN_SIGNOFF ref over a HUMAN_REVIEW source) that a report's turns cannot carry; "
              "build that bundle by hand" if decided_by == "human" else
              f"check {k}: 'decided_by' must be deterministic or semantic, not {decided_by!r:.30}")
        ballots, counts, model = [], None, None
        if decided_by == "semantic":
            ballots = _ballots(chk, k, p)
            counts = pool(ballots)
            _need(counts["distinct_pairs"], "BUILD_JURY", f"check {k} ({p}): every juror abstains; a model-graded "
                  "decision needs at least one juror that observed or did not observe")
            model = _text(chk.get("model", jury_model), f"check {k}: the jury 'model' (or jury_model)")
            if "state" not in chk and "passed" not in chk:
                majority = _majority_state(eio, p, counts)
                _need(majority, "BUILD_JURY", f"check {k} ({p}): the jury is tied ({counts['observed']} observed, "
                      f"{counts['not_observed']} not observed); give 'passed' to state the decision")
                chk = dict(chk, state=majority)
        else:
            _need("jury" not in chk, "BUILD_JURY", f"check {k}: a 'jury' is for a model-graded check; add "
                  "decided_by: semantic")
        if "state" in chk:
            state = chk["state"]
            _need(state in STATES, "BUILD_INPUT", f"check {k}: 'state' must be one of {', '.join(STATES)}")
        else:
            _need(isinstance(chk.get("passed"), bool), "BUILD_INPUT", f"check {k} ({p}, turn {t}): 'passed' must be "
                  "true or false (or give 'state')")
            state = "APPLICABLE_PASS" if chk["passed"] else "APPLICABLE_FAIL"
        if counts is not None:
            majority = _majority_state(eio, p, counts)
            _need(majority in (None, state) or state not in ("APPLICABLE_PASS", "APPLICABLE_FAIL"), "BUILD_JURY",
                  f"check {k} ({p}, turn {t}) is {state}, but its jury says {majority} ({counts['observed']} jurors "
                  f"observed, {counts['not_observed']} did not, for a {eio.pred[p]['polarity']} predicate); "
                  "'observed' means the juror saw what the predicate states")
        fidelity = chk.get("fidelity", "exact")
        _need(fidelity in FIDELITY, "BUILD_INPUT", f"check {k}: 'fidelity' must be exact or narrower")
        _need(chk.get("severity", d["severity"]) in SEVERITIES, "BUILD_INPUT",
              f"check {k}: 'severity' must be one of {', '.join(str(x) for x in SEVERITIES[1:])} or null")
        turn = obs[t - 1]
        kinds = _contract_kinds(eio.pred[p])
        evidence = []
        if chk.get("quote") is not None:
            evidence.append(_span(eio, "AGENT_SPAN", "AGENT_ANSWER", t, turn["answer"], _text(chk["quote"], "'quote'"),
                                  "quote", layout))
        if chk.get("tools", True):
            seen: dict[tuple, int] = {}
            for j, c in enumerate(turn["tool_calls"]):
                key = (c["name"], H(jb(c["arguments"])))
                seen[key] = seen.get(key, 0) + 1
                evidence.append(receipt_ref(eio, t, j, c["name"], c["arguments"], seen[key], "result" in c,
                                            c.get("result"), c["arguments_pointer"], layout))
            if not turn["tool_calls"] and "TOOL_RECEIPT" in kinds:
                evidence.append(no_call_ref(eio, t, [], source_ref=layout, calls_field=d["calls_field"]))
        uq = chk.get("user_quote")
        if uq is True:
            uq = turn["question"]
        if uq:
            evidence.append(_span(eio, "USER_INPUT", "USER_INPUT", t, turn["question"], _text(uq, "'user_quote'"),
                                  "user_quote", layout))
        if state in ("APPLICABLE_PASS", "APPLICABLE_FAIL"):
            _need(evidence, "BUILD_EVIDENCE", f"check {k} ({p}, turn {t}) cites no evidence: give a 'quote' from the "
                  f"agent answer{' or record the tool calls' if 'TOOL_RECEIPT' in kinds else ''} (its evidence "
                  f"contract names {', '.join(sorted(kinds)) or 'no kind'})")
        # 0.8.3: a failure of a predicate whose evidence contract has no group that can prove agent behaviour is
        # accepted: `convert` records it as an UNPROVEN, unreportable finding (0.8.2 refused the bundle).
        if state == "APPLICABLE_FAIL":
            _need(any(r["can_prove_agent_behaviour"] for r in evidence), "BUILD_EVIDENCE",
                  f"check {k} ({p}, turn {t}) failed but cites nothing the agent did: give a 'quote' of the agent "
                  "answer (a user message cannot show what the agent did)")
            # a failure needs each evidence group of its contract that only a report can supply (an agent span or a
            # receipt): without it the failure did not happen (a forbidden tool call with no call). A group that other
            # evidence (a policy text, a retrieval) could meet is left to `convert`, which records the claim UNPROVEN.
            for group in (eio.pred[p].get("evidence_contract") or {}).get("require_groups") or []:
                need = [x for x in group if x in SUPPLIED]
                met = any(r["kind"] in group and r["can_prove_agent_behaviour"] for r in evidence)
                if need and set(group) <= set(SUPPLIED) and not met:
                    _fail("BUILD_EVIDENCE", f"check {k} ({p}, turn {t}) failed, but its evidence contract needs one "
                          f"of {', '.join(group)} and the check cites none: {SUPPLIED[need[0]].format(t=t)}")
        for r in evidence:
            refs.setdefault(r["id"], r)
        claim = make_claim(eio, run_id=run_id, predicate=p, turn_indices=[t], state=state,
                           parameters={"fidelity": fidelity, "votes": counts}, evidence=[r["id"] for r in evidence],
                           decided_by=decided_by, resolver=None, plan_hash=plan_hash, model=model, seed=seed)
        if decided_by == "semantic" and state == "APPLICABLE_FAIL" and jury_consensus(claim, eio.pred[p]["polarity"]):
            cited = next((r for r in evidence if r["kind"] == "AGENT_SPAN" and r.get("source_type") == "AGENT_ANSWER"),
                         None)
            if _jury_located(turn["answer"], chk["jury"], eio.pred[p]["polarity"], cited):
                jury_proved.add(claim["id"])
        decided.append((claim, evidence, chk))
        pooled.extend({"claim_id": claim["id"], **x} for x in ballots)
    ids = [c["id"] for c, _, _ in decided]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    _need(not dup, "BUILD_INPUT", "two checks name the same predicate on the same turn (claim "
          f"{', '.join(dup)}); keep one decision per predicate and turn")

    # scope: the packaged facts, with the ones a report determines derived from it
    facts = dict(d["facts"])
    facts["tools"] = any(t["tool_calls"] for t in obs)
    facts["multi_turn"] = n > 1
    for key, v in (scope_facts or {}).items():
        _need(key in facts, "BUILD_INPUT", f"scope fact {key!r} is not one of {', '.join(sorted(facts))}")
        _need(v is None or isinstance(v, bool), "BUILD_INPUT", f"scope fact {key!r} must be true, false or null")
        facts[key] = v
    frameworks = list(d["frameworks"] if frameworks is None else frameworks)
    for f in frameworks:
        _need(f in eio.frameworks, "BUILD_PREDICATE", f"{f!r} is not a framework of EIO {eio.release}"
              + (f"; did you mean {', '.join(m)}?" if (m := difflib.get_close_matches(str(f), sorted(eio.frameworks),
                                                                                         n=3, cutoff=0.6)) else ""))
    predicates = {c["predicate"] for c, _, _ in decided}
    ratings = []
    for crit, value in (context_ratings or {}).items():
        _need(artifacts, "BUILD_INPUT", "context_ratings rate the system prompt: give 'system_prompt' too")
        _need(isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100, "BUILD_INPUT",
              f"context rating {crit!r} must be an integer from 0 to 100")
        ratings.append({"criterion_id": _criterion(eio, crit), "artifact_name": artifacts[0]["name"],
                        "artifact_sha256": artifacts[0]["sha256"], "assessor_id": assessor_id or prod["name"],
                        "rating": value})
    if telemetry is None:
        telemetry = {"agent_under_test": {"llm_calls": None, "tokens": None, "latency_ms": None, "error_rate": None,
                                          "cost_usd": None, "cost_provenance": "UNAVAILABLE"},
                     "wall_clock_seconds": None}
    _need(isinstance(telemetry, dict), "BUILD_INPUT", "'telemetry' must be an object")

    b = {
        "archive_schema": 3, "bundle_version": BUNDLE_VERSION,
        "header": {"run_id": run_id, "run_id_source": "producer",
                   "eio_agents": {"version": VERSION, "ontology_sha256": eio.ontology_sha256},
                   "eio": {"release": eio.release, "ontology_digest": eio.ontology_digest,
                           "ontology_sha256": eio.ontology_sha256},
                   "adapter": None, "crosswalk": None, "source_archive": None, "producer_eio": None,
                   "plan_hash": plan_hash, "seed": seed},
        "provenance": {
            "producer": {**prod, "kind": "native", "revision": None},
            "record": {"run": {"run_id": run_id, "run_id_source": "producer", "started_at": started_at,
                               "completed_at": completed_at, "seed": seed,
                               "turns": {"executed": n, "selected": n, "recommended": None}, "plan_hash": plan_hash,
                               "transcript_source": d["transcript_source"]},
                       "producer": dict(prod),
                       "inputs": {"governance_profile": None, "context_artifacts": copy.deepcopy(artifacts)}},
            "capsule": d["capsule"],
            "agent": who,
            "telemetry": copy.deepcopy(telemetry)},
        "sources": {"turn_source_ref": layout, "calls_field": d["calls_field"], "transcript_sha256": H(jb(obs)),
                    "archive_pointer": {layout: f"/sources/{layout}"}, "turns": obs, "context_artifacts": artifacts,
                    "context_texts": texts,
                    "completeness": dict(d["completeness"], tool_outputs="CAPTURED" if all(
                        "result" in c for t in obs for c in t["tool_calls"]) else "NOT_CAPTURED")},
        "scope": {"domain_candidates": [], "domain_tokens": [], "tier": None, "tier_source": None, "autonomy": None,
                  "region": None,
                  "facts": {k: {"value": facts[k], "source": d["fact_source"]} for k in sorted(facts)},
                  "frameworks": {"rule": "selection",
                                 "candidates": [{"id": f, "basis": d["framework_basis"]} for f in frameworks],
                                 "personal_data": d["personal_data"]},
                  "policy": d["policy"]},
        "context_assessment": None,
        "graph": {"refs": list(refs.values()), "episodes": [[t["turn_index"]] for t in obs]},
        "claims": [c for c, _, _ in decided],
        "ballots": {"pooled_claims": [c["id"] for c, _, _ in decided if c["decided_by"] == "semantic"],
                    "ballots": pooled},
        "trials": None,
        "limitations": [],
        "native_scoring": {
            "scenario_bindings": [{"binding_id": f"s{k}", "turn_indices": c["turn_indices"],
                                   "severity": chk.get("severity", d["severity"])}
                                  for k, (c, _, chk) in enumerate(decided)],
            "claim_bindings": [{"claim_id": c["id"], "binding_id": f"s{k}"} for k, (c, _, _) in enumerate(decided)],
            "applicable_controls": [{"framework": f, "control_id": cid} for f in frameworks
                                    for cid in eio.frameworks[f]["controls"]
                                    if predicates & set(eio.controls[cid]["predicate_targets"])],
            "context_ratings": ratings,
            "proof_citations": [{"claim_id": c["id"], "ref_id": r["id"], "role": "proof",
                                 "citation_anchor": r["anchor"], "locator_sha256": H(jb(r))}
                                for c, ev, _ in decided
                                if c["state"] == "APPLICABLE_FAIL"
                                and (c["decided_by"] == "deterministic" or c["id"] in jury_proved)
                                for r in _proof_ref(eio, c["predicate"], ev)]},
    }
    b["stage_records"] = [{"stage": s, "producer": "native", "sections": secs,
                           "output_sha256": stage_digest(b, secs)} for s, secs in d["stages"]]
    _privacy(b, eio)
    return b
