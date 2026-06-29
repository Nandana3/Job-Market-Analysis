"""
Naukri.com Scraper — Selenium Version
Uses a real Chrome browser so Naukri can't block it like a simple HTTP request.

Run this on your local Windows machine (not a server).
Chrome must be installed.

Usage:
    python scrapers/naukri_scraper_selenium.py

First run: downloads ChromeDriver automatically via webdriver-manager.
"""

import sqlite3
import hashlib
import time
import random
import os
import sys
import re
from datetime import datetime, date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.skill_extractor import extract_skills

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("Installing selenium and webdriver-manager...")
    os.system("pip install selenium webdriver-manager --break-system-packages -q")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")

SEARCH_KEYWORDS = [
    "Data Analyst",
    "MIS Analyst",
    "Business Analyst",
    "Reporting Analyst",
    "Operations Analyst",
]

# ─────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def generate_job_id(title: str, company: str, url: str) -> str:
    raw = f"{title.lower().strip()}{company.lower().strip()}{url.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def normalize_title(raw_title: str) -> str:
    title_lower = raw_title.lower()
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
    return "Other Analyst"


def parse_experience(exp_text: str) -> tuple:
    if not exp_text:
        return (0, 3)
    text = exp_text.lower().strip()
    if "fresher" in text or "0 year" in text:
        return (0, 0)
    match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match = re.search(r"(\d+)", text)
    if match:
        val = int(match.group(1))
        return (val, val)
    return (0, 3)


def parse_salary(salary_text: str) -> tuple:
    if not salary_text or "not disclosed" in salary_text.lower():
        return (None, None)
    numbers = re.findall(r"[\d.]+", salary_text.replace(",", ""))
    if len(numbers) >= 2:
        return (float(numbers[0]), float(numbers[1]))
    elif len(numbers) == 1:
        return (float(numbers[0]), float(numbers[0]))
    return (None, None)


def parse_work_mode(text: str) -> str:
    if not text:
        return "onsite"
    text_lower = text.lower()
    if "remote" in text_lower:
        return "remote"
    elif "hybrid" in text_lower:
        return "hybrid"
    return "onsite"


# ─────────────────────────────────────────────────────────────────
# BROWSER SETUP
# ─────────────────────────────────────────────────────────────────

def create_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Create Chrome WebDriver.
    headless=False means you'll see the browser open — useful for debugging.
    headless=True runs invisibly — use this once scraping is working.
    """
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    return driver


# ─────────────────────────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────────────────────────

def scrape_naukri_selenium(driver: webdriver.Chrome, keyword: str, pages: int = 3) -> list:
    """Scrape Naukri job listings using Selenium."""
    jobs = []
    keyword_url = keyword.replace(" ", "-").lower()

    for page in range(1, pages + 1):
        url = (
            f"https://www.naukri.com/{keyword_url}-jobs-in-bangalore"
            f"?experience=0&pageNo={page}"
        )

        print(f"  Page {page}: {url}")

        try:
            driver.get(url)

            wait = WebDriverWait(driver, 15)
            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "article.jobTuple, div.job-container, div[class*='jobTuple']")
                ))
            except:
                print(f"  Timeout waiting for job cards on page {page}")
                driver.save_screenshot(f"debug_page_{page}.png")
                continue

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(random.uniform(1, 2))

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "html.parser")

            job_cards = (
                soup.find_all("article", class_=lambda x: x and "jobTuple" in x) or
                soup.find_all("div", class_=lambda x: x and "jobTuple" in str(x)) or
                soup.find_all("div", attrs={"data-job-id": True})
            )

            print(f"  Found {len(job_cards)} job cards")

            for card in job_cards:
                try:
                    title_tag = (
                        card.find("a", class_=lambda x: x and "title" in str(x)) or
                        card.find("a", attrs={"title": True})
                    )
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    job_url = title_tag.get("href", "") if title_tag else ""

                    company_tag = (
                        card.find("a", class_=lambda x: x and "comp-name" in str(x)) or
                        card.find("span", class_=lambda x: x and "comp-name" in str(x)) or
                        card.find("a", class_=lambda x: x and "company" in str(x).lower())
                    )
                    company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                    exp_tag = card.find(class_=lambda x: x and "exp" in str(x).lower())
                    exp_raw = exp_tag.get_text(strip=True) if exp_tag else ""
                    exp_min, exp_max = parse_experience(exp_raw)

                    sal_tag = card.find(class_=lambda x: x and "sal" in str(x).lower())
                    sal_raw = sal_tag.get_text(strip=True) if sal_tag else "Not Disclosed"
                    sal_min, sal_max = parse_salary(sal_raw)

                    skills_tag = card.find("ul", class_=lambda x: x and "tag" in str(x).lower())
                    skills_raw = skills_tag.get_text(separator=", ", strip=True) if skills_tag else ""

                    desc_tag = card.find(class_=lambda x: x and "job-desc" in str(x).lower())
                    desc_raw = desc_tag.get_text(strip=True) if desc_tag else ""

                    if not title or not company:
                        continue

                    jobs.append({
                        "title": title,
                        "title_normalized": normalize_title(title),
                        "company": company,
                        "experience_raw": exp_raw,
                        "experience_min": exp_min,
                        "experience_max": exp_max,
                        "salary_raw": sal_raw,
                        "salary_min": sal_min,
                        "salary_max": sal_max,
                        "skills_raw": skills_raw,
                        "description_raw": desc_raw,
                        "work_mode": parse_work_mode(f"{title} {desc_raw}"),
                        "url": job_url,
                        "source": "naukri",
                        "date_scraped": str(date.today()),
                        "date_posted": str(date.today()),
                        "location": "Bangalore",
                    })

                except Exception as e:
                    continue

            time.sleep(random.uniform(3, 5))

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            continue

    return jobs


# ─────────────────────────────────────────────────────────────────
# DATABASE SAVE
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
                job.get("experience_min", 0), job.get("experience_max", 3),
                job.get("experience_raw", ""),
                job.get("salary_min"), job.get("salary_max"),
                job.get("salary_raw", "Not Disclosed"),
                job.get("skills_raw", ""), job.get("description_raw", ""),
                job.get("source", "naukri"), job.get("url", ""),
                job.get("date_posted", str(date.today())),
                job.get("date_scraped", str(date.today())),
            ))

            combined = f"{job.get('skills_raw','')} {job.get('description_raw','')} {job['title']}"
            for skill in extract_skills(combined):
                cursor.execute(
                    "INSERT INTO job_skills (job_id, skill) VALUES (?, ?)",
                    (job_id, skill)
                )

            new_added += 1

        except Exception as e:
            errors += 1

    cursor.execute("""
        INSERT INTO scrape_log (run_date, source, keyword, total_found, new_added, duplicates, errors)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(date.today()), "naukri", "all keywords", len(jobs), new_added, duplicates, errors))

    conn.commit()
    conn.close()

    return {"new_added": new_added, "duplicates": duplicates, "errors": errors}


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def run_scraper(headless: bool = False):
    print(f"\n{'='*50}")
    print(f"Naukri Scraper (Selenium) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    print("Starting Chrome browser...")
    driver = create_driver(headless=headless)

    all_jobs = []

    try:
        for keyword in SEARCH_KEYWORDS:
            print(f"\nKeyword: {keyword}")
            jobs = scrape_naukri_selenium(driver, keyword, pages=3)
            print(f"  Collected: {len(jobs)} postings")
            all_jobs.extend(jobs)
            time.sleep(random.uniform(3, 6))

    finally:
        driver.quit()
        print("\nBrowser closed.")

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
    run_scraper(headless=False)