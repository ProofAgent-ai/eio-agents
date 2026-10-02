"""Record-only discovery and proof navigation; never reads a bundle or local source."""
from __future__ import annotations

import re
import math
from difflib import SequenceMatcher
from typing import Any


AXES = {"Q": "Context", "E": "Behaviour", "C": "Compliance", "G": "Governance"}
AXIS_SYMBOLS = {"eio.axis.context": "Q", "eio.axis.behaviour": "E",
                "eio.axis.compliance": "C", "eio.axis.governance": "G"}


def _rc4_score(rec: dict[str, Any]) -> bool:
    score = rec.get("scores") or {}
    profile = score.get("scoring_profile") or {}
    # The rc5 policy wire retains the same record-only score explanation
    # shape. Do not strand measured axes/metrics merely because policy rules
    # were versioned separately from the score block.
    return (rec.get("header", {}).get("per_version") in
            ("2.0.0-rc4-draft", "2.0.0-rc5-policy-draft", "2.0.0")
            and score.get("kind") == "reference-draft"
            and profile.get("version") in ("0.3.0-draft.1", "0.3.1-draft.1"))


def _public_number(value: Any) -> int | float | None:
    """Never render arbitrary text from an invalid score row as a value."""
    return value if type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value) else None


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def targets(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Every explainable target in stable PER order, with only PER or fixed labels."""
    out: list[dict[str, Any]] = []

    def add(node: Any, key: str, label: str, kind: str) -> None:
        if isinstance(node, dict) and (isinstance(node.get("explanation"), dict)
                                       or (_rc4_score(rec) and kind in {"readiness", "axis", "metric"})):
            item = {"id": key, "label": label, "value": node.get("value", node.get("state")), "kind": kind}
            if _rc4_score(rec) and kind in {"readiness", "axis", "metric"}:
                item["value"] = _public_number(node.get("value"))
                item.update(status=node.get("status"), withheld_code=node.get("withheld_code"),
                            withheld_codes=node.get("withheld_codes"))
            out.append(item)

    scores = rec.get("scores") or {}
    add(scores.get("readiness"), "readiness", "Readiness", "readiness")
    for axis in scores.get("axes") or []:
        symbol = axis.get("symbol") or AXIS_SYMBOLS.get(axis.get("axis"), "")
        add(axis, axis.get("axis", ""), f"{AXES.get(symbol, symbol)} ({symbol})", "axis")
    for metric in scores.get("metrics") or []:
        key = metric.get("metric", "")
        add(metric, key, key.removeprefix("eio.metric.").replace("-", " ").title(), "metric")
    for finding in rec.get("findings") or []:
        add(finding, finding.get("finding_id", ""), finding.get("display_label", ""), "finding")
    for control in rec.get("controls") or []:
        add(control, control.get("control_id", ""), control.get("control_id", ""), "control")
    release = rec.get("release_recommendation") or {}
    for gate in release.get("gate_results") or []:
        add(gate, gate.get("gate", ""), gate.get("gate", ""), "gate")
    add(release, "release_recommendation", "Release recommendation", "release")
    return out


def _aliases(item: dict[str, Any]) -> set[str]:
    key, kind = item["id"], item["kind"]
    words = {_norm(key), _norm(item["label"])}
    if kind == "metric":
        stem = key.removeprefix("eio.metric.")
        words |= {_norm(stem), _norm(stem.replace("-resistance", ""))}
    elif kind == "axis":
        words |= {_norm(key.removeprefix("eio.axis.")), _norm(item["label"].split(" (")[0])}
        words.add(_norm(item["label"].rsplit("(", 1)[-1].rstrip(")")))
    elif kind == "readiness":
        words |= {"score", "overall score", "scores readiness"}
    elif kind == "release":
        words |= {"release", "decision", "recommendation"}
    elif kind == "finding":
        words.add(_norm(item["label"].split(" · ", 1)[0]))
    return {word for word in words if word}


def resolve_target(rec: dict[str, Any], target: str, *, kind: str | None = None) -> str:
    """Resolve an exact id/label or unambiguous alias; suggest but never auto-pick typos."""
    items = [item for item in targets(rec) if kind is None or item["kind"] == kind]
    for item in items:
        if target == item["id"] or target == item["label"]:
            return item["id"]
    query = _norm(target)
    exact = [item for item in items if query in _aliases(item)]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(exact) > 1:
        ids = ", ".join(item["id"] for item in exact)
        raise LookupError(f"{target}: ambiguous target; use an exact id: {ids}")
    ranked = sorted(
        ((max(SequenceMatcher(None, query, alias).ratio() for alias in _aliases(item)), item["id"])
         for item in items),
        key=lambda pair: (-pair[0], pair[1]),
    )
    suggestions = [key for score, key in ranked[:3] if score >= 0.4]
    suffix = f"; did you mean: {', '.join(suggestions)}" if suggestions else ""
    raise LookupError(f"{target}: no explanation for this target in the record{suffix}")


def metric_card(rec: dict[str, Any], target: str) -> dict[str, Any]:
    """Metric card using the PER's existing score basis and ranked drivers."""
    key = resolve_target(rec, target, kind="metric")
    metric = next(row for row in (rec.get("scores") or {}).get("metrics") or [] if row.get("metric") == key)
    if _rc4_score(rec) and "explanation" not in metric:
        members = metric.get("member_claim_ids") or []
        claims = {row.get("id"): row for row in rec.get("claims") or []}
        selected = [claims.get(cid) for cid in members]
        passed = sum(isinstance(row, dict) and row.get("state") == "APPLICABLE_PASS" for row in selected)
        failed = sum(isinstance(row, dict) and row.get("state") == "APPLICABLE_FAIL" for row in selected)
        turns = sorted({turn for row in selected if isinstance(row, dict)
                        for turn in row.get("turn_indices") or [] if type(turn) is int and turn >= 0})
        return {"id": key, "label": key.removeprefix("eio.metric.").replace("-", " ").title(),
                "value": _public_number(metric.get("value")), "status": metric.get("status"),
                "withheld_code": metric.get("withheld_code"), "member_count": len(members),
                "applicable": passed + failed, "passed": passed, "failed": failed,
                "other": len(members) - passed - failed, "excluded": len(members) - passed - failed,
                "turns": turns, "cap_claim_count": len(metric.get("cap_claim_ids") or []),
                "primary_failures": [], "source": "rc4"}
    basis = metric["explanation"].get("basis") or {}
    claims = {row.get("id"): row for row in rec.get("claims") or []}
    findings = {cid: finding for finding in rec.get("findings") or [] for cid in finding.get("claim_ids") or []}
    failures = []
    for driver in metric["explanation"].get("drivers") or []:
        cid = driver.get("claim_id")
        claim = claims.get(cid) or {}
        if claim.get("state") != "APPLICABLE_FAIL":
            continue
        finding = findings.get(cid) or {}
        failures.append({"claim_id": cid, "turn": (claim.get("turn_indices") or [None])[0],
                         "finding_id": finding.get("finding_id"), "label": finding.get("display_label"),
                         "severity": finding.get("severity")})
    return {"id": key, "label": key.removeprefix("eio.metric.").replace("-", " ").title(),
            "value": metric.get("value"), "applicable": basis.get("applicable", 0),
            "passed": basis.get("pass", 0), "failed": basis.get("fail", 0),
            "excluded": basis.get("not_applicable", 0) + basis.get("evaluator_fault", 0),
            "primary_failures": failures[:3]}


def finding_evidence(rec: dict[str, Any], target: str) -> dict[str, Any]:
    """Only the finding's cited PER refs and fields already supplied in that PER."""
    key = resolve_target(rec, target, kind="finding")
    finding = next(row for row in rec.get("findings") or [] if row.get("finding_id") == key)
    refs = {row.get("id"): row for row in (rec.get("evidence") or {}).get("refs") or []}
    cited = []
    for ref_id in (finding.get("explanation") or {}).get("evidence_refs") or []:
        ref = refs.get(ref_id)
        if ref is None:
            continue
        cited.append({"id": ref_id, "kind": ref.get("kind"), "turn": ref.get("turn_index"),
                      "excerpt": ref.get("excerpt"), "tool": ref.get("tool"),
                      "source_ref": ref.get("source_ref"), "span_sha256": ref.get("span_sha256")})
    return {"finding_id": key, "label": finding.get("display_label"), "proof_status": finding.get("proof_status"),
            "severity": finding.get("severity"), "refs": cited}


def findings_at_turn(rec: dict[str, Any], label: str) -> list[dict[str, Any]]:
    """All findings with an exact tNN display-label prefix, in PER order."""
    if not re.fullmatch(r"t\d+", label):
        raise LookupError(f"{label}: not a turn label (expected t01, t02, …)")
    matches = [row for row in rec.get("findings") or []
               if str(row.get("display_label", "")).startswith(label + " · ")]
    if not matches:
        raise LookupError(f"{label}: no finding at this turn")
    return [finding_evidence(rec, row["finding_id"]) for row in matches]
