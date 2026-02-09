"""
IMDb Natural Language Search — Flask Application

Usage:
    # First-time setup: download datasets and build SQLite DB
    python app.py setup

    # Rebuild database (reprocess from already-downloaded files)
    python app.py process [--force]

    # Run the web application
    python app.py [run]

Environment variables:
    ANTHROPIC_API_KEY   - Required (unless using OpenAI)
    OPENAI_API_KEY      - Required if LLM_PROVIDER=openai
    LLM_PROVIDER        - "anthropic" (default) or "openai"
    ANTHROPIC_MODEL     - Model name (default: claude-sonnet-4-20250514)
    OPENAI_MODEL        - Model name (default: gpt-4o-mini)
    PORT                - Server port (default: 5000)
"""

import os
import sys

from flask import Flask, jsonify, render_template, request

from config import DB_PATH, FLASK_PORT

app = Flask(__name__)


def _db_ready():
    return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0


@app.route("/")
def index():
    return render_template("index.html", db_ready=_db_ready())


@app.route("/api/search", methods=["POST"])
def api_search():
    if not _db_ready():
        return jsonify({"error": "Database not ready. Run: python app.py setup"}), 503

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Empty query"}), 400

    if len(query) > 1000:
        return jsonify({"error": "Query too long (max 1000 chars)"}), 400

    from search import execute_search
    result = execute_search(query)
    return jsonify(result)


@app.route("/api/status")
def api_status():
    if not _db_ready():
        return jsonify({"ready": False, "message": "Database not found. Run: python app.py setup"})

    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    stats = {}
    for table in ["title_basics", "title_ratings", "name_basics", "title_principals",
                   "title_crew", "title_episode", "title_akas"]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats[table] = 0

    conn.close()

    return jsonify({
        "ready": True,
        "tables": stats,
        "db_size_mb": round(os.path.getsize(DB_PATH) / (1024 * 1024), 1),
    })


@app.route("/api/examples")
def api_examples():
    """Return example queries to show in the UI."""
    return jsonify({
        "examples": [
            "Top 10 highest rated movies of all time",
            "Films by Christopher Nolan sorted by rating",
            "Horror movies from the 1980s with rating above 7",
            "Movies starring both Brad Pitt and Edward Norton",
            "Best sci-fi TV series with more than 50000 votes",
            "Movies directed by Quentin Tarantino",
            "Highest rated movies from 2023",
            "Films where Morgan Freeman played God",
            "Korean movies with rating above 8",
            "Longest movies ever made",
        ]
    })


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "run":
        if not _db_ready():
            print("WARNING: Database not found at", DB_PATH)
            print("Run 'python app.py setup' first to download and process IMDb data.")
            print("Starting server anyway — the UI will show a setup prompt.\n")

        print(f"Starting IMDb NL Search on http://localhost:{FLASK_PORT}")
        app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)

    elif sys.argv[1] == "setup":
        from downloader import download_all
        from processor import process_all
        download_all()
        print()
        process_all(force=True)
        print("\nSetup complete! Run 'python app.py' to start the web server.")

    elif sys.argv[1] == "download":
        from downloader import download_all
        download_all()

    elif sys.argv[1] == "process":
        from processor import process_all
        force = "--force" in sys.argv
        process_all(force=force)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
