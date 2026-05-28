import requests
import time

HEADERS = {"User-Agent": "CuriousHistory/1.0 (dev@curioushistory.app)"}
BASE    = "https://en.wikipedia.org/api/rest_v1"
MW_API  = "https://en.wikipedia.org/w/api.php"


def get_article(topic):
    try:
        slug = topic.strip().replace(" ", "_")
        r    = requests.get(
            f"{BASE}/page/summary/{slug}",
            headers=HEADERS,
            timeout=10
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        return {
            "title":       d.get("title",       ""),
            "description": d.get("description", ""),
            "summary":     d.get("extract",     ""),
            "image":       d.get("thumbnail",    {}).get("source"),
            "full_image":  d.get("originalimage",{}).get("source"),
            "wiki_url":    d.get("content_urls", {})
                            .get("desktop", {}).get("page", ""),
            "wikidata_id": d.get("wikibase_item", ""),
            "latitude":    d.get("coordinates",  {}).get("lat"),
            "longitude":   d.get("coordinates",  {}).get("lon"),
            "sections":    get_sections(topic)
        }
    except requests.exceptions.ConnectionError:
        return {"error": "No internet connection. Please check your WiFi."}
    except requests.exceptions.Timeout:
        return {"error": "Wikipedia took too long to respond. Try again."}
    except Exception as e:
        return {"error": str(e)}


def search_articles(query, limit=8):
    # Uses the current REST API search endpoint (v1 /page/search was removed)
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": query, "limit": limit},
            headers=HEADERS,
            timeout=10
        )
        r.raise_for_status()
        results = []
        for page in r.json().get("pages", []):
            thumb = page.get("thumbnail") or {}
            results.append({
                "title":       page.get("title",       ""),
                "description": page.get("description", ""),
                "image":       thumb.get("url"),
                "key":         page.get("key",         "")
            })
        return results
    except Exception:
        return []


def get_related(topic, limit=6):
    # Uses MediaWiki generator=links (REST /page/related was removed)
    try:
        r = requests.get(MW_API, headers=HEADERS, params={
            "action":     "query",
            "generator":  "links",
            "titles":     topic.strip(),
            "prop":       "pageimages|description",
            "pithumbsize": 60,
            "pilimit":    limit,
            "pllimit":    limit,
            "format":     "json",
        }, timeout=10)
        r.raise_for_status()
        pages = list(r.json().get("query", {}).get("pages", {}).values())[:limit]
        results = []
        for p in pages:
            thumb = (p.get("thumbnail") or {})
            slug  = p.get("title", "").replace(" ", "_")
            results.append({
                "title":       p.get("title",       ""),
                "description": p.get("description", ""),
                "image":       thumb.get("source"),
                "wiki_url":    f"https://en.wikipedia.org/wiki/{slug}",
            })
        return results
    except Exception:
        return []


def get_sections(topic):
    try:
        slug = topic.strip().replace(" ", "_")
        r    = requests.get(MW_API, headers=HEADERS, params={
            "action": "parse", "page": slug,
            "prop": "sections", "format": "json"
        }, timeout=10)
        r.raise_for_status()
        sections = r.json().get("parse", {}).get("sections", [])
        return [s.get("line", "") for s in sections[:10]]
    except Exception:
        return []


def get_on_this_day(month, day):
    try:
        r = requests.get(
            f"{BASE}/feed/onthisday/events/{month}/{day}",
            headers=HEADERS,
            timeout=10
        )
        r.raise_for_status()
        events = r.json().get("events", [])[:10]
        return [{
            "year":  e.get("year"),
            "text":  e.get("text"),
            "pages": [p.get("title") for p in e.get("pages", [])[:2]]
        } for e in events]
    except Exception:
        return []
