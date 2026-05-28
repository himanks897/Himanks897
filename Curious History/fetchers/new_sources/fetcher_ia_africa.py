"""
fetcher_ia_africa.py — Internet Archive: African Historical Collections

Queries the Internet Archive for sub-Saharan Africa, North Africa, and
pan-African history texts.

Auth    : None required
License : Public Domain / CC — commercial OK
Docs    : https://archive.org/advancedsearch.php
Coverage: Africa (all regions), African history ancient–modern
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Internet Archive — Africa"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

IA_QUERIES = [
    # North Africa
    'subject:"Egypt history" mediatype:texts language:English',
    'subject:"North Africa" subject:"history" mediatype:texts',
    'subject:"Algeria" OR subject:"Tunisia" subject:"history" mediatype:texts',
    # West Africa
    'subject:"West Africa" subject:"history" mediatype:texts',
    'subject:"Ghana" OR subject:"Mali Empire" OR subject:"Songhai" mediatype:texts',
    'subject:"Nigeria history" OR subject:"Yoruba" OR subject:"Benin Kingdom" mediatype:texts',
    # East Africa
    'subject:"East Africa" subject:"history" mediatype:texts',
    'subject:"Ethiopia" OR subject:"Abyssinia" history mediatype:texts',
    'subject:"Kenya" OR subject:"Tanzania" subject:"history" mediatype:texts',
    # Southern Africa
    'subject:"South Africa history" mediatype:texts language:English',
    'subject:"Zulu" OR subject:"Zimbabwe" history mediatype:texts',
    # Central Africa
    'subject:"Congo history" OR subject:"Central Africa" mediatype:texts',
    # African colonialism
    'subject:"African colonialism" OR subject:"scramble for Africa" mediatype:texts',
    'subject:"decolonization Africa" mediatype:texts language:English',
    # African kingdoms & civilisations
    'subject:"African kingdoms" OR subject:"Great Zimbabwe" mediatype:texts',
    '"Swahili coast" history mediatype:texts',
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _infer_region(title: str, subjects: list) -> str:
    """Return the most specific African region from title/subjects."""
    text = (title + " " + " ".join(subjects)).lower()
    if any(k in text for k in ["egypt", "north africa", "algeria", "morocco", "tunisia", "libya"]):
        return "North Africa"
    if any(k in text for k in ["nigeria", "ghana", "mali", "west africa", "senegal",
                                "ivory coast", "benin", "guinea"]):
        return "West Africa"
    if any(k in text for k in ["ethiopia", "kenya", "tanzania", "east africa",
                                "somalia", "uganda", "rwanda"]):
        return "East Africa"
    if any(k in text for k in ["south africa", "zimbabwe", "zulu", "botswana",
                                "mozambique", "zambia"]):
        return "Southern Africa"
    if any(k in text for k in ["congo", "central africa", "cameroon"]):
        return "Central Africa"
    return "Africa"


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
                               "description", "creator"],
                    "sort[]": "downloads desc",
                    "rows":   20,
                    "page":   1,
                    "output": "json",
                },
                timeout=20,
            )

            if resp.status_code == 429:
                print("  [IA-Africa] Rate limited — waiting 60s")
                time.sleep(60)
                continue

            if resp.status_code != 200:
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

                region = _infer_region(str(title), [str(s) for s in subj])

                ok = insert_record(conn, source_id, {
                    "title":       str(title)[:300],
                    "summary":     summary or None,
                    "date_text":   str(doc.get("date", ""))[:20],
                    "region":      region,
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"ia-africa-{ia_id}",
                    "record_type": "document",
                    "tags":        subj[:6] + ["Internet Archive Africa"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [IA-Africa] Error: {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
