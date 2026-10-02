"""No-loss checks for the isolated ontology/adapter dependency rewrite."""

import ast
import copy
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import yaml
import jsonschema
import pytest

from eio_agents.semantics import why
from eio_agents.per import privacy as per_privacy


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/eio_agents/ontology/data"
ADAPTER = Path(os.environ["EIO_ADAPTER_SNAPSHOT_DIR"]) if "EIO_ADAPTER_SNAPSHOT_DIR" in os.environ else None
sys.path.insert(0, str(ROOT / "tools"))
import xneu_l5a  # noqa: E402


def doc(base: Path | None, rel: str) -> dict:
    if base is None:
        pytest.skip("adapter no-loss comparison requires EIO_ADAPTER_SNAPSHOT_DIR outside the EIO package")
    return yaml.safe_load((base / rel).read_text())


def ids(rows: list[dict]) -> list[str]:
    return [row["id"] for row in rows]


def test_active_ontology_data_is_neutral_by_release_scanner() -> None:
    assert xneu_l5a.scan(ROOT) == []


def test_generic_flow_metric_and_governance_membership_is_unchanged() -> None:
    for rel, key in (("core/flow.yaml", "flow"), ("mappings/metrics.yaml", "concepts")):
        assert ids(doc(DATA, rel)[key]) == ids(doc(ADAPTER, rel)[key])
    metric = doc(DATA, "mappings/metrics.yaml")
    old_metric = doc(ADAPTER, "mappings/metrics.yaml")
    assert metric["mappings"] == old_metric["mappings"]
    core = doc(DATA, "core/flow.yaml")
    assert all("harness_node" not in stage for stage in core["flow"])
    new_gov = doc(DATA, "governance/gates.yaml")["governance"]
    old_gov = doc(ADAPTER, "governance/gates.yaml")["governance"]
    for key in ("tiers", "gates", "facts"):
        assert ids(new_gov[key]) == ids(old_gov[key])


def test_context_criteria_and_control_terms_are_unchanged() -> None:
    new = doc(DATA, "context/criteria.yaml")
    old = doc(ADAPTER, "context/criteria.yaml")
    assert ids(new["context_criteria"]) == ids(old["context_criteria"])
    for original, current in zip(old["context_criteria"], new["context_criteria"]):
        if "controls" not in original:
            continue
        assert [row["id"] for row in current["controls"]] == [row["id"] for row in original["controls"]]
        assert [row["requires_any"] for row in current["controls"]] == [row["requires_any"] for row in original["controls"]]


def test_predicate_context_links_preserve_every_old_check_association() -> None:
    new_links = doc(DATA, "graph/context-links.yaml")["context_links"]
    old_links = doc(ADAPTER, "graph/context-links.yaml")["context_links"]
    old_mapping = doc(ADAPTER, "mappings/legacy.yaml")["mappings"]
    targets = {
        row["source"].removeprefix("legacy.check."): row["target"]
        for row in old_mapping
        if row["source"].startswith("legacy.check.")
    }
    for check, edges in old_links.items():
        target = targets[check]
        assert target in new_links
        assert all(edge in new_links[target] for edge in edges)


def test_generic_domain_selection_and_scoring_axes_survive() -> None:
    new_domains = doc(DATA, "graph/domain-links.yaml")["domain_links"]
    old_domains = doc(ADAPTER, "graph/domain-links.yaml")["domain_links"]
    for key in ("universal_families", "family_defaults", "universal_domain"):
        assert new_domains[key] == old_domains[key]
    assert "trap_overrides" not in new_domains
    new_scoring = doc(DATA, "scoring/axes.yaml")["scoring"]
    old_scoring = doc(ADAPTER, "scoring/axes.yaml")["scoring"]
    assert ids(new_scoring["axes"]) == ids(old_scoring["axes"])
    assert ids(new_scoring["caps"]) == ids(old_scoring["caps"])


