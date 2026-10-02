#!/usr/bin/env python3
"""Prepare the dependency-independent L5a namespace batch in an isolated copy.

This intentionally does not reissue ontology digests or record pins. Those form one
reviewed post-L4 batch. The command refuses unexpected headers rather than
guessing a namespace or silently editing a rebased file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml

NEW_BASE = "https://w3id.org/eio-agents/"
OLD_BASE = "https://proofagent.ai/eio/"
HEADER = re.compile(r"(?m)^  (id|namespace|maintainers): (.+)$")
SCHEMA_IDS = {
    "module.schema.json",
    "evidence-graph.schema.json",
    "evaluation-claim.schema.json",
    "reference-case.schema.json",
}


def sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def module_namespace(module_id: str) -> str:
    if not re.fullmatch(r"eio(?:\.[a-z0-9][a-z0-9-]*)+", module_id):
        raise ValueError(f"unexpected module id: {module_id}")
    return NEW_BASE + "module/" + module_id.removeprefix("eio.").replace(".", "/") + "#"


def change_header(content: str) -> str:
    values = dict(HEADER.findall(content))
    if set(values) != {"id", "namespace", "maintainers"}:
        if set(values) == {"id", "namespace"} and values["namespace"] == module_namespace(values["id"]):
            return content  # idempotent after the maintainer field is removed
        raise ValueError("expected one id, namespace, and maintainer header")
    expected_old = (OLD_BASE + "manifest#" if values["id"] == "eio.manifest.public"
                    else OLD_BASE + values["id"].removeprefix("eio.").replace(".", "/") + "#")
    expected_new = module_namespace(values["id"])
    if values["namespace"] not in {expected_old, expected_new}:
        raise ValueError(f"unexpected namespace for {values['id']}: {values['namespace']}")
    if values["maintainers"] != "[ProofAgent]":
        raise ValueError(f"unexpected maintainer header for {values['id']}")
    content = content.replace(f"  namespace: {values['namespace']}\n", f"  namespace: {expected_new}\n", 1)
    return content.replace("  maintainers: [ProofAgent]\n", "", 1)


def change_schema(content: str, name: str) -> str:
    old = f'"$id": "{OLD_BASE}schemas/{name}"'
    new = f'"$id": "{NEW_BASE}schema/0.5.0/{name}"'
    if old in content:
        content = content.replace(old, new, 1)
    elif new not in content:
        raise ValueError(f"unexpected schema id in {name}")
    if name == "module.schema.json":
        content = re.sub(
            r'(?m)^        "maintainers": \{\n          "type": "array",\n          "items": \{\n            "type": "string",\n            "minLength": 1\n          \},\n          "minItems": 1\n        \}',
            "",
            content,
            count=1,
        )
        # Removing a final property leaves a trailing comma on the license property.
        content = content.replace('"const": "Apache-2.0"\n        },\n\n', '"const": "Apache-2.0"\n        }\n', 1)
        if '"maintainers"' in content:
            raise ValueError("module schema still admits hashed maintainers")
        json.loads(content)
    return content


def change_context(content: str) -> str:
    changes = {
        '"@vocab": "https://proofagent.ai/eio/id/"': '"@vocab": "https://w3id.org/eio-agents/id/"',
        '"eiop": "https://proofagent.ai/eio/prop/"': '"eiop": "https://w3id.org/eio-agents/prop/"',
    }
    for old, new in changes.items():
        if old in content:
            content = content.replace(old, new, 1)
        elif new not in content:
            raise ValueError(f"unexpected JSON-LD context prefix: {old}")
    json.loads(content)
    return content


def plan(root: Path) -> dict[Path, str]:
    data = root / "src/eio_agents/ontology/data"
    schema_dir = root / "src/eio_agents/schemas/eio"
    changes: dict[Path, str] = {}
    module_ids = []
    for path in sorted(data.rglob("*.yaml")):
        content = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(content)
        if not isinstance(doc, dict) or not isinstance(doc.get("eio"), dict):
            continue
        module_ids.append(doc["eio"]["id"])
        revised = change_header(content)
        if revised != content:
            changes[path] = revised
    manifest = yaml.safe_load((data / "manifest.yaml").read_text(encoding="utf-8"))
    pinned_ids = {manifest["eio"]["id"], *(item["module"] for item in manifest["imports"])}
    if len(module_ids) != len(pinned_ids) or set(module_ids) != pinned_ids:
        raise ValueError(f"module headers do not match the manifest's {len(pinned_ids)} pinned modules")
    for name in sorted(SCHEMA_IDS):
        path = schema_dir / name
        content = path.read_text(encoding="utf-8")
        revised = change_schema(content, name)
        if revised != content:
            changes[path] = revised
    context = schema_dir / "eio-context-0.4.0.jsonld"
    content = context.read_text(encoding="utf-8")
    revised = change_context(content)
    if revised != content:
        changes[context] = revised
    return changes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    changes = plan(root)
    rows = []
    for path, revised in sorted(changes.items()):
        old = path.read_bytes()
        new = revised.encode("utf-8")
        rows.append({"path": path.relative_to(root).as_posix(), "before": sha256(old), "after": sha256(new)})
    if args.apply:
        for path, revised in changes.items():
            path.write_text(revised, encoding="utf-8")
    if args.json:
        print(json.dumps({"applied": args.apply, "changed": rows}, indent=2))
    else:
        print(f"L5a namespace batch: {len(rows)} files {'changed' if args.apply else 'would change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
