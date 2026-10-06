"""`verify(rec, bundle, rederived=...)`: VER-1/3/4 on the record plus VER-5 against its evaluation bundle (split plan §4.2,
§3.5 `c_archive` "new N").

VER-5 here is the independent re-derivation over the bundle's own `sources`, per locator kind (`c_sources`): the archive
identity and run, the declared transcript digest and archive pointer (the verifier twin of carry note 2: the pointer is
compared with the declared `sources.archive_pointer`, never assumed), the names the sources are resolved by (each turn
index and artifact name once; the context texts are the embedded artifacts'), each turn's digests, and every ref the
sources determine:
- a span into a turn (AGENT_ANSWER, USER_INPUT) at the declared `sources.turn_source_ref`, whenever the ref locates text:
  offsets, digests, id, excerpt (the verifier's own PROD-42 redaction), and anchor `turn` citing the whole turn;
- a tool receipt over the tool-call list: the call, its argument digest and pointer, the `|k` collision rule, the output
  digest;
- a typed absence over tool calls (one turn, or listed turns that include the ref's turn, by lower-case ASCII names)
  and over context artifacts (every embedded file it names): statement, formula, output (0: an absence), id;
- a POLICY_SPAN, which must point into a declared, embedded context artifact: offsets, digests, id, excerpt (PROD-43 for
  model-confidential text, read fail-closed for every data class but public and internal, and as the most restrictive
  declaration of the artifact's content: L2 exit D-32, D-35);
- a STATE_FACT over the state snapshot the bundle declares for its turn: statement (the snapshot's digest), id, validity
  (L2 exit D-34).
Any other ref has its text in no source of the bundle (a juror citation, an unlocated question, a state fact without a
declared snapshot, a human sign-off, a calculation, an absence over a source the bundle does not carry): it passes only as
a non-witnessing ref that locates nothing (no offsets, digests or excerpt) and carries no statement, the rule `convert`
applies (review R-1, L2 exit D-31); a text-less turn ref must still name the declared turn source. The context artifacts'
data classes and kinds are the release's (L2 exit D-29). An exact or casefold span quotes at least one character, a
context search's terms are plain text and its names do not spell an embedded artifact's name another way (L2 exit D-35:
F-10, F-13). Every record claim must be a bundle claim with the same decision.

L3 fix round 1, the verifier's own reading of the same rules: every producer-chosen text of the record is the bundle's or
the release's (issue 1): the layout names are identifiers and the pointers hold identifier and index tokens; a ref with
its text in no source names a declared source and carries no tool receipt; a context search of a native producer names
declared artifacts with release checklist terms (of the gap's control), an adapter producer's may also name a portable
file and search a printable ASCII phrase; a named-call term is at most 64 characters; a term that is not a release term
(nor part of a declared tool name or tool schema) and an undeclared name reproduce neither a withheld artifact's text nor
a tool-call or state value (`validate.Content`); scenario labels and context links are labels and links. The record's
provenance.inputs.context_artifacts are the bundle's sources.context_artifacts (issue 2). The withheld set holds the same
normalized text too (issue 3), and a context search reads the casefold with the dot above an i dropped (issue 7).

The re-projection itself is the projector's (`eio_agents.per.project`): the verifier never runs it (contract P3), so the
caller passes the re-projected record as `rederived`; `eio_agents.verify` does this in process.
"""
import re
import unicodedata
from collections import Counter

from eio_agents.validation.canon import jb, jcs, sd, sha
from eio_agents.validation.native_score import native_proof_status_gate, native_score_gate
from eio_agents.validation.privacy import bundle_problems
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.redaction import EXCERPT_LIMIT, expected_excerpt
from eio_agents.validation.validate import (DATA_CLASS_ID, Content, bundle_content_problems, bundle_of, check_one, content_problems,
                                             declared_item_problems, layout_problems, record_content_problems, rows_as_problems,
                                             shape_problems)

