"""Check the built distributions of eio-agents before they are tested or published.

usage: python .github/scripts/check_dist.py [DIST_DIR]    (run from the repository root; DIST_DIR defaults to dist)

DIST_DIR must hold exactly one wheel and one sdist. The check fails when:
- a file under src/eio_agents/ is missing from the wheel, the wheel has a package file the source tree does not, or a
  packaged file differs from the source tree by a single byte (EIO data, schemas and vendored files are digest-pinned);
- the wheel metadata lacks the license expression, the license files or the Typing :: Typed classifier;
- a file of the sdist differs from the same file in the checkout, or the sdist lacks the files the test suite and the
  conformance tools need;
- either distribution contains compiled bytecode or an owner-only file.
"""
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path.cwd()
PKG = ROOT / "src" / "eio_agents"
SKIP_NAMES = {".DS_Store"}
SDIST_REQUIRED = [
    "pyproject.toml", "README.md", "LICENSE", "NOTICE", "PKG-INFO", "src/eio_agents/py.typed",
    "tests/conftest.py", "tests/test_verifier_selftest.py", "tests/data/native/native.per.jcs",
    "tools/eio_gates.py", "tools/eio_digests.py", "tools/snapshots/eio-0.3.0-baseline.json",
]
SDIST_FORBIDDEN = ("PUBLISHING_CHECKLIST.md", ".progress/", ".github/")
HISTORICAL_FIXTURE_DIRS = ("bundles", "context", "examples", "expected", "raw", "spec", "stress")
METADATA_REQUIRED = ["Name: eio-agents", "License-Expression: Apache-2.0", "License-File: LICENSE", "License-File: NOTICE",
                     "Classifier: Typing :: Typed", "Requires-Python: >=3.10"]


def _source_files() -> dict[str, bytes]:
    out = {}
    for p in sorted(PKG.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo") and p.name not in SKIP_NAMES:
            out[p.relative_to(PKG.parent).as_posix()] = p.read_bytes()
    return out


def check_wheel(wheel: Path, source: dict[str, bytes]) -> list[str]:
    problems = []
    with zipfile.ZipFile(wheel) as z:
        members = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    packaged = {n: b for n, b in members.items() if n.startswith("eio_agents/")}
    problems += [f"wheel: missing {n}" for n in sorted(set(source) - set(packaged))]
    problems += [f"wheel: not in the source tree: {n}" for n in sorted(set(packaged) - set(source))]
    problems += [f"wheel: bytes differ from the source tree: {n}" for n in sorted(set(source) & set(packaged))
                 if source[n] != packaged[n]]
    problems += [f"wheel: compiled bytecode {n}" for n in members if n.endswith((".pyc", ".pyo"))]
    problems += [f"wheel: unexpected top-level entry {n}" for n in members
                 if not n.startswith(("eio_agents/", "eio_agents-"))]
    meta = [n for n in members if n.endswith(".dist-info/METADATA")]
    if len(meta) != 1:
        return problems + ["wheel: no single METADATA file"]
    text = members[meta[0]].decode("utf-8")
    problems += [f"wheel METADATA: missing line {line!r}" for line in METADATA_REQUIRED if line not in text.splitlines()]
    for name in ("LICENSE", "NOTICE"):
        lic = [n for n in members if n.endswith(f".dist-info/licenses/{name}")]
        if len(lic) != 1:
            problems.append(f"wheel: {name} is not in dist-info/licenses")
        elif members[lic[0]] != (ROOT / name).read_bytes():
            problems.append(f"wheel: {name} differs from the checkout")
    return problems


def check_sdist(sdist: Path) -> list[str]:
    problems = []
    with tarfile.open(sdist) as t:
        files = {}
        for m in t.getmembers():
            if m.isfile():
                top, _, rel = m.name.partition("/")
                files[rel] = t.extractfile(m).read()
    problems += [f"sdist: missing {n}" for n in SDIST_REQUIRED if n not in files]
    problems += [f"sdist: owner-only or repository-only file {n}" for n in files if n.startswith(SDIST_FORBIDDEN)]
    problems += [f"sdist: historical adapter fixture {n}" for n in files
                 if n.startswith(tuple(f"tests/data/{part}/" for part in HISTORICAL_FIXTURE_DIRS))]
    problems += [f"sdist: compiled bytecode {n}" for n in files if n.endswith((".pyc", ".pyo")) or "__pycache__/" in n]
    for rel, data in sorted(files.items()):
        local = ROOT / rel
        if local.is_file() and local.read_bytes() != data:
            problems.append(f"sdist: bytes differ from the checkout: {rel}")
    return problems


def main(argv: list[str]) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    wheels, sdists = sorted(dist.glob("eio_agents-*.whl")), sorted(dist.glob("eio_agents-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f"expected one wheel and one sdist in {dist}, found {[p.name for p in wheels + sdists]}")
        return 1
    source = _source_files()
    problems = check_wheel(wheels[0], source) + check_sdist(sdists[0])
    for p in problems:
        print("FAIL", p)
    if problems:
        print(f"{len(problems)} problem(s) in {wheels[0].name} and {sdists[0].name}")
        return 1
    print(f"OK {wheels[0].name}: {len(source)} package files, byte-identical to src/eio_agents")
    print(f"OK {sdists[0].name}: required files present, byte-identical to the checkout")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
