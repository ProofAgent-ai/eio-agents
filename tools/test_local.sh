#!/usr/bin/env bash
# Local release check for EIO-Agents. Run it before every commit you push and before every release tag.
#
# EIO-Agents is tested locally (owner decision #45): GitHub runs no tests on push or pull request, and the release
# workflow (.github/workflows/release.yml) publishes a pushed tag v<version> to PyPI without testing it. This script
# runs the checks the manual CI workflow (.github/workflows/ci.yml) would run:
#
#   1. ruff and the pre-commit file-hygiene hooks           (ci.yml: lint)
#   2. the full test suite, network denied where possible    (ci.yml: test)
#   3. release digests, EIO gates, negative vectors, goldens (ci.yml: conformance)
#   4. sdist and wheel build, twine check, packaged bytes    (ci.yml: build)
#   5. the suite and the verifier self-test against the built wheel alone (ci.yml: wheel)
#
# One-time setup (Python 3.10 or newer):
#   python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" "pytest-xdist>=3.6" "hatchling>=1.27"
# Usage:
#   tools/test_local.sh            # everything
#   tools/test_local.sh --quick    # steps 1 and 2 only
# PYTHON=/path/to/python overrides the interpreter (default .venv/bin/python).
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1
export PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*"; exit 1; }

[ -x "$PY" ] || fail "no interpreter at $PY; see the one-time setup at the top of this script"
"$PY" - <<'EOF' || fail "missing tools; run: $PY -m pip install -e '.[dev]' 'pytest-xdist>=3.6' 'hatchling>=1.27'"
import sys
assert sys.version_info >= (3, 10), f"Python 3.10+ required, found {sys.version.split()[0]}"
import build, hatchling, pytest, twine, xdist  # noqa: F401
EOF
BIN="$(dirname "$PY")"

# Deny network to the test runs on macOS, as the suite must pass offline.
OFFLINE=()
if [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/sandbox-exec ]; then
  OFFLINE=(/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)')
fi
pytest_offline() { "${OFFLINE[@]}" "$PY" -m pytest -q -p no:cacheprovider "$@"; }

step "1/5 Lint"
"$BIN/ruff" check . || fail "ruff"
if [ -x "$BIN/pre-commit" ]; then
  SKIP=ruff-check "$BIN/pre-commit" run --all-files --show-diff-on-failure || fail "pre-commit hooks"
else
  echo "pre-commit not installed: file-hygiene hooks skipped"
fi

step "2/5 Test suite (offline, parallel)"
pytest_offline -n auto || fail "test suite"

if [ "$QUICK" = 1 ]; then
  printf '\n\033[32mQuick check passed (lint and test suite).\033[0m Run without --quick before a release tag.\n'
  exit 0
fi

step "3/5 Goldens and conformance"
"$PY" tools/eio_digests.py || fail "release digests"
"$PY" tools/eio_gates.py --examples tests/data/native || fail "EIO gates"
"$PY" tools/eio_gates.py --selftest --examples tests/data/native || fail "EIO negative vectors"
pytest_offline tests/test_verifier_selftest.py || fail "verifier self-test"

# Physical path: on macOS /var is a symlink to /private/var, and package paths resolve through it.
TMP="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP"' EXIT

step "4/5 Build and check the distributions"
"$PY" -m build --no-isolation --outdir "$TMP/dist" . >"$TMP/build.log" 2>&1 || { cat "$TMP/build.log"; fail "build"; }
"$PY" -m twine check --strict "$TMP"/dist/* || fail "twine check"
"$PY" .github/scripts/check_dist.py "$TMP/dist" || fail "packaged files differ from the source tree"
shasum -a 256 "$TMP"/dist/* | sed "s|$TMP/dist/||"

step "5/5 The built wheel, installed alone"
# The build is offline (--no-isolation uses the hatchling installed above). The wheel goes into its own directory, ahead of the source tree on sys.path; dependencies come from $PY.
"$PY" -m pip install -q --no-deps --target "$TMP/wheel" "$TMP"/dist/eio_agents-*.whl || fail "wheel install"
PYTHONPATH="$TMP/wheel" "$PY" - "$TMP/wheel" <<'EOF' || fail "wheel import"
import importlib.util, pathlib, sys
import eio_agents
assert importlib.util.find_spec("proofagent_harness") is None, "proofagent_harness must not be importable"
where = pathlib.Path(eio_agents.__file__).resolve()
assert pathlib.Path(sys.argv[1]).resolve() in where.parents, f"eio_agents imported from {where}, not the wheel"
print("eio_agents", eio_agents.__version__, "from the built wheel")
EOF
PYTHONPATH="$TMP/wheel" pytest_offline -n auto || fail "test suite against the wheel"
PYTHONPATH="$TMP/wheel" pytest_offline tests/test_verifier_selftest.py || fail "verifier self-test against the wheel"

printf '\n\033[32mAll local release checks passed.\033[0m Safe to commit, push and tag.\n'
