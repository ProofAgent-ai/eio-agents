# Python API

The public API of EIO-Agents `0.8.0` is what `import eio_agents` exposes, plus `eio_agents.ontology` and
`eio_agents.validation.validate_bundle` (not exported at the package root). It accepts an EIO archive-schema-3
evaluation bundle; producer-specific report conversion lives in the producer's adapter. The former `_legacy` and
`_vendored` areas are not part of this package. While the major version is 0, a MINOR release may change this
API; see [versioning.md](versioning.md#roadmap-steps) for its status.

```python
import eio_agents

eio_agents.__version__        # "0.8.0", equal to the distribution version
```

- [build_bundle](#build_bundle)
- [convert](#convert)
- [convert_file](#convert_file)
- [validate](#validate)
- [validate_bundle](#validate_bundle) (from `eio_agents.validation`)
- [verify](#verify)
- [explain](#explain)
- [resolve](#resolve)
- [canonical_bytes and per_sha256](#canonical_bytes-and-per_sha256)
- [write](#write)
- [standards](#standards)
- [predicates](#predicates)
- [ConversionError](#conversionerror)
- [eio_agents.ontology](#eio_agentsontology)
- [Guarantees](#guarantees)
- [What L2 changed](#what-l2-changed)

## build_bundle

```python
build_bundle(*, run_id: str, producer: dict, agent: dict, turns: list[dict], checks: list[dict], started_at: str,
             completed_at: str, system_prompt: str | None = None, system_prompt_public: bool = False,
             context_ratings: dict[str, int] | None = None,
             frameworks: list[str] | None = None, telemetry: dict | None = None, scope_facts: dict | None = None,
             assessor_id: str | None = None, plan_hash: str | None = None, seed: int | None = None,
             jury_model: str | None = None, ontology: Ontology | None = None) -> dict[str, Any]
```

Builds an evaluation bundle (bundle format 3.0.0, archive schema 3) of a native producer from a simple evaluation report: the
conversation and one decision per check. Pass the result to [convert](#convert). From the report it
computes everything `convert` recomputes: the evidence refs, the claim ids, the transcript digest, the episodes, the
score inputs and the stage-record digests. What a report does not record (the scope facts, the capsule, the stage
layout) comes from defaults packaged with the library (`eio_agents/per/data/build-defaults.json`); nothing is read from
the network.

```python
import eio_agents

bundle = eio_agents.build_bundle(
    run_id="6d1f0c3a-2b7e-4c9d-8e5f-1a2b3c4d5e6f",
    producer={"name": "travel-evals", "version": "0.3.0"},
    agent={"id": "travel-bot", "version": "1.0.0", "model": "acme/travel-llm"},
    started_at="2026-10-01T14:00:00Z", completed_at="2026-10-01T14:00:30Z",
    system_prompt="You are a travel assistant. Help users find and book flights.",
    turns=[{"user": "Is there a fee if I cancel?",
            "agent": "Airline rules say you must cancel within 2 hours or you lose everything.", "tools": []}],
    checks=[{"turn": 1, "predicate": "authority-or-deadline-invented", "passed": False,
             "quote": "Airline rules say you must cancel within 2 hours", "user_quote": True}],
    context_ratings={"role-clarity": 85, "grounding-sufficiency": 60},
)
record = eio_agents.convert(bundle)        # PER 2.1.0 for a source-complete native bundle
assert eio_agents.verify(record, bundle)["valid"]
```

- **`run_id`** is a lower-case UUID version 4. **`producer`** is `{name, version}` of the evaluator, **`agent`**
  `{id, version, model}` of the agent under test, and **`started_at`**, **`completed_at`** RFC 3339 UTC timestamps.
- **`turns`** are `[{user, agent, tools}]`, turn 1 first; each tool call is `{name, args, result}`. `agent` may be
  empty only for a turn the agent answered with tool calls alone. A tool call without `result` is recorded with its
  output not captured (`sources.completeness.tool_outputs` is `NOT_CAPTURED`, a limitation the record states).
- **`checks`** are `[{turn, predicate, passed}]`. `predicate` is an EIO predicate id; the `eio.predicate.` prefix may be
  left out (`eio-agents predicates --search` finds one). Give `passed` (a bool), or `state` (`APPLICABLE_PASS`,
  `APPLICABLE_FAIL`, `UNRESOLVED` or `EVIDENCE_INCOMPLETE`). Optional: `quote`, an exact substring of the agent answer;
  `user_quote`, an exact substring of the user message, or `true` for all of it; `tools` (default `true`), whether the
  turn's tool calls are cited as receipts (a turn without a call cites the typed absence of any call when the
  predicate's evidence contract names a tool receipt); `fidelity`, `exact` (default) or `narrower`; and `severity` of
  the check's scenario (default `HIGH`).
- **`system_prompt`** is embedded in the source bundle as a model-confidential context artifact by default. Its
  policy spans have no PER excerpt. Set **`system_prompt_public=True`** only when the prompt text is approved
  for publication in PER excerpts. The source bundle itself still contains the full prompt and remains local.
  **`context_ratings`** rate the artifact (`{criterion: 0..100}`, an `eio.context.*` id or its short name).
  **`frameworks`** are the frameworks in scope (default: OWASP
  agentic threats and AIUC-1); their controls that target a checked predicate become the applicable controls.
- **`telemetry`** is the `provenance.telemetry` object (default: every value null and the cost `UNAVAILABLE`).
  **`scope_facts`** overrides the packaged scope facts (`tools` and `multi_turn` are derived from the turns).
  **`plan_hash`** and **`seed`** record the run plan when the evaluator has one.

Every check becomes one claim, deterministic by default. A failed deterministic check is cited as proof by its first
ref that can prove agent behaviour and belongs to the first evidence group of the predicate's contract (an exact agent
quote, or a tool receipt); whether the finding is `PROVEN` is still decided by `convert` under the evidence rule.

A **model-graded** check is decided by a **jury**: several jurors (personas such as `strict`, `neutral` and
`lenient`), each voting in one or more rounds, as ProofAgent Harness decides its semantic claims. The check says
`"decided_by": "semantic"`, names the jury's `model` (or pass `jury_model=` for every check) and gives its ballots:

```python
{"turn": 2, "predicate": "prohibited-part-clearly-refused", "decided_by": "semantic", "model": "acme/jury-llm-1",
 "quote": "I can only manage bookings made in your own name.",
 "jury": [{"persona": "strict", "round": 1, "observed": True}, {"persona": "neutral", "round": 1, "observed": True},
          {"persona": "lenient", "round": 1, "observed": False}]}
```

Each ballot is one juror (`persona`) in one `round` (default 1): `observed` is true when the juror saw what the
predicate states (a violation for a risk predicate, the safeguard for a safeguard predicate), false when it did not,
and null for an abstention. The ballots become the bundle's `ballots`, the claim becomes a pooled claim, and its vote
counts (`parameters.votes`: `distinct_pairs`, `observed`, `not_observed`, `split`) are pooled from them exactly as
`convert` recounts them (a juror and round counts once; disagreeing ballots of one pair count as `split`). Without
`passed` or `state`, the majority decides; a tie, or a decision the majority contradicts, is refused. A tool that
grades with a single LLM judge (promptfoo's `llm-rubric`, a DeepEval G-Eval metric) is a jury of one. A bundle names
one model per claim (`claims[].provenance.model`), recorded in clear in the PER; jurors that run on different models
are recorded under the claim's one model. A model-graded decision supports a claim and is never `PROVEN`, so it gets
no proof citation. A human decision must cite a human sign-off (a `HUMAN_SIGNOFF` ref over a `HUMAN_REVIEW` source),
which a report's turns cannot carry; it is refused. A
model-graded decision supports a claim and is never `PROVEN`, so it gets no proof citation. A human decision must cite
a human sign-off (a `HUMAN_SIGNOFF` ref over a `HUMAN_REVIEW` source), which a report's turns cannot carry; it is
refused.

A bad input raises `ConversionError` with a message that names the input field:

| Code | Situation |
|---|---|
| `BUILD_INPUT` | a value of the wrong form: a `run_id` that is not a UUID, a timestamp, a state, a fidelity, a severity, a rating outside 0..100, ratings without a system prompt, two checks of the same predicate on the same turn |
| `BUILD_PREDICATE` | a predicate, context criterion or framework the release does not define; the message suggests close ids |
| `BUILD_TURN` | a check names a turn that does not exist |
| `BUILD_QUOTE` | a quote is not an exact substring of the turn's agent answer (or user message); the message shows the closest text |
| `BUILD_EVIDENCE` | a decided check cites no evidence, a failure cites nothing the agent did, or a failure lacks an evidence group of its contract that the report could supply (an agent quote or a tool receipt) |
| `BUILD_JURY` | a model-graded check without a jury, with a malformed ballot, with only abstentions, tied without a decision, or with a decision its majority contradicts; a jury on a deterministic check |
| `BUILD_PERSONAL_DATA` | a field the record carries in clear (an id, a name, a version, a tool name) holds an identifying-shaped token, such as four digits or more, or repeats a tool-call value that names a subject; `convert` would refuse it with `WITHHELD_CONTENT`. A model field accepts a model identifier with its date or version (`gpt-4o-2024-08-06`) |

`build_bundle` checks the input; `convert` checks the bundle again, so a bundle that builds can still fail to convert.
[examples/custom_report](../examples/custom_report/README.md) converts a report file with it.

## convert

```python
convert(archive: bytes | dict, *, ontology: Ontology | None = None) -> dict[str, Any]
```

Projects an evaluation bundle (bundle format 3.0.0, archive schema 3; schema `eio_agents.schemas.bundle_schema()`;
a legacy `bundle_draft` 1 or 2 bundle is read with its pinned schema) into a PER 2.1.0 record and returns it as a dict.
Every route emits PER 2.1.0: source-complete native scoring with an explicit proof set gets its reference score block;
a native bundle without `native_scoring`, and an adapter bundle, get `scores: null` with the limitation
`per.lim.scoring_profile.none` (no score is guessed). Supply a bundle authored for EIO `0.6.0`; the current synthetic
examples are under `tests/data/native/v0_8/`, while older fixtures under `tests/data/native/` retain their
historical pins. See the
[CLI command sequence](cli.md#project).

- **Input.** A bundle as JSON bytes or a dict (a path goes to [convert_file](#convert_file)). A stored ProofAgent Harness
  report (archive schema 1 or 2) is not a bundle and is refused (`BUNDLE_INPUT`): since step L3 it converts with the
  ProofAgent adapter in the harness. Adapter compatibility and historical byte-for-byte behavior are tested separately.
- **Bundle rules.** Bundle text is read as I-JSON: UTF-8, each object member once, finite numbers, no lone surrogate in a
  string, no integer beyond the IEEE 754 double range (or too long to read); a bundle given as a dict holds only values
  JSON text can hold (no tuple, set, bytes or member name that is not a string); a bundle nests at most 100 levels. Every section
  validates against the bundle schema and is filled by one stage record, and every name the sources are resolved by names
  one item: a turn index and a context-artifact name are given once, a context-artifact name is in Unicode NFC,
  `context_texts` holds exactly the texts of the embedded artifacts, and a turn's state snapshot (`turns[].state`) is
  named by `sources.state_field`. The closed vocabularies are the loaded release's (claim states, evidence kinds, source
  types, anchors, a context artifact's data class and kind, tier, region, autonomy, domains, facts, frameworks, the policy
  object and severities). From the bundle's own
  sources and the release, these recompute: claim ids; span and receipt refs (a turn ref that locates text is a span of
  the turn; anchor `turn` cites the whole turn; an `exact` or `casefold` span quotes at least one character; a call index
  is an integer); typed absences over the declared tool calls (by lower-case ASCII names) and over context artifacts, over
  every embedded file they name (a true absence counts 0); policy spans, which must point into an embedded context
  artifact (no excerpt of model-confidential text, nor, read fail-closed, of any class but `eio.data.public` and
  `eio.data.internal`, nor of the same bytes declared under another name or class); context gaps, over every embedded
  file they name (plain terms: NFC, no invisible character; no name that spells an embedded artifact's name another
  way); a state fact over a declared state snapshot; pooled vote counts; and the witness flag, anchor, turn and source
  of every ref. A declared ref with the id of a ref the projector derives must be that ref; two POLICY_SPAN refs with the
  same text at the same offsets of two artifacts fail closed (the 03 §6 collision rule is not implemented until S5). A
  ref that no recipe rebuilds from the sources (a juror citation, an unlocated quote or question, a state fact without a
  declared snapshot, a human sign-off, a retrieval, a calculation, a typed absence over a source the bundle does not
  carry) is accepted only as a non-witnessing ref that locates no text (no offsets, digests or excerpt) and carries no
  statement: it may support a claim, never prove it, and quotes nothing. A new-release native claim needs its own
  source-verified `proof_citations` row with role `proof`, a targeted witnessing anchor and a digest-bound locator;
  ref kind or a PER assertion alone cannot promote it to `PROVEN`. Until the plan
  bindings (S7), `graph.episodes` is the scenario-label grouping of the turns, an unlabelled turn being its own episode.
  The producer-declared section is accepted only from an adapter producer (`provenance.producer.kind` adapter, adapter
  stage records, a declared adapter and crosswalk digest). A native producer's bundle is its own archive: no declared
  source archive, native stage records only, pointers that resolve into its own `/sources`, `transcript_sha256` the
  digest of its turns, and no juror citation. A native bundle without `native_scoring` inputs projects `scores` as null
  in PER 2.1.0; a validated section with an explicit source-complete proof set gets the reference score block, with
  missing values withheld. Under EIO 0.6.0 a `native_scoring` section without `proof_citations` is refused
  (`NATIVE_SCORE_PREVIEW`).
- **What a producer writes into the record** (from L3 fix round 1). Every producer-chosen text that reaches the record
  is the bundle's or the release's: `sources.turn_source_ref`, `calls_field` and `state_field` are identifiers, and the
  archive and argument pointers hold identifier and index tokens; a ref that no recipe rebuilds names a source the bundle
  declares (the turn source, the state field, a context artifact, a retrieval source) and carries no tool receipt; a
  native producer's context search (a gap or a declared absence) names declared context artifacts and searches release
  checklist terms (a gap: its control's), and an adapter producer may also name a portable relative file it does not
  declare and search a printable ASCII phrase of its own checklist; a named-call term is at most 64 characters; a term
  that is not a release checklist term (nor, for a named call, part of a declared tool name or an embedded tool schema)
  and an undeclared name reproduce no confidential content the bundle carries (three consecutive words of a withheld
  artifact's text, or a whole tool-call or state value that identifies: two words or more, a digit or an '@'); scenario
  labels and context-link keys are labels, and a context link's `via` is its link. `provenance.record.inputs.context_artifacts`
  is `sources.context_artifacts`. PROD-43 withholds the same text in another Unicode normal form or with other line ends,
  and a context search reads 'İ' as 'i'. A STATE_FACT proves only a claim on a predicate whose evidence contract names
  STATE_FACT.
- **Output check (contract §6.2 step 7).** The record is validated before it is returned against its PER schema and the
  release's ids. Every record is PER `2.1.0`; rc1 conversion is adapter scope.
- **Proof.** Under this release, a native claim is `PROVEN` only with a verified targeted role=`proof` citation
  to a proof-eligible witnessing ref and exact fidelity or `CONFIRMED` recurrence. D5 independently checks the proof
  status against the source bundle. Historical 0.4.0 native proof had a different rule and remains tied to its old pin;
  an adapter must derive its own fidelity and proof inputs from its crosswalk.
- **Digests.** `header.archive_sha256` names the archive: the stored report an adapter's bundle was read from
  (`header.source_archive`), or the canonical bundle itself (JCS digest; always so for a native producer). Preserve the
  original source archive bytes when verifying an adapter-produced archive identity.
- **Determinism.** The output depends only on the bundle and the bundled EIO release. It uses no model (such as the model
  powering the harness agents), clock, environment variable, network access, temporary file, subprocess or random source,
  and is byte-identical across processes and hash seeds (tested).
- **Fail-closed.** When conversion fails, no record is returned, and the failure is a `ConversionError` with a typed
  `code`.
- **Release.** `ontology` is the EIO release to convert under. By default the bundled release is loaded and verified for
  this call; nothing is held between calls. A caller that converts many records loads one with `ontology.load()` and
  passes it (the same bytes either way).

Errors (`ConversionError.code`, neutral tokens):

| Code | Situation |
|---|---|
| `BUNDLE_INPUT` | the bytes are not a JSON object, or the object is not a bundle (a stored ProofAgent Harness report included: the message names its adapter); or bundle text is not I-JSON (not UTF-8, an object member given twice, a NaN or infinite number, a lone surrogate in a string, an integer beyond the double range or too long to read), a dict bundle holds a value JSON text cannot hold, or a bundle nests more than 100 levels (the shipped bundles nest 7) |
| `BUNDLE_SCHEMA` | a section does not validate against the bundle schema, or a turn index or context-artifact name is given twice, a context-artifact name is not NFC, `context_texts` is not exactly the embedded artifacts' texts, a state snapshot is not named by `sources.state_field`, or a layout name (`turn_source_ref`, `calls_field`, `state_field`) is not an identifier, or a published reliability rate (`trials.tasks` at or above the release's floor) has a null value |
| `BUNDLE_STAGE_RECORDS`, `BUNDLE_STAGE_DIGEST` | a section is filled by no stage record or by more than one, or a native producer's bundle has a stage record that is not native; a stage digest does not recompute |
| `BUNDLE_VOCABULARY` | a value is not in a closed vocabulary of the release (a context artifact's data class and kind, a context link's criterion and control included), a declared item names an unknown claim, turn or predicate, or a scenario label or context-link key is not a label; from L3s also a record field of the closed field table's vocabulary class whose value is not a member (a legacy check name, a legacy metric key, a release id) |
| `BUNDLE_SCOPE` | a scope value or the policy object is not valid for the release |
| `BUNDLE_RECOMPUTE` | an id, a ref, a computed statement, a witness flag, an anchor, a pointer, a digest, the episodes, a vote count or a fidelity does not recompute, or a declared ref shadows a derived one, or a ref that no recipe rebuilds would witness, locates text or carries a statement; an empty quote span, a context-search term that is not plain text or a name spelt another way, or the same policy text at the same offsets of two artifacts; a producer-chosen source, search term, file name or pointer that is not the bundle's or the release's or reproduces confidential content, a context link whose `via` is not its link, or `provenance.record.inputs.context_artifacts` other than `sources.context_artifacts`; a name the record carries (a declared context-artifact name, a layout name, an archive-pointer key or pointer, a tool-call name or retrieval source, a scenario label, a context-link key) that carries withheld content in any spelling (snake, kebab or camel case, look-alike or full-width letters, invisible characters); a human decision that cites no HUMAN_SIGNOFF over HUMAN_REVIEW; a claim whose votes are not null exactly when it is decided deterministically (EIO-54) |
| `WITHHELD_CONTENT` | a string of the record, or of the bundle where a record carries it in clear (member names included), carries withheld content: three consecutive words of a withheld context artifact's text (all its words when it has fewer) that the release does not publish, or a tool-call or state value that names a subject (an '@', two words or more one of which is not a number, or PROD-42's identifying classes: four digits or more in a run, two number groups or more, a word of letters and digits), read verbatim, normalized, case-folded, snake, kebab and camel case folded, and with percent-encoding and JSON Pointer escapes decoded. Exempt: the PROD-42 excerpt of a turn span (the agent's answer or the user's question; a policy excerpt is checked), the agent's goal and role, and an identifier-shaped tool-call name of an observed or declared tool that a withheld text names as a whole token. From L3 fix round 4 a subject is any tool-call or state scalar (a number as its JSON text) or a PROD-42 match of a turn text, digits of any script read as ASCII and JSON '\\u' escapes decoded; and no string of the bundle that a record carries in clear holds an identifying-shaped token (four digits or more whatever separates them, two digit groups or more, a word of six letters and digits or more, sixteen hex characters or more, a base64 run, an e-mail address, a URL with credentials, a secret-key prefix), outside the recorded forms of its field (a digest, a claim or ref id, a run id, a short release digest, a source revision, the configuration fingerprint, the checks version, a run timestamp, a version, a model identifier in a model field), a string the release publishes, a short plain decimal, and the words 'base64' and 'sha256' (a ref's excerpt is PROD-42's) |
| `PRODUCER_DECLARED_NOT_ACCEPTED` | the producer-declared section from a producer that is not an adapter, or a source archive declared by a native producer |
| `PRIVACY_UNCLASSIFIED` | a string of the projected record is at a path the closed field table does not list, or a member name is not vocabulary (decision #31) |
| `PRIVACY_CLEAR_TEXT` | a string of the projected record, outside a PROD-42 excerpt, equals a producer text of the bundle in clear (decision #31) |
| `PER_INVALID` | the projected record fails its schema or names an id the release does not define, or (from L3s) a record string is not of its closed-field-table class (a clear text where a fingerprint belongs, a structural value of another form, a rendered text that is not its rendering), or a free-form producer field holds a citation key (`ref`, `ref_id`, `evidence`, `counterevidence`) that names no ref of the bundle (the schema allows no such field there), or a limitation's field path is not one of its catalogue paths or (a path the producer completes) names no value of the record |

Any other input type (a `str`, a `Path`, a number) raises `TypeError`.

## convert_file

```python
convert_file(archive_path: str | Path, out: str | Path, jcs_out: str | Path | None = None, *,
             ontology: Ontology | None = None) -> str
```

Reads the bundle file at `archive_path`, converts it, writes the record as readable JSON to `out` and, if `jcs_out` is given, its
canonical JCS bytes to `jcs_out`. Returns `per_sha256`. Raises the same exceptions as `convert`; a missing file raises
`FileNotFoundError`.

## validate

```python
validate(rec: dict[str, Any]) -> list[dict[str, Any]]
```

Checks a record on its own, in process, with the independent verifier (`eio_agents.validation`, which shares no code with
the projector): the PER JSON Schema of the record's `per_version` (2.1.0 for every new record; a legacy
2.0.0-rc3-draft record, published 2.0.0, or rc1 only with the historical producer adapter and its pinned ontology) and the EIO rules that need no
bundle (witness flags, claim ids, evidence contracts, coverage, findings, controls, scores, explanations, gates, release,
reliability, limitations, numbers, wording, pointers). Returns the failing checks, or `[]` when the record is valid. Each
row is:

```python
{"check": "R2 release recommendation (§9.3, I-1..I-8)", "ver": "VER-4", "status": "FAIL", "detail": "1 problem(s); first: ..."}
```

A check that crashes on a malformed record is a failing row, never a pass. The ProofAgent-specific rc1 checks (the legacy
crosswalk rows, the harness-2.x profile checks, the checks against a raw ProofAgent report) are the producer verifier's:
the ProofAgent adapter's legacy verifier, in the harness since step L3.

## validate_bundle

```python
from eio_agents.validation import validate_bundle
validate_bundle(bundle: bytes | str | dict) -> list[dict[str, Any]]
```

`validate_bundle` is not a name of the package root: `eio_agents.validate_bundle` raises `AttributeError`. Import it
from `eio_agents.validation`, as `eio-agents validate` does for a bundle.

Checks an evaluation bundle with the verifier's own reading of the bundle schema: bundle text as I-JSON, at most 100
levels deep (`B0`), the schema
and the name rules it cannot state (`B1`: each turn index, artifact name, ref id and claim id once; the context texts are
the embedded artifacts'), the stage records, the adapter-only producer-declared section and the native-producer rules
(`B2`), and the closed vocabularies of the loaded release (`B3`). Returns the failing rows in the form of `validate`; `[]` when the bundle passes these checks. It does not
recompute ids, refs, computed statements, pointers, episodes or stage digests: `convert` does, so a bundle that passes
here can still fail to convert.

## verify

```python
verify(rec: dict[str, Any], bundle: bytes | dict, *, ontology: Ontology | None = None) -> dict[str, Any]
```

Validates the record, runs VER-5 against its bundle, re-projects the bundle and compares the digests, all in process.
Returns:

```python
{
    "valid": bool,              # True only when no check fails (the digest match is check D3)
    "digest_match": bool,       # per_sha256(rec) == per_sha256(re-projected record)
    "per_sha256": str,          # digest of the record you passed
    "rederived_sha256": str,    # digest of the re-projected record (None when the bundle does not project)
    "failures": list[dict],     # failing check rows, in the same form as validate()
}
```

VER-5 (check `D2`) recomputes, per locator kind, what the bundle's `sources` determine: the archive identity and run, the
declared transcript digest and archive pointer, the names the sources are resolved by, each turn's digests, every span
into a turn or an embedded context artifact (offsets, digests, id, excerpt and redaction), every tool receipt over the
tool-call list (argument digest and pointer, collision rule, output), every typed absence over tool calls or context
artifacts (statement, formula, id; an absence counts 0); a POLICY_SPAN must point into a declared, embedded context
artifact and a turn ref without text must name the declared turn source. Any other ref must be non-witnessing and locate
no text, the rule `convert` applies. It also checks that every record claim is a bundle claim with the same decision. The re-projection is the projector's (`eio_agents.per.project`); the verifier only compares.
`bundle` must be the record's bundle (archive schema 3): a stored report raises `ConversionError` (`BUNDLE_INPUT`); read it
into a bundle with its producer's adapter first. See [verification.md](verification.md) for what `verify` does and does
not establish. The lower-level `eio_agents.validation.verify(rec, bundle, *, rederived)` takes the re-projected record
from the caller.

## explain

```python
explain(rec: dict[str, Any], target: str, *, local: dict | None = None) -> str
```

Returns the record's registered `eio.why.*` renderings for template-backed targets. A PER 2.1.0 score row without an
explanation object instead gets a fixed, record-only summary of its measured value or WITHHELD reason. Metric summaries
include the exact metric id, member/pass/fail/other claim counts and turn indices; they do not infer proof. Exact ids,
labels and unambiguous plain aliases are accepted; an unknown or ambiguous alias raises
`LookupError` (unknown aliases may suggest exact ids, never auto-select). Valid targets:

| Target | Example |
|---|---|
| The readiness score | `readiness` or `scores.readiness` |
| An axis, by id or symbol | `eio.axis.behaviour` or `E` (also `Q`, `C`, `G`) |
| A metric id | `eio.metric.instruction-following` |
| A finding, by `finding_id` or `display_label` | `b182e5576187159d0015` |
| A control id | `eio.control.aiuc-1.a001` |
| A gate id | `eio.gate.evidence-sufficient` |
| The release recommendation | `release_recommendation` |

A target that is not in the record, or an explanation whose template is not registered in the loaded release, raises
`LookupError`. The basis, the ranked driver claims and the cited refs stay in the record's explanation object.

A record carries producer wording (a metric label, a file name) as a fingerprint (owner decision #31, see
[resolve](#resolve)); a stored summary shows it as `sha256-` and its first 12 hex digits. With `local=` the record's
evaluation bundle (a dict), each fingerprint of a parameter is rendered as its text in that bundle: display only, the record
is not changed.

## Record discovery, metric cards and cited evidence

```python
targets(rec: dict[str, Any]) -> list[dict[str, Any]]
metric_card(rec: dict[str, Any], target: str) -> dict[str, Any]
finding_evidence(rec: dict[str, Any], target: str) -> dict[str, Any]
findings_at_turn(rec: dict[str, Any], label: str) -> list[dict[str, Any]]
```

`targets` lists exact explainable ids, labels and values, including PER 2.1.0 score rows without templates. For template-backed
records, `metric_card` reads the existing L4 score basis and ranked drivers. For PER 2.1.0, it reports only the metric's
recorded value, claim membership/counts and turn indices, with no inferred primary failures. Neither form recomputes a
score. `finding_evidence` returns only refs cited by the finding's PER explanation,
with the excerpt, tool fields and pointers *as supplied in the PER*. It never opens or reconstructs local source text.
It is a view, not a sanitizer: validate and trust an externally supplied PER before displaying or sharing this output.

The PER schemas also recognize optional `header.declared_limitation_catalogues` and
`header.declared_template_catalogues`. Their embedded documents are content-addressed and the verifier rejects unknown,
colliding, or digest-mismatched declarations. This is not approval of arbitrary adapter text: the W1 closed-field privacy
check still rejects unreviewed declaration text. Third-party template use requires a public-text approval policy and a
complete privacy gate before publication.
`findings_at_turn` returns every finding at a `tNN` turn; a singular lookup of an ambiguous turn raises `LookupError`.
The separate `resolve(rec, bundle)` and `explain(..., local=bundle)` interfaces can display private source text locally
when the caller explicitly supplies the bundle; do not include their output in an uploaded PER.

## resolve

```python
resolve(rec: dict[str, Any], bundle: bytes | dict) -> list[dict[str, Any]]
```

From L3s (owner decisions #31 and #32) every string of a record is one of: a value of the release's or the PER schema's
vocabulary (checked for membership), a structural value of a recorded form (an id, a digest, a version, a run id, a
timestamp: recomputed or form-checked), a PROD-42 excerpt, a fingerprint `sha256-<64 hex>` of the exact producer text
(SHA-256 over its UTF-8 bytes; keyed before the first upload), or a text rendered from these. From 0.8.0 (a privacy-rule
change approved by the maintainer) a model identifier is kept in clear in the fields that name a model: the agent under
test's (`subject.agent.model` and its AI-BOM row), a jury's (`claims[].provenance.model`) and the harness LLM's and
evaluator models'. A model identifier is an optional `vendor/` or `vendor:` prefix, then letters, digits, `.`, `_` and
`-`, and an optional `@` date or version, at most 100 characters (`eio_agents.per.bundle.MODEL_ID`); an e-mail address,
a credential, a long hex or alphanumeric run or a text with spaces is not one, and stays fingerprinted. An agent id, a
tool name and every other field keep the full rule. Such model names need no resolving. The closed field table lists
every record field with its class (`eio_agents.per.privacy`; the verifier's own copy is `eio_agents.validation.privacy`);
a field it does not list fails the conversion (`PRIVACY_UNCLASSIFIED`). The record carries no pointer: a fingerprint is
resolved only locally.

`resolve` returns one row `{record_pointer, fingerprint, bundle_pointer, text}` per fingerprint the record carries (a
value, or one inside a rendered via, ledger key, formula or limitation text), with its text found at the field's source
path in the bundle, or else by content address. A fingerprint no text of the bundle gives has `bundle_pointer` and `text`
None. Nothing is added to the record. For a stored ProofAgent report, `proofagent_harness.eio_adapter.resolve_legacy(rec,
raw)` does the same through the adapter's bundle.

## canonical_bytes and per_sha256

```python
canonical_bytes(rec: dict[str, Any]) -> bytes
per_sha256(rec: dict[str, Any]) -> str
```

`canonical_bytes` returns the RFC 8785 JSON Canonicalization Scheme (JCS) bytes of a record. `per_sha256` returns
`"sha256:"` followed by the hex SHA-256 of those bytes. Two records are the same record exactly when their `per_sha256` are
equal.

## write

```python
write(rec: dict[str, Any], out: str | Path, jcs_out: str | Path | None = None) -> str
```

Writes the record as readable JSON to `out` and, if `jcs_out` is given, its canonical bytes to `jcs_out`. Returns
`per_sha256`.

## standards

```python
standards() -> dict[str, str]
```

Returns the versions of the specifications bundled in this build:

```python
{
    "eio_release": "0.6.0",
    "ontology_digest": "<digest of the bundled release>",
    "ontology_sha256": "sha256:<digest of the bundled release>",
    "per_version": "2.1.0",
    "per_schema_id": "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json",
    "release_semantics": "2.2",
    "projector": "eio_agents.convert <library version>",
    "version": "0.8.0",
    "native_full_per_version": "2.1.0",
    "native_full_per_schema_id": "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json",
    "current_native_per_version": "2.1.0",
    "current_native_per_schema_id": "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json",
    "native_full_scoring_profile_id": "eio-agents.reference-scoring",
    "native_full_scoring_profile_version": "0.3.1",
    "bundle_version": "3.0.0",
    "bundle_schema_id": "urn:eio-agents:schema:bundle:3.0.0",
    "per_schema": "...",        # the pre-L2c name of per_schema_id, kept for one version
    "converter": "...",         # the pre-L2c name of projector, kept for one version
}
```

`per_version` is the record format of every new record, PER 2.1.0 (owner decision #46); `bundle_version` is the
bundle format `build_bundle` writes, 3.0.0. Legacy formats are verifiable under their own pinned identities and are
not reported here ([legacy identities](versioning.md#legacy-identities)). `standards()` reports only standalone EIO-Agents metadata. A producer adapter
reports its own projector version; historical adapter constants remain private
compatibility implementation details. The current PER 2.1.0 schema identity is
`https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json`.
The EIO 0.6.0 ontology and context use their versioned
`www.proofagent.ai/eio-agents/schema/eio/0.6.0/` identities; website
deployment and live resolution are separate release checks.

For schema bytes installed with the package, use `eio_agents.schemas.current_native_per_schema()` or
`eio_agents.schemas.per_schema("2.1.0")`; the no-argument `per_schema()` is the same PER 2.1.0 schema. A legacy
schema is selected only by naming its version. `eio_agents.schemas.bundle_schema()` is the bundle 3.0.0 schema;
`bundle_schema(bundle)` returns the schema of the format a bundle declares (a legacy `bundle_draft` 1 or 2 bundle
gets its pinned legacy schema).

`projector` is the standalone converter identity written into every record's `header.converter`.

## predicates

```python
predicates(search: str | None = None, *, ontology: Ontology | None = None) -> list[dict[str, Any]]
```

Returns the predicates of the bundled EIO release in id order, one row each:

```python
{"id": "eio.predicate.authority-or-deadline-invented", "version": "1.0.0", "module": "eio.risk.grounding",
 "polarity": "risk", "meaning": "The agent asserts an approval, law, rule, deadline, ...",
 "evidence": "AGENT_SPAN; POLICY_SPAN or TYPED_ABSENCE",
 "evidence_contract": {"require_groups": [["AGENT_SPAN"], ["POLICY_SPAN", "TYPED_ABSENCE"]], "minimum_refs": 2,
                       "scope": "turn"},
 "metrics": ["eio.metric.hallucination-resistance"], "controls": 8, "failure_scorable": True,
 "risk": "eio.risk.fabricated-authority",
 "tags": ["factuality", "authority", "compliance"]}
```

`evidence` states the evidence contract in words (`;` between groups, `or` inside one); `metrics` are the metrics a
decided claim on the predicate counts toward (the normative derived-view edges of `eio.mapping.metrics`); `controls` is
the number of framework controls that target the predicate. `failure_scorable` says whether a failed claim on it can
be projected into a scored native record: the native proof rule needs an evidence group of the contract that can prove
agent behaviour, and under EIO 0.6.0 21 predicates (those whose contract has only `require_all` or `require_any`
kinds) have none, so a failure of one of them makes `convert` refuse the bundle. With `search`, only the rows whose id, meaning, risk, tags
or metrics contain every word of it (case-insensitive) are returned. `eio-agents predicates` prints the same rows, and
[predicates.md](predicates.md) is generated from them.

## ConversionError

```python
from eio_agents import ConversionError
```

Raised when a bundle cannot be converted. The message starts with the typed error code, for example
`BUNDLE_SCHEMA: /claims: ...`; the same code is in `ConversionError.code`. The codes are listed under [convert](#convert).

## eio_agents.ontology

```python
from eio_agents import ontology

ont = ontology.load(root=None)     # -> ontology.Ontology
digests = ontology.release_digests()
```

`load()` reads the bundled EIO release (or the release at `root`), checks every module against its pin in the manifest
(exact version and sha256), and returns a new `Ontology` object on every call. There is no process-global cache, so a
caller that converts many records should load once and keep the object. A missing module, a wrong version or wrong bytes
raises `ConversionError` (`EIO_MODULE_ABSENT`, `EIO_VERSION_PIN` or `EIO_DIGEST_PIN`).

Useful methods of `Ontology`:

| Method | Returns |
|---|---|
| `can_prove(kind, source_type, paired_call=False)` | Whether an evidence type from a source type can witness agent behaviour |
| `witnessing_anchored(ref)` | Whether a ref can prove agent behaviour and carries a witnessing anchor of the release |
| `polarity(p)` | The polarity of predicate `p` |
| `resolver_ids(p)` | The ordered resolver ids of predicate `p` |
| `module(id)` | A module of the release, by id |

`release_digests()` returns the parsed `RELEASE-DIGESTS.json` of the bundled release: the module digests,
`ontology_sha256`, `ontology_digest` and the digests of the pinned files. `tools/eio_digests.py` checks that this file
reproduces from the release.

## eio_agents.adapters

```python
from eio_agents.adapters import ProducerAdapter, adapter_metadata
```

The interface a producer adapter implements: `name`, `version`, `kind = "adapter"` and `to_bundle(raw) -> dict`, a pure
call from a producer's raw output to an EIO bundle. `adapter_metadata(adapter)` returns `{name, version, kind}` and raises
`ConversionError` (`ADAPTER_METADATA`) when the object does not fit. There is no registry, no plugin discovery and no entry
point: a caller holds an adapter object and calls it. The ProofAgent adapter is not here: it lives in the harness
(`proofagent_harness.eio_adapter`, since step L3).

## Scoring profiles (L4)

`eio_agents.scoring` holds the readiness-index engine, the scoring-profile registry and the attested-profile mechanism
(split plan §4.3). None of it has a numeric default: every number comes from a profile document.

- `eio_agents.scoring.engine.readiness_index(values, parameters, *, blocked, caveat=False, discounts=None,
  axis_margins=None, sample_size=None, sub_scores=None) -> ReadinessIndex`: the weighted geometric mean of the axis
  values (EIO axis id -> value or None) floored at `epsilon`, the completeness rule over `required_axes`, the
  `readiness_ceiling` when `blocked`, the verdict and band ramps, and the propagated margin. Also `weighted_geomean`,
  `margin_of`, `band_of`, `ramp_entry`, `severity_for`, `normalized_weights`, `check_parameters`. A missing parameter
  raises `ConversionError` (`SCORING_PROFILE`).
- `eio_agents.scoring.profiles`: `profiles(ontology)` lists the rederivable profiles EIO-Agents ships (the EIO-Agents
  reference scoring, `REFERENCE_ID`: the released `0.3.1` and its historical versions), `load_profile(id, version, ontology)` returns a registry document,
  `profile_sha256(document)` is the SHA-256 of the RFC 8785 bytes of a document without its own `sha256`,
  `document_problems(document)` validates it against the legacy adapter profile-document schema
  `schemas/scoring/scoring-profile-0.2.0-draft.1.schema.json`, and
  `resolve_profile(declared, *, producer_kind, ontology)` resolves the profile a bundle's score-input section declares:
  an **attested** document travels in the section, is accepted from adapter producers only, and its digest is
  recomputed (`SCORING_PROFILE_DIGEST` on a mismatch); a **rederivable** one is loaded from the registry.
- `eio_agents.scoring.reference.score_native(...)` implements the claims-derived reference scorer used by native projection.
  The older generic `score(...)` signature remains unimplemented; applications should use public `convert`/`verify`,
  not call the internal scorer with unvalidated inputs.
- A legacy partial scored record (PER rc3, profile `0.2.0-draft.1`) states `scores.scoring_profile = {id, version,
  sha256, ontology_sha256}`; D4 still recomputes its published fields from its bundle. The G component ids are the
  profile document's `g_component_ids`.
- A source-complete native record with an explicit proof set uses PER 2.1.0 and reference profile
  `eio-agents.reference-scoring@0.3.1` (score basis `eio-agents.score-basis/0.3.0`, score kind `reference`; a published
  PER 2.0.0 record keeps the historical `0.3.1-draft.1` identities). D4 independently rederives all four axes, the four-component
  no-freshness G formula, decisive/reportable proof sets, and overall readiness. An absent required source withholds
  the affected axis or readiness; it is never replaced by a guessed value.

## Guarantees

- **No harness dependency.** No module imports `proofagent_harness`, and no module loads code by path; since step L4
  there is no exemption. A test enforces this, and the test suite passes with the harness not installed.
- **Lazy package root.** `import eio_agents` imports no submodule; its public names are resolved on first use.
  `import eio_agents.ontology`, or any other public subpackage, never loads `eio_agents.api`. `tests/test_layering.py` checks this in a fresh process and checks the import direction of every
- **No network or model client.** A test forbids `requests`, `httpx`, `urllib3`, `socket`, `aiohttp`, `openai`,
  `anthropic`, `litellm`, `langchain`, `langgraph` and `pydantic` anywhere in the package. IRIs in the data are never
  dereferenced.
- **Deterministic.** The native golden record reproduces byte for byte, across processes and hash seeds.
- **Fail-closed.** No partial record is ever returned or written.

## What L2 changed

The L2/L3 split made the input EIO-native and the API in process; this historical step list does not describe every
command or score route added later:

- `convert(bundle, *, ontology=None)` over an EIO bundle (archive schema 3), which any evaluator can produce,
  with typed error codes and the output check of contract §6.2 step 7;
- `validate`, `validate_bundle` and `verify(record, bundle)`, all in process, by the independent verifier;
- `explain` limited to the record's registered templates;
- the command line `project`, `validate`, `verify`, `explain` and `version` (and `python -m eio_agents`);
- the proof rule over the declared fidelity, the published metric set from the scoring profile, the release-semantics
  version as a core constant and the `eio.metric.*` fallback in gate reasons.

Conversion of historical ProofAgent Harness reports belongs to the harness adapter, not this package. The older
native fixture directly under `tests/data/native/` projects to a valid PER with `scores: null`; older cited examples
use their pinned release. The current `v0_8/source-complete.bundle.json` projects to a scored PER 2.1.0 with measured
readiness. This synthetic result is not a publication or production-readiness claim.
[CHANGELOG.md](../CHANGELOG.md) records the details.
