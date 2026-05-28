"""
supabase_client.py — Initialises and exposes the Supabase client.
All database operations go through this module.
Falls back gracefully when Supabase credentials are not configured.
"""

import os
from config import Config

_client = None

def get_client():
    """Returns the Supabase client, initialising it on first call. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    if not Config.SUPABASE_URL or not Config.SUPABASE_ANON_KEY:
        return None
    try:
        from supabase import create_client
        _client = create_client(Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY)
        return _client
    except Exception:
        return None


def save_search(user_id: str, topic: str, year: int, country: str, era: str):
    """Saves a search entry to the search_history table."""
    client = get_client()
    if not client:
        return None
    try:
        return client.table("search_history").insert({
            "user_id": user_id, "topic": topic, "year": year,
            "country": country, "era": era
        }).execute()
    except Exception:
        return None


def get_search_history(user_id: str, limit: int = 5):
    """Returns the last N searches for a user."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("search_history").select("*").eq(
            "user_id", user_id
        ).order("searched_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception:
        return []


def save_event(user_id: str, topic: str, year: int, country: str, thumbnail_url: str = ""):
    """Saves an event to the saved_events table."""
    client = get_client()
    if not client:
        return None
    try:
        return client.table("saved_events").insert({
            "user_id": user_id, "topic": topic, "year": year,
            "country": country, "thumbnail_url": thumbnail_url
        }).execute()
    except Exception:
        return None


def get_saved_events(user_id: str):
    """Returns all saved events for a user."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("saved_events").select("*").eq(
            "user_id", user_id
        ).order("saved_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


def save_quote(user_id: str, text: str, source_topic: str, source_year: int = None):
    """Saves a highlighted quote to saved_quotes."""
    client = get_client()
    if not client:
        return None
    try:
        return client.table("saved_quotes").insert({
            "user_id": user_id, "quote_text": text,
            "source_topic": source_topic, "source_year": source_year
        }).execute()
    except Exception:
        return None


def upsert_reaction(event_key: str, user_id: str, reaction_type: str):
    """Inserts or updates a user's reaction to an event."""
    client = get_client()
    if not client:
        return None
    try:
        return client.table("reactions").upsert({
            "event_key": event_key,
            "user_id": user_id,
            "reaction_type": reaction_type
        }, on_conflict="event_key,user_id").execute()
    except Exception:
        return None


def get_reactions(event_key: str) -> dict:
    """Returns aggregate reaction counts for an event key."""
    client = get_client()
    if not client:
        return {"fascinating": 0, "shocking": 0, "inspiring": 0, "sad": 0}
    try:
        result = client.table("reactions").select("reaction_type").eq("event_key", event_key).execute()
        counts = {"fascinating": 0, "shocking": 0, "inspiring": 0, "sad": 0}
        for row in (result.data or []):
            rt = row.get("reaction_type", "")
            if rt in counts:
                counts[rt] += 1
        return counts
    except Exception:
        return {"fascinating": 0, "shocking": 0, "inspiring": 0, "sad": 0}
