"""
Adzuna API Job Collector
Replaces the Naukri Selenium scraper — uses Adzuna's official public API
instead of scraping a webpage. No browser, no bot detection issues.

Setup:
    1. Sign up free at https://developer.adzuna.com/
    2. Get your app_id and app_key from the dashboard
    3. Paste them below in APP_ID and APP_KEY
    4. Run: python scrapers/adzuna_collector.py

API docs: https://developer.adzuna.com/docs/search
"""

import sqlite3
import hashlib
import time
import os
import sys
import re
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.skill_extractor import extract_skills

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

# ─────────────────────────────────────────────────────────────────
# YOUR CREDENTIALS — paste your values here
# ─────────────────────────────────────────────────────────────────
APP_ID = "PASTE_YOUR_APP_ID_HERE"
APP_KEY = "PASTE_YOUR_APP_KEY_HERE"

# ─────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")
BASE_URL = "https://api.adzuna.com/v1/api/jobs/in/search"

SEARCH_KEYWORDS = [
    "data analyst",
    "MIS analyst",
    "business analyst",
    "reporting analyst",
    "operations analyst",
]

LOCATION = "bangalore"
RESULTS_PER_PAGE = 50   # Adzuna max per request
MAX_PAGES = 4           # 4 pages x 50 = up to 200 results per keyword


# ─────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS — same logic as before, reused for consistency
# ─────────────────────────────────────────────────────────────────

def generate_job_id(title: str, company: str, url: str) -> str:
    raw = f"{title.lower().strip()}{company.lower().strip()}{url.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def normalize_title(raw_title: str) -> str:
    """
    Classify a raw job title into a standardized category.

    Two-step logic:
    1. First check if this is genuinely a different job family entirely
       (Engineer, Developer, Scientist, Architect, Manager, Writer) with
       no "analyst" anywhere in the title — these get tagged 'Not Analyst Role'
       so they can be EXCLUDED from analyst-specific findings rather than
       silently diluting the "Other Analyst" bucket.
    2. If it IS an analyst-shaped title, classify into the right category,
       with a broader catch-all 'Data/Analytics Analyst' bucket for real
       analyst roles that don't fit the 5 main categories.
    """
    title_lower = raw_title.lower()

    # Step 1: filter out genuinely different job families.
    # Only exclude if NONE of these analyst-signal words are present —
    # e.g. "Data Quality Analyst" contains "analyst" so it's kept,
    # but "Senior Data Engineer" contains none, so it's excluded.
    non_analyst_keywords = ["engineer", "developer", "scientist", "architect", "writer"]
    has_analyst_signal = "analyst" in title_lower or "analytics" in title_lower

    if any(kw in title_lower for kw in non_analyst_keywords) and not has_analyst_signal:
        return "Not Analyst Role"

    # "Manager" is ambiguous (Analytics Manager is fine, Engineering Manager is not)
    if "manager" in title_lower and "analy" not in title_lower:
        return "Not Analyst Role"

    # Step 2: classify genuine analyst-shaped titles
    if "mis" in title_lower:
        return "MIS Analyst"
    elif "business analyst" in title_lower:
        return "Business Analyst"
    elif "operations" in title_lower or "ops" in title_lower:
        return "Operations Analyst"
    elif "reporting" in title_lower:
        return "Reporting Analyst"
    elif "data analyst" in title_lower:
        return "Data Analyst"
    elif has_analyst_signal:
        # Catches: Data Quality Analyst, Analytics Manager, Functional Analyst,
        # Data Protection Analyst, Analyst - Data Science, etc.
        return "Data/Analytics Analyst"

    return "Other Analyst"  # genuine leftover — should now be a small residual


def parse_experience(text: str) -> tuple:
    """
    Adzuna doesn't have a dedicated experience field — experience is
    mentioned inside the description text. We extract it with regex.
    """
    if not text:
        return (None, None)

    text_lower = text.lower()

    if "fresher" in text_lower or "fresh graduate" in text_lower or "entry level" in text_lower:
        return (0, 0)

    # Look for patterns like "2-5 years", "0-2 yrs", "3+ years"
    match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)\s*year", text_lower)
    if match:
        return (int(match.group(1)), int(match.group(2)))

    match = re.search(r"(\d+)\s*\+\s*year", text_lower)
    if match:
        val = int(match.group(1))
        return (val, val + 2)  # treat "3+ years" as a range

    match = re.search(r"minimum\s*(\d+)\s*year", text_lower)
    if match:
        val = int(match.group(1))
        return (val, val)

    return (None, None)  # unknown — will show as blank in analysis, which is honest


def parse_work_mode(text: str) -> str:
    if not text:
        return "onsite"
    text_lower = text.lower()
    if "remote" in text_lower or "work from home" in text_lower:
        return "remote"
    elif "hybrid" in text_lower:
        return "hybrid"
    return "onsite"


def lpa_from_annual(amount) -> float:
    """Convert Adzuna's annual INR salary figure into LPA (Lakhs Per Annum)."""
    if amount is None:
        return None
    try:
        return round(float(amount) / 100000, 2)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────
# API CALL
# ─────────────────────────────────────────────────────────────────

def fetch_adzuna_jobs(keyword: str, page: int = 1) -> dict:
    """
    Call the Adzuna API for one page of results.
    Returns the parsed JSON response, or None if the request failed.
    """
    url = f"{BASE_URL}/{page}"

    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "what": keyword,
        "where": LOCATION,
        "results_per_page": RESULTS_PER_PAGE,
        "content-type": "application/json",
    }

    try:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 401:
            print("  ERROR: Invalid app_id or app_key. Check your credentials.")
            return None

        if response.status_code != 200:
            print(f"  ERROR: Status {response.status_code} — {response.text[:200]}")
            return None

        return response.json()

    except Exception as e:
        print(f"  Request error: {e}")
        return None


