"""
Fetcher — Wikimedia Commons pipeline.

Pre-fetches image metadata (title, description, URL, license) for major
historical topics from Wikimedia Commons and stores them as searchable
records in the pipeline DB.

Why?  The live /api/multi-images endpoint already queries Wikimedia Commons
at request-time.  Pre-fetching adds image metadata to the full-text search
index, so topics like "Battle of Waterloo" or "French Revolution" return
image-linked records even when browsed through the archive panel.

API used: Wikimedia Commons API (MediaWiki action=query, no key needed)
  https://commons.wikimedia.org/w/api.php
Rate limit: 0.5 s between requests.
"""

import time
import re
import requests
from db import insert_record

SOURCE_NAME = "Wikimedia Commons"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Historical topics to pre-fetch Wikimedia Commons images for.
# These mirror the Wikipedia pipeline list — the same topics should
# have image metadata available for search.
TOPICS = [
    # Wars
    "World War I", "World War II", "American Civil War",
    "French Revolution", "Napoleonic Wars", "Crimean War",
    "Hundred Years War", "Battle of Waterloo", "Battle of Hastings",
    "Battle of Thermopylae", "Battle of Gettysburg", "Battle of Stalingrad",
    "Vietnam War", "Korean War", "Cold War", "Holocaust",
    "Spanish Civil War",

    # Empires & periods
    "Roman Empire", "Byzantine Empire", "Ottoman Empire", "Mongol Empire",
    "British Empire", "Mughal Empire", "Persian Empire",
    "Ancient Egypt", "Ancient Greece", "Ancient Rome",
    "Renaissance", "Industrial Revolution", "Age of Exploration",
    "Black Death", "Crusades", "Feudalism",

    # Historical figures
    "Alexander the Great", "Julius Caesar", "Napoleon Bonaparte",
    "Genghis Khan", "Cleopatra", "Charlemagne", "Joan of Arc",
    "Saladin", "Suleiman the Magnificent", "Queen Victoria",
    "Abraham Lincoln", "George Washington", "Mahatma Gandhi",
    "Nelson Mandela", "Christopher Columbus",

    # Regions / civilisations
    "Aztec Empire", "Inca Empire", "Maya civilization",
    "Silk Road", "Transatlantic slave trade", "Colonialism",
    "Decolonization", "Apartheid", "Indian independence movement",
]

_PER_TOPIC = 4    # images to fetch per topic
_IMG_EXTS  = (".jpg", ".jpeg", ".png", ".svg", ".tif", ".tiff")


def _commons_search(query: str, limit: int = 4) -> list:
    """
    Search Wikimedia Commons for images related to a historical query.
    Returns a list of dicts: {title, url, description, license, page_url}.
    """
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action":       "query",
        "generator":    "search",
        "gsrsearch":    f"file: {query} historical",
        "gsrnamespace": "6",   # File namespace
        "gsrlimit":     str(limit * 3),  # fetch more to filter
        "prop":         "imageinfo|categories",
        "iiprop":       "url|extmetadata|size",
        "iiurlwidth":   "800",
        "format":       "json",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        data    = resp.json()
        pages   = data.get("query", {}).get("pages", {})
        results = []

        for page in pages.values():
            if page.get("ns") != 6:
                continue
            ii_list = page.get("imageinfo", [])
            if not ii_list:
                continue
            ii  = ii_list[0]
            raw = ii.get("url", "")

            # Only real image files
            if not any(raw.lower().endswith(ext) for ext in _IMG_EXTS):
                continue
            # Skip tiny thumbnails
            if ii.get("width", 0) < 200 or ii.get("height", 0) < 100:
                continue

            meta = ii.get("extmetadata", {}) or {}
            desc = (
                meta.get("ImageDescription", {}).get("value")
                or meta.get("ObjectName", {}).get("value")
                or ""
            )
            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", " ", desc).strip()
            if len(desc) > 400:
                desc = desc[:400].rsplit(" ", 1)[0] + "…"

            license_val = (
                meta.get("LicenseShortName", {}).get("value")
                or meta.get("License", {}).get("value")
                or "Unknown"
            )

            title = page.get("title", "").replace("File:", "").strip()

            results.append({
                "title":    title,
                "url":      raw,
                "description": desc,
                "license":  license_val,
                "page_url": f"https://commons.wikimedia.org/wiki/{page.get('title','').replace(' ','_')}",
            })

            if len(results) >= limit:
                break

        return results

    except Exception:
        return []


def _guess_era(topic: str) -> str:
    """Quick era guess based on topic keywords."""
    t = topic.lower()
    if any(w in t for w in ["ancient", "roman empire", "roman republic",
                              "ancient egypt", "ancient greece",
                              "julius caesar", "cleopatra", "alexander",
                              "thermopylae", "marathon"]):
        return "Classical Antiquity"
    if any(w in t for w in ["medieval", "crusade", "feudal", "black death",
                              "charlemagne", "joan of arc", "hastings",
                              "hundred years", "byzantine"]):
        return "Medieval"
    if any(w in t for w in ["renaissance", "reformation", "age of exploration",
                              "ottoman", "mughal", "colonialism"]):
        return "Early Modern"
    if any(w in t for w in ["napoleonic", "waterloo", "industrial", "crimean",
                              "american civil"]):
        return "19th Century"
    if any(w in t for w in ["world war", "cold war", "holocaust", "apartheid"]):
        return "20th Century"
    return "Modern"


def fetch(conn, source_id) -> int:
    inserted = 0

    for topic in TOPICS:
        try:
            images = _commons_search(topic, limit=_PER_TOPIC)
            if not images:
                print(f"  [WARN] No Wikimedia Commons images for: {topic}")
                time.sleep(0.5)
                continue

            era = _guess_era(topic)

            for img in images:
                title = img["title"]
                if not title:
                    continue

                # Build a short text summary combining topic + description
                desc = img["description"]
                summary = f"Historical image: {title}."
                if desc:
                    summary += f" {desc}"

                ok = insert_record(conn, source_id, {
                    "title":       f"[Image] {title}",
                    "summary":     summary[:500],
                    "full_text":   summary[:500],
                    "era":         era,
                    "external_id": img["url"],
                    "source_url":  img["page_url"],
                    "image_url":   img["url"],
                    "record_type": "image",
                    "tags":        [
                        "Wikimedia Commons", "Historical Image",
                        topic, img["license"],
                    ],
                })
                if ok:
                    inserted += 1
                    print(f"  [Wikimedia] stored image: {title[:60]}")

        except Exception as e:
            print(f"  [ERROR] Wikimedia Commons '{topic}': {e}")

        time.sleep(0.5)

    print(f"  [Wikimedia Commons] {inserted} records inserted")
    return inserted
