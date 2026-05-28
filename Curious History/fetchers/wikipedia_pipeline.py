"""
Fetcher — Wikipedia pipeline.

Pre-fetches English Wikipedia article summaries for ~200 key historical topics
and stores them in the pipeline DB as searchable full-text records.

Why pre-fetch?  The live /api/multi-facts and results page already call
Wikipedia in real-time.  Pre-fetching adds these summaries to the ranked
full-text search index so that topics like "Industrial Revolution", "Cold War",
"Apartheid", etc. always surface at least one high-quality Wikipedia result
even when no IA or Cabinet Papers record covers them.

API used: Wikipedia REST summary endpoint (no key needed)
  https://en.wikipedia.org/api/rest_v1/page/summary/{title}
Rate limit: 0.5 s between requests (well under the 200 req/s cap).
"""

import time
import re
import requests
from db import insert_record

SOURCE_NAME = "Wikipedia"

HEADERS = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# ~200 key historical topics — broad coverage across all eras and regions.
HISTORICAL_TOPICS = [
    # ── World Wars ─────────────────────────────────────────────────────────────
    "World War I", "World War II", "Western Front (World War I)",
    "Eastern Front (World War II)", "Battle of Britain", "Battle of Stalingrad",
    "D-Day", "Holocaust", "Atomic bombings of Hiroshima and Nagasaki",

    # ── Other major wars ───────────────────────────────────────────────────────
    "American Civil War", "Vietnam War", "Korean War", "Cold War",
    "Napoleonic Wars", "Hundred Years War", "Thirty Years War",
    "Crimean War", "Boer War", "Russo-Japanese War", "Spanish Civil War",
    "Mexican-American War", "War of 1812", "Seven Years War",
    "Franco-Prussian War", "Indian Rebellion of 1857", "Gulf War",
    "Iraq War", "Afghan War", "Peloponnesian War", "Punic Wars",
    "First Crusade", "Third Crusade", "Reconquista",

    # ── Empires ────────────────────────────────────────────────────────────────
    "Roman Empire", "Roman Republic", "British Empire", "Ottoman Empire",
    "Mongol Empire", "Persian Empire", "Achaemenid Empire", "Byzantine Empire",
    "Mughal Empire", "Qing dynasty", "Han dynasty", "Tang dynasty",
    "Ming dynasty", "Holy Roman Empire", "Habsburg Monarchy",
    "Spanish Empire", "Portuguese Empire", "French colonial empire",
    "Russian Empire", "Macedonian Empire",

    # ── Revolutions ────────────────────────────────────────────────────────────
    "French Revolution", "American Revolution", "Russian Revolution",
    "Industrial Revolution", "Haitian Revolution", "Mexican Revolution",
    "Cuban Revolution", "Iranian Revolution", "Glorious Revolution",
    "English Civil War", "Chinese Communist Revolution",

    # ── Ancient civilisations ──────────────────────────────────────────────────
    "Ancient Egypt", "Ancient Greece", "Ancient Rome",
    "Mesopotamia", "Sumer", "Babylon", "Assyrian Empire",
    "Indus Valley Civilisation", "Aztec Empire", "Inca Empire",
    "Maya civilization", "Phoenicia", "Carthage",
    "Ancient China", "Zhou dynasty", "Shang dynasty",

    # ── Key periods / movements ────────────────────────────────────────────────
    "Black Death", "Renaissance", "Age of Enlightenment",
    "Protestant Reformation", "Age of Exploration", "Colonialism",
    "Transatlantic slave trade", "Apartheid", "Decolonization",
    "Pan-Africanism", "Indian independence movement",
    "Women's suffrage", "Civil rights movement",
    "Abolition of slavery", "Nationalism", "Imperialism",
    "Feudalism", "Silk Road", "Space Race", "Nuclear arms race",
    "Fall of the Berlin Wall", "Dissolution of the Soviet Union",
    "Marshall Plan", "League of Nations",

    # ── Famous historical figures ──────────────────────────────────────────────
    "Alexander the Great", "Julius Caesar", "Augustus",
    "Napoleon Bonaparte", "Genghis Khan", "Attila the Hun",
    "Cleopatra", "Queen Elizabeth I", "Queen Victoria",
    "Peter the Great", "Catherine the Great", "Charlemagne",
    "Saladin", "Suleiman the Magnificent", "Timur",
    "Christopher Columbus", "Vasco da Gama", "Ferdinand Magellan",
    "Martin Luther", "Joan of Arc",
    "Adolf Hitler", "Joseph Stalin", "Mao Zedong",
    "Winston Churchill", "Franklin D. Roosevelt", "Vladimir Lenin",
    "Karl Marx", "Abraham Lincoln", "George Washington",
    "Mahatma Gandhi", "Nelson Mandela", "Simon Bolivar",
    "Tokugawa Ieyasu", "Ashoka",

    # ── Major battles ──────────────────────────────────────────────────────────
    "Battle of Thermopylae", "Battle of Marathon", "Battle of Waterloo",
    "Battle of Gettysburg", "Battle of Hastings", "Battle of Agincourt",
    "Siege of Constantinople", "Battle of the Somme", "Battle of Midway",
    "Battle of Tours", "Battle of Trafalgar",

    # ── Treaties / political milestones ────────────────────────────────────────
    "Treaty of Versailles", "Peace of Westphalia", "Congress of Vienna",
    "Magna Carta", "Declaration of Independence",
    "Partition of India", "Scramble for Africa",

    # ── Religious / cultural history ───────────────────────────────────────────
    "History of Islam", "History of Christianity", "History of Buddhism",
    "History of Judaism", "Byzantine Iconoclasm",
    "Crusades", "Spanish Inquisition",

    # ── Economic / social history ──────────────────────────────────────────────
    "Mercantilism", "History of capitalism", "Great Depression",
    "Irish Famine", "Bengal famine of 1943", "Holodomor",

    # ── Specific regions ───────────────────────────────────────────────────────
    "History of India", "History of China", "History of Africa",
    "History of Japan", "History of the United States",
    "History of France", "History of England", "History of Russia",
    "History of the Ottoman Empire", "History of Egypt",
    "History of Ancient Greece", "History of Ancient Rome",
]


