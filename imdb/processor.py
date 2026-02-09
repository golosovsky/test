"""
IMDb dataset processor: reads TSV.gz files and loads them into SQLite.

Handles:
- Streaming gzipped TSV parsing (memory-efficient)
- NULL value conversion (backslash-N to NULL)
- Type coercion (integers, floats)
- Schema creation with indexes for fast querying
"""

import csv
import gzip
import os
import sqlite3
import sys
import time

from config import DATA_DIR, DB_PATH

# Increase CSV field size limit for large fields
csv.field_size_limit(10 * 1024 * 1024)

SCHEMA = """
CREATE TABLE IF NOT EXISTS title_basics (
    tconst TEXT PRIMARY KEY,
    titleType TEXT,
    primaryTitle TEXT,
    originalTitle TEXT,
    isAdult INTEGER,
    startYear INTEGER,
    endYear INTEGER,
    runtimeMinutes INTEGER,
    genres TEXT
);

CREATE TABLE IF NOT EXISTS title_ratings (
    tconst TEXT PRIMARY KEY,
    averageRating REAL,
    numVotes INTEGER
);

CREATE TABLE IF NOT EXISTS title_crew (
    tconst TEXT PRIMARY KEY,
    directors TEXT,
    writers TEXT
);

CREATE TABLE IF NOT EXISTS title_episode (
    tconst TEXT PRIMARY KEY,
    parentTconst TEXT,
    seasonNumber INTEGER,
    episodeNumber INTEGER
);

CREATE TABLE IF NOT EXISTS title_principals (
    tconst TEXT,
    ordering INTEGER,
    nconst TEXT,
    category TEXT,
    job TEXT,
    characters TEXT,
    PRIMARY KEY (tconst, ordering)
);

CREATE TABLE IF NOT EXISTS title_akas (
    titleId TEXT,
    ordering INTEGER,
    title TEXT,
    region TEXT,
    language TEXT,
    types TEXT,
    attributes TEXT,
    isOriginalTitle INTEGER,
    PRIMARY KEY (titleId, ordering)
);

CREATE TABLE IF NOT EXISTS name_basics (
    nconst TEXT PRIMARY KEY,
    primaryName TEXT,
    birthYear INTEGER,
    deathYear INTEGER,
    primaryProfession TEXT,
    knownForTitles TEXT
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_title_basics_type ON title_basics(titleType);
CREATE INDEX IF NOT EXISTS idx_title_basics_year ON title_basics(startYear);
CREATE INDEX IF NOT EXISTS idx_title_basics_title ON title_basics(primaryTitle);
CREATE INDEX IF NOT EXISTS idx_title_ratings_rating ON title_ratings(averageRating);
CREATE INDEX IF NOT EXISTS idx_title_ratings_votes ON title_ratings(numVotes);
CREATE INDEX IF NOT EXISTS idx_title_episode_parent ON title_episode(parentTconst);
CREATE INDEX IF NOT EXISTS idx_title_principals_nconst ON title_principals(nconst);
CREATE INDEX IF NOT EXISTS idx_title_principals_category ON title_principals(category);
CREATE INDEX IF NOT EXISTS idx_title_akas_title ON title_akas(title);
CREATE INDEX IF NOT EXISTS idx_name_basics_name ON name_basics(primaryName);
"""

# Mapping from filename to (table_name, column_types)
# Types: 's' = string, 'i' = integer, 'f' = float
FILE_TABLE_MAP = {
    "title.basics.tsv.gz": (
        "title_basics",
        ["s", "s", "s", "s", "i", "i", "i", "i", "s"],
    ),
    "title.ratings.tsv.gz": (
        "title_ratings",
        ["s", "f", "i"],
    ),
    "title.crew.tsv.gz": (
        "title_crew",
        ["s", "s", "s"],
    ),
    "title.episode.tsv.gz": (
        "title_episode",
        ["s", "s", "i", "i"],
    ),
    "title.principals.tsv.gz": (
        "title_principals",
        ["s", "i", "s", "s", "s", "s"],
    ),
    "title.akas.tsv.gz": (
        "title_akas",
        ["s", "i", "s", "s", "s", "s", "s", "i"],
    ),
    "name.basics.tsv.gz": (
        "name_basics",
        ["s", "s", "i", "i", "s", "s"],
    ),
}


def _coerce(value, type_code):
    """Convert a TSV value to the appropriate Python type."""
    if value == "\\N" or value == "":
        return None
    if type_code == "i":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if type_code == "f":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return value


def _load_file(conn, filename):
    """Stream-load a single TSV.gz file into SQLite."""
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  WARNING: {filepath} not found, skipping.")
        return

    table_name, col_types = FILE_TABLE_MAP[filename]
    num_cols = len(col_types)
    placeholders = ",".join(["?"] * num_cols)
    insert_sql = f"INSERT OR IGNORE INTO {table_name} VALUES ({placeholders})"

    cursor = conn.cursor()
    batch = []
    batch_size = 50000
    row_count = 0
    start = time.time()

    with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)  # skip header

        for row in reader:
            if len(row) != num_cols:
                # Some rows may have extra/missing fields; pad or truncate
                if len(row) < num_cols:
                    row.extend(["\\N"] * (num_cols - len(row)))
                else:
                    row = row[:num_cols]

            converted = tuple(_coerce(val, t) for val, t in zip(row, col_types))
            batch.append(converted)
            row_count += 1

            if len(batch) >= batch_size:
                cursor.executemany(insert_sql, batch)
                batch.clear()
                elapsed = time.time() - start
                rate = row_count / elapsed if elapsed > 0 else 0
                sys.stdout.write(
                    f"\r  {table_name}: {row_count:,} rows ({rate:,.0f} rows/s)"
                )
                sys.stdout.flush()

    if batch:
        cursor.executemany(insert_sql, batch)

    conn.commit()
    elapsed = time.time() - start
    print(f"\r  {table_name}: {row_count:,} rows in {elapsed:.1f}s")


def process_all(force=False):
    """Process all TSV.gz files into a SQLite database."""
    print("=" * 60)
    print("IMDb Dataset Processor → SQLite")
    print("=" * 60)

    if os.path.exists(DB_PATH) and not force:
        print(f"\nDatabase already exists at {DB_PATH}")
        print("Use --force to rebuild from scratch.")
        return

    if os.path.exists(DB_PATH) and force:
        os.remove(DB_PATH)
        print(f"Removed existing database.")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-256000")  # 256MB cache
    conn.execute("PRAGMA temp_store=MEMORY")

    print("\nCreating schema...")
    conn.executescript(SCHEMA)

    for filename in FILE_TABLE_MAP:
        print(f"\nLoading {filename}...")
        _load_file(conn, filename)

    print("\nCreating indexes (this may take a moment)...")
    conn.executescript(INDEXES)
    conn.commit()

    # Print summary
    cursor = conn.cursor()
    print("\n" + "-" * 40)
    print("Database summary:")
    for filename in FILE_TABLE_MAP:
        table_name = FILE_TABLE_MAP[filename][0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  {table_name}: {count:,} rows")

    db_size = os.path.getsize(DB_PATH)
    print(f"\nDatabase size: {db_size / (1024*1024):.1f} MB")
    print(f"Database path: {DB_PATH}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    force = "--force" in sys.argv
    process_all(force=force)