def test_adapter_only_scoring_profile_and_product_stack_are_retained_outside_core() -> None:
    scoring = doc(DATA, "scoring/axes.yaml")
    old_scoring = doc(ADAPTER, "scoring/axes.yaml")
    assert "eio.profile.legacy-scoring-harness-2x" in ids(old_scoring["profiles"])
    assert "eio.profile.legacy-scoring-harness-2x" not in ids(scoring["profiles"])
    assurance = doc(DATA, "assurance/system-of-record.yaml")
    old_assurance = doc(ADAPTER, "assurance/system-of-record.yaml")
    assert "eio.profile.proofagent-stack" in ids(old_assurance["profiles"])
    assert "eio.profile.proofagent-stack" not in ids(assurance["profiles"])


def test_neutral_template_versions_and_native_control_render() -> None:
    current = {row["id"]: row for row in doc(DATA, "templates/why.yaml")["explanation_templates"]}
    history = {row["id"]: row for row in doc(ADAPTER, "templates/why.yaml")["explanation_templates"]}
    changed = (
        "eio.why.control.observed_violation",
        "eio.why.claim.applicable_fail.deterministic",
        "eio.why.claim.applicable_pass.semantic",
        "eio.why.claim.evidence_invalid",
        "eio.why.claim",
    )
    for stem in changed:
        assert stem + "@1" in history
        assert stem + "@1" not in current
        assert stem + "@2" in current
    for removed in ("eio.why.axis.compliance.legacy@1", "eio.why.claim.not_applicable.premise@1"):
        assert removed in history and removed not in current
    assert "legacy_check" not in str(current["eio.why.claim@2"])
    assert "legacy_check" not in str(current["eio.why.claim.applicable_fail.deterministic@2"])

    eio = SimpleNamespace(templates=current)
    params = {
        "external_ref": "C-1",
        "fail": 1,
        "decided_split": {"deterministic": 1},
        "predicates_failed": ["eio.predicate.prohibited-tool-invoked"],
        "pass": 0,
        "evaluator_fault": 0,
        "proxy_note": False,
        "mapping_status": "provisional",
        "legal_review": True,
    }
    text = why.render(eio, "eio.why.control.observed_violation@2", params)
    assert "C-1 observed_violation" in text
    assert "evidence relevance only" in text
    assert "legacy" not in text.lower()


def test_all_literal_core_template_selectors_resolve() -> None:
    registered = {row["id"] for row in doc(DATA, "templates/why.yaml")["explanation_templates"]}
    for path in (ROOT / "src/eio_agents").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.fullmatch(r"eio\.why\.[a-z0-9_.-]+@\d+", node.value):
                    assert node.value in registered, (path, node.lineno, node.value)


def test_native_privacy_vocabulary_never_whitelists_adapter_labels(monkeypatch) -> None:
    monkeypatch.setattr(per_privacy.B, "release_strings", lambda _: set())
    monkeypatch.setattr(per_privacy, "schema_vocabulary", lambda: (frozenset(), frozenset()))
    eio = SimpleNamespace(
        doc={"eio.mapping.metrics": {"concepts": []}},
        release_evidence_floor=0.6,
        reference_cases=[],
        criteria={},
    )
    vocab = per_privacy.Vocabulary(eio)
    assert vocab.labels == vocab.check_names == vocab.metric_keys == frozenset()


def test_module_schema_accepts_neutral_facts_but_rejects_adapter_bindings() -> None:
    schema = json.loads((ROOT / "src/eio_agents/schemas/eio/module.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    gov = doc(DATA, "governance/gates.yaml")
    assert not list(validator.iter_errors(gov))
    with_alias = copy.deepcopy(gov)
    with_alias["governance"]["facts"][0]["aliases"] = ["producer_alias"]
    assert list(validator.iter_errors(with_alias))
    with_intake = copy.deepcopy(gov)
    with_intake["governance"]["facts"][0]["intake_keys"] = [{"key": "classification.tier"}]
    assert list(validator.iter_errors(with_intake))
    links = doc(DATA, "graph/domain-links.yaml")
    assert not list(validator.iter_errors(links))
    links["domain_links"]["trap_overrides"] = {"producer_trap": ["eio.domain.generic-agent"]}
    assert list(validator.iter_errors(links))


def test_domain_aliases_still_required_by_schema() -> None:
    schema = json.loads((ROOT / "src/eio_agents/schemas/eio/module.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    domain = doc(DATA, "domains/generic-agent.yaml")
    assert not list(validator.iter_errors(domain))
    del domain["domain"]["aliases"]
    assert list(validator.iter_errors(domain))