def _wiki_summary(title: str) -> dict:
    """Fetch Wikipedia REST API summary. Returns {} on failure."""
    encoded = requests.utils.quote(title.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _guess_era(summary: str, title: str) -> str:
    """Infer historical era from summary text."""
    combined = (title + " " + summary).lower()

    if any(w in combined for w in [
        "bc", "bce", "ancient", "classical antiquity",
        "roman republic", "ancient rome", "ancient egypt",
        "ancient greece", "mesopotamia", "sumer", "assyrian",
        "indus valley", "bronze age", "iron age",
        "herodotus", "thucydides", "alexander the great",
        "julius caesar", "cleopatra", "carthage", "phoenicia",
    ]) and "medieval" not in combined[:200] and "modern" not in combined[:100]:
        return "Classical Antiquity"

    if any(w in combined for w in [
        "middle ages", "medieval", "crusade", "feudal",
        "byzantine", "viking", "norman", "charlemagne",
        "carolingian", "1000 ad", "1100", "1200", "1300",
        "black death", "mongol empire", "genghis khan",
        "joan of arc", "100 years war", "hundred years",
    ]):
        return "Medieval"

    if any(w in combined for w in [
        "renaissance", "reformation", "age of exploration",
        "ottoman", "mughal", "conquistador", "colonialism",
        "16th century", "17th century", "1500s", "1600s", "1700s",
        "thirty years war", "english civil war", "glorious revolution",
    ]):
        return "Early Modern"

    if any(w in combined for w in [
        "industrial revolution", "napoleonic", "19th century",
        "1800s", "victorian", "manifest destiny", "civil war",
        "imperialism", "nationalism",
    ]):
        return "19th Century"

    if any(w in combined for w in [
        "world war", "20th century", "cold war", "soviet",
        "nuclear", "1914", "1939", "1945", "fascism",
        "communism", "decolonization", "apartheid",
    ]):
        return "20th Century"

    return "Modern"


def _region_from_text(summary: str, title: str) -> str:
    """Guess geographic region from text (best-effort)."""
    combined = (title + " " + summary).lower()
    if any(w in combined for w in ["europe", "france", "england", "britain",
                                    "germany", "italy", "spain", "greece", "rome",
                                    "russia", "ottoman", "byzantine"]):
        return "Europe"
    if any(w in combined for w in ["india", "mughal", "british india",
                                    "hindustan", "bengal", "delhi"]):
        return "South Asia"
    if any(w in combined for w in ["china", "japan", "korea", "han dynasty",
                                    "tang", "ming", "qing"]):
        return "East Asia"
    if any(w in combined for w in ["egypt", "africa", "sahara", "ethiopia",
                                    "carthage", "north africa"]):
        return "Africa"
    if any(w in combined for w in ["america", "united states", "mexico",
                                    "brazil", "inca", "aztec", "maya"]):
        return "Americas"
    if any(w in combined for w in ["mesopotamia", "persia", "iran", "iraq",
                                    "syria", "middle east", "arabia", "islam"]):
        return "Middle East"
    return ""


def fetch(conn, source_id) -> int:
    inserted = 0

    for title in HISTORICAL_TOPICS:
        try:
            data = _wiki_summary(title)
            if not data or not data.get("title"):
                print(f"  [WARN] No Wikipedia summary for: {title}")
                time.sleep(0.5)
                continue

            extract = (data.get("extract") or "").strip()
            if len(extract) < 60:
                time.sleep(0.5)
                continue

            # Truncate at sentence boundary around 1500 chars
            short = extract[:1500]
            last_dot = short.rfind(".")
            if last_dot > 500:
                short = short[:last_dot + 1]

            era    = _guess_era(extract, title)
            region = _region_from_text(extract, title)

            page_url = (data.get("content_urls") or {}).get("desktop", {}).get("page", "")
            thumb    = data.get("thumbnail") or {}
            image_url = thumb.get("source", "") if thumb else ""
            page_id  = data.get("pageid")

            ok = insert_record(conn, source_id, {
                "title":       data.get("title", title),
                "summary":     short,
                "full_text":   short,
                "era":         era,
                "region":      region,
                "external_id": str(page_id) if page_id else title,
                "source_url":  page_url,
                "record_type": "article",
                "image_url":   image_url,
                "tags":        ["Wikipedia", "Historical Summary", era],
            })
            if ok:
                inserted += 1
                print(f"  [Wikipedia] stored: {data.get('title', title)}")

        except Exception as e:
            print(f"  [ERROR] Wikipedia '{title}': {e}")

        time.sleep(0.5)

    print(f"  [Wikipedia] {inserted} records inserted")
    return inserted
