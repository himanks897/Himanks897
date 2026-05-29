"""
config.py — Centralised configuration for Curious History.
Reads all secrets from environment variables; never hardcodes keys.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"

    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

    # Gemini AI — disabled; key removed, all AI generation uses Wikipedia pipeline
    GEMINI_API_KEY = ""

    # Wikimedia
    WIKIMEDIA_USER_AGENT = os.getenv(
        "WIKIMEDIA_USER_AGENT", "CuriousHistory/1.0 (himanks897@gmail.com)"
    )

    # World History Encyclopedia
    WORLD_HISTORY_API_KEY = os.getenv("WORLD_HISTORY_ENCYCLOPEDIA_API_KEY", "")

    # Smithsonian
    SMITHSONIAN_API_KEY = os.getenv("SMITHSONIAN_API_KEY", "")

    # Trove (National Library of Australia) — free key: trove.nla.gov.au/about/create-something/using-api
    TROVE_API_KEY = os.getenv("TROVE_API_KEY", "")

    # DigitalNZ — free key: digitalnz.org/developers
    DIGITAL_NZ_API_KEY = os.getenv("DIGITAL_NZ_API_KEY", "")

    # Cache directory — use /tmp on Vercel (read-only filesystem), local .cache elsewhere
    _project_root = os.path.dirname(__file__)
    CACHE_DIR = (
        "/tmp/.curious_cache"
        if not os.access(_project_root, os.W_OK)
        else os.path.join(_project_root, ".cache")
    )

    # Guest search limit
    GUEST_SEARCH_LIMIT = 10
