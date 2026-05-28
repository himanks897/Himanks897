"""
Fetcher 5 — Perseus Digital Library (via Project Gutenberg direct download)

The Perseids CTS API returns HTTP 500 for all GetPassage requests.
Gutendex (gutendex.com) consistently times out.

This fetcher downloads classical historical texts directly from Project Gutenberg
using their stable plain-text cache URLs:
  https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt

These are the same Classical texts listed in the original spec
(Herodotus, Thucydides, Caesar, Plutarch, etc.) — all public domain, reliably served.

Source attribution: "Perseus Digital Library" kept to match sources table.
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "Perseus Digital Library"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Project Gutenberg book IDs for the classical texts specified in the original spec.
# All confirmed at gutenberg.org; use the stable /cache/epub/ URL format.
GUTENBERG_TEXTS = {
    "Herodotus - The Histories":               2707,
    "Thucydides - The Peloponnesian War":       7142,
    "Caesar - Gallic Wars":                   10657,
    "Plutarch - Parallel Lives (Vol I)":         674,
    "Livy - History of Rome (Vol I)":          19725,
    "Polybius - The Histories":                44125,
    "Suetonius - Lives of the Twelve Caesars":  6400,
    "Tacitus - Annals of Tiberius":              7959,   # correct ID (7469 was Daniel Deronda)
}

CHARS_PER_BOOK = 6000   # store first 6 000 chars of each text


def strip_html(text):
    if not text:
        return None
    return re.sub(r'<[^>]+>', ' ', text).strip()


def _download_text(book_id: int) -> str:
    """Try several known Gutenberg URL patterns; return text or empty string."""
    urls = [
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
    ]
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
        except Exception:
            continue
    return ""


def fetch(conn, source_id) -> int:
    inserted = 0

    for text_name, book_id in GUTENBERG_TEXTS.items():
        try:
            raw = _download_text(book_id)
            if not raw:
                print(f"  [WARN] Could not download book {book_id} ({text_name})")
                time.sleep(0.5)
                continue

            full_text = raw[:CHARS_PER_BOOK].strip()
            if len(full_text) < 50:
                time.sleep(0.5)
                continue

            ok = insert_record(conn, source_id, {
                "title":       text_name,
                "full_text":   full_text,
                "summary":     full_text[:300],
                "era":         "Classical Antiquity",
                "external_id": str(book_id),
                "source_url":  f"https://www.gutenberg.org/ebooks/{book_id}",
                "record_type": "document",
                "tags":        ["Primary Source", "Classical Text", "Ancient History"],
                "raw_json":    {"gutenberg_id": book_id, "text_name": text_name},
            })
            if ok:
                inserted += 1
                print(f"  [{SOURCE_NAME}] stored: {text_name}")

        except Exception as e:
            print(f"  [ERROR] Failed for {text_name} (id={book_id}): {e}")

        time.sleep(0.5)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
