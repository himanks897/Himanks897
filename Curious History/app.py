"""
app.py — Main Flask application for Curious History.
Defines all routes (pages + JSON APIs) and orchestrates API/DB calls.
All external API keys are read from .env via config.py — never hardcoded here.
"""

import os
import re
import json
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv

# Google Sign-In verification
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

load_dotenv()

from config import Config
from wikipedia_api import get_article, search_articles as wiki_search, get_related, get_on_this_day
from api import wikipedia, images as img_api, maps as maps_api
from api.gemini_synthesis import (
    generate_summary,
    simplify_paragraph, generate_timeline, generate_related_topics,
    generate_mcq_quiz, generate_fill_blanks_quiz, define_terms,
)
from api.key_facts import (
    get_key_people, get_key_people_data,
    get_key_places, get_key_places_data,
    get_key_causes,
)
from utils.content_formatter import format_for_article, format_for_detail
from utils.reading_time import estimate as reading_time
from utils.glossary import extract_terms
from utils.citations import build_citation

import db as _pdb          # pipeline database (in-memory JSON cache)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Google OAuth Client ID (public — safe to embed in frontend too)
GOOGLE_CLIENT_ID = "795621911465-a1122fukv8b3j96f2oq5bje7u9gnpooe.apps.googleusercontent.com"


@app.context_processor
def inject_user():
    """Makes current_user available in every Jinja2 template automatically."""
    return {"current_user": session.get("user")}

# ─── Helpers ────────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "static", "data")

# Classical-topic keyword hints (used in several places)
_CLASSICAL_HINTS = frozenset({
    'rome', 'roman', 'greece', 'greek', 'persian', 'caesar',
    'herodotus', 'thucydides', 'plutarch', 'livy', 'polybius',
    'suetonius', 'tacitus', 'hannibal', 'alexander', 'antiquity',
    'classical', 'ancient', 'athen', 'sparta', 'carthage',
    'peloponnesian', 'gallic', 'republic', 'senate', 'tribune',
    'crassus', 'pompey', 'cicero', 'augustus', 'nero',
})


def _clean_snippet(text: str) -> str:
    """Strip wikitext markup, URLs, and raw data so snippets are clean prose."""
    _re = re  # module-level re
    if not text or text == "None":
        return ""
    t = text
    # Remove wikitext templates (two passes for nesting)
    t = _re.sub(r'\{\{[^{}]*\}\}', '', t, flags=_re.DOTALL)
    t = _re.sub(r'\{\{[^{}]*\}\}', '', t, flags=_re.DOTALL)
    # Remove magic words and internal markers
    t = _re.sub(r'__[A-Z_]+__', '', t)
    # Remove category / file wiki links
    t = _re.sub(r'\[\[Category:[^\]]*\]\]', '', t)
    t = _re.sub(r'\[\[File:[^\]]*\]\]', '', t)
    t = _re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]+)\]\]', r'\1', t)
    t = _re.sub(r'Category:\S+', '', t)
    # Remove leftover braces, pipes, attribute patterns
    t = _re.sub(r'}}+|\{{2,}', '', t)
    t = _re.sub(r'\|[a-z_]+=\S*', '', t)
    # Remove bullet / list markers and wiki section headings
    t = _re.sub(r'\*+\s*;?\s*', ' ', t)
    t = _re.sub(r'={2,}[^=]+=+', '', t)
    # Remove all HTML / XML tags
    t = _re.sub(r'<[^>]+>', ' ', t)
    # Remove bare URLs (http / https / ftp)
    t = _re.sub(r'https?://\S+', '', t)
    t = _re.sub(r'ftp://\S+', '', t)
    # Remove file-path-style strings (underscored_words.ext)
    t = _re.sub(r'\b\w+(?:_\w+){2,}\.\w{2,5}\b', '', t)
    # Remove lone numeric IDs (e.g. archive item IDs like "14923847")
    t = _re.sub(r'\b\d{6,}\b', '', t)
    # Remove pipe-separated table fragments
    t = _re.sub(r'(?:^|\s)\|[^|\n]{0,80}\|', ' ', t)
    # Normalise whitespace
    t = _re.sub(r'\s+', ' ', t).strip()
    return t


def _is_prose(text: str) -> bool:
    """Return True if text looks like readable prose, not raw data or markup."""
    _re = re  # module-level re
    if not text or len(text) < 40:
        return False
    # Reject if too many pipe characters (table/template remnants)
    if text.count('|') > 2:
        return False
    # Reject if too many numbers relative to words (raw data / IDs)
    num_count = len(_re.findall(r'\b\d+\b', text))
    word_count = len(_re.findall(r'[a-zA-Z]{3,}', text))
    if word_count < 8:
        return False
    if num_count > word_count:
        return False
    # Must start with an uppercase letter (proper sentence)
    if not text[0:1].isupper():
        return False
    # Must contain at least one sentence-ending punctuation
    if not _re.search(r'[.!?]', text):
        return False
    return True


def _best_snippet(r: dict) -> str:
    """Return the cleanest, most readable prose snippet for a pipeline DB record."""
    _re = re  # module-level re
    ft  = _clean_snippet(r.get("full_text") or "")
    sm  = _clean_snippet(r.get("summary") or "")
    url = r.get("source_url", "")

    if "archive.org" in url or "openlibrary.org" in url:
        candidate = sm if sm else ft
        clean = candidate[:240].strip()
        return clean if _is_prose(clean) else ""

    raw = ft if len(ft) >= len(sm) else sm
    if not raw:
        return ""
    sentences = _re.split(r'(?<=[.!?])\s+|\n{2,}', raw)
    for sent in sentences:
        sent = sent.strip()
        if _is_prose(sent):
            return sent[:240]
    return ""


def _source_label(url: str, region: str = "") -> str:
    """Derive a friendly source badge from a record URL and optional region."""
    if not url:
        return "Historical Archive"
    if "gutenberg.org" in url:
        return "Project Gutenberg"
    if "wikisource.org" in url:
        return "Wikisource"
    if "archive.org" in url:
        return "Internet Archive"
    if "openlibrary.org" in url:
        return "Open Library"
    if "wikipedia.org" in url:
        return "Wikipedia"
    if "wikidata.org" in url:
        return "Wikidata"
    if "commons.wikimedia.org" in url:
        return "Wikimedia Commons"
    if "nationalarchives.gov.uk" in url:
        return "UK National Archives"
    # ── Europeana-hosted records: use region to give proper source label ───────
    if "europeana.eu" in url:
        _region_labels = {
            "Poland":   "Polona Poland",
            "Finland":  "Finna Finland",
            "Sweden":   "National Library Sweden",
            "Romania":  "Europeana Romania",
            "France":   "BnF Gallica",
            "Norway":   "National Library Norway",
        }
        return _region_labels.get(region, "Europeana")
    # ── Other direct-API sources ──────────────────────────────────────────────
    if "nb.no" in url or "api.nb.no" in url:
        return "National Library Norway"
    if "libris.kb.se" in url or "data.kb.se" in url:
        return "National Library Sweden"
    if "finna.fi" in url:
        return "Finna Finland"
    if "polona.pl" in url:
        return "Polona Poland"
    if "gallica.bnf.fr" in url:
        return "BnF Gallica"
    if "dp.la" in url:
        return "DPLA"
    if "bl.uk" in url or "bl.iro.bl.uk" in url:
        return "British Library"
    if "zenodo.org" in url:
        return "Zenodo"
    if "github.com/britishlibrary" in url:
        return "BL GitHub"
    if "jstor.org" in url:
        return "JSTOR"
    if "doi.org" in url:
        return "Academic Journal"
    if "perseus.tufts.edu" in url or "data.perseus.org" in url:
        return "Perseus Digital Library"
    if "wikimediafoundation.org" in url or "upload.wikimedia.org" in url:
        return "Wikimedia"
    if "loc.gov" in url:
        return "Library of Congress"
    if "theqi.com" in url or "qdl.qa" in url:
        return "Qatar Digital Library"
    if "ndl.go.jp" in url:
        return "National Diet Library Japan"
    if "hathitrust.org" in url:
        return "HathiTrust Digital Library"
    if "eprints.soas.ac.uk" in url or "digital.soas.ac.uk" in url:
        return "SOAS University London"
    if "memoriachilena.gob.cl" in url:
        return "Memoria Chilena"
    if "openiti.org" in url:
        return "OpenITI"
    return "Historical Archive"


