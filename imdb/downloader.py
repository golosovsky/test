"""
IMDb dataset downloader with smart caching.

Downloads TSV.gz files from datasets.imdbws.com.
Skips downloads if local files match the remote (same size + last-modified).
"""

import json
import os
import sys
import time

import requests

from config import CACHE_META_PATH, DATA_DIR, DATASET_FILES, DATASETS_BASE_URL


def _load_cache_meta():
    if os.path.exists(CACHE_META_PATH):
        with open(CACHE_META_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_cache_meta(meta):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def _get_remote_info(url):
    """Get Content-Length and Last-Modified from remote via HEAD request."""
    resp = requests.head(url, allow_redirects=True, timeout=30)
    resp.raise_for_status()
    return {
        "content_length": resp.headers.get("Content-Length", ""),
        "last_modified": resp.headers.get("Last-Modified", ""),
        "etag": resp.headers.get("ETag", ""),
    }


def needs_download(filename, meta):
    """Check if a file needs to be (re)downloaded."""
    local_path = os.path.join(DATA_DIR, filename)

    if not os.path.exists(local_path):
        return True

    local_size = os.path.getsize(local_path)
    cached = meta.get(filename, {})

    url = DATASETS_BASE_URL + filename
    try:
        remote_info = _get_remote_info(url)
    except requests.RequestException as e:
        print(f"  Warning: could not check remote for {filename}: {e}")
        return not os.path.exists(local_path)

    remote_size = remote_info.get("content_length", "")
    if remote_size and int(remote_size) != local_size:
        return True

    remote_modified = remote_info.get("last_modified", "")
    cached_modified = cached.get("last_modified", "")
    if remote_modified and cached_modified and remote_modified != cached_modified:
        return True

    remote_etag = remote_info.get("etag", "")
    cached_etag = cached.get("etag", "")
    if remote_etag and cached_etag and remote_etag != cached_etag:
        return True

    if not cached:
        return True

    return False


def download_file(filename):
    """Download a single dataset file with progress display."""
    url = DATASETS_BASE_URL + filename
    local_path = os.path.join(DATA_DIR, filename)

    os.makedirs(DATA_DIR, exist_ok=True)

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    start_time = time.time()

    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                elapsed = time.time() - start_time
                speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                sys.stdout.write(
                    f"\r  {filename}: {pct:5.1f}%  "
                    f"({downloaded // (1024*1024)}/"
                    f"{total // (1024*1024)} MB)  "
                    f"{speed:.1f} MB/s"
                )
                sys.stdout.flush()

    print()

    remote_info = {
        "content_length": resp.headers.get("Content-Length", ""),
        "last_modified": resp.headers.get("Last-Modified", ""),
        "etag": resp.headers.get("ETag", ""),
    }
    return remote_info


def download_all():
    """Download all IMDb datasets, skipping files that are up to date."""
    print("=" * 60)
    print("IMDb Dataset Downloader")
    print("=" * 60)

    meta = _load_cache_meta()

    for filename in DATASET_FILES:
        print(f"\nChecking {filename}...")
        if needs_download(filename, meta):
            print(f"  Downloading {filename}...")
            remote_info = download_file(filename)
            meta[filename] = remote_info
            _save_cache_meta(meta)
            print(f"  Done.")
        else:
            print(f"  Up to date, skipping.")

    print(f"\nAll datasets ready in {DATA_DIR}/")


if __name__ == "__main__":
    download_all()
