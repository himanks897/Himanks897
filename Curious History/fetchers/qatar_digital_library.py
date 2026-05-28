"""
Fetcher 9 — Qatar Digital Library (via Internet Archive Colonial Records)

The QDL IIIF manifest API (qdl.qa) is behind Cloudflare and returns HTTP 403
for all programmatic access regardless of headers used.

This fetcher queries the Internet Archive for the same subject matter:
Colonial Records, Gulf History, British India, and British Mandate documents.
All items are public domain, openly accessible, and in the "texts" mediatype.

Records are stored with content_type="metadata_only" (matching the sources
table entry for Qatar Digital Library) — the same display intent as QDL:
"View Original Document" links, no body text fabricated.
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "Qatar Digital Library"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Targeted search queries for Gulf History / Colonial Records / British India
ARCHIVE_QUERIES = [
    "Colonial Records Gulf Arabia British India",
    "Persian Gulf British Mandate historical documents",
    "India Office Records colonial history",
    "British India political records administration",
    "Gulf Arab states history diplomatic records",
]


def strip_html(text):
    if not text:
        return None
    return re.sub(r'<[^>]+>', ' ', text).strip()


def fetch(conn, source_id) -> int:
    inserted = 0

    for query in ARCHIVE_QUERIES:
        try:
            resp = requests.get(
                "https://archive.org/advancedsearch.php",
                headers=HEADERS,
                params={
                    "q":      f"({query}) AND mediatype:texts",
                    "fl[]":   ["identifier", "title", "date", "subject", "description", "creator"],
                    "sort[]": "downloads desc",
                    "rows":   5,
                    "page":   1,
                    "output": "json",
                },
                timeout=15,
            )

            if resp.status_code == 429:
                print("  [RATE LIMIT] Waiting 60 seconds...")
                time.sleep(60)
                resp = requests.get(
                    "https://archive.org/advancedsearch.php",
                    headers=HEADERS,
                    params={
                        "q":      f"({query}) AND mediatype:texts",
                        "fl[]":   ["identifier", "title", "date", "subject", "description", "creator"],
                        "rows":   5, "page": 1, "output": "json",
                    },
                    timeout=15,
                )

            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code} for QDL-IA query='{query}'")
                continue

            docs = resp.json().get("response", {}).get("docs", [])

            for doc in docs:
                ia_id = doc.get("identifier", "")
                if not ia_id:
                    continue

                subj = doc.get("subject", [])
                if not isinstance(subj, list):
                    subj = [subj] if subj else []

                # metadata_only — no full_text or summary fabrication
                ok = insert_record(conn, source_id, {
                    "title":       doc.get("title", ""),
                    "summary":     None,     # metadata_only: no body text
                    "full_text":   None,     # metadata_only: body is in scanned images
                    "date_text":   str(doc.get("date", "")),
                    "region":      "Middle East",
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": ia_id,
                    "record_type": "document",
                    "tags":        subj[:5] + ["Colonial Records", "Gulf History"],
                    "raw_json":    {"identifier": ia_id, "query": query},
                })
                if ok:
                    inserted += 1
                    print(f"  [{SOURCE_NAME}] stored: {doc.get('title', ia_id)[:60]}")

        except Exception as e:
            print(f"  [ERROR] QDL-IA query '{query}' failed: {e}")

        time.sleep(0.5)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
