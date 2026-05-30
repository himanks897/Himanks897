"""
audit_pipeline.py — Curious History Database Quality Auditor

Audits every formatted history essay entry in the database against the
Curious History Content Standard using the Claude API.

Usage:
    python audit_pipeline.py                  # audit all records
    python audit_pipeline.py --sample 50      # audit a random sample
    python audit_pipeline.py --source "CDLI"  # audit one source only

Output:
    audit_results.json              — per-entry JSON audit results
    CURIOUS_HISTORY_AUDIT_REPORT.md — final report

Requirements:
    pip install anthropic
    ANTHROPIC_API_KEY must be set in .env
"""

import os
import sys
import json
import time
import random
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL             = "claude-sonnet-4-6"          # Sonnet 4.6 — fast + accurate
MAX_TOKENS_AUDIT  = 1500                         # per audit call (compact JSON)
MAX_TOKENS_REPORT = 4096                         # final synthesis report
DELAY_BETWEEN     = 0.3                          # seconds between API calls
OUTPUT_FILE       = "audit_results.json"
REPORT_FILE       = "CURIOUS_HISTORY_AUDIT_REPORT.md"
DB_PATH           = os.path.join(os.path.dirname(__file__), "curious_history.json")

# ── SYSTEM PROMPTS ────────────────────────────────────────────────────────────

AUDITOR_SYSTEM_PROMPT = """You are the Curious History Database Auditor.

Your job is to examine one formatted history essay entry and score it against the
Curious History Content Standard. You return ONLY valid JSON — nothing else.
No preamble. No explanation outside the JSON object.

═══ CONTENT STANDARD (what every entry must satisfy) ═══

STRUCTURE CHECKS (each scored PASS / FAIL / PARTIAL):
  S1 — Has a clear, specific, historically accurate Title (not generic)
  S2 — Introduction present with: hook, context (2–3 sentences), thesis statement, signpost
  S3 — Minimum 3 body paragraphs present
  S4 — Each body paragraph follows PEEL: Point → Evidence → Explanation → Link
  S5 — Each body paragraph covers exactly ONE argument (no merged themes)
  S6 — Counter-argument paragraph present where source material allows
  S7 — Conclusion present with: restated thesis, argument summary, final judgement
  S8 — No new evidence introduced in the conclusion
  S9 — Section headers formatted correctly (## Introduction, ## Body — [Theme], ## Conclusion)

FORMAT CHECKS:
  F1 — All key historical terms, names, dates, events, treaties, places are bolded (**term**)
  F2 — Essay written entirely in past tense
  F3 — Essay written in third person (no "I", "we", "you")
  F4 — No vague language ("things", "stuff", "very important", "a lot of")
  F5 — Causation language used ("led to", "as a consequence of", "a contributing factor was")
  F6 — Body paragraphs are 150–250 words each
  F7 — Introduction and Conclusion are 100–150 words each
  F8 — No bullet-point lists used in essay prose (only allowed in Image Description blocks)
  F9 — Output is clean Markdown only (no HTML tags)

IMAGE/MAP DESCRIPTION CHECKS:
  I1 — Image/Map Description block present for every image/map in source (if applicable)
  I2 — Each block contains: Type, Subject, Historical Context, Key Details to Note, Source Attribution
  I3 — No verbatim caption copying — all descriptions are rewritten analytically
  I4 — Map descriptions include geographic scope, marked locations, and historical interpretation
  I5 — Portrait/painting descriptions include: subject, era, visual choices and their significance

ACCURACY CHECKS:
  A1 — No fabricated facts that are not in the source content
  A2 — No speculative gap-filling (invented transitions, assumed motives not in source)
  A3 — Manuscript modernisation (if applicable): archaic terms have [modern equivalent] in brackets
  A4 — Manuscript fragments (if applicable): fragmentation clearly flagged with [note]
  A5 — All claims in the Conclusion are supported by earlier body paragraphs

SEVERITY LEVELS:
  CRITICAL — makes the entry unpublishable
  MAJOR    — serious quality issue that must be fixed before publication
  MINOR    — small issue that reduces polish but does not block publication
  PASS     — fully meets the standard

═══ YOUR OUTPUT FORMAT (strict JSON, nothing else) ═══

{
  "entry_id": "[the ID you were given]",
  "entry_title": "[title of the essay]",
  "overall_status": "PASS | FAIL | NEEDS REVISION",
  "overall_score": 0-100,
  "critical_issues": [
    { "check": "S4", "description": "...", "severity": "CRITICAL" }
  ],
  "major_issues": [],
  "minor_issues": [],
  "check_results": {
    "S1": "PASS", "S2": "PASS", "S3": "PASS", "S4": "FAIL", "S5": "PASS",
    "S6": "PARTIAL", "S7": "PASS", "S8": "PASS", "S9": "PASS",
    "F1": "PASS", "F2": "PASS", "F3": "PASS", "F4": "PASS", "F5": "PASS",
    "F6": "PARTIAL", "F7": "PASS", "F8": "PASS", "F9": "PASS",
    "I1": "N/A", "I2": "N/A", "I3": "N/A", "I4": "N/A", "I5": "N/A",
    "A1": "PASS", "A2": "PASS", "A3": "N/A", "A4": "N/A", "A5": "PASS"
  },
  "word_counts": {
    "introduction": 130,
    "body_paragraphs": [210, 185, 220],
    "conclusion": 140
  },
  "recommended_action": "...",
  "publishable": false
}

SCORING GUIDE:
  Start at 100. Deduct: CRITICAL = -20 per issue, MAJOR = -10, MINOR = -3.
  overall_status:
    90–100 = PASS
    70–89  = NEEDS REVISION
    below 70 = FAIL
  If any CRITICAL issue: publishable = false, regardless of score.

IMPORTANT: Return ONLY the JSON object. No text before or after it."""


