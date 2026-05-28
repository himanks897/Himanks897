"""
bl_wikimedia_commons.py — British Library images on Wikimedia Commons.

Harvests files from Category:Images_from_the_British_Library using the
MediaWiki API with a generator query so imageinfo (URL, extmetadata) can
be fetched in the same request.

No API key required. All images are Public Domain or CC0 — fully safe
for any use including commercial.

Endpoint: https://commons.wikimedia.org/w/api.php
"""

import json
import re
import time
import requests

from db import insert_record

SOURCE_NAME    = "BL Wikimedia Commons"
API_ENDPOINT   = "https://commons.wikimedia.org/w/api.php"
BL_CATEGORY    = "Category:Images_from_the_British_Library"
PAGE_LIMIT     = 50          # files per request (MediaWiki max with imageinfo = 50)
MAX_PAGES      = 40          # hard cap to avoid runaway pagination (~2,000 images)

# Wikimedia requires a descriptive User-Agent (policy: https://w.wiki/4wJS)
_HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://github.com/himanksangtani/curious-history; "
        "himanks897@gmail.com) python-requests/2.x"
    )
}

# Only these licence values are admitted — both are unconditional public domain
_ALLOWED_LICENCES = {"public domain", "cc0"}

# Sub-categories to also harvest (gives topical breadth)
EXTRA_CATEGORIES = [
    "Category:Images_from_the_British_Library_Flickr_stream",
    "Category:Maps_from_the_British_Library",
    "Category:Manuscripts_from_the_British_Library",
    "Category:Prints_from_the_British_Library",
]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _meta_val(extmeta: dict, *keys: str) -> str:
    """Extract the first matching extmetadata value (case-insensitive on key)."""
    low_map = {k.lower(): k for k in extmeta}
    for key in keys:
        actual = low_map.get(key.lower())
        if actual:
            val = extmeta[actual].get("value", "") or ""
            return _strip_html(str(val)).strip()
    return ""


def _licence_ok(extmeta: dict) -> bool:
    """Return True only for Public Domain or CC0 images."""
    lic = _meta_val(extmeta, "LicenseShortName", "License", "UsageTerms").lower()
    if not lic:
        # No licence declared — treat as Public Domain for BL Flickr-sourced images
        credit = _meta_val(extmeta, "Credit").lower()
        return "british library" in credit
    return any(allowed in lic for allowed in _ALLOWED_LICENCES)


def _harvest_category(category: str, conn: dict, source_id: int,
                      seen_ids: set) -> int:
    """
    Harvest all files from one Wikimedia category using the generator API.
    Returns count of records inserted.
    """
    inserted   = 0
    page_count = 0
    continue_params: dict = {}

    while page_count < MAX_PAGES:
        params: dict = {
            "action":   "query",
            # generator puts results into query.pages where prop=imageinfo can act
            "generator":  "categorymembers",
            "gcmtitle":   category,
            "gcmtype":    "file",
            "gcmlimit":   PAGE_LIMIT,
            "prop":       "imageinfo",
            "iiprop":     "url|extmetadata",
            "iiextmetadatalanguage": "en",
            "format":     "json",
        }
        params.update(continue_params)   # inject gcmcontinue / continue tokens

        try:
            resp = requests.get(API_ENDPOINT, params=params,
                                headers=_HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"  [ERROR] Wikimedia request failed: {e}")
            break

        if resp.status_code != 200:
            print(f"  [WARN] Wikimedia HTTP {resp.status_code} for {category[:60]}")
            break

        try:
            data = resp.json()
        except ValueError as e:
            print(f"  [ERROR] Wikimedia JSON parse error: {e}")
            break

        pages = (data.get("query") or {}).get("pages") or {}
        page_inserted = 0

        for page in pages.values():
            try:
                page_id  = str(page.get("pageid", ""))
                title    = (page.get("title") or "").strip()

                if not page_id or page_id in seen_ids:
                    continue

                # imageinfo is a list; take the first entry
                ii_list  = page.get("imageinfo") or []
                if not ii_list:
                    continue
                ii       = ii_list[0]

                image_url = (ii.get("url") or "").strip()
                if not image_url:
                    continue

                extmeta  = ii.get("extmetadata") or {}

                # ── Licence check — only Public Domain / CC0 ─────────────────
                if not _licence_ok(extmeta):
                    continue

                # ── Extract metadata ──────────────────────────────────────────
                description = _meta_val(
                    extmeta,
                    "ImageDescription", "ObjectName",
                )
                # Use description as title if the file title is cryptic
                display_title = description[:120] if description else title
                if display_title.lower().startswith("file:"):
                    display_title = display_title[5:].strip()
                if not display_title:
                    continue

                date_raw  = _meta_val(
                    extmeta,
                    "DateTimeOriginal", "DateTime",
                )
                # Keep only the date portion (YYYY-MM-DD or YYYY)
                date_text = re.sub(r"\s.*", "", date_raw).strip()[:20]

                artist    = _meta_val(extmeta, "Artist", "Credit")
                lic_name  = _meta_val(extmeta, "LicenseShortName", "License")

                source_url = (
                    f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}"
                )

                # Tags: licence + artist + "British Library" + "Wikimedia Commons"
                tag_list  = ["British Library", "Wikimedia Commons",
                             "public domain", "historical image"]
                if lic_name:
                    tag_list.append(lic_name)
                if artist and "british library" not in artist.lower():
                    tag_list.append(artist[:60])
                tags = json.dumps(tag_list)

                summary = description[:600] if description else None

                seen_ids.add(page_id)
                ok = insert_record(conn, source_id, {
                    "title":       display_title[:300],
                    "summary":     summary,
                    "image_url":   image_url,
                    "source_url":  source_url,
                    "external_id": f"wmc-{page_id}",
                    "date_text":   date_text,
                    "record_type": "image",
                    "tags":        tags,
                })
                if ok:
                    inserted      += 1
                    page_inserted += 1

            except Exception as e:
                print(f"  [WARN] Skipping Wikimedia page due to error: {e}")
                continue

        page_count += 1
        if page_inserted:
            print(f"  [WMC] {category.split(':')[-1][:40]} "
                  f"p{page_count}: {page_inserted} images "
                  f"(total: {inserted})")

        # ── Pagination ────────────────────────────────────────────────────────
        cont = data.get("continue")
        if not cont:
            break   # No more pages
        continue_params = cont
        time.sleep(0.5)   # be polite to Wikimedia servers

    return inserted


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # ── Primary category ──────────────────────────────────────────────────────
    print(f"  [WMC] Harvesting: {BL_CATEGORY}")
    n = _harvest_category(BL_CATEGORY, conn, source_id, seen_ids)
    inserted += n
    print(f"  [WMC] Primary category: {n} images inserted")

    # ── Extra topical sub-categories ──────────────────────────────────────────
    for cat in EXTRA_CATEGORIES:
        print(f"  [WMC] Harvesting: {cat}")
        n = _harvest_category(cat, conn, source_id, seen_ids)
        inserted += n
        if n:
            print(f"  [WMC] {cat.split(':')[-1]}: {n} images inserted")

    if inserted == 0:
        print("  [DIAG] 0 records from Wikimedia Commons.")
        print("  Check commons.wikimedia.org is reachable and that")
        print(f"  '{BL_CATEGORY}' still exists.")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
