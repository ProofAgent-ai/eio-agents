# Contributing to EIO-Agents

Thank you for considering a contribution. EIO-Agents is small, but its output is byte-exact: a record's digest depends on
every byte of the conversion code and of the bundled EIO release. Most of this guide is about keeping that property.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Do not report security issues in public; see
[SECURITY.md](SECURITY.md).

## Ways to contribute

- **Report a bug.** Include the output of `eio-agents version`, the archive schema of your input, the command or call you
  ran, and what you expected. Do not attach archives that contain personal data or secrets.
- **Improve the documentation.** Corrections and clearer explanations are always welcome.
- **Propose a mapping change.** A framework or control mapping that is wrong, outdated or missing. See
  [Mapping changes](GOVERNANCE.md#mapping-changes).
- **Propose a change to EIO or PER.** A new predicate, a change of meaning, a new record field. These follow the proposal
  process in [GOVERNANCE.md](GOVERNANCE.md#proposals-to-change-eio-or-per).
- **Fix code.** Open an issue first for anything larger than a small fix, so the change class (below) is agreed before you
  start.

## Development setup

```bash
git clone https://github.com/ProofAgent-ai/eio-agents.git
cd eio-agents
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # the test, lint and build tools; ".[test]" is enough to run the tests
.venv/bin/pre-commit install           # optional: run the hooks on every commit
```

Any Python 3.10 or newer should work; the suite is known to pass on 3.11, 3.13 and 3.14.

## The gates every change must pass

Run all of these before you open a pull request:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_native.py tests/test_native_scored_end_to_end.py
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verifier_selftest.py
.venv/bin/python tools/eio_gates.py --examples tests/data/native
.venv/bin/python tools/eio_gates.py --selftest --examples tests/data/native
.venv/bin/python tools/eio_digests.py                # RELEASE-DIGESTS.json reproduces
.venv/bin/pre-commit run --all-files                 # ruff and file hygiene; byte-exact paths are excluded
```

The native tests require the checked-in bundles and byte/digest goldens; missing or changed fixtures fail. The EIO gate
runner also validates the native JCS record and checks that its negative mutations are caught.

The two `tools/eio_gates.py` lines are the forms CI runs; without `--examples` and `--goldens` some gates skip the checks
that read the example records and the sample archives.

Lint uses ruff with the rules in `pyproject.toml`. Do not run `ruff format` or another formatter over the tree: it would
rewrite most files, and the byte-exact paths listed under [Byte rules](#byte-rules) must never be reformatted.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on `main`:

- ruff, the pre-commit hooks and a `CITATION.cff` check;
- the test suite on Python 3.10 to 3.14 on Ubuntu and on Python 3.13 on macOS;
- the test suite with the lowest supported dependency versions (`pyyaml==6.0`, `jsonschema==4.20.0`);
- a build of the sdist and the wheel, `twine check`, and a byte comparison of the packaged files with the source tree;
- the test suite and the verifier self-test against the built wheel, installed alone into a clean virtual environment in
  which ProofAgent Harness is absent;
- the goldens and conformance job: `tools/eio_digests.py`, `tools/eio_gates.py` and its negative vectors, the golden
  and stress records, and the verifier self-test.

Releases are published by a maintainer with the manual workflow `.github/workflows/release.yml`, through PyPI trusted
publishing.

## Change classes

Every pull request states its class. [GOVERNANCE.md](GOVERNANCE.md#change-classes) defines the review each class needs.

| Class | What changes | Examples |
|---|---|---|
| A: editorial | Documentation, comments and docstrings only | A clearer explanation; a typo |
| B: library | Library code; record bytes stay identical | A refactor; a better error message; a new test |
| C: normative | EIO data, EIO or PER schemas, the witness rule, claim states, release rules, digests, PER fields, or any change to record bytes | A new predicate; a changed control mapping; a new record field |

## Byte rules

- **Never edit `src/eio_agents/_vendored/`.** These files are byte-exact copies of two ProofAgent Harness files, pinned by
  sha256; any edit fails the pin check. They are removed at step L4.
- **EIO data is versioned by bytes.** Any edit under `src/eio_agents/ontology/data/` (other than its `README.md` and
  `CHANGELOG.md`) or `src/eio_agents/schemas/eio/` is a Class C change. It needs a module and release version bump under
  the EIO versioning rule, regenerated digests (`tools/eio_digests.py --write`), and an entry in the EIO changelog. Even a
  comment change moves the digest of every record.
- **Record bytes need a reviewed diff.** A change that alters any golden record in `tests/data/expected/` must include the
  diff of the regenerated records and say "Record bytes change: yes" in [CHANGELOG.md](CHANGELOG.md).
- **Do not edit test fixtures by hand.** Every record carries `archive_sha256` of its raw archive, so editing a file in
  `tests/data/raw/` or `tests/data/stress/` changes the golden records and the pinned self-test values.
- **`convert` stays deterministic.** It must use no network, clock, environment variable, random source or harness LLM,
  and must not import ProofAgent Harness. The import-surface tests enforce this.
- **Keep line endings and final newlines.** The data files, schemas and golden records are compared byte for byte. Do not
  let an editor or a hook reformat files under `src/eio_agents/ontology/data/`, `src/eio_agents/schemas/`,
  `src/eio_agents/per/data/`, `src/eio_agents/_vendored/`, `tests/data/` or `tools/snapshots/`, or any `*.jcs` file.
  `.pre-commit-config.yaml` and `.gitattributes` exclude these paths; keep them excluded when you add a hook.

## Wording rules

EIO-Agents documentation and messages use precise, modest language:

- Call the model that grades transcripts the **harness LLM**, and its decisions **model-graded** (or "semantic" for the
  resolver kind). Do not use other names for it.
- A model-graded decision **supports** a claim; it never **proves** one.
- `PROVEN` means proven under the EIO evidence rule. Do not describe it as ground truth.
- Framework mappings express **evidence relevance** and are **provisional**. Do not describe a record, a control status or
  EIO-Agents as certified, compliant or conformant.
- EIO and PER are open specifications, not standards. Do not overstate novelty: each part has prior art, and what is
  new is the combination and the two per-claim rules.
- No emoji in code, documentation or commit messages.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests where behaviour changes.
3. Run every gate above.
4. Update the documentation and [CHANGELOG.md](CHANGELOG.md) (under `[Unreleased]`) if users will notice the change.
5. Open the pull request. State the change class, whether record bytes change, whether EIO data is touched, and which
   gates you ran.

## Contribution terms

No separate Contributor License Agreement or Developer Certificate of Origin sign-off is required for this release.
Unless you explicitly state otherwise, a contribution intentionally submitted for inclusion is submitted under
Apache License 2.0 section 5, without additional terms. See [LICENSE](LICENSE).

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
