"""The evaluation bundle (archive schema 3, draft 2): reading, section validation, the producer-declared acceptance rule,
stage-record digests and the recompute checks of `eio_agents.per.project` (contract §6.1-§6.2 steps 1, 2 and 4).

Typed error codes (neutral tokens, never EIO ids; `ConversionError.code`):
- `BUNDLE_INPUT`: not a JSON object, or not an archive-schema-3 bundle (a stored archive of another schema goes to its
  producer's adapter first); or bundle text that is not I-JSON (not UTF-8, an object member given twice, a NaN or
  infinite number, a lone surrogate in a string: L2 exit D-30; an integer beyond the IEEE 754 double range, or too long
  for Python to read: L3 fix round 1, issue 4), a bundle given as a dict that holds a value JSON has not (a set, bytes,
  a member name that is not a string: issue 4), or a bundle nested more than `MAX_DEPTH` (100) levels deep;
- `BUNDLE_SCHEMA`: a section does not validate against the bundle schema, or breaks a rule the schema language cannot
  state: a name the sources are resolved by (a turn index, a context-artifact name) is given twice, a context-artifact
  name is not in Unicode NFC, `context_texts` is not exactly the texts of the embedded context artifacts, or a turn's
  state snapshot is not named by `sources.state_field` (L2 exit D-34, D-35); or a name of the source layout
  (`turn_source_ref`, `calls_field`, `state_field`) is not an identifier (L3 fix round 1, issue 1);
- `BUNDLE_STAGE_RECORDS`: a section is filled by no stage record, or by more than one; or a native producer's bundle has
  a stage record that is not `producer: native`;
- `PRODUCER_DECLARED_NOT_ACCEPTED`: the producer-declared section is present but the producer is native, a matching
  stage record is not `producer: adapter`, or no crosswalk digest is declared (split plan §4.4); or a native producer's
  bundle declares a source archive (a native bundle is its own archive);
- `BUNDLE_STAGE_DIGEST`: a stage record's output digest does not recompute (checked when the bundle was built by this
  EIO-Agents version under this release);
- `BUNDLE_VOCABULARY`: a closed vocabulary value (claim state, evidence kind, source type, anchor, severity, a context
  artifact's data class or kind: L2 exit D-29; a context-link criterion or control) is not one of the loaded release, a
  declared item names a claim, turn or predicate the bundle does not have, or a scenario label or context-link key is
  not a label (L3 fix round 1, issue 1);
- `BUNDLE_SCOPE`: a scope value (tier, region, autonomy, domain, fact, framework, policy object) is not one of the loaded
  release, or the policy object is inconsistent;
- `BUNDLE_RECOMPUTE`: an id, a ref, a computed statement, a witness flag, an anchor, a pointer, a digest, the episodes or
  a pooled vote count does not recompute from the bundle's own sources and the loaded release, or a declared ref has the
  id of a ref the projector derives but other content; or a ref that no recipe of EIO-Agents rebuilds from the bundle's
  sources would witness agent behaviour, locates text (offsets, digests, an excerpt) in a source the bundle does not
  carry, or carries a statement (review R-1, L2 exit D-31: a declared ref may support a claim, never prove it, and quotes
  nothing); or an exact or casefold span that quotes nothing (L2 exit D-35, F-10), or a context search whose term holds
  an invisible or non-NFC character or whose file name spells an embedded artifact's name another way (L2 exit D-35,
  F-13). L3 fix round 1: a producer-chosen text that reaches the record is the bundle's or the release's (issue 1): an
  archive-pointer key is an identifier and the archive and argument pointers hold identifier and index tokens; a ref
  that no recipe rebuilds names a source the bundle declares and carries no tool receipt; a context search names
  declared artifacts with release checklist terms (an adapter producer may also name a portable file that is not
  declared and search a printable ASCII phrase of its own checklist), a named-call term is at most 64 characters, and no
  term or undeclared name reproduces confidential content the bundle carries (`Withheld`); a context-link row's `via` is
  its link; `provenance.record.inputs.context_artifacts` is `sources.context_artifacts` (issue 2).
"""
import copy
import json
import math
import re
import unicodedata
import urllib.parse
import weakref
from collections import Counter

from jsonschema import Draft202012Validator

from eio_agents.adjudication import pool
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError, require
from eio_agents.base.version import VERSION
from eio_agents.evidence import context_refs as ev_context
from eio_agents.evidence import redaction
from eio_agents.evidence.refs import CALL_TERM, no_call_ref, no_matching_call_ref, receipt_ref, span_ref, state_fact_ref
from eio_agents.per.context import embedded
from eio_agents.per.limitations import CATALOGUE as LIMITATION_CATALOGUE
from eio_agents.schemas import BUNDLE_VERSION, bundle_schema  # noqa: F401  (BUNDLE_VERSION: the current format)
from eio_agents.semantics import ids

