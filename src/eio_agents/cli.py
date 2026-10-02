"""The neutral `eio-agents` command line: project, validate, verify, explain, evidence, resolve, version.

    eio-agents project BUNDLE -o OUT.per.json [--jcs OUT.per.jcs]    evaluation bundle -> PER 2.0 record
    eio-agents validate FILE                                         a PER record, or a bundle (archive schema 3)
    eio-agents verify RECORD --bundle BUNDLE                         validate + VER-5 + re-projection digest match
    eio-agents explain RECORD TARGET [--local BUNDLE]                the record's eio.why.* renderings for a target
                                                                     (--local: fingerprints shown as their bundle text)
    eio-agents resolve RECORD BUNDLE                                 every withheld value with its text in the bundle
    eio-agents evidence RECORD FINDING                               cited PER proof refs only, no local source
    eio-agents version                                               library and bundled standard versions

`project` also reads a stored ProofAgent report until L3 (ACCEPTED_DEVIATIONS D-4); the raw-report command moves to the
harness command line (L6). Exit status: 0 success, 1 failure to read or project, 2 a check failed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eio_agents import api, validation
from eio_agents.validation.explain import _reason
from eio_agents.validation.validate import MAX_DEPTH


def _bounded_json(raw: bytes):
    """Reject excessive JSON nesting before parser-specific recursion limits vary."""
    depth = 0
    quoted = False
    escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                quoted = False
        elif byte == 0x22:
            quoted = True
        elif byte in (0x5B, 0x7B):  # [ {
            depth += 1
            if depth > MAX_DEPTH:
                raise RecursionError(f"JSON document exceeds {MAX_DEPTH} nesting levels")
        elif byte in (0x5D, 0x7D):  # ] }
            depth -= 1
    return json.loads(raw.decode("utf-8"))


def _load(p: str) -> dict:
    return _bounded_json(Path(p).read_bytes())


def _print_failures(fails) -> None:
    for f in fails:
        print(f"FAIL {f['check']} [{f['ver']}]: {f['detail']}")


def _print_proof(proof: dict) -> None:
    print(f"{proof['label']} | {proof['finding_id']} | {proof['severity']} | {proof['proof_status']}")
    for ref in proof["refs"]:
        print(f"Turn {ref['turn']}: {ref['kind']} | ref {ref['id']}")
        if ref["excerpt"]:
            print(f"  Quote: {ref['excerpt']}")
        if ref["tool"]:
            tool = ref["tool"]
            print(f"  Tool call: {tool.get('name')} | arguments {tool.get('arguments_pointer')} | "
                  f"sha256 {tool.get('arguments_sha256')}")
        if not ref["excerpt"] and not ref["tool"]:
            print(f"  Pointer: {ref['source_ref']} | span {ref['span_sha256']}")


def _run(a) -> int:
    if a.cmd == "project":
        try:
            digest = api.convert_file(a.bundle, a.out, a.jcs)
        except api.ConversionError as exc:
            print(f"PROJECTION FAILED (no record written): {exc}", file=sys.stderr)
            return 1
        rec = _load(a.out)
        rr, sc = rec["release_recommendation"], rec["scores"]
        readiness = sc["readiness"]["value"] if sc else None
        wire = rec["header"]["per_version"]
        if wire != "2.0.0":
            print(f"PARTIAL/HISTORICAL PER {wire}: not the public PER 2.0.0 scored contract", file=sys.stderr)
        print(f"{a.out}: PER {wire} · {digest} · state {rr['state']} · readiness {readiness} · claims {len(rec['claims'])} · "
              f"findings {len(rec['findings'])}")
        return 0
    if a.cmd == "validate":
        raw = Path(a.file).read_bytes()
        doc = _bounded_json(raw)
        is_bundle = isinstance(doc, dict) and doc.get("archive_schema") == 3 and "header" in doc and "stage_records" in doc
        # a bundle is checked from its bytes, so its reading as I-JSON (B0) is the one `project` applies (review R-2)
        fails = validation.validate_bundle(raw) if is_bundle else api.validate(doc)
        _print_failures(fails)
        print(("VALID" if not fails else f"{len(fails)} check(s) failed") + (" (bundle)" if is_bundle else ""))
        return 0 if not fails else 2
    if a.cmd == "verify":
        r = api.verify(_load(a.record), Path(a.bundle).read_bytes())
        print(json.dumps({k: r[k] for k in ("valid", "digest_match", "per_sha256", "rederived_sha256")}, indent=1))
        _print_failures(r["failures"])
        return 0 if r["valid"] else 2
    if a.cmd == "explain":
        try:
            rec = _load(a.record)
            if a.list:
                for item in api.targets(rec):
                    if item.get("status") == "WITHHELD":
                        codes = item.get("withheld_codes") or [item.get("withheld_code")]
                        value = "WITHHELD — " + "; ".join(_reason(code) for code in codes)
                    else:
                        value = item["value"]
                    print(f"{item['id']} | {item['label']} | {value}")
                print("Axes: Q = Context; E = Behaviour; C = Compliance; G = Governance")
                return 0
            target = " ".join(a.target)
            if not target:
                raise LookupError("a target is required (or use --list)")
            if target.startswith("finding "):
                target = target.removeprefix("finding ")
                if target.startswith("t"):
                    for proof in api.findings_at_turn(rec, target):
                        print(f"{proof['label']} | {proof['finding_id']}")
                        print(api.explain(rec, proof["finding_id"], local=_load(a.local) if a.local else None))
                    return 0
                api.finding_evidence(rec, target)
            try:
                card = api.metric_card(rec, target)
            except LookupError:
                card = None
            print(api.explain(rec, target, local=_load(a.local) if a.local else None))
            if card is not None and card.get("source") != "rc4":
                print(f"{card['label']} — {card['value']} | {card['id']}")
                print(f"Claims: applicable {card['applicable']}, passed {card['passed']}, failed {card['failed']}, "
                      f"excluded {card['excluded']}")
                for failure in card["primary_failures"]:
                    print(f"Primary failure: {failure['label'] or failure['claim_id']} · {failure['severity']}")
                print(f"Try next: eio-agents evidence {a.record} <finding-id>")
        except LookupError as exc:
            print(f"{exc}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "evidence":
        try:
            rec = _load(a.record)
            proofs = api.findings_at_turn(rec, a.finding) if a.finding.startswith("t") else [api.finding_evidence(rec, a.finding)]
        except LookupError as exc:
            print(f"{exc}", file=sys.stderr)
            return 2
        for proof in proofs:
            _print_proof(proof)
        return 0
    if a.cmd == "resolve":
        rows = api.resolve(_load(a.record), Path(a.bundle).read_bytes())
        for r in rows:
            print(f"{r['record_pointer']}\t{r['fingerprint'][:19]}\t{r['bundle_pointer'] or '-'}\t"
                  f"{json.dumps(r['text'], ensure_ascii=False) if r['text'] is not None else 'UNRESOLVED'}")
        unresolved = sum(1 for r in rows if r["text"] is None)
        print(f"{len(rows)} withheld value(s), {len(rows) - unresolved} resolved from the local bundle")
        return 0 if not unresolved else 2
    if a.cmd == "version":
        from eio_agents import __version__
        print(json.dumps({"eio_agents": __version__, **api.standards()}, indent=1))
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eio-agents", description="EIO-Agents: EIO evaluation bundles and PER 2.0 records")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("project", help="evaluation bundle (archive schema 3) -> PER 2.0 record")
    c.add_argument("bundle")
    c.add_argument("-o", "--out", required=True)
    c.add_argument("--jcs", help="also write the canonical JCS bytes")
    v = sub.add_parser("validate", help="the verifier's checks of a PER record, or of an evaluation bundle")
    v.add_argument("file")
    y = sub.add_parser("verify", help="validate + VER-5 over the bundle's sources + re-projection digest match")
    y.add_argument("record")
    y.add_argument("--bundle", required=True)
    e = sub.add_parser("explain", help="the eio.why.* renderings of a score, metric, axis, finding, control, gate or "
                                       "release_recommendation")
    e.add_argument("record")
    e.add_argument("target", nargs="*")
    e.add_argument("--local", help="the record's evaluation bundle: show each fingerprint as its text (display only)")
    e.add_argument("--list", action="store_true", help="list exact target ids, labels and values")
    p = sub.add_parser("evidence", help="show cited PER proof refs for a finding (never reads a local archive)")
    p.add_argument("record")
    p.add_argument("finding")
    r = sub.add_parser("resolve", help="every withheld value (fingerprint) of a record with its text in the local bundle")
    r.add_argument("record")
    r.add_argument("bundle")
    sub.add_parser("version", help="library and bundled standard versions")
    a = ap.parse_args(argv)
    try:
        return _run(a)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:   # a missing or unreadable file
        print(f"eio-agents {a.cmd}: {exc}", file=sys.stderr)
        return 1
    except api.ConversionError as exc:
        print(f"eio-agents {a.cmd}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
