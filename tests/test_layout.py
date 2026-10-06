"""The package layout of the library, and neutral modules never import the ProofAgent staging area."""
import ast
import importlib
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "eio_agents"
SUBPACKAGES = ["base", "ontology", "schemas", "semantics", "evidence", "resolvers", "adjudication", "reliability", "compliance",
               "scoring", "per", "validation"]
# the staging areas are gone: `_reference` (L1), `_legacy` and `_vendored` (L4); an import of any of them would be a regression
STAGING = ("_legacy", "_reference", "_vendored")
NEUTRAL = [s for s in SUBPACKAGES if not s.startswith("_")] + ["adapters.py"]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_exists(name):
    assert (SRC / name / "__init__.py").is_file()
    importlib.import_module(f"eio_agents.{name}")


def _staging_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names = [node.module or ""] + [a.name for a in node.names]
            elif node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for n in names:
            parts = n.split(".")
            if any(p in STAGING for p in parts):
                bad.append(n)
    return bad


def test_neutral_modules_do_not_import_the_staging_area():
    files = [p for n in NEUTRAL for p in ([SRC / n] if n.endswith(".py") else sorted((SRC / n).rglob("*.py")))]
    assert len(files) >= len(NEUTRAL)
    offenders = {str(p.relative_to(SRC)): b for p in files if (b := _staging_imports(p))}
    assert not offenders, offenders


def test_no_module_imports_from_the_package_root():
    """The package root resolves its public names lazily from `api` and the other public modules, so a module imports a
    sibling as `import eio_agents.<name> as <name>`, never `from eio_agents import <name>`: nothing looks names up on the
    root. `cli` is exempt: the root never imports it."""
    def from_root(n, package):
        if n.level == 0:
            return n.module == "eio_agents"
        return not n.module and len(package) < n.level          # `from .. import x` that resolves to the root

    offenders = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC)
        if rel.as_posix() in ("__init__.py", "cli.py"):
            continue
        bad = [f"from {'.' * n.level}{n.module or ''} import " + ", ".join(a.name for a in n.names)
               for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
               if isinstance(n, ast.ImportFrom) and from_root(n, rel.parent.parts)]
        if bad:
            offenders[rel.as_posix()] = bad
    assert not offenders, offenders


def test_eio_data_is_package_data_of_ontology():
    assert not (SRC / "_data").exists()             # the 04 mapping spec is test data (tests/data/spec), not package data
    assert (SRC / "ontology" / "data" / "manifest.yaml").is_file()
    assert sorted(p.name for p in (SRC / "schemas" / "eio").iterdir()) == [
        "0.6.0", "eio-context-0.4.0.jsonld", "eio-context-0.5.0-draft.1.jsonld", "evaluation-claim.schema.json", "evidence-graph.schema.json", "module.schema.json",
        "reference-case.schema.json"]
    # Historical schemas remain packaged alongside the current PER 2.1.0 schema and its 2.1.1 (jury-consensus) twin.
    assert sorted(p.name for p in (SRC / "schemas" / "per").iterdir()) == [
        "per-2.0-neutral-preview.context.jsonld", "per-2.0-rc3-draft.context.jsonld", "per-2.0.0-rc2-draft.schema.json",
        "per-2.0.0-rc2-neutral-preview.schema.json", "per-2.0.0-rc3-draft.schema.json",
        "per-2.0.0-rc3-neutral-preview.schema.json", "per-2.0.0-rc4-draft.schema.json",
        "per-2.0.0-rc5-policy-draft.schema.json",
        "per-2.0.0.schema.json", "per-2.0.context.jsonld", "per-2.0.schema.json",
        "per-2.1.0.schema.json", "per-2.1.1.schema.json", "per-2.1.2.schema.json"]
    assert sorted(p.name for p in (SRC / "schemas" / "scoring").iterdir()) == [
        "native-score-block-0.1.0-draft.schema.json", "native-score-block-0.2.0-draft.1.schema.json",
        "native-score-block-0.3.0-draft.1.schema.json", "native-score-block-0.3.1-draft.1.schema.json",
        "native-score-block-0.3.1.schema.json", "scoring-profile-0.1.0-draft.schema.json", "scoring-profile-0.2.0-draft.1.schema.json"]


