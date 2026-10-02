"""The EIO release. `load()` returns an `Ontology`: the EIO data in `data/`, loaded with the manifest pins verified.

The ProofAgent modules (legacy and trap mappings, the runtime crosswalk, check-keyed context links) are loaded and
verified like every module but not interpreted here; their readers use the generic accessor `Ontology.module(id)`.
"""
import json
import re
from pathlib import Path

import yaml

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require
from eio_agents.schemas import EIO_SCHEMA_DIR

# The decision states in the order of the PER enum; `Ontology` checks that the release declares exactly these.
STATES = ["APPLICABLE_PASS", "APPLICABLE_FAIL", "NOT_APPLICABLE", "UNRESOLVED", "EVIDENCE_INVALID", "EVIDENCE_INCOMPLETE",
          "EVALUATOR_ERROR"]
DATA_DIR = Path(__file__).resolve().parent / "data"
RELEASE_DIGESTS = "RELEASE-DIGESTS.json"


def norm_token(s):
    """eio.profile.domain-resolution: casefold, then every run of '_' or whitespace becomes '-'."""
    return re.sub(r"[_\s]+", "-", str(s).casefold())


ARTIFACT_ROOT = "eio.artifact.context"          # the concept every context-artifact kind specialises


def below(concepts, root):
    """The ids of the concepts that descend from `root` through `parent` (the root itself excluded); a cycle ends the walk."""
    parent = {c["id"]: c.get("parent") for c in concepts}
    out = set()
    for cid in parent:
        seen, p = {cid}, parent[cid]
        while p is not None and p not in seen:
            if p == root:
                out.add(cid)
                break
            seen.add(p)
            p = parent.get(p)
    return out


