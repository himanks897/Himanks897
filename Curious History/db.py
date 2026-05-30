"""
db.py — JSON-based database for the Curious History data pipeline.

Storage:  curious_history.json  (human-readable, open in VS Code / any editor)
Populated by: python3 main.py --reset
Queried by:   app.py routes

JSON structure:
{
  "meta":    { "version", "last_updated", "total_records" },
  "sources": [ { "id", "name", "base_url", "api_type", "content_type", ... } ],
  "records": [ { "id", "source_id", "title", "summary", "full_text", ... } ]
}
"""

import os
import json
import re
from datetime import datetime

# ── Historical synonym / abbreviation map ─────────────────────────────────────
# Maps common user inputs (abbreviations, alternate names, misspellings) to
# the canonical forms stored in the database. All values are lowercase.
# When the user types any key, ALL listed values are also searched.
_SYNONYM_MAP: dict[str, list[str]] = {
    # World Wars
    "ww1":          ["world war i", "world war 1", "great war", "first world war"],
    "ww2":          ["world war ii", "world war 2", "second world war", "nazi"],
    "wwi":          ["world war i", "world war 1", "great war", "first world war"],
    "wwii":         ["world war ii", "world war 2", "second world war"],
    "great war":    ["world war i", "world war 1", "ww1", "wwi"],
    "cold war":     ["ussr", "soviet", "communism", "nuclear", "nato"],
    # Countries / empires — alternate names
    "usa":          ["united states", "america", "american"],
    "us":           ["united states", "america", "american"],
    "uk":           ["united kingdom", "britain", "british", "england"],
    "ussr":         ["soviet union", "russia", "communist", "bolshevik"],
    "soviet":       ["ussr", "russia", "communism", "stalinist", "bolshevik"],
    "rome":         ["roman", "roman empire", "roman republic", "latins"],
    "roman empire": ["rome", "romans", "caesar", "augustus", "latin"],
    "greece":       ["greek", "ancient greece", "hellenic", "athenian"],
    "greek":        ["greece", "athens", "sparta", "hellenic", "olympia"],
    "egypt":        ["egyptian", "pharaoh", "nile", "cairo", "hieroglyph"],
    "persia":       ["persian", "achaemenid", "iran", "darius", "xerxes"],
    "ottoman":      ["turkey", "turkish", "ottoman empire", "istanbul"],
    "byzantine":    ["eastern roman", "constantinople", "byzantium"],
    "mongol":       ["mongolia", "genghis", "kublai", "mongol empire"],
    "aztec":        ["mexico", "mesoamerica", "tenochtitlan", "nahua"],
    "inca":         ["peru", "andean", "south america", "quechua"],
    "maya":         ["mesoamerica", "yucatan", "guatemala", "mayan"],
    # Civilisations
    "mesopotamia":  ["iraq", "babylon", "assyrian", "sumerian", "tigris", "euphrates"],
    "babylon":      ["babylonian", "mesopotamia", "nebuchadnezzar", "hammurabi"],
    "sumerian":     ["sumer", "mesopotamia", "gilgamesh", "uruk", "cuneiform"],
    "assyrian":     ["assyria", "nineveh", "mesopotamia", "ashurbanipal"],
    "pharaoh":      ["egypt", "egyptian", "nile", "pyramid", "hieroglyph"],
    "pyramid":      ["egypt", "giza", "pharaoh", "ancient egypt"],
    # Key events
    "french revolution": ["france", "robespierre", "napoleon", "bastille", "1789"],
    "industrial revolution": ["britain", "steam engine", "factory", "coal", "textiles"],
    "renaissance":  ["italy", "florence", "michelangelo", "da vinci", "humanism"],
    "reformation":  ["protestant", "luther", "calvin", "church", "religious war"],
    "crusades":     ["holy land", "jerusalem", "pope", "knights", "saladin"],
    "black death":  ["plague", "bubonic", "pandemic", "medieval", "1348"],
    "silk road":    ["trade", "china", "central asia", "spice", "marco polo"],
    # Key figures
    "alexander":    ["alexander the great", "macedon", "greece", "persia"],
    "napoleon":     ["french revolution", "france", "waterloo", "empire"],
    "hitler":       ["nazi", "germany", "world war ii", "holocaust", "third reich"],
    "cleopatra":    ["egypt", "ptolemaic", "roman", "caesar", "antony"],
    "caesar":       ["julius caesar", "rome", "roman republic", "rubicon"],
    "gandhi":       ["india", "independence", "british india", "nonviolence"],
    "churchill":    ["world war ii", "britain", "winston", "blitz", "allied"],
    "stalin":       ["ussr", "soviet union", "communism", "gulags", "cold war"],
    "columbus":     ["age of exploration", "americas", "1492", "spain"],
    "gilgamesh":    ["mesopotamia", "sumerian", "flood narrative", "uruk", "enkidu"],
    # Historical periods
    "medieval":     ["middle ages", "feudal", "crusades", "byzantine", "gothic"],
    "ancient":      ["classical antiquity", "greece", "rome", "egypt", "mesopotamia"],
    "colonial":     ["colonialism", "empire", "imperialism", "british", "french"],
    "slavery":      ["slave trade", "atlantic", "abolition", "plantation", "emancipation"],
    "holocaust":    ["nazi", "world war ii", "jewish", "concentration camp", "genocide"],
    # Geographic terms
    "middle east":  ["arab", "islam", "ottoman", "persia", "levant", "mesopotamia"],
    "africa":       ["african", "sahara", "ethiopia", "colonialism", "egypt"],
    "china":        ["chinese", "ming", "qing", "han", "dynasty", "beijing"],
    "india":        ["indian", "mughal", "british india", "hinduism", "gandhi"],
    "japan":        ["japanese", "samurai", "meiji", "shogunate", "edo"],
}

