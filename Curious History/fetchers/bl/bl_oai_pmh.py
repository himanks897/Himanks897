"""
bl_oai_pmh.py — British Library Research Repository via OAI-PMH protocol.

Harvests Dublin Core metadata records from bl.iro.bl.uk.
Handles pagination via resumptionToken, capped at 20 pages.
Token saved to bl_oai_token.txt for resumable runs.

Source: https://bl.iro.bl.uk/catalog/oai
Auth:   None (open OAI-PMH endpoint)
"""

import os
import re
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from db import insert_record

SOURCE_NAME = "BL Research Repository (OAI-PMH)"
OAI_BASE    = "https://bl.iro.bl.uk/catalog/oai"
TOKEN_FILE  = "./bl_oai_token.txt"
PAGE_CAP    = 20

# ── XML namespace map ─────────────────────────────────────────────────────────
NS = {
    "oai":    "http://www.openarchives.org/OAI/2.0/",
    "dc":     "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

# ── Licences permitted for insertion ─────────────────────────────────────────
_ALLOWED_LICENCE_PATTERNS = [
    "cc0", "cc-0", "creativecommons.org/publicdomain",
    "cc by", "cc-by", "creativecommons.org/licenses/by/",
    "cc by-sa", "creativecommons.org/licenses/by-sa/",
    "no known copyright", "noknowright",
    "public domain",
]
_BLOCKED_LICENCE_PATTERNS = ["nc", "noncommercial", "nd", "noderivat"]


def _allowed_licence(rights_text: str) -> bool:
    """Return True if the rights text permits commercial/derivative use."""
    if not rights_text:
        return True   # no rights declared → assume open
    low = rights_text.lower()
    for pat in _BLOCKED_LICENCE_PATTERNS:
        if pat in low:
            return False
    return True


def _get_dc(dc_elem, field: str, ns: dict) -> str:
    """Return the text of the first matching DC child element, or ''."""
    el = dc_elem.find(f"dc:{field}", ns)
    return (el.text or "").strip() if el is not None else ""


def _get_dc_all(dc_elem, field: str, ns: dict) -> list:
    """Return a list of text values for ALL matching DC child elements."""
    return [
        (el.text or "").strip()
        for el in dc_elem.findall(f"dc:{field}", ns)
        if el.text and el.text.strip()
    ]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _ask_resume() -> str | None:
    """
    If a saved token file exists, ask the user whether to resume.
    Returns the token string to start from, or None to start fresh.
    Non-interactive environments automatically resume.
    """
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if not token:
            return None
        # In non-interactive mode (no TTY), always resume
        if not os.isatty(0):
            print(f"  [OAI-PMH] Resuming from saved token: {token[:40]}...")
            return token
        answer = input(f"  [OAI-PMH] Saved token found. Resume from last position? (y/n): ").strip().lower()
        if answer == "y":
            return token
    except Exception:
        pass
    return None


def fetch(conn: dict, source_id: int) -> int:
    inserted   = 0
    page_count = 0

    # ── PHASE 1: Discover available sets ─────────────────────────────────────
    try:
        resp = requests.get(
            OAI_BASE,
            params={"verb": "ListSets"},
            timeout=15,
        )
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            sets = root.findall(".//oai:set", NS)
            if sets:
                print(f"  [OAI-PMH] Available sets ({len(sets)}):")
                for s in sets[:10]:
                    spec = s.findtext("oai:setSpec", namespaces=NS) or ""
                    name = s.findtext("oai:setName",  namespaces=NS) or ""
                    print(f"    - {spec}: {name}")
                if len(sets) > 10:
                    print(f"    ... and {len(sets) - 10} more")
        else:
            print(f"  [WARN] ListSets returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [WARN] Could not list OAI-PMH sets: {e}")

    # ── PHASE 2: Harvest records ──────────────────────────────────────────────
    resume_token = _ask_resume()

    if resume_token:
        params = {"verb": "ListRecords", "resumptionToken": resume_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}

    while True:
        if page_count >= PAGE_CAP:
            # Save token for next run
            if resume_token:
                with open(TOKEN_FILE, "w") as f:
                    f.write(resume_token)
                print(f"  [WARN] OAI-PMH page cap reached ({PAGE_CAP} pages).")
                print(f"  Token saved to {TOKEN_FILE} — re-run to continue.")
            break

        try:
            resp = requests.get(OAI_BASE, params=params, timeout=15)
        except requests.RequestException as e:
            print(f"  [ERROR] OAI-PMH request failed: {e}")
            break

        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code} from OAI-PMH endpoint. Stopping.")
            break

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            print(f"  [ERROR] OAI-PMH XML parse error on page {page_count + 1}: {e}")
            break

        # ── Process records on this page ──────────────────────────────────────
        page_inserted = 0
        for record_el in root.findall(".//oai:record", NS):
            try:
                # External identifier from header
                header   = record_el.find("oai:header", NS)
                ext_id   = ""
                if header is not None:
                    id_el  = header.find("oai:identifier", NS)
                    ext_id = (id_el.text or "").strip() if id_el is not None else ""

                # Skip deleted records
                status = header.get("status", "") if header is not None else ""
                if status == "deleted":
                    continue

                # Locate dc element
                metadata = record_el.find("oai:metadata", NS)
                if metadata is None:
                    continue
                dc = metadata.find("oai_dc:dc", NS)
                if dc is None:
                    continue

                # ── Field extraction ──────────────────────────────────────────
                title       = _get_dc(dc, "title",       NS)
                if not title.strip():
                    continue

                description = _get_dc(dc, "description", NS)
                summary     = _strip_html(description)[:800]

                date_text   = _get_dc(dc, "date",        NS)
                coverage    = _get_dc(dc, "coverage",    NS)
                rec_type    = _get_dc(dc, "type",        NS).lower() or "document"
                rights_raw  = _get_dc(dc, "rights",      NS)

                # Skip non-textual types
                if any(t in rec_type for t in ("image", "audio", "video", "dataset")):
                    continue

                # Commercial safety check
                if not _allowed_licence(rights_raw):
                    print(f"  [SKIP] NC/ND licence: {title[:60]}")
                    continue

                # All dc:identifier values — prefer the HTTP URL form
                identifiers = _get_dc_all(dc, "identifier", NS)
                source_url  = next(
                    (i for i in identifiers if i.startswith("http")), ""
                )

                subjects    = _get_dc_all(dc, "subject", NS)
                tags        = json.dumps(subjects[:15])  # cap at 15 subjects

                ok = insert_record(conn, source_id, {
                    "title":       title,
                    "summary":     summary,
                    "date_text":   date_text,
                    "region":      coverage,
                    "tags":        tags,
                    "source_url":  source_url,
                    "external_id": ext_id,
                    "record_type": rec_type if rec_type != "text" else "document",
                    "era":         None,
                })
                if ok:
                    inserted      += 1
                    page_inserted += 1

            except Exception as e:
                print(f"  [WARN] Skipping OAI record due to error: {e}")
                continue

        page_count += 1
        print(f"  [OAI-PMH] Page {page_count}: {page_inserted} inserted "
              f"(total so far: {inserted})")

        # ── Find resumptionToken for next page ────────────────────────────────
        token_el     = root.find(".//oai:resumptionToken", NS)
        resume_token = (token_el.text or "").strip() if token_el is not None else ""

        if not resume_token:
            # Clean up saved token file — we completed harvesting
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
                print("  [OAI-PMH] Harvest complete. Token file removed.")
            break

        params = {"verb": "ListRecords", "resumptionToken": resume_token}
        time.sleep(1)  # be polite to the server

    if inserted == 0:
        print("  [DIAG] 0 records inserted from OAI-PMH.")
        print("  Check bl.iro.bl.uk is reachable and returning valid OAI-PMH XML.")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
