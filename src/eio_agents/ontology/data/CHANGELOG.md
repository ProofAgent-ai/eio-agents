# EIO changelog

## 0.5.0-draft.1 — unpublished candidate

The bundled manifest identifies this draft release as `0.5.0-draft.1`. Its
`ontology_sha256` is
`sha256:4cbe3a904af9038eb3ecb79f8d309bde11f1a2b9967684c75f4cd591f7f05a2c`
and its `ontology_digest` is `4cbe3a904af9038e`, as pinned in
[`RELEASE-DIGESTS.json`](RELEASE-DIGESTS.json). The current native record format is PER
`2.0.0-rc3-draft`. This entry records the candidate state; it does not approve the public
identifiers, a package version, or publication. Owner decision #22 still holds publication.

The 0.4.0 entry below records the earlier release candidate and its historical digests. Its
module inventory and gate counts do not describe the current draft.

## 0.4.0 — 2026-09-27

Release `0.4.0` of the Evaluation Intelligence Ontology (manifest `eio.manifest.public` 0.4.0).

| Digest | Value |
|---|---|
| `ontology_sha256` | `sha256:ed5389af5235e4b8cfe49953e09a795d209bd91501eda6e0aff38bcb7f64fe1b` |
| `ontology_digest` | `ed5389af5235e4b8` |
| `module_sha256` of `eio.manifest.public` | `sha256:3e0cace879c603c064d16d6f4a30c3a8e623c2129a2c4f783bb9494483bb1893` |

`module_sha256` = `"sha256:" + hex(sha256(raw module file bytes))`; `ontology_sha256` = `"sha256:" + hex(sha256(JCS({module_id: module_sha256})))` over every module the manifest imports plus the manifest; `ontology_digest` = the first 16 hex characters of `ontology_sha256` (`eio.profile.ontology-digest`). Every value, per module, is in `RELEASE-DIGESTS.json`; the build gates recompute them (MANIFEST_AND_DIGESTS).

### Versioning rule (normative, EIO-1)

While the release major version is 0, a breaking change (a change of meaning) bumps the MINOR version of the changed module and of the release and is listed under BREAKING below; an additive change bumps PATCH or MINOR; a text or comment change bumps PATCH. Import pins are exact (no ranges). This release is breaking relative to 0.3.0: every changed module moved from 0.1.0 to 0.2.0 (`eio.mapping.frameworks` from 0.2.0 to 0.3.0), and `eio.template.why` 0.1.0 is new.

A predicate's version identifies its proposition: `applicable_when`, `satisfied_when`, `violated_when`, `polarity`, `unknown_policy`, `evidence_contract` and `subsumes` (`eio.profile.public-release` versioning). None of these changed for any predicate, so all 58 predicates stay `1.0.0` and every claim id and finding id computed under 0.3.0 is unchanged (for example FIN_3 claim `cf5d7d77a674dc3d58f2`, finding `b182e5576187159d0015`). The 0.4.0 edits to predicate resolver lists (order EIO-19, additions EIO-403, removal of `threshold` EIO-31) change the resolution strategy, not the proposition, and the new member `applicability_inputs` (EIO-227) names who provides a fact that `applicable_when` already reads.

### BREAKING

- `eio.core.entities` 0.2.0: `eio.entity.evaluation-claim` has parent `eio.entity.thing` (was `eio.entity.claim`, which is agent content). (EIO-7)
- `eio.core.relations` 0.2.0: `eio.relation.has-purpose` has range `eio.entity.policy-rule` (was `eio.entity.claim`). (EIO-7)
- `eio.core.relations` 0.2.0: relations `raises-impact-of`, `aggregates-to`, `recurred-in`, `evaluated-by` and `gates` moved, ids unchanged, to `eio.governance.gates`, `eio.scoring.axes`, `eio.reliability.ledgers`, `eio.context.criteria` and `eio.scoring.axes`. (EIO-6)
- Relations gain characteristics from the 01 §5.2 P column (`precedes` irreflexive; `issued-by`, `owned-by`, `changes`, `resolved-by`, `recorded-in` functional; `performs`, `produced` inverse-functional) and a `cardinality` on every relation. (EIO-9)
- Predicate resolver references: `threshold` removed from the schema and from `untrusted-instruction-execution` and `disclosure-without-entitlement`. (EIO-31)
- Governance: `escalates_tier` removed from every autonomy level (EIO-245); the tier-conditioned `impact_escalation` rules (tier high, tier elevated) removed because the tier's `obligation_floor` already yields at least as much (EIO-57); autonomy labels quoted (0.3.0 parsed `l0` and `l2` labels into spurious keys).
- Facts: `policy_defaults.applies_when` and test-template `requires` use canonical fact ids; the retired spellings are fact `aliases` (`accepts_external_content`, `has_side_effecting_tools`, `has_tools`, `reads_repository_content`, `legal_advice`, `eligibility_decisions`, `adverse_outcome`, `disruption_event`, `takes_consequential_actions`). (EIO-211)
- Domain aliases are normalised tokens: `customer_service` became `customer-service`; `triage` moved from `eio.domain.medical-devices` to `eio.domain.healthcare-operations`. (EIO-24)
- Six shared domain concepts moved into `eio.core.taxonomies`, ids unchanged: `eio.action.eligibility-decision`, `eio.role.clinician`, `eio.data.clinical-record`, `eio.action.clinical-decision`, `eio.action.payment-transfer`, `eio.action.account-change`. (EIO-209)
- `policy_defaults` rules are quoted strings; 12 of 38 rules had been truncated at their first comma. (EIO-207)
- `ontology_digest` is the first 16 hex of `ontology_sha256` (0.3.0: 16 hex of a hash over truncated per-module digests with Python separators). (EIO-3)
- `evaluation-claim.schema.json`: `id`, `run_id`, `episode_id`, `predicate_version`, `turn_indices` (1-based), `provenance.module_hash` and `provenance.plan_hash` have patterns; the 0.3.0 projection shape no longer validates. (EIO-27)
- `eio.profile.context-scoring`: the checklist score is no longer rounded to two places; the axis value is quantized once (EIO-233). The same inputs give Q 77.3, not 77.4.
- `mappings[]` rows of `legacy.check.*` sources require `polarity` and `legacy_metrics`. (EIO-28, EIO-221)

