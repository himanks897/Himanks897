"""
key_facts.py — Wikipedia-based extraction of key people, places, and causes.
Uses Wikipedia pageimages + extracts APIs. No Gemini dependency.
"""

import re
import requests
from collections import Counter
from api import cache
from config import Config

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": Config.WIKIMEDIA_USER_AGENT}

_SKIP_PHRASES = frozenset({
    "united states", "great britain", "soviet union", "world war",
    "cold war", "second world", "first world", "north korea", "south korea",
    "new york", "west germany", "east germany", "new delhi", "north vietnam",
    "south vietnam", "north america", "south america", "central asia",
    "middle east", "far east", "latin america", "world history",
    "also happening", "historical image", "bay of", "sea of",
    "indian ocean", "pacific ocean", "atlantic ocean",
    "united kingdom", "european union", "ottoman empire", "united nations",
    "also alive",
})

_PERSON_SIGNALS = [
    " was ", " is ", "born", "politician", "leader", "general",
    "president", "prime minister", "king", "queen", "emperor",
    "minister", "commander", "revolutionary", "diplomat", "secretary",
    "senator", "governor", "admiral", "colonel", "chancellor",
    "statesman", "activist", "philosopher", "scientist", "novelist",
    "poet", "artist", "military", "politician",
]

_PLACE_SIGNALS = [
    "city", "country", "island", "bay", "sea", "river", "located",
    "region", "province", "territory", "capital", "town", "village",
    "port", "coast", "valley", "mountain", "peninsula", "republic",
    "nation", "state", "district", "county", "municipality",
    "ocean", "lake", "border", "frontier", "continent",
]


def _wiki_get(params):
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _get_entity_info(title: str):
    """Fetch thumbnail + 3-sentence extract for any Wikipedia entity."""
    params = {
        "action":     "query",
        "titles":     title,
        "prop":       "pageimages|extracts",
        "piprop":     "thumbnail",
        "pithumbsize": 350,
        "exintro":    True,
        "exsentences": 3,
        "explaintext": True,
        "redirects":  1,
        "format":     "json",
    }
    data = _wiki_get(params)
    if not data:
        return None
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if "missing" in page or page.get("pageid", -1) < 0:
        return None
    extract = page.get("extract", "").strip()
    if not extract or len(extract) < 30:
        return None
    thumb = page.get("thumbnail", {})
    return {
        "name":      page.get("title", title),
        "image_url": thumb.get("source", ""),
        "description": extract,
        "wiki_url":  "https://en.wikipedia.org/wiki/{}".format(
            page.get("title", title).replace(" ", "_")
        ),
    }


def _extract_proper_names(raw_content: str) -> list:
    """Extract 2-4 word proper-noun sequences from cleaned article text."""
    pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b')
    counts = Counter(pattern.findall(raw_content))
    results = []
    seen = set()
    for name, count in counts.most_common(40):
        low = name.lower()
        if (count >= 2
                and low not in _SKIP_PHRASES
                and low not in seen
                and len(name.split()) >= 2):
            seen.add(low)
            results.append(name)
        if len(results) >= 20:
            break
    return results


# ─── Key People ────────────────────────────────────────────────────────────────

def get_key_people_data(topic: str, year: int, country: str, raw_content: str) -> list:
    """
    Returns list of {name, image_url, description, wiki_url} for key people.
    Used both for HTML cards and gallery portraits.
    """
    cache_key = f"kp_data:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    candidates = _extract_proper_names(raw_content)

    # Add results from Wikipedia biography search
    search_data = _wiki_get({
        "action":   "query",
        "list":     "search",
        "srsearch": f"{topic} {country} biography leader",
        "srlimit":  8,
        "format":   "json",
        "srprop":   "title",
    })
    if search_data:
        skip_words = {"war", "battle", "treaty", "revolution", "crisis",
                      "conflict", "history", "empire", "dynasty", "campaign"}
        for r in search_data.get("query", {}).get("search", []):
            t = r.get("title", "")
            if t and not any(w in t.lower() for w in skip_words):
                if t not in candidates:
                    candidates.append(t)

    people = []
    for name in candidates[:22]:
        if len(people) >= 6:
            break
        info = _get_entity_info(name)
        if not info:
            continue
        desc_low = info["description"][:300].lower()
        is_person = any(sig in desc_low for sig in _PERSON_SIGNALS)
        if not is_person and len(people) >= 3:
            continue
        people.append(info)

    cache.set(cache_key, people, ttl=86400)
    return people


