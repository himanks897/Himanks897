"""
fetcher_ia_india.py — Internet Archive: Digital Library of India + Indian Collections

Queries the Internet Archive for the dedicated Digital Library of India collection
plus broader India-related historical texts.

Auth    : None required
License : Public Domain / CC — commercial OK
Docs    : https://archive.org/advancedsearch.php
Coverage: India (ancient, medieval, colonial, modern), South Asia
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Internet Archive — India"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Curated Internet Archive queries targeting Indian history
IA_QUERIES = [
    # DLI collection
    "collection:digitallibraryindia history",
    # British India administrative records
    "subject:\"India\" subject:\"history\" language:English mediatype:texts",
    # Independence era
    "subject:\"Indian independence\" OR subject:\"Gandhi\" mediatype:texts",
    # Mughal / medieval India
    "subject:\"Mughal\" OR subject:\"Sultanate\" mediatype:texts",
    # Colonial India
    "subject:\"British India\" subject:\"colonial\" mediatype:texts",
    # Ancient India
    "subject:\"ancient India\" OR subject:\"Maurya\" OR subject:\"Gupta\" mediatype:texts",
    # Pakistan / Bangladesh
    "subject:\"Pakistan history\" OR subject:\"Bengal partition\" mediatype:texts",
    # Sri Lanka / Ceylon
    "subject:\"Ceylon\" OR subject:\"Sri Lanka history\" mediatype:texts",
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    for query_term in IA_QUERIES:
        try:
            resp = requests.get(
                "https://archive.org/advancedsearch.php",
                headers=HEADERS,
                params={
                    "q":      f"({query_term})",
                    "fl[]":   ["identifier", "title", "date", "subject",
                               "description", "creator", "language"],
                    "sort[]": "downloads desc",
                    "rows":   25,
                    "page":   1,
                    "output": "json",
                },
                timeout=20,
            )

            if resp.status_code == 429:
                print("  [IA-India] Rate limited — waiting 60s")
                time.sleep(60)
                continue

            if resp.status_code != 200:
                print(f"  [IA-India] HTTP {resp.status_code}")
                time.sleep(1)
                continue

            docs = resp.json().get("response", {}).get("docs", [])

            for doc in docs:
                ia_id = doc.get("identifier", "")
                title = doc.get("title", "")
                if not ia_id or not title:
                    continue

                subj = doc.get("subject", [])
                if isinstance(subj, str):
                    subj = [subj]

                raw_desc = doc.get("description", "")
                if isinstance(raw_desc, list):
                    raw_desc = " ".join(raw_desc)
                summary = _strip_html(str(raw_desc))[:500]

                ok = insert_record(conn, source_id, {
                    "title":       str(title)[:300],
                    "summary":     summary or None,
                    "date_text":   str(doc.get("date", ""))[:20],
                    "region":      "India",
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"ia-india-{ia_id}",
                    "record_type": "document",
                    "tags":        subj[:6] + ["Internet Archive India", "South Asia"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [IA-India] Error for query: {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
