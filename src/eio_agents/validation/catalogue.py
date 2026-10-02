"""Independent, offline verifier of embedded limitation/template catalogues.

The producer has its own implementation in ``per.catalogue_split``. This
module imports neither that implementation nor its canonicalization code.
Declared text is never fetched by URL, and placeholder values are restricted
to closed structural forms or fingerprints.
"""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

from eio_agents.validation.canon import jb, sha

CORE = Path(__file__).resolve().parents[1] / "per/data/limitations-core.json"
ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+")
TEMPLATE_ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+@[1-9][0-9]*")
SHA = re.compile(r"sha256:[0-9a-f]{64}")
FINGERPRINT = re.compile(r"sha256-[0-9a-f]{64}")
FORMS = {
    **dict.fromkeys(("turn", "calls", "total", "n", "hits", "scored"), re.compile(r"0|[1-9][0-9]{0,6}")),
    **dict.fromkeys(("ref", "finding_id", "claim_id"),
                    re.compile(r"[0-9a-f]{20,64}|urn:uuid:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")),
    "predicate": re.compile(r"eio\.predicate\.[a-z0-9][a-z0-9-]*"),
    "producer_release": re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?"),
    "producer_digest": re.compile(r"[0-9a-f]{16,64}|sha256:[0-9a-f]{64}"),
}
LIMITATION_FIELDS = {"id", "status", "paths", "raised_when", "reason", "impact", "next_step"}


class CatalogueError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


def _need(ok: bool, code: str, detail: str) -> None:
    if not ok:
        raise CatalogueError(code, detail)


def _id(value, *, template=False):
    return isinstance(value, str) and (TEMPLATE_ID if template else ID).fullmatch(value) is not None


def _safe(name: str, value: str) -> bool:
    if len(value) > 128 or not value:
        return False
    return FINGERPRINT.fullmatch(value) is not None or (
        name in FORMS and FORMS[name].fullmatch(value) is not None)


def _rendered_values(pattern: str, value: str):
    """Extract only bounded, typed placeholders from a catalogue rendering."""
    _need(isinstance(pattern, str) and isinstance(value, str), "LIMITATION_TEXT", "text must be a string")
    pieces, names = [], []
    for literal, name, fmt, conversion in string.Formatter().parse(pattern):
        pieces.append(re.escape(literal))
        if name is not None:
            _need(not fmt and conversion is None and re.fullmatch(r"[a-z_]+", name) is not None,
                  "CATALOGUE_SCHEMA", "unsupported placeholder")
            pieces.append("(.+?)")
            names.append(name)
    match = re.fullmatch("".join(pieces), value, re.S)
    if match is None:
        return None
    values = {}
    for name, captured in zip(names, match.groups()):
        if not _safe(name, captured) or (name in values and values[name] != captured):
            return None
        values[name] = captured
    return values


