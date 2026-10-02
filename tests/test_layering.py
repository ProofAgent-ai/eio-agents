"""The layering of `eio_agents`: which unit may import which, read from the source (every import statement, including the
ones inside functions and `if TYPE_CHECKING:` blocks), plus a subprocess check that the neutral units never load the rc1
staging area at run time.

    base  <-  ontology  <-  semantics  <-  evidence  <-  {resolvers, adjudication, reliability, compliance, scoring}  <-  per

- `base` (canonical form, digests, error type) imports only the standard library; `schemas` (path constants and loaders
  of the shipped JSON Schemas) sits beside it and may import only `base`.
- `ontology` depends on nothing above `base` and `schemas`.
- `evidence` may import `semantics` (the ref ids are the `semantics.ids` recipes, split plan §2.2), and `semantics` never
  imports `evidence`: no cycle between them.
- The views (`resolvers`, `adjudication`, `reliability`, `compliance`, `scoring`) do not import one another; `per` may
  import every unit below it.
- `validation`, the independent verifier (contract P3), imports only `eio_agents.schemas` and `eio_agents.per.limitations`
  besides its own modules (with the standard library, `yaml` and `jsonschema`).
- `adapters` (the producer-adapter interface) imports only `base`.
- The package root imports nothing at run time and names only `api`, `base`, `per` and `validation` (its lazy public
  names); no module imports `_legacy` or `_vendored` (the stored-report branch of ACCEPTED_DEVIATIONS D-4 was deleted at
  L3, when the ProofAgent adapter moved to the harness; both staging areas were deleted at L4, with the vendored scorer
  and its loader `harness2x`).
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "eio_agents"
LOWER = {"base", "schemas"}
VIEWS = {"resolvers", "adjudication", "reliability", "compliance", "scoring"}
NEUTRAL_UNITS = sorted(LOWER | VIEWS | {"ontology", "semantics", "evidence", "per", "validation", "adapters"})
ALLOWED = {  # unit -> the other units it may import
    "base": set(),
    "schemas": {"base"},
    "ontology": {"base", "schemas"},
    "semantics": {"base", "schemas", "ontology"},
    "evidence": {"base", "schemas", "ontology", "semantics"},
    **{v: {"base", "schemas", "ontology", "semantics", "evidence"} for v in VIEWS},
    "per": {"base", "schemas", "ontology", "semantics", "evidence"} | VIEWS,
    "validation": {"schemas", "per"},                         # narrowed to two modules by VALIDATION_MAY_IMPORT
    "adapters": {"base"},
    "root": {"api", "base", "per", "validation"},             # lazy (PEP 562) and TYPE_CHECKING only; see test_root_is_lazy
    "api": {"base", "schemas", "ontology", "per", "validation"},             # L3: the D-4 stored-report branch is gone
    "cli": {"root", "api", "validation"},
    "__main__": {"cli"},                                     # `python -m eio_agents`
}
VALIDATION_MAY_IMPORT = {"eio_agents.schemas", "eio_agents.per.limitations"}
THIRD_PARTY = {"yaml", "jsonschema"}


def _unit(module: str) -> str:
    """The layering unit of a dotted `eio_agents` module name."""
    parts = module.split(".")
    if len(parts) == 1:
        return "root"
    return {"api": "api", "cli": "cli", "adapters": "adapters", "__main__": "__main__"}.get(parts[1], parts[1])


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_module(dotted: str) -> bool:
    p = SRC.parent.joinpath(*dotted.split("."))
    return p.with_suffix(".py").is_file() or (p / "__init__.py").is_file()


def imports_of(path: Path) -> tuple[set[str], set[str]]:
    """(the `eio_agents` modules, the top-level non-`eio_agents` packages) one source file imports, anywhere in the file.
    `from pkg import name` counts `pkg.name` when that is a module, else `pkg`; relative imports are resolved."""
    name = _module_name(path)
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    ours, others = set(), set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module
            mods = [f"{mod}.{a.name}" if _is_module(f"{mod}.{a.name}") else mod for a in node.names]
        else:
            continue
        for m in mods:
            (ours if m.split(".")[0] == "eio_agents" else others).add(m if m.split(".")[0] == "eio_agents" else m.split(".")[0])
    return ours, others


FILES = sorted(p for p in SRC.rglob("*.py"))


def _graph() -> dict[str, dict[str, set[str]]]:
    """unit -> imported unit -> the files that make the edge"""
    g: dict[str, dict[str, set[str]]] = {}
    for p in FILES:
        src = _unit(_module_name(p))
        for m in imports_of(p)[0]:
            dst = _unit(m)
            if dst != src:
                g.setdefault(src, {}).setdefault(dst, set()).add(p.relative_to(SRC).as_posix())
    return g


def test_every_source_file_belongs_to_a_known_unit():
    units = {_unit(_module_name(p)) for p in FILES}
    assert units <= set(ALLOWED), sorted(units - set(ALLOWED))
    assert not (SRC / "errors.py").exists() and not (SRC / "semantics" / "canon.py").exists()   # moved to `base` (L2a)


def test_import_edges_follow_the_layering():
    offenders = {f"{src} -> {dst}": sorted(files) for src, out in _graph().items() for dst, files in out.items()
                 if dst not in ALLOWED[src]}
    assert not offenders, offenders


def test_the_unit_graph_is_acyclic():
    g = {src: set(out) for src, out in _graph().items()}
    seen, stack = set(), []

    def visit(u):
        if u in stack:
            raise AssertionError("import cycle: " + " -> ".join(stack[stack.index(u):] + [u]))
        if u in seen:
            return
        stack.append(u)
        for v in sorted(g.get(u, ())):
            visit(v)
        stack.pop()
        seen.add(u)

    for u in sorted(g):
        visit(u)


def test_evidence_and_semantics_have_no_cycle():
    g = _graph()
    assert "evidence" not in g.get("semantics", {}), g.get("semantics", {}).get("evidence")
    assert "ontology" in g.get("semantics", {}) and "semantics" in g.get("evidence", {})       # the one allowed direction


def test_base_and_ontology_sit_at_the_bottom():
    g = _graph()
    assert not g.get("base"), g.get("base")
    assert set(g.get("ontology", {})) <= {"base", "schemas"}, g.get("ontology")
    for p in sorted((SRC / "base").rglob("*.py")):
        ours, others = imports_of(p)
        assert {_unit(m) for m in ours} <= {"base"} and not others & THIRD_PARTY, (p.name, ours, others)


def test_the_verifier_imports_only_schemas_and_the_limitation_catalogue():
    """Contract P3: `validation` keeps its own JCS and digests; it imports no converter module and not `base`."""
    offenders = {}
    for p in sorted((SRC / "validation").rglob("*.py")):
        bad = sorted(m for m in imports_of(p)[0] if _unit(m) != "validation" and m not in VALIDATION_MAY_IMPORT)
        if bad:
            offenders[p.name] = bad
    assert not offenders, offenders


def test_no_module_imports_the_deleted_staging_area():
    """L4: `_legacy` and `_vendored` are gone; no unit imports either (and no unit of that name exists)."""
    staging = {"_legacy", "_vendored"}
    graph = _graph()
    offenders = {f"{src} -> {dst}": sorted(files) for src, out in graph.items() for dst, files in out.items() if dst in staging}
    assert not offenders and not staging & set(graph), offenders


def test_api_never_reaches_the_staging_area():
    """Review #18 / D-4, ended at L3: `api` imports neither `_legacy` nor `_vendored`, at module level or in any function
    (a stored report converts with its producer's adapter, outside EIO-Agents)."""
    tree = ast.parse((SRC / "api.py").read_text(encoding="utf-8"))
    names = [n for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
             for n in [a.name for a in node.names] + [getattr(node, "module", None) or ""]]
    assert names and not [n for n in names if "_legacy" in n or "_vendored" in n], names


def test_the_root_imports_nothing_at_run_time():
    """Every import of the root is inside `__getattr__` or an `if TYPE_CHECKING:` block."""
    tree = ast.parse((SRC / "__init__.py").read_text(encoding="utf-8"))
    runtime = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all(isinstance(n, ast.ImportFrom) and n.module in ("__future__", "typing") for n in runtime), \
        [ast.unparse(n) for n in runtime]


def test_the_scanner_sees_function_level_and_relative_imports(tmp_path, monkeypatch):
    pkg = tmp_path / "eio_agents" / "semantics"
    pkg.mkdir(parents=True)
    (tmp_path / "eio_agents" / "__init__.py").write_text("")
    (tmp_path / "eio_agents" / "evidence.py").write_text("")
    (pkg / "__init__.py").write_text("")
    f = pkg / "x.py"
    f.write_text("def f():\n    from ..evidence import witness\n    import eio_agents._legacy.harness2x\n")
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path / "eio_agents")
    ours, _ = imports_of(f)
    assert ours == {"eio_agents.evidence", "eio_agents._legacy.harness2x"}


