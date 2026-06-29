"""
Job Market Analysis — SQL Queries
Run this after collecting and validating data.

Usage:
    python analysis/run_analysis.py

We only analyze rows where data_quality_flag = 'clean' — this is the
546 verified, current postings, not the noisy raw 727.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_market.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ─────────────────────────────────────────────────────────────────
# FINDING 1: The Skill Demand Reality
# Do postings that SIGNAL entry-level intent in their title actually
# demand a low skill bar — or are they unicorns in disguise?
#
# We use title keywords (trainee/junior/fresher/graduate/associate/
# entry level) instead of the experience_min field, because Adzuna's
# 500-char description snippets made free-text experience parsing
# unreliable (only ~15% coverage). Title signals are directly visible
# and don't depend on truncated text.
# ─────────────────────────────────────────────────────────────────

FRESHER_TITLE_KEYWORDS = ["trainee", "junior", "fresher", "graduate", "entry level", "associate"]


def finding_1_skill_demand_reality(conn):
    print_header("FINDING 1: The Skill Demand Reality")

    cursor = conn.cursor()

    like_conditions = " OR ".join([f"LOWER(j.title) LIKE '%{kw}%'" for kw in FRESHER_TITLE_KEYWORDS])

    # Total validated, genuine analyst postings (excludes 'Not Analyst Role')
    cursor.execute("""
        SELECT COUNT(*) FROM jobs j
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
    """)
    total_analyst_postings = cursor.fetchone()[0]

    # How many signal entry-level intent in the title?
    cursor.execute(f"""
        SELECT COUNT(*) FROM jobs j
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        AND ({like_conditions})
    """)
    fresher_signal_count = cursor.fetchone()[0]

    print(f"\nTotal validated analyst postings: {total_analyst_postings}")
    print(f"Postings signaling entry-level intent in title "
          f"(trainee/junior/fresher/graduate/associate/entry level): {fresher_signal_count}")
    print(f"  → {fresher_signal_count/total_analyst_postings*100:.1f}% of all analyst postings")

    # Average skill count: fresher-signal postings vs. the rest of the market
    cursor.execute(f"""
        SELECT j.job_id, COUNT(s.skill) as skill_count
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        AND ({like_conditions})
        GROUP BY j.job_id
    """)
    fresher_skill_counts = [r[1] for r in cursor.fetchall()]

    cursor.execute(f"""
        SELECT j.job_id, COUNT(s.skill) as skill_count
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        AND NOT ({like_conditions})
        GROUP BY j.job_id
    """)
    rest_of_market_skill_counts = [r[1] for r in cursor.fetchall()]

    if not fresher_skill_counts:
        print("\nNo fresher-signal postings with skill data found.")
        return

    avg_fresher = sum(fresher_skill_counts) / len(fresher_skill_counts)
    avg_market = (sum(rest_of_market_skill_counts) / len(rest_of_market_skill_counts)
                  if rest_of_market_skill_counts else 0)

    print(f"\nAverage distinct skills required:")
    print(f"  Fresher-signal postings  : {avg_fresher:.1f} skills")
    print(f"  Rest of the market       : {avg_market:.1f} skills")

    high_demand_count = sum(1 for c in fresher_skill_counts if c >= 5)
    print(f"\nFresher-signal postings requiring 5+ distinct skills: {high_demand_count} "
          f"({high_demand_count/len(fresher_skill_counts)*100:.1f}% of fresher-signal postings)")

    # Show the actual "unicorn" examples — most skills demanded despite fresher signal
    cursor.execute(f"""
        SELECT j.title, j.company, COUNT(s.skill) as skill_count
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        AND ({like_conditions})
        GROUP BY j.job_id
        ORDER BY skill_count DESC
        LIMIT 5
    """)
    print(f"\nTop 5 most 'unicorn' fresher-signal postings (most skills demanded):")
    for title, company, skill_count in cursor.fetchall():
        print(f"  [{skill_count} skills] {title} — {company}")


# ─────────────────────────────────────────────────────────────────
# FINDING 2: The Skill Combination Wall
# It's not usually ONE missing skill that filters people out — it's a
# specific COMBINATION. This finds which skills are most in-demand
# individually, and which pairs of skills most often appear together
# in the same posting.
# ─────────────────────────────────────────────────────────────────

def finding_2_skill_combination_wall(conn):
    print_header("FINDING 2: The Skill Combination Wall")

    cursor = conn.cursor()

    # Step 1: overall skill frequency ranking across genuine analyst postings
    cursor.execute("""
        SELECT s.skill, COUNT(DISTINCT s.job_id) as cnt
        FROM job_skills s
        JOIN jobs j ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        GROUP BY s.skill
        ORDER BY cnt DESC
        LIMIT 15
    """)
    top_skills = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    """)
    total_postings = cursor.fetchone()[0]

    print(f"\nTop 15 most in-demand skills (out of {total_postings} validated analyst postings):\n")
    for skill, cnt in top_skills:
        pct = cnt / total_postings * 100
        bar = "█" * int(pct / 2)
        print(f"  {skill:22s} {cnt:4d}  ({pct:4.1f}%)  {bar}")

    # Step 2: skill co-occurrence — which PAIRS of skills appear together most often
    # This is the real "combination wall" — e.g. SQL alone is common,
    # but SQL + Power BI + Advanced Excel together is a much higher bar.
    cursor.execute("""
        SELECT s.job_id, s.skill
        FROM job_skills s
        JOIN jobs j ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
    """)
    rows = cursor.fetchall()

    # Group skills by job_id in Python (simpler and clearer than a self-join in SQL)
    from collections import defaultdict, Counter
    job_skills_map = defaultdict(list)
    for job_id, skill in rows:
        job_skills_map[job_id].append(skill)

    pair_counts = Counter()
    for job_id, skills in job_skills_map.items():
        unique_skills = sorted(set(skills))
        for i in range(len(unique_skills)):
            for j in range(i + 1, len(unique_skills)):
                pair_counts[(unique_skills[i], unique_skills[j])] += 1

    print(f"\nTop 10 most common skill PAIRS (appearing together in the same posting):\n")
    for (skill_a, skill_b), cnt in pair_counts.most_common(10):
        pct = cnt / total_postings * 100
        print(f"  {skill_a} + {skill_b:22s}  {cnt:4d}  ({pct:.1f}%)")

    # Step 3: the realistic "combination wall" — postings requiring the
    # single most common 3-skill combination found in the data
    if top_skills:
        top_3_skill_names = [s[0] for s in top_skills[:3]]
        placeholders = ",".join("?" * len(top_3_skill_names))
        cursor.execute(f"""
            SELECT s.job_id, COUNT(DISTINCT s.skill) as matched
            FROM job_skills s
            JOIN jobs j ON j.job_id = s.job_id
            WHERE j.data_quality_flag = 'clean'
            AND j.title_normalized != 'Not Analyst Role'
            AND s.skill IN ({placeholders})
            GROUP BY s.job_id
            HAVING matched = {len(top_3_skill_names)}
        """, top_3_skill_names)
        all_three_count = len(cursor.fetchall())

        print(f"\nPostings requiring ALL THREE of the top skills "
              f"({', '.join(top_3_skill_names)}) simultaneously:")
        print(f"  {all_three_count} / {total_postings} ({all_three_count/total_postings*100:.1f}%)")
        print(f"  → This is the real 'combination wall': each skill alone is common,")
        print(f"    but demanding all three together is a meaningfully higher bar.")


