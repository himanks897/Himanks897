"""
Fetcher — Wikidata pipeline.

Pre-fetches structured entity data (descriptions, key properties) for major
historical entities from Wikidata and stores them as searchable text records
in the pipeline DB.

Why?  The live wikidata_api.py answers /api/multi-facts at query-time.
Pre-fetching the same entities means they also appear in ranked full-text
search results (alongside IA / Wikipedia / Cabinet Papers records).

API used: Wikidata Wikibase REST API (no key needed)
  https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q362&languages=en
Rate limit: 0.5 s between requests.
"""

import time
import re
import requests
from db import insert_record

SOURCE_NAME = "Wikidata"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# (QID, human-readable title used for display + era/region detection)
ENTITIES = [
    # ── Wars ──────────────────────────────────────────────────────────────────
    ("Q361",    "World War I"),
    ("Q362",    "World War II"),
    ("Q8676",   "American Civil War"),
    ("Q6534",   "French Revolution"),
    ("Q42523",  "Black Death"),
    ("Q9159",   "Crusades"),
    ("Q812817", "Hundred Years War"),
    ("Q154697", "Thirty Years War"),
    ("Q215536", "Crimean War"),
    ("Q8463",   "Cold War"),
    ("Q6534",   "French Revolution"),
    ("Q21590",  "Russian Revolution"),
    ("Q219067", "Haitian Revolution"),
    ("Q179225", "American Revolution"),
    ("Q50858",  "Industrial Revolution"),

    # ── Empires & states ──────────────────────────────────────────────────────
    ("Q1747689","Roman Empire"),
    ("Q6507",   "Roman Republic"),
    ("Q161885", "British Empire"),
    ("Q12560",  "Ottoman Empire"),
    ("Q12551",  "Mongol Empire"),
    ("Q2741392","Persian Empire"),
    ("Q12544",  "Byzantine Empire"),
    ("Q33673",  "Mughal Empire"),
    ("Q7178",   "Qing dynasty"),
    ("Q9683",   "Han dynasty"),
    ("Q133492", "Holy Roman Empire"),

    # ── Historical people ─────────────────────────────────────────────────────
    ("Q8409",   "Alexander the Great"),
    ("Q1048",   "Julius Caesar"),
    ("Q1413",   "Cleopatra"),
    ("Q720",    "Genghis Khan"),
    ("Q517",    "Napoleon Bonaparte"),
    ("Q352",    "Adolf Hitler"),
    ("Q1001",   "Mahatma Gandhi"),
    ("Q91",     "Abraham Lincoln"),
    ("Q8016",   "Winston Churchill"),
    ("Q7200",   "Mao Zedong"),
    ("Q7552",   "Vladimir Lenin"),
    ("Q9068",   "Karl Marx"),
    ("Q9439",   "Queen Victoria"),
    ("Q82455",  "Peter the Great"),
    ("Q36450",  "Charlemagne"),
    ("Q9411",   "Saladin"),
    ("Q9269",   "Suleiman the Magnificent"),
    ("Q1047",   "Augustus"),
    ("Q38370",  "Attila the Hun"),
    ("Q34211",  "George Washington"),
    ("Q45661",  "Nelson Mandela"),
    ("Q6723",   "Christopher Columbus"),

    # ── Events & movements ────────────────────────────────────────────────────
    ("Q3430",   "Holocaust"),
    ("Q7209",   "Apartheid"),
    ("Q4692",   "Renaissance"),
    ("Q40591",  "Age of Exploration"),
    ("Q7181",   "Colonialism"),
    ("Q8060",   "Transatlantic slave trade"),
    ("Q11766",  "Decolonization"),

    # ── Ancient civilisations ─────────────────────────────────────────────────
    ("Q11768",  "Ancient Egypt"),
    ("Q11772",  "Ancient Greece"),
    ("Q11767",  "Ancient Rome"),
    ("Q11768",  "Mesopotamia"),
    ("Q11806",  "Indus Valley Civilisation"),
    ("Q12539",  "Aztec Empire"),
    ("Q49005",  "Inca Empire"),
]


def _fetch_entity(qid: str) -> dict:
    """
    Fetch label + description + a few claims for a Wikidata entity.
    Returns a simple dict; empty dict on failure.
    """
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action":    "wbgetentities",
        "ids":       qid,
        "languages": "en",
        "props":     "labels|descriptions|claims",
        "format":    "json",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        entities = data.get("entities", {})
        return entities.get(qid, {})
    except Exception:
        return {}


def _label(entity: dict) -> str:
    return (entity.get("labels", {}).get("en", {}) or {}).get("value", "")


