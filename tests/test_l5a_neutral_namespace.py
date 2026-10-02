"""The packaged core inventory, namespaces, and schema are internally pinned."""

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


DATA = Path(__file__).resolve().parents[1] / "src/eio_agents/ontology/data"
SCHEMA = Path(__file__).resolve().parents[1] / "src/eio_agents/schemas/eio/0.6.0/module.schema.json"


def _modules():
    modules = {}
    for path in sorted(DATA.rglob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("eio"), dict):
            module_id = document["eio"]["id"]
            assert module_id not in modules
            modules[module_id] = (path, document)
    return modules


def test_public_module_inventory_matches_its_manifest():
    modules = _modules()
    manifest_path, manifest = modules["eio.manifest.public"]
    assert manifest_path == DATA / "manifest.yaml"
    imports = {row["module"]: row for row in manifest["imports"]}
    assert len(imports) == len(manifest["imports"])
    assert set(imports) == set(modules) - {"eio.manifest.public"}
    for module_id, row in imports.items():
        path, document = modules[module_id]
        assert row["version"] == document["eio"]["version"]
        assert row["sha256"] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_pinned_headers_use_neutral_namespaces_and_validate():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/module.schema.json"
    assert "maintainers" not in schema["$defs"]["header"]["properties"]
    validator = Draft202012Validator(schema)
    for module_id, (_path, document) in _modules().items():
        header = document["eio"]
        expected = "https://www.proofagent.ai/eio-agents/module/" + module_id.removeprefix("eio.").replace(".", "/") + "#"
        assert header["namespace"] == expected
        assert "maintainers" not in header
        assert not list(validator.iter_errors(document)), module_id