# ─────────────────────────────────────────────────────────────────
# FINDING 3: What the Market is Actually Hiring For
# Role-type demand distribution, and which sectors/domains dominate —
# useful for freshers who may be targeting the wrong title or sector.
# ─────────────────────────────────────────────────────────────────

DOMAIN_SKILLS = ["BFSI Domain", "Finance Domain", "Supply Chain", "HR Analytics"]


def finding_3_market_demand(conn):
    print_header("FINDING 3: What the Market is Actually Hiring For")

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    """)
    total = cursor.fetchone()[0]

    # Role-type distribution
    cursor.execute("""
        SELECT title_normalized, COUNT(*) as cnt FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
        GROUP BY title_normalized ORDER BY cnt DESC
    """)
    print(f"\nRole-type demand (out of {total} validated analyst postings):\n")
    for role, cnt in cursor.fetchall():
        pct = cnt / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {role:22s} {cnt:4d}  ({pct:4.1f}%)  {bar}")

    # Domain/sector concentration — which industry knowledge is most requested
    print(f"\nDomain/sector knowledge most requested (independent of role title):\n")
    placeholders = ",".join("?" * len(DOMAIN_SKILLS))
    cursor.execute(f"""
        SELECT s.skill, COUNT(DISTINCT s.job_id) as cnt
        FROM job_skills s
        JOIN jobs j ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean'
        AND j.title_normalized != 'Not Analyst Role'
        AND s.skill IN ({placeholders})
        GROUP BY s.skill ORDER BY cnt DESC
    """, DOMAIN_SKILLS)
    domain_rows = cursor.fetchall()
    for skill, cnt in domain_rows:
        pct = cnt / total * 100
        print(f"  {skill:18s} {cnt:4d}  ({pct:.1f}%)")

    if not domain_rows:
        print("  (No domain-specific skill signals found)")

    # Cross-tab: role type x whether it requires domain knowledge
    # This tells us WHICH role types are most tied to a specific industry
    print(f"\nWhich role types most often require BFSI domain knowledge specifically:\n")
    cursor.execute("""
        SELECT j.title_normalized,
               COUNT(DISTINCT j.job_id) as total_in_role,
               COUNT(DISTINCT CASE WHEN s.skill = 'BFSI Domain' THEN j.job_id END) as with_bfsi
        FROM jobs j
        LEFT JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean' AND j.title_normalized != 'Not Analyst Role'
        GROUP BY j.title_normalized
        ORDER BY total_in_role DESC
    """)
    for role, total_in_role, with_bfsi in cursor.fetchall():
        pct = (with_bfsi / total_in_role * 100) if total_in_role else 0
        print(f"  {role:22s}: {with_bfsi:3d} / {total_in_role:3d} postings  ({pct:.1f}%)")


# ─────────────────────────────────────────────────────────────────
# FINDING 4: Company & Sector Concentration
# Is hiring demand broad-based across many companies, or concentrated
# in a few large players? And which companies set the highest skill bar?
# ─────────────────────────────────────────────────────────────────

def finding_4_company_concentration(conn):
    print_header("FINDING 4: Company & Sector Concentration")

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    """)
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT company) FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    """)
    distinct_companies = cursor.fetchone()[0]

    print(f"\nTotal validated analyst postings: {total}")
    print(f"Distinct companies represented: {distinct_companies}")
    print(f"Average postings per company: {total/distinct_companies:.1f}")

    # Top 15 companies by posting volume
    cursor.execute("""
        SELECT company, COUNT(*) as cnt FROM jobs
        WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
        GROUP BY company ORDER BY cnt DESC LIMIT 15
    """)
    top_companies = cursor.fetchall()

    print(f"\nTop 15 companies by posting volume:\n")
    for company, cnt in top_companies:
        pct = cnt / total * 100
        print(f"  {cnt:3d}  ({pct:4.1f}%)  {company}")

    # Concentration check: what % of all postings come from just the top 10 companies?
    top_10_total = sum(c for _, c in top_companies[:10])
    print(f"\nTop 10 companies account for {top_10_total} / {total} postings "
          f"({top_10_total/total*100:.1f}% of total demand)")
    print(f"  → {'Highly concentrated' if top_10_total/total > 0.3 else 'Broad-based'} hiring market: "
          f"demand is {'dominated by a handful of large employers' if top_10_total/total > 0.3 else 'spread across many companies, not dominated by a few large players'}")

    # Which companies post the most skill-demanding postings on average?
    # (only among companies with at least 3 postings, so single outlier
    # postings don't distort the ranking)
    cursor.execute("""
        SELECT j.company, COUNT(DISTINCT j.job_id) as posting_count,
               COUNT(s.skill) * 1.0 / COUNT(DISTINCT j.job_id) as avg_skills
        FROM jobs j
        JOIN job_skills s ON j.job_id = s.job_id
        WHERE j.data_quality_flag = 'clean' AND j.title_normalized != 'Not Analyst Role'
        GROUP BY j.company
        HAVING posting_count >= 3
        ORDER BY avg_skills DESC
        LIMIT 10
    """)
    print(f"\nCompanies setting the highest skill bar "
          f"(avg skills/posting, companies with 3+ postings):\n")
    for company, posting_count, avg_skills in cursor.fetchall():
        print(f"  {avg_skills:.1f} avg skills  ({posting_count} postings)  {company}")


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = get_connection()
    finding_1_skill_demand_reality(conn)
    finding_2_skill_combination_wall(conn)
    finding_3_market_demand(conn)
    finding_4_company_concentration(conn)
    conn.close()