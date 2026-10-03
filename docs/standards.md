# Standards coverage

This page summarises how EIO 0.6.0, bundled with EIO-Agents `0.8.0`, relates to external frameworks, standards and
laws, and where that coverage stops. Read it before you use a control status from a PER record for anything else.

- [What EIO and PER are, and are not](#what-eio-and-per-are-and-are-not)
- [How the crosswalk works](#how-the-crosswalk-works)
- [The 30 framework views](#the-30-framework-views)
- [Coverage of official item lists](#coverage-of-official-item-lists)
- [Known gaps](#known-gaps)
- [Relation to other evaluation formats](#relation-to-other-evaluation-formats)
- [Names and attribution](#names-and-attribution)

## What EIO and PER are, and are not

EIO and PER are open specifications with a reference library. They are not yet standards: they have no public,
multi-party governance and no second, independent implementation. [GOVERNANCE.md](../GOVERNANCE.md) sets out how that is
meant to change.

The core schemas' `$schema` value `https://json-schema.org/draft/2020-12/schema` names the official JSON Schema
dialect; it does not label EIO 0.6.0 as a draft release. A PER 2.1.0 record binds the separately versioned reference
scoring profile `0.3.1`; published PER 2.0.0 records keep their historical `0.3.1-draft.1` profile.

A PER record does not certify anything. Its control statuses show which evidence from one evaluation run is relevant to a
control. They do not establish that a framework applies to you, that you conform to it, or that an organisation meets its
requirements.

## How the crosswalk works

- EIO 0.6.0 maps **36 of its 58 predicates** to **165 controls** in **30 framework views**, with 406 control-to-risk
  links and 434 control-to-predicate links. The other 22 predicates map to no control (see [Known gaps](#known-gaps)).
- Every framework view and every control carries `mapping_status: provisional` and `legal_review_required: true`.
- Each framework view states its own assurance boundary: "This bundled view supports evidence-relevance screening only; it
  does not establish legal applicability, full conformity, attestation, or certification."
- A view is included in a record only when the evaluation's governance profile selects it (by jurisdiction, domain, risk
  tier and use case).
- A control's status is derived deterministically from the claims on its target predicates. The six statuses are
  `observed_satisfaction`, `observed_violation`, `not_tested`, `not_observable`, `not_applicable` and `inconclusive`.
- A violation that rests only on proxy (narrower) claims is marked `proxy_only` and is never decisive.
- `observed_satisfaction` means at least one passing claim and no failing claim on the control's targets. It does not mean
  that every target was exercised.
- The verifier rejects a control summary that says "compliant".

## The 30 framework views

| Framework view | EIO id | Kind | Controls |
|---|---|---|---|
| EU AI Act | `eio.framework.eu-ai-act` | law | 6 |
| NIST AI RMF | `eio.framework.nist-ai-rmf` | government framework | 6 |
| ISO/IEC 42001 | `eio.framework.iso-42001` | standard | 5 |
| Colorado AI Act (SB 24-205) | `eio.framework.colorado-ai-act` | law | 4 |
| NYC Local Law 144 (AEDT) | `eio.framework.nyc-ll144` | law | 3 |
| Canada AIDA | `eio.framework.canada-aida` | proposal | 4 |
| China GenAI Measures | `eio.framework.china-genai` | regulation | 4 |
| EU GDPR | `eio.framework.gdpr` | law | 6 |
| UK GDPR / DPA 2018 | `eio.framework.uk-gdpr` | law | 4 |
| CCPA / CPRA | `eio.framework.ccpa` | law | 4 |
| HIPAA | `eio.framework.hipaa` | law | 4 |
| PIPEDA | `eio.framework.pipeda` | law | 4 |
| Brazil LGPD | `eio.framework.lgpd` | law | 4 |
| Singapore PDPA | `eio.framework.pdpa-sg` | law | 4 |
| India DPDP Act | `eio.framework.dpdp-india` | law | 4 |
| South Africa POPIA | `eio.framework.popia` | law | 4 |
| Australia Privacy Act (APPs) | `eio.framework.au-privacy` | law | 4 |
| GLBA | `eio.framework.glba` | law | 3 |
| SOC 2 | `eio.framework.soc2` | attestation criteria | 5 |
| ISO/IEC 27001 | `eio.framework.iso-27001` | standard | 5 |
| PCI DSS | `eio.framework.pci-dss` | industry standard | 4 |
| FedRAMP | `eio.framework.fedramp` | government framework | 4 |
| NIST SP 800-53 Rev. 5 | `eio.framework.nist-800-53` | government framework | 11 |
| FAA (Aviation Safety) | `eio.framework.faa` | regulation | 4 |
| FDA SaMD (GMLP) | `eio.framework.fda-samd` | regulation | 4 |
| FINRA / SEC | `eio.framework.finra-sec` | regulation | 4 |
| OWASP Top 10 for LLM Applications (2025) | `eio.framework.owasp-llm` | security taxonomy | 7 |
| OWASP Top 10 for Agentic Applications (2026) | `eio.framework.owasp-asi` | security taxonomy | 8 |
| OWASP Agentic AI Threats and Mitigations (v1.1) | `eio.framework.owasp-agentic-threats` | security taxonomy | 11 |
| AIUC-1 | `eio.framework.aiuc-1` | industry standard | 21 |

"Kind" is the `authority` field of each view. Every row is `provisional` and requires legal review. The views, control ids,
references and targets are in `src/eio_agents/ontology/data/compliance/frameworks.yaml`.

## Coverage of official item lists

A view does not cover its framework in full. Where the coverage of the official item list was measured, it is:

| Framework | Items with a control in the EIO view |
|---|---|
| OWASP Top 10 for LLM Applications (2025) | 7 of 10 |
| OWASP Top 10 for Agentic Applications (2026) | 8 of 10 |
| OWASP Agentic AI Threats and Mitigations (v1.1) | 11 of 17 |
| NIST AI RMF | 3 of 72 subcategories mapped directly |
| ISO/IEC 42001 | 2 of 38 Annex A controls mapped directly |

For the other 25 views, coverage has not been measured. Most views hold 3 to 6 controls, so assume partial coverage.

The NIST AI RMF and ISO/IEC 42001 views also contain broad controls (whole NIST functions, topic-level ISO controls). Such
a control can show `observed_satisfaction` for organisational requirements that no single evaluation run can evidence.
Treat those statuses as "relevant evidence seen", not as "requirement met".

## Known gaps

- **Currency.** Only 6 of the 30 views have been checked against the current edition of their framework.
- **ISO/IEC 27001.** Three controls (`iso-27001.a9-access`, `a12-ops`, `a16-incident`) use the Annex A numbering of the
  2013 edition, which ISO/IEC 27001:2022 replaced. They are due for review in a later EIO release.
- **Canada AIDA.** The view is marked as a proposal. Its current legislative status has not been reviewed.
- **Missing views.** NIST AI 600-1 (the generative AI profile) and MITRE ATLAS have no view.
- **Missing predicates.** EU AI Act Article 50 (transparency obligations) has no predicate.
- **Unmapped predicates.** 22 of the 58 predicates are the target of no control, directly or through a risk target, so a
  record never shows them in a control status:
  - evaluator reliability (6): `evaluator-citation-invalid`, `controlled-rerun-decision-divergence`,
    `coverage-obligation-unreached`, `reproducibility-provenance-incomplete`, `jury-independence-insufficient`,
    `incomplete-score-presented-as-complete`;
  - other risk predicates (7): `autonomy-boundary-exceeded`, `resource-budget-exceeded`, `unverified-component-used`,
    `stale-information-used-as-current`, `tenant-boundary-crossing`, `context-provenance-missing`,
    `unauthenticated-peer-instruction-executed`;
  - safeguard predicates (7): `prohibited-part-clearly-refused`, `compliant-alternative-offered`,
    `documented-escalation-used`, `required-verification-requested`, `uncertainty-calibrated`,
    `permissible-task-completed`, `professional-tone-maintained`;
  - observation predicates (2): `untrusted-content-reproduced`, `permissible-task-present`.

  All ids carry the prefix `eio.predicate.`.
- **NIST AI RMF reference.** `eio.control.nist-ai-rmf.measure-valid` is titled "Validity & reliability" but cites
  MEASURE 2.3 (performance or assurance criteria measured for deployment-like conditions). Validity and reliability is
  MEASURE 2.5 in NIST AI 100-1. The reference is due for correction in an EIO patch release; the count "3 of 72
  subcategories" is not affected.
- **Review status.** No mapping has had legal review. The 45 EIO reference cases are unadjudicated seeds.

Proposals to add or correct a mapping are welcome; see [GOVERNANCE.md](../GOVERNANCE.md#mapping-changes).

## Relation to other evaluation formats

Each part of EIO and PER has prior art: pass^k reliability estimates, digest-checked evaluation records, framework
crosswalks, and claim and evidence models such as W3C EARL and CycloneDX attestations. EIO-Agents is intended to map to
existing work (for example EARL, OSCAL, CycloneDX, in-toto, OpenTelemetry, Every Eval Ever and AIUC-1), not to replace it.
This release ships no export to those formats; AIUC-1 is present only as one of the 30 framework views.
[concepts.md](concepts.md#related-work) lists the closest related formats and tools, with links.

## Names and attribution

Framework, standard and law names, and control identifiers, belong to their owners. EIO carries identifiers, references
and short titles only; it reproduces no control text. The OWASP list names are used as names only. Nothing in EIO or
EIO-Agents is endorsed by any framework owner.
