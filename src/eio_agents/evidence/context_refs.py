"""Context refs over the embedded context artifacts (04 MAP-28, §4.6; PER-507).

A lexical hit is a POLICY_SPAN on the line of the first casefold match of a checklist term (relation related_rule); no hit
is a TYPED_ABSENCE over the searched artifacts (relation absent_control). `artifacts` are the embedded context-artifact
descriptors (`artifact_kind`, `name`, `sha256`, `data_class`); `texts` maps an artifact name to its text.

PROD-43 withholds the excerpt of a model-confidential artifact. Read fail-closed since L3 (F-12 of the L2 re-verification):
the excerpt of every artifact whose data class is not `eio.data.public` or `eio.data.internal` is withheld (`withheld`),
and an artifact is read as the most restrictive declaration of its content (`confidential_digests`, `effective`: the same
bytes under another name or class stay withheld; L2 exit D-32), and so does the same text in another Unicode normal form
or with other line ends or trailing white space (`normalized_digest`; L3 fix round 1, issue 3). A text whose casefold changes
its length ('ß' -> 'ss') is searched through an offset map, never skipped, so no false absence is derived (L2 exit D-33);
the search reads the casefold with the dot above an i dropped (`fold`: 'İ' folds to 'i' + U+0307, so 'VERİFY' would not
contain 'verify'; L3 fix round 1, issue 7).
"""
import hashlib
import unicodedata

from eio_agents.base.canon import H, jcs
from eio_agents.base.errors import require
from eio_agents.evidence.redaction import excerpt_of
from eio_agents.evidence.witness import can_prove
from eio_agents.semantics import ids

MODEL_CONFIDENTIAL = "eio.data.model-confidential"
# The data classes whose text a record may quote (PROD-42 excerpt). PROD-43 names model-confidential; every other class of
# the release (a child of internal such as authentication-secret or source-code, and personal data) is withheld as well
# (L3, the fail-closed reading of F-12; spec text at L5b). Byte-neutral: the shipped artifacts are internal or
# model-confidential.
EXCERPTABLE = frozenset({"eio.data.public", "eio.data.internal"})


def withheld(data_class):
    """Whether a context artifact of `data_class` is never quoted (PROD-43, read fail-closed: see `EXCERPTABLE`)."""
    return data_class not in EXCERPTABLE


def normalized_digest(text):
    """The digest of a text as a reader compares texts: Unicode NFC, line ends LF, the trailing white space of every line
    and the trailing line ends removed (L3 fix round 1, issue 3: the same text re-encoded is the same content)."""
    t = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(line.rstrip() for line in t.split("\n")).rstrip("\n")
    return "sha256n:" + hashlib.sha256(t.encode("utf-8")).hexdigest()


def confidential_digests(artifacts, texts=None):
    """The content digests that any declared context artifact (embedded or not) gives a withheld class (`withheld`): its
    declared digest, and the normalized digest of its text when the text is embedded (`texts`: name -> text)."""
    out = {a["sha256"] for a in artifacts if withheld(a.get("data_class"))}
    for a in artifacts:
        if withheld(a.get("data_class")) and texts is not None and isinstance(texts.get(a.get("name")), str):
            out.add(normalized_digest(texts[a["name"]]))
    return out


def effective(art, confidential, text=None):
    """The artifact as PROD-43 reads it: withheld (read as model-confidential) when any artifact declares its content with
    a withheld class (`confidential`, from `confidential_digests`: the same bytes, or the same normalized text when `text`,
    the artifact's embedded text, is given); otherwise as declared."""
    same = art["sha256"] in confidential or (text is not None and normalized_digest(text) in confidential)
    if same and not withheld(art["data_class"]):
        return dict(art, data_class=MODEL_CONFIDENTIAL)
    return art


def casefold_offsets(text):
    """For each code point of `text.casefold()`, the index in `text` of the character it folds from (casefold is per
    character, and may give more than one code point: 'ß' -> 'ss')."""
    out = []
    for i, ch in enumerate(text):
        out.extend([i] * len(ch.casefold()))
    return out


def fold_map(text):
    """`(fold(text), offsets)`: the casefold of `text` with the dot above an i dropped (U+0307 after 'i': 'İ' folds to
    'i' + U+0307), and for each of its code points the index in `text` of the character it folds from."""
    out, where = [], []
    for i, ch in enumerate(text):
        for f in ch.casefold():
            if f == "\u0307" and out and out[-1] == "i":
                continue
            out.append(f)
            where.append(i)
    return "".join(out), where


