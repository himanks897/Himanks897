"""
bl_bnb.py — British National Bibliography (BNB) records.

The BNB itself is only distributed as large RDF/ZIP files (no CSV API).
This fetcher uses three complementary routes to build a BNB-flavoured
history book collection without downloading multi-GB dumps:

  Route 1  Open Library API — searches for British-Library-held books on
           historical topics (OL has catalogued millions of BL items).
  Route 2  Zenodo — finds BNB-related dataset metadata records on Zenodo.
  Route 3  Manual CSV fallback — if bl_bnb_manual.csv exists in the
           project root, it is processed directly (see Section 11 of the
           integration spec for how to obtain this file).

Source: https://ckan.publishing.service.gov.uk (+ Open Library + Zenodo)
Auth:   None
"""

import os
import re
import json
import time
import requests

from db import insert_record

SOURCE_NAME       = "BL British National Bibliography"
BNB_MANUAL_FILE   = "./bl_bnb_manual.csv"
MAX_ROWS_PER_FILE = 2000

OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"
ZENODO_API         = "https://zenodo.org/api/records"

# History topics to query in Open Library
OL_QUERIES = [
    "world war history british library",
    "colonial empire british library history",
    "ancient history medieval british library",
    "indian history mughal empire british library",
    "african history colonial british library",
    "ottoman empire history british library",
    "revolution history britain british library",
    "archaeology ancient world british library",
    "renaissance history europe british library",
    "slavery trade history british library",
]

# Zenodo BNB queries
ZENODO_QUERIES = [
    "british national bibliography",
    "british library books linked open data",
    "british library digitised books catalogue",
]

HISTORY_TERMS = [
    "history", "empire", "war", "colonial", "india", "africa",
    "asia", "ancient", "medieval", "revolution", "dynasty",
    "civilization", "ottoman", "mughal", "archaeology",
    "politics", "monarchy", "crusade", "slavery", "trade",
    "british library", "bibliography", "catalogue",
]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _safe(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "nat", "n/a", "<na>") else s


def _fetch_open_library(conn: dict, source_id: int) -> int:
    """
    Query Open Library for books related to British Library + historical topics.
    Returns count inserted.
    """
    inserted = 0
    seen_ids: set = set()
    OL_FIELDS = "title,author_name,first_publish_year,subject,key,isbn,publisher"

    for query in OL_QUERIES:
        try:
            resp = requests.get(
                OPENLIBRARY_SEARCH,
                params={
                    "q":      query,
                    "limit":  20,
                    "fields": OL_FIELDS,
                },
                timeout=20,
            )
            time.sleep(0.4)

            if resp.status_code != 200:
                print(f"  [WARN] OL HTTP {resp.status_code} for: {query[:50]}")
                continue

            docs = resp.json().get("docs", [])
            for doc in docs:
                try:
                    key    = doc.get("key", "")
                    ext_id = f"ol-{key.lstrip('/')}" if key else ""
                    if not ext_id or ext_id in seen_ids:
                        continue

                    title = _safe(doc.get("title", ""))
                    if not title:
                        continue

                    # Basic history-relevance check
                    title_low = title.lower()
                    subjects  = doc.get("subject", []) or []
                    all_text  = title_low + " " + " ".join(
                        str(s).lower() for s in subjects[:10])
                    if not any(t in all_text for t in HISTORY_TERMS):
                        continue

                    seen_ids.add(ext_id)

                    year      = doc.get("first_publish_year")
                    date_txt  = str(year) if year else ""
                    authors   = doc.get("author_name", []) or []
                    author    = authors[0] if authors else ""
                    src_url   = f"https://openlibrary.org{key}" if key else ""
                    publishers = doc.get("publisher", []) or []
                    pub        = publishers[0] if publishers else ""

                    subject_tags = subjects[:12]
                    if author:
                        subject_tags = [author] + subject_tags
                    tags = json.dumps(subject_tags)

                    summary = ""
                    if author and pub:
                        summary = f"By {author}. Published by {pub}."
                    elif author:
                        summary = f"By {author}."
                    if subjects:
                        summary += f" Subjects: {', '.join(str(s) for s in subjects[:5])}."

                    ok = insert_record(conn, source_id, {
                        "title":       title,
                        "summary":     summary[:800] or None,
                        "date_text":   date_txt,
                        "tags":        tags,
                        "source_url":  src_url,
                        "external_id": ext_id,
                        "record_type": "document",
                        "era":         None,
                    })
                    if ok:
                        inserted += 1

                except Exception as e:
                    print(f"  [WARN] OL record error: {e}")
                    continue

            print(f"  [OL] '{query[:45]}': {len(docs)} hits, "
                  f"{inserted} total inserted")

        except Exception as e:
            print(f"  [ERROR] OL query failed: {e}")
            continue

    return inserted


