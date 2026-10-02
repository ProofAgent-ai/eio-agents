"""Canonical form and digests: RFC 8785 JCS, stable_digest, sha256 strings and the number rules (03 PROD-9, PROD-11, PROD-13)."""
import hashlib
import math
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from eio_agents.base.errors import ConversionError


DOUBLE_MAX = 1.7976931348623157e308     # the largest finite IEEE 754 double


def es6num(x):
    if isinstance(x, bool):
        raise TypeError("bool is not a number")
    if isinstance(x, int):
        # an integer beyond the double range has no ES6 number form (and Python cannot even print one of more than 4,300
        # digits): typed, never an untyped ValueError (L3 fix round 1, issue 4)
        if abs(x) > DOUBLE_MAX:
            raise ConversionError("NON_FINITE: an integer outside the IEEE 754 double range (PROD-9)", code="NON_FINITE")
        return str(x)
    if math.isnan(x) or math.isinf(x):
        raise ConversionError("NON_FINITE: a number is NaN or infinite (PROD-9)", code="NON_FINITE")
    if x == 0:
        return "0"
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    if "e" in r:
        m, e = r.split("e")
        ei = int(e)
        return f"{m}e{'+' if ei > 0 else '-'}{abs(ei)}"
    return r


def jcs_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if 0xD800 <= o <= 0xDFFF:
            raise ConversionError("LONE_SURROGATE: strings must be Unicode scalar sequences (03 §5.1)", code="LONE_SURROGATE")
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def jcs(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return es6num(v)
    if isinstance(v, str):
        return jcs_str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        ks = sorted(v.keys(), key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(jcs_str(k) + ":" + jcs(v[k]) for k in ks) + "}"
    raise TypeError(type(v))


def jb(v):
    return jcs(v).encode("utf-8")


def sd(payload, n=20):
    """stable_digest (01 §10.1, 03 PROD-13)."""
    return hashlib.sha256(jb(payload)).hexdigest()[:n]


def H(s):
    """"sha256:<hex>" of bytes, or of a string's UTF-8 bytes; a string that is not a sequence of Unicode scalar values (a
    lone surrogate) has no UTF-8 form and fails closed with the code JCS uses for it (L2 exit D-30)."""
    if isinstance(s, str):
        try:
            s = s.encode("utf-8")
        except UnicodeEncodeError as e:
            raise ConversionError("LONE_SURROGATE: strings must be Unicode scalar sequences (03 §5.1)", code="LONE_SURROGATE") from e
    return "sha256:" + hashlib.sha256(s).hexdigest()


def q4(x):
    """03 PROD-11: shortest round-trip repr, then half-even at the 4th decimal."""
    return float(Decimal(repr(float(x))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))


def half_up_int(x):
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize(o):
    """ints stay ints; integral floats become ints (JCS writes 49.0 as 49); -0 -> 0."""
    if isinstance(o, bool) or o is None or isinstance(o, str):
        return o
    if isinstance(o, int):
        return o
    if isinstance(o, float):
        if o == 0:
            return 0
        return int(o) if o == int(o) else o
    if isinstance(o, list):
        return [normalize(x) for x in o]
    if isinstance(o, dict):
        return {k: normalize(v) for k, v in o.items()}
    raise TypeError(type(o))
