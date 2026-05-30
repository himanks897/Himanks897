"""
fetcher_mercury.py — Project MERCURY: Roman Open Data

Auth     : None required — downloadable open datasets
License  : Open / CC — commercial use allowed
Docs     : https://projectmercury.eu/datasets/
Coverage : Ancient Rome — cities, roads, trade routes, provinces

Converts geographic and economic Roman datasets into readable English
records about Roman cities, provinces, roads, and trade networks.
No raw coordinate data or database codes are exposed to users.
"""

import re
import csv
import time
import json
import io
import requests
from db import insert_record

SOURCE_NAME = "Project Mercury — Roman Datasets"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

# Open datasets for Roman history — public domain / CC licensed
# Using reliable GitHub raw URLs from well-maintained scholarly repos
DATASETS = [
    {
        "url":    "https://raw.githubusercontent.com/sfsheath/roman-amphitheaters/master/roman-amphitheaters.geojson",
        "type":   "geojson",
        "era":    "Ancient Rome",
        "region": "Roman Empire",
        "topic":  "Roman amphitheatres",
        "ext_prefix": "mercury_amp",
    },
]

# Static Roman province data — built-in since no API available for some
ROMAN_PROVINCES = [
    ("Italia",          "Core province of the Roman Empire, comprising the Italian peninsula.",
     "Italy",           -27,   500),
    ("Britannia",       "Roman province covering most of modern England and Wales, conquered from 43 CE.",
     "Britain",         43,    410),
    ("Gallia",          "Roman province encompassing modern France and parts of Belgium, conquered by Julius Caesar (58–50 BCE).",
     "France",          -50,   475),
    ("Hispania",        "Roman provinces on the Iberian Peninsula — one of Rome's wealthiest regions.",
     "Spain",           -197,  409),
    ("Germania",        "Roman territories east of the Rhine; never fully conquered.",
     "Germany",         -12,   400),
    ("Aegyptus",        "Province of Egypt, Rome's breadbasket, acquired after Cleopatra's death (30 BCE).",
     "Egypt",           -30,   395),
    ("Syria",           "Rich Roman province including Antioch, major eastern trade hub.",
     "Syria",           -64,   395),
    ("Judaea",          "Province of Judaea, site of the Jewish-Roman Wars and destruction of Jerusalem (70 CE).",
     "Levant",          -63,   395),
    ("Africa Proconsularis", "Province incorporating former Carthaginian territory in modern Tunisia.",
     "North Africa",    -146,  429),
    ("Graecia / Achaea","Roman province covering mainland Greece from 146 BCE.",
     "Greece",          -146,  395),
    ("Macedonia",       "Roman province covering northern Greece and modern North Macedonia.",
     "Greece / Balkans",-148,  395),
    ("Asia (Province)", "Rich province of western Anatolia, centre of Hellenistic culture under Rome.",
     "Anatolia",        -133,  395),
    ("Dacia",           "Province north of the Danube, conquered by Trajan (106 CE), modern Romania.",
     "Romania",          106,  271),
    ("Mesopotamia",     "Short-lived eastern province briefly conquered by Trajan (116 CE) and Septimius Severus.",
     "Mesopotamia",      116,  395),
    ("Cappadocia",      "Province in central Anatolia, important frontier region against Parthia.",
     "Anatolia",        17,    395),
    ("Pannonia",        "Danubian province covering modern Hungary and parts of Austria.",
     "Central Europe",  -35,   395),
    ("Dalmatia",        "Adriatic coastal province covering modern Croatia and Bosnia.",
     "Balkans",         -27,   395),
    ("Noricum",         "Province covering modern Austria and part of Slovenia.",
     "Central Europe",  -15,   395),
    ("Cyrenaica",       "Province in modern Libya, part of the broader North African territories.",
     "North Africa",    -74,   395),
    ("Pontus et Bithynia","Province in north-western Anatolia along the Black Sea coast.",
     "Anatolia",        -74,   395),
]

