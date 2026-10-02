"""The digest tool and structural EIO gates against the active neutral release."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
def _run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT, timeout=900)


def test_digest_tool_reproduces_release_digests():
    r = _run(TOOLS / "eio_digests.py")
    assert r.returncode == 0, r.stdout + r.stderr
    printed = _run(TOOLS / "eio_digests.py", "--print")
    assert printed.stdout.encode("utf-8") == (ROOT / "src/eio_agents/ontology/data/RELEASE-DIGESTS.json").read_bytes()


def test_neutral_gates_pass():
    r = _run(TOOLS / "eio_gates.py", "--examples", ROOT / "tests/data/native")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr
    gates = dict((g, s) for s, g in re.findall(r"^\[(\w+)\] (\w+):", r.stdout, re.M))
    assert len(gates) == 37 and set(gates.values()) == {"PASS"}, gates


def test_native_conformance_mutation_selftest_is_a_release_gate():
    """Current native goldens and all negative mutation vectors must be checked."""
    r = _run(TOOLS / "eio_gates.py", "--selftest", "--examples", ROOT / "tests/data/native")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr
    assert "40 negative vectors, 0 not caught" in r.stdout