TURN_FIELD = {"AGENT_ANSWER": "answer", "USER_INPUT": "question"}
MODEL_CONFIDENTIAL = "eio.data.model-confidential"
LOCATORS = ("char_start", "char_end", "span_sha256", "source_sha256")
EXCERPT_FIELDS = ("excerpt", "excerpt_truncated", "excerpt_redacted")
NAMED_CALL_FORMULA = "count(call for t in episode_turns for call in {cf}[t] if any(p in call.name.lower() for p in name_contains))"
CONTEXT_FORMULA = "count(term in casefold(file) for file in files_searched for term in requires_any)"
CALL_TERM = re.compile(r"[a-z0-9_.:-]+")            # a named-call term: a lower-case ASCII name (review R-5, L2 exit D-35)
QUOTE_ANCHORS = ("exact", "casefold")                # anchors that quote text: never empty (L2 exit D-35, F-10)
# L3 fix round 1, issue 1: what a producer may write into the record's search inputs
SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")   # a segment of a portable relative file name
PHRASE = re.compile(r"[\x20-\x7e]*[A-Za-z0-9][\x20-\x7e]*")   # an adapter producer's checklist phrase: printable ASCII
TERM_MAX, NAME_MAX = 64, 255


def _fold(text):
    """The casefold a context search reads, with the dot above an i dropped ('İ' folds to 'i' + U+0307; issue 7)."""
    out = []
    for ch in text:
        for f in ch.casefold():
            if not (f == "\u0307" and out and out[-1] == "i"):
                out.append(f)
    return "".join(out)


class _Rules:
    """The verifier's reading of what a producer may write into a record's search inputs (L3 fix round 1, issue 1; round 2:
    an undeclared name is exempt from the artifact-text rule only when it is a declared artifact's file name itself, and a
    tool schema exempts a named-call term only when its class is public or internal as PROD-43 reads it)."""

    def __init__(self, e, B, content):
        src = B["sources"]
        self.adapter = B["provenance"]["producer"]["kind"] == "adapter"
        self.declared = {a["name"] for a in src["context_artifacts"]}
        self.files = {n.split("/")[-1] for n in self.declared}
        self.public = {q for c in e.criteria.values() for x in c.get("controls") or [] for q in x["requires_any"]}
        self.content = content
        self.tools = [c["name"].lower() for t in src["turns"] for c in t["tool_calls"]]
        self.tools += [src["context_texts"][a["name"]].lower() for a in src["context_artifacts"]
                       if a.get("artifact_kind") == "eio.artifact.tool-schema" and a["name"] in src["context_texts"]
                       and a["name"] not in content.withheld]

    def term(self, q, allowed):
        if q in allowed or (self.adapter and q in self.public):
            return None
        if not self.adapter:
            return "is not a release checklist term of the search (a native producer)"
        if len(q) > TERM_MAX or not PHRASE.fullmatch(q):
            return "is not a checklist phrase (printable ASCII, at most 64 characters)"
        return self.content.reproduced(q)

    def name(self, f):
        if f in self.declared:
            return None
        if not self.adapter:
            return "is not a declared context artifact (a native producer)"
        if len(f) > NAME_MAX or not all(SEGMENT.fullmatch(x) and not x.endswith(".") for x in f.split("/")):
            return "is not a portable relative file name"
        return self.content.reproduced(f, artifacts=f not in self.files)

    def call_term(self, q):
        if len(q) > TERM_MAX:
            return "is longer than 64 characters"
        if q in self.public or any(q in x for x in self.tools):
            return None
        return self.content.reproduced(q)


def _plain(q):
    """A search term in NFC with no format, control or private-use character (L2 exit D-35, F-13)."""
    return unicodedata.normalize("NFC", q) == q and not any(unicodedata.category(ch) in ("Cf", "Cc", "Co") for ch in q)


def _spelt(name):
    return unicodedata.normalize("NFC", name).casefold().strip()


def _rid(kind, source_type, t, x, a=None, b=None, vf=None, vu=None):
    return sd({"k": kind, "s": source_type, "t": t, "x": x, "a": a, "b": b, "vf": vf, "vu": vu})


