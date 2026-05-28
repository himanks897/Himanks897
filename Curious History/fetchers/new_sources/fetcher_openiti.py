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
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "OpenITI — Islamic Texts"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Queries targeting Islamic and Middle Eastern historical texts
IA_QUERIES = [
    # Classic Islamic history
    "language:Arabic subject:history mediatype:texts",
    "language:Persian subject:history mediatype:texts",
    # Major Islamic empires
    'subject:"Ottoman Empire" history mediatype:texts language:English',
    'subject:"Abbasid" OR subject:"Umayyad" history mediatype:texts',
    'subject:"Safavid" OR subject:"Persia" history mediatype:texts',
    'subject:"Islamic history" OR subject:"Islamic civilization" mediatype:texts',
    # Islamic Golden Age
    '"Islamic Golden Age" history mediatype:texts',
    'subject:"Caliphate" history mediatype:texts language:English',
    # Regional Islamic history
    'subject:"Egypt Islamic" OR subject:"Fatimid" mediatype:texts',
    'subject:"Crusades" history mediatype:texts language:English',
    'subject:"Andalusia" OR subject:"Moorish Spain" history mediatype:texts',
    # Quran / religious-historical
    '"Al-Tabari" OR "Ibn Khaldun" OR "Ibn Battuta" mediatype:texts',
    # Modern Middle East
    'subject:"Palestine history" OR subject:"Arab nationalism" mediatype:texts',
    'subject:"Iran history" mediatype:texts language:English',
    'subject:"Iraq history" mediatype:texts language:English',
    'subject:"Syria history" OR subject:"Lebanon history" mediatype:texts',
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


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
    if any(k in text for k in ["arabia", "saudi", "mecca", "medina", "quran"]):
        return "Arabian Peninsula"
    if any(k in text for k in ["andalusia", "spain", "moorish", "iberia"]):
        return "Al-Andalus"
    return "Middle East"


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
                    "era":         "Islamic History",
                    "source_url":  f"https://archive.org/details/{ia_id}",
                    "external_id": f"iti-{ia_id}",
                    "record_type": "document",
                    "tags":        subj[:6] + ["Islamic History", "OpenITI"],
                })
                if ok:
                    inserted += 1

            time.sleep(0.8)

        except Exception as e:
            print(f"  [OpenITI] Error for '{query_term[:40]}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
