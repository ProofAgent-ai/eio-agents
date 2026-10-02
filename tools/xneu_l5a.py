#!/usr/bin/env python3
"""Check a candidate L5a release for ProofAgent-specific names and obsolete IRIs.

This is deliberately a *release-candidate* check: frozen rc1 schemas, fixtures,
examples and migration prose are historical and are not scanned. It reports
violations in the active manifest modules, EIO schemas/context, and rc2 PER
schema/context. It does not rewrite files or claim that semantic migration is
complete. Run after the L5a rebase and reviewed digest batch.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

RELEASE_BASE = "https://www.proofagent.ai/eio-agents/"
HISTORICAL_BASE = "https://w3id.org/eio-agents/"
OLD_TERMS = (
    re.compile(r"proofagent", re.IGNORECASE),
    re.compile(r"\bharness[ -]?llm\b", re.IGNORECASE),
    re.compile(r"tag:proofagent\.ai", re.IGNORECASE),
)
LEGACY_ID = re.compile(r"(?<![A-Za-z0-9_])legacy\.[A-Za-z0-9_.-]+")
PAI_ID_SEGMENT = re.compile(r"(?:^|[./:#])pai(?:[./:#-]|$)", re.IGNORECASE)
OBSOLETE_DATA_KEYS = frozenset({
    "harness_node", "intake_keys", "archive_source", "runtime_crosswalk",
    "legacy_key", "legacy_labels", "legacy_values", "legacy_behaviours",
    "legacy_checks", "legacy_profiles", "maintainers",
})
BRANDED_PROPERTY_NAMES = frozenset({
    "legacy_check", "legacy_decided_by", "harness_llm", "harness_version",
    "adjudication_source", "legacy_metric", "legacy_labels", "legacy_values",
    "runtime_crosswalk", "intake_keys", "archive_source", "harness_node",
}) | OBSOLETE_DATA_KEYS
EXTERNAL_CONTEXT_PREFIXES = (
    "http://www.w3.org/", "https://www.w3.org/",
    "http://purl.org/dc/terms/", "https://purl.org/dc/terms/",
)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    location: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.location}: {self.rule}"


def _walk(value, path="$", *, in_properties=False):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if in_properties:
                yield child_path, "property", key
            else:
                yield child_path, "key", key
            yield from _walk(child, child_path, in_properties=key in {"properties", "patternProperties"})
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")
    elif isinstance(value, str):
        yield path, "value", value


def _scan_doc(path: Path, root: Path, value, *, schema=False) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    findings = []
    for pointer, kind, text in _walk(value):
        if schema and kind in {"property", "key"} and text.split(":")[-1] in BRANDED_PROPERTY_NAMES:
            findings.append(Finding(rel, pointer, "branded schema/context term"))
        if not schema and kind == "key" and text in OBSOLETE_DATA_KEYS:
            findings.append(Finding(rel, pointer, "obsolete data key"))
        if kind == "value":
            for pattern in OLD_TERMS:
                # A publisher-owned URI is not a ProofAgent-specific ontology term.
                if pattern.search(text) and not text.startswith(RELEASE_BASE):
                    findings.append(Finding(rel, pointer, "ProofAgent-specific release text or IRI"))
                    break
            if LEGACY_ID.search(text):
                findings.append(Finding(rel, pointer, "legacy.* identifier"))
            if text.startswith(("eio.", RELEASE_BASE, HISTORICAL_BASE)) and PAI_ID_SEGMENT.search(text):
                findings.append(Finding(rel, pointer, "pai identifier segment"))
            if re.fullmatch(r"\$/profiles/\d+/id", pointer) and re.search(r"harness-2(?:\.x|x)", text):
                findings.append(Finding(rel, pointer, "packaged harness-2.x profile"))
            if schema and path.suffix == ".jsonld" and pointer.startswith("$/@context/"):
                if text.startswith(("http://", "https://")) and not text.startswith(
                    (RELEASE_BASE, HISTORICAL_BASE, *EXTERNAL_CONTEXT_PREFIXES)
                ):
                    findings.append(Finding(rel, pointer, "non-neutral JSON-LD term IRI"))
    return findings


def _missing_module_refs(doc, rel: str, active_ids: set[str]) -> list[Finding]:
    """Check only explicit module imports; other eio.* ids need a loaded ontology."""
    findings = []
    for index, row in enumerate(doc.get("imports", [])):
        module = row.get("module") if isinstance(row, dict) else None
        if isinstance(module, str) and module not in active_ids:
            findings.append(Finding(rel, f"$/imports/{index}/module", f"unloaded module reference {module}"))
    return findings


def _active_modules(data: Path) -> tuple[list[Path], list[Finding]]:
    manifest = data / "manifest.yaml"
    loaded = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    root = data.parents[3]
    by_id = {}
    for path in sorted(data.rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        header = doc.get("eio") if isinstance(doc, dict) else None
        if isinstance(header, dict) and isinstance(header.get("id"), str):
            by_id[header["id"]] = path
    missing = []
    paths = [manifest]
    for row in loaded.get("imports", []):
        module = row.get("module") if isinstance(row, dict) else None
        path = by_id.get(module)
        if path is None:
            missing.append(Finding(manifest.relative_to(root).as_posix(), "$/imports", f"missing active module {module}"))
        else:
            paths.append(path)
    return paths, missing


def scan(root: Path) -> list[Finding]:
    """Return sorted violations; *root* is the copied EIO-Agents repository."""
    root = root.resolve()
    data = root / "src/eio_agents/ontology/data"
    paths, findings = _active_modules(data)
    manifest = yaml.safe_load((data / "manifest.yaml").read_text(encoding="utf-8"))
    active_ids = {manifest["eio"]["id"]}
    active_ids.update(row["module"] for row in manifest.get("imports", []))
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        findings += _scan_doc(path, root, doc)
        header = doc.get("eio", {})
        rel = path.relative_to(root).as_posix()
        findings += _missing_module_refs(doc, rel, active_ids)
        if header.get("maintainers") is not None:
            findings.append(Finding(rel, "$/eio/maintainers", "hashed maintainer field"))
        namespace = header.get("namespace")
        if not isinstance(namespace, str) or not namespace.startswith(RELEASE_BASE):
            findings.append(Finding(rel, "$/eio/namespace", "non-neutral module namespace"))
    eio_schemas = root / "src/eio_agents/schemas/eio"
    per_schemas = root / "src/eio_agents/schemas/per"
    active_eio_schemas = eio_schemas / "0.6.0"
    schema_paths = sorted(active_eio_schemas.glob("*.json")) + sorted(active_eio_schemas.glob("*.jsonld"))
    schema_paths += [per_schemas / "per-2.0.0-rc2-draft.schema.json", per_schemas / "per-2.0.context.jsonld"]
    for path in schema_paths:
        rel = path.relative_to(root).as_posix()
        if not path.is_file():
            findings.append(Finding(rel, "$", "required candidate schema/context missing"))
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        findings += _scan_doc(path, root, doc, schema=True)
        if path.suffix == ".json":
            schema_id = doc.get("$id")
            allowed_base = HISTORICAL_BASE if path.parent == per_schemas else RELEASE_BASE
            if not isinstance(schema_id, str) or not schema_id.startswith(allowed_base):
                findings.append(Finding(rel, "$/$id", "non-neutral schema identifier"))
    return sorted(set(findings))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    args = parser.parse_args(argv)
    findings = scan(args.root)
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2))
    else:
        for finding in findings:
            print(finding)
        print(f"X-NEU candidate: {len(findings)} violation(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