REPORT_SYSTEM_PROMPT = """You are the Curious History Chief Audit Officer.

You receive a JSON array of individual audit results and synthesise them into a single,
authoritative, presentation-ready Audit Report in clean Markdown.

═══ REPORT STRUCTURE ═══

# Curious History — Database Quality Audit Report
**Prepared by:** Curious History Audit System
**Date:** [today's date]
**Scope:** Full database audit — [N] entries examined

---

## Executive Summary
- Total entries audited: N
- Entries: PASS / NEEDS REVISION / FAIL (counts and %)
- Publishable immediately: N (%)
- Overall database quality score: X/100
- Highest-risk finding: [one sentence on the most common critical issue]

---

## Audit Scorecard

| Metric | Result |
|--------|--------|
| Total entries | N |
| PASS | N (%) |
| NEEDS REVISION | N (%) |
| FAIL | N (%) |
| Publishable now | N (%) |
| Avg. quality score | X/100 |
| Critical issues found | N |
| Major issues found | N |
| Minor issues found | N |

---

## Check-by-Check Failure Analysis

| Check | Description | Entries failed | Severity |
|-------|-------------|----------------|----------|
...ranked table, worst first...

---

## Entries Requiring Immediate Action (FAIL status)

...list every FAIL entry with score, issues, recommended action...

---

## Entries Needing Revision (NEEDS REVISION status)

...list every NEEDS REVISION entry with score, issues, recommended action...

---

## Fully Passing Entries

...list entry IDs and titles that scored PASS — one line each...

---

## Systemic Patterns & Root Cause Analysis

...identify patterns, most common failures, root causes...

---

## Recommended Actions

1. [Highest priority fix]
2. ...

---

## Audit Certification

> This report was generated by the Curious History Automated Audit System.

**Database cleared for publication: YES / NO**"""


# ── DATABASE LOADER ───────────────────────────────────────────────────────────

