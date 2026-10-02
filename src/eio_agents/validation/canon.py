"""The verifier's own RFC 8785 canonical form and digests.

Independent of `eio_agents.base.canon`: the verifier recomputes every digest with its own code.
"""
import hashlib
import math
from decimal import ROUND_HALF_EVEN, Decimal


def _num(x):
    if isinstance(x, bool):
        raise TypeError("bool")
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        raise ValueError("non-finite number (PROD-9)")
    if x == 0:
        return "0"
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    if "e" in r:
        m, e = r.split("e")
        return f"{m}e{'+' if int(e) > 0 else '-'}{abs(int(e))}"
    return r


_ESC = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _str(s):
    out = ['"']
    for ch in s:
        c = ord(ch)
        if 0xD800 <= c <= 0xDFFF:
            raise ValueError("lone surrogate (03 §5.1)")
        out.append(_ESC.get(ch) or ("\\u%04x" % c if c < 0x20 else ch))
    return "".join(out) + '"'


def jcs(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, list):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(_str(k) + ":" + jcs(v[k]) for k in sorted(v, key=lambda k: k.encode("utf-16-be"))) + "}"
    raise TypeError(type(v))


def jb(v):
    return jcs(v).encode("utf-8")


def sha(b):
    return "sha256:" + hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def sd(p, n=20):
    return hashlib.sha256(jb(p)).hexdigest()[:n]


def q4(x):
    return float(Decimal(repr(float(x))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
