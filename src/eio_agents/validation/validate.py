"""`validate(rec)` and `validate_bundle(bundle)`: the independent verifier's check runs, in process (split plan §4.2).

`check_one` runs the record-level checks of `Checker` in the rc1 report order and returns the checker with its rows;
`validate` returns the failing rows as problems `{check, ver, status, detail}`. The ProofAgent halves of the mixed checks
and the archive checks are not run here: they are the producer verifier's (the ProofAgent adapter's legacy verifier, in
the ProofAgent Harness since L3). PER rules are chosen by `header.per_version`: HEAD validates rc1 (2.0.0-rc1) until L4.

`validate_bundle` checks an evaluation bundle (archive schema 3, draft 1) with its own reading of the bundle schema (the
section schemas of the projector's stage guard): the bundle text as I-JSON, the schema and the rules it cannot state (each
name the sources and the graph are resolved by is given once; the context texts are the embedded artifacts'), the stage
records, the adapter-only producer-declared section (§4.4), the native-producer rules (no declared source archive, every
stage record native) and the closed vocabularies of the loaded release. It shares no code with the projector (contract
P3). It does not recompute: ids, refs, computed statements, pointers, episodes, stage digests and the projected record
are checked by `convert` (and, from the record, by `verify`), so a bundle can pass here and still fail to convert.
"""
import hashlib
import json
import math
import re
import string
import unicodedata
import urllib.parse
import weakref
from collections import Counter

from jsonschema import Draft202012Validator

from eio_agents.schemas import bundle_schema, scoring_profile_schema
from eio_agents.validation.canon import jb as _jb, sha as _sha
from eio_agents.validation.checker import Checker
from eio_agents.validation.reader import EIO, EIO_DIR, LIMITATION_CATALOGUE, load_catalogue
from eio_agents.validation.redaction import REDACTION_CLASSES, class_matches

# (row label, VER id, Checker method, skipped for an abridged example) in the rc1 report order
CHECKS = (
    ("S1 schema (header.schema_uri, 2020-12, formats)", "VER-4", "c_schema", False),
    ("S2 claims valid against EIO evaluation-claim schema", "VER-4", "c_claim_schema", False),
    ("S3 header: 2.x, per_semantics_version", "VER-4", "c_header", False),
    ("S4 header.eio digests recompute from the release", "VER-4", "c_eio_digests", False),
    ("S5 relative_path values in Unicode NFC", "VER-4", "c_nfc", False),
    ("A1 every EIO id exists in the release, with its values", "VER-4", "c_eio_ids", False),
    ("A2 domain resolution (imports, default)", "VER-4", "c_domains", False),
    ("A3 coverage recomputed (obligations, census, counts)", "VER-4", "c_coverage", True),
    ("E1 cited refs resolve; only cited refs carried", "VER-3", "c_refs_resolve", False),
    ("E2 witness rule recomputed (W4, PER-68)", "VER-4", "c_witness", False),
    ("E3 cited_refs_hash and counts recompute", "VER-4", "c_counts", False),
    ("E4 declared array orders", "VER-4", "c_order", False),
    ("C1 claim ids recompute", "VER-4", "c_claim_ids", False),
    ("C2 conditional claim parameters (EIO-54), votes", "VER-4", "c_claim_params", False),
    ("C3 evidence contracts recomputed", "VER-4", "c_contract", False),
    ("F1 findings recomputed (ids, severity, decider, witness)", "VER-4", "c_findings", False),
    ("K1 control statuses recomputed", "VER-4", "c_controls", False),
    ("M1 scores: caps, cap reasons, drivers", "VER-4", "c_scores", False),
    ("X1 explanations re-render from eio.template.why", "VER-4", "c_explanations", False),
    ("X2 control and release wording (§7.9, §11.2)", "VER-4", "c_wording", False),
    ("R1 gates recomputed", "VER-4", "c_gates", False),
    ("R2 release recommendation (§9.3, I-1..I-8)", "VER-4", "c_release", False),
    ("L1 reliability ledgers and rate", "VER-4", "c_reliability", False),
    ("T1 limitations from the 04 §5.13 catalogue", "VER-4", "c_limitations", False),
    ("P1 PER Pointers and view ids resolve", "VER-3", "c_pointers", False),
    ("N1 numbers: finite, no -0, 4 dp, integral counts (PROD-9..11)", "VER-4", "c_numbers", False),
    ("W1 record strings in the closed field table (decision #31)", "VER-4", "c_privacy", False),
    ("D1 per_sha256", "VER-1", "c_per_sha", False),
)


def rows_as_problems(rows):
    return [{"check": n, "ver": v, "status": st, "detail": d} for n, v, st, d in rows]


def check_one(rec, eio=None, cat=None, label=None):
    """Run every record-level check on `rec` (a PER dict) and return the `Checker` with its rows. `eio` is the
    verifier's reader of the release (default: the bundled release, read for this call) and `cat` the limitation
    catalogue."""
    eio = eio if eio is not None else EIO(EIO_DIR)
    cat = cat if cat is not None else load_catalogue()
    try:
        k = Checker(rec, eio, cat, label or "record")
    except Exception as ex:                        # not a record at all: one failing S1 row, never an exception
        return Unreadable(ex)
    for name, ver, method, skip in CHECKS:
        k.run(name, ver, getattr(k, method), skip_if_abridged=skip)
    return k


class Unreadable:
    """The check run of an input that is not a PER record (not a JSON object, or without a required block)."""

    abridged = False

    def __init__(self, ex):
        self.rows = [(CHECKS[0][0], CHECKS[0][1], "FAIL", f"1 problem(s); first: not a PER record ({type(ex).__name__}: {ex})")]

    def run(self, name, ver, fn, skip_if_abridged=False):
        self.rows.append((name, ver, "SKIP", "not a PER record"))


def validate(rec, *, eio=None):
    """Schema and semantic (EIO alignment) validation of a PER record, in process. Returns the failing checks as
    `{check, ver, status, detail}`; [] when valid. An input that is not a record gives one failing S1 row."""
    return rows_as_problems(r for r in check_one(rec, eio).rows if r[2] == "FAIL")


# ---------------------------------------------------------------- bundles
SECTIONS = ("provenance", "sources", "scope", "context_assessment", "graph", "claims", "ballots", "trials", "limitations")
POLICY_SOURCES = ("embedded_profile", "tier_reconstructed", "none")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")


def _members(pairs):
    twice = sorted(k for k, n in Counter(k for k, _ in pairs).items() if n > 1)
    if twice:
        raise ValueError(f"the bundle text gives the object member(s) {twice} twice (I-JSON)")
    return dict(pairs)


def _not_a_number(token):
    raise ValueError(f"{token} is not a JSON number (I-JSON)")


