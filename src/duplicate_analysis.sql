ATTACH 'data/agent_skills_sample.db' AS GitSkills;


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


-- Summary Table of the identical groups
-- Shows file_sha, artifact count, and the earliest + latest artifact
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