def _clean_image_label(raw_label: str, topic: str = "") -> str:
    """
    Converts raw database image filenames/metadata into readable human labels.
    Strips resolution prefixes, underscores, file extensions, and technical IDs.
    Ensures the label is contextually meaningful and not blindly copied metadata.
    """
    if not raw_label:
        return topic or "Historical Image"
    label = raw_label
    # Strip resolution prefix like "800px-", "1200px-", "File:", "Image:"
    label = re.sub(r'^\d+px[-_]', '', label)
    label = re.sub(r'^(File|Image|Photo|Foto):\s*', '', label, flags=re.IGNORECASE)
    # Strip common file extensions
    label = re.sub(r'\.(jpg|jpeg|png|gif|svg|webp|tiff?|bmp)$', '', label, flags=re.IGNORECASE)
    # Replace underscores and hyphens with spaces
    label = label.replace('_', ' ').replace('-', ' ')
    # Strip Wikimedia Commons long ID suffixes (e.g. "q12345678")
    label = re.sub(r'\s+[qQ]\d{5,}\s*$', '', label)
    # Strip trailing/leading whitespace and normalise internal spaces
    label = re.sub(r'\s{2,}', ' ', label).strip()
    # Capitalise first letter
    if label:
        label = label[0].upper() + label[1:]
    # Reject labels that are just numbers, hashes, or very short
    if not label or len(label) < 4 or re.fullmatch(r'[\d\s\-_]+', label):
        return topic or "Historical Image"
    return label


def _fmt_record(r: dict) -> dict:
    """Format one pipeline DB record for template / JSON consumption."""
    url    = r.get("source_url", "")
    region = r.get("region", "")
    return {
        "title":       r.get("title", ""),
        "snippet":     _best_snippet(r),
        "date":        r.get("date_text", ""),
        "region":      region,
        "era":         r.get("era", ""),
        "source_url":  url,
        "record_type": r.get("record_type", ""),
        "source_name": _source_label(url, region),
        "image_url":   r.get("image_url", ""),
    }


def _get_archive_data(topic: str) -> dict:
    """
    Search the pipeline DB and return results split by SOURCE TYPE.
    Each database contributes its own section — results shown depend on
    whichever sources actually cover the topic, not a fixed priority.

    Returns:
      docs     – Primary source documents: Internet Archive, Cabinet Papers UK,
                 Open Library, Project Gutenberg, Wikisource
                 (ranked purely by text relevance to the topic)
      wiki     – Wikipedia pre-fetched summaries (1–3 most relevant articles)
      images   – Wikimedia Commons historical images (2–4 most relevant)
      primary  – Classical Antiquity primary sources (pill chips, all eras)
      metadata – Qatar Digital Library document links
    """
    _EMPTY = {"docs": [], "wiki": [], "images": [], "primary": [], "metadata": []}
    try:
        conn = _pdb.get_connection()
        if not conn.get("records"):
            return _EMPTY

        kw              = _pdb._extract_keywords(topic)
        classical_topic = any(w in _CLASSICAL_HINTS for w in kw)

        # ── Single ranked pass over all full_text records ─────────────────────
        # Fetch a larger pool so we have enough after splitting by source.
        # Increased from 40→80 to capture records from the 8 new global sources.
        all_ft = _pdb.search_records_ranked(
            conn, topic, content_types=("full_text",), limit=80
        )

        # ── Classical supplement ───────────────────────────────────────────────
        if classical_topic and kw:
            extra = _pdb.get_classical_by_keywords(conn, kw[:5])
            seen  = {r["id"] for r in all_ft}
            for r in extra:
                if r["id"] not in seen:
                    all_ft.append(r)

        # ── Metadata-only (Qatar Digital Library) ──────────────────────────────
        meta_records = _pdb.search_records_ranked(
            conn, topic, content_types=("metadata_only",), limit=5
        )

        # ── Minimum relevance threshold ───────────────────────────────────────
        # Require at least 2 DISTINCT ROOT WORDS from the query to match,
        # OR the full phrase to appear.
        #
        # "Distinct root" means we de-duplicate prefix-expanded keywords:
        # ['industrial', 'industr', 'revolution', 'revolut'] has 2 roots.
        # A doc matching 'revolution' + 'revolut' hits 1 root, not 2.
        # This prevents "Revolutionary War" from appearing for "Industrial Revolution".

        # Build root groups: each original keyword and its 7-char prefix are one root.
        _raw_kw = [w for w in re.split(r'\W+', topic.lower()) if len(w) >= 3]
        _raw_kw = [w for w in _raw_kw if w not in {
            'the','and','for','with','from','was','were','in','of','a','an',
            'at','by','on','to','its','or','but','not','are','is','it','as',
        }]
        # root_groups: list of sets, each set = {full_word, prefix_if_any}
        root_groups = []
        for w in _raw_kw:
            group = {w}
            if len(w) > 8:
                group.add(w[:7])
            root_groups.append(group)

        min_root_hit = 2 if len(root_groups) >= 2 else 1

        def _is_relevant(r: dict) -> bool:
            """True if the record matches at least min_root_hit DIFFERENT topic roots."""
            title    = (r.get("title") or "").lower()
            body     = " ".join([
                r.get("summary") or "", r.get("full_text") or ""
            ]).lower()
            combined = title + " " + body
            # Full phrase match → always relevant
            if topic.lower() in combined:
                return True
            # Count how many distinct root groups have at least one word matching
            matched_roots = sum(
                1 for grp in root_groups if any(w in combined for w in grp)
            )
            return matched_roots >= min_root_hit

        all_ft = [r for r in all_ft if _is_relevant(r)]

        # ── Split by source type — each database gets its own lane ─────────────
        docs    = []   # IA + Cabinet Papers + Gutenberg + Wikisource + OL
        wiki    = []   # Wikipedia pipeline records
        images  = []   # Wikimedia Commons records
        primary = []   # Classical Antiquity primary sources (only for classical topics)

        for r in all_ft:
            url   = r.get("source_url") or ""
            era   = r.get("era") or ""
            rtype = r.get("record_type") or ""

            # Wikidata records → already shown in the Wikidata facts panel,
            # so skip them here to avoid duplication.
            if "wikidata.org" in url:
                continue

            # Wikipedia articles → overview section, regardless of era.
            # (Some Wikipedia articles are tagged "Classical Antiquity" by the
            # pipeline fetcher — e.g. "Silk Road" — but they are still Wikipedia
            # overview articles, not primary-source documents.)
            if "en.wikipedia.org" in url:
                wiki.append(r)
                continue

            # Wikimedia Commons images → images section, regardless of era.
            if rtype == "image" or "commons.wikimedia.org" in url:
                images.append(r)
                continue

            # Classical primary sources (non-Wikipedia) → pill chips only when
            # the topic is genuinely about Classical Antiquity.
            # Without this guard, "world war two" would show Herodotus/Caesar
            # because they contain the word "war".
            if era == "Classical Antiquity":
                if classical_topic:
                    primary.append(r)
                continue

            # Everything else: IA, Cabinet Papers, Gutenberg, Wikisource, OL
            docs.append(r)

        return {
            "docs":     [_fmt_record(r) for r in docs[:8]],   # +2 slots for new sources
            "wiki":     [_fmt_record(r) for r in wiki[:3]],
            "images":   [_fmt_record(r) for r in images[:6]],  # +2 slots for Europeana images
            "primary":  [_fmt_record(r) for r in primary[:8]],
            "metadata": [_fmt_record(r) for r in meta_records[:5]],
        }
    except Exception:
        return _EMPTY


def _get_db_wikipedia_summary(topic: str) -> str:
    """
    Return the pre-fetched Wikipedia summary for a topic from the pipeline DB.
    Used as instant fallback when the live Wikipedia API is unavailable or slow.
    """
    try:
        conn = _pdb.get_connection()
        hits = _pdb.search_records_ranked(
            conn, topic,
            content_types=("full_text",),
            url_pattern="en.wikipedia.org",
            limit=1,
        )
        if hits:
            r = hits[0]
            return r.get("full_text") or r.get("summary") or ""
    except Exception:
        pass
    return ""


