import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "imdb.db")
CACHE_META_PATH = os.path.join(DATA_DIR, ".download_meta.json")

DATASETS_BASE_URL = "https://datasets.imdbws.com/"

DATASET_FILES = [
    "title.basics.tsv.gz",
    "title.ratings.tsv.gz",
    "title.crew.tsv.gz",
    "title.episode.tsv.gz",
    "title.principals.tsv.gz",
    "title.akas.tsv.gz",
    "name.basics.tsv.gz",
]

# LLM provider: "anthropic" or "openai"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

FLASK_PORT = int(os.environ.get("PORT", 5000))
