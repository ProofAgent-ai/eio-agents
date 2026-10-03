"""The closed record-field table (owner decisions #31 and #32, step L3s): no producer free text reaches a record in clear.

Every string of a projected record, member names included, is one of:
  a   vocabulary: a string the loaded EIO release publishes (`bundle.release_strings`), a string constant of the PER rc1 or
      bundle schema (an enum or const member), a member name of either schema or an rc1 layout token (`transcript`,
      `tools_called`, `memory_snapshot`), or an EIO-Agents constant; some fields name a narrower vocabulary (the legacy
      check names and legacy metric keys of the release) or a closed form of the rc1 schema (contract tokens, profile rule
      ids); a value outside it fails closed (`BUNDLE_VOCABULARY`);
  b   a structural value of one recorded form (an id, a digest, a version, a run id, a timestamp, a pointer), recomputed
      by the converter or declared by the producer and form-checked only (ACCEPTED_DEVIATIONS D-53, until S2);
  c   the PROD-42 excerpt of a ref (`evidence.refs[].excerpt`: D-43, D-48, D-56, unchanged);
  d   a fingerprint of the exact producer text: `sha256-` and the 64 lower-case hex digits of SHA-256 over its UTF-8 bytes
      (`fingerprint`), with no normalization; the same text gives the same value in every field, so the record's joins
      hold; plain SHA-256 until the keyed form before the first upload (decision #32);
  a|d a vocabulary member in clear, any other value as its fingerprint (decided per value: a trap-library label, a release
      checklist term or title, a layout token);
  b|d a strict version in clear, any other value as its fingerprint (a producer or agent version); `bd:model` a model
      identifier (`bundle.MODEL_ID`) in clear, any other value as its fingerprint (the agent's, a jury's, the harness
      LLM's model; 0.8.0, approved by the maintainer);
  m|d the agent model's AI-BOM row: its name as `bd:model`, any other row's name (a file) as its fingerprint;
  r   a text the converter renders (a release template of `eio.template.why`, the limitation catalogue, a converter
      recipe) over record values of the classes above; a fingerprint shows in a summary in its display form, `sha256-`
      and its first 12 hex digits (`display`), the full value staying in the explanation's params. `problems` rebuilds
      each rendered text from the record's own rows (`rendered_text`; a summary from its params) and requires byte
      equality; a limitation text, a via and a recurrence row's ledger key, whose parameters, link key or ledger label
      the record does not keep, are closed productions bound to their own rows (`_rendered_problem`).
`TABLE` lists every generalized record path (a list index as `*`, the member of an open map as `<key>`) with its class;
a path it does not list fails closed (`PRIVACY_UNCLASSIFIED`), and so does a member name outside the vocabulary.

`seal(eio, rec)` applies the table to a projected record (fingerprints, per-value decisions, the rendered texts that
carry a sealed value re-rendered, the lists the converter sorts re-sorted by their record values); `problems(eio, rec,
producer)` then asserts it: every value fits its class, and no string outside the excerpt equals a producer text of the
bundle in clear (`producer_texts`: `PRIVACY_CLEAR_TEXT`). `seal_params` seals a limitation's parameters before the
catalogue renders them. Content addresses (ref ids, span and argument digests) stay over the clear bundle, as before; a
behavioural finding's fingerprint takes its scenario label's record value (`label_value`). The round 2-4 pattern rules
(`bundle.Withheld`, `bundle.shape_problems`) stay as a second layer. The record carries no pointer: a fingerprint is
resolved only locally, from the bundle (`eio_agents.resolve`). The verifier's twin of this table is
`eio_agents.validation.privacy` (contract P3: no shared code).
"""
import ast
import hashlib
import re
import string
import weakref

from eio_agents.base.errors import ConversionError, require
from eio_agents.per import bundle as B
from eio_agents.per.catalogue_split import load_core_limitations, merge_catalogues
from eio_agents.schemas import bundle_schema, per_schema
from eio_agents.semantics import why
from eio_agents.semantics.release import GATE_CLAUSES_MAX, oversight_gate
from eio_agents.semantics.scope import CAVEATS

PREFIX = "sha256-"
FINGERPRINT = re.compile(r"sha256-[0-9a-f]{64}")
DISPLAY_LENGTH = 19                                  # 'sha256-' and 12 hex digits: a fingerprint inside a rendered text
LAYOUT_TOKENS = ("transcript", "tools_called", "memory_snapshot")         # the rc1 layout tokens the rc1 patterns fix
# member names that are EIO-Agents constants: the statement inputs of the converter's recipes, and a native producer's
# fields of split plan §5.3 N8 (`data/rc1_only.json`)
CONVERTER_NAMES = frozenset(("episode_turns", "name_contains", "snapshot_sha256", "name", "version", "kind", "revision",
                             "source_format"))
# open maps of the record: a member name is data (a fact id, a module id, a list name, a state), one table row for all
OPEN_MAPS = frozenset((("scope", "facts"), ("header", "eio", "modules"), ("reliability", "named_lists"),
                       ("scope", "escalations", "*", "promote"), ("scope", "escalations", "*", "when"),
                       ("coverage", "obligations", "*", "explanation", "params", "required_text")))
ARCHIVE_POINTER, ARCHIVE_POINTER_FIXED = ("evidence", "archive_pointer"), frozenset(("archive_sha256", "transcript"))
# the lists the converter sorts: sorted again by their record values, so the order does not reveal the clear text's order
SORTED_LISTS = frozenset(tuple(x.split(".")) for x in ("evidence.refs.*.statement.inputs.files_searched",
                                                        "findings.*.explanation.params.files", "findings.*.traps",
                                                        "findings.*.explanation.params.traps"))

_H = "[0-9a-f]"
VERSION = re.compile(r"(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){1,2}")      # b|d: a strict version stays in clear
FORMS_PACKAGE = re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?"
                           r"(\.dev(0|[1-9][0-9]*))?")                        # the rc1 package_version (a harness version)
BD_FORMS = {"version": VERSION, "digest": re.compile(r"sha256:[0-9a-f]{64}|[0-9a-f]{7,64}"), "package_version": FORMS_PACKAGE,
            "model": re.compile(B.MODEL_ID)}                  # b|d: a model identifier stays in clear (0.8.0)
