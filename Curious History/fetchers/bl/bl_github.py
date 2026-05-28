"""
bl_github.py — British Library Georeferencer Research Repository (GitHub).

Uses the GitHub Contents API to download README and source files from the
BL Georeferencer repository, inserting them as research methodology records.

The repository (britishlibrary/georeferencer_research_repo) contains Python
tools for georeferencing historical BL maps — it describes the georeferencer
workflow that produced the BL map collection on bl.iro.bl.uk.

Source: https://github.com/britishlibrary/georeferencer_research_repo
Auth:   None (public repo — GitHub allows 60 req/hr unauthenticated)
"""

import os
import json
import time
import requests

from db import insert_record

SOURCE_NAME = "BL GitHub Georeferencer"
REPO_OWNER  = "britishlibrary"
REPO_NAME   = "georeferencer_research_repo"
API_BASE    = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
RAW_BASE    = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/master"

# GitHub headers (unauthenticated but polite)
GH_HEADERS  = {"Accept": "application/vnd.github+json",
               "User-Agent": "CuriousHistory-pipeline/1.0"}

# Textual file types we can meaningfully extract content from
_TEXT_EXTENSIONS = {".md", ".py", ".txt", ".rst", ".ipynb", ".csv",
                    ".json", ".yaml", ".yml"}
_SKIP_NAMES      = {"test", "sample", "example", ".gitignore"}
_MAX_CONTENT     = 1500   # chars to store per file


def _get_repo_tree() -> list[dict]:
    """
    Use GitHub Trees API to list all files in the repo (recursive).
    Returns list of {path, size, download_url} for text-type files.
    """
    try:
        resp = requests.get(
            f"{API_BASE}/git/trees/HEAD",
            params={"recursive": "1"},
            headers=GH_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            files = []
            for item in resp.json().get("tree", []):
                if item.get("type") != "blob":
                    continue
                path = item.get("path", "")
                ext  = os.path.splitext(path)[1].lower()
                if ext not in _TEXT_EXTENSIONS:
                    continue
                fname = os.path.basename(path).lower()
                if any(s in fname for s in _SKIP_NAMES):
                    continue
                files.append({
                    "path":         path,
                    "size":         item.get("size", 0),
                    "download_url": f"{RAW_BASE}/{path}",
                })
            return files
        else:
            print(f"  [WARN] GitHub tree API: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [WARN] GitHub tree API failed: {e}")
    return []


def _get_repo_meta() -> dict:
    """Fetch repo-level metadata (description, topics, stars)."""
    try:
        resp = requests.get(API_BASE, headers=GH_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _summarise_python(code: str) -> str:
    """
    Extract the module docstring from a Python file as a summary.
    Falls back to first non-empty non-comment lines.
    """
    lines = code.splitlines()
    # Look for triple-quoted docstring at module level
    in_doc = False
    doc_lines = []
    for line in lines[:30]:
        stripped = line.strip()
        if not in_doc:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_doc = True
                inner = stripped[3:]
                if inner.endswith('"""') or inner.endswith("'''"):
                    return inner[:-3].strip()
                doc_lines.append(inner)
                continue
        else:
            if stripped.endswith('"""') or stripped.endswith("'''"):
                doc_lines.append(stripped[:-3])
                return " ".join(doc_lines).strip()
            doc_lines.append(stripped)

    # Fallback: first meaningful comment or code line
    for line in lines[:10]:
        s = line.strip().lstrip("#").strip()
        if s and len(s) > 10:
            return s[:200]
    return ""


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    # ── Step 1: Get repo metadata ─────────────────────────────────────────────
    meta      = _get_repo_meta()
    repo_desc = meta.get("description", "") or ""
    repo_url  = meta.get("html_url", f"https://github.com/{REPO_OWNER}/{REPO_NAME}")
    repo_name = meta.get("full_name", f"{REPO_OWNER}/{REPO_NAME}")

    print(f"  [GitHub] Repo: {repo_name}")
    if repo_desc:
        print(f"  [GitHub] Description: {repo_desc}")

    # ── Insert one record for the repo itself ─────────────────────────────────
    ok = insert_record(conn, source_id, {
        "title":       "BL Georeferencer: Research Repository Overview",
        "summary":     (repo_desc or
                        "British Library tool repository for georeferencing "
                        "historical maps and preparing them for the BL research "
                        "repository. Produces georeferenced GeoTIFF map images "
                        "from the BL digitised maps collection."),
        "source_url":  repo_url,
        "external_id": f"gh-{REPO_OWNER}-{REPO_NAME}-repo",
        "record_type": "document",
        "era":         "Multi-Era",
        "tags":        json.dumps(["georeferenced", "historical maps",
                                   "British Library", "open data", "GitHub"]),
    })
    if ok:
        inserted += 1

    # ── Step 2: List all text files ───────────────────────────────────────────
    files = _get_repo_tree()
    print(f"  [GitHub] Found {len(files)} text file(s) in repo")

    if not files:
        # If no files found, insert a minimal repo description
        print("  [GitHub] Repo has no additional text files — repository record inserted.")
        print(f"  [{SOURCE_NAME}] {inserted} records inserted")
        return inserted

    # ── Step 3: Download and insert each text file ────────────────────────────
    for file_info in files:
        path     = file_info["path"]
        dl_url   = file_info["download_url"]
        filename = os.path.basename(path)
        ext      = os.path.splitext(filename)[1].lower()

        try:
            resp = requests.get(dl_url, headers=GH_HEADERS, timeout=15)
            time.sleep(0.2)
            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code}: {filename}")
                continue

            content = resp.text

            # Build record fields from file type
            if ext == ".md":
                # Markdown: first heading as title, first paragraph as summary
                lines   = content.splitlines()
                title   = next((l.lstrip("#").strip() for l in lines
                                if l.strip() and l.startswith("#")),
                               f"BL Georeferencer: {filename}")
                summary = " ".join(
                    l.strip() for l in lines
                    if l.strip() and not l.startswith("#")
                )[:_MAX_CONTENT]

            elif ext == ".py":
                title   = f"BL Georeferencer: {filename}"
                summary = _summarise_python(content)
                if not summary:
                    summary = content[:_MAX_CONTENT]

            elif ext in (".ipynb",):
                # Jupyter notebook: extract first markdown cell text
                try:
                    nb    = json.loads(content)
                    cells = nb.get("cells", [])
                    text  = " ".join(
                        "".join(c.get("source", []))
                        for c in cells if c.get("cell_type") == "markdown"
                    )
                    title   = f"BL Georeferencer: {filename}"
                    summary = text[:_MAX_CONTENT]
                except Exception:
                    title   = f"BL Georeferencer: {filename}"
                    summary = content[:_MAX_CONTENT]

            else:
                title   = f"BL Georeferencer: {filename}"
                summary = content[:_MAX_CONTENT]

            if not summary.strip():
                continue

            ok = insert_record(conn, source_id, {
                "title":       title[:300],
                "summary":     summary[:800],
                "source_url":  f"{repo_url}/blob/master/{path}",
                "external_id": f"gh-{REPO_OWNER}-{REPO_NAME}-{path.replace('/','_')}",
                "record_type": "document",
                "era":         "Multi-Era",
                "tags":        json.dumps(["georeferenced", "historical maps",
                                           "British Library", "methodology",
                                           ext.lstrip(".")]),
            })
            if ok:
                inserted += 1
                print(f"  [GitHub] Inserted: {filename}")

        except Exception as e:
            print(f"  [WARN] Error processing {filename}: {e}")
            continue

    if inserted == 0:
        print("  [DIAG] 0 records from GitHub Georeferencer.")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