def get_key_people(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Returns HTML person entries: bold name + clickable portrait (zoom-capable) + full contributions.
    Format: name on one line, small portrait (click to zoom), contributions on next line.
    """
    import html as html_mod
    data = get_key_people_data(topic, year, country, raw_content)
    if not data:
        return (f'<p><em>No key people found in Wikipedia for <strong>{topic}</strong>. '
                f'Try searching individual names related to this event.</em></p>')

    entries = []
    for p in data:
        sentences = re.split(r'(?<=[.!?])\s+', p["description"])
        contributions = " ".join(sentences)  # full description as contributions

        portrait_html = ""
        if p.get("image_url"):
            src   = html_mod.escape(p["image_url"], quote=True)
            name  = html_mod.escape(p["name"],      quote=True)
            cap   = html_mod.escape(contributions[:200], quote=True)
            portrait_html = (
                f'<img src="{src}" alt="{name}" '
                f'class="person-mini-portrait" loading="lazy" '
                f'data-lb-src="{src}" data-lb-title="{name}" data-lb-caption="{cap}" '
                f'onerror="this.style.display=\'none\'" title="Click to zoom">'
            )

        entries.append(
            f'<div class="person-entry">\n'
            f'  <div class="person-entry-header">\n'
            f'    <strong class="person-name">{p["name"]}</strong>\n'
            f'    {portrait_html}\n'
            f'  </div>\n'
            f'  <p class="person-contributions">{contributions}</p>\n'
            f'  <a href="{p["wiki_url"]}" target="_blank" rel="noopener noreferrer" '
            f'class="wiki-link">Read more on Wikipedia →</a>\n'
            f'</div>'
        )
    return "\n".join(entries)


# ─── Key Places ────────────────────────────────────────────────────────────────

def get_key_places_data(topic: str, year: int, country: str, raw_content: str) -> list:
    """
    Returns list of {name, image_url, description, wiki_url} for key places.
    """
    cache_key = f"kpl_data:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    candidates = []
    seen = set()

    if country:
        candidates.append(country)
        seen.add(country.lower())

    for name in _extract_proper_names(raw_content):
        if name.lower() not in seen:
            candidates.append(name)
            seen.add(name.lower())

    # Wikipedia geography search
    search_data = _wiki_get({
        "action":   "query",
        "list":     "search",
        "srsearch": f"{topic} {country} geography location",
        "srlimit":  6,
        "format":   "json",
        "srprop":   "title",
    })
    if search_data:
        geo_words = {"city", "country", "island", "bay", "sea", "port",
                     "peninsula", "province", "region", "territory"}
        for r in search_data.get("query", {}).get("search", []):
            t = r.get("title", "")
            if t and any(w in t.lower() for w in geo_words) and t not in candidates:
                candidates.append(t)

    places = []
    for name in candidates[:22]:
        if len(places) >= 6:
            break
        info = _get_entity_info(name)
        if not info:
            continue
        desc_low = info["description"][:300].lower()
        is_place = any(sig in desc_low for sig in _PLACE_SIGNALS)
        if not is_place and len(places) >= 3:
            continue
        places.append(info)

    cache.set(cache_key, places, ttl=86400)
    return places


def get_key_places(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Returns HTML place entries: bold place name on one line, importance/description on next line.
    No images — clean text-only format as requested.
    """
    data = get_key_places_data(topic, year, country, raw_content)
    if not data:
        return f'<p><em>No key places found in Wikipedia for <strong>{topic}</strong>.</em></p>'

    entries = []
    for p in data:
        sentences = re.split(r'(?<=[.!?])\s+', p["description"])
        importance = " ".join(sentences[:3])
        entries.append(
            f'<div class="place-entry">\n'
            f'  <h4><strong>{p["name"]}</strong></h4>\n'
            f'  <p>{importance}</p>\n'
            f'</div>'
        )
    return "\n".join(entries)


# ─── Key Causes ────────────────────────────────────────────────────────────────

def get_key_causes(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Extracts key causes from Wikipedia article sections (Causes/Background/Origins).
    Parses == Section == markers preserved by _clean_wikitext. No Gemini.
    """
    cache_key = f"kc2_wiki:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    section_re = re.compile(
        r'==\s*(Causes?|Background|Origins?|Context|Prelude|Lead-?up|Reasons?|Precursors?)\s*==\s*\n'
        r'(.*?)(?=\n==\s*\w|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    sections = section_re.findall(raw_content)

    if not sections:
        sections = [("Historical Context", raw_content[:2500])]

    entries = []
    card_num = 1

    for _, section_body in sections[:3]:
        body = section_body.strip()
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', body)
                      if p.strip() and len(p.strip()) > 60]

        for para in paragraphs[:4]:
            clean = re.sub(r'<[^>]+>', '', para).strip()
            clean = re.sub(r'={2,}[^=\n]*={2,}', '', clean).strip()
            if len(clean) < 50:
                continue

            sentences = re.split(r'(?<=[.!?])\s+', clean)
            first = sentences[0] if sentences else clean
            rest = " ".join(sentences[1:4]) if len(sentences) > 1 else ""

            if len(first) > 90:
                title = first[:87] + "..."
                body_text = clean[:500]
            else:
                title = first.rstrip('.,')
                body_text = (rest or clean)[:500]

            entries.append(
                f'<div class="cause-entry">\n'
                f'  <h4><strong>{title}</strong></h4>\n'
                f'  <p>{body_text}</p>\n'
                f'</div>'
            )
            card_num += 1
            if card_num > 7:
                break
        if card_num > 7:
            break

    if not entries:
        paras = [p.strip() for p in raw_content.split('\n\n')
                 if p.strip() and len(p.strip()) > 80][:4]
        for para in paras:
            clean = re.sub(r'<[^>]+>', '', para)[:400]
            entries.append(
                f'<div class="cause-entry">\n'
                f'  <h4><strong>Historical Background</strong></h4>\n'
                f'  <p>{clean}</p>\n'
                f'</div>'
            )

    result = (
        "\n".join(entries) if entries
        else f'<p><em>Key causes for <strong>{topic}</strong> are derived from historical sources.</em></p>'
    )
    cache.set(cache_key, result, ttl=86400)
    return result
