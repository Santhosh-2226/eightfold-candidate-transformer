"""
Canonical internal schema for a candidate profile.
This is the FIXED internal representation every source gets mapped into,
before any runtime projection config is applied.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str
    confidence: float
    sources: List[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    employment_type: Optional[str] = None   # "Full Time" / "Part Time" / "Internship" / etc.
    start: Optional[str] = None             # YYYY-MM
    end: Optional[str] = None               # YYYY-MM or "Present"
    summary: List[str] = Field(default_factory=list)
    extraction_quality: Optional[str] = None  # "complete" | "partial" | "low_confidence"


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    cgpa: Optional[float] = None


class ProvenanceEntry(BaseModel):
    field: str
    value: Any = None
    source: Optional[str] = None
    method: Optional[str] = None
    normalization: Optional[str] = None
    normalization_trace: Optional[str] = None   # e.g. "6374071150 → +916374071150"
    trust: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    confidence_breakdown: Optional[Dict[str, float]] = None  # {reliability, conflict_penalty, agreement_boost}
    competing_values: List[Dict[str, Any]] = Field(default_factory=list)  # all observed values with their scores


class CanonicalCandidate(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    affiliation_raw: Optional[str] = None   # GitHub/social self-reported affiliation (not employer)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = 0.0


class RawRecord(BaseModel):
    """
    Intermediate object every parser must return.
    Loosely typed on purpose -- parsers only know their own source's shape.
    `source_type` and `source_name` are used downstream for trust scoring.
    """
    source_type: str       # "csv" | "ats_json" | "github" | "resume" | "notes"
    source_name: str       # human-readable, e.g. "recruiter_csv_row_3"
    fields: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)