def _get_db_wikidata_facts(topic: str) -> dict | None:
    """
    Return pre-fetched Wikidata entity data for a topic.
    Used as instant fallback / supplement to the live Wikidata API.
    """
    _re = re  # module-level re
    try:
        conn = _pdb.get_connection()
        hits = _pdb.search_records_ranked(
            conn, topic,
            content_types=("full_text",),
            url_pattern="wikidata.org",
            limit=1,
        )
        if hits:
            r    = hits[0]
            desc = _clean_snippet(r.get("summary") or "")
            # Strip raw QID tokens like "Q142" that appear when country names
            # weren't resolved to labels in the pipeline fetcher.
            desc = _re.sub(r'\b[Qq]\d{1,6}\b', '', desc)
            # Remove orphaned "Label: ." patterns (property with no value after QID removal)
            desc = _re.sub(r'\b[A-Z][a-z]+:\s*\.', '', desc)
            # Clean up whitespace
            desc = _re.sub(r'\s{2,}', ' ', desc).strip(' .,;')
            if not desc:
                return None
            return {
                "label":       r.get("title", ""),
                "description": desc,
                "entity_id":   r.get("external_id", ""),
                "wikidata_url": r.get("source_url", ""),
                "source":      "Wikidata",
            }
    except Exception:
        pass
    return None


