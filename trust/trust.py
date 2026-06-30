"""
Trust Engine.

Implements the 3-factor trust formula adapted from data-fusion /
truth-discovery literature (Michelfeit, Knap & Necasky, arXiv:1410.7990):

    trust(value) = source_reliability
                 x (1 - conflict_penalty)
                 x agreement_boost

  - source_reliability: per-source prior from config/settings.py, scaled by
    the method that produced the claim (regex-anchored > keyword-scan).
  - conflict_penalty: weighted average distance to other observed values for
    the same field (0 when all sources agree, up to 1 when maximally split).
  - agreement_boost: reflects corroboration.
      * Multiple distinct source types: min(1.0, 0.60 + 0.20 × (n_sources - 1))
      * Single source: min(0.85, 0.70 × method_multiplier)
        — so a tightly-anchored regex method (1.10) scores 0.77 while a
          loose heuristic (0.85) scores only 0.60, making every field
          distinguishable even when they share the same source.

Returns all components so callers can expose the full breakdown in
provenance and the UI.
"""
import re
from typing import List, Tuple
from rapidfuzz import fuzz
from config.settings import SOURCE_RELIABILITY, TRUST_FLOOR, METHOD_RELIABILITY_MULTIPLIER

Claim = Tuple[str, object, str, str, str]  # field, value, source_type, source_name, method

# Fields where multiple DISTINCT values legitimately co-exist.
MULTI_VALUE_FIELDS = {"skill", "email", "phone"}

_EMAIL_VALID_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_PHONE_VALID_RE = re.compile(r"^\+\d{8,15}$")


def _string_distance(a: str, b: str) -> float:
    """0 = identical, 1 = completely different."""
    if a == b:
        return 0.0
    score = fuzz.ratio(str(a).lower(), str(b).lower())
    return 1.0 - (score / 100.0)


def _numeric_distance(a: float, b: float, scale: float = 10.0) -> float:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, abs(a - b) / scale)


def _distance(field: str, a, b) -> float:
    if field in ("years_experience",):
        return _numeric_distance(a, b)
    return _string_distance(str(a), str(b))


def _method_multiplier(methods) -> float:
    """Highest applicable multiplier across the methods that claimed this value."""
    mults = [METHOD_RELIABILITY_MULTIPLIER.get(m, 1.0) for m in methods]
    return max(mults) if mults else 1.0


def score_claims_for_field(claims_for_field: List[Claim]) -> List[dict]:
    """
    claims_for_field: all claims for ONE canonical field of ONE candidate.

    Returns a list of dicts: {value, sources, source_names, methods, trust,
    below_floor, reliability, conflict_penalty, agreement_boost}

    Formula: trust = source_reliability × (1 - conflict_penalty) × agreement_boost
    All three factors are exposed in the dict for provenance / UI breakdown.
    """
    if not claims_for_field:
        return []

    # Group by distinct value (case-folded)
    groups: dict = {}
    for claim in claims_for_field:
        field, value, source_type, source_name, method = claim[:5]
        key = str(value).strip().lower()
        groups.setdefault(key, []).append((value, source_type, source_name, method))

    field_name = claims_for_field[0][0]
    results = []

    for key, entries in groups.items():
        # ── Factor 1: source reliability × method multiplier ──────────────────
        base_reliabilities = [SOURCE_RELIABILITY.get(st, 0.5) for (_, st, _, _) in entries]
        methods_for_value = [m for (_, _, _, m) in entries]
        method_mult = _method_multiplier(methods_for_value)
        source_reliability = min(1.0, max(base_reliabilities) * method_mult)

        # ── Factor 2: conflict penalty ─────────────────────────────────────────
        other_groups = [g for k, g in groups.items() if k != key]
        if other_groups and field_name not in MULTI_VALUE_FIELDS:
            weighted_distances = []
            for other_entries in other_groups:
                other_value = other_entries[0][0]
                other_reliability = max(
                    SOURCE_RELIABILITY.get(st, 0.5) for (_, st, _, _) in other_entries
                )
                d = _distance(field_name, entries[0][0], other_value)
                weighted_distances.append(d * other_reliability)
            conflict_penalty = min(1.0, sum(weighted_distances) / len(weighted_distances))
        else:
            conflict_penalty = 0.0

        # ── Factor 3: agreement boost ──────────────────────────────────────────
        distinct_sources = len({st for (_, st, _, _) in entries})
        if distinct_sources > 1:
            # Multi-source: each additional agreeing source adds weight
            agreement_boost = min(1.0, 0.60 + 0.20 * (distinct_sources - 1))
        else:
            # Single source: scale by extraction method quality so that
            # tightly-anchored regex (1.10) differs from a loose heuristic (0.85)
            agreement_boost = min(0.85, 0.70 * method_mult)

        # ── Final trust ────────────────────────────────────────────────────────
        trust = (
            source_reliability
            * (1 - conflict_penalty)
            * agreement_boost
        )
        trust = round(max(0.0, min(1.0, trust)), 3)

        results.append({
            "value":            entries[0][0],
            "sources":          sorted({st for (_, st, _, _) in entries}),
            "source_names":     [sn for (_, _, sn, _) in entries],
            "methods":          sorted({m for (_, _, _, m) in entries}),
            "trust":            trust,
            "below_floor":      trust < TRUST_FLOOR,
            # Full formula breakdown — exposed for provenance + UI
            "reliability":      round(source_reliability, 3),
            "conflict_penalty": round(conflict_penalty, 3),
            "agreement_boost":  round(agreement_boost, 3),
        })

    return sorted(results, key=lambda r: r["trust"], reverse=True)