# Key Roman cities with historical descriptions
ROMAN_CITIES = [
    ("Rome (Roma)",         "Capital of the Roman Republic and Empire. Home to the Senate, Forum Romanum, Colosseum, and the Pantheon. At its peak, Rome had a population of over one million.",
     "Italy",           -753),
    ("Carthage",            "Major Phoenician city destroyed by Rome in 146 BCE and rebuilt as a Roman provincial capital. Centre of North African Roman civilization.",
     "North Africa",    -814),
    ("Alexandria",          "Hellenistic city of Egypt, major intellectual centre with the Library of Alexandria. Became a key Roman city after 30 BCE.",
     "Egypt",           -331),
    ("Antioch",             "Capital of the Roman province of Syria, third-largest city of the Roman Empire after Rome and Alexandria.",
     "Syria",           -300),
    ("Ephesus",             "Major Roman city on the Aegean coast, home to the Temple of Artemis. An important commercial and religious centre.",
     "Anatolia",        -290),
    ("Pompeii",             "Roman city buried by the eruption of Mount Vesuvius in 79 CE, providing an extraordinarily well-preserved snapshot of Roman daily life.",
     "Italy",           -80),
    ("Londinium (London)",  "Roman capital of Britannia, founded around 50 CE after the Claudian invasion.",
     "Britain",          50),
    ("Lugdunum (Lyon)",     "Capital of Roman Gaul, birthplace of emperors Claudius and Caracalla.",
     "France",          -43),
    ("Mediolanum (Milan)",  "Important northern Italian city, later became co-capital of the Western Roman Empire.",
     "Italy",           -222),
    ("Ctesiphon",           "Parthian capital captured multiple times by Rome, near modern Baghdad.",
     "Mesopotamia",      -129),
    ("Caesarea Maritima",   "Roman capital of Judaea, built by Herod the Great. Major port and administrative centre.",
     "Levant",           -25),
    ("Palmyra",             "Desert trade city in Syria, a semi-autonomous kingdom under Rome until 273 CE.",
     "Syria",           100),
    ("Carthago Nova (Cartagena)", "Major Roman port city in Hispania, originally founded by Carthage, captured by Scipio Africanus in 209 BCE.",
     "Spain",           -209),
    ("Lugdunum Batavorum (Leiden)", "Roman frontier fort at the mouth of the Rhine river in Germania Inferior.",
     "Netherlands",     50),
    ("Augusta Treverorum (Trier)", "Major Roman city in Germania, briefly the western capital of the Roman Empire in the 3rd–4th centuries CE.",
     "Germany",         30),
    ("Aquincum (Budapest)", "Roman legionary fortress and provincial capital of Pannonia Inferior, on the Danube frontier.",
     "Hungary",         89),
    ("Gerasa (Jerash)",    "One of the best-preserved Roman provincial cities, featuring a colonnaded street, temples, and theatres in modern Jordan.",
     "Levant",          100),
]

# Key Roman battles and events
ROMAN_BATTLES = [
    ("Battle of Cannae (216 BCE)",
     "The Battle of Cannae was fought on 2 August 216 BCE during the Second Punic War, between the Roman Republic and the Carthaginian forces led by Hannibal Barca. Hannibal encircled a Roman army of 70,000–80,000 men using a double envelopment tactic and inflicted one of the worst defeats in Roman history, killing an estimated 47,000–70,000 Romans. It remains one of the most studied battles in military history.",
     "Italy", -216),
    ("Battle of Zama (202 BCE)",
     "The Battle of Zama ended the Second Punic War. Roman general Scipio Africanus defeated Hannibal of Carthage near Zama (in modern Tunisia). The victory established Roman dominance over the western Mediterranean. Hannibal, who had never lost a battle in Italy, was defeated partly because Scipio used a new formation that allowed Hannibal's war elephants to pass through without disrupting the Roman lines.",
     "North Africa", -202),
    ("Battle of Actium (31 BCE)",
     "The Battle of Actium (2 September 31 BCE) was the decisive confrontation between Octavian (later Augustus Caesar) and the combined forces of Mark Antony and Cleopatra VII of Egypt. Fought off the coast of Greece, Octavian's victory ended years of Roman civil war and made him the sole ruler of Rome, ushering in the Principate — the period of Roman emperors.",
     "Greece", -31),
    ("Sack of Rome by the Visigoths (410 CE)",
     "On 24 August 410 CE, the Visigoths under Alaric I sacked the city of Rome — the first time in 800 years that a foreign enemy had entered and pillaged the city. The three-day sack shocked the Roman world and is often used as a marker for the beginning of Rome's decline. The event prompted Saint Augustine to write The City of God, arguing that Rome's fall did not represent the defeat of Christianity.",
     "Italy", 410),
    ("Fall of the Western Roman Empire (476 CE)",
     "The Western Roman Empire formally ended on 4 September 476 CE when the Germanic chieftain Odoacer deposed the last Roman emperor Romulus Augustulus. This date is traditionally used by historians to mark the end of antiquity and the beginning of the Middle Ages, though Roman institutions, culture, and the Eastern Roman (Byzantine) Empire continued for centuries.",
     "Italy", 476),
]