MODEL_COMPONENT = "machine-learning-model"                    # m|d: the AI-BOM row whose name is a model identifier
FORMS = {                                                                     # b: the recorded forms (rc1 patterns)
    "id20": re.compile(f"{_H}{{20}}"),
    "hex16": re.compile(f"{_H}{{16}}"),
    "hex40": re.compile(f"{_H}{{40}}"),
    "hex64": re.compile(f"{_H}{{64}}"),
    "sha256": re.compile(f"sha256:{_H}{{64}}"),
    "lock_digest": re.compile(f"{_H}{{16}}|sha256:{_H}{{64}}"),
    "config_fingerprint": re.compile(f"{_H}{{8,64}}"),
    "checks_version": re.compile(f"{_H}{{7,40}}"),
    "semver": re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?"),
    "package_version": re.compile(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?"
                                  r"(\.dev(0|[1-9][0-9]*))?"),
    "run_id": re.compile(f"{_H}{{8}}-{_H}{{4}}-{_H}{{4}}-{_H}{{4}}-{_H}{{12}}|archive:{_H}{{64}}"),
    "timestamp": re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})"),
    "pointer": re.compile(r"(/([A-Za-z0-9_.:-]|~[01])+)+"),
    "arguments_pointer": re.compile(r"/(transcript/(0|[1-9][0-9]*)/tools_called|sources/turns/(0|[1-9][0-9]*)/tool_calls)"
                                    r"/(0|[1-9][0-9]*)/(arguments|args)"),
}
CONTRACT_TOKEN = re.compile(r"require_all:[A-Z_]+|require_any|group:[1-9][0-9]*|minimum_refs|scope|counterevidence|no_witnessing_ref")
PROFILE_RULE = re.compile(r"profile\.(prohibited_use_case|min_score|block_on_(critical|high|medium|low|informational)|signoff_required)")
COMPONENT_TOKENS = frozenset(("release_gate", "open_findings", "human_oversight", "compliance_scope", "evidence_freshness"))
APPROVED_PROFILE_IDS = frozenset(("harness-2.x", "eio-agents.reference-scoring"))
APPROVED_PROFILE_VERSIONS = frozenset(("2.1.0", "0.0.0-draft", "0.2.0-draft.1", "0.3.0-draft.1", "0.3.1-draft.1", "0.3.1"))
APPROVED_PROFILES = frozenset((("harness-2.x", "2.1.0"), ("eio-agents.reference-scoring", "0.0.0-draft"),
                               ("eio-agents.reference-scoring", "0.2.0-draft.1"),
                               ("eio-agents.reference-scoring", "0.3.0-draft.1"),
                               ("eio-agents.reference-scoring", "0.3.1-draft.1"),
                               ("eio-agents.reference-scoring", "0.3.1")))
# release semantics 2.2 review guards of a PER 2.1.0 record (owner decision #46 adds the two no-policy guards)
REVIEW_GUARD_IDS = frozenset(("eio.release.high-review-queue", "eio.release.default-readiness-floor",
                              "eio.release.hard-block-unmet"))
APPROVED_G_COMPONENTS = frozenset(("release_gate", "human_oversight", "policy_conformance", "obligation_coverage",
                                   "evidence_freshness", "prohibited_use_case"))
BASIS_PHRASE = re.compile(r"framework set of (eio\.region\.[a-z0-9-]+)")      # the converter's framework-selection basis
VIA_LINK = re.compile("eio\\.graph\\.context-links:(?P<key>[^→]+)→(?P<criterion>eio\\.context\\.[^/]+)/(?P<control>.+)")
VIA_CRITERION = re.compile(r"eio\.context\.criteria:(?P<criterion>[^/]+)/(?P<control>.+)")
LEDGER = re.compile(r"(?P<label>.+)::(?P<check>[a-z0-9_]+)@(?P<turn>[1-9][0-9]*)")
DISPLAY_LABEL = re.compile("t[0-9]{2,} · (?P<predicate>[a-z0-9][a-z0-9-]*)|ctx · (?P<criterion>[a-z0-9][a-z0-9-]*) / (?P<control>[a-z0-9][a-z0-9-]*)")
SEMANTICS = re.compile(r"2@(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*[+]eio(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                       r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?\.[0-9a-f]{16}")
FORMULAS = (re.compile(r"len\((?P<cf>[^\[\]()]+)\[t\]\)"),
            re.compile(r"count\(call for t in episode_turns for call in (?P<cf>[^\[\]()]+)\[t\] if any\(p in call\.name\.lower\(\) "
                       r"for p in name_contains\)\)"),
            re.compile(r"count\(term in casefold\(file\) for file in files_searched for term in requires_any\)"),
            re.compile(r"(?P<cf>[^\[\]()]+)\[t\] is non-empty"))
# a limitation parameter kept in clear: a structural form (an id, a digest, a version, a short number); else vocabulary
PARAM_FORM = re.compile(f"{_H}{{20}}|{_H}{{7,64}}|sha256:{_H}{{64}}|(0|[1-9][0-9]{{0,2}})(\\.(0|[1-9][0-9]{{0,2}})){{1,3}}"
                        r"(\.dev[0-9]+)?(\+[a-z]{1,16})?|-?(0|[1-9][0-9]{0,5})(\.[0-9]{1,4})?")
SHORT_NUMBER = re.compile(r"-?[0-9]{1,6}(\.[0-9]{1,4})?")

# ---------------------------------------------------------------------------------------------------------------- table
# class[:argument] then its generalized record paths. a:<vocabulary>, b:<form of FORMS>, c, d, ad:<vocabulary>,
# bd:version, bd:model, md:model, r:<renderer>. The twin `eio_agents.validation.privacy` holds its own copy (parity:
# tests/test_privacy.py).
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
    claims.*.parameters.fidelity
    claims.*.parameters.invalid_because
    claims.*.parameters.legacy_decided_by
    claims.*.parameters.mapping_relation
    claims.*.parameters.state_source
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
    findings.*.fidelity
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
    claims.*.parameters.scenario
    claims.*.parameters.trap
    evidence.turns.*.scenario
    evidence.turns.*.trap
    findings.*.scenarios.*
    findings.*.explanation.params.traps.*
    findings.*.traps.*
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