### Added

- `source_types` section in `eio.core.evidence` (10 values) with `may_witness` and `witness_requires`; `compatible_source_types` on every evidence type; profiles `eio.profile.witness-rule`, `eio.profile.resolver-order`, `eio.profile.contract-defaults`, `eio.profile.resolver-authority`. (EIO-10, EIO-11, EIO-18, EIO-19, EIO-48)
- `eio.core.decisions`: observation semantics in `eio.profile.decision-policy` and the proof rule `eio.profile.proof-status`, whose seven test vectors (three FIN_3, four synthetic) cover exact, native and `narrower` claims with and without recurrence. (EIO-33, EIO-34)
- `eio.template.why` 0.1.0 (`templates/why.yaml`): the 36-template explanation catalogue and `eio.profile.why-rendering`, whose `param_inputs` and `params_rule` fix the stored input of every param type (params store inputs, never rendered text). (EIO-49)
- `eio.reliability.ledgers`: `recurrence_bands` (the four recurrence bands with rank, rule and test vectors) and the weakest-band finding rule on `eio.ledger.recurrence`.
- `eio.governance.gates`: `governance.facts` (126 canonical facts, including `prohibited_use_case`, the declared fact of `eio.profile.resolver-authority`), `governance.runtime_crosswalk`, profiles `eio.profile.impact-escalation`, `eio.profile.coverage-evaluation`, `eio.profile.domain-resolution`, `eio.profile.framework-selection`. (EIO-24, EIO-25, EIO-57, EIO-211, EIO-214, EIO-301)
- `eio.scoring.axes`: `legacy_profiles` and `eio.profile.legacy-scoring-harness-2x`; named evidence-fraction definitions on `eio.floor.release-evidence`; floor `eio.floor.critical-metric`; EIO (3@) `claim_weights`. (EIO-219, EIO-220, EIO-222, PER-415)
- `eio.mapping.legacy`: columns `polarity`, `legacy_metrics`, `resolver`, `implemented`, `remediation`, `applicability_embedded`; profiles `eio.profile.legacy-crosswalk`, `eio.profile.polarity-derivation`, `eio.profile.mapping-relations`. (EIO-28, EIO-33, EIO-35, EIO-221, EIO-231, EIO-236, EIO-238)
- `eio.core.flow`: `eio.profile.coverage-census` and stage records. (EIO-238, EIO-22)
- Concepts `eio.artifact.policy`, `eio.role.regulator`, `eio.risk.evaluation-integrity`. (EIO-5, EIO-208, EIO-202)
- `eio.profile.assurance-freshness` (PER-209), `eio.profile.ontology-digest` (EIO-3), `RELEASE-DIGESTS.json`, this changelog.
- `eio.profile.witness-rule`: the `stored_flag` rule of a `TOOL_RESULT` ref and six stored-flag test vectors (`citing_claims`); `eio.profile.contract-defaults`: `direction` (which contract governs `APPLICABLE_FAIL`, `APPLICABLE_PASS` and `NOT_APPLICABLE`).
- `eio.cap.proven-critical-breach`: `requires_witnessing_anchored_ref: true` with `witnessing_required_in: [release_recommendation, readiness]` (01 §6.3 W1).
- `governance.gates[].test_vectors`: inputs and the expected `met` of every gate's evaluation rule (02 §5.5), FIN_3 values included.
- `schemas/eio-context-0.4.0.jsonld`: the JSON-LD `@context` of 01 §11.2, shipped and pinned in `RELEASE-DIGESTS.json` `files` (01 §11.4).

### Module versions