def _excerpt_problems(r, x):
    p = []
    ex, cut, red = expected_excerpt(x)
    if r.get("excerpt") != ex:
        p.append(f"ref {r['id']}: excerpt does not recompute from the source span (PROD-42: redacted, then at most "
                 f"{EXCERPT_LIMIT} code points without cutting a marker)")
    if bool(r.get("excerpt_truncated")) != cut:
        p.append(f"ref {r['id']}: excerpt_truncated is {bool(r.get('excerpt_truncated'))}, recomputed {cut} (PROD-42)")
    if bool(r.get("excerpt_redacted")) != red:
        p.append(f"ref {r['id']}: excerpt_redacted is {bool(r.get('excerpt_redacted'))}, recomputed {red} (PROD-42)")
    return p


def _names_problems(src):
    """The names the sources are resolved by name one item each (review R-2)."""
    p = []
    for what, names in (("turn_index", [t["turn_index"] for t in src["turns"]]),
                        ("context-artifact name", [a["name"] for a in src["context_artifacts"]])):
        twice = sorted(x for x, k in Counter(names).items() if k > 1)
        if twice:
            p.append(f"sources: the {what}(s) {twice} are given twice (a name resolves one item)")
    emb = sorted(a["name"] for a in src["context_artifacts"] if a.get("embedded", True))
    if sorted(src["context_texts"]) != emb:
        p.append(f"sources.context_texts {sorted(src['context_texts'])} are not the texts of the embedded context artifacts {emb}")
    return p


def _context_absence_problems(r, texts, emb, rules):
    """A context absence recomputes over every embedded file it names (review H-1, R-4), and its terms and names are the
    release's or the bundle's (`_Rules`; L3 fix round 1, issue 1)."""
    p, rid = [], r["id"]
    s = r["statement"]
    ins = s["inputs"]
    files, chars, terms = ins.get("files_searched"), ins.get("chars_searched"), ins.get("requires_any")
    if not (isinstance(files, list) and files and all(isinstance(f, str) for f in files) and isinstance(terms, list) and terms
            and all(isinstance(q, str) and q for q in terms) and type(chars) is int and chars >= 0):
        return [f"ref {rid}: a context absence needs files_searched, a count chars_searched and non-empty terms"]
    if not all(_plain(q) for q in terms):
        p.append(f"ref {rid}: a context-search term holds an invisible or non-NFC character (L2 exit D-35, F-13)")
    spelt = {_spelt(f) for f in emb}
    if any(f not in emb and _spelt(f) in spelt for f in files):
        p.append(f"ref {rid}: a searched name spells an embedded artifact's name another way, so its text was not searched "
                 "(L2 exit D-35, F-13)")
    for q in terms:
        if (why := rules.term(q, rules.public)) is not None:
            p.append(f"ref {rid}: the context-search term {q!r:.80} {why} (L3 fix round 1, issue 1)")
    for f in files:
        if (why := rules.name(f)) is not None:
            p.append(f"ref {rid}: the searched name {f!r:.80} {why} (L3 fix round 1, issue 1)")
    searched = [f for f in files if f in emb]
    folded = {f: _fold(texts[f]) for f in set(searched)}
    hits = sum(1 for f in searched for q in terms if _fold(q) in folded[f])
    got = sum(len(texts[f]) for f in searched)
    if (chars != got) if len(searched) == len(files) else (chars < got):
        p.append(f"ref {rid}: context absence: {chars} characters searched, recomputed {got} from the embedded artifacts")
    if hits or s["output"] != 0:
        p.append(f"ref {rid}: context absence (characters searched, occurrences) does not recompute: {hits} occurrence(s) in "
                 f"the embedded artifacts, output {s['output']}")
    want = {"inputs": {"files_searched": sorted(files), "chars_searched": chars, "requires_any": terms}, "formula": CONTEXT_FORMULA,
            "output": 0}
    if s != want or r["source_ref"] != ("context" if len(files) > 1 else files[0]):
        p.append(f"ref {rid}: the context-absence statement or source is not the recipe's (04 §5.10.3)")
    x = ("no casefold occurrence of " + jcs(terms) + " in context artifacts " + jcs(sorted(files)) + " (" + str(chars)
         + " characters searched)")
    if _rid(r["kind"], r["source_type"], None, x) != rid or r["turn_index"] is not None:
        p.append(f"ref {rid}: context absence id does not recompute (04 §5.10.3)")
    return p


