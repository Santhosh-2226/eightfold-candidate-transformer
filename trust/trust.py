"""
Trust Engine — Deterministic Additive Confidence Model.

Confidence formula:

    confidence = base_source_reliability
               + agreement_bonus
               - conflict_penalty
               + normalization_bonus
    
    clamped to [0.0, 1.0]

Evidence is classified per capable source (from FIELD_COVERAGE):

    CONFIRMED    — source provided the same normalized value
    CONFLICT     — source provided a different normalized value
    NO_EVIDENCE  — capable source provided no value for this field

Key principle: Missing evidence is NOT treated as disagreement.
Only explicit CONFLICT reduces confidence.

This is mathematically cleaner and consistent with the Eightfold
assignment requirement: "Wrong-but-confident is worse than honestly-empty."
"""
from typing import List, Tuple, Optional, Set
from config.settings import (
    SOURCE_RELIABILITY, TRUST_FLOOR, METHOD_RELIABILITY_MULTIPLIER, FIELD_COVERAGE
)

Claim = Tuple[str, object, str, str, str]  # field, value, source_type, source_name, method

# Fields where multiple distinct values co-exist legitimately.
# Conflicts are not meaningful for these — a different skill from the same source
# is a union entry, not a dispute.
MULTI_VALUE_FIELDS = {"skill", "email", "phone"}


def _method_multiplier(methods: list) -> float:
    """Highest applicable method multiplier across the methods that produced this value."""
    mults = [METHOD_RELIABILITY_MULTIPLIER.get(m, 1.0) for m in methods]
    return max(mults) if mults else 1.0


def score_claims_for_field(
    claims_for_field: List[Claim],
    active_sources: Optional[Set[str]] = None,
) -> List[dict]:
    """
    Score all claims for ONE canonical field of ONE candidate.

    Parameters
    ----------
    claims_for_field : list of 5- or 6-tuples
        (field, value, source_type, source_name, method[, raw_value])
    active_sources : set of source_type strings present in this candidate's cluster.
        Used to correctly classify NO_EVIDENCE (a capable source that IS active
        but simply didn't produce a value for this field).
        If None, falls back to the sources that actually provided values.

    Returns
    -------
    List of scored dicts, highest confidence first.
    Each dict contains the full additive breakdown for provenance + UI.
    """
    if not claims_for_field:
        return []

    field_name = claims_for_field[0][0]

    # ── Group claims by normalized value ─────────────────────────────────────
    # Track raw_value (6th element) for normalization bonus detection.
    # raw_value is non-None only when extractor actually transformed the value.
    groups: dict = {}
    for claim in claims_for_field:
        field, value, source_type, source_name, method = claim[:5]
        raw_value = claim[5] if len(claim) > 5 else None
        key = str(value).strip().lower()
        groups.setdefault(key, []).append(
            (value, source_type, source_name, method, raw_value)
        )

    # Source types that provided ANY value for this field
    all_providing_sources: Set[str] = {
        st for entries in groups.values() for (_, st, _, _, _) in entries
    }

    # Capable sources = those listed in FIELD_COVERAGE for this field
    # Capable + active = those both listed AND present in this cluster
    capable: Set[str] = set(FIELD_COVERAGE.get(field_name, []))
    if active_sources is not None:
        capable_active = capable & active_sources
    else:
        # Fallback: only consider sources that actually provided something
        capable_active = capable & all_providing_sources

    results = []

    for key, entries in groups.items():
        # ── Evidence classification ───────────────────────────────────────────
        # CONFIRMED: source types that provided this exact value
        confirmed_st: Set[str] = {st for (_, st, _, _, _) in entries}

        # CONFLICT: capable active sources that provided a DIFFERENT value.
        # Not applicable for multi-value fields (skills are a union, not a dispute).
        if field_name not in MULTI_VALUE_FIELDS:
            conflicting_st: Set[str] = all_providing_sources - confirmed_st
        else:
            conflicting_st = set()

        # NO_EVIDENCE: capable active sources that provided nothing at all
        no_evidence_st: Set[str] = capable_active - confirmed_st - conflicting_st

        confirmed_count = len(confirmed_st)
        conflict_count  = len(conflicting_st)

        # ── base_source_reliability ───────────────────────────────────────────
        # Highest reliability among sources that confirmed this value,
        # scaled by the best extraction method used.
        base_reliabilities = [SOURCE_RELIABILITY.get(st, 0.5) for (_, st, _, _, _) in entries]
        methods_for_value  = [m for (_, _, _, m, _) in entries]
        method_mult = _method_multiplier(methods_for_value)
        base_reliability = min(1.0, max(base_reliabilities) * method_mult)

        # ── agreement_bonus ───────────────────────────────────────────────────
        # Counts CONFIRMED sources only. NO_EVIDENCE is neutral — it does NOT
        # reduce this bonus. A single source with no conflict still earns +0.05.
        if confirmed_count >= 2:
            agreement_bonus = 0.15    # multiple independent sources agree
        elif confirmed_count == 1:
            agreement_bonus = 0.05    # single source, but no conflict
        else:
            agreement_bonus = 0.0

        # ── conflict_penalty ──────────────────────────────────────────────────
        # Only EXPLICIT conflicts reduce confidence.
        # NO_EVIDENCE is completely neutral — missing a field is not a dispute.
        if conflict_count == 0:
            conflict_penalty = 0.0
        elif conflict_count == 1:
            conflict_penalty = 0.20
        elif conflict_count == 2:
            conflict_penalty = 0.35
        else:
            conflict_penalty = 0.50

        # ── normalization_bonus ───────────────────────────────────────────────
        # +0.05 when canonical normalization actually transformed the value
        # (e.g. E.164 phone, lowercase email, canonical company/skill name).
        # raw_value is non-None only when transformation occurred (set by extractor).
        norm_happened = any(rv is not None for (_, _, _, _, rv) in entries)
        normalization_bonus = 0.05 if norm_happened else 0.0

        # ── Final confidence (additive, clamped to [0, 1]) ────────────────────
        confidence = (
            base_reliability
            + agreement_bonus
            - conflict_penalty
            + normalization_bonus
        )
        confidence = round(max(0.0, min(1.0, confidence)), 3)

        results.append({
            # Core output
            "value":               entries[0][0],
            "sources":             sorted(confirmed_st),
            "source_names":        [sn for (_, _, sn, _, _) in entries],
            "methods":             sorted({m for (_, _, _, m, _) in entries}),
            "trust":               confidence,
            "below_floor":         confidence < TRUST_FLOOR,
            # Full additive breakdown — exposed for provenance + UI
            "base_reliability":    round(base_reliability, 3),
            "agreement_bonus":     round(agreement_bonus, 3),
            "conflict_penalty":    round(conflict_penalty, 3),
            "normalization_bonus": round(normalization_bonus, 3),
            # Evidence classification
            "confirmed_sources":   sorted(confirmed_st),
            "conflicting_sources": sorted(conflicting_st),
            "no_evidence_sources": sorted(no_evidence_st),
        })

    return sorted(results, key=lambda r: r["trust"], reverse=True)