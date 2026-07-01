"""
Provenance Generator.
Turns a scored field result into a structured ProvenanceEntry with
full explainability: what value, from where, how extracted, with what
confidence, and why that confidence was assigned.

confidence_breakdown contains:
  base_reliability    — source reliability x method quality
  agreement_bonus     — +0.15 (2+ sources agree) / +0.05 (1 source) / +0.00
  conflict_penalty    — 0.0 / 0.20 / 0.35 / 0.50 depending on conflict count
  normalization_bonus — +0.05 when normalization actually transformed the value
  confirmed_sources   — source types that provided this value
  conflicting_sources — capable sources that provided a different value
  no_evidence_sources — capable active sources that provided nothing
  final_confidence    — the clamped sum
"""
from typing import Optional
from schemas.canonical import ProvenanceEntry

# Human-friendly labels for normalization types
_NORM_LABELS = {
    "E164":       "Normalized phone number to E.164 international format.",
    "lowercase":  "Normalized email address to lowercase.",
    "canonical":  "Canonicalized to standard form.",
}


def build_reasons(
    resolved: dict,
    strategy: str,
    was_conflict: bool,
    normalization: Optional[str] = None,
    norm_trace: Optional[str] = None,
) -> list:
    """Generate a list of human-readable explanation strings for this confidence score."""
    reasons = []

    confirmed   = resolved.get("confirmed_sources", [])
    conflicting = resolved.get("conflicting_sources", [])

    # ── Confirmation / single-source explanation ──────────────────────────────
    if len(confirmed) >= 2:
        sources_str = " and ".join(confirmed)
        reasons.append(f"Confirmed by {sources_str}.")
    else:
        # Single source but no conflict — confidence is retained, not penalised
        reasons.append(
            "Single-source value retained because no conflicting information exists."
        )

    # ── Conflict explanation ──────────────────────────────────────────────────
    if conflicting:
        n = len(conflicting)
        src_str = ", ".join(conflicting)
        reasons.append(
            f"{'One conflicting' if n == 1 else str(n) + ' conflicting'} "
            f"value{'s' if n > 1 else ''} detected from {src_str}."
        )
    else:
        reasons.append("No conflicting evidence found.")

    # ── Normalization explanation ─────────────────────────────────────────────
    norm_bonus = resolved.get("normalization_bonus", 0)
    if norm_bonus > 0:
        if normalization and normalization in _NORM_LABELS:
            reasons.append(_NORM_LABELS[normalization])
        elif norm_trace:
            reasons.append(f"Normalized: {norm_trace}.")
        else:
            reasons.append("Value was normalized to canonical form.")

    # ── Formula breakdown ─────────────────────────────────────────────────────
    br  = resolved.get("base_reliability", 0)
    ab  = resolved.get("agreement_bonus", 0)
    cp  = resolved.get("conflict_penalty", 0)
    nb  = resolved.get("normalization_bonus", 0)
    conf = resolved.get("trust", 0)
    reasons.append(
        f"Confidence = {br:.2f} (base) + {ab:.2f} (agreement) "
        f"- {cp:.2f} (conflict) + {nb:.2f} (normalisation) = {conf:.3f}"
    )
    reasons.append(f"Resolution strategy: {strategy}")
    return reasons


def build_provenance(
    field: str,
    resolved: dict,
    strategy: str,
    normalization: Optional[str],
    was_conflict: bool,
    raw_value: Optional[str] = None,
    competing_values: Optional[list] = None,
) -> ProvenanceEntry:
    # Normalization trace — only when an actual transformation occurred
    norm_trace = None
    if raw_value is not None and str(raw_value) != str(resolved["value"]):
        norm_trace = f"{raw_value} -> {resolved['value']}"

    # Full additive confidence breakdown
    breakdown = None
    if "base_reliability" in resolved:
        breakdown = {
            "base_reliability":    resolved["base_reliability"],
            "agreement_bonus":     resolved["agreement_bonus"],
            "conflict_penalty":    resolved["conflict_penalty"],
            "normalization_bonus": resolved["normalization_bonus"],
            "confirmed_sources":   resolved.get("confirmed_sources", []),
            "conflicting_sources": resolved.get("conflicting_sources", []),
            "no_evidence_sources": resolved.get("no_evidence_sources", []),
            "final_confidence":    resolved["trust"],
        }

    # Competing values for the Conflict Dashboard
    comp_entries = []
    if competing_values:
        for cv in competing_values:
            comp_entries.append({
                "value":               cv["value"],
                "sources":             cv["sources"],
                "trust":               cv["trust"],
                "selected":            str(cv["value"]) == str(resolved["value"]),
                "base_reliability":    cv.get("base_reliability"),
                "agreement_bonus":     cv.get("agreement_bonus"),
                "conflict_penalty":    cv.get("conflict_penalty"),
                "normalization_bonus": cv.get("normalization_bonus"),
                "confirmed_sources":   cv.get("confirmed_sources", []),
                "conflicting_sources": cv.get("conflicting_sources", []),
            })

    return ProvenanceEntry(
        field=field,
        value=resolved["value"],
        source=",".join(resolved["sources"]),
        method=",".join(resolved["methods"]),
        normalization=normalization if norm_trace else None,
        normalization_trace=norm_trace,
        trust=resolved["trust"],
        reasons=build_reasons(
            resolved, strategy, was_conflict,
            normalization=normalization, norm_trace=norm_trace,
        ),
        confidence_breakdown=breakdown,
        competing_values=comp_entries,
    )