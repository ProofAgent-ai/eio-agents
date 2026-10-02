"""Keep dedicated verifier checks from silently collecting zero tests in CI."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("workflow_name,expected", [("ci.yml", 3), ("release.yml", 1)])
def test_verifier_selftest_steps_use_pytest(workflow_name, expected):
    workflow_path = Path(__file__).parents[1] / ".github/workflows" / workflow_name
    if not workflow_path.exists():
        pytest.skip("workflow is intentionally absent from the source distribution")
    workflow = yaml.safe_load(workflow_path.read_text())
    commands = [str(step.get("run", "")) for job in workflow["jobs"].values()
                for step in job.get("steps", [])]
    commands = [command for command in commands if "tests/test_verifier_selftest.py" in command]
    assert len(commands) == expected
    assert all(" -m pytest " in command for command in commands)
