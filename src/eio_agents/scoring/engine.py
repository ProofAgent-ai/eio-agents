"""The readiness-index engine (split plan §3.7, §4.3; contract §4.2 "L4 + S1a"): the ported core of the main-tree harness
scoring function (`compute_pai`, `_weighted_geomean`, `_margin`, `severity_for`, the completeness rule and the grade ramp),
under neutral names. "PAI" and "ProofAgent Index" are called the readiness index here.

**No numeric defaults.** Every number the engine uses comes from the `parameters` of a scoring-profile document
(`eio_agents.scoring.profiles`): the geometric-mean floor `epsilon`, the `readiness_ceiling` of a blocked index, the
`axis_weights`, the `band_ramp`, the `verdict_ramp`, the `severity_bands`, the `required_axes`, the uncertainty clamp
`max_margin`, the sampling axis and its pseudo-counts, the `scale` and the rounding `decimals`. A missing parameter fails
closed (`SCORING_PROFILE`); there is no fallback value. For the attested harness-2.x profile these are epsilon 1.0 and
ceiling 49.0 (EIO's own aggregation declares epsilon 0.01, `axes.yaml`). An AST test (tests/test_scoring_engine.py)
asserts that no module of `eio_agents.scoring` holds a module-level float constant or a numeric default argument.

The engine is keyed by EIO axis id. It reads no report, no claim and no producer vocabulary: the inputs are the axis
values (0 to `scale` max, or None when the axis was not measured), a `blocked` flag decided by the caller (under an
attested profile, its declared trigger; the PER cap stays claim-driven, W1), optional per-axis discounts in [0, 1], the
measured per-axis uncertainties and the sample size of the sampling axis. Pure and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, log

from eio_agents.base.errors import require

# the parameters every readiness computation reads (a profile document names each; `SCORING_PROFILE` otherwise)
INDEX_PARAMETERS = ("epsilon", "readiness_ceiling", "axis_order", "axis_weights", "required_axes", "band_ramp",
                    "verdict_ramp", "max_margin", "sampling_axis", "sampling_pseudo_counts", "scale", "decimals")


def parameter(parameters, name):
    """One profile parameter; fails closed when the document does not declare it (no default exists)."""
    require(isinstance(parameters, dict) and parameters.get(name) is not None, "SCORING_PROFILE",
            f"the scoring profile declares no parameter {name!r} (the engine has no default)")
    return parameters[name]


def check_parameters(parameters):
    """Fail closed unless every parameter of `INDEX_PARAMETERS` is declared, and the weights name exactly the axes."""
    for name in INDEX_PARAMETERS:
        parameter(parameters, name)
    order, weights = parameters["axis_order"], parameters["axis_weights"]
    require(sorted(order) == sorted(weights), "SCORING_PROFILE", "axis_weights must name exactly the axes of axis_order")
    require(set(parameters["required_axes"]) <= set(order), "SCORING_PROFILE", "a required axis is not in axis_order")
    require(len(parameters["scale"]) == 2 and parameters["scale"][0] < parameters["scale"][1], "SCORING_PROFILE", "scale is [low, high]")
    return parameters


@dataclass
class IndexAxis:
    """One input axis of the readiness index (the ported `Axis`), on the profile's scale."""

    axis: str                       # EIO axis id
    score: float | None             # rounded to the profile's decimals; None = not measured (left out of the index)
    weight: float                   # the profile weight after any discount
    present: bool
    sub: list = field(default_factory=list)


@dataclass
class ReadinessIndex:
    """The readiness index (the ported `PAIResult` core): the value after the ceiling, the raw weighted geometric mean,
    the completeness rule, the verdict, the band, and the propagated uncertainty."""

    value: float                    # after the readiness ceiling when blocked (the gate)
    raw: float                      # weighted geometric mean before the ceiling (the gauge)
    blocked: bool
    complete: bool
    missing_axes: list
    axes: list
    weakest: str | None
    coverage: list
    verdict: str                    # ready | ready_with_caveats | not_ready | blocked | indeterminate (the verdict ramp)
    band: dict                      # the band-ramp entry of `value` ({"band": ...} plus any presentation keys)
    margin: float | None
    scale: tuple
    decimals: int

    @property
    def interval(self):
        """(low, high) around `value`, clamped to the scale; None when no margin was estimated."""
        if self.margin is None:
            return None
        lo, hi = self.scale
        return (round(max(lo, self.value - self.margin), self.decimals), round(min(hi, self.value + self.margin), self.decimals))


def weighted_geomean(items, *, epsilon):
    """Weighted geometric mean of (value, weight) pairs; None if nothing to average. Values are floored at `epsilon`
    (a profile parameter), so a genuine zero crushes the aggregate without taking log(0)."""
    pts = [(max(float(v), epsilon), float(w)) for v, w in items if v is not None and w > 0]
    wsum = sum(w for _, w in pts)
    if not pts or wsum <= 0:
        return None
    return exp(sum(w * log(v) for v, w in pts) / wsum)


def ramp_entry(value, ramp):
    """The first entry of a ramp `{bands: [{min, ...}], otherwise}` whose `min` the value reaches, else `{band: otherwise}`
    (the ported `grade_for`: the band ramp is profile data)."""
    for b in ramp["bands"]:
        if value >= b["min"]:
            return b
    return {"band": ramp["otherwise"]}


def band_of(value, ramp):
    """The band letter of `value` under the profile's band ramp; None for no value."""
    return None if value is None else ramp_entry(value, ramp)["band"]