def collect_keyword(keyword: str) -> list:
    """Fetch all pages for one keyword, return list of cleaned job dicts."""
    all_jobs = []

    for page in range(1, MAX_PAGES + 1):
        print(f"  Page {page}...")
        data = fetch_adzuna_jobs(keyword, page)

        if not data or "results" not in data:
            break

        results = data["results"]
        if not results:
            print(f"  No more results — stopping at page {page}")
            break

        for job in results:
            try:
                title = job.get("title", "")
                company = job.get("company", {}).get("display_name", "Unknown")
                description = job.get("description", "")
                job_url = job.get("redirect_url", "")
                location_name = job.get("location", {}).get("display_name", "Bangalore")
                date_posted = job.get("created", "")[:10]  # just the date part

                salary_min = lpa_from_annual(job.get("salary_min"))
                salary_max = lpa_from_annual(job.get("salary_max"))

                exp_min, exp_max = parse_experience(description)
                work_mode = parse_work_mode(f"{title} {description}")

                if not title or not company:
                    continue

                all_jobs.append({
                    "title": title,
                    "title_normalized": normalize_title(title),
                    "company": company,
                    "location": location_name,
                    "work_mode": work_mode,
                    "experience_min": exp_min,
                    "experience_max": exp_max,
                    "experience_raw": "",  # Adzuna has no dedicated field
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "salary_raw": f"{salary_min}-{salary_max} LPA" if salary_min else "Not Disclosed",
                    "skills_raw": "",  # skills come purely from description text
                    "description_raw": description,
                    "url": job_url,
                    "source": "adzuna",
                    "date_posted": date_posted or str(date.today()),
                    "date_scraped": str(date.today()),
                })

            except Exception as e:
                print(f"  Error parsing job: {e}")
                continue

        time.sleep(1)  # polite delay between pages, even though API allows faster

    return all_jobs


# ─────────────────────────────────────────────────────────────────
# DATABASE SAVE — identical logic to the scraper version
# ─────────────────────────────────────────────────────────────────

def save_jobs(jobs: list) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    new_added = 0
    duplicates = 0
    errors = 0

    for job in jobs:
        try:
            job_id = generate_job_id(job["title"], job["company"], job["url"])

            cursor.execute("SELECT id FROM jobs WHERE job_id = ?", (job_id,))
            if cursor.fetchone():
                duplicates += 1
                continue

            cursor.execute("""
                INSERT INTO jobs (
                    job_id, title, title_normalized, company,
                    location, work_mode,
                    experience_min, experience_max, experience_raw,
                    salary_min, salary_max, salary_raw,
                    skills_raw, description_raw,
                    source, url, date_posted, date_scraped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, job["title"], job["title_normalized"], job["company"],
                job.get("location", "Bangalore"), job.get("work_mode", "onsite"),
                job.get("experience_min"), job.get("experience_max"),
                job.get("experience_raw", ""),
                job.get("salary_min"), job.get("salary_max"),
                job.get("salary_raw", "Not Disclosed"),
                job.get("skills_raw", ""), job.get("description_raw", ""),
                job.get("source", "adzuna"), job.get("url", ""),
                job.get("date_posted", str(date.today())),
                job.get("date_scraped", str(date.today())),
            ))

            # Extract skills from description text — this matters MORE now
            # since Adzuna doesn't give a separate skills field.
            # NOTE: we deliberately do NOT include the job title here.
            # Titles like "Business Analyst" or "Data Analyst" would
            # falsely trigger skill matches just by restating the role
            # name, inflating generic categories rather than measuring
            # real tool/skill demand.
            combined = job.get('description_raw', '')
            for skill in extract_skills(combined):
                cursor.execute(
                    "INSERT INTO job_skills (job_id, skill) VALUES (?, ?)",
                    (job_id, skill)
                )

            new_added += 1

        except Exception as e:
            print(f"  DB error: {e}")
            errors += 1

    cursor.execute("""
        INSERT INTO scrape_log (run_date, source, keyword, total_found, new_added, duplicates, errors)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(date.today()), "adzuna", "all keywords", len(jobs), new_added, duplicates, errors))

    conn.commit()
    conn.close()

    return {"new_added": new_added, "duplicates": duplicates, "errors": errors}


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def run_collector():
    print(f"\n{'='*50}")
    print(f"Adzuna Job Collector — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    if APP_ID == "PASTE_YOUR_APP_ID_HERE" or APP_KEY == "PASTE_YOUR_APP_KEY_HERE":
        print("ERROR: You need to paste your real APP_ID and APP_KEY at the top of this file.")
        print("Get them free at https://developer.adzuna.com/")
        return

    all_jobs = []

    for keyword in SEARCH_KEYWORDS:
        print(f"\nKeyword: {keyword}")
        jobs = collect_keyword(keyword)
        print(f"  Collected: {len(jobs)} postings")
        all_jobs.extend(jobs)
        time.sleep(1)

    print(f"\nTotal collected: {len(all_jobs)}")
    print("Saving to database...")

    summary = save_jobs(all_jobs)

    print(f"\n{'='*50}")
    print(f"Run complete:")
    print(f"  New postings added : {summary['new_added']}")
    print(f"  Duplicates skipped : {summary['duplicates']}")
    print(f"  Errors             : {summary['errors']}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    run_collector()