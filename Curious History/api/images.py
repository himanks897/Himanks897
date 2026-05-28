"""
images.py — Fetches TOPIC-RELEVANT historical images from Wikipedia and Wikimedia Commons.

Strategy:
  1. Direct Wikipedia article for the exact topic (most relevant)
  2. Topic-only Wikimedia Commons search (NOT year/country to avoid false positives)
  3. Strict two-layer relevance filter on every image:
       a) Reject if image contains off-topic terms (sports, etc.) and topic is not about them
       b) Require at least one meaningful topic keyword in the filename or description

All URLs come from the imageinfo API — no manual MD5 construction.
Works universally for ANY topic — short words, abbreviations, single words, all handled.
"""

import re
import requests
from api import cache
from config import Config

WIKI_API    = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS     = {"User-Agent": Config.WIKIMEDIA_USER_AGENT}

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

# Generic system/icon filenames to always skip
_SKIP_NAMES = (
    "commons-logo", "wikisource-logo", "wikibooks-logo", "wikiquote-logo",
    "portal-", "question_book", "ambox", "edit-clear", "icon", "flag_of",
    "coat_of_arms", "blank_map", "map_of_the_world", "red_pog", "location",
    "wiki_letter", "translation", "nuvola", "crystal", "gnome", "tango",
    "emblem-", "logo", "symbol_", "pictogram", "arrow_",
)

# Terms that indicate a clearly OFF-TOPIC image for non-sport/non-game topics
_SPORT_TERMS = frozenset([
    "football", "soccer", "cricket", "tennis", "golf", "swimming",
    "athletics", "olympic", "olympics", "championship", "tournament",
    "league", "fifa", "stadium", "athlete", "player", "rugby",
    "baseball", "basketball", "volleyball", "cycling", "rowing",
    "boxing", "wrestling", "polo", "netball", "lacrosse", "squash",
    "handball", "badminton", "archery", "fencing", "sailing",
    "racing", "marathon", "triathlon", "weightlifting", "judo", "karate",
])

# Sport-related topic keywords (if the topic includes these, sport images are OK)
_SPORT_TOPIC_SIGNALS = frozenset([
    "sport", "football", "soccer", "olympic", "cup", "game",
    "championship", "world cup", "athlete", "tournament", "match",
    "league", "cricket", "tennis", "golf",
])

# Common abbreviation expansions — applied before word extraction
_ABBREVIATIONS = {
    r"\bww1\b": "world war one",
    r"\bww2\b": "world war two",
    r"\bwwi\b": "world war one",
    r"\bwwii\b": "world war two",
    r"\bww\s*1\b": "world war one",
    r"\bww\s*2\b": "world war two",
    r"\busa\b": "united states america",
    r"\bussr\b": "soviet union russia",
    r"\buk\b": "united kingdom britain",
    r"\buae\b": "united arab emirates",
    r"\bnato\b": "north atlantic treaty",
    r"\bun\b": "united nations",
    r"\beu\b": "european union",
}

_IMG_STOPWORDS = frozenset([
    "the", "and", "for", "with", "from", "this", "that", "was", "were",
    "in", "of", "a", "an", "at", "by", "on", "to", "its", "or", "but",
    "not", "are", "is", "it", "as", "be", "do", "had", "has", "have",
])


def _expand_abbreviations(text: str) -> str:
    """Expand common abbreviations so filter words match article content."""
    t = text.lower()
    for pattern, replacement in _ABBREVIATIONS.items():
        t = re.sub(pattern, replacement, t)
    return t


def _topic_words_img(topic: str) -> set:
    """
    Meaningful words from the topic for relevance filtering.
    Expands abbreviations and includes ALL words ≥ 2 chars after stopword removal.
    Works for any topic: long phrases, single words, abbreviations.
    """
    expanded = _expand_abbreviations(topic)
    # Extract words of 2+ chars (covers short words like "war", "usa")
    words = set(re.findall(r"\b[a-zA-Z]{2,}\b", expanded.lower()))
    filtered = words - _IMG_STOPWORDS
    return filtered if filtered else words


