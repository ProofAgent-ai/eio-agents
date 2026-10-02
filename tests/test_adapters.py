"""`eio_agents.adapters`: the producer-adapter interface, with no registry, no discovery and no implementation."""
import ast
from pathlib import Path

import pytest

from eio_agents import adapters
from eio_agents.base.errors import ConversionError

SRC = Path(adapters.__file__)


class ToyAdapter:
    name = "toy-producer"
    version = "1.0.0"
    kind = "adapter"

    def to_bundle(self, raw):
        return {"provenance": {"producer": {"name": self.name, "version": self.version, "kind": self.kind}}, "raw": raw}


def test_an_adapter_satisfies_the_protocol_and_reports_its_metadata():
    a = ToyAdapter()
    assert isinstance(a, adapters.ProducerAdapter)
    assert adapters.adapter_metadata(a) == {"name": "toy-producer", "version": "1.0.0", "kind": "adapter"}
    assert a.to_bundle({"x": 1})["provenance"]["producer"] == adapters.adapter_metadata(a)


@pytest.mark.parametrize("field, value", [("kind", "native"), ("name", ""), ("version", 1), ("to_bundle", None)])
def test_adapter_metadata_fails_closed(field, value):
    a = ToyAdapter()
    setattr(a, field, value)
    with pytest.raises(ConversionError, match="ADAPTER_METADATA"):
        adapters.adapter_metadata(a)


def test_a_non_adapter_is_rejected():
    class NoCall:
        name, version, kind = "x", "1", "adapter"

    assert not isinstance(NoCall(), adapters.ProducerAdapter)
    with pytest.raises(ConversionError, match="ADAPTER_METADATA"):
        adapters.adapter_metadata(NoCall())


def test_no_registry_no_discovery_no_implementation():
    """§4.1 "No plugin discovery", §4.4 "an adapter plugs in with data": the module keeps no mutable module state and uses
    no loader, entry point or registry; the only classes it defines are the interface."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            assert isinstance(value, ast.Constant), ast.unparse(node)        # constants only: no dict/list/set registry
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert classes == ["ProducerAdapter"]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree)
                                                                          if isinstance(n, ast.Attribute)}
    assert not names & {"entry_points", "import_module", "iter_modules", "register", "registry", "sys", "importlib"}
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods == {"__future__", "typing", "eio_agents.base.errors"}, mods
