"""The L2 exit AST/constant test (split plan §6.2 L2 Exit): no `eio_agents` module outside the staging area references the
rc1 adapter parameter names or the harness Report keys, except at the named allowlist entries.

Scanned: every module under `src/eio_agents` (from L4 there is no staging area to leave out: `_legacy/**`, the
vendored-scorer loader, and `_vendored/**`, the vendored harness-2.x scorer, were deleted). A reference is a string constant that
is not a docstring, an attribute name or a keyword-argument name equal to a watched name.

Watched names:
- the rc1 adapter parameters (§3.10: they pass through the PER untouched until L5a): `legacy_check`, `mapping_relation`,
  `trap`, `legacy_decided_by`, `state_source`;
- the Report keys of archive schemas 1 and 2 (`REPORT_KEYS`: the ProofAgent adapter's `KNOWN_TOP_LEVEL`, pinned here since
  L3, when the adapter moved to the harness; the adapter suite pins the same set by digest, `REPORT_KEYS_SHA256`) that are
  not field names of the neutral formats (the PER schema and the bundle schema): a neutral module never reads a Report. The
  12 keys left out because they are also PER or bundle field names are pinned (`EXCLUDED_REPORT_KEYS`, final L2
  verification L-2): a new schema property named like a Report key fails the test instead of dropping the key from the
  watch list;
- the harness vocabulary of the rc1 output fields and the adapter's crosswalk columns (the review's scan list).

The allowlist is exact: an entry that no longer matches fails the test too. Each entry names the step that removes it.
The method sees string constants, attributes and keywords; a key built by concatenation or an f-string is not seen.
"""
import ast
import json
from pathlib import Path

from eio_agents.base.canon import H, jb

SRC = Path(__file__).resolve().parents[1] / "src" / "eio_agents"
RC1_PARAMETERS = {"legacy_check", "mapping_relation", "trap", "legacy_decided_by", "state_source"}
HARNESS_VOCABULARY = {"traps", "scenario_severity", "legacy_metric", "adjudication_source", "harness_llm", "tools_called", "trap_name",
                      "findings_validation", "per_finding", "legacy_key", "legacy_labels", "legacy_values", "legacy_metrics",
                      "runtime_crosswalk", "intake_keys", "archive_source", "domains_inferred", "data_sensitivity"}
# The top-level keys of a stored ProofAgent Harness report, archive schemas 1 and 2 (04 §3.1, §3.17): the adapter's
# KNOWN_TOP_LEVEL (proofagent_harness.eio_adapter.schema12_adapter), pinned at L3 with its digest (the adapter suite's
# tests/eio_adapter/test_schema12_adapter.py pins the same digest, so the two copies cannot drift apart silently)
REPORT_KEYS = frozenset({
    "archive_schema", "assertion_results", "backpressure_wait_s", "ballot_cache", "bundle_consistency_findings",
    "cache_hit_rate", "cache_reported", "cache_savings_usd", "cached_prompt_tokens", "capsule", "certification",
    "check_verdicts", "checker", "compliance", "confidence", "consensus_log", "context_artifacts",
    "context_digests", "context_engineering", "duration_seconds", "eio", "executive_summary",
    "fallback_cached_prompt_tokens", "fallback_cached_tokens", "fallback_call_count", "fallback_causes",
    "fallback_completion_tokens", "fallback_cost_usd", "fallback_llm_model", "fallback_prompt_tokens",
    "fallback_rate", "final_score", "findings", "frameworks_selected", "governance_gate", "governance_profile",
    "governance_profile_declared", "metadata", "metric_explanations", "mode", "pai", "per_artifact_scores",
    "per_metric", "performance", "primary_cached_prompt_tokens", "primary_cached_tokens", "primary_call_count",
    "primary_completion_tokens", "primary_cost_usd", "primary_llm_model", "primary_prompt_tokens",
    "production_ready", "reliability", "rubric_packs_applied", "score_attribution", "severity", "stage_models",
    "summary", "technical_issues", "token_split", "tokens_used", "top_risk", "transcript", "vote_rule", "warnings"})
REPORT_KEYS_SHA256 = "sha256:005b3c70f021bead0090a2cc05da936c8f750de74b967bca9e5a7ae670f46632"   # H(jb(sorted(REPORT_KEYS)))
EXCLUDED_REPORT_KEYS = {  # the REPORT_KEYS that are also PER or bundle field names (not watched); pinned (L-2)
    "archive_schema", "cached_prompt_tokens", "capsule", "confidence", "context_artifacts", "eio", "findings",
    "governance_profile", "reliability", "severity", "summary", "transcript"}