# Legacy, read-only: the `bundle_draft` of bundles already issued (the ProofAgent Harness adapter still writes it).
# New bundles carry `bundle_version` BUNDLE_VERSION ("3.0.0"); both are read.
BUNDLE_DRAFT = 2
SECTIONS = ("provenance", "sources", "scope", "context_assessment", "graph", "claims", "ballots", "trials", "limitations")
DECLARED_ITEMS = ("scenarios", "capabilities", "context_links", "score_inputs")
TURN_FIELD = {"AGENT_ANSWER": "answer", "USER_INPUT": "question"}      # span source type -> the turn text it points into

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")           # 03 §7.8 severity (upper case in the PER)
POLICY_SOURCES = ("embedded_profile", "tier_reconstructed", "none")           # the rc1 policy sources (§5.3: S1b)
OFFSET_ANCHORS = ("exact", "casefold", "turn", "line")                        # anchors that locate a span by offsets
POLICY_ANCHORS = ("line", "document")                                         # anchors of a context-artifact ref only
QUOTE_ANCHORS = ("exact", "casefold")                                          # anchors that quote text: never empty (F-10)
LOCATORS = ("char_start", "char_end", "span_sha256", "source_sha256")         # what locates a ref's text in a source
EXCERPT_FIELDS = ("excerpt", "excerpt_truncated", "excerpt_redacted")
MAX_DEPTH = 100          # nesting levels of a bundle (RFC 8259 §9 lets a reader limit it; the shipped bundles have 7)
DOUBLE_MAX = 1.7976931348623157e308   # an integer beyond it has no JSON number form any reader keeps (L3 fix round 1, issue 4)
# L3 fix round 1, issue 1: every producer-chosen text that reaches the record is a name or a term the bundle or the release
# declares, of a shape that reads as what it names
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")          # a name of the source layout (turn source, calls, state field)
POINTER = re.compile(r"(?:/[A-Za-z0-9_]{1,64}){1,16}")       # an archive or argument pointer: identifier and index tokens
LABEL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}")    # a scenario label, a context-link key (a legacy check name)
PORTABLE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")       # a segment of a portable relative file name (POSIX portable)
PHRASE = re.compile(r"[\x20-\x7e]*[A-Za-z0-9][\x20-\x7e]*")   # a checklist phrase of an adapter producer: printable ASCII
NAME_MAX, TERM_MAX = 255, 64
CONTENT_WORDS = 3        # a text reproduces confidential content when it holds this many consecutive words of it (`Withheld`)
VIA = "eio.graph.context-links:{key}\u2192{criterion}/{control}"   # the via of a context-link row (the rc1 schema's form)
WORD = re.compile(r"[^\W_]+")                                # a word: letters and digits
# L3 fix round 2: how `Withheld` reads a text (`words`). The default-ignorable code points of Unicode (besides the format,
# private-use and combining characters, dropped by category): an invisible character inside a word does not split it
IGNORABLE = frozenset(c for a, b in ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
                                     (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
                                     (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
                                     (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF)) for c in range(a, b + 1))
DROPPED = ("Mn", "Me", "Cf", "Co", "Cs", "Cn")               # combining marks, format, private-use, surrogate, unassigned
# letters that read as a Latin letter (Cyrillic, Greek, Armenian and Latin look-alikes; case kept, before the casefold)
LOOKALIKE = str.maketrans(dict(pair for pair in (
    "\u0410A \u0412B \u0415E \u0405S \u0406I \u0408J \u041aK \u041cM \u041dH \u041eO \u0420P \u0421C \u0422T \u0425X \u0423Y \u050cG \u051aQ \u051cW \u0430a \u0435e \u0455s \u0456i \u0458j \u043ak \u043eo \u0440p \u0441c \u0445x \u0443y \u0501d \u04bbh \u04cfl \u051bq \u051dw \u04afy \u044cb "
    "\u0251a \u0261g \u0131i \u0237j \u0391A \u0392B \u0395E \u0396Z \u0397H \u0399I \u039aK \u039cM \u039dN \u039fO \u03a1P \u03a4T \u03a5Y \u03a7X \u03b1a \u03b9i \u03bfo \u03bak \u03c1p \u03c4t \u03c5u \u03c7x \u03bdv \u0585o \u057du \u0578n \u0570h").split()))
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")   # a camel-case word boundary (ASCII fast path)
FILE_NAME = re.compile(r".*[^\W_]\.[A-Za-z0-9]{1,8}")        # a name with a file extension ('credit_policy.md')
# the record fields exempt from the record-wide rule (`record_content_problems`), each with its recorded reason
AGENT_DESCRIPTION = (("subject", "agent", "goal"), ("subject", "agent", "role"))   # ACCEPTED_DEVIATIONS D-41: hash + pointer at S2
# the refs whose PROD-42 excerpt is exempt from the record-wide rule: a span of a turn text, the agent's answer
# (ACCEPTED_DEVIATIONS D-43) or the user's question (D-48); both L5b. A POLICY_SPAN's excerpt is checked
TURN_EXCERPT = tuple(TURN_FIELD)
# L3 fix round 3: a plain decimal number ('0.5', '12'): a count, an index or a score, never a subject by its groups alone
DECIMAL = re.compile(r"\s*[-+]?[0-9]+(?:\.[0-9]+)?\s*")


def nested_deeper_than(doc, limit):
    """Whether a JSON value nests more than `limit` levels (`{}` and `[]` are one level), found without recursion; it stops
    at the first container past the limit, so a cyclic dict ends too."""
    stack = [(doc, 1)]
    while stack:
        o, d = stack.pop()
        if isinstance(o, (dict, list)):
            if d > limit:
                return True
            stack.extend((v, d + 1) for v in (o.values() if isinstance(o, dict) else o))
    return False


def _validator(bundle=None):
    """A validator of the bundle schema of `bundle`'s declared format (3.0.0, or a legacy `bundle_draft` 1 or 2 read with
    its pinned schema), built per call (no process-global cache; the schemas are checked by the tests)."""
    return Draft202012Validator(bundle_schema(bundle))


def _members(pairs):
    """The members of one JSON object. A name given twice fails closed: RFC 8259 leaves its reading to the parser, I-JSON
    (RFC 7493 §2.3) and JCS forbid it, so no reader of the bundle can resolve it differently (review R-2)."""
    seen = Counter(k for k, _ in pairs)
    twice = sorted(k for k, n in seen.items() if n > 1)
    require(not twice, "BUNDLE_INPUT", f"the bundle text gives the object member(s) {twice} twice (I-JSON)")
    return dict(pairs)


def _not_a_number(token):
    raise ConversionError(f"BUNDLE_INPUT: {token} is not a JSON number (I-JSON, PROD-9)", code="BUNDLE_INPUT")


def _finite(token):
    x = float(token)
    require(math.isfinite(x), "BUNDLE_INPUT", f"the number {token[:40]} is outside the IEEE 754 double range (I-JSON, PROD-9)")
    return x


def loads(text):
    """Bundle JSON text (str, bytes) -> dict, as I-JSON: UTF-8, each object member once, finite numbers, no lone surrogate
    in a string (RFC 7493 §2.1; L2 exit D-30). Fails closed with `BUNDLE_INPUT`, a number too long for Python to read
    included (ValueError: L3 fix round 1, issue 4)."""
    try:
        if isinstance(text, (bytes, bytearray)):
            text = bytes(text).decode("utf-8")
        doc = json.loads(text, object_pairs_hook=_members, parse_constant=_not_a_number, parse_float=_finite)
    except (ValueError, RecursionError) as e:       # JSONDecodeError, UnicodeDecodeError, an integer of over 4,300 digits
        raise ConversionError(f"BUNDLE_INPUT: not a JSON text ({type(e).__name__}: {str(e)[:200]})", code="BUNDLE_INPUT") from e
    at = lone_surrogate_at(doc)
    require(at is None, "BUNDLE_INPUT", f"{at}: a string that is not a sequence of Unicode scalar values (a lone surrogate; "
            "I-JSON, RFC 7493 §2.1)")
    return doc


def lone_surrogate_at(doc):
    """The JSON Pointer of the first string (a member name or a value) of `doc` that is not a sequence of Unicode scalar
    values (it holds a lone surrogate), or None; found without recursion (`doc` nests at most `MAX_DEPTH` levels)."""
    stack = [(doc, "")]
    while stack:
        o, at = stack.pop()
        if isinstance(o, str):
            try:
                o.encode("utf-8")
            except UnicodeEncodeError:
                return at or "/"
        elif isinstance(o, dict):
            for k, v in o.items():
                name = json.dumps(k)[1:-1] if isinstance(k, str) else repr(k)
                try:
                    if isinstance(k, str):
                        k.encode("utf-8")
                except UnicodeEncodeError:
                    return f"{at}/{name}"
                stack.append((v, f"{at}/{name}"))
        elif isinstance(o, list):
            stack.extend((v, f"{at}/{i}") for i, v in enumerate(o))
    return None


def non_json_at(doc):
    """The JSON Pointer of the first value of `doc` that JSON text cannot hold as a number any reader keeps, or cannot hold
    at all: a member name that is not a string, an integer beyond the IEEE 754 double range, or any value but an object,
    an array (a list), a string, a number, true, false and null (a tuple, a set, bytes, ...); or None. Found without
    recursion (L3 fix round
    1, issue 4: such a value raised untyped in a later canonical form; a NaN keeps its code, `NON_FINITE`)."""
    stack = [(doc, "")]
    while stack:
        o, at = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(k, str):
                    return f"{at}/{k!r}"
                stack.append((v, f"{at}/{json.dumps(k)[1:-1]}"))
        elif isinstance(o, list):
            stack.extend((v, f"{at}/{i}") for i, v in enumerate(o))
        elif o is None or isinstance(o, (bool, str, float)):
            continue
        elif isinstance(o, int):
            if abs(o) > DOUBLE_MAX:
                return at or "/"
        else:                                     # a tuple, a set, bytes, any other object
            return at or "/"
    return None


def read(bundle):
    """A private deep copy of the bundle (bytes, JSON text or dict); fails closed on anything else, on a bundle nested
    deeper than `MAX_DEPTH` levels (so no later step can exhaust the stack, whoever calls it), on a string that holds a
    lone surrogate (I-JSON, RFC 7493 §2.1: no later digest or canonical form can encode it; L2 exit D-30), and on a value
    that JSON text cannot hold as I-JSON (`non_json_at`; L3 fix round 1, issue 4)."""
    if isinstance(bundle, (bytes, bytearray, str)):
        bundle = loads(bundle)
    require(isinstance(bundle, dict), "BUNDLE_INPUT", "a bundle is a JSON object")
    require(bundle.get("archive_schema") == 3 and not isinstance(bundle.get("archive_schema"), bool), "BUNDLE_INPUT",
            f"archive_schema {bundle.get('archive_schema')!r} is not a bundle (archive schema 3); convert a stored archive "
            "through its producer's adapter")
    require(not nested_deeper_than(bundle, MAX_DEPTH), "BUNDLE_INPUT", f"the bundle is nested more than {MAX_DEPTH} levels deep")
    at = lone_surrogate_at(bundle)
    require(at is None, "BUNDLE_INPUT", f"{at}: a string that is not a sequence of Unicode scalar values (a lone surrogate; "
            "I-JSON, RFC 7493 §2.1)")
    at = non_json_at(bundle)
    require(at is None, "BUNDLE_INPUT", f"{at}: a value that JSON text cannot hold (a member name that is not a string, an "
            "integer beyond the IEEE 754 double range, a tuple, a set, bytes, ...)")
    return copy.deepcopy(bundle)


def section_paths(bundle):
    """Every section a stage record must fill: the top-level sections and each producer-declared item."""
    paths = list(SECTIONS)
    if "native_scoring" in bundle:
        paths.append("native_scoring")
    paths += [f"producer_declared.{k}" for k in DECLARED_ITEMS if k in (bundle.get("producer_declared") or {})]
    return paths


def section_value(bundle, path):
    head, _, item = path.partition(".")
    return bundle[head][item] if item else bundle[head]


def stage_digest(bundle, sections):
    """The output digest of a stage record: sha256 over the JCS bytes of {section path: value}."""
    return H(jb({p: section_value(bundle, p) for p in sections}))


def validate_sections(bundle):
    """Step 1: every section validates against the bundle schema, and each is filled by exactly one stage record."""
    errs = sorted(_validator(bundle).iter_errors(bundle), key=lambda e: (list(e.absolute_path), e.message))
    if errs:
        e = errs[0]
        raise ConversionError(f"BUNDLE_SCHEMA: /{'/'.join(map(str, e.absolute_path))}: {e.message[:300]}", code="BUNDLE_SCHEMA")
    filled = [p for r in bundle["stage_records"] for p in r["sections"]]
    for p in section_paths(bundle):
        require(filled.count(p) == 1, "BUNDLE_STAGE_RECORDS", f"{p} is filled by {filled.count(p)} stage records")
    extra = sorted(set(filled) - set(section_paths(bundle)))
    require(not extra, "BUNDLE_STAGE_RECORDS", f"stage records name unknown sections {extra}")


def check_names(bundle):
    """Step 1, the rules the schema language cannot state (review R-2): every name the bundle's sources are resolved by
    names one item, so every reader (the recompute, the derived context lines, the views, the verifier twin) resolves it
    to the same entry. A turn index is given once; a context-artifact name is declared once; and `context_texts` holds
    exactly the texts of the embedded artifacts, so an artifact is embedded if and only if its text is in the bundle."""
    src = bundle["sources"]
    twice = sorted(u for u, n in Counter(t["turn_index"] for t in src["turns"]).items() if n > 1)
    require(not twice, "BUNDLE_SCHEMA", f"sources.turns: turn_index {twice} given twice")
    twice = sorted(x for x, n in Counter(a["name"] for a in src["context_artifacts"]).items() if n > 1)
    require(not twice, "BUNDLE_SCHEMA", f"sources.context_artifacts: {twice} declared twice (a name resolves one artifact)")
    # a name has one spelling (L2 exit D-35, F-11): an artifact name in another normal form would resolve another artifact
    # for a reader that normalises; the record's relative paths are NFC (VER-4)
    odd = sorted(a["name"] for a in src["context_artifacts"] if unicodedata.normalize("NFC", a["name"]) != a["name"])
    require(not odd, "BUNDLE_SCHEMA", f"sources.context_artifacts: the name(s) {odd} are not in Unicode NFC")
    emb = sorted(a["name"] for a in embedded(src["context_artifacts"]))
    require(sorted(src["context_texts"]) == emb, "BUNDLE_SCHEMA",
            f"sources.context_texts {sorted(src['context_texts'])} are not the texts of the embedded context artifacts {emb}")
    # a turn's state snapshot is named by the declared state field, the name its state facts read (L2 exit D-34)
    stated = sorted(t["turn_index"] for t in src["turns"] if "state" in t)
    require(not stated or "state_field" in src, "BUNDLE_SCHEMA",
            f"sources.turns {stated} carry a state snapshot, but sources.state_field does not name it")
    # the names of the source layout reach the record (source_ref, statements, formulas): each is an identifier (L3 fix
    # round 1, issue 1; the pointers: `check_pointers`)
    for k in ("turn_source_ref", "calls_field", "state_field"):
        require(k not in src or IDENT.fullmatch(src[k]) is not None, "BUNDLE_SCHEMA",
                f"sources.{k} {src.get(k)!r:.80} is not an identifier ({IDENT.pattern}): it is written into the record")


def check_pointers(src):
    """The archive pointer and every tool call's argument pointer reach the record (evidence.archive_pointer, a tool
    receipt's arguments_pointer): an archive-pointer key is an identifier and each pointer holds identifier and index
    tokens only (L3 fix round 1, issue 1; a native bundle's pointers also recompute: `check_native_sources`)."""
    for k, v in src["archive_pointer"].items():
        require(k == "archive_sha256" or (IDENT.fullmatch(k) is not None and isinstance(v, str) and POINTER.fullmatch(v) is not None),
                "BUNDLE_RECOMPUTE", f"sources.archive_pointer {k!r:.80}: {v!r:.80} is not an identifier with a pointer of identifier "
                f"and index tokens ({POINTER.pattern})")
    for t in src["turns"]:
        for j, c in enumerate(t["tool_calls"]):
            require(POINTER.fullmatch(c["arguments_pointer"]) is not None, "BUNDLE_RECOMPUTE",
                    f"sources.turns: turn {t['turn_index']}, call {j}: arguments_pointer {c['arguments_pointer']!r:.80} is not a "
                    f"pointer of identifier and index tokens ({POINTER.pattern})")


def producer_of(bundle, path):
    return next(r["producer"] for r in bundle["stage_records"] if path in r["sections"])


def accept_producer_declared(bundle):
    """Split plan §4.4: the producer-declared section is accepted only from an adapter producer (every matching stage
    record says `producer: adapter`, `provenance.producer.kind` is adapter, and a crosswalk digest is declared). A native
    producer's bundle with the section fails closed."""
    decl = bundle.get("producer_declared")
    if decl is None:
        return
    kind = bundle["provenance"]["producer"]["kind"]
    require(kind == "adapter", "PRODUCER_DECLARED_NOT_ACCEPTED",
            f"provenance.producer.kind is {kind}: the producer-declared section is accepted from adapter producers only")
    require(bundle["header"]["adapter"] is not None, "PRODUCER_DECLARED_NOT_ACCEPTED",
            "the producer-declared section needs a declared adapter (header.adapter)")
    crosswalk = bundle["header"]["crosswalk"]
    require(crosswalk is not None and crosswalk.get("sha256"), "PRODUCER_DECLARED_NOT_ACCEPTED",
            "the producer-declared section needs a declared crosswalk digest (header.crosswalk)")
    for k in decl:
        p = producer_of(bundle, f"producer_declared.{k}")
        require(p == "adapter", "PRODUCER_DECLARED_NOT_ACCEPTED", f"producer_declared.{k} is filled by a {p} stage record")


def accept_native(bundle):
    """A native producer's bundle (`provenance.producer.kind: native`) is its own archive and has no adapter-filled
    section: it declares no source archive (the record's archive is the bundle, schema 3, by its JCS digest), and every
    stage record says `producer: native` (review M-2, L-6)."""
    if bundle["provenance"]["producer"]["kind"] != "native":
        require("native_scoring" not in bundle, "NATIVE_SCORE_INPUT",
                "native_scoring is accepted from native producers only")
        return
    require(bundle["header"]["source_archive"] is None, "PRODUCER_DECLARED_NOT_ACCEPTED",
            "a native bundle is its own archive: header.source_archive is declared by adapter producers only")
    for r in bundle["stage_records"]:
        require(r["producer"] == "native", "BUNDLE_STAGE_RECORDS",
                f"stage {r['stage']}: producer {r['producer']} in a native producer's bundle")


def check_vocabulary(eio, bundle):
    """Closed vocabularies against the loaded release (the L2 structure review, findings 4 and 5): claim states, evidence kinds, source types
    and anchors, scope values, the policy object, and the claims, turns and predicates that declared items name."""
    turns = {t["turn_index"] for t in bundle["sources"]["turns"]}
    claims = {c["id"] for c in bundle["claims"]}
    for c in bundle["claims"]:
        require(c["state"] in eio.states, "BUNDLE_VOCABULARY", f"claim {c['id']}: state {c['state']!r} is not an EIO decision state")
        require(c["predicate"] in eio.pred, "BUNDLE_VOCABULARY", f"claim {c['id']}: unknown predicate {c['predicate']}")
    for a in bundle["sources"]["context_artifacts"]:      # L2 exit D-29: PROD-43 keys on the data class, never on a guess
        require(a["artifact_kind"] in eio.artifact_kinds, "BUNDLE_VOCABULARY",
                f"context artifact {a['name']!r}: artifact_kind {a['artifact_kind']!r} is not a context-artifact kind of the release")
        require(a["data_class"] in eio.data_classes, "BUNDLE_VOCABULARY",
                f"context artifact {a['name']!r}: data_class {a['data_class']!r} is not a data class of the release")
    for r in bundle["graph"]["refs"]:
        require(r["kind"] in eio.kind, "BUNDLE_VOCABULARY", f"ref {r['id']}: unknown evidence kind {r['kind']!r}")
        require(r["source_type"] in eio.source_type, "BUNDLE_VOCABULARY", f"ref {r['id']}: unknown source type {r['source_type']!r}")
        require(r["anchor"] in eio.anchors, "BUNDLE_VOCABULARY", f"ref {r['id']}: unknown anchor {r['anchor']!r}")
    sc = bundle["scope"]
    require(sc["tier"] is None or sc["tier"] in eio.tiers, "BUNDLE_SCOPE", f"unknown tier {sc['tier']!r}")
    require(sc["region"] is None or sc["region"] in eio.regions, "BUNDLE_SCOPE", f"unknown region {sc['region']!r}")
    require(sc["autonomy"] is None or sc["autonomy"] in eio.autonomy, "BUNDLE_SCOPE", f"unknown autonomy {sc['autonomy']!r}")
    for d in sc["domain_candidates"]:
        require(d["id"] in eio.domains, "BUNDLE_SCOPE", f"unknown domain {d['id']!r}")
    for k in sc["facts"]:
        require(k in eio.facts, "BUNDLE_SCOPE", f"unknown fact {k!r}")
    for f in sc["frameworks"]["candidates"]:
        require(f["id"] in eio.frameworks, "BUNDLE_SCOPE", f"unknown framework {f['id']!r}")
    pol = sc["policy"]
    require(pol["source"] in POLICY_SOURCES, "BUNDLE_SCOPE", f"unknown policy source {pol['source']!r}")
    if pol["source"] != "none":
        require(isinstance(pol["rules"], dict), "BUNDLE_SCOPE", f"policy source {pol['source']} needs a rules object")
        bs = pol["rules"].get("block_severity")
        require(isinstance(bs, str) and bs.upper() in SEVERITIES, "BUNDLE_SCOPE", f"unknown block_severity {bs!r}")
    decl = bundle.get("producer_declared") or {}
    sc_ = decl.get("scenarios")
    if sc_:
        labelled = set()
        for t in sc_["turns"]:
            require(t["turn_index"] in turns, "BUNDLE_VOCABULARY", f"scenario label of turn {t['turn_index']}, which is not in sources")
            require(t["turn_index"] not in labelled, "BUNDLE_VOCABULARY", f"turn {t['turn_index']} has two scenario labels")
            labelled.add(t["turn_index"])
        for lab, sev in sc_["severity"].items():
            require(sev is None or (isinstance(sev, str) and sev.upper() in SEVERITIES), "BUNDLE_VOCABULARY",
                    f"scenario {lab}: unknown severity {sev!r}")
        # a scenario label reaches the record (evidence.turns, findings): it is a label (L3 fix round 1, issue 1)
        odd = [x for x in [t["label"] for t in sc_["turns"]] + list(sc_["severity"]) if LABEL.fullmatch(x) is None]
        require(not odd, "BUNDLE_VOCABULARY", f"the scenario label {odd[:1]!r:.90} is not a label ({LABEL.pattern})")
    cl = decl.get("context_links")
    if cl:
        for cid in cl["claims"]:
            require(cid in claims, "BUNDLE_VOCABULARY", f"context links name claim {cid}, which is not a claim")
        # a row's criterion and control are the release's, and its `via` (written into the record) is its link, from a
        # key that is a label (L3 fix round 1, issue 1)
        for key, rows in cl["rows"].items():
            require(LABEL.fullmatch(key) is not None, "BUNDLE_VOCABULARY", f"the context-link key {key!r:.90} is not a label ({LABEL.pattern})")
            for row in rows:
                crit, ctl = row["criterion"], row["control"]
                require(crit in eio.criteria and ctl in [x["id"] for x in eio.criteria[crit].get("controls") or []],
                        "BUNDLE_VOCABULARY", f"context link {key}: {crit!r:.80}/{ctl!r:.80} is not a checklist control of the release")
                require(row["via"] == VIA.format(key=key, criterion=crit, control=ctl), "BUNDLE_RECOMPUTE",
                        f"context link {key}: via {row['via']!r:.90} is not the link {VIA.format(key=key, criterion=crit, control=ctl)!r}")
    cap = decl.get("capabilities")
    if cap:
        for pred in list(cap["reachable_predicates"]) + list(cap["not_implemented_predicates"]):
            require(pred in eio.pred, "BUNDLE_VOCABULARY", f"the capability registry names unknown predicate {pred}")
    tr = bundle["trials"]
    if tr is not None:
        seen = set()
        for x in tr["records"]:
            require(x["claim_id"] in claims, "BUNDLE_VOCABULARY", f"trial record names claim {x['claim_id']}, which is not a claim")
            require(x["claim_id"] not in seen, "BUNDLE_VOCABULARY", f"two trial records for claim {x['claim_id']}")
            seen.add(x["claim_id"])


def check_stage_digests(eio, bundle):
    """Step 4: when the bundle was built by this EIO-Agents version under this release, `header.eio` must name that
    release and every stage record's output digest must recompute. Otherwise the views are re-derived (the
    re-derivation limitation is a PER rc2 gap)."""
    h = bundle["header"]
    if h["eio_agents"]["version"] != VERSION or h["eio_agents"]["ontology_sha256"] != eio.ontology_sha256:
        return False
    loaded = {"release": eio.release, "ontology_digest": eio.ontology_digest, "ontology_sha256": eio.ontology_sha256}
    require(h["eio"] == loaded, "BUNDLE_RECOMPUTE",                                   # review L-6
            f"header.eio {h['eio']} is not the release that built the bundle ({loaded})")
    for r in bundle["stage_records"]:
        require(stage_digest(bundle, r["sections"]) == r["output_sha256"], "BUNDLE_STAGE_DIGEST",
                f"stage {r['stage']}: output digest does not recompute")
    return True


def check_episodes(bundle):
    """Until the plan bindings (S7), `graph.episodes` is the scenario-label grouping of the source turns, an unlabelled
    turn being its own episode: the one grouping the verifier can recompute from a record, which carries the labels and
    no episodes (review M-1). The order of the episodes and of their turns is free."""
    sc = (bundle.get("producer_declared") or {}).get("scenarios")
    label = {t["turn_index"]: t["label"] for t in sc["turns"]} if sc else {}
    groups = {}
    for t in bundle["sources"]["turns"]:
        u = t["turn_index"]
        groups.setdefault(("label", label[u]) if u in label else ("turn", u), []).append(u)
    want = sorted(sorted(g) for g in groups.values())
    got = sorted(sorted(e) for e in bundle["graph"]["episodes"])
    require(got == want, "BUNDLE_RECOMPUTE",
            f"graph.episodes {got} is not the scenario-label grouping of the turns {want} (an unlabelled turn is its own episode)")


def _resolves(doc, pointer):
    """Whether the RFC 6901 pointer names a value of `doc`."""
    o = doc
    for tok in pointer.split("/")[1:]:
        tok = tok.replace("~1", "/").replace("~0", "~")
        if isinstance(o, dict) and tok in o:
            o = o[tok]
        elif isinstance(o, list) and re.fullmatch(r"0|[1-9][0-9]*", tok) and int(tok) < len(o):
            o = o[int(tok)]
        else:
            return False
    return True


def check_native_sources(bundle):
    """A native bundle is its own archive (review M-2, L-6), so its pointers and its transcript digest recompute from the
    bundle: the archive pointer points into the bundle's own `/sources` and declares no archive digest (the projector
    writes it), each tool call's `arguments_pointer` is the location of that call's arguments in the bundle, and
    `transcript_sha256` is the digest of its turns (`sha256` of the JCS bytes of `sources.turns`)."""
    src = bundle["sources"]
    for k, v in src["archive_pointer"].items():
        require(k != "archive_sha256", "BUNDLE_RECOMPUTE",
                "sources.archive_pointer.archive_sha256: a native bundle cannot contain its own digest (the projector writes it)")
        require(isinstance(v, str) and (v == "/sources" or v.startswith("/sources/")) and _resolves(bundle, v), "BUNDLE_RECOMPUTE",
                f"sources.archive_pointer.{k}: {v!r} is not a pointer into the bundle's sources")
    for i, t in enumerate(src["turns"]):
        for j, c in enumerate(t["tool_calls"]):
            at = f"/sources/turns/{i}/tool_calls/{j}/arguments"
            require(c["arguments_pointer"] == at, "BUNDLE_RECOMPUTE",
                    f"turn {t['turn_index']}, call {j}: arguments_pointer {c['arguments_pointer']!r} is not the call's location {at!r}")
    require(src["transcript_sha256"] == H(jb(src["turns"])), "BUNDLE_RECOMPUTE",
            "sources.transcript_sha256 is not the digest of the bundle's turns")


def _case_split(text):
    """`text` with a space at each camel-case word boundary: before an upper-case letter that follows a lower-case letter
    or a digit, or that follows an upper-case letter and comes before a lower-case one ('neverDisclose', 'PINCode')."""
    if text.isascii():
        return CAMEL.sub(" ", text)
    out = []
    for i, ch in enumerate(text):
        if i and ch.isupper():
            p = text[i - 1]
            if p.islower() or p.isdigit() or (p.isupper() and i + 1 < len(text) and text[i + 1].islower()):
                out.append(" ")
        out.append(ch)
    return "".join(out)


def words(text):
    """The words of a text as `Withheld` compares them (L3 fix round 2: verbatim, normalized, case-folded, snake-, kebab-
    and camel-case folded): its compatibility decomposition (NFKD: full-width and mathematical letters, ligatures) without
    combining marks and without invisible characters (format, private-use, default-ignorable), a control character read
    as a space, look-alike letters read as Latin (`LOOKALIKE`), camel-case boundaries split (`_case_split`), then casefold;
    a word is a run of letters and digits, every other character ('_', '-', '.', a space, ...) separates words. L3 fix
    round 4: a decimal digit of any script (Unicode category Nd: Arabic-Indic, Devanagari, ...) reads as its ASCII digit
    (`ascii_digit`)."""
    if text.isascii():
        return WORD.findall(_case_split(text).lower())
    t = unicodedata.normalize("NFKD", text)
    t = "".join(" " if unicodedata.category(ch) == "Cc" else ascii_digit(ch) for ch in t
                if unicodedata.category(ch) not in DROPPED and ord(ch) not in IGNORABLE)
    t = _case_split(t.translate(LOOKALIKE)).casefold()
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if unicodedata.category(ch) not in DROPPED)
    return WORD.findall(t)


