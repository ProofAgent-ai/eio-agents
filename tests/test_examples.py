"""The examples under examples/ run against this checkout. They are outside `testpaths` and the sdist, so this module
runs them deliberately, and skips when the checkout has no examples (an unpacked sdist)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "custom_report"
pytestmark = pytest.mark.skipif(not (EXAMPLE / "convert.py").is_file(), reason="no examples/ in this checkout")


def _example_bundle():
    spec = importlib.util.spec_from_file_location("custom_report_convert", EXAMPLE / "convert.py")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, before = True, sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module.to_bundle(json.loads((EXAMPLE / "my_report.json").read_text(encoding="utf-8")))


def test_the_custom_report_example_converts_and_verifies():
    import eio_agents
    bundle = _example_bundle()
    record = eio_agents.convert(bundle)
    assert record["header"]["per_version"] == "2.1.0"
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"]


def test_the_custom_report_example_digest_in_its_readme_is_current():
    import eio_agents
    record = eio_agents.convert(_example_bundle())
    assert eio_agents.per_sha256(record) in (EXAMPLE / "README.md").read_text(encoding="utf-8")


def test_the_custom_report_example_tests_pass():
    source = str(Path(__file__).resolve().parents[1] / "src")
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_convert.py"],
                       cwd=EXAMPLE, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPATH": source + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")})
    assert p.returncode == 0, p.stdout + p.stderr
