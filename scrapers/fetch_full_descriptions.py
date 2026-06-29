"""
Full Description Fetcher
Adzuna's API only returns a 500-character snippet of each job description.
The real, full description lives at the original posting's `url` (Adzuna's
redirect_url, captured in our `url` column).

A 30-posting test run showed a 57% success rate — good enough to scale to
the full dataset. The 43% that fail (mostly HTTP 403 from protected career
pages) simply keep their original 500-char snippet as a fallback — nothing
is lost, we only gain coverage where we can.

Usage:
    python scrapers/fetch_full_descriptions.py
"""

import sqlite3
import os
import time
import random
import re

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    os.system("pip install requests beautifulsoup4 --break-system-packages -q")
    import requests
    from bs4 import BeautifulSoup

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")

TIMEOUT_SECONDS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def strip_adzuna_chrome(text: str) -> str:
    """
    Some redirect_url values route through an Adzuna-hosted interstitial
    page before reaching the real employer page. That page's navigation
    text ("adzuna.in What? Where? Search Advanced ... back to last search
    ... Apply for this job") gets mixed into the captured text. This
    removes that specific boilerplate so it doesn't pollute skill
    extraction with irrelevant chrome.
    """
    chrome_patterns = [
        r"adzuna\.in\s*",
        r"What\?\s*Where\?\s*Search\s*Advanced\s*",
        r"‹?\s*back to last search\s*",
        r"^.*?Apply for this job\s*",  # strip everything up to and including this phrase
    ]
    cleaned = text
    for pattern in chrome_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def fetch_full_text(url: str) -> tuple:
    """
    Try to fetch and extract the main visible text from a job posting URL.
    Returns (success: bool, text_or_error: str)
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)

        if response.status_code != 200:
            return (False, f"HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script/style tags — they add noise, not real content
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)

        # Detect Adzuna's own interstitial/redirect page specifically —
        # if we landed on an Adzuna-hosted page instead of the real
        # employer page, the navigation chrome is a strong signal.
        is_adzuna_interstitial = "adzuna.in" in text.lower() and "back to last search" in text.lower()

        if is_adzuna_interstitial:
            text = strip_adzuna_chrome(text)
            # After stripping chrome, what's left should still be
            # substantial real content — if not, treat as a failure
            # rather than storing mostly-empty text.
            if len(text) < 300:
                return (False, "Adzuna interstitial with no real content after stripping chrome")

        # A real job description page should have substantial text.
        # Very short results usually mean we hit a login wall, JS-only
        # shell, or block page instead of real content.
        if len(text) < 300:
            return (False, f"Too short ({len(text)} chars) — likely blocked/JS-rendered")

        return (True, text[:5000])  # cap stored length to keep DB reasonable

    except requests.exceptions.Timeout:
        return (False, "Timeout")
    except requests.exceptions.SSLError:
        return (False, "SSL error")
    except Exception as e:
        return (False, f"Error: {str(e)[:100]}")


def run_full_fetch():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add a column to store the full description, if not already present
    cursor.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    if "description_full" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN description_full TEXT")
        conn.commit()
        print("Added 'description_full' column to jobs table.\n")

    # Reset any previously-fetched descriptions that contain Adzuna's
    # navigation chrome — these were captured before the chrome-stripping
    # fix existed, so they need a fresh fetch with the corrected logic.
    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE description_full LIKE '%back to last search%'
    """)
    contaminated_count = cursor.fetchone()[0]

    if contaminated_count > 0:
        cursor.execute("""
            UPDATE jobs SET description_full = NULL
            WHERE description_full LIKE '%back to last search%'
        """)
        conn.commit()
        print(f"Reset {contaminated_count} previously-contaminated descriptions for re-fetch.\n")

    # Pick ALL eligible postings: clean, not yet tried
    cursor.execute("""
        SELECT job_id, title, company, url FROM jobs
        WHERE data_quality_flag = 'clean'
        AND (description_full IS NULL OR description_full = '')
        AND url IS NOT NULL AND url != ''
    """)
    batch = cursor.fetchall()

    if not batch:
        print("No eligible postings found (either none left, or all already processed).")
        conn.close()
        return

    print(f"Fetching full descriptions for {len(batch)} postings...")
    print("This will take a while due to polite delays between requests — that's normal.\n")

    success_count = 0
    fail_reasons = {}

    for job_id, title, company, url in batch:
        success, result = fetch_full_text(url)

        if success:
            cursor.execute(
                "UPDATE jobs SET description_full = ? WHERE job_id = ?",
                (result, job_id)
            )
            success_count += 1
            print(f"  OK   | {company[:30]:30s} | {title[:40]}")
        else:
            fail_reasons[result] = fail_reasons.get(result, 0) + 1
            print(f"  FAIL | {company[:30]:30s} | {result}")

        conn.commit()
        time.sleep(random.uniform(1, 2))  # polite delay, varies by domain anyway

    print(f"\n{'='*60}")
    print(f"Full fetch complete: {success_count} / {len(batch)} succeeded "
          f"({success_count/len(batch)*100:.0f}%)")
    print(f"{'='*60}")

    if fail_reasons:
        print("\nFailure breakdown:")
        for reason, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
            print(f"  {count:3d}x  {reason}")

    print(f"\nThose {len(batch) - success_count} postings keep their original 500-char")
    print(f"snippet as a fallback — no data was lost, only gained where possible.")
    print(f"\nNext step: re-run skill extraction so the newly fetched full text")
    print(f"can be scanned for skills that were previously cut off.\n")

    conn.close()


if __name__ == "__main__":
    run_full_fetch()