MOVED = {  # neutral rows of the §3 move map: defined once, in their eio_agents module, and no longer in the converter
    "base/canon.py": ["es6num", "jcs_str", "jcs", "jb", "sd", "H", "q4", "half_up_int", "normalize"],      # L2a: from semantics
    "base/errors.py": ["ConversionError", "require"],                                                      # L2a: from errors.py
    "ontology/__init__.py": ["STATES", "norm_token", "Ontology", "load"],   # L2a: STATES, norm_token from semantics
    "evidence/redaction.py": ["EMAIL", "SSN", "IBAN", "PAN", "SECRET", "LAST4", "MARKER", "EXCERPT_MAX", "luhn", "redact",
                              "excerpt_of"],
    "evidence/locate.py": ["locate"],
    "evidence/witness.py": ["can_prove", "witnessing_anchored"],
    "evidence/contract.py": ["in_scope", "contract_check"],
    "evidence/context_refs.py": ["context_line_ref", "ctx_absence_ref", "context_refs_for_criterion"],
    "evidence/refs.py": ["RefStore", "span_ref", "receipt_ref", "computed_ref", "no_call_ref"],   # L2b: constructors
    "semantics/why.py": ["KIND_PHRASE", "AXIS_SYMBOLS", "fmt_score", "fmt_decimal", "fmt_ids", "fmt_turn_list", "render_param",
                         "render", "ZB", "basis", "cited_first", "explanation", "claim_driven"],
    "semantics/release.py": ["RELEASE_SEMANTICS", "GATE_CLAUSES_MAX", "oversight_gate", "metric_label", "owning", "gates",
                             "release"],   # L2b: gates, release; L2c: RELEASE_SEMANTICS, metric_label (task 9)
    "semantics/claims.py": ["make_claim", "check_claims"],                                          # L2b
    "semantics/findings.py": ["findings"],                                                          # L2b
    "semantics/proof.py": ["claim_proven"],                                                         # L2b (rc1 rule until L2c)
    "adjudication/__init__.py": ["pool", "invalid_because"],                                        # L2b
    "compliance/selection.py": ["select_frameworks"],                                               # L2b
    "semantics/coverage.py": ["eff_impact", "coverage_step"],
    "semantics/scope.py": ["domains_declared", "resolve_domains", "escalations", "qualify"],       # L2b: qualify
    "reliability/__init__.py": ["BR", "band_of", "trial_index", "reliability_block"],               # L2b: trials
    "compliance/controls.py": ["controls_step"],
    "scoring/__init__.py": ["ScoreView", "cap_claims", "published_metric_set", "NO_VALUE_REASON"],   # L2b; L2c task 7
    # L4: the engine (the ported main-tree compute_pai core), the profile registry and the attested mechanism, the draft signature
    "scoring/engine.py": ["INDEX_PARAMETERS", "parameter", "check_parameters", "IndexAxis", "ReadinessIndex", "weighted_geomean",
                          "ramp_entry", "band_of", "severity_for", "normalized_weights", "verdict_of", "margin_of", "readiness_index"],
    "scoring/profiles.py": ["REFERENCE_ID", "REFERENCE_VERSION", "document_problems", "profile_sha256", "reference_document",
                            "profiles", "load_profile", "resolve_profile", "record_profile"],
    "scoring/reference.py": ["score"],
    "resolvers/__init__.py": ["RESOLVER_READS", "natural_resolver"],                                # L2b: MAP-20
    "per/__init__.py": ["PER_VERSION"],
    "per/header.py": ["CONVERTER", "SCHEMA_URI", "archive_identity", "header"],                    # L2b: from the converter
    "per/bundle.py": ["read", "validate_sections", "accept_producer_declared", "check_vocabulary", "check_stage_digests",
                      "recompute"],   # L2b; check_vocabulary L2c (review #4, #5)
    "per/conformance.py": ["RC1_ONLY", "rc1_only_rows", "rc1_only", "schema_errors", "id_problems", "check_record"],   # L2c (H2)
    "per/projection.py": ["project", "Projection", "capsule_block", "rc1_claim_key"],                  # L2b
    "per/evidence.py": ["KIND_ORDER", "order_refs", "cited_ref_ids"],
    "per/capsule.py": ["CAPSULE_FIELDS"],
    "per/context.py": ["embedded"],
    "per/limitations.py": ["CATALOGUE", "load_catalogue", "limitation"],
}
# ProofAgent rows of the §3 move map: none is left in EIO-Agents from L4 (the vendored-scorer loader `_legacy/harness2x.py`
# and the vendored scorer `_vendored/` were deleted). The adapter modules are in the harness (`proofagent_harness.eio_adapter`);
# their rows are checked there (tests/eio_adapter/test_adapter_layout.py), with the converter half of the check below.


def _module_level_names(path: Path) -> set[str]:
    out = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return out


def test_moved_neutral_rows_are_defined_once():
    """Each neutral row is defined in its module; that the adapter's converter defines none of them is the harness's half
    (tests/eio_adapter/test_adapter_layout.py)."""
    for rel, names in MOVED.items():
        defined = _module_level_names(SRC / rel)
        assert set(names) <= defined, (rel, sorted(set(names) - defined))


def _methods(path: Path, cls: str) -> set[str]:
    node = [n for n in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef) and n.name == cls][0]
    return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}


def test_no_proofagent_rows_are_left_in_a_staging_area():
    """From L4 no staging area is left: the ProofAgent adapter moved to the harness at L3, the vendored scorer and its loader
    were deleted at L4 (split plan §6.2 L4 task 7)."""
    assert not [s for s in STAGING if (SRC / s).exists()]         # check_per split (L1), why_chain deleted (L1), L4 deletions