def load_words_of_day():
    """Loads 365 historical word-of-the-day entries from JSON file."""
    path = os.path.join(DATA_DIR, "words.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_word_of_day():
    """Returns today's word-of-the-day entry."""
    words = load_words_of_day()
    if not words:
        return {"term": "History", "era": "All Eras", "definition": "The study of past events."}
    day_of_year = datetime.now().timetuple().tm_yday
    return words[(day_of_year - 1) % len(words)]


_TOPIC_STOPWORDS = frozenset([
    'the', 'and', 'for', 'with', 'from', 'this', 'that', 'was', 'were',
    'in', 'of', 'a', 'an', 'at', 'by', 'on', 'to', 'its', 'or', 'but',
    'not', 'are', 'is', 'it', 'as', 'be', 'do', 'had', 'has', 'have',
])

# Abbreviation expansions — applied before word extraction everywhere
_TOPIC_ABBREVIATIONS = {
    r'\bww1\b':  'world war one',
    r'\bww2\b':  'world war two',
    r'\bwwi\b':  'world war one',
    r'\bwwii\b': 'world war two',
    r'\busa\b':  'united states america',
    r'\bussr\b': 'soviet union russia',
    r'\buk\b':   'united kingdom britain',
    r'\buae\b':  'united arab emirates',
    r'\bnato\b': 'north atlantic treaty',
    r'\bun\b':   'united nations',
    r'\beu\b':   'european union',
}


# Famous historical person → broader historical context mapping
_PERSON_CONTEXT_MAP = {
    # WW2 / Nazi Germany
    'adolf hitler': 'World War 2 Nazi Germany Third Reich Holocaust',
    'hitler': 'World War 2 Nazi Germany Third Reich',
    'eva braun': 'World War 2 Nazi Germany Hitler',
    'himmler': 'World War 2 Nazi Germany SS Holocaust',
    'goebbels': 'World War 2 Nazi Germany Propaganda',
    'rommel': 'World War 2 North Africa Campaign Germany',
    'göring': 'World War 2 Nazi Germany Luftwaffe',
    'mussolini': 'World War 2 Fascist Italy',
    # WW1
    'kaiser wilhelm': 'World War 1 German Empire',
    'franz ferdinand': 'World War 1 Assassination Sarajevo',
    'haig': 'World War 1 British Western Front',
    # Napoleon
    'napoleon': 'Napoleonic Wars French Empire',
    'napoleon bonaparte': 'Napoleonic Wars French Empire',
    'josephine': 'Napoleon French Empire',
    'wellington': 'Napoleonic Wars Battle of Waterloo',
    # Ancient Rome
    'julius caesar': 'Roman Republic Roman Empire',
    'caesar': 'Roman Republic Roman Empire',
    'augustus': 'Roman Empire Pax Romana',
    'nero': 'Roman Empire Julio-Claudian Dynasty',
    'cleopatra': 'Ancient Egypt Roman Republic',
    'hannibal': 'Punic Wars Carthage Rome',
    'alexander': 'Ancient Greece Macedonian Empire',
    'alexander the great': 'Ancient Greece Macedonian Empire Persia',
    # India
    'gandhi': 'Indian Independence Movement Non-Cooperation',
    'nehru': 'Indian Independence Movement Partition',
    'ambedkar': 'Indian Independence Constitution Untouchability',
    'subhas chandra bose': 'Indian National Army World War 2',
    'aurangzeb': 'Mughal Empire Decline',
    'akbar': 'Mughal Empire Golden Age',
    'tipu sultan': 'Anglo-Mysore Wars British India',
    # Russia / Soviet
    'stalin': 'Soviet Union World War 2 Cold War Gulag',
    'trotsky': 'Russian Revolution Soviet Union',
    'rasputin': 'Russian Revolution Romanov Dynasty',
    'nicholas ii': 'Russian Revolution Romanov Dynasty',
    'kruschev': 'Cold War Soviet Union Cuban Missile Crisis',
    # USA
    'lincoln': 'American Civil War Emancipation',
    'washington': 'American Revolution United States founding',
    'jefferson': 'American Revolution Declaration Independence',
    'kennedy': 'Cold War Cuban Missile Crisis Assassination',
    'martin luther king': 'Civil Rights Movement USA',
    # UK / Europe
    'churchill': 'World War 2 British Empire',
    'cromwell': 'English Civil War',
    'henry viii': 'Tudor England Reformation',
    'elizabeth i': 'Tudor England Spanish Armada',
    'victoria': 'Victorian Era British Empire',
    # China
    'mao': 'Chinese Communist Revolution Cultural Revolution',
    'mao zedong': 'Chinese Communist Revolution Cultural Revolution',
    'chiang kai-shek': 'Chinese Civil War Republic of China',
    # Other
    'columbus': 'Age of Discovery Americas',
    'vasco da gama': 'Age of Discovery Spice Trade India',
    'spartacus': 'Roman Republic Slave Revolt',
    'genghis khan': 'Mongol Empire Conquest',
    'hirohito': 'World War 2 Imperial Japan',
    'truman': 'World War 2 Atomic Bomb Cold War',
    'eisenhower': 'World War 2 Cold War',
    'de gaulle': 'World War 2 France Liberation',
    'franco': 'Spanish Civil War Fascism',
}


def _expand_topic_abbr(topic: str) -> str:
    """Expand common abbreviations before word extraction."""
    _re = re  # module-level re
    t = topic.lower()
    for pattern, replacement in _TOPIC_ABBREVIATIONS.items():
        t = _re.sub(pattern, replacement, t)
    return t


def _topic_words(topic: str) -> set:
    """
    Returns meaningful words from any topic for relevance filtering.
    Handles abbreviations (WW1, WW2, USA, USSR…), short words (war, taj),
    single-word topics (Gandhi, Rome), and long phrases alike.
    """
    _re = re  # module-level re
    expanded = _expand_topic_abbr(topic)
    # Extract words of 2+ chars (covers 'war', 'us', 'un', etc.)
    words = set(_re.findall(r'\b[a-zA-Z]{2,}\b', expanded.lower()))
    filtered = words - _TOPIC_STOPWORDS
    return filtered if filtered else words


def _resolve_search_context(topic: str) -> str:
    """
    Enriches the search topic with broader historical context.
    If the user types a person's name (e.g. 'Adolf Hitler'), we return
    the enriched query 'World War 2 Nazi Germany Third Reich Holocaust'
    so the database search and article generation cover the full context.
    Returns the enriched topic string (or the original if no mapping found).
    """
    normalized = topic.lower().strip()
    if normalized in _PERSON_CONTEXT_MAP:
        return _PERSON_CONTEXT_MAP[normalized]
    for person, context in _PERSON_CONTEXT_MAP.items():
        if person in normalized and len(person) > 5:
            return f"{topic} {context}"
    return topic


# Page-title markers that strongly indicate a sport/entertainment/fiction page
# If the page title contains these AND the topic is not about that domain, reject it.
_OFFTOPIC_PAGE_SIGNALS = frozenset([
    "world cup", "cricket", "football", "soccer", "olympic", "olympics",
    "championship", "tournament", "premier league", "fifa", "ipl",
    "baseball", "basketball", "rugby", "tennis", "golf", "swimming",
    "athletics", "formula one", "formula 1", "grand prix", "nba", "nfl",
    "superhero", "marvel", "disney", "bollywood", "hollywood",
])

# Parenthetical suffixes on Wikipedia titles that always mean non-historical content
_DISAMBIGUATION_SUFFIXES = (
    "(video game)", "(game)", "(film)", "(movie)", "(tv series)",
    "(television series)", "(novel)", "(book)", "(song)", "(album)",
    "(band)", "(comics)", "(comic)", "(anime)", "(manga)", "(character)",
    "(disambiguation)", "(series)", "(franchise)", "(miniseries)",
)

_SPORT_TOPIC_WORDS = frozenset([
    "cricket", "football", "soccer", "olympic", "sport", "cup",
    "championship", "tournament", "league", "tennis", "golf", "rugby",
    "baseball", "basketball", "swimming", "athletics",
])


def _page_relevant_to_topic(page_title: str, topic: str) -> bool:
    """
    Returns True if the Wikipedia page title has meaningful overlap with the topic.
    Prevents content about unrelated events bleeding into an article.
    Works for any topic — abbreviations, single words, long phrases.

    Strategy:
      1. If the topic is not about sports/entertainment and the page title
         clearly is (cricket, world cup, olympics…), reject immediately.
      2. Prefer matching SPECIFIC long words (>4 chars) from the topic.
      3. For short-word-only topics, fall back to any word match.
    """
    topic_w = _topic_words(topic)
    if not topic_w:
        return True
    title_lower = page_title.lower()
    topic_lower = topic.lower()

    # ── Hard reject: Wikipedia disambiguation suffixes always mean non-historical ─
    if any(suffix in title_lower for suffix in _DISAMBIGUATION_SUFFIXES):
        return False

    # ── Guard: reject clearly off-topic sport/entertainment pages ──────────
    topic_is_sport = any(s in topic_lower for s in _SPORT_TOPIC_WORDS)
    if not topic_is_sport:
        if any(signal in title_lower for signal in _OFFTOPIC_PAGE_SIGNALS):
            return False

    # ── Prefer specific long words (>4 chars) — most discriminating ────────
    specific = sorted([w for w in topic_w if len(w) > 4], key=len, reverse=True)
    if specific:
        return any(w in title_lower for w in specific)

    # ── Short-word-only topics (War, Rome, etc.) — any match is OK ─────────
    return any(w in title_lower for w in topic_w)


def _fetch_ol_books(topic: str) -> list:
    """Fetch Open Library books for a topic — standalone so it can run in a thread."""
    try:
        import requests as _req
        r = _req.get(
            "https://openlibrary.org/search.json",
            params={"q": topic, "limit": 6,
                    "fields": "key,title,author_name,first_publish_year,cover_i"},
            headers={"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"},
            timeout=6,
        )
        books = []
        for doc in r.json().get("docs", []):
            cid = doc.get("cover_i")
            books.append({
                "title":     doc.get("title", ""),
                "authors":   doc.get("author_name", []),
                "year":      doc.get("first_publish_year"),
                "cover_url": f"https://covers.openlibrary.org/b/id/{cid}-M.jpg" if cid else None,
                "url":       f"https://openlibrary.org{doc.get('key', '')}",
                "source":    "Open Library",
            })
        return books
    except Exception:
        return []


def _fetch_commons_images(topic: str) -> list:
    """Fetch Wikimedia Commons images — standalone so it can run in a thread."""
    try:
        from wikimedia_commons_api import search_images as _commons_search
        return _commons_search(topic, limit=6)
    except Exception:
        return []


def gather_raw_content(topic: str, year: int, country: str,
                       detail: bool = False) -> tuple:
    """
    Aggregates raw text content ONLY about the searched topic.
    Strips year-page and country-history pages which are too broad and cause
    off-topic content to appear. Uses only topic-specific Wikipedia articles.
    Returns (combined_text, sources_list).
    """
    main_limit  = 30000 if detail else 18000
    extra_limit = 8000  if detail else 5000

    raw_parts = []
    sources   = []

    # 1. Direct Wikipedia page for the exact topic (most relevant)
    # NOTE: Do NOT apply _page_relevant_to_topic to the direct lookup —
    # if the user typed "Japanese invasion of Manchuria" we trust Wikipedia's
    # page resolver to return exactly that article. Filtering on the title would
    # incorrectly reject it when the title doesn't repeat all query words.
    direct = wikipedia.get_page_content(topic)
    if direct and direct.get("content"):
        raw_parts.append(direct["content"][:main_limit])
        sources.append("Wikipedia")

    # 2. Best search result for the topic (catches alternate titles).
    # Search WITHOUT the year appended — adding a year degrades search accuracy
    # (e.g. "Mughal Empire 1600" misses the canonical "Mughal Empire" article).
    # Try the exact query first, then "topic history" as a broader fallback.
    search_queries = [topic, f"{topic} history", f"{topic} {country}"]
    for sq in search_queries:
        wiki_results = wikipedia.search_wikipedia(sq, limit=5)
        found_extra = False
        for result in wiki_results[:4]:
            if result["title"] == (direct or {}).get("title"):
                continue  # already included above
            if not _page_relevant_to_topic(result["title"], topic):
                continue  # skip clearly unrelated pages
            page = wikipedia.get_page_content(result["title"])
            if page and page.get("content"):
                existing = "\n".join(raw_parts)
                chunk = page["content"][:extra_limit]
                if chunk[:120] not in existing:
                    raw_parts.append(chunk)
                    if "Wikipedia" not in sources:
                        sources.append("Wikipedia")
                found_extra = True
                break
        if found_extra:
            break

    combined = "\n\n".join(filter(None, raw_parts))

    # ── Fallback: use pre-fetched Wikipedia summary from pipeline DB ──────────
    # Triggered when the live Wikipedia API returns nothing (rate-limit, outage,
    # or topic not matching any article title).  The DB summary is already in
    # memory — this costs ~2 ms and never makes a network request.
    if not combined or len(combined) < 200:
        db_summary = _get_db_wikipedia_summary(topic)
        if db_summary and len(db_summary) > 100:
            combined = db_summary[:main_limit]
            if "Wikipedia" not in sources:
                sources.append("Wikipedia")

    # ── Supplement with pipeline DB content from ALL registered sources ─────────
    try:
        db_conn = _pdb.get_connection()
        if db_conn.get("records"):
            db_records = _pdb.search_records_ranked(
                db_conn, topic, content_types=("full_text",), limit=15
            )
            for r in db_records[:8]:
                url   = r.get("source_url", "")
                if "wikipedia.org" in url or "wikidata.org" in url:
                    continue
                snippet = _best_snippet(r)
                if not snippet or len(snippet) < 60:
                    snippet = _clean_snippet(r.get("summary") or r.get("full_text") or "")[:300]
                if snippet and len(snippet) > 50:
                    src_name = _source_label(url, r.get("region", ""))
                    chunk = f"[{src_name}] {snippet}"
                    if chunk[:80] not in "\n".join(raw_parts):
                        raw_parts.append(chunk)
                        if src_name not in sources:
                            sources.append(src_name)
    except Exception:
        pass

    if not sources:
        sources = ["Wikipedia"]

    seen = set()
    unique_sources = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            unique_sources.append(s)

    # Trim combined text to the last complete sentence so the formatter
    # never receives mid-word or mid-sentence input.
    if combined:
        last_end = -1
        for i in range(len(combined) - 1, max(len(combined) - 800, 0), -1):
            if combined[i] in '.!?' and (i + 1 >= len(combined) or combined[i + 1] in ' \n\t\r'):
                last_end = i
                break
        if last_end > 100:
            combined = combined[:last_end + 1]

    return combined, unique_sources


# ─── Page Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def welcome():
    """Screen 1 — Landing page."""
    return render_template("welcome.html")


@app.route("/login")
def login():
    """Sign-in page — shown when user clicks 'Enter Curious History'."""
    return render_template("login.html")


@app.route("/home")
def home():
    """Screen 2 — Home dashboard with Today in History and Word of the Day."""
    word = get_word_of_day()
    now = datetime.now()
    # Use wikipedia_api.get_on_this_day for richer event data (year + pages list)
    today_events = get_on_this_day(now.month, now.day)
    today_event = today_events[0] if today_events else wikipedia.get_on_this_day(now.month, now.day)
    recent_searches = session.get("recent_searches", [])
    return render_template(
        "home.html",
        word_of_day=word,
        today_event=today_event,
        today_events=today_events,
        recent_searches=recent_searches,
    )


@app.route("/year")
def year_select():
    """Screen 3 — Year selection (BCE or CE)."""
    era = request.args.get("era", "ce")
    return render_template("year.html", era=era)


@app.route("/country")
def country_select():
    """Screen 4 — Country selection."""
    era = request.args.get("era", "ce")
    year = request.args.get("year", "1900")
    return render_template("country.html", era=era, year=year)


@app.route("/topic")
def topic_input():
    """Screen 5 — Topic/keyword input with AI suggestions."""
    era = request.args.get("era", "ce")
    year = request.args.get("year", "1900")
    country = request.args.get("country", "World")
    return render_template("topic.html", era=era, year=year, country=country)


@app.route("/results")
def results():
    """Screen 6 — Main results page with full article content.
    All external API calls run in PARALLEL via ThreadPoolExecutor for speed.
    """
    topic    = request.args.get("topic", "")
    year_str = request.args.get("year", "1900")
    country  = request.args.get("country", "World")
    era      = request.args.get("era", "ce")

    if not topic:
        return redirect(url_for("home"))

    try:
        year = int(year_str)
    except ValueError:
        year = 1900

    _EMPTY_ARCHIVE = {"docs": [], "wiki": [], "images": [], "primary": [], "metadata": []}

    def _safe(future, default):
        """Collect a Future result with a timeout; return default on any failure."""
        try:
            return future.result(timeout=22)
        except Exception:
            return default

    # ── Phase 1: Fire ALL independent API calls in parallel ───────────────────
    # Sequential equivalent took 15-25 s. Parallel cuts it to ~3-6 s.
    with ThreadPoolExecutor(max_workers=12) as ex:
        f_article   = ex.submit(get_article, topic)
        f_raw       = ex.submit(gather_raw_content, topic, year, country)
        f_images    = ex.submit(img_api.get_all_images, topic, year, country, 10)
        f_maps      = ex.submit(maps_api.get_all_maps, topic, country, year, 5)
        f_also      = ex.submit(wikipedia.get_also_this_year, year, country)
        f_people    = ex.submit(wikipedia.get_famous_people_alive, year, country)
        f_related   = ex.submit(generate_related_topics, topic, year, country)
        f_wiki_rel  = ex.submit(get_related, topic, 6)
        f_archive   = ex.submit(_get_archive_data, topic)
        f_ol        = ex.submit(_fetch_ol_books, topic)
        f_commons   = ex.submit(_fetch_commons_images, topic)
        f_wiki_srch = ex.submit(wiki_search, topic, 6)  # fallback if article not found

        # ── Phase 1a: get raw content first → needed for article formatting ────
        raw_result  = _safe(f_raw, ("", ["Wikipedia"]))
        raw_content, sources = (
            raw_result if isinstance(raw_result, tuple) else ("", ["Wikipedia"])
        )

        # ── Phase 1b: format article from Wikipedia/DB content (no Gemini) ────────
        # Gemini is only used for summaries and quizzes, NOT for article generation.
        # The formatter produces complete, structured articles from raw source text.
        article_data = format_for_article(raw_content, topic, year, country, era)
        article_html = article_data.get("html", "")
        importance   = article_data.get("importance_level", "National")
        key_terms    = article_data.get("key_terms", []) or extract_terms(article_html)

        # ── Phase 1c: kick off define_terms while other futures complete ───────
        f_terms = ex.submit(define_terms, key_terms[:8], f"{topic} {country}") \
                  if key_terms else None

        # ── Collect all remaining futures ─────────────────────────────────────
        wiki_data_raw      = _safe(f_article,   None)
        event_images       = _safe(f_images,    [])
        event_maps         = _safe(f_maps,      [])
        also_year          = _safe(f_also,       [])
        _raw_people        = _safe(f_people,    [])
        # Filter out Wikipedia "List of …" articles that appear as fake "people"
        people_alive       = [
            p for p in _raw_people
            if p and not (p.get("name", "") or "").lower().startswith("list of")
            and not (p.get("description", "") or "").lower().startswith("list")
            and len((p.get("name", "") or "").strip()) > 1
        ]
        related            = _safe(f_related,   [])
        wiki_related       = _safe(f_wiki_rel,  [])
        archive_data       = _safe(f_archive,   _EMPTY_ARCHIVE)
        ol_books           = _safe(f_ol,        [])
        commons_images     = _safe(f_commons,   [])
        wiki_suggestions_r = _safe(f_wiki_srch, [])
        term_defs          = _safe(f_terms, {}) if f_terms else {}

    # ── Phase 2: post-process (no more network calls) ─────────────────────────
    wiki_suggestions = []
    wiki_error = None
    if wiki_data_raw is None:
        wiki_suggestions = wiki_suggestions_r
        wiki_data = {}
    elif "error" in (wiki_data_raw or {}):
        wiki_error = wiki_data_raw.get("error")
        wiki_data = {}
    else:
        wiki_data = wiki_data_raw or {}

    # Prepend Wikipedia thumbnail if not already present
    if wiki_data.get("image"):
        wiki_title = _clean_image_label(wiki_data.get("title", ""), topic)
        wiki_img = {
            "url":     wiki_data["image"],
            "title":   wiki_title,
            "caption": wiki_data.get("description", "") or wiki_title,
            "alt":     wiki_title,
            "source":  "Wikipedia",
            "license": "CC BY-SA",
        }
        if not any(i.get("url") == wiki_data["image"] for i in event_images):
            event_images.insert(0, wiki_img)

    # Clean labels on all event images from the API
    for img in event_images:
        img["title"]   = _clean_image_label(img.get("title", ""), topic)
        img["caption"] = _clean_image_label(img.get("caption", "") or img.get("title", ""), topic)
        img["alt"]     = img["title"]

    # Merge Wikimedia Commons images (deduplicated) with cleaned labels
    _seen = {i["url"] for i in event_images}
    for img in commons_images:
        if img.get("url") and img["url"] not in _seen:
            clean_title = _clean_image_label(img.get("title", ""), topic)
            event_images.append({
                "url":     img["url"],
                "title":   clean_title,
                "caption": _clean_image_label(img.get("description") or img.get("title", ""), topic),
                "alt":     clean_title,
                "source":  "Wikimedia Commons",
                "license": img.get("license", ""),
            })
            _seen.add(img["url"])

    gallery_images = event_images

    # Remaining quick / in-memory calculations
    read_time        = reading_time(article_html)
    wikidata_from_db = _get_db_wikidata_facts(topic)

    _db_src_count = sum(1 for k in ("full_text", "primary", "metadata")
                        if archive_data.get(k))
    confidence = (len(sources)
                  + (1 if event_images else 0)
                  + (1 if event_maps else 0)
                  + _db_src_count)

    search_entry = {"topic": topic, "year": year, "country": country, "era": era}
    recent = session.get("recent_searches", [])
    recent = [s for s in recent if s.get("topic") != topic]
    recent.insert(0, search_entry)
    session["recent_searches"] = recent[:5]

    citation  = build_citation(topic, year, country, sources)
    event_key = f"{year}_{country}_{topic}".lower().replace(" ", "_")

    # ── Build comprehensive source list for the "Verified Sources" popover ────
    # Starts with article-text sources, then adds every source that actually
    # contributed data to this article (images, maps, archive records, etc.)
    _seen_src = set()
    all_sources = []
    def _add_src(name):
        n = (name or "").strip()
        if n and n not in _seen_src:
            _seen_src.add(n)
            all_sources.append(n)

    for s in sources:                                      # article text sources
        _add_src(s)
    for img in event_images:                               # image sources
        _add_src(img.get("source", ""))
    for m in event_maps:                                   # map sources
        _add_src(m.get("source", ""))
    for rec in archive_data.get("docs", []):               # IA, Gutenberg, OL…
        _add_src(rec.get("source_name", ""))
    for rec in archive_data.get("wiki", []):               # Wikipedia records
        _add_src("Wikipedia")
    for rec in archive_data.get("primary", []):            # classical primaries
        _add_src(rec.get("source_name", ""))
    if wikidata_from_db:                                   # Wikidata facts
        _add_src("Wikidata")
    if ol_books:                                           # Open Library books
        _add_src("Open Library")

    return render_template(
        "results.html",
        topic=topic, year=year, country=country, era=era,
        article_html=article_html,
        importance=importance,
        key_terms=key_terms,
        term_defs=term_defs,
        read_time=read_time,
        images=gallery_images,
        all_images=event_images,
        maps=event_maps,
        also_year=also_year,
        people_alive=people_alive,
        related=related,
        sources=sources,
        confidence=confidence,
        citation=citation,
        event_key=event_key,
        raw_content=raw_content,
        ol_books=ol_books,
        wiki_data=wiki_data,
        wiki_suggestions=wiki_suggestions,
        wiki_error=wiki_error,
        wiki_related=wiki_related,
        archive_data=archive_data,
        wikidata_from_db=wikidata_from_db,
        all_sources=all_sources,
    )


@app.route("/api/landing-preview")
def api_landing_preview():
    """
    Pre-fetched Pearl Harbor images + text for the landing page preview.
    Cached 24 h — no live API call after the first request.
    """
    from api import cache as _cache
    _key = "landing_pearl_harbor_v2"
    cached = _cache.get(_key)
    if cached is not None:
        return jsonify(cached)

    ph_topic = "Attack on Pearl Harbor"
    images   = img_api.get_all_images(ph_topic, 1941, "United States", limit=4)
    result   = {
        "images": images[:2],
        "topic":  ph_topic,
        "year":   1941,
        "country": "United States",
    }
    _cache.set(_key, result, ttl=86400)
    return jsonify(result)


@app.route("/saved")
def saved():
    """Screen 7 — Saved events collection."""
    return render_template("saved.html")


@app.route("/quiz")
def quiz_page():
    """Quiz page — generated by Gemini based on article content."""
    topic = request.args.get("topic", "")
    year = request.args.get("year", "1900")
    country = request.args.get("country", "World")
    era = request.args.get("era", "ce")
    quiz_type = request.args.get("type", "mcq")  # 'mcq' or 'fitb'
    return render_template(
        "quiz.html",
        topic=topic, year=year, country=country, era=era, quiz_type=quiz_type
    )


@app.route("/summary-page")
def summary_page():
    """Summary page — shows Gemini-generated summary in a dedicated screen."""
    topic = request.args.get("topic", "")
    year = request.args.get("year", "1900")
    country = request.args.get("country", "World")
    era = request.args.get("era", "ce")
    word_count = request.args.get("words", "200")
    return render_template(
        "summary.html",
        topic=topic, year=year, country=country, era=era, word_count=word_count
    )


# ─── JSON API Routes ──────────────────────────────────────────────────────────

@app.route("/api/suggestions")
def api_suggestions():
    """Returns AI topic suggestions for a year/country combination."""
    year = int(request.args.get("year", 1900))
    country = request.args.get("country", "World")
    era = request.args.get("era", "ce")
    suggestions = wikipedia.get_topic_suggestions(year, country, era)
    return jsonify({"suggestions": suggestions})


@app.route("/api/today-history")
def api_today_history():
    """Returns today's 'On This Day' event from Wikipedia."""
    now = datetime.now()
    event = wikipedia.get_on_this_day(now.month, now.day)
    return jsonify({"event": event})


@app.route("/api/also-this-year")
def api_also_this_year():
    """Returns 2 other global events from the same year."""
    year = int(request.args.get("year", 1900))
    country = request.args.get("country", "")
    events = wikipedia.get_also_this_year(year, country)
    return jsonify({"events": events})


@app.route("/api/simplify", methods=["POST"])
def api_simplify():
    """Simplifies a paragraph using Gemini API."""
    data = request.get_json()
    paragraph = data.get("paragraph", "")
    topic = data.get("topic", "")
    if not paragraph:
        return jsonify({"error": "No paragraph provided"}), 400
    simplified = simplify_paragraph(paragraph, topic)
    return jsonify({"html": simplified})


@app.route("/api/more-detail", methods=["POST"])
def api_more_detail():
    """Returns detailed article content via Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    era = data.get("era", "ce")
    raw_content, _ = gather_raw_content(topic, year, country, detail=True)
    detailed = format_for_detail(raw_content, topic, year, country, era)
    return jsonify({"html": detailed})


@app.route("/api/summary", methods=["POST"])
def api_summary():
    """Generates a word-count-limited summary via Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    era = data.get("era", "ce")
    word_count = int(data.get("words", 200))
    raw_content, sources = gather_raw_content(topic, year, country)
    summary = generate_summary(topic, year, country, era, word_count, raw_content)
    return jsonify({"html": summary, "sources": sources})


@app.route("/api/key-places", methods=["POST"])
def api_key_places():
    """Returns key geographic places for an event — Wikipedia-based, no Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    raw_content, _ = gather_raw_content(topic, year, country)
    result = get_key_places(topic, year, country, raw_content)
    return jsonify({"html": result})


@app.route("/api/key-causes", methods=["POST"])
def api_key_causes():
    """Returns key causes of an event — Wikipedia section extraction, no Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    raw_content, _ = gather_raw_content(topic, year, country)
    result = get_key_causes(topic, year, country, raw_content)
    return jsonify({"html": result})


@app.route("/api/key-people", methods=["POST"])
def api_key_people():
    """Returns key people involved in an event — Wikipedia-based, no Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    raw_content, _ = gather_raw_content(topic, year, country)
    result = get_key_people(topic, year, country, raw_content)
    return jsonify({"html": result})


@app.route("/api/timeline", methods=["POST"])
def api_timeline():
    """Returns a chronological mini-timeline for an event."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    raw_content, _ = gather_raw_content(topic, year, country)
    result = generate_timeline(topic, year, country, raw_content)
    return jsonify({"html": result})


@app.route("/gallery/images")
def gallery_images():
    """Full-page image gallery for a topic."""
    topic = request.args.get("topic", "")
    year_str = request.args.get("year", "1900")
    country = request.args.get("country", "World")
    era = request.args.get("era", "ce")
    try:
        year = int(year_str)
    except ValueError:
        year = 1900
    return render_template(
        "images_gallery.html",
        topic=topic, year=year, country=country, era=era,
    )


@app.route("/gallery/maps")
def gallery_maps():
    """Full-page historical maps gallery for a topic."""
    topic = request.args.get("topic", "")
    year_str = request.args.get("year", "1900")
    country = request.args.get("country", "World")
    era = request.args.get("era", "ce")
    try:
        year = int(year_str)
    except ValueError:
        year = 1900
    return render_template(
        "maps_gallery.html",
        topic=topic, year=year, country=country, era=era,
    )


@app.route("/api/images")
def api_images():
    """Fetches all images for an event — used by the Images gallery button."""
    topic = request.args.get("topic", "")
    year = int(request.args.get("year", 1900))
    country = request.args.get("country", "World")
    result = img_api.get_all_images(topic, year, country, limit=12)

    # Augment with scraped database images
    try:
        from scrapers import query_images
        scraped_imgs = query_images(f"{topic} {country} {year}", limit=6)
        seen = {img.get("url") for img in result}
        for si in scraped_imgs:
            img_url = si.get("image_url", "")
            if img_url and img_url not in seen:
                seen.add(img_url)
                result.append({
                    "url":     img_url,
                    "title":   si.get("title", ""),
                    "caption": si.get("description", ""),
                    "alt":     si.get("title", ""),
                    "source":  si.get("source", ""),
                    "license": "",
                })
    except Exception:
        pass

    return jsonify({"images": result})


@app.route("/api/gallery-images")
def api_gallery_images():
    """Enriched image set for gallery page: topic images + key people portraits + key places."""
    topic = request.args.get("topic", "")
    year = int(request.args.get("year", 1900))
    country = request.args.get("country", "World")

    raw_content, _ = gather_raw_content(topic, year, country)

    topic_images = img_api.get_all_images(topic, year, country, limit=12)
    for img in topic_images:
        img.setdefault("category", "event")

    people_data = get_key_people_data(topic, year, country, raw_content)
    # Only include people whose name or description contains a topic keyword
    topic_kw = _topic_words(topic)
    person_images = []
    for p in people_data:
        if not p.get("image_url"):
            continue
        # Accept the person if their name/description overlaps with topic words
        person_combined = (p.get("name", "") + " " + p.get("description", "")).lower()
        if any(w in person_combined for w in topic_kw) or not topic_kw:
            person_images.append({
                "url":      p["image_url"],
                "title":    p["name"],
                "caption":  p["description"][:200],
                "alt":      p["name"],
                "category": "person",
                "wiki_url": p["wiki_url"],
            })

    # Place images removed per user request — only event + person images shown
    return jsonify({
        "topic_images":  topic_images,
        "person_images": person_images,
    })


@app.route("/api/maps")
def api_maps():
    """Fetches historical maps for a region/year."""
    topic = request.args.get("topic", "")
    country = request.args.get("country", "World")
    year = int(request.args.get("year", 1900))
    result = maps_api.get_all_maps(topic, country, year, limit=6)

    # Augment with scraped database maps
    try:
        from scrapers import query_maps
        scraped_maps = query_maps(f"{topic} {country} {year}", limit=4)
        seen = {m.get("url") for m in result}
        for sm in scraped_maps:
            map_url = sm.get("map_url", "")
            if map_url and map_url not in seen:
                seen.add(map_url)
                result.append({
                    "url":     map_url,
                    "title":   sm.get("title", ""),
                    "caption": sm.get("description", ""),
                    "alt":     sm.get("title", ""),
                    "source":  sm.get("source", ""),
                    "date":    sm.get("date_range", "historical"),
                    "license": "",
                })
    except Exception:
        pass

    return jsonify({"maps": result})


@app.route("/api/quiz", methods=["POST"])
def api_quiz():
    """Generates a quiz (MCQ or fill-in-blanks) via Gemini."""
    data = request.get_json()
    topic = data.get("topic", "")
    year = int(data.get("year", 1900))
    country = data.get("country", "World")
    era = data.get("era", "ce")
    quiz_type = data.get("type", "mcq")
    raw_content, _ = gather_raw_content(topic, year, country)

    if quiz_type == "fitb":
        result = generate_fill_blanks_quiz(topic, year, country, raw_content)
    else:
        result = generate_mcq_quiz(topic, year, country, raw_content)

    return jsonify(result)


@app.route("/api/reactions", methods=["GET", "POST"])
def api_reactions():
    """GET: returns reaction counts. POST: saves a reaction."""
    event_key = request.args.get("event_key", "") or request.get_json(silent=True, force=True).get("event_key", "")

    if request.method == "POST":
        data = request.get_json()
        reaction_type = data.get("reaction_type", "")
        user_id = session.get("user_id", "guest")
        try:
            from supabase.supabase_client import upsert_reaction
            upsert_reaction(event_key, user_id, reaction_type)
        except Exception:
            pass
        return jsonify({"ok": True})

    try:
        from supabase.supabase_client import get_reactions
        counts = get_reactions(event_key)
    except Exception:
        counts = {"fascinating": 0, "shocking": 0, "inspiring": 0, "sad": 0}
    return jsonify(counts)


@app.route("/api/save-event", methods=["POST"])
def api_save_event():
    """Saves an event to the user's collection."""
    data = request.get_json()
    user_id = session.get("user_id", "guest")
    try:
        from supabase.supabase_client import save_event
        save_event(user_id, data.get("topic"), int(data.get("year", 0)),
                   data.get("country"), data.get("thumbnail_url", ""))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/save-quote", methods=["POST"])
def api_save_quote():
    """Saves a highlighted quote."""
    data = request.get_json()
    user_id = session.get("user_id", "guest")
    try:
        from supabase.supabase_client import save_quote
        save_quote(user_id, data.get("text"), data.get("source_topic"),
                   int(data.get("source_year", 0)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/surprise")
def api_surprise():
    """Returns a random year, country, and topic for the Surprise Me button."""
    countries = [
        "India", "China", "France", "England", "Egypt", "Rome", "Greece",
        "United States", "Japan", "Ottoman Empire", "Mongolia", "Persia",
        "Spain", "Portugal", "Russia", "Aztec Empire", "Inca Empire"
    ]
    topics = [
        "war", "revolution", "trade routes", "empire", "dynasty", "battle",
        "discovery", "famine", "independence", "conquest", "renaissance",
        "plague", "exploration", "rebellion", "treaty"
    ]
    year = random.randint(-1000, 2020)
    country = random.choice(countries)
    topic = random.choice(topics)
    era = "bce" if year < 0 else "ce"
    return jsonify({
        "year": abs(year),
        "country": country,
        "topic": f"{topic} in {country}",
        "era": era,
    })


@app.route("/api/wiki-search")
def api_wiki_search():
    """Wikipedia REST API full-text search — returns title, description, image."""
    q = request.args.get("q", "")
    if not q or len(q) < 3:
        return jsonify({"results": []})
    results = wiki_search(q, limit=8)
    return jsonify({"results": results})


@app.route("/api/wiki-related")
def api_wiki_related():
    """Wikipedia REST API related pages for a given topic."""
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"results": []})
    results = get_related(topic, limit=6)
    return jsonify({"results": results})


@app.route("/api/multi-images")
def api_multi_images():
    """Lazy-load: Wikimedia Commons images for a topic."""
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"commons": [], "artefacts": []})
    try:
        from wikimedia_commons_api import search_images as _commons_search
        raw = _commons_search(topic, limit=12)
        commons = [{
            "url":      img.get("url", ""),
            "alt":      img.get("title", topic),
            "caption":  img.get("description", "") or img.get("title", ""),
            "source":   "Wikimedia Commons",
            "license":  img.get("license", ""),
            "page_url": "",
        } for img in raw if img.get("url")]
        return jsonify({"commons": commons, "artefacts": []})
    except Exception as e:
        return jsonify({"commons": [], "artefacts": [], "error": str(e)})