def _finite(token):
    x = float(token)
    if not math.isfinite(x):
        raise ValueError(f"the number {token[:40]} is outside the IEEE 754 double range (I-JSON)")
    return x


DOUBLE_MAX = 1.7976931348623157e308             # an integer beyond it has no number form a reader keeps (L3 fix round 1)


MAX_DEPTH = 100                                  # nesting levels of a bundle, the projector's limit (RFC 8259 §9)


def loads_bundle(text):
    """The verifier's own reading of bundle JSON text (str or bytes) as I-JSON: UTF-8, each object member once, finite
    numbers (review R-2: no reader can resolve a name given twice differently). Raises ValueError (an integer too long for
    Python included) or RecursionError."""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8")
    return json.loads(text, object_pairs_hook=_members, parse_constant=_not_a_number, parse_float=_finite)


def not_json_at(doc):
    """Where a bundle holds a value JSON text cannot hold (a member name that is not a string, an integer beyond the IEEE
    754 double range, a tuple, a set, bytes, ...), or None (without recursion; L3 fix round 1, issue 4)."""
    stack = [(doc, "")]
    while stack:
        o, at = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(k, str):
                    return f"{at}/{k!r}"
                stack.append((v, f"{at}/{k}"))
        elif isinstance(o, list):
            stack.extend((v, f"{at}/{i}") for i, v in enumerate(o))
        elif o is None or isinstance(o, (bool, str, float)):
            continue
        elif isinstance(o, int):
            if abs(o) > DOUBLE_MAX:
                return at or "/"
        else:
            return at or "/"
    return None


def too_deep(doc, limit=MAX_DEPTH):
    """Whether a JSON value nests more than `limit` levels, found without recursion (a cyclic dict ends too)."""
    stack = [(doc, 1)]
    while stack:
        o, d = stack.pop()
        if isinstance(o, (dict, list)):
            if d > limit:
                return True
            stack.extend((v, d + 1) for v in (o.values() if isinstance(o, dict) else o))
    return False


def surrogate_at(doc):
    """Where the first string of `doc` (a member name or a value) holds a lone surrogate, or None (found without recursion)."""
    stack = [(doc, "")]
    while stack:
        o, at = stack.pop()
        if isinstance(o, str) and not _scalar(o):
            return at or "/"
        if isinstance(o, dict):
            for k, v in o.items():
                name = json.dumps(k)[1:-1] if isinstance(k, str) else repr(k)
                if isinstance(k, str) and not _scalar(k):
                    return f"{at}/{name}"
                stack.append((v, f"{at}/{name}"))
        elif isinstance(o, list):
            stack.extend((v, f"{at}/{i}") for i, v in enumerate(o))
    return None


def _scalar(text):
    return not any(0xD800 <= ord(c) <= 0xDFFF for c in text)


def bundle_of(bundle):
    """A bundle as the verifier reads it: text through `loads_bundle`, then at most `MAX_DEPTH` levels, with no lone
    surrogate in a string (I-JSON, RFC 7493 §2.1; L2 exit D-30) and no value JSON cannot hold as I-JSON (`not_json_at`; L3
    fix round 1, issue 4). Raises ValueError."""
    b = loads_bundle(bundle) if isinstance(bundle, (bytes, bytearray, str)) else bundle
    if too_deep(b):
        raise ValueError(f"the bundle is nested more than {MAX_DEPTH} levels deep")
    at = surrogate_at(b)
    if at is not None:
        raise ValueError(f"{at}: a string that is not a sequence of Unicode scalar values (a lone surrogate; I-JSON)")
    at = not_json_at(b)
    if at is not None:                                 # L3 fix round 1, issue 4
        raise ValueError(f"{at}: a value that JSON text cannot hold (L3 fix round 1, issue 4)")
    return b


def _bundle_schema_problems(b):
    errs = sorted(Draft202012Validator(bundle_schema()).iter_errors(b), key=lambda e: (list(e.absolute_path), e.message))
    p = [f"/{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in errs]
    return p or _name_problems(b)


def _name_problems(b):
    """The B1 rules the schema language cannot state (review R-2): every name the bundle's sources and graph are resolved
    by is given once, and the context texts are exactly the embedded artifacts' texts."""
    p, src = [], b["sources"]
    for what, names in (("sources.turns turn_index", [t["turn_index"] for t in src["turns"]]),
                        ("sources.context_artifacts name", [a["name"] for a in src["context_artifacts"]]),
                        ("graph.refs id", [r["id"] for r in b["graph"]["refs"]]),
                        ("claims id", [c["id"] for c in b["claims"]])):
        twice = sorted(x for x, n in Counter(names).items() if n > 1)
        if twice:
            p.append(f"{what} {twice} given twice (a name resolves one item)")
    emb = sorted(a["name"] for a in src["context_artifacts"] if a["embedded"])
    if sorted(src["context_texts"]) != emb:
        p.append(f"sources.context_texts {sorted(src['context_texts'])} are not the texts of the embedded context artifacts {emb}")
    odd = sorted(a["name"] for a in src["context_artifacts"] if unicodedata.normalize("NFC", a["name"]) != a["name"])
    if odd:                                            # one spelling per name (L2 exit D-35, F-11)
        p.append(f"sources.context_artifacts names {odd} are not in Unicode NFC")
    stated = sorted(t["turn_index"] for t in src["turns"] if "state" in t)
    if stated and "state_field" not in src:            # a state snapshot is named by the state field (L2 exit D-34)
        p.append(f"sources.turns {stated} carry a state snapshot that sources.state_field does not name")
    return p + layout_problems(src)


LAYOUT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
ARCHIVE_POINTER = re.compile(r"(?:/[A-Za-z0-9_]{1,64}){1,16}")
LABEL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}")
LINK_VIA = "eio.graph.context-links:{key}\u2192{criterion}/{control}"


def layout_problems(src):
    """The names of the bundle's source layout and its pointers reach the record: each layout name is an identifier, each
    archive or argument pointer holds identifier and index tokens only (L3 fix round 1, issue 1)."""
    p = []
    for k in ("turn_source_ref", "calls_field", "state_field"):
        if k in src and not (isinstance(src[k], str) and LAYOUT_NAME.fullmatch(src[k])):
            p.append(f"sources.{k} {src[k]!r:.80} is not an identifier: it is written into the record")
    for k, v in src["archive_pointer"].items():
        if k != "archive_sha256" and not (LAYOUT_NAME.fullmatch(k) and isinstance(v, str) and ARCHIVE_POINTER.fullmatch(v)):
            p.append(f"sources.archive_pointer {k!r:.80}: {v!r:.80} is not an identifier with a pointer of identifier and index tokens")
    for t in src["turns"]:
        for c in t["tool_calls"]:
            if not (isinstance(c.get("arguments_pointer"), str) and ARCHIVE_POINTER.fullmatch(c["arguments_pointer"])):
                p.append(f"turn {t['turn_index']}: arguments_pointer {c.get('arguments_pointer')!r:.80} is not a pointer of "
                         "identifier and index tokens")
    return p


