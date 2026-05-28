"""
Fetcher 3 — Internet Archive
Auth: none (public JSON search API)
Filters: mediatype:texts, language:English, NOT audio/movies
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "Internet Archive"

SEARCH_TERMS = [
    "ancient history", "world war history", "colonial history",
    "revolution history", "empire history", "medieval history",
    "renaissance history", "Islamic history", "African history",
    "Indian independence", "American history", "European history",
]


def strip_html(text):
    if not text:
        return None
    return re.sub(r'<[^>]+>', ' ', text).strip()


def fetch(conn, source_id) -> int:
    inserted = 0

    for term in SEARCH_TERMS:
        try:
            resp = requests.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q":      f"{term} AND mediatype:texts AND language:English "
                              "AND NOT mediatype:audio AND NOT mediatype:movies",
                    "fl[]":   ["identifier", "title", "date", "subject", "description"],
                    "rows":   30,
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
                    params={
                        "q":      f"{term} AND mediatype:texts AND language:English",
                        "fl[]":   ["identifier", "title", "date", "subject", "description"],
                        "rows":   30,
                        "page":   1,
                        "output": "json",
                    },
                    timeout=15,
                )

            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code} for IA term='{term}'")
                continue

            docs = resp.json().get("response", {}).get("docs", [])

            for doc in docs:
                # Normalise subject (can be string or list)
                subj = doc.get("subject", [])
                if not isinstance(subj, list):
                    subj = [subj] if subj else []

                summary = str(doc.get("description", ""))[:500]

                try:
                    ok = insert_record(conn, source_id, {
                        "title":       doc.get("title", ""),
                        "summary":     summary,
                        "date_text":   str(doc.get("date", "")),
                        "tags":        subj,
                        "source_url":  f"https://archive.org/details/{doc.get('identifier', '')}",
                        "external_id": doc.get("identifier", ""),
                        "record_type": "document",
                        "raw_json":    doc,
                    })
                    if ok:
                        inserted += 1
                        if inserted % 50 == 0:
                            print(f"  [{SOURCE_NAME}] {inserted} records so far...")
                except Exception as e:
                    print(f"  [ERROR] Failed on IA doc {doc.get('identifier')}: {e}")
                time.sleep(0.5)

        except Exception as e:
            print(f"  [ERROR] IA search failed for term '{term}': {e}")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