def _description(entity: dict) -> str:
    return (entity.get("descriptions", {}).get("en", {}) or {}).get("value", "")


def _claim_values(entity: dict, prop: str) -> list:
    """Return string values for a specific property claim (best-effort)."""
    claims = entity.get("claims", {}).get(prop, [])
    values = []
    for claim in claims[:3]:
        try:
            snak = claim.get("mainsnak", {})
            dv   = snak.get("datavalue", {})
            typ  = dv.get("type", "")
            val  = dv.get("value")
            if typ == "string":
                values.append(str(val))
            elif typ == "monolingualtext":
                values.append(val.get("text", ""))
            elif typ == "time":
                # e.g. "+1939-09-01T00:00:00Z"
                t = val.get("time", "")
                # Strip down to year: "+1939-..."  → "1939"
                m = re.match(r'[+-]?(\d{4})', t)
                if m:
                    values.append(m.group(1))
            elif typ == "wikibase-entityid":
                # Return the QID (caller can fetch label separately if needed)
                values.append(val.get("id", ""))
        except Exception:
            continue
    return values


def _build_summary(entity: dict, title: str) -> str:
    """
    Build a one-paragraph text summary from Wikidata entity fields.
    Combines description + inception date + end date + location where available.
    """
    label       = _label(entity) or title
    description = _description(entity)

    parts = [f"{label}: {description}." if description else f"{label}."]

    # P571 = inception / founded, P576 = dissolved
    start_dates = _claim_values(entity, "P571") or _claim_values(entity, "P580")
    end_dates   = _claim_values(entity, "P576") or _claim_values(entity, "P582")
    if start_dates:
        parts.append(f"Started: {start_dates[0]}.")
    if end_dates:
        parts.append(f"Ended: {end_dates[0]}.")

    # P17 = country, P131 = located in admin. entity
    countries = _claim_values(entity, "P17")
    if countries:
        parts.append(f"Country: {', '.join(countries[:2])}.")

    return " ".join(parts)


_ERA_KEYWORDS = {
    "Classical Antiquity": [
        "ancient", "antiquity", "roman republic", "roman empire",
        "ancient egypt", "ancient greece", "mesopotamia",
        "1st century", "2nd century", "3rd century", "4th century",
        "alexander the great", "julius caesar", "cleopatra",
        "carthage", "phoenicia", "athen", "sparta",
    ],
    "Medieval": [
        "middle ages", "medieval", "crusade", "byzantine",
        "charlemagne", "feudal", "genghis khan", "black death",
        "viking", "5th century", "6th century", "7th century",
        "8th century", "9th century", "10th century", "11th century",
        "12th century", "13th century", "14th century",
    ],
    "Early Modern": [
        "renaissance", "reformation", "ottoman", "mughal",
        "colonialism", "age of exploration", "conquistador",
        "16th century", "17th century", "18th century",
        "thirty years war", "glorious revolution",
    ],
    "19th Century": [
        "industrial revolution", "napoleonic", "19th century",
        "victorian", "nationalism", "imperialism",
        "american civil war", "crimean war",
    ],
    "20th Century": [
        "world war", "cold war", "soviet", "nuclear",
        "holocaust", "apartheid", "decolonization",
        "20th century", "1914", "1939", "1945",
    ],
}


def _guess_era(text: str) -> str:
    t = text.lower()
    for era, keywords in _ERA_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return era
    return "Modern"


def fetch(conn, source_id) -> int:
    inserted  = 0
    seen_qids: set = set()

    for qid, title in ENTITIES:
        if qid in seen_qids:
            continue
        seen_qids.add(qid)

        try:
            entity = _fetch_entity(qid)
            if not entity:
                print(f"  [WARN] No Wikidata entity for {qid} ({title})")
                time.sleep(0.5)
                continue

            label   = _label(entity) or title
            summary = _build_summary(entity, title)
            if len(summary) < 20:
                time.sleep(0.5)
                continue

            era = _guess_era(summary + " " + title)

            ok = insert_record(conn, source_id, {
                "title":       label,
                "summary":     summary,
                "full_text":   summary,
                "era":         era,
                "external_id": qid,
                "source_url":  f"https://www.wikidata.org/wiki/{qid}",
                "record_type": "entity",
                "tags":        ["Wikidata", "Structured Data", era],
            })
            if ok:
                inserted += 1
                print(f"  [Wikidata] stored: {label} ({qid})")

        except Exception as e:
            print(f"  [ERROR] Wikidata {qid} ({title}): {e}")

        time.sleep(0.5)

    print(f"  [Wikidata] {inserted} records inserted")
    return inserted
