"""Profile-driven scoring primitives and draft reference-profile boundaries.

Historical producer-specific vectors and projection assertions are preserved
in the external adapter compatibility corpus, not this standalone suite.
"""
import ast
import copy
import json
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.scoring import engine, profiles, reference
from eio_agents.scoring.engine import readiness_index, weighted_geomean

SRC = Path(__file__).resolve().parents[1] / "src" / "eio_agents" / "scoring"
Q, E, C, G = "eio.axis.context", "eio.axis.behaviour", "eio.axis.compliance", "eio.axis.governance"
AXES = [Q, E, C, G]


def sample_params():
    """A synthetic test profile; none of these numbers is in the engine."""
    return {"method": "weighted-geometric-mean", "epsilon": 1.0, "readiness_ceiling": 49.0, "axis_order": list(AXES),
            "axis_weights": dict.fromkeys(AXES, 1.0), "required_axes": list(AXES),
            "band_ramp": {"bands": [{"min": 95, "band": "A"}, {"min": 85, "band": "B"}, {"min": 70, "band": "C"},
                                    {"min": 60, "band": "D"}, {"min": 50, "band": "E"}, {"min": 0, "band": "F"}], "otherwise": "F"},
            "verdict_ramp": {"bands": [{"min": 85, "verdict": "ready"}, {"min": 60, "verdict": "ready_with_caveats"}],
                             "otherwise": "not_ready", "caveat": "ready_with_caveats", "blocked": "blocked", "incomplete": "indeterminate"},
            "severity_bands": {"bands": [{"min": 85.0, "severity": "pass"}, {"min": 70.0, "severity": "info"},
                                         {"min": 50.0, "severity": "warn"}, {"min": 30.0, "severity": "fail"}], "otherwise": "critical"},
            "max_margin": 20.0, "sampling_axis": E, "sampling_pseudo_counts": [2, 4], "scale": [0, 100], "decimals": 1}


def attested_doc():
    return {"id": "example.adapter-scoring", "version": "1.0.0", "verifiability": "attested", "parameters": sample_params(),
            "published_metrics": ["eio.metric.safety"], "g_component_ids": [],
            "formulas": {"readiness": "weighted geometric mean"}}


