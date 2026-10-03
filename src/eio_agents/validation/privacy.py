"""The verifier's closed record-field table (owner decisions #31 and #32, step L3s): the twin of the converter's table
(`eio_agents.per.privacy`), written and read here independently (contract P3: no converter import; parity:
tests/test_privacy.py).

Record-only (`record_problems`, row W1 of `validate`): every string of the record, member names included, is listed by
the table and fits its class: (a) a member of its vocabulary (the release's strings, the PER rc1 and bundle schemas'
constants and member names, the rc1 layout tokens, the verifier's caveat constants; the release's legacy check names and
legacy metric keys, the trap library, or a closed rc1 form where the field names one), (b) its recorded form, (c) the
PROD-42 excerpt (checked by E2), (d) a fingerprint `sha256-` + 64 hex, (a|d) a member or a fingerprint, (b|d) a strict
version or a fingerprint, (r) a rendered text of these, rebuilt here from the record's own rows and the release
(`expected_text`) and equal byte for byte (a summary is checked by X1 with the display rule: a fingerprint renders as
`sha256-` + its first 12 hex digits; a limitation text and a via are closed productions bound to their rows). A
`sha256-` value appears nowhere else (T3).

With the bundle (`bundle_problems`, `clear_view`, VER-5 row D2): every fingerprint of the record is the fingerprint of a
text of the bundle at one of its field's source paths (`SOURCES`), each (a|d) and (b|d) decision recomputes from that text,
the singleton fields equal the sealed value of their bundle field, each gate reason is the rendering of its record rows
with its metrics named by the decision over their own bundle labels and each declared-link via is a declared row's link
(`rendered_source_problems`), D2's comparisons run on the record's clear view (each
fingerprint replaced by its bundle text, the sorted lists sorted again by the clear text), and no record string outside
the excerpt equals a producer text of the bundle in clear (T5).

`resolve(rec, bundle)` shows the real text of every withheld field from the local bundle (`eio_agents.resolve`,
`eio-agents resolve`, `eio-agents explain --local`); nothing is added to the record.
"""
import ast
import hashlib
import json
import re
import string
from decimal import Decimal, ROUND_HALF_UP

from eio_agents.per.limitations import CATALOGUE as LIMITATION_CATALOGUE
from eio_agents.schemas import (BUNDLE_SCHEMA, LEGACY_BUNDLE_SCHEMAS, PER_SCHEMA, PER_SCHEMA_NATIVE_PREVIEW, PER_SCHEMA_RC1,
                                PER_SCHEMA_RC4, PER_SCHEMA_RC5_POLICY, PER_SCHEMA_2_0_0, PER_SCHEMA_2_1_0)
from eio_agents.validation.canon import jb, q4, sha
from eio_agents.validation.redaction import redact_span

PREFIX = "sha256-"
FP = re.compile(r"sha256-[0-9a-f]{64}")
FP_IN_TEXT = re.compile(r"sha256-[0-9a-f]{12}(?:[0-9a-f]{52})?(?![0-9a-f])")
SHOWN = 19
RC1_LAYOUT = ("transcript", "tools_called", "memory_snapshot")
RECIPE_NAMES = frozenset(("episode_turns", "name_contains", "snapshot_sha256", "name", "version", "kind", "revision",
                          "source_format"))       # the recipes' statement inputs; a native producer's §5.3 N8 fields
CAVEAT_IDS = frozenset(("per.caveat.domain.default", "per.caveat.tier.unknown"))
CAVEAT_TEXTS = frozenset(("No domain was identified; domain-specific risk is UNTESTED, not absent.",
                          "No tier was declared; the tier is unknown and is never assumed to be minimal."))
OPEN = frozenset(tuple(x.split(".")) for x in ("scope.facts", "header.eio.modules", "reliability.named_lists",
                                                "scope.escalations.*.promote", "scope.escalations.*.when",
                                                "coverage.obligations.*.explanation.params.required_text"))
RESORTED = frozenset(tuple(x.split(".")) for x in ("evidence.refs.*.statement.inputs.files_searched",
                                                    "findings.*.explanation.params.files", "findings.*.traps",
                                                    "findings.*.explanation.params.traps"))
X = "[0-9a-f]"
STRICT_VERSION = re.compile(r"(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){1,2}")
# A model identifier (0.8.0, a privacy-rule change approved by the maintainer): a model name with its release date or
# version ('gpt-4o-2024-08-06', 'anthropic/claude-opus-4-1@20250805') is kept in clear in a field that names a model
# (`bd:model`, `md:model`). The verifier's own copy of the projector's `per.bundle.MODEL_ID` (contract P3; parity:
# tests/test_model_identifiers.py).
MODEL_ID_PATTERN = (r"(?=.{1,100}\Z)(?![^/:]*[A-Za-z0-9]{24})(?!.*[0-9A-Fa-f]{16})"
                    r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,39}[/:])?[A-Za-z0-9][A-Za-z0-9._-]*"
                    r"(?:@(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2}|v?[0-9]{1,4}(?:\.[0-9]{1,4})*))?")
_MODEL_SECRET = re.compile(r"(?:(?:sk|pk|rk)[-_](?:live|test|proj)[-_]|sk-|AKIA|gh[pousr]_|xox[abprs]-|glpat-)[A-Za-z0-9_\-]{8,}")


def safe_model_identifier(text):
    """Independently refuse a model-shaped value containing a PROD-42 sensitive token."""
    return bool(re.fullmatch(MODEL_ID_PATTERN, text)) and redact_span(text)[1] == 0 and not _MODEL_SECRET.search(text)


STRICT = {"version": STRICT_VERSION, "digest": re.compile(r"sha256:[0-9a-f]{64}|[0-9a-f]{7,64}"),   # b|d: kept in clear
          "package_version": re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?"
                                        r"(\.dev(0|[1-9][0-9]*))?"),
          "model": re.compile(MODEL_ID_PATTERN)}
MODEL_ROW = "machine-learning-model"         # m|d: the AI-BOM component whose name is the agent model
FORM = {
    "id20": X + "{20}", "hex16": X + "{16}", "hex40": X + "{40}", "hex64": X + "{64}", "sha256": "sha256:" + X + "{64}",
    "lock_digest": f"{X}{{16}}|sha256:{X}{{64}}", "config_fingerprint": X + "{8,64}", "checks_version": X + "{7,40}",
    "semver": r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?",
    "package_version": r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?(\.dev(0|[1-9][0-9]*))?",
    "run_id": f"{X}{{8}}-{X}{{4}}-{X}{{4}}-{X}{{4}}-{X}{{12}}|archive:{X}{{64}}",
    "timestamp": r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})",
    "pointer": r"(/([A-Za-z0-9_.:-]|~[01])+)+",
    "arguments_pointer": r"/(transcript/(0|[1-9][0-9]*)/tools_called|sources/turns/(0|[1-9][0-9]*)/tool_calls)/(0|[1-9][0-9]*)/(arguments|args)",
}
FORM = {k: re.compile(v) for k, v in FORM.items()}
CONTRACT = re.compile(r"require_all:[A-Z_]+|require_any|group:[1-9][0-9]*|minimum_refs|scope|counterevidence|no_witnessing_ref")
RULE = re.compile(r"profile\.(prohibited_use_case|min_score|block_on_(critical|high|medium|low|informational)|signoff_required)")
COMPONENTS = frozenset(("release_gate", "open_findings", "human_oversight", "compliance_scope", "evidence_freshness"))
PUBLIC_PROFILE_IDS = frozenset(("harness-2.x", "eio-agents.reference-scoring"))
PUBLIC_PROFILE_VERSIONS = frozenset(("2.1.0", "0.0.0-draft", "0.2.0-draft.1", "0.3.0-draft.1", "0.3.1-draft.1", "0.3.1"))
PUBLIC_PROFILES = frozenset((("harness-2.x", "2.1.0"), ("eio-agents.reference-scoring", "0.0.0-draft"),
                             ("eio-agents.reference-scoring", "0.2.0-draft.1"),
                             ("eio-agents.reference-scoring", "0.3.0-draft.1"),
                             ("eio-agents.reference-scoring", "0.3.1-draft.1"),
                             ("eio-agents.reference-scoring", "0.3.1")))
# the review guards a PER 2.1.0 record may carry (release semantics 2.2, owner decision #46)
REVIEW_GUARDS = frozenset(("eio.release.high-review-queue", "eio.release.default-readiness-floor",
                           "eio.release.hard-block-unmet"))
PUBLIC_G_IDS = frozenset(("release_gate", "human_oversight", "policy_conformance", "obligation_coverage",
                          "evidence_freshness", "prohibited_use_case"))
BASIS = re.compile(r"framework set of (eio\.region\.[a-z0-9-]+)")
VIA_LINK = re.compile("eio\\.graph\\.context-links:(?P<key>[^→]+)→(?P<criterion>eio\\.context\\.[^/]+)/(?P<control>.+)")
VIA_CRITERION = re.compile(r"eio\.context\.criteria:(?P<criterion>[^/]+)/(?P<control>.+)")
LEDGER = re.compile(r"(?P<label>.+)::(?P<check>[a-z0-9_]+)@(?P<turn>[1-9][0-9]*)")
LABEL = re.compile("t[0-9]{2,} · (?P<predicate>[a-z0-9][a-z0-9-]*)|ctx · (?P<criterion>[a-z0-9][a-z0-9-]*) / (?P<control>[a-z0-9][a-z0-9-]*)")
SEMANTICS = re.compile(r"2@(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*[+]eio(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                       r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?\.[0-9a-f]{16}")
RECIPES = (re.compile(r"len\((?P<cf>[^\[\]()]+)\[t\]\)"),
           re.compile(r"count\(call for t in episode_turns for call in (?P<cf>[^\[\]()]+)\[t\] if any\(p in call\.name\.lower\(\) "
                      r"for p in name_contains\)\)"),
           re.compile(r"count\(term in casefold\(file\) for file in files_searched for term in requires_any\)"),
           re.compile(r"(?P<cf>[^\[\]()]+)\[t\] is non-empty"))