def _fetch_zenodo_bnb(conn: dict, source_id: int) -> int:
    """
    Fetch BNB-related dataset metadata from Zenodo.
    Returns count inserted.
    """
    inserted = 0
    seen_ids: set = set()

    for query in ZENODO_QUERIES:
        try:
            resp = requests.get(
                ZENODO_API,
                params={"q": query, "size": 10},
                timeout=30,
            )
            time.sleep(0.5)

            if resp.status_code != 200:
                continue

            hits = resp.json().get("hits", {}).get("hits", [])
            for record in hits:
                try:
                    ext_id = f"zenodo-bnb-{record.get('id','')}"
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)

                    meta  = record.get("metadata", {})
                    title = meta.get("title", "").strip()
                    if not title:
                        continue

                    # Licence check
                    lic = (meta.get("license", {}) or {}).get("id", "").lower()
                    if any(b in lic for b in ("nc", "nd")):
                        continue

                    desc   = _strip_html(meta.get("description", "") or "")[:800]
                    date   = meta.get("publication_date", "")
                    src    = (record.get("links") or {}).get("self", "")
                    kws    = meta.get("keywords") or []
                    tags   = json.dumps(kws[:15])

                    ok = insert_record(conn, source_id, {
                        "title":       title,
                        "summary":     desc or None,
                        "date_text":   date,
                        "tags":        tags,
                        "source_url":  src,
                        "external_id": ext_id,
                        "record_type": "dataset",
                    })
                    if ok:
                        inserted += 1

                except Exception as e:
                    print(f"  [WARN] Zenodo BNB record error: {e}")
                    continue

        except Exception as e:
            print(f"  [WARN] Zenodo BNB query error: {e}")
            continue

    return inserted


def _process_manual_csv(conn: dict, source_id: int) -> int:
    """Process bl_bnb_manual.csv if it exists. Returns records inserted."""
    try:
        import pandas as pd
        try:
            df = pd.read_csv(BNB_MANUAL_FILE, encoding="utf-8",    low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(BNB_MANUAL_FILE, encoding="latin-1",  low_memory=False)

        print(f"  [BNB] Manual CSV columns: {df.columns.tolist()[:12]}")
        print(f"  [BNB] Manual CSV shape:   {df.shape}")

        # Filter for history rows
        mask = df.apply(
            lambda row: row.astype(str).str.lower()
            .str.contains("|".join(HISTORY_TERMS), regex=True).any(), axis=1)
        history_df = df[mask].head(MAX_ROWS_PER_FILE)
        print(f"  [BNB] History-relevant rows: {len(history_df)}")

        col_map = {c.strip().lower(): c for c in df.columns}

        def _col(*keys):
            for k in keys:
                actual = col_map.get(k.lower())
                if actual:
                    v = _safe(history_df.iloc[0].get(actual, ""))
                    return actual  # Return column name for row-wise use
            return None

        inserted = 0
        for _, row in history_df.iterrows():
            row_d = row.to_dict()

            def _val(*keys):
                for k in keys:
                    actual = col_map.get(k.lower())
                    if actual:
                        return _safe(row_d.get(actual, ""))
                return ""

            title = _val("title", "name", "dc:title", "Title")
            if not title or len(title) < 3:
                continue

            ok = insert_record(conn, source_id, {
                "title":       title,
                "summary":     _strip_html(_val("description", "abstract",
                                                "notes", "dc:description"))[:800],
                "date_text":   _val("date", "year", "dc:date"),
                "region":      _val("place", "country", "dc:coverage"),
                "tags":        json.dumps([_val("subject", "dc:subject")] or []),
                "source_url":  _val("identifier", "url", "dc:identifier"),
                "external_id": _val("bl record id", "id", "identifier")
                                or str(hash(title)),
                "record_type": "document",
            })
            if ok:
                inserted += 1
        return inserted

    except Exception as e:
        print(f"  [WARN] Manual CSV processing error: {e}")
        return 0


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    # ── Route 0: Manual CSV fallback ─────────────────────────────────────────
    if os.path.exists(BNB_MANUAL_FILE):
        print(f"  [BNB] Processing manual CSV: {BNB_MANUAL_FILE}")
        n = _process_manual_csv(conn, source_id)
        inserted += n
        print(f"  [BNB] Manual CSV: {n} records inserted")

    # ── Route 1: Open Library history books ───────────────────────────────────
    print("  [BNB] Querying Open Library for British Library history books...")
    n = _fetch_open_library(conn, source_id)
    inserted += n
    if n:
        print(f"  [BNB] Open Library route: {n} records")

    # ── Route 2: Zenodo BNB dataset metadata ─────────────────────────────────
    print("  [BNB] Fetching BNB-related Zenodo dataset metadata...")
    n = _fetch_zenodo_bnb(conn, source_id)
    inserted += n
    if n:
        print(f"  [BNB] Zenodo route: {n} records")

    # ── Guidance if nothing worked ─────────────────────────────────────────────
    if inserted == 0:
        print("  [DIAG] 0 records from BNB.")
        print("  Manual fallback: Download BNB CSV from bl.iro.bl.uk,")
        print("  save as bl_bnb_manual.csv in project root, then re-run.")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
