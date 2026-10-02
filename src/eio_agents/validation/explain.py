"""`explain(rec, target)`: the "why" of a score, metric, axis, finding, control or the release recommendation, as the
record's registered `eio.why.*` renderings only (split plan §4.2).

It reads only the record and the release's template catalogue (`eio.template.why`). Each explanation of the target is
rendered from its `template_id` and `params` by the verifier's own renderer; nothing else is printed (no hard-coded
lines, no values read from fields the template does not name). A target that is not in the record, or an explanation
whose template is not registered in the loaded release, raises `LookupError`.
"""
from __future__ import annotations

from typing import Any

from eio_agents.validation.explore import AXIS_SYMBOLS, _public_number, _rc4_score, metric_card, resolve_target
from eio_agents.validation.privacy import FP, bundle_texts
from eio_agents.validation.reader import EIO, EIO_DIR
from eio_agents.validation.render import render


def _node(rec: dict[str, Any], target: str):
    sc = rec.get("scores") or {}
    if target in ("readiness", "scores.readiness"):
        return sc.get("readiness")
    for a in sc.get("axes") or []:
        if target in (a.get("axis"), a.get("symbol")):
            return a
    for m in sc.get("metrics") or []:
        if target == m.get("metric"):
            return m
    for f in rec.get("findings") or []:
        if target in (f.get("finding_id"), f.get("display_label")):
            return f
    for c in rec.get("controls") or []:
        if target == c.get("control_id"):
            return c
    for g in (rec.get("release_recommendation") or {}).get("gate_results") or []:
        if target == g.get("gate"):
            return g
    if target == "release_recommendation":
        return rec.get("release_recommendation")
    return None


def _clear(v, texts):
    """A parameter value with each fingerprint replaced by its text in the local bundle (display only, never stored)."""
    if isinstance(v, str) and FP.fullmatch(v) and texts.get(v):
        return texts[v][0][1]
    if isinstance(v, list):
        return [_clear(x, texts) for x in v]
    if isinstance(v, dict):
        return {k: _clear(x, texts) for k, x in v.items()}
    return v


_WITHHELD_REASONS = {
    "NO_APPLICABLE_CLAIM": "no applicable decided claim",
    "SCENARIO_BINDING_ABSENT": "native scenario binding is absent",
    "SCENARIO_SEVERITY_ABSENT": "scenario severity is absent",
    "TOOLS_NOT_USED": "tools were exposed but none were called",
    "CONTEXT_ARTIFACT_UNVERIFIED": "context artifact could not be verified",
    "ASSESSOR_RATING_ABSENT": "an applicable assessor rating is absent",
    "NO_CONTEXT_CRITERION": "no context criterion was evaluated",
    "CONTROL_SAMPLE_INSUFFICIENT": "fewer than six control statuses were observed",
    "REQUIRED_AXIS_WITHHELD": "at least one required axis is withheld",
    "DECISIVE_SET_UNVERIFIED": "the decisive claim set is unverified",
    "FRESHNESS_UNVERIFIED": "evidence freshness is unverified",
}
_AXIS_NAMES = {"eio.axis.context": "Context", "eio.axis.behaviour": "Behaviour",
               "eio.axis.compliance": "Compliance", "eio.axis.governance": "Governance"}


def _reason(code: Any) -> str:
    return (_WITHHELD_REASONS.get(code, "an unrecognized reason was recorded")
            if isinstance(code, str) else "reason unavailable")


def _rc4_summary(rec: dict[str, Any], key: str, node: dict[str, Any]) -> str:
    """Render only fixed wording and fields already public in the rc4 PER."""
    value = _public_number(node.get("value"))
    measured = node.get("status") == "MEASURED" and value is not None
    if key == "readiness":
        if not measured:
            codes = node.get("withheld_codes") or []
            reasons = "; ".join(_reason(code) for code in codes) if isinstance(codes, list) else "reason unavailable"
            return f"Readiness: WITHHELD — {reasons or 'reason unavailable'}."
        text = f"Readiness: {value}/100 (recorded). Raw weighted score: {_public_number(node.get('raw'))}/100."
        cap = node.get("cap") or {}
        if cap.get("applied") is True:
            text += (f" Recorded ceiling: {_public_number(cap.get('ceiling'))}/100; "
                     f"listed cap claim IDs: {len(cap.get('claim_ids') or [])}.")
        return text
    if key in _AXIS_NAMES:
        label = f"{_AXIS_NAMES[key]} ({AXIS_SYMBOLS[key]})"
        if measured:
            return f"{label}: {value}/100 (recorded)."
        return f"{label}: WITHHELD — {_reason(node.get('withheld_code'))}."
    if key.startswith("eio.metric."):
        card = metric_card(rec, key)
        score = f"{value}/100 (recorded)" if measured else f"WITHHELD — {_reason(node.get('withheld_code'))}"
        turns = ", ".join(str(turn) for turn in card["turns"]) or "none"
        return (f"{key}: {score}. Member claims: {card['member_count']}; "
                f"passed: {card['passed']}; failed: {card['failed']}; other: {card['other']}; "
                f"turn indices: {turns}.")
    raise LookupError(f"{key}: no explanation for this target in the record")


def explain(rec: dict[str, Any], target: str, *, eio=None, local=None) -> str:
    """The rendering of the target's explanation under its registered template (one line per explanation it holds).
    Targets: `readiness`, an axis id or symbol, an `eio.metric.*` id, a finding id or display label, a control id, an
    `eio.gate.*` id, or `release_recommendation`. With `local` (the record's evaluation bundle, a dict), each fingerprint
    of a parameter is shown as its text in that bundle (decision #31: resolved locally for display; nothing is written
    into the record); without it a fingerprint shows in its display form, as in the stored summary."""
    key = resolve_target(rec, target)
    node = _node(rec, key)
    if not isinstance(node, dict):
        raise LookupError(f"{target}: no explanation for this target in the record")
    if (_rc4_score(rec) and "explanation" not in node
            and (key == "readiness" or key in AXIS_SYMBOLS or key.startswith("eio.metric."))):
        return _rc4_summary(rec, key, node)
    if "explanation" not in node:
        raise LookupError(f"{target}: no explanation for this target in the record")
    texts = bundle_texts(local) if local is not None else {}
    eio = eio if eio is not None else EIO(EIO_DIR)
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "template_id" in o and "params" in o and "summary" in o:
                if o["template_id"] not in eio.templates:
                    raise LookupError(f"{o['template_id']} is not a registered template of EIO {eio.release}")
                out.append(render(eio, o["template_id"], _clear(o["params"], texts)))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(node["explanation"])
    return "\n".join(out)
