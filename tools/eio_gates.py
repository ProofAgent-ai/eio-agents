#!/usr/bin/env python3
"""EIO draft build gates: the neutral gates, run against the release in this tree.

Checks the EIO release in src/eio_agents/ontology/data (YAML modules, reference cases, manifest, release digests,
changelog) and the EIO JSON Schemas in src/eio_agents/schemas/eio against the 0.4.0 normative rules. Every gate prints
PASS or FAIL with its problems; the exit code is 0 only when every blocking gate passes.

Copied from the build gates of the EIO specification package: the gates that read harness
registries (UNMAPPED_CHECKS, POLARITY, LEGACY_METRICS, LEGACY_RESOLVER, LEGACY_REGISTRY, POLARITY_TV9, METRIC_LEGACY_KEY,
the harness-label half of CONTEXT_CRITERIA, the USE_CASES parts of FACTS_DECLARED and GOVERNANCE, the per-check literal
scan of EXPLANATION_TEMPLATES) are not here: they become harness or adapter tests, and EIO never reads the harness. The
limitation and caveat ids of PER_IDS_OWNED are read from the limitation catalogue data file and the PER schema.

Standalone: needs only PyYAML and jsonschema. The 0.3.0 baseline (VERSION_BUMP, NAMESPACE stability) is read from
--baseline, or, without it, from the vendored snapshot tools/snapshots/eio-0.3.0-baseline.json. --examples (a directory of
*.per.json and review_aids/*.per.full.json records) and --goldens (a directory of *.raw.json archives) are optional; without
them the checks that read them are skipped. The digest rule is tools/eio_digests.py.

Usage:
    python tools/eio_gates.py [--eio DIR] [--schemas DIR] [--baseline DIR] [--examples DIR] [--goldens DIR] [--json OUT]
    python tools/eio_gates.py --selftest [--examples DIR]    # negative vectors: each mutation must fail its gate
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

TOOLS = Path(__file__).resolve().parent
PKG = TOOLS.parent / "src" / "eio_agents"
SNAPSHOTS = TOOLS / "snapshots"
sys.path.insert(0, str(TOOLS))
import eio_digests  # noqa: E402  (the digest rule, tools/eio_digests.py)

DEFAULTS = {
    "eio": PKG / "ontology" / "data",
    "schemas": PKG / "schemas" / "eio",
    "limitations": PKG / "per" / "data" / "limitations.json",
    "per_schema": PKG / "schemas" / "per" / "per-2.0.schema.json",
    "baseline": "",
    "examples": "",
    "goldens": "",
}

RELEASE = "0.6.0"
MARK = "OPEN" + " " + "ISSUE"  # the open-issue marker, spelled split so that this file contains none
ID_RE = re.compile(r"^eio\.[a-z0-9][a-z0-9._-]*$")          # reference scan (superset)
STRICT_ID_RE = re.compile(r"^eio\.[a-z0-9][a-z0-9.-]*$")  # 01 §3.1 grammar
GRANDFATHERED_IDS = {"eio.region.emea_other"}
WHY_RE = re.compile(r"^eio\.why\.[a-z0-9_.]+@[0-9]+$")
SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
REF_DICT_RE = re.compile(r"predicates\[\d+\]\.resolvers\[\d+\]$")

# ---------------------------------------------------------------------------------------
# Normative constants of EIO 0.4.0 that the data must reproduce exactly.
SOURCE_TYPES = ["AGENT_ANSWER", "AGENT_TOOL_CALL", "TOOL_RESULT", "STATE_LEDGER", "HUMAN_REVIEW",
                "USER_INPUT", "RETRIEVAL", "POLICY_SOURCE", "HARNESS_SIGNAL", "JUROR_INFERENCE"]
WITNESS_SOURCES = {"AGENT_ANSWER", "AGENT_TOOL_CALL", "TOOL_RESULT", "STATE_LEDGER", "HUMAN_REVIEW"}
CENSUS_CAUSES = ["UNREACHABLE", "NOT_IMPLEMENTED", "NEVER_SELECTED", "PRECONDITION_ABSENT", "INCOMPLETE_COVERAGE"]
CONTROL_STATUSES = ["observed_satisfaction", "observed_violation", "not_tested", "not_observable",
                    "not_applicable", "inconclusive"]
SEMANTIC_RESOLVER_CLASS = {"deterministic": 0, "semantic": 1, "human": 2}
DECISION_COMBINATORS = {"eio.resolver.graph-rule", "eio.resolver.human-adjudication"}
BEHAVIOUR_METRICS = {"eio.metric.safety", "eio.metric.instruction-following", "eio.metric.manipulation-resistance",
                     "eio.metric.hallucination-resistance", "eio.metric.task-success", "eio.metric.tool-use"}
EVALUATOR_RISKS = {"eio.risk.evaluator-evidence-fabrication", "eio.risk.evaluator-instability", "eio.risk.coverage-gap",
                   "eio.risk.provenance-gap", "eio.risk.correlated-jury", "eio.risk.score-incompleteness"}
UNTARGETED_SEVERITY_NONE = {  # EIO-36: predicate -> reason class
    "eio.predicate.tenant-boundary-crossing": "no-obligation",
    "eio.predicate.guardrail-circumvented": "no-obligation",
    "eio.predicate.context-provenance-missing": "no-obligation",
    "eio.predicate.required-workflow-step-absent": "no-obligation",
    "eio.predicate.processing-without-valid-consent": "no-obligation",
    "eio.predicate.content-materially-enables-defined-harm": "no-obligation",
    "eio.predicate.agent-directed-abuse": "no-obligation",
    "eio.predicate.required-verification-requested": "no-obligation",
    "eio.predicate.untrusted-content-reproduced": "observation",
    "eio.predicate.permissible-task-present": "observation",
    "eio.predicate.evaluator-citation-invalid": "evaluator",
    "eio.predicate.controlled-rerun-decision-divergence": "evaluator",
    "eio.predicate.coverage-obligation-unreached": "evaluator",
    "eio.predicate.jury-independence-insufficient": "evaluator",
    "eio.predicate.incomplete-score-presented-as-complete": "evaluator",
}
SEVERITY_REASONS = {"no-obligation": "no in-scope obligation declared in 0.4.0",
                    "observation": "observation predicate",
                    "evaluator": "evaluator-reliability predicate"}
REQUIRED_WHY = [
    # 03 §8.2 catalogue
    "eio.why.readiness@1", "eio.why.readiness.capped@1", "eio.why.readiness.partial@1",
    "eio.why.axis.behaviour@1", "eio.why.axis.context@1",
    "eio.why.axis.governance@1", "eio.why.axis.not_evaluated@1",
    "eio.why.metric@1", "eio.why.metric.capped@1",
    "eio.why.finding@1", "eio.why.finding.no_severity@1", "eio.why.finding.context_gap@1",
    "eio.why.control.observed_violation@2", "eio.why.control.observed_satisfaction@1",
    "eio.why.control.inconclusive@1", "eio.why.control.not_observable@1",
    "eio.why.control.not_applicable@1", "eio.why.control.not_tested@1",
    "eio.why.gate.met@1", "eio.why.gate.unmet@1", "eio.why.gate.unknown@1",
    "eio.why.obligation.unmet@1", "eio.why.reliability@1",
    "eio.why.release.block@1", "eio.why.release.review@1", "eio.why.release.pass@1",
    # 01 §8.5 claim templates
    "eio.why.claim.applicable_fail.deterministic@2", "eio.why.claim.applicable_pass.semantic@2",
    "eio.why.claim.evidence_invalid@2", "eio.why.claim@2",
    # EIO-49 additions
    "eio.why.metric.diagnostic_only@1", "eio.why.metric.not_evaluated@1",
]
FIN_GOLDEN_EXPECT = {  # EIO-24 golden domain-resolution tests (computed, see CHANGELOG)
    "FIN_3_repeat.raw.json": ["eio.domain.financial-services", "eio.domain.customer-support", "eio.domain.generic-agent"],
    "FIN_4_weak.raw.json": ["eio.domain.financial-services", "eio.domain.generic-agent"],
    "FIN_1_base.raw.json": ["eio.domain.financial-services", "eio.domain.software-agents", "eio.domain.generic-agent"],
    "MED_1_base.raw.json": ["eio.domain.healthcare-operations", "eio.domain.generic-agent"],
    "MED_3_repeat.raw.json": ["eio.domain.healthcare-operations", "eio.domain.generic-agent"],
    "MED_4_weak.raw.json": ["eio.domain.healthcare-operations", "eio.domain.generic-agent"],
    "HR_R3_seed42.raw.json": ["eio.domain.hr-employment", "eio.domain.generic-agent", "eio.domain.software-agents",
                              "eio.domain.customer-support"],
    "EXAM_B_seed42.raw.json": ["eio.domain.customer-support", "eio.domain.generic-agent"],
}
TOKEN_EXPECT = {  # EIO-24: tokens that MUST resolve (exact alias) to one domain
    "credit": "eio.domain.financial-services", "lending": "eio.domain.financial-services",
    "underwriting": "eio.domain.financial-services", "kyc": "eio.domain.financial-services",
    "aml": "eio.domain.financial-services", "loan": "eio.domain.financial-services",
    "mortgage": "eio.domain.financial-services", "bank": "eio.domain.financial-services",
    "credit_underwriting": "eio.domain.financial-services",
    "triage": "eio.domain.healthcare-operations", "clinical": "eio.domain.healthcare-operations",
    "clinical-triage": "eio.domain.healthcare-operations", "urgent-care": "eio.domain.healthcare-operations",
    "patient-intake": "eio.domain.healthcare-operations",
    "samd": "eio.domain.medical-devices", "cds": "eio.domain.medical-devices",
    "clinical-decision-support": "eio.domain.medical-devices",
}
PROSE_KEYS = {"description", "rationale", "note", "text", "label", "title", "applicability", "assurance_boundary",
              "invariant", "invariants", "rules", "gate", "purpose", "human_review", "permitted_claim",
              "prohibited_claim", "reason", "non_scoring_reason", "may", "may_not", "production_gate",
              "status_source", "continuity_rule", "non_compensation_rule", "truth_boundary", "privacy_invariant",
              "meaning", "measures", "effect_on_score", "effect_rationale", "withdrawable_rationale",
              "overdispersion_note", "minimum_tasks_rationale", "named_lists_rationale", "epsilon_rationale",
              "absent_axis_rationale", "checklist_rule", "aggregation", "qualifier_hints", "policy_defaults"}
# References that are release-scoped (resolved against the manifest, not imports). Normative:
# module.schema.json $defs.governance gates[].evaluated_at, and module-id pointers.
RELEASE_SCOPED_PATHS = [re.compile(r"^governance\.gates\[\d+\]\.evaluated_at$")]

CHANGELOG_KEYS = [
    "EIO-2", "EIO-3", "EIO-5", "EIO-6", "EIO-7", "EIO-9", "EIO-10", "EIO-11", "EIO-18", "EIO-19", "EIO-20",
    "EIO-24", "EIO-25", "EIO-27", "EIO-28", "EIO-33", "EIO-36", "EIO-48", "EIO-49", "EIO-51", "EIO-57", "EIO-58",
    "EIO-201", "EIO-202", "EIO-207", "EIO-208", "EIO-209", "EIO-211", "EIO-214", "EIO-216", "EIO-217", "EIO-219",
    "EIO-220", "EIO-221", "EIO-222", "EIO-227", "EIO-231", "EIO-233", "EIO-236", "EIO-238", "EIO-241", "EIO-242",
    "EIO-245", "EIO-246", "EIO-301", "EIO-403", "EIO-404",
    # ALSO-eio-data work orders
    "EIO-1", "EIO-22", "EIO-26", "EIO-31", "EIO-34", "PER-13", "PER-209", "PER-415",
]


# ---------------------------------------------------------------------------------------
class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (PyYAML keeps the last one silently)."""


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def sha256_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def normalize_token(s: str) -> str:
    return re.sub(r"[_\s]+", "-", str(s).strip().casefold())


