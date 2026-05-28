"""
fetcher_soas.py — SOAS University London Research Online (OAI-PMH)

SOAS (School of Oriental and African Studies) is the world's leading
institution for the study of Africa, Asia and the Middle East.
Their open-access repository contains thousands of academic papers,
theses, and digitised primary sources.

Endpoint : https://eprints.soas.ac.uk/cgi/oai2  (OAI-PMH 2.0)
Auth     : None required — standard OAI-PMH
License  : CC BY / Open Access — commercial use allowed per item
Docs     : https://eprints.soas.ac.uk/
Coverage : Africa, Middle East, South Asia, Southeast Asia, East Asia
"""

import time
import xml.etree.ElementTree as ET
import requests
from db import insert_record

SOURCE_NAME   = "SOAS University London"
OAI_ENDPOINT  = "https://eprints.soas.ac.uk/cgi/oai2"
HEADERS       = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

OAI_NS    = "http://www.openarchives.org/OAI/2.0/"
DC_NS     = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"

# OAI-PMH sets at SOAS (use set names to narrow harvest)
SETS = [
    "7",     # Africa Studies
    "8",     # Middle East / Islamic Studies
    "9",     # South Asia
    "10",    # Southeast Asia
    "11",    # East Asia
]

MAX_RECORDS_PER_SET = 100


def _dc(el, tag) -> str:
    """Extract first Dublin Core element value."""
    if el is None:
        return ""
    child = el.find(f"{{{DC_NS}}}{tag}")
    return (child.text or "").strip() if child is not None else ""


def _dc_all(el, tag) -> list:
    """Extract all Dublin Core element values for a tag."""
    if el is None:
        return []
    return [c.text.strip() for c in el.findall(f"{{{DC_NS}}}{tag}")
            if c.text and c.text.strip()]


def _fetch_set(conn: dict, source_id: int, set_id: str) -> int:
    inserted      = 0
    token         = None
    fetched_count = 0

    while fetched_count < MAX_RECORDS_PER_SET:
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        if set_id:
            params["set"] = set_id
        if token:
            # When resuming, only use the resumptionToken
            params = {"verb": "ListRecords", "resumptionToken": token}

        try:
            resp = requests.get(OAI_ENDPOINT, params=params,
                                headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                break

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError:
                break

            ns = OAI_NS
            list_records = root.find(f"{{{ns}}}ListRecords")
            if list_records is None:
                # Check for error
                error = root.find(f"{{{ns}}}error")
                if error is not None:
                    print(f"  [SOAS] OAI error set={set_id}: {error.text}")
                break

            for record in list_records.findall(f"{{{ns}}}record"):
                header = record.find(f"{{{ns}}}header")
                if header is not None:
                    status = header.get("status", "")
                    if status == "deleted":
                        continue

                metadata_el = record.find(f"{{{ns}}}metadata")
                if metadata_el is None:
                    continue

                dc = metadata_el.find(f"{{{OAI_DC_NS}}}dc")
                if dc is None:
                    continue

                title       = _dc(dc, "title")
                description = " ".join(_dc_all(dc, "description"))[:500]
                subjects    = _dc_all(dc, "subject")
                date        = _dc(dc, "date")
                creator     = _dc(dc, "creator")
                identifiers = _dc_all(dc, "identifier")
                # Prefer http URL as source
                src_url     = next((i for i in identifiers
                                    if i.startswith("http")), "")
                if not src_url and header is not None:
                    oai_id  = header.findtext(f"{{{ns}}}identifier") or ""
                    src_url = f"https://eprints.soas.ac.uk/{oai_id.split(':')[-1]}"

                if not title:
                    continue

                ext_id = src_url.split("/")[-1] if "/" in src_url else src_url

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     description or None,
                    "date_text":   date[:20],
                    "source_url":  src_url,
                    "external_id": f"soas-{ext_id}",
                    "record_type": "document",
                    "tags":        subjects[:8] + ["SOAS University"],
                    "region":      _infer_region(title, subjects),
                })
                if ok:
                    inserted      += 1
                    fetched_count += 1

            # Get resumption token
            rt_el = list_records.find(f"{{{ns}}}resumptionToken")
            token = (rt_el.text or "").strip() if rt_el is not None else ""
            if not token or fetched_count >= MAX_RECORDS_PER_SET:
                break

            time.sleep(1)

        except requests.RequestException as e:
            print(f"  [SOAS] Request error (set={set_id}): {e}")
            break
        except Exception as e:
            print(f"  [SOAS] Unexpected error (set={set_id}): {e}")
            break

    return inserted


def _infer_region(title: str, subjects: list) -> str:
    text = (title + " " + " ".join(subjects)).lower()
    if any(k in text for k in ["africa", "nigeria", "kenya", "ghana",
                                "ethiopia", "south africa", "congo", "egypt"]):
        return "Africa"
    if any(k in text for k in ["middle east", "arab", "islam", "iran", "iraq",
                                "turkey", "ottoman", "syria", "palestine"]):
        return "Middle East"
    if any(k in text for k in ["india", "pakistan", "bangladesh", "mughal",
                                "south asia", "ceylon", "sri lanka"]):
        return "South Asia"
    if any(k in text for k in ["china", "japan", "korea", "east asia"]):
        return "East Asia"
    if any(k in text for k in ["southeast asia", "vietnam", "indonesia",
                                "malaysia", "thailand", "burma"]):
        return "Southeast Asia"
    return "Asia"


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    for set_id in SETS:
        count = _fetch_set(conn, source_id, set_id)
        print(f"  [SOAS] Set {set_id}: +{count}")
        inserted += count
        time.sleep(2)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
