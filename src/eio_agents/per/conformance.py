"""Step 7 of the projection (contract §6.2): the projected record is validated in process before it is returned.

`check_record(eio, rec, native)` validates the record against the PER schema of its `header.per_version` (HEAD projects
2.0.0-rc2-draft from L4, whose only change is the scores block; the rc1 schema stays for stored records until L5a) and checks that every EIO id it names exists in the loaded release. Any problem fails the projection with the typed
code `PER_INVALID`. For a record projected from a native producer's bundle, the rc1 requirements that carry ProofAgent
vocabulary cannot be met (split plan §5.3); exactly those schema errors are accepted, as listed with the §5.3 row that
removes each in `data/rc1_only.json` (X-NATIVE pins the same list). Each row names the error's path, validator and full
message, so a row accepts only the rc1 error its §5.3 row removes: `'producer' is not one of [...]`, `3 is not one of
[1, 2]`, the §5.3 producer field names, the counts of a pooled vote, an empty `traps`, and pointers into the bundle itself
(the projector checks that a native bundle's pointers resolve into its own `/sources`, `per.bundle.check_native_sources`).
The rows that are not about the producer (`scores` null, and the null readiness a policy rule then observes) apply to any
bundle that declares no scoring profile (split plan §6.2 L2 task 4). No other relaxation exists.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from eio_agents.base.errors import require
from eio_agents.per.limitations import catalogue_paths
from eio_agents.schemas import PER_SCHEMAS, per_schema

RC1_ONLY = Path(__file__).resolve().parent / "data" / "rc1_only.json"


@lru_cache(maxsize=1)
def rc1_only_rows():
    """The rc1-only relaxation rows `(path regex, validator, message regex, removed_by)`: immutable data read once."""
    doc = json.loads(RC1_ONLY.read_text(encoding="utf-8"))
    return tuple((re.compile(r["path"] + "$"), r["validator"], re.compile(r["message"] + "$"), r["removed_by"], r["applies_to"])
                 for r in doc["rows"])


def rc1_only(error_path, validator, message, *, native=True, scored=False):
    """The §5.3 row that removes this rc1 schema error, or None: a `native` row applies to a native producer's record,
    the `no_scoring_profile` row to a record whose bundle declares no scoring profile (`scored` False)."""
    for path, v, msg, row, applies in rc1_only_rows():
        if v == validator and path.match(error_path) and msg.match(message):
            return row if (native if applies == "native" else not scored) else None
    return None


def schema_errors(rec):
    """Every PER-schema error of `rec` as `(instance path, validator, message)`, in path order, against the schema of its
    `header.per_version` (rc2-draft, or rc1 for a stored record; LS8). An unknown version is one error."""
    ver = (rec.get("header") or {}).get("per_version") if isinstance(rec, dict) else None
    if ver not in PER_SCHEMAS:
        return [("header/per_version", "const", f"{ver!r} is not a PER version of this build ({sorted(PER_SCHEMAS)})")]
    errs = Draft202012Validator(per_schema(ver), format_checker=FormatChecker()).iter_errors(rec)
    return sorted((("/".join(map(str, e.absolute_path)), e.validator, e.message) for e in errs), key=lambda x: (x[0], x[2]))


def id_problems(eio, rec):
    """EIO ids of the record that the loaded release does not define (the ids of every claim, ref, scope row, obligation,
    control, metric and explanation template)."""
    p = []
    for c in rec["claims"]:
        if c["predicate"] not in eio.pred or c["state"] not in eio.states:
            p.append(f"claim {c['id']}: predicate or state not in the release")
    for r in rec["evidence"]["refs"]:
        if r["kind"] not in eio.kind or r["source_type"] not in eio.source_type or r["anchor"] not in eio.anchors:
            p.append(f"ref {r['id']}: kind, source type or anchor not in the release")
    sc = rec["scope"]
    p += [f"domain {d['id']}" for d in sc["domains"] if d["id"] not in eio.domains]
    if sc["tier"] and sc["tier"]["id"] not in eio.tiers:
        p.append(f"tier {sc['tier']['id']}")
    if sc["region"] and sc["region"] not in eio.regions:
        p.append(f"region {sc['region']}")
    if sc["autonomy"] and sc["autonomy"] not in eio.autonomy:
        p.append(f"autonomy {sc['autonomy']}")
    p += [f"framework {f['id']}" for f in sc["frameworks"] if f["id"] not in eio.frameworks]
    p += [f"obligation {o['id']}" for o in rec["coverage"]["obligations"] if o["id"] not in eio.obligation]
    p += [f"control {k['control_id']}" for k in rec["controls"] if k["control_id"] not in eio.controls]
    metrics = {m["id"] for m in eio.metrics}
    p += [f"metric {m['metric']}" for m in (rec["scores"] or {}).get("metrics") or [] if m["metric"] not in metrics]

    def walk(o):
        if isinstance(o, dict):
            if "template_id" in o and "summary" in o and o["template_id"] not in eio.templates:
                p.append(f"template {o['template_id']}")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(rec)
    return p


# PER Pointers (03 §7.13 PROD-36): an identifier token selects an element of these id-keyed arrays, a numeric index any other
ID_KEYED = {("claims",): "id", ("evidence", "refs"): "id", ("findings",): "finding_id", ("controls",): "control_id",
            ("coverage", "obligations"): "id", ("scores", "metrics"): "metric"}
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def resolves(rec, pointer):
    """Whether the PER Pointer names a value of `rec` (PROD-36: an id-keyed array element by its identifier)."""
    if not pointer.startswith("/"):
        return False
    cur, at = rec, ()
    for tok in (pointer[1:].split("/") if pointer != "/" else []):
        tok = tok.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and tok in cur:
            cur, at = cur[tok], at + (tok,)
        elif isinstance(cur, list) and at in ID_KEYED:
            hit = [x for x in cur if isinstance(x, dict) and x.get(ID_KEYED[at]) == tok]
            if len(hit) != 1:
                return False
            cur, at = hit[0], at + ("*",)
        elif isinstance(cur, list) and re.fullmatch(r"[0-9]+", tok) and int(tok) < len(cur):
            cur, at = cur[int(tok)], at + ("*",)
        else:
            return False
    return True


def limitation_problems(rec):
    """A limitation's field path is one of its catalogue paths, and a path the producer completes (a catalogue path with a
    `{name}` placeholder: a finding, claim, ref or metric) names a value of the record (L3 fix round 2: a producer's
    limitation path is read as the verifier reads it, T1 and P1; a fixed catalogue path may name a block a record without
    a scoring profile leaves null, the rc1-only relaxation of split plan §6.2)."""
    paths, p = catalogue_paths(), []
    for x in rec["limitations"]:
        fp = x["field_path"]
        hit = [c for c in paths.get(x["limitation_id"], [])
               if re.fullmatch("".join("[^/]+" if PLACEHOLDER.fullmatch(part) else re.escape(part)
                                       for part in re.split(r"(\{[a-z_]+\})", c)), fp)]
        if not hit:
            p.append(f"{x['limitation_id']}: field_path {fp[:80]!r} is not a catalogue path of the limitation")
        elif all(PLACEHOLDER.search(c) for c in hit) and not resolves(rec, fp):
            p.append(f"{x['limitation_id']}: field_path {fp[:80]!r} names no value of the record")
    return p


def check_record(eio, rec, native):
    """Fail closed (`PER_INVALID`) unless `rec` is a valid PER record of the loaded release; for a native producer's
    record the rc1-only schema errors of `data/rc1_only.json` are accepted."""
    scored = rec["scores"] is not None
    errs = [e for e in schema_errors(rec) if not rc1_only(*e, native=native, scored=scored)]
    require(not errs, "PER_INVALID", f"{len(errs)} schema error(s); first: /{errs[0][0]}: {errs[0][2][:200]}" if errs else "")
    ids = id_problems(eio, rec)
    require(not ids, "PER_INVALID", f"{len(ids)} id(s) not in EIO {eio.release}; first: {ids[0]}" if ids else "")
    lims = limitation_problems(rec)
    require(not lims, "PER_INVALID", f"{len(lims)} limitation path(s) outside the catalogue or the record; first: {lims[0]}" if lims else "")
