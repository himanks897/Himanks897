"""
fetcher_memoria_chilena.py — Memoria Chilena (Biblioteca Nacional de Chile)

Memoria Chilena is the digital library of the Biblioteca Nacional de Chile,
providing access to Chilean and Latin American historical documents,
photographs, maps, and primary sources.

Endpoint : OAI-PMH at http://www.memoriachilena.gob.cl/oai/request
Auth     : None required
License  : CC BY 4.0 — commercial use allowed
Docs     : https://www.memoriachilena.gob.cl/602/w3-channel.html
Coverage : Chile, Latin America, colonial history, indigenous history,
           19th–20th century South America
"""

import time
import xml.etree.ElementTree as ET
import requests
from db import insert_record

SOURCE_NAME  = "Memoria Chilena"
OAI_ENDPOINT = "http://www.memoriachilena.gob.cl/oai/request"
HEADERS      = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

OAI_NS    = "http://www.openarchives.org/OAI/2.0/"
DC_NS     = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"

MAX_RECORDS = 200   # cap to avoid overwhelming the server


def _dc(el, tag) -> str:
    if el is None:
        return ""
    child = el.find(f"{{{DC_NS}}}{tag}")
    return (child.text or "").strip() if child is not None else ""


def _dc_all(el, tag) -> list:
    if el is None:
        return []
    return [c.text.strip() for c in el.findall(f"{{{DC_NS}}}{tag}")
            if c.text and c.text.strip()]


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    token    = None

    while inserted < MAX_RECORDS:
        if token:
            params = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}

        try:
            resp = requests.get(OAI_ENDPOINT, params=params,
                                headers=HEADERS, timeout=30)

            if resp.status_code != 200:
                print(f"  [MC] HTTP {resp.status_code}")
                break

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                print(f"  [MC] XML parse error: {e}")
                break

            ns = OAI_NS
            # Check for OAI error
            error = root.find(f"{{{ns}}}error")
            if error is not None:
                print(f"  [MC] OAI error: {error.get('code')} — {error.text}")
                break

            list_records = root.find(f"{{{ns}}}ListRecords")
            if list_records is None:
                break

            for record in list_records.findall(f"{{{ns}}}record"):
                header = record.find(f"{{{ns}}}header")
                if header is not None and header.get("status") == "deleted":
                    continue

                metadata_el = record.find(f"{{{ns}}}metadata")
                if metadata_el is None:
                    continue

                dc = metadata_el.find(f"{{{OAI_DC_NS}}}dc")
                if dc is None:
                    continue

                title       = _dc(dc, "title")
                desc        = " ".join(_dc_all(dc, "description"))[:500]
                subjects    = _dc_all(dc, "subject")
                date_v      = _dc(dc, "date")
                creator     = _dc(dc, "creator")
                identifiers = _dc_all(dc, "identifier")
                src_url     = next((i for i in identifiers
                                    if i.startswith("http")), "")

                if not title:
                    continue
                if not src_url and header is not None:
                    oai_id = header.findtext(f"{{{ns}}}identifier") or ""
                    src_url = oai_id

                ext_id = src_url.split("/")[-1] if "/" in src_url else src_url

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     desc or None,
                    "date_text":   date_v[:20],
                    "region":      "Chile",
                    "source_url":  src_url,
                    "external_id": f"mc-{ext_id[:80]}",
                    "record_type": "document",
                    "tags":        subjects[:6] + ["Memoria Chilena", "Latin America"],
                })
                if ok:
                    inserted += 1
                    if inserted % 50 == 0:
                        print(f"  [MC] {inserted} records so far...")

                if inserted >= MAX_RECORDS:
                    break

            # Resumption token
            rt_el = list_records.find(f"{{{ns}}}resumptionToken")
            token = (rt_el.text or "").strip() if rt_el is not None else ""
            if not token or inserted >= MAX_RECORDS:
                break

            time.sleep(1.5)

        except requests.RequestException as e:
            print(f"  [MC] Request error: {e}")
            break
        except Exception as e:
            print(f"  [MC] Unexpected error: {e}")
            break

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
