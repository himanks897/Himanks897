"""
plans.py — Single source of truth for all subscription plan constants.
Import Plan and PLAN_LIMITS / PLAN_FEATURES everywhere — never use raw strings.
"""


class Plan:
    GUEST      = 'guest'
    EXPLORER   = 'explorer'
    SCHOLAR    = 'scholar'
    RESEARCHER = 'researcher'


# Per-plan daily search limits and pricing
PLAN_LIMITS = {
    Plan.GUEST:      {'searches_per_day': 3,   'price': 0,    'price_display': 'Free'},
    Plan.EXPLORER:   {'searches_per_day': 20,  'price': 99,   'price_display': '₹99/month'},
    Plan.SCHOLAR:    {'searches_per_day': 50,  'price': 999,  'price_display': '₹999/month'},
    Plan.RESEARCHER: {'searches_per_day': 150, 'price': 4999, 'price_display': '₹4,999/month'},
}

# Feature gates — list the plans that have access to each feature
PLAN_FEATURES = {
    'summary_200':     [Plan.EXPLORER, Plan.SCHOLAR, Plan.RESEARCHER],
    'summary_500':     [Plan.SCHOLAR, Plan.RESEARCHER],
    'summary_1000':    [Plan.SCHOLAR, Plan.RESEARCHER],
    'ai_timelines':    [Plan.SCHOLAR, Plan.RESEARCHER],
    'images_maps':     [Plan.EXPLORER, Plan.SCHOLAR, Plan.RESEARCHER],
    'bookmarks':       [Plan.SCHOLAR, Plan.RESEARCHER],
    'citations_apa':   [Plan.SCHOLAR, Plan.RESEARCHER],
    'citations_mla':   [Plan.SCHOLAR, Plan.RESEARCHER],
    'dark_mode':       [Plan.SCHOLAR, Plan.RESEARCHER],
    'quizzes':         [Plan.RESEARCHER],
    'comparison_tool': [Plan.RESEARCHER],
    'surprise_me':     [Plan.EXPLORER, Plan.SCHOLAR, Plan.RESEARCHER],
}

# Human-readable plan display names
PLAN_DISPLAY_NAMES = {
    Plan.GUEST:      'Guest',
    Plan.EXPLORER:   'Explorer',
    Plan.SCHOLAR:    'Scholar',
    Plan.RESEARCHER: 'Researcher',
}