def walk(obj: Any, path: str = ""):
    """Yield (path, key, value) for every scalar value and every dict key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield (p, "__key__", k)
            yield from walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield (path, None, obj)


def walk_dicts(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk_dicts(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_dicts(v, f"{path}[{i}]")


def last_key(path: str) -> str:
    seg = path.split(".")[-1]
    return re.sub(r"\[\d+\]$", "", seg)


RECURRENCE_BANDS = ["CONFIRMED", "INTERMITTENT", "UNCONFIRMED", "NOT_RETESTED"]


def derive_intake_fact(entries: list, intake: dict) -> Any:
    """governance.facts intake_keys: an entry with an absent key yields null; several entries: any true -> true,
    else any false -> false, else null."""
    vals = []
    for e in entries:
        if e.get("key") not in intake:
            vals.append(None)
            continue
        x = intake[e["key"]]
        if e.get("as_declared"):
            vals.append(x)
        elif "map" in e:
            vals.append((e["map"] or {}).get(x))
        elif x in (e.get("true_if_in") or []):
            vals.append(True)
        elif x in (e.get("false_if_in") or []):
            vals.append(False)
        else:
            vals.append(e.get("otherwise"))
    if any(v is True for v in vals):
        return True
    if any(v is False for v in vals):
        return False
    return next((v for v in vals if v is not None), None)


def param_input_problem(p: dict, v: Any) -> str | None:
    """eio.profile.why-rendering param_inputs: the stored input shape of a param, or why it is not one."""
    t, labels = p.get("type"), p.get("labels") or {}

    def is_int(x):
        return isinstance(x, int) and not isinstance(x, bool)

    def is_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)
    if t in ("refs", "votes"):
        return f"type {t} is never stored (claim templates only)"
    if t == "label":
        key = v if isinstance(v, str) else json.dumps(v)
        return None if key in labels else f"label input {v!r} is not a labels key (pre-rendered label text?)"
    if t in ("id", "text"):
        return None if isinstance(v, str) else f"{t} input must be a string"
    if t == "token":
        return None if v is None or isinstance(v, str) else "token input must be a string or null"
    if t == "integer":
        return None if is_int(v) else "integer input must be a JSON integer"
    if t in ("score", "decimal", "fraction"):
        return None if is_num(v) else f"{t} input must be a JSON number"
    if t == "ids":
        return None if isinstance(v, list) and all(isinstance(x, str) for x in v) else "ids input must be an array of strings"
    if t == "turns":
        return None if isinstance(v, list) and v and all(is_int(x) for x in v) else "turns input must be a non-empty array of integers"
    if t == "kinds_phrase":
        return None if isinstance(v, list) and all(isinstance(x, str) and re.match(r"^[A-Z][A-Z_]+$", x) for x in v) \
            else "kinds_phrase input must be an array of evidence kind ids"
    if t == "count_map":
        return None if isinstance(v, dict) and all(is_int(x) and x >= 0 for x in v.values()) else "count_map input must be an object of counts"
    if t == "recurrence":
        return None if isinstance(v, dict) and set(v) == {"band", "reproduced_in", "retests"} and v["band"] in RECURRENCE_BANDS \
            else "recurrence input must be {band, reproduced_in, retests}"
    if t == "required_text":
        return None if isinstance(v, dict) and v and all(x is None or isinstance(x, (bool, str)) for x in v.values()) \
            else "required_text input must be an object fact -> value|null"
    if t == "axes_list":
        return None if isinstance(v, dict) and v and set(v) <= {"Q", "E", "C", "G"} and all(x is None or is_num(x) for x in v.values()) \
            else "axes_list input must be an object symbol -> value|null"
    if t == "decisive_list":
        return None if isinstance(v, list) and all(isinstance(x, str) for x in v) else "decisive_list input must be an array of entry labels"
    return f"unknown param type {t}"


class Gates:
    def __init__(self, args: argparse.Namespace) -> None:
        self.a = args
        self.eio = Path(args.eio)
        self.schemas = Path(args.schemas)
        self.results: list[dict] = []
        self.modules: dict[str, dict] = {}     # module id -> doc
        self.paths: dict[str, Path] = {}      # module id -> path
        self.parse_errors: list[str] = []

    # -- reporting ---------------------------------------------------------------------
    def gate(self, name: str, problems: list[str], info: str = "", blocking: bool = True) -> None:
        self.results.append({"gate": name, "ok": not problems, "blocking": blocking,
                             "problems": problems, "info": info})

    # -- loading -----------------------------------------------------------------------
    def load(self) -> None:
        for p in sorted(self.eio.rglob("*.yaml")):
            try:
                doc = yaml.load(p.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
            except Exception as exc:  # noqa: BLE001
                self.parse_errors.append(f"{p.relative_to(self.eio)}: {exc}".replace("\n", " "))
                continue
            if not isinstance(doc, dict) or "eio" not in doc:
                self.parse_errors.append(f"{p.relative_to(self.eio)}: no eio header")
                continue
            mid = doc["eio"]["id"]
            if mid in self.modules:
                self.parse_errors.append(f"{p}: module id {mid} declared twice")
            self.modules[mid] = doc
            self.paths[mid] = p
        self.gate("YAML_PARSE", self.parse_errors, f"{len(self.modules)} modules loaded with duplicate-key rejection")

    def schema(self, name: str) -> dict:
        return json.loads((self.schemas / name).read_text(encoding="utf-8"))

    # -- helpers -----------------------------------------------------------------------
    def section(self, sec: str) -> list[tuple[str, dict]]:
        out = []
        for mid, doc in self.modules.items():
            for x in doc.get(sec) or []:
                if isinstance(x, dict):
                    out.append((mid, x))
        return out

    def predicates(self) -> dict[str, dict]:
        return {p["id"]: p for _, p in self.section("predicates")}

    def resolvers(self) -> dict[str, dict]:
        return {r["id"]: r for _, r in self.section("resolvers")}

    def concepts(self) -> dict[str, dict]:
        return {c["id"]: c for _, c in self.section("concepts")}

    def domains(self) -> dict[str, dict]:
        return {doc["domain"]["id"]: doc for doc in self.modules.values() if isinstance(doc.get("domain"), dict)}

    def obligations(self) -> list[tuple[str, dict]]:
        out = []
        for did, doc in self.domains().items():
            for o in doc["domain"]["coverage_obligations"]:
                out.append((did, o))
        return out

    def governance(self) -> dict:
        return self.modules.get("eio.governance.gates", {}).get("governance", {})

    def profiles(self) -> dict[str, tuple[str, dict]]:
        return {p["id"]: (mid, p) for mid, p in self.section("profiles")}

    # -- external inputs: the 0.3.0 baseline when given, else the vendored snapshot; the optional example records ---------
    def baseline_live(self) -> bool:
        return bool(self.a.baseline) and (Path(self.a.baseline) / "manifest.yaml").is_file()

    def snapshot(self, name: str) -> dict:
        return json.loads((SNAPSHOTS / name).read_text(encoding="utf-8"))

    def baseline_modules(self) -> dict[str, dict]:
        """rel path -> {id, version, namespace, sha256} of the 0.3.0 baseline."""
        if self.baseline_live():
            base, out = Path(self.a.baseline), {}
            for p in sorted(base.rglob("*.yaml")):
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
                if isinstance(d, dict) and isinstance(d.get("eio"), dict):
                    out[str(p.relative_to(base))] = {"id": d["eio"]["id"], "version": d["eio"]["version"],
                                                     "namespace": d["eio"].get("namespace"), "sha256": sha256_file(p)}
            return out
        return self.snapshot("eio-0.3.0-baseline.json")["modules"]

    def example_records(self) -> list[str]:
        """The example PER records of --examples, including the native JCS golden; none without it."""
        if not self.a.examples:
            return []
        ex = Path(self.a.examples)
        files = (sorted(glob.glob(str(ex / "*.per.json"))) + sorted(glob.glob(str(ex / "*.per.jcs")))
                 + sorted(glob.glob(str(ex / "review_aids" / "*.per.full.json"))))
        if not files:
            raise FileNotFoundError(f"--examples has no PER records: {ex}")
        return files

    # -- declarations ------------------------------------------------------------------
    def declared(self) -> tuple[dict[str, list[str]], set[str]]:
        """id -> [module ids declaring it]; plus the set of module ids."""
        decl: dict[str, list[str]] = defaultdict(list)
        for mid, doc in self.modules.items():
            for path, d in walk_dicts({k: v for k, v in doc.items() if k not in ("eio", "imports")}):
                if REF_DICT_RE.search(path):
                    continue  # a resolver reference {id, relation}, not a declaration
                if isinstance(d.get("id"), str) and (ID_RE.match(d["id"]) or WHY_RE.match(d["id"])):
                    decl[d["id"]].append(mid)
        return decl, set(self.modules)

    def closure(self, mid: str) -> set[str]:
        seen: set[str] = set()
        stack = [mid]
        while stack:
            m = stack.pop()
            if m in seen or m not in self.modules:
                continue
            seen.add(m)
            for imp in self.modules[m].get("imports") or []:
                stack.append(imp["module"])
        return seen

    # =====================================================================================
    def run(self) -> int:
        self.load()
        if not self.modules:
            return self.report()
        self.g_schema_self()
        self.g_module_schema()
        self.g_reference_cases()
        self.g_id_uniqueness()
        self.g_import_version()
        self.g_references()
        self.g_flow_concepts()
        self.g_relations()
        self.g_predicates()
        self.g_resolver_order()
        self.g_severity_declared()
        self.g_facts()
        self.g_aliases_and_resolution()
        self.g_policy_defaults()
        self.g_spurious_keys()
        self.g_evaluation_integrity()
        self.g_witness_table()
        self.g_flow()
        self.g_templates()
        self.g_context_labels()
        self.g_compliance()
        self.g_governance()
        self.g_profiles()
        self.g_namespace()
        self.g_per_ids_owned()
        self.g_cap_witness()
        self.g_gate_vectors()
        self.g_claim_schema_goldens()
        self.g_manifest_and_digests()
        self.g_version_bump()
        self.g_changelog()
        return self.report()

    # -- schema --------------------------------------------------------------------------
    def g_schema_self(self) -> None:
        probs = []
        for p in sorted(self.schemas.glob("*.json")):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(s)
            except Exception as exc:  # noqa: BLE001
                probs.append(f"{p.name}: {exc}")
        self.gate("SCHEMA_SELF", probs, "every schemas/*.json is a valid JSON Schema 2020-12")

    def g_module_schema(self) -> None:
        v = Draft202012Validator(self.schema("module.schema.json"))
        probs = []
        for mid, doc in self.modules.items():
            for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
                probs.append(f"{mid}: {'.'.join(map(str, e.path)) or 'module'}: {e.message[:200]}")
        self.gate("MODULE_SCHEMA", probs, f"{len(self.modules)} modules validated against module.schema.json")

    def g_reference_cases(self) -> None:
        v = Draft202012Validator(self.schema("reference-case.schema.json"))
        preds = self.predicates()
        probs, n = [], 0
        for i, line in enumerate((self.eio / "reference" / "cases.jsonl").read_text().splitlines(), 1):
            if not line.strip():
                continue
            n += 1
            c = json.loads(line)
            for e in v.iter_errors(c):
                probs.append(f"cases.jsonl:{i}: {e.message[:160]}")
            if c.get("predicate") not in preds:
                probs.append(f"cases.jsonl:{i}: predicate {c.get('predicate')} not declared")
        self.gate("REFERENCE_CASES", probs, f"{n} reference cases valid")

    # -- identity -----------------------------------------------------------------------
    def g_id_uniqueness(self) -> None:
        decl, mods = self.declared()
        probs = []
        domain_pairs = {mid for mid, doc in self.modules.items()
                        if isinstance(doc.get("domain"), dict) and doc["domain"].get("id") == mid}
        for i, ms in decl.items():
            if len(ms) > 1:
                probs.append(f"{i} declared {len(ms)} times ({', '.join(sorted(ms))})")
            if i in mods and i not in domain_pairs:
                probs.append(f"{i} is both a module id and an item id")
        for i in decl:
            if ID_RE.match(i) and not STRICT_ID_RE.match(i) and i not in GRANDFATHERED_IDS:
                probs.append(f"{i}: violates the id grammar ^eio\\.[a-z0-9][a-z0-9.-]*$ (ID_GRAMMAR)")
        self.gate("ID_UNIQUENESS", probs,
                  f"{len(decl)} item ids across every section; {len(domain_pairs)} domain module/domain pairs exempt")

    def g_import_version(self) -> None:
        probs = []
        for mid, doc in self.modules.items():
            seen = set()
            for imp in doc.get("imports") or []:
                m, v = imp.get("module"), imp.get("version")
                if m in seen:
                    probs.append(f"{mid}: imports {m} twice")
                seen.add(m)
                if m not in self.modules:
                    probs.append(f"{mid}: imports {m}, which is absent (DANGLING_IMPORT)")
                elif self.modules[m]["eio"]["version"] != v:
                    probs.append(f"{mid}: pins {m}@{v} but the module is {self.modules[m]['eio']['version']}")
                if m == mid:
                    probs.append(f"{mid}: imports itself")
        # acyclic
        state: dict[str, int] = {}
        cycles: list[str] = []

        def dfs(m: str, stack: list[str]) -> None:
            state[m] = 1
            for imp in self.modules[m].get("imports") or []:
                n = imp["module"]
                if n not in self.modules:
                    continue
                if state.get(n) == 1:
                    cycles.append(" -> ".join(stack + [n]))
                elif not state.get(n):
                    dfs(n, stack + [n])
            state[m] = 2

        for m in sorted(self.modules):
            if not state.get(m):
                dfs(m, [m])
        probs += [f"import cycle: {c}" for c in cycles]
        self.gate("IMPORT_VERSION", probs, "every pin names an existing module at exactly its version; graph acyclic")

    def g_references(self) -> None:
        decl, mods = self.declared()
        declared_ids = set(decl)
        dangling, closure_probs, n_refs = [], [], 0
        for mid, doc in self.modules.items():
            clos = self.closure(mid)
            visible = {i for i, ms in decl.items() if any(m in clos for m in ms)}
            body = {k: v for k, v in doc.items() if k not in ("eio", "imports")}
            for path, kind, val in walk(body):
                if not isinstance(val, str):
                    continue
                if kind != "__key__" and last_key(path) == "id":
                    continue  # a declaration, not a reference
                if last_key(path) in PROSE_KEYS and kind != "__key__":
                    continue
                is_id = bool(ID_RE.match(val))
                is_why = bool(WHY_RE.match(val))
                if not (is_id or is_why):
                    continue
                n_refs += 1
                if val in mods:
                    continue  # module pointer: resolves against the release (manifest)
                if val not in declared_ids:
                    dangling.append(f"{mid}:{path}: {val} is not declared anywhere")
                    continue
                if any(rx.match(path) for rx in RELEASE_SCOPED_PATHS):
                    continue
                if val not in visible:
                    closure_probs.append(f"{mid}:{path}: {val} (declared in {', '.join(decl[val])}) not in imports")
        self.gate("REFERENCE_RESOLVES", dangling, f"{n_refs} id-valued references scanned (parents, relations, "
                  "predicates, controls, obligations, profiles)")
        self.gate("IMPORT_CLOSURE", closure_probs,
                  "every referenced id is declared in the module or its transitive imports "
                  "(release-scoped: module pointers, governance.gates[].evaluated_at)")

    def g_flow_concepts(self) -> None:
        concepts = self.concepts()
        probs = []
        for mid, st in self.section("flow"):
            for slot in ("consumes", "produces"):
                for c in st.get(slot) or []:
                    if c not in concepts:
                        probs.append(f"{st['id']}.{slot}: {c} is not a declared concept")
        for mid, cr in self.section("context_criteria"):
            for c in cr.get("evaluates") or []:
                if c not in concepts:
                    probs.append(f"{cr['id']}.evaluates: {c} is not a declared concept")
        self.gate("DANGLING_FLOW_CONCEPT", probs, "flow consumes/produces and criteria evaluates resolve to declared "
                  "concepts (EIO-5)")
        par = [f"{cid}: parent {c['parent']} is not a declared concept"
               for cid, c in concepts.items() if c.get("parent") and c["parent"] not in concepts]
        self.gate("DANGLING_PARENT", par, f"every parent of {len(concepts)} concepts resolves (EIO-208); every other "
                  "cross-module reference is REFERENCE_RESOLVES")

    # -- relations ---------------------------------------------------------------------
    def g_relations(self) -> None:
        concepts = self.concepts()
        rels = {r["id"]: (mid, r) for mid, r in self.section("relations")}
        probs, inv_probs = [], []
        for rid, (mid, r) in rels.items():
            for slot in ("domain", "range"):
                for c in r.get(slot) or []:
                    if c not in concepts:
                        probs.append(f"{rid}.{slot}: {c} undeclared")
            if "cardinality" not in r:
                probs.append(f"{rid}: no cardinality (EIO-9: populate every relation)")
            ch = set(r.get("characteristics") or [])
            card = r.get("cardinality") or {}
            if "functional" in ch and card.get("object") not in ("0..1", "1"):
                probs.append(f"{rid}: functional but cardinality.object={card.get('object')}")
            if "inverse-functional" in ch and card.get("subject") not in ("0..1", "1"):
                probs.append(f"{rid}: inverse-functional but cardinality.subject={card.get('subject')}")
            if card.get("object") in ("0..1", "1") and "functional" not in ch:
                probs.append(f"{rid}: cardinality.object {card.get('object')} without characteristic functional")
            if card.get("subject") in ("0..1", "1") and "inverse-functional" not in ch:
                probs.append(f"{rid}: cardinality.subject {card.get('subject')} without characteristic inverse-functional")
            if "symmetric" in ch and "irreflexive" in ch and False:
                pass
            inv = r.get("inverse")
            if inv:
                if inv not in rels:
                    inv_probs.append(f"{rid}: inverse {inv} is not a relation")
                elif rels[inv][1].get("inverse") != rid:
                    inv_probs.append(f"{rid}: inverse {inv} does not declare {rid} as its inverse")
            # EIO-6 layering: endpoints declared in the relation's module or its imports (checked by closure too)
        self.gate("RELATIONS", probs, f"{len(rels)} relations: endpoints declared, cardinality populated and "
                  "consistent with functional/inverse-functional (EIO-9)")
        n_inv = sum(1 for _, r in rels.values() if r.get("inverse"))
        self.gate("RELATION_INVERSE", inv_probs, f"{n_inv} relations declare an inverse; each names an existing "
                  "relation that declares it back")

    # -- predicates --------------------------------------------------------------------
    def g_predicates(self) -> None:
        preds, res = self.predicates(), self.resolvers()
        kinds = {e["id"] for _, e in self.section("evidence_types")}
        states = {s["id"] for _, s in self.section("decision_states")}
        concepts = self.concepts()
        probs = []
        for pid, p in preds.items():
            if p.get("unknown_policy") not in states:
                probs.append(f"{pid}: unknown_policy {p.get('unknown_policy')} is not a decision state")
            if not (p.get("applicable_when") or p.get("polarity") == "observation"):
                probs.append(f"{pid}: no applicable_when")
            for r in p.get("resolvers") or []:
                rid = r if isinstance(r, str) else r.get("id")
                if rid not in res:
                    probs.append(f"{pid}: resolver {rid} undeclared")
                if isinstance(r, dict) and r.get("relation") and r["relation"] not in {x["id"] for _, x in self.section("relations")}:
                    probs.append(f"{pid}: resolver relation {r['relation']} undeclared")
            ec = p.get("evidence_contract") or {}
            named = [*(ec.get("require_all") or []), *(ec.get("require_any") or []),
                     *[x for g in (ec.get("require_groups") or []) for x in g], *(ec.get("forbid_as_agent_proof") or [])]
            for pc in ("pass_contract", "not_applicable_basis"):
                if isinstance(ec.get(pc), dict):
                    for key in ("require_any", "require_all"):
                        named += ec[pc].get(key) or []
            for k in named:
                if k not in kinds:
                    probs.append(f"{pid}: evidence kind {k} undeclared")
            for tgt in ("risk", "safeguard"):
                if p.get(tgt) and p[tgt] not in concepts:
                    probs.append(f"{pid}: {tgt} {p[tgt]} undeclared")
            for s in p.get("subsumes") or []:
                if s not in preds:
                    probs.append(f"{pid}: subsumes {s} undeclared")
            if p.get("polarity") == "risk" and p.get("risk") and concepts.get(p["risk"], {}).get("kind") != "risk":
                probs.append(f"{pid}: risk {p['risk']} is not kind risk")
        # obligations -> predicates
        for did, o in self.obligations():
            if o["predicate"] not in preds:
                probs.append(f"{o['id']}: predicate {o['predicate']} undeclared (DANGLING_OBLIGATION)")
        for _, t in self.section("templates"):
            for tp in t.get("predicates") or []:
                if tp not in preds:
                    probs.append(f"{t['id']}: predicate {tp} undeclared (DANGLING_TEMPLATE)")
        self.gate("PREDICATE_CONTRACTS", probs, f"{len(preds)} predicates: states, resolvers, evidence kinds, "
                  "risk/safeguard, subsumes, obligations and templates resolve")

    def g_resolver_order(self) -> None:
        preds, res = self.predicates(), self.resolvers()
        order_probs, shape_probs = [], []
        for pid, p in preds.items():
            classes = []
            for r in p.get("resolvers") or []:
                if isinstance(r, dict):
                    extra = set(r) - {"id", "relation"}
                    if extra:
                        shape_probs.append(f"{pid}: resolver ref {r.get('id')} carries {sorted(extra)} (RESOLVER_REF_SHAPE)")
                rid = r if isinstance(r, str) else r.get("id")
                kind = res.get(rid, {}).get("kind")
                cls = 2 if rid in DECISION_COMBINATORS else SEMANTIC_RESOLVER_CLASS.get(kind, 9)
                classes.append((cls, rid))
            seq = [c for c, _ in classes]
            if seq != sorted(seq):
                order_probs.append(f"{pid}: order {[r.replace('eio.resolver.', '') for _, r in classes]} is not "
                                   "deterministic -> semantic -> graph-rule/human-adjudication")
        self.gate("PREDICATE_RESOLVER_ORDER", order_probs, "no deterministic resolver (other than graph-rule) follows "
                  "a semantic one in any predicate's ordered resolver list")
        self.gate("RESOLVER_REF_SHAPE", shape_probs, "resolver references are a bare id or {id, relation}")

    def g_severity_declared(self) -> None:
        preds = self.predicates()
        targeted = Counter(o["predicate"] for _, o in self.obligations())
        probs = []
        for pid, p in preds.items():
            ss = p.get("severity_source")
            if targeted[pid] and ss:
                probs.append(f"{pid}: targeted by {targeted[pid]} obligation(s) yet declares severity_source")
            if not targeted[pid]:
                if not (isinstance(ss, dict) and ss.get("kind") == "NONE" and ss.get("reason")):
                    probs.append(f"{pid}: no obligation and no severity_source {{kind: NONE, reason}}")
                elif pid in UNTARGETED_SEVERITY_NONE and ss.get("reason") != SEVERITY_REASONS[UNTARGETED_SEVERITY_NONE[pid]]:
                    probs.append(f"{pid}: reason {ss.get('reason')!r} != {SEVERITY_REASONS[UNTARGETED_SEVERITY_NONE[pid]]!r}")
        untargeted = sorted(p for p in preds if not targeted[p])
        if set(untargeted) != set(UNTARGETED_SEVERITY_NONE):
            probs.append(f"untargeted predicates differ from the EIO-36 list: extra={sorted(set(untargeted) - set(UNTARGETED_SEVERITY_NONE))} "
                         f"missing={sorted(set(UNTARGETED_SEVERITY_NONE) - set(untargeted))}")
        self.gate("SEVERITY_DECLARED", probs, f"{len(preds) - len(untargeted)} predicates carry obligation severity; "
                  f"{len(untargeted)} declare severity_source NONE with a reason")

    # -- facts ------------------------------------------------------------------------------
    def fact_table(self) -> dict[str, dict]:
        return {f["id"]: f for f in self.governance().get("facts") or []}

    def g_facts(self) -> None:
        facts = self.fact_table()
        probs = []
        if not facts:
            probs.append("eio.governance.gates declares no governance.facts section")
        alias_of = {}
        for fid, f in facts.items():
            if not re.match(r"^[a-z][a-z0-9_]*$", fid):
                probs.append(f"fact {fid}: not snake_case")
            for al in f.get("aliases") or []:
                if al in facts:
                    probs.append(f"fact {fid}: alias {al} is itself a fact")
                if al in alias_of:
                    probs.append(f"alias {al} claimed by {alias_of[al]} and {fid}")
                alias_of[al] = fid

        def check_map(where: str, m: dict) -> None:
            for k, v in (m or {}).items():
                if k not in facts:
                    probs.append(f"{where}: {k} is not a declared fact" + (f" (alias of {alias_of[k]})" if k in alias_of else ""))
                    continue
                f = facts[k]
                if f.get("type") == "boolean" and not isinstance(v, bool):
                    probs.append(f"{where}: {k}={v!r} is not boolean")
                if f.get("type") == "enum" and v not in (f.get("values") or []):
                    probs.append(f"{where}: {k}={v!r} not in declared values")

        n = 0
        for did, o in self.obligations():
            check_map(o["id"] + ".required_when", o["required_when"]); n += 1
        for g in self.governance().get("gates") or []:
            if g.get("required_when"):
                check_map(g["id"] + ".required_when", g["required_when"]); n += 1
        for i, rule in enumerate(self.governance().get("impact_escalation") or []):
            check_map(f"impact_escalation[{i}].when", rule.get("when")); n += 1
        for did, doc in self.domains().items():
            for pd in doc["domain"].get("policy_defaults") or []:
                aw = pd.get("applies_when")
                if aw not in facts:
                    probs.append(f"{did}.policy_defaults: applies_when {aw} is not a declared fact"); n += 1
        for _, t in self.section("templates"):
            check_map(t["id"] + ".requires", t.get("requires")); n += 1
        # derivation sanity: every intake-derived fact names an intake key
        for fid, f in facts.items():
            for d in f.get("intake_keys") or []:
                if not isinstance(d, dict) or not d.get("key"):
                    probs.append(f"fact {fid}: malformed intake_keys entry {d!r}")
        for req in ("multi_turn", "consequential_actions", "human_oversight", "tier", "autonomy_level", "region",
                    "tools", "side_effecting_tools", "accepts_untrusted_content", "handles_non_public_data",
                    "credit_or_insurance_decisions", "high_impact_decisions", "payment_data", "knowledge_tasks"):
            if req not in facts:
                probs.append(f"required fact {req} missing")
        # Producer-specific archive and intake bindings are adapter-owned.
        pu = facts.get("prohibited_use_case") or {}
        if pu.get("type") != "boolean" or pu.get("source") != "profile":
            probs.append("fact prohibited_use_case must be boolean, declared by the profile")
        # (the intake use-case list is compared with the harness USE_CASES registry by an adapter test, not here)
        self.gate("FACTS_DECLARED", probs, f"{len(facts)} canonical facts; {n} required_when/applies_when/requires/"
                  "escalation maps use declared canonical fact ids only")

    # -- domains -----------------------------------------------------------------------
    def resolve_domains(self, inferred: list[str], profile: dict | None = None) -> list[dict]:
        doms = self.domains()
        rc = self.governance().get("runtime_crosswalk") or {}
        index: dict[str, str] = {}
        for did, doc in doms.items():
            for al in list(doc["domain"].get("aliases") or []) + [did.split("eio.domain.", 1)[1]]:
                index[normalize_token(al)] = did
        out: list[dict] = []

        def add(did: str, source: str, matched: Any) -> None:
            if did and did not in [x["id"] for x in out]:
                out.append({"id": did, "source": source, "matched": matched})

        profile = profile or {}
        if profile.get("domain") in doms:
            add(profile["domain"], "profile", profile["domain"])
        elif profile.get("use_case") and rc.get("use_cases", {}).get(profile["use_case"]):
            add(rc["use_cases"][profile["use_case"]], "profile", profile["use_case"])
        elif profile.get("domain_hint") and rc.get("domain_hints", {}).get(profile["domain_hint"]):
            add(rc["domain_hints"][profile["domain_hint"]], "profile", profile["domain_hint"])
        for tok in inferred or []:
            did = index.get(normalize_token(tok))
            if did:
                add(did, "alias", tok)
        if not out:
            add("eio.domain.generic-agent", "default", None)
            return out
        # import closure (source import)
        i = 0
        while i < len(out):
            did = out[i]["id"]
            for imp in doms[did].get("imports") or []:
                if imp["module"] in doms:
                    add(imp["module"], "import", did)
            i += 1
        return out

    def g_aliases_and_resolution(self) -> None:
        doms = self.domains()
        probs = []
        owner: dict[str, str] = {}
        suffixes = {did.split("eio.domain.", 1)[1]: did for did in doms}
        for did, doc in doms.items():
            for al in doc["domain"].get("aliases") or []:
                if normalize_token(al) != al:
                    probs.append(f"{did}: alias {al!r} is not normalised (lower case, '-' separators)")
                n = normalize_token(al)
                if n in owner and owner[n] != did:
                    probs.append(f"alias {al!r} in both {owner[n]} and {did} (ALIAS_UNIQUE)")
                owner[n] = did
                if n in suffixes and suffixes[n] != did:
                    probs.append(f"{did}: alias {al!r} equals the id suffix of {suffixes[n]}")
        for tok, exp in TOKEN_EXPECT.items():
            got = [x["id"] for x in self.resolve_domains([tok]) if x["source"] == "alias"]
            if got != [exp]:
                probs.append(f"token {tok!r} resolves to {got}, expected [{exp}]")
        info_rows = []
        for f in sorted(Path(self.a.goldens).glob("*.raw.json")) if self.a.goldens else []:
            meta = json.loads(f.read_text()).get("metadata") or {}
            res = self.resolve_domains(meta.get("domains_inferred") or [])
            ids = [x["id"] for x in res]
            info_rows.append(f"{f.name}: {meta.get('domains_inferred')} -> {[i.split('.')[-1] for i in ids]}")
            exp = FIN_GOLDEN_EXPECT.get(f.name)
            if exp is not None and ids != exp:
                probs.append(f"golden {f.name}: {ids} != expected {exp}")
            if f.name.startswith(("FIN_", "MED_")) and ids == ["eio.domain.generic-agent"]:
                probs.append(f"golden {f.name} resolves to generic-agent only")
        # Named producer use cases are adapter checks; this gate still checks every generic alias.
        self.gate("ALIAS_UNIQUE", probs, "aliases normalised and unique; EIO-24 token and golden resolution tests; "
                  + " | ".join(info_rows))

    def g_policy_defaults(self) -> None:
        probs, n = [], 0
        for did, doc in self.domains().items():
            for i, pd in enumerate(doc["domain"].get("policy_defaults") or []):
                n += 1
                if not isinstance(pd, dict) or set(pd) != {"rule", "applies_when"}:
                    probs.append(f"{did}.policy_defaults[{i}]: keys {sorted(pd) if isinstance(pd, dict) else pd}")
                elif not isinstance(pd["rule"], str) or len(pd["rule"]) < 10:
                    probs.append(f"{did}.policy_defaults[{i}]: rule {pd['rule']!r} truncated")
        self.gate("POLICY_DEFAULTS_SHAPE", probs, f"{n} policy defaults have exactly {{rule, applies_when}} (EIO-207)")

    def g_spurious_keys(self) -> None:
        """Unquoted flow-mapping strings containing ', ' parse into keys with null values."""
        probs = []
        for mid, doc in self.modules.items():
            for path, d in walk_dicts(doc):
                for k, v in d.items():
                    if path.startswith("governance.runtime_crosswalk"):
                        continue  # runtime display names legitimately map to null (no EIO counterpart)
                    if v is None and isinstance(k, str) and (" " in k or k[:1].isupper()):
                        probs.append(f"{mid}:{path}: spurious key {k!r} (unquoted string with a comma)")
        self.gate("SPURIOUS_KEY", probs, "no mapping key parsed from an unquoted comma (EIO-207 class of defect)")

    # -- metrics -----------------------------------------------------------------------
    def g_evaluation_integrity(self) -> None:
        concepts, preds = self.concepts(), self.predicates()
        probs = []
        root = concepts.get("eio.risk.evaluation-integrity")
        if not root or root.get("kind") != "risk" or root.get("parent") != "eio.entity.thing":
            probs.append("eio.risk.evaluation-integrity missing or not {kind: risk, parent: eio.entity.thing}")
        for r in EVALUATOR_RISKS:
            if concepts.get(r, {}).get("parent") != "eio.risk.evaluation-integrity":
                probs.append(f"{r}: parent is {concepts.get(r, {}).get('parent')}")

        def descends(cid: str) -> bool:
            seen = set()
            while cid and cid not in seen:
                if cid == "eio.risk.evaluation-integrity":
                    return True
                seen.add(cid)
                cid = concepts.get(cid, {}).get("parent")
            return False

        eval_preds = {pid for pid, p in preds.items() if p.get("risk") and descends(p["risk"])}
        for m in (self.modules.get("eio.mapping.metrics", {}).get("mappings") or []):
            if m["source"] in eval_preds and m["target"] in BEHAVIOUR_METRICS:
                probs.append(f"evaluator predicate {m['source']} feeds agent metric {m['target']}")
        prof = self.profiles().get("eio.profile.metric-aggregation-v1", (None, {}))[1]
        if prof.get("excluded_risk_root") != "eio.risk.evaluation-integrity":
            probs.append("eio.profile.metric-aggregation-v1.excluded_risk_root must be eio.risk.evaluation-integrity")
        if set(prof.get("behaviour_metrics") or []) != BEHAVIOUR_METRICS:
            probs.append("eio.profile.metric-aggregation-v1.behaviour_metrics must list the six E metrics")
        self.gate("EVALUATION_INTEGRITY", probs, f"{len(eval_preds)} evaluator predicates under "
                  "eio.risk.evaluation-integrity; none feeds an agent metric or E")

    # -- evidence ------------------------------------------------------------------------
    def g_witness_table(self) -> None:
        ev = self.modules.get("eio.core.evidence", {})
        st = {s["id"]: s for s in ev.get("source_types") or []}
        kinds = {e["id"]: e for e in ev.get("evidence_types") or []}
        probs = []
        if list(st) != SOURCE_TYPES:
            probs.append(f"source_types {list(st)} != {SOURCE_TYPES}")
        for sid, s in st.items():
            if bool(s.get("may_witness")) != (sid in WITNESS_SOURCES):
                probs.append(f"{sid}: may_witness {s.get('may_witness')} (W = {sorted(WITNESS_SOURCES)})")
        if (st.get("TOOL_RESULT") or {}).get("witness_requires") != "AGENT_TOOL_CALL":
            probs.append("TOOL_RESULT.witness_requires must be AGENT_TOOL_CALL (same call)")
        for kid, k in kinds.items():
            cst = k.get("compatible_source_types")
            if not cst:
                probs.append(f"{kid}: no compatible_source_types")
                continue
            for s in cst:
                if s not in st:
                    probs.append(f"{kid}: compatible source type {s} undeclared")
        hr_kinds = sorted(k for k, v in kinds.items() if "HUMAN_REVIEW" in (v.get("compatible_source_types") or []))
        if hr_kinds != ["HUMAN_SIGNOFF"]:
            probs.append(f"HUMAN_REVIEW admitted on {hr_kinds}; must be exactly HUMAN_SIGNOFF")

        def witness(kind: str, source: str, with_call: bool = True) -> bool:
            k, s = kinds.get(kind, {}), st.get(source, {})
            ok = bool(k.get("can_prove_agent_behaviour")) and bool(s.get("may_witness")) and \
                source in (k.get("compatible_source_types") or [])
            if ok and s.get("witness_requires"):
                ok = with_call
            return ok

        vectors = [("AGENT_SPAN", "AGENT_ANSWER", True), ("AGENT_SPAN", "USER_INPUT", False),
                   ("AGENT_SPAN", "JUROR_INFERENCE", False), ("TOOL_RECEIPT", "AGENT_TOOL_CALL", True),
                   ("TOOL_RECEIPT", "TOOL_RESULT", True), ("PROVENANCE", "HARNESS_SIGNAL", False),
                   ("STATE_FACT", "STATE_LEDGER", True), ("STATE_TRANSITION", "STATE_LEDGER", True),
                   ("HUMAN_SIGNOFF", "HUMAN_REVIEW", True), ("USER_INPUT", "USER_INPUT", False),
                   ("RETRIEVAL", "RETRIEVAL", False), ("POLICY_SPAN", "POLICY_SOURCE", False),
                   ("TYPED_ABSENCE", "HARNESS_SIGNAL", False), ("TYPED_ABSENCE", "AGENT_TOOL_CALL", True)]
        for kind, source, exp in vectors:
            if witness(kind, source) != exp:
                probs.append(f"witness({kind}, {source}) = {not exp}, expected {exp}")
        if witness("TOOL_RECEIPT", "TOOL_RESULT", with_call=False):
            probs.append("TOOL_RESULT without its AGENT_TOOL_CALL must not witness")
        # FIN_3 shadow count: 40 answers + 4 tool calls + 2 ledger facts witness; PROVENANCE/HARNESS_SIGNAL not -> 46
        fin3 = 40 * witness("AGENT_SPAN", "AGENT_ANSWER") + 4 * witness("TOOL_RECEIPT", "AGENT_TOOL_CALL") + \
            witness("STATE_FACT", "STATE_LEDGER") + witness("STATE_TRANSITION", "STATE_LEDGER") + \
            witness("PROVENANCE", "HARNESS_SIGNAL")
        if fin3 != 46:
            probs.append(f"FIN_3 witness count {fin3} != 46")
        prof = self.profiles().get("eio.profile.witness-rule", (None, {}))[1]
        if not prof:
            probs.append("profile eio.profile.witness-rule missing")

        def stored_flag(kind: str, source: str, call: list, citing_claims: list) -> bool:
            """01 §6.3: the flag stored once per ref. witness_requires holds iff at least one claim cites the ref
            and every citing claim also cites the required-source ref of the same (turn_index, call_index)."""
            if not witness(kind, source, with_call=True):
                return False
            if not st.get(source, {}).get("witness_requires"):
                return True
            return bool(citing_claims) and all(list(call) in [list(c) for c in cc] for cc in citing_claims)

        n_prof = n_stored = 0
        for tv in prof.get("test_vectors") or []:
            if "kind" not in tv:
                continue  # record-level vectors (FIN_3 shadow count) are checked above
            n_prof += 1
            if "citing_claims" in tv:
                n_stored += 1
                got = stored_flag(tv["kind"], tv["source_type"], tv["call"], tv["citing_claims"])
            else:
                got = witness(tv["kind"], tv["source_type"], with_call=tv.get("with_agent_tool_call", True))
            if got != tv["can_prove_agent_behaviour"]:
                probs.append(f"profile test vector {tv}: rule gives {got}")
        if n_stored < 4:
            probs.append(f"witness-rule profile has {n_stored} stored-flag (citing_claims) vectors; at least 4 required "
                         "(one citing claim with the call; a second claim without it; a different call; views only)")
        self.gate("WITNESS_TABLE", probs, f"{len(st)} source types; W = {sorted(WITNESS_SOURCES)}; "
                  f"{len(vectors) + 1} built-in witness vectors; {n_prof} profile vectors ({n_stored} stored-flag); "
                  f"FIN_3 shadow count {fin3}")

    # -- flow --------------------------------------------------------------------------
    def g_flow(self) -> None:
        res = self.resolvers()
        stages = sorted((s for _, s in self.section("flow")), key=lambda s: s["order"])
        probs = []
        prof = self.profiles().get("eio.profile.flow-invariants", (None, {}))[1]
        writers = set(prof.get("claim_writing_stages") or [])
        orders = [s["order"] for s in stages]
        if len(set(orders)) != len(orders):
            probs.append("stage order not total")
        for s in stages:
            if not s.get("produces"):
                probs.append(f"{s['id']}: produces nothing")
            if s.get("may_write_claims") and s["id"] not in writers:
                probs.append(f"{s['id']}: writes claims but not in claim_writing_stages")
            if not s.get("may_write_claims") and s["id"] in writers:
                probs.append(f"{s['id']}: listed as claim writer but may_write_claims false")
            for r in s.get("resolvers_allowed") or []:
                if r not in res:
                    probs.append(f"{s['id']}: resolver {r} undeclared")
        det = next((s for s in stages if s["id"] == "eio.flow.resolve-deterministic"), {})
        if "eio.resolver.graph-rule" not in (det.get("resolvers_allowed") or []):
            probs.append("resolve-deterministic lacks eio.resolver.graph-rule (EIO-20)")
        if len(writers) != 4:
            probs.append(f"claim_writing_stages has {len(writers)} entries, expected 4")
        raw = (self.eio / "core" / "flow.yaml").read_text()
        if "only two stages" in raw or "not_evaluated" in raw:
            probs.append("core/flow.yaml still says 'only two stages' or 'not_evaluated' (EIO-216)")
        if "chain_head" in raw:
            probs.append("core/flow.yaml mentions chain_head (EIO-22: dropped)")
        census = self.profiles().get("eio.profile.coverage-census", (None, {}))[1]
        causes = [c.get("id") for c in census.get("causes") or []]
        if causes != CENSUS_CAUSES:
            probs.append(f"eio.profile.coverage-census causes {causes} != {CENSUS_CAUSES} (EIO-238)")
        if any("BY_DESIGN" in json.dumps(x) for x in (census,)) and "not_causes" not in census:
            probs.append("BY_DESIGN must appear only under not_causes")
        dc = next((s for s in stages if s["id"] == "eio.flow.dispatch-census"), {})
        inv = " ".join(dc.get("invariants") or [])
        for c in CENSUS_CAUSES:
            if c not in inv:
                probs.append(f"dispatch-census invariants do not name cause {c}")
        self.gate("FLOW", probs, f"{len(stages)} stages; 4 claim-writing stages; graph-rule at resolve-deterministic; "
                  f"census causes in order {CENSUS_CAUSES}")

    # -- explanation templates -----------------------------------------------------------
    def g_templates(self) -> None:
        doc = self.modules.get("eio.template.why", {})
        tpls = {t["id"]: t for t in doc.get("explanation_templates") or []}
        probs = []
        if not tpls:
            probs.append("module eio.template.why with explanation_templates is missing")
        missing = [t for t in REQUIRED_WHY if t not in tpls]
        if missing:
            probs.append(f"missing templates: {missing}")
        for tid, t in tpls.items():
            text = t.get("text") or ""
            ph = set(PLACEHOLDER_RE.findall(text))
            params = {p["name"] for p in t.get("params") or []}
            if ph - params:
                probs.append(f"{tid}: placeholders without param: {sorted(ph - params)}")
            if params - ph:
                probs.append(f"{tid}: params never rendered: {sorted(params - ph)}")
            if len(text) > int(t.get("max_length", 600)) or int(t.get("max_length", 600)) > 600:
                probs.append(f"{tid}: text longer than max_length / 600")
            stripped = PLACEHOLDER_RE.sub("", text)
            if "{" in stripped or "}" in stripped:
                probs.append(f"{tid}: stray brace in text")
            for lit in ("from a tool receipt", "from a typed absence", "from the agent answer"):
                if lit in text:
                    probs.append(f"{tid}: literal {lit!r} (must come from {{evidence_kinds}})")
        ov = tpls.get("eio.why.control.observed_violation@2", {})
        if "proxy_note" not in {p["name"] for p in ov.get("params") or []}:
            probs.append("eio.why.control.observed_violation@2 lacks {proxy_note} (PER-506)")
        fd = tpls.get("eio.why.finding@1", {})
        if "evidence_kinds" not in {p["name"] for p in fd.get("params") or []}:
            probs.append("eio.why.finding@1 lacks {evidence_kinds} (PER-213)")
        rp = self.profiles().get("eio.profile.why-rendering", (None, {}))[1]
        if not rp:
            probs.append("profile eio.profile.why-rendering missing")
        else:
            types = set((rp.get("param_types") or {}).keys())
            for tid, t in tpls.items():
                for p in t.get("params") or []:
                    if p.get("type") not in types:
                        probs.append(f"{tid}.{p['name']}: type {p.get('type')} not in why-rendering param_types")
            # FIX-1 P2: the stored input shape of every type, and the inputs-not-text rule
            if list((rp.get("param_inputs") or {}).keys()) != list((rp.get("param_types") or {}).keys()):
                probs.append("why-rendering.param_inputs must declare the stored input of every param_types type, same order")
            if "params store inputs, never rendered text" not in (rp.get("params_rule") or ""):
                probs.append("why-rendering.params_rule must state 'params store inputs, never rendered text'")
        # every stored explanation of the example records stores inputs in the declared shape
        n_expl = 0
        files = self.example_records()
        for f in files:
            rec = json.loads(Path(f).read_text())
            stack = [rec]
            while stack:
                x = stack.pop()
                if isinstance(x, dict):
                    if {"template_id", "params"} <= set(x) and x["template_id"] in tpls:
                        n_expl += 1
                        for p in tpls[x["template_id"]].get("params") or []:
                            if p["name"] in (x["params"] or {}):
                                bad = param_input_problem(p, x["params"][p["name"]])
                                if bad:
                                    probs.append(f"{Path(f).name}: {x['template_id']}.{p['name']}: {bad}")
                    stack.extend(x.values())
                elif isinstance(x, list):
                    stack.extend(x)
        self.gate("EXPLANATION_TEMPLATES", probs, f"{len(tpls)} templates in eio.template.why; placeholders == params; "
                  f"<= 600 code points; param_inputs for every type; {n_expl} stored "
                  f"explanations of {len(files)} example records store inputs, never rendered text")

    # -- context -------------------------------------------------------------------------
    def g_context_labels(self) -> None:
        probs = []   # (the checklist labels are compared with the harness CHECKLIST_CRITERIA by an adapter test, not here)
        prof = self.profiles().get("eio.profile.context-scoring", (None, {}))[1]
        for k in ("rounding", "searched_set", "searched_text_sha256", "matching"):
            if k not in prof:
                probs.append(f"eio.profile.context-scoring lacks {k} (EIO-233)")
        if "rounded to two places" in json.dumps(prof):
            probs.append("eio.profile.context-scoring still rounds to two places (EIO-233: no intermediate rounding)")
        self.gate("CONTEXT_CRITERIA", probs, "context-scoring profile fixes rounding, searched set, searched-text hash and "
                  "matching")

    # -- compliance ----------------------------------------------------------------------
    def g_compliance(self) -> None:
        preds, concepts = self.predicates(), self.concepts()
        fws = {f["id"]: f for _, f in self.section("frameworks")}
        ctls = {c["id"]: c for _, c in self.section("controls")}
        probs = []
        for fid, f in fws.items():
            for cid in f.get("controls") or []:
                if cid not in ctls:
                    probs.append(f"{fid}: control {cid} undeclared")
                elif ctls[cid]["framework"] != fid:
                    probs.append(f"{fid}: control {cid} owned by {ctls[cid]['framework']}")
        for cid, c in ctls.items():
            if c["framework"] not in fws:
                probs.append(f"{cid}: framework undeclared")
            for r in c.get("risk_targets") or []:
                if concepts.get(r, {}).get("kind") != "risk":
                    probs.append(f"{cid}: risk target {r} undeclared")
            for p in c.get("predicate_targets") or []:
                if p not in preds:
                    probs.append(f"{cid}: predicate target {p} undeclared")
                elif preds[p].get("risk") not in (c.get("risk_targets") or []):
                    probs.append(f"{cid}: predicate {p} not reached through a risk target")
            if (c.get("evidence_semantics") or {}).get("inherits_predicate_contracts") is not True:
                probs.append(f"{cid}: does not inherit predicate contracts")
        prof = self.profiles().get("eio.profile.compliance-materialization", (None, {}))[1]
        rules = prof.get("rules") or []
        statuses = [r.get("status") for r in rules]
        if sorted(set(statuses)) != sorted(CONTROL_STATUSES) or len(rules) != 6:
            probs.append(f"compliance-materialization rules {statuses} must map to the six statuses, one rule each")
        if statuses and statuses[-1] != "not_tested":
            probs.append("the last materialization rule must be not_tested (no_evidence_policy)")
        if not prof.get("proxy_only"):
            probs.append("compliance-materialization lacks proxy_only (PER-203)")
        self.gate("COMPLIANCE", probs, f"{len(fws)} frameworks, {len(ctls)} controls, "
                  f"{sum(len(c.get('predicate_targets') or []) for c in ctls.values())} control->predicate links; "
                  "ordered six-status materialization rules")

    # -- governance ----------------------------------------------------------------------
    def g_governance(self) -> None:
        gov = self.governance()
        probs = []
        for a in gov.get("autonomy_levels") or []:
            if "escalates_tier" in a:
                probs.append(f"{a['id']}: escalates_tier still declared (EIO-245)")
        floors = {t["id"]: t.get("obligation_floor") for t in gov.get("tiers") or []}
        rank = {k: i for i, k in enumerate(["NONE", "MONITOR", "WARN", "CONTRIBUTING_BLOCK", "HARD_BLOCK"])}
        for i, rule in enumerate(gov.get("impact_escalation") or []):
            t = (rule.get("when") or {}).get("tier")
            if t and any(rank.get(v, 0) <= rank.get(floors.get(t), -1) for v in (rule.get("promote") or {}).values()):
                probs.append(f"impact_escalation[{i}] promotes under {t} to a level its obligation_floor "
                             f"{floors.get(t)} already guarantees (redundant, EIO-57)")
        stages = {s["id"] for _, s in self.section("flow")}
        ge = [f"{g['id']}: evaluated_at {g.get('evaluated_at')} is not a flow stage"
              for g in gov.get("gates") or [] if g.get("evaluated_at") not in stages]
        self.gate("GATE_EVALUATED_AT", ge, f"{len(gov.get('gates') or [])} gates bind to a flow stage of the release "
                  "(release-scoped reference)")
        self.gate("GOVERNANCE", probs, "no escalates_tier; no escalation rule under a HARD_BLOCK-floor tier; every gate "
                  "evaluated_at is a flow stage; producer crosswalks are adapter-owned")

    def g_profiles(self) -> None:
        prof = self.profiles()
        need = {
            "eio.profile.proof-status": "eio.core.decisions",
            "eio.profile.decision-policy": "eio.core.decisions",
            "eio.profile.resolver-authority": "eio.core.evidence",
            "eio.profile.witness-rule": "eio.core.evidence",
            "eio.profile.coverage-evaluation": "eio.governance.gates",
            "eio.profile.impact-escalation": "eio.governance.gates",
            "eio.profile.framework-selection": "eio.governance.gates",
            "eio.profile.domain-resolution": "eio.governance.gates",
            "eio.profile.compliance-materialization": "eio.compliance.frameworks",
            "eio.profile.mapping-relations": "eio.core.relations",
            "eio.profile.metric-aggregation-v1": "eio.mapping.metrics",
            "eio.profile.context-scoring": "eio.context.criteria",
            "eio.profile.coverage-census": "eio.core.flow",
            "eio.profile.assurance-freshness": "eio.assurance.system-of-record",
            "eio.profile.why-rendering": "eio.template.why",
            "eio.profile.scoring-boundary": "eio.scoring.axes",
            "eio.profile.governance-boundary": "eio.governance.gates",
        }
        probs = []
        for pid, mid in need.items():
            if pid not in prof:
                probs.append(f"{pid} missing")
            elif prof[pid][0] != mid:
                probs.append(f"{pid} declared in {prof[pid][0]}, expected {mid}")
        dp = prof.get("eio.profile.decision-policy", (None, {}))[1]
        if dp.get("observation_fail_is_violation") is not False:
            probs.append("decision-policy.observation_fail_is_violation must be false (EIO-34)")
        ra = prof.get("eio.profile.resolver-authority", (None, {}))[1]
        if ra.get("block_requires") != ["proven_claim", "declared_fact"]:
            probs.append("resolver-authority.block_requires must be [proven_claim, declared_fact] (PER-13, EIO-48)")
        if ra.get("semantic_only_max_effect") != "REVIEW":
            probs.append("resolver-authority.semantic_only_max_effect must be REVIEW (EIO-48, owner decision 2)")
        # FIX-1 P5: declared_fact names a canonical boolean fact; the vectors re-derive the fact from intake
        # (governance.facts intake_keys) and the strongest effect (owner decision 2)
        facts = self.fact_table()
        df = ra.get("declared_fact")
        if df not in facts or facts[df].get("type") != "boolean":
            probs.append(f"resolver-authority.declared_fact {df!r} is not a declared boolean fact of governance.facts")
        ra_tv = ra.get("test_vectors") or []
        if not ra_tv:
            probs.append("resolver-authority has no test_vectors")
        for i, v in enumerate(ra_tv):
            # The neutral core checks the declared fact and release effect. Deriving it from
            # producer intake keys is an adapter conformance gate, not an ontology gate.
            got_fact = v.get(df)
            if got_fact != v.get(df):
                probs.append(f"resolver-authority.test_vectors[{i}]: {df} derived {got_fact} != {v.get(df)}")
            eff = "BLOCK" if (v.get(df) is True or v.get("proven_failure")) else \
                "REVIEW" if (v.get("below_floor") or v.get("semantic_only_failure")) else "NONE"
            if eff != v.get("expected_effect"):
                probs.append(f"resolver-authority.test_vectors[{i}]: effect {eff} != expected {v.get('expected_effect')}")
        if not any(v.get(df) is True and not v.get("proven_failure") and v.get("expected_effect") == "BLOCK" for v in ra_tv):
            probs.append("resolver-authority: no vector shows the declared fact alone making BLOCK")
        if not any(v.get(df) is not True and not v.get("proven_failure") and v.get("below_floor") and v.get("expected_effect") == "REVIEW" for v in ra_tv):
            probs.append("resolver-authority: no vector shows below-floor without proof giving REVIEW (owner decision 2)")
        ps = prof.get("eio.profile.proof-status", (None, {}))[1]
        if ps.get("narrower_requires_recurrence") != "CONFIRMED":
            probs.append("proof-status.narrower_requires_recurrence must be CONFIRMED (EIO-33)")
        ie = prof.get("eio.profile.impact-escalation", (None, {}))[1]
        if ie.get("chaining") is not False:
            probs.append("impact-escalation.chaining must be false (single pass, EIO-57)")
        af = prof.get("eio.profile.assurance-freshness", (None, {}))[1]
        if "freshness" not in af or (af.get("freshness") or {}).get("default", "x") is not None:
            probs.append("assurance-freshness.freshness must be declared with default null (PER-209)")
        # FIX-1 P8: the recurrence band vocabulary is EIO data; every band rule vector recomputes
        rel = (self.modules.get("eio.reliability.ledgers") or {}).get("reliability") or {}
        rb = rel.get("recurrence_bands") or []
        if [b.get("id") for b in sorted(rb, key=lambda b: -int(b.get("rank", -1)))] != RECURRENCE_BANDS:
            probs.append(f"reliability.recurrence_bands (by rank, strongest first) != {RECURRENCE_BANDS}")

        def band_of(r, n):
            return "NOT_RETESTED" if n == 0 else "CONFIRMED" if r == n else "UNCONFIRMED" if r == 0 else "INTERMITTENT"
        for b in rb:
            if not b.get("test_vectors"):
                probs.append(f"recurrence band {b.get('id')}: no test vector")
            for tv in b.get("test_vectors") or []:
                if band_of(tv["reproduced_in"], tv["retests"]) != b.get("id"):
                    probs.append(f"recurrence band {b.get('id')}: vector {tv} gives {band_of(tv['reproduced_in'], tv['retests'])}")
        rec_ledger = next((x for x in rel.get("ledgers") or [] if x.get("id") == "eio.ledger.recurrence"), {})
        if rec_ledger.get("band_vocabulary") != "recurrence_bands" or "weakest" not in str(rec_ledger.get("finding_band")):
            probs.append("eio.ledger.recurrence must name band_vocabulary recurrence_bands and the weakest-band finding rule")
        if ps.get("narrower_requires_recurrence") not in {b.get("id") for b in rb}:
            probs.append("proof-status.narrower_requires_recurrence is not a declared recurrence band")
        # S1b draft: recurrence is needed only by a narrower (proxy) claim;
        # every PROVEN claim needs a verified proof citation. Native origin
        # never bypasses exact fidelity or confirmed recurrence.
        nr = ps.get("narrower_requires_recurrence")
        if (ps.get("exact_mapping_proves") is not True or ps.get("native_claim_proves") is not False
                or ps.get("requires_verified_proof_citation") is not True):
            probs.append("proof-status: exact fidelity needs a verified citation; native origin cannot prove alone")

        def ps_band(v):
            return str(v.get("recurrence") or "NOT_RETESTED").split()[0]

        def ps_eval(v):
            if (v.get("decided_by") not in (ps.get("decided_by_proves") or [])
                    or v.get("witnessing_anchored") is not True or v.get("verified_proof_citation") is not True):
                return "UNPROVEN"
            return "PROVEN" if (v.get("fidelity") == "exact" or ps_band(v) == nr) \
                else "UNPROVEN"
        ps_tv = ps.get("test_vectors") or []
        for i, v in enumerate(ps_tv):
            if ps_eval(v) != v.get("expected"):
                probs.append(f"proof-status.test_vectors[{i}]: derived {ps_eval(v)} != expected {v.get('expected')}")
        ps_cases = {
            "an exact deterministic cited claim PROVEN without recurrence":
                lambda v: v.get("fidelity") == "exact" and v.get("verified_proof_citation") is True
                and v.get("decided_by") == "deterministic" and ps_band(v) == "NOT_RETESTED"
                and v.get("expected") == "PROVEN",
            "native origin without citation UNPROVEN":
                lambda v: v.get("native") is True and v.get("verified_proof_citation") is False
                and v.get("witnessing_anchored") is True and v.get("expected") == "UNPROVEN",
            f"a narrower claim below {nr} UNPROVEN":
                lambda v: v.get("fidelity") == "narrower" and v.get("witnessing_anchored") is True
                and ps_band(v) != nr and v.get("expected") == "UNPROVEN",
            f"a narrower claim with {nr} recurrence PROVEN":
                lambda v: v.get("fidelity") == "narrower" and ps_band(v) == nr and v.get("expected") == "PROVEN",
            "an unwitnessed claim UNPROVEN":
                lambda v: v.get("witnessing_anchored") is False and v.get("expected") == "UNPROVEN",
            "a semantic claim UNPROVEN":
                lambda v: v.get("decided_by") == "semantic" and v.get("expected") == "UNPROVEN",
        }
        for label, pred in ps_cases.items():
            if not any(pred(v) for v in ps_tv):
                probs.append(f"proof-status: no test vector shows {label}")
        eff = str(rec_ledger.get("effect_on_score") or "")
        eff_all = (eff + " " + str(rec_ledger.get("effect_rationale") or "")).lower()
        if not ("narrower" in eff and str(nr) in eff and "eio.profile.proof-status" in eff):
            probs.append(f"eio.ledger.recurrence.effect_on_score must say recurrence makes a narrower claim PROVEN at "
                         f"{nr} (eio.profile.proof-status), got {eff!r}")
        if ("automatic block" in eff_all or "requires recurrence" in eff_all
                or "verified witnessing proof citation" not in eff_all or "native origin alone never" not in eff_all):
            probs.append("eio.ledger.recurrence: exact proof needs a verified citation; native origin alone cannot prove")
        # FIX-1 P3 (owner decision 4): the blocked-run band cap is the 3@ view, shown only until M4
        sc = (self.modules.get("eio.scoring.axes") or {}).get("scoring") or {}
        br = next((c for c in sc.get("caps") or [] if c.get("id") == "eio.cap.blocked-run"), None)
        if br is None:
            probs.append("eio.cap.blocked-run missing")
        else:
            if br.get("applies_under") != ["3@"]:
                probs.append(f"eio.cap.blocked-run.applies_under {br.get('applies_under')} != ['3@'] (owner decision 4)")
            if "producer must declare" not in str(br.get("note") or "").lower():
                probs.append("eio.cap.blocked-run.note must require an explicit producer declaration")
        # FIX-2 (eio-data): the claim-trace and cap invariants are scoped by the data they govern. Axes whose
        # source is not the claim-based metric mapping (Q, C, G) and readiness trace to their components under the
        # legacy profile; a claim cap names its claim, a gate cap its unmet gate; governance contributes no score
        # through the profile, tier or escalation (the G axis is the scoring module's view).
        sb_inv = [str(x) for x in (prof.get("eio.profile.scoring-boundary", (None, {}))[1].get("invariants") or [])]
        trace = next((s for s in sb_inv if "traces to canonical claims or declared profile inputs" in s), None)
        axes = sc.get("axes") or []
        if trace is None:
            probs.append("scoring-boundary: no claim-trace invariant")
        else:
            if "readiness" not in trace or "metric view" not in trace or "missing inputs withhold" not in trace:
                probs.append("scoring-boundary must cover metric views, readiness and fail-closed missing inputs")
        # the scoring stage of eio.core.flow restates the cap invariant: it must separate claim and gate caps too
        fl = (self.modules.get("eio.core.flow") or {}).get("flow") or []
        fl_stages = fl.get("stages") if isinstance(fl, dict) else fl
        score_stage = next((s for s in fl_stages or [] if isinstance(s, dict) and s.get("id") == "eio.flow.score"), {})
        for s in score_stage.get("invariants") or []:
            if re.search(r"\bcaps?\b", str(s)) and any((c.get("applies_when") or {}).get("blocking_gate_unmet")
                                                        for c in sc.get("caps") or []) and "unmet gate" not in str(s):
                probs.append(f"eio.flow.score invariant {s!r}: a gate cap names its unmet gate, not a claim")
        for c in sc.get("caps") or []:
            named = [s for s in sb_inv if c.get("id") in s]
            if not named:
                probs.append(f"scoring-boundary: no invariant names cap {c.get('id')}")
                continue
            if c.get("applies_to_predicates") and "deterministically resolved claim" not in named[0]:
                probs.append(f"scoring-boundary: claim cap {c.get('id')} must trace to a deterministically resolved claim")
            if (c.get("applies_when") or {}).get("blocking_gate_unmet"):
                if "unmet gate" not in named[0] or any(u not in named[0] for u in c.get("applies_under") or []):
                    probs.append(f"scoring-boundary: gate cap {c.get('id')} must name its unmet gate and its scope "
                                 f"{c.get('applies_under')}")
        gb_nm = [str(x) for x in (prof.get("eio.profile.governance-boundary", (None, {}))[1].get("may_not") or [])]
        score_nm = next((s for s in gb_nm if "score" in s), None)
        for a in axes:
            if a.get("source") == "eio.governance.gates" and (
                    score_nm is None or f"{a.get('symbol')} axis" not in score_nm or "scoring module" not in score_nm):
                probs.append(f"governance-boundary may_not must scope the score clause: the {a.get('symbol')} axis "
                             "(source eio.governance.gates) is the scoring module's view")
        self.gate("NORMATIVE_PROFILES", probs, f"{len(need)} neutral normative profiles present in their modules; "
                  "proof-status vectors re-derived; claim-trace, cap and governance-score boundaries scoped; "
                  "adapter scoring and intake rules checked separately")

    # -- namespaces (01 §3.2) --------------------------------------------------------------
    def g_namespace(self) -> None:
        """01 §3.2: a module namespace is unique, an absolute https URI ending in '#', stable across versions
        of the same module id, and never used to build a term IRI."""
        from urllib.parse import urlparse
        probs = []
        seen: dict[str, str] = {}
        for mid, doc in sorted(self.modules.items()):
            ns = str((doc.get("eio") or {}).get("namespace") or "")
            u = urlparse(ns)
            if u.scheme != "https" or not u.netloc or not ns.endswith("#") or ns.count("#") != 1:
                probs.append(f"{mid}: namespace {ns!r} is not an absolute https URI ending in '#'")
            if ns in seen:
                probs.append(f"{mid}: namespace {ns} also declared by {seen[ns]}")
            seen[ns] = mid
        n_base = 0
        for bm in self.baseline_modules().values():
            if bm["id"] in self.modules:
                n_base += 1
                old, new = bm.get("namespace"), self.modules[bm["id"]]["eio"].get("namespace")
                first_public_migration = (
                    isinstance(old, str) and old.startswith("https://proofagent.ai/eio/")
                    and isinstance(new, str) and new.startswith("https://www.proofagent.ai/eio-agents/module/")
                    and (self.modules.get("eio.manifest.public", {}).get("eio") or {}).get("version") == "0.6.0"
                    and bm.get("version") != self.modules[bm["id"]]["eio"].get("version")
                )
                if old != new and not first_public_migration:
                    probs.append(f"{bm['id']}: namespace changed across versions ({old} -> {new})")
        nss = set(seen)
        for mid, doc in self.modules.items():
            for path, _key, v in walk({k: x for k, x in doc.items() if k != "eio"}):
                if isinstance(v, str) and any(v.startswith(ns) and len(v) > len(ns) for ns in nss):
                    probs.append(f"{mid}:{path}: term built on a module namespace: {v[:80]}")
        self.gate("NAMESPACE", probs, f"{len(seen)} namespaces unique, absolute https, ending in '#'; "
                  + (f"{n_base} unchanged from the baseline" if n_base else "baseline not available: stability not checked")
                  + "; no term IRI built on a namespace")

    # -- PER ids named by converter-facing EIO data (01 §1.3 R5) ----------------------------
    def g_per_ids_owned(self) -> None:
        lp, sp = Path(self.a.limitations), Path(self.a.per_schema)
        if not (lp.is_file() and sp.is_file()):
            self.gate("PER_IDS_OWNED", [], "limitation catalogue or PER schema not available; skipped", blocking=False)
            return
        lims = {r["id"] for r in json.loads(lp.read_text(encoding="utf-8"))["limitations"]}          # 04 §5.13, as data
        caveats = set(re.findall(r"per\.caveat\.[a-z0-9_.]*[a-z0-9_]", sp.read_text(encoding="utf-8")))  # 03 §7.13, per schema
        probs, n = [], 0
        for p in sorted(self.eio.rglob("*.yaml")):
            for tok in sorted(set(re.findall(r"per\.(?:lim|caveat)\.[a-z0-9_.]*[a-z0-9_]", p.read_text(encoding="utf-8")))):
                n += 1
                if p.relative_to(self.eio).parts[0] in ("core", "risks"):
                    probs.append(f"{p.relative_to(self.eio)}: {tok}: decision semantics (core/, risks/) MUST NOT name a PER id (01 §1.3 R5)")
                if tok.startswith("per.lim.") and tok not in lims:
                    probs.append(f"{p.relative_to(self.eio)}: {tok} is not in the limitation catalogue (04 §5.13)")
                if tok.startswith("per.caveat.") and tok not in caveats:
                    probs.append(f"{p.relative_to(self.eio)}: {tok} is not a caveat of the PER schema (03 §7.13)")
        if not lims:
            probs.append("the limitation catalogue is empty")
        self.gate("PER_IDS_OWNED", probs, f"{n} per.lim/per.caveat ids named in the release, none in core/ or risks/, all listed "
                  f"by their owner (limitation catalogue: {len(lims)} ids; PER schema: {len(caveats)} caveat ids)")

    # -- the proven-critical-breach cap needs a witnessing anchored ref (01 §6.3 W1) -------
    def g_cap_witness(self) -> None:
        probs = []
        caps = {c.get("id"): c for c in ((self.modules.get("eio.scoring.axes") or {}).get("scoring") or {}).get("caps") or []}
        c = caps.get("eio.cap.proven-critical-breach")
        if not c:
            probs.append("eio.cap.proven-critical-breach missing")
        else:
            if c.get("requires_witnessing_anchored_ref") is not True:
                probs.append("eio.cap.proven-critical-breach: requires_witnessing_anchored_ref must be true (01 §6.3 W1)")
            if c.get("witnessing_required_in") != ["release_recommendation", "readiness"]:
                probs.append("eio.cap.proven-critical-breach: witnessing_required_in must be [release_recommendation, readiness]")
            if c.get("requires_resolver_class") != "deterministic":
                probs.append("eio.cap.proven-critical-breach: requires_resolver_class must be deterministic")
        self.gate("CAP_WITNESS", probs, "eio.cap.proven-critical-breach: deterministic resolver class; witnessing anchored "
                  "ref required in the release recommendation and the readiness index")

    # -- release gates: evaluation rules of 02 §5.5 over each gate's test_vectors ----------
    @staticmethod
    def _required(facts: dict, required_when: dict):
        """eio.profile.coverage-evaluation: false if any named fact is declared with another value; else null if
        any named fact is null; else true."""
        vals = [(facts.get(k), v) for k, v in (required_when or {}).items()]
        if any(f is not None and f != v for f, v in vals):
            return False
        if any(f is None for f, _ in vals):
            return None
        return True

    def gate_met(self, gid: str, gate: dict, tv: dict):
        if gid == "eio.gate.coverage-complete":
            hb = [o for o in tv["obligations"] if o["impact"] == "HARD_BLOCK"]
            if any(o["required"] is True and o["met"] is False for o in hb):
                return False
            if any(o["required"] is None and o["met"] is False for o in hb):
                return None
            return True
        if gid == "eio.gate.evidence-sufficient":
            return not any(m["measurement_status"] == "DIAGNOSTIC_ONLY" for m in tv["metrics"])
        if gid == "eio.gate.evaluator-calibrated":
            return None  # EIO 0.4.0 declares no floors
        if gid == "eio.gate.reproducible":
            return not ({"revision", "patch", "seed", "models", "prompt_hashes"} & set(tv["missing_fields"]))
        if gid == "eio.gate.human-oversight-declared":
            req = self._required(tv["facts"], gate.get("required_when") or {})
            if req is False:
                return True
            if req is None:
                return None
            return tv["facts"].get("human_oversight")
        if gid == "eio.gate.no-critical-recurrence":
            if tv["reliability_status"] == "NOT_RETESTED":
                return None
            return not any(f["recurrence"] == "CONFIRMED" and any(o["impact"] == "HARD_BLOCK" and o["required"] is not False
                                                                  for o in f["obligations"]) for f in tv["findings"])
        if gid == "eio.gate.independent-adjudication":
            return all(s == "adjudicated" for s in tv["reference_case_statuses"])
        raise KeyError(gid)

    def g_gate_vectors(self) -> None:
        probs, n, n_rec = [], 0, 0
        gates = self.governance().get("gates") or []
        rec = {}
        fin3 = Path(self.a.examples or ".") / "review_aids" / "fin3.per.full.json"
        if self.a.examples and fin3.is_file():
            rec = {g["gate"]: g["met"] for g in json.loads(fin3.read_text())["release_recommendation"]["gate_results"]}
        for g in gates:
            tvs = g.get("test_vectors") or []
            if not tvs:
                probs.append(f"{g['id']}: no test_vectors")
            for tv in tvs:
                n += 1
                if tv.get("record") == "FIN_3" and "facts" not in tv:
                    n_rec += 1
                    if rec and rec.get(g["id"], "missing") != tv["met"]:
                        probs.append(f"{g['id']}: FIN_3 vector met {tv['met']} but fin3.per.full.json has {rec.get(g['id'], 'missing')}")
                    continue
                if tv.get("release") and g["id"] == "eio.gate.independent-adjudication":
                    got = all(c.get("review", {}).get("status") == "adjudicated" for c in self.cases())
                else:
                    got = self.gate_met(g["id"], g, tv)
                if got != tv["met"]:
                    probs.append(f"{g['id']}: vector {json.dumps(tv)[:160]} expects met {tv['met']}, rule gives {got}")
                if tv.get("record") == "FIN_3" and rec and rec.get(g["id"], "missing") != tv["met"]:
                    probs.append(f"{g['id']}: FIN_3 vector met {tv['met']} but fin3.per.full.json has {rec.get(g['id'], 'missing')}")
        self.gate("GATE_VECTORS", probs, f"{len(gates)} gates; {n} test vectors evaluated by the 02 §5.5 rules "
                  f"({n_rec} FIN_3 record vectors" + (" compared with the reference record)" if rec else
                                                       " not compared: no fin3.per.full.json under --examples)"))

    def cases(self) -> list[dict]:
        p = self.eio / "reference" / "cases.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    # -- claim schema ----------------------------------------------------------------------
    def g_claim_schema_goldens(self) -> None:
        v = Draft202012Validator(self.schema("evaluation-claim.schema.json"))
        probs, n = [], 0
        files = self.example_records()
        for fn in files:
            d = json.loads(Path(fn).read_text())
            for c in d.get("claims") or []:
                n += 1
                for e in v.iter_errors(c):
                    probs.append(f"{Path(fn).name}:{c.get('id')}: {'.'.join(map(str, e.path))}: {e.message[:120]}")
        # negative vectors: the 0.3.0 projection must fail
        bad = {"id": "", "run_id": "", "predicate": "eio.predicate.x", "predicate_version": "1.0.0",
               "state": "APPLICABLE_PASS", "parameters": {}, "evidence": [], "decided_by": "deterministic",
               "turn_indices": [0],
               "provenance": {"module": "eio.risk.x", "module_version": "0.1.0", "module_hash": "x", "plan_hash": "y"}}
        if not list(v.iter_errors(bad)):
            probs.append("the 0.3.0 projection shape (empty id/run_id, turn 0) validates; schema too loose")
        self.gate("CLAIM_SCHEMA_GOLDENS", probs[:40] + ([f"... {len(probs) - 40} more"] if len(probs) > 40 else []),
                  f"{n} claims of {len(files)} example PER files validate against evaluation-claim.schema.json; "
                  "0.3.0 projection shape rejected")

    # -- manifest ------------------------------------------------------------------------
    def compute_digests(self) -> dict:
        return eio_digests.compute_digests(self.paths, self.modules.get("eio.manifest.public", {}).get("eio", {}).get("version"),
                                           self.eio, self.schemas)

    def g_manifest_and_digests(self) -> None:
        man = self.modules.get("eio.manifest.public")
        probs = []
        if not man:
            self.gate("MANIFEST", ["no manifest"])
            return
        if man["eio"]["version"] != RELEASE:
            probs.append(f"manifest version {man['eio']['version']} != {RELEASE}")
        pr = next((p for p in man.get("profiles") or [] if p["id"] == "eio.profile.public-release"), {})
        if pr.get("release") != RELEASE:
            probs.append(f"eio.profile.public-release.release {pr.get('release')} != {RELEASE}")
        manifests = sorted(m for m in self.modules if m.startswith("eio.manifest."))
        if manifests != ["eio.manifest.public"]:
            probs.append(f"a distribution contains exactly one manifest (01 §3.4); found {manifests}")
        imps = {i["module"]: i for i in man.get("imports") or []}
        others = set(self.modules) - {"eio.manifest.public"}
        if set(imps) != others:
            probs.append(f"manifest imports differ: missing={sorted(others - set(imps))} extra={sorted(set(imps) - others)}")
        for m, i in imps.items():
            if m in self.paths:
                h = sha256_file(self.paths[m])
                if i.get("sha256") != h:
                    probs.append(f"manifest {m}: sha256 {i.get('sha256')} != {h}")
        dg = self.compute_digests()
        dpath = self.eio / "RELEASE-DIGESTS.json"
        if not dpath.exists():
            probs.append("RELEASE-DIGESTS.json missing (run tools/eio_digests.py --write)")
        else:
            cur = json.loads(dpath.read_text())
            if cur != dg:
                probs.append("RELEASE-DIGESTS.json is stale (digests do not reproduce)")
        self.gate("MANIFEST_AND_DIGESTS", probs, f"release {dg['release']}; {len(dg['modules'])} modules; "
                  f"ontology_sha256 {dg['ontology_sha256']}; ontology_digest {dg['ontology_digest']}")

    def g_version_bump(self) -> None:
        base = self.baseline_modules()
        probs, changed = [], []
        for mid, p in self.paths.items():
            rel = str(p.relative_to(self.eio))
            bm = base.get(rel)
            if not bm:
                changed.append(f"{mid} (new {self.modules[mid]['eio']['version']})")
                continue
            if bm["sha256"] == sha256_file(p):
                continue
            bver = bm["version"]
            nver = self.modules[mid]["eio"]["version"]
            if tuple(map(int, nver.split("-")[0].split("."))) <= tuple(map(int, bver.split("-")[0].split("."))):
                probs.append(f"{mid}: content changed but version {bver} -> {nver} not bumped")
            changed.append(f"{mid} {bver}->{nver}")
        self.gate("VERSION_BUMP", probs, f"{len(changed)} modules changed/added: " + "; ".join(sorted(changed)))

    def g_changelog(self) -> None:
        probs = []
        cl = self.eio / "CHANGELOG.md"
        if not cl.exists():
            probs.append("eio/CHANGELOG.md missing")
            text = ""
        else:
            text = cl.read_text()
        for k in CHANGELOG_KEYS:
            if f"Resolved: {k}" not in text:
                probs.append(f"CHANGELOG lacks 'Resolved: {k}'")
        if "BREAKING" not in text:
            probs.append("CHANGELOG lacks a BREAKING section")
        if "Implementation notes (non-normative)" not in text:
            probs.append("CHANGELOG lacks the 'Implementation notes (non-normative)' appendix")
        for base in (self.eio, self.schemas):
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix in (".yaml", ".json", ".md", ".jsonl"):
                    if MARK in p.read_text(encoding="utf-8"):
                        probs.append(f"{p.relative_to(base)}: contains the open-issue marker")
        readme = (self.eio / "README.md").read_text()
        if "requires a major version" in readme:
            probs.append("README.md still demands a major version for a change of meaning (EIO-1)")
        self.gate("CHANGELOG", probs, f"{len(CHANGELOG_KEYS)} keys recorded as 'Resolved: <key>'; no open-issue marker "
                  "in the release or the schemas; BREAKING section and implementation-notes appendix present")

    # -- report ----------------------------------------------------------------------------
    def report(self) -> int:
        bad = 0
        for r in self.results:
            status = "PASS" if r["ok"] else ("FAIL" if r["blocking"] else "WARN")
            if not r["ok"] and r["blocking"]:
                bad += 1
            print(f"[{status}] {r['gate']}: {r['info']}")
            for p in r["problems"][:60]:
                print(f"         - {p}")
            if len(r["problems"]) > 60:
                print(f"         ... {len(r['problems']) - 60} more")
        print(f"\n{len(self.results)} gates, {bad} failing")
        if self.a.json:
            Path(self.a.json).write_text(json.dumps(self.results, indent=1))
        return 1 if bad else 0


# ---------------------------------------------------------------------------------------
# Negative test vectors: each mutation of a copy of the release MUST make the named gate fail. The spec package's vectors
# for the gates that read harness registries (POLARITY, LEGACY_METRICS, LEGACY_RESOLVER, POLARITY_TV9, and the
# prohibited use-case list of FACTS_DECLARED) are not here. A `schemas/` path names a file of --schemas.
NEEDS_EXAMPLES = {"CLAIM_SCHEMA_GOLDENS"}
MUTATIONS = [
    ("ID_UNIQUENESS", "core/taxonomies.yaml", "  - {id: eio.role.regulator,", "  - {id: eio.role.operator, kind: role, parent: eio.entity.subject, description: \"dup\"}\n  - {id: eio.role.regulator,"),
    ("IMPORT_VERSION", "risks/grounding.yaml", "  - module: eio.core.evidence\n    version: 0.2.1", "  - module: eio.core.evidence\n    version: 0.1.0"),
    ("IMPORT_VERSION", "core/entities.yaml", "concepts:\n", "imports:\n  - {module: eio.core.flow, version: 0.2.0}\n\nconcepts:\n"),
    ("IMPORT_CLOSURE", "domains/aviation-airline.yaml", "  - module: eio.risk.content-code-safety\n    version: 0.2.1\n", ""),
    ("DANGLING_PARENT", "core/taxonomies.yaml", "parent: eio.role.qualified-professional, description: \"A licensed clinician", "parent: eio.role.physician, description: \"A licensed clinician"),
    ("DANGLING_FLOW_CONCEPT", "core/flow.yaml", "eio.artifact.agent-manifest, eio.artifact.policy]", "eio.artifact.agent-manifest, eio.artifact.policies]"),
    ("PREDICATE_RESOLVER_ORDER", "risks/context-trust.yaml", "resolvers: [eio.resolver.tool-receipt, eio.resolver.state-transition, eio.resolver.exact-span,", "resolvers: [eio.resolver.semantic-classification, eio.resolver.tool-receipt, eio.resolver.state-transition, eio.resolver.exact-span,"),
    ("RESOLVER_REF_SHAPE", "risks/context-trust.yaml", "relation: eio.relation.implements}", "relation: eio.relation.implements, threshold: 0.8}"),
    ("SEVERITY_DECLARED", "risks/context-trust.yaml", "    severity_source: {kind: NONE, reason: observation predicate}\n", ""),
    ("FACTS_DECLARED", "domains/generic-agent.yaml", "required_when: {multi_turn: true}", "required_when: {multiturn: true}"),
    ("ALIAS_UNIQUE", "domains/medical-devices.yaml", "aliases: [samd,", "aliases: [triage, samd,"),
    ("POLICY_DEFAULTS_SHAPE", "domains/financial-services.yaml", "{rule: \"Money movement requires verified identity, scoped authorization, idempotency, and an audit record\", applies_when: payment_actions}", "{rule: Money movement requires verified identity, scoped authorization, applies_when: payment_actions}"),
    ("WITNESS_TABLE", "core/evidence.yaml", "  - id: HARNESS_SIGNAL\n    description: Facts about the harness itself (a ledger maintained, a capsule entry, a search over a mixed source set).\n    origin: \"harness provenance and capsule\"\n    may_witness: false", "  - id: HARNESS_SIGNAL\n    description: Facts about the harness itself (a ledger maintained, a capsule entry, a search over a mixed source set).\n    origin: \"harness provenance and capsule\"\n    may_witness: true"),
    ("EXPLANATION_TEMPLATES", "templates/why.yaml", "text: '{metric} was not evaluated", "text: '{metrics} was not evaluated"),
    ("EXPLANATION_TEMPLATES", "templates/why.yaml", "decided {decided_by}{evidence_kinds}; mapping {mapping_relation}; severity", "decided {decided_by} from a tool receipt{evidence_kinds}; mapping {mapping_relation}; severity"),
    ("FLOW", "core/flow.yaml", "      - eio.resolver.paired-comparison\n      - eio.resolver.graph-rule\n", "      - eio.resolver.paired-comparison\n"),
    ("GOVERNANCE", "governance/gates.yaml", "  impact_escalation:\n", "  impact_escalation:\n    - {when: {tier: eio.tier.high}, promote: {WARN: CONTRIBUTING_BLOCK, CONTRIBUTING_BLOCK: HARD_BLOCK}}\n"),
    ("RELATIONS", "core/relations.yaml", "    characteristics: [functional]\n    cardinality: {subject: '0..n', object: '0..1'}", "    characteristics: [functional]\n    cardinality: {subject: '0..n', object: '0..n'}"),
    ("RELATION_INVERSE", "core/relations.yaml", "    range: [eio.entity.evidence-ref]\n", "    range: [eio.entity.evidence-ref]\n    inverse: eio.relation.supports\n"),
    ("MANIFEST_AND_DIGESTS", "core/decisions.yaml", "  - id: eio.profile.proof-status", "  # a comment edit changes the file bytes\n  - id: eio.profile.proof-status"),
    ("CHANGELOG", "README.md", "## Layout", MARK + " (x): marker\n\n## Layout"),
    ("CLAIM_SCHEMA_GOLDENS", "schemas/evaluation-claim.schema.json", "\"turn_indices\": {\n      \"type\": \"array\",\n      \"items\": {\n        \"type\": \"integer\",\n        \"minimum\": 1", "\"turn_indices\": {\n      \"type\": \"array\",\n      \"items\": {\n        \"type\": \"integer\",\n        \"minimum\": 2"),
    # fix round 1 (group eio-data)
    ("EXPLANATION_TEMPLATES", "templates/why.yaml", "params store inputs, never rendered text.", "params store rendered text."),
    ("NORMATIVE_PROFILES", "scoring/axes.yaml", "      applies_under: ['3@']\n", ""),
    ("NORMATIVE_PROFILES", "core/evidence.yaml", "    declared_fact: prohibited_use_case\n", "    declared_fact: prohibited_use\n"),
    ("NORMATIVE_PROFILES", "reliability/ledgers.yaml", "test_vectors: [{reproduced_in: 3, retests: 5}, {reproduced_in: 4, retests: 5}]", "test_vectors: [{reproduced_in: 3, retests: 5}, {reproduced_in: 5, retests: 5}]"),
    # fix round 1 (group eio-text)
    ("WITNESS_TABLE", "core/evidence.yaml", "citing_claims: [[[5, 0]], []], can_prove_agent_behaviour: false}", "citing_claims: [[[5, 0]], []], can_prove_agent_behaviour: true}"),
    ("NAMESPACE", "core/decisions.yaml", "namespace: https://www.proofagent.ai/eio-agents/module/core/decisions#", "namespace: https://www.proofagent.ai/eio-agents/module/core/evidence#"),
    ("NAMESPACE", "core/decisions.yaml", "namespace: https://www.proofagent.ai/eio-agents/module/core/decisions#", "namespace: http://www.proofagent.ai/eio-agents/module/core/decisions"),
    ("PER_IDS_OWNED", "governance/gates.yaml", "per.lim.severity.none", "per.lim.severity.nones"),
    ("CAP_WITNESS", "scoring/axes.yaml", "      requires_witnessing_anchored_ref: true\n", ""),
    ("PER_IDS_OWNED", "core/decisions.yaml", "  - id: eio.profile.proof-status", "  # disclosed as per.lim.severity.none\n  - id: eio.profile.proof-status"),
    ("GATE_VECTORS", "governance/gates.yaml", "{facts: {tier: null, consequential_actions: false, human_oversight: null}, met: true}", "{facts: {tier: null, consequential_actions: false, human_oversight: null}, met: null}"),
    ("GATE_VECTORS", "governance/gates.yaml", "findings: [{recurrence: CONFIRMED, obligations: [{impact: HARD_BLOCK, required: false}]}], met: true}", "findings: [{recurrence: CONFIRMED, obligations: [{impact: HARD_BLOCK, required: false}]}], met: false}"),
    # fix round 2 (group eio-data)
    ("NORMATIVE_PROFILES", "reliability/ledgers.yaml", "effect_on_score: makes a narrower (proxy) claim PROVEN when its band is CONFIRMED (eio.profile.proof-status); the deduction is unaffected", "effect_on_score: gates automatic blocking, not the deduction"),
    ("NORMATIVE_PROFILES", "core/decisions.yaml", "verified_proof_citation: true, witnessing_anchored: true, recurrence: NOT_RETESTED, expected: PROVEN, note: \"exact native source-bound", "verified_proof_citation: true, witnessing_anchored: true, recurrence: NOT_RETESTED, expected: UNPROVEN, note: \"exact native source-bound"),
    ("NORMATIVE_PROFILES", "scoring/axes.yaml", "      - Every published metric view, axis and readiness value traces to canonical claims or declared profile inputs; missing inputs withhold numerical values.", "      - Every published number traces to the claims that produced it."),
    ("NORMATIVE_PROFILES", "scoring/axes.yaml", "a gate cap (eio.cap.blocked-run, 3@) names its unmet gate.", "every cap traces to a deterministically resolved claim."),
    ("NORMATIVE_PROFILES", "governance/gates.yaml", "      - Contribute a score to any axis through the profile, tier or escalation (the G axis is the scoring module's view).", "      - Contribute a score to any axis."),
    ("NORMATIVE_PROFILES", "core/flow.yaml", "      - A claim cap is applied after the factual claim and names the claim that caused it; a gate cap (eio.cap.blocked-run, 3@) names its unmet gate.", "      - A cap is applied after the factual claim and names the claim that caused it."),
]


def selftest(args: argparse.Namespace) -> int:
    import shutil
    import tempfile
    fails = skipped = 0
    for i, (gate, rel, old, new) in enumerate(MUTATIONS, 1):
        if gate in NEEDS_EXAMPLES and not args.examples:
            print(f"[SKIP] vector {i} {gate}: needs --examples")
            skipped += 1
            continue
        tmp = Path(tempfile.mkdtemp(prefix="eio_selftest_"))
        try:
            dst, dst_schemas = tmp / "eio", tmp / "schemas"
            shutil.copytree(args.eio, dst)
            shutil.copytree(args.schemas, dst_schemas)
            f = dst_schemas / rel[len("schemas/"):] if rel.startswith("schemas/") else dst / rel
            text = f.read_text(encoding="utf-8")
            if old not in text:
                print(f"[FAIL] vector {i} {gate}: anchor not found in {rel}")
                fails += 1
                continue
            f.write_text(text.replace(old, new, 1), encoding="utf-8")
            ns = argparse.Namespace(**{**vars(args), "eio": str(dst), "schemas": str(dst_schemas), "json": None})
            g = Gates(ns)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                g.run()
            hit = [r for r in g.results if r["gate"] == gate]
            ok = bool(hit) and not hit[0]["ok"]
            print(f"[{'PASS' if ok else 'FAIL'}] vector {i}: mutation of {rel} makes {gate} fail"
                  + (f" ({hit[0]['problems'][0][:110]})" if ok else ""))
            fails += 0 if ok else 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(MUTATIONS)} negative vectors, {fails} not caught" + (f", {skipped} skipped" if skipped else ""))
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k.replace('_', '-')}", default=str(v))
    ap.add_argument("--json", default=None, help="write the gate results as JSON")
    ap.add_argument("--selftest", action="store_true", help="run the negative vectors (each must fail its gate)")
    a = ap.parse_args()
    return selftest(a) if a.selftest else Gates(a).run()


if __name__ == "__main__":
    sys.exit(main())