def parse_table(text):
    """{generalized path (a tuple): (class, argument)} from the table text."""
    out, cur = {}, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            c, _, arg = line.strip().partition(":")
            cur = (c, arg or None)
            continue
        path = tuple(line.strip().split("."))
        require(path not in out, "PRIVACY_UNCLASSIFIED", f"the field table lists {'.'.join(path)} twice")
        out[path] = cur
    return out


TABLE = parse_table(TABLE_TEXT)


def counts():
    """{class: number of value paths} of the table (the member-name rule is one more (a) rule)."""
    out = {}
    for c, _ in TABLE.values():
        out[c] = out.get(c, 0) + 1
    return out


# ---------------------------------------------------------------------------------------------------------------- values
def fingerprint(text):
    """`sha256-` + the hex SHA-256 of the exact UTF-8 bytes of `text` (no normalization)."""
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as e:                   # a lone surrogate: the bundle reader refuses it first
        raise ConversionError(f"PER_INVALID: a producer text has no UTF-8 form ({e.reason})", code="PER_INVALID") from e
    return PREFIX + hashlib.sha256(data).hexdigest()


def is_fingerprint(v):
    return isinstance(v, str) and FINGERPRINT.fullmatch(v) is not None


def display(v):
    """The display form of every fingerprint in a parameter value (a summary shows `sha256-` + 12 hex digits)."""
    if is_fingerprint(v):
        return v[:DISPLAY_LENGTH]
    if isinstance(v, list):
        return [display(x) for x in v]
    if isinstance(v, dict):
        return {k: display(x) for k, x in v.items()}
    return v


def _schema_strings(doc, props, consts):
    stack = [doc]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "properties" and isinstance(v, dict):
                    props.update(v)
                if k == "enum" and isinstance(v, list):
                    consts.update(x for x in v if isinstance(x, str))
                if k == "const" and isinstance(v, str):
                    consts.add(v)
                stack.append(v)
        elif isinstance(o, list):
            stack.extend(o)


def _keys(doc):
    out, stack = set(), [doc]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            out.update(o)
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return out


_SCHEMA = {}


def schema_vocabulary():
    """Member names and public constants of both supported PER schemas, the bundle schema, and rc1 layout tokens."""
    if not _SCHEMA:
        props, consts = set(), set()
        for d in (per_schema("2.0.0-rc1"), per_schema("2.0.0-rc3-draft"), per_schema("2.0.0-rc4-draft"),
                  per_schema("2.0.0-rc5-policy-draft"), per_schema("2.0.0"),
                  per_schema("2.1.0"), bundle_schema(), bundle_schema({"bundle_draft": 2})):
            _schema_strings(d, props, consts)
        # The scored-route precheck uses this one diagnostic header URI. Do
        # not import the preview schema's other words into public vocabulary.
        consts.add(per_schema("2.0.0-rc3-neutral-preview")["$id"])
        _SCHEMA["layout"] = frozenset(props | set(LAYOUT_TOKENS))
        _SCHEMA["consts"] = frozenset(consts)
    return _SCHEMA["layout"], _SCHEMA["consts"]


class Vocabulary:
    """The named vocabularies of one loaded release: `vocab` (release strings, schema constants and names, EIO-Agents
    constants), `layout` and `names` (what a member name may be). Producer-specific labels and check names are not
    public vocabulary; an adapter may resolve them locally, but the standalone release fingerprints unknown labels."""

    def __init__(self, eio):
        doc = eio.doc
        layout, consts = schema_vocabulary()
        self.release = B.release_strings(eio)
        self.layout = layout
        self.labels = frozenset()
        self.check_names = frozenset()
        self.metric_keys = frozenset()
        constants = {x["id"] for x in CAVEATS.values()} | {x["text"] for x in CAVEATS.values()}
        self.vocab = frozenset(self.release | consts | layout | constants)
        self.names = frozenset(self.vocab | _keys(list(doc.values())) | self.labels | self.check_names | CONVERTER_NAMES)
        self.all = frozenset(self.vocab | self.labels | self.check_names | self.metric_keys)
        self.evidence_floor, self.reference_cases = eio.release_evidence_floor, eio.reference_cases   # gate reasons
        self.controls = {k: frozenset(x["id"] for x in c.get("controls") or []) for k, c in eio.criteria.items()}


_VOCABULARY = weakref.WeakKeyDictionary()


def vocabulary(eio):
    v = _VOCABULARY.get(eio)
    if v is None:
        v = _VOCABULARY[eio] = Vocabulary(eio)
    return v


def label_value(eio, label):
    """A scenario label's record value: a trap-library label in clear, any other label as its fingerprint (the fingerprint
    recipe of a behavioural finding takes this value, so the twin recomputes it from the record)."""
    if label is None:
        return None
    return label if label in vocabulary(eio).labels else fingerprint(label)


def _member(V, arg, v):
    """Whether `v` is a member of the vocabulary `arg` of an (a|d) field."""
    if arg == "label":
        return v in V.labels
    if arg == "release":
        return v in V.release
    if arg == "layout":
        return v in V.layout
    if arg == "pointer":
        return v.startswith("/") and all(t in V.layout or t.isdigit() for t in v[1:].split("/"))
    if arg == "source_ref":
        return v in ("transcript", "context") or v in V.layout
    if arg == "basis":
        m = BASIS_PHRASE.fullmatch(v)
        return v in V.release or (m is not None and m.group(1) in V.release)
    raise ConversionError(f"PRIVACY_UNCLASSIFIED: unknown vocabulary {arg}", code="PRIVACY_UNCLASSIFIED")


def _ad(V, arg, v):
    return v if _member(V, arg, v) else fingerprint(v)


def metric_label_value(eio, label):
    """A metric label's record value: a release string in clear, any other label as its fingerprint (the a|d decision of
    `scores.metrics.*.explanation.params.metric`). A gate reason names a metric by exactly this value, so the reason is
    rebuilt from the metric's row (`gate_reason_text`)."""
    return _ad(vocabulary(eio), "release", label)


def _via_key(V, key):
    return key if key in V.labels or key in V.check_names or key in V.vocab else fingerprint(key)