def load_database(source_filter: str = None, sample: int = None) -> list[dict]:
    """
    Load records from curious_history.json.
    Each record is turned into an "entry" with id, title, and content.
    Content is the essay text built from the record's summary + era + region.
    """
    print(f"  Loading database from {DB_PATH}…")
    with open(DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    source_map = {s["id"]: s["name"] for s in db.get("sources", [])}
    records    = db.get("records", [])

    # Filter by source if requested
    if source_filter:
        records = [r for r in records
                   if source_filter.lower() in
                   source_map.get(r.get("source_id", 0), "").lower()]

    # Only audit records with meaningful text content
    records = [r for r in records
               if (r.get("summary") or r.get("full_text")) and
               len(r.get("summary") or r.get("full_text") or "") >= 100]

    # Random sample if requested
    if sample and sample < len(records):
        records = random.sample(records, sample)

    print(f"  {len(records)} records selected for audit")

    # Build entries with id, title, content
    entries = []
    for r in records:
        source_name = source_map.get(r.get("source_id", 0), "Unknown Source")
        content = _build_essay_content(r, source_name)
        if not content:
            continue
        entries.append({
            "id":      str(r.get("id", "")),
            "title":   r.get("title", "Untitled"),
            "content": content,
            "source":  source_name,
            "era":     r.get("era", ""),
            "region":  r.get("region", ""),
        })

    return entries


def _build_essay_content(record: dict, source_name: str) -> str:
    """
    Build a structured essay content string from a raw record for auditing.
    This mirrors what the live app produces via essay_formatter.format_as_essay().
    """
    try:
        from utils.essay_formatter import format_as_essay, bold_key_terms
        fmt_record = {
            "title":       record.get("title", ""),
            "snippet":     (record.get("summary") or record.get("full_text") or "")[:500],
            "era":         record.get("era", ""),
            "region":      record.get("region", ""),
            "source_name": source_name,
            "source_url":  record.get("source_url", ""),
            "record_type": record.get("record_type", "document"),
            "image_url":   record.get("image_url", ""),
        }
        essay = format_as_essay(
            topic       = record.get("title", "Historical Record"),
            records     = [fmt_record],
            era_hint    = record.get("era", ""),
            region_hint = record.get("region", ""),
        )
        return essay if essay else ""
    except Exception:
        # Fallback: use raw text
        text = record.get("full_text") or record.get("summary") or ""
        return f"# {record.get('title', 'Untitled')}\n\n{text}"


# ── AUDIT ONE ENTRY ───────────────────────────────────────────────────────────

def audit_entry(client: anthropic.Anthropic, entry: dict) -> dict:
    """Call Claude to audit a single database entry. Returns audit JSON."""
    user_msg = (
        f"ENTRY ID: {entry['id']}\n"
        f"ENTRY TITLE: {entry['title']}\n"
        f"SOURCE: {entry.get('source', '')}\n"
        f"ERA: {entry.get('era', '')}\n\n"
        f"FORMATTED CONTENT TO AUDIT:\n{entry['content']}"
    )

    try:
        # Use prompt caching on the large system prompt to save cost
        response = client.messages.create(
            model      = MODEL,
            max_tokens = MAX_TOKENS_AUDIT,
            system     = [
                {
                    "type": "text",
                    "text": AUDITOR_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }
            ],
            messages   = [{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        result["_source"] = entry.get("source", "")
        result["_era"]    = entry.get("era", "")
        return result

    except json.JSONDecodeError as e:
        return {
            "entry_id": entry["id"], "entry_title": entry["title"],
            "overall_status": "AUDIT_ERROR", "overall_score": 0,
            "error": f"JSON parse error: {e}", "publishable": False,
            "_source": entry.get("source", ""), "_era": entry.get("era", ""),
        }
    except anthropic.RateLimitError:
        print("  [RATE LIMIT] sleeping 30s…")
        time.sleep(30)
        return audit_entry(client, entry)   # retry once
    except Exception as e:
        return {
            "entry_id": entry["id"], "entry_title": entry["title"],
            "overall_status": "AUDIT_ERROR", "overall_score": 0,
            "error": str(e), "publishable": False,
            "_source": entry.get("source", ""), "_era": entry.get("era", ""),
        }


# ── GENERATE FINAL REPORT ─────────────────────────────────────────────────────

def generate_report(client: anthropic.Anthropic, all_results: list[dict]) -> str:
    """Generate the full audit report by synthesising all individual results."""
    today = datetime.now().strftime("%Y-%m-%d")
    user_msg = (
        f"Today's date: {today}\n"
        f"Here are the audit results for all {len(all_results)} entries "
        f"in the Curious History database. Generate the full Audit Report now.\n\n"
        f"AUDIT RESULTS JSON:\n{json.dumps(all_results, indent=2)}"
    )

    response = client.messages.create(
        model      = MODEL,
        max_tokens = MAX_TOKENS_REPORT,
        system     = REPORT_SYSTEM_PROMPT,
        messages   = [{"role": "user", "content": user_msg}],
    )
    return response.content[0].text


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Curious History Database Auditor")
    parser.add_argument("--sample",  type=int,   default=None,
                        help="Audit a random sample of N records (default: all)")
    parser.add_argument("--source",  type=str,   default=None,
                        help="Only audit records from this source (substring match)")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip final report generation (just save audit_results.json)")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    entries = load_database(source_filter=args.source, sample=args.sample)
    total   = len(entries)

    if total == 0:
        print("No entries to audit. Check --source filter or database content.")
        sys.exit(0)

    print(f"\n[Curious History Auditor] Auditing {total} entries…")
    print("─" * 64)

    all_results: list[dict] = []

    for i, entry in enumerate(entries, 1):
        label = entry["title"][:52]
        print(f"[{i:4}/{total}] {label:<54}", end=" ", flush=True)

        result  = audit_entry(client, entry)
        status  = result.get("overall_status", "ERROR")
        score   = result.get("overall_score", 0)
        icon    = "✓" if status == "PASS" else ("~" if status == "NEEDS REVISION" else "✗")
        print(f"{icon} {status:<16} {score:>3}/100")

        all_results.append(result)

        # Save incrementally — progress survives interruption
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        time.sleep(DELAY_BETWEEN)

    print("─" * 64)

    # ── Quick summary ─────────────────────────────────────────────────────────
    passed   = sum(1 for r in all_results if r.get("overall_status") == "PASS")
    revised  = sum(1 for r in all_results if r.get("overall_status") == "NEEDS REVISION")
    failed   = sum(1 for r in all_results if r.get("overall_status") == "FAIL")
    errors   = sum(1 for r in all_results if r.get("overall_status") == "AUDIT_ERROR")
    scored   = [r.get("overall_score", 0) for r in all_results
                if isinstance(r.get("overall_score"), int)]
    avg      = sum(scored) // len(scored) if scored else 0
    publish  = sum(1 for r in all_results if r.get("publishable"))

    print(f"\n  PASS:           {passed}/{total} ({100*passed//total}%)")
    print(f"  NEEDS REVISION: {revised}/{total} ({100*revised//total}%)")
    print(f"  FAIL:           {failed}/{total} ({100*failed//total}%)")
    if errors:
        print(f"  AUDIT ERRORS:   {errors}/{total}")
    print(f"  Publishable:    {publish}/{total}")
    print(f"  Avg Score:      {avg}/100")
    print(f"  Results saved:  {OUTPUT_FILE}")

    # ── Final report ──────────────────────────────────────────────────────────
    if not args.no_report:
        print("\n  Generating audit report…")
        try:
            report_md = generate_report(client, all_results)
            with open(REPORT_FILE, "w", encoding="utf-8") as f:
                f.write(report_md)
            print(f"  Report saved:   {REPORT_FILE}")
        except Exception as e:
            print(f"  Report generation failed: {e}")

    print("─" * 64)


if __name__ == "__main__":
    main()
