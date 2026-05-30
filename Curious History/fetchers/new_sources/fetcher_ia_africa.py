"""
fetcher_ia_africa.py — Internet Archive: African Historical Collections

Queries the Internet Archive for sub-Saharan Africa, North Africa, and
pan-African history texts. All queries enforce language:English so users
only see readable English summaries — not raw African-language manuscripts.

Auth    : None required
License : Public Domain / CC — commercial OK
Coverage: Africa (all regions), African history ancient–modern
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Internet Archive — Africa"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# (query, era, region) — ALL enforce language:English
IA_QUERIES = [
    # North Africa
    ('subject:"Egypt history" mediatype:texts language:English',
     "African History — North Africa", "North Africa"),
    ('subject:"North Africa" subject:"history" mediatype:texts language:English',
     "African History — North Africa", "North Africa"),
    ('subject:"Algeria" subject:"history" mediatype:texts language:English',
     "African History — North Africa", "North Africa"),
    ('subject:"Tunisia" OR subject:"Morocco" subject:"history" mediatype:texts language:English',
     "African History — North Africa", "North Africa"),
    # West Africa
    ('subject:"West Africa" subject:"history" mediatype:texts language:English',
     "African History — West Africa", "West Africa"),
    ('subject:"Ghana" OR subject:"Mali Empire" mediatype:texts language:English',
     "African History — West Africa", "West Africa"),
    ('subject:"Songhai" OR subject:"Timbuktu" mediatype:texts language:English',
     "African History — West Africa", "West Africa"),
    ('subject:"Nigeria" subject:"history" mediatype:texts language:English',
     "African History — West Africa", "West Africa"),
    ('subject:"Benin Kingdom" OR subject:"Yoruba" mediatype:texts language:English',
     "African History — West Africa", "West Africa"),
    # East Africa
    ('subject:"East Africa" subject:"history" mediatype:texts language:English',
     "African History — East Africa", "East Africa"),
    ('subject:"Ethiopia" OR subject:"Abyssinia" subject:"history" mediatype:texts language:English',
     "African History — East Africa", "East Africa"),
    ('subject:"Kenya" OR subject:"Tanzania" subject:"history" mediatype:texts language:English',
     "African History — East Africa", "East Africa"),
    # Southern Africa
    ('subject:"South Africa" subject:"history" mediatype:texts language:English',
     "African History — Southern Africa", "Southern Africa"),
    ('subject:"Zulu" OR subject:"Zimbabwe" subject:"history" mediatype:texts language:English',
     "African History — Southern Africa", "Southern Africa"),
    # Central Africa
    ('"Congo" subject:"history" mediatype:texts language:English',
     "African History — Central Africa", "Central Africa"),
    # African colonialism
    ('subject:"African colonialism" OR subject:"scramble for Africa" mediatype:texts language:English',
     "African History — Colonialism", "Africa"),
    ('subject:"decolonization Africa" mediatype:texts language:English',
     "African History — Decolonisation", "Africa"),
    # African kingdoms and civilisations
    ('subject:"African kingdoms" OR subject:"Great Zimbabwe" mediatype:texts language:English',
     "African History — Ancient Kingdoms", "Africa"),
    ('"Swahili coast" subject:"history" mediatype:texts language:English',
     "African History — East Africa", "East Africa"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _is_readable_english(text: str) -> bool:
    """Return True only if text is readable English — not raw African-language text."""
    if not text or len(text.strip()) < 20:
        return False
    t = text.strip()
    non_latin = sum(1 for c in t if ord(c) > 0x024F)
    if non_latin / max(len(t), 1) > 0.08:
        return False
    words = t.split()
    english = sum(1 for w in words if len(w) > 3 and w.isalpha()
                  and all(ord(c) < 128 for c in w))
    return english >= 4


def _infer_region(title: str, subjects: list) -> str:
    """Return the most specific African region from title/subjects."""
    text = (title + " " + " ".join(subjects)).lower()
    if any(k in text for k in ["egypt", "north africa", "algeria", "morocco",
                                "tunisia", "libya", "sahara"]):
        return "North Africa"
    if any(k in text for k in ["nigeria", "ghana", "mali", "west africa", "senegal",
                                "ivory coast", "benin", "guinea", "timbuktu", "songhai"]):
        return "West Africa"
    if any(k in text for k in ["ethiopia", "kenya", "tanzania", "east africa",
                                "somalia", "uganda", "rwanda", "swahili", "abyssinia"]):
        return "East Africa"
    if any(k in text for k in ["south africa", "zimbabwe", "zulu", "botswana",
                                "mozambique", "zambia", "rhodesia"]):
        return "Southern Africa"
    if any(k in text for k in ["congo", "central africa", "cameroon", "angola"]):
        return "Central Africa"
    return "Africa"


def _infer_era(region: str, subjects: list, title: str) -> str:
    text = (title + " " + " ".join(subjects)).lower()
    if any(k in text for k in ["ancient", "kingdom", "empire", "medieval",
                                "mali empire", "songhai", "great zimbabwe"]):
        return "African History — Ancient & Medieval"
    if any(k in text for k in ["colonial", "scramble", "imperialism", "british",
                                "french", "belgian", "portuguese"]):
        return "African History — Colonial Era"
    if any(k in text for k in ["independence", "decoloniz", "nationalist",
                                "liberation", "apartheid"]):
        return "African History — Independence Era"
    return "African History"


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for (query_term, default_era, default_region) in IA_QUERIES:
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
                print("  [IA-Africa] Rate limited — waiting 60s")
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

                # Skip if title is not readable English
                if not _is_readable_english(title):
                    continue

                # Skip if language field indicates non-English
                lang = doc.get("language", "")
                if isinstance(lang, list):
                    lang = " ".join(lang)
                lang_lower = lang.lower()
                if lang and not any(e in lang_lower for e in ["english", "eng", ""]):
                    if any(l in lang_lower for l in ["arabic", "french", "portuguese",
                                                      "swahili", "amharic", "hausa"]):
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
                               f"on African history from the Internet Archive.")

                region = _infer_region(title, [str(s) for s in subj])
                era    = _infer_era(region, [str(s) for s in subj], title)

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary or None,
                    "date_text":   str(doc.get("date", ""))[:20],
                    "region":      region,
                    "era":         era,
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"ia-africa-{ia_id}",
                    "record_type": "document",
                    "tags":        [str(s) for s in subj[:6]] + ["Internet Archive Africa"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [IA-Africa] Error: {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
