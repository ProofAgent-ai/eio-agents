#!/usr/bin/env python3
"""The EIO release digests: compute, check or write RELEASE-DIGESTS.json of the release in this tree.

module_sha256 = sha256(raw file bytes); ontology_sha256 = sha256(JCS({module_id: module_sha256})) over every module
including the manifest; ontology_digest = the first 16 hex of ontology_sha256. The pinned files are the EIO JSON Schemas
and JSON-LD context (in `src/eio_agents/schemas/eio`, keyed `schemas/<name>`) and `reference/cases.jsonl`.

The digest rule of the EIO build gates (`compute_digests`, `--write-digests`), run against
`src/eio_agents/ontology/data`. Needs only PyYAML.

Usage:
    python tools/eio_digests.py            # check: exit 0 iff RELEASE-DIGESTS.json reproduces byte for byte
    python tools/eio_digests.py --print    # print the computed document
    python tools/eio_digests.py --write    # (re)write RELEASE-DIGESTS.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "eio_agents" / "ontology" / "data"
SCHEMAS = ROOT / "src" / "eio_agents" / "schemas" / "eio"
MANIFEST_ID = "eio.manifest.public"
DIGESTS = "RELEASE-DIGESTS.json"
ALGORITHM = ("module_sha256 = sha256(raw file bytes); ontology_sha256 = sha256(JCS({module_id: module_sha256})) over every "
             "module incl. the manifest; ontology_digest = first 16 hex of ontology_sha256")


def sha256_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def jcs(obj) -> bytes:
    """RFC 8785 for the value shapes used here (objects of strings, sorted by code point)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def module_paths(data: Path) -> dict[str, Path]:
    """module id -> file, for every YAML file of the release that carries an `eio.id` header."""
    out = {}
    for p in sorted(data.rglob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("eio"), dict) and doc["eio"].get("id"):
            out[doc["eio"]["id"]] = p
    return out


def compute_digests(paths: dict[str, Path], release, data: Path, schemas: Path) -> dict:
    mods = {mid: sha256_file(p) for mid, p in sorted(paths.items())}
    osha = "sha256:" + hashlib.sha256(jcs(mods)).hexdigest()
    files = {}
    for p in sorted(schemas.rglob("*.json")) + sorted(schemas.rglob("*.jsonld")):
        files["schemas/" + p.relative_to(schemas).as_posix()] = sha256_file(p)
    files["reference/cases.jsonl"] = sha256_file(data / "reference" / "cases.jsonl")
    return {"release": release, "algorithm": ALGORITHM, "modules": mods, "ontology_sha256": osha,
            "ontology_digest": osha.split(":", 1)[1][:16], "files": files}


def render(dg: dict) -> str:
    return json.dumps(dg, indent=2, sort_keys=True) + "\n"


def release_digests(data: Path = DATA, schemas: Path = SCHEMAS) -> dict:
    paths = module_paths(data)
    man = yaml.safe_load(paths[MANIFEST_ID].read_text(encoding="utf-8")) if MANIFEST_ID in paths else {}
    return compute_digests(paths, (man.get("eio") or {}).get("version"), data, schemas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(DATA), help="the EIO release directory (default: src/eio_agents/ontology/data)")
    ap.add_argument("--schemas", default=str(SCHEMAS), help="the EIO JSON Schemas (default: src/eio_agents/schemas/eio)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help=f"(re)write {DIGESTS}")
    mode.add_argument("--print", action="store_true", help="print the computed document")
    a = ap.parse_args(argv)
    data, schemas = Path(a.data), Path(a.schemas)
    text = render(release_digests(data, schemas))
    target = data / DIGESTS
    if a.print:
        sys.stdout.write(text)
        return 0
    if a.write:
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}")
        return 0
    if not target.is_file():
        print(f"{DIGESTS} missing (run with --write)")
        return 1
    if target.read_bytes() != text.encode("utf-8"):
        print(f"{DIGESTS} is stale: the digests do not reproduce")
        return 1
    dg = json.loads(text)
    print(f"{DIGESTS} reproduces: release {dg['release']}; {len(dg['modules'])} modules; {len(dg['files'])} pinned files; "
          f"ontology_digest {dg['ontology_digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
