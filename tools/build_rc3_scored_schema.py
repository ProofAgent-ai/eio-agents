"""Mechanically build the one canonical rc3 PER schema from reviewed inputs.

This script is for the isolated scored-PER candidate. The old rc1/rc2 schemas
and the diagnostic native-preview file remain separate immutable resources.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1] / "src/eio_agents/schemas"
PREVIEW = ROOT / "per/per-2.0.0-rc3-neutral-preview.schema.json"
SCORE = ROOT / "scoring/native-score-block-0.2.0-draft.1.schema.json"
OUTPUT = ROOT / "per/per-2.0.0-rc3-draft.schema.json"
PUBLIC_ID = "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json"


def _namespace_refs(value):
    if isinstance(value, dict):
        return {key: _namespace_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_namespace_refs(item) for item in value]
    if isinstance(value, str) and value.startswith("#/$defs/"):
        return value.replace("#/$defs/", "#/$defs/native_score_", 1)
    return value


def main() -> None:
    schema = json.loads(PREVIEW.read_text(encoding="utf-8"))
    native = json.loads(SCORE.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(native)
    schema["$id"] = PUBLIC_ID
    schema["title"] = "PER 2.0 — Portable Evaluation Record (rc3 draft)"
    schema["description"] = (
        "Unpublished rc3 draft: native citation-witnessed proof and the "
        "source-bound partial reference score block. Numeric governance and "
        "readiness remain withheld until independently verified freshness."
    )
    for name, definition in native.pop("$defs").items():
        target = f"native_score_{name}"
        if target in schema["$defs"]:
            raise ValueError(f"duplicate score definition {target}")
        schema["$defs"][target] = _namespace_refs(definition)
    schema["$defs"]["native_draft_scores"] = _namespace_refs(native)
    schema["properties"]["scores"] = {
        "anyOf": [
            {"$ref": "#/$defs/scores"},
            {"$ref": "#/$defs/native_draft_scores"},
            {"type": "null"},
        ],
        "description": "A rederivable reference score block, historical score view, or explicit null.",
    }
    Draft202012Validator.check_schema(schema)
    OUTPUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
