"""The record-level checks of the reference PER verifier (03 §3.3 VER-1, VER-3, VER-4).

`Checker` holds the bookkeeping and every check that reads only the record and the EIO release: schema, NFC, claim schema,
header, EIO digests and ids, domains, refs, witness rule, counts, orders, claim ids and parameters, evidence contracts,
coverage, findings, controls, scores, explanations, gates, release, reliability, limitations, numbers, wording, pointers
and per_sha256. The mixed checks are split at their seams (split plan §3.10 row 19): the neutral half is here, and the
ProofAgent half (the rc1 legacy rows, the harness-2.x profile checks, the archive checks) is added by the producer
verifier (`LegacyChecker` of the ProofAgent adapter's legacy verifier, in the ProofAgent Harness since L3), which
overrides the hooks `episode_turns`, `census`, `targets_unobservable` and `cap_proof`.

The historical rc1 claim-id and sort recipes remain available for frozen records.
The isolated neutral rc2 preview selects `source_key` and the neutral sort key by
its exact schema URI. This is preparatory only; the complete L5a reissue is pending.
"""
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal

from jsonschema import Draft202012Validator, FormatChecker

from eio_agents.schemas import EIO_SCHEMA_CURRENT_DIR, PER_SCHEMAS
from eio_agents.validation.catalogue import CatalogueError, check_record_catalogues
from eio_agents.validation.canon import jb, q4, sd, sha
from eio_agents.validation.full_score import default_floor_guards
from eio_agents.validation.gates import gate_inputs, gate_met
from eio_agents.validation.pointer import resolve_pointer
from eio_agents.validation.redaction import EXCERPT_LIMIT, surviving_matches
from eio_agents.validation.privacy import _score, record_problems
from eio_agents.validation.render import render

# the `via` of a context ref (the rc1 schema's two forms): a context link from a label, or a checklist row
VIA_LINK = re.compile("eio\\.graph\\.context-links:[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}\u2192(?P<criterion>[^/]+)/(?P<control>[^/]+)")
VIA_CRITERION = re.compile(r"eio\.context\.criteria:(?P<criterion>[^/]+)/(?P<control>[^/]+)")

VER6 = ("VER-6: these checks establish the integrity of the record (VER-1, VER-3, VER-4) and, with the archive, its "
        "derivation from the archive (VER-5). They do not show that the agent, or the evaluator model's judgement, would be "
        "the same again. A claim decided only by an evaluator model is never PROVEN and cannot by itself make the recommendation BLOCK.")

RELEASE_SEMANTICS = "2.x"      # the release-semantics version of a 2.0 record (PER-16); the verifier's own constant (P3)
NEUTRAL_RC3_PREVIEW_URI = "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json"
INTERNAL_RC3_PREVIEW_URI = "urn:eio-agents:diagnostic:per:2.0.0-rc3-neutral-preview"
NEUTRAL_RC4_URI = "https://w3id.org/eio-agents/per/2.0.0-rc4-draft/per.schema.json"
POLICY_RC5_URI = "urn:eio-agents:provisional:per:2.0.0-rc5-policy-draft"
PER_2_0_0_URI = "https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json"
PER_2_1_0_URI = "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
NEUTRAL_SCHEMA_URIS = frozenset((NEUTRAL_RC3_PREVIEW_URI, INTERNAL_RC3_PREVIEW_URI, NEUTRAL_RC4_URI,
                                 POLICY_RC5_URI, PER_2_0_0_URI, PER_2_1_0_URI))
SCHEMA_VERSIONS = ("2.0.0-rc1", "2.0.0-rc2-draft", "2.0.0-rc3-draft",
                   "2.0.0-rc3-neutral-preview", "2.0.0-rc4-draft", "2.0.0-rc5-policy-draft", "2.0.0", "2.1.0")


def _schema_for_uri(uri):
    """Resolve one canonical static schema, never the first filesystem glob hit.

    Historical preview resources may carry the same URI as an older canonical
    schema. They remain packaged for compatibility but are not public schema
    authorities. The active rc3 resource is the unique website-facing schema.
    """
    for version in SCHEMA_VERSIONS:
        schema = json.loads(PER_SCHEMAS[version].read_text(encoding="utf-8"))
        if schema.get("$id") == uri:
            return schema
    return None
CAPSULE_ORDER = ["ontology_module_hashes", "agent_manifest_hash", "policy_hash", "tool_schema_hash", "domain_profile_hash",
                 "template_ids", "binding_ids", "generator_version", "seed", "evidence_graph_schema", "evidence_source_hashes",
                 "extractor_versions", "revision", "models", "prompt_hashes", "sampling_parameters", "cache_identity",
                 "predicate_versions", "metric_view_versions", "patch", "lock_digest"]      # PER-513 declaration order
IMP = ["NONE", "MONITOR", "WARN", "CONTRIBUTING_BLOCK", "HARD_BLOCK"]
SEVR = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFORMATIONAL": 1}
KORDER = ["AGENT_SPAN", "TOOL_RECEIPT", "TYPED_ABSENCE", "CALCULATION", "STATE_FACT", "STATE_TRANSITION", "USER_INPUT",
          "RETRIEVAL", "POLICY_SPAN", "PROVENANCE", "HUMAN_SIGNOFF"]
FAULT = {"EVIDENCE_INVALID", "EVIDENCE_INCOMPLETE", "EVALUATOR_ERROR"}
SCORED = {"APPLICABLE_PASS", "APPLICABLE_FAIL"}
READS = {"eio.resolver.tool-receipt": {"TOOL_RECEIPT"}, "eio.resolver.typed-absence": {"TYPED_ABSENCE"},
         "eio.resolver.state-transition": {"STATE_FACT", "STATE_TRANSITION"}, "eio.resolver.paired-comparison": {"CALCULATION"},
         "eio.resolver.exact-span": {"AGENT_SPAN"}, "eio.resolver.arithmetic": {"AGENT_SPAN", "CALCULATION"}}


def rc1_claim_key(c):
    """The rc1 claim order (§5.6 rule 1): (first turn, predicate, rc1 source key or "", id). The twin of the projector's
    rule; `(turn_indices, predicate, id)` from L5a. A native claim has no source key."""
    return (min(c["turn_indices"]), c["predicate"], c["parameters"].get("legacy_check") or "", c["id"])


def neutral_claim_key(c):
    """The L5a order does not depend on any adapter crosswalk source key."""
    return (tuple(c["turn_indices"]), c["predicate"], c["id"])


