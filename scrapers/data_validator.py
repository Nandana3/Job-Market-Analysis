"""
Data Quality Validator
Flags low-quality job postings: vague descriptions, likely recruitment-agency
spam, and stale/expired listings — without deleting them.

Why we flag instead of delete: a 12% "spam rate" is itself a finding for
your case study. Deleting silently would hide a real insight about the
job market's quality problem.

Run this AFTER collecting data, before running analysis queries:
    python scrapers/data_validator.py
"""

import sqlite3
import os
import re
from collections import Counter
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION — thresholds you can tune as you see more real data
# ─────────────────────────────────────────────────────────────────

MIN_DESCRIPTION_WORDS = 40          # below this = "vague"
SAME_COMPANY_THRESHOLD = 8          # one company posting 8+ truly identical titles = "likely_spam"
STALE_DAYS_THRESHOLD = 60           # postings older than this = "stale" (Adzuna itself rarely returns anything older than ~5 weeks, so this is a safety net, not the main signal)

# Common patterns in generic recruitment-agency / database-building postings
AGENCY_NAME_PATTERNS = [
    "consultancy", "consultants", "talent", "hr solutions", "hr services",
    "manpower", "staffing", "recruitment", "placement", "hiring solutions",
    "career", "workforce solutions",
]

VAGUE_PHRASES = [
    "good communication skills required", "freshers can apply",
    "immediate joiner", "walk-in interview", "multiple openings",
]

# Generic templated title patterns used by bulk/agency-style listings.
# Real employers write specific titles ("Senior Data Analyst - BI Team");
# bulk listings often follow a generic "Require a X in Y" template instead.
GENERIC_TITLE_PATTERNS = [
    r"^require\s+an?\s+",       # "Require a Data Analyst in Bangalore"
    r"^urgent\s+requirement",
    r"^urgently\s+hiring",
    r"^hiring\s+for\s+",
]


def get_word_count(text: str) -> int:
    """Simple word count, used to flag suspiciously short/vague postings."""
    if not text:
        return 0
    return len(text.split())


def has_generic_title_pattern(title: str) -> bool:
    """Detect generic, templated bulk-listing title patterns."""
    if not title:
        return False
    title_lower = title.lower().strip()
    return any(re.search(pattern, title_lower) for pattern in GENERIC_TITLE_PATTERNS)


def is_agency_name(company: str) -> bool:
    """Check if a company name looks like a recruitment agency rather than a direct employer."""
    if not company:
        return False
    company_lower = company.lower()
    return any(pattern in company_lower for pattern in AGENCY_NAME_PATTERNS)


def is_vague_posting(description: str) -> bool:
    """Flag postings that are too short or too generic to be useful for analysis."""
    if get_word_count(description) < MIN_DESCRIPTION_WORDS:
        return True

    description_lower = description.lower()
    vague_phrase_count = sum(1 for phrase in VAGUE_PHRASES if phrase in description_lower)

    # If it's short AND has multiple generic phrases, it's likely a low-effort posting
    if get_word_count(description) < 80 and vague_phrase_count >= 2:
        return True

    return False


def is_stale(date_posted: str) -> bool:
    """Flag postings older than the stale threshold."""
    if not date_posted:
        return False
    try:
        posted_date = datetime.strptime(date_posted, "%Y-%m-%d").date()
        days_old = (date.today() - posted_date).days
        return days_old > STALE_DAYS_THRESHOLD
    except ValueError:
        return False


def find_repeat_posters(conn) -> set:
    """
    Find companies that have posted an unusually high number of EXACTLY
    identical job titles — a strong signal of recruitment-agency mass-posting
    (e.g. the same generic "Data Analyst Opening" repeated many times).

    Important: we compare the exact raw `title`, not `title_normalized`.
    Large companies (banks, MNCs) often post many genuinely distinct roles
    that all fall into the same broad category (e.g. "Other Analyst") —
    that's normal hiring, not spam. Only flag when the literal title text
    repeats far more than is plausible for distinct openings.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT company, title FROM jobs")
    rows = cursor.fetchall()

    company_title_counts = Counter()
    for company, title in rows:
        # Normalize only whitespace/case for the exact-match check —
        # NOT category bucketing
        key = (company, title.strip().lower())
        company_title_counts[key] += 1

    flagged_companies = set()
    for (company, title), count in company_title_counts.items():
        if count >= SAME_COMPANY_THRESHOLD:
            flagged_companies.add(company)

    return flagged_companies


# ─────────────────────────────────────────────────────────────────
# MAIN VALIDATION RUN
# ─────────────────────────────────────────────────────────────────

def run_validation():
    print(f"\n{'='*50}")
    print("Data Quality Validator")
    print(f"{'='*50}\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Reset all flags to 'clean' before re-validating
    # (safe to run this script multiple times as data grows)
    cursor.execute("UPDATE jobs SET data_quality_flag = 'clean'")

    # Step 1: find repeat-posting agencies first (needs a full table scan)
    repeat_posters = find_repeat_posters(conn)
    print(f"Companies flagged as repeat/mass posters: {len(repeat_posters)}")
    if repeat_posters:
        for company in list(repeat_posters)[:10]:
            print(f"  - {company}")

    # Step 2: go through every job and assign a flag
    cursor.execute("SELECT job_id, title, company, description_raw, date_posted FROM jobs")
    all_jobs = cursor.fetchall()

    flag_counts = Counter()

    for job_id, title, company, description, date_posted in all_jobs:
        flag = "clean"

        if company in repeat_posters or is_agency_name(company) or has_generic_title_pattern(title):
            flag = "likely_spam"
        elif is_vague_posting(description):
            flag = "vague"
        elif is_stale(date_posted):
            flag = "stale"

        cursor.execute(
            "UPDATE jobs SET data_quality_flag = ? WHERE job_id = ?",
            (flag, job_id)
        )
        flag_counts[flag] += 1

    conn.commit()

    # Step 3: print a summary — this is what goes into your case study
    total = sum(flag_counts.values())
    print(f"\n{'='*50}")
    print(f"Validation complete — {total} total postings checked")
    print(f"{'='*50}")
    for flag, count in flag_counts.most_common():
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {flag:15s}: {count:4d}  ({pct:.1f}%)")
    print(f"{'='*50}\n")

    print("Note: nothing was deleted. Use data_quality_flag = 'clean'")
    print("in your SQL queries to analyze only validated postings,")
    print("or report the breakdown above as a finding about market quality.\n")

    conn.close()
    return flag_counts


if __name__ == "__main__":
    run_validation()