@app.route("/api/multi-maps")
def api_multi_maps():
    """Lazy-load: Wikimedia Commons + Wikipedia maps for a topic."""
    topic = request.args.get("topic", "")
    country = request.args.get("country", "World")
    year = int(request.args.get("year", 1900))
    if not topic:
        return jsonify({"old_maps": [], "loc_maps": []})
    try:
        raw = maps_api.get_all_maps(topic, country, year, limit=8)
        old_maps = [{
            "url":      m.get("url", ""),
            "alt":      m.get("title", topic),
            "title":    m.get("title", ""),
            "source":   m.get("source", "Wikimedia Commons"),
            "date":     str(m.get("date", "")),
            "page_url": m.get("page_url", ""),
        } for m in raw if m.get("url")]
        return jsonify({"old_maps": old_maps, "loc_maps": []})
    except Exception as e:
        return jsonify({"old_maps": [], "loc_maps": [], "error": str(e)})


@app.route("/api/multi-books")
def api_multi_books():
    """Lazy-load: Open Library books for a topic."""
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"books": []})
    try:
        import requests as _req
        _r = _req.get(
            "https://openlibrary.org/search.json",
            params={"q": topic, "limit": 12,
                    "fields": "key,title,author_name,first_publish_year,cover_i"},
            headers={"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"},
            timeout=8,
        )
        books = []
        for doc in _r.json().get("docs", []):
            cid = doc.get("cover_i")
            books.append({
                "title":   doc.get("title", ""),
                "authors": ", ".join(doc.get("author_name", []))[:80],
                "year":    doc.get("first_publish_year", ""),
                "cover":   f"https://covers.openlibrary.org/b/id/{cid}-M.jpg" if cid else None,
                "url":     f"https://openlibrary.org{doc.get('key','')}",
                "source":  "Open Library",
            })
        return jsonify({"books": books})
    except Exception as e:
        return jsonify({"books": [], "error": str(e)})