# ---- run time: the neutral units never load the staging area or `api`
PROBE = """
import json, sys
import {mod}
print(json.dumps(sorted(m for m in sys.modules if m == "eio_agents.api" or m.startswith(("eio_agents._legacy",
                                                                                        "eio_agents._vendored")))))
"""


@pytest.mark.parametrize("mod", ["eio_agents"] + [f"eio_agents.{u}" for u in NEUTRAL_UNITS])
def test_importing_a_neutral_unit_loads_no_staging_module(mod):
    out = subprocess.run([sys.executable, "-c", PROBE.format(mod=mod)], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [], (mod, out.stdout)


def test_root_is_lazy_and_keeps_its_public_names():
    code = """
import json, sys
import eio_agents
before = sorted(m for m in sys.modules if m.startswith("eio_agents."))
from eio_agents import ConversionError, canonical_bytes, per_sha256, write, explain
mid = sorted(m for m in sys.modules if m == "eio_agents.api" or m.startswith("eio_agents._"))
import eio_agents.api, eio_agents.base.errors, eio_agents.per, eio_agents.validation
same = [getattr(eio_agents, n) is getattr(eio_agents.api, n) for n in ("convert", "convert_file", "standards", "validate",
        "verify", "canonical_bytes", "per_sha256", "write", "explain", "ConversionError")]
same += [eio_agents.ConversionError is eio_agents.base.errors.ConversionError, eio_agents.write is eio_agents.per.write,
         eio_agents.explain is eio_agents.validation.explain]
print(json.dumps({"before": before, "mid": mid, "same": all(same), "dir": sorted(set(eio_agents.__all__) - set(dir(eio_agents)))}))
"""
    r = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout)
    assert r == {"before": [], "mid": [], "same": True, "dir": []}, r
    import eio_agents
    with pytest.raises(AttributeError):
        eio_agents.no_such_name  # noqa: B018
