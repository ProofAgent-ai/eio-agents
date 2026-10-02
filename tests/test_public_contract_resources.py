"""Current public EIO/PER resources need no historical private preview files."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from eio_agents.schemas import EIO_SCHEMA_CURRENT_DIR, eio_schema, per_schema


GOLDEN = Path(__file__).parent / "data/native/v0_6/source-complete.per.jcs"
BASE = "https://www.proofagent.ai/eio-agents/schema/"


def test_current_eio_schema_and_context_use_versioned_public_authority():
    context = json.loads((EIO_SCHEMA_CURRENT_DIR / "eio-context-0.6.0.jsonld").read_text())
    assert context["@context"]["@vocab"] == "https://www.proofagent.ai/eio-agents/id/"
    for name in ("module", "evaluation-claim", "evidence-graph", "reference-case"):
        schema = eio_schema(f"{name}.schema.json")
        Draft202012Validator.check_schema(schema)
        assert schema["$id"] == f"{BASE}eio/0.6.0/{name}.schema.json"


def test_current_per2_schema_validates_source_complete_golden():
    schema = per_schema("2.0.0")
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == f"{BASE}per/2.0.0/per.schema.json"
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(GOLDEN.read_bytes())))