@app.route("/api/multi-docs")
def api_multi_docs():
    """
    Lazy-load: Open Library book references from the Cabinet Papers pipeline.
    Shows scholarly/historical book bibliography — distinct from the raw-text
    archive records shown in #archive-panel.
    """
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"docs": [], "newspapers": []})
    try:
        conn = _pdb.get_connection()
        records = _pdb.search_records_ranked(
            conn, topic, content_types=("full_text",),
            url_pattern="openlibrary.org", limit=8
        )
        docs = []
        for r in records:
            if not r.get("title"):
                continue
            sm = r.get("summary", "") or ""
            docs.append({
                "title":       r.get("title", ""),
                "date":        r.get("date_text", ""),
                "description": sm[:180] if sm else "",
                "url":         r.get("source_url", ""),
                "source":      "Open Library",
            })
        return jsonify({"docs": docs, "newspapers": []})
    except Exception as e:
        return jsonify({"docs": [], "newspapers": [], "error": str(e)})


@app.route("/api/multi-facts")
def api_multi_facts():
    """
    Wikidata entity facts for a topic.
    Checks pre-fetched DB first (instant); falls back to live Wikidata API.
    """
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"facts": None})
    try:
        # 1 — try pre-fetched Wikidata record from pipeline DB (instant, no HTTP)
        facts = _get_db_wikidata_facts(topic)
        if facts:
            return jsonify({"facts": facts})
        # 2 — fall back to live Wikidata API
        from wikidata_api import get_wikidata_facts
        facts = get_wikidata_facts(topic)
        return jsonify({"facts": facts})
    except Exception as e:
        return jsonify({"facts": None, "error": str(e)})


