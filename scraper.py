#!/usr/bin/env python3
"""
iremember.ru interview scraper
Fetches all WWII veteran interview texts from iremember.ru (Я помню).

Requirements:
    pip install curl-cffi beautifulsoup4 lxml

Usage:
    python scraper.py                          # scrape everything
    python scraper.py --list-categories        # print discovered categories and exit
    python scraper.py --category tankisti      # scrape one category only
    python scraper.py --output-dir ./out --delay 3
"""

import argparse
import json
import os
import re
import time
import random
from pathlib import Path
from urllib.parse import urljoin, urlparse

from curl_cffi import requests
from bs4 import BeautifulSoup

BASE_URL = "https://iremember.ru"
MEMOIRS_URL = f"{BASE_URL}/memoirs/"

# Fallback category list in case the main page can't be parsed.
# Slug → Russian display name, derived from Google-indexed URLs.
KNOWN_CATEGORIES = {
    "pekhotintsi":              "Пехотинцы",
    "artilleristi":             "Артиллеристы",
    "grazhdanskie":             "Гражданские",
    "svyazisti":                "Связисты",
    "mediki":                   "Медики",
    "partizani":                "Партизаны",
    "razvedchiki":              "Разведчики",
    "drugie-voyska":            "Другие войска",
    "letchiki-bombardirovshchiki": "Летчики-бомбардировщики",
    "pulemetchiki":             "Пулеметчики",
    "krasnoflottsi":            "Краснофлотцы",
    "zenitchiki":               "Зенитчики",
    "tankisti":                 "Танкисты",
    "minometchiki":             "Минометчики",
    "sapery":                   "Саперы",
    "nkvd-i-smersh":            "НКВД и СМЕРШ",
    "desantniki":               "Десантники",
    "kavalleristi":             "Кавалеристы",
    "voditeli":                 "Водители",
    "gmch-katiushi":            "ГМЧ (Катюши)",
    "germany":                  "Противники",
    "letno-tekhnicheskiy-sostav": "Летно-технический состав",
    "snajpery":                 "Снайперы",
}

# CSS/HTML selectors for Joomla article content, tried in order.
# iremember.ru runs Joomla; article body lives in div.item-page on most themes.
CONTENT_SELECTORS = [
    ("div", {"class_": "item-page"}),
    ("div", {"class_": "article-content"}),
    ("div", {"itemprop": "articleBody"}),
    ("article", {}),
    ("div", {"id": "content"}),
    ("div", {"class_": re.compile(r"(item|content|memoir)", re.I)}),
]

# Classes whose elements should be stripped from article content.
JUNK_CLASSES = re.compile(
    r"(pagination|breadcrumb|social|share|print|email|pdf|tags|nav|button|"
    r"toolbar|related|comments|sidebar|modal|icon)",
    re.I,
)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    """Build a curl_cffi session impersonating Chrome to pass TLS fingerprint checks."""
    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
    })
    return session


def fetch(session: requests.Session, url: str, retries: int = 4) -> str:
    """GET a URL with exponential-backoff retries. Raises on permanent failure."""
    wait = 2
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"    [retry {attempt + 1}/{retries - 1}] {exc}")
            time.sleep(wait + random.uniform(0, 1))
            wait *= 2
    return ""  # unreachable


# ---------------------------------------------------------------------------
# Category discovery
# ---------------------------------------------------------------------------

def get_categories(session: requests.Session) -> dict[str, tuple[str, str]]:
    """
    Fetch /memoirs/ and extract category links.
    Returns {slug: (display_name, url)}.
    Falls back to KNOWN_CATEGORIES if the page can't be parsed.
    """
    print(f"Fetching category list from {MEMOIRS_URL}")
    try:
        html = fetch(session, MEMOIRS_URL)
    except Exception as exc:
        print(f"  Warning: could not fetch categories page ({exc}). Using built-in list.")
        return _known_categories()

    soup = BeautifulSoup(html, "lxml")
    categories: dict[str, tuple[str, str]] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Match exactly /memoirs/{slug}/ — not deeper paths
        m = re.match(r"(?:https?://iremember\.ru)?/memoirs/([^/?#]+)/?$", href)
        if m:
            slug = m.group(1)
            name = a.get_text(strip=True) or slug
            categories[slug] = (name, urljoin(BASE_URL, f"/memoirs/{slug}/"))

    if not categories:
        print("  No categories found in page HTML. Using built-in list.")
        return _known_categories()

    print(f"  Discovered {len(categories)} categories.")
    return categories


def _known_categories() -> dict[str, tuple[str, str]]:
    return {
        slug: (name, f"{BASE_URL}/memoirs/{slug}/")
        for slug, name in KNOWN_CATEGORIES.items()
    }


# ---------------------------------------------------------------------------
# Category listing pagination
# ---------------------------------------------------------------------------

def get_interview_urls(session: requests.Session, category_url: str) -> list[str]:
    """
    Walk through paginated Joomla category-blog listing and collect interview URLs.

    Joomla paginates with ?start=N. Each page typically shows 20 items.
    We stop when a page yields no new links.
    """
    ITEMS_PER_PAGE = 20
    seen: set[str] = set()
    start = 0

    while True:
        url = category_url if start == 0 else f"{category_url}?start={start}"
        print(f"  Listing page start={start}: {url}")

        html = fetch(session, url)
        soup = BeautifulSoup(html, "lxml")

        new_count = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Match /memoirs/{category}/{slug}/ — the individual interview path
            m = re.match(
                r"(?:https?://iremember\.ru)?/memoirs/([^/?#]+)/([^/?#]+)/?(?:[?#].*)?$",
                href,
            )
            if m:
                clean = f"{BASE_URL}/memoirs/{m.group(1)}/{m.group(2)}/"
                if clean not in seen:
                    seen.add(clean)
                    new_count += 1

        if new_count == 0:
            break

        # Check whether the page links to a next page
        next_start = start + ITEMS_PER_PAGE
        has_next = any(f"start={next_start}" in a.get("href", "") for a in soup.find_all("a"))
        if not has_next:
            break

        start = next_start
        time.sleep(random.uniform(1.0, 2.5))

    return sorted(seen)


