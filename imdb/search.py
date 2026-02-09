"""
Natural Language to SQL search engine for IMDb data.

Uses a cloud LLM (Anthropic Claude or OpenAI) to convert natural language
queries into SQL, then executes them against the local SQLite database.

Architecture decision:
  - Cloud LLM is the best fit here because:
    1. The schema is small (7 tables) — fits easily in a prompt
    2. Cloud LLMs (Claude, GPT-4) have excellent text-to-SQL accuracy
    3. No fine-tuning or local model hosting needed
    4. The LLM sees the full schema + column descriptions and generates
       precise SQL for arbitrarily complex natural language queries
  - The schema description is sent as a system prompt, so the LLM has
    full context about available tables, columns, types, and relationships
  - Generated SQL is validated (SELECT-only) before execution
  - Results are limited to prevent runaway queries
"""

import re
import sqlite3

import anthropic
import openai

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DB_PATH,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

SYSTEM_PROMPT = """You are an SQL query generator for an IMDb database stored in SQLite.
Given a natural language question about movies, TV shows, actors, directors, or any film industry topic, generate a SQLite-compatible SELECT query that answers the question.

DATABASE SCHEMA:

CREATE TABLE title_basics (
    tconst TEXT PRIMARY KEY,       -- unique title ID, e.g. 'tt0111161'
    titleType TEXT,                -- 'movie', 'short', 'tvSeries', 'tvEpisode', 'tvMovie', 'tvMiniSeries', 'tvSpecial', 'video', 'videoGame'
    primaryTitle TEXT,             -- title used for promotion
    originalTitle TEXT,            -- original title in original language
    isAdult INTEGER,               -- 0 or 1
    startYear INTEGER,             -- release year (YYYY) or series start year
    endYear INTEGER,               -- TV series end year, NULL for movies
    runtimeMinutes INTEGER,        -- runtime in minutes
    genres TEXT                    -- comma-separated, e.g. 'Drama,Crime,Thriller'
);

CREATE TABLE title_ratings (
    tconst TEXT PRIMARY KEY,       -- matches title_basics.tconst
    averageRating REAL,            -- weighted average rating (1-10)
    numVotes INTEGER               -- number of votes
);

CREATE TABLE title_crew (
    tconst TEXT PRIMARY KEY,       -- matches title_basics.tconst
    directors TEXT,                -- comma-separated nconst IDs of directors
    writers TEXT                   -- comma-separated nconst IDs of writers
);

CREATE TABLE title_episode (
    tconst TEXT PRIMARY KEY,       -- episode tconst
    parentTconst TEXT,             -- parent TV series tconst
    seasonNumber INTEGER,
    episodeNumber INTEGER
);

CREATE TABLE title_principals (
    tconst TEXT,                   -- title ID
    ordering INTEGER,              -- row ordering per title
    nconst TEXT,                   -- person ID (matches name_basics.nconst)
    category TEXT,                 -- role: 'actor', 'actress', 'director', 'writer', 'producer', 'composer', 'cinematographer', 'editor', 'self', 'archive_footage', 'archive_sound'
    job TEXT,                      -- specific job title for crew
    characters TEXT,               -- character name(s) played, as JSON-like string e.g. '["Michael Corleone"]'
    PRIMARY KEY (tconst, ordering)
);

CREATE TABLE title_akas (
    titleId TEXT,                  -- matches title_basics.tconst
    ordering INTEGER,
    title TEXT,                    -- localized title
    region TEXT,                   -- region code (e.g. 'US', 'GB', 'FR')
    language TEXT,                 -- language code
    types TEXT,                    -- e.g. 'imdbDisplay', 'original'
    attributes TEXT,
    isOriginalTitle INTEGER,       -- 0 or 1
    PRIMARY KEY (titleId, ordering)
);

CREATE TABLE name_basics (
    nconst TEXT PRIMARY KEY,       -- unique person ID, e.g. 'nm0000001'
    primaryName TEXT,              -- person's name
    birthYear INTEGER,
    deathYear INTEGER,             -- NULL if alive
    primaryProfession TEXT,        -- comma-separated, e.g. 'actor,director,writer'
    knownForTitles TEXT            -- comma-separated tconst IDs
);

KEY RELATIONSHIPS:
- title_basics.tconst = title_ratings.tconst (join for ratings)
- title_basics.tconst = title_principals.tconst (join for cast/crew)
- title_principals.nconst = name_basics.nconst (join for person info)
- title_basics.tconst = title_crew.tconst (join for director/writer nconst lists)
- title_episode.parentTconst = title_basics.tconst (episodes → series)
- title_akas.titleId = title_basics.tconst (alternate titles)

QUERY GUIDELINES:
1. ALWAYS include "LIMIT 25" unless the user explicitly asks for more results or asks for a count/aggregate.
2. For person-related searches (actors, directors, etc.), JOIN title_principals with name_basics on nconst.
3. For director searches, use: title_principals.category = 'director'
   (title_crew.directors has comma-separated IDs which are harder to query)
4. For actor searches, use: title_principals.category IN ('actor', 'actress')
5. For genres, use: title_basics.genres LIKE '%Drama%' (genres are comma-separated strings)
6. For decades: startYear BETWEEN 1980 AND 1989 (for "the 80s")
7. For "best" or "top" films, ORDER BY title_ratings.averageRating DESC and/or title_ratings.numVotes DESC
8. Always prefer title_basics.titleType = 'movie' unless the user asks about TV shows, series, etc.
9. NOTE: There is NO gender field in the database. The only gender signal is title_principals.category:
   'actress' implies female, 'actor' implies male. For directors/writers/producers, gender CANNOT be determined from this data.
   If asked about "female directors", explain this limitation by looking at people who also appear as 'actress' in other titles.
10. When returning results, include useful columns: primaryTitle, startYear, genres, averageRating, numVotes, and relevant person names.
11. Use COLLATE NOCASE for case-insensitive string comparisons on names.
12. Exclude adult content by default: add "AND tb.isAdult = 0" unless explicitly asked about adult content.
13. For meaningful results, often filter by numVotes > 1000 to exclude obscure titles, unless the user wants comprehensive results.

RESPONSE FORMAT:
Return ONLY the raw SQL query. No explanation, no markdown, no code fences. Just the SQL statement.
If the query cannot be answered with the available data, return a SELECT that explains why in a comment, like:
SELECT 'This query cannot be answered: gender information for directors is not available in this dataset' AS message;
"""


