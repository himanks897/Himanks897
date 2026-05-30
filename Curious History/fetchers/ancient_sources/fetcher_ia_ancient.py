"""
fetcher_ia_ancient.py — Internet Archive: Ancient Civilisations Texts

Auth     : None required
License  : Public Domain / CC — commercial use allowed
Coverage : Ancient Greece, Ancient Rome, Ancient Egypt, Mesopotamia

Searches Internet Archive for scholarly English-language texts on the four
ancient civilisations. Only English-language texts are fetched (no raw Greek,
Latin, or hieroglyphic manuscripts delivered to users).
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Internet Archive — Ancient History"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

IA_SEARCH   = "https://archive.org/advancedsearch.php"

# (query, era, region) — specifically targeting ancient history scholarship
IA_QUERIES = [
    # ── Ancient Greece ────────────────────────────────────────────────────────
    ('subject:"ancient Greece" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('subject:"Greek history" subject:"ancient" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('subject:"Athens" subject:"ancient" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('subject:"Sparta" subject:"ancient" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('"ancient Greek" subject:"history" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('subject:"Alexander the Great" mediatype:texts language:English',
     "Ancient Greece / Macedonia", "Greece"),
    ('subject:"Peloponnesian War" mediatype:texts language:English',
     "Ancient Greece", "Greece"),
    ('subject:"Persian Wars" subject:"ancient" mediatype:texts language:English',
     "Ancient Greece / Persia", "Greece"),
    # ── Ancient Rome ──────────────────────────────────────────────────────────
    ('subject:"ancient Rome" mediatype:texts language:English',
     "Ancient Rome", "Italy"),
    ('subject:"Roman Empire" subject:"history" mediatype:texts language:English',
     "Ancient Rome", "Roman Empire"),
    ('subject:"Roman Republic" mediatype:texts language:English',
     "Ancient Rome", "Italy"),
    ('subject:"Julius Caesar" mediatype:texts language:English',
     "Ancient Rome", "Roman Empire"),
    ('"Roman civilization" mediatype:texts language:English',
     "Ancient Rome", "Roman Empire"),
    ('subject:"Pompeii" mediatype:texts language:English',
     "Ancient Rome", "Italy"),
    ('subject:"Byzantine Empire" mediatype:texts language:English',
     "Byzantine Empire", "Byzantine Empire"),
    # ── Ancient Egypt ─────────────────────────────────────────────────────────
    ('subject:"ancient Egypt" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('subject:"Egyptian history" subject:"ancient" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('subject:"pharaoh" subject:"ancient Egypt" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('subject:"Egyptian mythology" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('"Nile civilization" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('subject:"Cleopatra" subject:"Egypt" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    ('subject:"Tutankhamun" OR subject:"Ramesses" mediatype:texts language:English',
     "Ancient Egypt", "Egypt"),
    # ── Ancient Mesopotamia ───────────────────────────────────────────────────
    ('subject:"Mesopotamia" subject:"history" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia"),
    ('subject:"Babylonian" subject:"history" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia — Babylon"),
    ('subject:"Assyrian" subject:"history" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia — Assyria"),
    ('subject:"Sumerian" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia — Sumer"),
    ('"Epic of Gilgamesh" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia"),
    ('subject:"ancient Near East" mediatype:texts language:English',
     "Ancient Near East", "Near East"),
    ('"Hammurabi" subject:"law" OR subject:"Babylon" mediatype:texts language:English',
     "Ancient Mesopotamia", "Mesopotamia — Babylon"),
]

_ERA_REGION_MAP = {
    "greece":      ("Ancient Greece", "Greece"),
    "roman":       ("Ancient Rome",   "Roman Empire"),
    "egypt":       ("Ancient Egypt",  "Egypt"),
    "mesopotamia": ("Ancient Mesopotamia", "Mesopotamia"),
    "babylon":     ("Ancient Mesopotamia", "Mesopotamia — Babylon"),
    "assyria":     ("Ancient Mesopotamia", "Mesopotamia — Assyria"),
    "sumer":       ("Ancient Mesopotamia", "Mesopotamia — Sumer"),
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _infer_era_region(title: str, subjects: list, default_era: str, default_region: str):
    text = (title + " " + " ".join(subjects)).lower()
    for keyword, (era, region) in _ERA_REGION_MAP.items():
        if keyword in text:
            return era, region
    return default_era, default_region


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    for (query, era, region) in IA_QUERIES:
        try:
            resp = requests.get(
                IA_SEARCH,
                headers=HEADERS,
                params={
                    "q":      query,
                    "fl[]":   ["identifier", "title", "date", "subject",
                               "description", "creator", "language"],
                    "sort[]": "downloads desc",
                    "rows":   25,
                    "page":   1,
                    "output": "json",
                },
                timeout=20,
            )
        except Exception as e:
            print(f"  [IA-Ancient] Request error for '{query[:50]}': {e}")
            time.sleep(2)
            continue

        if resp.status_code == 429:
            print("  [IA-Ancient] Rate limited — sleeping 60s")
            time.sleep(60)
            continue
        if resp.status_code != 200:
            time.sleep(0.5)
            continue

        try:
            docs = resp.json().get("response", {}).get("docs", [])
        except Exception:
            continue

        for doc in docs:
            ext_id = doc.get("identifier", "")
            if not ext_id or ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            title = _strip_html(doc.get("title") or "").strip()
            if not title:
                continue

            # Skip titles that look like they're original-language editions
            # (e.g. "Iliad in Greek", "Aeneid Latin text")
            title_lower = title.lower()
            if any(s in title_lower for s in
                   ["text in greek", "latin text", "greek text only",
                    "hieroglyphic text", "cuneiform text"]):
                continue

            subj = doc.get("subject") or []
            if not isinstance(subj, list):
                subj = [subj] if subj else []

            summary = _strip_html(str(doc.get("description") or ""))[:600]
            if not summary:
                creator = doc.get("creator") or ""
                summary = (f"{title}. A scholarly English-language text on {era} "
                           f"from the Internet Archive. "
                           + (f"Author: {creator}." if creator else ""))

            rec_era, rec_region = _infer_era_region(title, subj, era, region)

            # Parse date
            date_raw  = str(doc.get("date") or "")
            year      = None
            m = re.search(r'(\d{4})', date_raw)
            if m:
                yr = int(m.group(1))
                if 1400 <= yr <= 2024:   # publication year, not historical year
                    year = None           # publication dates are not historical dates
                    date_raw = date_raw   # keep as text for reference

            tags = [t for t in [
                "ancient history", rec_era, rec_region,
            ] + subj[:4] if t and len(t) > 1]

            ok = insert_record(conn, source_id, {
                "title":       title,
                "summary":     summary,
                "record_type": "document",
                "region":      rec_region,
                "era":         rec_era,
                "date_text":   date_raw,
                "source_url":  f"https://archive.org/details/{ext_id}",
                "external_id": f"ia_ancient_{ext_id}",
                "tags":        tags,
            })
            if ok:
                inserted += 1
                if inserted % 30 == 0:
                    print(f"  [IA-Ancient] {inserted} records so far…")

        time.sleep(0.5)

    print(f"  [IA-Ancient] {inserted} records inserted")
    return inserted
