"""PER Pointers (03 §7.13 PROD-36): an identifier token selects an element of an id-keyed array, a numeric index any other."""


ID_KEYED = {("claims",): "id", ("evidence", "refs"): "id", ("findings",): "finding_id", ("controls",): "control_id",
            ("coverage", "obligations"): "id", ("scores", "metrics"): "metric"}


def resolve_pointer(rec, ptr):
    if not ptr.startswith("/"):
        return False, "not absolute"
    toks = [t.replace("~1", "/").replace("~0", "~") for t in ptr[1:].split("/")] if ptr != "/" else []
    cur, path = rec, ()
    for tok in toks:
        if isinstance(cur, dict):
            if tok not in cur:
                return False, f"no member {tok}"
            cur = cur[tok]
            path = path + (tok,)
        elif isinstance(cur, list):
            key = ID_KEYED.get(path)
            if key:
                hit = [x for x in cur if isinstance(x, dict) and x.get(key) == tok]
                if len(hit) != 1:
                    return False, f"no element {key}={tok}" + (" (a numeric index MUST NOT be used)" if tok.isdigit() else "")
                cur = hit[0]
            else:
                if not tok.isdigit() or int(tok) >= len(cur):
                    return False, f"bad index {tok}"
                cur = cur[int(tok)]
            path = path + ("*",)
        else:
            return False, f"scalar at {tok}"
    return True, ""
