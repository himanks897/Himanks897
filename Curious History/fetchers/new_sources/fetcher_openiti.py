"""
fetcher_openiti.py — OpenITI / Islamic Texts (via Internet Archive)

The Open Islamicate Texts Initiative (OpenITI) corpus hosts 10,000+
Arabic and Persian historical texts. Since their GitHub corpus is
raw text files, we query Internet Archive which mirrors much of this
content plus other Islamic historical collections.

Auth    : None required
License : CC BY 4.0 for OpenITI metadata — commercial OK
Docs    : https://openiti.org/
Coverage: Islamic world, Arabic literature, Persian history,
          Abbasid / Umayyad / Ottoman / Safavid / Mughal eras

MANUSCRIPT RULE: Only English-language records are stored.
Raw Arabic, Persian, Ottoman Turkish, or Urdu manuscripts are never
stored or returned to users — all summaries must be readable English.
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "OpenITI — Islamic Texts"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# All queries explicitly require English-language content.
# Arabic/Persian raw-text queries removed — they returned unreadable manuscripts.
IA_QUERIES = [
    # Major Islamic empires — English scholarship
    ('subject:"Ottoman Empire" subject:"history" mediatype:texts language:English',
     "Ottoman Empire", "Turkey / Ottoman"),
    ('subject:"Abbasid" subject:"history" mediatype:texts language:English',
     "Islamic History — Abbasid Caliphate", "Iraq / Baghdad"),
    ('subject:"Umayyad" subject:"history" mediatype:texts language:English',
     "Islamic History — Umayyad Caliphate", "Syria / Damascus"),
    ('subject:"Safavid" subject:"history" mediatype:texts language:English',
     "Islamic History — Safavid Persia", "Iran"),
    ('subject:"Islamic history" mediatype:texts language:English',
     "Islamic History", "Middle East"),
    ('subject:"Islamic civilization" mediatype:texts language:English',
     "Islamic Civilisation", "Middle East"),
    # Islamic Golden Age
    ('"Islamic Golden Age" history mediatype:texts language:English',
     "Islamic Golden Age", "Middle East"),
    ('subject:"Caliphate" subject:"history" mediatype:texts language:English',
     "Islamic History — Caliphate", "Middle East"),
    # Regional Islamic history
    ('subject:"Fatimid" history mediatype:texts language:English',
     "Islamic History — Fatimid Egypt", "Egypt"),
    ('subject:"Crusades" subject:"history" mediatype:texts language:English',
     "Medieval History — Crusades", "Levant"),
    ('subject:"Moorish" OR subject:"Al-Andalus" history mediatype:texts language:English',
     "Islamic History — Al-Andalus", "Al-Andalus"),
    # Key Islamic historians and travellers
    ('"Ibn Khaldun" mediatype:texts language:English',
     "Islamic History — Ibn Khaldun", "North Africa"),
    ('"Ibn Battuta" mediatype:texts language:English',
     "Islamic History — Ibn Battuta", "Middle East"),
    # Modern Middle East
    ('subject:"Iran" subject:"history" mediatype:texts language:English',
     "Iranian History", "Iran"),
    ('subject:"Iraq" subject:"history" mediatype:texts language:English',
     "Iraqi History", "Iraq"),
    ('subject:"Arab nationalism" mediatype:texts language:English',
     "Modern Middle East", "Middle East"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _is_readable_english(text: str) -> bool:
    """Return True only if text is readable English prose."""
    if not text or len(text.strip()) < 20:
        return False
    t = text.strip()
    # Reject if >10 % non-Latin / non-ASCII characters (Arabic, Persian, etc.)
    non_latin = sum(1 for c in t if ord(c) > 0x024F)
    if non_latin / max(len(t), 1) > 0.10:
        return False
    # Require at least 4 English words (>3 letters, ASCII only)
    words = t.split()
    english = sum(1 for w in words if len(w) > 3 and w.isalpha()
                  and all(ord(c) < 128 for c in w))
    return english >= 4


def _infer_region(title: str, subjects: list) -> str:
    text = (title + " " + " ".join(subjects)).lower()
    if any(k in text for k in ["ottoman", "turkey", "anatolia", "byzantine"]):
        return "Turkey / Ottoman"
    if any(k in text for k in ["iran", "persia", "safavid"]):
        return "Iran"
    if any(k in text for k in ["iraq", "mesopotamia", "baghdad", "abbasid"]):
        return "Iraq"
    if any(k in text for k in ["egypt", "fatimid", "mamluk"]):
        return "Egypt"
    if any(k in text for k in ["palestine", "israel", "jerusalem", "crusade"]):
        return "Levant"
    if any(k in text for k in ["arabia", "saudi", "mecca", "medina"]):
        return "Arabian Peninsula"
    if any(k in text for k in ["andalusia", "spain", "moorish", "iberia", "andalus"]):
        return "Al-Andalus"
    return "Middle East"


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for (query_term, era, default_region) in IA_QUERIES:
        try:
            resp = requests.get(
                "https://archive.org/advancedsearch.php",
                headers=HEADERS,
                params={
                    "q":      f"({query_term})",
                    "fl[]":   ["identifier", "title", "date", "subject",
                               "description", "creator", "language"],
                    "sort[]": "downloads desc",
                    "rows":   20,
                    "page":   1,
                    "output": "json",
                },
                timeout=20,
            )

            if resp.status_code == 429:
                print("  [OpenITI] Rate limited — waiting 60s")
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

                # Language guard: skip non-English items
                lang = doc.get("language", "")
                if isinstance(lang, list):
                    lang = " ".join(lang)
                lang_lower = lang.lower()
                if any(l in lang_lower for l in ["arabic", "persian", "urdu", "turkish",
                                                  "farsi", "ottoman"]):
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

                # If description is non-English, replace with a scholarly stub
                if summary and not _is_readable_english(summary):
                    summary = (f"{title}: an English-language scholarly work on "
                               f"{era} from the Internet Archive.")

                region = _infer_region(title, [str(s) for s in subj])

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary or None,
                    "date_text":   str(doc.get("date", ""))[:20],
                    "region":      region,
                    "era":         era,
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"iti-{ia_id}",
                    "record_type": "document",
                    "tags":        [str(s) for s in subj[:6]] + ["Islamic History", "OpenITI"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [OpenITI] Error for '{query_term[:40]}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