def fold(text):
    """The text a context search compares (`fold_map`): casefold, with the dot above an i dropped (L3 fix round 1, issue 7)."""
    return fold_map(text)[0]


def context_line_ref(eio, criterion, control, artifacts, texts):
    """The POLICY_SPAN ref on the line of the first casefold checklist-term match, or None (lexical: related_rule)."""
    terms = [c for c in eio.criteria[criterion].get("controls") or [] if c["id"] == control][0]["requires_any"]
    evaluates = eio.criteria[criterion].get("evaluates") or []
    searched = [a for k in evaluates for a in sorted(artifacts, key=lambda a: a["name"]) if a["artifact_kind"] == k]
    for art in searched:                                   # 04 §4.6: evaluates order, then artifact-name order
        text = texts[art["name"]]
        cf, where = fold_map(text)                         # a length change is mapped, not skipped (D-33); 'İ' reads as 'i'
        hits = sorted((cf.find(fold(t)), k, t) for k, t in enumerate(terms) if cf.find(fold(t)) >= 0)
        if not hits:
            continue
        i = where[hits[0][0]]
        a = text.rfind("\n", 0, i) + 1
        b = text.find("\n", i)
        b = len(text) if b < 0 else b
        return policy_span_ref(eio, art, text, a, b)
    return None


def policy_span_ref(eio, art, text, a, b, anchor="line"):
    """The POLICY_SPAN ref over `text[a:b]`, `text` being the embedded text of the context artifact `art`. An
    `eio.data.model-confidential` artifact (and, read fail-closed, any withheld class: `withheld`) gives no excerpt, with
    `excerpt_redacted` true (PROD-43); a public or internal one gives the PROD-42 excerpt. An exact or casefold span quotes
    at least one character (L2 exit D-35, F-10)."""
    require(a < b or anchor not in ("exact", "casefold"), "INVARIANT", f"an {anchor} span [{a}, {b}) quotes nothing")
    x = text[a:b]
    rid = ids.ref_id("POLICY_SPAN", "POLICY_SOURCE", None, x, a, b)
    r = {"id": rid, "kind": "POLICY_SPAN", "source_type": "POLICY_SOURCE",
         "can_prove_agent_behaviour": can_prove(eio, "POLICY_SPAN", "POLICY_SOURCE"),
         "anchor": anchor, "turn_index": None, "char_start": a, "char_end": b, "span_sha256": H(x)}
    if withheld(art["data_class"]):
        r["excerpt_redacted"] = True                                                    # PROD-43: excerpt omitted
    else:
        ex, cut, red = excerpt_of(x)
        r["excerpt"] = ex
        if cut:
            r["excerpt_truncated"] = True
        if red:
            r["excerpt_redacted"] = True
    r.update({"source_ref": art["name"], "source_sha256": art["sha256"]})
    return r


def ctx_absence_ref(eio, files, chars, terms):
    """The TYPED_ABSENCE ref of no casefold occurrence of any term in the searched artifacts (absent_control)."""
    files = sorted(files)
    x = "no casefold occurrence of " + jcs(terms) + " in context artifacts " + jcs(files) + " (" + str(chars) + " characters searched)"
    rid = ids.ref_id("TYPED_ABSENCE", "POLICY_SOURCE", None, x)
    return {"id": rid, "kind": "TYPED_ABSENCE", "source_type": "POLICY_SOURCE",
            "can_prove_agent_behaviour": can_prove(eio, "TYPED_ABSENCE", "POLICY_SOURCE"),
            "anchor": "computed", "turn_index": None, "char_start": None, "char_end": None, "span_sha256": None,
            "source_ref": "context" if len(files) > 1 else files[0], "source_sha256": None,
            "statement": {"inputs": {"files_searched": files, "chars_searched": chars, "requires_any": terms},
                          "formula": "count(term in casefold(file) for file in files_searched for term in requires_any)",
                          "output": 0}}


def context_refs_for_criterion(store, eio, criterion, artifacts, texts):
    """The related_rule context refs of a context criterion, one per line (04 §4.6 rule 2); the refs are put in `store`."""
    out = []
    for ctl in eio.criteria[criterion].get("controls") or []:
        r = context_line_ref(eio, criterion, ctl["id"], artifacts, texts)
        rid = store.put(r) if r is not None else None
        if rid and rid not in [x["ref_id"] for x in out]:                 # 04 §4.6 rule 2: a line is cited once
            out.append({"ref_id": rid, "relation": "related_rule", "via": f"eio.context.criteria:{criterion}/{ctl['id']}"})
    return out