def ascii_digit(ch):
    """`ch`, or its ASCII digit when it is a decimal digit of another script (Unicode category Nd; L3 fix round 4)."""
    if ch.isascii() or unicodedata.category(ch) != "Nd":
        return ch
    return str(unicodedata.decimal(ch))


def string_leaves(value, path=()):
    """(path, string) for every string of a JSON value, member names included (at the path of their object plus None);
    found without recursion."""
    out, stack = [], [(value, path)]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                out.append((p + (None,), k))
                stack.append((v, p + (k,)))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in enumerate(o))
        elif isinstance(o, str):
            out.append((p, o))
    return out


_PUBLIC = weakref.WeakKeyDictionary()     # loaded release -> its public runs (dies with the caller's release object)


def public_runs(eio):
    """{n: the runs of n consecutive words} (n = 1 .. CONTENT_WORDS) of the texts the release itself publishes, every string
    of its modules and of the limitation catalogue: public vocabulary, never withheld content (L3 fix round 2; a control
    title such as '... for human review' may share words with a system prompt). Read once per loaded release object, held
    only as long as the caller holds that object (a weak reference)."""
    runs = _PUBLIC.get(eio)
    if runs is None:
        texts = [s for _, s in string_leaves(list(eio.doc.values()))]
        texts += [s for _, s in string_leaves(json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8")))]
        runs = _PUBLIC[eio] = {n: frozenset(x) for n, x in _word_runs(texts).items()}
    return runs


def json_leaves(value):
    """The strings of a JSON value and the JSON text of its numbers (member names left out), found without recursion."""
    out, stack = [], [value]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            stack.extend(o.values())
        elif isinstance(o, (list, tuple)):
            stack.extend(o)
        elif isinstance(o, str):
            out.append(o)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out.append(json.dumps(o))
    return out


def _word_runs(texts):
    """{n: the runs of n consecutive words of any of `texts`} for n = 1 .. CONTENT_WORDS."""
    runs = {n: set() for n in range(1, CONTENT_WORDS + 1)}
    for text in texts:
        w = words(text)
        for n in runs:
            runs[n].update(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    return runs


def _holds(w, runs):
    """Whether the words `w` hold a run of `runs`: CONTENT_WORDS consecutive words, or all of `w` when it has fewer."""
    n = min(len(w), CONTENT_WORDS)
    return n > 0 and any(tuple(w[i:i + n]) in runs[n] for i in range(len(w) - n + 1))


class Withheld:
    """The confidential content a bundle carries, which no producer-chosen term or name of a record may reproduce (L3 fix
    round 1, issue 1): the texts of the embedded context artifacts that PROD-43 withholds, each read as the most
    restrictive declaration of its content (`evidence.context_refs.effective`), and the values of every tool call's
    arguments and result and of every state snapshot, which a record carries only as digests (PROD-41, 03 §13.1). A text
    reproduces a withheld text when its words (`words`) hold `CONTENT_WORDS` consecutive words of it, or all its words in
    order when it has fewer; it reproduces a value when its words hold the value's words, the whole value, for a value that
    identifies (`identifying`: two words or more, a digit or an '@'; a one-word value such as 'lookup' is vocabulary, not
    a subject). Content the bundle does not carry (a digest-only artifact) cannot be recognised: ACCEPTED_DEVIATIONS D-40.

    L3 fix round 4: a subject is any scalar of a tool call's arguments or result or of a state snapshot (a number read
    as its JSON text, so a card number sent as a JSON number is one), and any PROD-42 identifying-class match of a turn's
    question or answer (`turn_subjects`: a value the user or the agent states that no tool call carries).

    L3 fix round 2: `carried` is the rule for every other text of the record (the names a producer declares, the layout
    names, pointers, labels and keys: `check_withheld_names`; every string of the record: `record_content_problems`). A
    text carries withheld content when its words hold `CONTENT_WORDS` consecutive words of a withheld text (all its words
    when the withheld text has fewer), or all the words of a value that names a subject (`subject_value`). Not counted: a
    run the release itself publishes (`public_runs`), and a run inside one token of the withheld text that is the file name
    of a declared context artifact ('credit_policy.md' in a system prompt: the record carries the declared names)."""

    def __init__(self, src, eio):
        arts, texts = src["context_artifacts"], src["context_texts"]
        conf = ev_context.confidential_digests(arts, texts)
        withheld = [texts[a["name"]] for a in embedded(arts) if a["name"] in texts
                    and ev_context.withheld(ev_context.effective(a, conf, texts[a["name"]])["data_class"])]
        values = [x for t in src["turns"] for c in t["tool_calls"] for x in json_leaves([c["arguments"], c.get("result")])]
        values += [x for t in src["turns"] for x in json_leaves(t.get("state"))]
        self.texts = _word_runs(withheld)
        self.values = {}                                  # n -> the word tuples of the identifying values of n words
        for v in values:
            w = words(v)
            if identifying(v, w):
                self.values.setdefault(len(w), set()).add(tuple(w))
        # round 2: the record-wide rule (`carried`); a token of a withheld text is read as its words (`words`)
        self.tokens = {tuple(words(x)) for text in withheld for x in text.split()}
        # round 3: the tools the bundle observes (its tool calls) or declares (a public or internal tool schema's names)
        self.tools = {c["name"] for t in src["turns"] for c in t["tool_calls"] if isinstance(c.get("name"), str)}
        self.tools |= declared_tools(arts, texts, conf)
        files = {tuple(words(n)) for a in arts for n in (a["name"], a["name"].rsplit("/", 1)[-1]) if FILE_NAME.fullmatch(n)}
        # L3 fix round 4: every scalar of the tool calls and state snapshots (a number as its JSON text; booleans and
        # null left out), and the PROD-42 identifying-class matches of the turn texts (`turn_subjects`)
        subjects = values + turn_subjects(src["turns"])
        subjects = [w for w in (tuple(words(v)) for v in subjects if subject_value(v)) if w]
        self.content, self.subjects = {}, {}
        if not withheld and not subjects:
            return
        public = public_runs(eio)
        for text in withheld:
            seq = [(w, k, tuple(words(x)) in files) for k, x in enumerate(text.split()) for w in words(x)]
            n = min(CONTENT_WORDS, len(seq))
            for i in range(len(seq) - n + 1):
                part = seq[i:i + n]
                run = tuple(w for w, _, _ in part)
                if n and not (part[0][2] and part[0][1] == part[-1][1]) and run not in public.get(n, ()):
                    self.content.setdefault(n, set()).add(run)
        for w in subjects:
            n = len(w)
            if not all(tuple(w[i:i + min(n, CONTENT_WORDS)]) in public.get(min(n, CONTENT_WORDS), ())
                       for i in range(n - min(n, CONTENT_WORDS) + 1)):
                self.subjects.setdefault(n, set()).add(w)

    def names_token(self, name):
        """Whether a withheld text names the tool `name` as a whole token (the same words: 'flag_for_human_review' in a
        system prompt); such a tool-call name is a transcript observation the record carries (ACCEPTED_DEVIATIONS D-41).
        L3 fix round 3: only an identifier-shaped name (`IDENT`) of a tool the bundle observes (a tool call) or declares (a
        public or internal tool schema: `declared_tools`), and not itself of an identifying class (`identifying_words`: a
        secret key or an account number in a withheld text is not a tool name); any other name is checked."""
        return (isinstance(name, str) and IDENT.fullmatch(name) is not None and name in self.tools
                and not identifying_words(words(name)) and tuple(words(name)) in self.tokens)

    def reproduced(self, text, *, artifacts=True):
        """Why `text` may not reach a record, or None: it reproduces a withheld artifact's text (unless `artifacts` is
        false) or a tool-call or state value."""
        w = words(text)
        if artifacts and _holds(w, self.texts):
            return "reproduces the text of a withheld context artifact (PROD-43)"
        if any(tuple(w[i:i + n]) in self.values.get(n, ()) for n in range(1, len(w) + 1) for i in range(len(w) - n + 1)):
            return "reproduces a tool-call or state value, which a record carries only as a digest (PROD-41, 03 §13.1)"
        return None

    def carried(self, text):
        """Why `text` may not be written into a record, or None (L3 fix round 2, the record-wide rule). L3 fix round 3: a
        text is also read with its percent-encoding and JSON Pointer escapes decoded (`decoded`)."""
        if not self.content and not self.subjects:
            return None
        d = decoded(text)
        for t in (text,) if d == text else (text, d):
            w = words(t)
            for n, runs in self.content.items():
                if any(tuple(w[i:i + n]) in runs for i in range(len(w) - n + 1)):
                    return "carries the text of a withheld context artifact (PROD-43)"
            for n, runs in self.subjects.items():
                if any(tuple(w[i:i + n]) in runs for i in range(len(w) - n + 1)):
                    return "carries a tool-call or state value, which a record carries only as a digest (PROD-41, 03 §13.1)"
        return None


def turn_subjects(turns):
    """The PROD-42 identifying-class matches of the turns' questions and answers (L3 fix round 4): e-mail addresses,
    national ids (the SSN form, an IBAN), Luhn-valid card numbers, secrets, and the four digits after 'last 4' or 'ssn',
    found as `evidence.redaction` finds them, on the text with every decimal digit read as its ASCII digit."""
    out = []
    for t in turns:
        for field in ("question", "answer"):
            text = t.get(field)
            if not isinstance(text, str) or not text:
                continue
            text = "".join(ascii_digit(ch) for ch in text)
            out += [m.group() for rx in (redaction.EMAIL, redaction.SSN, redaction.IBAN, redaction.SECRET) for m in rx.finditer(text)]
            out += [m.group() for m in redaction.PAN.finditer(text) if redaction.luhn(re.sub(r"\D", "", m.group()))]
            out += [m.group(3) for m in redaction.LAST4.finditer(text)]
    return out


JSON_U = re.compile(r"\\u([dD][89abAB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})|\\u([0-9a-fA-F]{4})")


def _json_u(m):
    if m.group(3) is None:                              # a surrogate pair: one code point
        return chr(0x10000 + ((int(m.group(1), 16) - 0xD800) << 10) + int(m.group(2), 16) - 0xDC00)
    c = int(m.group(3), 16)
    return "\ufffd" if 0xD800 <= c <= 0xDFFF else chr(c)


def decoded(text):
    """`text` with its percent-encoding (RFC 3986) and its JSON Pointer escapes ('~1', '~0'; RFC 6901) decoded, as the
    record-wide rule also reads it (L3 fix round 3); the text itself when it holds neither. L3 fix round 4: JSON's
    '\\uXXXX' escapes are decoded first (a surrogate pair as its code point, a lone surrogate as U+FFFD)."""
    if "\\u" in text:
        text = JSON_U.sub(_json_u, text)
    if "%" not in text and "~" not in text:
        return text
    return urllib.parse.unquote(text, errors="replace").replace("~1", "/").replace("~0", "~")


def identifying_words(w):
    """Whether the words `w` of a value are of an identifying class of PROD-42 (L3 fix round 3): a run of four digits or
    more ('0000', a card, account or phone number), two number groups or more ('123-45-6789', '312 555 0147'), or a word of
    letters and digits ('ACCT88419372')."""
    return any((x.isdigit() and len(x) >= 4) or (not x.isdigit() and any(ch.isdigit() for ch in x)) for x in w) or (
        len(w) >= 2 and all(x.isdigit() for x in w))


def subject_value(value):
    """Whether a tool-call or state string names a subject for the record-wide rule (`Withheld.carried`): it has an '@', or
    two words or more of which one is not a number ('synthetic-recipient@example.invalid', 'Zorvath LZK Holdings'), or (L3 fix round 3)
    its words are of an identifying class of PROD-42 (`identifying_words`: '123-45-6789', '4111 1111 1111 1111',
    '312 555 0147', 'ACCT88419372', '0000'), unless it is one plain decimal number of fewer than four digits in a run
    (`DECIMAL`: '0.5', '12'). One word and a short number ('lookup', '42', '0.5') are left out: a record states counts,
    indexes and scores."""
    w = words(value)
    if not w:
        return False
    if "@" in value or (len(w) >= 2 and any(not x.isdigit() for x in w)):
        return True
    if DECIMAL.fullmatch(value) is not None:
        return any(len(x) >= 4 for x in w)
    return identifying_words(w)


def declared_tools(arts, texts, conf):
    """The tool names a public or internal embedded tool schema declares (L3 fix round 3): every identifier-shaped string
    under a member `name` of its JSON text (none when the text is not JSON)."""
    out = set()
    for a in embedded(arts):
        if a["artifact_kind"] != "eio.artifact.tool-schema" or a["name"] not in texts or ev_context.withheld(
                ev_context.effective(a, conf, texts[a["name"]])["data_class"]):
            continue
        try:
            doc = json.loads(texts[a["name"]])
        except (ValueError, RecursionError):
            continue
        stack = [doc]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                v = o.get("name")
                if isinstance(v, str) and IDENT.fullmatch(v):
                    out.add(v)
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return out


def identifying(value, w):
    """Whether a tool-call or state value identifies a subject (`Withheld`): it has two words or more, a digit or an '@'."""
    return bool(w) and (len(w) >= 2 or any(ch.isdigit() for ch in value) or "@" in value)


def release_terms(eio):
    """Every checklist term of the release's context criteria: public vocabulary."""
    return {q for c in eio.criteria.values() for x in c.get("controls") or [] for q in x["requires_any"]}


def portable_name(name):
    """Whether `name` is a portable relative file name: '/'-separated segments of POSIX portable file name characters, no
    segment starting or ending with '.', at most NAME_MAX characters."""
    return len(name) <= NAME_MAX and all(PORTABLE.fullmatch(x) is not None and not x.endswith(".") for x in name.split("/"))


class SearchRules:
    """What a producer-chosen search input of a record may be (L3 fix round 1, issue 1). A native producer's context search
    names declared context artifacts and searches release checklist terms; an adapter producer (a stored archive's own
    checklist) may also name a file that is not declared, as a portable relative file name, and search a printable ASCII
    phrase of its own checklist (ACCEPTED_DEVIATIONS D-40: carried in clear until L5a). A named-call term is at most
    TERM_MAX characters. A term that is not a release checklist term (nor, for a named call, part of a declared tool name
    or of a tool schema the record may quote) and a name that is not declared reproduce no confidential content the bundle
    carries (`Withheld`); an undeclared name that is the file name of a declared artifact may be text of a withheld
    artifact. L3 fix round 2: only a name equal to that file name is exempt (not a path ending in it), and only a tool
    schema whose class is public or internal (as PROD-43 reads it: `evidence.context_refs.effective`) exempts a term; a
    declared name is checked with the other declared names (`check_withheld_names`)."""

    def __init__(self, eio, bundle, guard=None):
        src = bundle["sources"]
        self.adapter = bundle["provenance"]["producer"]["kind"] == "adapter"
        self.declared = {a["name"] for a in src["context_artifacts"]}
        self.basenames = {n.rsplit("/", 1)[-1] for n in self.declared}
        self.public = release_terms(eio)
        self.guard = guard if guard is not None else Withheld(src, eio)
        texts = src["context_texts"]
        conf = ev_context.confidential_digests(src["context_artifacts"], texts)
        self.tools = [c["name"].lower() for t in src["turns"] for c in t["tool_calls"]]
        self.tools += [texts[a["name"]].lower() for a in embedded(src["context_artifacts"])
                       if a["artifact_kind"] == "eio.artifact.tool-schema" and a["name"] in texts
                       and not ev_context.withheld(ev_context.effective(a, conf, texts[a["name"]])["data_class"])]

    def term_problem(self, q, allowed):
        """Why the context-search term `q` may not reach a record, or None; `allowed` are the release terms a native
        producer may search here (a context gap's control's, else every checklist term)."""
        if q in allowed or (self.adapter and q in self.public):
            return None
        if not self.adapter:
            return "is not a release checklist term of this search (a native producer searches with the release's terms)"
        if len(q) > TERM_MAX or PHRASE.fullmatch(q) is None:
            return f"is not a checklist phrase (printable ASCII with a letter or digit, at most {TERM_MAX} characters)"
        return self.guard.reproduced(q)

    def name_problem(self, f):
        """Why the searched file name `f` may not reach a record, or None (a declared name: `check_withheld_names`)."""
        if f in self.declared:
            return None
        if not self.adapter:
            return "is not a declared context artifact (a native producer searches its declared artifacts)"
        if not portable_name(f):
            return f"is not a portable relative file name (segments of A-Z a-z 0-9 . _ -, at most {NAME_MAX} characters)"
        return self.guard.reproduced(f, artifacts=f not in self.basenames)

    def call_term_problem(self, q):
        """Why the named-call term `q` (a lower-case ASCII name) may not reach a record, or None."""
        if len(q) > TERM_MAX:
            return f"is longer than {TERM_MAX} characters"
        if q in self.public or any(q in x for x in self.tools):
            return None
        return self.guard.reproduced(q)


def check_withheld_names(bundle, guard):
    """L3 fix round 2: every name a producer chooses that the record carries holds no withheld content (`Withheld.carried`):
    the layout names (`turn_source_ref`, `calls_field`, `state_field`), the archive pointer's keys and pointers and every
    tool call's argument pointer, the declared context-artifact names (provenance.inputs, the AI-BOM, a ref's source_ref, a
    context search's file names), each retrieval source, each tool-call name (unless a withheld text names that tool: a
    whole token of it, 'flag_for_human_review' in a system prompt), and the scenario labels and context-link keys (the
    record's evidence turns, findings, claims and links). A snake-, kebab- or camel-case spelling of a withheld line is the
    line (`words`). Fails closed with `BUNDLE_RECOMPUTE`."""
    src = bundle["sources"]
    items = [(f"sources.{k}", src[k]) for k in ("turn_source_ref", "calls_field", "state_field") if k in src]
    for k, v in src["archive_pointer"].items():
        if k != "archive_sha256":
            items += [("an archive-pointer key", k), (f"the archive pointer of {k!r:.40}", v)]
    items += [("the context-artifact name", a["name"]) for a in src["context_artifacts"]]
    for t in src["turns"]:
        u = t["turn_index"]
        items += [(f"turn {u}: the arguments pointer", c["arguments_pointer"]) for c in t["tool_calls"]]
        items += [(f"turn {u}: the tool-call name", c["name"]) for c in t["tool_calls"] if not guard.names_token(c["name"])]
        items += [(f"turn {u}: the retrieval source", x["source"]) for x in t["retrievals"] if isinstance(x.get("source"), str)]
    decl = bundle.get("producer_declared") or {}
    sc = decl.get("scenarios")
    if sc:
        items += [("the scenario label", x) for x in [t["label"] for t in sc["turns"]] + list(sc["severity"])]
    cl = decl.get("context_links")
    if cl:
        items += [("the context-link key", k) for k in list(cl["rows"]) + list(cl["claims"].values())]
    for what, text in items:
        why = guard.carried(text) if isinstance(text, str) else None
        require(why is None, "BUNDLE_RECOMPUTE", f"{what} {text!r:.80} {why}: it is written into the record (L3 fix round 2)")


def _in_clear(path):
    """Whether the bundle string at `path` (None as the last element: a member name) reaches a record in clear: everything
    but the context texts, a turn's question, answer and state snapshot, a tool call's arguments and result, and a
    retrieval's members other than its source (a record carries these as digests or through a ref's PROD-42 excerpt, which
    is read as the record's excerpt: `bundle_content_problems`)."""
    if path == ("bundle_version",):           # the bundle format version (a schema constant) never reaches a record
        return False
    if path[:1] == ("native_scoring",):
        # Native scorer declarations remain in the local source bundle. No
        # identifier, assessor label or context value is projected into PER.
        return False
    if path[:2] == ("sources", "context_texts") and len(path) >= 3:
        return False
    if path[:2] == ("sources", "turns") and len(path) >= 4:
        if path[3] in ("question", "answer", "state"):
            return False
        if path[3] == "tool_calls" and len(path) >= 6 and path[5] in ("arguments", "result"):
            return False
        if path[3] == "retrievals" and len(path) >= 6 and path[5] != "source":
            return False
    return True


def bundle_content_problems(bundle, guard):
    """L3 fix round 2, the bundle's side of the record-wide rule (`record_content_problems`): the JSON Pointers of the
    strings of the bundle (member names included) that a record carries in clear (`_in_clear`) and that carry withheld
    content (`Withheld.carried`). Exempt as in the record: the excerpt of a turn span (D-43, D-48), the agent description
    (`provenance.agent` goal and role: D-41) and a tool-call name that a withheld text names as a whole token (D-41)."""
    refs = bundle["graph"]["refs"]
    out = []
    for path, text in string_leaves(bundle):
        if not _in_clear(path) or path in (("provenance", "agent", "goal"), ("provenance", "agent", "role")):
            continue
        if path[:2] == ("graph", "refs") and len(path) == 4 and path[3] == "excerpt" and (
                refs[path[2]]["source_type"] in TURN_EXCERPT):
            continue
        if guard.names_token(text) and ((path[:2] == ("sources", "turns") and len(path) == 6 and path[3] == "tool_calls"
                                      and path[5] == "name") or (path[:2] == ("graph", "refs") and path[3:] == ("tool", "name"))):
            continue
        if guard.carried(text) is not None:
            out.append("/" + "/".join("{member name}" if x is None else str(x) for x in path))
    return out


def record_content_problems(rec, guard):
    """L3 fix round 2, the record-wide rule: the JSON Pointers of the strings of the projected record (member names
    included) that carry withheld content (`Withheld.carried`). Exempt, each field with its recorded reason: the PROD-42
    excerpt of a turn span, `/evidence/refs/<i>/excerpt` of a ref over AGENT_ANSWER or USER_INPUT (the transcript's own
    words: the agent may quote a withheld text or a tool-call value, ACCEPTED_DEVIATIONS D-43; the user's question names
    the subject the agent looks up and shares common phrases with a withheld policy, D-48; both L5b; a policy excerpt is
    checked), the agent description `/subject/agent/goal` and `/subject/agent/role` (the producer's declaration: D-41,
    hash and pointer at S2), and a tool-call name that a withheld text names as a whole token (a transcript observation:
    D-41, L5b)."""
    refs = rec["evidence"]["refs"]
    out = []
    for path, text in string_leaves(rec):
        if path in AGENT_DESCRIPTION:
            continue
        if path[:2] == ("evidence", "refs") and len(path) == 4 and path[3] == "excerpt" and (
                refs[path[2]]["source_type"] in TURN_EXCERPT):
            continue
        if guard.names_token(text) and ((path[:2] == ("evidence", "turns") and len(path) == 6 and path[3] == "tool_calls"
                                      and path[5] == "name") or (path[:2] == ("evidence", "refs") and path[3:] == ("tool", "name"))):
            continue
        if guard.carried(text) is not None:
            out.append("/" + "/".join("{member name}" if x is None else str(x) for x in path))
    return out


# ---------------------------------------------------------------- L3 fix round 4: the identifying-shape backstop
# Every string of the bundle that a record carries in clear (`_in_clear`: every producer string but the context texts,
# the turn texts and state, the tool-call values and the retrieval bodies, which a record carries as digests or through a
# PROD-42 excerpt) holds no identifying-shaped token, whether or not the value is a known subject (`shape_problems`). A
# token is read on the text's shape reading (`shape_text`). The shapes (`SHAPES`), each a class of PROD-42's identifying
# values written in any grouping:
SHAPE_SEPARATOR = r"[\s\-‐-―−﹘﹣._/()+,:;#*~|\\'\"]"     # between the digits of one value
SHAPE_DIGITS = re.compile(r"[0-9](?:" + SHAPE_SEPARATOR + r"*[0-9])*")   # 4+ digits: split, regrouped or flat
SHAPE_GROUPS = re.compile(r"[0-9]+(?:[-./ ][0-9]+)+")                   # 2+ digit groups joined by - . / or a space
SHAPE_TOKEN = re.compile(r"[^\W_]+")                                   # letters and digits: 6+ with both
SHAPE_HEX = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-f]{16,}|[0-9A-F]{16,})(?![0-9A-Za-z])")   # 16+ hex characters
SHAPE_BASE64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")                   # 16+ base64 characters, mixed, with + or /
SHAPE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SHAPE_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/?#@]+@")    # a URL with credentials (user[:password]@)
SHAPE_SECRET = re.compile(r"(?:(?:sk|pk|rk)[-_](?:live|test|proj)[-_]|sk-|AKIA|gh[pousr]_|xox[abprs]-|glpat-)[A-Za-z0-9_\-]{8,}")
# The allowlist: the legitimate shapes the gated inputs use in these fields (measured, fix round 4), each with its reason.
# A field's value is exempt only when it is exactly the form (a digest, an id, a run id, a timestamp, a version, a score,
# a string the release publishes); inside other text, a short plain decimal and two algorithm names.
_DIGEST_KEY = re.compile(r"(?:.*_)?sha256|plan_hash|module_hash|selected_digest")
_HEX = "[0-9a-f]"
# A model identifier, the one exemption of the shape backstop that names no recorded form (approved by the maintainer
# for 0.8.0, a privacy-rule change): model names carry release dates and versions ('gpt-4o-2024-08-06',
# 'claude-sonnet-4-5-20250929', 'anthropic/claude-opus-4-1@20250805'). An optional 'vendor/' or 'vendor:' prefix, then
# letters, digits, '.', '_' and '-', and an optional '@' date or version; at most 100 characters, no space, no e-mail
# address or credentials (an '@' takes only a date or version), no run of sixteen hex characters or of twenty-four
# letters and digits. It applies only in the fields that name a model (`SHAPE_FORMS`); an agent id, a tool name or any
# other field keeps the full rule. The independent verifier keeps the same pattern (`validation.validate._MODEL_ID`;
# tests/test_model_identifiers.py checks that they are equal).
MODEL_ID = (r"(?=.{1,100}\Z)(?![^/:]*[A-Za-z0-9]{24})(?!.*[0-9A-Fa-f]{16})"
            r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,39}[/:])?[A-Za-z0-9][A-Za-z0-9._-]*"
            r"(?:@(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2}|v?[0-9]{1,4}(?:\.[0-9]{1,4})*))?")


