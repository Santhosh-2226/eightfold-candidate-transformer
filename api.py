"""
Flask API server for the TrustProfile Candidate Transformer.
Accepts file uploads (CSV, ATS JSON, Resume TXT/PDF, Notes TXT, GitHub username)
and returns the transformed candidate golden records.
"""

import os
import json
import tempfile
import sys

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Ensure the candidate-transformer package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_pipeline import run_pipeline

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

ALLOWED_EXTENSIONS = {
    "csv": [".csv"],
    "ats_json": [".json"],
    "resume": [".txt", ".pdf"],
    "notes": [".txt"],
}


def allowed_file(filename, source_type):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS.get(source_type, [])


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/transform", methods=["POST"])
def transform():
    """
    Accepts multipart form data with optional fields:
      - csv: recruiter CSV file
      - ats_json: ATS JSON file
      - resume: resume .txt or .pdf
      - notes: recruiter notes .txt
      - github: GitHub username (text field)
      - config: optional projection config JSON file

    Returns: { "success": true, "candidates": [...], "count": N }
    """
    sources = {}
    tmp_files = []

    try:
        # Handle file uploads
        for source_type in ("csv", "ats_json", "resume", "notes"):
            file_key = source_type
            if file_key in request.files:
                f = request.files[file_key]
                if f and f.filename:
                    # Save to a temp file with correct extension
                    ext = os.path.splitext(f.filename)[1].lower() or ".tmp"
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=ext, mode="wb"
                    )
                    f.save(tmp.name)
                    tmp.close()
                    tmp_files.append(tmp.name)
                    sources[source_type] = tmp.name

        # Handle GitHub username (text field)
        github = request.form.get("github", "").strip()
        if github:
            # Strip URL to just username if full URL provided
            if "github.com/" in github:
                github = github.rstrip("/").split("github.com/")[-1]
            sources["github"] = github

        if not sources:
            return jsonify({
                "success": False,
                "error": "At least one source is required (CSV, ATS JSON, Resume, Notes, or GitHub username)."
            }), 400

        # Optional projection config
        config = None
        if "config" in request.files:
            cfg_file = request.files["config"]
            if cfg_file and cfg_file.filename:
                config_tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".json", mode="wb"
                )
                cfg_file.save(config_tmp.name)
                config_tmp.close()
                tmp_files.append(config_tmp.name)
                with open(config_tmp.name, "r") as cf:
                    config = json.load(cf)

        # Run the pipeline
        result = run_pipeline(sources, config)

        return jsonify({
            "success": True,
            "candidates": result,
            "count": len(result),
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }), 500

    finally:
        # Clean up temp files
        for path in tmp_files:
            try:
                os.unlink(path)
            except Exception:
                pass


@app.route("/api/sample", methods=["GET"])
def sample():
    """Returns sample data to pre-populate the form for demo purposes."""
    sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    
    samples = {}
    for filename in os.listdir(sample_dir):
        filepath = os.path.join(sample_dir, filename)
        if os.path.isfile(filepath) and not filename.endswith(".json"):
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    samples[filename] = f.read()
            except Exception:
                pass
    return jsonify(samples)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "TrustProfile Candidate Transformer"})


if __name__ == "__main__":
    print("TrustProfile API starting on http://localhost:5000")
    app.run(debug=True, port=5000, host="0.0.0.0")
