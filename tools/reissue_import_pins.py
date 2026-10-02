"""Refresh exact manifest import pins after an intentional ontology module reissue.

This does not change module versions or semantic content. Review the resulting
module and ontology digests before admitting the release.
"""

import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1] / "src/eio_agents/ontology/data"
MANIFEST = ROOT / "manifest.yaml"
IMPORT_RE = re.compile(r'^(  - \{module: ([^,]+), version: [^,]+, sha256: ")sha256:[0-9a-f]{64}("\})$', re.M)


def main() -> None:
    paths = {}
    for path in ROOT.rglob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("eio"), dict):
            module_id = document["eio"]["id"]
            if module_id in paths:
                raise ValueError(f"duplicate module {module_id}")
            paths[module_id] = path
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    imported = {row["module"] for row in manifest["imports"]}
    if imported != paths.keys() - {manifest["eio"]["id"]}:
        raise ValueError("manifest imports do not match the packaged module inventory")

    replaced = set()

    def replace(match: re.Match[str]) -> str:
        module_id = match.group(2)
        if module_id not in imported or module_id in replaced:
            raise ValueError(f"unexpected or duplicate import {module_id}")
        replaced.add(module_id)
        digest = hashlib.sha256(paths[module_id].read_bytes()).hexdigest()
        return f"{match.group(1)}sha256:{digest}{match.group(3)}"

    original = MANIFEST.read_text(encoding="utf-8")
    updated = IMPORT_RE.sub(replace, original)
    if replaced != imported:
        raise ValueError(f"unmatched imports: {sorted(imported - replaced)}")
    MANIFEST.write_text(updated, encoding="utf-8")
    print(f"refreshed {len(replaced)} module pins in {MANIFEST}")


if __name__ == "__main__":
    main()