@app.route("/api/archive-records")
def api_archive_records():
    """
    Pipeline DB search for a topic — source-separated results.
    Returns: docs, wiki, images, primary, metadata
    """
    topic = request.args.get("topic", "")
    if not topic:
        return jsonify({"docs": [], "wiki": [], "images": [],
                        "primary": [], "metadata": []})
    try:
        return jsonify(_get_archive_data(topic))
    except Exception as e:
        return jsonify({"docs": [], "wiki": [], "images": [],
                        "primary": [], "metadata": [], "error": str(e)})


@app.route("/api/search")
def api_search():
    """Global live search across Wikipedia. Returns top results as JSON."""
    q = request.args.get("q", "")
    if not q or len(q) < 3:
        return jsonify({"results": []})
    results = wikipedia.search_wikipedia(q, limit=6)
    return jsonify({"results": results})


@app.route("/api/history-spell")
def api_history_spell():
    """
    History-aware spelling correction.
    Checks common misspelling dictionary first, then uses Gemini for unknown terms.
    Returns suggested correction for historical terminologies only.
    """
    q = request.args.get("q", "").strip()
    if not q or len(q) < 3:
        return jsonify({"suggestion": None})

    _HISTORY_SPELL = {
        'hitlar': 'Hitler', 'hittler': 'Hitler', 'eidolf': 'Adolf',
        'napolean': 'Napoleon', 'napoleen': 'Napoleon',
        'caeser': 'Caesar', 'ceaser': 'Caesar',
        'ghandi': 'Gandhi', 'gandi': 'Gandhi', 'mahatma ghandi': 'Mahatma Gandhi',
        'cleopetra': 'Cleopatra', 'cleopatra': 'Cleopatra',
        'alexnder': 'Alexander', 'macedona': 'Macedonia',
        'ottomon': 'Ottoman', 'ottaman': 'Ottoman',
        'mugal': 'Mughal', 'mughal': 'Mughal', 'moghul': 'Mughal',
        'chingis': 'Genghis', 'gengis': 'Genghis', 'genghes': 'Genghis',
        'sparticus': 'Spartacus', 'spartakus': 'Spartacus',
        'crusaide': 'Crusade', 'crusaides': 'Crusades',
        'rennaisance': 'Renaissance', 'renaisance': 'Renaissance', 'renaissence': 'Renaissance',
        'reformation': 'Protestant Reformation',
        'medievel': 'Medieval', 'medival': 'Medieval',
        'byzentine': 'Byzantine', 'bizantine': 'Byzantine',
        'mesopotama': 'Mesopotamia', 'mesopotemia': 'Mesopotamia',
        'phaorah': 'Pharaoh', 'pharoah': 'Pharaoh',
        'hieroglifics': 'Hieroglyphics', 'hieroglyphics': 'Hieroglyphics',
        'feudalisim': 'Feudalism', 'feudalim': 'Feudalism',
        'colonalisim': 'Colonialism', 'colonalim': 'Colonialism',
        'imperalisim': 'Imperialism',
        'bolshevik': 'Bolshevik Revolution', 'bolshevist': 'Bolshevik',
        'mao setung': 'Mao Zedong', 'mao ze dong': 'Mao Zedong',
        'hiroshema': 'Hiroshima',
        'versaille': 'Versailles', 'versails': 'Versailles',
        'austia-hungary': 'Austria-Hungary', 'austro-hungaria': 'Austria-Hungary',
        'sumerians': 'Sumerians Mesopotamia', 'sumeria': 'Sumer Mesopotamia',
        'aztecs': 'Aztec Empire', 'inkas': 'Inca Empire',
        'vikigns': 'Vikings', 'vikingz': 'Vikings',
        'mongols': 'Mongol Empire', 'mongal': 'Mongol',
    }

    q_lower = q.lower()
    if q_lower in _HISTORY_SPELL:
        return jsonify({"suggestion": _HISTORY_SPELL[q_lower]})

    for misspell, correct in _HISTORY_SPELL.items():
        if misspell in q_lower and len(misspell) > 4:
            return jsonify({"suggestion": q.lower().replace(misspell, correct.lower()).title()})

    return jsonify({"suggestion": None})