def _catalogue(doc, *, kind: str, core: bool, existing: dict):
    _need(isinstance(doc, dict), "CATALOGUE_SCHEMA", "catalogue must be an object")
    expected = {"id", "version", kind} if core else {"id", "version", "sha256", kind}
    _need(set(doc) == expected, "CATALOGUE_SCHEMA", "unexpected catalogue fields")
    cid = doc["id"]
    _need(_id(cid) and isinstance(doc["version"], str) and bool(doc["version"]),
          "CATALOGUE_ID", "catalogue id/version is invalid")
    if core:
        _need(cid == ("per.lim.core" if kind == "limitations" else "eio.why.core"),
              "CATALOGUE_ID", "unexpected core catalogue")
    else:
        _need(not cid.startswith(("per.lim", "eio.")), "CATALOGUE_ID", "reserved catalogue namespace")
        digest = doc["sha256"]
        _need(isinstance(digest, str) and SHA.fullmatch(digest) is not None and
              digest == sha(jb({k: v for k, v in doc.items() if k != "sha256"})),
              "CATALOGUE_DIGEST", "embedded catalogue digest mismatch")
    rows = doc[kind]
    _need(isinstance(rows, list), "CATALOGUE_SCHEMA", "catalogue rows must be an array")
    out = {}
    for row in rows:
        _need(isinstance(row, dict), "CATALOGUE_SCHEMA", "catalogue row must be an object")
        rid = row.get("id")
        _need(_id(rid, template=kind == "templates") and
              rid.startswith(f"{cid}." if not core else ("per.lim." if kind == "limitations" else "eio.why.")),
              "CATALOGUE_ID", "catalogue row id/prefix is invalid")
        _need(rid not in existing and rid not in out, "CATALOGUE_COLLISION", "duplicate catalogue row")
        if kind == "limitations":
            _need(set(row) == LIMITATION_FIELDS and row.get("status") in
                  {"NOT_SUPPLIED", "NOT_CAPTURED", "NOT_APPLICABLE"}, "CATALOGUE_SCHEMA", "invalid limitation row")
            _need(isinstance(row["paths"], list) and bool(row["paths"]) and
                  all(isinstance(path, str) and path.startswith("/") for path in row["paths"]),
                  "CATALOGUE_SCHEMA", "invalid limitation paths")
            _need(all(isinstance(row[key], str) and bool(row[key]) for key in ("reason", "impact", "next_step")),
                  "CATALOGUE_SCHEMA", "invalid limitation text")
        else:
            _need(set(row) == {"id", "text", "params", "max_length"} and
                  isinstance(row["text"], str) and bool(row["text"]) and
                  isinstance(row["params"], list) and isinstance(row["max_length"], int) and row["max_length"] > 0,
                  "CATALOGUE_SCHEMA", "invalid template row")
        out[rid] = row
    return out


def check_record_catalogues(record: dict, *, core_templates: dict | None = None) -> dict:
    """Return effective limitations or raise a typed independent verifier error."""
    _need(isinstance(record, dict) and isinstance(record.get("header"), dict),
          "CATALOGUE_SCHEMA", "record header is missing")
    header = record["header"]
    core = json.loads(CORE.read_text(encoding="utf-8"))
    merged = _catalogue(core, kind="limitations", core=True, existing={})
    declared = header.get("declared_limitation_catalogues", [])
    _need(isinstance(declared, list), "CATALOGUE_SCHEMA", "declared limitations must be an array")
    seen = set()
    for doc in declared:
        _need(isinstance(doc, dict), "CATALOGUE_SCHEMA", "declaration must be an object")
        _need(doc.get("id") not in seen, "CATALOGUE_COLLISION", "duplicate catalogue declaration")
        seen.add(doc.get("id"))
        merged.update(_catalogue(doc, kind="limitations", core=False, existing=merged))

    rows = record.get("limitations")
    _need(isinstance(rows, list), "LIMITATION_SCHEMA", "limitations must be an array")
    for row in rows:
        _need(isinstance(row, dict) and row.get("limitation_id") in merged,
              "UNKNOWN_LIMITATION", "limitation id is not declared")
        spec = merged[row["limitation_id"]]
        _need(row.get("status") == spec["status"], "LIMITATION_STATUS", "limitation status differs")
        _need(isinstance(row.get("field_path"), str) and
              any(_rendered_values(path, row["field_path"]) is not None for path in spec["paths"]),
              "LIMITATION_PATH", "limitation path is not a safe rendering")
        bound = {}
        for field in ("reason", "impact", "next_step"):
            values = _rendered_values(spec[field], row.get(field))
            _need(values is not None, "LIMITATION_TEXT", f"{field} is not a safe rendering")
            _need(all(name not in bound or bound[name] == value for name, value in values.items()),
                  "LIMITATION_PARAM", "conflicting limitation placeholder")
            bound.update(values)

    if core_templates is not None:
        templates = _catalogue(core_templates, kind="templates", core=True, existing={})
        declared_templates = header.get("declared_template_catalogues", [])
        _need(isinstance(declared_templates, list), "CATALOGUE_SCHEMA", "declared templates must be an array")
        seen.clear()
        for doc in declared_templates:
            _need(isinstance(doc, dict), "CATALOGUE_SCHEMA", "declaration must be an object")
            _need(doc.get("id") not in seen, "CATALOGUE_COLLISION", "duplicate template catalogue declaration")
            seen.add(doc.get("id"))
            templates.update(_catalogue(doc, kind="templates", core=False, existing=templates))
    return merged