| Module | File | 0.3.0 | 0.4.0 | module_sha256 (prefix) |
|---|---|---|---|---|
| `eio.assurance.system-of-record` | `assurance/system-of-record.yaml` | 0.1.0 | 0.2.0 | `sha256:ee9d3cac66bf22ef…` |
| `eio.compliance.frameworks` | `compliance/frameworks.yaml` | 0.1.0 | 0.2.0 | `sha256:894820ddd2b30118…` |
| `eio.context.criteria` | `context/criteria.yaml` | 0.1.0 | 0.2.0 | `sha256:de9537ce0da4711b…` |
| `eio.core.decisions` | `core/decisions.yaml` | 0.1.0 | 0.2.0 | `sha256:09ac9f43460325fc…` |
| `eio.core.entities` | `core/entities.yaml` | 0.1.0 | 0.2.0 | `sha256:5453db046c8a7035…` |
| `eio.core.evidence` | `core/evidence.yaml` | 0.1.0 | 0.2.0 | `sha256:65af37c12acdc847…` |
| `eio.core.flow` | `core/flow.yaml` | 0.1.0 | 0.2.0 | `sha256:b9b70065d8c2ba9c…` |
| `eio.core.relations` | `core/relations.yaml` | 0.1.0 | 0.2.0 | `sha256:c349cf8251e870c1…` |
| `eio.core.taxonomies` | `core/taxonomies.yaml` | 0.1.0 | 0.2.0 | `sha256:f6dddd35fb93d921…` |
| `eio.domain.aviation-airline` | `domains/aviation-airline.yaml` | 0.1.0 | 0.2.0 | `sha256:2896a0b25fee97f3…` |
| `eio.domain.customer-support` | `domains/customer-support.yaml` | 0.1.0 | 0.2.0 | `sha256:1e743a7c8d912da5…` |
| `eio.domain.energy-utilities` | `domains/energy-utilities.yaml` | 0.1.0 | 0.2.0 | `sha256:c77ecd280738a899…` |
| `eio.domain.financial-services` | `domains/financial-services.yaml` | 0.1.0 | 0.2.0 | `sha256:8f721e0a3ccb644b…` |
| `eio.domain.generic-agent` | `domains/generic-agent.yaml` | 0.1.0 | 0.2.0 | `sha256:4d169bda04b0b5ff…` |
| `eio.domain.healthcare-operations` | `domains/healthcare-operations.yaml` | 0.1.0 | 0.2.0 | `sha256:082840f651e13dde…` |
| `eio.domain.hr-employment` | `domains/hr-employment.yaml` | 0.1.0 | 0.2.0 | `sha256:14173ac95b255084…` |
| `eio.domain.legal-public-sector` | `domains/legal-public-sector.yaml` | 0.1.0 | 0.2.0 | `sha256:65aaec5fe62e517d…` |
| `eio.domain.medical-devices` | `domains/medical-devices.yaml` | 0.1.0 | 0.2.0 | `sha256:e108e973b1a02d82…` |
| `eio.domain.payments-cardholder` | `domains/payments-cardholder.yaml` | 0.1.0 | 0.2.0 | `sha256:ed0ee9727ca28ee4…` |
| `eio.domain.software-agents` | `domains/software-agents.yaml` | 0.1.0 | 0.2.0 | `sha256:99b0892aa0690158…` |
| `eio.governance.gates` | `governance/gates.yaml` | 0.1.0 | 0.2.0 | `sha256:d7aa60f2cca9bd68…` |
| `eio.graph.context-links` | `graph/context-links.yaml` | 0.1.0 | 0.2.0 | `sha256:b5ae98b02d2eba8c…` |
| `eio.graph.domain-links` | `graph/domain-links.yaml` | 0.1.0 | 0.2.0 | `sha256:993fb0086b4ff673…` |
| `eio.manifest.public` | `manifest.yaml` | 0.3.0 | 0.4.0 | `sha256:3e0cace879c603c0…` |
| `eio.mapping.frameworks` | `mappings/frameworks.yaml` | 0.2.0 | 0.3.0 | `sha256:6c472256d3c60c4e…` |
| `eio.mapping.legacy` | `mappings/legacy.yaml` | 0.1.0 | 0.2.0 | `sha256:32948ca67ebb86e1…` |
| `eio.mapping.metrics` | `mappings/metrics.yaml` | 0.1.0 | 0.2.0 | `sha256:33aff2721ac2dd54…` |
| `eio.mapping.traps` | `mappings/traps.yaml` | 0.1.0 | 0.2.0 | `sha256:2ecfdbd64903b13c…` |
| `eio.reliability.ledgers` | `reliability/ledgers.yaml` | 0.1.0 | 0.2.0 | `sha256:f39827ad904a0df8…` |
| `eio.risk.action-safety` | `risks/action-safety.yaml` | 0.1.0 | 0.2.0 | `sha256:69f4da6399ccf59b…` |
| `eio.risk.catalog` | `risks/catalog.yaml` | 0.1.0 | 0.2.0 | `sha256:d73d1416a587f478…` |
| `eio.risk.content-code-safety` | `risks/content-code-safety.yaml` | 0.1.0 | 0.2.0 | `sha256:6b432a282f3588ca…` |
| `eio.risk.context-trust` | `risks/context-trust.yaml` | 0.1.0 | 0.2.0 | `sha256:fe08729659d8f527…` |
| `eio.risk.data-handling` | `risks/data-handling.yaml` | 0.1.0 | 0.2.0 | `sha256:698f0a3b2b1deed1…` |
| `eio.risk.evaluator-reliability` | `risks/evaluator-reliability.yaml` | 0.1.0 | 0.2.0 | `sha256:d13d2620d7dbb309…` |
| `eio.risk.fairness-rights` | `risks/fairness-rights.yaml` | 0.1.0 | 0.2.0 | `sha256:9f9c6b68fbe75f76…` |
| `eio.risk.grounding` | `risks/grounding.yaml` | 0.1.0 | 0.2.0 | `sha256:1313997c05f216de…` |
| `eio.risk.safeguards` | `risks/safeguards.yaml` | 0.1.0 | 0.2.0 | `sha256:d0e14298cefdb957…` |
| `eio.scoring.axes` | `scoring/axes.yaml` | 0.1.0 | 0.2.0 | `sha256:0165a7c9e758acb0…` |
| `eio.template.core` | `templates/core.yaml` | 0.1.0 | 0.2.0 | `sha256:fcc19efde0cc54b9…` |
| `eio.template.why` | `templates/why.yaml` | new | 0.1.0 | `sha256:73c8d01af341cf8f…` |

### Build gates

`tools/eio_gates.py` (shipped in the specification package under `tools/`, and ported to the reference library) runs these gates; all pass on this release:

