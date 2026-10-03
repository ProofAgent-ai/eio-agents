#!/usr/bin/env python3
"""Write, or check, docs/predicates.md: the reference table of the predicates of the bundled EIO release.

The table is generated from `eio_agents.predicates()` (the ontology data), so it never states a meaning, an evidence
contract or a mapping by hand. tests/test_predicate_reference.py checks that the page is in sync.

Usage:
    python tools/predicate_reference.py            # check: exit 0 iff docs/predicates.md is what this script writes
    python tools/predicate_reference.py --write    # (re)write docs/predicates.md
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import eio_agents  # noqa: E402

PAGE = ROOT / "docs" / "predicates.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _wrap(text: str, indent: str = "") -> list[str]:
    return textwrap.wrap(text, 120, subsequent_indent=indent, break_long_words=False, break_on_hyphens=False)


def render() -> str:
    rows = eio_agents.predicates()
    release = eio_agents.standards()["eio_release"]
    polarity = Counter(row["polarity"] for row in rows)
    intro = (
        f"The {len(rows)} predicates of EIO {release}, the release bundled with this library "
        f"({', '.join(f'{n} {p}' for p, n in sorted(polarity.items()))}). A predicate is what a check decides: one claim "
        "names one predicate, the turns it was checked on and its state. This page is generated from the ontology data "
        "by `tools/predicate_reference.py`; do not edit it by hand. `eio-agents predicates --search WORD` searches the "
        "same catalogue, and `eio_agents.predicates()` returns it as data.")
    notes = [
        "- **Evidence** is the predicate's evidence contract: the kinds a failed claim must cite, one group per `;`, any "
        "kind of a group (`or`) satisfying it. A claim that does not meet its contract can still be recorded, but it is "
        "not `PROVEN`. See [concepts.md](concepts.md) for the evidence kinds.",
        "- **Metrics** are the metrics a decided claim on the predicate counts toward (the normative derived-view edges of "
        "`eio.mapping.metrics`).",
        "- **Controls** is the number of framework controls that target the predicate. Framework mappings are provisional "
        "evidence-relevance links, not compliance determinations.",
        "- **Fail** says whether a failed claim on the predicate can be projected into a scored native record: the native "
        "proof rule needs an evidence group that can prove agent behaviour, and a failure of a predicate marked `no` "
        "makes `convert` refuse the bundle (`build_bundle` refuses it first). A passed claim is always accepted.",
    ]
    lines = ["# Predicate reference", "", *_wrap(intro), ""]
    for note in notes:
        lines += _wrap(note, "  ")
    lines.append("")
    for module in sorted({row["module"] for row in rows}):
        group = [row for row in rows if row["module"] == module]
        lines += [f"## {module}", "", "| Predicate | Version | Meaning | Evidence | Metrics | Controls | Fail |",
                  "|---|---|---|---|---|---|---|"]
        for row in group:
            metrics = ", ".join(m.removeprefix("eio.metric.") for m in row["metrics"]) or "none"
            lines.append(f"| `{row['id'].removeprefix('eio.predicate.')}` | {row['version']} | {_cell(row['meaning'])} "
                         f"| {_cell(row['evidence'])} | {metrics} | {row['controls']} "
                         f"| {'yes' if row['failure_scorable'] else 'no'} |")
        lines.append("")
    lines += _wrap("Use a predicate id (with or without the `eio.predicate.` prefix) as a check's `predicate` in "
                   "[build_bundle](api.md#build_bundle).")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="(re)write docs/predicates.md")
    a = ap.parse_args(argv)
    text = render()
    if a.write:
        PAGE.write_text(text, encoding="utf-8")
        print(f"wrote {PAGE.relative_to(ROOT)}")
        return 0
    if PAGE.is_file() and PAGE.read_text(encoding="utf-8") == text:
        print(f"{PAGE.relative_to(ROOT)} is in sync")
        return 0
    print(f"{PAGE.relative_to(ROOT)} is out of date: run python tools/predicate_reference.py --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