NUMBER = re.compile(r"-?[0-9]{1,6}(\.[0-9]{1,4})?")
PARAM_SAFE = re.compile(r"[0-9a-f]{20}|[0-9a-f]{7,64}|sha256:[0-9a-f]{64}|"
                        r"(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){1,3}(\.dev[0-9]+)?(\+[a-z]{1,16})?|"
                        r"-?(0|[1-9][0-9]{0,5})(\.[0-9]{1,4})?")

TABLE_TEXT = """
a:vocab
    scores.kind
    scores.score_basis_version
    scores.metrics.*.status
    scores.metrics.*.withheld_code
    scores.axes.*.status
    scores.axes.*.withheld_code
    scores.readiness.status
    scores.readiness.withheld_codes.*
    claims.*.decided_by
    claims.*.parameters.applicability_basis.source
    claims.*.parameters.contract_check.status
    claims.*.parameters.invalid_because
    claims.*.parameters.legacy_decided_by
    claims.*.parameters.mapping_relation
    claims.*.parameters.state_source
    claims.*.parameters.fidelity
    findings.*.fidelity
    claims.*.predicate
    claims.*.provenance.module
    claims.*.resolver
    claims.*.risk
    claims.*.state
    controls.*.assurance_boundary
    controls.*.control_id
    controls.*.explanation.context_refs.*.relation
    controls.*.explanation.drivers.*.contribution.unit
    controls.*.explanation.drivers.*.role
    controls.*.explanation.params.external_ref
    controls.*.explanation.params.framework
    controls.*.explanation.params.legal_review
    controls.*.explanation.params.mapping_status
    controls.*.explanation.params.predicates.*
    controls.*.explanation.params.predicates_failed.*
    controls.*.explanation.params.predicates_passed.*
    controls.*.explanation.params.proxy_note
    controls.*.explanation.template_id
    controls.*.external_ref
    controls.*.framework
    controls.*.framework_state
    controls.*.mapping_status
    controls.*.status
    controls.*.title
    coverage.dispatch.*.cause_if_silent
    coverage.dispatch.*.predicate
    coverage.obligations.*.cause_if_unmet
    coverage.obligations.*.domain
    coverage.obligations.*.explanation.context_refs.*.relation
    coverage.obligations.*.explanation.drivers.*.contribution.unit
    coverage.obligations.*.explanation.drivers.*.role
    coverage.obligations.*.explanation.params.cause
    coverage.obligations.*.explanation.params.obligation
    coverage.obligations.*.explanation.params.predicate
    coverage.obligations.*.explanation.params.release_impact
    coverage.obligations.*.explanation.params.required_text.<key>
    coverage.obligations.*.explanation.template_id
    coverage.obligations.*.id
    coverage.obligations.*.predicate
    coverage.obligations.*.release_impact
    coverage.obligations.*.release_impact_declared
    coverage.obligations.*.severity
    evidence.archive_pointer.transcript
    evidence.completeness.code_check_offsets
    evidence.completeness.context_artifacts
    evidence.completeness.reliability_pass_transcripts
    evidence.completeness.retrieval_text
    evidence.completeness.sentinel_locations
    evidence.completeness.tool_outputs
    evidence.refs.*.anchor
    evidence.refs.*.kind
    evidence.refs.*.source_type
    evidence.refs.*.tool.output
    findings.*.control
    findings.*.control_ids.*
    findings.*.criterion
    findings.*.decided_by
    findings.*.explanation.context_refs.*.relation
    findings.*.explanation.drivers.*.contribution.unit
    findings.*.explanation.drivers.*.role
    findings.*.explanation.params.control
    findings.*.explanation.params.criterion
    findings.*.explanation.params.decided_by
    findings.*.explanation.params.evidence_kinds.*
    findings.*.explanation.params.mapping_relation
    findings.*.explanation.params.predicate
    findings.*.explanation.params.proof_status
    findings.*.explanation.params.recurrence.band
    findings.*.explanation.params.severity
    findings.*.explanation.params.severity_source.*
    findings.*.explanation.template_id
    findings.*.kind
    findings.*.mapping_relation
    findings.*.mitigations.*.action
    findings.*.mitigations.*.category
    findings.*.mitigations.*.verification
    findings.*.predicate
    findings.*.proof_status
    findings.*.recurrence.band
    findings.*.recurrence.trial_kind
    findings.*.release_impact
    findings.*.risk
    findings.*.scenario_severity
    findings.*.severity
    findings.*.severity_source.kind
    findings.*.severity_source.obligation_ids.*
    findings.*.status
    header.adjudication_source
    header.converter.name
    header.per_version
    header.release_semantics
    header.schema_uri
    limitations.*.limitation_id
    limitations.*.status
    provenance.capsule.missing_fields.*
    provenance.harness_llm.per_stage
    provenance.harness_llm.per_stage.*.stage
    provenance.inputs.context_artifacts.*.artifact_kind
    provenance.inputs.context_artifacts.*.data_class
    provenance.producer.kind
    provenance.run.run_id_source
    provenance.run.transcript_source
    release_recommendation.contributing.*.effect
    release_recommendation.contributing.*.id
    release_recommendation.contributing.*.kind
    release_recommendation.contributing.*.metric
    release_recommendation.contributing.*.obligation_ids.*
    release_recommendation.contributing.*.proof_status
    release_recommendation.decisive.*.effect
    release_recommendation.decisive.*.kind
    release_recommendation.decisive.*.metric
    release_recommendation.decisive.*.obligation_ids.*
    release_recommendation.decisive.*.proof_status
    release_recommendation.explanation.context_refs.*.relation
    release_recommendation.explanation.drivers.*.contribution.unit
    release_recommendation.explanation.drivers.*.role
    release_recommendation.explanation.params.semantics
    release_recommendation.explanation.template_id
    release_recommendation.gate_results.*.evaluated_at
    release_recommendation.gate_results.*.explanation.context_refs.*.relation
    release_recommendation.gate_results.*.explanation.drivers.*.contribution.unit
    release_recommendation.gate_results.*.explanation.drivers.*.role
    release_recommendation.gate_results.*.explanation.params.gate
    release_recommendation.gate_results.*.explanation.params.unmet_state
    release_recommendation.gate_results.*.explanation.template_id
    release_recommendation.gate_results.*.gate
    release_recommendation.gate_results.*.obligation_ids.*
    release_recommendation.gate_results.*.unmet_state
    release_recommendation.metric_floors.*.metric
    release_recommendation.metric_floors.*.result
    release_recommendation.policy.declared.origin
    release_recommendation.policy.declared.state
    release_recommendation.policy.origin
    release_recommendation.policy.rules.*.result
    release_recommendation.policy.source
    release_recommendation.policy.tier
    release_recommendation.semantics
    release_recommendation.signoff.status
    release_recommendation.state
    reliability.explanation.context_refs.*.relation
    reliability.explanation.drivers.*.contribution.unit
    reliability.explanation.drivers.*.role
    reliability.explanation.params.publication
    reliability.explanation.params.trial_kind
    reliability.explanation.template_id
    reliability.rate.denominator
    reliability.rate.suppressed_state
    reliability.recurrence.*.band
    reliability.status
    reliability.trial_kind
    scope.autonomy
    scope.domains.*.id
    scope.domains.*.matched
    scope.domains.*.source
    scope.escalations.*.promote.<key>
    scope.escalations.*.when.<key>
    scope.frameworks.*.id
    scope.frameworks.*.registry_id
    scope.frameworks.*.state
    scope.region
    scope.tier.id
    scope.tier.source
    scores.axes.*.axis
    scores.axes.*.explanation.context_refs.*.relation
    scores.axes.*.explanation.drivers.*.contribution.unit
    scores.axes.*.explanation.drivers.*.role
    scores.axes.*.explanation.template_id
    scores.axes.*.measurement_status
    scores.axes.*.symbol
    scores.metrics.*.cap.cap
    scores.metrics.*.cap.scope
    scores.metrics.*.explanation.context_refs.*.relation
    scores.metrics.*.explanation.drivers.*.contribution.unit
    scores.metrics.*.explanation.drivers.*.role
    scores.metrics.*.explanation.params.cap
    scores.metrics.*.explanation.params.predicate
    scores.metrics.*.explanation.template_id
    scores.metrics.*.measurement_status
    scores.metrics.*.metric
    scores.readiness.band
    scores.readiness.cap_reasons.*.cap
    scores.readiness.cap_reasons.*.scope
    scores.readiness.cap_reasons.*.trigger
    scores.readiness.explanation.context_refs.*.relation
    scores.readiness.explanation.drivers.*.contribution.unit
    scores.readiness.explanation.drivers.*.role
    scores.readiness.explanation.params.band
    scores.readiness.explanation.params.cap
    scores.readiness.explanation.params.predicate
    scores.readiness.explanation.template_id
    scores.readiness.method
    scores.readiness.missing_axes.*
    subject.ai_bom.components.*.kind
    telemetry.agent_under_test.cost_provenance
    telemetry.harness_llm.cost_provenance
a:check_name
    claims.*.parameters.applicability_basis.premise_check
    claims.*.parameters.legacy_check
a:metric_key
    scores.metrics.*.legacy_metric
a:contract_token
    claims.*.parameters.contract_check.unmet.*
a:profile_rule
    release_recommendation.policy.rules.*.rule
a:decisive_id
    release_recommendation.decisive.*.id
a:caveat_id
    scope.caveats.*.id
a:component_id
    scores.axes.*.basis_ids.*
    scores.axes.*.components.*.id
b:profile_id
    scores.scoring_profile.id
b:legacy_profile_id
    scores.scoring_profile
b:profile_version
    scores.scoring_profile.version
b:arguments_pointer
    evidence.refs.*.tool.arguments_pointer
b:checks_version
    provenance.inputs.checks_version
b:config_fingerprint
    provenance.run.config_fingerprint
b:hex16
    header.eio.ontology_digest
b:hex40
    provenance.producer.source_revision
b:hex64
    findings.*.fingerprint
b:id20
    scores.metrics.*.member_claim_ids.*
    scores.metrics.*.cap_claim_ids.*
    scores.proof_sets.reportable_finding_ids.*
    scores.proof_sets.decisive_finding_ids.*
    scores.proof_sets.decisive_claim_ids.*
    scores.readiness.cap.claim_ids.*
    claims.*.counterevidence.*
    claims.*.evidence.*
    claims.*.id
    controls.*.claim_ids.*
    controls.*.evidence_refs.*
    controls.*.explanation.context_refs.*.ref_id
    controls.*.explanation.drivers.*.claim_id
    controls.*.explanation.evidence_refs.*
    coverage.obligations.*.claim_ids.*
    coverage.obligations.*.explanation.context_refs.*.ref_id
    coverage.obligations.*.explanation.drivers.*.claim_id
    coverage.obligations.*.explanation.evidence_refs.*
    evidence.cited_refs_hash
    evidence.refs.*.id
    findings.*.claim_ids.*
    findings.*.evidence_refs.*
    findings.*.explanation.context_refs.*.ref_id
    findings.*.explanation.drivers.*.claim_id
    findings.*.explanation.evidence_refs.*
    findings.*.finding_id
    findings.*.issue_signature
    release_recommendation.contributing.*.claim_ids.*
    release_recommendation.contributing.*.finding_ids.*
    release_recommendation.decisive.*.claim_ids.*
    release_recommendation.decisive.*.finding_ids.*
    release_recommendation.explanation.context_refs.*.ref_id
    release_recommendation.explanation.drivers.*.claim_id
    release_recommendation.explanation.evidence_refs.*
    release_recommendation.gate_results.*.claim_ids.*
    release_recommendation.gate_results.*.explanation.context_refs.*.ref_id
    release_recommendation.gate_results.*.explanation.drivers.*.claim_id
    release_recommendation.gate_results.*.explanation.evidence_refs.*
    reliability.explanation.context_refs.*.ref_id
    reliability.explanation.drivers.*.claim_id
    reliability.explanation.evidence_refs.*
    reliability.occurrence.*.claim_ids.*
    reliability.occurrence.*.finding_id
    reliability.recurrence.*.claim_id
    reliability.recurrence.*.finding_id
    scores.axes.*.explanation.context_refs.*.ref_id
    scores.axes.*.explanation.drivers.*.claim_id
    scores.axes.*.explanation.evidence_refs.*
    scores.metrics.*.cap.claim_id
    scores.metrics.*.cap.ref
    scores.metrics.*.explanation.context_refs.*.ref_id
    scores.metrics.*.explanation.drivers.*.claim_id
    scores.metrics.*.explanation.evidence_refs.*
    scores.metrics.*.explanation.params.claim_id
    scores.readiness.cap_reasons.*.claim_id
    scores.readiness.cap_reasons.*.ref
    scores.readiness.explanation.context_refs.*.ref_id
    scores.readiness.explanation.drivers.*.claim_id
    scores.readiness.explanation.evidence_refs.*
    scores.readiness.explanation.params.claim_id
b:lock_digest
    provenance.capsule.lock_digest
b:package_version
    header.converter.version
b:pointer
    limitations.*.field_path
    release_recommendation.contributing.*.field_refs.*
    release_recommendation.decisive.*.field_refs.*
b:run_id
    claims.*.run_id
    provenance.run.run_id
b:semver
    claims.*.predicate_version
    claims.*.provenance.module_version
    findings.*.predicate_version
    header.eio.release
b:sha256
    scores.scoring_profile.ontology_sha256
    scores.score_basis_sha256
    scores.score_sha256
    scores.scoring_profile.sha256
    claims.*.provenance.module_hash
    claims.*.provenance.plan_hash
    evidence.archive_pointer.archive_sha256
    evidence.refs.*.source_sha256
    evidence.refs.*.span_sha256
    evidence.refs.*.statement.inputs.snapshot_sha256
    evidence.refs.*.tool.arguments_sha256
    evidence.refs.*.tool.output.sha256
    evidence.transcript_sha256
    evidence.turns.*.answer_sha256
    evidence.turns.*.question_sha256
    evidence.turns.*.tool_calls.*.arguments_sha256
    header.archive_sha256
    header.eio.modules.<key>
    header.eio.ontology_sha256
    provenance.inputs.context_artifacts.*.sha256
    provenance.inputs.governance_profile.profile_sha256
    provenance.inputs.traps.selected_digest
    provenance.run.plan_hash
    release_recommendation.policy.declared.profile_sha256
    release_recommendation.policy.profile_sha256
    subject.ai_bom.components.*.sha256
    subject.ai_bom.content_hash
b:timestamp
    provenance.run.completed_at
    provenance.run.started_at
c
    evidence.refs.*.excerpt
d
    evidence.refs.*.statement.inputs.files_searched.*
    evidence.refs.*.tool.name
    evidence.turns.*.retrievals.*.source
    evidence.turns.*.tool_calls.*.name
    findings.*.explanation.params.files.*
    provenance.capsule.caveats.*
    provenance.harness_llm.consensus.personas.*
    provenance.harness_llm.consensus.strategy
    provenance.inputs.context_artifacts.*.name
    provenance.inputs.governance_profile.name
    provenance.producer.name
    provenance.producer.source_format
    release_recommendation.policy.declared.name
    release_recommendation.policy.name
    scope.facts.<key>.source
    subject.agent.agent_id
    subject.agent.business_case
    subject.agent.class
    subject.agent.goal
    subject.agent.role
ad:basis
    scope.frameworks.*.basis.*
ad:layout
    evidence.refs.*.statement.inputs.source
ad:pointer
    evidence.archive_pointer.<key>
ad:release
    evidence.refs.*.statement.inputs.name_contains.*
    evidence.refs.*.statement.inputs.requires_any.*
    findings.*.explanation.params.terms.*
    scores.axes.*.explanation.params.axis
    scores.axes.*.explanation.params.lowest
    scores.axes.*.explanation.params.lowest_metric
    scores.axes.*.explanation.params.lowest_rule
    scores.axes.*.explanation.params.reason
    scores.metrics.*.explanation.params.metric
    scores.metrics.*.explanation.params.reason
ad:source_ref
    evidence.refs.*.source_ref
ad:label
    claims.*.parameters.trap
    evidence.turns.*.trap
    findings.*.explanation.params.traps.*
    findings.*.traps.*
    claims.*.parameters.scenario
    evidence.turns.*.scenario
    findings.*.scenarios.*
    provenance.inputs.traps.selected.*
    provenance.evaluator_models.*.role
    telemetry.evaluator_models.*.role
    reliability.named_lists.<key>.*
bd:model
    claims.*.provenance.model
    provenance.evaluator_models.*.model
    provenance.harness_llm.fallback.model
    provenance.harness_llm.per_stage.*.model
    provenance.harness_llm.primary.model
    subject.agent.model
    telemetry.evaluator_models.*.model
md:model
    subject.ai_bom.components.*.name
bd:digest
    provenance.producer.patch_digest
    provenance.producer.revision
bd:package_version
    provenance.producer.harness_version
bd:version
    provenance.producer.version
    subject.agent.version
r:caveat
    scope.caveats.*.text
r:converter
    release_recommendation.contributing.*.expected
    release_recommendation.contributing.*.observed
    release_recommendation.decisive.*.expected
    release_recommendation.decisive.*.observed
    release_recommendation.explanation.params.decisive_list.*
    release_recommendation.gate_results.*.explanation.params.reason
    release_recommendation.policy.rules.*.expected
    release_recommendation.policy.rules.*.observed
r:display_label
    findings.*.display_label
r:formula
    evidence.refs.*.statement.formula
r:ledger_key
    findings.*.recurrence.ledger_key
    reliability.recurrence.*.ledger_key
r:limitation
    limitations.*.impact
    limitations.*.next_step
    limitations.*.reason
r:semantics
    header.per_semantics_version
r:summary
    controls.*.explanation.summary
    coverage.obligations.*.explanation.summary
    findings.*.explanation.summary
    release_recommendation.explanation.summary
    release_recommendation.gate_results.*.explanation.summary
    reliability.explanation.summary
    scores.axes.*.explanation.summary
    scores.metrics.*.explanation.summary
    scores.readiness.explanation.summary
r:via
    controls.*.explanation.context_refs.*.via
    coverage.obligations.*.explanation.context_refs.*.via
    findings.*.explanation.context_refs.*.via
    release_recommendation.explanation.context_refs.*.via
    release_recommendation.gate_results.*.explanation.context_refs.*.via
    reliability.explanation.context_refs.*.via
    scores.axes.*.explanation.context_refs.*.via
    scores.metrics.*.explanation.context_refs.*.via
    scores.readiness.explanation.context_refs.*.via
"""


