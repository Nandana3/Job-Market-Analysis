"""
Skill Extraction Engine
Defines the master skill dictionary and extracts standardized skill tags
from raw job description text.

Why this matters: Raw JDs say things like "MS Excel", "excel", "Advanced Excel",
"Microsoft Excel" — all meaning the same thing. This normalizes everything
so your frequency counts are accurate.
"""

import re

# ─────────────────────────────────────────────────────────────────
# MASTER SKILL DICTIONARY
# Key   = standardized name (what gets stored in DB)
# Value = list of patterns to match in raw text (case-insensitive)
# ─────────────────────────────────────────────────────────────────

SKILL_DICTIONARY = {

    # ── SQL & Databases ──────────────────────────────────────────
    "SQL":              ["\\bsql\\b", "structured query language"],
    "MySQL":            ["\\bmysql\\b"],
    "PostgreSQL":       ["postgresql", "postgres"],
    "SQLite":           ["sqlite"],
    "Snowflake":        ["snowflake"],
    "SQL Server":       ["sql server", "ms sql", "mssql", "microsoft sql"],
    "Oracle DB":        ["oracle db", "oracle database", "\\boracle\\b"],
    "NoSQL":            ["nosql", "mongodb", "\\bmongo\\b"],

    # ── BI & Visualization ───────────────────────────────────────
    "Power BI":         ["power bi", "powerbi"],
    "Tableau":          ["\\btableau\\b"],
    "Looker":           ["\\blooker\\b"],
    "QlikView":         ["qlikview", "qlik sense", "\\bqlik\\b"],
    "DAX":              ["\\bdax\\b"],
    "MIS Reporting":    ["mis reporting", "mis reports", "\\bmis\\b"],

    # ── Excel ────────────────────────────────────────────────────
    "Advanced Excel":   ["advanced excel", "ms excel", "microsoft excel", "\\bexcel\\b",
                         "pivot table", "vlookup", "hlookup", "sumifs", "index match"],

    # ── Python ───────────────────────────────────────────────────
    "Python":           ["\\bpython\\b"],
    "Pandas":           ["\\bpandas\\b"],
    "NumPy":            ["\\bnumpy\\b"],
    "Matplotlib":       ["matplotlib", "seaborn"],
    "Scikit-learn":     ["scikit.learn", "sklearn"],

    # ── Cloud & Data Warehousing ─────────────────────────────────
    "AWS":              ["\\baws\\b", "amazon web services", "s3", "redshift"],
    "Azure":            ["\\bazure\\b", "azure synapse", "azure data factory"],
    "GCP":              ["\\bgcp\\b", "google cloud", "bigquery"],

    # ── ETL & Data Engineering ───────────────────────────────────
    "ETL":              ["\\betl\\b", "data pipeline", "data ingestion",
                         "data transformation"],
    "Airflow":          ["\\bairflow\\b", "apache airflow"],
    "Spark":            ["\\bspark\\b", "apache spark", "pyspark"],

    # ── Statistics & ML ──────────────────────────────────────────
    "Statistics":       ["statistics", "statistical analysis", "hypothesis testing",
                         "regression", "\\banova\\b"],
    "Machine Learning": ["machine learning", "\\bml\\b", "predictive model",
                         "random forest", "decision tree", "xgboost"],

    # ── Soft / Business Skills ───────────────────────────────────
    # NOTE: deliberately narrow patterns here. Generic phrases like
    # "communication skills required" or the job title itself
    # ("Business Analyst") appear in nearly every posting regardless
    # of actual tooling — including them as "skills" just restates
    # the job title/boilerplate rather than measuring real demand.
    "Data Storytelling":    ["data storytelling", "data narrative", "insight communication"],
    "Dashboard Development": ["build.*dashboard", "develop.*dashboard", "design.*dashboard",
                              "reporting dashboard", "interactive dashboard"],
    "KPI Tracking":         ["\\bkpi\\b", "key performance indicator", "metrics tracking",
                             "performance metrics"],
    "Requirement Gathering": ["requirement gathering", "requirements gathering",
                              "business requirement document", "\\bbrd\\b"],

    # ── Domain Knowledge ─────────────────────────────────────────
    "Finance Domain":       ["finance domain", "financial analysis", "p&l", "revenue analysis",
                             "\\bfmcg\\b"],
    "BFSI Domain":          ["banking", "\\bbfsi\\b", "insurance", "nbfc", "financial services"],
    "Supply Chain":         ["supply chain", "logistics", "inventory"],
    "HR Analytics":         ["hr analytics", "workforce analytics", "people analytics"],

    # ── Other Tools ──────────────────────────────────────────────
    "R":                    ["\\br programming\\b", "\\br language\\b", "\\brstudio\\b"],
    "Google Sheets":        ["google sheets", "google spreadsheet"],
    "JIRA":                 ["\\bjira\\b"],
    "Alteryx":              ["\\balteryx\\b"],
}


def extract_skills(text: str) -> list[str]:
    """
    Given raw job description text, return a list of matched
    standardized skill names.

    Usage:
        skills = extract_skills(job_description_text)
        # Returns e.g. ['SQL', 'Power BI', 'Advanced Excel', 'Python']
    """
    if not text:
        return []

    text_lower = text.lower()
    matched_skills = []

    for skill_name, patterns in SKILL_DICTIONARY.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                matched_skills.append(skill_name)
                break  # matched this skill, move to next

    return matched_skills


def count_skills(text: str) -> int:
    """Returns total number of distinct skills found in a JD."""
    return len(extract_skills(text))


# ─────────────────────────────────────────────────────────────────
# Quick test — run this file directly to verify extraction works
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_jd = """
    We are looking for a Data Analyst with strong SQL skills and experience
    in Power BI dashboard development. The candidate should be proficient in
    Advanced Excel including Pivot Tables and VLOOKUP. Knowledge of Python
    and Pandas is a plus. Experience with KPI tracking and MIS reporting
    preferred. 0-2 years experience. BFSI domain preferred.
    """

    skills_found = extract_skills(sample_jd)
    print(f"Skills extracted ({len(skills_found)} found):")
    for s in skills_found:
        print(f"  - {s}")