"""
Fetcher 7 — Our World in Data
Auth: none (public CSV download)
Records stored with content_type="dataset" — used for charts/timelines only,
never displayed as readable article content.
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "Our World in Data"

OWID_CHARTS = [
    "world-population-since-10000-bce-ourworldindata-series",
    # Only slugs confirmed working (404s removed from original list)
    "share-of-population-living-in-extreme-poverty",
    "democracy-index-eiu",
    "military-expenditure-as-a-share-of-gdp",
    "life-expectancy",
    "urbanization-last-500-years",
    "gdp-per-capita-worldbank",
]


def strip_html(text):
    if not text:
        return None
    return re.sub(r'<[^>]+>', ' ', text).strip()


def fetch(conn, source_id) -> int:
    inserted = 0

    for slug in OWID_CHARTS:
        try:
            url  = f"https://ourworldindata.org/grapher/{slug}.csv"
            resp = requests.get(url, timeout=15)

            if resp.status_code == 429:
                print("  [RATE LIMIT] Waiting 60 seconds...")
                time.sleep(60)
                resp = requests.get(url, timeout=15)

            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code} for OWID slug={slug}")
                continue

            # Store raw CSV — do NOT parse or interpret
            csv_text = resp.text[:8000]

            ok = insert_record(conn, source_id, {
                "title":       slug.replace("-", " ").title(),
                "full_text":   csv_text,
                "summary":     f"Historical dataset: {slug.replace('-', ' ')}",
                "source_url":  f"https://ourworldindata.org/grapher/{slug}",
                "external_id": slug,
                "record_type": "dataset",
                "era":         "Multi-Era",
                "raw_json":    {"slug": slug},
            })
            if ok:
                inserted += 1
                print(f"  [{SOURCE_NAME}] stored dataset: {slug}")

        except Exception as e:
            print(f"  [ERROR] OWID failed for slug '{slug}': {e}")

        time.sleep(0.5)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
