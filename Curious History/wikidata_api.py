import requests

HEADERS  = {"User-Agent": "CuriousHistory/1.0 (dev@curioushistory.app)"}
WD_API   = "https://www.wikidata.org/w/api.php"

def get_wikidata_facts(topic):
    try:
        r = requests.get(WD_API, headers=HEADERS, params={
            "action": "wbsearchentities", "search": topic,
            "language": "en", "format": "json", "limit": 1
        }, timeout=10)
        r.raise_for_status()
        results = r.json().get("search", [])
        if not results:
            return None
        e = results[0]
        return {
            "entity_id":   e.get("id", ""),
            "label":       e.get("label", ""),
            "description": e.get("description", ""),
            "url":         e.get("url", ""),
            "wikidata_url": f"https://www.wikidata.org/wiki/{e.get('id','')}",
            "source":      "Wikidata"
        }
    except Exception:
        return None

def run_sparql(query):
    try:
        r = requests.get(
            "https://query.wikidata.org/sparql",
            params={"query": query, "format": "json"},
            headers={**HEADERS, "Accept": "application/sparql-results+json"},
            timeout=15
        )
        r.raise_for_status()
        return r.json()["results"]["bindings"]
    except Exception:
        return []