# ---------------------------------------------------------------------------
# Article text extraction
# ---------------------------------------------------------------------------

def extract_text(soup: BeautifulSoup) -> str:
    """
    Extract the main article body from a Joomla page.
    Strips navigation, pagination, share buttons, and other chrome.
    """
    content = None
    for tag, attrs in CONTENT_SELECTORS:
        content = soup.find(tag, **attrs)
        if content:
            break

    if not content:
        # Last resort: body minus header/footer
        content = soup.find("body") or soup

    # Remove junk sub-elements in place
    for junk in content.find_all(["nav", "aside", "footer", "script", "style", "noscript"]):
        junk.decompose()
    for junk in content.find_all(class_=JUNK_CLASSES):
        junk.decompose()
    for junk in content.find_all(id=JUNK_CLASSES):
        junk.decompose()

    text = content.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_page_offsets(soup: BeautifulSoup) -> list[int]:
    """
    Detect multi-page articles. iremember.ru uses ?start=N for article pages too.
    Returns sorted list of start values; 0 means the first (no ?start param) page.
    """
    offsets: set[int] = {0}
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]start=(\d+)", a["href"])
        if m:
            offsets.add(int(m.group(1)))
    return sorted(offsets)


def scrape_interview(session: requests.Session, url: str) -> str:
    """
    Fetch a complete interview (potentially multi-page) and return plain text.
    The source URL is prepended as a header for easy reference.
    """
    first_html = fetch(session, url)
    first_soup = BeautifulSoup(first_html, "lxml")

    # Title
    title_tag = first_soup.find("h1") or first_soup.find("h2")
    title = title_tag.get_text(strip=True) if title_tag else ""

    offsets = get_page_offsets(first_soup)
    parts: list[str] = [f"SOURCE: {url}"]
    if title:
        parts.append(f"\n{title}\n{'=' * min(len(title), 80)}")

    for i, offset in enumerate(offsets):
        if offset == 0:
            page_soup = first_soup
        else:
            page_html = fetch(session, f"{url}?start={offset}")
            page_soup = BeautifulSoup(page_html, "lxml")
            time.sleep(random.uniform(0.8, 2.0))

        text = extract_text(page_soup)
        if text:
            parts.append(text)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def load_done(path: Path) -> set[str]:
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_done(path: Path, done: set[str]) -> None:
    with open(path, "w") as f:
        json.dump(sorted(done), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def slug_from_url(url: str) -> str:
    """Turn an interview URL into a safe filesystem name."""
    parts = urlparse(url).path.strip("/").split("/")
    # parts = ['memoirs', 'category', 'slug']
    if len(parts) >= 3:
        return f"{parts[2]}"
    return parts[-1] or "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape all WWII veteran interview texts from iremember.ru"
    )
    parser.add_argument("--output-dir", default="./interviews",
                        help="Directory to save .txt files (default: ./interviews)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Base seconds between interview requests (default: 2.0)")
    parser.add_argument("--category",
                        help="Scrape only this category slug, e.g. tankisti")
    parser.add_argument("--list-categories", action="store_true",
                        help="Print discovered categories and exit")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    progress_file = out / ".progress.json"

    session = make_session()
    done = load_done(progress_file)
    if done:
        print(f"Resuming: {len(done)} interviews already saved.")

    # Discover categories
    try:
        categories = get_categories(session)
    except Exception as exc:
        print(f"Error fetching categories: {exc}. Using built-in list.")
        categories = _known_categories()

    if args.list_categories:
        for slug, (name, url) in sorted(categories.items()):
            print(f"  {slug:<40} {name}")
        return

    if args.category:
        if args.category not in categories:
            avail = ", ".join(sorted(categories))
            raise SystemExit(f"Unknown category '{args.category}'. Available: {avail}")
        categories = {args.category: categories[args.category]}

    total_ok = 0
    total_err = 0

    for slug, (name, cat_url) in categories.items():
        cat_dir = out / slug
        cat_dir.mkdir(exist_ok=True)
        print(f"\n{'=' * 60}")
        print(f"Category: {name} ({slug})")

        try:
            urls = get_interview_urls(session, cat_url)
        except Exception as exc:
            print(f"  Failed to list interviews: {exc}")
            continue

        remaining = [u for u in urls if u not in done]
        print(f"  {len(urls)} interviews found, {len(remaining)} to scrape.")

        for url in remaining:
            fname = slug_from_url(url) + ".txt"
            fpath = cat_dir / fname

            try:
                print(f"  → {url}")
                text = scrape_interview(session, url)
                fpath.write_text(text, encoding="utf-8")
                done.add(url)
                save_done(progress_file, done)
                total_ok += 1
            except Exception as exc:
                print(f"    ERROR: {exc}")
                total_err += 1

            time.sleep(random.uniform(args.delay * 0.7, args.delay * 1.4))

    print(f"\n{'=' * 60}")
    print(f"Done. Saved {total_ok} interviews. Errors: {total_err}.")
    print(f"Output: {out.resolve()}")


if __name__ == "__main__":
    main()