# ------------------------------------------------------------------ no numeric defaults (AST)
def _module_level_numbers(tree):
    out = []
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if value is not None:
            out += [n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    return out


def _numeric_defaults(tree):
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for d in list(fn.args.defaults) + [x for x in fn.args.kw_defaults if x is not None]:
                if isinstance(d, ast.Constant) and isinstance(d.value, (int, float)) and not isinstance(d.value, bool):
                    out.append((getattr(fn, "name", "lambda"), d.value))
    return out


@pytest.mark.parametrize("path", sorted(SRC.glob("*.py")), ids=lambda p: p.name)
def test_scoring_has_no_module_level_float_constant_and_no_numeric_default(path):
    """§3.7: epsilon, the ceiling, the weights and the ramp are profile parameters; no module of eio_agents.scoring holds a
    module-level float constant or a numeric default argument."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert _module_level_numbers(tree) == [] and _numeric_defaults(tree) == []


def test_the_ast_check_sees_a_float_constant_and_a_numeric_default():
    assert _module_level_numbers(ast.parse("_EPS = 1.0\n_BLOCK_CAP = min(49.0, 50)")) == [1.0, 49.0]
    assert _numeric_defaults(ast.parse("def f(x, eps=1.0, *, cap=49): pass")) == [("f", 1.0), ("f", 49)]


# ------------------------------------------------------------------ the engine: no defaults, the vectors
@pytest.mark.parametrize("name", engine.INDEX_PARAMETERS)
def test_every_parameter_is_required(name):
    p = sample_params()
    del p[name]
    with pytest.raises(ConversionError) as e:
        readiness_index(dict.fromkeys(AXES, 50.0), p, blocked=False)
    assert e.value.code == "SCORING_PROFILE" and name in str(e.value)


def test_a_null_parameter_is_refused():
    p = sample_params()
    p["epsilon"] = None
    with pytest.raises(ConversionError, match="epsilon"):
        readiness_index(dict.fromkeys(AXES, 50.0), p, blocked=False)


def test_weighted_geomean_takes_epsilon_as_a_keyword_without_default():
    with pytest.raises(TypeError):
        weighted_geomean([(50.0, 1.0)])                                # the missing epsilon is the point
    assert weighted_geomean([(0.0, 1.0), (100.0, 1.0)], epsilon=1.0) == pytest.approx(10.0)
    assert weighted_geomean([(0.0, 1.0), (100.0, 1.0)], epsilon=0.01) == pytest.approx(1.0)
    assert weighted_geomean([(None, 1.0), (50.0, 0.0)], epsilon=1.0) is None


def test_sample_profile_determines_readiness_and_blocking():
    vals = {Q: 90.0, E: 47.8, C: 63.8, G: 52.0}
    idx = readiness_index(vals, sample_params(), blocked=False)
    assert idx.complete and idx.weakest == E and idx.value > 49
    blocked = readiness_index(vals, sample_params(), blocked=True)
    assert blocked.raw == idx.raw and blocked.value == 49 and blocked.verdict == "blocked"


def test_completeness_weights_discounts_and_the_verdict_ramp():
    p = sample_params()
    part = readiness_index({Q: 90.0, E: 80.0, C: None, G: 70.0}, p, blocked=False)
    assert part.missing_axes == [C] and not part.complete and part.verdict == "indeterminate" and part.coverage == [Q, E, G]
    top = readiness_index(dict.fromkeys(AXES, 90.0), p, blocked=False, caveat=True)
    assert (top.verdict, readiness_index(dict.fromkeys(AXES, 90.0), p, blocked=False).verdict) == ("ready_with_caveats", "ready")
    assert readiness_index(dict.fromkeys(AXES, 40.0), p, blocked=False).verdict == "not_ready"
    d = readiness_index({Q: 100.0, E: 100.0, C: 100.0, G: 1.0}, p, blocked=False, discounts={G: 0.0})
    assert d.raw == 100.0 and G in d.coverage                         # a weight of 0: covered, not contributing
    with pytest.raises(ConversionError):
        readiness_index({"eio.axis.unknown": 1.0}, p, blocked=False)
    p2 = sample_params()
    p2["axis_weights"] = {Q: 1.0, E: 3.0, C: 1.0, G: 1.0}
    assert engine.normalized_weights(p2)[E] == 0.5 and engine.normalized_weights(sample_params())[Q] == 0.25


def test_the_margin_rule():
    """The ported `_margin`: the sampling term of E over the turns (pseudo-counts from the profile), the measured axis
    uncertainty, the clamp at max_margin; None when nothing is available (never 0) and on a blocked index."""
    p = sample_params()
    vals = {Q: 90.0, E: 96.1, C: 73.2, G: 72.0}
    assert readiness_index(vals, p, blocked=False).margin is None
    m = readiness_index(vals, p, blocked=False, sample_size=40).margin
    assert m is not None and 0 < m < 20
    assert readiness_index(vals, p, blocked=False, sample_size=40, axis_margins={E: 100.0}).margin == 20.0
    p["max_margin"] = 5.0
    assert readiness_index(vals, p, blocked=False, sample_size=40, axis_margins={E: 100.0}).margin == 5.0
    assert readiness_index(vals, p, blocked=True, sample_size=40).margin is None
    i = readiness_index(vals, sample_params(), blocked=False, axis_margins={E: 100.0})
    assert i.interval == (62.2, 100) and engine.severity_for(None, p["severity_bands"]) == ""
    assert [engine.severity_for(s, p["severity_bands"]) for s in (90, 75, 55, 35, 10)] == ["pass", "info", "warn", "fail", "critical"]


# ------------------------------------------------------------------ the profile document, the registry, the attested mechanism
def test_the_profile_digest_is_the_jcs_of_the_document_without_its_sha256():
    doc = attested_doc()
    d = profiles.profile_sha256(doc)
    assert d.startswith("sha256:") and profiles.profile_sha256({**doc, "sha256": "sha256:" + "0" * 64}) == d
    doc2 = copy.deepcopy(doc)
    doc2["parameters"]["epsilon"] = 0.01
    assert profiles.profile_sha256(doc2) != d


def _declared(doc, **over):
    return {"id": doc["id"], "version": doc["version"], "verifiability": doc["verifiability"],
            "sha256": profiles.profile_sha256(doc), "document": doc, **over}


def test_unapproved_adapter_profile_fails_closed(eio):
    doc = attested_doc()
    with pytest.raises(ConversionError) as e:
        profiles.resolve_profile(_declared(doc), producer_kind="adapter", ontology=eio)
    assert e.value.code == "SCORING_PROFILE"


def test_the_registry_holds_the_draft_reference_scoring(eio):
    """§4.3: the rederivable profiles EIO-Agents ships: the EIO-Agents reference scoring, a draft (its id and several
    parameters are EIO gaps); its published metric set is every eio.metric.* of the loaded release."""
    reg = profiles.profiles(eio)
    assert [(r["id"], r["version"], r["verifiability"], r["status"]) for r in reg] == [
        (profiles.REFERENCE_ID, profiles.REFERENCE_VERSION, "rederivable", "draft"),
        (profiles.REFERENCE_ID, profiles.REFERENCE_FULL_VERSION, "rederivable", "draft")]
    doc = profiles.load_profile(profiles.REFERENCE_ID, profiles.REFERENCE_VERSION, eio)
    assert profiles.document_problems(doc) == [] and reg[0]["sha256"] == profiles.profile_sha256(doc)
    assert doc["published_metrics"] == [m["id"] for m in eio.metrics] and len(doc["published_metrics"]) == 9
    assert doc["parameters"]["epsilon"] == 0.01 and doc["parameters"]["axis_weights"] == dict.fromkeys(AXES, 0.25)
    assert doc["ontology_sha256"] == eio.ontology_sha256
    assert doc["parameters"]["band_ramp"] is None and doc["parameters"]["max_margin"] is None
    assert doc["g_component_ids"] == ["release_gate", "human_oversight", "policy_conformance",
                                      "obligation_coverage", "evidence_freshness"]
    full = profiles.load_profile(profiles.REFERENCE_ID, profiles.REFERENCE_FULL_VERSION, eio)
    assert full["g_component_ids"] == ["release_gate", "human_oversight", "policy_conformance",
                                       "obligation_coverage"]
    assert reg[1]["sha256"] == profiles.profile_sha256(full)
    assert doc["gaps"]
    decl = {"id": doc["id"], "version": doc["version"], "verifiability": "rederivable", "sha256": profiles.profile_sha256(doc),
            "document": None}
    assert profiles.resolve_profile(decl, producer_kind="native", ontology=eio) == doc
    with pytest.raises(ConversionError, match="SCORING_PROFILE_DIGEST"):
        profiles.resolve_profile({**decl, "sha256": "sha256:" + "3" * 64}, producer_kind="native", ontology=eio)
    with pytest.raises(ConversionError, match="no rederivable scoring profile"):
        profiles.load_profile("example.adapter-scoring", "1.0.0", eio)  # an attested profile is never in the registry
    with pytest.raises(ConversionError, match="SCORING_PROFILE"):
        readiness_index(dict.fromkeys(AXES, 50.0), doc["parameters"], blocked=False)   # a draft: parameters are gaps


def test_the_reference_scoring_signature_is_a_draft(eio):
    import inspect
    assert list(inspect.signature(reference.score).parameters) == [
        "claims", "trials", "control_statuses", "context_assessment", "scope", "coverage", "profile", "ontology"]
    with pytest.raises(NotImplementedError, match="S1b"):
        reference.score([], None, [], None, {}, {}, profiles.reference_document(eio), ontology=eio)


def test_no_attested_adapter_document_is_package_data():
    """The draft reference profile ships; no adapter-attested document does."""
    def documents(o):
        if isinstance(o, dict):
            if {"verifiability", "parameters", "published_metrics"} <= set(o):
                yield o
            for v in o.values():
                yield from documents(v)
        elif isinstance(o, list):
            for v in o:
                yield from documents(v)
    hits = [(p.name, d.get("id")) for p in SRC.parent.rglob("*.json")
            if not p.name.endswith(".schema.json") for d in documents(json.loads(p.read_text(encoding="utf-8")))]
    assert sorted(hits) == sorted([
        ("reference-profile-0.2.0-draft.1.json", "eio-agents.reference-scoring"),
        ("reference-profile-0.3.1-draft.1.json", "eio-agents.reference-scoring"),
        ("reference-profile-0.3.0-draft.1.json", "eio-agents.reference-scoring"),
    ])
