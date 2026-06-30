# TrustProfile — Multi-Source Candidate Data Transformer

Builds one trustworthy canonical candidate profile from multiple
heterogeneous, conflicting, and possibly-missing data sources.

Core principle: **honestly-empty beats wrong-but-confident.** Every
field is traceable to a source and a method, and a value is only
asserted if it clears a minimum trust threshold — otherwise it's
returned as `null` rather than guessed.

## Quickstart

```bash
pip install -r requirements.txt

# Default schema output, all sources
python main.py \
  --csv sample_data/recruiters.csv \
  --ats sample_data/ats.json \
  --resume sample_data/resume.txt \
  --notes sample_data/notes.txt \
  --out output_default.json

# Custom runtime config (subset/rename/normalize fields)
python main.py \
  --csv sample_data/recruiters.csv \
  --ats sample_data/ats.json \
  --resume sample_data/resume.txt \
  --notes sample_data/notes.txt \
  --config config/sample_config.json \
  --out output_custom.json

# Include a live GitHub source (public API, no auth needed)
python main.py --github octocat --csv sample_data/recruiters.csv

# Run tests
pytest tests/ -v
```

Any combination of `--csv / --ats / --resume / --notes / --github` is
valid — at minimum, provide one structured source (`--csv` or `--ats`)
and one unstructured source (`--resume`, `--notes`, or `--github`).

## Pipeline

```
Sources (CSV, ATS JSON, GitHub, Resume, Notes)
        │
1. PARSE           — one parser per source (registry pattern), isolated
        │             failure: a bad/missing source never crashes the run
2. SCHEMA-MAP        — map each source's native field names to canonical
        │              names (e.g. ATS "candidateName" -> "full_name")
3. EXTRACT           — regex/rule-based extraction for unstructured text
        │              (deliberately no LLM — keeps the pipeline fully
        │              deterministic; see "Descoped" below)
4. CANONICALIZE      — collapse semantically-equivalent values
        │              ("Google Inc." -> "Google", "CPP" -> "C++")
5. NORMALIZE         — format standardization: phones -> E.164,
        │              dates -> YYYY-MM, country -> ISO-3166 alpha-2,
        │              emails -> lowercase
6. VALIDATE          — drop malformed values (invalid email/phone/etc.)
        │              rather than keep or invent them
7. MATCH             — cluster records into one-per-candidate, using
        │              email > phone > fuzzy name+company (RapidFuzz)
8. TRUST SCORE       — trust = source_reliability x (1-conflict_penalty)
        │              x agreement_boost, per field, per claimed value
        │              (see "Trust formula" below)
9. RESOLVE           — apply a named resolution function per field
        │              (Best / Concat), selecting only from OBSERVED
        │              values — never fabricated
10. PROVENANCE        — record {field, value, source, method,
        │               normalization, trust, reasons[]} for every value
11. GOLDEN RECORD      — assembled canonical record (internal, rich)
        │
12. PROJECT            — apply runtime config: field subset, rename,
        │               per-field normalize override, provenance/
        │               confidence toggle, missing-value policy
13. SCHEMA VALIDATE     — validate the projected output against the
        │               requested shape before returning
        ▼
    Output JSON
```

## Trust formula

```
trust(value) = source_reliability x (1 - conflict_penalty) x agreement_boost
```

- **source_reliability**: static prior per source type (`config/settings.py`)
  — ATS 0.95, CSV 0.90, GitHub 0.85, Resume 0.70, Notes 0.50.
- **conflict_penalty**: grows with how far this value is from *other*
  claimed values for the same field, weighted by those sources'
  reliability. Type-specific distance: Levenshtein-based similarity
  (RapidFuzz) for strings, normalized absolute difference for numbers.
  Skipped for multi-value/union fields (skills, emails, phones) where
  several distinct values legitimately co-exist rather than compete.
- **agreement_boost**: rises when multiple independent sources claim
  the same value; a single uncorroborated source never reaches the
  top trust tier.