| Gate | Checks | Closes |
|---|---|---|
| YAML_PARSE | 41 modules loaded with duplicate-key rejection | every module parses (duplicate keys rejected) |
| SCHEMA_SELF | every schemas/*.json is a valid JSON Schema 2020-12 | schemas are valid 2020-12 |
| MODULE_SCHEMA | 41 modules validated against module.schema.json | modules validate |
| REFERENCE_CASES | 45 reference cases valid | reference cases validate |
| ID_UNIQUENESS | 867 item ids across every section; 11 domain module/domain pairs exempt | EIO-58 |
| IMPORT_VERSION | every pin names an existing module at exactly its version; graph acyclic | EIO-2 |
| REFERENCE_RESOLVES | 3333 id-valued references scanned (parents, relations, predicates, controls, obligations, profiles) | EIO-208 |
| IMPORT_CLOSURE | every referenced id is declared in the module or its transitive imports (release-scoped: module pointers, governance.gates[].evaluated_at) | EIO-6, EIO-209 |
| DANGLING_FLOW_CONCEPT | flow consumes/produces and criteria evaluates resolve to declared concepts (EIO-5) | EIO-5 |
| DANGLING_PARENT | every parent of 264 concepts resolves (EIO-208); every other cross-module reference is REFERENCE_RESOLVES | EIO-208 |
| RELATIONS | 44 relations: endpoints declared, cardinality populated and consistent with functional/inverse-functional (EIO-9) | EIO-9 |
| RELATION_INVERSE | 0 relations declare an inverse; each names an existing relation that declares it back | EIO-9 |
| PREDICATE_CONTRACTS | 58 predicates: states, resolvers, evidence kinds, risk/safeguard, subsumes, obligations and templates resolve | predicate contracts |
| PREDICATE_RESOLVER_ORDER | no deterministic resolver (other than graph-rule) follows a semantic one in any predicate's ordered resolver list | EIO-19 |
| RESOLVER_REF_SHAPE | resolver references are a bare id or {id, relation} | EIO-31 |
| SEVERITY_DECLARED | 43 predicates carry obligation severity; 15 declare severity_source NONE with a reason | EIO-36 |
| FACTS_DECLARED | 126 canonical facts; 146 required_when/applies_when/requires/escalation maps use declared canonical fact ids only | EIO-211 |
| ALIAS_UNIQUE | aliases normalised and unique; EIO-24 token and golden resolution tests; EXAM_A_maintree_checker.raw.json: ['education', 'support'] -> ['customer-support', 'generic-agent'] | EIO-24 |
| POLICY_DEFAULTS_SHAPE | 38 policy defaults have exactly {rule, applies_when} (EIO-207) | EIO-207 |
| SPURIOUS_KEY | no mapping key parsed from an unquoted comma (EIO-207 class of defect) | EIO-207 |
| UNMAPPED_CHECKS | unmapped_checks == []; 48 legacy check rows for 48 checks.yaml checks | unmapped_checks == [] |
| POLARITY | every legacy check row declares polarity equal to checks.yaml (40 negative, 8 positive) | EIO-28 |
| LEGACY_METRICS | every legacy check row carries legacy_metrics equal to checks.yaml metrics (the 2.x membership, EIO-221) | EIO-221 |
| LEGACY_RESOLVER | every code/gated row names a deterministic resolver listed by its predicate; llm rows name none (EIO-33, EIO-403) | EIO-33, EIO-403 |
| LEGACY_REGISTRY | not-implemented registry ['paired_outcome_diverged']; applicability_embedded ['invented_rule_or_deadline']; checks_version 1756167a5e05; polarity derivation table | EIO-35, EIO-236, EIO-238 |
| POLARITY_TV9 | TV-9: answered_legitimate_task observed=false -> APPLICABLE_FAIL; kept_professional_tone observed=true -> APPLICABLE_PASS; 7 profile vectors re-derived; observation override on a positive row exercised by ['turn_had_perm | EIO-28 |
| METRIC_LEGACY_KEY | legacy keys: hallucination_resistance->eio.metric.hallucination-resistance, instruction_following->eio.metric.instruction-following, manipulation_resistance->eio.metric.manipulation-resistance, safety->eio.metric.safety, | EIO-241 |
| EVALUATION_INTEGRITY | 6 evaluator predicates under eio.risk.evaluation-integrity; none feeds an agent metric or E | EIO-202 |
| WITNESS_TABLE | 10 source types; W = ['AGENT_ANSWER', 'AGENT_TOOL_CALL', 'HUMAN_REVIEW', 'STATE_LEDGER', 'TOOL_RESULT']; 15 built-in witness vectors; 11 profile vectors (6 stored-flag); FIN_3 shadow count 46 | EIO-10, EIO-11 |
| FLOW | 13 stages; 4 claim-writing stages; graph-rule at resolve-deterministic; census causes in order ['UNREACHABLE', 'NOT_IMPLEMENTED', 'NEVER_SELECTED', 'PRECONDITION_ABSENT', 'INCOMPLETE_COVERAGE'] | EIO-20, EIO-216, EIO-238 |
| EXPLANATION_TEMPLATES | 36 templates in eio.template.why; placeholders == params; <= 600 code points; no per-check literals; param_inputs for every type; 184 stored explanations of 3 example records store inputs, never rendered text | EIO-49 |
| CONTEXT_CRITERIA | checklist controls carry the exact harness labels; context-scoring profile fixes rounding, searched set, searched-text hash and matching | EIO-233, EIO-404 |
| COMPLIANCE | 30 frameworks, 165 controls, 434 control->predicate links; ordered six-status materialization rules | EIO-217 |
| GATE_EVALUATED_AT | 7 gates bind to a flow stage of the release (release-scoped reference) | EIO-6 |
| GOVERNANCE | no escalates_tier; no escalation rule under a HARD_BLOCK-floor tier; every gate evaluated_at is a flow stage; runtime crosswalk complete over governance_profile.USE_CASES | EIO-57, EIO-214, EIO-245 |
| NORMATIVE_PROFILES | 20 normative profiles present in their modules with the decisive keys of EIO-33/34/48/57, PER-13/209/415; eio.cap.blocked-run applies under 3@ only, shown until M4; proof-status vectors re-derived (rec | EIO-33, EIO-34, EIO-48, EIO-57, PER-13, PER-209, PER-415 |
| NAMESPACE | 41 namespaces unique, absolute https, ending in '#'; 40 unchanged from the baseline; no term IRI built on a namespace | 01 §3.2 (namespace rules) |
| PER_IDS_OWNED | 9 per.lim/per.caveat ids named in eio/**, none in core/ or risks/, all listed by their owner (04 §5.13: 48 limitation ids; 03 §7.13: 2 caveat ids) | 01 §1.3 R5 (PER ids named by EIO data) |
| CAP_WITNESS | eio.cap.proven-critical-breach: deterministic resolver class; witnessing anchored ref required in the release recommendation and the readiness index | 01 §6.3 W1 (cap needs a witnessing anchored ref) |
| GATE_VECTORS | 7 gates; 28 test vectors evaluated by the 02 §5.5 rules (5 FIN_3 record vectors compared with the reference record) | 02 §5.5 (gate evaluation rules) |
| CLAIM_SCHEMA_GOLDENS | 259 claims of 3 example PER files validate against evaluation-claim.schema.json; 0.3.0 projection shape rejected | EIO-27 |
| MANIFEST_AND_DIGESTS | release 0.4.0; 41 modules; ontology_sha256 sha256:ed5389af5235e4b8cfe49953e09a795d209bd91501eda6e0aff38bcb7f64fe1b; ontology_digest ed5389af5235e4b8 | EIO-3, EIO-201 |
| VERSION_BUMP | 41 modules changed/added: eio.assurance.system-of-record 0.1.0->0.2.0; eio.compliance.frameworks 0.1.0->0.2.0; eio.context.criteria 0.1.0->0.2.0; eio.core.decisions 0.1.0->0.2.0; eio.core.entities 0.1.0->0.2.0; eio.core. | EIO-1 |
| CHANGELOG | 55 keys recorded as 'Resolved: <key>'; no open-issue marker in eio/**; BREAKING section and implementation-notes appendix present | EIO-1 (this file) |

`tools/eio_gates.py --selftest` runs 45 negative vectors: each copies the release, injects one defect (a duplicate id, a stale pin, an import cycle, a missing import, a dangling parent, a semantic-first resolver list, a `threshold`, a missing severity reason, an undeclared fact, a shared alias, an unquoted policy default, a wrong polarity or metric membership, a missing legacy resolver, a witnessing `HARNESS_SIGNAL`, a bad template placeholder or a per-check literal, a flow without graph-rule, a redundant tier rule, an inconsistent cardinality, a dangling inverse, an edited module under a stale manifest, an open-issue marker, a too-strict claim schema, a wrong polarity-derivation vector, a params rule that admits rendered text, a blocked-run cap without its 3@ scope, an undeclared declared fact, a wrong recurrence-band vector, an incomplete prohibited use-case list, a stored-flag or gate vector error, a shared or malformed namespace, an unowned PER limitation id, a cap without its witness requirement, a recurrence ledger that gates the block of an exact claim, a wrong proof-status vector, an unscoped claim-trace or gate-cap invariant, an unscoped governance score clause) and requires the named gate to fail. All 45 are caught.

### Inventory 0.4.0

| Item | Count | 0.3.0 |
|---|---:|---:|
| Modules (manifest included) | 41 | 40 |
| Concepts | 264 (risk 49, action 48, entity 46, data-class 40, role 35, event 12, metric 11, channel 7, safeguard 7, policy 5, state 3, control 1) | 261 |
| Relations | 44 | 44 |
| Predicates | 58 (all 1.0.0) | 58 |
| Resolvers / evidence types / source types / decision states | 11 / 11 / 10 / 7 | 11 / 11 / 0 / 7 |
| Coverage obligations | 126 | 126 |
| Canonical facts | 126 | 0 |
| Domain aliases | 107 | 96 |
| Explanation templates | 36 | 0 |
| Test templates / flow stages / context criteria | 16 / 13 / 7 | 16 / 13 / 7 |
| Frameworks / controls / control-predicate links | 30 / 165 / 434 | 30 / 165 / 434 |
| Profiles | 34 | 17 |

### Resolved

Each line closes an issue key of the 0.4.0 review; the normative rule now lives in the data named.

- Resolved: EIO-1 — 0.x versioning rule in `eio.profile.public-release` and README; every changed module bumped; this BREAKING list.
- Resolved: EIO-2 — exact import pins enforced by gate IMPORT_VERSION (acyclic graph included); the manifest pins every module with its `sha256`.
- Resolved: EIO-3 — `module_sha256` over raw bytes, `ontology_sha256` over JCS of the module map, `ontology_digest` = its first 16 hex (`eio.profile.ontology-digest`, `RELEASE-DIGESTS.json`).
- Resolved: EIO-5 — `eio.artifact.policy` declared in `eio.context.criteria` 0.2.0 with the policy-versus-knowledge rule; gate DANGLING_FLOW_CONCEPT.
- Resolved: EIO-6 — five relations moved to their endpoint modules; `eio.core.flow` imports governance, scoring, reliability and context; gate IMPORT_CLOSURE.
- Resolved: EIO-7 — `evaluation-claim` re-parented to `eio.entity.thing`; `has-purpose` range `eio.entity.policy-rule`.
- Resolved: EIO-9 — `cardinality`, `inverse` and `irreflexive` in `$defs.relation`; every relation populated; gates RELATIONS and RELATION_INVERSE.
- Resolved: EIO-10 — witness rule as data (`source_types`, `compatible_source_types`, `eio.profile.witness-rule`); gate WITNESS_TABLE (FIN_3 shadow count 46).
- Resolved: EIO-11 — 10 source types including `HUMAN_REVIEW` (admitted only on `HUMAN_SIGNOFF`); `source_types` is a schema section.
- Resolved: EIO-18 — `pass_contract` and `not_applicable_basis` with normative defaults (`eio.profile.contract-defaults`).
- Resolved: EIO-19 — ordered resolver lists (deterministic, semantic, then graph-rule / human-adjudication); 6 predicates reordered; the other predicates that list a semantic resolver first have no deterministic resolver besides graph-rule and already conform; gate PREDICATE_RESOLVER_ORDER.
- Resolved: EIO-20 — `eio.resolver.graph-rule` allowed at `eio.flow.resolve-deterministic`.
- Resolved: EIO-22 — no `chain_head` in any EIO module; stage records in `eio.profile.flow-invariants` (the STAGE_BINDING gate is declared by 01 §12.3).
- Resolved: EIO-24 — deterministic domain resolution (`eio.profile.domain-resolution`), alias additions and moves, gate ALIAS_UNIQUE with golden resolution tests.
- Resolved: EIO-25 — obligation evaluation (`eio.profile.coverage-evaluation`): `required` from declared facts, distinct scored cases, effective impact.
- Resolved: EIO-26 — census causes defined without `BY_DESIGN` (`eio.profile.coverage-census`).
- Resolved: EIO-27 — claim schema patterns; gate CLAIM_SCHEMA_GOLDENS over the example records.
- Resolved: EIO-28 — polarity column and `eio.profile.polarity-derivation`; gates POLARITY and POLARITY_TV9.
- Resolved: EIO-31 — `threshold` removed; gate RESOLVER_REF_SHAPE.
- Resolved: EIO-33 — `eio.profile.proof-status` (narrower proves only with recurrence CONFIRMED); `resolver` column on code and gated legacy rows.
- Resolved: EIO-34 — `observation_fail_is_violation: false` and the observation meaning of states in `eio.profile.decision-policy`; P09 and P45 declare `severity_source` NONE.
- Resolved: EIO-36 — every predicate is targeted by an obligation or declares `severity_source {kind: NONE, reason}` (15 predicates); finding-severity rule in `eio.profile.coverage-evaluation`; gate SEVERITY_DECLARED.
- Resolved: EIO-48 — rule RS6 in `eio.profile.resolver-authority`: a semantic-only claim is never PROVEN and at most yields REVIEW; only PROVEN claims or the declared fact `prohibited_use_case` yield BLOCK (six test vectors; gates NORMATIVE_PROFILES and FACTS_DECLARED).
- Resolved: EIO-49 — one normative catalogue, `eio.template.why`; no per-check literal (gate EXPLANATION_TEMPLATES).
- Resolved: EIO-51 — `eio.entity.episode` is one trap binding; `episode_id` recipe.
- Resolved: EIO-57 — single-pass escalation plus tier floor (`eio.profile.impact-escalation`); redundant tier rules removed.
- Resolved: EIO-58 — gate ID_UNIQUENESS over every `id` of every section (and ID_GRAMMAR).
- Resolved: EIO-201 — manifest and release 0.4.0; new and changed modules imported at their new versions with `sha256`.
- Resolved: EIO-202 — root `eio.risk.evaluation-integrity`; evaluator predicates excluded from agent metrics and E (`eio.profile.metric-aggregation-v1`); gate EVALUATION_INTEGRITY.
- Resolved: EIO-207 — quoted policy defaults; `{rule, applies_when}` shape; gates POLICY_DEFAULTS_SHAPE and SPURIOUS_KEY.
- Resolved: EIO-208 — `eio.role.regulator` in `eio.core.taxonomies`; gates DANGLING_PARENT and REFERENCE_RESOLVES.
- Resolved: EIO-209 — six shared concepts in `eio.core.taxonomies`; IMPORT_CLOSURE passes.
- Resolved: EIO-211 — `governance.facts` (126 facts with type, aliases, intake keys, archive source; `multi_turn` from `/mode`, `consequential_actions` from `intake.takes_consequential_actions`); gate FACTS_DECLARED.
- Resolved: EIO-214 — `governance.runtime_crosswalk` (use cases, domain hints, tiers, tier labels, regions, autonomy, frameworks); SR 11-7 yields `per.lim.frameworks.not_in_eio`.
- Resolved: EIO-216 — `core/flow.yaml` says four claim-writing stages and `not_tested`.
- Resolved: EIO-217 — ordered materialization rules and `proxy_only` in `eio.profile.compliance-materialization`.
- Resolved: EIO-219 — named fractions `harness-2.x` and `eio-3` on `eio.floor.release-evidence`; C and G have no EIO 0.4.0 formula (the pinned scoring function under `harness-2.x`).
- Resolved: EIO-220 — `eio.profile.legacy-scoring-harness-2x` declares the 2.x constants (epsilon 1.0, ceiling 49.0, weights, axis keys, Q x E coupling).
- Resolved: EIO-221 — `legacy_metrics` is the 2.x membership; the EIO edges are the 3@ view.
- Resolved: EIO-222 — 2.x trap-severity weights and 3@ obligation-severity `claim_weights` declared.
- Resolved: EIO-227 — `permissible-task-present` is an applicability input of `permissible-task-completed` (`applicability_inputs`).
- Resolved: EIO-231 — mapping-relation definitions in the schema and in `eio.profile.mapping-relations`.
- Resolved: EIO-233 — rounding, searched set, searched-text hash and lexical matching fixed in `eio.profile.context-scoring`.
- Resolved: EIO-236 — `checks_version` 1756167a5e05, fail-closed `UNKNOWN_CHECK`, mismatch limitation (`eio.profile.legacy-crosswalk`).
- Resolved: EIO-238 — five ordered census causes and the not-implemented registry (`implemented: false`, seed `paired_outcome_diverged`).
- Resolved: EIO-241 — `legacy_key` on every metric concept; gate METRIC_LEGACY_KEY.
- Resolved: EIO-242 — subsumption grouping scope and claim equivalence in `eio.profile.metric-aggregation-v1`.
- Resolved: EIO-245 — `escalates_tier` removed.
- Resolved: EIO-246 — optional `safeguard` in `evaluation-claim.schema.json`.
- Resolved: EIO-301 — `eio.profile.framework-selection` (candidates, category rules, REVIEW_REQUIRED by default, schema-1 rule).
- Resolved: EIO-403 — resolvers added: arithmetic (excessive-data-disclosure), tool-receipt (required-human-oversight-absent, required-verification-requested), exact-span (untrusted-instruction-execution).
- Resolved: EIO-404 — `legacy_labels` on every checklist control; gate CONTEXT_CRITERIA compares them with the harness labels.
- Resolved: PER-13 — `eio.profile.resolver-authority` `block_requires: [proven_claim, declared_fact]`; cap `decisive_effect`.
- Resolved: PER-209 — freshness is a platform policy parameter with no default (`eio.profile.assurance-freshness`).
- Resolved: PER-415 — `eio.floor.critical-metric` (50 on 0-100; safety, hallucination resistance, tool use) under the `harness-2.x` profile.

Aliases closed with their primary key: EIO-21 (EIO-216), EIO-32 (EIO-48), EIO-39 (EIO-220), EIO-203 (EIO-34), EIO-204 and EIO-225 (EIO-36), EIO-210 (EIO-5), EIO-212 and EIO-213 (EIO-24), EIO-215 (EIO-57), EIO-230 (EIO-28), EIO-243 and EIO-401 (EIO-301), EIO-244 (EIO-19), EIO-402 (EIO-211), EIO-407 and EIO-408 (EIO-238), PER-11 and PER-201 (EIO-36), PER-12, PER-213, PER-420, PER-506 and PER-707 (EIO-49), PER-20 (EIO-33), PER-26 and PER-214 (EIO-219), PER-29 and PER-428 (EIO-238), PER-30 (EIO-214), PER-202 (EIO-24), PER-205 and PER-413 (EIO-221), PER-208 (EIO-25), PER-419 (EIO-222), PER-45 (EIO-11), PER-516 (EIO-301).

### Release facts

Facts of this release that the data above decides; 01, 02, 03, 04 and 05 state the same.

1. Predicate versions stay `1.0.0`: an edit of the resolver list or its order is a resolution-strategy change, not a proposition change (01 §3.5).
2. The `eio-3` evidence fraction over the EIO edges of `eio.metric.manipulation-resistance` is 41/75 = 0.5467 for FIN_3; 0.5181 is the same formula over the 2.x (`legacy_metrics`) membership.
3. The `multi_turn` fact reads the archive's top-level `/mode`; raw reports have no `metadata.mode`.
4. Golden domain resolution under the exact-alias rule: FIN_3 financial-services, customer-support, generic-agent; FIN_4 financial-services, generic-agent; FIN_1 financial-services, software-agents (alias `security`), generic-agent; MED_* healthcare-operations, generic-agent; HR_R3 hr-employment, generic-agent (alias `agentic`), software-agents, customer-support; EXAM_* customer-support, generic-agent.
5. `AGENT_SPAN` lists `JUROR_INFERENCE` as a compatible source type, so a juror citation is a compatible pair that never witnesses (`JUROR_INFERENCE` is outside W; 01 §6.3 W3).
6. The label table of `eio.why.claim.evidence_invalid@1` uses the PER 2.0.0 `invalid_because` enum (`cited_span_not_found`, `cited_span_not_agent`, `cited_span_other_turn`).
7. `handles_non_public_data` is true for data sensitivity `internal`, `confidential`, `pii`, `phi` and `pci` (internal data is non-public, `eio.data.internal`), false for `none`.
8. Explanation `params` store inputs, never rendered text (`eio.profile.why-rendering` `params_rule` and `param_inputs`); `eio.why.reliability@1` counts recurrence rows, observation rows included, not findings. `eio.template.why` is new in this release, so that text was corrected before its first publication and stays `@1`.
9. `eio.region.emea_other` keeps its underscore (the one grandfathered id; the PER schema admits it); no new id may use one.
10. IMPORT_CLOSURE has two release-scoped reference kinds: a module-id pointer and `governance.gates[].evaluated_at`.
11. The harness checklist for `injection-hardening` uses term lists and a searched set that differ from `requires_any` and `evaluates`; PER 2.0 carries the 2.x Q values (`eio.profile.context-scoring` legacy_values) and joins controls by `legacy_labels`.
12. The recurrence band vocabulary is EIO data: `eio.reliability.ledgers` `recurrence_bands` declares `CONFIRMED`, `INTERMITTENT`, `UNCONFIRMED` and `NOT_RETESTED`, each with its rank and rule; a finding takes the weakest band of its claims. The PER 2.0 `recurrence_band` enum is this list.
13. The declared fact of `eio.profile.resolver-authority` (`block_requires: [proven_claim, declared_fact]`) is the canonical fact `prohibited_use_case`: true when the intake `classification.tier` is `unacceptable` or the intake `use_case` is prohibited. The runtime tier `unacceptable` maps to `eio.tier.high`; the prohibition is carried by the fact.
14. `eio.cap.blocked-run` applies under semantics 3@ only and is shown only until M4: no PER 2.0 (semantics 2.x) record takes band F from it.
15. The `eio.profile.polarity-derivation` test vectors name the target predicate's polarity; `turn_had_permissible_request` (a positive row whose target is an observation predicate) with `observed: true` is `APPLICABLE_FAIL`, the case where the observation override changes the table result.
16. The witness flag is stored once per ref: a `TOOL_RESULT` ref's `can_prove_agent_behaviour` is true iff at least one claim cites it and every claim that cites it also cites the `AGENT_TOOL_CALL` ref of the same `turn_index` and `call_index`; a ref cited only by views is false (01 §6.3).
17. `evidence_contract` governs `APPLICABLE_FAIL` for every polarity; `pass_contract`, else `eio.profile.contract-defaults`, governs `APPLICABLE_PASS` (01 §6.5).
18. A gate's `required_when` is evaluated with the rule of `eio.profile.coverage-evaluation`: a named fact declared with another value makes the gate not required (`met: true`); otherwise a null fact gives `met: null` (02 §5.5).
19. Recurrence proves only a proxy: `eio.ledger.recurrence` makes a `narrower` (proxy) claim PROVEN when its band is `CONFIRMED` (`eio.profile.proof-status`) and leaves the deduction unaffected. An `exact` or native deterministic claim that cites a witnessing anchored ref is PROVEN without recurrence, so it may make the recommendation BLOCK with no reliability block (`NOT_RETESTED`).
20. The claim-trace and cap invariants of `eio.profile.scoring-boundary` are scoped (01 §2 "Scope of the claim-trace rules"): every published metric view and the E axis trace to the claims that produced them; under `harness-2.x` the Q, C and G axes and readiness are the pinned harness numbers and trace to their components. A claim cap (`eio.cap.proven-critical-breach`) traces to a deterministically resolved claim; a gate cap (`eio.cap.blocked-run`, 3@) names its unmet gate (the same split in the invariant of stage `eio.flow.score`). `eio.profile.governance-boundary` contributes no score through the profile, tier or escalation; the G axis is the scoring module's view.

## Implementation notes (non-normative)

Work the 0.4.0 rules require outside this data, and where it is done. Timing follows the roadmap steps of the reference
library (`docs/versioning.md` in the EIO-Agents repository). None of it changes a rule above.

| Item | Work | Where |
|---|---|---|
| EIO-2 | The loader rejects an absent import, a version that differs from its pin, and a file whose bytes do not hash to its manifest `sha256` | reference library |
| EIO-11, EIO-49 | `MODULE_SECTIONS` in the loader adds `source_types` and `explanation_templates`; the private-pack boundary keeps both protected | reference library |
| EIO-10 | The witness function is the library's, computed from `eio.profile.witness-rule`; the harness drops the `schemas.py` and `eio_runtime` witness sets | reference library; ProofAgent Harness |
| EIO-24 | The harness qualifier is replaced by the library resolver implementing `eio.profile.domain-resolution` | ProofAgent Harness |
| EIO-25 | Coverage evaluation implemented in the library from `eio.profile.coverage-evaluation`; the 0.3.0 `coverage_from_claims` is not ported | reference library |
| EIO-27 | The 0.3.0 claim projection (`claim_from_verdict`, empty `run_id`) is removed from the harness | ProofAgent Harness |
| EIO-28 | `eio._derive_state` and `CheckVerdict.resolved_state` are replaced by `eio.profile.polarity-derivation` | ProofAgent Harness |
| EIO-22, EIO-26 | The harness emits instrumented stage records and computes the dispatch census from claims and scope | ProofAgent Harness |
| EIO-29 | The harness evaluates declared `applicable_when` deterministically, emits the premise as a `permissible-task-present` claim, and never gates `refused_clearly` on it | ProofAgent Harness |
| EIO-35 | The harness splits questions that embed applicability into an applicability ballot and a violation ballot | ProofAgent Harness |
| EIO-59 | Archive schema 2 carries `state` on every verdict | ProofAgent Harness |
| EIO-36 | Generic obligations for `guardrail-circumvented`, `required-workflow-step-absent`, `content-materially-enables-defined-harm` and `agent-directed-abuse`, after a stored-run replay (they change scores) | EIO data, with compliance review |
| EIO-48 | Whether `semantic_only_max_effect` may be BLOCK for a harness LLM that passes qualification with `eio.gate.evaluator-calibrated` met is decided after the qualification (EIO 0.5.0 at the earliest) | EIO data (a normative change) |
| EIO-229 | Floors (per-predicate precision, recall, agreement) for `eio.gate.evaluator-calibrated`, from the harness-LLM qualification | EIO data |
| EIO-219, EIO-220, EIO-222 | After a stored-run replay: one constant set, the `eio-3` fraction, C and G formulas and the 3@ weights become decisive | EIO data |
| EIO-221 | After a replay, `checks.yaml` metric membership is generated from the EIO metric edges | ProofAgent Harness |
| EIO-236 | A crosswalk for the main-tree 46-check vocabulary | ProofAgent Harness |
| EIO-233 | The harness checklist searches exactly the `evaluates` artifacts with the `requires_any` terms and records `searched_text_sha256`; the injection-hardening term lists are aligned after a replay | ProofAgent Harness |
| PER-209 | The system of record declares and applies its freshness policy | system-of-record implementer |
| Build gates | `tools/eio_gates.py` is ported into the reference library's test suite | reference library |
