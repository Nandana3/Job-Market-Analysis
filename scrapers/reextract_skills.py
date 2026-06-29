"""
Re-extract Skills Using Full Descriptions
After fetch_full_descriptions.py runs, some jobs now have a much longer,
uncut description_full. This re-runs skill extraction using the best
available text for each job: description_full if we got it, otherwise
falling back to the original description_raw snippet.

Run this AFTER fetch_full_descriptions.py:
    python scrapers/reextract_skills.py
"""

import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.skill_extractor import extract_skills

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")


def run_reextraction():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT job_id, title, description_raw, description_full
        FROM jobs
        WHERE data_quality_flag = 'clean'
    """)
    all_jobs = cursor.fetchall()

    print(f"Re-extracting skills for {len(all_jobs)} clean postings...\n")

    jobs_using_full_text = 0
    jobs_using_snippet_only = 0
    total_skill_tags_added = 0

    for job_id, title, description_raw, description_full in all_jobs:
        # Prefer the full description when we successfully fetched one
        if description_full and len(description_full) > 0:
            text_to_use = description_full
            jobs_using_full_text += 1
        else:
            text_to_use = description_raw or ""
            jobs_using_snippet_only += 1

        # NOTE: deliberately excluding `title` here — see adzuna_collector.py
        # for why (titles like "Business Analyst" caused false skill matches)
        combined = text_to_use
        skills = extract_skills(combined)

        # Clear old skill tags for this job, then insert fresh ones
        cursor.execute("DELETE FROM job_skills WHERE job_id = ?", (job_id,))
        for skill in skills:
            cursor.execute(
                "INSERT INTO job_skills (job_id, skill) VALUES (?, ?)",
                (job_id, skill)
            )
        total_skill_tags_added += len(skills)

    conn.commit()

    # Report the new coverage
    cursor.execute("""
        SELECT COUNT(DISTINCT j.job_id)
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
    """)
    jobs_with_skills_now = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE data_quality_flag = 'clean'")
    total_clean = cursor.fetchone()[0]

    print(f"{'='*60}")
    print(f"Re-extraction complete")
    print(f"{'='*60}")
    print(f"  Jobs using full fetched description : {jobs_using_full_text}")
    print(f"  Jobs using original snippet only     : {jobs_using_snippet_only}")
    print(f"  Total skill tags inserted            : {total_skill_tags_added}")
    print()
    print(f"  Jobs with at least 1 skill detected  : {jobs_with_skills_now} / {total_clean} "
          f"({jobs_with_skills_now/total_clean*100:.1f}%)")
    print(f"{'='*60}\n")

    conn.close()


if __name__ == "__main__":
    run_reextraction()