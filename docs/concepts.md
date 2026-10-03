# Core concepts

This page explains EIO and PER 2.1 as implemented in EIO-Agents `0.8.0`, which bundles
EIO `0.6.0`. It produces PER `2.1.0` for every new record (release semantics `2.2`); a bundle without native scoring
inputs gets `scores: null`. Counts describe the bundled ontology; they do not imply an accredited standard.

- [The idea in one paragraph](#the-idea-in-one-paragraph)
- [Claims](#claims)
- [Claim states](#claim-states)
- [Predicates and evidence contracts](#predicates-and-evidence-contracts)
- [Evidence](#evidence)
- [The witness rule](#the-witness-rule)
- [Resolvers: code-verified and jury findings](#resolvers-code-verified-and-jury-findings)
- [Proof status](#proof-status)
- [Release recommendation](#release-recommendation)
- [Reliability](#reliability)
- [Scores](#scores)
- [Compliance crosswalk](#compliance-crosswalk)
- [The PER record](#the-per-record)
- [What a record is not](#what-a-record-is-not)
- [Related work](#related-work)
- [EIO at a glance](#eio-at-a-glance)

## The idea in one paragraph

An evaluator produces an archive-schema-3 bundle: transcript, tool calls and results, state, and evaluator signals.
EIO-Agents turns that bundle into claims. Each claim applies one versioned predicate to specific turns and cites its
evidence. Findings, control statuses and the release recommendation are views over claims. Scores may be absent: a
bundle without native scoring inputs remains unscored, and missing required inputs withhold affected score values.
The claims-derived reference scoring is profile `0.3.1`. Whether a claim is
`PROVEN` depends on its decider and evidence, under rules recomputable from the bundle.

## Claims

A claim is the only statement a PER makes about agent behaviour.

- It applies one versioned predicate, for example `eio.predicate.untrusted-instruction-execution` 1.0.0, to specific turns
  of a run.
- It records a state, the evidence refs it cites, and `decided_by`: deterministic code (a code-verified finding, or
  deterministic decision), a semantic resolver (a jury finding, or semantic decision), or a human.
- It records its provenance: the EIO module and module hash, the plan hash and, for semantic claims, the model and seed.
- Claim ids are content digests, so re-deriving a record reproduces them.

Scores, findings, control statuses and the release recommendation cite claim ids and add no facts of their own.

## Claim states

EIO defines seven claim states, and `unknown_is_pass` is `false`: an unknown outcome never counts as a pass.

| Group | States | Meaning |
|---|---|---|
| Scored | `APPLICABLE_PASS`, `APPLICABLE_FAIL` | The predicate applied and was decided |
| Unscored | `NOT_APPLICABLE`, `UNRESOLVED` | The predicate did not apply, or could not be decided |
| Evaluator faults | `EVIDENCE_INVALID`, `EVIDENCE_INCOMPLETE`, `EVALUATOR_ERROR` | The evaluation failed, not the agent |

Only the two scored states enter scores. "Not tested" never becomes "passed", and an evaluator fault is never charged to
the agent.

## Predicates and evidence contracts

EIO 0.6.0 has 58 predicates: 49 risk predicates, 7 safeguard predicates and 2 observation predicates, in 8 risk modules.

Every predicate declares an **evidence contract**: the evidence groups a decision requires, the evidence types that are
forbidden as proof of agent behaviour, `minimum_refs`, and the scope in which refs count.

A predicate's version identifies its proposition (when it applies, when it is satisfied or violated, its polarity, its
unknown policy, its evidence contract). A change to any of these is a new predicate version.

## Evidence

Evidence refs point into the evaluation archive. Each ref has an evidence type, a source type and an anchor.

**Evidence types (11).** Seven can prove agent behaviour: `AGENT_SPAN`, `TOOL_RECEIPT`, `STATE_FACT`, `STATE_TRANSITION`,
`TYPED_ABSENCE` (for example "no verification call before the action"), `CALCULATION` and `HUMAN_SIGNOFF`. Four cannot:
`POLICY_SPAN`, `PROVENANCE`, `USER_INPUT` and `RETRIEVAL`.

**Source types (10).** Five may witness: `AGENT_ANSWER`, `AGENT_TOOL_CALL`, `TOOL_RESULT` (only when paired with its
`AGENT_TOOL_CALL`), `STATE_LEDGER` and `HUMAN_REVIEW`. Five never witness: `USER_INPUT`, `RETRIEVAL`, `POLICY_SOURCE`,
`HARNESS_SIGNAL` and `JUROR_INFERENCE` (a juror's statement that appears in no source).

**Anchors.** Witnessing anchors are `exact`, `casefold`, `receipt` and `computed`. The anchors `line`, `turn`, `document`
and `none` do not witness.

**Privacy.** Refs are content-addressed. Tool arguments are represented by a sha256 and JSON pointer, not copied as
clear text. Excerpts are capped and pattern-redacted, and the record's closed field table fingerprints producer wording
that must not travel in clear. From 0.8.0 a model identifier is the exception: the agent's model, its AI-BOM row and a
jury's model are recorded in clear when the value is a model identifier (`gpt-4o-2024-08-06`,
`anthropic/claude-opus-4-1@20250805`); any other value in those fields is still fingerprinted. `JUROR_INFERENCE` refs carry no text. These controls do not establish that every possible
personal-data class is removed: review a PER before sharing it, and keep `resolve` and `explain --local` output local.

## The witness rule

A ref can witness agent behaviour only when three things hold:

1. its evidence type can prove behaviour;
2. its source type may witness;
3. the pair is compatible. A tool result also needs its paired tool call.

So a user message, a retrieved document, a policy text, or a juror's quote that appears in no source never
witnesses. EIO-Agents computes the witness flag itself and never trusts a flag supplied by the producer of the archive; the
verifier recomputes it for every ref.

A failing risk claim, or a passing safeguard claim, must cite a witnessing, anchored ref. If it does not, the claim records
the unmet rule and cannot be `PROVEN`.

You can query the rule directly:

```python
from eio_agents import ontology

ont = ontology.load()
ont.can_prove("AGENT_SPAN", "AGENT_ANSWER")                      # True
ont.can_prove("USER_INPUT", "USER_INPUT")                        # False
ont.can_prove("TOOL_RECEIPT", "TOOL_RESULT")                     # False: no paired call
ont.can_prove("TOOL_RECEIPT", "TOOL_RESULT", paired_call=True)   # True
```

## Resolvers: code-verified and jury findings

A resolver decides a claim. EIO 0.6.0 has 11 resolvers: 8 deterministic, 2 semantic and 1 human. A deterministic resolver
gives code-verified findings (deterministic decisions): checks in code with exact evidence. A semantic resolver gives jury
findings (semantic decisions): the verdict of an evaluation jury. In the ProofAgent Harness, a multi-agent evaluation
infrastructure, that is a jury of juror agents that reach consensus.

A jury finding is useful evidence for a human reviewer, but EIO treats it as support, not proof:

- a claim decided by a semantic resolver is never `PROVEN`;
- a release decision that rests only on semantic resolvers can at most be REVIEW (`eio.profile.resolver-authority`).

The standalone package's synthetic native fixture demonstrates both deterministic and semantic decisions. Historical
producer golden records are adapter-compatibility tests, not bundled native examples.

## Proof status

A claim is `PROVEN` only when all three of these hold:

1. it was decided by deterministic code or by an identified human;
2. it cites a witnessing, anchored ref;
3. its declared fidelity to the predicate (`parameters.fidelity`, required on every claim) is `exact`, or its recurrence
   band is `CONFIRMED`. No claim is exempt by where it came from: an adapter derives the fidelity from its crosswalk (the
   ProofAgent adapter uses the mapping relation), and a native producer declares it.

Every other claim is `UNPROVEN`. A finding is `PROVEN` when one of its claims is.

`PROVEN` is a rule about the evidence type and the decider. It means proven under the EIO evidence rule, not ground truth:
a deterministic check can still be wrong, and an archive can still be wrong.

In the synthetic native fixture, the turn-3 `authority-or-deadline-invented` finding is `UNPROVEN`: a deterministic
decision alone does not suffice when the declared fidelity is `narrower` and recurrence is `NOT_RETESTED`. The fixture's
overall recommendation is `REVIEW` (it declares no policy, and its readiness is below the default floor of 85); it is
a small demonstration, not a safety benchmark.

## Release recommendation

The release recommendation is PASS, REVIEW or BLOCK, derived from claims by the release rules of the bundled EIO release.

- BLOCK requires a `PROVEN` claim or a declared prohibited use case.
- A failed floor or a triggered policy rule without proof gives REVIEW, with the evidence attached for a human.
- With no declared policy (`policy.source` `none`), a PER 2.1.0 record is REVIEW whenever readiness is below the
  default floor of 85 (or withheld) or any HARD_BLOCK obligation is unmet (release semantics 2.2, decisive entries
  `eio.release.default-readiness-floor` and `eio.release.hard-block-unmet`). These never BLOCK.
- The recommendation lists its decisive conditions and the claims that drive them, so `explain` can show why.

## Reliability

Flagged scenarios can be re-run. EIO keeps two ledgers apart:

- **Occurrence:** did the behaviour happen, with valid evidence? A later non-recurrence never withdraws it.
- **Recurrence:** did it reproduce across re-test passes?

A finding's recurrence band is one of `CONFIRMED`, `INTERMITTENT`, `UNCONFIRMED` or `NOT_RETESTED`. A proxy (narrower)
observation becomes `PROVEN` only when its band is `CONFIRMED`.

EIO defines three trial kinds: repeat, metamorphic and counterfactual. A decision that changes under a metamorphic variant
counts against the evaluator, not the agent.

pass^k is estimated without bias as C(c, k) / C(n, k), with a standard error. Below `minimum_tasks` (5) no rate is
published; the record gives named lists instead (always, sometimes and never failing).

## Scores

A record may carry a readiness score, four axis values and metric values. The axes are Q (context), E (behaviour), C
(compliance) and G (governance); EIO 0.6.0 defines nine metric concepts. A bundle with no native scoring inputs
projects `scores: null` (with the limitation `per.lim.scoring_profile.none`). Validated native scoring inputs produce the
reference score block (kind `reference`), where a value whose sources are absent is withheld: the cited synthetic
example measures metrics and axes, but readiness is null/`WITHHELD` because requisite evidence is not established. D4 independently checks its score fields, and D5 checks citation-based proof status. This is not a
complete numeric readiness score or an accuracy claim. An approved producer adapter may separately supply an attested
profile; those results are adapter-scoped, not native reference scoring.

## Compliance crosswalk

36 of the 58 predicates map to 165 controls in 30 framework views, such as the EU AI Act, NIST AI RMF, ISO/IEC 42001, the
OWASP lists for LLM and agentic applications, AIUC-1, SOC 2 and privacy laws. There are 406 control-to-risk links and 434
control-to-predicate links. The other 22 predicates map to no control: the 6 evaluator-reliability predicates, the 7
safeguard predicates, the 2 observation predicates, and 7 risk predicates such as `resource-budget-exceeded` and
`tenant-boundary-crossing` ([standards.md](standards.md#known-gaps) lists them).

A control's status is derived deterministically from the claims on its target predicates. There are six statuses:
`observed_satisfaction`, `observed_violation`, `not_tested`, `not_observable`, `not_applicable` and `inconclusive`.

Read them with care:

- Every mapping is `provisional` and flagged `legal_review_required`. A status shows evidence relevance from one run, not
  certification or legal conformity. The verifier rejects a control summary that says "compliant".
- A violation that rests only on proxy claims is marked `proxy_only` and is never decisive.
- `observed_satisfaction` means at least one passing claim and no failing one. It does not mean that every target was
  exercised.
- Some controls are broad (whole NIST AI RMF functions, topic-level ISO/IEC 42001 controls). They can show
  `observed_satisfaction` for organisational requirements that a single run cannot evidence.

[standards.md](standards.md) lists the 30 views and the known coverage gaps.

## The PER record

A PER record (2.1.0, and the legacy rc1 and rc3 formats) has exactly 14 required top-level blocks, and no others:

`header`, `provenance`, `subject`, `scope`, `evidence`, `claims`, `coverage`, `findings`, `controls`, `scores`,
`reliability`, `release_recommendation`, `limitations`, `telemetry`.

- Claims are the facts. Every other block cites claims and evidence refs.
- Every "why" is rendered from one of 36 registered templates, never from model-written prose.
- The `limitations` block uses core limitations plus any explicitly declared, content-addressed limitation catalogue;
  an undeclared or digest-mismatched id fails closed.
- `per_sha256` is `"sha256:"` followed by the SHA-256 of the record's RFC 8785 (JCS) canonical bytes.

Anyone with the archive and the same EIO-Agents version can re-derive the record and compare digests. See
[verification.md](verification.md).

## What a record is not

- It is not proof that the archive came from a real run. Verification proves integrity and a correct conversion only.
- It is not a prediction that the agent, or a jury, would decide the same way again.
- It is not a certification, an attestation or a statement of legal conformity.
- It is not signed. Signed attestation is planned, not built.
- `PROVEN` is not ground truth. It is the outcome of the EIO evidence rule.

## Related work

As of 2026-09-28. Each part of EIO and PER has prior art. These are the closest formats and tools we know of;
[standards.md](standards.md#relation-to-other-evaluation-formats) lists the formats EIO-Agents is meant to map to.

- [W3C EARL 1.0](https://www.w3.org/TR/EARL10-Schema/): test outcomes (`passed`, `failed`, `cantTell`, `inapplicable`,
  `untested`) and assertion modes (`automatic`, `manual`, `semiAuto`).
- [UK AISI Inspect](https://inspect.aisi.org.uk/): evaluation logs in which unscored samples are excluded from metrics
  and a score can carry a reason (`Score.reason`), and pass@k and pass^k metrics over epochs.
- [JUnit XML](https://github.com/windyroad/JUnit-Schema/blob/master/JUnit.xsd): the distinction between an error, a
  failure and a skipped test, the same split as between EIO's evaluator-fault states and a failing claim.
- [tau-bench](https://arxiv.org/abs/2406.12045): the pass^k reliability metric for agents.
- [verievals](https://github.com/KaushikKC/verievals) and [inspect-receipts](https://pypi.org/project/inspect-receipts/):
  digest-checked and signed evaluation records.
- [release-gate](https://github.com/VamsiSudhakaran1/release-gate): a release verdict (PROMOTE, HOLD or BLOCK) derived
  from claims, stated coverage and a methodology.
- [PROCTOR](https://arxiv.org/abs/2609.02246): a position paper that makes a model grader an advisor behind
  deterministic acceptance checks. The [Evaluation Context Protocol](https://arxiv.org/abs/2608.19263) (ECP) plans
  deterministic graders that gate model-based ones.
- [AIUC-1](https://www.aiuc-1.com/): a certification standard for AI agents. EIO includes it as one of the 30 framework
  views, as evidence relevance only.

## EIO at a glance

EIO 0.6.0 in this development tree is a release of 39 modules (the manifest `eio.manifest.public` plus 38 imported modules), each pinned by exact
version and sha256. The loader rejects a missing module, a wrong version or wrong bytes.

| Item | Count in EIO 0.6.0 |
|---|---|
| Predicates | 58 (49 risk, 7 safeguard, 2 observation) |
| Evidence types | 11 (7 can prove agent behaviour) |
| Source types | 10 (5 may witness) |
| Resolvers | 11 (8 deterministic, 2 semantic, 1 human) |
| Claim states | 7 |
| Recurrence bands | 4 |
| Axes | 4 (Q, E, C, G) |
| Context criteria | 7 |
| Metric concepts | 9 (reference profile 0.3.1; a value without its sources is withheld) |
| Domain modules | 11, with 126 coverage obligations |
| Flow stages | 13 |
| "Why" templates | 34 |
| Profiles | 29 |
| Framework views and controls | 30 views, 165 controls |
| Reference cases | 45, all `review.status: seed` (not adjudicated) |

EIO is "a vocabulary with contracts", not an OWL or RDF ontology. It ships as YAML modules with JSON Schemas (4 EIO
schemas) and a JSON-LD context. There is no OWL or SKOS projection. Its `production_status` is `candidate`.
