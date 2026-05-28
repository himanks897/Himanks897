"""
cache.py — File-based caching layer for all external API responses.
Prevents duplicate calls to Wikipedia, Gemini, images, etc.
Returns cached data within TTL; otherwise triggers a fresh fetch.
"""

import os
import json
import time
import hashlib
from config import Config

CACHE_DIR = Config.CACHE_DIR
DEFAULT_TTL = 86400  # 24 hours in seconds

def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_key(key: str) -> str:
    """Returns a filesystem-safe filename for any cache key."""
    return hashlib.md5(key.encode()).hexdigest() + ".json"

def get(key: str):
    """Returns cached value if it exists and hasn't expired, else None."""
    _ensure_cache_dir()
    path = os.path.join(CACHE_DIR, _cache_key(key))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) > data.get("ttl", DEFAULT_TTL):
            os.remove(path)
            return None
        return data.get("value")
    except Exception:
        return None

def set(key: str, value, ttl: int = DEFAULT_TTL):
    """Stores value in cache with the given TTL (seconds)."""
    _ensure_cache_dir()
    path = os.path.join(CACHE_DIR, _cache_key(key))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "ttl": ttl, "value": value}, f)
    except Exception:
        pass

def clear(key: str):
    """Removes a specific cache entry."""
    _ensure_cache_dir()
    path = os.path.join(CACHE_DIR, _cache_key(key))
    if os.path.exists(path):
        os.remove(path)