def severity_for(score, severity_bands):
    """Severity for a component score under the profile's severity bands (the ported `severity_for`); '' for no score."""
    if score is None:
        return ""
    for b in severity_bands["bands"]:
        if float(score) >= b["min"]:
            return b["severity"]
    return severity_bands["otherwise"]


def normalized_weights(parameters):
    """axis id -> weight / sum of weights (the weight a record states for each axis)."""
    w = parameter(parameters, "axis_weights")
    total = sum(float(x) for x in w.values())
    require(total > 0, "SCORING_PROFILE", "the axis weights sum to zero")
    return {a: float(x) / total for a, x in w.items()}


def verdict_of(value, blocked, complete, caveat, ramp):
    """The admissibility verdict (the ported readiness rule): a block is definitive even on partial evidence;
    incompleteness blocks admission; otherwise the verdict ramp, whose top verdict a caveat downgrades."""
    if blocked:
        return ramp["blocked"]
    if not complete:
        return ramp["incomplete"]
    top = ramp["bands"][0]
    for b in ramp["bands"]:
        if value >= b["min"]:
            return ramp["caveat"] if (caveat and b is top) else b["verdict"]
    return ramp["otherwise"]


def margin_of(axes, geo_items, raw, axis_margins, sample_size, parameters):
    """Half-width of the uncertainty on the index, propagated from the axes (the ported `_margin`).

    Two independent sources combine in quadrature: the measured per-axis uncertainty (`axis_margins`), and the sampling
    error of the profile's `sampling_axis`, a rate estimated from `sample_size` trials with the profile's pseudo-counts
    (`sampling_pseudo_counts` = [successes, trials] added, the Agresti-Coull correction). A geometric mean's sensitivity to
    one axis is (index / axis) x (w / sum w). The result is clamped to `max_margin`. None when nothing is available to
    estimate from, never 0."""
    if raw <= 0 or not geo_items:
        return None
    lo, hi = parameter(parameters, "scale")
    s0, n0 = parameter(parameters, "sampling_pseudo_counts")
    samp = parameter(parameters, "sampling_axis")
    wsum = sum(w for _, w in geo_items)
    terms = []
    for a in axes:
        if not a.present or a.score is None or a.weight <= 0 or a.score <= 0:
            continue
        sens = (raw / float(a.score)) * (a.weight / wsum)
        unc = float((axis_margins or {}).get(a.axis) or 0)
        if a.axis == samp and sample_size:
            p_hat = (float(a.score) / hi * sample_size + s0) / (sample_size + n0)
            se = hi * (p_hat * (1 - p_hat) / (sample_size + n0)) ** 0.5
            unc = (unc ** 2 + se ** 2) ** 0.5
        if unc > 0:
            terms.append(sens * unc)
    if not terms:
        return None
    return round(min(parameter(parameters, "max_margin"), sum(t * t for t in terms) ** 0.5), parameter(parameters, "decimals"))


def readiness_index(values, parameters, *, blocked, caveat=False, discounts=None, axis_margins=None, sample_size=None,
                    sub_scores=None):
    """The readiness index of `values` (EIO axis id -> value or None) under the profile `parameters` (the ported
    `compute_pai` core). `blocked` caps the value at the profile's `readiness_ceiling`; `caveat` downgrades a top verdict;
    `discounts` (axis id -> factor in [0, 1]) scale an axis weight (anti-theatre); `axis_margins` and `sample_size` feed
    the margin. A weight of 0 makes an axis non-contributing but still counts it as covered."""
    P = check_parameters(parameters)
    nd, (lo, hi) = P["decimals"], P["scale"]
    unknown = sorted(set(values) - set(P["axis_order"]))
    require(not unknown, "SCORING_PROFILE", f"axis values for axes the profile does not declare: {unknown}")
    w = {a: float(P["axis_weights"][a]) for a in P["axis_order"]}
    for a, d in (discounts or {}).items():
        require(a in w, "SCORING_PROFILE", f"a discount for an undeclared axis {a}")
        w[a] = w[a] * max(0, min(1, float(d)))
    axes, geo = [], []
    for a in P["axis_order"]:
        val = values.get(a)
        present = val is not None
        axes.append(IndexAxis(axis=a, score=round(float(val), nd) if present else None, weight=w[a], present=present,
                              sub=list((sub_scores or {}).get(a) or [])))
        if present and w[a] > 0:
            geo.append((float(val), w[a]))
    raw = weighted_geomean(geo, epsilon=P["epsilon"])
    raw = lo if raw is None else round(raw, nd)
    value = round(max(lo, min(hi, min(raw, P["readiness_ceiling"]) if blocked else raw)), nd)
    coverage = [x.axis for x in axes if x.present]
    scored = [x for x in axes if x.present and x.score is not None]
    weakest = min(scored, key=lambda x: x.score).axis if scored else None
    missing = [a for a in P["required_axes"] if a not in coverage]
    complete = not missing
    return ReadinessIndex(value=value, raw=raw, blocked=bool(blocked), complete=complete, missing_axes=missing, axes=axes,
                          weakest=weakest, coverage=coverage,
                          verdict=verdict_of(value, blocked, complete, caveat, P["verdict_ramp"]),
                          band=dict(ramp_entry(value, P["band_ramp"])),
                          margin=margin_of(axes, geo, raw, axis_margins, sample_size, P) if not blocked else None,
                          scale=(lo, hi), decimals=nd)
