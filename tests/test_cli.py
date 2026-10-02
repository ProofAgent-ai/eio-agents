"""The console script is `eio-agents`: the neutral commands project, validate, verify, explain and version."""
import json
import re
from pathlib import Path

import pytest

import eio_agents
from eio_agents import cli

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"


def test_console_script_is_eio_agents():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    assert re.findall(r"^([\w.-]+)\s*=", scripts, flags=re.M) == ["eio-agents"]


def test_cli_prog_name(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert capsys.readouterr().out.startswith("usage: eio-agents ")


def test_cli_project_writes_native_canonical_bytes(tmp_path, capsys):
    bundle = DATA / "native" / "v0_6/native.bundle.json"
    out, jcs = tmp_path / "native.per.json", tmp_path / "native.per.jcs"
    assert cli.main(["project", str(bundle), "-o", str(out), "--jcs", str(jcs)]) == 0
    assert jcs.read_bytes() == eio_agents.canonical_bytes(eio_agents.convert(bundle.read_bytes()))
    assert json.loads(out.read_text(encoding="utf-8"))["provenance"]["producer"]["kind"] == "native"
    output = capsys.readouterr()
    assert "PER 2.0.0-rc3-draft" in output.out and "state " in output.out
    assert "PARTIAL/HISTORICAL PER 2.0.0-rc3-draft" in output.err
    assert cli.main(["version"]) == 0
    v = json.loads(capsys.readouterr().out)
    assert "eio_agents" in v and {"per_schema_id", "projector", "ontology_sha256"} <= set(v)


def test_the_neutral_commands(tmp_path, capsys):
    """project | validate | verify | explain | version (split plan §4.2); no `convert` command."""
    with pytest.raises(SystemExit):
        cli.main(["convert", "x", "-o", "y"])
    capsys.readouterr()
    bundle = DATA / "native" / "v0_6/native.bundle.json"
    out = tmp_path / "native.per.json"
    assert cli.main(["project", str(bundle), "-o", str(out)]) == 0
    assert "readiness None" in capsys.readouterr().out                         # no scoring profile
    assert cli.main(["validate", str(bundle)]) == 0 and "VALID (bundle)" in capsys.readouterr().out
    assert cli.main(["validate", str(out)]) == 0 and capsys.readouterr().out.strip() == "VALID"
    assert cli.main(["verify", str(out), "--bundle", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["digest_match"] is True
    assert cli.main(["explain", str(out), "release_recommendation"]) == 0
    assert capsys.readouterr().out.strip()
    assert cli.main(["explain", str(out), "eio.metric.none"]) == 2


def test_a_missing_file_is_reported_without_a_traceback(tmp_path, capsys):
    assert cli.main(["project", str(tmp_path / "missing.json"), "-o", str(tmp_path / "x.json")]) == 1
    err = capsys.readouterr().err
    assert "missing.json" in err and "Traceback" not in err
    assert cli.main(["validate", str(tmp_path / "missing.json")]) == 1


def test_python_dash_m_runs_the_command_line():
    import subprocess
    import sys
    p = subprocess.run([sys.executable, "-m", "eio_agents", "version"], capture_output=True, text=True, check=True)
    assert json.loads(p.stdout)["eio_agents"] == eio_agents.__version__


def test_version_is_the_distribution_version(capsys):
    """`eio_agents.__version__` is the pyproject version (both are bumped on every rebuild), and `version` prints it."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"$', text, flags=re.M).group(1) == eio_agents.__version__
    assert cli.main(["version"]) == 0
    assert json.loads(capsys.readouterr().out)["eio_agents"] == eio_agents.__version__


def test_a_bundle_is_validated_from_its_bytes(tmp_path, capsys):
    """L2 fix round 2 (review R-2): `validate` reads a bundle file as I-JSON, as `project` and `verify` do, so a member given
    twice fails in all three; input that is not a record or cannot be read is reported without a traceback."""
    text = (DATA / "native" / "v0_6/native.bundle.json").read_text(encoding="utf-8")
    twice = tmp_path / "twice.bundle.json"
    twice.write_text(text.replace('"archive_schema": 3', '"archive_schema": 3, "archive_schema": 3', 1), encoding="utf-8")
    assert '"archive_schema": 3, "archive_schema": 3' in twice.read_text(encoding="utf-8")
    assert cli.main(["validate", str(twice)]) == 2 and "B0" in capsys.readouterr().out
    assert cli.main(["project", str(twice), "-o", str(tmp_path / "x.json")]) == 1 and "twice" in capsys.readouterr().err
    rec = tmp_path / "native.per.json"
    assert cli.main(["project", str(DATA / "native" / "v0_6/native.bundle.json"), "-o", str(rec)]) == 0
    capsys.readouterr()
    assert cli.main(["verify", str(rec), "--bundle", str(twice)]) == 1 and "BUNDLE_INPUT" in capsys.readouterr().err
    listed = tmp_path / "list.json"
    listed.write_text("[]", encoding="utf-8")
    assert cli.main(["validate", str(listed)]) == 2 and "S1" in capsys.readouterr().out
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
    assert cli.main(["validate", str(deep)]) == 1 and "Traceback" not in capsys.readouterr().err


def test_cli_json_depth_limit_is_python_version_independent():
    value = cli._bounded_json(b"[" * 100 + b"0" + b"]" * 100)
    for _ in range(100):
        value = value[0]
    assert value == 0
    with pytest.raises(RecursionError, match="100 nesting levels"):
        cli._bounded_json(b"[" * 101 + b"0" + b"]" * 101)
    assert cli._bounded_json(json.dumps({"quote": "[\\\"{" * 120}).encode()) == {"quote": "[\\\"{" * 120}