def safe_model_identifier(text):
    """A model-shaped value is public only if PROD-42 finds no sensitive token in it."""
    return bool(re.fullmatch(MODEL_ID, text)) and not redaction.redact(text)[1] and not SHAPE_SECRET.search(text)


SHAPE_FORMS = (
    ("a digest (sha256:<64 hex>) in a digest member (its schema pattern; recomputed or declared)",
     lambda p, lid: isinstance(p[-1], str) and _DIGEST_KEY.fullmatch(p[-1]) is not None, re.compile(f"sha256:{_HEX}{{64}}")),
    ("a claim or ref id (20 hex, `semantics.ids`): the claims', refs', ballots', trials', metrics' and limitations' ids, a context link's claim",
     lambda p, lid: _at(p, "claims", 0, "id") or _at(p, "claims", 0, "evidence", 0) or _at(p, "claims", 0, "counterevidence", 0)
     or _at(p, "graph", "refs", 0, "id") or _at(p, "ballots", "ballots", 0, "claim_id") or _at(p, "ballots", "pooled_claims", 0)
     or _at(p, "trials", "records", 0, "claim_id") or _at(p, "limitations", 0, "params", "claim_id")
     or _at(p, "limitations", 0, "params", "ref") or _at(p, "producer_declared", "context_links", "claims", None)
     or _at(p, "producer_declared", "score_inputs", "readiness", "cap_claims", 0)
     or _at(p, "producer_declared", "score_inputs", "metrics", 0, "members", 0)
     or _at(p, "producer_declared", "score_inputs", "metrics", 0, "contributions", 0, 0), re.compile(f"{_HEX}{{20}}")),
    ("a run id: a UUID, or 'archive:' and the archive digest (a report without a run id)",
     lambda p, lid: _at(p, "header", "run_id") or _at(p, "provenance", "record", "run", "run_id") or _at(p, "claims", 0, "run_id"),
     re.compile(f"{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}|archive:{_HEX}{{64}}")),
    ("a short release digest (16 hex): the ontology digest, the capsule lock digest",
     lambda p, lid: _at(p, "header", "eio", "ontology_digest") or _at(p, "header", "producer_eio", "ontology_digest")
     or _at(p, "provenance", "capsule", "lock_digest"), re.compile(f"{_HEX}{{16}}")),
    ("a source revision (a 40-hex commit)",
     lambda p, lid: _at(p, "provenance", "producer", "revision") or _at(p, "provenance", "record", "producer", "source_revision"),
     re.compile(f"{_HEX}{{40}}")),
    ("a run configuration fingerprint (24 hex)", lambda p, lid: _at(p, "provenance", "record", "run", "config_fingerprint"),
     re.compile(f"{_HEX}{{24}}")),
    ("a checks version (a 12-hex commit), also as a parameter of per.lim.checks_version.mismatch",
     lambda p, lid: _at(p, "provenance", "record", "inputs", "checks_version") or _param(p, lid, "per.lim.checks_version.mismatch",
                                                                                   "converter", "producer"),
     re.compile(f"{_HEX}{{12}}")),
    ("a run timestamp (RFC 3339)",
     lambda p, lid: _at(p, "provenance", "record", "run", "started_at") or _at(p, "provenance", "record", "run", "completed_at"),
     re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})")),
    ("a version (at most three groups of at most two digits, 'rcN', '.devN', a '+label') in a version member",
     lambda p, lid: p[-1] in ("version", "predicate_version", "module_version", "release"),
     re.compile(r"[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}(?:rc[0-9]{1,2}|\.dev[0-9])?(?:\+[a-z]{1,16})?")),
    ("a model identifier (`MODEL_ID`) in a field that names a model: the agent under test's, a model-graded claim's",
     lambda p, lid: _at(p, "provenance", "agent", "model") or _at(p, "claims", 0, "provenance", "model"),
     re.compile(MODEL_ID)),
)
# a short plain decimal (1-3 digits, a point, 1-2 digits) is not a digit run or group: a score, a rate or a model family
# version ('0.5', '12.75', '82.0', 'gpt-4.1-nano'); ACCEPTED_DEVIATIONS D-54
SHAPE_DECIMAL = re.compile(r"[0-9]{1,3}\.[0-9]{1,2}")
SHAPE_WORDS = frozenset(("base64", "sha256"))                  # algorithm names: the harness's trap names, digest members
_RELEASE_STRINGS = weakref.WeakKeyDictionary()                 # loaded release -> every string it publishes