# Key Roman emperors
ROMAN_EMPERORS = [
    ("Augustus Caesar — First Roman Emperor",
     "Augustus (63 BCE – 14 CE), born Gaius Octavius, was the first Roman emperor, reigning from 27 BCE until his death. After defeating Mark Antony and Cleopatra at the Battle of Actium (31 BCE), he transformed Rome from a republic into an empire while maintaining the appearance of republican institutions. His reign, the Pax Romana, was a period of relative peace and prosperity. He reformed the army, the tax system, and built extensively in Rome.",
     "Roman Empire", -27),
    ("Julius Caesar — Roman Dictator and Reformer",
     "Gaius Julius Caesar (100–44 BCE) was a Roman general, statesman, and author who played a critical role in transforming Rome from a republic into an empire. His conquest of Gaul (58–50 BCE) extended Roman territory to the Rhine and the English Channel. After crossing the Rubicon river in 49 BCE, he won the civil war and became dictator perpetuo. He was assassinated on the Ides of March (15 March 44 BCE) by senators including Brutus and Cassius.",
     "Roman Empire", -49),
    ("Hadrian — Builder of the Roman Wall",
     "Hadrian (76–138 CE) was Roman emperor from 117 to 138 CE. He is famous for consolidating the empire's borders rather than expanding them. Hadrian's Wall, built across northern Britain from 122 CE, marked the northern frontier of the Roman Empire. He also rebuilt the Pantheon in Rome, constructed Hadrian's Villa at Tivoli, and extensively travelled the provinces. He revoked Trajan's eastern conquests and adopted a defensive military strategy.",
     "Roman Empire", 117),
    ("Constantine I — First Christian Emperor",
     "Constantine I (272–337 CE) was the first Roman emperor to convert to Christianity. At the Battle of Milvian Bridge (312 CE), he attributed his victory to the Christian God. The Edict of Milan (313 CE) granted religious tolerance throughout the empire. Constantine moved the capital to Byzantium (renamed Constantinople) in 330 CE. His reign transformed Christianity from a persecuted minority religion into the dominant faith of the Roman world.",
     "Roman Empire", 306),
    ("Trajan — Rome's Greatest General",
     "Trajan (53–117 CE) was Roman emperor from 98 to 117 CE. He is remembered as one of Rome's greatest military emperors. His two Dacian campaigns (101–102 and 105–106 CE) are commemorated on Trajan's Column in Rome, a spiral relief carving depicting the campaigns in detail. He also conquered Nabataea (modern Jordan), Armenia, and briefly Mesopotamia, bringing the Roman Empire to its greatest territorial extent.",
     "Roman Empire", 98),
]


