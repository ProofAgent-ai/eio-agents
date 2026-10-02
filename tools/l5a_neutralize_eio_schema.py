#!/usr/bin/env python3
"""Remove adapter-only shape from isolated EIO schemas; digests are not reissued here."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
EIO = ROOT / "src/eio_agents/schemas/eio"


def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def neutralize() -> None:
    path = EIO / "module.schema.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    d = doc["$defs"]
    doc["title"] = "EIO-Agents ontology module"

    def drop(obj: dict, *keys: str) -> None:
        for key in keys:
            obj["properties"].pop(key, None)
        if "required" in obj:
            obj["required"] = [key for key in obj["required"] if key not in keys]

    drop(d["concept"], "legacy_key")
    drop(d["control"], "legacy_behaviours", "legacy_checks")
    drop(d["flow_stage"], "harness_node")
    drop(d["governance"], "runtime_crosswalk")
    drop(d["scoring"], "legacy_profiles")
    drop(d["governance"]["properties"]["facts"]["items"], "intake_keys", "archive_source")
    drop(d["context_criterion"]["properties"]["controls"]["items"], "legacy_labels")
    source = d["explanationTemplate"]["properties"]["params"]["items"]["properties"]["source"]
    source["description"] = "Declared source of a rendered value: record field, view value, or ontology label."
    # These crosswalk columns belong in a producer-declared adapter schema, not
    # in the normative EIO module shape. The adapter/data split is a later gate.
    drop(d["mapping"], "applicability_embedded", "implemented", "legacy_metrics", "polarity", "resolver")
    Draft202012Validator.check_schema(doc)
    _write(path, doc)

    path = EIO / "evaluation-claim.schema.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["properties"]["rationale"]["description"] = (
        "If present, deterministic rendering of an EIO explanation template, never private evaluator prose.")
    Draft202012Validator.check_schema(doc)
    _write(path, doc)

    path = EIO / "eio-context-0.4.0.jsonld"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["@context"].pop("claim", None)
    doc["@context"].pop("ref", None)
    _write(path, doc)


if __name__ == "__main__":
    neutralize()