def seal_value(V, spec, v):
    """The record value of the string `v` in a field of class `spec` (an empty string carries no text and stays empty:
    the schema's length rules still read it)."""
    c, arg = spec
    if v == "" and c in ("d", "ad", "bd", "md"):
        return v
    if c in ("d", "md"):                         # an `md` value outside a model row is decided by `seal_row`
        return fingerprint(v)
    if c == "ad":
        return _ad(V, arg, v)
    if c == "bd":
        return v if (B.safe_model_identifier(v) if arg == "model" else BD_FORMS[arg].fullmatch(v)) else fingerprint(v)
    if c == "r" and arg == "via":
        m = VIA_LINK.fullmatch(v)
        return f"eio.graph.context-links:{_via_key(V, m.group('key'))}→{m.group('criterion')}/{m.group('control')}" if m else v
    if c == "r" and arg == "ledger_key":
        m = LEDGER.fullmatch(v)
        return f"{_ad(V, 'label', m.group('label'))}::{m.group('check')}@{m.group('turn')}" if m else v
    if c == "r" and arg == "formula":
        for rx in FORMULAS:
            m = rx.fullmatch(v)
            if m and "cf" in rx.groupindex:
                cf = m.group("cf")
                return v[:m.start("cf")] + _ad(V, "layout", cf) + v[m.end("cf"):]
        return v
    return v


def seal_param(V, v):
    """A limitation parameter's value as the catalogue renders it: vocabulary and structural forms in clear, a ledger key
    with its label decided (a|d), any other text as its fingerprint (in full: the record keeps no parameter)."""
    if isinstance(v, str):
        if v in V.all or PARAM_FORM.fullmatch(v):
            return v
        m = LEDGER.fullmatch(v)
        if m and m.group("check") in V.check_names:
            return f"{_ad(V, 'label', m.group('label'))}::{m.group('check')}@{m.group('turn')}"
        return fingerprint(v)
    if isinstance(v, list):
        return [seal_param(V, x) for x in v]
    if isinstance(v, dict):
        return {seal_param(V, k): seal_param(V, x) for k, x in v.items()}
    return v


def seal_params(eio, params):
    V = vocabulary(eio)
    return {k: seal_param(V, v) for k, v in params.items()}


def gpath(path):
    """The generalized path of a record path: a list index as '*', the member of an open map as '<key>' (and an archive
    pointer other than the archive digest and the transcript root: a native producer's pointers into its own sources)."""
    out = []
    for x in path:
        if type(x) is int:
            out.append("*")
        elif tuple(out) in OPEN_MAPS or (tuple(out) == ARCHIVE_POINTER and x not in ARCHIVE_POINTER_FIXED):
            out.append("<key>")
        else:
            out.append(x)
    return tuple(out)


def pointer(path):
    return "/" + "/".join(str(x) for x in path)