def _at(path, *want):
    """Whether `path` is `want` (0: any list index, '*': any member)."""
    return len(path) == len(want) and all(w == "*" and isinstance(x, str) or (w == 0 and type(x) is int) or w == x
                                          for w, x in zip(want, path))


def _param(path, lid, want, *names):
    """Whether `path` is one of the parameters `names` of a bundle limitation whose id `lid` is `want`."""
    return lid == want and _at(path, "limitations", 0, "params", "*") and path[3] in names


def release_strings(eio):
    """Every string the release publishes (its modules and the limitation catalogue: public text), read once per loaded
    release object."""
    out = _RELEASE_STRINGS.get(eio)
    if out is None:
        out = _RELEASE_STRINGS[eio] = frozenset(
            [s for _, s in string_leaves(list(eio.doc.values()))]
            + [s for _, s in string_leaves(json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8")))])
    return out


def shape_text(text):
    """A text as the backstop reads it: its compatibility decomposition (NFKD) without combining marks and invisible
    characters (format, private-use, default-ignorable: a zero-width space inside a number does not split it), a control
    character as a space, every decimal digit of any script as its ASCII digit (`ascii_digit`), look-alike letters as
    Latin (`LOOKALIKE`), and JSON '\\\\u' escapes, percent-encoding and JSON Pointer escapes decoded (`decoded`)."""
    t = unicodedata.normalize("NFKD", decoded(text))
    return "".join(" " if unicodedata.category(ch) == "Cc" else ascii_digit(ch) for ch in t
                   if unicodedata.category(ch) not in DROPPED and ord(ch) not in IGNORABLE).translate(LOOKALIKE)


def identifying_shapes(text):
    """The identifying-shaped tokens of `text` (L3 fix round 4), as (shape, token): 'digits' (four digits or more, the
    separators between them removed), 'groups' (two digit groups or more joined by '-', '.', '/' or a space: a
    partial date or a short id), 'alphanumeric' (a word of six letters and digits or more, with both), 'hex' (sixteen
    hex characters or more), 'base64' (sixteen base64 characters or more, both cases, a digit and a '+' or '/'),
    'email', 'userinfo' (a URL with credentials), 'secret' (a key prefix: PROD-42's secret class and its sk_ forms).
    A short plain decimal (`SHAPE_DECIMAL`: '0.5', '12.75', the '4.1' of 'gpt-4.1-nano') is neither digits nor groups."""
    t = shape_text(text)
    out = [("digits", m.group()) for m in SHAPE_DIGITS.finditer(t) if sum(ch.isdigit() for ch in m.group()) >= 4
           and not SHAPE_DECIMAL.fullmatch(m.group())]
    out += [("groups", m.group()) for m in SHAPE_GROUPS.finditer(t) if sum(ch.isdigit() for ch in m.group()) < 4
            and not SHAPE_DECIMAL.fullmatch(m.group())]
    out += [("alphanumeric", x) for x in SHAPE_TOKEN.findall(t) if len(x) >= 6 and not x.isdigit()
            and any(ch.isdigit() for ch in x) and x.casefold() not in SHAPE_WORDS]
    out += [("hex", m.group()) for m in SHAPE_HEX.finditer(t)]
    out += [("base64", m.group()) for m in SHAPE_BASE64.finditer(t) if ("+" in m.group() or "/" in m.group())
            and any(ch.isdigit() for ch in m.group()) and any(ch.isupper() for ch in m.group()) and any(ch.islower() for ch in m.group())]
    for shape, rx in (("email", SHAPE_EMAIL), ("userinfo", SHAPE_USERINFO), ("secret", SHAPE_SECRET)):
        out += [(shape, m.group()) for m in rx.finditer(t)]
    return out


def shape_problems(bundle, eio):
    """L3 fix round 4, the shape backstop: the JSON Pointers (with the shapes found) of the strings of the bundle that a
    record carries in clear (`_in_clear`; member names included) that hold an identifying-shaped token
    (`identifying_shapes`), whether or not the value is a subject the bundle carries (`Withheld`): a producer's own free
    text (a capsule caveat, a policy or profile name, a persona, a label, a limitation parameter, a metric label, a
    provenance string, the agent description) never states an identifying value. Allowed, each with its reason: a value
    that is exactly one of `SHAPE_FORMS` in its field, a string the release publishes (`release_strings`), a short plain
    decimal (`SHAPE_DECIMAL`), the words of `SHAPE_WORDS`; not read: a ref's excerpt (PROD-42 redacts and recomputes
    it from the sources; ACCEPTED_DEVIATIONS D-43, D-48)."""
    lims = bundle.get("limitations") if isinstance(bundle.get("limitations"), list) else []
    public = release_strings(eio)
    out = []
    for path, text in string_leaves(bundle):
        if not _in_clear(path) or (path[:2] == ("graph", "refs") and len(path) == 4 and path[3] == "excerpt"):
            continue
        lid = lims[path[1]].get("id") if (len(path) == 4 and path[0] == "limitations" and path[2] == "params" and type(path[1])
                                          is int and path[1] < len(lims) and isinstance(lims[path[1]], dict)) else None
        if text in public or any(field(path, lid) and form.fullmatch(text) and
                                 (form.pattern != MODEL_ID or safe_model_identifier(text))
                                 for _, field, form in SHAPE_FORMS):
            continue
        found = identifying_shapes(text)
        if found:
            out.append("/" + "/".join("{member name}" if x is None else str(x) for x in path) + " (" + ", ".join(
                sorted({s for s, _ in found})) + ")")
    return out


def declared_sources(src):
    """The sources a ref that locates no text may name (`source_ref`): the turn source, the state field, a declared context
    artifact and a turn's retrieval source (L3 fix round 1, issue 1)."""
    out = {src["turn_source_ref"]} | {a["name"] for a in src["context_artifacts"]}
    out |= {x["source"] for t in src["turns"] for x in t["retrievals"] if isinstance(x.get("source"), str)}
    return out | ({src["state_field"]} if "state_field" in src else set())


def _call_absence(eio, r, src, turns, rules):
    """A typed absence over the declared tool-call list (contract §6.2 step 2, computed statements; review H-1). Its
    statement must hold over the bundle's own turns, and the ref must be the one the neutral builder makes from them:
    TA(t) (`evidence.refs.no_call_ref`), or the absence of a named call over listed turns that include t
    (`evidence.refs.no_matching_call_ref`), whose terms reach the record (`SearchRules.call_term_problem`; L3 fix round 1,
    issue 1). A true absence counts 0."""
    rid, t, ins = r["id"], r["turn_index"], r["statement"]["inputs"]
    require(ins.get("source") == src["calls_field"], "BUNDLE_RECOMPUTE",
            f"ref {rid}: the absence is not over the declared tool-call list {src['calls_field']!r}")
    require(t in turns, "BUNDLE_RECOMPUTE", f"ref {rid}: turn {t} is not in sources")
    if "episode_turns" in ins:
        ep, terms = ins["episode_turns"], ins.get("name_contains")
        require(isinstance(ep, list) and all(type(u) is int and u in turns for u in ep) and t in ep, "BUNDLE_RECOMPUTE",
                f"ref {rid}: the episode turns {ep!r} are not turns of sources that include turn {t}")
        # the formula lower-cases the call name, not the term: a term that is not lower case would never match (review R-5);
        # and a term is an ASCII name, so the statement text reads as what it counts (no quote, space or look-alike letter:
        # L2 exit D-35, F-8)
        require(isinstance(terms, list) and terms and all(isinstance(q, str) and CALL_TERM.fullmatch(q) for q in terms),
                "BUNDLE_RECOMPUTE", f"ref {rid}: name_contains {terms!r:.120} is not a list of lower-case ASCII names ({CALL_TERM.pattern})")
        for q in terms:
            why = rules.call_term_problem(q)
            require(why is None, "BUNDLE_RECOMPUTE", f"ref {rid}: the named-call term {q!r:.80} {why} (L3 fix round 1, issue 1)")
        hit = [c["name"] for u in ep for c in turns[u]["tool_calls"] if any(q in c["name"].lower() for q in terms)]
        require(not hit, "BUNDLE_RECOMPUTE", f"ref {rid}: the typed absence is false: turns {ep} call {hit}")
        want = no_matching_call_ref(eio, t, ep, terms, [], source_ref=src["turn_source_ref"], calls_field=src["calls_field"])
    else:
        n = len(turns[t]["tool_calls"])
        require(n == 0, "BUNDLE_RECOMPUTE", f"ref {rid}: the typed absence is false: turn {t} has {n} tool call(s)")
        want = no_call_ref(eio, t, [], source_ref=src["turn_source_ref"], calls_field=src["calls_field"])
    require(r == want, "BUNDLE_RECOMPUTE", f"ref {rid}: the typed absence does not recompute from sources")


def _plain_term(q):
    """A search term reads as what it searches for: in Unicode NFC, with no format, control or private-use character (a
    zero-width joiner inside a present word would make it 'absent'; L2 exit D-35, F-13)."""
    return unicodedata.normalize("NFC", q) == q and not any(unicodedata.category(ch) in ("Cf", "Cc", "Co") for ch in q)


def _spelling(name):
    """A context-artifact name as a reader that normalises it would read it: NFC, casefold, outer spaces removed."""
    return unicodedata.normalize("NFC", name).casefold().strip()


def check_context_search(what, files, chars, terms, texts, embedded_names, rules, allowed):
    """A search of context artifacts for terms (a context gap, or a context absence) recomputes over every embedded file
    it names (review H-1, R-4), whatever else it names: no term occurs, casefold, in any of them; and the characters
    searched are theirs when every file is embedded, at least theirs when some file is not (a file that is not embedded
    has its text in no source of the bundle: it adds characters, never hides a term). Each term is plain text (`_plain_term`),
    and a name that is not embedded does not spell an embedded artifact's name another way (it would not be searched:
    L2 exit D-35, F-13). The terms and names reach the record, so each is the release's or the bundle's (`rules`, a
    `SearchRules`; `allowed` are the release terms of this search; L3 fix round 1, issue 1). The search reads the casefold
    with the dot above an i dropped (`evidence.context_refs.fold`; L3 fix round 1, issue 7)."""
    require(isinstance(files, list) and files and all(isinstance(f, str) for f in files), "BUNDLE_RECOMPUTE",
            f"{what}: files_searched {files!r:.120} is not a list of artifact names")
    require(isinstance(terms, list) and terms and all(isinstance(q, str) and q for q in terms), "BUNDLE_RECOMPUTE",
            f"{what}: the terms {terms!r:.120} are not a list of non-empty terms")
    odd = [q for q in terms if not _plain_term(q)]
    require(not odd, "BUNDLE_RECOMPUTE", f"{what}: the term(s) {odd!r:.120} hold an invisible or non-NFC character, so the "
            "search would not read as the term (L2 exit D-35, F-13)")
    spelt = {_spelling(n): n for n in embedded_names}
    other = sorted(f for f in files if f not in embedded_names and _spelling(f) in spelt)
    require(not other, "BUNDLE_RECOMPUTE", f"{what}: files_searched {other!r:.120} spell an embedded artifact's name another "
            f"way ({sorted(spelt[_spelling(f)] for f in other)}), so the search would skip its text (L2 exit D-35, F-13)")
    for q in terms:
        why = rules.term_problem(q, allowed)
        require(why is None, "BUNDLE_RECOMPUTE", f"{what}: the term {q!r:.80} {why} (L3 fix round 1, issue 1)")
    for f in files:
        why = rules.name_problem(f)
        require(why is None, "BUNDLE_RECOMPUTE", f"{what}: files_searched names {f!r:.80}, which {why} (L3 fix round 1, issue 1)")
    require(type(chars) is int and chars >= 0, "BUNDLE_RECOMPUTE", f"{what}: chars_searched {chars!r} is not a count")
    emb = [f for f in files if f in embedded_names]
    folded = {f: ev_context.fold(texts[f]) for f in set(emb)}
    hit = sorted({q for f in emb for q in terms if ev_context.fold(q) in folded[f]})
    require(not hit, "BUNDLE_RECOMPUTE", f"{what}: the context search is false: {hit!r:.120} occur in {sorted(set(emb))}")
    n = sum(len(texts[f]) for f in emb)
    every = len(emb) == len(files)
    require(chars == n if every else chars >= n, "BUNDLE_RECOMPUTE",
            f"{what}: {chars} characters searched, recomputed {'' if every else 'at least '}{n} from the embedded artifacts")


def _context_absence(eio, r, texts, embedded_names, rules):
    """A context absence (TYPED_ABSENCE over POLICY_SOURCE) is always rebuilt (review H-1, R-4): its search recomputes over
    the embedded files it names (`check_context_search`, with every release checklist term allowed), and the ref is the one
    the neutral builder makes from its inputs (`evidence.context_refs.ctx_absence_ref`: id, statement, formula, a count
    of 0)."""
    ins = r["statement"]["inputs"]
    files, chars, terms = ins.get("files_searched"), ins.get("chars_searched"), ins.get("requires_any")
    check_context_search(f"ref {r['id']}", files, chars, terms, texts, embedded_names, rules, rules.public)
    want = ev_context.ctx_absence_ref(eio, files, chars, terms)
    require(r == want, "BUNDLE_RECOMPUTE", f"ref {r['id']}: the context absence does not recompute (evidence.context_refs.ctx_absence_ref)")


def _policy_span(eio, r, texts, artifacts):
    """A POLICY_SPAN points into a declared, embedded context artifact and recomputes from its text: offsets, span and
    source digests, id, and the excerpt (PROD-42; none, with `excerpt_redacted`, for model-confidential text, PROD-43, read
    fail-closed: `evidence.context_refs.withheld`). No rename of its source escapes the recompute (review H-1). An exact or
    casefold span quotes at least one character (L2 exit D-35, F-10)."""
    art = artifacts.get(r["source_ref"])
    require(art is not None and r["source_ref"] in texts, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a POLICY_SPAN points into {r['source_ref']!r}, which is not an embedded context artifact")
    text = texts[r["source_ref"]]
    require(H(text.encode("utf-8")) == art["sha256"], "BUNDLE_RECOMPUTE", f"ref {r['id']}: the artifact text does not recompute")
    a, b = r["char_start"], r["char_end"]
    require(isinstance(a, int) and isinstance(b, int) and 0 <= a <= b <= len(text), "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: offsets outside the artifact text")
    require(a < b or r["anchor"] not in QUOTE_ANCHORS, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: an {r['anchor']} span [{a}, {b}) quotes nothing (L2 exit D-35, F-10)")
    want = ev_context.policy_span_ref(eio, art, text, a, b, r["anchor"])
    require(r == want, "BUNDLE_RECOMPUTE", f"ref {r['id']}: the policy span does not recompute from the embedded artifact (PROD-42, PROD-43)")


def _state_fact(eio, r, src, turns):
    """A STATE_FACT over the state ledger (L2 exit D-34): the state snapshot that the bundle declares for the ref's turn
    (`sources.turns[].state`, under the name `sources.state_field`) is non-empty. It is rebuilt from that snapshot with the
    neutral builder (`evidence.refs.state_fact_ref`: its id over the snapshot's JCS text, anchor computed, valid from the
    turn, a statement that carries the snapshot only as its digest) and must equal it."""
    t = r["turn_index"]
    snap = turns[t]["state"]
    require(bool(snap), "BUNDLE_RECOMPUTE", f"ref {r['id']}: the state snapshot of turn {t} is empty, so it states no fact")
    want = state_fact_ref(eio, t, snap, source_ref=src["turn_source_ref"], state_field=src["state_field"])
    require(r == want, "BUNDLE_RECOMPUTE", f"ref {r['id']}: the state fact does not recompute from the declared state snapshot of turn {t}")


def _declared(eio, r, sources):
    """A ref that no recipe of EIO-Agents rebuilds from the bundle's sources (review R-1): a juror citation, an unlocated
    quote or question, and any kind over a source the bundle does not carry (a state ledger, a human review, a retrieval,
    a harness signal), or a calculation. Its text is in no source of the bundle, so it is accepted only as a ref that
    cannot prove and locates nothing: it is not witnessing anchored (under the release a CALCULATION, a TYPED_ABSENCE over
    the answer, a state ledger or a paired tool result, a STATE_* ref and a HUMAN_SIGNOFF with a witnessing anchor would
    count for proof), and it has no offsets, digests or excerpt (nothing it would quote can be checked: PROD-42, PROD-43).
    It may support a claim, never prove it. It carries no statement either (L2 exit D-31): nothing checks a declared
    statement against the bundle's sources, so it could quote them (03 §13.1: subjects only as digests), and the release's
    computed kinds are rebuilt or refused. What it names reaches the record, so it names a source the bundle declares
    (`declared_sources`) and carries no tool receipt (L3 fix round 1, issue 1). Nothing is downgraded: a declared ref
    that breaks a rule fails closed."""
    require(not eio.witnessing_anchored(r), "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a {r['kind']} ref over {r['source_type']} with anchor {r['anchor']} would witness agent behaviour, "
            "but EIO-Agents has no recipe that rebuilds it from the bundle's sources (a declared ref may support a claim, never prove it)")
    located = [k for k in LOCATORS if r.get(k) is not None] + [k for k in EXCERPT_FIELDS if k in r]
    require(not located, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a {r['kind']} ref over {r['source_type']} that EIO-Agents cannot rebuild from the bundle's sources "
            f"locates no text, but it carries {located}")
    require("statement" not in r, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a {r['kind']} ref over {r['source_type']} that EIO-Agents cannot rebuild from the bundle's sources "
            "carries a statement, which nothing checks against them (subjects only as digests, 03 §13.1)")
    # what it names reaches the record: a source the bundle declares, and no tool receipt (L3 fix round 1, issue 1)
    require(r["source_ref"] in sources, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a {r['kind']} ref over {r['source_type']} that EIO-Agents cannot rebuild names the source "
            f"{r['source_ref']!r:.80}, which the bundle does not declare (the turn source, the state field, a context artifact or "
            "a retrieval source; L3 fix round 1, issue 1)")
    require("tool" not in r, "BUNDLE_RECOMPUTE",
            f"ref {r['id']}: a {r['kind']} ref over {r['source_type']} carries a tool receipt, which only a TOOL_RECEIPT rebuilt "
            "from the declared tool calls carries (L3 fix round 1, issue 1)")


def recompute(eio, bundle, claims, refs, guard=None):
    """Step 2: recompute the ids and the refs from the bundle's own sources, per locator kind (turn spans, tool receipts,
    typed absences over tool calls and over context artifacts, policy spans), the episodes, a native bundle's pointers
    and transcript digest, and the pooled vote counts. `claims` are the bundle claims (parameters without `fidelity`),
    `refs` the graph refs by id. For every ref the witness flag, the source-type compatibility and the anchor rules follow
    from the release; a ref of a kind that the bundle's sources determine (a turn span, a tool receipt, a typed absence
    over tool calls or context artifacts, a policy span, a state fact over a declared state snapshot) is rebuilt with the
    neutral builder and must equal it; any other ref is declared (`_declared`): accepted only as a non-witnessing ref that
    locates no text and carries no statement."""
    h, src = bundle["header"], bundle["sources"]
    require(h["run_id"] == bundle["provenance"]["record"]["run"]["run_id"], "BUNDLE_RECOMPUTE", "header.run_id != provenance run_id")
    # the record states its context artifacts in provenance.inputs (copied from the bundle): the artifacts and data classes
    # PROD-43 reads, never another declaration of them (L3 fix round 1, issue 2)
    inputs = bundle["provenance"]["record"]["inputs"]
    require("context_artifacts" not in inputs or inputs["context_artifacts"] == src["context_artifacts"], "BUNDLE_RECOMPUTE",
            "provenance.record.inputs.context_artifacts is not sources.context_artifacts: the record would state other context "
            "artifacts or data classes than the ones PROD-43 reads (L3 fix round 1, issue 2)")
    check_pointers(src)
    # the names the record carries hold no withheld content (L3 fix round 2)
    guard = guard if guard is not None else Withheld(src, eio)
    check_withheld_names(bundle, guard)
    turns = {t["turn_index"]: t for t in src["turns"]}            # turn indices are unique (check_names)
    native = bundle["provenance"]["producer"]["kind"] == "native"
    check_episodes(bundle)
    texts = src["context_texts"]
    # PROD-43 reads the artifact as the most restrictive declaration of its content (L2 exit D-32): the same bytes (or the
    # same normalized text: L3 fix round 1, issue 3) under another name or class stay model-confidential
    confidential = ev_context.confidential_digests(src["context_artifacts"], texts)
    artifacts = {a["name"]: ev_context.effective(a, confidential, texts.get(a["name"])) for a in embedded(src["context_artifacts"])}
    rules, sources = SearchRules(eio, bundle, guard), declared_sources(src)
    citing = {}
    for c in claims:
        for rid in c["evidence"] + c.get("counterevidence", []):
            citing.setdefault(rid, []).append(c)
    calls = {(r["turn_index"], (r.get("tool") or {}).get("call_index")) for r in refs.values() if r["source_type"] == "AGENT_TOOL_CALL"}
    for r in refs.values():
        t = r["turn_index"]
        # every ref: the witness flag and the anchor follow from the release, never from the producer (review H1)
        require(r["source_type"] in eio.kind[r["kind"]]["compatible_source_types"], "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: source type {r['source_type']} is not compatible with kind {r['kind']}")
        paired = False
        if r["source_type"] == "TOOL_RESULT":                                          # PER-68: paired with its tool call
            key = (t, (r.get("tool") or {}).get("call_index"))
            paired = key in calls and bool(citing.get(r["id"])) and all(
                any(refs[x]["source_type"] == "AGENT_TOOL_CALL" and (refs[x]["turn_index"], (refs[x].get("tool") or {}).get("call_index")) == key
                    for x in c["evidence"] if x in refs) for c in citing[r["id"]])
        require(r["can_prove_agent_behaviour"] is eio.can_prove(r["kind"], r["source_type"], paired), "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: can_prove_agent_behaviour {r['can_prove_agent_behaviour']} does not follow from the release")
        offsets = r.get("char_start") is not None
        require(offsets == (r["anchor"] in OFFSET_ANCHORS), "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: anchor {r['anchor']} {'without' if not offsets else 'with'} offsets")
        require((r["kind"] == "TOOL_RECEIPT") == (r["anchor"] == "receipt"), "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: anchor receipt iff TOOL_RECEIPT")
        require(r["kind"] not in ("TYPED_ABSENCE", "CALCULATION") or r["anchor"] == "computed", "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: a {r['kind']} ref has anchor computed")
        require(r["anchor"] not in POLICY_ANCHORS or r["kind"] == "POLICY_SPAN", "BUNDLE_RECOMPUTE",
                f"ref {r['id']}: anchor {r['anchor']} locates a context-artifact line or document (a POLICY_SPAN only, 03 §7.5)")
        if r["source_type"] == "JUROR_INFERENCE":
            require(not native, "BUNDLE_RECOMPUTE", f"ref {r['id']}: a native producer mints no JUROR_INFERENCE ref (split plan §3.3)")
            require(r["anchor"] == "none" and "excerpt" not in r, "BUNDLE_RECOMPUTE", f"ref {r['id']}: a juror citation has anchor none and no excerpt")
        require(t is None or t in turns, "BUNDLE_RECOMPUTE", f"ref {r['id']}: turn {t} is not in sources")
        if r["source_type"] in TURN_FIELD:              # every turn ref, with or without text: no rename escapes (review L-5)
            require(r["source_ref"] == src["turn_source_ref"], "BUNDLE_RECOMPUTE",
                    f"ref {r['id']}: a turn ref points into {r['source_ref']!r}, not the declared turn source {src['turn_source_ref']!r}")
        if r["kind"] == "TOOL_RECEIPT":
            j = r["tool"]["call_index"]
            # an index is an integer (the schema's `integer` also admits 0.0: L2 exit D-30)
            require(type(j) is int and t in turns and 0 <= j < len(turns[t]["tool_calls"]), "BUNDLE_RECOMPUTE",
                    f"ref {r['id']}: no such tool call")
            call = turns[t]["tool_calls"][j]
            ah = H(jb(call["arguments"]))
            k = sum(1 for cc in turns[t]["tool_calls"][: j + 1] if cc["name"] == call["name"] and H(jb(cc["arguments"])) == ah)
            want = receipt_ref(eio, t, j, call["name"], call["arguments"], k, "result" in call, call.get("result"),
                               call["arguments_pointer"], src["turn_source_ref"])
            require(r == want, "BUNDLE_RECOMPUTE", f"ref {r['id']}: the tool receipt does not recompute from sources")
        elif r["source_type"] in TURN_FIELD and (offsets or r["span_sha256"] is not None):
            # a turn ref that locates text is a span of the turn, rebuilt whole: a partial form (offsets without the span
            # digest, or the reverse) never escapes the recompute as a declared ref (review R-1)
            require(t in turns, "BUNDLE_RECOMPUTE", f"ref {r['id']}: turn {t} is not in sources")
            text = turns[t][TURN_FIELD[r["source_type"]]]
            a, b = r["char_start"], r["char_end"]
            require(isinstance(a, int) and isinstance(b, int) and 0 <= a <= b <= len(text), "BUNDLE_RECOMPUTE", f"ref {r['id']}: offsets")
            # a quote anchor quotes something: an empty exact span holds in every text, so it would witness nothing
            # (L2 exit D-35, F-10; the whole-turn anchor `turn` may cite an empty turn)
            require(a < b or r["anchor"] not in QUOTE_ANCHORS, "BUNDLE_RECOMPUTE",
                    f"ref {r['id']}: an {r['anchor']} span [{a}, {b}) quotes nothing (L2 exit D-35, F-10)")
            require(r["anchor"] != "turn" or (a, b) == (0, len(text)), "BUNDLE_RECOMPUTE",
                    f"ref {r['id']}: anchor turn cites the whole turn source [0, {len(text)}), not [{a}, {b}) (03 §7.5)")
            want = span_ref(eio, r["kind"], r["source_type"], t, text, a, b, r["anchor"], r["source_ref"])
            got = {k: r.get(k) for k in want}
            require(got == want and set(r) <= set(want), "BUNDLE_RECOMPUTE", f"ref {r['id']}: the span does not recompute from sources")
        elif r["kind"] == "TYPED_ABSENCE" and r["source_type"] == "AGENT_TOOL_CALL":
            _call_absence(eio, r, src, turns, rules)
        elif r["kind"] == "TYPED_ABSENCE" and r["source_type"] == "POLICY_SOURCE":
            _context_absence(eio, r, texts, set(artifacts), rules)
        elif r["kind"] == "POLICY_SPAN":
            _policy_span(eio, r, texts, artifacts)
        elif r["kind"] == "STATE_FACT" and r["source_type"] == "STATE_LEDGER" and t in turns and "state" in turns[t]:
            _state_fact(eio, r, src, turns)
        else:
            _declared(eio, r, sources)
    if native:
        check_native_sources(bundle)
    for c in claims:
        require(c["run_id"] == h["run_id"], "BUNDLE_RECOMPUTE", f"claim {c['id']}: run_id")
        # seam row 9: the reason is computed by the producer from texts the bundle does not carry; the rule EIO-54 is checked
        require(("invalid_because" in c["parameters"]) == (c["state"] == "EVIDENCE_INVALID"), "BUNDLE_RECOMPUTE",
                f"claim {c['id']}: invalid_because iff EVIDENCE_INVALID (EIO-54)")
        require(ids.claim_id_of(c) == c["id"], "BUNDLE_RECOMPUTE", f"claim {c['id']}: the claim id does not recompute")
        for rid in c["evidence"]:
            require(rid in refs, "BUNDLE_RECOMPUTE", f"claim {c['id']} cites {rid}, which is not in graph.refs")
        # eio.profile.resolver-authority: a human decision MUST cite a HUMAN_SIGNOFF ref with source type HUMAN_REVIEW (L3 fix
        # round 2; without one it read as a deterministic decision, PROVEN on any witnessing span)
        require(c["decided_by"] != "human" or any((refs[x]["kind"], refs[x]["source_type"]) == ("HUMAN_SIGNOFF", "HUMAN_REVIEW")
                                                  for x in c["evidence"]), "BUNDLE_RECOMPUTE",
                f"claim {c['id']}: a human decision cites no HUMAN_SIGNOFF ref over HUMAN_REVIEW (eio.profile.resolver-authority)")
        # EIO-54 (L3 fix round 3: the twin's C2 read it, the projector did not): votes are null iff the decision is deterministic
        require((c["parameters"].get("votes") is None) == (c["decided_by"] == "deterministic"), "BUNDLE_RECOMPUTE",
                f"claim {c['id']}: votes null iff deterministic (EIO-54), but it is decided by {c['decided_by']!r:.40} with votes "
                f"{'null' if c['parameters'].get('votes') is None else 'given'}")
        for t in c["turn_indices"]:
            require(t in turns, "BUNDLE_RECOMPUTE", f"claim {c['id']}: turn {t} is not in sources")
    by_claim = {}
    for b in bundle["ballots"]["ballots"]:
        by_claim.setdefault(b["claim_id"], []).append(b)
    C = {c["id"]: c for c in claims}
    require(set(by_claim) <= set(bundle["ballots"]["pooled_claims"]), "BUNDLE_RECOMPUTE", "a ballot names a claim that is not pooled")
    for c in claims:                                     # votes are counted from ballots only (review #11)
        require(c["parameters"].get("votes") is None or c["id"] in bundle["ballots"]["pooled_claims"], "BUNDLE_RECOMPUTE",
                f"claim {c['id']}: carries votes but is not a pooled claim")
    for cid in bundle["ballots"]["pooled_claims"]:
        require(cid in C, "BUNDLE_RECOMPUTE", f"pooled claim {cid} is not a claim")
        votes = C[cid]["parameters"].get("votes") or {}
        got = pool(by_claim.get(cid, []))
        require({k: votes.get(k) for k in got} == got, "BUNDLE_RECOMPUTE", f"claim {cid}: the votes do not pool from its ballots")