- **Trust floor** (`TRUST_FLOOR = 0.40`): below this, the value is
  withheld (`null`) instead of asserted — this is the direct
  implementation of "honestly-empty over wrong-but-confident."
- **overall_confidence** is computed as `0.5 x average + 0.5 x weakest`
  field trust, not a flat average — so one unreliable field can't hide
  behind several strong ones.

This 3-factor structure, and the conflict/agreement mechanics, follow
the data-fusion approach in Michelfeit, Knap & Nečaský, *"Linked Data
Integration with Conflicts"* (arXiv:1410.7990) — adapted here for
candidate-profile fields instead of RDF triples.

## Resolution functions

Per-field, selected in `resolver/resolver.py`:
- `Best` — highest-trust value wins (full_name, current_company, title, headline, years_experience)
- `Concat` — union of all above-floor values (emails, phones, skills)

(`BestSource` and `Vote` are implemented and available for future fields
that need them, e.g. always preferring ATS for a specific field.)

## Matching strategy

Priority: exact normalized email match → exact normalized phone match
→ fuzzy name+company match (RapidFuzz, threshold 88) as a fallback
only. Emails/phones are treated as stronger identifiers than names,
since names collide far more often across a real candidate pool.

## Edge cases handled

1. **Missing source** — file not provided or not found → that source
   contributes nothing, run continues normally.
2. **Conflicting values across sources** (e.g. "Google" vs "Google Inc.")
   — resolved by canonicalization first, then trust scoring if a true
   conflict remains; see `test_conflicting_company_names_resolve_after_canonicalization`.
3. **Malformed CSV/JSON row** — skipped with a warning, never crashes
   the batch; see `test_missing_source_does_not_crash`.
4. **Low-trust single-source claim** — a value seen from only one
   low-reliability source (e.g. recruiter notes) can fall below the
   trust floor and is withheld as `null` rather than asserted; see
   `test_low_trust_single_source_value_is_withheld`.
5. **Same candidate, different spelling/source combos** — merged via
   email/phone match keys rather than name, since names are an
   unreliable join key.

## Assumptions

- Email and phone are stronger identifiers than name for matching.
- Canonicalization happens before conflict scoring (so "Google Inc."
  and "Google" are treated as agreement, not conflict).
- The internal canonical record is never mutated by the projection
  layer — projection is a read-only view.
- A field with zero supporting claims is `null`; the system never
  invents a default.

## What was descoped (and why)

- **LLM-based extraction for resumes/notes** — considered, but
  removed from the core pipeline because hosted LLM calls aren't
  guaranteed reproducible across model versions even at temperature 0,
  which conflicts with the assignment's hard determinism constraint
  (same input → same output). Rule-based regex/heuristic extraction
  is used instead; LLM extraction is a reasonable future enhancement
  once reproducibility tradeoffs are evaluated.
- **Blocking before matching** — a real technique for avoiding O(n²)
  comparisons at large scale (millions of records), but unnecessary
  at the assignment's scale (thousands of candidates, small per-run
  source counts). Noted here as a scale-up path rather than built.
- **LinkedIn parsing** — no public API without authentication/scraping
  concerns; out of scope for the 2-day window.
- **OCR for scanned resumes** — `pdfplumber` handles text-layer PDFs;
  scanned/image-only resumes are out of scope.

## Project structure

```
candidate-transformer/
  parsers/          one parser per source type + registry
  mapper/           source field names -> canonical field names
  extractor/         canonicalize + normalize + validate raw claims
  canonicalizer/     semantic-equivalence normalization
  normalizer/        format normalization (E.164, ISO dates, etc.)
  validator/         claim validation + final schema validation
  matcher/           entity resolution / clustering
  trust/             the trust scoring formula
  resolver/          named per-field resolution functions
  provenance/        builds provenance entries
  projection/         runtime-config-driven output reshaping
  schemas/            canonical Pydantic models
  config/             source reliability config + sample projection config
  sample_data/        sample CSV/ATS/resume/notes for the demo
  tests/              pytest suite, including edge cases
  main.py             CLI entrypoint
  main_pipeline.py    pipeline orchestration
```
