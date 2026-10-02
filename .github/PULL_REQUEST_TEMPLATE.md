## Summary

<!-- What does this pull request change, and why? Link the issue or the EIO change proposal it implements. -->

Closes #

## Change class

<!-- See "Change classes" in CONTRIBUTING.md. Tick one. -->

- [ ] A: editorial (documentation, comments and docstrings only)
- [ ] B: library (library code; record bytes stay identical)
- [ ] C: normative (EIO data, EIO or PER schemas, the witness rule, claim states, release rules, digests, PER fields, or
      any change to record bytes). Link the accepted proposal:

## Record bytes and EIO data

- Record bytes change: <!-- yes / no. If yes, attach the diff of the regenerated golden records in tests/data/expected/
  and say "Record bytes change: yes" in CHANGELOG.md. -->
- EIO data or schemas touched (`src/eio_agents/ontology/data/`, `src/eio_agents/schemas/`, `src/eio_agents/per/data/`):
  <!-- yes / no. If yes: module and release version bumps, `tools/eio_digests.py --write`, and an entry in the EIO
  changelog. -->
- `src/eio_agents/_vendored/` is unchanged. <!-- It must be: these files are pinned by sha256. -->

## Gates run

<!-- Tick what you ran locally. CI runs all of them. -->

- [ ] `python -m pytest -q -p no:cacheprovider`
- [ ] `python -m pytest -q tests/test_native.py tests/test_native_scored_end_to_end.py` (native goldens and rc3 cited record)
- [ ] `python -m pytest -q -p no:cacheprovider tests/test_verifier_selftest.py` (13 collected cases)
- [ ] `python tools/eio_gates.py --examples tests/data/native` (0 failing)
- [ ] `python tools/eio_gates.py --selftest --examples tests/data/native` (0 not caught)
- [ ] `python tools/eio_digests.py` (exit 0)
- [ ] `ruff check .` or `pre-commit run --all-files`

## Checklist

- [ ] Tests added or updated where behaviour changes.
- [ ] Documentation and `CHANGELOG.md` (under `[Unreleased]`) updated if users will notice the change.
- [ ] The wording rules in CONTRIBUTING.md are followed: a model-graded (harness LLM) decision supports a claim but never
      proves it; mappings express evidence relevance and are provisional; no claim of certification or compliance.
- [ ] No personal data, secrets or confidential content in code, fixtures or messages.