def declared_item_problems(b, e):
    """The producer-declared labels that reach the record: each scenario label and context-link key is a label, and each
    context-link row names a checklist control of the release with its link as `via` (L3 fix round 1, issue 1)."""
    p, decl = [], b.get("producer_declared") or {}
    sc = decl.get("scenarios")
    if sc:
        for x in [t["label"] for t in sc["turns"]] + list(sc["severity"]):
            if not (isinstance(x, str) and LABEL.fullmatch(x)):
                p.append(f"the scenario label {x!r:.80} is not a label")
    cl = decl.get("context_links")
    for key, rows in (cl["rows"] if cl else {}).items():
        if not LABEL.fullmatch(key):
            p.append(f"the context-link key {key!r:.80} is not a label")
        for row in rows:
            crit, ctl = row["criterion"], row["control"]
            if crit not in e.criteria or ctl not in [x["id"] for x in e.criteria[crit].get("controls") or []]:
                p.append(f"context link {key!r:.60}: {crit!r:.60}/{ctl!r:.60} is not a checklist control of the release")
            elif row["via"] != LINK_VIA.format(key=key, criterion=crit, control=ctl):
                p.append(f"context link {key!r:.60}: via {row['via']!r:.80} is not its link")
    return p


# ---------------------------------------------------------------- withheld content (L3 fix rounds 1 and 2), the twin's reading
EXCERPTABLE = ("eio.data.public", "eio.data.internal")    # the data classes a record may quote (PROD-43 read fail-closed)
DATA_CLASS_ID = re.compile(r"eio[.]data[.][a-z0-9][a-z0-9_.-]*")   # the PER schema's form of a data-class id (L3 fix round 2)
_WORDS = re.compile(r"[^\W_]+")
_ASCII_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_FILE = re.compile(r".*[^\W_]\.[A-Za-z0-9]{1,8}")
_TOOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")          # an identifier-shaped tool name (L3 fix round 3)
_PLAIN_NUMBER = re.compile(r"\s*[-+]?[0-9]+(?:\.[0-9]+)?\s*")   # one decimal number: a count, an index or a score
_INVISIBLE_RANGES = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
                     (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
                     (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
_LATIN = {"А": "A", "В": "B", "Е": "E", "Ѕ": "S", "І": "I", "Ј": "J", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
          "Т": "T", "Х": "X", "У": "Y", "Ԍ": "G", "Ԛ": "Q", "Ԝ": "W", "а": "a", "е": "e", "ѕ": "s", "і": "i", "ј": "j", "к": "k",
          "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "ԁ": "d", "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ү": "y", "ь": "b",
          "ɑ": "a", "ɡ": "g", "ı": "i", "ȷ": "j", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
          "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "α": "a", "ι": "i", "ο": "o", "κ": "k", "ρ": "p", "τ": "t",
          "υ": "u", "χ": "x", "ν": "v", "օ": "o", "ս": "u", "ո": "n", "հ": "h"}
_GONE = ("Mn", "Me", "Cf", "Co", "Cs", "Cn")
_TURN_TEXTS = ("AGENT_ANSWER", "USER_INPUT")      # a ref whose PROD-42 excerpt quotes a turn text: exempt (D-43, D-48)
EXEMPT_AGENT = (("subject", "agent", "goal"), ("subject", "agent", "role"))    # ACCEPTED_DEVIATIONS D-41 (S2: hash + pointer)


def _invisible(ch):
    o = ord(ch)
    return unicodedata.category(ch) in _GONE or any(a <= o <= b for a, b in _INVISIBLE_RANGES)


def _decimal(ch):
    """The ASCII digit of a decimal digit of another script (category Nd), else the character (L3 fix round 4)."""
    return chr(0x30 + unicodedata.decimal(ch)) if unicodedata.category(ch) == "Nd" and ord(ch) > 0x7F else ch


def _boundaries(text):
    """A space at each camel-case boundary: before an upper-case letter after a lower-case letter or a digit, or after an
    upper-case letter and before a lower-case one."""
    if text.isascii():
        return _ASCII_BOUNDARY.sub(" ", text)
    out = []
    for i, ch in enumerate(text):
        if i and ch.isupper() and (text[i - 1].islower() or text[i - 1].isdigit()
                                   or (text[i - 1].isupper() and i + 1 < len(text) and text[i + 1].islower())):
            out.append(" ")
        out.append(ch)
    return "".join(out)


def content_words(text):
    """The words of a text as this verifier compares it with withheld content (L3 fix round 2): NFKD without combining marks
    or invisible characters, a control character read as a space, look-alike letters read as Latin, camel-case boundaries
    split, casefold; a word is a run of letters and digits (so snake, kebab and camel case read as the words they join).
    L3 fix round 4: a decimal digit of any script (category Nd) is read as the ASCII digit of its value."""
    if text.isascii():
        return _WORDS.findall(_boundaries(text).lower())
    t = "".join(" " if unicodedata.category(ch) == "Cc" else _LATIN.get(ch) or _decimal(ch)
                for ch in unicodedata.normalize("NFKD", text) if not _invisible(ch))
    t = unicodedata.normalize("NFKD", _boundaries(t).casefold())
    return _WORDS.findall("".join(ch for ch in t if unicodedata.category(ch) not in _GONE))


def normalized_text_digest(text):
    """The digest of a text read as the same content: NFC, LF line ends, no trailing white space per line or at the end."""
    t = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "sha256n:" + hashlib.sha256("\n".join(x.rstrip() for x in t.split("\n")).rstrip("\n").encode("utf-8")).hexdigest()


def _strings_at(value):
    """[(path, string, is a member name)] of a JSON value, without recursion."""
    out, stack = [], [(value, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                out.append((p, k, True))
                stack.append((v, p + (k,)))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in enumerate(o))
        elif isinstance(o, str):
            out.append((p, o, False))
    return out


def _value_texts(value):
    """The strings of a JSON value and the JSON text of its numbers (member names left out)."""
    out, stack = [], [value]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
        elif isinstance(o, str):
            out.append(o)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out.append(json.dumps(o))
    return out


def _identifying(w):
    """PROD-42's identifying classes, read on a value's words (L3 fix round 3): four digits or more in a run, two number
    groups or more, or a word that mixes letters and digits."""
    if len(w) >= 2 and all(x.isdigit() for x in w):
        return True
    return any(len(x) >= 4 if x.isdigit() else any(ch.isdigit() for ch in x) for x in w)


def _names_subject(s, w):
    """Whether a tool-call or state string names a subject for the record-wide rule: an '@', two words or more one of
    which is not a number, or (L3 fix round 3) an identifying class (`_identifying`) unless it is one plain decimal number
    without a run of four digits."""
    if "@" in s or (len(w) >= 2 and any(not x.isdigit() for x in w)):
        return True
    if _PLAIN_NUMBER.fullmatch(s):
        return any(len(x) >= 4 for x in w)
    return _identifying(w)


def _json_escapes(text):
    """The text with its JSON '\\uXXXX' escapes read as the characters they stand for (L3 fix round 4): a high and a low
    surrogate escape together as one code point, an unpaired surrogate escape as U+FFFD."""
    out, i, n = [], 0, len(text)
    while i < n:
        j = text.find("\\u", i)
        if j < 0 or j + 6 > n or any(c not in string.hexdigits for c in text[j + 2:j + 6]):
            if j < 0:
                out.append(text[i:])
                break
            out.append(text[i:j + 2])
            i = j + 2
            continue
        out.append(text[i:j])
        u = int(text[j + 2:j + 6], 16)
        if 0xD800 <= u < 0xDC00 and text[j + 6:j + 8] == "\\u" and all(c in string.hexdigits for c in text[j + 8:j + 12]) \
                and 0xDC00 <= int(text[j + 8:j + 12], 16) < 0xE000:
            out.append(chr(0x10000 + (u - 0xD800) * 0x400 + int(text[j + 8:j + 12], 16) - 0xDC00))
            i = j + 12
        else:
            out.append("\ufffd" if 0xD800 <= u < 0xE000 else chr(u))
            i = j + 6
    return "".join(out)


def _unescaped(text):
    """The text with JSON '\\u' escapes (L3 fix round 4), then percent-encoding and JSON Pointer escapes decoded (L3 fix
    round 3)."""
    if "\\u" in text:
        text = _json_escapes(text)
    if "%" in text or "~" in text:
        return urllib.parse.unquote(text, errors="replace").replace("~1", "/").replace("~0", "~")
    return text


def _turn_matches(turns):
    """The spans of a turn question or answer that PROD-42 redacts (this verifier's `redaction` classes: e-mail, SSN form,
    IBAN, Luhn-valid card, secret, the four digits after 'last 4' or 'ssn'), read with every decimal digit as ASCII: values
    the user or the agent states, subjects of the record-wide rule (L3 fix round 4)."""
    found = []
    for t in turns:
        for key in ("question", "answer"):
            x = t.get(key)
            if isinstance(x, str) and x:
                x = "".join(_decimal(ch) for ch in x)
                found += [x[a:b] for cls in REDACTION_CLASSES for _, (a, b) in class_matches(x, cls)]
    return found


def _schema_tools(src, withheld):
    """The identifier-shaped names under a member `name` of every embedded tool schema that is not withheld."""
    out = set()
    for a in src["context_artifacts"]:
        if a.get("artifact_kind") != "eio.artifact.tool-schema" or a["name"] in withheld or a["name"] not in src["context_texts"]:
            continue
        try:
            todo = [json.loads(src["context_texts"][a["name"]])]
        except (ValueError, RecursionError):
            continue
        while todo:
            o = todo.pop()
            if isinstance(o, list):
                todo += o
            elif isinstance(o, dict):
                todo += list(o.values())
                if isinstance(o.get("name"), str) and _TOOL.fullmatch(o["name"]):
                    out.add(o["name"])
    return out


def _runs(texts, sizes=(1, 2, 3)):
    runs = {n: set() for n in sizes}
    for t in texts:
        w = content_words(t)
        for n in sizes:
            runs[n].update(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    return runs


def withheld_names(src):
    """The embedded context artifacts whose text a record never quotes: a class other than public or internal, or the same
    bytes or normalized text as an artifact declared with such a class (PROD-43 read fail-closed; L2 exit D-32, D-35; L3
    fix round 1, issue 3)."""
    arts, texts = src["context_artifacts"], src["context_texts"]
    confidential = {a["sha256"] for a in arts if a.get("data_class") not in EXCERPTABLE}
    confidential |= {normalized_text_digest(texts[a["name"]]) for a in arts
                     if a.get("data_class") not in EXCERPTABLE and isinstance(texts.get(a["name"]), str)}
    emb = {a["name"]: a for a in arts if a.get("embedded", True) and a["name"] in texts}
    return {x for x, a in emb.items() if a.get("data_class") not in EXCERPTABLE or a["sha256"] in confidential
            or normalized_text_digest(texts[x]) in confidential}


_RELEASE_RUNS = weakref.WeakKeyDictionary()      # a release reader -> the runs of its published texts (dies with the reader)


def _published(e):
    """The runs of 1 to 3 words of every string the release publishes (its modules and the limitation catalogue): public
    wording, never withheld content; read once per release reader."""
    if e not in _RELEASE_RUNS:
        _RELEASE_RUNS[e] = _runs([s for _, s, _ in _strings_at(list(e.doc.values()))]
                                 + [s for _, s, _ in _strings_at(json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8")))])
    return _RELEASE_RUNS[e]


class Content:
    """The confidential content of a bundle, as this verifier reads it: the withheld artifacts' texts, and the tool-call and
    state values. `reproduced` is the rule for search terms and undeclared file names (L3 fix round 1): RUN consecutive
    words of a withheld text (all the text's words when it has fewer), or all the words of a value that identifies (two
    words or more, a digit or an '@'). `carried` is the rule for every other text of the record (L3 fix round 2): RUN
    consecutive words of a withheld text (all its words when it has fewer) that the release does not publish and that are
    not inside one token of the text naming a declared artifact's file, or all the words of a value that names a subject
    (an '@', or two words or more, one not a number; L3 fix round 3: or PROD-42's identifying classes, `_names_subject`) and
    is not release wording, read verbatim and with percent and JSON Pointer escapes decoded."""

    RUN = 3

    def __init__(self, B, e):
        src = B["sources"]
        texts = src["context_texts"]
        self.withheld = withheld_names(src)
        wt = [texts[x] for x in sorted(self.withheld)]
        self.runs = _runs(wt)
        self.values = set()
        vals = [v for t in src["turns"] for c in t["tool_calls"] for v in _value_texts([c["arguments"], c.get("result")])]
        vals += [v for t in src["turns"] for v in _value_texts(t.get("state"))]
        for v in vals:
            w = tuple(content_words(v))
            if w and (len(w) >= 2 or any(ch.isdigit() for ch in v) or "@" in v):
                self.values.add(w)
        self.tokens = {tuple(content_words(x)) for t in wt for x in t.split()}     # a whole token of a withheld text, as words
        files = {tuple(content_words(n)) for a in src["context_artifacts"] for n in (a["name"], a["name"].split("/")[-1])
                 if _FILE.fullmatch(n)}
        # L3 fix round 4: every scalar (numbers as their JSON text) and the PROD-42 matches of the turn texts
        strings = list(vals) + _turn_matches(src["turns"])
        subj = []
        for s in strings:
            w = tuple(content_words(s))
            if w and _names_subject(s, w):
                subj.append(w)
        self.tools = {c["name"] for t in src["turns"] for c in t["tool_calls"] if isinstance(c.get("name"), str)}
        self.tools |= _schema_tools(src, self.withheld)
        self.by_size = {}                      # n -> the protected runs and subject values of n words
        self.kind = {}                         # a protected run or subject value -> what it is
        if not wt and not subj:
            return
        public = _published(e)
        for t in wt:
            seq = []
            for k, tok in enumerate(t.split()):
                inside = tuple(content_words(tok)) in files
                seq += [(w, k, inside) for w in content_words(tok)]
            n = min(self.RUN, len(seq))
            for i in range(len(seq) - n + 1) if n else ():
                part = seq[i:i + n]
                if part[0][2] and part[0][1] == part[-1][1]:
                    continue
                run = tuple(w for w, _, _ in part)
                if run not in public[n]:
                    self.by_size.setdefault(n, set()).add(run)
                    self.kind.setdefault(run, "carries the text of a withheld context artifact")
        for w in subj:
            m = min(len(w), self.RUN)
            if not all(tuple(w[i:i + m]) in public[m] for i in range(len(w) - m + 1)):
                self.by_size.setdefault(len(w), set()).add(w)
                self.kind.setdefault(w, "carries a tool-call or state value naming a subject")

    def names(self, name):
        """Whether a withheld text names the tool `name` as a whole token (the same words); L3 fix round 3: only an
        identifier-shaped name of a tool the bundle observes or declares (a tool schema that is not withheld), not itself of
        an identifying class."""
        if not isinstance(name, str) or not _TOOL.fullmatch(name) or name not in self.tools:
            return False
        w = tuple(content_words(name))
        return w in self.tokens and not _identifying(w)

    def reproduced(self, text, artifacts=True):
        w = content_words(text)
        n = min(len(w), self.RUN)
        if artifacts and n > 0 and any(tuple(w[i:i + n]) in self.runs[n] for i in range(len(w) - n + 1)):
            return "reproduces the text of a withheld context artifact"
        if any(tuple(w[i:j]) in self.values for i in range(len(w)) for j in range(i + 1, len(w) + 1)):
            return "reproduces a tool-call or state value"
        return None

    def carried(self, text):
        if not self.by_size:
            return None
        readings = [text] + ([u] if (u := _unescaped(text)) != text else [])   # L3 fix round 3: escaped forms too
        for t in readings:
            w = content_words(t)
            for n, found in self.by_size.items():
                for i in range(len(w) - n + 1):
                    x = tuple(w[i:i + n])
                    if x in found:
                        return self.kind[x]
        return None


def content_problems(b, content):
    """The names a producer chooses that the record carries (the layout names, the archive and argument pointers, the
    declared context-artifact names, retrieval sources, tool-call names unless a withheld text names the tool as a whole
    token, scenario labels and context-link keys): none carries withheld content (`Content.carried`; L3 fix round 2)."""
    src, p = b["sources"], []
    items = [(f"sources.{k}", src[k]) for k in ("turn_source_ref", "calls_field", "state_field") if k in src]
    for k, v in src["archive_pointer"].items():
        if k != "archive_sha256":
            items += [("an archive-pointer key", k), ("an archive pointer", v)]
    items += [("a context-artifact name", a["name"]) for a in src["context_artifacts"]]
    for t in src["turns"]:
        items += [(f"turn {t['turn_index']}: an arguments pointer", c.get("arguments_pointer")) for c in t["tool_calls"]]
        items += [(f"turn {t['turn_index']}: a tool-call name", c["name"]) for c in t["tool_calls"] if not content.names(c["name"])]
        items += [(f"turn {t['turn_index']}: a retrieval source", x.get("source")) for x in t["retrievals"]]
    decl = b.get("producer_declared") or {}
    sc = decl.get("scenarios")
    if sc:
        items += [("a scenario label", x) for x in [t["label"] for t in sc["turns"]] + list(sc["severity"])]
    cl = decl.get("context_links")
    if cl:
        items += [("a context-link key", k) for k in list(cl["rows"]) + list(cl["claims"].values())]
    for what, text in items:
        if isinstance(text, str) and (why := content.carried(text)) is not None:
            p.append(f"{what} {text!r:.80} {why}: it is written into the record (L3 fix round 2)")
    return p


def record_content_problems(rec, content):
    """The record-wide rule (L3 fix round 2): the strings of the record (member names included) that carry withheld content,
    outside the PROD-42 excerpt of a turn span (a ref over AGENT_ANSWER or USER_INPUT: ACCEPTED_DEVIATIONS D-43, D-48; a
    policy excerpt is checked), the agent description goal and role (D-41) and a tool-call name that a withheld text names
    as a whole token (D-41)."""
    refs = rec["evidence"]["refs"]
    p = []
    for path, text, key in _strings_at(rec):
        if not key:
            if path in EXEMPT_AGENT:
                continue
            if (len(path) == 4 and path[:2] == ("evidence", "refs") and path[3] == "excerpt"
                    and refs[path[2]].get("source_type") in _TURN_TEXTS):
                continue
            if content.names(text) and ((len(path) == 6 and path[:2] == ("evidence", "turns") and path[3] == "tool_calls"
                                            and path[5] == "name") or (path[:2] == ("evidence", "refs") and path[3:] == ("tool", "name"))):
                continue
        if (why := content.carried(text)) is not None:
            p.append(f"/{'/'.join(map(str, path))}{'/{member name}' if key else ''}: {why} (L3 fix round 2, the record-wide rule)")
    return p


def _carried_in_clear(path):
    """Whether a bundle string at `path` reaches a record in clear (the twin's reading): not a context text, a turn's
    question, answer or state, a tool call's arguments or result, or a retrieval's member other than its source (a ref's
    excerpt is the record's excerpt: `bundle_content_problems`)."""
    if path[:1] == ("native_scoring",):
        return False
    if len(path) >= 3 and path[:2] == ("sources", "context_texts"):
        return False
    if len(path) >= 4 and path[:2] == ("sources", "turns"):
        if path[3] in ("question", "answer", "state"):
            return False
        if len(path) >= 6 and ((path[3] == "tool_calls" and path[5] in ("arguments", "result"))
                               or (path[3] == "retrievals" and path[5] != "source")):
            return False
    return True


def bundle_content_problems(b, content):
    """The bundle's side of the record-wide rule (L3 fix round 2): every string of the bundle that a record carries in
    clear (`_carried_in_clear`) carries no withheld content, outside the excerpt of a turn span (D-43, D-48), the agent
    description goal and role (D-41) and a tool-call name that a withheld text names as a whole token (D-41)."""
    refs = (b.get("graph") or {}).get("refs") or []
    p = []
    for path, text, key in _strings_at(b):
        at = path + (None,) if key else path          # a member name: the path of its object, then None
        if not _carried_in_clear(at) or (not key and path in (("provenance", "agent", "goal"), ("provenance", "agent", "role"))):
            continue
        if (not key and len(path) == 4 and path[:2] == ("graph", "refs") and path[3] == "excerpt" and isinstance(refs[path[2]], dict)
                and refs[path[2]].get("source_type") in _TURN_TEXTS):
            continue
        if not key and content.names(text) and ((len(path) == 6 and path[:2] == ("sources", "turns") and path[3] == "tool_calls"
                                                    and path[5] == "name") or (path[:2] == ("graph", "refs") and path[3:] == ("tool", "name"))):
            continue
        if (why := content.carried(text)) is not None:
            p.append(f"/{'/'.join(map(str, path))}{'/{member name}' if key else ''}: {why}: a record carries it (L3 fix round 2)")
    return p


# ---------------------------------------------------------------- L3 fix round 4: identifying shapes, the twin's reading
_DASHES = "\\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63"
_BETWEEN_DIGITS = "[\\s" + _DASHES + "._/()+,:;#*~|\\\\'\"]"          # what may stand between the digits of one value
_DIGIT_SEQ = re.compile("[0-9](?:" + _BETWEEN_DIGITS + "*[0-9])*")
_NUMBER_GROUPS = re.compile(r"[0-9]+(?:[-./ ][0-9]+)+")
_ALNUM = re.compile(r"[^\W_]+")
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-f]{16,}|[0-9A-F]{16,})(?![0-9A-Za-z])")
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CREDENTIALS = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/?#@]+@")
_KEY_PREFIX = re.compile(r"(?:(?:sk|pk|rk)[-_](?:live|test|proj)[-_]|sk-|AKIA|gh[pousr]_|xox[abprs]-|glpat-)[A-Za-z0-9_\-]{8,}")
_SHORT_DECIMAL = re.compile(r"[0-9]{1,3}\.[0-9]{1,2}")      # a score, a rate, a model family version (D-54)
_ALGORITHM_NAMES = ("base64", "sha256")
_H = "[0-9a-f]"
_SHA = re.compile("sha256:" + _H + "{64}")
_ID20 = re.compile(_H + "{20}")
_RUN = re.compile(_H + "{8}-" + _H + "{4}-" + _H + "{4}-" + _H + "{4}-" + _H + "{12}|archive:" + _H + "{64}")
_HEX16, _HEX40, _HEX24, _HEX12 = (re.compile(_H + "{%d}" % n) for n in (16, 40, 24, 12))
_STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})")
_SEMVER = re.compile(r"[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}(?:rc[0-9]{1,2}|\.dev[0-9])?(?:\+[a-z]{1,16})?")
_RELEASE_TEXTS = weakref.WeakKeyDictionary()    # a release reader -> every string it publishes


def _release_texts(e):
    if e not in _RELEASE_TEXTS:
        _RELEASE_TEXTS[e] = frozenset(s for _, s, _ in _strings_at(list(e.doc.values())) + _strings_at(
            json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8"))))
    return _RELEASE_TEXTS[e]


def _shape_reading(text):
    """NFKD of the unescaped text (`_unescaped`), without combining marks or invisible characters, a control character as a
    space, decimal digits as ASCII, look-alike letters as Latin."""
    return "".join(" " if unicodedata.category(ch) == "Cc" else _LATIN.get(ch) or _decimal(ch)
                   for ch in unicodedata.normalize("NFKD", _unescaped(text)) if not _invisible(ch))


def shapes_of(text):
    """The identifying shapes a producer string holds (L3 fix round 4), by name: digits (four or more, whatever separates
    them), groups (two digit groups or more joined by '-', '.', '/' or a space, fewer than four digits in all),
    alphanumeric (a letters-and-digits word of six or more with a digit; not an algorithm name), hex (sixteen or more),
    base64 (sixteen or more, both cases, a digit and a '+' or '/'), email, userinfo (credentials in a URL), secret (a key
    prefix). A short plain decimal ('0.5', '12.75', the '4.1' of a model name) is neither digits nor groups."""
    t = _shape_reading(text)
    found = set()
    if any(sum(c in "0123456789" for c in m.group()) > 3 and not _SHORT_DECIMAL.fullmatch(m.group()) for m in _DIGIT_SEQ.finditer(t)):
        found.add("digits")
    for m in _NUMBER_GROUPS.finditer(t):
        if sum(c in "0123456789" for c in m.group()) < 4 and not _SHORT_DECIMAL.fullmatch(m.group()):
            found.add("groups")
    for w in _ALNUM.findall(t):
        if len(w) > 5 and not w.isdigit() and any(c.isdigit() for c in w) and w.casefold() not in _ALGORITHM_NAMES:
            found.add("alphanumeric")
    if _LONG_HEX.search(t):
        found.add("hex")
    for m in _B64_RUN.finditer(t):
        x = m.group()
        if (set(x) & {"+", "/"}) and any(c.isdigit() for c in x) and any(c.isupper() for c in x) and any(c.islower() for c in x):
            found.add("base64")
    for name, rx in (("email", _MAIL), ("userinfo", _CREDENTIALS), ("secret", _KEY_PREFIX)):
        if rx.search(t):
            found.add(name)
    return found


def _field_forms(path, limitation):
    """The legitimate whole-value forms of the bundle field at `path` (the allowlist of L3 fix round 4; `limitation`: the
    id of the limitation whose parameter `path` is)."""
    last, n = path[-1], len(path)
    forms = []
    if isinstance(last, str) and (last in ("sha256", "plan_hash", "module_hash", "selected_digest") or last.endswith("_sha256")):
        forms.append(_SHA)
    head = path[:1]
    idx = [type(x) is int for x in path] + [False] * 7          # an index at each position (False past the end)
    if (head == ("claims",) and idx[1] and (path[2:] == ("id",) or (n == 4 and path[2] in ("evidence", "counterevidence") and idx[3]))
            or (path[:2] == ("graph", "refs") and n == 4 and idx[2] and last == "id")
            or (path[:2] == ("ballots", "ballots") and n == 4 and idx[2] and last == "claim_id")
            or (path[:2] == ("ballots", "pooled_claims") and n == 3 and idx[2])
            or (path[:2] == ("trials", "records") and n == 4 and idx[2] and last == "claim_id")
            or (head == ("limitations",) and n == 4 and idx[1] and path[2] == "params" and last in ("claim_id", "ref"))
            or (path[:3] == ("producer_declared", "context_links", "claims") and n == 4 and last is None)
            or (path[:4] == ("producer_declared", "score_inputs", "readiness", "cap_claims") and n == 5 and idx[4])
            or (path[:3] == ("producer_declared", "score_inputs", "metrics") and idx[3] and (
                (n == 6 and path[4] == "members" and idx[5]) or (n == 7 and path[4] == "contributions" and idx[5] and idx[6])))):
        forms.append(_ID20)
    if path in (("header", "run_id"), ("provenance", "record", "run", "run_id")) or (n == 3 and head == ("claims",) and idx[1]
                                                                                     and last == "run_id"):
        forms.append(_RUN)
    if path in (("header", "eio", "ontology_digest"), ("header", "producer_eio", "ontology_digest"), ("provenance", "capsule", "lock_digest")):
        forms.append(_HEX16)
    if path in (("provenance", "producer", "revision"), ("provenance", "record", "producer", "source_revision")):
        forms.append(_HEX40)
    if path == ("provenance", "record", "run", "config_fingerprint"):
        forms.append(_HEX24)
    params = head == ("limitations",) and n == 4 and idx[1] and path[2] == "params" and last in ("converter", "producer")
    if path == ("provenance", "record", "inputs", "checks_version") or (params and limitation == "per.lim.checks_version.mismatch"):
        forms.append(_HEX12)
    if path in (("provenance", "record", "run", "started_at"), ("provenance", "record", "run", "completed_at")):
        forms.append(_STAMP)
    if last in ("version", "predicate_version", "module_version", "release"):
        forms.append(_SEMVER)
    return forms


def shape_problems(b, e):
    """L3 fix round 4, the identifying-shape backstop: every string of the bundle that a record carries in clear
    (`_carried_in_clear`, member names included; a ref's excerpt is PROD-42's) holds no identifying shape (`shapes_of`),
    unless the whole value is a legitimate form of its field (`_field_forms`) or a string the release publishes."""
    lims = b.get("limitations") if isinstance(b.get("limitations"), list) else []
    public = _release_texts(e)
    p = []
    for path, text, key in _strings_at(b):
        at = path + (None,) if key else path
        if not _carried_in_clear(at) or (not key and len(path) == 4 and path[:2] == ("graph", "refs") and path[3] == "excerpt"):
            continue
        lim = None
        if (len(at) == 4 and at[0] == "limitations" and at[2] == "params" and type(at[1]) is int and at[1] < len(lims)
                and isinstance(lims[at[1]], dict)):
            lim = lims[at[1]].get("id")
        if text in public or any(f.fullmatch(text) for f in _field_forms(at, lim)):
            continue
        found = shapes_of(text)
        if found:
            p.append(f"/{'/'.join(map(str, path))}{'/{member name}' if key else ''}: an identifying-shaped token "
                     f"({', '.join(sorted(found))}) in a producer string a record carries in clear (L3 fix round 4)")
    return p


def _stage_problems(b):
    p = []
    paths = list(SECTIONS) + [f"producer_declared.{k}" for k in (b.get("producer_declared") or {})]
    if "native_scoring" in b:
        paths.append("native_scoring")
        if b["provenance"]["producer"]["kind"] != "native":
            p.append("native_scoring is accepted from native producers only")
        if any(r["producer"] != "native" for r in b["stage_records"] if "native_scoring" in r["sections"]):
            p.append("native_scoring must be filled by a native stage record")
    filled = [x for r in b["stage_records"] for x in r["sections"]]
    for x in paths:
        if filled.count(x) != 1:
            p.append(f"{x} is filled by {filled.count(x)} stage records")
    for x in sorted(set(filled) - set(paths)):
        p.append(f"a stage record names the unknown section {x}")
    decl = b.get("producer_declared")
    if decl is not None:                      # split plan §4.4: adapter producers only
        if b["provenance"]["producer"]["kind"] != "adapter":
            p.append("the producer-declared section is accepted from adapter producers only")
        if b["header"]["adapter"] is None or not (b["header"]["crosswalk"] or {}).get("sha256"):
            p.append("the producer-declared section needs a declared adapter and crosswalk digest")
        for k in decl:
            if any(r["producer"] != "adapter" for r in b["stage_records"] if f"producer_declared.{k}" in r["sections"]):
                p.append(f"producer_declared.{k} is filled by a stage record that is not producer adapter")
    if b["provenance"]["producer"]["kind"] == "native":        # a native bundle is its own archive, with no adapter section
        if b["header"]["source_archive"] is not None:
            p.append("a native bundle declares a source archive (it is its own archive)")
        p += [f"stage {r['stage']} is producer {r['producer']} in a native producer's bundle" for r in b["stage_records"]
              if r["producer"] != "native"]
    return p


def _vocabulary_problems(b, e):
    p = []
    for a in b["sources"]["context_artifacts"]:        # PROD-43 keys on the data class (L2 exit D-29)
        if a["artifact_kind"] not in e.artifact_kinds:
            p.append(f"context artifact {a['name']!r}: artifact_kind {a['artifact_kind']!r} is not a context-artifact kind of the release")
        if a["data_class"] not in e.data_classes or not DATA_CLASS_ID.fullmatch(a["data_class"]):
            p.append(f"context artifact {a['name']!r}: data_class {a['data_class']!r} is not a data class of the release "
                     "(an eio.data.* concept of kind data-class; L3 fix round 2: the PER schema's form)")
    for c in b["claims"]:
        if c["state"] not in e.states:
            p.append(f"claim {c['id']}: state {c['state']!r} is not an EIO decision state")
        if c["predicate"] not in e.pred:
            p.append(f"claim {c['id']}: unknown predicate {c['predicate']}")
        # L3 fix round 3: the claim rules `convert` recomputes and C2 reads in a record, named here too
        if (c["parameters"].get("votes") is None) != (c["decided_by"] == "deterministic"):
            p.append(f"claim {c['id']}: votes null iff deterministic (EIO-54)")
        if c["decided_by"] == "human" and not any(isinstance(r, dict) and r.get("id") in c["evidence"] and (r.get("kind"), r.get(
                "source_type")) == ("HUMAN_SIGNOFF", "HUMAN_REVIEW") for r in b["graph"]["refs"]):
            p.append(f"claim {c['id']}: a human decision cites no HUMAN_SIGNOFF ref over HUMAN_REVIEW (eio.profile.resolver-authority)")
    tr = b.get("trials")
    if isinstance(tr, dict) and isinstance(tr.get("tasks"), int) and tr["tasks"] >= e.minimum_tasks:
        p += [f"trials.rate.{k} is null, but the rate is published ({tr['tasks']} tasks, the floor {e.minimum_tasks}): a published "
              "rate states its values (L3 fix round 3)" for k in ("pass_1", "pass_k", "pass_1_se", "pass_k_se")
              if (tr.get("rate") or {}).get(k) is None]
    native = b["provenance"]["producer"]["kind"] == "native"
    for r in b["graph"]["refs"]:
        if r["kind"] not in e.kinds or r["source_type"] not in e.sources or r["anchor"] not in e.anchors:
            p.append(f"ref {r['id']}: unknown kind, source type or anchor {r['kind']}/{r['source_type']}/{r['anchor']}")
        elif r["source_type"] not in e.kinds[r["kind"]]["compatible_source_types"]:
            p.append(f"ref {r['id']}: source type {r['source_type']} is not compatible with kind {r['kind']}")
        if native and r["source_type"] == "JUROR_INFERENCE":
            p.append(f"ref {r['id']}: a native producer mints no JUROR_INFERENCE ref")
    sc = b["scope"]
    for key, known in (("tier", e.tiers), ("region", e.regions), ("autonomy", e.autonomy)):
        if sc[key] is not None and sc[key] not in known:
            p.append(f"scope.{key} {sc[key]!r} is not in the release")
    p += [f"unknown domain {d['id']}" for d in sc["domain_candidates"] if d["id"] not in e.domains]
    p += [f"unknown fact {k}" for k in sc["facts"] if k not in e.facts]
    p += [f"unknown framework {f['id']}" for f in sc["frameworks"]["candidates"] if f["id"] not in e.frameworks]
    pol = sc["policy"]
    if pol["source"] not in POLICY_SOURCES:
        p.append(f"unknown policy source {pol['source']!r}")
    elif pol["source"] != "none" and not (isinstance(pol["rules"], dict) and str(pol["rules"].get("block_severity")).upper() in SEVERITIES):
        p.append("a policy object with a source needs rules with a known block_severity")
    # L3 fix round 2 (untyped KeyErrors in the projector, now typed): a score-input axis names context criteria of the
    # release, and a producer limitation is a catalogue row whose texts its parameters fill
    for ax in ((b.get("producer_declared") or {}).get("score_inputs") or {}).get("axes") or []:
        p += [f"score-input axis {ax.get('axis')!r:.60}: unknown context criterion {c!r:.80}" for c in ax.get("context_criteria") or []
              if c not in e.criteria]
    cat = load_catalogue()
    for x in b["limitations"]:
        row = cat.get(x["id"])
        if row is None:
            p.append(f"limitation {x['id']!r:.80} is not in the 04 §5.13 catalogue")
            continue
        texts = [row["reason"], row["impact"], row["next_step"]] + ([row["paths"][0]] if not x.get("path") else [])
        need = {f for t in texts for _, f, _, _ in string.Formatter().parse(t) if f}
        if not need <= set(x.get("params") or {}):
            p.append(f"limitation {x['id']}: its parameters {sorted(x.get('params') or {})!r:.100} do not fill its catalogue texts "
                     f"(missing {sorted(need - set(x.get('params') or {}))!r:.80})")
    content = Content(b, e)                              # L3 fix round 2: no name or other text the record carries holds
    return (p + declared_item_problems(b, e) + content_problems(b, content) + bundle_content_problems(b, content)
            + shape_problems(b, e))                      # L3 fix round 4: nor an identifying-shaped token


def _score_profile_problems(b):
    """B4: independently check the score-input profile schema, identity and JCS digest."""
    si = (b.get("producer_declared") or {}).get("score_inputs")
    if not si:
        return []
    prof, p = si["profile"], []
    doc = prof.get("document")
    if prof["verifiability"] == "attested":
        if b["provenance"]["producer"]["kind"] != "adapter":
            p.append("an attested scoring profile is accepted from adapter producers only")
        if not isinstance(doc, dict):
            return p + ["an attested scoring profile travels with its document"]
        # Independent B4 authority check: a self-declared digest does not make arbitrary public IDs safe.
        approved_g = ("release_gate", "human_oversight", "policy_conformance", "obligation_coverage",
                      "evidence_freshness", "prohibited_use_case")
        if (doc.get("id"), doc.get("version")) != ("harness-2.x", "2.1.0"):
            p.append("the attested profile id/version is not approved for public PER fields")
        if tuple(doc.get("g_component_ids") or ()) != approved_g:
            p.append("the attested profile G component ids differ from the reviewed public set")
    if isinstance(doc, dict):
        p += [f"profile document /{'/'.join(map(str, e.path))}: {e.message[:120]}"
              for e in Draft202012Validator(scoring_profile_schema()).iter_errors(doc)]
        if (doc.get("id"), doc.get("version"), doc.get("verifiability")) != (prof["id"], prof["version"], prof["verifiability"]):
            p.append("the declared profile id, version or verifiability differs from its document's")
        got = _sha(_jb({k: v for k, v in doc.items() if k != "sha256"}))
        if prof["sha256"] != got:
            p.append(f"the declared profile sha256 {prof['sha256']} is not the document's digest {got}")
    return p


def validate_bundle(bundle, *, eio=None):
    """Check an evaluation bundle (dict, bytes or JSON text): its text as I-JSON (B0), its schema and the name rules the
    schema cannot state (B1), its stage records, the producer-declared acceptance rule and the native-producer rules
    (B2), and the closed vocabularies of the release (B3). Returns the failing checks as `{check, ver, status, detail}`;
    [] when the bundle passes these checks. It does not recompute ids, refs, computed statements, pointers, episodes or
    digests: `eio_agents.convert` does, so [] here does not mean that the bundle converts."""
    try:
        bundle = bundle_of(bundle)
    except (ValueError, RecursionError) as ex:               # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return [{"check": "B0 an archive-schema-3 bundle", "ver": "BUNDLE", "status": "FAIL",
                 "detail": f"not a readable bundle: I-JSON, at most {MAX_DEPTH} levels ({type(ex).__name__}: {str(ex)[:200]})"}]
    if not isinstance(bundle, dict) or bundle.get("archive_schema") != 3:
        return [{"check": "B0 an archive-schema-3 bundle", "ver": "BUNDLE", "status": "FAIL",
                 "detail": "not an evaluation bundle (archive schema 3); a stored report goes through its producer's adapter"}]
    rows = []

    def run(name, fn):
        try:
            problems = fn()
        except Exception as ex:                          # a crash is a failure, never a pass
            problems = [f"{type(ex).__name__}: {ex}"]
        rows.append((name, "BUNDLE", "FAIL" if problems else "PASS",
                     f"{len(problems)} problem(s); first: {problems[0]}" if problems else ""))
        return not problems
    if run("B1 bundle schema (archive schema 3, draft 1) and its name rules", lambda: _bundle_schema_problems(bundle)):
        run("B2 stage records and the producer-declared section (§4.4)", lambda: _stage_problems(bundle))
        e = eio if eio is not None else EIO(EIO_DIR)
        run("B3 closed vocabularies of the release", lambda: _vocabulary_problems(bundle, e))
        run("B4 the declared scoring profile (schema, digest)", lambda: _score_profile_problems(bundle))
    return rows_as_problems(r for r in rows if r[2] == "FAIL")