def _table(text):
    t, cls = {}, None
    for line in text.splitlines():
        if line.strip() and not line.startswith(" "):
            c, _, a = line.strip().partition(":")
            cls = (c, a or None)
        elif line.strip():
            path = tuple(line.strip().split("."))
            assert path not in t, path
            t[path] = cls
    return t


TABLE = _table(TABLE_TEXT)

# the bundle source fields of every fingerprinted or decided record field (generalized; `|` separates alternatives): a
# fingerprint must be the fingerprint of a text at one of them (`bundle_problems`) and resolves there (`resolve`)
SOURCES_TEXT = """
subject.agent.goal                              provenance.agent.goal
subject.agent.role                              provenance.agent.role
subject.agent.business_case                     provenance.agent.business_case
subject.agent.class                             provenance.agent.class
subject.agent.agent_id                          provenance.agent.agent_id
subject.agent.model                             provenance.agent.model
subject.agent.version                           provenance.agent.version
subject.ai_bom.components.*.name                provenance.agent.model|sources.context_artifacts.*.name
provenance.capsule.caveats.*                    provenance.capsule.caveats.*
provenance.harness_llm.primary.model            provenance.record.harness_llm.primary.model
provenance.harness_llm.fallback.model           provenance.record.harness_llm.fallback.model
provenance.harness_llm.consensus.personas.*     provenance.record.harness_llm.consensus.personas.*
provenance.harness_llm.consensus.strategy       provenance.record.harness_llm.consensus.strategy
claims.*.provenance.model                       claims.*.provenance.model
provenance.inputs.context_artifacts.*.name      provenance.record.inputs.context_artifacts.*.name|sources.context_artifacts.*.name
provenance.inputs.governance_profile.name       provenance.record.inputs.governance_profile.name
release_recommendation.policy.name              scope.policy.name
provenance.producer.name                        provenance.record.producer.name|provenance.producer.name
provenance.producer.version                     provenance.record.producer.version|provenance.producer.version
provenance.producer.harness_version             provenance.record.producer.harness_version
provenance.producer.patch_digest                provenance.record.producer.patch_digest
provenance.producer.revision                    provenance.record.producer.revision|provenance.producer.revision
provenance.producer.source_format               provenance.record.producer.source_format
scope.facts.<key>.source                        scope.facts.<key>.source
scope.frameworks.*.basis.*                      scope.frameworks.candidates.*.basis|scope.frameworks.candidates.*.basis.*
evidence.turns.*.tool_calls.*.name              sources.turns.*.tool_calls.*.name
evidence.refs.*.tool.name                       sources.turns.*.tool_calls.*.name|graph.refs.*.tool.name
evidence.turns.*.retrievals.*.source            sources.turns.*.retrievals.*.source
evidence.refs.*.source_ref                      sources.context_artifacts.*.name|graph.refs.*.source_ref|sources.turn_source_ref|context_assessment.gaps.*.files_searched.*
evidence.refs.*.statement.inputs.files_searched.*   context_assessment.gaps.*.files_searched.*|graph.refs.*.statement.inputs.files_searched.*|sources.context_artifacts.*.name
findings.*.explanation.params.files.*           context_assessment.gaps.*.files_searched.*
evidence.refs.*.statement.inputs.requires_any.*     context_assessment.gaps.*.terms.*|graph.refs.*.statement.inputs.requires_any.*
findings.*.explanation.params.terms.*           context_assessment.gaps.*.terms.*
evidence.refs.*.statement.inputs.name_contains.*    graph.refs.*.statement.inputs.name_contains.*
evidence.refs.*.statement.inputs.source         sources.calls_field|graph.refs.*.statement.inputs.source
evidence.archive_pointer.<key>                  sources.archive_pointer.<key>
claims.*.parameters.trap                        claims.*.parameters.trap
evidence.turns.*.trap                           producer_declared.scenarios.turns.*.label
findings.*.traps.*                              producer_declared.scenarios.turns.*.label
findings.*.explanation.params.traps.*           producer_declared.scenarios.turns.*.label
provenance.inputs.traps.selected.*              provenance.record.inputs.traps.selected.*
reliability.named_lists.<key>.*                 trials.named_lists.<key>.*
scores.axes.*.explanation.params.lowest         producer_declared.score_inputs.axes.*.explanation.params.lowest
scores.axes.*.explanation.params.lowest_metric  producer_declared.score_inputs.axes.*.explanation.params.lowest_metric
scores.axes.*.explanation.params.lowest_rule    producer_declared.score_inputs.axes.*.explanation.params.lowest_rule
scores.metrics.*.explanation.params.metric      producer_declared.score_inputs.metrics.*.label
scores.metrics.*.explanation.params.reason      producer_declared.score_inputs.metrics.*.not_evaluated_reason
scores.axes.*.explanation.params.axis           producer_declared.score_inputs.axes.*.explanation.params.axis
scores.axes.*.explanation.params.reason         producer_declared.score_inputs.axes.*.explanation.params.reason
provenance.harness_llm.per_stage.*.model        provenance.record.harness_llm.per_stage.*.model
release_recommendation.policy.declared.name     scope.policy.declared.name
"""
SOURCES = {tuple(r.split(".")): tuple(tuple(a.split(".")) for a in s.split("|"))
           for r, s in (line.split() for line in SOURCES_TEXT.strip().splitlines())}