def _is_valid_image(title: str) -> bool:
    """Check the file has a valid image extension and isn't a system icon."""
    t = title.lower()
    if not any(t.endswith(ext) for ext in _IMAGE_EXTS):
        return False
    if any(skip in t for skip in _SKIP_NAMES):
        return False
    return True


def _image_passes_strict_filter(file_title: str, img_title: str,
                                 img_desc: str, topic: str) -> bool:
    """
    Strict two-layer filter applied to every candidate image:

    Layer 1 — Reject off-topic images:
      If the topic is NOT about sports/games but the image filename/description
      contains sport terms, reject it immediately.

    Layer 2 — Require topic keyword match:
      At least one meaningful word from the topic must appear in the image
      filename, title, or description. This stops random unrelated images
      from slipping through even if they pass layer 1.

    Returns True only if the image should be included.
    """
    topic_lower  = topic.lower()
    combined     = (file_title + " " + img_title + " " + img_desc).lower()

    # Layer 1: reject sport images unless topic is about sports
    topic_is_sport = any(s in topic_lower for s in _SPORT_TOPIC_SIGNALS)
    if not topic_is_sport:
        if any(s in combined for s in _SPORT_TERMS):
            return False

    # Layer 2: require at least one meaningful topic keyword
    # Use all topic words (including short ones like 'war', 'usa')
    # Prefer longer words first (more specific) to reduce false positives
    tw = _topic_words_img(topic)
    if not tw:
        return True  # Cannot determine topic — allow
    # Sort longest first so more specific words are checked first
    candidates = sorted(tw, key=len, reverse=True)
    return any(w in combined for w in candidates)


def _batch_imageinfo(file_titles: list, width: int = 600,
                     api: str = WIKI_API) -> list:
    """
    Given a list of 'File:…' titles, return image dicts with real thumb URLs.
    Batches up to 20 at a time.
    """
    if not file_titles:
        return []

    results = []
    for i in range(0, len(file_titles), 20):
        batch  = file_titles[i : i + 20]
        params = {
            "action":    "query",
            "titles":    "|".join(batch),
            "prop":      "imageinfo",
            "iiprop":    "url|extmetadata|size",
            "iiurlwidth": width,
            "format":    "json",
        }
        try:
            r = requests.get(api, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
        except Exception:
            continue

        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            url  = info.get("thumburl") or info.get("url", "")
            if not url or not any(url.lower().split("?")[0].endswith(e)
                                   for e in _IMAGE_EXTS):
                continue
            meta  = info.get("extmetadata", {})
            desc  = re.sub(r"<[^>]+>", "",
                           meta.get("ImageDescription", {}).get("value", ""))[:200]
            title = (page.get("title", "")
                        .replace("File:", "").rsplit(".", 1)[0]
                        .replace("_", " ").strip())
            lic   = meta.get("LicenseShortName", {}).get("value", "")
            results.append({
                "url":     url,
                "title":   title,
                "caption": desc.strip() or title,
                "alt":     desc.strip() or title,
                "source":  "Wikimedia Commons",
                "license": lic,
            })

    return results


def get_wikipedia_article_images(wiki_title: str, topic: str,
                                  limit: int = 8) -> list:
    """
    Returns images used inside the Wikipedia article `wiki_title`,
    filtered strictly to be relevant to `topic`.
    """
    cache_key = f"wp_art_imgs_v3:{wiki_title}:{topic}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params = {
        "action":   "query",
        "titles":   wiki_title,
        "prop":     "images",
        "imlimit":  50,
        "format":   "json",
        "redirects": 1,
    }
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        page  = next(iter(pages.values()), {})
        file_titles = [
            img["title"]
            for img in page.get("images", [])
            if _is_valid_image(img.get("title", ""))
        ]
    except Exception:
        return []

    # Fetch imageinfo for candidates
    candidates = _batch_imageinfo(file_titles[: limit * 3], width=600)

    # Apply strict relevance filter
    results = [
        img for img in candidates
        if _image_passes_strict_filter(
            img.get("title", ""), img.get("title", ""),
            img.get("caption", ""), topic
        )
    ][:limit]

    cache.set(cache_key, results, ttl=86400)
    return results


