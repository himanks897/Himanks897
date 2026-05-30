"""
fetcher_nomisma.py — Nomisma.org: Ancient Coins Linked Open Data

Auth     : None required — public SPARQL endpoint
License  : CC0 — fully open, commercial use allowed
Docs     : http://nomisma.org/documentation/apis/
SPARQL   : https://nomisma.org/query
Coverage : Ancient Greek, Roman, Byzantine, Persian coins

Results are readable English descriptions of ancient coin types with
historical context — not raw numismatic codes or Latin abbreviations.
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Nomisma — Ancient Coins"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/sparql-results+json",
}

SPARQL_ENDPOINT = "https://nomisma.org/query"

# Simpler SPARQL queries — fetch TypeSeriesItems with English labels,
# grouped by numismatic authority (mint-issuer) to get diverse coverage.
# Using broad filters so more items are returned.
SPARQL_QUERIES = [
    # ── Roman coins (denarius, aureus, sestertius) ────────────────────────────
    ("""
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT DISTINCT ?coin ?label ?description ?date
WHERE {
  ?coin a nmo:TypeSeriesItem ;
        skos:prefLabel ?label .
  FILTER(LANG(?label) = 'en')
  OPTIONAL { ?coin dcterms:description ?description .
             FILTER(LANG(?description) = 'en') }
  OPTIONAL { ?coin nmo:hasStartDate ?date }
  FILTER(
    REGEX(STR(?coin), 'ric|rrc|ocre|roman', 'i') ||
    REGEX(LCASE(?label), 'roman|denarius|aureus|sestertius|antoninianus', 'i')
  )
}
LIMIT 100
""", "Ancient Rome", "Roman Empire"),

    # ── Greek coins ───────────────────────────────────────────────────────────
    ("""
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT DISTINCT ?coin ?label ?description ?date
WHERE {
  ?coin a nmo:TypeSeriesItem ;
        skos:prefLabel ?label .
  FILTER(LANG(?label) = 'en')
  OPTIONAL { ?coin dcterms:description ?description .
             FILTER(LANG(?description) = 'en') }
  OPTIONAL { ?coin nmo:hasStartDate ?date }
  FILTER(
    REGEX(STR(?coin), 'greek|athens|corinth|macedon|sng|bmc.greek', 'i') ||
    REGEX(LCASE(?label), 'greek|athenian|tetradrachm|drachm|stater', 'i')
  )
}
LIMIT 80
""", "Ancient Greece", "Greece"),

    # ── Byzantine coins ───────────────────────────────────────────────────────
    ("""
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT DISTINCT ?coin ?label ?description ?date
WHERE {
  ?coin a nmo:TypeSeriesItem ;
        skos:prefLabel ?label .
  FILTER(LANG(?label) = 'en')
  OPTIONAL { ?coin dcterms:description ?description .
             FILTER(LANG(?description) = 'en') }
  OPTIONAL { ?coin nmo:hasStartDate ?date }
  FILTER(
    REGEX(STR(?coin), 'byzantine|byz|doi', 'i') ||
    REGEX(LCASE(?label), 'byzantine|solidus|nomisma|follis|tremissis', 'i')
  )
}
LIMIT 60
""", "Byzantine Empire", "Byzantine Empire"),

    # ── Broad fetch — any TypeSeriesItem with English label + description ─────
    ("""
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT DISTINCT ?coin ?label ?description ?date
WHERE {
  ?coin a nmo:TypeSeriesItem ;
        skos:prefLabel ?label ;
        dcterms:description ?description .
  FILTER(LANG(?label) = 'en')
  FILTER(LANG(?description) = 'en')
  FILTER(STRLEN(?description) > 20)
  OPTIONAL { ?coin nmo:hasStartDate ?date }
}
LIMIT 120
""", "Ancient World", "Mediterranean"),
]


# ── Built-in coin records (guaranteed baseline) ───────────────────────────────
_BUILTIN_COINS = [
    ("Athenian Tetradrachm — Owl Coin",
     "The Athenian tetradrachm (4-drachma coin), known as the 'owl' for its reverse design, was one of the most widely used coins in the ancient world from the 5th–1st centuries BCE. The obverse shows the helmeted head of Athena; the reverse shows her sacred owl with an olive sprig and the letters AOE (Athens). Minted in vast quantities from the silver mines at Laurion, Athenian owls served as an international reserve currency throughout the Mediterranean and Near East.",
     "Ancient Greece", "Greece", -480),
    ("Roman Denarius — Silver Coin",
     "The denarius was the standard Roman silver coin from 211 BCE to the 3rd century CE. It bore the portrait of the ruling emperor on the obverse and various reverse designs celebrating military victories, deities, and civic events. The word 'denarius' is the origin of the letter 'd' for pence in pre-decimal British currency. The gradual debasement of the denarius — reducing its silver content — is seen as a symptom of Rome's economic decline.",
     "Ancient Rome", "Roman Empire", -211),
    ("Roman Aureus — Gold Coin",
     "The aureus was the standard gold coin of the Roman Empire from the 1st century BCE until the 4th century CE, worth 25 silver denarii. Julius Caesar greatly increased its production to fund his campaigns. The aureus bore the emperor's portrait and was used primarily for large transactions and payments to the military. It was eventually replaced by the solidus under Constantine I.",
     "Ancient Rome", "Roman Empire", -50),
    ("Byzantine Solidus — Gold Coin",
     "The Byzantine solidus (known in the West as the bezant) was the gold coin of the Byzantine Empire, introduced by Emperor Constantine I in 312 CE and used until the 11th century. It maintained a consistent gold purity (24 carats) for over 700 years and was the dominant international currency of the medieval world. The coin featured the emperor's portrait on the obverse and a Christian cross or religious image on the reverse.",
     "Byzantine Empire", "Byzantine Empire", 312),
    ("Achaemenid Daric — Persian Gold Coin",
     "The daric was the gold coin of the Achaemenid Persian Empire, introduced by Darius I (522–486 BCE). It showed a kneeling archer (representing the king himself) on the obverse. The daric was the primary international gold coin before the spread of Greek coinage and was widely used to pay Greek mercenaries. Alexander the Great captured enormous quantities of darics when he conquered Persia.",
     "Ancient Persia", "Persia", -516),
    ("Macedonian Tetradrachm — Alexander the Great",
     "The tetradrachm issued by Alexander the Great (336–323 BCE) and his successors became the first truly international currency of the ancient world. The obverse showed the head of Heracles wearing a lion-skin headdress; the reverse showed Zeus seated on a throne. Minted across Alexander's vast empire from Greece to India, these coins standardised trade across the Hellenistic world and influenced coinage from Rome to India.",
     "Ancient Greece / Macedonia", "Macedonia", -336),
    ("Roman Sestertius — Large Bronze Coin",
     "The sestertius was a large bronze coin of the Roman Empire worth one quarter of a denarius. From Augustus onwards, it bore the emperor's portrait and elaborate reverse designs commemorating military triumphs, architectural achievements, and civic events — making it a significant medium of imperial propaganda. The term 'sestertium' (1,000 sestertii) was the standard unit of large-scale financial accounting in Rome.",
     "Ancient Rome", "Roman Empire", -23),
    ("Ptolemaic Tetradrachm — Cleopatra",
     "Ptolemaic Egypt produced silver tetradrachms bearing the portraits of its rulers. Late Ptolemaic coins bearing the portrait of Cleopatra VII (51–30 BCE) are among the most historically significant ancient coins. Unlike the idealised portraits on modern depictions, contemporary coins show her with a prominent nose and chin — a realistic portrait of the last active ruler of the Ptolemaic dynasty before Egypt became a Roman province.",
     "Ancient Egypt — Ptolemaic", "Egypt", -51),
]


def _build_coin_summary(label: str, description: str, date_val: str, era: str) -> str:
    """Build readable English description of an ancient coin."""
    parts = []
    if description and len(description.strip()) > 20:
        parts.append(description.strip())
    else:
        parts.append(f"{label}: an ancient coin from the {era} period.")
    if date_val:
        parts.append(f"Date: {date_val}.")
    return " ".join(parts)[:700]


def _parse_date(date_val: str) -> int | None:
    """Parse Nomisma date string to integer year (negative = BCE)."""
    if not date_val:
        return None
    try:
        return int(date_val)
    except (ValueError, TypeError):
        m = re.search(r'-?\d+', str(date_val))
        if m:
            return int(m.group())
    return None


def _try_sparql(sparql: str) -> list:
    """POST/GET the SPARQL query and return bindings list."""
    for method, kwargs in [
        ("POST", {"data": {"query": sparql.strip()}}),
        ("GET",  {"params": {"query": sparql.strip(), "format": "json"}}),
    ]:
        try:
            if method == "POST":
                resp = requests.post(SPARQL_ENDPOINT, headers=HEADERS,
                                     timeout=30, **kwargs)
            else:
                resp = requests.get(SPARQL_ENDPOINT, headers={
                    **HEADERS, "Accept": "application/sparql-results+json,application/json"
                }, timeout=30, **kwargs)

            if resp.status_code in (200, 206):
                data = resp.json()
                bindings = data.get("results", {}).get("bindings", [])
                if bindings:
                    return bindings
        except Exception:
            continue
    return []


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # ── Phase 1: Built-in coin records (guaranteed baseline) ──────────────────
    for (title, summary, era, region, year) in _BUILTIN_COINS:
        ext_id = f"nomisma_builtin_{title[:35].lower().replace(' ', '_')}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        ok = insert_record(conn, source_id, {
            "title":           title,
            "summary":         summary,
            "record_type":     "artefact",
            "region":          region,
            "era":             era,
            "date_year_start": year,
            "source_url":      "https://nomisma.org/",
            "external_id":     ext_id,
            "tags":            ["coins", "numismatics", "ancient", era, region,
                                "Nomisma"],
        })
        if ok:
            inserted += 1
    print(f"  [Nomisma] {inserted} built-in records loaded")

    # ── Phase 2: Live SPARQL queries ───────────────────────────────────────────
    for (sparql, era, region) in SPARQL_QUERIES:
        bindings = _try_sparql(sparql)
        if not bindings:
            print(f"  [Nomisma] No results for {era} SPARQL query")
            time.sleep(1)
            continue

        query_count = 0
        for binding in bindings:
            def _val(k):
                return (binding.get(k) or {}).get("value") or ""

            coin_uri    = _val("coin")
            label       = _val("label").strip()
            description = _val("description").strip()
            date_str    = _val("date")

            if not label:
                continue

            ext_id = coin_uri.rstrip("/").split("/")[-1] if coin_uri else label[:40]
            ext_id = f"nomisma_{ext_id}"
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            title   = f"{label} — {era} coin"
            summary = _build_coin_summary(label, description, date_str, era)
            year    = _parse_date(date_str)

            tags = [t for t in ["coins", "numismatics", "ancient", era, region]
                    if t and len(t) > 1]

            ok = insert_record(conn, source_id, {
                "title":           title,
                "summary":         summary,
                "record_type":     "artefact",
                "region":          region,
                "era":             era,
                "date_text":       date_str or era,
                "date_year_start": year,
                "source_url":      coin_uri or "https://nomisma.org/",
                "external_id":     ext_id,
                "tags":            tags,
            })
            if ok:
                inserted  += 1
                query_count += 1
                if inserted % 25 == 0:
                    print(f"  [Nomisma] {inserted} records so far…")

        print(f"  [Nomisma] {era}: {query_count} live coin records")
        time.sleep(1.5)

    print(f"  [Nomisma] {inserted} ancient coin records inserted")
    return inserted
