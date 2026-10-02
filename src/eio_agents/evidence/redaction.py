"""Redaction and excerpts of evidence text (03 §13.1 PROD-42; 04 §5.4.1): `luhn`, `redact`, `excerpt_of`.

ASCII classes (re.ASCII): \\d = [0-9], \\b between [A-Za-z0-9_] and any other character, ASCII-only case folding (PROD-6).
"""
import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.ASCII)
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b", re.ASCII)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.ASCII)
PAN = re.compile(r"\b(?:\d[ -]?){13,19}\b", re.ASCII)
SECRET = re.compile(r"(?:sk-|AKIA|ghp_|xox[abp]-)[A-Za-z0-9_\-]{8,}", re.ASCII)
LAST4 = re.compile(r"(?i)(last ?4|ssn)([^0-9]{0,12})(\d{4})", re.ASCII)
MARKER = re.compile(r"\[REDACTED:(?:email|card|national_id|secret|last4)\]")
EXCERPT_MAX = 400


def luhn(d):
    s = 0
    for i, c in enumerate(reversed(d)):
        n = int(c)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        s += n
    return s % 10 == 0


def redact(s):
    """The classes in order, each pass over the previous pass's output; the sequence repeats until it replaces nothing
    (a replacement can expose a match). A match overlapping a [REDACTED:<class>] marker is kept (a marker's 'last4').
    Returns (redacted text, at least one match replaced)."""
    passes = (("email", EMAIL, lambda m: "[REDACTED:email]"), ("national_id", SSN, lambda m: "[REDACTED:national_id]"),
              ("national_id", IBAN, lambda m: "[REDACTED:national_id]"),
              ("card", PAN, lambda m: "[REDACTED:card]" if luhn(re.sub(r"\D", "", m.group())) else None),
              ("secret", SECRET, lambda m: "[REDACTED:secret]"),
              ("last4", LAST4, lambda m: m.group(1) + m.group(2) + "[REDACTED:last4]"))
    r, replaced = s, 0
    while True:
        before = replaced
        for _, rx, repl in passes:
            marks = [k.span() for k in MARKER.finditer(r)]

            def sub(m, repl=repl, marks=marks):
                nonlocal replaced
                new = None if any(a < m.end() and m.start() < b for a, b in marks) else repl(m)
                replaced += new is not None
                return m.group() if new is None else new
            r = rx.sub(sub, r)
        if replaced == before:
            return r, replaced > 0


def excerpt_of(x):
    """03 §13.1 PROD-42: redact the whole span, then keep the first 400 code points of the redacted text without
    splitting a [REDACTED:<class>] marker. Returns (excerpt, excerpt_truncated, excerpt_redacted)."""
    r, red = redact(x)
    cut = len(r)
    if cut > EXCERPT_MAX:
        cut = EXCERPT_MAX
        for m in MARKER.finditer(r):
            if m.start() < EXCERPT_MAX < m.end():
                cut = m.start()
                break
    return r[:cut], len(r) > cut, red
