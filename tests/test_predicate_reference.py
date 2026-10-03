"""docs/predicates.md is generated from the ontology data by tools/predicate_reference.py and must stay in sync."""
import importlib.util
from pathlib import Path

import eio_agents

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("predicate_reference", ROOT / "tools" / "predicate_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_predicate_reference_page_is_in_sync():
    tool = _tool()
    assert tool.PAGE.read_text(encoding="utf-8") == tool.render(), \
        "docs/predicates.md is out of date: run python tools/predicate_reference.py --write"
    assert tool.main([]) == 0


def test_the_page_lists_every_predicate_once():
    text = (ROOT / "docs" / "predicates.md").read_text(encoding="utf-8")
    rows = eio_agents.predicates()
    assert len(rows) == 58
    for row in rows:
        assert text.count(f"| `{row['id'].removeprefix('eio.predicate.')}` |") == 1, row["id"]