# ---- the reference verifier: neutral rows in `validation`, the rest in `legacy_verifier`
VERIFIER_MOVED = {
    "validation/canon.py": ["_num", "_ESC", "_str", "jcs", "jb", "sha", "sd", "q4"],
    "validation/reader.py": ["EIO", "load_catalogue"],
    "validation/render.py": ["PHRASE", "r_score", "r_param", "render"],
    "validation/pointer.py": ["ID_KEYED", "resolve_pointer"],
    "validation/redaction.py": ["A_", "EXCERPT_LIMIT", "REDACTION_CLASSES", "REDACTION_MARKER", "luhn_ok", "class_matches",
                                "unmarked", "redact_span", "expected_excerpt", "CUT_ZONE", "surviving_matches"],
    "validation/gates.py": ["REPRO_FIELDS", "gate_met", "gate_inputs"],
    "validation/checker.py": ["VER6", "RELEASE_SEMANTICS", "CAPSULE_ORDER", "IMP", "SEVR", "KORDER", "FAULT", "SCORED", "READS",
                              "rc1_claim_key", "Checker", "report"],
    "validation/validate.py": ["CHECKS", "rows_as_problems", "check_one", "validate", "validate_bundle"],     # L2c (carry note 5)
    "validation/verify.py": ["c_sources", "verify"],                                                         # L2c (task 5)
    "validation/explain.py": ["explain"],
}
NEUTRAL_CHECKS = ["run", "wa", "basis", "explanations", "c_schema", "c_nfc", "c_claim_schema", "c_eio_digests", "cited",
                  "c_refs_resolve", "c_witness", "c_counts", "c_claim_ids", "c_contract", "eff_impact", "c_coverage", "band",
                  "c_explanations", "c_gates", "c_numbers", "c_wording", "c_pointers", "c_per_sha",
                  "c_order", "c_limitations", "c_release", "in_scope"]              # L2c: moved whole (row 19)
SPLIT_CHECKS = ["c_header", "c_eio_ids", "c_domains", "c_claim_params", "c_findings", "c_controls", "c_scores", "c_reliability",
                "episode_turns", "census", "targets_unobservable", "cap_proof"]   # L2c: neutral half here, legacy override
LEGACY_CHECKS = ["proven", "c_premise", "c_archive"]     # the ProofAgent adapter's `LegacyChecker` (harness, since L3)


def test_verifier_rows_are_split_between_validation_and_the_legacy_verifier():
    """The neutral half: every verifier row is defined in `validation`, and the legacy-only checks are not. The legacy half
    (`LegacyChecker` overrides the split checks and holds the legacy ones) is the harness's, since the legacy verifier
    moved with the adapter at L3 (tests/eio_adapter/test_adapter_layout.py)."""
    for rel, names in VERIFIER_MOVED.items():
        assert set(names) <= _module_level_names(SRC / rel), (rel, sorted(set(names) - _module_level_names(SRC / rel)))
    base = _methods(SRC / "validation" / "checker.py", "Checker")
    assert set(NEUTRAL_CHECKS) <= base and set(SPLIT_CHECKS) <= base
    assert not set(LEGACY_CHECKS) & base


def test_the_neutral_checker_answers_its_hooks_from_the_record():
    """The census accepts a declared registry cause for a predicate without claims (an rc1 record does not carry the
    producer capability registry) and recomputes the three native causes; the episode of a claim is read from the
    record's scenario labels, and a claim on unlabelled turns is its own episode."""
    from eio_agents.validation.checker import Checker
    rec = {"claims": [], "evidence": {"refs": [], "turns": [{"turn_index": 1, "trap": "a"}, {"turn_index": 2, "trap": "a"},
                                                         {"turn_index": 3, "trap": None}]}, "findings": [], "limitations": []}
    k = Checker(rec, None, {}, "x")
    assert k.census("p", [], "UNREACHABLE") == "UNREACHABLE" and k.census("p", []) == "NEVER_SELECTED"
    assert k.census("p", [{"state": "NOT_APPLICABLE"}], "UNREACHABLE") == "PRECONDITION_ABSENT"
    assert k.episode_turns({"turn_indices": [2]}) == {1, 2} and k.episode_turns({"turn_indices": [3]}) == {3}
    assert k.in_scope({"kind": "AGENT_SPAN", "turn_index": 1}, "episode", {"turn_indices": [2]})
    assert not k.in_scope({"kind": "AGENT_SPAN", "turn_index": 3}, "episode", {"turn_indices": [2]})


def test_the_verifier_imports_no_converter_module():
    """Contract P3: `validation` reads the release files itself. Besides its own modules it imports only the path constants
    and loaders of `schemas` and the catalogue file of `per.limitations`, and it finds the release without `ontology`."""
    from eio_agents.ontology import DATA_DIR
    from eio_agents.validation import reader
    allowed = {"eio_agents.schemas", "eio_agents.per.limitations"}
    offenders = {}
    for p in sorted((SRC / "validation").rglob("*.py")):
        mods = set()
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods.add(node.module)
        bad = sorted(m for m in mods if m.split(".")[0] == "eio_agents" and m not in allowed
                     and not m.startswith("eio_agents.validation"))
        if bad:
            offenders[p.name] = bad
    assert not offenders, offenders
    assert reader.EIO_DIR == DATA_DIR
