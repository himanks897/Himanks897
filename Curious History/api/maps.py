"""
maps.py — Fetches HISTORICAL maps (not modern) from Wikimedia Commons.

Strategy:
  1. Search Wikimedia Commons for map files mentioning the topic/country/period
  2. Filter filenames that suggest historical maps (keywords: map, carte, atlas, etc.)
  3. Exclude modern maps (satellite, current, contemporary, etc.)
  4. Return real URLs via imageinfo API — no manual MD5 construction
"""

import re
import requests
from api import cache
from config import Config

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS     = {"User-Agent": Config.WIKIMEDIA_USER_AGENT}

_MAP_KEYWORDS   = ("map", "carte", "mapa", "karte", "atlas", "chart",
                   "plan", "territory", "empire", "kingdom", "region",
                   "battle", "campaign", "route", "boundary", "border")
_MODERN_SKIP    = ("satellite", "topographic", "topo", "political_map",
                   "location_map", "locator_map", "blank_map", "administrative",
                   "flag", "coat_of_arms", "logo", "icon", "current",
                   "2020", "2021", "2022", "2023", "2024", "2025")
_IMAGE_EXTS     = (".jpg", ".jpeg", ".png", ".svg")

# Stopwords for topic relevance — too generic to meaningfully filter maps
_MAP_STOPWORDS = frozenset([
    "the", "and", "for", "with", "from", "this", "that", "was", "were",
    "in", "of", "a", "an", "at", "by", "on", "to", "its", "or", "but",
    "map", "historical", "history", "old", "ancient", "medieval", "carte",
    "mapa", "atlas", "plan", "territory",
])

# Abbreviation expansion for maps — same patterns as images
_MAP_ABBREVIATIONS = {
    r"\bww1\b":  "world war one",
    r"\bww2\b":  "world war two",
    r"\bwwi\b":  "world war one",
    r"\bwwii\b": "world war two",
    r"\busa\b":  "united states",
    r"\bussr\b": "soviet union",
    r"\buk\b":   "united kingdom",
    r"\bnato\b": "north atlantic",
    r"\bun\b":   "united nations",
    r"\beu\b":   "european union",
}


def _expand_map_abbr(text: str) -> str:
    """Expand common abbreviations so filter words match map filenames."""
    t = text.lower()
    for pattern, replacement in _MAP_ABBREVIATIONS.items():
        t = re.sub(pattern, replacement, t)
    return t


def _topic_words_map(topic: str) -> set:
    """
    Extract meaningful keywords from ANY topic for map relevance checking.
    Expands abbreviations; includes words of 2+ chars; removes generic stopwords.
    Works universally: single words, abbreviations, long phrases.
    """
    expanded = _expand_map_abbr(topic)
    words = set(re.findall(r'\b[a-zA-Z]{2,}\b', expanded.lower()))
    filtered = words - _MAP_STOPWORDS
    return filtered if filtered else words


def _map_is_topic_relevant(title: str, caption: str, topic: str) -> bool:
    """
    Returns True only if the map title or caption contains at least one
    meaningful word from the topic. Prevents off-topic maps from appearing.
    Works universally for any topic searched on the website.
    """
    topic_words = _topic_words_map(topic)
    if not topic_words:
        return True  # Cannot determine topic — allow
    combined = (title + " " + caption).lower().replace("_", " ")
    # Longer words checked first — more specific → fewer false positives
    candidates = sorted(topic_words, key=len, reverse=True)
    return any(w in combined for w in candidates)


def _looks_like_historical_map(title: str) -> bool:
    t = title.lower()
    if not any(t.endswith(e) for e in _IMAGE_EXTS):
        return False
    if any(s in t for s in _MODERN_SKIP):
        return False
    if any(k in t for k in _MAP_KEYWORDS):
        return True
    return False


