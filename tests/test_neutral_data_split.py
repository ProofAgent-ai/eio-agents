"""Focused structural checks for the isolated four-module adapter extraction."""

import os
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/eio_agents/ontology/data"
ADAPTER = Path(os.environ["EIO_ADAPTER_SNAPSHOT_DIR"]) if "EIO_ADAPTER_SNAPSHOT_DIR" in os.environ else None
sys.path.insert(0, str(ROOT / "tools"))
import xneu_l5a  # noqa: E402


def doc(base: Path | None, rel: str) -> dict:
    if base is None:
        pytest.skip("adapter no-loss comparison requires EIO_ADAPTER_SNAPSHOT_DIR outside the EIO package")
    return yaml.safe_load((base / rel).read_text())


def test_all_four_active_modules_have_zero_xneu_findings() -> None:
    for rel in ("compliance/frameworks.yaml", "governance/gates.yaml"):
        path = DATA / rel
        assert xneu_l5a._scan_doc(path, ROOT, doc(DATA, rel)) == []


def test_framework_and_governance_generic_semantics_survive() -> None:
    core = doc(DATA, "compliance/frameworks.yaml")
    original = doc(ADAPTER, "compliance/frameworks.yaml")
    assert len(core["frameworks"]) == len(original["frameworks"]) == 30
    assert len(core["controls"]) == len(original["controls"]) == 165
    for old, new in zip(original["controls"], core["controls"]):
        assert {k: v for k, v in old.items() if k not in {"legacy_behaviours", "legacy_checks"}} == new
    gov = doc(DATA, "governance/gates.yaml")
    prior = doc(ADAPTER, "governance/gates.yaml")
    assert len(gov["governance"]["tiers"]) == len(prior["governance"]["tiers"]) == 4
    assert len(gov["governance"]["gates"]) == len(prior["governance"]["gates"]) == 7
    assert len(gov["governance"]["facts"]) == len(prior["governance"]["facts"]) == 126
    assert "runtime_crosswalk" not in gov["governance"]


def test_proofagent_rows_retained_only_in_adapter_data() -> None:
    assert len(doc(ADAPTER, "mappings/traps.yaml")["mappings"]) == 183
    assert len(doc(ADAPTER, "mappings/legacy.yaml")["mappings"]) == 95
    assert not (DATA / "mappings/traps.yaml").exists()
    assert not (DATA / "mappings/legacy.yaml").exists()
    manifest = doc(DATA, "manifest.yaml")
    assert "eio.mapping.legacy" not in {row["module"] for row in manifest["imports"]}
    assert "eio.mapping.traps" not in {row["module"] for row in manifest["imports"]}
    relations = doc(DATA, "core/relations.yaml")
    current = next(row for row in relations["profiles"] if row["id"] == "eio.profile.mapping-relations")
    original = next(row for row in doc(ADAPTER, "mappings/legacy.yaml")["profiles"] if row["id"] == "eio.profile.mapping-relations")
    assert current == original
