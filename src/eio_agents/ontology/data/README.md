# EIO: Evaluation Intelligence Ontology (0.6.0)

EIO is a public, machine-readable semantic layer for AI-agent evaluations. It defines
what an evaluation harness can observe, what evaluation propositions mean, what evidence they
require, how risks relate to domains, and how canonical claims map to metrics and external
control frameworks.

The ontology is Apache-2.0 licensed and operates locally. It contains no remote lookup,
telemetry, entitlement check, or hosted dependency.

## Design rules

1. **Meaning is versioned.** Every module and predicate has a semantic version.
2. **Facts precede judgement.** Deterministic extractors and tool/state receipts are used
   before a semantic resolver.
3. **LLMs resolve relations, not policy.** A model may decide a narrow relation such as
   `implements(action, instruction)`; it cannot invent applicability, severity, or a rule.
4. **Unknown is explicit.** Missing or invalid evidence never becomes a pass.
5. **Evidence is typed.** User input cannot prove an agent behaviour.
6. **Plans are pinned.** Generated scenarios are frozen with their bindings and hashes
   before execution.
7. **Scores are views.** Metrics and compliance controls derive from canonical evaluation
   claims and are not part of factual truth.
8. **Domains extend the core.** Domain modules add roles, data, actions, obligations, and
   risk profiles without redefining core relations.

## Layout

```text
schemas/     JSON Schemas for modules, evidence graphs, evaluation claims, cases
core/        entities, relations, evidence kinds, resolver contracts, outcomes, FLOW
risks/       framework-neutral risk concepts and evaluable predicates
domains/     domain types, protected actions, policies, and coverage obligations
context/     the Q axis — criteria over the agent's own static artifacts
governance/  risk tiers, autonomy levels, regions, and release gates
compliance/  first-class framework and control views with claim/evidence traceability
scoring/     axes, aggregation, caps and floors
reliability/ trials, the two ledgers, the estimator and its publication floor
assurance/   stack, lifecycle, releases, monitoring, and system-of-record semantics
mappings/    legacy, trap, metric, and compatibility views
templates/   reproducible gold and generative test-template declarations, and the explanation
             ("why") template catalogue (templates/why.yaml)
reference/   seed reference cases (not yet adjudicated; review.status seed) for validating the evaluator
```

## The four axes, and one spine

Every behavioural layer reaches the report through `EvaluationClaim` and nothing else; the context layer reaches it through typed evidence of what its artifacts contain:

| Layer | Reaches the report by | Never |
|---|---|---|
| `context/` | checklist control presence over a `ContextArtifact` (a view, not a claim; a CONTEXT_GAP finding cites `TYPED_ABSENCE` refs) | rating a checklist criterion by assessor |
| `risks/` | producing claims over an `Episode` | deciding severity or applicability |
| `governance/` | `raises-impact-of` on an obligation | contributing a score to any axis through the profile, tier or escalation (the G axis is the scoring module's view) |
| `compliance/` | a control view over claims and inherited evidence contracts | asserting certification |
| `scoring/` | `aggregates-to` from claims (metric views, the E axis); under harness-2.x, the pinned Q, C, G and readiness numbers traced to their components | creating or re-opening a claim |
| `reliability/` | `recurred-in` from claims to trials | withdrawing an occurrence |

If a layer can reach a published metric view or the E axis without passing through a claim,
the meaning has leaked back into code — which is the condition this ontology exists to remove.
Under the harness-2.x scoring profile the Q, C and G axes and readiness are the pinned harness
numbers and trace to their components instead (01 §2 "Scope of the claim-trace rules";
`eio.profile.scoring-boundary`). A claim cap (`eio.cap.proven-critical-breach`) names the
deterministically resolved claim that caused it; a gate cap (`eio.cap.blocked-run`, 3@) names
its unmet gate.

## Stack and governed lifecycle

The reference operating model is represented in
`assurance/system-of-record.yaml`:

```text
01 Agent infrastructure       (customer environment)
        ↓ local evidence
02 Open-source harness        (customer environment)
        ↓ canonical claims
03 Behavioural intelligence  ┐
04 Governance + compliance   ├ governance platform
05 Assurance + system record ┘

Register → AI-BOM → Evaluate → Comply → Govern → Release → Assure
```

The public ontology also materializes a compliance crosswalk: 30 framework views,
165 controls, 406 control-to-risk links, and 434 control-to-predicate links, which together
reach 36 of the 58 predicates. Each control inherits the evidence contracts of its mapped
predicates. These are evidence-relevance views: legal applicability, organizational
conformity, attestation, and certification require separate qualified review.

## `core/flow.yaml` — the stage contract

Thirteen stages from `qualify` to `report`, each declaring what it may consume, what it must
produce, which resolvers it may use, and the invariants it must not break. Two rules carry
most of the weight:

* **Only four stages may write a claim.** A planner that can write claims can decide the
  answer before the agent has spoken.
* **Every stage must produce something observable.** A stage with no output cannot be
  audited, and an unauditable stage is where a capability wired to nothing hides;
  `eio.flow.dispatch-census` exists to make silence explain itself.

## Public and private

The bundled `0.6.0` manifest imports **public** modules only. Private-pack support is
not established by this candidate. The public modules use `license: Apache-2.0` and `eio.` ids;
the historical 0.4.0 validator rejected modules with another licence or id prefix.

The proposed private-pack profile from `01-EIO-core.md` §3.3
(`PRIVATE_EXTENSIBLE_SECTIONS`) specifies this section boundary:

| A private module may declare only | A private module may never declare |
|---|---|
| `eio`, `imports`, `concepts`, `domain`, `mappings`, `templates`, `profiles` | `predicates`, `decision_states`, `relations`, `evidence_types`, `source_types`, `resolvers`, `explanation_templates`, `scoring`, `reliability`, `flow`, `governance`, `context_criteria`, `frameworks`, `controls`, `domain_links`, `context_links` |

The boundary keeps pass/fail semantics in the open ontology, so results produced with a private
pack stay comparable and auditable against it.

## Validation

From a clone of the EIO-Agents repository:

```bash
python tools/eio_gates.py --examples tests/data/native
python tools/eio_gates.py --selftest --examples tests/data/native
python tools/eio_digests.py
python -m pytest -q tests/test_native.py tests/test_native_scored_end_to_end.py
```

`tools/eio_gates.py` runs the build gates for the bundled 0.6.0 ontology, among them exact import pins and an
acyclic import graph (IMPORT_VERSION), import closure of every referenced id (IMPORT_CLOSURE),
id uniqueness over every section (ID_UNIQUENESS), resolver order (PREDICATE_RESOLVER_ORDER),
the witness table (WITNESS_TABLE), declared facts (FACTS_DECLARED), severity or a declared
reason on every predicate (SEVERITY_DECLARED), unique normalised domain aliases (ALIAS_UNIQUE)
and reproducible release digests (MANIFEST_AND_DIGESTS); `--selftest` checks their negative
vectors. `tools/eio_digests.py` checks that `RELEASE-DIGESTS.json` reproduces. The historical
0.4.0 entry in `CHANGELOG.md` lists its gates and issue closures; gates that read ProofAgent
Harness registries (for example POLARITY and LEGACY_METRICS) are not part of this reference library.

Together the gates check JSON Schema conformance, stable and unique ids, imports, relation
references, predicate contracts, compliance views, flow stages and explanation templates.

## Namespace and compatibility

Canonical IDs use the `eio.` prefix. Modules use names such as
`eio.risk.data-handling`; concepts and predicates use names such as
`eio.risk.unauthorized-disclosure` and
`eio.predicate.disclosure-without-entitlement`.

While the release major version is 0, removing or changing the meaning of a public ID is a
breaking change that bumps the MINOR version of the module and of the release, and it is listed
under BREAKING in `CHANGELOG.md`. Adding a backward-compatible concept, mapping, or optional field
bumps the minor version. Text or metadata corrections that do not change decisions bump the patch
version. Import pins are exact. The release digests (`module_sha256` per module, `ontology_sha256`,
`ontology_digest`) are published in `RELEASE-DIGESTS.json`.

The historical 0.4.0 release included `mappings/legacy.yaml` for ProofAgent Harness check
vocabulary. The current 0.6.0 manifest does not import that producer-specific module; historical
report conversion remains with the matching adapter and pinned release. See
[`docs/versioning.md`](../../../../docs/versioning.md) for the current version lines.

## Contribution quality gate

A new predicate must include:

- formal applicability and pass/fail semantics;
- an evidence contract and explicit unknown policy;
- an ordered resolver strategy;
- `severity_source` NONE with a reason unless an obligation targets it;
- at least one positive, negative, not-applicable, and insufficient-evidence reference
  case;
- a reproducible test template or a documented reason why it is observation-only;
- risk, remediation, and metric mappings;
- domain and framework mappings only when evidence supports them.