# Stemming pairs: if the user types the left side, also search the right side
_STEM_PAIRS: list[tuple[str, str]] = [
    ("colonializ",  "colonial"),
    ("colonialis",  "colonial"),
    ("industriali", "industrial"),
    ("revolution",  "revolut"),
    ("democrac",    "democrat"),
    ("civilization","civiliz"),
    ("civilisation","civilis"),
    ("emperor",     "empire"),
    ("imperial",    "empire"),
    ("archaeolog",  "archaeol"),
    ("philosophi",  "philosoph"),
    ("religious",   "religion"),
    ("economical",  "econom"),
    ("political",   "politic"),
    ("military",    "militari"),
    ("conquered",   "conquer"),
    ("established", "establ"),
]

DB_PATH = os.path.join(os.path.dirname(__file__), "curious_history.json")

# ── Source metadata registry ──────────────────────────────────────────────────
# Maps source name → {"tier", "primary", "secondary", "description", "manuscript"}
#   tier        : "text" | "image" | "map" | "mixed" | "specialist"
#   primary     : main content type delivered
#   secondary   : secondary content type (if mixed), else None
#   manuscript  : True if source contains primary manuscripts needing English-only filter
SOURCE_METADATA: dict[str, dict] = {
    # ── Text-rich ─────────────────────────────────────────────────────────────
    "Perseus Digital Library": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Complete English translations of Herodotus, Thucydides, Caesar, Livy, Plutarch, Suetonius, Tacitus, and Plato. Deepest text per record (avg 6,000 chars).",
        "manuscript": False,
    },
    "Our World in Data": {
        "tier": "text", "primary": "dataset", "secondary": None,
        "description": "Long-form CSV datasets on historical population, GDP, warfare, and mortality. Data-rich content (avg 8,000 chars).",
        "manuscript": False,
    },
    "BL Zenodo Datasets": {
        "tier": "text", "primary": "dataset", "secondary": None,
        "description": "British Library open research datasets with rich metadata descriptions.",
        "manuscript": False,
    },
    "Wikipedia": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Pre-fetched English Wikipedia article summaries — broadest topic coverage across all eras and regions.",
        "manuscript": False,
    },
    "Wikidata": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Structured entity facts: dates, classifications, relationships for key historical topics.",
        "manuscript": False,
    },
    "BL Research Repository (OAI-PMH)": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "British Library scholarly papers, theses, and digitised collections via OAI-PMH. Largest single text source (1,642 records).",
        "manuscript": False,
    },
    "BL British National Bibliography": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "British Library book catalogue with detailed bibliographic descriptions.",
        "manuscript": False,
    },
    "Internet Archive": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Digitised public-domain books, journals, and historical texts across all eras and languages.",
        "manuscript": False,
    },
    "Internet Archive — Ancient History": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language scholarly books on ancient Greece, Rome, Egypt, and Mesopotamia. English-only filter enforced.",
        "manuscript": False,
    },
    "Cabinet Papers UK": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "UK government cabinet documents and policy papers via Open Library.",
        "manuscript": False,
    },
    "Qatar Digital Library": {
        "tier": "text", "primary": "metadata_only", "secondary": None,
        "description": "Islamic and Arabic manuscript metadata links. Full text not stored — metadata only.",
        "manuscript": False,
    },
    "National Library Norway (nb.no)": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Norwegian national library catalogue — titles and metadata for Norwegian and Nordic history.",
        "manuscript": False,
    },
    "HathiTrust Digital Library": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language digitised books from 57 global historical topics. Language-filtered to English only.",
        "manuscript": False,
    },
    "Internet Archive — India": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language texts on Indian history — ancient, Mughal, colonial, and independence eras.",
        "manuscript": False,
    },
    "Internet Archive — Africa": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language texts on African history across all regions and periods.",
        "manuscript": False,
    },
    "SOAS University London": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Academic papers and theses from SOAS — world leader in Africa, Asia, and Middle East studies.",
        "manuscript": False,
    },
    "OpenITI — Islamic Texts": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language Islamic history scholarship. Arabic/Persian raw texts excluded — English only.",
        "manuscript": False,
    },
    "Library of Congress": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "US and world history documents from the Library of Congress collections.",
        "manuscript": False,
    },
    "National Diet Library Japan": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "English-language books on Japanese and East Asian history from Japan's national library.",
        "manuscript": False,
    },
    "Memoria Chilena": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Chilean and Latin American history from the Biblioteca Nacional de Chile. Spanish-language content.",
        "manuscript": False,
    },
    # ── Manuscript sources (English-only, curated translations) ───────────────
    "CDLI — Cuneiform Digital Library": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Mesopotamian cuneiform texts — Gilgamesh, Hammurabi Code, Babylonian myths. English translations only. Raw cuneiform never stored.",
        "manuscript": True,
    },
    "ORACC — Annotated Cuneiform Corpus": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Annotated Mesopotamian cuneiform — royal inscriptions, Assyrian archives, Babylonian law. English translations only.",
        "manuscript": True,
    },
    "TLA — Thesaurus Linguae Aegyptiae": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Ancient Egyptian texts — Book of the Dead, Pyramid Texts, literary works. Hieroglyphic source never stored; English only.",
        "manuscript": True,
    },
    "ISAC — Oriental Institute Chicago": {
        "tier": "text", "primary": "full_text", "secondary": None,
        "description": "Oriental Institute scholarly publications on Egypt, Mesopotamia, Persia, and the ancient Near East.",
        "manuscript": False,
    },
    # ── Image-rich ────────────────────────────────────────────────────────────
    "Finna Finland": {
        "tier": "image", "primary": "image", "secondary": "full_text",
        "description": "Finnish and Nordic cultural heritage — largest image source (3,105 records). Photographs, illustrations, portraits, and maps.",
        "manuscript": False,
    },
    "BL Wikimedia Commons": {
        "tier": "image", "primary": "image", "secondary": None,
        "description": "British Library's historical image collection via Wikimedia Commons (839 images).",
        "manuscript": False,
    },
    "Wikimedia Commons": {
        "tier": "image", "primary": "image", "secondary": None,
        "description": "Pre-fetched historical images across all eras — battle maps, portraits, archaeological photographs.",
        "manuscript": False,
    },
    # ── Map-rich ──────────────────────────────────────────────────────────────
    "National Library Sweden (KB)": {
        "tier": "mixed", "primary": "image", "secondary": "full_text",
        "description": "Sweden's national library — #1 map source (724 maps) plus 1,703 images and 601 documents. Scandinavian and European historical cartography.",
        "manuscript": False,
    },
    # ── Mixed (significant text AND images) ───────────────────────────────────
    "DPLA": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "Digital Public Library of America — 3,131 documents plus 1,341 images (including 227 maps). Deep US history coverage.",
        "manuscript": False,
    },
    "Polona Poland": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "Polish national digital library — 4,084 documents and 807 images (120 maps). Richest combined source.",
        "manuscript": False,
    },
    "Europeana Romania": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "Eastern European cultural heritage — 1,657 documents and 775 images (102 maps). Romania, Bulgaria, Serbia, Balkans.",
        "manuscript": False,
    },
    "BnF Gallica France": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "French national library — 3,011 documents and 361 images. Strong French history text coverage.",
        "manuscript": False,
    },
    "Europeana": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "Pan-European cultural heritage — near-equal split of 709 documents and 727 images across global topics.",
        "manuscript": False,
    },
    "Europeana Middle East & Global": {
        "tier": "mixed", "primary": "full_text", "secondary": "image",
        "description": "Middle Eastern, Islamic, and global cultural heritage via Europeana — documents and images on Ottoman, Persian, Arab history.",
        "manuscript": False,
    },
    # ── Specialist ────────────────────────────────────────────────────────────
    "Open Context — Archaeology Data": {
        "tier": "specialist", "primary": "artefact", "secondary": None,
        "description": "Archaeological finds from Mediterranean, Near East, Egypt, and Mesopotamia excavations — pottery, tools, structures (255 artefact records).",
        "manuscript": False,
    },
    "Project Mercury — Roman Datasets": {
        "tier": "specialist", "primary": "place", "secondary": "full_text",
        "description": "Roman geographic and historical data — provinces, cities, amphitheatres, roads, battles, and emperors.",
        "manuscript": False,
    },
    "Nomisma — Ancient Coins": {
        "tier": "specialist", "primary": "artefact", "secondary": None,
        "description": "Ancient coin linked open data — Greek, Roman, Byzantine, Persian coinage via SPARQL. Built-in records for 8 key coin types.",
        "manuscript": False,
    },
    "Pleiades — Ancient World Gazetteer": {
        "tier": "specialist", "primary": "place", "secondary": None,
        "description": "Community gazetteer of ancient places — cities, temples, sites, rivers for Greece, Rome, Egypt, and Mesopotamia.",
        "manuscript": False,
    },
    "BL GitHub Georeferencer": {
        "tier": "specialist", "primary": "metadata_only", "secondary": None,
        "description": "British Library georeferenced map metadata from GitHub.",
        "manuscript": False,
    },
}


