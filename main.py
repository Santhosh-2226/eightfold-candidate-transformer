#!/usr/bin/env python3
"""
CLI entrypoint for the Candidate Data Transformer.

Usage:
  python main.py --csv sample_data/recruiters.csv \
                  --ats sample_data/ats.json \
                  --resume sample_data/resume.txt \
                  --notes sample_data/notes.txt \
                  --github octocat \
                  --config config/sample_config.json \
                  --out output.json
"""
import argparse
import json
import sys

from main_pipeline import run_pipeline


def main():
    p = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    p.add_argument("--csv", help="path to recruiter CSV export")
    p.add_argument("--ats", help="path to ATS JSON blob")
    p.add_argument("--resume", help="path to resume file (.pdf or .txt)")
    p.add_argument("--notes", help="path to recruiter notes .txt")
    p.add_argument("--github", help="GitHub username or profile URL")
    p.add_argument("--config", help="path to runtime projection config JSON "
                                     "(omit for default full schema output)")
    p.add_argument("--out", help="path to write output JSON (default: stdout)")
    args = p.parse_args()

    sources = {}
    if args.csv:
        sources["csv"] = args.csv
    if args.ats:
        sources["ats_json"] = args.ats
    if args.resume:
        sources["resume"] = args.resume
    if args.notes:
        sources["notes"] = args.notes
    if args.github:
        sources["github"] = args.github

    if not sources:
        print("error: at least one source must be provided", file=sys.stderr)
        sys.exit(1)

    config = None
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    result = run_pipeline(sources, config)
    output_str = json.dumps(result, indent=2, default=str)

    if args.out:
        with open(args.out, "w") as f:
            f.write(output_str)
        print(f"wrote output to {args.out}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
