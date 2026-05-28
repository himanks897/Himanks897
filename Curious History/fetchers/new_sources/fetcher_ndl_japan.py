"""
fetcher_ndl_japan.py — National Diet Library Japan (NDL)

Endpoint : https://iss.ndl.go.jp/api/opensearch  (OpenSearch / RSS)
Auth     : None required
License  : NDL Open Data License — commercial use allowed
Docs     : https://iss.ndl.go.jp/information/api/
Coverage : Japan, Japanese history, East Asian history
"""

import time
import xml.etree.ElementTree as ET
import requests
from db import insert_record

SOURCE_NAME = "National Diet Library Japan"
BASE_URL    = "https://iss.ndl.go.jp/api/opensearch"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

TOPICS = [
    "Japanese history feudal Edo Meiji",
    "Samurai Japan history",
    "Meiji Restoration Japan",
    "Japanese colonial history",
    "World War II Japan Pacific",
    "Ancient Japan Nara Heian",
    "China history dynasty Tang Song",
    "Korean history Joseon dynasty",
    "Silk Road East Asia history",
    "Buddhism history Asia",
    "Mongol Empire China",
    "Ming dynasty China history",
    "Japanese Shogunate history",
    "Asia Pacific history colonialism",
    "Hiroshima Nagasaki history",
]

_NS = {
    "rss":  "",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}


def _text(el, tag) -> str:
    if el is None:
        return ""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    for topic in TOPICS:
        try:
            resp = requests.get(
                BASE_URL,
                headers=HEADERS,
                params={"q": topic, "cnt": 20, "type": 1, "mediatype": 1},
                timeout=20,
            )
            if resp.status_code != 200:
                print(f"  [NDL] HTTP {resp.status_code} for '{topic}'")
                time.sleep(1)
                continue

            # NDL returns RSS/XML
            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                print(f"  [NDL] XML parse error for '{topic}': {e}")
                continue

            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                title   = _text(item, "title")
                link    = _text(item, "link")
                desc    = _text(item, "description")
                creator = _text(item, "{http://purl.org/dc/elements/1.1/}creator")
                date    = _text(item, "{http://purl.org/dc/elements/1.1/}date")
                subject = _text(item, "{http://purl.org/dc/elements/1.1/}subject")

                if not title or not link:
                    continue

                ext_id = link.split("/")[-1] if "/" in link else link

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     desc[:500] if desc else None,
                    "date_text":   date[:20],
                    "region":      "Japan",
                    "source_url":  link,
                    "external_id": f"ndl-{ext_id}",
                    "record_type": "document",
                    "tags":        [t.strip() for t in subject.split(";") if t.strip()][:8]
                                   + ["National Diet Library Japan", topic[:40]],
                })
                if ok:
                    inserted += 1

            time.sleep(0.6)

        except Exception as e:
            print(f"  [NDL] Error for '{topic}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
