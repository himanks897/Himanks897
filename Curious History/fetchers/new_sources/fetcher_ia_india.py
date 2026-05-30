"""
fetcher_ia_india.py — Internet Archive: Indian Historical Collections

Queries the Internet Archive for Indian history texts. All queries enforce
language:English so users only see readable English content — not raw
Sanskrit, Hindi, Urdu, Tamil, or other Indian-language manuscripts.

Auth    : None required
License : Public Domain / CC — commercial OK
Coverage: India (ancient, medieval, colonial, modern), South Asia
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Internet Archive — India"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# (query, era, region) — ALL enforce language:English
IA_QUERIES = [
    # Ancient India
    ('subject:"ancient India" mediatype:texts language:English',
     "Indian History — Ancient", "India"),
    ('subject:"Maurya" OR subject:"Gupta" subject:"history" mediatype:texts language:English',
     "Indian History — Ancient", "India"),
    ('subject:"Indus Valley" OR subject:"Harappa" mediatype:texts language:English',
     "Indian History — Indus Valley Civilisation", "India"),
    ('subject:"Ashoka" OR subject:"Buddhism India" mediatype:texts language:English',
     "Indian History — Ancient", "India"),
    # Medieval India
    ('subject:"Mughal" subject:"history" mediatype:texts language:English',
     "Indian History — Mughal Empire", "India"),
    ('subject:"Delhi Sultanate" OR subject:"medieval India" mediatype:texts language:English',
     "Indian History — Medieval", "India"),
    ('subject:"Vijayanagara" OR subject:"Maratha" mediatype:texts language:English',
     "Indian History — Medieval", "India"),
    # Colonial India
    ('subject:"British India" subject:"history" mediatype:texts language:English',
     "Indian History — British Colonial", "India"),
    ('subject:"East India Company" subject:"history" mediatype:texts language:English',
     "Indian History — British Colonial", "India"),
    ('subject:"Indian Rebellion 1857" OR subject:"Sepoy Mutiny" mediatype:texts language:English',
     "Indian History — Colonial", "India"),
    # Independence era
    ('subject:"Indian independence" mediatype:texts language:English',
     "Indian History — Independence", "India"),
    ('subject:"Gandhi" subject:"India" mediatype:texts language:English',
     "Indian History — Independence", "India"),
    ('subject:"partition India" OR subject:"Bengal partition" mediatype:texts language:English',
     "Indian History — Partition", "India"),
    # Pakistan / Bangladesh
    ('subject:"Pakistan history" mediatype:texts language:English',
     "South Asian History — Pakistan", "Pakistan"),
    ('subject:"Sri Lanka history" OR subject:"Ceylon history" mediatype:texts language:English',
     "South Asian History — Sri Lanka", "Sri Lanka"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _is_readable_english(text: str) -> bool:
    """Return True only if text is readable English — not Sanskrit/Hindi/Urdu."""
    if not text or len(text.strip()) < 20:
        return False
    t = text.strip()
    # Reject if >8 % non-Latin characters (Devanagari, Tamil, Arabic script, etc.)
    non_latin = sum(1 for c in t if ord(c) > 0x024F)
    if non_latin / max(len(t), 1) > 0.08:
        return False
    words = t.split()
    english = sum(1 for w in words if len(w) > 3 and w.isalpha()
                  and all(ord(c) < 128 for c in w))
    return english >= 4


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for (query_term, era, region) in IA_QUERIES:
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
                time.sleep(1)
                continue

            docs = resp.json().get("response", {}).get("docs", [])

            for doc in docs:
                ia_id = doc.get("identifier", "")
                title = _strip_html(str(doc.get("title") or "")).strip()
                if not ia_id or not title or ia_id in seen_ids:
                    continue

                # Language guard — skip non-English items
                lang = doc.get("language", "")
                if isinstance(lang, list):
                    lang = " ".join(lang)
                lang_lower = lang.lower()
                if lang_lower and not any(e in lang_lower for e in ["english", "eng"]):
                    if any(l in lang_lower for l in ["hindi", "sanskrit", "urdu",
                                                      "tamil", "telugu", "bengali",
                                                      "marathi", "gujarati"]):
                        continue

                # Title readability guard
                if not _is_readable_english(title):
                    continue

                seen_ids.add(ia_id)

                subj = doc.get("subject", [])
                if isinstance(subj, str):
                    subj = [subj]

                raw_desc = doc.get("description", "")
                if isinstance(raw_desc, list):
                    raw_desc = " ".join(raw_desc)
                summary = _strip_html(str(raw_desc))[:500]

                if summary and not _is_readable_english(summary):
                    summary = (f"{title}: an English-language historical text "
                               f"on {era} from the Internet Archive.")

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary or None,
                    "date_text":   str(doc.get("date", ""))[:20],
                    "region":      region,
                    "era":         era,
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"ia-india-{ia_id}",
                    "record_type": "document",
                    "tags":        [str(s) for s in subj[:6]] + ["Internet Archive India",
                                                                   "South Asia"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [IA-India] Error for query: {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
