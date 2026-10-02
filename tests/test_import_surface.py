"""The import surface of `eio_agents`: no harness, no LLM client, no network library, and the dependency direction.

The dependency rule: EIO-Agents never reaches `proofagent_harness`, by an import statement, a dynamic
import, a `sys.modules` write, path-based loading or entry-point or pkgutil discovery. Strict from L4 (split plan §6.1
X-DEP (a)): the vendored harness-2.x scorer (`_vendored/**`) and its loader with the stub modules (`_legacy/harness2x.py`)
were deleted at L4, and with them both exemptions; every module under `src/eio_agents` is scanned.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "eio_agents"
FORBIDDEN = {"proofagent_harness", "litellm", "openai", "anthropic", "langgraph", "langchain", "eio_runtime", "pydantic",
             "requests", "httpx", "urllib3", "socket", "aiohttp"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out


def test_no_forbidden_imports_in_library_code():
    offenders = {}
    for p in SRC.rglob("*.py"):
        bad = _imports(p) & FORBIDDEN
        if bad:
            offenders[str(p.relative_to(SRC))] = sorted(bad)
    assert not offenders, offenders


def test_the_staging_areas_are_gone():
    """L4 task 7: `_vendored/` (the vendored scorer) and `_legacy/` (its loader and stubs) are deleted, so no exemption is
    left for the dependency rule."""
    assert not (SRC / "_vendored").exists() and not (SRC / "_legacy").exists()
    assert not [p for p in SRC.rglob("*") if p.name in ("_vendored", "_legacy", "harness2x.py")]


# ---- the dependency rule
HARNESS = "proofagent_harness"
LOADER_MODULES = {"runpy", "pkgutil", "pkg_resources", "importlib"}   # importlib.resources (package data) is allowed
LOADING_CALLS = {"import_module", "__import__", "find_spec", "spec_from_file_location", "spec_from_loader", "module_from_spec",
                 "ModuleType", "SourceFileLoader", "SourcelessFileLoader", "ExtensionFileLoader", "load_module", "exec_module",
                 "run_path", "run_module", "entry_points", "iter_modules", "walk_packages"}
BUILTIN_LOADERS = {"exec", "compile", "__import__"}                   # as builtins only: `re.compile` is not a loader
SYS_MODULES_WRITES = {"update", "pop", "setdefault", "popitem", "clear", "__setitem__", "__delitem__"}


def _names_harness(name: str) -> bool:
    return name == HARNESS or name.startswith(HARNESS + ".")


def _is_sys_modules(n) -> bool:
    return isinstance(n, ast.Attribute) and n.attr == "modules" and isinstance(n.value, ast.Name) and n.value.id == "sys"


def _loader_module(name: str) -> bool:
    top = name.split(".")[0]
    return top in LOADER_MODULES and name != "importlib.resources" and not name.startswith("importlib.resources.")


def xdep_a(source: str) -> list[str]:
    """Every violation of the dependency rule in one Python source."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            bad += [f"import {a.name}" for a in node.names if _names_harness(a.name) or _loader_module(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _names_harness(node.module) or (_loader_module(node.module) and node.module != "importlib"):
                bad.append(f"from {node.module} import")
            if node.module == "sys" and any(a.name == "modules" for a in node.names):
                bad.append("from sys import modules")
            if node.module == "importlib" and any(a.name != "resources" for a in node.names):
                bad.append("from importlib import " + ", ".join(a.name for a in node.names))
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            builtin = isinstance(f, ast.Name) or (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                                                   and f.value.id == "builtins")
            if name in LOADING_CALLS or (builtin and name in BUILTIN_LOADERS):
                bad.append(f"{name}(...)")
            if isinstance(f, ast.Attribute) and _is_sys_modules(f.value) and f.attr in SYS_MODULES_WRITES:
                bad.append(f"sys.modules.{f.attr}(...)")
            args = list(node.args) + [k.value for k in node.keywords]
            bad += [f"{name or 'call'}({a.value!r})" for a in args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and _names_harness(a.value)]
        elif isinstance(node, ast.Name) and node.id == "__import__":
            bad.append("__import__")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            bad += ["sys.modules[...] write" for t in targets if isinstance(t, ast.Subscript) and _is_sys_modules(t.value)]
            if not isinstance(node, ast.Delete) and _is_sys_modules(getattr(node, "value", None)):
                bad.append("sys.modules aliased")
        elif isinstance(node, ast.Subscript) and _is_sys_modules(node.value):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and _names_harness(key.value):
                bad.append(f"sys.modules[{key.value!r}]")
    return bad


def test_xdep_a_eio_agents_never_reaches_the_harness():
    offenders = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).as_posix()
        if bad := xdep_a(p.read_text(encoding="utf-8")):
            offenders[rel] = bad
    assert not offenders, offenders


# the two shapes the deleted exemptions had (the loader's stubs and path loading; the vendored scorer's lazy harness import)
DELETED_LOADER = """
import importlib.util, sys, types
pk = types.ModuleType("proofagent_harness"); pk.__path__ = []
sys.modules[pk.__name__] = pk
spec = importlib.util.spec_from_file_location("_per_ref_vendored_pai", "scoring/pai.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
"""
DELETED_SCORER = """
def proven_critical_failures(report):
    from proofagent_harness.agents.consensus import CODE_CRITICAL_CHECKS
    from proofagent_harness.checks import load_checks
"""


def test_xdep_a_sees_the_shapes_of_the_deleted_exemptions():
    assert xdep_a(DELETED_LOADER) and xdep_a(DELETED_SCORER)


@pytest.mark.parametrize("snippet", [
    "import proofagent_harness",
    "import proofagent_harness.agents.consensus as c",
    "from proofagent_harness.checks import load_checks",
    "from proofagent_harness import cli",
    "import importlib\nimportlib.import_module('proofagent_harness.checks')",
    "from importlib import import_module",
    "__import__('proofagent_harness')",
    "m = __import__",
    "import builtins\nbuiltins.__import__('proofagent_harness')",
    "import sys\nsys.modules['proofagent_harness'] = object()",
    "import sys\nsys.modules['x'] += 1",
    "import sys\ndel sys.modules['proofagent_harness']",
    "import sys\nsys.modules.update({})",
    "import sys\nsys.modules.pop('proofagent_harness', None)",
    "import sys\nsys.modules.setdefault('proofagent_harness', None)",
    "import sys\nmods = sys.modules",
    "from sys import modules",
    "import sys\nx = sys.modules['proofagent_harness']",
    "import importlib.util",
    "from importlib.util import spec_from_file_location",
    "from importlib.machinery import SourceFileLoader",
    "import importlib.metadata",
    "import runpy\nrunpy.run_path('x.py')",
    "import pkgutil\npkgutil.iter_modules()",
    "import pkg_resources",
    "import types\ntypes.ModuleType('proofagent_harness')",
    "exec(open('x.py').read())",
    "compile('x = 1', 'x.py', 'exec')",
    "import builtins\nbuiltins.exec('x = 1')",
    "getattr(object(), 'x')('proofagent_harness.agents')",
])
def test_xdep_a_scanner_catches(snippet):
    assert xdep_a(snippet), snippet


@pytest.mark.parametrize("snippet", [
    "import importlib.resources",
    "from importlib import resources",
    "import sys\nx = sys.modules.get('json')",
    'CONVERTER = {"name": "proofagent_harness.per.convert", "version": "0.13.0"}',   # the rc1 header constant (data)
    "import json\njson.loads('{}')",
    "import re\nrx = re.compile('a+')",
])
def test_xdep_a_scanner_allows(snippet):
    assert not xdep_a(snippet), snippet
