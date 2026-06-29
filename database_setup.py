"""
Job Market Tracker — Database Setup
Run this once to create the SQLite database and all tables.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "job_market.db")


def create_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ─────────────────────────────────────────────
    # TABLE 1: jobs
    # One row per unique job posting
    # ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id              TEXT UNIQUE,          -- unique hash to prevent duplicates
            title               TEXT NOT NULL,        -- raw job title from posting
            title_normalized    TEXT,                 -- cleaned: 'Data Analyst', 'MIS Analyst' etc.
            company             TEXT,
            company_size        TEXT,                 -- 'small', 'mid', 'large' (manual enrichment)
            sector              TEXT,                 -- 'IT Services', 'BFSI', 'Startup' etc.
            location            TEXT,                 -- 'Bangalore', 'Remote', 'Hybrid'
            work_mode           TEXT,                 -- 'onsite', 'remote', 'hybrid'
            experience_min      INTEGER,              -- minimum years required (0 for fresher)
            experience_max      INTEGER,              -- maximum years required
            experience_raw      TEXT,                 -- original text: '0-2 Yrs', 'Fresher' etc.
            salary_min          REAL,                 -- in LPA
            salary_max          REAL,                 -- in LPA
            salary_raw          TEXT,                 -- original text: '3-6 Lacs PA'
            skills_raw          TEXT,                 -- full skills text from posting
            description_raw     TEXT,                 -- full job description text
            source              TEXT,                 -- 'naukri', 'internshala', 'adzuna' etc.
            url                 TEXT,
            date_posted         TEXT,                 -- date from the posting
            date_scraped        TEXT,                 -- when we collected it
            is_active           INTEGER DEFAULT 1,    -- 1 = still live, 0 = removed
            data_quality_flag   TEXT DEFAULT 'clean'  -- 'clean', 'vague', 'likely_spam', 'stale'
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE 2: job_skills
    # Normalized skill tags — one row per skill per job
    # This powers the skill frequency and co-occurrence analysis
    # ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT NOT NULL,
            skill       TEXT NOT NULL,               -- standardized skill name
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE 3: scrape_log
    # Tracks every scraping run — useful for debugging
    # and for showing "data collected over X weeks" in your case study
    # ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date        TEXT NOT NULL,
            source          TEXT NOT NULL,
            keyword         TEXT,                    -- search keyword used
            total_found     INTEGER,                 -- postings found in this run
            new_added       INTEGER,                 -- genuinely new postings added
            duplicates      INTEGER,                 -- skipped as duplicates
            errors          INTEGER DEFAULT 0,
            notes           TEXT
        )
    """)

    # ─────────────────────────────────────────────
    # INDEXES
    # Speed up the queries you'll run most often
    # ─────────────────────────────────────────────
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_title_norm ON jobs(title_normalized)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_date_scraped ON jobs(date_scraped)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_experience ON jobs(experience_min, experience_max)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_quality_flag ON jobs(data_quality_flag)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_skills_job ON job_skills(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills(skill)")

    conn.commit()
    conn.close()
    print(f"Database created at: {DB_PATH}")
    print("Tables created: jobs, job_skills, scrape_log")
    print("Indexes created for fast querying.")


if __name__ == "__main__":
    create_database()