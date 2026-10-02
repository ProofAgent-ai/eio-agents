"""Draft LS9 core/declared catalogue mechanics.

Declared catalogues are copied into the PER header. A verifier needs only the
record and the neutral core catalogue; it must never fetch adapter data by URL.
The wire field names and the sample ProofAgent prefix are draft pending owner
review, so this module is not yet routed into the released converter.
"""

from __future__ import annotations

import json
import re
import string
from pathlib import Path

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import ConversionError, require

CORE_LIMITATIONS = Path(__file__).resolve().parent / "data" / "limitations-core.json"
RC1_TO_CORE_ID = {
    "per.lim.harness_llm.per_stage": "per.lim.evaluator_model.per_stage",
    "per.lim.harness_llm.fallback_unattributed": "per.lim.evaluator_model.fallback_unattributed",
    "per.lim.sentinel_locations.not_captured": "per.lim.input_locations.not_captured",
    "per.lim.code_check_offsets.not_captured": "per.lim.deterministic_check_offsets.not_captured",
    "per.lim.anchor.sentinel_location": "per.lim.anchor.input_location",
}
_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+@[1-9][0-9]*$")
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROW_FIELDS = {"id", "status", "paths", "raised_when", "reason", "impact", "next_step"}
_STATUSES = {"NOT_SUPPLIED", "NOT_CAPTURED", "NOT_APPLICABLE"}
_FINGERPRINT = re.compile(r"sha256-[0-9a-f]{64}")
_COUNT = re.compile(r"0|[1-9][0-9]{0,6}")
_IDENTIFIER = re.compile(r"[0-9a-f]{20,64}|urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_PREDICATE = re.compile(r"eio\.predicate\.[a-z0-9][a-z0-9-]*")
_RELEASE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")
_DIGEST = re.compile(r"[0-9a-f]{16,64}|sha256:[0-9a-f]{64}")
_PARAM_FORMS = {
    **dict.fromkeys(("turn", "calls", "total", "n", "hits", "scored"), _COUNT),
    **dict.fromkeys(("ref", "finding_id", "claim_id"), _IDENTIFIER),
    "predicate": _PREDICATE,
    "producer_release": _RELEASE,
    "producer_digest": _DIGEST,
}


def _safe_param(name: str, value: str) -> bool:
    """A catalogue placeholder is a closed structural value or a fingerprint, never free text."""
    if not isinstance(value, str) or not value or len(value) > 128:
        return False
    if _FINGERPRINT.fullmatch(value):
        return True
    pattern = _PARAM_FORMS.get(name)
    return pattern is not None and pattern.fullmatch(value) is not None


def _template_values(template: str, rendered: str) -> dict[str, str] | None:
    parts, names = [], []
    for literal, name, format_spec, conversion in string.Formatter().parse(template):
        if format_spec or conversion is not None:
            return None
        parts.append(re.escape(literal))
        if name is not None:
            if re.fullmatch(r"[a-z_]+", name) is None:
                return None
            names.append(name)
            parts.append("(.+?)")
    match = re.fullmatch("".join(parts), rendered, re.S)
    if match is None:
        return None
    values = {}
    for name, value in zip(names, match.groups()):
        if not _safe_param(name, value) or (name in values and values[name] != value):
            return None
        values[name] = value
    return values


def catalogue_sha256(document: dict) -> str:
    """Content address of exactly the embedded declaration, excluding sha256."""
    require(isinstance(document, dict), "CATALOGUE_SCHEMA", "catalogue must be an object")
    return H(jb({key: value for key, value in document.items() if key != "sha256"}))


def _rows(document: dict, *, kind: str, declared: bool, occupied: set[str]) -> dict:
    require(isinstance(document, dict), "CATALOGUE_SCHEMA", "catalogue must be an object")
    expected = {"id", "version", kind} | ({"sha256"} if declared else set())
    require(set(document) == expected, "CATALOGUE_SCHEMA", f"{kind}: expected {sorted(expected)}")
    cid, version = document["id"], document["version"]
    require(isinstance(cid, str) and _ID.fullmatch(cid) is not None,
            "CATALOGUE_ID", "catalogue id must be a qualified identifier")
    require(isinstance(version, str) and version, "CATALOGUE_SCHEMA", "catalogue version is required")
    if declared:
        digest = document["sha256"]
        require(isinstance(digest, str) and _SHA.fullmatch(digest) is not None and digest == catalogue_sha256(document),
                "CATALOGUE_DIGEST", "embedded catalogue digest mismatch")
        require(not cid.startswith("per.lim") and not cid.startswith("eio."),
                "CATALOGUE_ID", "declared catalogue must not use a core namespace")
    else:
        require(cid == "per.lim.core" if kind == "limitations" else cid == "eio.why.core",
                "CATALOGUE_ID", "unexpected core catalogue id")
    rows = document[kind]
    require(isinstance(rows, list), "CATALOGUE_SCHEMA", f"{kind} must be an array")
    out = {}
    for row in rows:
        require(isinstance(row, dict), "CATALOGUE_SCHEMA", "catalogue row must be an object")
        rid = row.get("id")
        pattern = _ID if kind == "limitations" else _TEMPLATE_ID
        require(isinstance(rid, str) and pattern.fullmatch(rid) is not None,
                "CATALOGUE_ID", "catalogue row id is invalid")
        prefix = f"{cid}." if declared else ("per.lim." if kind == "limitations" else "eio.why.")
        require(rid.startswith(prefix), "CATALOGUE_ID", f"{rid} is outside catalogue {cid}")
        require(rid not in occupied and rid not in out, "CATALOGUE_COLLISION", f"duplicate catalogue id {rid}")
        if kind == "limitations":
            require(set(row) == _ROW_FIELDS and row.get("status") in _STATUSES,
                    "CATALOGUE_SCHEMA", f"malformed limitation {rid}")
            require(isinstance(row["paths"], list) and row["paths"] and
                    all(isinstance(path, str) and path.startswith("/") for path in row["paths"]),
                    "CATALOGUE_SCHEMA", f"malformed paths in {rid}")
            require(all(isinstance(row[k], str) and row[k] for k in ("reason", "impact", "next_step")),
                    "CATALOGUE_SCHEMA", f"missing text in {rid}")
        else:
            require(set(row) == {"id", "text", "params", "max_length"} and
                    isinstance(row["text"], str) and row["text"] and
                    isinstance(row["params"], list) and
                    isinstance(row["max_length"], int) and row["max_length"] > 0,
                    "CATALOGUE_SCHEMA", f"malformed template {rid}")
        out[rid] = row
    return out


def merge_catalogues(core: dict, header: dict, *, kind: str) -> dict:
    """Fail closed on unknown, colliding or digest-mismatched embedded catalogues."""
    require(kind in {"limitations", "templates"}, "CATALOGUE_SCHEMA", "unknown catalogue kind")
    require(isinstance(header, dict), "CATALOGUE_SCHEMA", "PER header must be an object")
    merged = _rows(core, kind=kind, declared=False, occupied=set())
    field = "declared_limitation_catalogues" if kind == "limitations" else "declared_template_catalogues"
    declarations = header.get(field, [])
    require(isinstance(declarations, list), "CATALOGUE_SCHEMA", f"{field} must be an array")
    catalogue_ids = set()
    for declaration in declarations:
        require(isinstance(declaration, dict), "CATALOGUE_SCHEMA", "declaration must be an object")
        cid = declaration.get("id")
        require(isinstance(cid, str), "CATALOGUE_ID", "catalogue id must be a string")
        require(cid not in catalogue_ids, "CATALOGUE_COLLISION", "duplicate catalogue declaration")
        catalogue_ids.add(cid)
        merged.update(_rows(declaration, kind=kind, declared=True, occupied=set(merged)))
    return merged


def load_core_limitations(path: Path = CORE_LIMITATIONS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_limitation_row(row: dict, catalogue: dict) -> None:
    """Check an emitted row against core plus declared text/path/status rules."""
    require(isinstance(row, dict), "LIMITATION_SCHEMA", "limitation must be an object")
    lid = row.get("limitation_id")
    require(isinstance(lid, str) and lid in catalogue, "UNKNOWN_LIMITATION", f"undeclared limitation {lid}")
    spec = catalogue[lid]
    require(row.get("status") == spec["status"], "LIMITATION_STATUS", f"status differs for {lid}")
    path = row.get("field_path")
    require(isinstance(path, str) and any(_template_values(pattern, path) is not None for pattern in spec["paths"]),
            "LIMITATION_PATH", f"path differs or has unsafe placeholder for {lid}")
    values = {}
    for field in ("reason", "impact", "next_step"):
        found = _template_values(spec[field], row.get(field)) if isinstance(row.get(field), str) else None
        require(found is not None, "LIMITATION_TEXT", f"{field} differs or has unsafe placeholder for {lid}")
        require(all(name not in values or values[name] == value for name, value in found.items()),
                "LIMITATION_PARAM", f"conflicting placeholder for {lid}")
        values.update(found)


def render_limitation_row(catalogue: dict, lid: str, *, path: str | None = None, **params) -> dict:
    """Produce a row from pinned core/declared data, never freehand text."""
    require(lid in catalogue, "UNKNOWN_LIMITATION", f"undeclared limitation {lid}")
    require(all(_safe_param(name, str(value)) for name, value in params.items()),
            "LIMITATION_PARAM", f"unsafe placeholder for {lid}")
    spec = catalogue[lid]
    try:
        row = {"limitation_id": lid, "field_path": path or spec["paths"][0].format(**params),
               "status": spec["status"],
               **{field: spec[field].format(**params) for field in ("reason", "impact", "next_step")}}
    except (KeyError, IndexError, ValueError) as exc:
        raise ConversionError(f"TEMPLATE_PARAMS: {lid}: missing or invalid parameters", code="TEMPLATE_PARAMS") from exc
    verify_limitation_row(row, catalogue)
    return row


def validate_record_catalogues(record: dict, *, core_limitations: dict | None = None,
                               core_templates: dict | None = None) -> dict:
    """Self-contained LS9 gate; verifies all limitation rows against header declarations.

    A core template document can be supplied when the L5a neutral template
    catalogue has landed. Until then, limitation verification is independent.
    """
    require(isinstance(record, dict) and isinstance(record.get("header"), dict),
            "CATALOGUE_SCHEMA", "PER record must have a header")
    header = record["header"]
    limitations = merge_catalogues(core_limitations or load_core_limitations(), header, kind="limitations")
    require(isinstance(record.get("limitations"), list), "LIMITATION_SCHEMA", "limitations must be an array")
    for row in record["limitations"]:
        verify_limitation_row(row, limitations)
    if core_templates is not None:
        merge_catalogues(core_templates, header, kind="templates")
    return limitations


def migrate_rc1_core_row(row: dict, old_spec: dict, core_catalogue: dict,
                         new_id: str | None = None) -> dict:
    """Temporary native-preview bridge, until projection emits neutral rows directly.

    Extract only values proven to match the frozen rc1 catalogue's own text. A
    freehand value cannot be laundered into a neutral row through this bridge.
    """
    params = {}
    for field in ("reason", "impact", "next_step"):
        old_text = old_spec[field]
        parts, names = [], []
        for literal, name, format_spec, conversion in string.Formatter().parse(old_text):
            require(not format_spec and conversion is None, "CATALOGUE_MIGRATION", "unsupported rc1 placeholder")
            parts.append(re.escape(literal))
            if name is not None:
                require(re.fullmatch(r"[a-z_]+", name) is not None,
                        "CATALOGUE_MIGRATION", "unsupported rc1 placeholder name")
                names.append(name)
                parts.append("(.+?)")
        match = re.fullmatch("".join(parts), row[field], re.S)
        require(match is not None, "CATALOGUE_MIGRATION", f"{field} is not rc1 catalogue text")
        for name, value in zip(names, match.groups()):
            require(name not in params or params[name] == value,
                    "CATALOGUE_MIGRATION", f"conflicting rc1 value for {name}")
            params[name] = value
    target = new_id or row["limitation_id"]
    return render_limitation_row(core_catalogue, target, path=row["field_path"], **params)


def embed_catalogue(document: dict) -> dict:
    """Construct a content-addressed header declaration without mutating input."""
    if "sha256" in document:
        raise ConversionError("CATALOGUE_SCHEMA: input already has a digest", code="CATALOGUE_SCHEMA")
    return {**document, "sha256": catalogue_sha256(document)}
