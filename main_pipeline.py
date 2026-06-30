"""
Pipeline orchestration: source detection -> parse -> map -> extract ->
match -> resolve -> golden record -> project -> validate.

This module contains the engine; main.py (CLI) just wires inputs/config
to this function and prints the result.

Key design points:
  - Handles 6-tuple claims (field, value, source_type, source_name, method, raw_value)
  - Assembles Experience[] from resume experience_entry claims (with dates + summary)
  - Assembles Education[] from resume education_entry claims
  - Falls back to current_company/title for experience if no parsed entries exist
  - Assembles links.github, links.portfolio, links.linkedin from all sources
  - Parses location_raw into location.city / location.country
  - Uses OVERALL_CONFIDENCE_WEIGHTS from settings for weighted overall confidence
  - score_claims_for_field called ONCE per field (not twice)
"""
import warnings
import uuid
from collections import defaultdict
from typing import List, Dict, Any, Optional

from parsers.registry import run_parser
from mapper.schema_mapper import map_record
from extractor.extractor import process_claims
from matcher.matcher import cluster_records
from resolver.resolver import resolve_field, FIELD_STRATEGY
from trust.trust import score_claims_for_field
from provenance.provenance import build_provenance
from projection.projector import project
from schemas.canonical import (
    CanonicalCandidate, Skill, ProvenanceEntry, Experience, Education, Location
)
from canonicalizer.canonicalizer import canonicalize_company
from config.settings import SOURCE_RELIABILITY, OVERALL_CONFIDENCE_WEIGHTS
from normalizer.normalizer import normalize_country


