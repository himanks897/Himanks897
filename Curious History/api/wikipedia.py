"""
wikipedia.py — Fetches historical content from Wikipedia REST API and Wikidata.
Primary text source for all event lookups, "On This Day", and people lookups.
Returns plain dicts; all HTML formatting is done by gemini_synthesis.py.
"""

import requests
import re
from api import cache
from config import Config

BASE = "https://en.wikipedia.org/api/rest_v1"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

HEADERS = {"User-Agent": Config.WIKIMEDIA_USER_AGENT}


def _get(url, params=None, timeout=10):
    """Makes a GET request with caching. Returns parsed JSON or None."""
    key = f"wiki:{url}:{str(params)}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        cache.set(key, data, ttl=3600)
        return data
    except Exception:
        return None


def search_wikipedia(query: str, limit: int = 5):
    """
    Searches Wikipedia for pages matching the query.
    Returns a list of {title, snippet, pageid} dicts.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "srprop": "snippet|titlesnippet",
    }
    data = _get(WIKI_API, params)
    if not data:
        return []
    return [
        {"title": r["title"], "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", "")), "pageid": r["pageid"]}
        for r in data.get("query", {}).get("search", [])
    ]


def _clean_wikitext(wikitext: str) -> str:
    """
    Converts raw MediaWiki markup to clean plain English text.
    Strips templates, references, tables, file/image links, HTML, non-English
    parentheticals, and all MediaWiki markup characters.
    Section headers (== Title ==) are preserved for the article formatter.
    """
    import html as _html
    t = wikitext

    # Remove table markup
    t = re.sub(r'\{\|.*?\|\}', '', t, flags=re.DOTALL)
    # Remove templates {{...}} — nested-safe with iterative stripping
    for _ in range(6):
        t = re.sub(r'\{\{[^{}]*\}\}', '', t)
    # Remove <ref ...> ... </ref> references
    t = re.sub(r'<ref[^>]*/>', '', t)
    t = re.sub(r'<ref[^>]*>.*?</ref>', '', t, flags=re.DOTALL)
    # Remove HTML comments
    t = re.sub(r'<!--.*?-->', '', t, flags=re.DOTALL)
    # Remove HTML tags (keep text)
    t = re.sub(r'<[^>]+>', '', t)
    # Convert HTML entities to real characters (&nbsp; → space, &amp; → &, etc.)
    t = _html.unescape(t)
    # Replace non-breaking spaces / thin spaces / other Unicode spaces with regular space
    t = re.sub(r'[      ​﻿]', ' ', t)

    # ── Remove non-English content ─────────────────────────────────────────
    # Remove parentheticals that are entirely non-Latin (Cyrillic, Arabic, CJK, etc.)
    t = re.sub(r'\([^()]*[Ѐ-ӿ؀-ۿ一-鿿぀-ヿ][^()]*\)', '', t)
    # Remove "Language: text" parentheticals, e.g. (Russian: Советский Союз)
    t = re.sub(r'\([A-Z][a-z]+(?:\s[A-Z][a-z]+)?:\s*[^)]{1,80}\)', '', t)
    # Remove bare single-word non-ASCII parentheticals remaining
    t = re.sub(r'\(\s*[^a-zA-Z0-9()\s]+\s*\)', '', t)
    # Clean up any empty parentheses left behind
    t = re.sub(r'\(\s*\)', '', t)

    # ── Wikilink handling ──────────────────────────────────────────────────
    # Strip inner [[link|text]] and [[link]] iteratively so nested wikilinks
    # inside File/Image captions are resolved before the file block is removed.
    # The character class allows single [ or ] (e.g. "text with [s]") but not [[ or ]].
    _lnk = r'(?:[^\[\]]|\[(?!\[)|\](?!\]))'  # one char: anything except [[ or ]]
    for _ in range(4):
        t = re.sub(r'\[\[(?!(?:File|Image|Media):)' + _lnk + r'+\|(' + _lnk + r'+)\]\]', r'\1', t, flags=re.IGNORECASE)
        t = re.sub(r'\[\[(?!(?:File|Image|Media):)(' + _lnk + r'+)\]\]', r'\1', t, flags=re.IGNORECASE)
    # Now remove [[File:...]] / [[Image:...]] — no nested brackets remain inside
    t = re.sub(r'\[\[(?:File|Image|Media):' + _lnk + r'*\]\]', '', t, flags=re.IGNORECASE)
    # Remove external links [http... text] → text
    t = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', t)
    t = re.sub(r'\[https?://\S+\]', '', t)
    # Remove bold/italic markup (''' and '')
    t = re.sub(r"'{2,3}", '', t)
    # Remove indent markers
    t = re.sub(r'^[:;]+', '', t, flags=re.MULTILINE)
    # Remove list markers that are * or # at line start
    t = re.sub(r'^[*#]+\s*', '', t, flags=re.MULTILINE)
    # Normalize section headers: ==Title== → == Title ==
    t = re.sub(r'(={2,4})([^=\n]+)(={2,4})', lambda m: m.group(1) + ' ' + m.group(2).strip() + ' ' + m.group(3), t)
    # Collapse multiple spaces into one
    t = re.sub(r'  +', ' ', t)
    # Collapse excessive blank lines
    t = re.sub(r'\n{4,}', '\n\n\n', t)
    # Strip trailing whitespace per line
    t = '\n'.join(line.rstrip() for line in t.split('\n'))
    return t.strip()


def get_page_content(title: str):
    """
    Fetches full Wikipedia article content as structured plain text.
    Uses raw wikitext (via revisions API) so section headers are preserved.
    Returns {title, content, url, pageid} or None.
    """
    key = f"wiki_page_v5:{title}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    # Fetch raw wikitext — preserves == Section == headers
    params = {
        "action":   "query",
        "titles":   title,
        "prop":     "revisions|info",
        "rvprop":   "content",
        "rvslots":  "main",
        "inprop":   "url",
        "format":   "json",
        "redirects": 1,
    }
    data = _get(WIKI_API, params)
    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    page  = next(iter(pages.values()), None)
    if not page or "missing" in page:
        return None

    revisions = page.get("revisions", [{}])
    wikitext  = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    if not wikitext:
        # Fallback to older API format
        wikitext = revisions[0].get("*", "")

    content = _clean_wikitext(wikitext) if wikitext else ""

    result = {
        "title":   page.get("title", title),
        "content": content,
        "url":     page.get("fullurl",
                            f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"),
        "pageid":  page.get("pageid"),
    }
    cache.set(key, result, ttl=86400)
    return result


def get_today_in_history(month: int, day: int):
    """
    Fetches Wikipedia's 'On This Day' events for a given month and day.
    Returns a list of event dicts with {year, text, pages}.
    """
    url = f"{BASE}/feed/onthisday/events/{month}/{day}"
    data = _get(url, ttl_override=86400)
    if not data:
        return []
    return data.get("events", [])


def _get(url, params=None, timeout=10, ttl_override=3600):
    key = f"wiki:{url}:{str(params)}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        cache.set(key, data, ttl=ttl_override)
        return data
    except Exception:
        return None


def get_events_for_year(year: int, country: str = None):
    """
    Returns notable events from Wikipedia for the given year.
    Optionally filters results relevant to a country.
    Returns list of {year, text} dicts.
    """
    # Use Wikipedia's year article as a source
    title = str(year) if year > 0 else f"{abs(year)} BC"
    page = get_page_content(title)
    if not page:
        return []
    # Extract event lines from the content
    lines = [l.strip() for l in page["content"].split("\n") if l.strip() and len(l.strip()) > 30]
    events = []
    for line in lines[:20]:
        events.append({"year": year, "text": line})
    return events


def get_on_this_day(month: int, day: int):
    """
    Fetches 'On This Day' events from Wikipedia feed API.
    Returns a random notable event dict or None.
    """
    import random
    url = f"{BASE}/feed/onthisday/events/{month}/{day}"
    key = f"onthisday:{month}:{day}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        events = data.get("events", [])
        if events:
            event = random.choice(events[:10])
            result = {
                "year": event.get("year"),
                "text": event.get("text", ""),
                "pages": [p.get("title") for p in event.get("pages", [])][:2],
            }
            cache.set(key, result, ttl=86400)
            return result
    except Exception:
        pass
    return None


def get_also_this_year(year: int, exclude_country: str = ""):
    """
    Returns 2 other notable global events from the same year.
    Used for the 'Also Happening That Year' sidebar.
    Returns list of {year, text, country} dicts.
    """
    key = f"also_year:{year}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        import datetime, random
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        url = f"{BASE}/feed/onthisday/events/{month}/{day}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        events = data.get("events", [])
        results = []
        for ev in events:
            if ev.get("year") and abs(int(ev.get("year", 0)) - year) < 5:
                results.append({"year": ev.get("year"), "text": ev.get("text", "")[:200]})
            if len(results) >= 2:
                break
        # fallback: just pick any 2 events
        if not results:
            for ev in events[:2]:
                results.append({"year": ev.get("year"), "text": ev.get("text", "")[:200]})
        cache.set(key, results, ttl=3600)
        return results
    except Exception:
        return []


def get_famous_people_alive(year: int, country: str = ""):
    """
    Returns 3 famous people who were alive in the given year using Wikipedia search.
    Returns list of {name, birth_year, death_year, age, description} dicts.
    """
    key = f"people_alive:{year}:{country}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    people = []
    search_queries = [
        f"famous historical figure {year}",
        f"notable person history {year} politician",
        f"scientist artist {year}",
    ]
    for q in search_queries:
        results = search_wikipedia(q, limit=3)
        for r in results:
            if r.get("title"):
                people.append({
                    "name": r["title"],
                    "description": r.get("snippet", "")[:100],
                    "age": "~",
                })
        if len(people) >= 3:
            break

    people = people[:3]
    cache.set(key, people, ttl=86400)
    return people


def get_topic_suggestions(year: int, country: str, era: str):
    """
    Returns AI-style topic suggestions for a given year and country.
    Searches Wikipedia for notable events and returns keyword chips.
    Returns list of string keywords.
    """
    key = f"suggestions:{year}:{country}:{era}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    query = f"{country} history {year}"
    results = search_wikipedia(query, limit=8)
    suggestions = [r["title"] for r in results if r.get("title")][:6]

    cache.set(key, suggestions, ttl=3600)
    return suggestions
