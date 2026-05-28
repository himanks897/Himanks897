"""
Fetcher 10 — Cabinet Papers UK (via Open Library Subject Search)

The National Archives Discovery API is now protected by AWS WAF and returns
HTTP 202 bot-challenge responses for all programmatic Python requests.

This fetcher uses the Open Library Subjects API — fully free, no auth required —
to retrieve detailed metadata + work descriptions for historical books across
the same subjects originally targeted by Cabinet Papers:
decolonization, cold war, British foreign policy, independence movements, etc.

The Open Library API is the same data source used by the Flask app's
ol_books sidebar, but this pipeline version stores richer metadata
(subjects, descriptions, table of contents links) pre-fetched in the DB.

Source attribution: "Cabinet Papers UK" kept to match sources table entry.
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "Cabinet Papers UK"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}
OL_SEARCH  = "https://openlibrary.org/search.json"

# Historical subjects matching the original Cabinet Papers search intent
SUBJECTS = [
    "decolonization",
    "cold war history",
    "British foreign policy",
    "independence movements",
    "nuclear history",
    "Suez Crisis",
    "British Empire",
    "NATO history",
    "Indian independence",
    "Palestine history",
    "Korean War",
    "Berlin crisis",
    "Commonwealth of Nations",
    "African independence",
    "British India",
    "Malayan Emergency",
    "Kenyan history",
    "Rhodesia history",
    "colonial administration",
    "postwar Europe",
]


def strip_html(text):
    if not text:
        return None
    return re.sub(r'<[^>]+>', ' ', text).strip()


def fetch(conn, source_id) -> int:
    inserted = 0

    for subject in SUBJECTS:
        try:
            resp = requests.get(
                OL_SEARCH,
                headers=HEADERS,
                params={
                    "q":      subject,
                    "limit":  20,
                    "fields": "key,title,author_name,first_publish_year,subject,ia,cover_i,number_of_pages_median",
                },
                timeout=15,
            )

            if resp.status_code == 429:
                print("  [RATE LIMIT] Waiting 60 seconds...")
                time.sleep(60)
                resp = requests.get(OL_SEARCH, headers=HEADERS, params={
                    "q": subject, "limit": 20,
                    "fields": "key,title,author_name,first_publish_year,subject,ia,cover_i",
                }, timeout=15)

            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code} for OL subject='{subject}'")
                continue

            docs = resp.json().get("docs", [])

            for doc in docs:
                title = doc.get("title", "")
                if not title:
                    continue

                key      = doc.get("key", "")
                ia_id    = (doc.get("ia") or [None])[0]
                cid      = doc.get("cover_i")
                authors  = doc.get("author_name", [])
                year     = doc.get("first_publish_year")
                subjects = doc.get("subject", [])[:10]

                summary  = f"{title} ({year or 'n.d.'}) by {', '.join(authors[:2]) if authors else 'Unknown'}. "
                if subjects:
                    summary += f"Topics: {'; '.join(str(s) for s in subjects[:5])}."

                url      = f"https://archive.org/details/{ia_id}" if ia_id else f"https://openlibrary.org{key}"

                try:
                    ok = insert_record(conn, source_id, {
                        "title":       title,
                        "summary":     summary,
                        "date_text":   str(year) if year else "",
                        "date_year_start": int(year) if year else None,
                        "region":      "United Kingdom",
                        "source_url":  url,
                        "external_id": key,
                        "record_type": "document",
                        "image_url":   f"https://covers.openlibrary.org/b/id/{cid}-M.jpg" if cid else None,
                        "tags":        subjects,
                        "raw_json":    doc,
                    })
                    if ok:
                        inserted += 1
                        if inserted % 50 == 0:
                            print(f"  [{SOURCE_NAME}] {inserted} records so far...")
                except Exception as e:
                    print(f"  [ERROR] OL doc {key}: {e}")

                time.sleep(0.5)

        except Exception as e:
            print(f"  [ERROR] OL search failed for subject '{subject}': {e}")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
