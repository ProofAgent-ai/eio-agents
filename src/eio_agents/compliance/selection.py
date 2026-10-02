"""Framework selection (eio.profile.framework-selection): the region framework sets and the selection rule.

It reads the bundle `scope.frameworks` declaration: the producer's framework candidates `{id, basis}` (in declaration
order), whether personal data is processed, and the rule to apply. How a producer names its candidates (a governance
profile, a run selection, an archive's assessed frameworks) is the producer's (adapter's) part (split plan §3.10 row 6).

Rules:
- `selection`: the region's framework sets are candidates too; an AI regulation applies in a declared jurisdiction, a
  privacy regulation also needs personal data (and, when sector-bound, a declared domain of its sector), a sector
  regulation needs a declared domain of its sector; every other candidate is REVIEW_REQUIRED.
- `assessed`: every candidate is REVIEW_REQUIRED (the producer declares only what it assessed; no jurisdiction or sector
  is known), with its basis entries as declared.
"""
from collections import defaultdict

from eio_agents.base.errors import require


def select_frameworks(eio, declared, region, domains_declared):
    """The scope's framework rows `{id, registry_id, state, basis}`, sorted by id."""
    rule = declared["rule"]
    require(rule in ("selection", "assessed"), "BUNDLE_SCOPE", f"framework rule {rule!r}")
    basis = defaultdict(list)
    for c in declared["candidates"]:
        require(c["id"] in eio.frameworks, "BUNDLE_SCOPE", f"unknown framework candidate {c['id']}")
    if rule == "assessed":
        for c in declared["candidates"]:
            basis[c["id"]].append(c["basis"])
        return sorted([{"id": fid, "registry_id": eio.frameworks[fid]["registry_id"], "state": "REVIEW_REQUIRED", "basis": b}
                       for fid, b in basis.items()], key=lambda x: x["id"])
    sel = eio.profiles["eio.profile.framework-selection"]
    if region:
        for reg in eio.regions[region].get("framework_sets") or []:
            if reg in eio.fw_of_registry:
                basis[eio.fw_of_registry[reg]].append(f"framework set of {region}")
    for c in declared["candidates"]:
        basis[c["id"]].append(c["basis"])
    juris = set(sel["region_jurisdictions"].get(region) or []) if region else set()
    resolved_declared = set(domains_declared)
    personal = bool(declared["personal_data"])
    res = []
    for fid, b in basis.items():
        fw = eio.frameworks[fid]
        cat, reg = fw.get("category"), fw["registry_id"]
        in_j = bool(juris & set(fw.get("jurisdictions") or []))
        sector = sel["sector_domains"].get(reg)
        if cat == "ai-regulation":
            ok = in_j
        elif cat == "privacy-regulation":
            ok = in_j and personal and (not sector or bool(set(sector) & resolved_declared))
        elif cat == "sector-regulation":
            ok = in_j and bool(set(sector or []) & resolved_declared)
        else:
            ok = False
        res.append({"id": fid, "registry_id": reg, "state": "APPLICABLE" if ok else "REVIEW_REQUIRED",
                    "basis": sorted(dict.fromkeys(b))})
    return sorted(res, key=lambda x: x["id"])