def c_sources(rec, B, eio=None):
    """VER-5 over the bundle `sources` (see the module docstring). `eio` is the verifier's reader of the release (its
    witness rule; default: the bundled release). Returns (problems, info)."""
    e = eio if eio is not None else EIO(EIO_DIR)
    wanchors = e.wanchors
    p, n = [], Counter()
    # decision #31 (T4, T5): the record's fingerprints resolve to their bundle texts and its decisions recompute; the
    # comparisons below run on the record's clear view (each withheld value replaced by its bundle text)
    sealed = rec
    wp, rec = bundle_problems(sealed, B, e)
    p += wp
    h, bh, src = rec["header"], B["header"], B["sources"]
    sa = bh["source_archive"]
    want = (sa["archive_sha256"], sa["archive_schema"]) if sa else (sha(jb(B)), B["archive_schema"])
    if (h["archive_sha256"], h["archive_schema"]) != want:
        p.append(f"header archive_sha256/archive_schema {(h['archive_sha256'], h['archive_schema'])} != the bundle's {want}")
    run = rec["provenance"]["run"]
    if (run["run_id"], run["plan_hash"]) != (bh["run_id"], bh["plan_hash"]):
        p.append("provenance.run run_id/plan_hash differ from the bundle header")
    ev = rec["evidence"]
    if ev["transcript_sha256"] != src["transcript_sha256"]:
        p.append("evidence.transcript_sha256 != the bundle's sources.transcript_sha256")
    declared = {k: v for k, v in src["archive_pointer"].items() if k != "archive_sha256"}
    if {k: v for k, v in ev["archive_pointer"].items() if k != "archive_sha256"} != declared:
        p.append("evidence.archive_pointer != the bundle's declared sources.archive_pointer")
    if ev["archive_pointer"].get("archive_sha256") != h["archive_sha256"]:
        p.append("evidence.archive_pointer.archive_sha256 != the record's archive digest")
    p += _names_problems(src)
    p += layout_problems(src) + declared_item_problems(B, e)          # L3 fix round 1, issue 1
    content = Content(B, e)                                            # L3 fix round 2: what the record carries in clear
    p += content_problems(B, content) + bundle_content_problems(B, content) + record_content_problems(sealed, content)
    p += shape_problems(B, e)                                          # L3 fix round 4: identifying shapes in clear
    stated = (rec["provenance"].get("inputs") or {}).get("context_artifacts")
    if stated is not None and stated != src["context_artifacts"]:     # L3 fix round 1, issue 2
        p.append("provenance.inputs.context_artifacts are not the bundle's sources.context_artifacts: the record states other "
                 "context artifacts or data classes than the ones PROD-43 reads (L3 fix round 1, issue 2)")
    turns = {t["turn_index"]: t for t in src["turns"]}
    sc = (B.get("producer_declared") or {}).get("scenarios") or {"turns": []}
    label = {t["turn_index"]: t["label"] for t in sc["turns"]}
    if [t["turn_index"] for t in ev["turns"]] != sorted(turns):
        p.append("evidence.turns are not the bundle's turns")
    neutral = h["schema_uri"] in {
        "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json",
        "https://w3id.org/eio-agents/per/2.0.0-rc4-draft/per.schema.json",
        "urn:eio-agents:diagnostic:per:2.0.0-rc3-neutral-preview",
        "urn:eio-agents:provisional:per:2.0.0-rc5-policy-draft",
        "https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json",
        "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json",
        "https://www.proofagent.ai/eio-agents/schema/per/2.1.1/per.schema.json",
    }
    for te in ev["turns"]:
        t = turns.get(te["turn_index"])
        if t is None:
            continue
        exp = {"turn_index": t["turn_index"], "scenario" if neutral else "trap": label.get(t["turn_index"]),
               "question_sha256": sha(t["question"]),
               "answer_sha256": sha(t["answer"]),
               "tool_calls": [{"name": c["name"], "arguments_sha256": sha(jb(c["arguments"]))} for c in t["tool_calls"]],
               "retrievals": [{"source": x["source"]} for x in t["retrievals"]]}
        if te != exp:
            p.append(f"evidence.turns[{te['turn_index']}] digests do not recompute from the bundle's sources")
    arts = {a["name"]: a for a in src["context_artifacts"]}
    texts = src["context_texts"]
    emb = {x for x, a in arts.items() if a.get("embedded", True) and x in texts}         # embedded, with its text
    for a in src["context_artifacts"]:                  # the release's vocabularies (PROD-43 keys on the data class: D-29)
        if (a.get("artifact_kind") not in e.artifact_kinds or a.get("data_class") not in e.data_classes
                or not DATA_CLASS_ID.fullmatch(str(a.get("data_class")))):
            p.append(f"context artifact {a.get('name')!r}: artifact_kind {a.get('artifact_kind')!r} or data_class "
                     f"{a.get('data_class')!r} is not in the release")
    # PROD-43, read fail-closed: the text of an artifact whose class is not public or internal is never quoted, nor the
    # same bytes (or the same normalized text: L3 fix round 1, issue 3) declared under another name or class (L2 exit
    # D-32, D-35)
    withheld = content.withheld
    rules = _Rules(e, B, content)
    named = ({src["turn_source_ref"]} | set(arts) | ({src["state_field"]} if "state_field" in src else set())
             | {x.get("source") for t in src["turns"] for x in t["retrievals"] if isinstance(x.get("source"), str)})
    for g in (B.get("context_assessment") or {}).get("gaps") or []:          # a native gap: the release's terms, declared names
        crit = e.criteria.get(g["criterion"])
        ctl = {x["id"]: x for x in (crit or {}).get("controls") or []}.get(g["control"])
        if ctl is None:
            p.append(f"context gap {g['criterion']!r:.60}/{g['control']!r:.60}: not a checklist control of the release")
        elif not rules.adapter and not (set(g["terms"]) <= set(ctl["requires_any"]) and set(g["files_searched"]) <= rules.declared):
            p.append(f"context gap {g['criterion']}/{g['control']}: a native producer searches its declared artifacts with the "
                     "control's checklist terms (L3 fix round 1, issue 1)")
    for r in ev["refs"]:
        k, st, t = r["kind"], r["source_type"], r["turn_index"]
        if st in TURN_FIELD and (r.get("span_sha256") is not None or r.get("char_start") is not None):   # a span into a turn
            if r["source_ref"] != src["turn_source_ref"] or t not in turns:
                p.append(f"ref {r['id']}: a turn span outside the declared turn source {src['turn_source_ref']!r}")
                continue
            S = turns[t][TURN_FIELD[st]]
            a, b = r.get("char_start"), r.get("char_end")
            if not (isinstance(a, int) and isinstance(b, int) and 0 <= a <= b <= len(S)):
                p.append(f"ref {r['id']}: offsets outside the turn text")
                continue
            x = S[a:b]
            if a == b and r["anchor"] in QUOTE_ANCHORS:
                p.append(f"ref {r['id']}: an {r['anchor']} span [{a}, {b}) quotes nothing (L2 exit D-35, F-10)")
            if (r.get("span_sha256"), r["source_sha256"]) != (sha(x), sha(S)):
                p.append(f"ref {r['id']}: span/source digest does not recompute")
            if _rid(k, st, t, x, a, b, r.get("valid_from"), r.get("valid_until")) != r["id"]:
                p.append(f"ref {r['id']}: id does not recompute from the span (01 §10.3)")
            if r["anchor"] == "turn" and (a, b) != (0, len(S)):
                p.append(f"ref {r['id']}: anchor turn cites the whole turn source [0, {len(S)}), not [{a}, {b}) (03 §7.5)")
            p += _excerpt_problems(r, x)
            n["spans"] += 1
        elif k == "TOOL_RECEIPT":
            tl = r["tool"]
            calls = turns[t]["tool_calls"] if t in turns else []
            if (st != "AGENT_TOOL_CALL" or r["source_ref"] != src["turn_source_ref"] or type(tl["call_index"]) is not int
                    or not 0 <= tl["call_index"] < len(calls)):                   # an index is an integer (L2 exit D-30)
                p.append(f"ref {r['id']}: no such tool call in the declared turn source")
                continue
            c = calls[tl["call_index"]]
            ah = sha(jb(c["arguments"]))
            occ = sum(1 for cc in calls[: tl["call_index"] + 1] if cc["name"] == c["name"] and sha(jb(cc["arguments"])) == ah)
            out = {"sha256": sha(jb(c["result"]))} if "result" in c else "NOT_CAPTURED"
            if (tl["name"], tl["arguments_sha256"], tl["arguments_pointer"], tl["output"]) != (c["name"], ah, c["arguments_pointer"], out):
                p.append(f"ref {r['id']}: tool name / arguments_sha256 / arguments_pointer / output do not recompute")
            x = c["name"] + "|" + ah + ("" if occ == 1 else "|" + str(occ))
            if _rid(k, st, t, x) != r["id"]:
                p.append(f"ref {r['id']}: id does not recompute from the tool call (01 §10.3)")
            n["receipts"] += 1
        elif k == "TYPED_ABSENCE" and st == "AGENT_TOOL_CALL":
            s = r["statement"]
            ins = s["inputs"]
            cf = src["calls_field"]
            if ins.get("source") != cf:
                p.append(f"ref {r['id']}: the absence is not over the declared tool-call list {cf!r}")
            if "episode_turns" in ins:
                ep, terms = ins["episode_turns"], ins.get("name_contains")
                if not (isinstance(terms, list) and terms and all(isinstance(q, str) and CALL_TERM.fullmatch(q) for q in terms)):
                    p.append(f"ref {r['id']}: name_contains {terms!r:.120} is not a list of lower-case ASCII names (review R-5, D-35)")
                    continue
                for q in terms:
                    if (why := rules.call_term(q)) is not None:
                        p.append(f"ref {r['id']}: the named-call term {q!r:.80} {why} (L3 fix round 1, issue 1)")
                x = "no tool call whose name contains " + " or ".join(f"'{q}'" for q in terms) + " in episode turns " + jcs(ep)
                if not all(u in turns for u in ep) or t not in ep:
                    p.append(f"ref {r['id']}: episode turns {ep} are not turns of the bundle that include turn {t}")
                cnt = sum(1 for u in ep for c in (turns[u]["tool_calls"] if u in turns else [])
                          if any(q in c["name"].lower() for q in terms))
                want = {"inputs": {"source": cf, "episode_turns": ep, "name_contains": terms},
                        "formula": NAMED_CALL_FORMULA.format(cf=cf), "output": s["output"]}
            else:
                x = f"no tool call on turn {t}"
                cnt = len(turns[t]["tool_calls"]) if t in turns else None
                want = {"inputs": {"source": cf, "turns": [t]}, "formula": f"len({cf}[t])", "output": s["output"]}
            if cnt != s["output"]:
                p.append(f"ref {r['id']}: typed-absence output {s['output']} != {cnt} recomputed from sources")
            elif cnt != 0:
                p.append(f"ref {r['id']}: a typed absence with {cnt} matching tool call(s) is not an absence")
            if s != want or r["source_ref"] != src["turn_source_ref"]:
                p.append(f"ref {r['id']}: the typed-absence statement or source is not the recipe's")
            if _rid(k, st, t, x, vf=r.get("valid_from"), vu=r.get("valid_until")) != r["id"]:
                p.append(f"ref {r['id']}: id does not recompute from its statement (01 §10.3)")
            n["absences"] += 1
        elif k == "TYPED_ABSENCE" and st == "POLICY_SOURCE":
            p += _context_absence_problems(r, texts, emb, rules)
            n["absences"] += 1
        elif k == "POLICY_SPAN":
            if r["source_ref"] not in arts:
                p.append(f"ref {r['id']}: a POLICY_SPAN outside the bundle's declared context artifacts")
                continue
            art, text = arts[r["source_ref"]], texts.get(r["source_ref"])
            if r["source_ref"] not in emb:
                p.append(f"ref {r['id']}: its context artifact is not embedded in the bundle")
                continue
            a, b = r.get("char_start"), r.get("char_end")
            if not (isinstance(a, int) and isinstance(b, int) and 0 <= a <= b <= len(text)):
                p.append(f"ref {r['id']}: offsets outside the artifact text")
                continue
            x = text[a:b]
            if a == b and r["anchor"] in QUOTE_ANCHORS:
                p.append(f"ref {r['id']}: an {r['anchor']} span [{a}, {b}) quotes nothing (L2 exit D-35, F-10)")
            if (r.get("span_sha256"), r["source_sha256"]) != (sha(x), art["sha256"]) or sha(text) != art["sha256"]:
                p.append(f"ref {r['id']}: span/source digest does not recompute from the embedded artifact")
            if _rid(k, st, None, x, a, b) != r["id"] or t is not None:
                p.append(f"ref {r['id']}: id does not recompute from the span (01 §10.3)")
            if r["source_ref"] in withheld:
                if "excerpt" in r or not r.get("excerpt_redacted"):
                    p.append(f"ref {r['id']}: a model-confidential artifact (or one of another withheld class) carries no "
                             "excerpt, with excerpt_redacted (PROD-43)")
            else:
                p += _excerpt_problems(r, x)
            n["spans"] += 1
        elif k == "STATE_FACT" and st == "STATE_LEDGER" and t in turns and "state" in turns[t]:     # D-34: the declared snapshot
            snap, sf = turns[t]["state"], src.get("state_field")
            want = {"inputs": {"source": sf, "turns": [t], "snapshot_sha256": sha(jb(snap))}, "formula": f"{sf}[t] is non-empty",
                    "output": 1}
            if not snap or not isinstance(sf, str):
                p.append(f"ref {r['id']}: a state fact over an empty or unnamed state snapshot of turn {t}")
            elif (r.get("statement"), r["anchor"], r["source_ref"], r.get("valid_from"), r.get("valid_until")) != (
                    want, "computed", src["turn_source_ref"], t, None):
                p.append(f"ref {r['id']}: the state fact (statement, anchor, source, validity) does not recompute from the "
                         f"declared state snapshot of turn {t}")
            elif _rid(k, st, t, jcs(snap), vf=t) != r["id"]:
                p.append(f"ref {r['id']}: id does not recompute from the declared state snapshot (01 §10.3)")
            n["state_facts"] += 1
        else:                                    # text in no source of the bundle: non-witnessing, locating nothing (R-1)
            if st in TURN_FIELD and r["source_ref"] != src["turn_source_ref"]:        # a text-less turn ref (anchor none)
                p.append(f"ref {r['id']}: a turn ref outside the declared turn source {src['turn_source_ref']!r}")
            if r["can_prove_agent_behaviour"] and r["anchor"] in wanchors:
                p.append(f"ref {r['id']}: a witnessing {k} ref over {st} that does not recompute from the bundle's sources "
                         "(a declared ref may support a claim, never prove it)")
            located = [f for f in LOCATORS if r.get(f) is not None] + [f for f in EXCERPT_FIELDS if f in r]
            if located:
                p.append(f"ref {r['id']}: a {k} ref over {st} with its text in no source of the bundle carries {located}")
            if "statement" in r:                  # nothing checks it against the sources (subjects only as digests: D-31)
                p.append(f"ref {r['id']}: a {k} ref over {st} with its text in no source of the bundle carries a statement")
            if r["source_ref"] not in named or "tool" in r:       # what it names reaches the record (L3 fix round 1, issue 1)
                p.append(f"ref {r['id']}: a {k} ref over {st} with its text in no source of the bundle names the source "
                         f"{r['source_ref']!r:.80} (not a source the bundle declares) or carries a tool receipt")
            n["declared"] += 1
    if neutral:
        BC = {sd({"run_id": c["run_id"], "predicate": c["predicate"],
                  "predicate_version": c["predicate_version"],
                  "source_key": c["parameters"].get("source_key"),
                  "turn_indices": sorted(c["turn_indices"])}): c for c in B["claims"]}
    else:
        BC = {c["id"]: c for c in B["claims"]}
    for c in rec["claims"]:
        bc = BC.get(c["id"])
        if bc is None:
            p.append(f"claim {c['id']} is not a claim of the bundle")
            continue
        for key in ("predicate", "predicate_version", "turn_indices", "state", "decided_by"):
            if c[key] != bc[key]:
                p.append(f"claim {c['id']}: {key} differs from the bundle claim (PROD-4)")
        if sorted(c["evidence"]) != sorted(bc["evidence"]):
            p.append(f"claim {c['id']}: evidence differs from the bundle claim")
    if len(rec["claims"]) != len(BC):
        p.append(f"the record carries {len(rec['claims'])} claims, the bundle {len(BC)}")
    facts = f" (and {n['state_facts']} state facts)" if n["state_facts"] else ""
    return p, (f"archive identity, run, transcript digest, archive pointer and {len(ev['turns'])} turns; {n['spans']} spans, "
               f"{n['receipts']} receipts and {n['absences']} absences{facts} recomputed from the bundle's sources; "
               f"{n['declared']} refs with no source text checked by the record checks")