# ── Map detection keywords ────────────────────────────────────────────────────
_MAP_KEYWORDS = frozenset([
    'map', 'maps', 'carte', 'atlas', 'mappa', 'topograph', 'topographic',
    'kart', 'landkart', 'kaart', 'mapa', 'cartograph', 'cartography',
    'plan of', 'chart of', 'survey map', 'military map', 'battle map',
    'siege plan', 'floor plan', 'town plan', 'city plan',
])


def is_map_record(record: dict) -> bool:
    """Return True if an image record is a historical map."""
    if record.get("record_type") != "image":
        return False
    t    = (record.get("title") or "").lower()
    s    = (record.get("summary") or "").lower()
    tags = " ".join(record.get("tags") or []).lower()
    combined = f"{t} {s} {tags}"
    return any(kw in combined for kw in _MAP_KEYWORDS)


def get_source_metadata(source_name: str) -> dict:
    """Return metadata dict for a source, with safe defaults."""
    return SOURCE_METADATA.get(source_name, {
        "tier": "text", "primary": "full_text",
        "secondary": None, "description": "", "manuscript": False,
    })


# ── Source registry ───────────────────────────────────────────────────────────
SOURCES = [
    {"name": "Internet Archive",        "base_url": "https://archive.org",                           "api_type": "REST", "content_type": "full_text"},
    {"name": "Perseus Digital Library", "base_url": "https://gutenberg.org",                         "api_type": "REST", "content_type": "full_text"},
    {"name": "Our World in Data",       "base_url": "https://ourworldindata.org",                    "api_type": "REST", "content_type": "dataset"},
    {"name": "Qatar Digital Library",   "base_url": "https://archive.org",                           "api_type": "REST", "content_type": "metadata_only"},
    {"name": "Cabinet Papers UK",       "base_url": "https://discovery.nationalarchives.gov.uk/API", "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikipedia",               "base_url": "https://en.wikipedia.org",                      "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikidata",                "base_url": "https://www.wikidata.org",                      "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikimedia Commons",       "base_url": "https://commons.wikimedia.org",                 "api_type": "REST", "content_type": "full_text"},
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _empty_db() -> dict:
    return {
        "meta":    {"version": "2.0", "last_updated": None, "total_records": 0},
        "sources": [],
        "records": [],
    }


def _source_content_type(conn: dict, source_id: int) -> str:
    for src in conn["sources"]:
        if src["id"] == source_id:
            return src.get("content_type", "full_text")
    return "full_text"


# ── Public API ────────────────────────────────────────────────────────────────

# ── In-memory cache ───────────────────────────────────────────────────────────
# The JSON is loaded once and kept in RAM.  On every call we check the file's
# mtime; if it hasn't changed (normal during serving) we return the cached dict
# directly — zero disk I/O, effectively instantaneous.
# The cache is invalidated automatically when main.py writes a new DB.

_CACHE: dict = {"data": None, "mtime": 0.0}


def get_connection() -> dict:
    """
    Return the in-memory database dict.
    Reads from disk only when curious_history.json has changed since last load.
    """
    try:
        mtime = os.path.getmtime(DB_PATH)
    except OSError:
        return _empty_db()

    if _CACHE["data"] is None or _CACHE["mtime"] != mtime:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            _CACHE["data"] = json.load(f)
        _CACHE["mtime"] = mtime

    return _CACHE["data"]


def save(conn: dict) -> None:
    """Write the in-memory database back to curious_history.json."""
    conn["meta"]["last_updated"] = datetime.utcnow().isoformat()
    conn["meta"]["total_records"] = len(conn.get("records", []))
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(conn, f, indent=2, ensure_ascii=False)
    # Bust the cache so the next get_connection() reloads the freshly-written file
    _CACHE["data"] = None
    _CACHE["mtime"] = 0.0


def reset_database() -> dict:
    """
    Wipe everything and rebuild from scratch.
    Seeds all sources and returns the empty data dict ready for fetchers.
    """
    data = _empty_db()
    for i, src in enumerate(SOURCES, start=1):
        data["sources"].append({
            "id":           i,
            "name":         src["name"],
            "base_url":     src["base_url"],
            "api_type":     src["api_type"],
            "content_type": src["content_type"],
            "last_synced":  None,
        })
    save(data)
    print("Database reset complete. All previous records and source integrations deleted.")
    return data


def get_source_id(conn: dict, source_name: str):
    for src in conn["sources"]:
        if src["name"] == source_name:
            return src["id"]
    return None


def update_last_synced(conn: dict, source_id: int) -> None:
    for src in conn["sources"]:
        if src["id"] == source_id:
            src["last_synced"] = datetime.utcnow().isoformat()
            return


def insert_record(conn: dict, source_id: int, data: dict) -> bool:
    """
    Insert one record. Returns True if inserted, False if skipped/duplicate.
    Deduplicates on (source_id, external_id).
    """
    title = data.get("title")
    if not title:
        return False

    ext_id  = data.get("external_id")
    records = conn.setdefault("records", [])

    # Deduplication check
    if ext_id:
        for r in records:
            if r.get("source_id") == source_id and r.get("external_id") == ext_id:
                return False

    content_type = _source_content_type(conn, source_id)

    # Normalise tags — keep as list in JSON
    tags = data.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [tags] if tags else []
    elif tags is None:
        tags = []

    record = {
        "id":             len(records) + 1,
        "source_id":      source_id,
        "external_id":    ext_id,
        "title":          title,
        "summary":        data.get("summary"),
        "full_text":      data.get("full_text"),
        "record_type":    data.get("record_type", "document"),
        "content_type":   content_type,
        "region":         data.get("region"),
        "era":            data.get("era"),
        "date_text":      data.get("date_text"),
        "date_year_start": data.get("date_year_start"),
        "image_url":      data.get("image_url"),
        "source_url":     data.get("source_url"),
        "tags":           tags,
        "created_at":     datetime.utcnow().isoformat(),
    }
    records.append(record)
    return True


def get_total_count(conn: dict) -> int:
    return len(conn.get("records", []))


def get_count_by_content_type(conn: dict) -> dict:
    counts = {}
    for r in conn.get("records", []):
        ct = r.get("content_type", "unknown")
        counts[ct] = counts.get(ct, 0) + 1
    return counts


# ── Numeral normalisation ─────────────────────────────────────────────────────
_WORD_TO_ROMAN = {
    'one': 'i', 'two': 'ii', 'three': 'iii', 'four': 'iv', 'five': 'v',
    'six': 'vi', 'seven': 'vii', 'eight': 'viii', 'nine': 'ix', 'ten': 'x',
}
_ROMAN_TO_WORD = {v: k for k, v in _WORD_TO_ROMAN.items()}


def _normalise_numerals(text: str) -> str:
    words = text.split()
    return ' '.join(_WORD_TO_ROMAN.get(w, w) for w in words)


# ── Query expansion ───────────────────────────────────────────────────────────

def expand_query(topic: str) -> list[str]:
    """
    Return a list of all search phrases to match against records,
    expanded from the original topic using:
      1. The raw topic and its numeral-normalised form
      2. Synonym expansion from _SYNONYM_MAP (multi-word and single-word keys)
      3. Stem pairs so "colonialism" also hits "colonial"

    All returned strings are lowercase.
    """
    topic_lower = topic.lower().strip()
    topic_norm  = _normalise_numerals(topic_lower)

    phrases: list[str] = [topic_lower]
    if topic_norm != topic_lower:
        phrases.append(topic_norm)

    # ── Synonym expansion ────────────────────────────────────────────────────
    # Try the full topic as a key first, then individual words
    matched_keys: set[str] = set()
    for key, synonyms in _SYNONYM_MAP.items():
        if key in topic_lower:
            if key not in matched_keys:
                matched_keys.add(key)
                phrases.extend(synonyms)

    # ── Stem pair expansion ──────────────────────────────────────────────────
    for (stem, short) in _STEM_PAIRS:
        if stem in topic_lower and short not in phrases:
            phrases.append(short)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ── Keyword extraction ────────────────────────────────────────────────────────

def _extract_keywords(topic: str) -> list:
    """
    Extract meaningful search keywords from a topic string, including
    synonym-expanded terms. Keeps historically important words.
    For words > 8 chars, also adds the first 7 chars for prefix matching.
    """
    _STOPWORDS = {
        'the', 'and', 'for', 'with', 'from', 'this', 'that', 'was', 'were',
        'in', 'of', 'a', 'an', 'at', 'by', 'on', 'to', 'its', 'or', 'but',
        'not', 'are', 'is', 'it', 'as', 'be', 'do', 'had', 'has', 'have',
        'also', 'when', 'been', 'more', 'into', 'over', 'two', 'one',
        'then', 'than', 'they', 'them', 'their', 'all', 'any', 'how',
    }

    # Start from the full expanded phrase list
    all_phrases = expand_query(topic)
    raw_words: list[str] = []
    for phrase in all_phrases:
        for w in re.split(r'\W+', phrase):
            if len(w) >= 3 and w.lower() not in _STOPWORDS:
                raw_words.append(w.lower())

    expanded: list[str] = []
    seen: set[str] = set()
    for w in raw_words:
        if w not in seen:
            expanded.append(w)
            seen.add(w)
        if len(w) > 8:
            prefix = w[:7]
            if prefix not in seen:
                expanded.append(prefix)
                seen.add(prefix)
    return expanded


# ── Search ────────────────────────────────────────────────────────────────────

def _record_text(r: dict) -> str:
    """Concatenate all searchable text fields for a record (lowercase)."""
    parts = [
        r.get("title")    or "",
        r.get("summary")  or "",
        r.get("full_text") or "",
        r.get("era")      or "",
        r.get("region")   or "",
        " ".join(r.get("tags") or []),
    ]
    return " ".join(parts).lower()


def search_records_ranked(conn: dict, topic: str,
                          content_types=("full_text",),
                          limit: int = 20,
                          url_pattern: str = None) -> list:
    """
    Multi-keyword, synonym-aware, relevance-ranked search.

    Scoring per record:
      +15  title IS exactly the query (exact match)
      +8   query phrase found in title
      +10  query phrase found in body
      +6   synonym/expanded phrase found in title
      +4   synonym/expanded phrase found in body
      +2   per individual keyword found in title
      +1   per individual keyword found in body
      +3   content depth bonus (>400 chars)
      +2   era/region matches query context
      -4   record_type == "image"
    """
    # Build all search variants (topic + synonyms + stems)
    all_phrases   = expand_query(topic)
    primary_phrase = all_phrases[0]                # original query, lowercase
    extra_phrases  = all_phrases[1:]               # synonyms / stems

    keywords      = _extract_keywords(topic)

    candidates = [
        r for r in conn.get("records", [])
        if r.get("content_type") in content_types
        and r.get("title")
        and (not url_pattern or url_pattern in (r.get("source_url") or ""))
    ]

    scored: dict = {}
    for r in candidates:
        title = (r.get("title") or "").lower()
        body  = " ".join([
            r.get("summary")   or "",
            r.get("full_text") or "",
            " ".join(r.get("tags") or []),
            r.get("era")       or "",
            r.get("region")    or "",
        ]).lower()
        score = 0

        # ── Exact title match ─────────────────────────────────────────────────
        if title == primary_phrase or any(title == p for p in extra_phrases[:3]):
            score += 15

        # ── Primary phrase match in title / body ──────────────────────────────
        if primary_phrase in title:
            score += 8
        if primary_phrase in body:
            score += 10

        # ── Synonym / expanded phrase match ───────────────────────────────────
        for phrase in extra_phrases[:8]:
            if phrase in title:
                score += 6
                break   # only award once per position
        for phrase in extra_phrases[:8]:
            if phrase in body:
                score += 4
                break

        # ── Per-keyword match ─────────────────────────────────────────────────
        for kw in keywords[:12]:
            if kw in title:
                score += 2
            if kw in body:
                score += 1

        # ── Content depth bonus ───────────────────────────────────────────────
        content_len = len(r.get("full_text") or r.get("summary") or "")
        if content_len > 400:
            score += 3

        # ── Image penalty ─────────────────────────────────────────────────────
        if r.get("record_type") == "image":
            score -= 4

        if score > 0:
            scored[r["id"]] = (r, score)

    sorted_pairs = sorted(
        scored.values(),
        key=lambda x: (-x[1], -len(x[0].get("full_text") or x[0].get("summary") or ""))
    )
    return [pair[0] for pair in sorted_pairs[:limit]]


# Keep the old name as an alias so existing callers don't break
def search_records(conn: dict, query: str,
                   content_types=("full_text",),
                   limit: int = 20,
                   url_pattern: str = None) -> list:
    """Single-phrase search (alias kept for backward compatibility)."""
    return search_records_ranked(conn, query, content_types, limit, url_pattern)


def get_classical_by_keywords(conn: dict, keywords: list) -> list:
    """
    Return Classical Antiquity records that contain ANY of the given keywords.
    Used as a supplement to ensure primary sources appear for classical topics.
    """
    if not keywords:
        return []
    results = []
    for r in conn.get("records", []):
        if r.get("era") != "Classical Antiquity":
            continue
        text = _record_text(r)
        if any(kw in text for kw in keywords):
            results.append(r)
    return results


# Ancient-era prefix set for fast membership test
_ANCIENT_ERA_PREFIXES = (
    "ancient mesopotamia", "ancient egypt", "ancient rome", "ancient greece",
    "ancient persia", "ancient near east", "ancient nubia", "ancient syria",
    "ancient anatolia", "ancient phoenicia", "ancient", "byzantine",
)


def get_ancient_by_keywords(conn: dict, keywords: list) -> list:
    """
    Return ancient-world records (Mesopotamia, Egypt, Rome, Greece, Persia …)
    that contain ANY of the given keywords.  Used as a supplement so ancient
    source records (CDLI, ORACC, TLA, ISAC, Pleiades, Mercury, Nomisma,
    Open Context, Internet Archive Ancient) appear in search results alongside
    Wikipedia/IA content.
    """
    if not keywords:
        return []
    results = []
    for r in conn.get("records", []):
        era = (r.get("era") or "").lower()
        if not any(era.startswith(p) for p in _ANCIENT_ERA_PREFIXES):
            continue
        text = _record_text(r)
        if any(kw in text for kw in keywords):
            results.append(r)
    return results