def _build_province_summary(name: str, desc: str, region: str, start: int) -> str:
    period = (f"{abs(start)} BCE" if start < 0 else f"{start} CE")
    return f"{name}: Roman province. {desc} Established circa {period}."


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # ── 1. Roman provinces (built-in, always reliable) ────────────────────────
    for (name, desc, region, start, end) in ROMAN_PROVINCES:
        ext_id = f"mercury_prov_{name.lower().replace(' ', '_')[:30]}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        title   = f"Roman Province of {name}"
        summary = _build_province_summary(name, desc, region, start)
        tags    = ["Roman Empire", "province", "ancient Rome", name, region]

        ok = insert_record(conn, source_id, {
            "title":           title,
            "summary":         summary,
            "record_type":     "document",
            "region":          region,
            "era":             "Ancient Rome",
            "date_text":       f"~{abs(start)} BCE" if start < 0 else f"~{start} CE",
            "date_year_start": start,
            "source_url":      "https://projectmercury.eu/datasets/",
            "external_id":     ext_id,
            "tags":            tags,
        })
        if ok:
            inserted += 1

    # ── 2. Roman cities (built-in) ─────────────────────────────────────────────
    for (name, desc, region, start) in ROMAN_CITIES:
        ext_id = f"mercury_city_{name.lower().replace(' ', '_')[:30]}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        title   = f"{name} — Roman City"
        summary = desc
        tags    = ["Roman Empire", "city", "ancient Rome", name, region]

        ok = insert_record(conn, source_id, {
            "title":           title,
            "summary":         summary,
            "record_type":     "place",
            "region":          region,
            "era":             "Ancient Rome",
            "date_year_start": start,
            "source_url":      "https://projectmercury.eu/datasets/",
            "external_id":     ext_id,
            "tags":            tags,
        })
        if ok:
            inserted += 1

    # ── 3. Roman battles (built-in) ────────────────────────────────────────────
    for (name, desc, region, year) in ROMAN_BATTLES:
        ext_id = f"mercury_battle_{name.lower().replace(' ', '_')[:30]}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        tags = ["Roman Empire", "battle", "ancient Rome", "military", region]
        ok = insert_record(conn, source_id, {
            "title":           name,
            "summary":         desc,
            "record_type":     "document",
            "region":          region,
            "era":             "Ancient Rome",
            "date_year_start": year,
            "source_url":      "https://projectmercury.eu/datasets/",
            "external_id":     ext_id,
            "tags":            tags,
        })
        if ok:
            inserted += 1

    # ── 4. Roman emperors (built-in) ───────────────────────────────────────────
    for (name, desc, region, year) in ROMAN_EMPERORS:
        ext_id = f"mercury_emperor_{name.lower().replace(' ', '_')[:30]}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        tags = ["Roman Empire", "emperor", "ancient Rome", "biography", region]
        ok = insert_record(conn, source_id, {
            "title":           name,
            "summary":         desc,
            "record_type":     "document",
            "region":          region,
            "era":             "Ancient Rome",
            "date_year_start": year,
            "source_url":      "https://projectmercury.eu/datasets/",
            "external_id":     ext_id,
            "tags":            tags,
        })
        if ok:
            inserted += 1

    # ── 5. GeoJSON datasets (amphitheatres etc.) ───────────────────────────────
    for dataset in DATASETS:
        try:
            resp = requests.get(dataset["url"], headers=HEADERS, timeout=25)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"  [Mercury] Dataset fetch error ({dataset['topic']}): {e}")
            time.sleep(1)
            continue

        features = data.get("features") if isinstance(data, dict) else data
        if not isinstance(features, list):
            continue

        for feat in features[:60]:
            props   = feat.get("properties") or {}
            ext_raw = (props.get("id") or props.get("name") or
                       props.get("title") or "")
            ext_id  = f"{dataset['ext_prefix']}_{str(ext_raw)[:30]}"
            if not ext_raw or ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            name_val = (props.get("label") or props.get("name") or
                        props.get("title") or dataset["topic"])
            title    = f"{str(name_val).strip()} — {dataset['topic']}"

            # Build readable summary from properties
            parts = []
            if props.get("dating"):
                parts.append(f"Dating: {props['dating']}.")
            if props.get("summary") or props.get("description"):
                parts.append(props.get("summary") or props.get("description"))
            if props.get("country"):
                parts.append(f"Location: {props['country']}.")
            if not parts:
                parts.append(f"{name_val}: a {dataset['topic'].rstrip('s')} of the Roman Empire.")

            summary = " ".join(str(p) for p in parts)[:600]
            tags    = ["Roman Empire", "ancient Rome", dataset["topic"],
                       dataset["region"]]

            ok = insert_record(conn, source_id, {
                "title":       title,
                "summary":     summary,
                "record_type": "place",
                "region":      dataset["region"],
                "era":         dataset["era"],
                "source_url":  dataset["url"],
                "external_id": ext_id,
                "tags":        tags,
            })
            if ok:
                inserted += 1

        time.sleep(0.5)

    print(f"  [Mercury] {inserted} Roman records inserted")
    return inserted