def _fetch_map_info(file_titles: list) -> list:
    """Fetch real image URLs via Wikimedia Commons imageinfo."""
    if not file_titles:
        return []

    results = []
    for i in range(0, len(file_titles), 20):
        batch = file_titles[i:i+20]
        params = {
            "action":    "query",
            "titles":    "|".join(batch),
            "prop":      "imageinfo",
            "iiprop":    "url|extmetadata",
            "iiurlwidth": 700,
            "format":    "json",
        }
        try:
            r = requests.get(COMMONS_API, params=params,
                             headers=HEADERS, timeout=12)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
        except Exception:
            continue

        for page in pages.values():
            info  = page.get("imageinfo", [{}])[0]
            url   = info.get("thumburl") or info.get("url", "")
            if not url:
                continue
            # Skip SVGs served as PNGs only if they are tiny
            meta  = info.get("extmetadata", {})
            desc  = re.sub(r"<[^>]+>", "",
                           meta.get("ImageDescription", {}).get("value", ""))[:120]
            title = page.get("title", "").replace("File:", "").rsplit(".", 1)[0]
            title = title.replace("_", " ").strip()
            date_info = (meta.get("DateTimeOriginal", {}).get("value", "")
                         or meta.get("DateTime", {}).get("value", ""))
            results.append({
                "url":    url,
                "title":  title,
                "alt":    title,
                "caption": desc or title,
                "source": "Wikimedia Commons",
                "date":   date_info[:10] if date_info else "historical",
                "license": meta.get("LicenseShortName", {}).get("value", ""),
            })

    return results


def _commons_map_search(query: str, limit: int) -> list:
    """Search Wikimedia Commons files, return File: titles that look like maps."""
    params = {
        "action":      "query",
        "list":        "search",
        "srsearch":    query,
        "srnamespace": 6,
        "srlimit":     15,
        "format":      "json",
        "srprop":      "title",
    }
    try:
        r = requests.get(COMMONS_API, params=params,
                         headers=HEADERS, timeout=10)
        r.raise_for_status()
        items = r.json().get("query", {}).get("search", [])
        titles = [it["title"] for it in items
                  if _looks_like_historical_map(it.get("title", ""))]
        return titles[:limit]
    except Exception:
        return []


def get_all_maps(topic: str, country: str, year: int,
                 limit: int = 5) -> list:
    """
    Returns up to `limit` historical maps for the topic/country/year.
    Falls back through multiple search strategies.
    """
    cache_key = f"maps_v3:{topic}:{country}:{year}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Search queries — topic-first so results stay relevant
    search_strategies = [
        f"historical map {topic}",
        f"battle map {topic}",
        f"map {topic} history",
        f"map {topic} {country}",
    ]

    file_titles = []
    seen = set()
    for query in search_strategies:
        for t in _commons_map_search(query, limit=8):
            if t not in seen:
                seen.add(t)
                file_titles.append(t)
        if len(file_titles) >= limit * 3:
            break

    # Fallback: Wikipedia article images filtered for maps
    if len(file_titles) < limit:
        try:
            from api import wikipedia as wiki_api
            results = wiki_api.search_wikipedia(f"map {topic} history", limit=2)
            for res in results:
                params = {
                    "action":   "query",
                    "titles":   res["title"],
                    "prop":     "images",
                    "imlimit":  20,
                    "format":   "json",
                    "redirects": 1,
                }
                r = requests.get("https://en.wikipedia.org/w/api.php",
                                 params=params, headers=HEADERS, timeout=10)
                r.raise_for_status()
                pages = r.json().get("query", {}).get("pages", {})
                page  = next(iter(pages.values()), {})
                for img in page.get("images", []):
                    t = img.get("title", "")
                    if t not in seen and _looks_like_historical_map(t):
                        seen.add(t)
                        file_titles.append(t)
        except Exception:
            pass

    if not file_titles:
        result = []
        cache.set(cache_key, result, ttl=86400)
        return result

    all_maps = _fetch_map_info(file_titles[:limit * 3])

    # ── Strict topic relevance filter ─────────────────────────────────────
    filtered = [
        m for m in all_maps
        if _map_is_topic_relevant(m.get("title", ""), m.get("caption", ""), topic)
    ]

    # Fall back to unfiltered if nothing passes (very short / single-word topics)
    maps = (filtered if filtered else all_maps)[:limit]
    cache.set(cache_key, maps, ttl=86400)
    return maps