def _leaves(rec):
    """(path, string) of every string value of `rec` (member names apart), in document order."""
    out, stack = [], [(rec, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            stack.extend((v, p + (k,)) for k, v in reversed(list(o.items())))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in reversed(list(enumerate(o))))
        elif isinstance(o, str):
            out.append((p, o))
    return out


def _names(rec):
    """(path of the object, member name) of every member of `rec`."""
    out, stack = [], [(rec, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                out.append((p, k))
                stack.append((v, p + (k,)))
        elif isinstance(o, list):
            stack.extend((v, p + (i,)) for i, v in enumerate(o))
    return out


def spec_of(path):
    """The (class, argument) of a record string at `path`; an unlisted path fails closed."""
    s = TABLE.get(gpath(path))
    require(s is not None, "PRIVACY_UNCLASSIFIED", f"{pointer(path)}: the record field {'.'.join(gpath(path))} is not in "
            "the closed field table (every record string is vocabulary, a structural value, an excerpt, a fingerprint or a "
            "rendered text of these; decision #31)")
    return s


def _set(rec, path, v):
    o = rec
    for x in path[:-1]:
        o = o[x]
    o[path[-1]] = v


def _explanations(o, out):
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if "template_id" in x and "params" in x and "summary" in x:
                out.append(x)
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return out


def seal(eio, rec):
    """Apply the closed field table to a projected record, in place; returns it. A path the table does not list is left
    as it is: `check` fails it closed (`PRIVACY_UNCLASSIFIED`) after the schema and the round 2-4 rules gave their codes."""
    V = vocabulary(eio)
    for p, v in _leaves(rec):
        spec = TABLE.get(gpath(p))
        nv = seal_value(V, spec, v) if spec is not None else v     # an unlisted field fails closed in `check`
        if spec is not None and spec[0] == "md" and _model_row(rec, p) and B.safe_model_identifier(v):
            nv = v                                                  # the agent model's AI-BOM row, in clear
        if nv != v:
            _set(rec, p, nv)
    for p in _list_paths(rec):
        lst = _get(rec, p)
        if all(isinstance(x, str) for x in lst):
            lst.sort()
    for x in _explanations(rec, []):
        x["summary"] = why.render(eio, x["template_id"], display(x["params"]))
    return rec


def _model_row(rec, path):
    """Whether the AI-BOM component at `path` (its `name`) is the agent model's row."""
    return _get(rec, path[:-1]).get("kind") == MODEL_COMPONENT


def _get(rec, path):
    o = rec
    for x in path:
        o = o[x]
    return o


def _list_paths(rec):
    """The concrete paths of the lists the converter sorts (`SORTED_LISTS`)."""
    out, stack = [], [(rec, ())]
    while stack:
        o, p = stack.pop()
        if isinstance(o, dict):
            stack.extend((v, p + (k,)) for k, v in o.items())
        elif isinstance(o, list):
            if gpath(p) in SORTED_LISTS:
                out.append(p)
            else:
                stack.extend((v, p + (i,)) for i, v in enumerate(o))
    return out


# ---------------------------------------------------------------------------------------------------------------- checks
def producer_texts(bundle, eio):
    """The producer texts of a bundle: every string a record could carry in clear (`bundle._in_clear`, member names
    included) that is not vocabulary, not a structural form and not a short number. No record string outside the
    excerpt may equal one (`problems`)."""
    V = vocabulary(eio)
    return frozenset(s for p, s in B.string_leaves(bundle) if B._in_clear(p) and s not in V.all
                     and not any(f.fullmatch(s) for f in FORMS.values()) and not SHORT_NUMBER.fullmatch(s)
                     and not public_form(V, s))


def public_form(V, s):
    """Whether `s` is a closed composite of vocabulary: a recipe formula over a layout token, a ledger key over a trap-library
    label and a legacy check, a context-link via over release ids, a contract token, a profile rule, an axis component."""
    if s in COMPONENT_TOKENS | APPROVED_G_COMPONENTS | APPROVED_PROFILE_IDS | APPROVED_PROFILE_VERSIONS \
            or CONTRACT_TOKEN.fullmatch(s) or PROFILE_RULE.fullmatch(s):
        return True
    for rx in FORMULAS:
        m = rx.fullmatch(s)
        if m:
            return "cf" not in rx.groupindex or m.group("cf") in V.layout
    m = LEDGER.fullmatch(s)
    if m:
        return m.group("label") in V.labels and m.group("check") in V.check_names
    m = VIA_LINK.fullmatch(s) or VIA_CRITERION.fullmatch(s)
    if m:
        key = m.groupdict().get("key")
        return (key is None or key in V.labels or key in V.check_names or key in V.vocab) and m.group("criterion") in V.vocab \
            and m.group("control") in V.vocab
    return False


def _limitation_texts(rec):
    # The native rc2 record can carry declared producer catalogues.  A
    # process-global rc1 table is neither complete nor safe for that record.
    catalogue = merge_catalogues(load_core_limitations(), rec["header"], kind="limitations")
    out = {}
    for lid, row in catalogue.items():
        out[lid] = {}
        for k in ("reason", "impact", "next_step"):
            t = row[k]
            parts = list(string.Formatter().parse(t))
            rx = "".join(re.escape(literal) + ("(.+?)" if name is not None else "")
                         for literal, name, _, _ in parts)
            out[lid][k] = (re.compile(rx, re.S), [name for _, name, _, _ in parts if name is not None])
    return out


def _safe_param(V, value):
    """Only released words, sealed text, structural atoms and their Python container display may fill a template."""
    if not isinstance(value, str) or len(value) > 4096:
        return False
    if value in V.all or PARAM_FORM.fullmatch(value) or is_fingerprint(value) or value in ("None", "True", "False"):
        return True
    m = LEDGER.fullmatch(value)
    if m and (m.group("label") in V.labels or is_fingerprint(m.group("label"))) and m.group("check") in V.check_names:
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
            return _safe_param(V, x)
        if isinstance(x, (int, float, bool)) or x is None:
            return True
        if isinstance(x, (list, tuple)) and len(x) <= 128:
            return all(safe(v, depth + 1) for v in x)
        if isinstance(x, dict) and len(x) <= 128:
            return all(safe(k, depth + 1) and safe(v, depth + 1) for k, v in x.items())
        return False
    return safe(obj)


# ------------------------------------------------------------------------------------------- rendered texts (class r)
# Every rendered record text is rebuilt from the record's own rows and compared byte for byte (L3s grammar fix: a
# production with an open slot -- a number, a word list, any fingerprint -- admits a payload; an exact rebuild admits
# none). Three texts cannot be rebuilt from the record alone, so each is a closed production bound to its rows instead:
# a limitation text (the record keeps no parameter) is its own limitation's catalogue text with every parameter a
# vocabulary member, a structural form, a fingerprint or a sealed ledger key; a via (the record keeps no context-link key)
# names a checklist control of its own criterion of the release, under a key that is a fingerprint or vocabulary; a
# recurrence row's ledger key (the producer's trial-ledger key) is a trap-library label or a fingerprint, a legacy check
# name and its claim's first turn. The twin binds all three to their bundle sources (T4).
REPRODUCIBLE_FIELDS = ("revision", "patch", "seed", "models", "prompt_hashes")
BAND_ORDER = {"NOT_RETESTED": 0, "UNCONFIRMED": 1, "INTERMITTENT": 2, "CONFIRMED": 3}
CONTEXT_FORMULA = "count(term in casefold(file) for file in files_searched for term in requires_any)"
_UNBUILT = (KeyError, IndexError, TypeError, AttributeError, ValueError, StopIteration, ArithmeticError)


def _typed(x, *types):
    """`x` when its type is one of `types` (bool is not an int here), else a TypeError: a rendered text over a row of
    another type is never rebuilt."""
    if type(x) not in types:
        raise TypeError(f"{type(x).__name__} in a rendered row")
    return x


def _int(x):
    return _typed(x, int)


def _str(x):
    return _typed(x, str)


def _many(n, one, many):
    return one if n == 1 else many


def gate_reason_text(V, rec, row):
    """The exact reason of the gate result `row`, rebuilt from the record (`semantics.release.gates` renders it from the
    projection): the coverage obligations; the diagnostic metric rows, each named by its label's record value (the value
    of its explanation's `metric` parameter), with its basis counts and evidence fraction; the capsule's missing fields;
    the declared tier and facts; the row's own met and claim ids with their claims and recurrence rows; the release's
    evidence floor and reference cases. A row the record does not support raises."""
    gid, met = _str(row["gate"]), row["met"]
    if gid == "eio.gate.coverage-complete":
        hb = [o for o in _typed(rec["coverage"]["obligations"], list) if o["release_impact"] == "HARD_BLOCK" and o["met"] is False]
        unmet, unknown = [o for o in hb if o["required"] is True], [o for o in hb if o["required"] is None]
        if unmet:
            return f"{len(unmet)} required HARD_BLOCK {_many(len(unmet), 'obligation is', 'obligations are')} unmet"
        if unknown:
            n = len(unknown)
            return (f"{n} HARD_BLOCK {_many(n, 'obligation is', 'obligations are')} unmet and {_many(n, 'its', 'their')} "
                    "required status is unknown because a required_when fact is not declared")
        return "every HARD_BLOCK obligation whose required is not false reached its minimum cases"
    if gid == "eio.gate.evidence-sufficient":
        floor = why.fmt_decimal(V.evidence_floor)
        diag = [m for m in _typed((rec.get("scores") or {}).get("metrics") or [], list) if m["measurement_status"] == "DIAGNOSTIC_ONLY"]
        if not diag:
            return f"every metric returned at least {floor} of its expected claims"

        def named(m):
            return _str(m["explanation"]["params"]["metric"]), f"{_typed(m['evidence_fraction'], int, float):.4f}"
        if len(diag) <= GATE_CLAUSES_MAX:
            out = []
            for m in diag:
                (label, frac), b = named(m), m["explanation"]["basis"]
                returned = _int(b["pass"]) + _int(b["fail"]) + _int(b["not_applicable"])
                out.append(f"{label} returned {returned} of {_int(b['claims'])} expected claims ({frac}), below the {floor} floor")
            return "; ".join(out)
        return (f"{len(diag)} metrics returned less than the {floor} floor of their expected claims: "
                + ", ".join("%s (%s)" % named(m) for m in diag))
    if gid == "eio.gate.evaluator-calibrated":
        return "the archive carries no calibration result against adjudicated reference cases"
    if gid == "eio.gate.reproducible":
        missing = _typed(rec["provenance"]["capsule"]["missing_fields"], list)
        lacks = [f for f in REPRODUCIBLE_FIELDS if f in missing]
        return ("the capsule lacks " + ", ".join(lacks)) if lacks else "the capsule records revision, patch, seed, models and prompt hashes"
    if gid == "eio.gate.human-oversight-declared":
        facts = _typed(rec["scope"]["facts"], dict)
        value = {k: (facts[k]["value"] if k in facts else None) for k in ("consequential_actions", "human_oversight")}
        tier = _typed(rec["release_recommendation"]["policy"]["tier"], str, type(None))
        return oversight_gate(tier, value["consequential_actions"], value["human_oversight"])[1]
    if gid == "eio.gate.no-critical-recurrence":
        cids = [_str(x) for x in _typed(row["claim_ids"], list)]
        if not cids:
            if met is None:
                return "no reliability trials were run"
            if met is True:
                return "no finding on a HARD_BLOCK obligation reproduced in every re-test pass"
            raise ValueError("an unmet recurrence gate without claims")
        claims = {c["id"]: c for c in rec["claims"]}
        trials = {r["claim_id"]: r for r in rec["reliability"]["recurrence"]}

        def at(x):
            c, t = claims[x], trials[x]
            return _str(c["predicate"]), _int(c["turn_indices"][0]), _int(t["reproduced_in"]), _int(t["retests"])
        if len(cids) <= GATE_CLAUSES_MAX:
            reason = "; ".join("claim %s (%s, turn %d) reproduced in %d of %d re-test passes" % ((x,) + at(x)) for x in cids)
        else:
            groups = {}
            for x in cids:
                pred, turn, r, n = at(x)
                groups.setdefault((pred, r, n), []).append(turn)
            clauses = [f"{len(ts)} {_many(len(ts), 'claim', 'claims')} of {pred} ({why.fmt_turn_list(ts)}) reproduced in {r} of {n} "
                       "re-test passes" for (pred, r, n), ts in groups.items()]
            reason = "; ".join(clauses[:GATE_CLAUSES_MAX]) + (f" and {len(clauses) - GATE_CLAUSES_MAX} more"
                                                              if len(clauses) > GATE_CLAUSES_MAX else "")
        return reason + " on a HARD_BLOCK obligation"
    if gid == "eio.gate.independent-adjudication":
        cases = V.reference_cases
        pending = [c for c in cases if (c.get("review") or {}).get("status") != "adjudicated"]
        if not pending:
            return f"all {len(cases)} reference cases are adjudicated"
        statuses = ", ".join(sorted({(c.get("review") or {}).get("status") or "unknown" for c in pending}))
        return f"{len(pending)} of {len(cases)} reference cases are not adjudicated (review status {statuses})"
    raise KeyError(gid)


def decisive_text(rec, row, field):
    """The exact `expected` or `observed` text of the decisive row `row`, rebuilt from its claims, metric floor or policy
    rule (`semantics.release.release`)."""
    kind, rid = _str(row["kind"]), _str(row["id"])
    if kind == "review_guard" and rid == "eio.release.high-review-queue":
        return ("no unresolved HIGH or CRITICAL findings" if field == "expected" else
                f"{len(row['finding_ids'])} unresolved HIGH or CRITICAL finding(s)")
    if kind == "review_guard" and rid == "eio.release.default-readiness-floor":
        # release semantics 2.2 (owner decision #46); the readiness is read from the record once it is scored (the
        # producer renders the entry while the score block is still being assembled, from the same value)
        if field == "expected":
            return "readiness >= 85.0"
        scores = rec.get("scores")
        if scores is None:
            return _str(row["observed"])
        value = scores["readiness"]["value"]
        return "withheld" if value is None else why.fmt_score(_typed(value, int, float))
    if kind == "review_guard" and rid == "eio.release.hard-block-unmet":
        return ("0" if field == "expected" else
                str(len(row['obligation_ids'])))
    if kind == "cap":
        if field == "expected":
            return "no deterministic, witnessed APPLICABLE_FAIL on a cap predicate"
        claims = {x["id"]: x for x in rec["claims"]}
        return ", ".join(f"{_str(claims[x]['predicate'])} at turn {_int(claims[x]['turn_indices'][0])}" for x in row["claim_ids"])
    if kind == "metric_floor":
        floor = next(x for x in rec["release_recommendation"]["metric_floors"] if x["metric"] == row["metric"])
        return f">= {_typed(floor['floor'], int, float)}" if field == "expected" else why.fmt_score(_typed(floor["observed"], int, float))
    if rid == "profile.prohibited_use_case":
        return "use case not prohibited" if field == "expected" else "prohibited use case"
    if rid == "profile.signoff_required":
        return "human sign-off recorded" if field == "expected" else "not recorded"
    rule = next(x for x in rec["release_recommendation"]["policy"]["rules"] if x["rule"] == rid)
    if rid == "profile.min_score":
        if field == "expected":
            return f">= {why.fmt_score(_typed(rule['expected'], int, float))}"
        if rule["result"] == "not_evaluated":
            return "not evaluated"
        return "null" if rule["observed"] is None else why.fmt_score(_typed(rule["observed"], int, float))
    if rid.startswith("profile.block_on_"):
        return f"0 findings with severity >= {rid.removeprefix('profile.block_on_').upper()}" if field == "expected" else str(_int(rule["observed"]))
    raise KeyError(rid)


def decisive_entry_text(rec, row):
    """One entry of the release explanation's `decisive_list`, rebuilt from its decisive row (its texts checked first)."""
    rid = _str(row["id"])
    if row["kind"] == "cap":
        claim = next(c for c in rec["claims"] if c["id"] == row["claim_ids"][0])
        s = f"{rid} (claim {_str(claim['id'])}, turn {_int(claim['turn_indices'][0])})"
    elif row["kind"] == "metric_floor":
        s = f"{rid} ({_str(row['metric'])} {decisive_text(rec, row, 'observed')} < {decisive_text(rec, row, 'expected').split()[-1]})"
    elif rid.startswith("profile.block_on_"):
        s = f"{rid} ({decisive_text(rec, row, 'observed')} findings)"
    else:
        s = f"{rid} (expected {decisive_text(rec, row, 'expected')}, observed {decisive_text(rec, row, 'observed')})"
    return s + (" -> REVIEW" if row["effect"] == "REVIEW" else "")


def ledger_key_problem(V, rec, row, v):
    """Why the ledger key `v` of the recurrence row `row` is not bound to its claim, or None. The key is the producer's
    trial-ledger key (the record keeps no other copy of its label or check): its label is a trap-library label or a
    fingerprint, its check a legacy check name of the release and its turn the claim's first turn."""
    m = LEDGER.fullmatch(v)
    claim = next((c for c in rec["claims"] if c["id"] == row["claim_id"]), None)
    if m is None or claim is None:
        return "is not a ledger key of a claim of the record"
    label_ok = is_fingerprint(m.group("label")) or m.group("label") in V.labels
    bound = m.group("check") in V.check_names and m.group("turn") == str(_int(claim["turn_indices"][0]))
    return None if label_ok and bound else "is not a sealed ledger key over a legacy check and its claim's first turn"


def finding_ledger_key_text(rec, finding):
    """A finding's recurrence ledger key: the key of the recurrence row of its weakest-band claim (the first in claim
    order), as `semantics.findings` picks the finding's recurrence."""
    trials = {r["claim_id"]: r for r in rec["reliability"]["recurrence"]}
    weakest = min(finding["claim_ids"], key=lambda x: BAND_ORDER[trials[x]["band"]] if x in trials else 0)
    if trials.get(weakest, {}).get("band", "NOT_RETESTED") == "NOT_RETESTED":
        raise KeyError("a ledger key on a finding whose weakest claim was not re-tested")
    return _str(trials[weakest]["ledger_key"])


def formula_text(statement):
    """A computed ref's formula, rebuilt from its statement's inputs: the recipe their shape names, over the record value
    of the source they name (`evidence.refs`, `evidence.context_refs`)."""
    inputs = statement["inputs"]
    if "files_searched" in inputs:
        return CONTEXT_FORMULA
    src = _str(inputs["source"])
    if "name_contains" in inputs:
        return f"count(call for t in episode_turns for call in {src}[t] if any(p in call.name.lower() for p in name_contains))"
    if "snapshot_sha256" in inputs:
        return f"{src}[t] is non-empty"
    return f"len({src}[t])"


def display_label_text(finding):
    """A finding's display label, rebuilt from its kind, first turn and predicate, or its criterion and control."""
    if finding["kind"] == "CONTEXT_GAP":
        return "ctx · " + _str(finding["criterion"]).replace("eio.context.", "") + " / " + _str(finding["control"])
    return "t%02d · %s" % (_int(finding["turn_indices"][0]), _str(finding["predicate"]).replace("eio.predicate.", ""))


def semantics_text(header):
    """`header.per_semantics_version`, rebuilt from the header's converter version, EIO release and ontology digest."""
    return f"2@{_str(header['converter']['version'])}+eio{_str(header['eio']['release'])}.{_str(header['eio']['ontology_digest'])}"


CAVEAT_TEXT = {x["id"]: x["text"] for x in CAVEATS.values()}


def rendered_text(V, rec, path):
    """The exact text the converter renders at the record path `path` of a rebuilt renderer, from the record's rows; it
    raises when the rows do not support one (an unused string slot included)."""
    g = gpath(path)
    if g == ("release_recommendation", "gate_results", "*", "explanation", "params", "reason"):
        return gate_reason_text(V, rec, rec["release_recommendation"]["gate_results"][path[2]])
    if g[:3] == ("release_recommendation", "decisive", "*") and g[3:] in (("expected",), ("observed",)):
        return decisive_text(rec, rec["release_recommendation"]["decisive"][path[2]], g[3])
    if g == ("release_recommendation", "explanation", "params", "decisive_list", "*"):
        return decisive_entry_text(rec, rec["release_recommendation"]["decisive"][path[-1]])
    if g == ("findings", "*", "recurrence", "ledger_key"):
        return finding_ledger_key_text(rec, rec["findings"][path[1]])
    if g == ("findings", "*", "display_label"):
        return display_label_text(rec["findings"][path[1]])
    if g == ("evidence", "refs", "*", "statement", "formula"):
        return formula_text(rec["evidence"]["refs"][path[2]]["statement"])
    if g == ("header", "per_semantics_version"):
        return semantics_text(rec["header"])
    if g == ("scope", "caveats", "*", "text"):
        return CAVEAT_TEXT[rec["scope"]["caveats"][path[2]]["id"]]
    raise KeyError(".".join(g))      # contributing.*.expected|observed, policy.rules.*.expected|observed: no string


def _rebuilt(V, rec, path, v):
    try:
        return rendered_text(V, rec, path) == v
    except _UNBUILT:
        return False


def _pair(V, criterion, control):
    return control in V.controls.get(criterion, ())


def _key_ok(V, key):
    return is_fingerprint(key) or key in V.labels or key in V.check_names or key in V.vocab


def value_problem(V, spec, v, path, rec):
    """Why the string `v` does not fit its class, or None."""
    c, arg = spec
    if c == "a":
        ok = {"vocab": lambda: v in V.vocab, "check_name": lambda: v in V.check_names,
              "metric_key": lambda: v in V.metric_keys, "contract_token": lambda: CONTRACT_TOKEN.fullmatch(v),
              "profile_rule": lambda: PROFILE_RULE.fullmatch(v), "decisive_id": lambda: v in V.vocab or PROFILE_RULE.fullmatch(v) or (
                  rec["header"]["per_version"] == "2.1.0" and v in REVIEW_GUARD_IDS),
              "caveat_id": lambda: v in {x["id"] for x in CAVEATS.values()},
              "component_id": lambda: v in V.vocab or v in COMPONENT_TOKENS or (
                  rec["scores"]["axes"][path[2]]["axis"] == "eio.axis.governance" and v in APPROVED_G_COMPONENTS)}[arg]()
        return None if ok else "is not a member of its vocabulary"
    if c == "b":
        if arg == "legacy_profile_id":
            return None if rec["header"]["per_version"] == "2.0.0-rc1" and v == "harness-2.x" else "is not the reviewed rc1 scoring-profile id"
        if arg == "profile_id":
            pair = (v, rec["scores"]["scoring_profile"]["version"])
            return None if pair in APPROVED_PROFILES else "is not a reviewed public scoring-profile id/version pair"
        if arg == "profile_version":
            pair = (rec["scores"]["scoring_profile"]["id"], v)
            return None if pair in APPROVED_PROFILES else "is not a reviewed public scoring-profile id/version pair"
        return None if FORMS[arg].fullmatch(v) else f"is not of the form {arg}"
    if c == "c":
        return None
    if v == "" and c in ("d", "ad", "bd", "md"):
        return None
    if c == "d":
        return None if FINGERPRINT.fullmatch(v) else "is not a fingerprint"
    if c == "md":
        return None if FINGERPRINT.fullmatch(v) or (_model_row(rec, path) and B.safe_model_identifier(v)) else \
            "is neither a model identifier of the model row nor a fingerprint"
    if c == "ad":
        return None if FINGERPRINT.fullmatch(v) or _member(V, arg, v) else "is neither a vocabulary member nor a fingerprint"
    if c == "bd":
        safe = B.safe_model_identifier(v) if arg == "model" else BD_FORMS[arg].fullmatch(v)
        return None if FINGERPRINT.fullmatch(v) or safe else f"is neither of the strict form {arg} nor a fingerprint"
    if c == "r":
        return _rendered_problem(V, arg, v, path, rec)
    return f"has the unknown class {c}"


def _rendered_problem(V, arg, v, path, rec):
    if arg == "summary":
        return None                                   # rebuilt with its explanation (`problems`)
    if arg == "ledger_key" and gpath(path) == ("reliability", "recurrence", "*", "ledger_key"):
        try:
            return ledger_key_problem(V, rec, rec["reliability"]["recurrence"][path[2]], v)
        except _UNBUILT:
            return "is not a ledger key of a claim of the record"
    if arg in ("converter", "ledger_key", "formula", "display_label", "semantics", "caveat"):
        return None if _rebuilt(V, rec, path, v) else "is not the exact rendering of its record rows"
    if arg == "via":
        m = VIA_LINK.fullmatch(v)
        if m:
            return None if _key_ok(V, m.group("key")) and _pair(V, m.group("criterion"), m.group("control")) \
                else "names no checklist control of its criterion, or a clear key outside the vocabulary"
        m = VIA_CRITERION.fullmatch(v)
        return None if m and _pair(V, m.group("criterion"), m.group("control")) else "is not a via to a checklist control"
    if arg == "limitation":
        row = rec["limitations"][path[1]]
        try:
            entry = _limitation_texts(rec).get(row["limitation_id"], {}).get(path[2])
        except (ConversionError, KeyError, TypeError):
            return "has an invalid or undeclared limitation catalogue"
        if entry is None:
            return "is not its limitation's catalogue text"
        rx, names = entry
        m = rx.fullmatch(v)
        if m is None or not all(_safe_param(V, x) for x in m.groups()):
            return "is not its limitation's catalogue text with sealed parameters"
        return None
    return f"has the unknown renderer {arg}"


def problems(eio, rec, producer=frozenset()):
    """[(code, detail)]: every string of `rec` against its class (`TABLE`), every summary against its re-rendering with
    the display rule, and no string outside the excerpt equal to a producer text (`producer_texts`)."""
    V = vocabulary(eio)
    out = []
    for p, k in _names(rec):
        if k not in V.names:
            out.append(("PRIVACY_UNCLASSIFIED", f"{pointer(p)}: member name {k!r:.60} is not vocabulary"))
    for p, v in _leaves(rec):
        spec = TABLE.get(gpath(p))
        if spec is None:
            out.append(("PRIVACY_UNCLASSIFIED", f"{pointer(p)}: {'.'.join(gpath(p))} is not in the closed field table"))
            continue
        why_not = value_problem(V, spec, v, p, rec)
        released = spec[0] in ("bd", "md") and not FINGERPRINT.fullmatch(v) and not why_not   # a decided clear form
        if spec[0] != "c" and v in producer and not released:
            out.append(("PRIVACY_CLEAR_TEXT", f"{pointer(p)} carries a producer text of the bundle in clear"))
        if why_not:
            code = "BUNDLE_VOCABULARY" if spec[0] == "a" else "PER_INVALID"
            out.append((code, f"{pointer(p)} ({spec[0]}{':' + spec[1] if spec[1] else ''}) {why_not}: {v[:60]!r}"))
    for x in _explanations(rec, []):
        try:
            ok = why.render(eio, x["template_id"], display(x["params"])) == x["summary"]
        except ConversionError:
            ok = False
        if not ok:
            out.append(("PER_INVALID", f"explanation {x['template_id']}: the summary is not the rendering of its params with "
                                       "the display rule"))
    return out


def check(eio, rec, producer=frozenset()):
    """Fail closed with the first problem's code (`problems`)."""
    ps = problems(eio, rec, producer)
    if ps:
        code, detail = ps[0]
        raise ConversionError(f"{code}: {len(ps)} record string(s) outside the closed field table's classes (decision #31); "
                              f"first: {detail}", code=code)
