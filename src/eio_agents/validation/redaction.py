"""The verifier's own excerpt redaction (03 §13.1 PROD-42; 04 §5.4.1), independent of `eio_agents.evidence.redaction`."""
import re

# Not imported from the generator: D2 recomputes every excerpt from the archive span with this code and E2 screens the
# published excerpts with it. Classes in their application order; each pass reads the output of the previous one.
# ASCII classes (PROD-6): \d is [0-9], \b lies between [A-Za-z0-9_] and any other character or either end, and
# case-insensitivity is ASCII only; every pattern is compiled with A_ = re.ASCII.
# (class, pattern, the group whose text is replaced (0 = the whole match), Luhn required on the match's digits)
A_ = re.ASCII
EXCERPT_LIMIT = 400
REDACTION_CLASSES = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", A_), 0, False),
    ("national_id", re.compile(r"\b\d{3}-\d{2}-\d{4}\b", A_), 0, False),                    # SSN form
    ("national_id", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", A_), 0, False),         # IBAN
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b", A_), 0, True),                           # 13-19 digits passing Luhn
    ("secret", re.compile(r"(?:sk-|AKIA|ghp_|xox[abp]-)[A-Za-z0-9_\-]{8,}", A_), 0, False),
    ("last4", re.compile(r"(?i)(?:last ?4|ssn)[^0-9]{0,12}(\d{4})", A_), 1, False),        # only the four digits
]
REDACTION_MARKER = re.compile(r"\[REDACTED:(?:email|card|national_id|secret|last4)\]")


def luhn_ok(digits):
    """Luhn mod 10 over a digit string: double every second digit from the right, subtract 9 above 9."""
    total = 0
    for pos, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if pos % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def class_matches(text, cls):
    """The matches of one redaction class in text: [(whole match span, span to replace)] (card: Luhn-valid only)."""
    _, rx, grp, needs_luhn = cls
    out = []
    for m in rx.finditer(text):
        if needs_luhn and not luhn_ok("".join(ch for ch in m.group() if ch in "0123456789")):
            continue
        out.append((m.span(), m.span(grp)))
    return out


def unmarked(text, matches):
    """The matches that do not overlap a [REDACTED:<class>] marker (a marker's own text, e.g. 'last4', is never redacted)."""
    marks = [m.span() for m in REDACTION_MARKER.finditer(text)]
    return [(w, rep) for w, rep in matches if not any(w[0] < mb and ma < w[1] for ma, mb in marks)]


def redact_span(span):
    """Every class in order over the whole span, the sequence repeated until it replaces nothing (a replacement can
    expose a match); returns (redacted text, number of replacements). Terminates: each replacement removes an '@', a
    secret prefix or at least three digits and adds none."""
    text, n = span, 0
    while True:
        n0 = n
        for cls in REDACTION_CLASSES:
            spans = [rep for _, rep in unmarked(text, class_matches(text, cls))]
            for a, b in reversed(spans):
                text = text[:a] + f"[REDACTED:{cls[0]}]" + text[b:]
            n += len(spans)
        if n == n0:
            return text, n


def expected_excerpt(span):
    """PROD-42: redact the whole span, then keep at most 400 code points without cutting a marker.
    Returns (excerpt, excerpt_truncated, excerpt_redacted)."""
    red, n = redact_span(span)
    keep = min(len(red), EXCERPT_LIMIT)
    for m in REDACTION_MARKER.finditer(red):
        if m.start() < keep < m.end():
            keep = m.start()
    return red[:keep], keep < len(red), n > 0


CUT_ZONE = 38   # the longest card match (19 digits, 19 separators): the longest match a cut can reshape


def surviving_matches(excerpt, truncated):
    """E2 (record only): class matches left outside the markers of a published excerpt. The redacted span has none
    (redaction runs to a fixed point), so any match is a defect, except one that starts in the last CUT_ZONE code
    points of a truncated excerpt: the cut can form one there (a shortened digit run); D2, which has the span, decides."""
    found = []
    for cls in REDACTION_CLASSES:
        for (a, b), _ in unmarked(excerpt, class_matches(excerpt, cls)):
            if truncated and a >= len(excerpt) - CUT_ZONE:
                continue
            found.append((cls[0], excerpt[a:b]))
    return found