ALLOWLIST = {  # (module, name): why it is here, and the step that removes it
    # Temporary native rc2 bridge: the pre-L5a projector still writes rc1 fields; this
    # module removes them before the public API returns a record. Remove the bridge
    # with the coordinated rc2 projector rewrite, not by hiding these references.
    **{("per/native_preview.py", name): "isolated L5a native bridge; remove with final rc2 projector rewrite"
       for name in ("adjudication_source", "harness_llm", "legacy_check", "legacy_decided_by", "mapping_relation",
                    "state_source", "trap", "traps")},
    # ---- split plan §6.2 L2 Exit allowlist
    ("semantics/ids.py", "legacy_check"): "the claim-id recipe slot (null natively); renamed source_key at L5a (LS4)",
    ("semantics/ids.py", "trap"): "the fingerprint key (the scenario label, or null); kept until S7 (LS5)",
    ("validation/checker.py", "legacy_check"): "twins of the claim-id slot (c_claim_ids) and of the rc1 claim sort key "
                                               "(rc1_claim_key, c_order); L5a",
    ("validation/checker.py", "trap"): "twin of the fingerprint key (c_findings; S7), and the rc1 label field "
                                       "evidence.turns[].trap read for episodes (D-11; L5a)",
    ("per/projection.py", "legacy_check"): "the rc1 claim sort key; (turn_indices, predicate, id) at L5a",
    # ---- review L2a/L2b H3: the declared fidelity must equal the rc1 mapping relation an adapter claim carries
    ("per/projection.py", "mapping_relation"): "the fidelity/mapping-relation agreement guard; leaves with the rc1 parameters (L5a)",
    # ---- ACCEPTED_DEVIATIONS D-11: rc1 output field names written (or recomputed) by neutral code; renamed at L5a
    ("per/projection.py", "trap"): "D-11: evidence.turns[].trap (scenario at L5a)",
    ("semantics/findings.py", "traps"): "D-11: finding.traps (scenarios at L5a)",
    ("semantics/findings.py", "scenario_severity"): "D-11: finding.scenario_severity (removed S1b/S7)",
    ("semantics/findings.py", ".scenario_severity"): "D-11: the projector's accessor of the declared scenario severity (S7)",
    ("semantics/findings.py", "mapping_relation"): "D-11: finding.mapping_relation, from the declared fidelity (fidelity at L5a)",
    ("scoring/__init__.py", "legacy_metric"): "D-11: metric_view.legacy_metric (adapter extension at L5a)",
    ("per/header.py", "adjudication_source"): "D-11: header.adjudication_source (adapter extension at L5a)",
    ("validation/checker.py", "traps"): "D-11 twin: finding.traps read by c_findings (scenarios at L5a)",
    ("validation/checker.py", "mapping_relation"): "D-11 twin: a CONTEXT_GAP finding's mapping_relation is null (fidelity at L5a)",
    ("validation/verify.py", "trap"): "D-11 twin: evidence.turns[].trap recomputed from the declared labels (scenario at L5a)",
    # ---- decision #31 (L3s): the closed field table keeps the rc1 layout tokens in clear (the rc1 arguments_pointer pattern)
    ("per/privacy.py", "tools_called"): "an rc1 layout token of the closed field table (the rc1 arguments_pointer pattern); L5a",
    ("validation/privacy.py", "tools_called"): "twin: an rc1 layout token of the closed field table; L5a",
}


def _format_field_names():
    def props(o, out):
        if isinstance(o, dict):
            for k in ("properties", "patternProperties"):
                if isinstance(o.get(k), dict):
                    out |= set(o[k])
            if isinstance(o.get("required"), list):
                out |= {x for x in o["required"] if isinstance(x, str)}
            for v in o.values():
                props(v, out)
        elif isinstance(o, list):
            for v in o:
                props(v, out)
        return out
    names = set()
    for rel in ("schemas/per/per-2.0.schema.json", "schemas/per/per-2.0.0-rc2-draft.schema.json",
                "schemas/bundle/bundle-3.0.0-draft.1.schema.json"):
        props(json.loads((SRC / rel).read_text(encoding="utf-8")), names)
    return names


def watched():
    return RC1_PARAMETERS | HARNESS_VOCABULARY | (REPORT_KEYS - EXCLUDED_REPORT_KEYS)


def references(path, names):
    """{(name or .attribute or keyword=): [line]} of the watched names in one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    out = {}
    for n in ast.walk(tree):
        key = None
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and n.value in names:
            key = n.value
        elif isinstance(n, ast.Attribute) and n.attr in names:
            key = "." + n.attr
        elif isinstance(n, ast.keyword) and n.arg in names:
            key = n.arg + "="
        if key:
            out.setdefault(key, []).append(getattr(n, "lineno", 0))
    return out


def scanned():
    for p in sorted(SRC.rglob("*.py")):
        yield p.relative_to(SRC).as_posix(), p

def test_the_watch_list_is_the_rc1_parameters_and_the_report_only_keys():
    w = watched()
    assert RC1_PARAMETERS <= w and {"final_score", "per_metric", "check_verdicts", "consensus_log", "pai"} <= w
    assert "findings" not in w and "claims" not in w                  # PER field names are not Report reads


def test_the_report_keys_are_the_pinned_adapter_set():
    """L3: the set is pinned by value and digest; the adapter suite checks its KNOWN_TOP_LEVEL against the same digest."""
    assert len(REPORT_KEYS) == 65 and H(jb(sorted(REPORT_KEYS))) == REPORT_KEYS_SHA256


def test_the_excluded_report_keys_are_pinned():
    """Review L-2: the Report keys left out of the watch list are exactly the pinned 12 (53 of the 65 are watched). If a
    schema change makes another Report key a format field name, this fails and the key stays watched until the pin is
    changed on purpose."""
    known = set(REPORT_KEYS)
    assert known & _format_field_names() == EXCLUDED_REPORT_KEYS
    assert EXCLUDED_REPORT_KEYS <= known and len(known) == 65 and len(known - EXCLUDED_REPORT_KEYS) == 53


def test_no_neutral_module_references_the_rc1_parameters_or_report_keys_outside_the_allowlist():
    names = watched()
    found = {(rel, k): lines for rel, p in scanned() for k, lines in references(p, names).items()}
    unexpected = {k: v for k, v in found.items() if k not in ALLOWLIST}
    stale = sorted(set(ALLOWLIST) - set(found))
    assert not unexpected, unexpected
    assert not stale, stale


def test_the_scanner_sees_constants_attributes_and_keywords(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""legacy_check in a docstring is not a reference."""\nx = c["trap"]\ny = r.state_source\nf(mapping_relation=1)\n')
    assert references(f, RC1_PARAMETERS) == {"trap": [2], ".state_source": [3], "mapping_relation=": [4]}
