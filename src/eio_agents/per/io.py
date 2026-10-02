"""PER record io: canonical bytes, per_sha256, the deterministic pretty form and writing a record."""
import json
from pathlib import Path

from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require


def canonical_bytes(rec):
    """RFC 8785 (JCS) canonical bytes of a record."""
    return jb(rec)


def per_sha256(rec):
    """`sha256:<hex>` over the JCS bytes of a record."""
    return H(canonical_bytes(rec))


def pretty(o, ind=0, width=160):
    """Deterministic pretty form: an object or array fits on one line when short enough, else one member per line."""
    one = json.dumps(o, ensure_ascii=False, separators=(", ", ": "))
    pad = " " * ind
    if len(one) + len(pad) <= width or not isinstance(o, (dict, list)) or not o:
        return one
    if isinstance(o, dict):
        return "{\n" + ",\n".join(f"{pad} {json.dumps(k, ensure_ascii=False)}: {pretty(v, ind + 1, width)}" for k, v in o.items()) + "\n" + pad + "}"
    return "[\n" + ",\n".join(pad + " " + pretty(v, ind + 1, width) for v in o) + "\n" + pad + "]"


def write_record(rec, out_json, out_jcs=None):
    """Write the pretty record (UTF-8, trailing newline) and optionally the JCS bytes. Returns (per_sha256, JCS length)."""
    body = jb(rec)
    text = pretty(rec) + "\n"
    require(json.loads(text) == json.loads(body), "PRETTY_ROUNDTRIP")
    Path(out_json).write_text(text, encoding="utf-8")
    if out_jcs:
        Path(out_jcs).write_bytes(body)
    return H(body), len(body)


def write(rec, out, jcs_out=None):
    """Write the pretty record (and optionally the JCS bytes). Returns per_sha256."""
    digest, _n = write_record(rec, str(out), str(jcs_out) if jcs_out else None)
    return digest
