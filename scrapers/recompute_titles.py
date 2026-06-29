"""
Recompute Title Categories
Applies the corrected normalize_title() logic to all existing rows,
without needing to re-collect from Adzuna. Run this once after
updating normalize_title() in adzuna_collector.py.

Usage:
    python scrapers/recompute_titles.py
"""

import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.adzuna_collector import normalize_title

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")


def run_recompute():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT job_id, title FROM jobs")
    all_jobs = cursor.fetchall()

    print(f"Recomputing title categories for {len(all_jobs)} postings...\n")

    for job_id, title in all_jobs:
        new_category = normalize_title(title)
        cursor.execute(
            "UPDATE jobs SET title_normalized = ? WHERE job_id = ?",
            (new_category, job_id)
        )

    conn.commit()

    # Report the new distribution
    cursor.execute("""
        SELECT title_normalized, COUNT(*) as cnt FROM jobs
        WHERE data_quality_flag = 'clean'
        GROUP BY title_normalized ORDER BY cnt DESC
    """)
    rows = cursor.fetchall()
    total = sum(r[1] for r in rows)

    print(f"{'='*60}")
    print(f"New role type distribution (validated 'clean' postings only)")
    print(f"{'='*60}")
    for title_norm, cnt in rows:
        pct = cnt / total * 100
        print(f"  {title_norm:25s}: {cnt:4d}  ({pct:.1f}%)")
    print(f"{'='*60}\n")

    not_analyst_count = next((cnt for tn, cnt in rows if tn == "Not Analyst Role"), 0)
    print(f"Note: {not_analyst_count} postings are tagged 'Not Analyst Role'.")
    print(f"Filter these out in your analysis queries with:")
    print(f"  WHERE title_normalized != 'Not Analyst Role'\n")

    conn.close()


if __name__ == "__main__":
    run_recompute()