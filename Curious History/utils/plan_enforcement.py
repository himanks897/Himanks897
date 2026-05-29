"""
plan_enforcement.py — Plan-based feature gating helpers and decorators.
Import these in app.py to enforce subscription limits on routes and API calls.
"""

from functools import wraps
from datetime import date
from flask import session, request, jsonify, redirect, url_for
from plans import Plan, PLAN_FEATURES, PLAN_LIMITS, PLAN_DISPLAY_NAMES


def get_current_plan() -> str:
    """
    Returns the current user's plan string.
    Logged-in users have their plan cached in session['user_plan'].
    Guests fall back to Plan.GUEST.
    """
    return session.get("user_plan", Plan.GUEST)


def has_feature(feature: str) -> bool:
    """True if the current user's plan includes the named feature."""
    plan = get_current_plan()
    return plan in PLAN_FEATURES.get(feature, [])


def get_min_plan_for_feature(feature: str) -> str:
    """Returns the lowest plan name that unlocks a feature, for error messages."""
    order = [Plan.EXPLORER, Plan.SCHOLAR, Plan.RESEARCHER]
    allowed = PLAN_FEATURES.get(feature, [])
    for p in order:
        if p in allowed:
            return p
    return Plan.RESEARCHER


def plan_required(feature: str):
    """
    Decorator that gates a route behind a plan feature.
    - API routes (path starts with /api/): returns JSON error.
    - Page routes: redirects to /pricing.
    Usage:
        @plan_required('quizzes')
        def api_quiz(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not has_feature(feature):
                required = get_min_plan_for_feature(feature)
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "upgrade_required",
                        "feature": feature,
                        "required_plan": required,
                        "required_plan_display": PLAN_DISPLAY_NAMES.get(required, required),
                        "current_plan": get_current_plan(),
                    }), 403
                return redirect(url_for("pricing"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def check_search_limit() -> tuple:
    """
    Checks and increments the daily search count for the current user.
    Guests use the Flask session; signed-in users use Supabase.
    Returns (allowed: bool, message: str, searches_used: int, daily_limit: int).
    """
    plan = get_current_plan()
    daily_limit = PLAN_LIMITS[plan]["searches_per_day"]
    user = session.get("user")

    if user:
        # Signed-in user: use Supabase for persistent counting
        from supabase.supabase_client import check_and_increment_search
        allowed, used, limit = check_and_increment_search(user["sub"], plan)
        if not allowed:
            plan_display = PLAN_DISPLAY_NAMES.get(plan, plan)
            msg = (
                f"You've used all {limit} daily searches on the {plan_display} plan. "
                f"Upgrade to get more searches."
            )
            return (False, msg, used, limit)
        return (True, "", used, limit)
    else:
        # Guest: use session-based counting
        today_str = date.today().isoformat()
        session.setdefault("guest_search_date", today_str)
        session.setdefault("guest_searches_used", 0)

        # Reset if date changed
        if session["guest_search_date"] != today_str:
            session["guest_search_date"] = today_str
            session["guest_searches_used"] = 0

        used = session["guest_searches_used"]
        if used >= daily_limit:
            msg = (
                f"You've used all {daily_limit} free guest searches for today. "
                f"Sign in and upgrade to Explorer for 20 searches/day."
            )
            return (False, msg, used, daily_limit)

        session["guest_searches_used"] = used + 1
        return (True, "", used + 1, daily_limit)


def get_plan_status() -> dict:
    """Returns a dict with current plan info — used by /api/plan-status and templates."""
    plan = get_current_plan()
    limits = PLAN_LIMITS[plan]
    user = session.get("user")

    if user:
        from supabase.supabase_client import get_user_plan
        record = get_user_plan(user["sub"])
        today_str = date.today().isoformat()
        searches_used = record["searches_today"] if record.get("last_search_date") == today_str else 0
    else:
        today_str = date.today().isoformat()
        if session.get("guest_search_date") == today_str:
            searches_used = session.get("guest_searches_used", 0)
        else:
            searches_used = 0

    return {
        "plan":            plan,
        "plan_display":    PLAN_DISPLAY_NAMES.get(plan, plan),
        "price_display":   limits["price_display"],
        "searches_used":   searches_used,
        "searches_limit":  limits["searches_per_day"],
        "features": {f: has_feature(f) for f in PLAN_FEATURES},
    }