class Ontology:
    """The EIO release at `root`, loaded from the manifest; module digests verified against the pins (EIO-2, EIO-3)."""

    def __init__(self, root: Path):
        self.root = root
        man_raw = (root / "manifest.yaml").read_bytes()
        man = yaml.safe_load(man_raw)
        files = {}
        for f in sorted(root.rglob("*.yaml")):
            y = yaml.safe_load(f.read_bytes())
            if isinstance(y, dict) and isinstance(y.get("eio"), dict) and y["eio"].get("id"):
                files[y["eio"]["id"]] = f
        self.release = str(man["eio"]["version"])
        self.manifest_id = man["eio"]["id"]
        self.pins = {imp["module"]: {"version": str(imp["version"]), "sha256": imp["sha256"]} for imp in man["imports"]}
        self.doc, modules = {}, {}
        for imp in man["imports"]:
            mid = imp["module"]
            require(mid in files, "EIO_MODULE_ABSENT", mid)
            raw = files[mid].read_bytes()
            y = yaml.safe_load(raw)
            require(str(y["eio"]["version"]) == str(imp["version"]), "EIO_VERSION_PIN", mid)
            require(H(raw) == imp["sha256"], "EIO_DIGEST_PIN", mid)
            self.doc[mid] = y
            modules[mid] = H(raw)
        modules[man["eio"]["id"]] = H(man_raw)
        self.doc[man["eio"]["id"]] = man
        self.modules = dict(sorted(modules.items()))
        self.ontology_sha256 = H(jb(self.modules))
        self.ontology_digest = self.ontology_sha256[7:23]
        # ---- predicates, polarity, risk
        self.pred, self.mod_of_pred = {}, {}
        for mid, y in self.doc.items():
            for p in y.get("predicates") or []:
                self.pred[p["id"]] = p
                self.mod_of_pred[p["id"]] = (mid, str(y["eio"]["version"]))
        ev = self.doc["eio.core.evidence"]
        self.kind = {e["id"]: e for e in ev["evidence_types"]}
        self.source_type = {s["id"]: s for s in ev["source_types"]}
        self.resolver_kind = {r["id"]: r["kind"] for r in ev["resolvers"]}
        wr = [p for p in ev["profiles"] if p["id"] == "eio.profile.witness-rule"][0]
        self.witnessing_anchors = set(wr["witnessing_anchors"])
        self.anchors = self.witnessing_anchors | set(wr["non_witnessing_anchors"])     # the closed anchor vocabulary
        dec = self.doc["eio.core.decisions"]
        self.states = [s["id"] if isinstance(s, dict) else s for s in dec["decision_states"]]
        require(self.states == STATES, "EIO_STATES", "decision states differ from the PER enum order")
        # ---- metrics (every eio.metric.*, in module order)
        self.metrics = [c for c in self.doc["eio.mapping.metrics"]["concepts"] if c.get("kind") == "metric"]
        # ---- domains
        self.domains = {}
        for mid, y in self.doc.items():
            if mid.startswith("eio.domain.") and isinstance(y.get("domain"), dict):
                d = y["domain"]
                self.domains[d["id"]] = {
                    "aliases": [norm_token(a) for a in d.get("aliases") or []],
                    "imports": [i["module"] for i in y.get("imports") or [] if i["module"].startswith("eio.domain.")],
                    "obligations": d.get("coverage_obligations") or [],
                }
        self.obligation = {o["id"]: dict(o, domain=did) for did, d in self.domains.items() for o in d["obligations"]}
        # ---- governance
        gov = self.doc["eio.governance.gates"]["governance"]
        self.tiers = {t["id"]: t for t in gov["tiers"]}
        self.gates = gov["gates"]
        self.escalation = gov["impact_escalation"]
        self.facts = {f["id"]: f for f in gov["facts"]}
        self.regions = {r["id"]: r for r in gov["regions"]}
        self.autonomy = {a["id"]: a for a in gov["autonomy_levels"]}
        self.profiles = {p["id"]: p for y in self.doc.values() for p in (y.get("profiles") or []) if isinstance(p, dict)}
        # ---- scoring
        sc = self.doc["eio.scoring.axes"]["scoring"]
        self.axes = sc["axes"]
        self.cap = [c for c in sc["caps"] if c["id"] == "eio.cap.proven-critical-breach"][0]
        self.cap_preds = set(self.cap["applies_to_predicates"])
        self.floor = {f["id"]: f for f in sc["floors"]}
        self.release_evidence_floor = float(self.floor["eio.floor.release-evidence"]["value"])
        # A neutral release may not prescribe a producer-specific metric floor.
        self.critical_metric_floor = self.floor.get("eio.floor.critical-metric")
        # ---- compliance
        comp = self.doc["eio.compliance.frameworks"]
        self.frameworks = {f["id"]: f for f in comp["frameworks"]}
        self.controls = {c["id"]: c for c in comp["controls"]}
        self.fw_of_registry = {f["registry_id"]: fid for fid, f in self.frameworks.items()}
        # ---- context
        self.criteria = {c["id"]: c for c in self.doc["eio.context.criteria"]["context_criteria"]}
        # the closed vocabularies of a context artifact (L2 exit D-29): its data class, a `data-class` concept of the release
        # (PROD-43 keys on it, so an id the release does not define fails closed instead of reading as not confidential), and
        # its kind, a concept below eio.artifact.context
        concepts = [c for y in self.doc.values() for c in (y.get("concepts") or []) if isinstance(c, dict) and c.get("id")]
        self.data_classes = frozenset(c["id"] for c in concepts if c.get("kind") == "data-class")
        self.artifact_kinds = frozenset(below(concepts, ARTIFACT_ROOT))
        # ---- reliability
        rel = self.doc["eio.reliability.ledgers"]["reliability"]
        self.minimum_tasks = int(rel["publication"]["minimum_tasks"])
        # ---- explanation templates (EIO-49)
        self.templates = {t["id"]: t for t in self.doc["eio.template.why"]["explanation_templates"]}
        # ---- reference cases (independent-adjudication gate)
        self.reference_cases = [json.loads(line) for line in (root / "reference/cases.jsonl").read_text(encoding="utf-8").splitlines()
                                if line.strip()]

    def module(self, module_id):
        """A module document of the loaded release by id (manifest-pinned and verified), for readers of modules this class
        does not interpret."""
        require(module_id in self.doc, "EIO_MODULE_ABSENT", module_id)
        return self.doc[module_id]

    # -- witness rule (01 §6.3 W4; eio.profile.witness-rule; PER-68); `eio_agents.evidence.witness` exposes it as free
    #    functions over a loaded release
    def can_prove(self, kind, source_type, paired_call=False):
        """Whether a ref of this kind and source type can prove agent behaviour under this release."""
        k, s = self.kind[kind], self.source_type[source_type]
        if not (k["can_prove_agent_behaviour"] and s["may_witness"] and source_type in k["compatible_source_types"]):
            return False
        if s.get("witness_requires"):
            return bool(paired_call)
        return True

    def witnessing_anchored(self, ref):
        """A ref that can prove agent behaviour and carries a witnessing anchor of this release."""
        return ref["can_prove_agent_behaviour"] and ref["anchor"] in self.witnessing_anchors

    def polarity(self, predicate):
        return self.pred[predicate]["polarity"]

    def resolver_ids(self, predicate):
        return [r if isinstance(r, str) else r["id"] for r in self.pred[predicate].get("resolvers") or []]


def load(root=None) -> Ontology:
    """The EIO release at `root` (default: the bundled `data/`), read and verified on every call: a new `Ontology`, with no
    process-global cache. A caller that converts many records holds one and passes it on."""
    return Ontology(Path(root).resolve() if root is not None else DATA_DIR)


def release_digests(root: Path = DATA_DIR) -> dict:
    """RELEASE-DIGESTS.json of the release: module digests, ontology_sha256, ontology_digest and the pinned files."""
    return json.loads((root / RELEASE_DIGESTS).read_text(encoding="utf-8"))


def release_file(rel: str, root: Path = DATA_DIR) -> Path:
    """Where a file pinned in RELEASE-DIGESTS.json `files` lives: `schemas/<name>` in `eio_agents.schemas`, the rest in
    the release directory."""
    if rel.startswith("schemas/"):
        return EIO_SCHEMA_DIR / rel[len("schemas/"):]
    return root / rel
