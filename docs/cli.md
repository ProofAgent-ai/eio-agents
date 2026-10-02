# Command line

Installing EIO-Agents adds one console script, `eio-agents` (also `python -m eio_agents`). It wraps the
[Python API](api.md). The commands are `project`, `validate`, `verify`, `explain`, `evidence`, `resolve` and `version`.

```text
usage: eio-agents [-h] {project,validate,verify,explain,evidence,resolve,version} ...
```

| Command | Exit codes |
|---|---|
| [`project`](#project) | 0 success (whatever the state); 1 a projection error or a file that cannot be read |
| [`validate`](#validate) | 0 valid; 2 invalid; 1 a file that cannot be read |
| [`verify`](#verify) | 0 valid and digests match; 2 otherwise; 1 a file that cannot be read or a bundle input error |
| [`explain`](#explain) | 0; 2 an unknown/ambiguous target or an unregistered template |
| [`evidence`](#evidence) | 0; 2 an unknown/ambiguous finding |
| [`resolve`](#resolve) | 0; 2 a withheld value that no text of the bundle gives |
| [`version`](#version) | 0 |

A missing or unreadable file is reported on standard error as `eio-agents <command>: <reason>`, without a traceback, and
nothing is written.

## project

```bash
eio-agents project BUNDLE -o OUT [--jcs JCS_OUT]
```

Projects an evaluation bundle (archive schema 3, draft 2) into a PER record (PER 2.0.0 full-score wire when its explicit proof
set and all required sources are present; explicitly labeled rc3 partial route when the proof set is absent), writes it as readable JSON to `OUT`
and, with `--jcs`, its canonical JCS bytes to `JCS_OUT`. A stored ProofAgent Harness report (archive schema 1 or 2) is not
a bundle and is refused (`BUNDLE_INPUT`): since step L3 it converts with the ProofAgent adapter in the harness
(`proofagent_harness.eio_adapter`). It prints the actual PER version in its summary and warns on standard error if it produced the partial route:

From the repository root, supply a native bundle authored for EIO `0.6.0`. The `v0_6` fixture below is a
current synthetic quick-start input; older fixtures directly under `tests/data/native/` retain historical pins:

```bash
eio-agents project tests/data/native/v0_6/source-complete.bundle.json -o native.per.json --jcs native.per.jcs
```

The output path and its `sha256:` digest precede a summary whose state, readiness, claims and findings depend on the
bundle. A rule-derived recommendation is not a quality grade.

- The exit code is 0 on success, whatever the release recommendation. Mapping PASS, REVIEW and BLOCK to exit codes is the
  job of the program that runs the evaluation, not of EIO-Agents.
- On a `ConversionError` it prints `PROJECTION FAILED (no record written): <CODE>: <reason>` to standard error and exits
  with 1. The codes are listed in [api.md](api.md#convert).
- A bundle without native scoring inputs prints `readiness None` and has `scores: null`; a partially scored bundle may
  also print `readiness None` when required evidence for G/readiness is absent.

## validate

```bash
eio-agents validate FILE
```

Checks a record on its own with the independent verifier: the PER JSON Schema and the EIO rules that need no bundle.
Prints `VALID` and exits with 0, or prints one line per failing check and a count, and exits with 2. Run
`eio-agents validate native.per.json` to check the projected PER, or
`eio-agents validate tests/data/native/v0_6/source-complete.bundle.json` to check the synthetic input bundle.

A JSON file that is not a record (for example `[]`) gives one failing S1 row and exit code 2. When `FILE` is an evaluation
bundle (archive schema 3), `validate` checks the bundle instead, from the file's bytes (`validate_bundle`: the text as
I-JSON, the schema and its name rules, stage records, the adapter-only section, the release's vocabularies) and prints
`VALID (bundle)`.

## verify

```bash
eio-agents verify RECORD --bundle BUNDLE
```

Validates the record, runs VER-5 over the bundle's sources, re-projects the bundle and compares the digests, in process.
For the same bundle, run `eio-agents verify native.per.json --bundle tests/data/native/v0_6/source-complete.bundle.json`. It
prints a JSON summary, then one line per failing check:

```json
{
 "valid": true,
 "digest_match": true,
 "per_sha256": "sha256:<the record digest>",
 "rederived_sha256": "sha256:<the same digest>"
}
```

Exits with 0 when `valid` is true, otherwise with 2. `BUNDLE` must be the record's bundle; a stored report is refused
(`BUNDLE_INPUT`, exit code 1). See [verification.md](verification.md).

## explain

```bash
eio-agents explain RECORD TARGET [--local BUNDLE]
eio-agents explain RECORD --list
eio-agents explain RECORD finding t01
```

Prints a target's registered `eio.why.*` rendering when that target has a template explanation. For PER 2.0.0 score
rows without templates, it displays the PER's recorded Q/E/C/G/readiness value or a fixed plain-language WITHHELD
reason. `--list` shows exact ids, labels, values or WITHHELD reasons, and the Q/E/C/G legend. An exact id, label or
unambiguous plain alias such as `hallucination`, `context` or `release` may be a target; a typo suggests exact ids
without auto-selecting. A PER 2.0.0 metric shows its exact metric id, member/pass/fail/other claim counts and turn indices;
it does not infer proof or rank failures. Template-backed metric cards retain their existing driver rendering.
`TARGET` must be one of the targets actually listed:

- `readiness` or `scores.readiness`;
- an axis id or symbol: `Q`, `E`, `C`, `G`, or for example `eio.axis.behaviour`;
- a metric id, for example `eio.metric.instruction-following`;
- a `finding_id` or a finding's `display_label`;
- a `control_id`, for example `eio.control.aiuc-1.a001`;
- a gate id, for example `eio.gate.evidence-sufficient`;
- `release_recommendation`.

```bash
eio-agents explain native.per.json --list
eio-agents explain native.per.json release_recommendation
eio-agents explain native.per.json TARGET_ID
```

The release explanation and finding states depend on your bundle. Replace `TARGET_ID` with an id from `--list`.
To display locally resolvable producer wording, add
`--local tests/data/native/v0_6/source-complete.bundle.json` for the synthetic example; do not upload that local output as the PER.

A record carries no producer free text in clear (owner decision #31): the metric label is the producer's wording, so the
record holds its fingerprint `sha256-<64 hex>` and a summary shows the first 12 hex digits. With `--local BUNDLE` (the
record's evaluation bundle, on your machine) each fingerprint of the rendering is shown as its text in that bundle; this is
display only, and nothing is written into the record.

`finding t01` explains every finding at that turn. A plain `t01` that names multiple findings is ambiguous and exits 2;
the command never silently picks one. An unknown target or unregistered template also exits 2.
For PER 2.0.0 score targets, `--local BUNDLE` does not add raw source text to the score summary. Finding and template-backed
explanations still follow the local fingerprint-resolution behavior described above.

## evidence

```bash
eio-agents evidence RECORD FINDING
```

Shows only the supplied PER's refs cited by that finding, with turn, its existing redacted excerpt, tool receipt or
source pointer/hash. `FINDING` accepts an exact finding id or `tNN` to display every finding at that turn. This command
does not accept a bundle, read local source, or reconstruct a fingerprint. In contrast, `explain --local` and `resolve`
are explicitly local-only interfaces that can display withheld source text when the caller supplies a bundle.
`evidence` displays fields in the supplied file; it does not validate or sanitize an untrusted file first. Run
`eio-agents validate RECORD` and trust the record's provenance before displaying or sharing its output.

## resolve

```bash
eio-agents resolve RECORD BUNDLE
```

Prints every withheld value of the record (a fingerprint in a field of the closed field table, or inside a rendered via,
ledger key, formula or limitation text), one per line: the record pointer, the fingerprint's display form, the bundle
pointer of its text and the text itself (JSON-quoted); then a count. The text is found at the field's source path, or else
by content address anywhere in the bundle. Exit 0 when every value resolves, 2 otherwise. Local only: the record is not
changed.

```bash
eio-agents resolve native.per.json tests/data/native/v0_6/source-complete.bundle.json
```

Its output can contain sensitive text for real bundles; keep it local. The exact number of resolved values depends on
the supplied bundle and the record's fingerprints.

## version

```bash
eio-agents version
```

Prints the library version and bundled specifications as JSON: `eio_agents`, `eio_release`, `ontology_digest`,
`ontology_sha256`, the historical partial-route `per_version` and `per_schema_id`, `projector`, `version`, and the
`native_full_per_version`, `native_full_per_schema_id`, `native_full_scoring_profile_id`, and
`native_full_scoring_profile_version` for the PER 2.0.0 route. It also includes `per_schema` and `converter` (the pre-L2
names of `per_schema_id` and `projector`, kept for one version). Include this output in every bug report.