def verify(rec, bundle, *, rederived, eio=None):
    """The record checks (VER-1, VER-3, VER-4), VER-5 over the bundle's sources, and the digest comparison with
    `rederived`: the record re-projected from `bundle` (a PER dict), or an exception when the re-projection failed.
    Returns `{valid, digest_match, per_sha256, rederived_sha256, failures}`."""
    k = check_one(rec, eio)
    # bundle text is read as I-JSON, at most MAX_DEPTH levels (review R-2); a bundle that is not is a failing D2 row
    k.run("D2 refs and digests recompute from the bundle sources", "VER-5", lambda: c_sources(rec, bundle_of(bundle), k.eio))
    k.run("D5 native proof status independently recomputed", "VER-5",
          lambda: native_proof_status_gate(bundle_of(bundle), rec, k.eio))
    # A producer round-trip can prove byte identity but cannot independently
    # validate the producer's numeric scoring. Native scored records stay RED
    # until a pinned profile and every source-derived score are recomputed by
    # this separate validation unit.
    prior_ok = (all(row[2] != "FAIL" for row in k.rows)
                and any(row[0].startswith("D2 refs") and row[2] == "PASS" for row in k.rows)
                and any(row[0].startswith("D5 native proof") and row[2] == "PASS" for row in k.rows))
    k.run("D4 native score independently recomputed", "VER-5",
          lambda: native_score_gate(rec, bundle_of(bundle), eio=k.eio, source_checked=prior_ok))
    try:
        mine = sha(jb(rec))
    except (TypeError, ValueError, RecursionError):   # not canonicalisable (NaN, a lone surrogate, too deep): D1 fails
        mine = None
    if mine is None:
        other = sha(jb(rederived)) if isinstance(rederived, dict) else None
        k.run("D3 re-projection byte-identical", "VER-5", lambda: (["the record has no canonical form, so no digest"], ""))
    elif isinstance(rederived, dict):
        other = sha(jb(rederived))
        k.run("D3 re-projection byte-identical", "VER-5",
              lambda: ([] if other == mine else [f"re-projection differs: {other} vs record {mine}"], f"{other[:23]}…"))
    else:
        other = None
        k.run("D3 re-projection byte-identical", "VER-5", lambda: ([f"the bundle does not project: {rederived}"], ""))
    fails = rows_as_problems(r for r in k.rows if r[2] == "FAIL")
    return {"valid": not fails, "digest_match": mine is not None and other == mine, "per_sha256": mine, "rederived_sha256": other,
            "failures": fails}
