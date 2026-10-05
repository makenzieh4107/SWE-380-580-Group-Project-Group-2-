"""
Duplicate Artifact Analysis for the GitSkills Dataset

This script connects to the approved GitSkills sample database and runs the
duplicate-analysis SQL queries used to investigate potential artifact reuse.
It examines the artifacts table to:

1. Retrieve the artifact fields needed for analysis.
2. Find artifacts that have the same file_sha, indicating identical content.
3. Group and display identical artifacts across repositories.
4. Summarize the size and available timestamps of each identical-content group, plus name and description of first one.
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
#    Shows file_sha, artifact count, and the earliest artifact name and description
# ---------------------------------------------------------

query4 = """
WITH ranked_artifacts AS (
    SELECT
        file_sha,
        name,
        description,
        first_commit_at,
        ROW_NUMBER() OVER (
            PARTITION BY file_sha
            ORDER BY first_commit_at ASC
        ) AS rn
    FROM GitSkills.artifacts
    WHERE file_sha IN (
        SELECT file_sha
        FROM GitSkills.artifacts
        GROUP BY file_sha
        HAVING COUNT(*) > 1
    )
)

SELECT
    file_sha,
    COUNT(*) AS artifact_count,
    MAX(CASE WHEN rn = 1 THEN name END) AS earliest_artifact_name,
    MAX(CASE WHEN rn = 1 THEN description END) AS earliest_artifact_description,
    MIN(first_commit_at) AS earliest_first_commit
FROM ranked_artifacts
GROUP BY file_sha
ORDER BY artifact_count DESC;
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




print("\n" + "=" * 70)
print("Duplicate analysis complete.")
print("=" * 70)




# ---------------------------------------------------------
# Distribution of Duplicate Group Sizes
# ---------------------------------------------------------

import matplotlib.pyplot as plt

# Find all duplicate groups and count how many artifacts
# have the same file_sha
group_sizes = con.execute("""
SELECT
    file_sha,
    COUNT(*) AS artifact_count
FROM GitSkills.artifacts
GROUP BY file_sha
HAVING COUNT(*) > 1
ORDER BY artifact_count DESC;
""").fetchdf()

# Print statistics about the duplicate groups
print("\nDuplicate Group Size Statistics")
print(group_sizes["artifact_count"].describe())


# ---------------------------------------------------------
# Categorize duplicate groups by size
# ---------------------------------------------------------

def categorize_size(size):
    if size == 2:
        return "2"
    elif size <= 5:
        return "3-5"
    elif size <= 10:
        return "6-10"
    elif size <= 20:
        return "11-20"
    elif size <= 50:
        return "21-50"
    elif size <= 100:
        return "51-100"
    elif size <= 150:
        return "101-150"
    else:
        return "151+"


# Apply the categories to each duplicate group
group_sizes["size_category"] = (
    group_sizes["artifact_count"].apply(categorize_size)
)


# ---------------------------------------------------------
# Count how many duplicate groups are in each category
# ---------------------------------------------------------

size_distribution = (
    group_sizes["size_category"]
    .value_counts()
    .reindex([
        "2",
        "3-5",
        "6-10",
        "11-20",
        "21-50",
        "51-100",
        "101-150",
        "151+"
    ])
    .fillna(0)
)


# Print the distribution in the terminal
print("\nDistribution of Duplicate Group Sizes")
print(size_distribution)


# ---------------------------------------------------------
# Save the distribution as a CSV table
# ---------------------------------------------------------

size_distribution.to_csv(
    "results/duplicate_group_size_distribution.csv",
    header=["number_of_groups"]
)

print(
    "\nSaved table to "
    "results/duplicate_group_size_distribution.csv"
)


# ---------------------------------------------------------
# Create the graph
# ---------------------------------------------------------

plt.figure(figsize=(10, 6))

plt.bar(
    size_distribution.index,
    size_distribution.values
)

plt.xlabel("Number of artifacts in identical-content group")
plt.ylabel("Number of duplicate groups")

plt.title(
    "Distribution of Duplicate Group Sizes"
)

plt.xticks(rotation=45)

plt.tight_layout()


# ---------------------------------------------------------
# Save the graph as a PNG
# ---------------------------------------------------------

plt.savefig(
    "results/duplicate_group_size_distribution.png",
    dpi=300
)

print(
    "Saved graph to "
    "results/duplicate_group_size_distribution.png"
)

# Display the graph
plt.show()




# Close the database connection
con.close()
