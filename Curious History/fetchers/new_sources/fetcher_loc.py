"""
fetcher_loc.py — Library of Congress (loc.gov)

The Library of Congress provides free JSON search API access to its
digital collections, including the World Digital Library content
(now integrated into loc.gov).

Endpoint : https://www.loc.gov/search/?q={query}&fo=json
Auth     : None required
License  : US Government works = Public Domain (17 USC §105) — commercial OK
Docs     : https://www.loc.gov/apis/json-and-yaml-output/
Coverage : Americas (strong), World history, Asia, Africa
"""

import time
import requests
from db import insert_record

SOURCE_NAME = "Library of Congress"
BASE_URL    = "https://www.loc.gov/search/"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json",
}

QUERIES = [
    # Latin America
    "Mexico colonial history Aztec",
    "Peru history Inca Empire",
    "Argentina history colonial independence",
    "Brazil history colonial",
    "Colombia Venezuela history",
    "Bolivia Ecuador history",
    "Caribbean history colonial",
    "Latin American independence revolution",
    "Cuba history colonial",
    "Chile history colonial independence",
    # Asia
    "China history dynasty imperial",
    "Japan history feudal Meiji",
    "Korea history Joseon",
    "India history colonial British",
    "Vietnam history French colonial",
    "Philippines history Spanish American",
    "Indonesia history colonial",
    # Africa
    "Africa history colonialism",
    "Congo history Leopold",
    "Kenya history colonial independence",
    # Middle East
    "Ottoman Empire history",
    "Palestine history",
    "Egypt history modern ancient",
    # Americas (general)
    "American Revolution history",
    "Civil War United States",
    "World War II American",
    "Native American history",
    "Slavery United States history",
]

_ALLOWED_FORMATS = {
    "photograph", "map", "manuscript",
    "text", "periodical", "book", "newspaper",
}


def _safe_str(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v).strip()
    return str(val).strip()


def _infer_region(query: str, subjects: list) -> str:
    text = (query + " " + " ".join(subjects)).lower()
    latin_am = ["mexico", "peru", "argentina", "brazil", "colombia",
                "venezuela", "bolivia", "ecuador", "caribbean", "latin america",
                "chile", "cuba", "inca", "aztec"]
    asia_kw  = ["china", "japan", "korea", "india", "vietnam", "philippines",
                "indonesia", "asia"]
    africa_kw = ["africa", "congo", "kenya"]
    mideast   = ["ottoman", "palestine", "egypt", "middle east"]
    if any(k in text for k in latin_am):
        return "Latin America"
    if any(k in text for k in asia_kw):
        return "Asia"
    if any(k in text for k in africa_kw):
        return "Africa"
    if any(k in text for k in mideast):
        return "Middle East"
    return "United States"


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    for query in QUERIES:
        try:
            params = {
                "q":  query,
                "fo": "json",
                "c":  20,
                "sp": 1,
                "fa": "online-format:online text|online-format:image",
            }
            resp = requests.get(BASE_URL, headers=HEADERS,
                                params=params, timeout=25)

            if resp.status_code != 200:
                time.sleep(1)
                continue

            try:
                data = resp.json()
            except ValueError:
                time.sleep(0.5)
                continue

            results = data.get("results", [])

            for item in results:
                title    = _safe_str(item.get("title"))
                item_id  = item.get("id") or item.get("url") or ""
                src_url  = item.get("url") or item.get("id") or ""
                if not src_url.startswith("http"):
                    src_url = f"https://www.loc.gov{src_url}"
                date_v   = _safe_str(item.get("date") or item.get("dates") or "")[:20]
                desc_raw = item.get("description") or item.get("summary") or ""
                summary  = _safe_str(desc_raw)[:500]
                subjects = item.get("subject") or item.get("topics") or []
                if isinstance(subjects, str):
                    subjects = [subjects]

                if not title or not src_url:
                    continue

                region = _infer_region(query, [str(s) for s in subjects])

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary or None,
                    "date_text":   date_v,
                    "region":      region,
                    "source_url":  src_url,
                    "external_id": f"loc-{str(item_id).replace('/', '-')[-60:]}",
                    "record_type": "document",
                    "tags":        [str(s)[:60] for s in subjects[:6]]
                                   + ["Library of Congress", query[:40]],
                })
                if ok:
                    inserted += 1

            time.sleep(0.7)

        except requests.RequestException as e:
            print(f"  [LOC] Request error '{query}': {e}")
            time.sleep(2)
        except Exception as e:
            print(f"  [LOC] Error '{query}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
