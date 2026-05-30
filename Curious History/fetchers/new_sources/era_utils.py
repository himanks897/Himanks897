"""
era_utils.py — Shared era-inference helper for new_sources fetchers.

Maps topic/query/region text to a human-readable era string used in
insert_record calls across all new_sources fetchers.
"""


def infer_era(text: str, fallback: str = "World History") -> str:
    """
    Return an era string by scanning text (topic / query / region combined).
    Call with the topic + region joined: infer_era(f"{topic} {region}")
    """
    t = text.lower()

    # Ancient world
    if any(k in t for k in ["ancient egypt", "pharaoh", "hieroglyph", "pyramid"]):
        return "Ancient Egypt"
    if any(k in t for k in ["ancient greece", "greek", "athens", "sparta", "olympia"]):
        return "Ancient Greece"
    if any(k in t for k in ["ancient rome", "roman empire", "roman republic", "caesar"]):
        return "Ancient Rome"
    if any(k in t for k in ["mesopotamia", "babylon", "sumerian", "assyrian", "cuneiform"]):
        return "Ancient Mesopotamia"
    if any(k in t for k in ["ancient", "bronze age", "neolithic", "prehistoric"]):
        return "Ancient History"

    # Scandinavian / Nordic — check before Medieval (vikings are often counted as both)
    if any(k in t for k in ["norway", "norwegian", "nordic", "scandinavia", "finland",
                             "swedish", "denmark", "iceland", "viking"]):
        return "Scandinavian / Nordic History"

    # Medieval
    if any(k in t for k in ["crusade", "medieval", "feudal", "byzantine",
                             "norman", "magna carta", "black death", "hundred years"]):
        return "Medieval History"

    # Islamic world
    if any(k in t for k in ["ottoman empire", "ottoman history"]):
        return "Ottoman Empire"
    if any(k in t for k in ["abbasid", "umayyad", "caliphate", "islamic golden age"]):
        return "Islamic Golden Age"
    if any(k in t for k in ["safavid", "mughal", "islamic", "caliphate"]):
        return "Islamic History"

    # East Asia
    if any(k in t for k in ["china", "ming dynasty", "qing dynasty", "tang", "song dynasty",
                             "chinese history"]):
        return "Chinese History"
    if any(k in t for k in ["japan", "meiji", "edo", "shogunate", "samurai", "feudal japan",
                             "tokugawa"]):
        return "Japanese History"
    if any(k in t for k in ["korea", "joseon"]):
        return "Korean History"
    if any(k in t for k in ["mongol", "genghis"]):
        return "Mongol Empire"

    # South / Southeast Asia
    if any(k in t for k in ["india", "mughal", "british india", "maharaja", "gandhi",
                             "independence india"]):
        return "Indian History"
    if any(k in t for k in ["southeast asia", "vietnam", "cambodia", "indonesia",
                             "malaysia", "philippines"]):
        return "Southeast Asian History"

    # Africa — more specific checks first
    if any(k in t for k in ["mali empire", "songhai", "timbuktu", "great zimbabwe",
                             "african kingdom", "nubia", "kush", "aksum"]):
        return "African History — Ancient & Medieval"
    if any(k in t for k in ["colonial africa", "scramble for africa", "africa colonialism",
                             "african colonialism", "african independence",
                             "decolonization africa", "decolonisation africa"]):
        return "African History — Colonial Era"
    if any(k in t for k in ["ethiopia", "nigeria", "ghana", "kenya", "south africa",
                             "congo", "africa history", "west africa", "east africa",
                             "north africa", "african history"]):
        return "African History"

    # Latin America
    if any(k in t for k in ["aztec", "inca", "maya", "pre-columbian"]):
        return "Pre-Columbian Americas"
    if any(k in t for k in ["latin american independence", "bolivar", "san martin"]):
        return "Latin American Independence"
    if any(k in t for k in ["mexico", "peru", "brazil", "argentina", "colombia",
                             "chile", "cuba", "caribbean", "latin america"]):
        return "Latin American History"

    # Europe
    if any(k in t for k in ["age of exploration", "age of discovery", "columbus",
                             "vasco da gama"]):
        return "Age of Exploration"
    if any(k in t for k in ["renaissance"]):
        return "European History — Renaissance"
    if any(k in t for k in ["reformation", "protestant", "luther"]):
        return "European History — Reformation"
    if any(k in t for k in ["french revolution", "napoleon"]):
        return "European History — Revolutionary Era"
    if any(k in t for k in ["industrial revolution"]):
        return "European History — Industrial Revolution"
    # Check WW2 BEFORE WW1 — "world war ii" contains "world war i"
    if any(k in t for k in ["world war ii", "world war 2", "ww2", "second world war",
                             "nazi", "holocaust"]):
        return "Second World War"
    if any(k in t for k in ["world war i", "world war 1", "great war", "ww1"]):
        return "First World War"
    if any(k in t for k in ["cold war", "soviet", "ussr", "communism"]):
        return "Cold War"
    if any(k in t for k in ["decolonization", "decolonisation"]):
        return "Decolonisation"
    if any(k in t for k in ["poland", "polish", "warsaw"]):
        return "Eastern European History — Poland"
    if any(k in t for k in ["romania", "romanian", "balkans", "bulgaria", "serbia"]):
        return "Eastern European History"
    if any(k in t for k in ["france", "french", "paris", "versailles", "gallic"]):
        return "French History"
    if any(k in t for k in ["atlantic slave trade", "slavery", "abolition"]):
        return "History of Slavery"

    # United States
    if any(k in t for k in ["american revolution", "civil war united states",
                             "united states history", "american history",
                             "native american", "slavery united states"]):
        return "American History"

    # Middle East
    if any(k in t for k in ["middle east", "arab", "iran", "iraq", "palestine",
                             "egypt history"]):
        return "Middle Eastern History"

    return fallback
