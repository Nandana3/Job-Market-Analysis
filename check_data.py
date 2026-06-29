import sqlite3
conn = sqlite3.connect('data/job_market.db')
cursor = conn.cursor()

# Recount distinct companies, exactly as before
cursor.execute("""
    SELECT COUNT(DISTINCT company) FROM jobs
    WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
""")
print("Distinct companies (SQL):", cursor.fetchone()[0])

# NEW: check for near-duplicate company names that might be merging differently
# in Power BI vs SQL due to subtle text differences (trailing space, different case, etc.)
cursor.execute("""
    SELECT company, COUNT(*) FROM jobs
    WHERE data_quality_flag = 'clean' AND title_normalized != 'Not Analyst Role'
    GROUP BY company
    ORDER BY company
""")
companies = cursor.fetchall()
print("Total rows from GROUP BY:", len(companies))

# Print companies with anything unusual - leading/trailing spaces, etc.
for company, cnt in companies:
    if company != company.strip():
        print(f"  SUSPICIOUS (whitespace): '{company}'")

conn.close()