"""
Data Health Check
Gives an honest, complete picture of field coverage across your dataset —
what's strong, what's weak, before building analysis on top of it.

Run anytime you want a fresh read on data quality:
    python analysis/health_check.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run_health_check():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE data_quality_flag = 'clean'")
    total_clean = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_all = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    """)
    total_genuine_analyst = cursor.fetchone()[0]

    print_header("OVERALL DATASET")
    print(f"\nTotal postings collected: {total_all}")
    print(f"Validated as 'clean': {total_clean} ({total_clean/total_all*100:.1f}%)")
    print(f"Genuine analyst postings (excludes 'Not Analyst Role'): {total_genuine_analyst} "
          f"({total_genuine_analyst/total_clean*100:.1f}% of clean)")
    print(f"\nNOTE: all stats below use 'genuine analyst postings' ({total_genuine_analyst}) as the base,")
    print(f"since Engineer/Developer/Scientist roles shouldn't count toward analyst-market findings.")

    # ─────────────────────────────────────────────────────────
    # Field-by-field coverage check (clean + genuine analyst only)
    # ─────────────────────────────────────────────────────────
    print_header("FIELD COVERAGE (genuine analyst postings only)")

    base_filter = "data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'"

    fields_to_check = {
        "salary_min (any salary disclosed)": "salary_min IS NOT NULL",
        "experience_min (experience text parsed)": "experience_min IS NOT NULL",
        "work_mode = remote": "work_mode = 'remote'",
        "work_mode = hybrid": "work_mode = 'hybrid'",
        "work_mode = onsite": "work_mode = 'onsite'",
    }

    for label, condition in fields_to_check.items():
        cursor.execute(f"SELECT COUNT(*) FROM jobs WHERE {base_filter} AND {condition}")
        count = cursor.fetchone()[0]
        pct = (count / total_genuine_analyst * 100) if total_genuine_analyst else 0
        print(f"  {label:45s}: {count:4d} / {total_genuine_analyst}  ({pct:.1f}%)")

    # ─────────────────────────────────────────────────────────
    # Skill extraction coverage — how many jobs got AT LEAST 1 skill tagged?
    # ─────────────────────────────────────────────────────────
    print_header("SKILL EXTRACTION COVERAGE")

    cursor.execute(f"""
        SELECT COUNT(DISTINCT j.job_id)
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE {base_filter}
    """)
    jobs_with_skills = cursor.fetchone()[0]
    print(f"\nJobs with at least 1 skill tagged: {jobs_with_skills} / {total_genuine_analyst} "
          f"({jobs_with_skills/total_genuine_analyst*100:.1f}%)")

    cursor.execute(f"""
        SELECT j.job_id, COUNT(s.skill) as cnt
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE {base_filter}
        GROUP BY j.job_id
    """)
    skill_counts = [row[1] for row in cursor.fetchall()]
    if skill_counts:
        avg_skills = sum(skill_counts) / len(skill_counts)
        print(f"Average distinct skills per job (where any found): {avg_skills:.1f}")
        print(f"Jobs with 0 skills detected: {total_genuine_analyst - jobs_with_skills} "
              f"({(total_genuine_analyst - jobs_with_skills)/total_genuine_analyst*100:.1f}%)")

    # ─────────────────────────────────────────────────────────
    # Title-based fresher signal
    # ─────────────────────────────────────────────────────────
    print_header("TITLE-BASED FRESHER SIGNAL")

    fresher_title_keywords = ["trainee", "junior", "fresher", "graduate", "entry level", "associate"]
    like_conditions = " OR ".join([f"LOWER(title) LIKE '%{kw}%'" for kw in fresher_title_keywords])

    cursor.execute(f"""
        SELECT COUNT(*) FROM jobs
        WHERE {base_filter} AND ({like_conditions})
    """)
    fresher_title_count = cursor.fetchone()[0]
    print(f"\nPostings with fresher-signal keywords in TITLE "
          f"(trainee/junior/fresher/graduate/entry level/associate):")
    print(f"  {fresher_title_count} / {total_genuine_analyst} ({fresher_title_count/total_genuine_analyst*100:.1f}%)")

    # ─────────────────────────────────────────────────────────
    # Company spread
    # ─────────────────────────────────────────────────────────
    print_header("COMPANY SPREAD")

    cursor.execute(f"SELECT COUNT(DISTINCT company) FROM jobs WHERE {base_filter}")
    distinct_companies = cursor.fetchone()[0]
    print(f"\nDistinct companies represented: {distinct_companies}")

    cursor.execute(f"""
        SELECT company, COUNT(*) as cnt FROM jobs
        WHERE {base_filter}
        GROUP BY company ORDER BY cnt DESC LIMIT 10
    """)
    print("\nTop 10 companies by posting volume:")
    for company, cnt in cursor.fetchall():
        print(f"  {cnt:3d}  {company}")

    # ─────────────────────────────────────────────────────────
    # Title type spread — includes 'Not Analyst Role' here specifically,
    # since this is the one place we WANT to see that exclusion category
    # ─────────────────────────────────────────────────────────
    print_header("ROLE TYPE SPREAD (including excluded 'Not Analyst Role')")

    cursor.execute("""
        SELECT title_normalized, COUNT(*) as cnt FROM jobs
        WHERE data_quality_flag = 'clean'
        GROUP BY title_normalized ORDER BY cnt DESC
    """)
    print()
    for title_norm, cnt in cursor.fetchall():
        pct = cnt / total_clean * 100
        marker = "  <- excluded from all stats above" if title_norm == "Not Analyst Role" else ""
        print(f"  {title_norm:20s}: {cnt:4d}  ({pct:.1f}%){marker}")

    print(f"\n{'='*60}\n")
    conn.close()


if __name__ == "__main__":
    run_health_check()