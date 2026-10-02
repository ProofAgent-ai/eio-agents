"""The verifier's own EIO reader and the limitation catalogue.

Independent of `eio_agents.ontology`: it reads the files of the bundled release itself. It interprets the
neutral content only; the rc1 verifier of the ProofAgent adapter (`LegacyEIO` of its legacy verifier, in the ProofAgent
Harness since L3) adds the legacy adjunct (legacy check rows, legacy metric keys, trap severities) through the generic
module accessor `module(id)`.
"""
import json
import re
from pathlib import Path

import yaml

from eio_agents.per.limitations import CATALOGUE as LIMITATION_CATALOGUE
from eio_agents.validation.canon import sha

__all__ = ["EIO", "EIO_DIR", "load_catalogue"]

EIO_DIR = Path(__file__).resolve().parent.parent / "ontology" / "data"   # the bundled release, located without the converter


class EIO:
    """The EIO release at `root`, read by the verifier itself: module digests, predicates, evidence kinds and source
    types, states, domains and obligations, governance, scoring, compliance, criteria, templates and reference cases."""

    def __init__(self, root):
        man_raw = (root / "manifest.yaml").read_bytes()
        self.man = yaml.safe_load(man_raw)
        self.files = {}
        for f in root.rglob("*.yaml"):
            y = yaml.safe_load(f.read_bytes())
            if isinstance(y, dict) and isinstance(y.get("eio"), dict) and y["eio"].get("id"):
                self.files[y["eio"]["id"]] = f
        self.release = str(self.man["eio"]["version"])
        self.manifest_id = self.man["eio"]["id"]
        self.imports = {i["module"]: i for i in self.man["imports"]}
        self.doc = {m: yaml.safe_load(self.files[m].read_bytes()) for m in list(self.imports) + [self.manifest_id]}
        self.module_sha = {m: sha(self.files[m].read_bytes()) for m in self.doc}
        self.version = {m: str(d["eio"]["version"]) for m, d in self.doc.items()}
        self.pred, self.pred_mod = {}, {}
        for m, d in self.doc.items():
            for p in d.get("predicates") or []:
                self.pred[p["id"]] = p
                self.pred_mod[p["id"]] = m
        ev = self.doc["eio.core.evidence"]
        self.kinds = {k["id"]: k for k in ev["evidence_types"]}
        self.sources = {s["id"]: s for s in ev["source_types"]}
        self.resolvers = {r["id"]: r for r in ev["resolvers"]}
        wr = [p for p in ev["profiles"] if p["id"] == "eio.profile.witness-rule"][0]
        self.wanchors = set(wr["witnessing_anchors"])
        self.anchors = self.wanchors | set(wr["non_witnessing_anchors"])
        self.states = [s["id"] if isinstance(s, dict) else s for s in self.doc["eio.core.decisions"]["decision_states"]]
        met = self.doc["eio.mapping.metrics"]
        self.metrics = [c for c in met["concepts"] if c.get("kind") == "metric"]
        self.domains = {}
        for m, d in self.doc.items():
            if m.startswith("eio.domain.") and isinstance(d.get("domain"), dict):
                self.domains[d["domain"]["id"]] = {"imports": [i["module"] for i in d.get("imports") or [] if i["module"].startswith("eio.domain.")],
                                                   "obligations": {o["id"]: o for o in d["domain"].get("coverage_obligations") or []},
                                                   "aliases": [re.sub(r"[_\s]+", "-", a.casefold()) for a in d["domain"].get("aliases") or []]}
        self.obligation = {oid: dict(o, domain=did) for did, d in self.domains.items() for oid, o in d["obligations"].items()}
        gov = self.doc["eio.governance.gates"]["governance"]
        self.gates = gov["gates"]
        self.tiers = {t["id"]: t for t in gov["tiers"]}
        self.regions = {r["id"] for r in gov["regions"]}
        self.autonomy = {a["id"] for a in gov["autonomy_levels"]}
        self.escalation = gov["impact_escalation"]
        self.facts = {f["id"]: f for f in gov["facts"]}
        self.profiles = {p["id"]: p for d in self.doc.values() for p in (d.get("profiles") or []) if isinstance(p, dict)}
        sc = self.doc["eio.scoring.axes"]["scoring"]
        self.axes = sc["axes"]
        self.caps = {c["id"]: c for c in sc["caps"]}
        self.floors = {f["id"]: f for f in sc["floors"]}
        comp = self.doc["eio.compliance.frameworks"]
        self.frameworks = {f["id"]: f for f in comp["frameworks"]}
        self.controls = {c["id"]: c for c in comp["controls"]}
        self.criteria = {c["id"]: c for c in self.doc["eio.context.criteria"]["context_criteria"]}
        # a context artifact's closed vocabularies, read here independently of the projector (L2 exit D-29): the data-class
        # concepts, and the kinds below eio.artifact.context
        concepts = [c for d in self.doc.values() for c in (d.get("concepts") or []) if isinstance(c, dict) and c.get("id")]
        self.data_classes = {c["id"] for c in concepts if c.get("kind") == "data-class"}
        parent = {c["id"]: c.get("parent") for c in concepts}
        self.artifact_kinds = set()
        for cid in parent:
            seen, up = {cid}, parent[cid]
            while up is not None and up not in seen:
                if up == "eio.artifact.context":
                    self.artifact_kinds.add(cid)
                    break
                seen.add(up)
                up = parent.get(up)
        self.templates = {t["id"]: t for t in self.doc["eio.template.why"]["explanation_templates"]}
        self.minimum_tasks = int(self.doc["eio.reliability.ledgers"]["reliability"]["publication"]["minimum_tasks"])
        self.trial_kinds = {t["id"] for t in self.doc["eio.reliability.ledgers"]["reliability"]["trial_kinds"]}
        self.flow = {s["id"] for s in self.doc["eio.core.flow"]["flow"]}
        self.cases = [json.loads(x) for x in (root / "reference/cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

    def module(self, module_id):
        """A module document by id, for readers of modules this class does not interpret."""
        return self.doc[module_id]

    def can_prove(self, kind, source, paired=False):
        k, s = self.kinds[kind], self.sources[source]
        ok = k["can_prove_agent_behaviour"] and s["may_witness"] and source in k["compatible_source_types"]
        if ok and s.get("witness_requires"):
            ok = paired
        return bool(ok)


def load_catalogue():
    """The 04 §5.13 limitation catalogue, read from its data file: id -> status, paths and text templates."""
    doc = json.loads(LIMITATION_CATALOGUE.read_text(encoding="utf-8"))
    return {r["id"]: {"status": r["status"], "paths": list(r["paths"]), "reason": r["reason"], "impact": r["impact"],
                      "next_step": r["next_step"]} for r in doc["limitations"]}
