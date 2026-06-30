"""
Provenance Generator.
Turns a resolved field result into a structured ProvenanceEntry,
explaining what was selected, from where, by what method, with what
trust, and why.

Stores:
  - normalization_trace: e.g. "6374071150 -> +916374071150"
  - confidence_breakdown: {reliability, conflict_penalty, agreement_boost}
"""
from typing import Optional
from schemas.canonical import ProvenanceEntry


def build_reasons(resolved: dict, strategy: str, was_conflict: bool) -> list:
    reasons = []

    # Use the number of sources that AGREED on the winning value,
    # not the total number of sources that offered any value for this field.
    # (A field with 3 sources but only 1 agreeing still gets "single source".)
    n_agreeing = len(resolved.get("sources", []))
    if n_agreeing > 1:
        reasons.append(f"Confirmed by {n_agreeing} independent sources")
    else:
        reasons.append("Supported by a single source")

    if was_conflict:
        reasons.append("Selected over conflicting value(s) from other sources")

    # Formula breakdown as a readable reason (3-factor only)
    r  = resolved.get("reliability", 0)
    cp = resolved.get("conflict_penalty", 0)
    ab = resolved.get("agreement_boost", 0)
    reasons.append(
        f"Trust = {r:.2f} (reliability) x (1 - {cp:.2f}) (conflict) x {ab:.2f} (agreement)"
    )
    reasons.append(f"Resolution strategy: {strategy}")
    return reasons


def build_provenance(
    field: str,
    resolved: dict,
    strategy: str,
    normalization: Optional[str],
    was_conflict: bool,
    raw_value: Optional[str] = None,       # original value before normalization
    competing_values: Optional[list] = None, # all competing values evaluated
) -> ProvenanceEntry:
    # Build normalization trace only when an actual transformation occurred
    norm_trace = None
    if raw_value is not None and str(raw_value) != str(resolved["value"]):
        norm_trace = f"{raw_value} -> {resolved['value']}"

    # Confidence breakdown — 3-factor only (no stale validation_score / completeness_score)
    breakdown = None
    if "reliability" in resolved:
        breakdown = {
            "reliability":      resolved["reliability"],
            "conflict_penalty": resolved["conflict_penalty"],
            "agreement_boost":  resolved["agreement_boost"],
        }

    comp_entries = []
    if competing_values:
        for cv in competing_values:
            comp_entries.append({
                "value":            cv["value"],
                "sources":          cv["sources"],
                "trust":            cv["trust"],
                "selected":         str(cv["value"]) == str(resolved["value"]),
                "reliability":      cv.get("reliability"),
                "conflict_penalty": cv.get("conflict_penalty"),
                "agreement_boost":  cv.get("agreement_boost"),
            })

    return ProvenanceEntry(
        field=field,
        value=resolved["value"],
        source=",".join(resolved["sources"]),
        method=",".join(resolved["methods"]),
        normalization=normalization if norm_trace else None,
        normalization_trace=norm_trace,
        trust=resolved["trust"],
        reasons=build_reasons(resolved, strategy, was_conflict),
        confidence_breakdown=breakdown,
        competing_values=comp_entries,
    )