def _generate_sql_anthropic(nl_query):
    """Generate SQL using the Anthropic Claude API."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": nl_query}],
    )
    return message.content[0].text.strip()


def _generate_sql_openai(nl_query):
    """Generate SQL using the OpenAI API."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": nl_query},
        ],
    )
    return response.choices[0].message.content.strip()


def generate_sql(nl_query):
    """Generate SQL from natural language using the configured LLM provider."""
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        raw = _generate_sql_openai(nl_query)
    else:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        raw = _generate_sql_anthropic(nl_query)

    # Clean up: remove markdown code fences if present
    sql = raw.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        # Remove first and last lines (the fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()

    return sql


def validate_sql(sql):
    """Validate that the SQL is a safe SELECT query."""
    normalized = sql.strip().upper()

    # Remove leading comments
    while normalized.startswith("--"):
        normalized = normalized.split("\n", 1)[-1].strip().upper()

    if not normalized.startswith("SELECT"):
        return False, "Only SELECT queries are allowed."

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH",
                 "DETACH", "PRAGMA", "VACUUM", "REINDEX"]
    # Check for forbidden statements (not as substrings of identifiers)
    for kw in forbidden:
        pattern = r'\b' + kw + r'\b'
        if re.search(pattern, normalized):
            # Allow these in subqueries/CTEs only if the top-level is SELECT
            # Simple check: is there a standalone forbidden statement?
            statements = re.split(r';\s*', normalized)
            for stmt in statements:
                stmt = stmt.strip()
                if stmt and not stmt.startswith("SELECT") and not stmt.startswith("WITH") and not stmt.startswith("--"):
                    return False, f"Forbidden SQL keyword: {kw}"

    return True, ""


def execute_search(nl_query):
    """
    Full pipeline: NL query → SQL generation → validation → execution → results.

    Returns a dict with:
      - sql: the generated SQL query
      - columns: list of column names
      - results: list of row dicts
      - error: error message if any
      - row_count: number of rows returned
    """
    try:
        sql = generate_sql(nl_query)
    except Exception as e:
        return {"sql": None, "columns": [], "results": [], "error": f"LLM error: {e}", "row_count": 0}

    is_valid, reason = validate_sql(sql)
    if not is_valid:
        return {"sql": sql, "columns": [], "results": [], "error": f"Invalid query: {reason}", "row_count": 0}

    # Enforce LIMIT if not present
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 25;"

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # Set a timeout to prevent very slow queries
        conn.execute("PRAGMA busy_timeout = 10000")

        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        results = [dict(row) for row in rows]
        conn.close()

        return {
            "sql": sql,
            "columns": columns,
            "results": results,
            "error": None,
            "row_count": len(results),
        }
    except sqlite3.Error as e:
        return {"sql": sql, "columns": [], "results": [], "error": f"SQL error: {e}", "row_count": 0}
    except Exception as e:
        return {"sql": sql, "columns": [], "results": [], "error": f"Error: {e}", "row_count": 0}
