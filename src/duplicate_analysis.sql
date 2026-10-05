ATTACH 'data/agent_skills_sample.db' AS GitSkills;

-- Analysis developed and tested in DuckDB first.
-- These queries were then incorporated into the Python pipeline
-- to make the analysis reproducible and automated.

-- Fields We Need 
SELECT
  repo_full_name,
  path,
  content,
  file_sha,
  name,
  description,
  first_commit_at,
  last_commit_at
  From GitSkills.artifacts


-- Find file_sha values that appear more than once
SELECT file_sha, COUNT(*) AS artifact_count
FROM GitSkills.artifacts
GROUP BY file_sha
HAVING COUNT(*) > 1
ORDER BY artifact_count DESC;


-- Show artifacts with identical file_sha with needed feilds and sorted by first_commit_at
-- Ordered from biggest group to smallest group
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


-- One row per duplicate file_sha group.
-- Gets the name and description from the earliest artifact in each group.

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


-- Testing use of dedup_primary
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


-- How many duplicate groups, how many with exactly 1 primary, how many with at least 1 non-primary
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
