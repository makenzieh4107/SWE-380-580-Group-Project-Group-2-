"""
Duplicate Artifact Analysis for the GitSkills Dataset

This script connects to the approved GitSkills sample database and runs the
duplicate-analysis SQL queries used to investigate potential artifact reuse.
It examines the artifacts table to:

1. Retrieve the artifact fields needed for analysis.
2. Find artifacts that have the same file_sha, indicating identical content.
3. Group and display identical artifacts across repositories.
4. Summarize the size and available timestamps of each identical-content group.
5. Examine the dedup_primary field to identify GitSkills-designated primary
   and non-primary artifacts within duplicate groups.
6. Count the total number of duplicate groups and verify that each group
   contains both a primary and non-primary artifact.

The results provide the data foundation for investigating reused or copied
skills and will later be used to compare related artifacts for newly
introduced security-sensitive capabilities.

The script analyzes the dataset as data only and does not execute any
scripts or code contained within the artifacts.
"""

import duckdb

# Connect to DuckDB
con = duckdb.connect()

# Attach the GitSkills database and give it the name GitSkills
con.execute("ATTACH 'data/agent_skills_sample.db' AS GitSkills")

# ---------------------------------------------------------
# 1. Fields We Need
# ---------------------------------------------------------

query1 = """
SELECT
  repo_full_name,
  path,
  content,
  file_sha,
  name,
  description,
  first_commit_at,
  last_commit_at
FROM GitSkills.artifacts
"""

result1 = con.execute(query1).fetchdf()

print("\n" + "=" * 70)
print("1. FIELDS WE NEED")
print("=" * 70)
print(result1)


# ---------------------------------------------------------
# 2. Find file_sha values that appear more than once
# ---------------------------------------------------------

query2 = """
SELECT file_sha, COUNT(*) AS artifact_count
FROM GitSkills.artifacts
GROUP BY file_sha
HAVING COUNT(*) > 1
ORDER BY artifact_count DESC;
"""

result2 = con.execute(query2).fetchdf()

print("\n" + "=" * 70)
print("2. DUPLICATE file_sha VALUES")
print("=" * 70)
print(result2)


# ---------------------------------------------------------
# 3. Show artifacts with identical file_sha
#    with needed fields and sorted by first_commit_at
#    Ordered from biggest group to smallest group
# ---------------------------------------------------------

query3 = """
SELECT
    repo_full_name,
    path,
    file_sha,
    COUNT(*) OVER (PARTITION BY file_sha) AS artifacts_in_group,
    name,
    first_commit_at,
    last_commit_at
FROM GitSkills.artifacts
WHERE file_sha IN (
    SELECT file_sha
    FROM GitSkills.artifacts
    GROUP BY file_sha
    HAVING COUNT(*) > 1
)
ORDER BY artifacts_in_group DESC, file_sha, first_commit_at;
"""

result3 = con.execute(query3).fetchdf()

print("\n" + "=" * 70)
print("3. IDENTICAL ARTIFACTS")
print("=" * 70)
print(result3)


# ---------------------------------------------------------
# 4. Summary Table of the identical groups
#    Shows file_sha, artifact count, and the earliest + latest artifact
# ---------------------------------------------------------

query4 = """
SELECT
    file_sha,
    COUNT(*) AS artifact_count,
    COUNT(first_commit_at) AS artifacts_with_first_commit,
    MIN(first_commit_at) AS earliest_first_commit,
    MAX(first_commit_at) AS latest_first_commit
FROM GitSkills.artifacts
WHERE file_sha IN (
    SELECT file_sha
    FROM GitSkills.artifacts
    GROUP BY file_sha
    HAVING COUNT(*) > 1
)
GROUP BY file_sha
ORDER BY artifact_count DESC
"""

result4 = con.execute(query4).fetchdf()

print("\n" + "=" * 70)
print("4. SUMMARY TABLE OF IDENTICAL GROUPS")
print("=" * 70)
print(result4)


# ---------------------------------------------------------
# 5. Testing use of dedup_primary
# ---------------------------------------------------------

query5 = """
SELECT
    file_sha,
    repo_full_name,
    path,
    dedup_primary,
    first_commit_at,
    last_commit_at
FROM GitSkills.artifacts
WHERE file_sha IN (
    SELECT file_sha
    FROM GitSkills.artifacts
    GROUP BY file_sha
    HAVING COUNT(*) > 1
)
ORDER BY file_sha, dedup_primary DESC;
"""

result5 = con.execute(query5).fetchdf()

print("\n" + "=" * 70)
print("5. TESTING dedup_primary")
print("=" * 70)
print(result5)


# ---------------------------------------------------------
# 6. How many duplicate groups, how many with exactly 1 primary,
#    how many with at least 1 non-primary
# ---------------------------------------------------------

query6 = """
SELECT
    COUNT(DISTINCT file_sha) AS duplicate_groups,
    COUNT(DISTINCT CASE WHEN dedup_primary = 1 THEN file_sha END) AS groups_with_primary,
    COUNT(DISTINCT CASE WHEN dedup_primary = 0 THEN file_sha END) AS groups_with_non_primary
FROM GitSkills.artifacts
WHERE file_sha IN (
    SELECT file_sha
    FROM GitSkills.artifacts
    GROUP BY file_sha
    HAVING COUNT(*) > 1
);
"""

result6 = con.execute(query6).fetchdf()

print("\n" + "=" * 70)
print("6. DUPLICATE GROUP SUMMARY")
print("=" * 70)
print(result6)


# Close the database connection
con.close()

print("\n" + "=" * 70)
print("Duplicate analysis complete.")
print("=" * 70)