def get_wikimedia_commons_images(topic: str, year: int,
                                  country: str, limit: int = 8) -> list:
    """
    Searches Wikimedia Commons for images using ONLY the topic keywords
    (never year or country to prevent off-topic results like sports events
    from the same year). Applies strict relevance filter on every result.
    """
    cache_key = f"commons_strict_v3:{topic}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Use only topic in queries — adding year/country causes false positives
    queries = [topic, f"{topic} historical"]

    file_titles = []
    seen = set()
    for q in queries:
        params = {
            "action":      "query",
            "list":        "search",
            "srsearch":    q,
            "srnamespace": 6,  # File namespace only
            "srlimit":     20,
            "format":      "json",
            "srprop":      "title",
        }
        try:
            r = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            for item in r.json().get("query", {}).get("search", []):
                t = item.get("title", "")
                if t and t not in seen and _is_valid_image(t):
                    seen.add(t)
                    file_titles.append(t)
        except Exception:
            pass
        if len(file_titles) >= limit * 3:
            break

    if not file_titles:
        return []

    # Fetch URLs via Commons imageinfo
    candidates = []
    for i in range(0, min(len(file_titles), limit * 3), 20):
        batch  = file_titles[i : i + 20]
        params = {
            "action":    "query",
            "titles":    "|".join(batch),
            "prop":      "imageinfo",
            "iiprop":    "url|extmetadata",
            "iiurlwidth": 600,
            "format":    "json",
        }
        try:
            r = requests.get(COMMONS_API, params=params,
                             headers=HEADERS, timeout=10)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
        except Exception:
            continue

        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            url  = info.get("thumburl") or info.get("url", "")
            if not url:
                continue
            meta  = info.get("extmetadata", {})
            desc  = re.sub(r"<[^>]+>", "",
                           meta.get("ImageDescription", {}).get("value", ""))[:200]
            title = (page.get("title", "")
                        .replace("File:", "").rsplit(".", 1)[0]
                        .replace("_", " ").strip())
            lic   = meta.get("LicenseShortName", {}).get("value", "")
            candidates.append({
                "url":     url,
                "title":   title,
                "caption": desc.strip() or title,
                "alt":     desc.strip() or f"{topic} — historical image",
                "source":  "Wikimedia Commons",
                "license": lic,
            })
        if len(candidates) >= limit * 2:
            break

    # Apply strict filter
    results = [
        img for img in candidates
        if _image_passes_strict_filter(
            img.get("title", ""), img.get("title", ""),
            img.get("caption", ""), topic
        )
    ][:limit]

    cache.set(cache_key, results, ttl=86400)
    return results


def _article_relevant(page_title: str, topic: str) -> bool:
    """Check if a Wikipedia page title is relevant to the topic."""
    tw = _topic_words_img(topic)
    tl = page_title.lower()
    return any(w in tl for w in tw)


def get_all_images(topic: str, year: int, country: str,
                   limit: int = 8) -> list:
    """
    Aggregates strictly topic-relevant images from:
      1. The exact Wikipedia article for this topic
      2. Topic-only Wikimedia Commons search
    Returns up to `limit` deduplicated, filtered images with proper labels.
    """
    from api import wikipedia as wiki_api

    article_images = []

    # 1. Direct Wikipedia page for the exact topic
    direct = wiki_api.get_page_content(topic)
    if direct and _article_relevant(direct.get("title", ""), topic):
        imgs = get_wikipedia_article_images(direct["title"], topic, limit=8)
        article_images.extend(imgs)

    # 2. Search result fallback (only topic-relevant articles)
    if len(article_images) < 4:
        search_results = wiki_api.search_wikipedia(f"{topic} {year}", limit=3)
        for result in search_results[:2]:
            if result["title"] == (direct or {}).get("title"):
                continue
            if not _article_relevant(result["title"], topic):
                continue
            imgs = get_wikipedia_article_images(result["title"], topic, limit=5)
            article_images.extend(imgs)
            if len(article_images) >= 6:
                break

    # 3. Commons search — topic only (strict filter already applied inside)
    commons_images = get_wikimedia_commons_images(topic, year, country, limit=6)

    # Merge and deduplicate by URL
    seen_urls = set()
    combined  = []
    for img in article_images + commons_images:
        u = img.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            combined.append(img)
        if len(combined) >= limit:
            break

    return combined