# rendered texts whose inner values are fingerprints: their bundle sources
TEXT_SOURCES = {"via": (("producer_declared", "context_links", "claims", "<key>"), ("producer_declared", "context_links", "rows", "{name}")),
                "ledger_key": (("trials", "records", "*", "ledger_key"), ("producer_declared", "scenarios", "turns", "*", "label")),
                "limitation": (("limitations", "*", "params", "<key>"), ("limitations", "*", "params", "<key>", "*")),
                "formula": (("sources", "calls_field"), ("sources", "state_field")),
                "converter": (("producer_declared", "score_inputs", "metrics", "*", "label"),)}   # a gate's metric label


def fingerprint(text):
    return PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def shown(v):
    """A parameter value as a summary renders it: each fingerprint in its display form."""
    if isinstance(v, str) and FP.fullmatch(v):
        return v[:SHOWN]
    if isinstance(v, list):
        return [shown(x) for x in v]
    if isinstance(v, dict):
        return {k: shown(x) for k, x in v.items()}
    return v


def _walk_strings(doc, out_values, out_names):
    stack = [doc]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            out_names.update(o)
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
        elif isinstance(o, str):
            out_values.add(o)


def _schema(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    props, consts, stack = set(), set(), [doc]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if isinstance(o.get("properties"), dict):
                props |= set(o["properties"])
            if isinstance(o.get("enum"), list):
                consts |= {x for x in o["enum"] if isinstance(x, str)}
            if isinstance(o.get("const"), str):
                consts.add(o["const"])
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return props, consts


class Words:
    """The verifier's vocabularies of one release reader `e`."""

    def __init__(self, e):
        values, keys = set(), set()
        _walk_strings(list(e.doc.values()), values, keys)
        cat_values, cat_keys = set(), set()
        _walk_strings(json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8")), cat_values, cat_keys)
        self.release = frozenset(values | keys | cat_values | cat_keys)        # strings and member names: public text
        p1, c1 = set(), set()
        # Only the active rc3/rc4 drafts and rc1 baseline may expand this release's
        # clear-text vocabulary. Historical rc2 and diagnostic previews must
        # be checked with their own pinned releases, not silently trusted here.
        for schema in (PER_SCHEMA_RC1, PER_SCHEMA, PER_SCHEMA_RC4, PER_SCHEMA_RC5_POLICY,
                       PER_SCHEMA_2_0_0, PER_SCHEMA_2_1_0):
            properties, constants = _schema(schema)
            p1 |= properties
            c1 |= constants
        # Internal native prechecks need only the exact preview header URI;
        # the diagnostic schema's other terms must not broaden public PER text.
        c1.add(json.loads(PER_SCHEMA_NATIVE_PREVIEW.read_text(encoding="utf-8"))["$id"])
        p2, c2 = _schema(BUNDLE_SCHEMA)
        p3, c3 = _schema(LEGACY_BUNDLE_SCHEMAS[2])                    # legacy bundle_draft 2 bundles (read-only)
        p2, c2 = p2 | p3, c2 | c3
        self.layout = frozenset(p1 | p2 | set(RC1_LAYOUT))
        self.vocab = frozenset(self.release | c1 | c2 | self.layout | CAVEAT_IDS | CAVEAT_TEXTS)
        self.labels = frozenset()
        self.checks = frozenset()
        self.metric_keys = frozenset()
        self.names = frozenset(self.vocab | keys | self.labels | self.checks | RECIPE_NAMES)
        self.every = frozenset(self.vocab | self.labels | self.checks | self.metric_keys)
        self.evidence_floor = e.floors["eio.floor.release-evidence"]["value"]           # gate reasons (rebuilt)
        self.cases = list(e.cases)
        self.checklist = {cid: {x["id"] for x in c.get("controls") or []} for cid, c in e.criteria.items()}


_WORDS = {}


def words(e):
    w = _WORDS.get(id(e))
    if w is None or w[0] is not e:
        w = _WORDS[id(e)] = (e, Words(e))
    return w[1]


def gen(path):
    out = []
    for x in path:
        open_ = tuple(out) in OPEN or (tuple(out) == ("evidence", "archive_pointer") and x not in ("archive_sha256", "transcript"))
        out.append("*" if type(x) is int else ("<key>" if open_ else x))
    return tuple(out)


def ptr(path):
    return "/" + "/".join(str(x) for x in path)


def strings(doc):
    """[(path, string)] of the string values of `doc`, document order."""
    out, stack = [], [(doc, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            stack.extend((v, p + (k,)) for k, v in reversed(list(o.items())))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in reversed(list(enumerate(o))))
        elif isinstance(o, str):
            out.append((p, o))
    return out


def members(doc):
    out, stack = [], [(doc, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                out.append((p, k))
                stack.append((v, p + (k,)))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in enumerate(o))
    return out


def is_member(w, arg, v):
    if arg == "label":
        return v in w.labels
    if arg == "release":
        return v in w.release
    if arg == "layout":
        return v in w.layout
    if arg == "pointer":
        return v.startswith("/") and all(t in w.layout or t.isdigit() for t in v[1:].split("/"))
    if arg == "source_ref":
        return v in ("transcript", "context") or v in w.layout
    if arg == "basis":
        m = BASIS.fullmatch(v)
        return v in w.release or bool(m and m.group(1) in w.release)
    raise ValueError(f"unknown vocabulary {arg}")


def decide(w, spec, text):
    """The record value of a clear text in a field of class `spec` (the converter's decision, recomputed)."""
    c, arg = spec
    if text == "" and c in ("d", "ad", "bd", "md"):
        return text                               # an empty string carries no text
    if c in ("d", "md"):                          # an `md` text of the model row: `decide_row`
        return fingerprint(text)
    if c == "ad":
        return text if is_member(w, arg, text) else fingerprint(text)
    if c == "bd":
        return text if (safe_model_identifier(text) if arg == "model" else STRICT[arg].fullmatch(text)) else fingerprint(text)
    return text


def decide_row(w, spec, text, rec, path):
    """`decide` for a field whose class depends on its row: the agent model's AI-BOM row keeps a model identifier in
    clear (m|d), any other row's name is fingerprinted."""
    if spec[0] == "md" and text and _get(rec, path[:-1]).get("kind") == MODEL_ROW and safe_model_identifier(text):
        return text
    return decide(w, spec, text)


def _via_ok(w, key):
    return bool(FP.fullmatch(key)) or key in w.labels or key in w.checks or key in w.vocab


def _safe_param(w, value):
    """Independent check of catalogue substitutions, including nested Python display containers."""
    if not isinstance(value, str) or len(value) > 4096:
        return False
    if value in w.every or PARAM_SAFE.fullmatch(value) or FP.fullmatch(value) or value in ("None", "True", "False"):
        return True
    m = LEDGER.fullmatch(value)
    if m and (m["label"] in w.labels or FP.fullmatch(m["label"])) and m["check"] in w.checks:
        return True
    if value[:1] not in ("[", "{", "("):
        return False
    try:
        obj = ast.literal_eval(value)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return False
    def safe(x, depth=0):
        if depth > 12:
            return False
        if isinstance(x, str):
            return _safe_param(w, x)
        if isinstance(x, (int, float, bool)) or x is None:
            return True
        if isinstance(x, (list, tuple)) and len(x) <= 128:
            return all(safe(v, depth + 1) for v in x)
        if isinstance(x, dict) and len(x) <= 128:
            return all(safe(k, depth + 1) and safe(v, depth + 1) for k, v in x.items())
        return False
    return safe(obj)


# rendered texts (class r), rebuilt here from the record independently of the converter's renderer (L3s grammar fix):
# each rebuilt text must equal the record's byte for byte, so no slot of a rendered text is open to a number, a word list
# or a fingerprint that the record's own rows do not give. A limitation text, a via and a recurrence row's ledger key are
# closed productions (the record keeps no limitation parameter, context-link key or ledger label); `bundle_problems` binds
# them to the bundle (T4).
CAPSULE_ORDER = ("revision", "patch", "seed", "models", "prompt_hashes")
BANDS = ("NOT_RETESTED", "UNCONFIRMED", "INTERMITTENT", "CONFIRMED")          # weakest first
CLAUSES = 3                                                                   # 04 §5.12: a gate reason's clause limit


class Unrendered(Exception):
    """The record's rows do not support the rendered text at this path."""


def _need(ok):
    if not ok:
        raise Unrendered


def _i(x):
    _need(isinstance(x, int) and not isinstance(x, bool))
    return x


def _s(x):
    _need(isinstance(x, str))
    return x


def _f(x):
    _need(isinstance(x, (int, float)) and not isinstance(x, bool))
    return x


def _decimal(v):
    return f"{int(v)}.0" if isinstance(v, int) or float(v) == int(v) else repr(float(v))


def _turns(ts):
    shown_ = ", ".join(str(t) for t in ts[:5])
    return ("turn " if len(ts) == 1 else "turns ") + shown_ + (f" and {len(ts) - 5} more" if len(ts) > 5 else "")


def _n(count, one, many):
    return f"{count} {one if count == 1 else many}"


def _gate_coverage(w, rec, row):
    rows = rec["coverage"]["obligations"]
    _need(isinstance(rows, list))
    false_ = sum(1 for o in rows if o["release_impact"] == "HARD_BLOCK" and o["met"] is False and o["required"] is True)
    null_ = sum(1 for o in rows if o["release_impact"] == "HARD_BLOCK" and o["met"] is False and o["required"] is None)
    if false_:
        return _n(false_, "required HARD_BLOCK obligation is", "required HARD_BLOCK obligations are") + " unmet"
    if null_:
        return (_n(null_, "HARD_BLOCK obligation is", "HARD_BLOCK obligations are") + " unmet and "
                + ("its" if null_ == 1 else "their") + " required status is unknown because a required_when fact is not declared")
    return "every HARD_BLOCK obligation whose required is not false reached its minimum cases"


def _gate_evidence(w, rec, row, label=None):
    """`label(metric_row)`: the metric's name in the reason (default: its row's `metric` parameter, the label's record
    value); `bundle_problems` passes the decision over the bundle's matching metric label instead."""
    floor = _decimal(w.evidence_floor)
    scores = rec.get("scores") or {}
    # The native draft metric's MEASURED/WITHHELD status is not the archived
    # evidence-fraction DIAGNOSTIC_ONLY status used by this legacy gate.
    metrics = [] if scores.get("kind") in ("reference-draft", "reference") else scores.get("metrics") or []
    _need(isinstance(metrics, list))
    diag = [m for m in metrics if m["measurement_status"] == "DIAGNOSTIC_ONLY"]
    if not diag:
        return f"every metric returned at least {floor} of its expected claims"
    name = label or (lambda m: _s(m["explanation"]["params"]["metric"]))
    if len(diag) > CLAUSES:
        items = [f"{name(m)} ({_f(m['evidence_fraction']):.4f})" for m in diag]
        return f"{len(diag)} metrics returned less than the {floor} floor of their expected claims: " + ", ".join(items)
    out = []
    for m in diag:
        b = m["explanation"]["basis"]
        got = _i(b["pass"]) + _i(b["fail"]) + _i(b["not_applicable"])
        out.append(f"{name(m)} returned {got} of {_i(b['claims'])} expected claims ({_f(m['evidence_fraction']):.4f}), "
                   f"below the {floor} floor")
    return "; ".join(out)


def _gate_reproducible(w, rec, row):
    missing = rec["provenance"]["capsule"]["missing_fields"]
    _need(isinstance(missing, list))
    lacks = [x for x in CAPSULE_ORDER if x in missing]
    return "the capsule lacks " + ", ".join(lacks) if lacks else "the capsule records revision, patch, seed, models and prompt hashes"


def _gate_oversight(w, rec, row):
    tier = rec["release_recommendation"]["policy"]["tier"]
    _need(tier is None or isinstance(tier, str))
    facts = rec["scope"]["facts"]
    _need(isinstance(facts, dict))
    ca = facts["consequential_actions"]["value"] if "consequential_actions" in facts else None
    ho = facts["human_oversight"]["value"] if "human_oversight" in facts else None
    if tier is not None and tier != "eio.tier.high":
        return "oversight is not required: tier is " + tier
    if ca is False:
        return "oversight is not required: consequential_actions is false"
    if tier is None:
        return "tier is not declared"
    if ca is None:
        return "tier is eio.tier.high and consequential_actions is not declared"
    return "tier is eio.tier.high, consequential_actions is true and human_oversight is " + ("not declared" if ho is None else json.dumps(ho))


def _gate_recurrence(w, rec, row):
    ids = row["claim_ids"]
    _need(isinstance(ids, list))
    if not ids:
        _need(row["met"] in (None, True))
        return "no reliability trials were run" if row["met"] is None else "no finding on a HARD_BLOCK obligation reproduced in every re-test pass"
    _need(row["met"] is False)
    claim = {c["id"]: c for c in rec["claims"]}
    trial = {t["claim_id"]: t for t in rec["reliability"]["recurrence"]}
    facts = [(_s(x), _s(claim[x]["predicate"]), _i(claim[x]["turn_indices"][0]), _i(trial[x]["reproduced_in"]),
              _i(trial[x]["retests"])) for x in ids]
    if len(facts) <= CLAUSES:
        text = "; ".join(f"claim {x} ({p}, turn {t}) reproduced in {r} of {n} re-test passes" for x, p, t, r, n in facts)
    else:
        order, turns_of = [], {}
        for _, p, t, r, n in facts:
            if (p, r, n) not in turns_of:
                order.append((p, r, n))
                turns_of[(p, r, n)] = []
            turns_of[(p, r, n)].append(t)
        clauses = [f"{_n(len(turns_of[k]), 'claim', 'claims')} of {k[0]} ({_turns(turns_of[k])}) reproduced in {k[1]} of {k[2]} "
                   "re-test passes" for k in order]
        text = "; ".join(clauses[:CLAUSES]) + (f" and {len(clauses) - CLAUSES} more" if len(clauses) > CLAUSES else "")
    return text + " on a HARD_BLOCK obligation"


def _gate_adjudication(w, rec, row):
    status = [(c.get("review") or {}).get("status") for c in w.cases]
    pending = [s for s in status if s != "adjudicated"]
    if not pending:
        return f"all {len(status)} reference cases are adjudicated"
    return (f"{len(pending)} of {len(status)} reference cases are not adjudicated (review status "
            + ", ".join(sorted({s or "unknown" for s in pending})) + ")")


GATE_TEXT = {"eio.gate.coverage-complete": _gate_coverage, "eio.gate.evidence-sufficient": _gate_evidence,
             "eio.gate.evaluator-calibrated": lambda w, rec, row: "the archive carries no calibration result against adjudicated reference cases",
             "eio.gate.reproducible": _gate_reproducible, "eio.gate.human-oversight-declared": _gate_oversight,
             "eio.gate.no-critical-recurrence": _gate_recurrence, "eio.gate.independent-adjudication": _gate_adjudication}


def _score(value):
    return str(Decimal(repr(q4(value))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _decisive(rec, row, field):
    kind, rid = _s(row["kind"]), _s(row["id"])
    if kind == "review_guard" and rid == "eio.release.high-review-queue":
        return ("no unresolved HIGH or CRITICAL findings" if field == "expected" else
                f"{len(row['finding_ids'])} unresolved HIGH or CRITICAL finding(s)")
    if kind == "review_guard" and rid == "eio.release.default-readiness-floor":
        if field == "expected":
            return "readiness >= 85.0"
        value = ((rec.get("scores") or {}).get("readiness") or {}).get("value")      # a null score block: withheld
        return "withheld" if value is None else _score(_f(value))
    if kind == "review_guard" and rid == "eio.release.hard-block-unmet":
        return ("0" if field == "expected" else
                str(len(row['obligation_ids'])))
    if kind == "cap":
        claim = {c["id"]: c for c in rec["claims"]}
        return ("no deterministic, witnessed APPLICABLE_FAIL on a cap predicate" if field == "expected" else
                ", ".join(f"{_s(claim[x]['predicate'])} at turn {_i(claim[x]['turn_indices'][0])}" for x in row["claim_ids"]))
    if kind == "metric_floor":
        fl = [x for x in rec["release_recommendation"]["metric_floors"] if x["metric"] == row["metric"]][0]
        return f">= {_f(fl['floor'])}" if field == "expected" else _score(_f(fl["observed"]))
    fixed = {"profile.prohibited_use_case": ("use case not prohibited", "prohibited use case"),
             "profile.signoff_required": ("human sign-off recorded", "not recorded")}
    if rid in fixed:
        return fixed[rid][field == "observed"]
    rule = [x for x in rec["release_recommendation"]["policy"]["rules"] if x["rule"] == rid][0]
    if rid == "profile.min_score":
        if field == "expected":
            return ">= " + _score(_f(rule["expected"]))
        if rule["result"] == "not_evaluated":
            return "not evaluated"
        return "null" if rule["observed"] is None else _score(_f(rule["observed"]))
    _need(rid.startswith("profile.block_on_"))
    return ("0 findings with severity >= " + rid[len("profile.block_on_"):].upper()) if field == "expected" else str(_i(rule["observed"]))


def _decisive_entry(rec, row):
    rid, kind = _s(row["id"]), row["kind"]
    if kind == "cap":
        first = [c for c in rec["claims"] if c["id"] == row["claim_ids"][0]][0]
        text = f"{rid} (claim {_s(first['id'])}, turn {_i(first['turn_indices'][0])})"
    elif kind == "metric_floor":
        text = f"{rid} ({_s(row['metric'])} {_decisive(rec, row, 'observed')} < {_decisive(rec, row, 'expected').split()[-1]})"
    elif rid.startswith("profile.block_on_"):
        text = f"{rid} ({_decisive(rec, row, 'observed')} findings)"
    else:
        text = f"{rid} (expected {_decisive(rec, row, 'expected')}, observed {_decisive(rec, row, 'observed')})"
    return text + (" -> REVIEW" if row["effect"] == "REVIEW" else "")


def _ledger_bound(w, rec, row, v):
    """None when the recurrence row's ledger key `v` (the producer's trial-ledger key: the record has no other copy of
    its label) is a library label or a fingerprint, a legacy check name and the row's claim's first turn, else why not."""
    m = LEDGER.fullmatch(v)
    claims = [c for c in rec["claims"] if c["id"] == row["claim_id"]]
    if not m or len(claims) != 1:
        return "not the ledger key of a claim of the record"
    c = claims[0]
    if not (FP.fullmatch(m["label"]) or m["label"] in w.labels):
        return "a ledger key over a clear label outside the trap library"
    if m["check"] not in w.checks or m["turn"] != str(_i(c["turn_indices"][0])):
        return "a ledger key over a check outside the release or another turn than its claim's"
    return None


def _finding_ledger(rec, f):
    trial = {t["claim_id"]: t for t in rec["reliability"]["recurrence"]}
    band = {x: (trial[x]["band"] if x in trial else "NOT_RETESTED") for x in f["claim_ids"]}
    weakest = None
    for x in f["claim_ids"]:                         # the first claim of the weakest band
        if weakest is None or BANDS.index(band[x]) < BANDS.index(band[weakest]):
            weakest = x
    _need(weakest is not None and band[weakest] != "NOT_RETESTED")
    return _s(trial[weakest]["ledger_key"])


def _formula(st):
    inp = st["inputs"]
    if "files_searched" in inp:
        return "count(term in casefold(file) for file in files_searched for term in requires_any)"
    cf = _s(inp["source"])
    if "name_contains" in inp:
        return "count(call for t in episode_turns for call in " + cf + "[t] if any(p in call.name.lower() for p in name_contains))"
    return cf + "[t] is non-empty" if "snapshot_sha256" in inp else "len(" + cf + "[t])"


def _label(f):
    if f["kind"] == "CONTEXT_GAP":
        return f"ctx · {_s(f['criterion']).replace('eio.context.', '')} / {_s(f['control'])}"
    return f"t{_i(f['turn_indices'][0]):02d} · {_s(f['predicate']).replace('eio.predicate.', '')}"


CAVEAT_BY_ID = {"per.caveat.domain.default": "No domain was identified; domain-specific risk is UNTESTED, not absent.",
                "per.caveat.tier.unknown": "No tier was declared; the tier is unknown and is never assumed to be minimal."}


def expected_text(w, rec, path):
    """The text the record's own rows give at `path` (a rebuilt renderer), else Unrendered (or a lookup error)."""
    g = gen(path)
    rr = rec.get("release_recommendation") or {}
    if g == ("release_recommendation", "gate_results", "*", "explanation", "params", "reason"):
        row = rr["gate_results"][path[2]]
        return GATE_TEXT[row["gate"]](w, rec, row)
    if g in (("release_recommendation", "decisive", "*", "expected"), ("release_recommendation", "decisive", "*", "observed")):
        return _decisive(rec, rr["decisive"][path[2]], g[-1])
    if g == ("release_recommendation", "explanation", "params", "decisive_list", "*"):
        return _decisive_entry(rec, rr["decisive"][path[4]])
    if g == ("findings", "*", "recurrence", "ledger_key"):
        return _finding_ledger(rec, rec["findings"][path[1]])
    if g == ("findings", "*", "display_label"):
        return _label(rec["findings"][path[1]])
    if g == ("evidence", "refs", "*", "statement", "formula"):
        return _formula(rec["evidence"]["refs"][path[2]]["statement"])
    if g == ("header", "per_semantics_version"):
        h = rec["header"]
        return "2@" + _s(h["converter"]["version"]) + "+eio" + _s(h["eio"]["release"]) + "." + _s(h["eio"]["ontology_digest"])
    if g == ("scope", "caveats", "*", "text"):
        return CAVEAT_BY_ID[rec["scope"]["caveats"][path[2]]["id"]]
    raise Unrendered                                 # the unused contributing / policy rule expected|observed slots


def _matches(w, rec, path, v):
    try:
        return expected_text(w, rec, path) == v
    except (Unrendered, KeyError, IndexError, TypeError, AttributeError, ValueError, ArithmeticError):
        return False


def _rendered(w, arg, v, rec, path, cat):
    if arg == "summary":
        return None                              # checked by X1's display rule
    if arg == "ledger_key" and gen(path) == ("reliability", "recurrence", "*", "ledger_key"):
        try:
            return _ledger_bound(w, rec, rec["reliability"]["recurrence"][path[2]], v)
        except (Unrendered, KeyError, IndexError, TypeError, AttributeError):
            return "not the ledger key of a claim of the record"
    if arg in ("converter", "ledger_key", "formula", "display_label", "semantics", "caveat"):
        return None if _matches(w, rec, path, v) else "not the exact rendering of its record rows"
    if arg == "via":
        m = VIA_LINK.fullmatch(v)
        if m:
            return None if _via_ok(w, m["key"]) and m["control"] in w.checklist.get(m["criterion"], ()) else "a via outside the release"
        m = VIA_CRITERION.fullmatch(v)
        return None if m and m["control"] in w.checklist.get(m["criterion"], ()) else "not a via to a checklist control"
    if arg == "limitation":
        row = rec["limitations"][path[1]]
        c = cat.get(row.get("limitation_id")) or {}
        t = c.get(path[2]) if isinstance(c, dict) else None
        if not isinstance(t, str):
            return "not a limitation of the catalogue"
        parts = list(string.Formatter().parse(t))
        rx = "".join(re.escape(literal) + ("(.+?)" if name is not None else "")
                     for literal, name, _, _ in parts)
        m = re.fullmatch(rx, v, re.S)
        return None if m is not None and all(_safe_param(w, x) for x in m.groups()) else "not its limitation's catalogue text with sealed parameters"
    return f"the unknown renderer {arg}"


def fits(w, spec, v, rec, path, cat):
    """None when the string `v` fits its class `spec`, else why not."""
    c, arg = spec
    if c == "a":
        if arg == "component_id":
            ok = v in w.vocab or v in COMPONENTS or (
                rec["scores"]["axes"][path[2]]["axis"] == "eio.axis.governance" and v in PUBLIC_G_IDS)
        else:
            ok = {"vocab": v in w.vocab, "check_name": v in w.checks, "metric_key": v in w.metric_keys,
                  "contract_token": bool(CONTRACT.fullmatch(v)), "profile_rule": bool(RULE.fullmatch(v)),
                  "decisive_id": v in w.vocab or bool(RULE.fullmatch(v)) or
                  (rec["header"]["per_version"] == "2.1.0" and v in REVIEW_GUARDS),
                  "caveat_id": v in CAVEAT_IDS}.get(arg)
        return None if ok else "not a member of its vocabulary"
    if c == "b":
        if arg == "legacy_profile_id":
            return None if rec["header"]["per_version"] == "2.0.0-rc1" and v == "harness-2.x" else "not the reviewed rc1 scoring-profile id"
        if arg == "profile_id":
            pair = (v, rec["scores"]["scoring_profile"]["version"])
            return None if pair in PUBLIC_PROFILES else "not a reviewed public scoring-profile id/version pair"
        if arg == "profile_version":
            pair = (rec["scores"]["scoring_profile"]["id"], v)
            return None if pair in PUBLIC_PROFILES else "not a reviewed public scoring-profile id/version pair"
        return None if FORM[arg].fullmatch(v) else f"not of the form {arg}"
    if c == "c":
        return None
    if v == "" and c in ("d", "ad", "bd", "md"):
        return None
    if c == "d":
        return None if FP.fullmatch(v) else "not a fingerprint (clear text in a withheld field)"
    if c == "md":
        return None if FP.fullmatch(v) or decide_row(w, spec, v, rec, path) == v else \
            "neither the model identifier of the model row nor a fingerprint"
    if c == "ad":
        return None if FP.fullmatch(v) or is_member(w, arg, v) else "a clear non-member (neither vocabulary nor a fingerprint)"
    if c == "bd":
        safe = safe_model_identifier(v) if arg == "model" else STRICT[arg].fullmatch(v)
        return None if FP.fullmatch(v) or safe else f"neither of the strict form {arg} nor a fingerprint"
    if c == "r":
        return _rendered(w, arg, v, rec, path, cat)
    return f"the unknown class {c}"


def record_problems(rec, e, cat):
    """T1-T3 on the record alone: every member name is vocabulary, every string path is in the table (closed world) and
    its value fits its class; a `sha256-` value occurs only where its class allows it."""
    w, p = words(e), []
    for path, k in members(rec):
        if k not in w.names:
            p.append(f"{ptr(path)}: member name {k!r:.60} is not vocabulary (T1)")
    for path, v in strings(rec):
        spec = TABLE.get(gen(path))
        if spec is None:
            p.append(f"{ptr(path)}: unclassified text field {'.'.join(gen(path))} (T1)")
            continue
        why = fits(w, spec, v, rec, path, cat)
        if why:
            p.append(f"{ptr(path)} ({spec[0]}{':' + spec[1] if spec[1] else ''}): {why} (T2)")
        elif spec[0] in ("a", "b") and "sha256-" in v:
            p.append(f"{ptr(path)}: a fingerprint in a {spec[0]} field (T3)")
    return p


# ---------------------------------------------------------------------------------------------------------------- bundle
def bundle_texts(B):
    """{fingerprint: [(bundle path, text)]} of every string of the bundle, member names included (a member name at the
    path of its object plus '{name}')."""
    out, stack = {}, [(B, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                out.setdefault(fingerprint(k), []).append((p + ("{name}",), k))
                stack.append((v, p + (k,)))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in enumerate(o))
        elif isinstance(o, str):
            out.setdefault(fingerprint(o), []).append((p, o))
    return out


def _bgen(path):
    out = []
    for x in path:
        if type(x) is int:
            out.append("*")
        elif tuple(out) in (("scope", "facts"), ("trials", "named_lists"), ("producer_declared", "context_links", "claims"),
                            ("limitations", "*", "params"), ("sources", "archive_pointer")):
            out.append("<key>")
        else:
            out.append(x)
    return tuple(out)


def _at_source(cands, sources):
    """The first candidate (bundle path, text) whose generalized path is one of `sources`."""
    for bp, t in cands:
        if _bgen(bp) in sources:
            return bp, t
    return None


def withheld(rec):
    """[(record path, fingerprint, spec)] of every fingerprint the record carries: a (d), (a|d) or (b|d) value, and a
    fingerprint inside a via, a ledger key, a formula or a limitation text (display forms inside summaries resolve through
    their explanation's params)."""
    out = []
    for path, v in strings(rec):
        spec = TABLE.get(gen(path))
        if spec is None:
            continue
        if spec[0] in ("d", "ad", "bd", "md") and FP.fullmatch(v):
            out.append((path, v, spec))
        elif spec[0] == "r" and spec[1] in ("via", "ledger_key", "formula", "limitation"):
            out.extend((path, m.group(), spec) for m in FP_IN_TEXT.finditer(v) if len(m.group()) == 71)
    return out


def resolve(rec, B):
    """[{record_pointer, fingerprint, bundle_pointer, text}] for every withheld value of the record, from the bundle `B`
    (a dict): found at its field's source path (`SOURCES`), else anywhere in the bundle by content address. A fingerprint
    that no bundle text gives has `bundle_pointer` and `text` None."""
    texts, out = bundle_texts(B), []
    for path, v, spec in withheld(rec):
        cands = texts.get(v) or []
        src = SOURCES.get(gen(path)) or (TEXT_SOURCES.get(spec[1]) if spec[0] == "r" else None) or ()
        hit = _at_source(cands, src) or (cands[0] if cands else None)
        out.append({"record_pointer": ptr(path), "fingerprint": v, "bundle_pointer": ptr(hit[0]) if hit else None,
                    "text": hit[1] if hit else None})
    return out


def clear_view(rec, B):
    """A copy of the record with every withheld value replaced by its bundle text (the lists the converter sorts sorted
    again by the clear text) and [problems]: a fingerprint that no text at its field's source paths gives, or an (a|d) or
    (b|d) decision that does not recompute from that text."""
    import copy
    texts, p = bundle_texts(B), []
    view = copy.deepcopy(rec)
    clear = {}
    for path, v in strings(rec):
        spec = TABLE.get(gen(path))
        if spec is None or spec[0] not in ("d", "ad", "bd", "md", "r"):
            continue
        if spec[0] == "r":
            for m in FP_IN_TEXT.finditer(v):
                fp = m.group()
                if len(fp) != 71:
                    continue
                cands = texts.get(fp) or []
                if spec[1] == "limitation":
                    lid = rec["limitations"][path[1]]["limitation_id"]
                    matching = {i for i, x in enumerate(B.get("limitations", [])) if x.get("id") == lid}
                    found = any(len(bp) >= 4 and bp[0] == "limitations" and bp[1] in matching and bp[2] == "params"
                                for bp, _ in cands)
                else:
                    src = TEXT_SOURCES.get(spec[1]) or ()
                    found = _at_source(cands, src) is not None if src else bool(cands)
                if not found:
                    p.append(f"{ptr(path)}: rendered fingerprint {fp[:19]}… is not bound to its bundle source (T4)")
            if spec[1] in ("via", "ledger_key", "formula"):
                new = FP_IN_TEXT.sub(lambda m: (texts.get(m.group()) or [(None, m.group())])[0][1] if len(m.group()) == 71 else m.group(), v)
                if new != v:
                    _put(view, path, new)
            continue
        if not FP.fullmatch(v):
            continue
        cands = texts.get(v) or []
        src = SOURCES.get(gen(path)) or ()
        hit = _at_source(cands, src) if src else (cands[0] if cands else None)
        if hit is None:
            p.append(f"{ptr(path)}: the fingerprint {v[:19]}… is the fingerprint of no text at its source field "
                     f"({' or '.join('.'.join(s) for s in src) or 'the bundle'}) (T4)")
            continue
        _put(view, path, hit[1])
        clear[path] = hit[1]
    for path in _sorted_lists(view):
        lst = _get(view, path)
        if all(isinstance(x, str) for x in lst):
            lst.sort()
    return view, p, clear


def _put(doc, path, v):
    for x in path[:-1]:
        doc = doc[x]
    doc[path[-1]] = v


def _get(doc, path):
    for x in path:
        doc = doc[x]
    return doc


def _sorted_lists(doc):
    out, stack = [], [(doc, ())]
    while stack:
        o, q = stack.pop()
        if isinstance(o, dict):
            stack.extend((v, q + (k,)) for k, v in o.items())
        elif isinstance(o, list):
            if gen(q) in RESORTED:
                out.append(q)
            else:
                stack.extend((v, q + (i,)) for i, v in enumerate(o))
    return out


def decision_problems(rec, clear, e):
    """T4: each withheld or decided field of the record is the converter's decision over its clear text (`clear`: record
    path -> the bundle text its fingerprint resolved to)."""
    w, p = words(e), []
    for path, v in strings(rec):
        spec = TABLE.get(gen(path))
        if spec is None or spec[0] not in ("d", "ad", "bd", "md"):
            continue
        if not FP.fullmatch(v):
            if decide_row(w, spec, v, rec, path) != v:
                p.append(f"{ptr(path)}: a clear value the converter fingerprints (T4)")
        elif path in clear and decide_row(w, spec, clear[path], rec, path) != v:
            p.append(f"{ptr(path)}: the decision over its clear text does not recompute (a vocabulary member fingerprinted) (T4)")
    return p


# record fields copied from one bundle field in order (the record's provenance is the bundle's `provenance.record`, its
# agent the bundle's `provenance.agent`, its capsule caveats and scope facts the bundle's): the index or key of the record
# path is the index or key of the source path
PARALLEL = frozenset(tuple(x.split(".")) for x in (
    "subject.agent.goal", "subject.agent.role", "subject.agent.business_case", "subject.agent.class", "subject.agent.agent_id",
    "subject.agent.model", "subject.agent.version", "provenance.capsule.caveats.*", "provenance.harness_llm.primary.model",
    "provenance.harness_llm.fallback.model", "provenance.harness_llm.consensus.personas.*", "provenance.harness_llm.consensus.strategy",
    "provenance.inputs.context_artifacts.*.name", "provenance.inputs.governance_profile.name", "release_recommendation.policy.name",
    "provenance.producer.name", "provenance.producer.version", "provenance.producer.harness_version", "provenance.producer.patch_digest",
    "provenance.producer.revision", "provenance.harness_llm.per_stage.*.model",
    "provenance.producer.source_format", "provenance.inputs.traps.selected.*", "scope.facts.<key>.source",
    "evidence.archive_pointer.<key>"))


def _concrete(src, g, rpath):
    """The concrete bundle path of the source template `src` for the record path `rpath` (generalized `g`): each wildcard
    of the source takes the index or key at the record's wildcard of the same rank."""
    vals = [x for x, y in zip(rpath, g) if y in ("*", "<key>")]
    out, i = [], 0
    for t in src:
        if t in ("*", "<key>"):
            if i >= len(vals):
                return None
            out.append(vals[i])
            i += 1
        else:
            out.append(t)
    return tuple(out)


def singleton_problems(rec, B, e):
    """T4 for the fields copied from one bundle field (`PARALLEL`): the record value is the decision over the text of the
    first source that the bundle holds."""
    w, p = words(e), []
    for path, v in strings(rec):
        g = gen(path)
        if g not in PARALLEL:
            continue
        for src in SOURCES[g]:
            q = _concrete(src, g, path)
            try:
                text = _get(B, q) if q is not None else None
            except (KeyError, IndexError, TypeError):
                text = None
            if isinstance(text, str):
                if v != decide(w, TABLE[g], text):
                    p.append(f"{ptr(path)}: not the decision over the bundle's text at {ptr(q)} (T4)")
                break
    return p


def identity_source_problems(rec, B, e):
    """T4: an indexed claim/score source must match the record row's stable id, not another row in its family."""
    w, p = words(e), []
    claims = {x.get("id"): x for x in B.get("claims", []) if isinstance(x, dict)}
    for row in rec.get("claims", []):
        original = claims.get(row.get("id"))
        if original is None:
            continue
        source = (original.get("provenance") or {}).get("model")
        if isinstance(source, str) and row.get("provenance", {}).get("model") != fingerprint(source):
            p.append(f"/claims/{row.get('id')}/provenance/model: not bound to the matching claim (T4)")

    score_inputs = (B.get("producer_declared") or {}).get("score_inputs") or {}
    metrics = {x.get("id"): x for x in score_inputs.get("metrics", []) if isinstance(x, dict)}
    scores = rec.get("scores") or {}
    declared_profile = score_inputs.get("profile") or {}
    record_profile = scores.get("scoring_profile") or {}
    if isinstance(record_profile, str):
        if not (rec.get("header", {}).get("per_version") == "2.0.0-rc1"
                and record_profile == "harness-2.x" and isinstance(declared_profile, dict)
                and declared_profile.get("id") == record_profile):
            p.append("/scores/scoring_profile: not bound to the declared rc1 scoring profile (T4)")
    elif scores.get("kind") in ("reference-draft", "reference") and isinstance(record_profile, dict):
        # Native draft profile identity is pinned and checked by independent
        # D4, not supplied by legacy producer_declared.score_inputs.
        pass
    elif isinstance(record_profile, dict) and record_profile:
        for key in ("id", "version", "sha256"):
            if record_profile.get(key) != declared_profile.get(key):
                p.append(f"/scores/scoring_profile/{key}: not bound to the declared scoring profile (T4)")
        document = declared_profile.get("document")
        if isinstance(document, dict):
            digest = sha(jb({k: v for k, v in document.items() if k != "sha256"}))
            if record_profile.get("sha256") != digest:
                p.append("/scores/scoring_profile/sha256: not the declared profile document digest (T4)")
            allowed_g = set(document.get("g_component_ids") or ())
            for axis in scores.get("axes", []):
                if axis.get("axis") == "eio.axis.governance":
                    for component in axis.get("components", []):
                        if component.get("id") not in allowed_g:
                            p.append("/scores/axes/G/components/id: not declared by the scoring profile document (T4)")
    elif record_profile:
        p.append("/scores/scoring_profile: unsupported scoring-profile shape (T4)")
    for row in scores.get("metrics", []):
        original = metrics.get(row.get("metric"))
        if original is None:
            continue
        params = row.get("explanation", {}).get("params", {})
        for field, source in (("metric", original.get("label") or row.get("metric")),
                              ("reason", original.get("not_evaluated_reason"))):
            if field in params and isinstance(source, str) and params[field] != decide(w, TABLE[("scores", "metrics", "*", "explanation", "params", field)], source):
                p.append(f"/scores/metrics/{row.get('metric')}/explanation/params/{field}: not bound to the matching metric (T4)")
    axes = {x.get("axis"): x for x in score_inputs.get("axes", []) if isinstance(x, dict)}
    for row in scores.get("axes", []):
        original = axes.get(row.get("axis"))
        if original is None:
            continue
        params = row.get("explanation", {}).get("params", {})
        source_params = original.get("explanation", {}).get("params", {})
        for field in ("axis", "lowest", "lowest_metric", "lowest_rule", "reason"):
            source = source_params.get(field)
            if field in params and isinstance(source, str) and params[field] != decide(w, TABLE[("scores", "axes", "*", "explanation", "params", field)], source):
                p.append(f"/scores/axes/{row.get('axis')}/explanation/params/{field}: not bound to the matching axis (T4)")
    return p


def _in_clear(path):
    """Whether a bundle string reaches a record in clear: not a context text, turn text or state, tool-call value, or
    retrieval body (the verifier's reading of the projector's rule)."""
    if path == ("bundle_version",):           # the bundle format version (a schema constant) never reaches a record
        return False
    if path[:2] == ("sources", "context_texts") and len(path) >= 3:
        return False
    if path[:2] == ("sources", "turns") and len(path) >= 4:
        if path[3] in ("question", "answer", "state"):
            return False
        if path[3] == "tool_calls" and len(path) >= 6 and path[5] in ("arguments", "result"):
            return False
        if path[3] == "retrievals" and len(path) >= 6 and path[5] != "source":
            return False
    return True


def _public(w, s):
    if s in COMPONENTS | PUBLIC_G_IDS | PUBLIC_PROFILE_IDS | PUBLIC_PROFILE_VERSIONS or CONTRACT.fullmatch(s) or RULE.fullmatch(s):
        return True
    for rx in RECIPES:
        m = rx.fullmatch(s)
        if m:
            return "cf" not in rx.groupindex or m["cf"] in w.layout
    m = LEDGER.fullmatch(s)
    if m:
        return m["label"] in w.labels and m["check"] in w.checks
    m = VIA_LINK.fullmatch(s) or VIA_CRITERION.fullmatch(s)
    if m:
        key = m.groupdict().get("key")
        return (key is None or _via_ok(w, key)) and m["criterion"] in w.vocab and m["control"] in w.vocab
    return False


def clear_text_problems(rec, B, e):
    """T5: no record string outside the excerpt equals, as a whole value, a producer text of the bundle in clear (a string
    a record could carry in clear that is not vocabulary, a structural form or a short number)."""
    w = words(e)
    prod, stack = set(), [(B, ())]
    while stack:
        o, q = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if _in_clear(q + (None,)):
                    prod.add(k)
                stack.append((v, q + (k,)))
        elif isinstance(o, list):
            stack.extend((v, q + (i,)) for i, v in enumerate(o))
        elif isinstance(o, str) and _in_clear(q):
            prod.add(o)
    prod = {s for s in prod if s not in w.every and not any(f.fullmatch(s) for f in FORM.values()) and not NUMBER.fullmatch(s)
            and not _public(w, s)}
    def released(path, v):                        # a model identifier kept in clear by its class (b|d, m|d)
        spec = TABLE.get(gen(path)) or ("?", None)
        return spec[0] in ("bd", "md") and spec[1] == "model" and decide_row(w, spec, v, rec, path) == v
    return [f"{ptr(path)}: a producer text of the bundle in clear (T5)" for path, v in strings(rec)
            if v in prod and (TABLE.get(gen(path)) or ("?",))[0] != "c" and not released(path, v)]


LINK_VIA = "eio.graph.context-links:{key}→{criterion}/{control}"


def rendered_source_problems(rec, B, e):
    """T4 for the rendered texts: each rebuilt gate reason equals the record's, with the evidence gate's metrics named by
    the decision over the bundle's label of the same metric (not any text of the bundle); each recurrence row's ledger key
    is the sealed key of the bundle's trial record of the same claim (the last record of a claim, as the converter reads
    it); each via of a declared context link is the link of a declared row, its key decided as the record decides it."""
    w, p = words(e), []
    score_inputs = (B.get("producer_declared") or {}).get("score_inputs") or {}
    source = {x.get("id"): x for x in score_inputs.get("metrics") or [] if isinstance(x, dict)}

    def from_bundle(m):
        mid = _s(m["metric"])
        text = (source.get(mid) or {}).get("label") or mid
        return decide(w, ("ad", "release"), _s(text))
    for i, row in enumerate((rec.get("release_recommendation") or {}).get("gate_results") or []):
        reason = ((row.get("explanation") or {}).get("params") or {}).get("reason")
        try:
            want = (_gate_evidence(w, rec, row, from_bundle) if row.get("gate") == "eio.gate.evidence-sufficient"
                    else GATE_TEXT[row["gate"]](w, rec, row))
        except (Unrendered, KeyError, IndexError, TypeError, AttributeError, ValueError, ArithmeticError):
            want = None
        if reason != want:
            p.append(f"/release_recommendation/gate_results/{i}/explanation/params/reason: not the rendering of its record rows "
                     "and its metrics' bundle labels (T4)")
    trials = {x.get("claim_id"): x for x in (B.get("trials") or {}).get("records") or [] if isinstance(x, dict)}
    for i, row in enumerate((rec.get("reliability") or {}).get("recurrence") or []):
        src = (trials.get(row.get("claim_id")) or {}).get("ledger_key")
        m = LEDGER.fullmatch(src) if isinstance(src, str) else None
        want = f"{m['label'] if m['label'] in w.labels else fingerprint(m['label'])}::{m['check']}@{m['turn']}" if m else None
        if isinstance(row.get("ledger_key"), str) and row["ledger_key"] != want:
            p.append(f"/reliability/recurrence/{i}/ledger_key: not the sealed ledger key of the bundle's trial record of its claim (T4)")
    links = ((B.get("producer_declared") or {}).get("context_links") or {}).get("rows") or {}
    declared = {LINK_VIA.format(key=key if (key in w.labels or key in w.checks or key in w.vocab) else fingerprint(key),
                                criterion=r.get("criterion"), control=r.get("control"))
                for key, rows in links.items() for r in rows or [] if isinstance(r, dict)}
    for path, v in strings(rec):
        if TABLE.get(gen(path)) == ("r", "via") and VIA_LINK.fullmatch(v) and v not in declared:
            p.append(f"{ptr(path)}: the via is not the link of a declared context-link row of the bundle (T4)")
    return p


def bundle_problems(rec, B, e):
    """T4 and T5 (with the bundle) and the record's clear view for D2: (problems, view)."""
    view, p, clear = clear_view(rec, B)
    p += decision_problems(rec, clear, e) + singleton_problems(rec, B, e) + identity_source_problems(rec, B, e) + clear_text_problems(rec, B, e)
    p += rendered_source_problems(rec, B, e)
    return p, view