# ─── Google Auth ──────────────────────────────────────────────────────────────

@app.route("/api/google-login", methods=["POST"])
def api_google_login():
    """
    Accepts either:
      { "access_token": "..." }  — from OAuth Token Client (desktop + mobile)
      { "credential":   "..." }  — from One Tap ID token (kept for compat)

    Verifies with Google and stores the user in the Flask session.
    Returns: { name, email, picture } on success, or { error } on failure.
    """
    import requests as _requests
    data = request.get_json(silent=True) or {}

    # ── Path A: OAuth2 access token (Token Client — works on mobile) ──────────
    access_token = (data.get("access_token") or "").strip()
    if access_token:
        # Ask Google's userinfo endpoint to validate the token and return user data
        resp = _requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=8,
        )
        if resp.status_code != 200:
            return jsonify({"error": "Google token rejected"}), 401

        info = resp.json()
        # Reject tokens not issued for our client (aud field)
        if info.get("aud") and info["aud"] != GOOGLE_CLIENT_ID:
            return jsonify({"error": "Token audience mismatch"}), 401

        user = {
            "sub":     info.get("sub", ""),
            "name":    info.get("name", ""),
            "email":   info.get("email", ""),
            "picture": info.get("picture", ""),
        }

    # ── Path B: ID token credential (One Tap — desktop fallback) ─────────────
    else:
        credential = (data.get("credential") or "").strip()
        if not credential:
            return jsonify({"error": "No token provided"}), 400

        try:
            id_info = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=10,
            )
        except ValueError as exc:
            return jsonify({"error": f"Token verification failed: {exc}"}), 401

        user = {
            "sub":     id_info.get("sub", ""),
            "name":    id_info.get("name", ""),
            "email":   id_info.get("email", ""),
            "picture": id_info.get("picture", ""),
        }

    # ── Store in session ──────────────────────────────────────────────────────
    session["user"]    = user
    session["user_id"] = user["sub"]   # used by reactions / save endpoints
    session.permanent  = True

    return jsonify({
        "name":    user["name"],
        "email":   user["email"],
        "picture": user["picture"],
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Clears the session and signs the user out."""
    session.clear()
    return jsonify({"ok": True})


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=port)