def build_golden_records(sources: Dict[str, str]) -> List[CanonicalCandidate]:
    """
    sources: dict mapping source_type -> path/handle, e.g.
      {"csv": "sample_data/recruiters.csv", "resume": "sample_data/resume.pdf"}
    Missing keys are simply not parsed -- a missing source never crashes the run.
    """
    all_records = []
    for source_type, path in sources.items():
        all_records.extend(run_parser(source_type, path))

    per_record_claims = []
    for record in all_records:
        raw_claims = map_record(record)
        processed = process_claims(raw_claims)
        per_record_claims.append(processed)

    if not per_record_claims:
        return []

    clusters = cluster_records(per_record_claims)

    golden_records = []
    for cluster in clusters:
        cluster_claims = []
        for idx in cluster:
            cluster_claims.extend(per_record_claims[idx])
        if not cluster_claims:
            # A source file parsed to zero usable claims — skip rather than
            # emitting a record with no evidence.
            warnings.warn(
                f"Empty cluster (indices {cluster}) — source produced no valid claims; "
                "record skipped.  Check that the source file has parseable content.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        golden_records.append(_build_one_record(cluster_claims))

    return golden_records


def _raw_value(claim) -> Optional[str]:
    """Extract the raw_value (6th element) from a claim tuple, or None."""
    return claim[5] if len(claim) > 5 else None


def _build_one_record(claims) -> CanonicalCandidate:
    by_field = defaultdict(list)
    for claim in claims:
        by_field[claim[0]].append(claim)

    candidate = CanonicalCandidate(candidate_id=str(uuid.uuid4())[:8])

    # field_trusts: {canonical_field_name -> trust_score} for weighted confidence
    field_trusts: Dict[str, float] = {}

    # ── Scalar "best" fields ──────────────────────────────────────────────────
    for field in ("full_name", "current_company", "title", "headline", "years_experience"):
        field_claims = by_field.get(field, [])
        # Score ONCE, pass to both resolve and provenance (Issue 6.1)
        scored = score_claims_for_field(field_claims)
        resolved = _pick_best(scored, field, field_claims)
        if resolved:
            was_conflict = len(set(str(c[1]) for c in field_claims)) > 1
            raw = next((_raw_value(c) for c in field_claims if _raw_value(c)), None)
            prov = build_provenance(
                field, resolved, FIELD_STRATEGY.get(field, "best"),
                normalization=None, was_conflict=was_conflict, raw_value=raw,
                competing_values=scored,
            )
            candidate.provenance.append(prov)
            field_trusts[field] = resolved["trust"]

            if field == "full_name":
                candidate.full_name = resolved["value"]
            elif field == "years_experience":
                candidate.years_experience = float(resolved["value"])
            elif field == "headline":
                candidate.headline = resolved["value"]

    # ── List fields: emails, phones ──────────────────────────────────────────
    for field, target_attr, norm_label in (
        ("email", "emails", "lowercase"),
        ("phone", "phones", "E164"),
    ):
        field_claims = by_field.get(field, [])
        scored = score_claims_for_field(field_claims)
        resolved_list = [r for r in scored if not r["below_floor"]]
        values = []
        for r in resolved_list:
            was_conflict = len(resolved_list) > 1
            raw = next((_raw_value(c) for c in field_claims
                        if str(c[1]) == str(r["value"]) and _raw_value(c)), None)
            prov = build_provenance(
                field, r, "concat",
                normalization=norm_label, was_conflict=was_conflict, raw_value=raw,
                competing_values=scored,
            )
            candidate.provenance.append(prov)
            values.append(r["value"])
        setattr(candidate, target_attr, values)
        if values:
            # Use max trust of the list for weight purposes
            field_trusts[field] = max(r["trust"] for r in resolved_list)

    # ── Skills ───────────────────────────────────────────────────────────────
    skill_claims = by_field.get("skill", [])
    scored_skills = score_claims_for_field(skill_claims)
    resolved_skills = [r for r in scored_skills if not r["below_floor"]]
    for r in resolved_skills:
        candidate.skills.append(Skill(
            name=r["value"], confidence=r["trust"], sources=r["sources"]
        ))
        candidate.provenance.append(build_provenance(
            "skill", r, "concat",
            normalization="canonical", was_conflict=False,
            competing_values=scored_skills,
        ))
    if resolved_skills:
        field_trusts["skill"] = sum(r["trust"] for r in resolved_skills) / len(resolved_skills)

    # ── Links: github_url, portfolio, linkedin_url ──────────────────────────
    for field, link_attr in (
        ("github_url",   "github"),
        ("portfolio",    "portfolio"),
        ("linkedin_url", "linkedin"),
    ):
        field_claims = by_field.get(field, [])
        if field_claims:
            scored = score_claims_for_field(field_claims)
            best = next((r for r in scored if not r["below_floor"]), None)
            if best:
                setattr(candidate.links, link_attr, best["value"])
                candidate.provenance.append(build_provenance(
                    field, best, "best",
                    normalization=None, was_conflict=len(scored) > 1,
                    competing_values=scored,
                ))

    # ── affiliation_raw (GitHub self-reported affiliation) ───────────────────
    aff_claims = by_field.get("affiliation_raw", [])
    if aff_claims:
        scored = score_claims_for_field(aff_claims)
        best = next((r for r in scored if not r["below_floor"]), None)
        if best:
            candidate.affiliation_raw = str(best["value"]).lstrip("@").strip() or None

    # ── Location: parse location_raw from GitHub or other sources ────────────
    loc_claims = by_field.get("location_raw", [])
    if loc_claims:
        scored = score_claims_for_field(loc_claims)
        best = next((r for r in scored if not r["below_floor"]), None)
        if best:
            raw_loc = str(best["value"]).strip()
            parts = [p.strip() for p in raw_loc.split(",") if p.strip()]
            city = parts[0] if len(parts) >= 1 else None
            country_raw = parts[-1] if len(parts) >= 2 else None
            country_code = normalize_country(country_raw) if country_raw else None
            candidate.location = Location(
                city=city,
                country=country_code or (country_raw if country_raw and len(parts) >= 2 else None),
            )

    # ── Experience: parsed entries from resume ────────────────────────────────
    exp_entries_built = False
    for claim in by_field.get("experience_entry", []):
        entry = claim[1]  # dict with company/title/start/end/summary
        if not isinstance(entry, dict):
            continue
        company = entry.get("company")
        if company:
            company = canonicalize_company(company)

        # Compute trust from settings rather than hardcoding
        exp_trust = round(SOURCE_RELIABILITY.get("resume", 0.70) * 0.75, 3)

        exp = Experience(
            company=company,
            title=entry.get("title"),
            employment_type=entry.get("employment_type"),
            start=entry.get("start"),
            end=entry.get("end"),
            summary=entry.get("summary") or [],   # never None
            extraction_quality=entry.get("extraction_quality"),
        )
        candidate.experience.append(exp)
        exp_entries_built = True

        candidate.provenance.append(ProvenanceEntry(
            field="experience",
            value=f"{company or '?'} | {entry.get('title') or '?'}",
            source=claim[2],
            method=claim[4],
            normalization=None,
            trust=exp_trust,
            reasons=[
                f"Parsed from resume: {entry.get('start', '')} \u2013 {entry.get('end', '')}",
                "Resolution strategy: concat",
            ],
            confidence_breakdown={
                "reliability":      SOURCE_RELIABILITY.get("resume", 0.70),
                "conflict_penalty": 0.0,
                "agreement_boost":  0.75,
            },
        ))
        field_trusts.setdefault("experience", exp_trust)

    # Fallback: if no parsed experience entries, use current_company/title from ATS/CSV
    if not exp_entries_built:
        company_prov = next((p for p in candidate.provenance if p.field == "current_company"), None)
        title_prov   = next((p for p in candidate.provenance if p.field == "title"), None)
        if company_prov or title_prov:
            candidate.experience.append(Experience(
                company=company_prov.value if company_prov else None,
                title=title_prov.value if title_prov else None,
                summary=[],
            ))

    # ── Education ─────────────────────────────────────────────────────────────
    for claim in by_field.get("education_entry", []):
        entry = claim[1]
        if not isinstance(entry, dict):
            continue
        edu_trust = round(SOURCE_RELIABILITY.get("resume", 0.70) * 0.75, 3)
        edu = Education(
            institution=entry.get("institution"),
            degree=entry.get("degree"),
            field=entry.get("field"),
            start_year=entry.get("start_year"),
            end_year=entry.get("end_year"),
            cgpa=entry.get("cgpa"),
        )
        candidate.education.append(edu)

        candidate.provenance.append(ProvenanceEntry(
            field="education",
            value=f"{entry.get('institution', '?')} | {entry.get('degree', '?')}",
            source=claim[2],
            method=claim[4],
            normalization=None,
            trust=edu_trust,
            reasons=[
                f"Parsed from resume — field: {entry.get('field', 'N/A')}, year: {entry.get('end_year', 'N/A')}",
                "Resolution strategy: concat",
            ],
            confidence_breakdown={
                "reliability":      SOURCE_RELIABILITY.get("resume", 0.70),
                "conflict_penalty": 0.0,
                "agreement_boost":  0.75,
            },
        ))
        field_trusts.setdefault("education", edu_trust)

    # ── Overall confidence (weighted by field importance) ─────────────────────
    # Uses OVERALL_CONFIDENCE_WEIGHTS from settings.py. Fields not listed
    # in the weight map contribute their share of the remaining weight equally.
    # The worst-field penalty is blended in as a 30% floor modifier so one
    # low-confidence field drags the overall down without dominating it.
    candidate.overall_confidence = _compute_overall_confidence(field_trusts)

    return candidate


def _pick_best(scored: List[dict], field: str, field_claims: list) -> Optional[dict]:
    """
    Thin wrapper: applies the resolver's field filter then picks the best
    scored result. Avoids calling score_claims_for_field a second time.
    """
    from resolver.resolver import _filter_claims, TRUST_FLOOR
    filtered_claims = _filter_claims(field, field_claims)
    # Re-score on filtered subset only if filtering actually removed anything
    if len(filtered_claims) != len(field_claims):
        scored = score_claims_for_field(filtered_claims)
    if not scored:
        return None
    top = scored[0]
    return None if top["trust"] < TRUST_FLOOR else top


def _compute_overall_confidence(field_trusts: Dict[str, float]) -> float:
    """
    Weighted average of per-field trust scores using OVERALL_CONFIDENCE_WEIGHTS.
    Fields present but not in the weight map share the residual weight equally.
    Blended with a 30% worst-field penalty to prevent high-average profiles
    from masking one unreliable field.
    """
    if not field_trusts:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0
    unweighted_fields = []

    for f, trust in field_trusts.items():
        w = OVERALL_CONFIDENCE_WEIGHTS.get(f)
        if w is not None:
            weighted_sum += w * trust
            total_weight += w
        else:
            unweighted_fields.append(trust)

    # Distribute remaining weight equally among unweighted fields
    residual = max(0.0, 1.0 - total_weight)
    if unweighted_fields:
        per_field_w = residual / len(unweighted_fields)
        for trust in unweighted_fields:
            weighted_sum += per_field_w * trust
            total_weight += per_field_w

    avg = weighted_sum / total_weight if total_weight > 0 else 0.0
    worst = min(field_trusts.values())
    # 70% weighted average + 30% worst-field penalty
    return round(0.70 * avg + 0.30 * worst, 3)


def run_pipeline(sources: Dict[str, str], config: Optional[Dict[str, Any]] = None):
    records = build_golden_records(sources)
    if config is None:
        return [r.model_dump() for r in records]

    projected = []
    for r in records:
        projected.append(project(r.model_dump(), config))
    return projected