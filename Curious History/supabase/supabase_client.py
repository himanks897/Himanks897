"""
supabase_client.py — Initialises and exposes the Supabase client.
All database operations go through this module.
Falls back gracefully when Supabase credentials are not configured.
"""

import os
from datetime import date
from config import Config
from plans import Plan, PLAN_LIMITS

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


# ── Subscription / Plan functions ────────────────────────────────────────────

_PLAN_DEFAULTS = {
    "plan": Plan.GUEST,
    "searches_today": 0,
    "last_search_date": None,
    "subscription_active": False,
}


def get_user_plan(user_id: str) -> dict:
    """Returns plan record for user_id, or guest defaults if not found."""
    client = get_client()
    if not client or not user_id:
        return _PLAN_DEFAULTS.copy()
    try:
        result = client.table("user_plans").select("*").eq("user_id", user_id).limit(1).execute()
        if result.data:
            row = result.data[0]
            return {
                "plan":               row.get("plan", Plan.GUEST),
                "searches_today":     row.get("searches_today", 0),
                "last_search_date":   row.get("last_search_date"),
                "subscription_active": row.get("subscription_active", False),
            }
    except Exception:
        pass
    return _PLAN_DEFAULTS.copy()


def upsert_user_plan(user_id: str, plan: str, subscription_active: bool = True) -> None:
    """Creates or updates the user's plan in the database."""
    client = get_client()
    if not client or not user_id:
        return
    try:
        client.table("user_plans").upsert({
            "user_id": user_id,
            "plan": plan,
            "subscription_active": subscription_active,
        }, on_conflict="user_id").execute()
    except Exception:
        pass


def check_and_increment_search(user_id: str, plan: str) -> tuple:
    """
    Checks daily search limit and increments count if allowed.
    Returns (allowed: bool, searches_used: int, daily_limit: int).
    Resets searches_today to 0 when the date has changed.
    """
    daily_limit = PLAN_LIMITS.get(plan, PLAN_LIMITS[Plan.GUEST])["searches_per_day"]
    client = get_client()
    if not client or not user_id:
        return (False, 0, daily_limit)

    today_str = date.today().isoformat()
    try:
        result = client.table("user_plans").select(
            "searches_today,last_search_date"
        ).eq("user_id", user_id).limit(1).execute()

        if result.data:
            row = result.data[0]
            stored_date = row.get("last_search_date") or ""
            searches_today = row.get("searches_today", 0)

            # Reset if the date has changed
            if stored_date != today_str:
                searches_today = 0

            if searches_today >= daily_limit:
                return (False, searches_today, daily_limit)

            # Increment
            client.table("user_plans").update({
                "searches_today": searches_today + 1,
                "last_search_date": today_str,
            }).eq("user_id", user_id).execute()
            return (True, searches_today + 1, daily_limit)
        else:
            # Row doesn't exist yet — create with plan, start at 1 search
            client.table("user_plans").upsert({
                "user_id": user_id,
                "plan": plan,
                "searches_today": 1,
                "last_search_date": today_str,
                "subscription_active": plan != Plan.GUEST,
            }, on_conflict="user_id").execute()
            return (True, 1, daily_limit)
    except Exception:
        return (True, 0, daily_limit)


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