class Checker:
    """The record-level checks of one PER record against the loaded EIO release (`reader.EIO`) and the limitation
    catalogue; each check returns (problems, info) and `run` records it as PASS, FAIL or SKIP."""

    def __init__(self, rec, eio, cat, label):
        self.rec, self.eio, self.cat, self.label = rec, eio, cat, label
        self.rows = []                       # (check, ver, status, detail)
        self.abridged = any(l["limitation_id"] == "per.lim.example.abridged" for l in rec.get("limitations") or [])
        self.C = {c["id"]: c for c in rec["claims"]}
        self.CI = {c["id"]: i for i, c in enumerate(rec["claims"])}
        self.R = {r["id"]: r for r in rec["evidence"]["refs"]}
        self.RI = {r["id"]: i for i, r in enumerate(rec["evidence"]["refs"])}
        self.F = {f["finding_id"]: f for f in rec["findings"]}
        self.FI = {f["finding_id"]: i for i, f in enumerate(rec["findings"])}
        self.A = None                        # the archive, when one is given (archive-derived reconciliation, e.g. L1 named lists)

    # -------------------------------------------------------------- bookkeeping
    def run(self, name, ver, fn, skip_if_abridged=False):
        if skip_if_abridged and self.abridged:
            self.rows.append((name, ver, "SKIP", "abridged record: reconciliation skipped as declared by per.lim.example.abridged"))
            return
        try:
            problems, info = fn()
        except Exception as e:                                    # a crash is a failure, never a pass
            problems, info = [f"{type(e).__name__}: {e}"], ""
        if problems:
            self.rows.append((name, ver, "FAIL", f"{len(problems)} problem(s); first: {problems[0]}"))
        else:
            self.rows.append((name, ver, "PASS", info))

    def wa(self, rid):
        r = self.R[rid]
        return r["can_prove_agent_behaviour"] and r["anchor"] in self.eio.wanchors

    def witnesses(self, rid, predicate):
        """A witnessing anchored ref that witnesses a claim on `predicate`: a STATE_FACT (a declared state snapshot is
        non-empty) only where the predicate's evidence contract names STATE_FACT (L3 fix round 1, issue 8)."""
        if not self.wa(rid):
            return False
        if self.R[rid]["kind"] != "STATE_FACT":
            return True
        ec = self.eio.pred[predicate].get("evidence_contract") or {}
        named = set(ec.get("require_all") or []) | set(ec.get("require_any") or []) | {k for g in ec.get("require_groups") or [] for k in g}
        return "STATE_FACT" in named

    def basis(self, cl):
        s = Counter(c["state"] for c in cl)
        return {"claims": len(cl), "applicable": s["APPLICABLE_PASS"] + s["APPLICABLE_FAIL"], "pass": s["APPLICABLE_PASS"],
                "fail": s["APPLICABLE_FAIL"], "not_applicable": s["NOT_APPLICABLE"], "unresolved": s["UNRESOLVED"],
                "evaluator_fault": sum(s[x] for x in FAULT)}

    def explanations(self):
        out = []
        rec = self.rec

        def walk(o, path):
            if isinstance(o, dict):
                if "template_id" in o and "summary" in o:
                    out.append((path, o))
                for k, v in o.items():
                    walk(v, path + "/" + k)
            elif isinstance(o, list):
                for i, x in enumerate(o):
                    walk(x, path + "/" + str(i))
        walk(rec, "")
        return out

    # -------------------------------------------------------------- S: schema, EIO digests
    def c_schema(self):
        uri = self.rec["header"]["schema_uri"]
        schema = _schema_for_uri(uri)
        if schema is None:
            return [f"no local schema with $id {uri}"], ""
        Draft202012Validator.check_schema(schema)
        errs = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(self.rec))
        return [f"{'/'.join(map(str, e.path))}: {e.message[:160]}" for e in errs], f"0 errors against {uri}"

    def c_nfc(self):
        """VER-4 (03 §13.2, schema $defs/relative_path): every relative_path value is in Unicode NFC. The schema cannot say
        it, so its relative_path definition is given a verifier-only format and the record is validated against that."""
        import copy as _copy
        import unicodedata
        uri = self.rec["header"]["schema_uri"]
        schema = _schema_for_uri(uri)
        if schema is None:
            return [f"no local schema with $id {uri}"], ""
        s = _copy.deepcopy(schema)
        s["$defs"]["relative_path"]["format"] = "per-verifier-nfc"
        fc, seen = FormatChecker(), []

        @fc.checks("per-verifier-nfc")
        def _nfc(v):
            if not isinstance(v, str):
                return True
            seen.append(v)
            return unicodedata.is_normalized("NFC", v)
        mine = lambda e: e.validator == "format" and e.validator_value == "per-verifier-nfc"
        bad = [f"{'/'.join(map(str, e.path))}: relative_path is not in Unicode NFC (VER-4, §13.2)"
               for e in Draft202012Validator(s, format_checker=fc).iter_errors(self.rec)
               if mine(e) or any(mine(c) for c in e.context or [])]
        return bad, f"{len(seen)} relative_path values checked, all NFC"

    def c_claim_schema(self):
        s = json.loads((EIO_SCHEMA_CURRENT_DIR / "evaluation-claim.schema.json").read_text(encoding="utf-8"))
        v = Draft202012Validator(s)
        bad = [f"{c['id']}: {e.message[:120]}" for c in self.rec["claims"] for e in v.iter_errors(c)]
        return bad, f"{len(self.rec['claims'])} claims valid against eio/schemas/evaluation-claim.schema.json"

    def c_eio_digests(self):
        e, h, p = self.eio, self.rec["header"]["eio"], []
        if h["release"] != e.release:
            p.append(f"eio.release {h['release']} != {e.release}")
        full = dict(sorted(e.module_sha.items()))
        if sha(jb(full)) != h["ontology_sha256"]:
            p.append("ontology_sha256 does not recompute from the EIO release in ../eio/")
        if h["ontology_sha256"][7:23] != h["ontology_digest"]:
            p.append("ontology_digest != ontology_sha256[7:23]")
        for m, d in h["modules"].items():
            if full.get(m) != d:
                p.append(f"module {m}: {d} != {full.get(m)}")
        if not self.abridged and set(h["modules"]) != set(full):
            p.append(f"modules set differs from manifest imports + manifest ({len(h['modules'])} vs {len(full)})")
        for mid, imp in e.imports.items():
            if imp.get("sha256") and imp["sha256"] != e.module_sha[mid]:
                p.append(f"manifest pin {mid} does not match the file")
        return p, f"{len(h['modules'])} module hashes; ontology_sha256 {h['ontology_sha256'][:23]}…"

    # -------------------------------------------------------------- E: evidence refs, witness rule (PER-68), counts
    def cited(self):
        out = defaultdict(set)

        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("evidence", "evidence_refs", "counterevidence") and isinstance(v, list) and all(isinstance(x, str) for x in v):
                        for x in v:
                            out[x].add(path + "/" + k)
                    elif k in ("ref", "ref_id") and isinstance(v, str):
                        out[v].add(path + "/" + k)
                    elif k != "refs" or not path.endswith("/evidence"):
                        walk(v, path + "/" + k)
            elif isinstance(o, list):
                for i, x in enumerate(o):
                    walk(x, path + "/" + str(i))
        walk(self.rec, "")
        return out

    def c_refs_resolve(self):
        p = []
        ids = [r["id"] for r in self.rec["evidence"]["refs"]]
        if len(ids) != len(set(ids)):
            p.append("duplicate ref ids")
        cited = self.cited()
        for rid, where in cited.items():
            if rid not in self.R:
                p.append(f"cited ref {rid} does not resolve (at {sorted(where)[0]})")
        for rid in self.R:
            if rid not in cited:
                p.append(f"ref {rid} is carried but cited nowhere (only cited refs are carried)")
        return p, f"{len(cited)} cited ref ids resolve; {len(self.R)} carried refs all cited"

    def c_witness(self):
        """03 §7.5.2 / 01 §6.3 W4 recomputed from EIO data; PER-68: TOOL_RESULT only with its AGENT_TOOL_CALL cited by the same claim."""
        e, p = self.eio, []
        calls = {(r["turn_index"], (r.get("tool") or {}).get("call_index")) for r in self.rec["evidence"]["refs"] if r["source_type"] == "AGENT_TOOL_CALL"}
        claims_citing = defaultdict(list)
        for c in self.rec["claims"]:
            for r in c["evidence"] + c.get("counterevidence", []):
                claims_citing[r].append(c)
        n = Counter()
        for r in self.rec["evidence"]["refs"]:
            if r["source_type"] not in e.kinds[r["kind"]]["compatible_source_types"]:   # 01 §6.1: the pair MUST be compatible
                p.append(f"ref {r['id']}: source_type {r['source_type']} is not compatible with kind {r['kind']} "
                         f"(compatible_source_types {e.kinds[r['kind']]['compatible_source_types']}, 01 §6.1)")
            paired = False
            if r["source_type"] == "TOOL_RESULT":
                key = (r["turn_index"], (r.get("tool") or {}).get("call_index"))
                paired = key in calls and all(any(self.R[x]["source_type"] == "AGENT_TOOL_CALL" and
                                                  (self.R[x]["turn_index"], (self.R[x].get("tool") or {}).get("call_index")) == key
                                                  for x in c["evidence"]) for c in claims_citing[r["id"]]) and bool(claims_citing[r["id"]])
            exp = e.can_prove(r["kind"], r["source_type"], paired)
            if r["can_prove_agent_behaviour"] != exp:
                p.append(f"ref {r['id']}: can_prove_agent_behaviour {r['can_prove_agent_behaviour']} != computed {exp} (W4{', PER-68' if r['source_type'] == 'TOOL_RESULT' else ''})")
            if r["source_type"] == "HUMAN_REVIEW" and r["kind"] != "HUMAN_SIGNOFF":
                p.append(f"ref {r['id']}: HUMAN_REVIEW only on HUMAN_SIGNOFF")
            anc = r["anchor"]
            if anc in ("receipt", "computed", "document", "none") and (r.get("char_start") is not None or "excerpt" in r):
                p.append(f"ref {r['id']}: anchor {anc} carries offsets or an excerpt")
            if anc in ("exact", "casefold", "turn", "line") and r.get("char_start") is None:
                p.append(f"ref {r['id']}: anchor {anc} without offsets")
            if (r["kind"] == "TOOL_RECEIPT") != ("tool" in r) or (r["kind"] == "TOOL_RECEIPT" and anc != "receipt"):
                p.append(f"ref {r['id']}: tool member iff TOOL_RECEIPT with anchor receipt")
            if r["kind"] in ("TYPED_ABSENCE", "CALCULATION") and (anc != "computed" or "formula" not in (r.get("statement") or {})):
                p.append(f"ref {r['id']}: {r['kind']} needs anchor computed and a statement with a formula")
            if r["source_type"] == "JUROR_INFERENCE" and ("excerpt" in r or anc != "none"):
                p.append(f"ref {r['id']}: a juror citation has anchor none and no excerpt (PROD-5)")
            if r.get("excerpt") is not None:                    # PROD-42, record only (D2 recomputes it from the archive)
                n["excerpts"] += 1
                for cls, txt in surviving_matches(r["excerpt"], bool(r.get("excerpt_truncated"))):   # reported first
                    p.append(f"ref {r['id']}: {'an' if cls[0] in 'aeiou' else 'a'} {cls} match survives in the excerpt at code point "
                             f"{r['excerpt'].find(txt)} (PROD-42 redaction classes; the value is not printed)")
                if len(r["excerpt"]) > EXCERPT_LIMIT:
                    p.append(f"ref {r['id']}: excerpt longer than {EXCERPT_LIMIT} code points (PROD-42)")
            if r.get("span_sha256") is not None and r.get("char_start") is None:
                p.append(f"ref {r['id']}: span_sha256 without offsets")
            n["agent"] += r["can_prove_agent_behaviour"]
        return p, (f"(kind, source_type) compatible and can_prove_agent_behaviour recomputed for {len(self.R)} refs "
                   f"({n['agent']} agent refs); PER-68 TOOL_RESULT pairing checked; {n['excerpts']} excerpts <= "
                   f"{EXCERPT_LIMIT} code points with no redaction-class match left")

    def c_counts(self):
        ev, p = self.rec["evidence"], []
        refs = ev["refs"]
        if ev["cited_refs_hash"] != sd(sorted(r["id"] for r in refs)):
            p.append("cited_refs_hash does not recompute")
        exp = {"refs": len(refs), "by_kind": dict(sorted(Counter(r["kind"] for r in refs).items())),
               "agent_refs": sum(1 for r in refs if r["can_prove_agent_behaviour"]),
               "witnessing_anchored": sum(1 for r in refs if self.wa(r["id"]))}
        if ev["counts"] != exp:
            p.append(f"counts {ev['counts']} != {exp}")
        if ev["archive_pointer"]["archive_sha256"] != self.rec["header"]["archive_sha256"]:
            p.append("archive_pointer.archive_sha256 != header.archive_sha256")
        return p, f"cited_refs_hash {ev['cited_refs_hash']}; counts {exp['refs']} refs / {exp['agent_refs']} agent / {exp['witnessing_anchored']} witnessing anchored"

    # -------------------------------------------------------------- C: claims
    def c_claim_ids(self):
        rec, p = self.rec, []
        run = rec["provenance"]["run"]["run_id"]
        neutral = rec["header"]["schema_uri"] in NEUTRAL_SCHEMA_URIS
        for c in rec["claims"]:
            if c["run_id"] != run:
                p.append(f"claim {c['id']}: run_id differs")
            recipe = {"run_id": c["run_id"], "predicate": c["predicate"],
                      "predicate_version": c["predicate_version"],
                      "turn_indices": sorted(c["turn_indices"])}
            if neutral:
                recipe["source_key"] = c["parameters"]["source_key"]
            else:
                recipe["legacy_check"] = c["parameters"].get("legacy_check")
            exp = sd(recipe)
            if exp != c["id"]:
                p.append(f"claim {c['id']}: id recomputes to {exp} (01 §10.5)")
            if c["provenance"]["plan_hash"] != rec["provenance"]["run"]["plan_hash"]:
                p.append(f"claim {c['id']}: provenance.plan_hash differs")
        if len(self.C) != len(rec["claims"]):
            p.append("duplicate claim ids")
        return p, f"{len(rec['claims'])} claim ids recomputed from the record (01 §10.5)"

    def episode_turns(self, c):
        """The episode of a claim, read from the record: the union, over the claim's turns, of the turns that carry that
        turn's scenario label (`evidence.turns[].trap`, the rc1 name of the label), an unlabelled turn being its own
        episode. It is the grouping the projector requires of the bundle's episodes until S7 (review M-1)."""
        lab = {t["turn_index"]: t.get("trap") for t in self.rec["evidence"]["turns"]}
        out = set()
        for u in c["turn_indices"]:
            x = lab.get(u)
            out |= {t for t, y in lab.items() if y == x} if x is not None else {u}
        return out

    def in_scope(self, r, scope, c):
        """Whether ref r lies in the evidence-contract scope of claim c (01 §6.5)."""
        if r["kind"] in ("POLICY_SPAN", "PROVENANCE") or scope in ("run", "artifact", "paired-episode"):
            return True
        if r["turn_index"] is None:
            return False
        if scope in ("span", "turn"):
            return r["turn_index"] in c["turn_indices"]
        return r["turn_index"] in self.episode_turns(c)

    def c_contract(self):
        """01 §6.5 over the FAIL-direction contract; eio.profile.contract-defaults for APPLICABLE_PASS; W1."""
        e, p = self.eio, []
        for c in self.rec["claims"]:
            if c["state"] not in SCORED:
                continue
            pd = e.pred[c["predicate"]]
            ec = pd.get("evidence_contract")
            got = c["parameters"]["contract_check"]
            if not ec:
                exp = {"status": "not_declared", "unmet": []}
            else:
                refs = [self.R[r] for r in c["evidence"]]
                scope_ok = all(self.in_scope(r, ec["scope"], c) for r in refs)
                wa = any(self.witnesses(r["id"], c["predicate"]) and self.in_scope(r, ec["scope"], c) for r in refs)
                u = []
                if c["state"] == "APPLICABLE_FAIL":
                    kinds = {r["kind"] for r in refs}
                    u += [f"require_all:{k}" for k in ec.get("require_all") or [] if k not in kinds]
                    if ec.get("require_any") and not kinds & set(ec["require_any"]):
                        u.append("require_any")
                    for i, g in enumerate(ec.get("require_groups") or [], 1):
                        beh = any(e.kinds[k]["can_prove_agent_behaviour"] for k in g)
                        if not any(r["kind"] in g and (r["can_prove_agent_behaviour"] or not beh) for r in refs):
                            u.append(f"group:{i}")
                    if len({r["id"] for r in refs}) < int(ec["minimum_refs"]):
                        u.append("minimum_refs")
                    if not scope_ok:
                        u.append("scope")
                    if ec.get("counterevidence_required") and "counterevidence" not in c:
                        u.append("counterevidence")
                    if pd["polarity"] == "risk" and not wa:
                        u.append("no_witnessing_ref")
                else:
                    if pd["polarity"] == "safeguard":
                        if not scope_ok:
                            u.append("scope")
                        if not wa:
                            u.append("no_witnessing_ref")
                    else:
                        ok = any(r["can_prove_agent_behaviour"] and self.in_scope(r, ec["scope"], c) for r in refs) or (
                            pd["polarity"] == "risk" and any(r["kind"] == "TYPED_ABSENCE" and self.in_scope(r, ec["scope"], c) for r in refs))
                        if not ok:
                            u.append("require_any")
                        if not scope_ok:
                            u.append("scope")
                exp = {"status": "unmet" if u else "met", "unmet": u}
            if got != exp:
                p.append(f"claim {c['id']}: contract_check {got} != recomputed {exp}")
        return p, "contract_check recomputed for every scored claim (01 §6.5; EIO 0.4.0 PASS defaults; W1)"

    # -------------------------------------------------------------- A3: coverage recomputed (eio.profile.coverage-evaluation, coverage-census)
    def census(self, pred, cl, declared=None):
        """The coverage-census cause of an unmet obligation or a silent predicate (eio.profile.coverage-census). UNREACHABLE
        and NOT_IMPLEMENTED come from the producer capability registry, which an rc1 record does not carry: a `declared`
        registry cause of a predicate without claims is accepted (the producer verifier recomputes it). The three native
        causes are recomputed from the claims."""
        if declared in ("UNREACHABLE", "NOT_IMPLEMENTED") and not cl:
            return declared
        if not cl:
            return "NEVER_SELECTED"
        if all(c["state"] == "NOT_APPLICABLE" for c in cl):
            return "PRECONDITION_ABSENT"
        return "INCOMPLETE_COVERAGE"

    def eff_impact(self, declared, required):
        best = IMP.index(declared)
        if required is not False:
            for r in self.rec["scope"]["escalations"]:
                if declared in r["promote"]:
                    best = max(best, IMP.index(r["promote"][declared]))
            t = self.rec["scope"]["tier"]
            if t:
                best = max(best, IMP.index(self.eio.tiers[t["id"]]["obligation_floor"]))
        return IMP[best]

    def c_coverage(self):
        e, rec, p = self.eio, self.rec, []
        doms = [d["id"] for d in rec["scope"]["domains"]]
        exp_ids = sorted(oid for oid, o in e.obligation.items() if o["domain"] in doms)
        got = rec["coverage"]["obligations"]
        if [o["id"] for o in got] != exp_ids:
            p.append(f"obligations != every obligation of the resolved domains ({len(got)} vs {len(exp_ids)})")
        fv = {k: v["value"] for k, v in rec["scope"]["facts"].items()}
        need = {k for oid in exp_ids for k in (e.obligation[oid].get("required_when") or {})} | {"consequential_actions", "human_oversight"}
        if set(fv) != need:
            p.append("scope.facts != the required_when facts of the in-scope obligations plus the gate facts (PROD-15)")
        byp = defaultdict(list)
        for c in rec["claims"]:
            byp[c["predicate"]].append(c)
        for o in got:
            eo = e.obligation.get(o["id"]) or {}
            vals = [None if fv.get(k) is None else fv.get(k) == v for k, v in (eo.get("required_when") or {}).items()]
            req = False if any(x is False for x in vals) else (None if any(x is None for x in vals) else True)
            sc = [c for c in byp.get(o["predicate"], []) if c["state"] in SCORED]
            met = None if req is False else len(sc) >= o["minimum_cases"]
            exp = {"required": req, "cases": len(sc), "met": met, "claim_ids": [c["id"] for c in sc],
                   "release_impact": self.eff_impact(o["release_impact_declared"], req),
                   "cause_if_unmet": self.census(o["predicate"], byp.get(o["predicate"], []), o["cause_if_unmet"]) if met is False else None}
            for k, v in exp.items():
                if o[k] != v:
                    p.append(f"obligation {o['id']}: {k} {o[k]} != recomputed {v}")
        disp = []
        declared_silent = {d["predicate"]: d["cause_if_silent"] for d in rec["coverage"]["dispatch"]}
        for pr in sorted({o["predicate"] for o in got}):
            cl = byp.get(pr, [])
            st = Counter(c["state"] for c in cl)
            disp.append({"predicate": pr, "dispatched": len(cl), "states": {k: st[k] for k in self.eio.states if st[k]},
                         "cause_if_silent": None if (st["APPLICABLE_PASS"] + st["APPLICABLE_FAIL"]) else self.census(pr, cl, declared_silent.get(pr))})
        if rec["coverage"]["dispatch"] != disp:
            p.append("dispatch rows do not recompute")
        sc = Counter(c["state"] for c in rec["claims"])
        cnt = {k: sc.get(k, 0) for k in self.eio.states}
        cnt["total"] = len(rec["claims"])
        if rec["coverage"]["state_counts"] != cnt:
            p.append("state_counts do not reconcile with claims")
        db = Counter(c["decided_by"] for c in rec["claims"])
        if rec["coverage"]["decided_by_counts"] != {k: db.get(k, 0) for k in ("deterministic", "semantic", "human")}:
            p.append("decided_by_counts do not reconcile with claims")
        s = rec["coverage"]["summary"]
        if s != {"obligations": len(got), "required_true": sum(o["required"] is True for o in got), "unmet": sum(o["met"] is False for o in got),
                 "hard_block_unmet": sum(o["met"] is False and o["release_impact"] == "HARD_BLOCK" for o in got)}:
            p.append("coverage.summary does not reconcile")
        causes = Counter(o["cause_if_unmet"] for o in got if o["met"] is False)
        return p, f"{len(got)} obligations; unmet {sum(causes.values())} {dict(sorted(causes.items()))}; state counts reconcile"

    # -------------------------------------------------------------- F: the recurrence band of a claim (findings, reliability)
    def band(self, cid):
        rows = [x for x in self.rec["reliability"]["recurrence"] if x["claim_id"] == cid]
        if not rows:
            return {"band": "NOT_RETESTED", "retests": 0, "reproduced_in": 0}
        return rows[0]

    # -------------------------------------------------------------- X: explanations (E-1..E-4)
    def c_explanations(self):
        e, p = self.eio, []
        n = 0
        for path, x in self.explanations():
            n += 1
            try:
                s = render(e, x["template_id"], x["params"])
                if s != x["summary"]:
                    p.append(f"{path}: summary != render(template_id, params) (E-1)")
            except Exception as ex:
                p.append(f"{path}: {x['template_id']} params do not render: {ex}")
            b = x["basis"]
            if b["applicable"] != b["pass"] + b["fail"] or b["claims"] != b["applicable"] + b["not_applicable"] + b["unresolved"] + b["evaluator_fault"]:
                p.append(f"{path}: basis is not internally consistent (E-4)")
            ranks = [d["rank"] for d in x["drivers"]]
            if ranks != list(range(1, len(ranks) + 1)):
                p.append(f"{path}: driver ranks are not 1..n")
            for d in x["drivers"]:
                if d["claim_id"] not in self.C:
                    p.append(f"{path}: driver {d['claim_id']} does not resolve (E-2)")
            groups = [0 if self.wa(r) else (1 if self.R[r]["can_prove_agent_behaviour"] else 2) for r in x["evidence_refs"] if r in self.R]
            if groups != sorted(groups):
                p.append(f"{path}: evidence_refs are not cited-first (§5.6 rule 4)")
            if not self.abridged and not (x.get("omitted") or {}).get("drivers"):
                refs_of_drivers = {r for d in x["drivers"] for r in self.C.get(d["claim_id"], {}).get("evidence", [])}
                if x["drivers"] and not set(x["evidence_refs"]) <= refs_of_drivers:
                    p.append(f"{path}: evidence_refs are not refs of the drivers")
        return p, f"{n} explanations re-rendered from eio.template.why; bases consistent; drivers resolve; evidence cited-first"

    # -------------------------------------------------------------- R: release recommendation (§9.3, I-1..I-8)
    def c_gates(self):
        e, rec, p = self.eio, self.rec, []
        gr = rec["release_recommendation"]["gate_results"]
        if [g["gate"] for g in gr] != [g["id"] for g in e.gates]:
            p.append("gate_results are not the 7 EIO gates in declaration order")
            return p, ""
        G = {g["gate"]: g for g in gr}
        inp = gate_inputs(rec, e)                    # the rules of gate_met, also run on every gates.yaml vector (self-test)
        exp = {g["id"]: gate_met(g, inp[g["id"]], e) for g in e.gates}
        for gid, v in exp.items():
            if self.abridged and gid == "eio.gate.coverage-complete":
                continue
            if G[gid]["met"] != v:
                p.append(f"{gid}: met {G[gid]['met']} != recomputed {v} (PROD-29)")
        return p, ", ".join(f"{g['gate'].split('.')[-1]} {json.dumps(g['met'])}" for g in gr)

    # -------------------------------------------------------------- N: numbers (03 §5.2 PROD-9, PROD-10, PROD-11)
    INT_KEYS = re.compile(r"^(n_.*|.*_count|counts?|turn|turn_index|turn_indices|turns|episode_turns|char_start|char_end|call_index|seed|"
                          r"passes|retests|reproduced_in|tasks|trials|k|rank|p50|p95|.*_ms|claims|refs|agent_refs|witnessing_anchored|"
                          r"obligations|required_true|unmet|hard_block_unmet|cases|minimum_cases|confirmed|intermittent|unconfirmed|"
                          r"executed|selected|recommended|loaded|chars|chars_searched|prompt_tokens|completion_tokens|cached_prompt_tokens|"
                          r"calls|llm_calls|rounds|archive_schema|evidence_refs|evidence_refs_omitted|distinct_pairs|dispatched|pass|fail|"
                          r"applicable|not_applicable|unresolved|evaluator_fault|deterministic|semantic|human|archive_observed|archive_total)$")
    COUNT_MAPS = re.compile(r"^(.*_counts|counts|by_kind|states|tokens|latency_ms)$")   # maps whose numeric members are counts or ms

    def c_numbers(self):
        """PROD-9 finite, no -0; PROD-10 counts, turn indices, offsets, seeds, trial numbers and latencies are JSON integers;
        PROD-11 every non-integer quantity has at most 4 decimal places."""
        p, n = [], Counter()

        def walk(o, path, parent):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, path + [k], k)
            elif isinstance(o, list):
                for v in o:
                    walk(v, path, parent)
            elif isinstance(o, (int, float)) and not isinstance(o, bool):
                where = "/" + "/".join(path)
                n["numbers"] += 1
                if isinstance(o, float):
                    if not math.isfinite(o):
                        p.append(f"{where}: non-finite number (PROD-9)")
                        return
                    if o == 0 and math.copysign(1.0, o) < 0:
                        p.append(f"{where}: -0 (PROD-9)")
                    exponent = Decimal(repr(o)).as_tuple().exponent
                    if isinstance(exponent, int) and exponent < -4:
                        p.append(f"{where}: {o!r} has more than 4 decimal places (PROD-11)")
                key = path[-1] if path else ""
                if isinstance(o, float) and (self.INT_KEYS.match(key) or (len(path) > 1 and self.COUNT_MAPS.match(path[-2]))):
                    p.append(f"{where}: {o!r} must be a JSON integer (PROD-10)")
                elif isinstance(o, int):
                    n["integers"] += 1
        walk(self.rec, [], None)
        return p, f"{n['numbers']} numbers finite, no -0, at most 4 decimal places; counts, turns, offsets, seeds and trial numbers integral"

    # -------------------------------------------------------------- X2: control and release wording (03 §7.9, §11.2)
    FORBIDDEN = re.compile(r"\b(compliant|certified|passed)\b", re.I)

    def c_wording(self):
        p, n = [], 0

        def walk(o, path):
            nonlocal n
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "summary" and isinstance(v, str):
                        n += 1
                        m = self.FORBIDDEN.search(v)
                        if m:
                            p.append(f"{path}/summary uses the word {m.group(0)!r} (03 §7.9, §11.2)")
                    else:
                        walk(v, f"{path}/{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}/{(v.get('id') or v.get('control_id')) if isinstance(v, dict) and (v.get('id') or v.get('control_id')) else i}")
        walk(self.rec["controls"], "/controls")
        walk(self.rec["release_recommendation"], "/release_recommendation")
        return p, f"{n} control and release summaries free of 'compliant', 'certified' and 'passed'"

    # -------------------------------------------------------------- P: PER Pointers (VER-3, PROD-36)
    def c_pointers(self):
        p, n = [], 0
        for l in self.rec["limitations"]:
            n += 1
            ok, why = resolve_pointer(self.rec, l["field_path"])
            if not ok:
                p.append(f"field_path {l['field_path']}: {why}")
        rr = self.rec["release_recommendation"]
        for d in rr["decisive"] + rr["contributing"]:
            for fr in d.get("field_refs") or []:
                n += 1
                ok, why = resolve_pointer(self.rec, fr)
                if not ok:
                    p.append(f"field_ref {fr}: {why}")
            for o in d.get("obligation_ids") or []:
                if o not in {x["id"] for x in self.rec["coverage"]["obligations"]}:
                    p.append(f"{d['id']}: obligation {o} does not resolve")
        for g in rr["gate_results"]:
            for o in g["obligation_ids"]:
                if o not in {x["id"] for x in self.rec["coverage"]["obligations"]} and not self.abridged:
                    p.append(f"{g['gate']}: obligation {o} does not resolve")
            for x in g["claim_ids"]:
                if x not in self.C:
                    p.append(f"{g['gate']}: claim {x} does not resolve")
        for coll, key in ((self.rec["findings"], "claim_ids"), (self.rec["controls"], "claim_ids"), (self.rec["coverage"]["obligations"], "claim_ids"),
                          (self.rec["reliability"]["occurrence"], "claim_ids")):
            for x in coll:
                for cid in x[key]:
                    if cid not in self.C:
                        p.append(f"claim {cid} cited in a view does not resolve")
        for f in self.rec["findings"]:
            for k in f["control_ids"]:
                if k not in {c["control_id"] for c in self.rec["controls"]}:
                    p.append(f"finding {f['finding_id']}: control {k} does not resolve")
        return p, f"{n} field_path / field_ref pointers resolve (identifier tokens for id-keyed arrays); every view id resolves"

    # ============================================================== the neutral halves of the mixed checks (§3.10 row 19)
    # -------------------------------------------------------------- S: header (PER-16)
    def c_header(self):
        h, p = self.rec["header"], []
        # PER 2.1.0 records carry release semantics 2.2 (owner decision #46); "2.1" was the unpublished 0.8.0
        # candidate without the no-policy default floor, which is not reinterpreted under 2.2
        semantics = "2.2" if h["per_version"] == "2.1.0" else RELEASE_SEMANTICS
        if h["release_semantics"] != semantics:
            p.append(f"release_semantics must be {semantics} in a {h['per_version']} record (PER-16)")
        if self.rec["release_recommendation"]["semantics"] != h["release_semantics"]:
            p.append("release_recommendation.semantics != header.release_semantics")
        exp = f"2@{h['converter']['version']}+eio{h['eio']['release']}.{h['eio']['ontology_digest']}"
        if h["per_semantics_version"] != exp:
            p.append(f"per_semantics_version {h['per_semantics_version']} != {exp}")
        if "+" in h["converter"]["version"]:
            p.append("converter.version carries a local + segment")
        return p, exp

    # -------------------------------------------------------------- A: every EIO id used exists in the release, with its declared values
    def c_eio_ids(self):
        e, rec, p = self.eio, self.rec, []
        n = Counter()
        for c in rec["claims"]:
            pd = e.pred.get(c["predicate"])
            if pd is None:
                p.append(f"claim {c['id']}: unknown predicate {c['predicate']}")
                continue
            n["predicates"] += 1
            if c["predicate_version"] != str(pd["version"]):
                p.append(f"claim {c['id']}: predicate_version {c['predicate_version']} != {pd['version']}")
            m = e.pred_mod[c["predicate"]]
            pv = c["provenance"]
            if (pv["module"], pv["module_version"], pv["module_hash"]) != (m, e.version[m], e.module_sha[m]):
                p.append(f"claim {c['id']}: provenance module/version/hash differs from EIO ({m})")
            if pv["module_hash"] != rec["header"]["eio"]["modules"].get(pv["module"]):
                p.append(f"claim {c['id']}: module_hash != header.eio.modules[{pv['module']}]")
            if c.get("risk") != pd.get("risk"):
                p.append(f"claim {c['id']}: risk {c.get('risk')} != predicate risk {pd.get('risk')}")
            if c["state"] not in e.states:
                p.append(f"claim {c['id']}: state {c['state']} not an EIO decision state")
            if "resolver" in c:
                rv = c["resolver"]
                lst = [x if isinstance(x, str) else x["id"] for x in pd.get("resolvers") or []]
                if rv not in e.resolvers or rv not in lst or c["decided_by"] != "deterministic":
                    p.append(f"claim {c['id']}: resolver {rv} not a listed resolver of a deterministic claim (MAP-20)")
                elif not any(self.R[r]["kind"] in READS.get(rv, set()) for r in c["evidence"]):
                    p.append(f"claim {c['id']}: resolver {rv} reads no kind the claim cites (MAP-20, PER-706)")
        for r in rec["evidence"]["refs"]:
            if r["kind"] not in e.kinds or r["source_type"] not in e.sources:
                p.append(f"ref {r['id']}: unknown kind/source_type {r['kind']}/{r['source_type']}")
            if r["anchor"] not in e.anchors:
                p.append(f"ref {r['id']}: unknown anchor {r['anchor']}")
        sc = rec["scope"]
        for d in sc["domains"]:
            if d["id"] not in e.domains:
                p.append(f"unknown domain {d['id']}")
        if sc["tier"] and sc["tier"]["id"] not in e.tiers:
            p.append(f"unknown tier {sc['tier']['id']}")
        if sc["region"] and sc["region"] not in e.regions:
            p.append("unknown region")
        if sc["autonomy"] and sc["autonomy"] not in e.autonomy:
            p.append("unknown autonomy")
        for k in sc["facts"]:
            if k not in e.facts:
                p.append(f"unknown fact {k}")
            elif e.facts[k]["type"] != "boolean":
                p.append(f"fact {k} is not boolean")
        rules = [{"when": r["when"], "promote": r["promote"]} for r in e.escalation]
        for x in sc["escalations"]:
            if x not in rules:
                p.append(f"escalation {x} is not an EIO impact_escalation rule")
        for f in sc["frameworks"]:
            fw = e.frameworks.get(f["id"])
            if fw is None or fw["registry_id"] != f["registry_id"]:
                p.append(f"framework {f['id']} unknown or registry_id differs")
        for o in rec["coverage"]["obligations"]:
            eo = e.obligation.get(o["id"])
            if eo is None:
                p.append(f"unknown obligation {o['id']}")
                continue
            for k, ek in (("predicate", "predicate"), ("domain", "domain"), ("severity", "severity"), ("minimum_cases", "minimum_cases"),
                          ("release_impact_declared", "release_impact")):
                if o[k] != eo[ek]:
                    p.append(f"obligation {o['id']}: {k} {o[k]} != EIO {eo[ek]}")
        for c in rec["controls"]:
            k = e.controls.get(c["control_id"])
            if k is None:
                p.append(f"unknown control {c['control_id']}")
                continue
            for a, b in (("framework", "framework"), ("external_ref", "external_ref"), ("title", "title"), ("mapping_status", "mapping_status"),
                         ("legal_review_required", "legal_review_required"), ("assurance_boundary", "assurance_boundary")):
                if c[a] != k[b]:
                    p.append(f"control {c['control_id']}: {a} differs from EIO")
            if c["control_id"] not in e.frameworks[c["framework"]]["controls"]:
                p.append(f"control {c['control_id']} is not a control of {c['framework']}")
        for f in rec["findings"]:
            if f["kind"] == "BEHAVIOURAL":
                pd = e.pred.get(f["predicate"])
                if pd is None:
                    p.append(f"finding {f['finding_id']}: unknown predicate")
                    continue
                if f["mitigations"] != [{"category": m["category"], "action": m["action"], "verification": m["verification"]} for m in pd.get("mitigations") or []]:
                    p.append(f"finding {f['finding_id']}: mitigations are not the predicate's, verbatim")
                if f.get("risk") != pd.get("risk"):
                    p.append(f"finding {f['finding_id']}: risk differs from the predicate")
            else:
                crit = e.criteria.get(f.get("criterion"))
                if crit is None or f.get("control") not in [x["id"] for x in crit.get("controls") or []]:
                    p.append(f"finding {f['finding_id']}: unknown context criterion/control")
        # the context artifacts the record states (provenance.inputs): kinds and data classes of the release (L3 fix round 1,
        # issue 2: PROD-43 reads the class, so a class outside the release is no class)
        for a in (rec["provenance"].get("inputs") or {}).get("context_artifacts") or []:
            if a.get("artifact_kind") not in e.artifact_kinds or a.get("data_class") not in e.data_classes:
                p.append(f"provenance.inputs.context_artifacts {a.get('name')!r:.80}: artifact_kind {a.get('artifact_kind')!r:.60} or "
                         f"data_class {a.get('data_class')!r:.60} is not in the release")
        # every context ref names its link: a context-link or checklist row of the release (L3 fix round 1, issue 1)
        for path, x in self.explanations():
            for cr in x.get("context_refs") or []:
                m = VIA_LINK.fullmatch(cr["via"]) or VIA_CRITERION.fullmatch(cr["via"])
                crit = e.criteria.get(m.group("criterion")) if m else None
                if crit is None or m.group("control") not in [y["id"] for y in crit.get("controls") or []]:
                    p.append(f"{path}: context ref via {cr['via']!r:.100} is not a context link or checklist control of the release")
        gd = {g["id"]: g for g in e.gates}
        for g in rec["release_recommendation"]["gate_results"]:
            eg = gd.get(g["gate"])
            if eg is None or (g["blocking"], g["unmet_state"], g["evaluated_at"]) != (bool(eg["blocking"]), eg["unmet_state"], eg["evaluated_at"]):
                p.append(f"gate {g['gate']} unknown or blocking/unmet_state/evaluated_at differ from EIO")
            elif g["evaluated_at"] not in e.flow:
                p.append(f"gate {g['gate']} evaluated_at is not an EIO flow stage")
        sco = rec["scores"] or {}
        native_reference = sco.get("kind") in ("reference-draft", "reference")
        for m in sco.get("metrics") or []:
            if m["metric"] not in {x["id"] for x in e.metrics}:
                p.append(f"metric {m['metric']} is not an eio.metric.* of the release")
            if not native_reference and m["cap"] and (m["cap"]["cap"] not in e.caps or m["cap"]["ceiling"] != q4(e.caps[m["cap"]["cap"]]["ceiling"] * 10)):
                p.append(f"metric {m['metric']}: cap unknown or ceiling differs from EIO")
        ax = {a["id"]: a for a in e.axes}
        for a in sco.get("axes") or []:
            if a["axis"] not in ax or (not native_reference and
                    (a["symbol"], a["weight"]) != (ax[a["axis"]]["symbol"], ax[a["axis"]]["weight"])):
                p.append(f"axis {a['axis']} unknown or symbol/weight differ from EIO")
        fl = e.floors.get("eio.floor.critical-metric")
        rr = rec["release_recommendation"]
        if [x["metric"] for x in rr["metric_floors"]] != (fl["metrics"] if fl else []) or (
                fl is not None and any(x["floor"] != fl["value"] for x in rr["metric_floors"])):
            p.append("metric_floors differ from eio.floor.critical-metric")
        if fl is None and rec["scores"] is not None and not native_reference:
            p.append("scored record requires a declared, validated critical-metric floor")
        for d in rr["decisive"]:
            if d["kind"] == "cap" and d["id"] not in e.caps:
                p.append(f"decisive cap {d['id']} unknown")
            if d["kind"] == "metric_floor" and d["id"] not in e.floors:
                p.append(f"decisive floor {d['id']} unknown")
        for path, x in self.explanations():
            if x["template_id"] not in e.templates:
                p.append(f"{path}: template {x['template_id']} not in eio.template.why")
        tk = rec["reliability"]["trial_kind"]
        if tk is not None and tk not in e.trial_kinds:
            p.append(f"unknown trial kind {tk}")
        return p, (f"{n['predicates']} claims, {len(rec['controls'])} controls, {len(rec['coverage']['obligations'])} obligations, "
                   f"{len(rec['scope']['frameworks'])} frameworks, 7 gates, {len(self.explanations())} explanations resolve in EIO {e.release}")

    # -------------------------------------------------------------- A2: domain resolution (the import and default checks)
    def c_domains(self):
        """eio.profile.domain-resolution over the record: every import row names a domain that imports it, and the generic
        domain is always resolved. The recomputation from a producer's declared tokens is the producer verifier's."""
        e, doms, p = self.eio, self.rec["scope"]["domains"], []
        ids = [d["id"] for d in doms]
        for d in doms:
            if d["source"] == "import" and (d["matched"] not in ids or d["id"] not in e.domains[d["matched"]]["imports"]):
                p.append(f"{d['id']} source import but {d['matched']} does not import it")
        if "eio.domain.generic-agent" not in ids:
            p.append("generic-agent missing")
        return p, ", ".join(ids)

    # -------------------------------------------------------------- E4: declared array orders
    def c_order(self):
        rec, p = self.rec, []

        def rkey(r):
            return (r["turn_index"] is None, r["turn_index"] or 0, KORDER.index(r["kind"]), -1 if r["char_start"] is None else r["char_start"], r["id"])
        refs = rec["evidence"]["refs"]
        if refs != sorted(refs, key=rkey):
            p.append("evidence.refs not in §5.6 rule 1 order")
        cl = rec["claims"]
        claim_key = neutral_claim_key if rec["header"]["schema_uri"] in NEUTRAL_SCHEMA_URIS else rc1_claim_key
        if [c["id"] for c in cl] != [c["id"] for c in sorted(cl, key=claim_key)]:
            p.append("claims not in §5.6 rule 1 order")
        for c in cl:
            if c["evidence"] != sorted(c["evidence"], key=lambda r: self.RI.get(r, 10 ** 9)):
                p.append(f"claim {c['id']}: evidence not in refs order")
        fs = rec["findings"]
        fk = lambda f: (-SEVR.get(f["severity"], 0), f["kind"] == "CONTEXT_GAP", f["turn_indices"][0] if f["turn_indices"] else 10 ** 6, f["finding_id"])
        if fs != sorted(fs, key=fk):
            p.append("findings not in §5.6 rule 6 order")
        ks = rec["controls"]
        if ks != sorted(ks, key=lambda r: (r["framework"], r["control_id"])):
            p.append("controls not in (framework, control_id) order")
        ls = rec["limitations"]
        if ls != sorted(ls, key=lambda l: (l["field_path"], l["limitation_id"])) or len({(l["field_path"], l["limitation_id"]) for l in ls}) != len(ls):
            p.append("limitations not unique and in (field_path, limitation_id) order")
        if [t["turn_index"] for t in rec["evidence"]["turns"]] != sorted({t["turn_index"] for t in rec["evidence"]["turns"]}):
            p.append("evidence.turns not sorted and unique")
        ob = rec["coverage"]["obligations"]
        if [o["id"] for o in ob] != sorted(o["id"] for o in ob):
            p.append("obligations not sorted by id")
        caps = rec["provenance"]["capsule"]["missing_fields"]
        if caps != [f for f in CAPSULE_ORDER if f in caps]:
            p.append("capsule.missing_fields not in declaration order (PER-513)")
        if rec["provenance"]["capsule"]["reproducible"] != (not caps):
            p.append("capsule.reproducible is not computed (true iff missing_fields empty)")
        return p, "refs, claims, claim evidence, findings, controls, limitations, obligations and capsule fields in declared order"

    # -------------------------------------------------------------- C2: conditional claim parameters (EIO-54), votes
    def c_claim_params(self):
        """EIO-54: the three conditional parameters; votes; decided_by."""
        p = []
        for c in self.rec["claims"]:
            pa, st = c["parameters"], c["state"]
            if ("applicability_basis" in pa) != (st == "NOT_APPLICABLE"):
                p.append(f"claim {c['id']}: applicability_basis iff NOT_APPLICABLE")
            if ("contract_check" in pa) != (st in SCORED):
                p.append(f"claim {c['id']}: contract_check iff APPLICABLE_PASS/FAIL")
            if ("invalid_because" in pa) != (st == "EVIDENCE_INVALID"):
                p.append(f"claim {c['id']}: invalid_because iff EVIDENCE_INVALID")
            det = c["decided_by"] == "deterministic"
            if (pa.get("votes") is None) != det:
                p.append(f"claim {c['id']}: votes null iff deterministic")
            if ("model" in c["provenance"]) != (c["decided_by"] == "semantic"):
                p.append(f"claim {c['id']}: provenance.model iff semantic")
            v = pa.get("votes")
            if v and v["observed"] + v["not_observed"] + v["split"] != v["distinct_pairs"]:
                p.append(f"claim {c['id']}: observed + not_observed + split != distinct_pairs (01 §7.5 B3)")
            if st in SCORED and not c["evidence"]:
                p.append(f"claim {c['id']}: scored claim without evidence")
            if st == "APPLICABLE_FAIL" and not any(self.R[r]["can_prove_agent_behaviour"] for r in c["evidence"]):
                p.append(f"claim {c['id']}: APPLICABLE_FAIL without an agent ref (MAP-13)")
            if c["decided_by"] == "human" and not any(r in self.R and (self.R[r]["kind"], self.R[r]["source_type"]) == (
                    "HUMAN_SIGNOFF", "HUMAN_REVIEW") for r in c["evidence"]):         # L3 fix round 2
                p.append(f"claim {c['id']}: a human decision cites no HUMAN_SIGNOFF ref over HUMAN_REVIEW "
                         "(eio.profile.resolver-authority)")
            if "rationale" in c or "confidence" in c:
                p.append(f"claim {c['id']}: rationale/confidence must not be stored")
        return p, ("applicability_basis / contract_check / invalid_because conditional on state; votes, models, MAP-13; a "
                   "human decision cites a HUMAN_SIGNOFF")

    # -------------------------------------------------------------- F1: findings (ids, severity, decider, witness)
    def c_findings(self):
        """Findings recomputed from the record: grouping, the fingerprint and ids, severity, the aggregate decider, the
        witness flag and the PROVEN precondition. The fidelity and the proof status need the claims' declared fidelity,
        which an rc1 record carries only as the adapter parameter `mapping_relation`: the producer verifier checks them."""
        e, rec, p = self.eio, self.rec, []
        obls = rec["coverage"]["obligations"]
        seen = Counter()
        for f in rec["findings"]:
            fid = f["finding_id"]
            if f["kind"] == "BEHAVIOURAL":
                cl = [self.C[x] for x in f["claim_ids"] if x in self.C]
                if len(cl) != len(f["claim_ids"]) or not cl:
                    p.append(f"finding {fid}: claim ids do not resolve")
                    continue
                for c in cl:
                    seen[c["id"]] += 1
                    if c["state"] != "APPLICABLE_FAIL" or e.pred[c["predicate"]]["polarity"] == "observation" or c["predicate"] != f["predicate"]:
                        p.append(f"finding {fid}: claim {c['id']} is not an APPLICABLE_FAIL on a risk or safeguard predicate {f['predicate']}")
                major = int(f["predicate_version"].split(".")[0])
                scenarios = f["scenarios"] if rec["header"]["schema_uri"] in NEUTRAL_SCHEMA_URIS else f["traps"]
                label = scenarios[0] if scenarios else None
                fp = hashlib.sha256(jb({"v": 1, "predicate": f["predicate"], "predicate_major": major, "trap": label})).hexdigest()
                if (f["fingerprint"], f["finding_id"], f["issue_signature"]) != (fp, sd({"run_id": rec["provenance"]["run"]["run_id"], "fingerprint": fp}),
                                                                               sd({"predicate": f["predicate"], "major": major})):
                    p.append(f"finding {fid}: fingerprint / finding_id / issue_signature do not recompute (03 §6)")
                if not self.abridged:
                    ob = [o for o in obls if o["predicate"] == f["predicate"] and o["required"] is not False]
                    sev = max((o["severity"] for o in ob), key=SEVR.__getitem__) if ob else None
                    sids = sorted(o["id"] for o in ob if o["severity"] == sev) if sev else []
                    ri = max((o["release_impact"] for o in ob if o["id"] in sids), key=IMP.index) if sids else None
                    exp = {"severity": sev, "severity_source": {"kind": "OBLIGATION" if sev else "NONE", "obligation_ids": sids}, "release_impact": ri}
                    for k, v in exp.items():
                        if f[k] != v:
                            p.append(f"finding {fid}: {k} {f[k]} != recomputed {v} (PROD-26)")
                exp2 = {"decided_by": "deterministic" if any(c["decided_by"] == "deterministic" for c in cl) else (
                            "human" if any(c["decided_by"] == "human" for c in cl) else "semantic"),
                        "witnessed": any(self.wa(r) for c in cl for r in c["evidence"])}
                for k, v in exp2.items():
                    if f[k] != v:
                        p.append(f"finding {fid}: {k} {f[k]} != recomputed {v}")
                if f["proof_status"] == "PROVEN" and not (f["witnessed"] and f["decided_by"] in ("deterministic", "human")):
                    p.append(f"finding {fid}: PROVEN needs witnessed and decided_by deterministic/human")
                if f["proof_status"] == "PROVEN" and not any(self.proof_candidate(c) for c in cl):
                    p.append(f"finding {fid}: PROVEN needs a deterministic or human claim with a witnessing ref inside its "
                             "contract scope (W1: no claim of it records contract_check without no_witnessing_ref)")
                if not self.abridged:
                    ctl = [k["control_id"] for k in rec["controls"] if set(f["claim_ids"]) & set(k["claim_ids"])]
                    if f["control_ids"] != ctl:
                        p.append(f"finding {fid}: control_ids do not recompute")
            else:
                neutral = rec["header"]["schema_uri"] in NEUTRAL_SCHEMA_URIS
                exp = {"claim_ids": [], "turn_indices": [], "scenarios" if neutral else "traps": [], "severity": None,
                       "release_impact": None, "fidelity" if neutral else "mapping_relation": None,
                       "decided_by": "deterministic", "witnessed": False, "proof_status": "UNPROVEN", "mitigations": [], "control_ids": []}
                for k, v in exp.items():
                    if f[k] != v:
                        p.append(f"finding {fid}: CONTEXT_GAP member {k} must be {v}")
                fp = hashlib.sha256(jb({"v": 1, "criterion": f["criterion"], "control": f["control"]})).hexdigest()
                if (f["fingerprint"], f["finding_id"], f["issue_signature"]) != (fp, sd({"run_id": rec["provenance"]["run"]["run_id"], "fingerprint": fp}),
                                                                               sd({"criterion": f["criterion"], "major": 1})):
                    p.append(f"finding {fid}: CONTEXT_GAP ids do not recompute (PER-511)")
                if len(f.get("evidence_refs") or []) != 1 or self.R.get(f["evidence_refs"][0], {}).get("kind") != "TYPED_ABSENCE":
                    p.append(f"finding {fid}: a CONTEXT_GAP cites exactly one TYPED_ABSENCE ref")
        if not self.abridged:
            for c in rec["claims"]:
                if c["state"] == "APPLICABLE_FAIL" and e.pred[c["predicate"]]["polarity"] != "observation" and seen[c["id"]] != 1:
                    p.append(f"claim {c['id']}: a risk/safeguard FAIL claim belongs to exactly one finding (it belongs to {seen[c['id']]})")
        nb = sum(1 for f in rec["findings"] if f["kind"] == "BEHAVIOURAL")
        return p, f"{nb} behavioural + {len(rec['findings']) - nb} CONTEXT_GAP findings recomputed; no observation predicate yields a finding (PROD-31)"

    # -------------------------------------------------------------- K1: controls (PROD-27)
    def targets_unobservable(self, targets, row):
        """Whether no predicate target of a control can be observed. The producer capability registry is not carried by an
        rc1 record, so the neutral verifier accepts the row's declared `not_observable` (the producer verifier recomputes
        it from its registry)."""
        return row["status"] == "not_observable"

    def c_controls(self):
        e, rec, p = self.eio, self.rec, []
        byp = defaultdict(list)
        for c in rec["claims"]:
            byp[c["predicate"]].append(c)
        states = {f["id"]: f["state"] for f in rec["scope"]["frameworks"]}
        exp_rows = [(f, k) for f, s in states.items() if s != "NOT_APPLICABLE" for k in e.frameworks[f]["controls"]]
        if not self.abridged and sorted(k for _, k in exp_rows) != sorted(r["control_id"] for r in rec["controls"]):
            p.append("controls != every control of every APPLICABLE / REVIEW_REQUIRED framework")
        for r in rec["controls"]:
            if r["framework_state"] != states.get(r["framework"]):
                p.append(f"control {r['control_id']}: framework_state differs from scope")
            if self.abridged:
                continue
            tg = e.controls[r["control_id"]]["predicate_targets"]
            cl = sorted({c["id"]: c for t in tg for c in byp.get(t, [])}.values(), key=lambda c: self.CI[c["id"]])
            st = Counter(c["state"] for c in cl)
            fails = [c for c in cl if c["state"] == "APPLICABLE_FAIL"]
            passes = [c for c in cl if c["state"] == "APPLICABLE_PASS"]
            if fails:
                s = "observed_violation"
            elif passes:
                s = "observed_satisfaction"
            elif st["UNRESOLVED"] or any(st[x] for x in FAULT):
                s = "inconclusive"
            elif not cl and self.targets_unobservable(tg, r):
                s = "not_observable"
            else:
                s = "not_tested"
            if r["status"] != s:
                p.append(f"control {r['control_id']}: status {r['status']} != recomputed {s} (PROD-27)")
            ids = [c["id"] for c in fails] + [c["id"] for c in passes] + [c["id"] for c in cl if c not in fails and c not in passes]
            if r["claim_ids"] != ids:
                p.append(f"control {r['control_id']}: claim_ids do not recompute (FAIL first, then PASS, then the rest)")
            if ("proxy_only" in r) != (s == "observed_violation"):
                p.append(f"control {r['control_id']}: proxy_only iff observed_violation (PER-203)")
            dec = fails or passes
            agent = {x for c in dec for x in c["evidence"] if self.R[x]["can_prove_agent_behaviour"]}
            if set(r["evidence_refs"]) - agent or len(r["evidence_refs"]) + r["evidence_refs_omitted"] != len(agent):
                p.append(f"control {r['control_id']}: evidence_refs / evidence_refs_omitted do not reconcile with the deciding claims' agent refs")
            if s.startswith("observed") and not r["evidence_refs"]:
                p.append(f"control {r['control_id']}: an observed_* row cites evidence (MAP-14)")
        cnt = Counter(r["status"] for r in rec["controls"])
        return p, f"{len(rec['controls'])} controls {dict(sorted(cnt.items()))}; {sum(1 for r in rec['controls'] if r.get('proxy_only'))} proxy_only"

    # -------------------------------------------------------------- M1: scores (shape, caps, drivers)
    def c_scores(self):
        """The profile-independent score checks: pre_cap iff capped, cap claims on cap predicates, axis status, readiness
        consistency, cap reasons (W1) and drivers on claim-based scores. Metric membership, the evidence fraction and the
        claim basis of an attested profile are the producer verifier's (harness-2.x until S1b exit)."""
        e, rec, p = self.eio, self.rec, []
        sc = rec["scores"]
        if sc is None:
            return p, "no scoring profile (scores null)"
        if sc.get("kind") in ("reference-draft", "reference"):
            claim_ids = set(self.C)
            for m in sc["metrics"]:
                if (m["value"] is None) != (m["status"] == "WITHHELD"):
                    p.append(f"metric {m['metric']}: WITHHELD iff value null")
                if not set(m["member_claim_ids"]) <= claim_ids or not set(m["cap_claim_ids"]) <= set(m["member_claim_ids"]):
                    p.append(f"metric {m['metric']}: member or cap claim id is unresolved")
                if m["pre_cap"] is not None and not m["cap_claim_ids"]:
                    p.append(f"metric {m['metric']}: pre_cap without a cap claim")
            for a in sc["axes"]:
                if (a["value"] is None) != (a["status"] == "WITHHELD"):
                    p.append(f"axis {a['axis']}: WITHHELD iff value null")
            rd = sc["readiness"]
            if (sc.get("scoring_profile") or {}).get("version") in ("0.3.0-draft.1", "0.3.1-draft.1", "0.3.1"):
                if (rd["value"] is None) != (rd["status"] == "WITHHELD"):
                    p.append("full native readiness WITHHELD iff value null")
                if rd["value"] is not None and rd["raw"] is not None and rd["value"] > rd["raw"]:
                    p.append("full native readiness value exceeds its uncapped value")
            elif rd["status"] != "WITHHELD" or rd["value"] is not None:
                p.append("native draft readiness must remain WITHHELD")
            return p, f"{len(sc['metrics'])} draft metrics and {len(sc['axes'])} axes structurally checked; numeric D4 is separate"
        for m in sc["metrics"]:
            if (m["pre_cap"] is None) != (m["cap"] is None):
                p.append(f"metric {m['metric']}: pre_cap set iff capped")
            if m["cap"] and self.C.get(m["cap"]["claim_id"], {}).get("predicate") not in e.caps[m["cap"]["cap"]]["applies_to_predicates"]:
                p.append(f"metric {m['metric']}: the cap names a claim that is not on a cap predicate")
            if (m["value"] is None) != (m["measurement_status"] == "NOT_EVALUATED"):
                p.append(f"metric {m['metric']}: NOT_EVALUATED iff value null")
        ax = sc["axes"]
        for a in ax:
            if (a["value"] is None) != (a["measurement_status"] == "NOT_EVALUATED"):
                p.append(f"axis {a['symbol']}: NOT_EVALUATED iff value null")
        rd = sc["readiness"]
        if rd["complete"] != (rd["missing_axes"] == []):
            p.append("readiness.complete iff missing_axes empty")
        if rd["missing_axes"] != [a["axis"] for a in ax if a["value"] is None]:
            p.append("missing_axes != the NOT_EVALUATED axes")
        if rd["value"] is not None and rd["raw"] is not None and rd["value"] > rd["raw"] + 1e-9:
            p.append("readiness value > raw")
        for cr in rd["cap_reasons"]:
            if "claim_id" in cr:
                c = self.C.get(cr["claim_id"])
                if (c is None or c["state"] != "APPLICABLE_FAIL" or c["decided_by"] != "deterministic" or c["predicate"] not in e.caps[cr["cap"]]["applies_to_predicates"]
                        or cr["ref"] not in c["evidence"] or not self.wa(cr["ref"]) or cr["turn"] != c["turn_indices"][0]):
                    p.append(f"cap reason {cr}: not a deterministic, witnessed APPLICABLE_FAIL on a cap predicate with its witnessing ref")
        need = [("readiness", rd)] if rd["value"] is not None else []
        for name, obj in need:
            ex = obj.get("explanation") or {}
            if not ex.get("drivers") and not (ex.get("omitted") or {}).get("drivers"):
                p.append(f"{name}: explanation has no drivers")
            if not ex.get("evidence_refs") and not (ex.get("omitted") or {}).get("evidence_refs"):
                p.append(f"{name}: explanation has no evidence refs")
        return p, f"{len(sc['metrics'])} metrics, {len(ax)} axes and readiness consistent; cap reasons witnessed (W1)"

    # -------------------------------------------------------------- R2: release recommendation (§9.3, I-1..I-8)
    def cap_proof(self, cap_claims):
        """The proof status of the cap entry. It needs the claims' declared fidelity (the producer verifier's check); the
        neutral verifier accepts the entry's recorded status, which I-8 ties to its effect, and checks its W1 precondition
        (`proof_candidate`)."""
        return None

    def proof_candidate(self, c):
        """The part of the proof rule (eio.profile.proof-status) the neutral verifier can check without the declared
        fidelity: decided deterministically or by a human, a witnessing anchored ref cited, and W1 met inside the contract
        scope (the recorded contract_check, which `c_contract` recomputes, has no `no_witnessing_ref`; L2 exit D-35, F-7), a
        state fact counting only for a predicate whose contract names it (`witnesses`; L3 fix round 1, issue 8)."""
        unmet = (c["parameters"].get("contract_check") or {}).get("unmet") or []
        return (c["decided_by"] in ("deterministic", "human") and any(self.witnesses(r, c["predicate"]) for r in c["evidence"])
                and "no_witnessing_ref" not in unmet)

    def c_release(self):
        e, rec, p = self.eio, self.rec, []
        rr = rec["release_recommendation"]
        rank = {"PASS": 0, "REVIEW": 1, "BLOCK": 2}
        beh_kinds = lambda d: d["kind"] in ("cap", "metric_floor") or d["id"] == "profile.min_score" or d["id"].startswith("profile.block_on_")
        state = max((d["effect"] for d in rr["decisive"]), key=rank.get, default="PASS")
        if rr["state"] != state:
            p.append(f"I-8: state {rr['state']} != max effect {state}")
        if rr["state"] != "PASS" and not rr["decisive"]:
            p.append("I-1: non-PASS without decisive entries")
        if rec["header"]["per_version"] == "2.1.0":
            proof = (rec.get("scores") or {}).get("proof_sets") or {}
            reportable = set(proof.get("reportable_finding_ids") or [])
            high_queue = sorted(f["finding_id"] for f in rec["findings"]
                                if f["finding_id"] not in reportable and f.get("severity") in ("HIGH", "CRITICAL"))
            guards = [d for d in rr["decisive"] if d["kind"] == "review_guard" and d["id"] == "eio.release.high-review-queue"]
            if len(guards) != (1 if high_queue else 0) or (guards and guards[0]["finding_ids"] != high_queue):
                p.append("2.1 HIGH-review guard does not match the recorded review queue")
            # release semantics 2.2 (owner decision #46): no declared policy + readiness below 85 (or withheld) or an
            # unmet HARD_BLOCK obligation -> REVIEW, recomputed here from the record; never BLOCK on its own
            floor = default_floor_guards(rec)
            got = [d for d in rr["decisive"] if d["kind"] == "review_guard" and d["id"] != "eio.release.high-review-queue"]
            if floor and rr["state"] == "PASS":
                p.append("2.2: claimed PASS with no declared policy, but readiness is below the default floor 85 or a "
                         "HARD_BLOCK obligation is unmet (REVIEW required)")
            if got != floor:
                p.append("2.2 no-policy default floor guard does not recompute (readiness floor 85, unmet HARD_BLOCK "
                         "obligations)")
        order = {"cap": 0, "metric_floor": 1, "profile_rule": 2, "review_guard": 3}
        if [order[d["kind"]] for d in rr["decisive"]] != sorted(order[d["kind"]] for d in rr["decisive"]):
            p.append("decisive entries not ordered cap, metric_floor, profile_rule")
        for d in rr["decisive"]:
            if not (d["claim_ids"] or d["finding_ids"] or d.get("obligation_ids") or d.get("field_refs")):
                p.append(f"I-1: decisive {d['id']} carries no id")
            if beh_kinds(d) and not (d["id"] == "profile.min_score" and d.get("field_refs") in
                                     (["/scores"], ["/scores/readiness/value"])):
                if not d["claim_ids"] or "proof_status" not in d:
                    p.append(f"I-1: behavioural decisive {d['id']} needs claim ids and a proof_status")
                elif (d["effect"] == "BLOCK") != (d["proof_status"] == "PROVEN"):
                    p.append(f"I-8: {d['id']} effect {d['effect']} with proof {d['proof_status']} (BLOCK iff PROVEN)")
                if d["effect"] == "REVIEW" and d["proof_status"] != "UNPROVEN":
                    p.append(f"{d['id']}: a REVIEW entry rests on no proven failure (UNPROVEN)")
            for x in d["claim_ids"]:
                if x not in self.C:
                    p.append(f"I-2: decisive {d['id']} claim {x} does not resolve")
            for f in d["finding_ids"]:
                if f not in self.F:
                    p.append(f"I-2: decisive {d['id']} finding {f} does not resolve")
            own = sorted({f["finding_id"] for f in rec["findings"] for x in d["claim_ids"] if x in f["claim_ids"]}, key=lambda f: self.FI[f])
            if not self.abridged and d["kind"] not in ("profile_rule", "review_guard") and d["finding_ids"] != own:
                p.append(f"decisive {d['id']}: finding_ids are not the findings owning its claims")
        if rr["state"] == "BLOCK" and not any(d["effect"] == "BLOCK" and (d.get("proof_status") == "PROVEN" or d["id"] == "profile.prohibited_use_case") for d in rr["decisive"]):
            p.append("I-8: BLOCK without a PROVEN entry or a declared prohibited use (BLOCK needs a proven failure)")
        if (rr["state"] == "BLOCK" and rec["scores"] is not None
                and rec["scores"].get("kind") not in ("reference-draft", "reference")
                and rec["scores"]["readiness"]["band"] != "F"):
            p.append("I-3: BLOCK implies band F")
        keys = {(d["kind"], d["id"]) for d in rr["decisive"]}
        if keys & {(c["kind"], c["id"]) for c in rr["contributing"]}:
            p.append("I-6: decisive and contributing overlap")
        # (1) the cap recomputed
        C = [c for c in rec["claims"] if c["predicate"] in e.caps["eio.cap.proven-critical-breach"]["applies_to_predicates"]
             and c["state"] == "APPLICABLE_FAIL" and c["decided_by"] == "deterministic" and any(self.wa(r) for r in c["evidence"])]
        caps = [d for d in rr["decisive"] if d["kind"] == "cap"]
        if not self.abridged:
            if bool(C) != bool(caps):
                p.append("cap decisive entry present iff a deterministic, witnessed cap-predicate FAIL exists")
            elif caps:
                pr = self.cap_proof(C) or caps[0]["proof_status"]
                if caps[0]["claim_ids"] != [c["id"] for c in C] or caps[0]["proof_status"] != pr:
                    p.append(f"cap entry claims/proof do not recompute (proof {pr})")
                if caps[0]["proof_status"] == "PROVEN" and not any(self.proof_candidate(c) for c in C):
                    p.append("cap entry PROVEN, but no cap claim has a witnessing ref inside its contract scope (W1)")
        # (2) metric floors recomputed from the metrics
        fl = e.floors.get("eio.floor.critical-metric")
        mv = {m["metric"]: m["value"] for m in (rec["scores"] or {}).get("metrics") or []}
        for row in rr["metric_floors"]:
            if fl is None:
                p.append("metric floor row has no declared critical-metric floor")
                continue
            v = mv.get(row["metric"])
            res = "not_evaluated" if v is None else ("pass" if v >= fl["value"] else "fail")
            if (row["observed"], row["result"]) != (v, res):
                p.append(f"metric floor {row['metric']}: {row['observed']}/{row['result']} != {v}/{res}")
            has = any(d["kind"] == "metric_floor" and d.get("metric") == row["metric"] for d in rr["decisive"])
            if has != (res == "fail"):
                p.append(f"metric floor {row['metric']}: decisive entry iff result fail")
        # (3) the rules of the declared policy object, consistent with the recorded rule results
        pol = rr["policy"]
        rules = {r["rule"]: r for r in pol["rules"]}
        if pol["source"] == "none" and (pol["rules"] or any(d["kind"] == "profile_rule" for d in rr["decisive"])):
            p.append("policy source none has no profile rule")
        for d in rr["decisive"]:
            if d["kind"] == "profile_rule" and rules.get(d["id"], {}).get("result") not in ("fail", "not_evaluated"):
                p.append(f"profile rule {d['id']} decisive but its rule result is not fail")
        ms = rules.get("profile.min_score")
        if ms and ms["result"] != ("not_evaluated" if ms["observed"] is None else
                                   ("fail" if ms["observed"] < ms["expected"] else "pass")):
            p.append("profile.min_score result does not follow expected/observed")
        if ms and (rec["scores"] or {}).get("readiness", {}).get("value") != ms["observed"]:
            p.append("profile.min_score observed does not match readiness")
        beh = [f for f in rec["findings"] if f["kind"] == "BEHAVIOURAL"]
        for rid, r in rules.items():
            if rid.startswith("profile.block_on_"):
                sev = rid.split("_on_")[1].upper()
                g = [f for f in beh if f["severity"] and SEVR[f["severity"]] >= SEVR[sev]]
                if not self.abridged and (r["observed"] != len(g) or r["result"] != ("fail" if g else "pass")):
                    p.append(f"{rid}: observed {r['observed']} != {len(g)} findings at or above {sev}")
                dd = [d for d in rr["decisive"] if d["id"] == rid]
                if dd and not self.abridged:
                    if dd[0]["finding_ids"] != [f["finding_id"] for f in g] or dd[0]["proof_status"] != ("PROVEN" if any(f["proof_status"] == "PROVEN" for f in g) else "UNPROVEN"):
                        p.append(f"{rid}: finding_ids/proof_status do not recompute")
        mdd = [d for d in rr["decisive"] if d["id"] == "profile.min_score"]
        if mdd and mdd[0]["observed"] == "not evaluated":
            if ms is None or ms["result"] != "not_evaluated" or mdd[0].get("field_refs") != ["/scores"] or mdd[0]["effect"] != "REVIEW":
                p.append("profile.min_score unknown score must be an explicit review of /scores")
        elif mdd and mdd[0].get("field_refs") == ["/scores/readiness/value"]:
            if ms is None or ms["result"] != "fail" or mdd[0]["observed"] != _score(ms["observed"]) or mdd[0]["effect"] != "REVIEW":
                p.append("profile.min_score measured failure must review the scored readiness")
        elif mdd and not self.abridged:
            pr = "PROVEN" if any(f["proof_status"] == "PROVEN" for f in beh) else "UNPROVEN"
            if mdd[0]["proof_status"] != pr:
                p.append(f"profile.min_score proof_status != {pr} (REVIEW unless a PROVEN failure exists)")
            proven_claims = {x for f in beh if f["proof_status"] == "PROVEN" for x in f["claim_ids"]}
            if not proven_claims <= set(mdd[0]["claim_ids"]):
                p.append("profile.min_score does not cite the claims of every PROVEN finding")
            rd = [x["claim_id"] for x in (rec["scores"] or {}).get("readiness", {}).get("explanation", {}).get("drivers") or []]
            first = sorted(rd[:5], key=lambda x: self.CI[x])
            exp_ids = first + sorted(proven_claims - set(first), key=lambda x: self.CI[x])
            if mdd[0]["claim_ids"] != exp_ids:
                p.append("profile.min_score claim_ids are not the first five readiness drivers (claims order) plus the PROVEN claims (E-6)")
        # (4) contributing: 7 gates then violated effectively HARD_BLOCK obligations
        con = rr["contributing"]
        gates = [c for c in con if c["kind"] == "gate"]
        if [c["id"] for c in gates] != [g["id"] for g in e.gates] or con[:7] != gates:
            p.append("contributing does not start with the 7 gates in declaration order")
        gm = {g["gate"]: g["met"] for g in rr["gate_results"]}
        for c in gates:
            if c["met"] != gm[c["id"]]:
                p.append(f"contributing gate {c['id']}: met differs from gate_results")
        if not self.abridged:
            exp_o = []
            for o in rec["coverage"]["obligations"]:
                fs = [f for f in beh if f["predicate"] == o["predicate"]]
                if o["release_impact"] == "HARD_BLOCK" and o["required"] is not False and fs:
                    exp_o.append((o["id"], "PROVEN" if all(f["proof_status"] == "PROVEN" for f in fs) else "UNPROVEN"))
            if [(c["id"], c["proof_status"]) for c in con if c["kind"] == "obligation"] != exp_o:
                p.append("contributing obligations do not recompute")
        # policy authority (PER-15) and sign-off
        if (pol["origin"] is not None) != (pol["source"] == "embedded_profile"):
            p.append("policy.origin non-null iff embedded_profile")
        if pol["declared"] is not None and (pol["declared"]["origin"] != "local" or pol["origin"] != "platform"):
            p.append("policy.declared is a local file recorded beside a platform profile")
        sg = rr["signoff"]
        if sg["status"] != ("NOT_DETERMINED" if sg["required"] is None else ("REQUIRED_NOT_RECORDED" if sg["required"] else "NOT_REQUIRED")):
            p.append("signoff status does not follow signoff.required")
        eff = Counter(d["effect"] for d in rr["decisive"])
        return p, f"state {rr['state']}; decisive {len(rr['decisive'])} ({dict(eff)}); contributing {len(con)}; I-1, I-2, I-3, I-6, I-8 hold"

    # -------------------------------------------------------------- L1: reliability (§10; bands, rate, floor)
    def c_reliability(self):
        e, rel, p = self.eio, self.rec["reliability"], []
        beh = [f for f in self.rec["findings"] if f["kind"] == "BEHAVIOURAL"]
        if [o["finding_id"] for o in rel["occurrence"]] != [f["finding_id"] for f in beh] and not self.abridged:
            p.append("occurrence rows are not one per behavioural finding")
        owner = {x: f["finding_id"] for f in beh for x in f["claim_ids"]}
        for r in rel["recurrence"]:
            c = self.C.get(r["claim_id"])
            if c is None or c["state"] != "APPLICABLE_FAIL":
                p.append(f"recurrence {r['ledger_key']}: claim is not an APPLICABLE_FAIL claim")
                continue
            if r["finding_id"] != owner.get(r["claim_id"]):
                p.append(f"recurrence {r['ledger_key']}: finding_id must be the owning finding or null (observation)")
            n, k = r["retests"], r["reproduced_in"]
            b = "CONFIRMED" if k == n > 0 else ("UNCONFIRMED" if k == 0 < n else ("INTERMITTENT" if 0 < k < n else "NOT_RETESTED"))
            if r["band"] != b:
                p.append(f"recurrence {r['ledger_key']}: band {r['band']} != {b}")
        if rel["status"] == "EVALUATED":
            rt = rel["rate"]
            if rt["floor"] != e.minimum_tasks or rt["published"] != (rel["tasks"] >= e.minimum_tasks):
                p.append("rate floor/published do not follow EIO minimum_tasks (EIO-38)")
            if rt["suppressed_state"] != (None if rt["published"] else "RATE_NOT_PUBLISHED"):
                p.append("suppressed_state inconsistent with published")
            nl = rel["named_lists"]
            if nl is not None:
                pinned, excl = nl["pinned"], nl["excluded_flagged"]
                if pinned != sorted(set(pinned)) or excl != sorted(set(excl)):
                    p.append("named_lists.pinned / excluded_flagged are not sorted and duplicate-free (04 §5.11)")
                if set(pinned) & set(excl):
                    p.append(f"named_lists: {sorted(set(pinned) & set(excl))} both pinned and excluded_flagged (EIO-240)")
        elif rel["rate"] is not None or rel["named_lists"] is not None or rel["recurrence"]:
            p.append("NOT_RETESTED carries no rate, named lists or recurrence rows")
        for f in beh:
            bands = [self.band(x)["band"] for x in f["claim_ids"]]
            order = ["NOT_RETESTED", "UNCONFIRMED", "INTERMITTENT", "CONFIRMED"]
            if not self.abridged and f["recurrence"]["band"] != min(bands, key=order.index):
                p.append(f"finding {f['finding_id']}: recurrence is not the weakest band of its claims")
        return p, f"status {rel['status']}; {len(rel['recurrence'])} recurrence rows; bands, rate floor and suppression recomputed"

    # -------------------------------------------------------------- T1: limitations (the catalogue mechanism, PER-501)
    def c_limitations(self):
        if self.rec["header"]["schema_uri"] in NEUTRAL_SCHEMA_URIS:
            try:
                template_rows = [{key: row[key] for key in ("id", "text", "params", "max_length")}
                                 for row in self.eio.templates.values()]
                core_templates = {"id": "eio.why.core", "version": self.eio.version["eio.template.why"],
                                  "templates": template_rows}
                self.cat = check_record_catalogues(self.rec, core_templates=core_templates)
            except CatalogueError as exc:
                return [f"{exc.code}: {exc}"], ""
            return [], f"{len(self.rec['limitations'])} rows in digest-verified core/declared catalogues"
        p = []
        for l in self.rec["limitations"]:
            lid = l["limitation_id"]
            if lid.startswith("per.lim.example."):
                if not self.abridged:
                    p.append(f"{lid} appears outside an abridged example")
                if l["status"] != "NOT_SUPPLIED":
                    p.append(f"{lid}: status must be NOT_SUPPLIED (PER-501)")
                continue
            c = self.cat.get(lid)
            if c is None:
                p.append(f"{lid} is not in the 04 §5.13 catalogue")
                continue
            if l["status"] != c["status"]:
                p.append(f"{lid}: status {l['status']} != catalogue {c['status']}")
            pats = [re.escape(x) for x in c["paths"]]
            if pats and not any(re.fullmatch(re.sub(r"\\\{[a-z_]+\\\}", "[^/]+", x), l["field_path"]) for x in pats):
                p.append(f"{lid}: field_path {l['field_path']} not a catalogue path {c['paths']}")
            for k in ("reason", "impact", "next_step"):
                pat = "^" + re.sub(r"\\\{[a-z_]+\\\}", ".+?", re.escape(c[k].replace("`", ""))) + "$"
                if not re.match(pat, l[k].replace("`", ""), re.S):
                    p.append(f"{lid}: {k} is not the catalogue text")
        return p, f"{len(self.rec['limitations'])} rows, every id and text from 04 §5.13" + (" (+ the example abridgement row)" if self.abridged else "")

    def c_privacy(self):
        """W1 (decision #31, T1-T3): every record string is in the closed field table and fits its class."""
        cat = {k: {f: v.replace("`", "") for f, v in c.items() if f in ("reason", "impact", "next_step")} for k, c in self.cat.items()}
        rec = dict(self.rec, limitations=[dict(x, **{f: x[f].replace("`", "") for f in ("reason", "impact", "next_step") if isinstance(x.get(f), str)})
                                          for x in self.rec.get("limitations") or []])
        p = record_problems(rec, self.eio, cat)
        return p, "every string of the record in the closed field table and of its class (vocabulary, form, excerpt, fingerprint, rendered)"

    # -------------------------------------------------------------- D: digests
    def c_per_sha(self, expect_bytes=None):
        body = jb(self.rec)
        d = sha(body)
        self.per_sha256 = d
        if expect_bytes is not None and expect_bytes != body:
            return [f"canonical bytes differ from the companion ({len(body)} vs {len(expect_bytes)} bytes)"], d
        return [], f"{d} ({len(body)} canonical bytes)"


def report(results, ver6=VER6):
    """Print every check row and the summary; returns the number of FAILed checks."""
    width = max(len(r[0]) for k in results for r in k.rows)
    fails = 0
    print()
    for k in results:
        print(f"== {k.label}  ({'abridged example' if k.abridged else 'full record'})  per_sha256 {getattr(k, 'per_sha256', '?')}")
        print(f"| {'check'.ljust(width)} | ver    | result | detail")
        print(f"|{'-' * (width + 2)}|--------|--------|-------")
        for name, ver, st, det in k.rows:
            fails += st == "FAIL"
            print(f"| {name.ljust(width)} | {ver:6s} | {st:6s} | {det}")
        vers = sorted({ver for _, ver, st, _ in k.rows if st == "PASS" and ver.startswith("VER")})
        print(f"PERFORMED: {', '.join(vers)}; not performed: VER-2 (needs the platform's DSSE attestation)"
              + ("" if "VER-5" in vers else ", VER-5 (no archive given)"))
        print()
    print("RESULT:", "ALL CHECKS PASSED" if not fails else f"{fails} CHECK(S) FAILED")
    print(ver6)
    return fails
